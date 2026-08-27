from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
    assert body["last_run_at"] is None
    assert body["last_successful_run_at"].startswith(now_utc.isoformat().split("+")[0])
    assert body["last_successful_run_source"] == "latest_feed_created_at"
    assert body["pipeline_stale_after_hours"] == 28
    assert body["pipeline_is_stale"] is False
    assert "fallback freshness signal" in body["pipeline_status_reason"]
    assert body["degraded_sources"] == []
    assert body["source_article_counts"] == {}

    root = client.get("/")
    assert root.status_code == 200
    root_body = root.json()
    assert root_body["status"] == "ok"
    assert root_body["service"] == "Saaf Baat API"

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
    assert body["last_run_at"] is None
    assert body["last_successful_run_at"] is None
    assert body["last_successful_run_source"] == "none"
    assert body["pipeline_stale_after_hours"] == 28
    assert body["pipeline_is_stale"] is True
    assert body["pipeline_status_reason"] == "Database unavailable; pipeline freshness cannot be confirmed."


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
        json.dumps(
            {
                "last_run_at": now_utc.isoformat().replace("+00:00", "Z"),
                "last_successful_run_at": now_utc.isoformat().replace("+00:00", "Z"),
                "source_article_counts": {"dawn": 0, "geo": 3},
                "degraded_sources": ["dawn"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))

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
    assert body["last_run_at"].startswith(now_utc.isoformat().split("+")[0])
    assert body["last_successful_run_at"].startswith(now_utc.isoformat().split("+")[0])
    assert body["last_successful_run_source"] == "heartbeat"
    assert body["pipeline_is_stale"] is False
    assert body["pipeline_status_reason"] == "Pipeline heartbeat is within the 28-hour freshness window."
    assert body["degraded_sources"] == ["dawn"]
    assert body["source_article_counts"] == {"dawn": 0, "geo": 3}


def test_health_reports_stale_db_fallback_when_heartbeat_missing(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(tmp_path / "pipeline_heartbeat.json"))
    stale_feed_time = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=40)

    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return [
                AnalyzedFeed(
                    cluster_id=uuid4(),
                    headline="Old brief",
                    summary="s",
                    category="economy",
                    created_at=stale_feed_time,
                )
            ]

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["last_run_at"] is None
    assert body["last_successful_run_at"].startswith(stale_feed_time.isoformat().split("+")[0])
    assert body["last_successful_run_source"] == "latest_feed_created_at"
    assert body["pipeline_is_stale"] is True
    assert "heartbeat is missing" in body["pipeline_status_reason"]
    assert "newest analyzed feed row is older than the 28-hour freshness window" in body["pipeline_status_reason"]


