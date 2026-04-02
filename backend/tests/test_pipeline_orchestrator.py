from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID, uuid4

import numpy as np
import spacy
import yaml

from src.agents.analysis import AnalysisService, ConsensusDetector, EntityExtractor, RuleBasedClassifier
from src.agents.clustering import ClusteringResult
from src.db.client import DuplicateArticleError
from src.db.models import AnalyzedFeed, Cluster, RawArticle
from src.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator, PipelineStats


class FakeScraper:
    def __init__(self, articles_by_source: Dict[str, List[RawArticle]]):
        self._articles_by_source = articles_by_source
        self.closed = False

    def scrape_source(self, source: str, **_kwargs):
        return list(self._articles_by_source.get(source, []))

    def close(self) -> None:
        self.closed = True


@dataclass
class _FakeEmbedResult:
    embeddings: np.ndarray
    model: str = "fake"
    texts_count: int = 0


class FakeEmbedder:
    def __init__(self, embeddings: np.ndarray):
        self._embeddings = embeddings.astype(np.float32)

    def embed_batch(self, texts: List[str], batch_size: int = 100) -> _FakeEmbedResult:
        out = self._embeddings[: len(texts)]
        return _FakeEmbedResult(embeddings=out, texts_count=len(texts))


class FakeClusterer:
    def __init__(self, labels: List[int]):
        self._labels = np.array(labels, dtype=np.int64)

    def cluster(self, embeddings: np.ndarray) -> ClusteringResult:
        assert len(embeddings) == len(self._labels)
        return ClusteringResult.from_labels(self._labels, "hdbscan")


class FakeEditorialService:
    def __init__(self, selected_cluster_ids: List[UUID]):
        self.selected_cluster_ids = {str(cluster_id) for cluster_id in selected_cluster_ids}
        self.model = "fake-editorial"

    def review_clusters(self, candidates, *, max_stories: int = 9):
        from src.agents.editorial import EditorialStory

        selected = {}
        for priority, candidate in enumerate(candidates, start=1):
            if str(candidate.cluster_id) not in self.selected_cluster_ids:
                continue
            selected[candidate.cluster_id] = EditorialStory(
                cluster_id=str(candidate.cluster_id),
                priority=100 - priority,
                headline=f"Edited: {candidate.base_feed.headline}",
                summary="Editorial summary for the morning brief.",
                category=str(candidate.base_feed.category),
                impact_labels=list(candidate.base_feed.impact_labels or ["🏛️ GOVERNANCE"]),
                why_it_matters="This has direct public relevance.",
                what_to_watch="Watch for the next official update.",
                public_impact="high",
                story_tags=["pakistan", "brief"],
                confidence=0.9,
                selection_reason="Selected by editorial gate.",
            )
            if len(selected) >= max_stories:
                break
        return selected


