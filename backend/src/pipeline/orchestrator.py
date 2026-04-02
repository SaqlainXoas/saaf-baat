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

from src.agents.analysis import (
    AnalysisService,
    ConsensusDetector,
    EntityExtractor,
    RuleBasedClassifier,
)
from src.agents.dedup import (
    SimHashIndex,
    SimHashIndexConfig,
    hamming_distance64,
    jaccard,
    shingle_hashes,
    simhash64,
)
from src.agents.clustering import (
    ClusteringResult,
    ClusteringService,
    calculate_centroid,
    calculate_intra_cluster_similarity,
)
from src.agents.editorial import (
    ClusterEditorialCandidate,
    EditorialError,
    GroqMorningBriefService,
    merge_editorial_story,
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
    max_articles_per_source: int = 30
    enable_playwright_fallback: bool = True
    embedding_batch_size: int = 100
    embedding_backfill_limit: int = 100
    min_cluster_size: int = 2
    min_clusters: int = 2
    max_noise_ratio: float = 0.3
    consensus_min_agreement_ratio: float = 0.66
    max_confirmed_facts: int = 8
    max_debated_claims: int = 12
    analyze_recent_clusters_limit: int = 200
    cluster_lookback_hours: int = 24
    recluster_recent_window: bool = True
    recluster_limit: int = 500
    refresh_existing_feeds: bool = True
    retention_days: int = 7
    # Near-duplicate guardrails to keep clustering clean.
    dedup_lookback_hours: int = 72
    dedup_hamming_threshold: int = 18
    dedup_bands: int = 4
    dedup_min_jaccard: float = 0.7
    # Cluster quality guardrails (semantic coherence).
    min_intra_cluster_similarity: float = 0.65
    min_member_similarity_to_centroid: float = 0.70
    max_cluster_articles: int = 30
    max_cluster_articles_per_source: int = 2
    enable_editorial_llm: bool = False
    editorial_candidate_limit: int = 15
    editorial_max_stories: int = 9


@dataclass
class PipelineStats:
    scraped: int = 0
    inserted: int = 0
    duplicates: int = 0
    near_duplicates: int = 0
    insert_failures: int = 0
    embedded: int = 0
    embed_failures: int = 0
    clustered_articles: int = 0
    clusters_created: int = 0
    clusters_rejected_low_similarity: int = 0
    cluster_failures: int = 0
    clusters_removed_for_recluster: int = 0
    cluster_assignments_cleared: int = 0
    feeds_inserted: int = 0
    feeds_skipped_existing: int = 0
    feeds_replaced: int = 0
    feeds_rejected_editorial: int = 0
    analyze_failures: int = 0
    pruned_articles: int = 0
    pruned_clusters: int = 0
    pruned_feeds: int = 0
    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scraped": self.scraped,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "near_duplicates": self.near_duplicates,
            "insert_failures": self.insert_failures,
            "embedded": self.embedded,
            "embed_failures": self.embed_failures,
            "clustered_articles": self.clustered_articles,
            "clusters_created": self.clusters_created,
            "clusters_rejected_low_similarity": self.clusters_rejected_low_similarity,
            "cluster_failures": self.cluster_failures,
            "clusters_removed_for_recluster": self.clusters_removed_for_recluster,
            "cluster_assignments_cleared": self.cluster_assignments_cleared,
            "feeds_inserted": self.feeds_inserted,
            "feeds_skipped_existing": self.feeds_skipped_existing,
            "feeds_replaced": self.feeds_replaced,
            "feeds_rejected_editorial": self.feeds_rejected_editorial,
            "analyze_failures": self.analyze_failures,
            "pruned_articles": self.pruned_articles,
            "pruned_clusters": self.pruned_clusters,
            "pruned_feeds": self.pruned_feeds,
            "sources_attempted": self.sources_attempted,
            "sources_succeeded": self.sources_succeeded,
            "sources_failed": self.sources_failed,
        }


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
        editorial_service: Optional[GroqMorningBriefService] = None,
    ):
        self.config = config
        self.db = db
        self.scraper = scraper
        self.embedder = embedder
        self.clusterer = clusterer
        self.analyzer = analyzer
        self.editorial_service = editorial_service

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
            if (
                self.config.consensus_min_agreement_ratio <= 0
                or self.config.consensus_min_agreement_ratio > 1
            ):
                raise ValueError("consensus_min_agreement_ratio must be in (0, 1]")
            rules = RuleBasedClassifier.from_yaml(self.config.classification_yaml)
            extractor = EntityExtractor()
            detector = ConsensusDetector(
                min_agreement_ratio=self.config.consensus_min_agreement_ratio
            )
            self.analyzer = AnalysisService(
                entity_extractor=extractor,
                consensus_detector=detector,
                classifier=rules,
                max_confirmed_facts=self.config.max_confirmed_facts,
                max_debated_claims=self.config.max_debated_claims,
            )
        return self.analyzer

    def _get_editorial_service(self) -> Optional[GroqMorningBriefService]:
        if self.editorial_service is not None:
            return self.editorial_service
        if not self.config.enable_editorial_llm:
            return None

        api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        if not api_key:
            return None

        try:
            self.editorial_service = GroqMorningBriefService(api_key=api_key)
        except EditorialError as exc:
            logger.warning("Editorial service unavailable: %s", exc)
            return None
        return self.editorial_service

    # ---------------------------------------------------------------------
    # Phases
    # ---------------------------------------------------------------------

    def scrape_and_insert(self) -> tuple[PipelineStats, List[RawArticle]]:
        stats = PipelineStats()
        dedup_index = SimHashIndex(SimHashIndexConfig(bands=self.config.dedup_bands))
        shingles_by_id: Dict[str, set[int]] = {}
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=self.config.dedup_lookback_hours)
            recent = self.db.get_articles_since(since=since, limit=2000)
            for a in recent:
                doc_id = str(a.id)
                text = f"{a.headline}. {a.main_text[:1000]}"
                fp = simhash64(text)
                dedup_index.add(doc_id, fp)
                shingles_by_id[doc_id] = shingle_hashes(text)
        except Exception as e:
            logger.warning("Dedup index build skipped (fetch failed): %s", e)
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
            stats.sources_attempted += 1

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
                stats.sources_failed += 1
                continue
            else:
                stats.sources_succeeded += 1

            stats.scraped += len(scraped)

            for article in scraped:
                if not self._host_allowed(article.url, base_url):
                    logger.warning("Skipping off-domain url for %s: %s", source_name, article.url)
                    continue
                text = f"{article.headline}. {article.main_text[:1000]}"
                fp = simhash64(text)
                article_shingles = shingle_hashes(text)
                is_near_dup = False
                for _doc_id, other_fp in dedup_index.candidates(fp):
                    if hamming_distance64(fp, other_fp) > self.config.dedup_hamming_threshold:
                        continue
                    other_shingles = shingles_by_id.get(_doc_id)
                    if other_shingles is None:
                        continue
                    if jaccard(article_shingles, other_shingles) < self.config.dedup_min_jaccard:
                        continue
                    stats.near_duplicates += 1
                    is_near_dup = True
                    break
                if is_near_dup:
                    continue
                try:
                    self.db.insert_article(article)
                    inserted_articles.append(article)
                    stats.inserted += 1
                    doc_id = str(article.id)
                    dedup_index.add(doc_id, fp)
                    shingles_by_id[doc_id] = article_shingles
                except DuplicateArticleError:
                    stats.duplicates += 1
                except Exception as e:
                    stats.insert_failures += 1
                    logger.warning("Insert failed (%s): %s", article.url, e)

        return stats, inserted_articles

    def embed_articles(self, articles: Sequence[RawArticle], stats: PipelineStats) -> None:
        to_embed = [a for a in articles if a.embedding is None]
        if not to_embed:
            return

        embedder = self._get_embedder()
        texts = [f"{a.headline}. {a.main_text[:500]}" for a in to_embed]
        try:
            result = embedder.embed_batch(texts, batch_size=self.config.embedding_batch_size)
        except Exception as e:
            stats.embed_failures += len(to_embed)
            logger.exception("Embedding stage failed for %d articles: %s", len(to_embed), e)
            return

        for idx, article in enumerate(to_embed):
            emb = result.embeddings[idx].tolist()
            article.embedding = emb
            try:
                self.db.update_article_embedding(article.id, emb)
                stats.embedded += 1
            except Exception as e:
                stats.embed_failures += 1
                logger.warning("Failed updating embedding for %s: %s", article.id, e)

    def embed_backfill(self, stats: PipelineStats) -> None:
        """Resume embeddings for articles that were inserted in previous runs."""
        try:
            pending = self.db.get_articles_without_embeddings(
                limit=self.config.embedding_backfill_limit
            )
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
            cluster_articles_all = [candidates[i] for i in indices]
            if len(cluster_articles_all) < self.config.min_cluster_size:
                continue

            cluster_id = uuid4()
            cluster_embeddings_raw = embeddings[indices].astype(np.float32)
            norms = np.linalg.norm(cluster_embeddings_raw, axis=1, keepdims=True)
            norms = np.where(norms <= 0, 1.0, norms)
            cluster_embeddings = cluster_embeddings_raw / norms

            centroid_vec = calculate_centroid(cluster_embeddings)
            member_sims = cluster_embeddings @ centroid_vec
            keep_local = np.where(member_sims >= self.config.min_member_similarity_to_centroid)[0]
            if len(keep_local) < self.config.min_cluster_size:
                stats.clusters_rejected_low_similarity += 1
                continue

            # Prefer the most centroid-aligned members, while capping per-source
            # and overall cluster size to keep stories tight and credible.
            ranked_local = sorted(
                (int(i) for i in keep_local),
                key=lambda i: (-float(member_sims[i]), cluster_articles_all[i].source, cluster_articles_all[i].url),
            )
            per_source: Dict[str, int] = {}
            kept_local: List[int] = []
            for i in ranked_local:
                if len(kept_local) >= int(self.config.max_cluster_articles):
                    break
                src = cluster_articles_all[i].source
                if per_source.get(src, 0) >= int(self.config.max_cluster_articles_per_source):
                    continue
                per_source[src] = per_source.get(src, 0) + 1
                kept_local.append(i)

            if len(kept_local) < self.config.min_cluster_size:
                stats.clusters_rejected_low_similarity += 1
                continue

            kept_embeddings = cluster_embeddings[np.array(kept_local, dtype=np.int64)]
            similarity = calculate_intra_cluster_similarity(kept_embeddings)
            if similarity < float(self.config.min_intra_cluster_similarity):
                stats.clusters_rejected_low_similarity += 1
                continue

            centroid = calculate_centroid(kept_embeddings).tolist()
            kept_articles = [cluster_articles_all[i] for i in kept_local]

            try:
                self.db.create_cluster(
                    cluster_id=cluster_id,
                    article_ids=[a.id for a in kept_articles],
                    centroid_embedding=centroid,
                    algorithm_used=result.algorithm_used,
                )
                stats.clusters_created += 1
                created_cluster_ids.append(cluster_id)
            except Exception as e:
                stats.cluster_failures += 1
                logger.exception("Failed creating cluster %s: %s", cluster_id, e)
                continue

            for article in kept_articles:
                try:
                    self.db.assign_to_cluster(article.id, cluster_id)
                except Exception as e:
                    logger.warning("Failed assigning %s to %s: %s", article.id, cluster_id, e)

            # Persist similarity for observability without schema changes.
            # We store it on the feed metadata later; keep local for now.
            logger.info(
                "Cluster %s: %d articles (kept=%d), similarity=%.3f",
                cluster_id,
                len(indices),
                len(kept_articles),
                similarity,
            )

        return created_cluster_ids

    def remediate_recent_clusters(self, stats: PipelineStats) -> None:
        """Re-cluster recent embedded articles to recover from poor historical clusters."""
        if not self.config.recluster_recent_window:
            return

        since = datetime.now(timezone.utc) - timedelta(hours=self.config.cluster_lookback_hours)
        try:
            recent_embedded = self.db.get_articles_with_embeddings_since(
                since=since, limit=self.config.recluster_limit
            )
        except Exception as e:
            logger.warning("Recent cluster remediation skipped (fetch failed): %s", e)
            return

        affected_cluster_ids = {
            article.cluster_id for article in recent_embedded if article.cluster_id is not None
        }
        if not affected_cluster_ids:
            return

        try:
            stats.cluster_assignments_cleared += int(self.db.clear_cluster_assignments_since(since))
        except Exception as e:
            logger.warning("Failed clearing recent cluster assignments: %s", e)
            return

        for cluster_id in affected_cluster_ids:
            try:
                replaced = int(self.db.delete_analyzed_feed_by_cluster_id(cluster_id))
                stats.feeds_replaced += replaced
            except Exception as e:
                logger.warning("Failed deleting feeds for cluster %s: %s", cluster_id, e)
            try:
                self.db.delete_cluster(cluster_id)
                stats.clusters_removed_for_recluster += 1
            except Exception as e:
                logger.warning("Failed deleting cluster %s during remediation: %s", cluster_id, e)

    def analyze_clusters_missing_feed(self, stats: PipelineStats) -> List[UUID]:
        analyzer = self._get_analyzer()
        editorial = self._get_editorial_service()

        clusters = self.db.get_all_clusters(limit=self.config.analyze_recent_clusters_limit)
        inserted_feed_ids: List[UUID] = []
        candidates: List[ClusterEditorialCandidate] = []
        cutoff: Optional[datetime] = None
        days = int(self.config.retention_days)
        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        for cluster in clusters:
            # Avoid analyzing clusters that will be pruned in the same run (prevents
            # orphan analyzed_feed rows pointing at deleted clusters/articles).
            if cutoff is not None:
                created_at = cluster.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < cutoff:
                    continue

            if cluster.cluster_size < self.config.min_cluster_size:
                continue

            has_existing_feed = False
            try:
                has_existing_feed = self.db.analyzed_feed_exists(cluster.id)
            except Exception as e:
                logger.warning("Feed-exists check failed for %s: %s", cluster.id, e)
            if has_existing_feed:
                if not self.config.refresh_existing_feeds:
                    stats.feeds_skipped_existing += 1
                    continue
                try:
                    replaced = int(self.db.delete_analyzed_feed_by_cluster_id(cluster.id))
                    stats.feeds_replaced += replaced
                except Exception as e:
                    logger.warning("Failed deleting existing feed rows for %s: %s", cluster.id, e)

            try:
                articles = self.db.get_articles_by_ids(cluster.article_ids)
                feed = analyzer.analyze_cluster(cluster.id, articles)
                candidates.append(
                    ClusterEditorialCandidate(
                        cluster_id=cluster.id,
                        base_feed=feed,
                        representative_article=analyzer.choose_representative_article(articles),
                        articles=tuple(articles),
                        algorithm_used=cluster.algorithm_used,
                        avg_similarity=self._compute_cluster_avg_similarity(articles),
                        min_member_similarity=self._compute_cluster_min_similarity(articles),
                    )
                )
            except Exception as e:
                stats.analyze_failures += 1
                logger.exception("Failed analyzing cluster %s: %s", cluster.id, e)

        editorial_result: Dict[UUID, Any] | None = None
        if editorial and candidates:
            ranked_candidates = sorted(
                candidates,
                key=lambda candidate: (
                    -max(list(candidate.base_feed.source_attribution.values()) or [0]),
                    -len(candidate.articles),
                    candidate.cluster_id.hex,
                ),
            )
            limited_candidates = ranked_candidates[: max(1, int(self.config.editorial_candidate_limit))]
            try:
                editorial_result = editorial.review_clusters(
                    limited_candidates,
                    max_stories=self.config.editorial_max_stories,
                )
            except EditorialError as exc:
                logger.warning("Editorial review failed, falling back to deterministic feed: %s", exc)

        if editorial_result is not None:
            selected_candidates = []
            for candidate in candidates:
                story = editorial_result.get(candidate.cluster_id)
                if story is None:
                    stats.feeds_rejected_editorial += 1
                    continue
                selected_candidates.append((candidate, story))

            selected_candidates.sort(
                key=lambda row: (int(row[1].priority), len(row[0].articles), row[0].cluster_id.hex)
            )

            for candidate, story in selected_candidates:
                try:
                    merged_feed = merge_editorial_story(
                        candidate,
                        story,
                        model_name=editorial.model,
                    )
                    merged_feed.created_at = datetime.now(timezone.utc)
                    feed_id = self.db.insert_analyzed_feed(merged_feed)
                    inserted_feed_ids.append(feed_id)
                    stats.feeds_inserted += 1
                except Exception as e:
                    stats.analyze_failures += 1
                    logger.exception("Failed inserting editorial feed for cluster %s: %s", candidate.cluster_id, e)
            return inserted_feed_ids

        for candidate in candidates:
            try:
                candidate.base_feed.created_at = datetime.now(timezone.utc)
                feed_id = self.db.insert_analyzed_feed(candidate.base_feed)
                inserted_feed_ids.append(feed_id)
                stats.feeds_inserted += 1
            except Exception as e:
                stats.analyze_failures += 1
                logger.exception("Failed inserting deterministic feed for cluster %s: %s", candidate.cluster_id, e)

        return inserted_feed_ids

    @staticmethod
    def _normalized_embedding_matrix(articles: Sequence[RawArticle]) -> Optional[np.ndarray]:
        rows: List[np.ndarray] = []
        dims: Optional[int] = None
        for article in articles:
            if article.embedding is None:
                return None
            vec = np.asarray(article.embedding, dtype=np.float32)
            if vec.ndim != 1 or vec.size == 0:
                return None
            if dims is None:
                dims = int(vec.size)
            elif int(vec.size) != dims:
                return None
            norm = float(np.linalg.norm(vec))
            if norm <= 0:
                return None
            rows.append(vec / norm)
        if not rows:
            return None
        return np.vstack(rows)

    def _compute_cluster_avg_similarity(self, articles: Sequence[RawArticle]) -> Optional[float]:
        matrix = self._normalized_embedding_matrix(articles)
        if matrix is None:
            return None
        return float(calculate_intra_cluster_similarity(matrix))

    def _compute_cluster_min_similarity(self, articles: Sequence[RawArticle]) -> Optional[float]:
        matrix = self._normalized_embedding_matrix(articles)
        if matrix is None:
            return None
        centroid = calculate_centroid(matrix)
        similarities = (matrix @ centroid).astype(np.float32)
        if not len(similarities):
            return None
        return float(np.min(similarities))

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
        logger.info(
            "Pipeline run started "
            "(max_articles_per_source=%d, embedding_backfill_limit=%d, cluster_lookback_hours=%d)",
            self.config.max_articles_per_source,
            self.config.embedding_backfill_limit,
            self.config.cluster_lookback_hours,
        )
        stats, inserted_articles = self.scrape_and_insert()
        logger.info(
            "Scrape+insert complete: scraped=%d inserted=%d duplicates=%d near_duplicates=%d failures=%d",
            stats.scraped,
            stats.inserted,
            stats.duplicates,
            stats.near_duplicates,
            stats.insert_failures,
        )

        # Embedding only for newly inserted articles.
        self.embed_articles(inserted_articles, stats)
        # Resume embeddings that failed in prior runs.
        self.embed_backfill(stats)
        logger.info(
            "Embedding complete: embedded=%d embed_failures=%d",
            stats.embedded,
            stats.embed_failures,
        )

        # Re-cluster recent window to remediate historical low-quality clusters.
        self.remediate_recent_clusters(stats)
        # Clustering uses DB state so it can resume after partial failures.
        self.cluster_unclustered_articles(stats)
        logger.info(
            "Clustering complete: clustered_articles=%d clusters_created=%d cluster_failures=%d rejected_low_similarity=%d",
            stats.clustered_articles,
            stats.clusters_created,
            stats.cluster_failures,
            stats.clusters_rejected_low_similarity,
        )

        # Analysis also uses DB state and avoids duplicate feed items per cluster.
        self.analyze_clusters_missing_feed(stats)
        logger.info(
            "Analysis complete: feeds_inserted=%d feeds_replaced=%d feeds_rejected_editorial=%d analyze_failures=%d",
            stats.feeds_inserted,
            stats.feeds_replaced,
            stats.feeds_rejected_editorial,
            stats.analyze_failures,
        )
        self.prune_old_data(stats)

        try:
            if self.scraper is not None:
                self.scraper.close()
        except Exception:
            pass

        logger.info("Pipeline run summary: %s", stats.as_dict())
        return stats


