from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import UUID, uuid4

import numpy as np
import yaml
from urllib.parse import urlparse

from src.agents.analysis import AnalysisService, ConsensusDetector, EntityExtractor, RuleBasedClassifier
from src.agents.clustering import (
    ClusteringResult,
    ClusteringService,
    calculate_centroid,
    calculate_intra_cluster_similarity,
)
from src.agents.embeddings import GeminiEmbeddingProvider
from src.db.client import DuplicateArticleError, SupabaseClient
from src.db.models import AnalyzedFeed, RawArticle
from src.scrapers.hybrid_orchestrator import HybridOrchestrator
from src.utils.validators import validate_sources_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineConfig:
    sources_yaml: Path
    classification_yaml: Path
    max_articles_per_source: int = 50
    enable_playwright_fallback: bool = True
    embedding_batch_size: int = 100
    embedding_backfill_limit: int = 200
    min_cluster_size: int = 2
    min_clusters: int = 2
    max_noise_ratio: float = 0.3
    analyze_recent_clusters_limit: int = 200
    cluster_lookback_hours: int = 24
    retention_days: int = 7


@dataclass
class PipelineStats:
    scraped: int = 0
    inserted: int = 0
    duplicates: int = 0
    embedded: int = 0
    clustered_articles: int = 0
    clusters_created: int = 0
    feeds_inserted: int = 0
    feeds_skipped_existing: int = 0
    pruned_articles: int = 0
    pruned_clusters: int = 0
    pruned_feeds: int = 0


class FeedExistsError(RuntimeError):
    pass


