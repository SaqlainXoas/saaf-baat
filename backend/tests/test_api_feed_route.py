from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.feed import get_db
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
    assert isinstance(payload, list) and len(payload) == 1
    assert payload[0]["headline"] == "Test story"
    assert payload[0]["snippet"] == "Two-line snippet."
    assert payload[0]["story_id"]
    assert payload[0]["sources"][0]["source"] == "dawn"
