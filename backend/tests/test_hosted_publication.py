from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_hosted import publish, published_stories, warm_frontend_cache  # noqa: E402

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
    This is the run paying that cost itself, while everything is still awake,
    and checking that what Vercel now serves is the new edition.
    """

    ORIGIN = "https://saaf-baat.vercel.app/"
    STORIES = [
        {"id": "lead", "headline": "Three terrorists killed in Mastung operation"},
        {"id": "second", "headline": "Petrol price cut by Rs5 & diesel held"},
    ]

    def _serve(self, monkeypatch, pages):
        """pages maps a URL to the responses it returns in order; the last repeats."""
        import publish_hosted

        monkeypatch.setenv("SAAF_REVALIDATE_URL", f"{self.ORIGIN}api/revalidate")
        monkeypatch.setattr(publish_hosted, "WARM_RETRY_SECONDS", 0)
        seen = []

        class _Response:
            def __init__(self, status, body):
                self.status = status
                self._body = body

            def read(self):
                return self._body.encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(request, timeout=None):
            url = request.full_url
            seen.append((url, timeout))
            queue = pages[url]
            result = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(result, Exception):
                raise result
            return _Response(*result)

        monkeypatch.setattr("publish_hosted.urllib.request.urlopen", fake_urlopen)
        return seen

    def _home(self, *ids):
        return "".join(f'<a href="/stories/{i}">' for i in ids)

    def _story(self, headline):
        # Next escapes the headline in HTML; the check must survive that.
        return f"<h1>{headline.replace('&', '&amp;')}</h1>"

    def _all_current(self):
        return {
            self.ORIGIN: [(200, self._home("lead", "second"))],
            f"{self.ORIGIN}stories/lead": [(200, self._story(self.STORIES[0]["headline"]))],
            f"{self.ORIGIN}stories/second": [(200, self._story(self.STORIES[1]["headline"]))],
        }

    def test_warms_the_home_page_and_every_published_story(self, monkeypatch):
        seen = self._serve(monkeypatch, self._all_current())

        assert warm_frontend_cache(self.STORIES) is True

        assert [url for url, _ in seen] == [
            self.ORIGIN,
            f"{self.ORIGIN}stories/lead",
            f"{self.ORIGIN}stories/second",
        ]

    def test_allows_long_enough_for_a_cold_start(self, monkeypatch):
        # These are the requests that may have to wake Render. Paying 90s here
        # is the whole point of paying it instead of a reader.
        seen = self._serve(monkeypatch, self._all_current())

        warm_frontend_cache(self.STORIES)

        assert all(timeout >= 60 for _, timeout in seen)

    def test_retries_while_vercel_still_serves_the_previous_edition(self, monkeypatch):
        # The first request after a revalidation gets the old page while Vercel
        # rebuilds in the background. A 200 of yesterday's brief is not a warm.
        pages = self._all_current()
        pages[self.ORIGIN] = [(200, self._home("yesterday")), (200, self._home("lead", "second"))]
        seen = self._serve(monkeypatch, pages)

        assert warm_frontend_cache(self.STORIES) is True
        assert [url for url, _ in seen].count(self.ORIGIN) == 2

    def test_retries_a_story_page_that_failed_to_render(self, monkeypatch):
        # 2026-09-15: the lead story's first build hit a 503 and was cached as
        # an error page. The page now throws (HTTP 500), and the warm retries.
        import urllib.error

        pages = self._all_current()
        pages[f"{self.ORIGIN}stories/lead"] = [
            urllib.error.HTTPError(f"{self.ORIGIN}stories/lead", 500, "error", {}, None),
            (200, self._story(self.STORIES[0]["headline"])),
        ]
        seen = self._serve(monkeypatch, pages)

        assert warm_frontend_cache(self.STORIES) is True
        assert [url for url, _ in seen].count(f"{self.ORIGIN}stories/lead") == 2

    def test_gives_up_with_a_visible_warning_but_never_fails_the_run(self, monkeypatch, capsys):
        # The edition is already published by the time this runs. A warm cache
        # is an optimisation; losing it must not lose the edition.
        import publish_hosted

        pages = self._all_current()
        pages[f"{self.ORIGIN}stories/second"] = [OSError("connection reset")]
        seen = self._serve(monkeypatch, pages)

        assert warm_frontend_cache(self.STORIES) is False

        out = capsys.readouterr().out
        assert "::warning::could not warm story second" in out
        assert [url for url, _ in seen].count(f"{self.ORIGIN}stories/second") == publish_hosted.WARM_ATTEMPTS

    def test_the_whole_warm_ends_inside_its_time_budget(self, monkeypatch, capsys):
        # Unbounded, 13 pages x 6 attempts x (90s + 15s) is over two hours. The
        # workflow is killed at 45 minutes, and a killed job runs "Record failed
        # run" and marks an already-published edition as failed.
        import publish_hosted

        clock = {"now": 0.0}
        timeouts = []

        def hanging_urlopen(request, timeout=None):
            timeouts.append(timeout)
            clock["now"] += timeout  # every request hangs until it times out
            raise OSError("timed out")

        def advance(seconds):
            clock["now"] += seconds

        monkeypatch.setenv("SAAF_REVALIDATE_URL", f"{self.ORIGIN}api/revalidate")
        monkeypatch.setattr(
            publish_hosted, "time", SimpleNamespace(monotonic=lambda: clock["now"], sleep=advance)
        )
        monkeypatch.setattr("publish_hosted.urllib.request.urlopen", hanging_urlopen)
        stories = [{"id": f"story-{i}", "headline": "h"} for i in range(12)]

        assert warm_frontend_cache(stories) is False

        assert clock["now"] <= publish_hosted.WARM_BUDGET_SECONDS
        assert all(timeout <= publish_hosted.WARM_REQUEST_TIMEOUT for timeout in timeouts)
        out = capsys.readouterr().out
        assert "warm budget" in out
        assert "left for readers to build" in out

    def test_the_budget_leaves_room_inside_the_workflow_timeout(self):
        # 45-minute job limit; the slowest recent daily run took 22 minutes.
        import publish_hosted

        assert publish_hosted.WARM_BUDGET_SECONDS <= 10 * 60

    def test_without_story_ids_it_still_warms_the_home_page(self, monkeypatch):
        seen = self._serve(monkeypatch, self._all_current())

        assert warm_frontend_cache([]) is True
        assert [url for url, _ in seen] == [self.ORIGIN]

    def test_no_url_configured_is_not_an_error(self, monkeypatch, capsys):
        monkeypatch.delenv("SAAF_REVALIDATE_URL", raising=False)

        warm_frontend_cache(self.STORIES)

        assert "first reader will rebuild" in capsys.readouterr().out

    def test_a_malformed_url_is_skipped_rather_than_guessed_at(self, monkeypatch, capsys):
        monkeypatch.setenv("SAAF_REVALIDATE_URL", "not-a-url")

        warm_frontend_cache(self.STORIES)

        assert "site origin" in capsys.readouterr().out


def test_published_stories_reads_this_runs_promoted_cards():
    db = SimpleNamespace(client=MagicMock())
    query = db.client.table.return_value.select.return_value.eq.return_value.eq.return_value
    query.execute.return_value.data = [{"cluster_id": "lead", "headline": "Mastung operation"}]

    assert published_stories(db, "run-123") == [{"id": "lead", "headline": "Mastung operation"}]
    db.client.table.return_value.select.return_value.eq.assert_called_with("metadata->>publication_token", "run-123")


def test_published_stories_failure_is_a_warning_not_a_failed_run(capsys):
    db = SimpleNamespace(client=MagicMock())
    db.client.table.side_effect = RuntimeError("supabase down")

    assert published_stories(db, "run-123") == []
    assert "::warning::" in capsys.readouterr().out


def test_the_warm_runs_after_the_revalidate_not_before(monkeypatch):
    """Order matters: warming before the purge would cache the old edition."""
    import publish_hosted

    calls = []
    stories = [{"id": "lead", "headline": "h"}]
    monkeypatch.setattr(publish_hosted, "published_stories", lambda db, token: stories)
    monkeypatch.setattr(publish_hosted, "wake_backend", lambda: calls.append("wake"))
    monkeypatch.setattr(publish_hosted, "notify_frontend", lambda: calls.append("revalidate"))
    monkeypatch.setattr(
        publish_hosted, "warm_frontend_cache", lambda warmed: calls.append(("warm", warmed))
    )
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

    assert calls == ["wake", "revalidate", ("warm", stories)]
