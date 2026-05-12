from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.feed import get_db
from src.db.client import DatabaseError
from src.db.models import AnalyzedFeed


class _FakeDB:
    def __init__(self, items: List[AnalyzedFeed]):
        self._items = items

    def get_analyzed_feed(
        self,
        category: Optional[str] = None,
        impact_label: Optional[str] = None,
        limit: int = 50,
        published_only: bool = True,
    ) -> List[AnalyzedFeed]:
        items = self._items
        if category:
            items = [i for i in items if i.category == category]
        if impact_label:
            items = [i for i in items if impact_label in (i.impact_labels or [])]
        return items[:limit]


def test_feed_route_returns_items():
    items = [
        AnalyzedFeed(
            cluster_id=uuid4(),
            headline="Test story",
            summary="Two-line snippet.",
            category="economy",
            impact_labels=["💳 WALLET"],
            source_attribution={"dawn": 1},
        )
    ]
    fake_db = _FakeDB(items)

    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/api/feed?limit=10")
    assert res.status_code == 200
    payload = res.json()
    assert payload["stories"][0]["headline"] == "Test story"
    assert payload["stories"][0]["snippet"] == "Two-line snippet."
    assert payload["stories"][0]["story_id"]
    assert payload["stories"][0]["sources"][0]["source"] == "dawn"
    assert payload["is_fresh"] is True


def test_feed_route_returns_503_when_db_unavailable():
    class _FailDB:
        def get_analyzed_feed(self, **_kwargs):
            raise DatabaseError("down")

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FailDB()  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/api/feed?limit=10")
    assert res.status_code == 503
    assert "Database unavailable" in res.json()["detail"]


def test_feed_route_returns_empty_list_when_no_rows():
    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDB([])  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/api/feed?limit=10")
    assert res.status_code == 200
    assert res.json() == {"generated_at": None, "is_fresh": False, "stories": []}


def test_feed_route_handles_missing_source_attribution_and_summary():
    items = [
        AnalyzedFeed(
            cluster_id=uuid4(),
            headline="No attribution story",
            summary=None,
            category="economy",
            impact_labels=[],
            source_attribution={},
        )
    ]
    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDB(items)  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/api/feed?limit=10")
    assert res.status_code == 200
    payload = res.json()
    assert payload["stories"][0]["snippet"] == ""
    assert payload["stories"][0]["sources"] == []


def test_feed_route_sorts_by_editorial_priority_before_created_at():
    older_high_priority = AnalyzedFeed(
        cluster_id=uuid4(),
        created_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        headline="Higher-priority story",
        summary="Should lead despite being older.",
        category="economy",
        impact_labels=["💳 WALLET"],
        source_attribution={"dawn": 2},
        metadata={"editorial_priority": 95, "deterministic_publish_score": 80},
    )
    newer_lower_priority = AnalyzedFeed(
        cluster_id=uuid4(),
        created_at=datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc),
        headline="Lower-priority story",
        summary="Newer but weaker.",
        category="economy",
        impact_labels=["💳 WALLET"],
        source_attribution={"tribune": 1},
        metadata={"editorial_priority": 70, "deterministic_publish_score": 40},
    )

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDB([newer_lower_priority, older_high_priority])  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get("/api/feed?limit=10")
    assert res.status_code == 200
    payload = res.json()
    assert payload["stories"][0]["headline"] == "Higher-priority story"
    assert payload["stories"][1]["headline"] == "Lower-priority story"
