from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.stories import get_db
from src.db.client import DatabaseError
from src.db.models import AnalyzedFeed, Cluster, RawArticle


class _FakeDB:
    def __init__(
        self, cluster_id: UUID, feed: AnalyzedFeed, cluster: Cluster, articles: List[RawArticle]
    ):
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
    scraped_at = datetime(2026, 2, 4, 10, 0, tzinfo=timezone.utc)
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
        scraped_at=scraped_at,
        publish_date=datetime(2026, 2, 4, 8, 0, tzinfo=timezone.utc),
    )
    a2 = RawArticle(
        id=uuid4(),
        source="geo",
        url="https://www.geo.tv/y",
        headline="Geo headline",
        main_text=("Pakistan IMF " * 30),
        scraped_at=scraped_at,
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
    assert body["articles"][0]["publish_date_status"] == "precise"
    assert body["articles"][0]["published_on"] == "2026-02-04"


def test_story_detail_exposes_analysis_and_cited_context_without_inflating_sources():
    cluster_id = uuid4()
    primary = RawArticle(
        id=uuid4(),
        source="tribune",
        url="https://example.com/pims-fire",
        headline="Newborns killed in PIMS nursery fire",
        main_text="Newborns were killed in the PIMS nursery fire.",
    )
    related = RawArticle(
        id=uuid4(),
        source="nation",
        url="https://example.com/pims-funding",
        headline="PIMS receives Rs22bn in federal funding",
        main_text="PIMS received Rs22bn in federal funding.",
    )
    feed = AnalyzedFeed(
        cluster_id=cluster_id,
        headline="PIMS nursery fire kills newborns",
        summary="A fire killed newborns at PIMS.",
        category="health",
        source_attribution={"tribune": 1},
        metadata={
            "story_analysis": {
                "analysis": "Tribune reports the fire; Nation reports Rs22bn in funding.",
                "question": "PIMS received Rs22bn. Which office was responsible for fire safety?",
                "related_article_ids": [str(related.id)],
                "claims": [
                    {"text": "internal", "supporting_article_ids": [str(primary.id)]}
                ],
                "question_supporting_article_ids": [str(related.id)],
                "rejected": {"question": "a rejected question", "question_basis": "none"},
                "status": "ok",
            }
        },
    )
    cluster = Cluster(id=cluster_id, article_ids=[primary.id])
    fake_db = _FakeDB(
        cluster_id=cluster_id,
        feed=feed,
        cluster=cluster,
        articles=[primary, related],
    )
    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db  # type: ignore[assignment]

    body = TestClient(app).get(f"/api/stories/{cluster_id}").json()

    assert body["analysis"].startswith("Tribune reports")
    assert body["question"].startswith("PIMS received")
    assert [source["source"] for source in body["sources"]] == ["tribune"]
    assert [article["id"] for article in body["articles"]] == [str(primary.id)]
    assert [article["id"] for article in body["analysis_sources"]] == [str(related.id)]
    # Internal validation evidence and the rejected copy are not public. The
    # reader gets analysis / question / analysis_sources as typed fields.
    shipped = body["metadata"]["story_analysis"]
    assert "claims" not in shipped
    assert "question_supporting_article_ids" not in shipped
    assert "rejected" not in shipped
    assert shipped["status"] == "ok"


def test_story_detail_returns_503_when_db_unavailable():
    cluster_id = uuid4()

    class _FailDB:
        def get_analyzed_feed_by_cluster_id(self, _cluster_id: UUID) -> AnalyzedFeed:
            raise DatabaseError("down")

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FailDB()  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get(f"/api/stories/{cluster_id}")
    assert res.status_code == 503
    assert "Database unavailable" in res.json()["detail"]


def test_story_detail_derives_sources_when_missing():
    cluster_id = uuid4()
    feed = AnalyzedFeed(
        cluster_id=cluster_id,
        headline="Entity-heavy story",
        summary="Snippet here.",
        category="economy",
        impact_labels=["💳 WALLET"],
        source_attribution={},
    )
    a1 = RawArticle(
        id=uuid4(),
        source="dawn",
        url="https://www.dawn.com/x2",
        headline="Dawn headline",
        main_text=("Pakistan IMF " * 30),
    )
    a2 = RawArticle(
        id=uuid4(),
        source="geo",
        url="https://www.geo.tv/y2",
        headline="Geo headline",
        main_text=("Pakistan IMF " * 30),
    )
    cluster = Cluster(id=cluster_id, article_ids=[a1.id, a2.id])
    fake_db = _FakeDB(cluster_id=cluster_id, feed=feed, cluster=cluster, articles=[a1, a2])

    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get(f"/api/stories/{cluster_id}")
    assert res.status_code == 200
    body = res.json()
    assert [s["source"] for s in body["sources"]] == ["dawn", "geo"]
    assert all(article["publish_date"] is None for article in body["articles"])
    assert all(article["publish_date_status"] == "missing" for article in body["articles"])


def test_story_detail_filters_obviously_unrelated_articles_from_source_list():
    cluster_id = uuid4()
    feed = AnalyzedFeed(
        cluster_id=cluster_id,
        headline="National Assembly surrenders Rs470 million for austerity drive",
        summary="Parliament hands money back to the exchequer under austerity measures.",
        category="politics",
        impact_labels=["🏛️ GOVERNANCE"],
        source_attribution={"dawn": 2},
        metadata={"story_tags": ["National Assembly", "Austerity", "Exchequer"]},
    )
    relevant = RawArticle(
        id=uuid4(),
        source="dawn",
        url="https://www.dawn.com/news/relevant",
        headline="NA surrenders over Rs470m into national exchequer to support govt austerity drive",
        main_text=("National Assembly austerity " * 30),
        publish_date=datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc),
    )
    unrelated = RawArticle(
        id=uuid4(),
        source="dawn",
        url="https://www.dawn.com/news/unrelated",
        headline="Imran, Bushra move IHC to fix appeals in Toshakhana-I case",
        main_text=("Toshakhana appeal hearing " * 30),
        publish_date=datetime(2026, 4, 3, 7, 0, tzinfo=timezone.utc),
    )
    cluster = Cluster(id=cluster_id, article_ids=[relevant.id, unrelated.id])
    fake_db = _FakeDB(cluster_id=cluster_id, feed=feed, cluster=cluster, articles=[relevant, unrelated])

    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get(f"/api/stories/{cluster_id}")
    assert res.status_code == 200
    body = res.json()
    assert len(body["articles"]) == 1
    assert body["articles"][0]["headline"].startswith("NA surrenders")


