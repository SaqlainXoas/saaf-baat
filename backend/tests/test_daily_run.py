from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily_run  # noqa: E402

import run_pipeline  # noqa: E402


def test_september_24_drafts_recover_without_editor_or_full_pipeline(monkeypatch):
    token = "35995811518-1"
    now = datetime.now(timezone.utc).isoformat()
    drafts = [
        {"id": str(index), "cluster_id": str(index), "created_at": now,
         "is_published": False, "metadata": {"why_it_matters": "Public impact"}}
        for index in range(6)
    ]
    db = SimpleNamespace(client=MagicMock())
    monkeypatch.setattr(daily_run, "publication_drafts", lambda _db, _token: drafts)
    monkeypatch.setattr(daily_run, "default_config", lambda **kwargs: object())
    seen = []

    class RecoverOnly:
        def __init__(self, *, config, db):
            pass

        def embed_backfill(self, stats):
            seen.append("embeddings")

        def triage_backfill(self, stats):
            seen.append("triage")
            stats.embedding_status = "ok"
            stats.triage_status = "ok"
            stats.triage_unresolved = 0

    monkeypatch.setattr(daily_run, "PipelineOrchestrator", RecoverOnly)
    monkeypatch.setattr(daily_run, "write_heartbeat", lambda payload: seen.append(payload))
    heartbeat = {
        "edition_date": daily_run.edition_date(), "publication_token": token,
        "stats": {"embedding_status": "ok", "triage_status": "degraded",
                  "editorial_status": "ok", "feeds_inserted": 6,
                  "triage_failures": 50, "analyze_failures": 0},
    }

    result = daily_run.recover_processing(db, heartbeat, token)

    assert result["stats"]["triage_status"] == "ok"
    assert result["stats"]["triage_failures"] == 50
    assert result["stats"]["feeds_inserted"] == 6
    assert seen[:2] == ["embeddings", "triage"]


def test_backup_does_not_duplicate_a_published_edition(monkeypatch):
    db = SimpleNamespace()
    monkeypatch.setattr(daily_run, "create_db_client", lambda: db)
    monkeypatch.setattr(daily_run, "saved_state", lambda _db: {
        "edition_date": daily_run.edition_date(),
        "stats": {"publication_status": "ok"},
    })
    monkeypatch.setattr(daily_run.run_pipeline, "main", lambda *_: (_ for _ in ()).throw(AssertionError("reran")))

    assert daily_run.run_daily("backup", "new-token") == 0


def test_backup_keeps_an_honest_short_published_edition(monkeypatch):
    db = SimpleNamespace()
    monkeypatch.setattr(daily_run, "create_db_client", lambda: db)
    monkeypatch.setattr(daily_run, "saved_state", lambda _db: {
        "edition_date": daily_run.edition_date(),
        "stats": {"publication_status": "ok",
                  "short_brief_reason": "editorial_selected_fewer_than_six"},
    })
    monkeypatch.setattr(daily_run.run_pipeline, "main", lambda *_: (_ for _ in ()).throw(AssertionError("reran")))

    assert daily_run.run_daily("backup", "new-token") == 0


def test_backup_reuses_failed_attempt_drafts_without_restarting_generation(monkeypatch):
    db = SimpleNamespace()
    old_token = "morning-1"
    heartbeat = {
        "edition_date": daily_run.edition_date(), "publication_token": old_token,
        "stats": {"publication_status": "failed", "editorial_status": "ok", "feeds_inserted": 6},
    }
    monkeypatch.setattr(daily_run, "create_db_client", lambda: db)
    monkeypatch.setattr(daily_run, "saved_state", lambda _db: heartbeat)
    monkeypatch.setattr(daily_run, "published_today", lambda _db: False)
    monkeypatch.setattr(daily_run, "before_noon", lambda: True)
    monkeypatch.setattr(daily_run, "valid_drafts", lambda *_: [{}] * 6)
    monkeypatch.setattr(daily_run, "recover_processing", lambda *_: heartbeat)
    monkeypatch.setattr(daily_run, "check_health", lambda *_: 0)
    monkeypatch.setattr(daily_run.run_pipeline, "main", lambda *_: (_ for _ in ()).throw(AssertionError("regenerated")))
    published = []
    monkeypatch.setattr(daily_run, "publish", lambda _db, token, _heartbeat: (published.append(token), 6)[1])
    monkeypatch.setattr(daily_run, "published_stories", lambda *_: [])
    monkeypatch.setattr(daily_run, "wake_backend", lambda: None)
    monkeypatch.setattr(daily_run, "notify_frontend", lambda: None)
    monkeypatch.setattr(daily_run, "warm_frontend_cache", lambda *_: None)

    assert daily_run.run_daily("backup", "later-1") == 0
    assert published == [old_token]


def test_expired_drafts_cannot_be_promoted(monkeypatch):
    from datetime import timedelta

    old = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    db = SimpleNamespace()
    monkeypatch.setattr(daily_run, "publication_drafts", lambda *_: [
        {"id": "one", "cluster_id": "one", "created_at": old,
         "is_published": False, "metadata": {"why_it_matters": "Impact"}}
    ])

    assert daily_run.valid_drafts(db, "old-token") == []


def test_staged_drafts_do_not_advance_last_successful_publication(monkeypatch, tmp_path):
    path = tmp_path / "heartbeat.json"
    path.write_text('{"last_successful_run_at": "2026-09-23T05:00:00Z"}')
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(path))
    monkeypatch.setenv("SAAF_STAGE_PUBLICATION", "1")
    stats = SimpleNamespace(feeds_inserted=6, as_dict=lambda: {"feeds_inserted": 6})

    run_pipeline._write_pipeline_heartbeat(daily_run.BACKEND, stats)

    import json
    assert json.loads(path.read_text())["last_successful_run_at"] == "2026-09-23T05:00:00Z"
