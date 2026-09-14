from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional
from uuid import UUID, uuid4

import numpy as np
import pytest
import spacy
import yaml

from src.agents.analysis import AnalysisService, ConsensusDetector, EntityExtractor
from src.agents.clustering import ClusteringResult
from src.agents.editorial import ClusterEditorialCandidate
from src.agents.story_analysis import StoryAnalysisError
from src.db.client import DuplicateArticleError
from src.db.models import AnalyzedFeed, Cluster, RawArticle
from src.pipeline.orchestrator import (
    PipelineConfig,
    PipelineOrchestrator,
    PipelineStats,
    default_config,
)
from src.scrapers.feeds import EndpointReport, IngestResult


class FakeIngestor:
    """Stands in for FeedIngestor: returns a canned IngestResult."""

    def __init__(
        self,
        articles_by_source: Dict[str, List[RawArticle]],
        reports: List[EndpointReport] | None = None,
    ):
        self._articles_by_source = articles_by_source
        self._reports = list(reports) if reports is not None else None
        self.runs = 0

    def _default_reports(self) -> List[EndpointReport]:
        return [
            EndpointReport(
                source=source,
                channel="rss",
                url=f"https://example.com/{source}/rss",
                status="ok",
                newest_age_hours=1.0,
                item_count=len(articles),
            )
            for source, articles in self._articles_by_source.items()
        ]

    def run(self) -> IngestResult:
        self.runs += 1
        articles = [a for group in self._articles_by_source.values() for a in group]
        reports = self._reports if self._reports is not None else self._default_reports()
        return IngestResult(articles=articles, reports=reports)


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
                impact_line="This has direct public relevance.",
                category=str(candidate.base_feed.category),
                impact_labels=list(candidate.base_feed.impact_labels or ["🏛️ GOVERNANCE"]),
                what_to_watch="Watch for the next official update.",
                public_impact="high",
                story_tags=["pakistan", "brief"],
                confidence=0.9,
                selection_reason="Selected by editorial gate.",
            )
            if len(selected) >= max_stories:
                break
        return selected


class FailingEditorialService:
    model = "failing-editorial"

    def review_clusters(self, candidates, *, max_stories: int = 9):
        from src.agents.editorial import EditorialError

        raise EditorialError("editorial down")


class FailingStoryAnalysisService:
    model = "failing-story-analysis"
    last_call_count = 1

    def __init__(self):
        self.calls = 0

    def analyze(self, _story_input):
        self.calls += 1
        raise StoryAnalysisError("story analysis down", calls=1)


# Keyword matching is fine for a test fixture; it was never fine as product
# logic. This stands in for GeminiTriageService so orchestrator tests exercise
# the real triage stage without a network call.
_FIXTURE_CATEGORY_HINTS = (
    ("economy", ("imf", "rupee", "inflation", "oil", "budget", "tax", "economic", "market", "port", "$")),
    ("security", ("attack", "police", "blast", "security", "militant", "killed", "army")),
    ("politics", ("minister", "assembly", "government", "pml", "pti", "election", "senate", "court", "shc", "jit")),
    ("city", ("karachi", "lahore", "traffic", "toll", "expressway", "water", "road")),
    ("health", ("hospital", "dengue", "health", "polio")),
    ("education", ("school", "university", "exam", "student")),
    ("international", ("iran", "china", "india", "us ", "tehran", "sanctions")),
    ("sports", ("cricket", "football", "atp", "premier league")),
    ("entertainment", ("film", "box office", "actor", "prince", "gala")),
)
_FIXTURE_IMPACT_HINTS = (
    ("💳 WALLET", ("rupee", "inflation", "tax", "price", "oil", "budget", "$")),
    ("🛡️ SAFETY", ("attack", "blast", "killed", "police", "security", "lion")),
    ("🚦 COMMUTE", ("traffic", "toll", "expressway", "road", "transport")),
    ("⚡ UTILITIES", ("power", "electricity", "gas", "water", "internet")),
    ("🏛️ GOVERNANCE", ("minister", "assembly", "government", "court", "policy")),
)


class FakeTriageService:
    """Deterministic triage stand-in keyed off the fixture vocabulary."""

    def __init__(self, category: str | None = None, story_type: str = "hard_news"):
        self.category = category
        self.story_type = story_type
        self.calls = 0

    def triage(self, items):
        from src.agents.triage import TriageResult, TriageVerdict

        self.calls += 1
        verdicts = {}
        for item in items:
            text = f"{item.headline} {item.summary}".lower()
            category = self.category or next(
                (name for name, hints in _FIXTURE_CATEGORY_HINTS if any(h in text for h in hints)),
                "other",
            )
            labels = [
                label
                for label, hints in _FIXTURE_IMPACT_HINTS
                if any(hint in text for hint in hints)
            ][:3]
            verdicts[item.key] = TriageVerdict(
                key=item.key,
                category=category,
                impact_labels=labels,
                story_type=self.story_type,
                pk_relevance="national",
                confidence=0.9,
            )
        return TriageResult(verdicts=verdicts, calls=1, failures=0, missing_keys=[])


def _triaged(article, category="economy", impact_labels=("💳 WALLET",),
             story_type="hard_news", pk_relevance="national", confidence=0.9):
    """
    Stamp the verdict the triage stage would have persisted.

    Tests that call analyze_clusters_missing_feed directly skip that stage, and
    a cluster triage never saw is deliberately unpublishable.
    """
    article.metadata = dict(article.metadata or {}) | {
        "triage": {
            "category": category,
            "impact_labels": list(impact_labels),
            "story_type": story_type,
            "pk_relevance": pk_relevance,
            "confidence": confidence,
        }
    }
    return article


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

    def update_article_body(
        self, article_id: UUID, main_text: str, metadata: Optional[Dict[str, object]] = None
    ) -> None:
        article = self._articles_by_id[article_id]
        article.main_text = main_text
        if metadata is not None:
            article.metadata = dict(metadata)

    def update_article_metadata(self, article_id: UUID, metadata: Dict[str, object]) -> None:
        self._articles_by_id[article_id].metadata = dict(metadata)

    def update_article_embedding(self, article_id: UUID, embedding: List[float]) -> None:
        self._articles_by_id[article_id].embedding = list(embedding)

    def get_articles_since(self, since: datetime, limit: int = 2000) -> List[RawArticle]:
        rows = [a for a in self._articles_by_id.values() if a.scraped_at >= since]
        return rows[:limit]

    def get_articles_without_clusters_since(
        self, since: datetime, limit: Optional[int] = None
    ) -> List[RawArticle]:
        rows = [
            a
            for a in self._articles_by_id.values()
            if a.cluster_id is None and a.scraped_at >= since
        ]
        return rows[:limit]

    def get_articles_without_embeddings(self, limit: int = 100) -> List[RawArticle]:
        rows = [a for a in self._articles_by_id.values() if a.embedding is None]
        return rows[:limit]

    def get_articles_with_embeddings_since(
        self, since: datetime, limit: Optional[int] = None
    ) -> List[RawArticle]:
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

    def get_all_clusters(
        self, limit: Optional[int] = 100, *, order: str = "recent"
    ) -> List[Cluster]:
        clusters = list(self._clusters_by_id.values())
        if order == "size":
            clusters.sort(key=lambda c: -int(getattr(c, "cluster_size", 0) or 0))
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


