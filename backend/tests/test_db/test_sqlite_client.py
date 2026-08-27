"""
Tests for the local SQLite database backend.

These are real round-trips against a temporary database file, not mocks, so
they verify the encoding choices (UUID/TEXT, ISO-8601 timestamps, JSON blobs)
actually survive a write/read cycle.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.db.errors import DuplicateArticleError, NotFoundError
from src.db.factory import configured_backend, create_db_client
from src.db.models import AnalyzedFeed, Category, ExtractedEntity, ImpactLabel, RawArticle
from src.db.sqlite_client import SqliteClient, default_sqlite_path


@pytest.fixture
def db(tmp_path):
    client = SqliteClient(path=tmp_path / "test.db")
    yield client
    client.close()


def make_article(**overrides) -> RawArticle:
    defaults = {
        "source": "dawn",
        "url": f"https://www.dawn.com/news/{uuid4().hex}",
        "headline": "Rupee steadies against dollar",
        "main_text": (
            "The Pakistani rupee held its ground against the US dollar in "
            "interbank trading on Tuesday, dealers said, after several sessions "
            "of decline driven by import payments."
        ),
        "author": "Staff Reporter",
        "publish_date": datetime(2026, 8, 24, 6, 30, tzinfo=timezone.utc),
        "scraped_at": datetime(2026, 8, 24, 7, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return RawArticle(**defaults)


class TestSchemaAndConnection:
    def test_creates_file_and_tables(self, tmp_path):
        path = tmp_path / "nested" / "saaf.db"
        client = SqliteClient(path=path)
        assert path.exists()
        for table in ("raw_articles", "clusters", "analyzed_feed"):
            assert client.table_exists(table)
        client.close()

    def test_is_connected(self, db):
        assert db.is_connected() is True

    def test_table_schema_lists_columns(self, db):
        columns = db.get_table_schema("raw_articles")["columns"]
        assert {"id", "url", "content_hash", "embedding", "cluster_id"} <= set(columns)

    def test_unknown_table_does_not_exist(self, db):
        assert db.table_exists("not_a_table") is False

    def test_memory_database_persists_within_client(self):
        client = SqliteClient(path=":memory:")
        article_id = client.insert_article(make_article())
        assert client.get_article_by_id(article_id).source == "dawn"
        client.close()


class TestArticleRoundTrip:
    def test_insert_and_fetch_preserves_fields(self, db):
        article = make_article()
        article_id = db.insert_article(article)

        loaded = db.get_article_by_id(article_id)
        assert loaded.id == article.id
        assert loaded.url == article.url
        assert loaded.headline == article.headline
        assert loaded.author == "Staff Reporter"
        assert loaded.content_hash == article.content_hash
        assert loaded.publish_date == article.publish_date
        assert loaded.scraped_at == article.scraped_at

    def test_metadata_json_round_trips(self, db):
        article = make_article(
            metadata={"discovery_rank": 3, "bucket": "lead", "nested": {"a": [1, 2]}}
        )
        db.insert_article(article)
        loaded = db.get_article_by_id(article.id)
        assert loaded.metadata["discovery_rank"] == 3
        assert loaded.metadata["nested"] == {"a": [1, 2]}

    def test_naive_datetimes_are_treated_as_utc(self, db):
        article = make_article(scraped_at=datetime(2026, 8, 24, 7, 0))
        db.insert_article(article)
        loaded = db.get_article_by_id(article.id)
        assert loaded.scraped_at == datetime(2026, 8, 24, 7, 0, tzinfo=timezone.utc)

    def test_duplicate_url_raises(self, db):
        article = make_article()
        db.insert_article(article)
        clash = make_article(url=article.url, headline="Different headline entirely")
        with pytest.raises(DuplicateArticleError):
            db.insert_article(clash)

    def test_duplicate_content_hash_raises(self, db):
        article = make_article()
        db.insert_article(article)
        clash = make_article(
            url="https://www.dawn.com/news/other",
            headline=article.headline,
            main_text=article.main_text,
        )
        with pytest.raises(DuplicateArticleError):
            db.insert_article(clash)

    def test_missing_article_raises_not_found(self, db):
        with pytest.raises(NotFoundError):
            db.get_article_by_id(uuid4())

    def test_batch_insert_skips_duplicates(self, db):
        first = make_article()
        second = make_article(source="tribune", headline="Second story about the budget")
        duplicate = make_article(url=first.url, headline="Yet another headline here")

        ids = db.batch_insert_articles([first, second, duplicate])
        assert len(ids) == 2
        assert len(db.get_recent_articles(limit=50)) == 2

    def test_batch_insert_empty_returns_empty(self, db):
        assert db.batch_insert_articles([]) == []

    def test_get_articles_by_ids(self, db):
        a, b = make_article(), make_article(headline="Second distinct headline text")
        db.batch_insert_articles([a, b])
        loaded = db.get_articles_by_ids([a.id, b.id])
        assert {row.id for row in loaded} == {a.id, b.id}

    def test_get_articles_by_ids_empty(self, db):
        assert db.get_articles_by_ids([]) == []

    def test_get_articles_by_source_filters_and_orders(self, db):
        older = make_article(source="dawn", scraped_at=datetime(2026, 8, 24, 1, 0, tzinfo=timezone.utc))
        newer = make_article(
            source="dawn",
            headline="A newer dawn headline about power tariffs",
            scraped_at=datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc),
        )
        other = make_article(source="geo", headline="Geo headline about a cabinet meeting")
        db.batch_insert_articles([older, newer, other])

        rows = db.get_articles_by_source("dawn")
        assert [row.id for row in rows] == [newer.id, older.id]

    def test_delete_article(self, db):
        article = make_article()
        db.insert_article(article)
        db.delete_article(article.id)
        with pytest.raises(NotFoundError):
            db.get_article_by_id(article.id)


class TestEmbeddings:
    def test_embedding_round_trips_as_floats(self, db):
        article = make_article()
        db.insert_article(article)
        vector = [round(i * 0.001, 6) for i in range(768)]
        db.update_article_embedding(article.id, vector)

        loaded = db.get_article_by_id(article.id)
        assert loaded.embedding is not None
        assert len(loaded.embedding) == 768
        assert loaded.embedding == pytest.approx(vector)

    def test_articles_without_embeddings(self, db):
        embedded = make_article()
        bare = make_article(headline="An article with no embedding yet at all")
        db.batch_insert_articles([embedded, bare])
        db.update_article_embedding(embedded.id, [0.1, 0.2, 0.3])

        pending = db.get_articles_without_embeddings()
        assert [row.id for row in pending] == [bare.id]

    def test_articles_with_embeddings_since(self, db):
        recent = make_article(scraped_at=datetime.now(timezone.utc))
        stale = make_article(
            headline="An older embedded story about fuel prices",
            scraped_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        db.batch_insert_articles([recent, stale])
        db.update_article_embedding(recent.id, [0.1] * 8)
        db.update_article_embedding(stale.id, [0.2] * 8)

        since = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = db.get_articles_with_embeddings_since(since)
        assert [row.id for row in rows] == [recent.id]


class TestClusterAssignment:
    def test_create_cluster_and_assign_articles(self, db):
        a, b = make_article(), make_article(headline="Second article on the same event")
        db.batch_insert_articles([a, b])

        cluster_id = db.create_cluster(
            article_ids=[a.id, b.id],
            centroid_embedding=[0.5] * 8,
            algorithm_used="event_graph",
        )
        db.assign_to_cluster(a.id, cluster_id)
        db.assign_to_cluster(b.id, cluster_id)

        cluster = db.get_cluster_by_id(cluster_id)
        assert cluster.cluster_size == 2
        assert set(cluster.article_ids) == {a.id, b.id}
        assert cluster.algorithm_used == "event_graph"
        assert cluster.centroid_embedding == pytest.approx([0.5] * 8)
        assert db.get_article_by_id(a.id).cluster_id == cluster_id

    def test_missing_cluster_raises_not_found(self, db):
        with pytest.raises(NotFoundError):
            db.get_cluster_by_id(uuid4())

    def test_unclustered_query_excludes_assigned(self, db):
        a, b = make_article(), make_article(headline="A second unclustered news story")
        db.batch_insert_articles([a, b])
        cluster_id = db.create_cluster(article_ids=[a.id])
        db.assign_to_cluster(a.id, cluster_id)

        pending = db.get_articles_without_clusters()
        assert [row.id for row in pending] == [b.id]

    def test_clear_cluster_assignments_since(self, db):
        article = make_article(scraped_at=datetime.now(timezone.utc))
        db.insert_article(article)
        cluster_id = db.create_cluster(article_ids=[article.id])
        db.assign_to_cluster(article.id, cluster_id)

        cleared = db.clear_cluster_assignments_since(
            datetime.now(timezone.utc) - timedelta(hours=1)
        )
        assert cleared == 1
        assert db.get_article_by_id(article.id).cluster_id is None

    def test_update_cluster_articles(self, db):
        a, b = make_article(), make_article(headline="Another article joining the cluster")
        db.batch_insert_articles([a, b])
        cluster_id = db.create_cluster(article_ids=[a.id])

        db.update_cluster_articles(cluster_id, [a.id, b.id])
        cluster = db.get_cluster_by_id(cluster_id)
        assert cluster.cluster_size == 2

    def test_deleting_cluster_nulls_article_reference(self, db):
        article = make_article()
        db.insert_article(article)
        cluster_id = db.create_cluster(article_ids=[article.id])
        db.assign_to_cluster(article.id, cluster_id)

        db.delete_cluster(cluster_id)
        assert db.get_article_by_id(article.id).cluster_id is None

    def test_get_all_clusters_orders_newest_first(self, db):
        first = db.create_cluster()
        second = db.create_cluster()
        ids = [c.id for c in db.get_all_clusters()]
        assert set(ids) == {first, second}


class TestAnalyzedFeed:
    def _feed(self, cluster_id, **overrides) -> AnalyzedFeed:
        defaults = {
            "cluster_id": cluster_id,
            "headline": "Government announces relief on electricity tariffs",
            "summary": "A short brief summary for the card.",
            "category": Category.ECONOMY,
            "confirmed_facts": [ExtractedEntity(text="NEPRA", type="ORG", sources=2)],
            "debated_claims": [ExtractedEntity(text="Rs 3 per unit", type="MONEY", sources=1)],
            "impact_labels": [ImpactLabel.WALLET, ImpactLabel.UTILITIES],
            "source_attribution": {"dawn": 2, "geo": 1},
            "entity_counts": {"NEPRA": 3},
            "classification_confidence": 0.82,
            "metadata": {"why_it_matters": "Bills may fall.", "editorial_priority": 4},
        }
        defaults.update(overrides)
        return AnalyzedFeed(**defaults)

    def test_feed_round_trip_preserves_structured_fields(self, db):
        cluster_id = db.create_cluster()
        feed = self._feed(cluster_id)
        feed_id = db.insert_analyzed_feed(feed)

        loaded = db.get_analyzed_feed_by_id(feed_id)
        assert loaded.headline == feed.headline
        assert loaded.category == "economy"
        assert loaded.classification_confidence == pytest.approx(0.82)
        assert loaded.is_published is True
        assert loaded.source_attribution == {"dawn": 2, "geo": 1}
        assert loaded.entity_counts == {"NEPRA": 3}
        assert loaded.metadata["editorial_priority"] == 4
        assert [e.text for e in loaded.confirmed_facts] == ["NEPRA"]
        assert [e.text for e in loaded.debated_claims] == ["Rs 3 per unit"]
        assert set(loaded.impact_labels) == {"💳 WALLET", "⚡ UTILITIES"}

    def test_feed_exists_and_lookup_by_cluster(self, db):
        cluster_id = db.create_cluster()
        assert db.analyzed_feed_exists(cluster_id) is False
        db.insert_analyzed_feed(self._feed(cluster_id))
        assert db.analyzed_feed_exists(cluster_id) is True
        assert db.get_analyzed_feed_by_cluster_id(cluster_id).cluster_id == cluster_id

    def test_missing_feed_raises_not_found(self, db):
        with pytest.raises(NotFoundError):
            db.get_analyzed_feed_by_id(uuid4())
        with pytest.raises(NotFoundError):
            db.get_analyzed_feed_by_cluster_id(uuid4())

    def test_category_filter(self, db):
        economy = db.create_cluster()
        politics = db.create_cluster()
        db.insert_analyzed_feed(self._feed(economy))
        db.insert_analyzed_feed(
            self._feed(politics, category=Category.POLITICS, headline="Senate passes bill")
        )

        rows = db.get_analyzed_feed(category="politics")
        assert [row.headline for row in rows] == ["Senate passes bill"]

    def test_impact_label_filter(self, db):
        wallet = db.create_cluster()
        safety = db.create_cluster()
        db.insert_analyzed_feed(self._feed(wallet))
        db.insert_analyzed_feed(
            self._feed(
                safety,
                headline="Security alert issued for the capital",
                category=Category.SECURITY,
                impact_labels=[ImpactLabel.SAFETY],
            )
        )

        rows = db.get_analyzed_feed(impact_label="🛡️ SAFETY")
        assert [row.headline for row in rows] == ["Security alert issued for the capital"]

    def test_published_only_filter(self, db):
        cluster_id = db.create_cluster()
        db.insert_analyzed_feed(self._feed(cluster_id, is_published=False))

        assert db.get_analyzed_feed() == []
        assert len(db.get_analyzed_feed(published_only=False)) == 1

    def test_delete_by_cluster_id_returns_count(self, db):
        cluster_id = db.create_cluster()
        db.insert_analyzed_feed(self._feed(cluster_id))
        assert db.delete_analyzed_feed_by_cluster_id(cluster_id) == 1
        assert db.analyzed_feed_exists(cluster_id) is False

    def test_deleting_cluster_cascades_to_feed(self, db):
        cluster_id = db.create_cluster()
        db.insert_analyzed_feed(self._feed(cluster_id))
        db.delete_cluster(cluster_id)
        assert db.get_analyzed_feed() == []


class TestRetentionPruning:
    def test_prune_by_age(self, db):
        old_time = datetime.now(timezone.utc) - timedelta(days=30)
        fresh = make_article(scraped_at=datetime.now(timezone.utc))
        stale = make_article(
            headline="A very old story that should be pruned away",
            scraped_at=old_time,
        )
        db.batch_insert_articles([fresh, stale])

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        assert db.delete_raw_articles_older_than(cutoff) == 1
        assert [row.id for row in db.get_recent_articles()] == [fresh.id]

    def test_prune_feeds_and_clusters_by_age(self, db):
        cluster_id = db.create_cluster()
        feed = AnalyzedFeed(
            cluster_id=cluster_id,
            headline="Old story",
            category=Category.OTHER,
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db.insert_analyzed_feed(feed)

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        assert db.delete_analyzed_feed_older_than(cutoff) == 1


class TestTestModeCleanup:
    def test_cleanup_removes_tracked_rows(self, tmp_path):
        client = SqliteClient(path=tmp_path / "cleanup.db", test_mode=True)
        article = make_article()
        client.insert_article(article)
        cluster_id = client.create_cluster(article_ids=[article.id])
        client.insert_analyzed_feed(
            AnalyzedFeed(cluster_id=cluster_id, headline="Temp", category=Category.OTHER)
        )

        client.cleanup_test_data()
        assert client.get_recent_articles() == []
        assert client.get_all_clusters() == []
        assert client.get_analyzed_feed() == []
        client.close()


class TestFactory:
    def test_defaults_to_sqlite(self, monkeypatch):
        monkeypatch.delenv("SAAF_DB_BACKEND", raising=False)
        assert configured_backend() == "sqlite"

    def test_creates_sqlite_client(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SAAF_DB_BACKEND", raising=False)
        monkeypatch.setenv("SAAF_SQLITE_PATH", str(tmp_path / "factory.db"))
        client = create_db_client()
        assert isinstance(client, SqliteClient)
        assert client.path == tmp_path / "factory.db"
        client.close()

    def test_supabase_opt_in_is_recognised(self, monkeypatch):
        monkeypatch.setenv("SAAF_DB_BACKEND", "supabase")
        assert configured_backend() == "supabase"

    def test_relative_sqlite_path_resolves_under_backend(self, monkeypatch):
        monkeypatch.setenv("SAAF_SQLITE_PATH", "data/custom.db")
        assert default_sqlite_path().is_absolute()
        assert default_sqlite_path().name == "custom.db"


class TestClusterOrdering:
    """The analysis stage truncates on this ordering, so it has to be right."""

    def _cluster(self, db, size: int):
        cluster_id = db.create_cluster(
            article_ids=[], centroid_embedding=[0.1] * 768, algorithm_used="event_graph"
        )
        db.update_cluster_metadata(cluster_id, {"probe_size": size})
        return cluster_id

    def test_size_ordering_keeps_the_biggest_cluster_when_the_limit_truncates(self, db):
        # A run on 2026-08-25 produced 570 clusters and the analysis stage
        # looked at 200 of them, ordered by creation time. The day's two most
        # corroborated stories - Imran Khan's hospital transfer at 7 sources
        # and the Munir visit to Iran at 6 - fell outside the window and were
        # never analysed. If the limit has to drop something, it drops the
        # singletons.
        big = db.create_cluster(article_ids=[], centroid_embedding=[0.1] * 768)
        db.update_cluster_articles(big, [uuid4() for _ in range(9)])
        for _ in range(3):
            small = db.create_cluster(article_ids=[], centroid_embedding=[0.1] * 768)
            db.update_cluster_articles(small, [uuid4()])

        by_size = db.get_all_clusters(limit=1, order="size")
        assert [c.id for c in by_size] == [big]

    def test_default_ordering_is_still_most_recent_first(self, db):
        first = db.create_cluster(article_ids=[], centroid_embedding=[0.1] * 768)
        second = db.create_cluster(article_ids=[], centroid_embedding=[0.1] * 768)
        ids = [c.id for c in db.get_all_clusters(limit=10)]
        assert ids.index(second) <= ids.index(first)