class FakeDB:
    def __init__(self):
        self._articles_by_id: Dict[UUID, RawArticle] = {}
        self._articles_by_url: Dict[str, UUID] = {}
        self._clusters_by_id: Dict[UUID, Cluster] = {}
        self._feed_by_cluster: Dict[UUID, AnalyzedFeed] = {}
        self._now = datetime.now(timezone.utc)

    def insert_article(self, article: RawArticle) -> UUID:
        if article.url in self._articles_by_url:
            raise DuplicateArticleError("dup")
        if article.scraped_at.tzinfo is None:
            article.scraped_at = article.scraped_at.replace(tzinfo=timezone.utc)
        self._articles_by_id[article.id] = article
        self._articles_by_url[article.url] = article.id
        return article.id

    def update_article_embedding(self, article_id: UUID, embedding: List[float]) -> None:
        self._articles_by_id[article_id].embedding = list(embedding)

    def get_articles_since(self, since: datetime, limit: int = 2000) -> List[RawArticle]:
        rows = [a for a in self._articles_by_id.values() if a.scraped_at >= since]
        return rows[:limit]

    def get_articles_without_clusters_since(self, since: datetime, limit: int = 100) -> List[RawArticle]:
        rows = [
            a
            for a in self._articles_by_id.values()
            if a.cluster_id is None and a.scraped_at >= since
        ]
        return rows[:limit]

    def get_articles_without_embeddings(self, limit: int = 100) -> List[RawArticle]:
        rows = [a for a in self._articles_by_id.values() if a.embedding is None]
        return rows[:limit]

    def get_articles_with_embeddings_since(self, since: datetime, limit: int = 100) -> List[RawArticle]:
        rows = [
            a
            for a in self._articles_by_id.values()
            if a.embedding is not None and a.scraped_at >= since
        ]
        return rows[:limit]

    def create_cluster(
        self,
        cluster_id: Optional[UUID] = None,
        article_ids: Optional[List[UUID]] = None,
        centroid_embedding: Optional[List[float]] = None,
        algorithm_used: str = "hdbscan",
    ) -> UUID:
        cid = cluster_id or uuid4()
        cluster = Cluster(
            id=cid,
            article_ids=list(article_ids or []),
            centroid_embedding=centroid_embedding,
            algorithm_used=algorithm_used,
        )
        self._clusters_by_id[cid] = cluster
        return cid

    def assign_to_cluster(self, article_id: UUID, cluster_id: UUID) -> None:
        self._articles_by_id[article_id].cluster_id = cluster_id

    def clear_cluster_assignments_since(self, since: datetime) -> int:
        count = 0
        for article in self._articles_by_id.values():
            if article.scraped_at >= since and article.cluster_id is not None:
                article.cluster_id = None
                count += 1
        return count

    def get_all_clusters(self, limit: int = 100) -> List[Cluster]:
        clusters = list(self._clusters_by_id.values())
        return clusters[:limit]

    def analyzed_feed_exists(self, cluster_id: UUID) -> bool:
        return cluster_id in self._feed_by_cluster

    def get_articles_by_ids(self, article_ids: List[UUID]) -> List[RawArticle]:
        return [self._articles_by_id[UUID(str(aid))] for aid in article_ids]

    def insert_analyzed_feed(self, feed: AnalyzedFeed) -> UUID:
        self._feed_by_cluster[feed.cluster_id] = feed
        return feed.id

    def delete_analyzed_feed_by_cluster_id(self, cluster_id: UUID) -> int:
        if cluster_id in self._feed_by_cluster:
            del self._feed_by_cluster[cluster_id]
            return 1
        return 0

    def delete_analyzed_feed_older_than(self, cutoff: datetime) -> int:
        to_delete = []
        for cid, feed in self._feed_by_cluster.items():
            created = feed.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                to_delete.append(cid)
        for cid in to_delete:
            del self._feed_by_cluster[cid]
        return len(to_delete)

    def delete_clusters_older_than(self, cutoff: datetime) -> int:
        to_delete = []
        for cid, cluster in self._clusters_by_id.items():
            created = cluster.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                to_delete.append(cid)
        for cid in to_delete:
            del self._clusters_by_id[cid]
        return len(to_delete)

    def delete_raw_articles_older_than(self, cutoff: datetime) -> int:
        to_delete = []
        for aid, article in self._articles_by_id.items():
            scraped = article.scraped_at
            if scraped.tzinfo is None:
                scraped = scraped.replace(tzinfo=timezone.utc)
            if scraped < cutoff:
                to_delete.append(aid)
        for aid in to_delete:
            url = self._articles_by_id[aid].url
            del self._articles_by_id[aid]
            self._articles_by_url.pop(url, None)
        return len(to_delete)


def test_pipeline_orchestrator_chains_phases(tmp_path):
    # Minimal sources config with two enabled sources.
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": True,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )

    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)

    nlp = spacy.blank("en")
    extractor = EntityExtractor(nlp=nlp)
    consensus = ConsensusDetector(min_agreement_ratio=1.0)
    analyzer = AnalysisService(entity_extractor=extractor, consensus_detector=consensus, classifier=clf)

    a1 = RawArticle(
        source="dawn",
        url="https://example.com/a",
        headline="Pakistan talks to IMF",
        main_text=("Pakistan IMF rupee " * 30),
    )
    a2 = RawArticle(
        source="tribune",
        url="https://example.com/b",
        headline="IMF meeting in Pakistan",
        main_text=("Pakistan IMF inflation " * 30),
    )
    off = RawArticle(
        source="dawn",
        url="https://evil.com/phish",
        headline="Off domain",
        main_text=("Pakistan IMF " * 30),
    )

    fake_scraper = FakeScraper({"dawn": [a1, off], "tribune": [a2]})

    # Two identical unit vectors ⇒ centroid and similarity are deterministic.
    emb = np.zeros((2, 768), dtype=np.float32)
    emb[:, 0] = 1.0
    fake_embedder = FakeEmbedder(embeddings=emb)
    fake_clusterer = FakeClusterer(labels=[0, 0])

    db = FakeDB()
    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        min_cluster_size=2,
        analyze_recent_clusters_limit=10,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=fake_scraper,  # type: ignore[arg-type]
        embedder=fake_embedder,  # type: ignore[arg-type]
        clusterer=fake_clusterer,  # type: ignore[arg-type]
        analyzer=analyzer,
    )

    stats = runner.run()

    assert stats.inserted == 2
    assert stats.embedded == 2
    assert stats.clusters_created == 1
    assert stats.feeds_inserted == 1

    # Ensure the feed is "card-complete": headline + snippet summary.
    feed = next(iter(db._feed_by_cluster.values()))
    assert feed.headline
    assert isinstance(feed.summary, str) and feed.summary
    assert "Pakistan" in feed.summary