def test_recent_regrouping_requests_the_entire_bounded_window(tmp_path):
    class RecordingDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.unclustered_limit = "unset"
            self.embedded_limit = "unset"

        def get_articles_without_clusters_since(self, since, limit=None):
            self.unclustered_limit = limit
            return []

        def get_articles_with_embeddings_since(self, since, limit=None):
            self.embedded_limit = limit
            return []

    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text("sources: {}\n", encoding="utf-8")
    db = RecordingDB()
    runner = PipelineOrchestrator(
        config=PipelineConfig(sources_yaml=sources_yaml, recluster_recent_window=True),
        db=db,  # type: ignore[arg-type]
    )
    stats = PipelineStats()

    runner.remediate_recent_clusters(stats)
    runner.cluster_unclustered_articles(stats)

    assert db.embedded_limit is None
    assert db.unclustered_limit is None


def test_pipeline_orchestrator_chains_phases(tmp_path):
    # Minimal sources config with two enabled sources.
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )


    nlp = spacy.blank("en")
    extractor = EntityExtractor(nlp=nlp)
    consensus = ConsensusDetector(min_agreement_ratio=1.0)
    analyzer = AnalysisService(entity_extractor=extractor, consensus_detector=consensus)
    now = datetime.now(timezone.utc)

    a1 = RawArticle(
        source="dawn",
        url="https://example.com/a",
        headline="Pakistan talks to IMF",
        main_text=("Pakistan IMF rupee " * 30),
        publish_date=now,
        scraped_at=now,
    )
    a2 = RawArticle(
        source="tribune",
        url="https://example.com/b",
        headline="IMF meeting in Pakistan",
        main_text=("Pakistan IMF inflation " * 30),
        publish_date=now,
        scraped_at=now,
    )
    off = RawArticle(
        source="dawn",
        url="https://evil.com/phish",
        headline="Off domain",
        main_text=("Pakistan IMF " * 30),
        publish_date=now,
        scraped_at=now,
    )

    fake_ingestor = FakeIngestor({"dawn": [a1, off], "tribune": [a2]})

    # Two identical unit vectors ⇒ centroid and similarity are deterministic.
    emb = np.zeros((2, 768), dtype=np.float32)
    emb[:, 0] = 1.0
    fake_embedder = FakeEmbedder(embeddings=emb)
    fake_clusterer = FakeClusterer(labels=[0, 0])

    db = FakeDB()
    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        min_cluster_size=2,
        analyze_recent_clusters_limit=10,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=fake_ingestor,  # type: ignore[arg-type]
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


def test_deterministic_fallback_caps_inserted_feeds_to_editorial_max_stories(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    }
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )

    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
    )

    db = FakeDB()
    now = datetime.now(timezone.utc)
    for idx in range(4):
        article_ids = []
        for source in ("dawn", "tribune"):
            article = RawArticle(
                source=source,
                url=f"https://example.com/{source}/story-{idx}",
                headline=f"Fuel subsidy change {idx}",
                main_text=("fuel subsidy government petrol inflation " * 30),
                embedding=[1.0, 0.0, 0.0],
                publish_date=now - timedelta(hours=idx),
                scraped_at=now - timedelta(hours=idx),
            )
            db.insert_article(_triaged(article))
            article_ids.append(article.id)
        cluster_id = uuid4()
        db.create_cluster(
            cluster_id=cluster_id,
            article_ids=article_ids,
            centroid_embedding=[1.0, 0.0, 0.0],
            algorithm_used="event_graph",
        )
        for article_id in article_ids:
            db.assign_to_cluster(article_id, cluster_id)

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        min_cluster_size=1,
        analyze_recent_clusters_limit=10,
        editorial_max_stories=2,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
        analyzer=analyzer,
        editorial_service=FailingEditorialService(),
    )

    stats = PipelineStats()
    runner.analyze_clusters_missing_feed(stats)

    # An editorial outage publishes nothing at all. It used to ship template
    # cards - a drill on 2026-08-25 replaced a real brief with twelve cards
    # reading "This could affect public life in Pakistan today and is worth
    # tracking closely", stamped as today's and served under "Today's brief".
    # Leaving the previous brief in place, to be served as stale, is better
    # than filler dressed as news.
    assert stats.feeds_inserted == 0
    assert db._feed_by_cluster == {}
    assert stats.editorial_status == "unavailable"


def test_editorial_selection_is_supplemented_to_story_floor(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    }
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )

    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
    )
    db = FakeDB()
    now = datetime.now(timezone.utc)
    cluster_ids: List[UUID] = []

    for idx in range(6):
        article_ids = []
        for source in ("dawn", "tribune"):
            article = RawArticle(
                source=source,
                url=f"https://example.com/{source}/yield-{idx}",
                headline=f"Fuel relief measure {idx}",
                main_text=("fuel relief commuters prices government " * 30),
                embedding=[1.0, 0.0, 0.0],
                publish_date=now - timedelta(hours=idx),
                scraped_at=now - timedelta(hours=idx),
            )
            db.insert_article(_triaged(article))
            article_ids.append(article.id)
        cluster_id = uuid4()
        cluster_ids.append(cluster_id)
        db.create_cluster(
            cluster_id=cluster_id,
            article_ids=article_ids,
            centroid_embedding=[1.0, 0.0, 0.0],
            algorithm_used="event_graph",
        )
        for article_id in article_ids:
            db.assign_to_cluster(article_id, cluster_id)

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            min_cluster_size=1,
            analyze_recent_clusters_limit=20,
            recluster_recent_window=False,
            editorial_max_stories=9,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
        analyzer=analyzer,
        editorial_service=FakeEditorialService(cluster_ids[:4]),  # type: ignore[arg-type]
    )

    stats = runner.run()

    assert stats.feeds_inserted == 3
    assert stats.feeds_rejected_editorial == 3
    assert len(db._feed_by_cluster) == 3
    llm_augmented_count = sum(
        1 for feed in db._feed_by_cluster.values() if (feed.metadata or {}).get("llm_augmented")
    )
    assert llm_augmented_count == 3


