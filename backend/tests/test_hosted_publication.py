from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_hosted import publish, warm_frontend_cache  # noqa: E402

from src.db.client import SupabaseClient  # noqa: E402
from src.db.models import AnalyzedFeed  # noqa: E402


def heartbeat(count=6, **overrides):
    return {"stats": {"embedding_status": "ok", "triage_status": "ok", "editorial_status": "ok", "feeds_inserted": count, **overrides}}


def test_drafts_remain_private_until_atomic_promotion(monkeypatch):
    monkeypatch.setenv("SAAF_STAGE_PUBLICATION", "1")
    monkeypatch.setenv("SAAF_PUBLICATION_TOKEN", "run-123")
    db = SupabaseClient(url="https://example.supabase.co", key="test")
    db._client = MagicMock()
    row = AnalyzedFeed(cluster_id=uuid4(), headline="A grounded story", category="economy")
    db._client.table.return_value.insert.return_value.execute.return_value.data = [{"id": str(row.id)}]
    db.insert_analyzed_feed(row)
    payload = db._client.table.return_value.insert.call_args.args[0]
    assert payload["is_published"] is False
    assert payload["metadata"]["publication_token"] == "run-123"
    assert row.is_published is True  # staging doesn't mutate the pipeline's model
    db._client.rpc.return_value.execute.return_value.data = 6
    assert publish(db, "run-123", heartbeat()) == 6
    assert db._client.rpc.call_args.args[0] == "publish_brief"


@pytest.mark.parametrize("stats", [heartbeat(0), heartbeat(13), heartbeat(editorial_status="unavailable"), heartbeat(analyze_failures=1)])
def test_invalid_run_cannot_promote(monkeypatch, stats):
    monkeypatch.setenv("SAAF_STAGE_PUBLICATION", "1")
    db = SimpleNamespace(client=MagicMock())
    with pytest.raises(ValueError):
        publish(db, "run-123", stats)
    db.client.rpc.assert_not_called()


def test_missing_staging_token_cannot_write(monkeypatch):
    monkeypatch.setenv("SAAF_STAGE_PUBLICATION", "1")
    monkeypatch.delenv("SAAF_PUBLICATION_TOKEN", raising=False)
    db = SupabaseClient(url="https://example.supabase.co", key="test")
    db._client = MagicMock()
    with pytest.raises(Exception, match="publication token"):
        db.insert_analyzed_feed(AnalyzedFeed(cluster_id=uuid4(), headline="h", category="economy"))
    db._client.table.assert_not_called()



class TestWarmFrontendCache:
    """Revalidating empties Vercel's cache; something has to refill it.

    Overnight nothing does. The run finishes around 06:20, Render idles back to
    sleep fifteen minutes later, and the morning's first reader arrives to an
    empty cache and a sleeping API - so Vercel builds the page on the spot and
    the reader waits out a cold start for a brief that was ready hours earlier.
    This is the run paying that cost itself, while everything is still awake.
    """

    def _capture(self, monkeypatch, response_status=200, raises=None):
        seen = {}

        class _Response:
            status = response_status

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(request, timeout=None):
            seen["url"] = getattr(request, "full_url", request)
            seen["timeout"] = timeout
            if raises is not None:
                raise raises
            return _Response()

        monkeypatch.setattr("publish_hosted.urllib.request.urlopen", fake_urlopen)
        return seen

    def test_warms_the_site_origin_taken_from_the_revalidate_url(self, monkeypatch):
        # No new secret: the origin is already in the URL the pipeline pings.
        monkeypatch.setenv("SAAF_REVALIDATE_URL", "https://saaf-baat.vercel.app/api/revalidate")
        seen = self._capture(monkeypatch)

        warm_frontend_cache()

        assert seen["url"] == "https://saaf-baat.vercel.app/"

    def test_allows_long_enough_for_a_cold_start(self, monkeypatch):
        # This is the request that may have to wake Render. Paying 90s here is
        # the whole point of paying it instead of a reader.
        monkeypatch.setenv("SAAF_REVALIDATE_URL", "https://saaf-baat.vercel.app/api/revalidate")
        seen = self._capture(monkeypatch)

        warm_frontend_cache()

        assert seen["timeout"] >= 60

    def test_no_url_configured_is_not_an_error(self, monkeypatch, capsys):
        monkeypatch.delenv("SAAF_REVALIDATE_URL", raising=False)

        warm_frontend_cache()

        assert "first reader will rebuild" in capsys.readouterr().out

    def test_a_malformed_url_is_skipped_rather_than_guessed_at(self, monkeypatch, capsys):
        monkeypatch.setenv("SAAF_REVALIDATE_URL", "not-a-url")

        warm_frontend_cache()

        assert "site origin" in capsys.readouterr().out

    def test_a_failed_warm_never_fails_the_run(self, monkeypatch, capsys):
        # The edition is already published by the time this runs. A warm cache
        # is an optimisation; losing it must not lose the edition.
        monkeypatch.setenv("SAAF_REVALIDATE_URL", "https://saaf-baat.vercel.app/api/revalidate")
        self._capture(monkeypatch, raises=OSError("connection reset"))

        warm_frontend_cache()

        assert "could not warm" in capsys.readouterr().out


def test_the_warm_runs_after_the_revalidate_not_before(monkeypatch):
    """Order matters: warming before the purge would cache the old edition."""
    import publish_hosted

    calls = []
    monkeypatch.setattr(publish_hosted, "wake_backend", lambda: calls.append("wake"))
    monkeypatch.setattr(publish_hosted, "notify_frontend", lambda: calls.append("revalidate"))
    monkeypatch.setattr(publish_hosted, "warm_frontend_cache", lambda: calls.append("warm"))
    monkeypatch.setattr(publish_hosted, "publish", lambda *a, **k: 6)
    monkeypatch.setattr(publish_hosted, "create_db_client", lambda: SimpleNamespace())
    monkeypatch.setattr(publish_hosted, "heartbeat_path", lambda: Path("/nonexistent"))
    monkeypatch.setattr(
        publish_hosted.json, "loads", lambda *a, **k: {"stats": {"feeds_inserted": 6}}
    )
    monkeypatch.setattr(Path, "read_text", lambda self: "{}")
    monkeypatch.setenv("SAAF_DB_BACKEND", "supabase")
    monkeypatch.setenv("SAAF_PUBLICATION_TOKEN", "token")
    monkeypatch.setattr(sys, "argv", ["publish_hosted.py"])

    publish_hosted.main()

    assert calls == ["wake", "revalidate", "warm"]