class PipelineOrchestrator:
    """
    Orchestrates the end-to-end Saaf Baat pipeline.

    Designed to be:
    - Incremental (safe to re-run)
    - Dependency-injectable for unit tests
    - Opinionated about MVP: no LLM summaries
    """

    def __init__(
        self,
        config: PipelineConfig,
        db: SupabaseClient,
        scraper: Optional[HybridOrchestrator] = None,
        embedder: Optional[GeminiEmbeddingProvider] = None,
        clusterer: Optional[ClusteringService] = None,
        analyzer: Optional[AnalysisService] = None,
    ):
        self.config = config
        self.db = db
        self.scraper = scraper
        self.embedder = embedder
        self.clusterer = clusterer
        self.analyzer = analyzer

    # ---------------------------------------------------------------------
    # Config / construction
    # ---------------------------------------------------------------------

    @staticmethod
    def load_sources_config(path: Path) -> Dict[str, Any]:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        verdict = validate_sources_config(data)
        if not verdict["valid"]:
            raise ValueError(f"Invalid sources config: {verdict['errors']}")
        return data

    @staticmethod
    def _host_allowed(url: str, base_url: str) -> bool:
        """Allow same host or subdomain of the configured base_url host."""
        try:
            u = urlparse(url)
            b = urlparse(base_url)
            url_host = (u.hostname or "").lower()
            base_host = (b.hostname or "").lower()
            if not url_host or not base_host:
                return False
            if url_host == base_host:
                return True
            return url_host.endswith("." + base_host)
        except Exception:
            return False

    def _get_scraper(self) -> HybridOrchestrator:
        if self.scraper is None:
            self.scraper = HybridOrchestrator(
                enable_playwright_fallback=self.config.enable_playwright_fallback
            )
        return self.scraper

    def _get_embedder(self) -> GeminiEmbeddingProvider:
        if self.embedder is None:
            self.embedder = GeminiEmbeddingProvider()
        return self.embedder

    def _get_clusterer(self) -> ClusteringService:
        if self.clusterer is None:
            self.clusterer = ClusteringService(
                min_clusters=self.config.min_clusters,
                max_noise_ratio=self.config.max_noise_ratio,
                min_cluster_size=self.config.min_cluster_size,
                hdbscan_params={"min_cluster_size": self.config.min_cluster_size},
            )
        return self.clusterer

    def _get_analyzer(self) -> AnalysisService:
        if self.analyzer is None:
            rules = RuleBasedClassifier.from_yaml(self.config.classification_yaml)
            extractor = EntityExtractor()
            detector = ConsensusDetector(min_agreement_ratio=1.0)
            self.analyzer = AnalysisService(
                entity_extractor=extractor,
                consensus_detector=detector,
                classifier=rules,
            )
        return self.analyzer

    # ---------------------------------------------------------------------
    # Phases
    # ---------------------------------------------------------------------

    def scrape_and_insert(self) -> tuple[PipelineStats, List[RawArticle]]:
        stats = PipelineStats()
        sources_cfg = self.load_sources_config(self.config.sources_yaml)
        sources = sources_cfg.get("sources") or {}
        max_per_source = int(
            (sources_cfg.get("scraping_config") or {}).get(
                "max_articles_per_source", self.config.max_articles_per_source
            )
        )

        scraper = self._get_scraper()
        inserted_articles: List[RawArticle] = []

        for source_name, source in sources.items():
            if not source.get("enabled", False):
                continue

            base_url = str(source.get("url"))
            sections = list(source.get("sections") or [])
            feed_url = source.get("feed_url")

            try:
                scraped = scraper.scrape_source(
                    source=source_name,
                    base_url=base_url,
                    sections=sections,
                    max_articles=max_per_source,
                    feed_url=feed_url,
                )
            except Exception as e:
                logger.exception("Scrape failed for %s: %s", source_name, e)
                continue

            stats.scraped += len(scraped)

            for article in scraped:
                if not self._host_allowed(article.url, base_url):
                    logger.warning("Skipping off-domain url for %s: %s", source_name, article.url)
                    continue
                try:
                    self.db.insert_article(article)
                    inserted_articles.append(article)
                    stats.inserted += 1
                except DuplicateArticleError:
                    stats.duplicates += 1
                except Exception as e:
                    logger.warning("Insert failed (%s): %s", article.url, e)

        return stats, inserted_articles

    def embed_articles(self, articles: Sequence[RawArticle], stats: PipelineStats) -> None:
        to_embed = [a for a in articles if a.embedding is None]
        if not to_embed:
            return

        embedder = self._get_embedder()
        texts = [f"{a.headline}. {a.main_text[:500]}" for a in to_embed]
        result = embedder.embed_batch(texts, batch_size=self.config.embedding_batch_size)

        for idx, article in enumerate(to_embed):
            emb = result.embeddings[idx].tolist()
            article.embedding = emb
            try:
                self.db.update_article_embedding(article.id, emb)
                stats.embedded += 1
            except Exception as e:
                logger.warning("Failed updating embedding for %s: %s", article.id, e)

    def embed_backfill(self, stats: PipelineStats) -> None:
        """Resume embeddings for articles that were inserted in previous runs."""
        try:
            pending = self.db.get_articles_without_embeddings(limit=self.config.embedding_backfill_limit)
        except Exception as e:
            logger.warning("Embedding backfill fetch failed: %s", e)
            return

        # Avoid double work (e.g. if caller already has local objects).
        pending = [a for a in pending if a.embedding is None]
        if not pending:
            return

        self.embed_articles(pending, stats)

    def cluster_unclustered_articles(self, stats: PipelineStats, limit: int = 500) -> List[UUID]:
        """
        Cluster DB articles with embeddings but no cluster_id.

        Returns:
            List of created cluster UUIDs (noise excluded).
        """
        since = datetime.now(timezone.utc) - timedelta(hours=self.config.cluster_lookback_hours)
        candidates = self.db.get_articles_without_clusters_since(since=since, limit=limit)
        candidates = [a for a in candidates if a.embedding is not None]
        if len(candidates) < 2:
            return []

        embeddings = np.array([a.embedding for a in candidates], dtype=np.float32)
        clusterer = self._get_clusterer()
        result = clusterer.cluster(embeddings)

        created_cluster_ids: List[UUID] = []
        stats.clustered_articles += len(candidates)

        for label in sorted(set(int(x) for x in result.labels)):
            if label == -1:
                continue

            indices = np.where(result.labels == label)[0]
            cluster_articles = [candidates[i] for i in indices]
            if len(cluster_articles) < self.config.min_cluster_size:
                continue

            cluster_id = uuid4()
            cluster_embeddings = embeddings[indices]
            centroid = calculate_centroid(cluster_embeddings).tolist()
            similarity = calculate_intra_cluster_similarity(cluster_embeddings)

            try:
                self.db.create_cluster(
                    cluster_id=cluster_id,
                    article_ids=[a.id for a in cluster_articles],
                    centroid_embedding=centroid,
                    algorithm_used=result.algorithm_used,
                )
                stats.clusters_created += 1
                created_cluster_ids.append(cluster_id)
            except Exception as e:
                logger.warning("Failed creating cluster %s: %s", cluster_id, e)
                continue

            for article in cluster_articles:
                try:
                    self.db.assign_to_cluster(article.id, cluster_id)
                except Exception as e:
                    logger.warning("Failed assigning %s to %s: %s", article.id, cluster_id, e)

            # Persist similarity for observability without schema changes.
            # We store it on the feed metadata later; keep local for now.
            logger.info("Cluster %s: %d articles, similarity=%.3f", cluster_id, len(indices), similarity)

        return created_cluster_ids

    def analyze_clusters_missing_feed(self, stats: PipelineStats) -> List[UUID]:
        analyzer = self._get_analyzer()

        clusters = self.db.get_all_clusters(limit=self.config.analyze_recent_clusters_limit)
        inserted_feed_ids: List[UUID] = []

        for cluster in clusters:
            if cluster.cluster_size < self.config.min_cluster_size:
                continue

            try:
                if self.db.analyzed_feed_exists(cluster.id):
                    stats.feeds_skipped_existing += 1
                    continue
            except Exception as e:
                logger.warning("Feed-exists check failed for %s: %s", cluster.id, e)

            try:
                articles = self.db.get_articles_by_ids(cluster.article_ids)
                feed = analyzer.analyze_cluster(cluster.id, articles)
                feed_id = self.db.insert_analyzed_feed(feed)
                inserted_feed_ids.append(feed_id)
                stats.feeds_inserted += 1
            except Exception as e:
                logger.warning("Failed analyzing cluster %s: %s", cluster.id, e)

        return inserted_feed_ids

    def prune_old_data(self, stats: PipelineStats) -> None:
        days = int(self.config.retention_days)
        if days <= 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            stats.pruned_feeds += int(self.db.delete_analyzed_feed_older_than(cutoff))
        except Exception as e:
            logger.warning("Failed pruning analyzed_feed: %s", e)
        try:
            stats.pruned_clusters += int(self.db.delete_clusters_older_than(cutoff))
        except Exception as e:
            logger.warning("Failed pruning clusters: %s", e)
        try:
            stats.pruned_articles += int(self.db.delete_raw_articles_older_than(cutoff))
        except Exception as e:
            logger.warning("Failed pruning raw_articles: %s", e)

    # ---------------------------------------------------------------------
    # Public entrypoint
    # ---------------------------------------------------------------------

    def run(self) -> PipelineStats:
        stats, inserted_articles = self.scrape_and_insert()

        # Embedding only for newly inserted articles.
        self.embed_articles(inserted_articles, stats)
        # Resume embeddings that failed in prior runs.
        self.embed_backfill(stats)

        # Clustering uses DB state so it can resume after partial failures.
        self.cluster_unclustered_articles(stats)

        # Analysis also uses DB state and avoids duplicate feed items per cluster.
        self.analyze_clusters_missing_feed(stats)
        self.prune_old_data(stats)

        try:
            if self.scraper is not None:
                self.scraper.close()
        except Exception:
            pass

        return stats


def default_config(
    sources_yaml: Path | str = "backend/config/sources.yaml",
    classification_yaml: Path | str = "backend/config/classification_rules.yaml",
) -> PipelineConfig:
    enable_playwright = os.getenv("SAAF_ENABLE_PLAYWRIGHT_FALLBACK", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    return PipelineConfig(
        sources_yaml=Path(sources_yaml),
        classification_yaml=Path(classification_yaml),
        enable_playwright_fallback=enable_playwright,
    )