def test_deterministic_supplemental_feeds_get_renderable_brief_copy(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "geo": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )

    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
    )
    db = FakeDB()
    now = datetime.now(timezone.utc)

    for idx in range(2):
        article_ids = []
        for source in ("dawn", "geo"):
            article = RawArticle(
                source=source,
                url=f"https://example.com/{source}/budget-{idx}",
                headline=f"Budget preparation update {idx}",
                main_text=("budget imf inflation petrol subsidy " * 30),
                embedding=[1.0, 0.0, 0.0],
                publish_date=now - timedelta(hours=idx),
                scraped_at=now - timedelta(hours=idx),
            )
            db.insert_article(_triaged(article))
            article_ids.append(article.id)
        cluster_id = uuid4()
        db.create_cluster(
            cluster_id=cluster_id,
            article_ids=article_ids,
            centroid_embedding=[1.0, 0.0, 0.0],
            algorithm_used="event_graph",
        )
        for article_id in article_ids:
            db.assign_to_cluster(article_id, cluster_id)

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            min_cluster_size=1,
            analyze_recent_clusters_limit=20,
            recluster_recent_window=False,
            editorial_max_stories=5,
            # Switched off deliberately, which is what `eval_golden_day.py`
            # does to score selection and ordering without spending LLM calls.
            # Distinct from an outage, which publishes nothing.
            enable_editorial_llm=False,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
        analyzer=analyzer,
    )

    stats = runner.run()

    assert stats.editorial_status == "disabled"
    assert stats.feeds_inserted >= 1
    for feed in db._feed_by_cluster.values():
        assert (feed.metadata or {}).get("why_it_matters")
        assert (feed.metadata or {}).get("what_to_watch")
        assert (feed.metadata or {}).get("copy_generation_mode") == "deterministic_fallback"


def test_scrape_stage_uses_runtime_article_cap_over_yaml_default(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 20},
            }
        ),
        encoding="utf-8",
    )
    ingestor = FakeIngestor({"dawn": []})
    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            max_articles_per_source=4,
            recluster_recent_window=False,
        ),
        db=FakeDB(),  # type: ignore[arg-type]
        ingestor=ingestor,  # type: ignore[arg-type]
    )

    runner.scrape_and_insert()

    assert ingestor.runs == 1

    # The runtime override must reach a real ingestor, not just the yaml default.
    built = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            max_articles_per_source=4,
            recluster_recent_window=False,
        ),
        db=FakeDB(),  # type: ignore[arg-type]
    )._get_ingestor(yaml.safe_load(sources_yaml.read_text(encoding="utf-8")))
    assert built.max_articles_per_source == 4
    assert [spec.name for spec in built.sources] == ["dawn"]


def test_pipeline_daily_digest_window_skips_old_articles(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )

    nlp = spacy.blank("en")
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=nlp),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
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
    fake_ingestor = FakeIngestor({"dawn": [recent], "tribune": [old]})

    emb = np.zeros((2, 768), dtype=np.float32)
    emb[:, 0] = 1.0
    fake_embedder = FakeEmbedder(embeddings=emb)
    fake_clusterer = FakeClusterer(labels=[0, 0])

    db = FakeDB()
    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        min_cluster_size=1,
        cluster_lookback_hours=24,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=fake_ingestor,  # type: ignore[arg-type]
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
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    }
                    ,
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
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
    fake_ingestor = FakeIngestor({"dawn": [existing]})
    emb = np.zeros((1, 768), dtype=np.float32)
    emb[:, 0] = 1.0
    fake_embedder = FakeEmbedder(embeddings=emb)
    fake_clusterer = FakeClusterer(labels=[-1])

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        embedding_backfill_limit=10,
        cluster_lookback_hours=24,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=fake_ingestor,  # type: ignore[arg-type]
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
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
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

    fake_ingestor = FakeIngestor({"dawn": [] , "tribune": []})
    fake_embedder = FakeEmbedder(embeddings=np.zeros((0, 768), dtype=np.float32))
    fake_clusterer = FakeClusterer(labels=[])

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        retention_days=7,
        embedding_backfill_limit=0,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=fake_ingestor,  # type: ignore[arg-type]
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
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
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

    fake_ingestor = FakeIngestor({"dawn": [], "tribune": []})
    fake_embedder = FakeEmbedder(embeddings=np.zeros((0, 768), dtype=np.float32))
    fake_clusterer = FakeClusterer(labels=[])

    cfg = PipelineConfig(
        sources_yaml=sources_yaml,
        retention_days=7,
        embedding_backfill_limit=0,
        recluster_recent_window=False,
        refresh_existing_feeds=True,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=fake_ingestor,  # type: ignore[arg-type]
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
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    }
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
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
        recluster_recent_window=False,
        refresh_existing_feeds=True,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({"dawn": []}),  # type: ignore[arg-type]
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
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                    "tribune": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
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
                publish_date=datetime.now(timezone.utc),
            ),
            RawArticle(
                source="tribune",
                url=f"https://example.com/{cluster_no}-b",
                headline=f"Pakistan story {cluster_no} B",
                main_text=("Pakistan inflation IMF " * 30),
                embedding=[1.0, 0.0, 0.0],
                publish_date=datetime.now(timezone.utc),
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
            recluster_recent_window=False,
            editorial_candidate_limit=10,
            editorial_max_stories=5,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
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



def test_publish_gate_keeps_high_impact_single_source_civic_story(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                    "tribune": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
    )
    db = FakeDB()

    cluster_id = db.create_cluster(article_ids=[])
    articles = [
        RawArticle(
            source="dawn",
            url="https://example.com/karachi-rain-1",
            headline="Heavy rain triggers emergency in Karachi as roads flood",
            main_text=(
                "Heavy rain flooded major roads in Karachi, stranded passengers, and prompted rescue teams "
                "to respond through the night. " * 8
            ),
            embedding=[1.0, 0.0, 0.0],
            publish_date=datetime.now(timezone.utc),
        ),
        RawArticle(
            source="dawn",
            url="https://example.com/karachi-rain-2",
            headline="Karachi commuters stranded after floodwaters block roads",
            main_text=(
                "Floodwaters blocked highways and roads in Karachi, leaving passengers stranded as emergency "
                "workers carried out rescue activity. " * 8
            ),
            embedding=[0.98, 0.02, 0.0],
            publish_date=datetime.now(timezone.utc),
        ),
    ]

    for article in articles:
        db.insert_article(article)
        db.assign_to_cluster(article.id, cluster_id)
        db._clusters_by_id[cluster_id].add_article(article.id)

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(category="city"),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
        analyzer=analyzer,
    )

    stats = runner.run()

    assert stats.feeds_inserted == 1
    assert cluster_id in db._feed_by_cluster
    feed = db._feed_by_cluster[cluster_id]
    assert feed.category == "city"
    assert "🚦 COMMUTE" in feed.impact_labels
    evidence = feed.metadata["evidence"]
    assert evidence["source_count"] == 1, "a single-source story still reaches the brief"
    assert evidence["story_type"] == "hard_news"
    assert "deterministic_publish_score" not in feed.metadata