def test_pipeline_daily_digest_window_skips_old_articles(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": True,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)

    nlp = spacy.blank("en")
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=nlp),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=clf,
    )

    now = datetime.now(timezone.utc)
    recent = RawArticle(
        source="dawn",
        url="https://example.com/recent",
        headline="Recent article",
        main_text=("Pakistan IMF " * 30),
        scraped_at=now,
    )
    old = RawArticle(
        source="tribune",
        url="https://example.com/old",
        headline="Old article",
        main_text=("Pakistan IMF " * 30),
        scraped_at=now - timedelta(hours=48),
    )
    fake_scraper = FakeScraper({"dawn": [recent], "tribune": [old]})

    emb = np.zeros((2, 768), dtype=np.float32)
    emb[:, 0] = 1.0
    fake_embedder = FakeEmbedder(embeddings=emb)
    fake_clusterer = FakeClusterer(labels=[0, 0])

    db = FakeDB()
    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        min_cluster_size=1,
        cluster_lookback_hours=24,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=fake_scraper,  # type: ignore[arg-type]
        embedder=fake_embedder,  # type: ignore[arg-type]
        clusterer=fake_clusterer,  # type: ignore[arg-type]
        analyzer=analyzer,
    )

    runner.run()
    # Clustering should not create a cluster because only one article is within 24h window.
    assert len(db._clusters_by_id) == 0


def test_pipeline_embedding_backfill_handles_previous_failures(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": True,
                    }
                    ,
                    "tribune": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=clf,
    )

    # Simulate: article already exists in DB from a prior run but has no embedding.
    db = FakeDB()
    existing = RawArticle(
        source="dawn",
        url="https://example.com/existing",
        headline="Existing",
        main_text=("Pakistan IMF " * 30),
    )
    db.insert_article(existing)

    # Next run scrapes same URL again → treated as duplicate, so inserted list is empty.
    fake_scraper = FakeScraper({"dawn": [existing]})
    emb = np.zeros((1, 768), dtype=np.float32)
    emb[:, 0] = 1.0
    fake_embedder = FakeEmbedder(embeddings=emb)
    fake_clusterer = FakeClusterer(labels=[-1])

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        embedding_backfill_limit=10,
        cluster_lookback_hours=24,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=fake_scraper,  # type: ignore[arg-type]
        embedder=fake_embedder,  # type: ignore[arg-type]
        clusterer=fake_clusterer,  # type: ignore[arg-type]
        analyzer=analyzer,
    )

    stats = runner.run()
    assert stats.embedded >= 1
    assert db._articles_by_id[existing.id].embedding is not None


def test_pipeline_retention_prunes_old_data(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=clf,
    )

    db = FakeDB()
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=10)

    # Seed old rows.
    old_article = RawArticle(
        source="dawn",
        url="https://example.com/old-a",
        headline="Old",
        main_text=("Pakistan IMF " * 30),
        scraped_at=old_time,
    )
    db.insert_article(old_article)
    old_cluster_id = uuid4()
    db.create_cluster(cluster_id=old_cluster_id, article_ids=[old_article.id])
    db._clusters_by_id[old_cluster_id].created_at = old_time  # type: ignore[assignment]
    old_feed = AnalyzedFeed(
        cluster_id=old_cluster_id,
        headline="Old story",
        summary="Old snippet",
        category="economy",
        created_at=old_time,
    )
    db.insert_analyzed_feed(old_feed)

    fake_scraper = FakeScraper({"dawn": [] , "tribune": []})
    fake_embedder = FakeEmbedder(embeddings=np.zeros((0, 768), dtype=np.float32))
    fake_clusterer = FakeClusterer(labels=[])

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        retention_days=7,
        embedding_backfill_limit=0,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=fake_scraper,  # type: ignore[arg-type]
        embedder=fake_embedder,  # type: ignore[arg-type]
        clusterer=fake_clusterer,  # type: ignore[arg-type]
        analyzer=analyzer,
    )

    stats = runner.run()
    assert stats.pruned_articles >= 1
    assert stats.pruned_clusters >= 1
    assert stats.pruned_feeds >= 1


