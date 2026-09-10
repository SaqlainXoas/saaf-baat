from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.feed import _is_fresh, get_db
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


def test_freshness_requires_the_completed_morning_edition():
    now = datetime(2026, 8, 28, 5, 0, tzinfo=timezone.utc)  # 10:00 PKT

    assert _is_fresh(
        datetime(2026, 8, 27, 19, 25, tzinfo=timezone.utc), now=now
    ) is False  # 00:25 PKT: an overnight run, not the morning edition
    assert _is_fresh(
        datetime(2026, 8, 28, 2, 5, tzinfo=timezone.utc), now=now
    ) is True  # 07:05 PKT today


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


def _feed_row(*, headline: str, metadata: dict) -> AnalyzedFeed:
    return AnalyzedFeed(
        cluster_id=uuid4(),
        created_at=datetime(2026, 8, 25, 0, 15, tzinfo=timezone.utc),
        headline=headline,
        summary="Summary.",
        category="politics",
        impact_labels=["\U0001f3db\ufe0f GOVERNANCE"],
        source_attribution={"dawn": 1},
        metadata=metadata,
    )


def test_feed_serves_only_the_latest_brief_not_every_run(monkeypatch):
    """Analyzed feeds accumulate; the brief must not.

    A live check served eleven cards for an eight-card brief, two of them the
    same Tehran story under two headlines written hours apart. Each published
    card carries the run that produced it.
    """
    from src.api.routes import feed as feed_route

    today = _feed_row(
        headline="Army Chief and Interior Minister arrive in Tehran for talks",
        metadata={"why_it_matters": "Traders at the border face new checks.",
                  "brief_run_at": "2026-08-25T00:15:00+00:00"},
    )
    yesterday = _feed_row(
        headline="Army Chief travels to Tehran for talks on regional tensions",
        metadata={"why_it_matters": "Same event, previous run.",
                  "brief_run_at": "2026-08-24T16:36:00+00:00"},
    )

    kept = feed_route._latest_brief_only([yesterday, today])

    assert [f.headline for f in kept] == [today.headline]


def test_feed_keeps_unstamped_rows_rather_than_serving_nothing():
    """Rows written before the stamp existed still make a brief."""
    from src.api.routes import feed as feed_route

    rows = [_feed_row(headline="An older card", metadata={"why_it_matters": "x"})]

    assert feed_route._latest_brief_only(rows) == rows


def test_feed_never_ships_the_story_analysis_blob():
    """The homepage renders no analysis, so it must not carry one.

    The DTO schema was unchanged, so this looked like a satisfied contract -
    but the whole story_analysis payload rode along inside metadata, 46% of a
    34KB response, internal claim evidence included.
    """
    feed = AnalyzedFeed(
        cluster_id=uuid4(),
        headline="PIMS nursery fire kills newborns",
        summary="A fire killed newborns at PIMS.",
        category="health",
        source_attribution={"dawn": 1},
        metadata={
            "why_it_matters": "Parents of newborns face an inquiry with no findings yet.",
            "story_analysis": {
                "analysis": "A long multi-source analysis." * 40,
                "question": "Which office was responsible?",
                "claims": [{"text": "internal", "supporting_article_ids": ["x"]}],
            },
        },
    )
    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDB([feed])  # type: ignore[assignment]

    body = TestClient(app).get("/api/feed").json()

    assert len(body["stories"]) == 1
    assert "story_analysis" not in body["stories"][0]["metadata"]
    assert "analysis" not in json.dumps(body["stories"][0]["metadata"])