def test_missing_publish_date_articles_are_rejected_and_source_is_marked_degraded(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": True},
                    "tribune": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    ingestor = FakeIngestor(
        {
            "dawn": [
                RawArticle(
                    source="dawn",
                    url="https://example.com/no-date",
                    headline="Undated item",
                    main_text=("x " * 80),
                    publish_date=None,
                )
            ]
        }
    )
    db = FakeDB()
    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=ingestor,  # type: ignore[arg-type]
    )

    stats = runner.run()

    assert stats.inserted == 0
    assert stats.source_article_counts["dawn"] == 0
    assert stats.degraded_sources == ["dawn"]



def test_diversity_rules_cap_politics_and_keep_economy(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                    "tribune": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
        ),
        db=FakeDB(),  # type: ignore[arg-type]
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
    )

    def _candidate(index: int, category: str) -> ClusterEditorialCandidate:
        article = RawArticle(
            source="dawn" if category == "politics" else "tribune",
            url=f"https://example.com/{category}-{index}",
            headline=f"{category.title()} headline {index}",
            main_text=("x " * 80),
            publish_date=datetime.now(timezone.utc),
            embedding=[1.0, 0.0, 0.0],
        )
        feed = AnalyzedFeed(
            cluster_id=uuid4(),
            headline=article.headline,
            summary="Snippet",
            category=category,
            impact_labels=["🏛️ GOVERNANCE"] if category == "politics" else ["💳 WALLET"],
            source_attribution={article.source: 1},
            metadata={"evidence": {"source_count": 9 - index}},
        )
        return ClusterEditorialCandidate(
            cluster_id=feed.cluster_id,
            base_feed=feed,
            representative_article=article,
            articles=(article,),
            algorithm_used="singleton",
            avg_similarity=1.0,
            min_member_similarity=1.0,
        )

    ranked_candidates = [_candidate(index, "politics") for index in range(6)] + [_candidate(6, "economy")]
    selected = runner._select_diverse_candidates(ranked_candidates, max_items=7)

    categories = [candidate.base_feed.category for candidate in selected]
    assert categories.count("politics") == 3
    assert "economy" in categories


def test_diversity_rules_keep_one_card_per_named_story_family(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    }
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    runner = PipelineOrchestrator(
        config=PipelineConfig(sources_yaml=sources_yaml, recluster_recent_window=False),
        db=FakeDB(),  # type: ignore[arg-type]
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
    )

    def _candidate(headline: str, sources: int = 1) -> ClusterEditorialCandidate:
        articles = tuple(
            RawArticle(
                source=name,
                url=f"https://example.com/{uuid4()}",
                headline=headline,
                main_text=("x " * 80),
                publish_date=datetime.now(timezone.utc),
                embedding=[1.0, 0.0, 0.0],
            )
            for name in ("dawn", "geo", "ary", "nation")[:sources]
        )
        feed = AnalyzedFeed(
            cluster_id=uuid4(),
            headline=headline,
            summary="Snippet",
            category="politics",
            impact_labels=["🏛️ GOVERNANCE"],
            source_attribution={article.source: 1 for article in articles},
        )
        return ClusterEditorialCandidate(
            cluster_id=feed.cluster_id,
            base_feed=feed,
            representative_article=articles[0],
            articles=articles,
            algorithm_used="event_graph",
            avg_similarity=1.0,
            min_member_similarity=1.0,
        )

    selected = runner._select_diverse_candidates(
        [
            _candidate("National Assembly forms PIMS fact-finding committee"),
            _candidate("Health secretary removed following PIMS tragedy"),
            _candidate("Judicial commission begins Mir Raza inquiry"),
        ],
        max_items=3,
    )

    assert [candidate.base_feed.headline for candidate in selected] == [
        "National Assembly forms PIMS fact-finding committee",
        "Judicial commission begins Mir Raza inquiry",
    ]


def test_a_well_corroborated_story_is_not_collapsed_into_another_card_family(tmp_path):
    """Four publishers is a story, not a presentation-layer duplicate.

    A province-wide hospital safety audit carried by four publishers was being
    deleted from the brief behind the fire that prompted it, purely because a
    member headline named PIMS.
    """
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": False,
                    }
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    runner = PipelineOrchestrator(
        config=PipelineConfig(sources_yaml=sources_yaml, recluster_recent_window=False),
        db=FakeDB(),  # type: ignore[arg-type]
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
    )

    def _candidate(headline: str, sources: int) -> ClusterEditorialCandidate:
        articles = tuple(
            RawArticle(
                source=name,
                url=f"https://example.com/{uuid4()}",
                headline=headline,
                main_text=("x " * 80),
                publish_date=datetime.now(timezone.utc),
                embedding=[1.0, 0.0, 0.0],
            )
            for name in ("dawn", "geo", "ary", "nation")[:sources]
        )
        feed = AnalyzedFeed(
            cluster_id=uuid4(),
            headline=headline,
            summary="Snippet",
            category="politics",
            impact_labels=["🏛️ GOVERNANCE"],
            source_attribution={article.source: 1 for article in articles},
        )
        return ClusterEditorialCandidate(
            cluster_id=feed.cluster_id,
            base_feed=feed,
            representative_article=articles[0],
            articles=articles,
            algorithm_used="event_graph",
            avg_similarity=1.0,
            min_member_similarity=1.0,
        )

    selected = runner._select_diverse_candidates(
        [
            _candidate("14 newborns killed in fire at PIMS Hospital", sources=4),
            _candidate("PIMS fire: Punjab CM directs safety audits of govt hospitals", sources=4),
            _candidate("My head hanged in shame over PIMS incident: AG Punjab", sources=1),
        ],
        max_items=3,
    )

    headlines = [candidate.base_feed.headline for candidate in selected]
    assert "PIMS fire: Punjab CM directs safety audits of govt hospitals" in headlines
    assert "My head hanged in shame over PIMS incident: AG Punjab" not in headlines


def test_editorial_candidate_articles_are_capped_at_eight(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                    "tribune": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
        ),
        db=FakeDB(),  # type: ignore[arg-type]
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
    )

    now = datetime.now(timezone.utc)
    articles = [
        RawArticle(
            source=f"source-{index % 4}",
            url=f"https://example.com/story-{index}",
            headline=f"Story {index}",
            main_text=("x " * 80),
            publish_date=now - timedelta(minutes=index),
            scraped_at=now - timedelta(minutes=index),
            embedding=[1.0, 0.0, 0.0],
        )
        for index in range(12)
    ]

    selected = runner._select_editorial_articles(articles, max_articles=8)

    assert len(selected) == 8


