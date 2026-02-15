from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.health import get_db
from src.db.models import AnalyzedFeed


def test_docs_and_health_endpoints(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(tmp_path / "pipeline_heartbeat.json"))
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)

    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return [
                AnalyzedFeed(
                    cluster_id=uuid4(),
                    headline="h",
                    summary="s",
                    category="economy",
                    created_at=now_utc,
                )
            ]

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["latest_feed_created_at"].startswith(now_utc.isoformat().split("+")[0])
    assert body["last_successful_pipeline_run_at"].startswith(now_utc.isoformat().split("+")[0])
    assert body["pipeline_stale_after_hours"] >= 1
    assert body["pipeline_is_stale"] is False

    docs = client.get("/docs")
    assert docs.status_code == 200


def test_health_degraded_when_db_unavailable(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(tmp_path / "pipeline_heartbeat.json"))

    class _FakeUnhealthyDB:
        def is_connected(self) -> bool:
            return False

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeUnhealthyDB()  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded"
    assert body["database"] == "disconnected"
    assert body["latest_feed_created_at"] is None
    assert body["last_successful_pipeline_run_at"] is None
    assert body["pipeline_stale_after_hours"] >= 1
    assert body["pipeline_is_stale"] is True


def test_cors_allows_configured_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv(
        "BACKEND_CORS_ALLOW_ORIGINS",
        "http://localhost:3000,https://app.example.com",
    )
    app = create_app()
    client = TestClient(app)
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_blocks_unconfigured_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "https://app.example.com")
    app = create_app()
    client = TestClient(app)
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.status_code == 200
    assert "access-control-allow-origin" not in res.headers


def test_cors_rejects_wildcard_in_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="Wildcard CORS origin"):
        create_app()


def test_health_uses_pipeline_heartbeat(tmp_path, monkeypatch: pytest.MonkeyPatch):
    heartbeat = tmp_path / "pipeline_heartbeat.json"
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    heartbeat.write_text(
        json.dumps({"last_successful_pipeline_run_at": now_utc.isoformat().replace("+00:00", "Z")}),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))
    monkeypatch.setenv("SAAF_FEED_STALE_AFTER_HOURS", "6")

    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return []

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["database"] == "connected"
    assert body["last_successful_pipeline_run_at"].startswith(now_utc.isoformat().split("+")[0])
    assert body["pipeline_is_stale"] is False