def test_pipeline_does_not_refresh_feeds_for_clusters_older_than_retention_cutoff(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": False,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=RuleBasedClassifier.from_yaml(rules_path),
    )
    db = FakeDB()

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=10)

    a1 = RawArticle(
        source="dawn",
        url="https://example.com/old-1",
        headline="Old story A",
        main_text=("Pakistan IMF " * 30),
        scraped_at=old_time,
        embedding=[1.0, 0.0, 0.0],
    )
    a2 = RawArticle(
        source="tribune",
        url="https://example.com/old-2",
        headline="Old story B",
        main_text=("Pakistan IMF " * 30),
        scraped_at=old_time,
        embedding=[1.0, 0.0, 0.0],
    )
    db.insert_article(a1)
    db.insert_article(a2)

    old_cluster_id = uuid4()
    db.create_cluster(cluster_id=old_cluster_id, article_ids=[a1.id, a2.id])
    db._clusters_by_id[old_cluster_id].created_at = old_time  # type: ignore[assignment]
    db._clusters_by_id[old_cluster_id].updated_at = old_time  # type: ignore[assignment]
    db.assign_to_cluster(a1.id, old_cluster_id)
    db.assign_to_cluster(a2.id, old_cluster_id)
    db.insert_analyzed_feed(
        AnalyzedFeed(
            cluster_id=old_cluster_id,
            headline="Old story",
            summary="Old snippet",
            category="economy",
            created_at=old_time,
        )
    )

    fake_scraper = FakeScraper({"dawn": [], "tribune": []})
    fake_embedder = FakeEmbedder(embeddings=np.zeros((0, 768), dtype=np.float32))
    fake_clusterer = FakeClusterer(labels=[])

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        retention_days=7,
        embedding_backfill_limit=0,
        recluster_recent_window=False,
        refresh_existing_feeds=True,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=fake_scraper,  # type: ignore[arg-type]
        embedder=fake_embedder,  # type: ignore[arg-type]
        clusterer=fake_clusterer,  # type: ignore[arg-type]
        analyzer=analyzer,
    )

    stats = runner.run()
    assert stats.feeds_replaced == 0
    assert stats.feeds_inserted == 0
    assert stats.pruned_feeds >= 1
    assert old_cluster_id not in db._feed_by_cluster


def test_pipeline_refreshes_existing_feed_rows(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": False,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "feed_url": "https://example.com/rss",
                        "sections": ["latest"],
                        "enabled": False,
                    }
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=RuleBasedClassifier.from_yaml(rules_path),
    )
    db = FakeDB()

    a1 = RawArticle(
        source="dawn",
        url="https://example.com/new-1",
        headline="Pakistan IMF update",
        main_text=("Pakistan IMF " * 30),
    )
    a2 = RawArticle(
        source="tribune",
        url="https://example.com/new-2",
        headline="IMF talks continue",
        main_text=("Pakistan IMF " * 30),
    )
    db.insert_article(a1)
    db.insert_article(a2)
    a1.embedding = [1.0, 0.0, 0.0]
    a2.embedding = [1.0, 0.0, 0.0]
    cluster_id = db.create_cluster(article_ids=[a1.id, a2.id])
    db.assign_to_cluster(a1.id, cluster_id)
    db.assign_to_cluster(a2.id, cluster_id)
    db.insert_analyzed_feed(
        AnalyzedFeed(
            cluster_id=cluster_id,
            headline="Old stale headline",
            summary="Old stale summary",
            category="economy",
        )
    )

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        recluster_recent_window=False,
        refresh_existing_feeds=True,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=FakeScraper({"dawn": []}),  # type: ignore[arg-type]
        analyzer=analyzer,
    )
    stats = runner.run()

    assert stats.feeds_replaced >= 1
    refreshed = db._feed_by_cluster[cluster_id]
    assert refreshed.headline != "Old stale headline"