def test_publish_score_carries_publisher_topline_metadata(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                    "geo": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                    "tribune": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": False},
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )

    class _Analyzer:
        def choose_representative_article(self, articles: List[RawArticle]) -> RawArticle:
            return articles[0]

        def analyze_cluster(self, cluster_id: UUID, articles: List[RawArticle]) -> AnalyzedFeed:
            sources: Dict[str, int] = {}
            for a in articles:
                sources[a.source] = sources.get(a.source, 0) + 1
            return AnalyzedFeed(
                cluster_id=cluster_id,
                headline="Pakistan facilitates US-Iran ceasefire",
                summary="Pakistan says it helped secure a ceasefire understanding.",
                category="politics",
                confirmed_facts=[],
                debated_claims=[],
                impact_labels=["🏛️ GOVERNANCE"],
                source_attribution=sources,
                entity_counts={},
                classification_confidence=0.8,
                metadata={},
            )

    db = FakeDB()
    cluster_id = db.create_cluster(article_ids=[])
    now = datetime.now(timezone.utc)
    articles = [
        RawArticle(
            source="dawn",
            url="https://example.com/a",
            headline="Pakistan facilitates US-Iran ceasefire",
            main_text=("x " * 80),
            scraped_at=now,
            embedding=[1.0, 0.0, 0.0],
            metadata={"source_prominence_score": 24, "topline_bucket": "lead"},
        ),
        RawArticle(
            source="geo",
            url="https://example.com/b",
            headline="Pakistan role praised in US-Iran ceasefire",
            main_text=("x " * 80),
            scraped_at=now,
            embedding=[0.99, 0.01, 0.0],
            metadata={"source_prominence_score": 18, "topline_bucket": "topline"},
        ),
        RawArticle(
            source="tribune",
            url="https://example.com/c",
            headline="Ceasefire follows Pakistan mediation effort",
            main_text=("x " * 80),
            scraped_at=now,
            embedding=[0.98, 0.02, 0.0],
            metadata={"source_prominence_score": 18, "topline_bucket": "topline"},
        ),
    ]
    for article in articles:
        db.insert_article(article)
        db.assign_to_cluster(article.id, cluster_id)
        db._clusters_by_id[cluster_id].add_article(article.id)

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
        analyzer=_Analyzer(),  # type: ignore[arg-type]
    )

    runner.run()

    feed = db._feed_by_cluster[cluster_id]
    assert feed.metadata["publisher_topline_score"] >= 36
    assert set(feed.metadata["publisher_topline_sources"]) == {"dawn", "geo", "tribune"}
    assert feed.metadata["selection_mode"] == "national_topline"



def test_host_allowed_accepts_www_and_bare_domain_variants():
    assert PipelineOrchestrator._host_allowed("https://dawn.com/news/1001", "https://www.dawn.com")
    assert PipelineOrchestrator._host_allowed("https://www.dawn.com/news/1001", "https://dawn.com")
    assert not PipelineOrchestrator._host_allowed("https://images.dawn.com/news/1001", "https://www.dawn.com")


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
        recluster_recent_window=False,
        min_cluster_size=2,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
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
        recluster_recent_window=False,
        min_cluster_size=2,
        max_cluster_articles_per_source=2,
        max_cluster_articles=10,
    )
    runner = PipelineOrchestrator(
        config=cfg,
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
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


def _rss_sources_yaml(tmp_path) -> Path:
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "url": "https://example.com",
                        "tier": "A",
                        "feed_urls": ["https://example.com/rss"],
                        "enabled": True,
                    },
                    "geo": {
                        "url": "https://example.com",
                        "tier": "B",
                        "feed_urls": ["https://example.com/geo-rss"],
                        "sitemap_urls": ["https://example.com/geo-sitemap"],
                        "enabled": True,
                    },
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    return sources_yaml


def test_quarantined_endpoints_surface_in_stats_and_heartbeat_payload(tmp_path):
    """A dead feed must be visible, not silent."""
    sources_yaml = _rss_sources_yaml(tmp_path)
    now = datetime.now(timezone.utc)

    fresh = RawArticle(
        source="dawn",
        url="https://example.com/fresh",
        headline="Fresh story",
        main_text=("Pakistan IMF budget " * 40),
        publish_date=now,
        scraped_at=now,
    )
    reports = [
        EndpointReport(
            source="dawn",
            channel="rss",
            url="https://example.com/rss",
            status="ok",
            newest_age_hours=0.5,
            item_count=1,
        ),
        EndpointReport(
            source="geo",
            channel="rss",
            url="https://example.com/geo-rss",
            status="STALE",
            newest_age_hours=7074.3,
            item_count=0,
        ),
        EndpointReport(
            source="geo",
            channel="sitemap",
            url="https://example.com/geo-sitemap",
            status="no-dates",
            item_count=0,
        ),
    ]

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
        ),
        db=FakeDB(),  # type: ignore[arg-type]
        ingestor=FakeIngestor({"dawn": [fresh]}, reports=reports),  # type: ignore[arg-type]
    )

    stats, inserted = runner.scrape_and_insert()

    assert [a.headline for a in inserted] == ["Fresh story"]
    assert "geo:rss:STALE" in stats.degraded_sources
    assert "geo:sitemap:no-dates" in stats.degraded_sources
    assert "geo" in stats.degraded_sources  # the source produced nothing usable
    assert stats.sources_attempted == 2
    assert stats.sources_succeeded == 1
    assert stats.source_article_counts == {"dawn": 1, "geo": 0}

    payload = stats.as_dict()
    stale = next(row for row in payload["endpoint_health"] if row["status"] == "STALE")
    assert stale["newest_age_hours"] == 7074.3
    assert stale["url"] == "https://example.com/geo-rss"


def test_ingest_skips_urls_already_in_the_database(tmp_path):
    sources_yaml = _rss_sources_yaml(tmp_path)
    now = datetime.now(timezone.utc)

    existing = RawArticle(
        source="dawn",
        url="https://example.com/known",
        headline="Known story",
        main_text=("Pakistan IMF budget " * 40),
        publish_date=now,
        scraped_at=now,
    )
    db = FakeDB()
    db.insert_article(existing)

    rediscovered = RawArticle(
        source="dawn",
        url="https://example.com/known/",  # same article, trailing slash
        headline="Known story",
        main_text=("Pakistan IMF budget " * 40),
        publish_date=now,
        scraped_at=now,
    )

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({"dawn": [rediscovered]}),  # type: ignore[arg-type]
    )

    stats, inserted = runner.scrape_and_insert()

    assert inserted == []
    assert stats.duplicates == 1
    assert stats.scraped == 1


class RecordingBodyFetcher:
    def __init__(self, min_chars: int = 600):
        self.min_chars = min_chars
        self.hydrated: List[str] = []

    def needs_body(self, article: RawArticle) -> bool:
        return len(article.main_text) < self.min_chars

    def hydrate(self, article: RawArticle) -> bool:
        self.hydrated.append(str(article.url))
        article.main_text = "Fetched body. " * 60
        article.metadata = {**(article.metadata or {}), "body_status": "full"}
        return True

    def close(self) -> None:
        return None


