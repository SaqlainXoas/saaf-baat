from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.stories import get_db
from src.db.models import AnalyzedFeed, Cluster, RawArticle


class _FakeDB:
    def __init__(self, cluster_id: UUID, feed: AnalyzedFeed, cluster: Cluster, articles: List[RawArticle]):
        self._cluster_id = cluster_id
        self._feed = feed
        self._cluster = cluster
        self._articles = articles

    def get_analyzed_feed_by_cluster_id(self, cluster_id: UUID) -> AnalyzedFeed:
        assert cluster_id == self._cluster_id
        return self._feed

    def get_cluster_by_id(self, cluster_id: UUID) -> Cluster:
        assert cluster_id == self._cluster_id
        return self._cluster

    def get_articles_by_ids(self, article_ids):
        ids = {UUID(str(aid)) for aid in article_ids}
        return [a for a in self._articles if a.id in ids]


def test_story_detail_includes_articles():
    cluster_id = uuid4()
    feed = AnalyzedFeed(
        cluster_id=cluster_id,
        headline="Test story",
        summary="Snippet here.",
        category="economy",
        impact_labels=["💳 WALLET"],
        source_attribution={"dawn": 1, "geo": 1},
    )
    a1 = RawArticle(
        id=uuid4(),
        source="dawn",
        url="https://www.dawn.com/x",
        headline="Dawn headline",
        main_text=("Pakistan IMF " * 30),
        publish_date=datetime(2026, 2, 4, 8, 0, tzinfo=timezone.utc),
    )
    a2 = RawArticle(
        id=uuid4(),
        source="geo",
        url="https://www.geo.tv/y",
        headline="Geo headline",
        main_text=("Pakistan IMF " * 30),
        publish_date=datetime(2026, 2, 4, 9, 0, tzinfo=timezone.utc),
    )
    cluster = Cluster(id=cluster_id, article_ids=[a1.id, a2.id])
    fake_db = _FakeDB(cluster_id=cluster_id, feed=feed, cluster=cluster, articles=[a1, a2])

    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get(f"/api/stories/{cluster_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["story_id"] == str(cluster_id)
    assert body["snippet"] == "Snippet here."
    assert len(body["articles"]) == 2
    # Newest publish_date first
    assert body["articles"][0]["source"] == "geo"