def test_pipeline_editorial_gate_rejects_unselected_clusters(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "sections": ["pakistan"],
                        "enabled": False,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "sections": ["business"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=RuleBasedClassifier.from_yaml(rules_path),
    )
    db = FakeDB()

    cluster_ids: List[UUID] = []
    for cluster_no in range(2):
        articles = [
            RawArticle(
                source="dawn",
                url=f"https://example.com/{cluster_no}-a",
                headline=f"Pakistan story {cluster_no} A",
                main_text=("Pakistan inflation budget " * 30),
                embedding=[1.0, 0.0, 0.0],
            ),
            RawArticle(
                source="tribune",
                url=f"https://example.com/{cluster_no}-b",
                headline=f"Pakistan story {cluster_no} B",
                main_text=("Pakistan inflation IMF " * 30),
                embedding=[1.0, 0.0, 0.0],
            ),
        ]
        for article in articles:
            db.insert_article(article)
        cluster_id = db.create_cluster(article_ids=[a.id for a in articles])
        cluster_ids.append(cluster_id)
        for article in articles:
            db.assign_to_cluster(article.id, cluster_id)

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            classification_yaml=rules_path,
            recluster_recent_window=False,
            editorial_candidate_limit=10,
            editorial_max_stories=5,
        ),
        db=db,  # type: ignore[arg-type]
        scraper=FakeScraper({}),  # type: ignore[arg-type]
        analyzer=analyzer,
        editorial_service=FakeEditorialService([cluster_ids[0]]),  # type: ignore[arg-type]
    )

    stats = runner.run()

    assert stats.feeds_inserted == 1
    assert stats.feeds_rejected_editorial >= 1
    selected_feed = db._feed_by_cluster[cluster_ids[0]]
    assert selected_feed.headline.startswith("Edited:")
    assert selected_feed.metadata["llm_augmented"] is True
    assert cluster_ids[1] not in db._feed_by_cluster


def test_cluster_guardrails_reject_low_similarity_cluster(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {},
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"

    db = FakeDB()
    now = datetime.now(timezone.utc)
    articles = [
        RawArticle(
            source="dawn",
            url="https://example.com/a",
            headline="A",
            main_text=("x " * 80),
            scraped_at=now,
            embedding=[1.0, 0.0, 0.0],
        ),
        RawArticle(
            source="geo",
            url="https://example.com/b",
            headline="B",
            main_text=("x " * 80),
            scraped_at=now,
            embedding=[0.0, 1.0, 0.0],
        ),
        RawArticle(
            source="tribune",
            url="https://example.com/c",
            headline="C",
            main_text=("x " * 80),
            scraped_at=now,
            embedding=[0.0, 0.0, 1.0],
        ),
    ]
    for a in articles:
        db.insert_article(a)

    # Force a single-cluster assignment from the clusterer so only guardrails can reject it.
    fake_clusterer = FakeClusterer(labels=[0, 0, 0])
    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        recluster_recent_window=False,
        min_cluster_size=2,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=FakeScraper({}),  # type: ignore[arg-type]
        clusterer=fake_clusterer,  # type: ignore[arg-type]
    )

    stats = PipelineStats()
    created = runner.cluster_unclustered_articles(stats)
    assert created == []
    assert stats.clusters_created == 0
    assert stats.clusters_rejected_low_similarity >= 1


def test_cluster_guardrails_cap_per_source(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {},
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"

    db = FakeDB()
    now = datetime.now(timezone.utc)

    # 5 from dawn, 3 from geo. All embeddings identical => very high similarity.
    rows: List[RawArticle] = []
    for i in range(5):
        rows.append(
            RawArticle(
                source="dawn",
                url=f"https://example.com/dawn-{i}",
                headline=f"D{i}",
                main_text=("Pakistan IMF " * 30),
                scraped_at=now,
                embedding=[1.0, 0.0, 0.0],
            )
        )
    for i in range(3):
        rows.append(
            RawArticle(
                source="geo",
                url=f"https://example.com/geo-{i}",
                headline=f"G{i}",
                main_text=("Pakistan IMF " * 30),
                scraped_at=now,
                embedding=[1.0, 0.0, 0.0],
            )
        )
    for a in rows:
        db.insert_article(a)

    fake_clusterer = FakeClusterer(labels=[0] * len(rows))
    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        classification_yaml=rules_path,
        recluster_recent_window=False,
        min_cluster_size=2,
        max_cluster_articles_per_source=2,
        max_cluster_articles=10,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        scraper=FakeScraper({}),  # type: ignore[arg-type]
        clusterer=fake_clusterer,  # type: ignore[arg-type]
    )

    stats = PipelineStats()
    created = runner.cluster_unclustered_articles(stats)
    assert len(created) == 1
    cluster = db._clusters_by_id[created[0]]
    assert len(cluster.article_ids) == 4  # 2 per source, 2 sources

    sources = [db._articles_by_id[aid].source for aid in cluster.article_ids]
    assert sources.count("dawn") <= 2
    assert sources.count("geo") <= 2