def test_lazy_body_fetch_runs_only_for_shortlisted_representatives(tmp_path):
    """The expensive path is bounded by the editorial shortlist, not the pool."""
    sources_yaml = _rss_sources_yaml(tmp_path)
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
    )
    db = FakeDB()
    now = datetime.now(timezone.utc)

    cluster_ids: List[UUID] = []
    for cluster_no in range(3):
        articles = [
            RawArticle(
                source="dawn",
                url=f"https://example.com/{cluster_no}-a",
                headline=f"Pakistan inflation story {cluster_no}",
                main_text=("Pakistan inflation budget IMF " * 30),
                embedding=[1.0, 0.0, 0.0],
                publish_date=now,
                metadata={"body_status": "full"},
            ),
            RawArticle(
                source="geo",
                url=f"https://example.com/{cluster_no}-b",
                headline=f"Pakistan inflation story {cluster_no} follow-up",
                main_text=f"Pakistan inflation story {cluster_no} follow-up",
                embedding=[1.0, 0.0, 0.0],
                publish_date=now,
                metadata={"body_status": "headline_only"},
            ),
        ]
        for article in articles:
            db.insert_article(article)
        cluster_id = db.create_cluster(article_ids=[a.id for a in articles])
        cluster_ids.append(cluster_id)
        for article in articles:
            db.assign_to_cluster(article.id, cluster_id)

    body_fetcher = RecordingBodyFetcher()
    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
            editorial_candidate_limit=1,
            editorial_max_stories=5,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=FakeIngestor({}),  # type: ignore[arg-type]
        analyzer=analyzer,
        editorial_service=FakeEditorialService(cluster_ids),  # type: ignore[arg-type]
        body_fetcher=body_fetcher,  # type: ignore[arg-type]
    )

    stats = PipelineStats()
    runner.analyze_clusters_missing_feed(stats)

    # editorial_candidate_limit=1, so at most one representative is fetched,
    # even though every cluster contains a thin Tier B article.
    assert len(body_fetcher.hydrated) <= 1
    assert stats.lazy_body_fetches == len(body_fetcher.hydrated)
    for url in body_fetcher.hydrated:
        stored = db._articles_by_id[db._articles_by_url[url]]
        assert stored.metadata["body_status"] == "full"
        assert len(stored.main_text) >= 600


def test_lazy_body_fetch_failure_is_counted_and_non_fatal(tmp_path):
    sources_yaml = _rss_sources_yaml(tmp_path)

    class FailingFetcher(RecordingBodyFetcher):
        def hydrate(self, article: RawArticle) -> bool:
            raise RuntimeError("403 from publisher")

    thin = RawArticle(
        source="geo",
        url="https://example.com/thin",
        headline="Thin corroboration record",
        main_text="Thin corroboration record",
        publish_date=datetime.now(timezone.utc),
        metadata={"body_status": "headline_only"},
    )
    candidate = ClusterEditorialCandidate(
        cluster_id=uuid4(),
        base_feed=AnalyzedFeed(
            cluster_id=uuid4(),
            headline="Thin corroboration record",
            category="other",
        ),
        representative_article=thin,
        articles=(thin,),
        algorithm_used="event_graph",
        avg_similarity=1.0,
        min_member_similarity=1.0,
    )

    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {
                        "name": "Dawn",
                        "url": "https://www.dawn.com",
                        "enabled": True,
                        "tier": "A",
                        "feed_urls": ["https://www.dawn.com/feeds/home"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    runner = PipelineOrchestrator(
        # embed_articles never reads the sources file.
        config=PipelineConfig(sources_yaml=tmp_path / "sources.yaml"),
        db=FakeDB(),  # type: ignore[arg-type]
        body_fetcher=FailingFetcher(),  # type: ignore[arg-type]
    )

    stats = PipelineStats()
    runner._hydrate_representative_bodies([candidate], stats)

    assert stats.lazy_body_fetches == 0
    assert stats.lazy_body_fetch_failures == 1
    assert thin.main_text == "Thin corroboration record"


def test_story_analysis_circuit_breaker_preserves_all_selected_cards(tmp_path):
    sources_yaml = _rss_sources_yaml(tmp_path)
    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
    )
    db = FakeDB()
    now = datetime.now(timezone.utc)
    cluster_ids: List[UUID] = []
    categories = ["economy", "politics", "health", "security"]
    labels = ["💳 WALLET", "🏛️ GOVERNANCE", "🛡️ SAFETY", "🛡️ SAFETY"]
    for index, (category, label) in enumerate(zip(categories, labels)):
        article = _triaged(
            RawArticle(
                source="dawn",
                url=f"https://example.com/circuit-{index}",
                headline=f"Distinctive Agency{index} announces a public development",
                main_text=(f"Distinctive Agency{index} public development. " * 30),
                embedding=[1.0, float(index) / 100.0, 0.0],
                publish_date=now,
                scraped_at=now,
                metadata={"body_status": "full"},
            ),
            category=category,
            impact_labels=(label,),
        )
        db.insert_article(article)
        cluster_id = db.create_cluster(article_ids=[article.id])
        db.assign_to_cluster(article.id, cluster_id)
        cluster_ids.append(cluster_id)

    story_service = FailingStoryAnalysisService()
    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            recluster_recent_window=False,
            enable_editorial_llm=True,
            enable_story_analysis_llm=True,
            editorial_max_stories=4,
        ),
        db=db,  # type: ignore[arg-type]
        analyzer=analyzer,
        editorial_service=FakeEditorialService(cluster_ids),  # type: ignore[arg-type]
        story_analysis_service=story_service,  # type: ignore[arg-type]
    )
    stats = PipelineStats()

    feed_ids = runner.analyze_clusters_missing_feed(stats)

    assert len(feed_ids) == 4
    assert story_service.calls == 3
    assert stats.story_analysis_calls == 3
    assert stats.story_analysis_fallbacks == 4
    assert stats.story_analysis_status == "unavailable"
    assert all(
        (feed.metadata or {}).get("story_analysis", {}).get("status") == "fallback"
        for feed in db._feed_by_cluster.values()
    )


# ---------------------------------------------------------------------------
# Hard gates: the only deterministic exclusions left after R-4.
# ---------------------------------------------------------------------------