def test_health_reads_legacy_last_successful_pipeline_key(tmp_path, monkeypatch: pytest.MonkeyPatch):
    heartbeat = tmp_path / "pipeline_heartbeat.json"
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    heartbeat.write_text(
        json.dumps(
            {
                "last_successful_pipeline_run_at": now_utc.isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))

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
    assert body["last_successful_run_at"].startswith(now_utc.isoformat().split("+")[0])
    assert body["last_successful_run_source"] == "heartbeat"
    assert body["pipeline_is_stale"] is False


def test_health_surfaces_quarantined_endpoints(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A dead feed must be legible from /health, not only from the logs."""
    heartbeat = tmp_path / "pipeline_heartbeat.json"
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    heartbeat.write_text(
        json.dumps(
            {
                "last_run_at": now_utc.isoformat().replace("+00:00", "Z"),
                "last_successful_run_at": now_utc.isoformat().replace("+00:00", "Z"),
                "source_article_counts": {"dawn": 12, "thenews": 4},
                "degraded_sources": ["thenews:rss:STALE", "tribune:sitemap:no-dates"],
                "endpoint_health": [
                    {
                        "source": "dawn",
                        "channel": "rss",
                        "url": "https://www.dawn.com/feeds/pakistan",
                        "status": "ok",
                        "newest_age_hours": 0.4,
                        "item_count": 30,
                    },
                    {
                        "source": "thenews",
                        "channel": "rss",
                        "url": "https://www.thenews.com.pk/rss/1/1",
                        "status": "STALE",
                        "newest_age_hours": 6630.6,
                        "item_count": 0,
                    },
                    {
                        "source": "tribune",
                        "channel": "sitemap",
                        "url": "https://tribune.com.pk/sitemap/sitemap_main.xml",
                        "status": "no-dates",
                        "newest_age_hours": None,
                        "item_count": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))

    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return []

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]
    client = TestClient(app)

    body = client.get("/health").json()

    assert body["quarantined_endpoint_count"] == 2
    assert body["degraded_sources"] == ["thenews:rss:STALE", "tribune:sitemap:no-dates"]
    stale = next(row for row in body["endpoint_health"] if row["status"] == "STALE")
    assert stale["url"] == "https://www.thenews.com.pk/rss/1/1"
    assert stale["newest_age_hours"] == 6630.6


def test_health_endpoint_health_defaults_to_empty(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ALLOW_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(tmp_path / "missing.json"))

    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return []

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]
    body = TestClient(app).get("/health").json()

    assert body["endpoint_health"] == []
    assert body["quarantined_endpoint_count"] == 0


def test_health_reports_editorial_unavailability(tmp_path, monkeypatch):
    """Total LLM unavailability must be loud, not a silently flatter brief (I-5)."""
    import json

    from fastapi.testclient import TestClient

    from main import app

    heartbeat = tmp_path / "heartbeat.json"
    heartbeat.write_text(
        json.dumps(
            {
                "last_run_at": "2026-08-24T05:00:00Z",
                "last_successful_run_at": "2026-08-24T05:00:00Z",
                "stats": {
                    "editorial_status": "unavailable",
                    "triage_status": "ok",
                    "triage_calls": 7,
                    "adjudication_calls": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))
    from src.api import deps

    deps._client.cache_clear()

    payload = TestClient(app).get("/health").json()

    assert payload["editorial_status"] == "unavailable"
    assert payload["triage_status"] == "ok"
    assert payload["llm_calls"] == {
        "triage": 7,
        "adjudication": 1,
        "story_analysis": 0,
    }
    assert payload["status"] == "degraded"
    assert "template copy" in payload["pipeline_status_reason"]


def test_feed_guarantees_why_it_matters_on_every_card(tmp_path):
    """The contract the homepage used to enforce with a silent filter (I-7)."""
    from datetime import datetime, timezone
    from uuid import uuid4

    from src.api.routes.feed import _to_story_card
    from src.db.models import AnalyzedFeed

    feed = AnalyzedFeed(
        cluster_id=uuid4(),
        headline="A development in Pakistan today",
        summary="A summary.",
        category="economy",
        impact_labels=["💳 WALLET"],
        source_attribution={"dawn": 1},
        classification_confidence=0.8,
        created_at=datetime.now(timezone.utc),
        metadata={},
    )

    card = _to_story_card(feed)

    assert card.metadata["why_it_matters"].strip()
    assert card.metadata["why_it_matters_source"] == "api_contract_default"


def test_health_is_degraded_when_triage_failed(tmp_path, monkeypatch):
    """An untriaged cluster is not publishable, so a bad triage run is not "ok".

    triage_status was reported but excluded from the verdict, so a run that
    triaged nothing - and therefore published only what it could describe -
    still answered status "ok".
    """
    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return []

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]

    heartbeat = tmp_path / "heartbeat.json"
    heartbeat.write_text(
        json.dumps(
            {
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_successful_run_at": datetime.now(timezone.utc).isoformat(),
                "stats": {
                    "editorial_status": "ok",
                    "triage_status": "unavailable",
                    "triage_calls": 0,
                    "adjudication_calls": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))

    from src.api import deps

    deps._client.cache_clear()

    payload = TestClient(app).get("/health").json()

    assert payload["triage_status"] == "unavailable"
    assert payload["status"] == "degraded"
    assert "Triage was unavailable" in payload["pipeline_status_reason"]


def test_health_is_degraded_when_story_analysis_is_partial(tmp_path, monkeypatch):
    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return []

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]
    heartbeat = tmp_path / "story-analysis-heartbeat.json"
    heartbeat.write_text(
        json.dumps(
            {
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_successful_run_at": datetime.now(timezone.utc).isoformat(),
                "stats": {
                    "editorial_status": "ok",
                    "story_analysis_status": "partial",
                    "story_analysis_calls": 8,
                    "story_analysis_successes": 7,
                    "story_analysis_question_rejections": 2,
                    "story_analysis_fallbacks": 1,
                    "story_analysis_failures": 1,
                    "triage_status": "ok",
                    "embedding_status": "ok",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))

    payload = TestClient(app).get("/health").json()

    assert payload["status"] == "degraded"
    assert payload["story_analysis_status"] == "partial"
    assert payload["llm_calls"]["story_analysis"] == 8
    # Calls alone cannot tell "ran eight times and worked" from "ran eight
    # times and fell back every time". All five are recorded; all five ship.
    assert payload["story_analysis"] == {
        "calls": 8,
        "successes": 7,
        "question_rejections": 2,
        "fallbacks": 1,
        "failures": 1,
    }
    assert "detail pages" in payload["pipeline_status_reason"]


def test_health_story_analysis_counters_default_to_zero(tmp_path, monkeypatch):
    class _FakeHealthyDB:
        def is_connected(self) -> bool:
            return True

        def get_analyzed_feed(self, limit: int = 1, published_only: bool = False):
            return []

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeHealthyDB()  # type: ignore[assignment]
    heartbeat = tmp_path / "empty-stats-heartbeat.json"
    heartbeat.write_text(json.dumps({"stats": {}}), encoding="utf-8")
    monkeypatch.setenv("SAAF_PIPELINE_HEARTBEAT_FILE", str(heartbeat))

    payload = TestClient(app).get("/health").json()

    assert payload["story_analysis"] == {
        "calls": 0,
        "successes": 0,
        "question_rejections": 0,
        "fallbacks": 0,
        "failures": 0,
    }