def default_config(
    sources_yaml: Path | str = "backend/config/sources.yaml",
    classification_yaml: Path | str = "backend/config/classification_rules.yaml",
) -> PipelineConfig:
    def _env_int(name: str, default: int) -> int:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
            return value if value > 0 else default
        except ValueError:
            return default

    enable_playwright = os.getenv("SAAF_ENABLE_PLAYWRIGHT_FALLBACK", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    enable_editorial_llm = os.getenv("SAAF_ENABLE_EDITORIAL_LLM", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    low_cost_mode = os.getenv("SAAF_LOW_COST_MODE", "0").strip().lower() in {"1", "true", "yes"}
    max_articles_per_source = _env_int("SAAF_MAX_ARTICLES_PER_SOURCE", 30)
    embedding_backfill_limit = _env_int("SAAF_EMBEDDING_BACKFILL_LIMIT", 100)
    editorial_candidate_limit = _env_int("SAAF_EDITORIAL_CANDIDATE_LIMIT", 15)
    editorial_max_stories = _env_int("SAAF_EDITORIAL_MAX_STORIES", 9)
    if low_cost_mode:
        max_articles_per_source = min(max_articles_per_source, 20)
        embedding_backfill_limit = min(embedding_backfill_limit, 50)
        editorial_candidate_limit = min(editorial_candidate_limit, 12)
        editorial_max_stories = min(editorial_max_stories, 9)

    return PipelineConfig(
        sources_yaml=Path(sources_yaml),
        classification_yaml=Path(classification_yaml),
        enable_playwright_fallback=enable_playwright,
        enable_editorial_llm=enable_editorial_llm,
        max_articles_per_source=max_articles_per_source,
        embedding_backfill_limit=embedding_backfill_limit,
        editorial_candidate_limit=editorial_candidate_limit,
        editorial_max_stories=editorial_max_stories,
    )