def _gate_candidate(tmp_path, **triage):
    """A minimal candidate carrying one triage verdict, for gate testing."""
    from src.agents.editorial import ClusterEditorialCandidate
    from src.db.models import AnalyzedFeed

    now = datetime.now(timezone.utc)
    article = _triaged(
        RawArticle(
            source="dawn",
            url="https://example.com/gate-story",
            headline="A development in Pakistan today",
            main_text="Body text " * 40,
            publish_date=triage.pop("publish_date", now),
            scraped_at=now,
        ),
        **triage,
    )
    verdict = article.metadata["triage"]
    feed = AnalyzedFeed(
        cluster_id=uuid4(),
        headline=article.headline,
        summary="A summary.",
        category=verdict["category"],
        impact_labels=list(verdict["impact_labels"]),
        source_attribution={"dawn": 1},
        classification_confidence=verdict["confidence"],
    )
    return ClusterEditorialCandidate(
        cluster_id=feed.cluster_id,
        base_feed=feed,
        representative_article=article,
        articles=(article,),
        algorithm_used="event_graph",
        avg_similarity=1.0,
        min_member_similarity=1.0,
    )


def _gate_runner(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump({"sources": {}, "scraping_config": {"max_articles_per_source": 5}}),
        encoding="utf-8",
    )
    return PipelineOrchestrator(
        config=PipelineConfig(sources_yaml=sources_yaml),
        db=FakeDB(),  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "triage,expected_reason",
    [
        ({"category": "sports"}, "excluded category"),
        ({"category": "entertainment"}, "excluded category"),
        ({"story_type": "opinion"}, "excluded story type"),
        ({"story_type": "advertorial"}, "excluded story type"),
        ({"pk_relevance": "foreign"}, "no Pakistan relevance"),
    ],
)
def test_hard_gates_exclude_what_must_never_be_negotiable(tmp_path, triage, expected_reason):
    allowed, reason = _gate_runner(tmp_path)._passes_hard_gates(_gate_candidate(tmp_path, **triage))

    assert not allowed
    assert expected_reason in reason


def test_hard_gates_exclude_a_cluster_triage_never_saw(tmp_path):
    """An article with no verdict cannot be described honestly, so it is not published."""
    candidate = _gate_candidate(tmp_path)
    candidate.articles[0].metadata = {}

    allowed, reason = _gate_runner(tmp_path)._passes_hard_gates(candidate)

    assert not allowed
    assert "no triage verdict" in reason


def test_hard_gates_exclude_a_stale_story(tmp_path):
    runner = _gate_runner(tmp_path)
    stale = datetime.now(timezone.utc) - timedelta(hours=runner.config.article_max_age_hours + 5)

    allowed, reason = runner._passes_hard_gates(_gate_candidate(tmp_path, publish_date=stale))

    assert not allowed
    assert "stale" in reason


@pytest.mark.parametrize(
    "triage",
    [
        {"category": "economy"},
        # Previously rejected by a score threshold; judgement now belongs to the editor.
        {"category": "other", "impact_labels": ()},
        {"category": "international", "pk_relevance": "foreign_with_pk_effect"},
        {"category": "technology", "impact_labels": ()},
        {"story_type": "feature"},
    ],
)
def test_hard_gates_leave_judgement_to_the_editor(tmp_path, triage):
    """No score thresholds: anything not mechanically excluded reaches the editor."""
    allowed, reason = _gate_runner(tmp_path)._passes_hard_gates(_gate_candidate(tmp_path, **triage))

    assert allowed, reason


def test_ranking_does_not_saturate_across_candidates(tmp_path):
    """Every published card scored exactly 100 before R-4, so ranking meant nothing."""
    runner = _gate_runner(tmp_path)
    candidates = [
        _gate_candidate(tmp_path, category="economy"),
        _gate_candidate(tmp_path, category="politics", pk_relevance="local"),
        _gate_candidate(tmp_path, category="health", story_type="feature"),
    ]
    keys = [runner._candidate_evidence(c).ranking_key() for c in candidates]

    assert len(set(keys)) == len(keys), "distinct candidates must order distinctly"
    ranked = runner._rank_publishable_candidates(candidates)
    assert runner._candidate_evidence(ranked[0]).story_type == "hard_news"
    assert runner._candidate_evidence(ranked[-1]).story_type == "feature"


def test_a_missing_embedding_key_degrades_loudly_instead_of_crashing(tmp_path, monkeypatch):
    """Without a key the run raised out of embed_articles and died.

    /health then had nothing to report: it only looked wrong 28 hours later
    when the heartbeat went stale. No embeddings means no new cards, which is a
    real answer - it just has to be recorded.
    """
    from src.agents.embeddings import EmbeddingError
    from src.pipeline import orchestrator as orch

    def _no_provider(*_args, **_kwargs):
        raise EmbeddingError("Gemini API key not provided.")

    monkeypatch.setattr(orch, "GeminiEmbeddingProvider", _no_provider)

    runner = _gate_runner(tmp_path)
    stats = PipelineStats()
    articles = [
        RawArticle(
            source="dawn",
            url="https://www.dawn.com/news/embed-drill",
            headline="A real Pakistani development today",
            main_text="Body text.",
            publish_date=datetime.now(timezone.utc),
        )
    ]

    runner.embed_articles(articles, stats)

    assert stats.embedding_status == "unavailable"
    assert stats.embed_failures == 1
    assert stats.as_dict()["embedding_status"] == "unavailable"

    # Backfill hits the same rows; it must not double-count them.
    runner.embed_articles(articles, stats)
    assert stats.embed_failures == 1


