from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_hosted import publish  # noqa: E402

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