def test_story_detail_hides_date_only_midnight_timestamps_but_keeps_calendar_day():
    cluster_id = uuid4()
    feed = AnalyzedFeed(
        cluster_id=cluster_id,
        headline="Cabinet meets on budget measures",
        summary="Snippet here.",
        category="politics",
        impact_labels=["🏛️ GOVERNANCE"],
        source_attribution={"dawn": 1},
    )
    article = RawArticle(
        id=uuid4(),
        source="dawn",
        url="https://www.dawn.com/news/date-only",
        headline="Cabinet meets on budget measures",
        main_text=("Budget cabinet Pakistan " * 30),
        scraped_at=datetime(2026, 5, 12, 2, 0, tzinfo=timezone.utc),
        publish_date=datetime(2026, 5, 11, 19, 0, tzinfo=timezone.utc),
    )
    cluster = Cluster(id=cluster_id, article_ids=[article.id])
    fake_db = _FakeDB(cluster_id=cluster_id, feed=feed, cluster=cluster, articles=[article])

    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db  # type: ignore[assignment]
    client = TestClient(app)

    res = client.get(f"/api/stories/{cluster_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["articles"][0]["publish_date"] is None
    assert body["articles"][0]["published_on"] == "2026-05-12"
    assert body["articles"][0]["publish_date_status"] == "date_only"