class TestLowCostModeConfig:
    """Low-cost mode lowers defaults; it must never discard explicit config.

    The bare `min()` this replaced cost three consecutive live briefs their
    floor. The scheduled workflow asked for 40 articles per source and got 25,
    silently, which starved clustering and left the editor with a 24-candidate
    shortlist it exhausted on its second attempt - so the short-pass retry had
    nothing deeper to offer and the brief shipped at 4, 4 and 5 cards.
    """

    _LOW_COST_KEYS = (
        "SAAF_MAX_ARTICLES_PER_SOURCE",
        "SAAF_EMBEDDING_BACKFILL_LIMIT",
        "SAAF_EDITORIAL_CANDIDATE_LIMIT",
        "SAAF_EDITORIAL_MAX_STORIES",
    )

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch):
        monkeypatch.delenv("SAAF_LOW_COST_MODE", raising=False)
        for key in self._LOW_COST_KEYS:
            monkeypatch.delenv(key, raising=False)

    def test_low_cost_mode_lowers_unset_defaults(self, monkeypatch):
        monkeypatch.setenv("SAAF_LOW_COST_MODE", "1")
        config = default_config()

        assert config.max_articles_per_source == 25
        assert config.embedding_backfill_limit == 50
        assert config.editorial_candidate_limit == 24

    def test_explicit_value_survives_low_cost_mode(self, monkeypatch):
        # This is the exact pairing in .github/workflows/daily_pipeline.yml.
        monkeypatch.setenv("SAAF_LOW_COST_MODE", "1")
        monkeypatch.setenv("SAAF_MAX_ARTICLES_PER_SOURCE", "40")
        config = default_config()

        assert config.max_articles_per_source == 40

    def test_explicit_candidate_limit_survives_low_cost_mode(self, monkeypatch):
        # The shortlist the editor retries against. Clamped to 24, attempt two
        # saw 24/24 and stopped; there was no deeper candidate to reach for.
        monkeypatch.setenv("SAAF_LOW_COST_MODE", "1")
        monkeypatch.setenv("SAAF_EDITORIAL_CANDIDATE_LIMIT", "30")
        config = default_config()

        assert config.editorial_candidate_limit == 30

    def test_explicit_value_below_the_ceiling_is_still_honoured(self, monkeypatch):
        # Explicit wins in both directions: asking for less than the low-cost
        # ceiling must not be raised up to it.
        monkeypatch.setenv("SAAF_LOW_COST_MODE", "1")
        monkeypatch.setenv("SAAF_MAX_ARTICLES_PER_SOURCE", "10")
        config = default_config()

        assert config.max_articles_per_source == 10

    def test_low_cost_mode_off_uses_full_defaults(self, monkeypatch):
        config = default_config()

        assert config.max_articles_per_source == 40
        assert config.editorial_candidate_limit == 30

    def test_clamping_an_unset_default_is_logged(self, monkeypatch, caplog):
        # The original defect was silence, not the number itself.
        monkeypatch.setenv("SAAF_LOW_COST_MODE", "1")
        with caplog.at_level(logging.INFO, logger="src.pipeline.orchestrator"):
            default_config()

        assert "SAAF_MAX_ARTICLES_PER_SOURCE lowered from 40 to 25" in caplog.text

    def test_keeping_an_explicit_value_is_logged(self, monkeypatch, caplog):
        monkeypatch.setenv("SAAF_LOW_COST_MODE", "1")
        monkeypatch.setenv("SAAF_MAX_ARTICLES_PER_SOURCE", "40")
        with caplog.at_level(logging.INFO, logger="src.pipeline.orchestrator"):
            default_config()

        assert "keeping explicit SAAF_MAX_ARTICLES_PER_SOURCE=40" in caplog.text



class TestPreviousEditionRepeats:
    """A card the reader already read, with nothing reported since, is not news.

    On 2026-09-12 two of four published cards had run in the 2026-09-11 brief,
    one under a byte-identical headline. Nothing caught it: cluster ids are
    regenerated every run so `analyzed_feed_exists(cluster.id)` never matched,
    and the editor rewrites headlines so a headline comparison would have
    missed the second repeat outright.
    """

    def _candidate(self, source, headline, latest):
        article = SimpleNamespace(source=source, headline=headline, scraped_at=latest, publish_date=latest)
        return SimpleNamespace(representative_article=article, articles=[article])

    def _orchestrator(self, rows):
        db = SimpleNamespace(get_analyzed_feed=lambda limit=60: rows)
        orch = PipelineOrchestrator.__new__(PipelineOrchestrator)
        orch.db = db
        orch._previous_edition_cache = None
        return orch

    def _row(self, source, headline, run_at):
        return SimpleNamespace(metadata={
            "brief_run_at": run_at,
            "representative_source": source,
            "representative_headline": headline,
        })

    RAN_AT = "2026-09-11T18:39:46.408269+00:00"
    BEFORE = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    AFTER = datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc)

    def test_suppresses_the_byte_identical_repeat(self):
        # The real one: same representative article, same headline, next day.
        orch = self._orchestrator([
            self._row("nation", "LHC restrains medical colleges from expelling Afghan students", self.RAN_AT)
        ])
        candidate = self._candidate(
            "nation", "LHC restrains medical colleges from expelling Afghan students", self.BEFORE
        )

        assert orch._repeats_previous_edition(candidate) is True

    def test_suppresses_a_repeat_the_editor_reworded(self):
        # The editor published this under two different headlines on
        # consecutive days off one article. Keying on the card headline would
        # have let it straight through; the representative article held still.
        orch = self._orchestrator([
            self._row("tribune", "PM Shehbaz directs no area to face more than two hours of load-shedding", self.RAN_AT)
        ])
        candidate = self._candidate(
            "tribune", "PM Shehbaz directs no area to face more than two hours of load-shedding", self.BEFORE
        )

        assert orch._repeats_previous_edition(candidate) is True

    def test_a_developing_story_is_never_suppressed(self):
        # The safety valve, and the reason the gate is two conditions rather
        # than one. A brief must be able to lead with a running story - the 36h
        # ingest window exists for that - so any reporting filed since the last
        # brief ran clears the candidate however familiar it looks.
        orch = self._orchestrator([
            self._row("nation", "LHC restrains medical colleges from expelling Afghan students", self.RAN_AT)
        ])
        candidate = self._candidate(
            "nation", "LHC restrains medical colleges from expelling Afghan students", self.AFTER
        )

        assert orch._repeats_previous_edition(candidate) is False

    def test_a_different_story_is_untouched(self):
        orch = self._orchestrator([self._row("nation", "Something else entirely", self.RAN_AT)])
        candidate = self._candidate("dawn", "FBR slaps Rs80/litre FED on 3 POL products", self.BEFORE)

        assert orch._repeats_previous_edition(candidate) is False

    def test_only_the_newest_edition_counts(self):
        # Two editions in the table. A story that ran two briefs ago but not in
        # the last one is fair game again.
        older = "2026-09-10T06:00:00+00:00"
        orch = self._orchestrator([
            self._row("nation", "Older story", older),
            self._row("dawn", "Newest edition story", self.RAN_AT),
        ])

        assert orch._repeats_previous_edition(self._candidate("nation", "Older story", self.BEFORE)) is False
        assert orch._repeats_previous_edition(self._candidate("dawn", "Newest edition story", self.BEFORE)) is True

    def test_no_previous_edition_suppresses_nothing(self):
        orch = self._orchestrator([])

        assert orch._repeats_previous_edition(self._candidate("nation", "Anything", self.BEFORE)) is False

    def test_a_database_failure_fails_open(self):
        # Losing the edition is far worse than risking a repeat.
        def boom(limit=60):
            raise RuntimeError("supabase unavailable")

        orch = PipelineOrchestrator.__new__(PipelineOrchestrator)
        orch.db = SimpleNamespace(get_analyzed_feed=boom)
        orch._previous_edition_cache = None

        assert orch._repeats_previous_edition(self._candidate("nation", "Anything", self.BEFORE)) is False

    def test_the_previous_edition_is_read_once_per_run(self):
        calls = []

        def counted(limit=60):
            calls.append(limit)
            return [self._row("nation", "Story", self.RAN_AT)]

        orch = PipelineOrchestrator.__new__(PipelineOrchestrator)
        orch.db = SimpleNamespace(get_analyzed_feed=counted)
        orch._previous_edition_cache = None

        for _ in range(5):
            orch._repeats_previous_edition(self._candidate("nation", "Story", self.BEFORE))

        assert len(calls) == 1
