from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import numpy as np
import yaml

from src.agents.adjudication import AdjudicationError, GeminiAdjudicationService
from src.agents.analysis import (
    AnalysisService,
    ConsensusDetector,
    EntityExtractor,
    aggregate_triage,
    article_triage,
)
from src.agents.clustering import (
    ClusteringResult,
    EventGroupingResult,
    EventGroupingService,
    calculate_centroid,
    calculate_intra_cluster_similarity,
    trusted_article_timestamp,
)
from src.agents.dedup import (
    SimHashIndex,
    SimHashIndexConfig,
    hamming_distance64,
    jaccard,
    shingle_hashes,
    simhash64,
)
from src.agents.editorial import (
    ClusterEditorialCandidate,
    EditorialError,
    merge_editorial_story,
)
from src.agents.editorial_gemini import GeminiMorningBriefService
from src.agents.embeddings import EmbeddingError, GeminiEmbeddingProvider
from src.agents.story_analysis import (
    StoryAnalysisError,
    StoryAnalysisValidationError,
    build_story_analysis_input,
    validate_story_analysis,
)
from src.agents.story_analysis_gemini import GeminiStoryAnalysisService
from src.agents.triage import GeminiTriageService, TriageError, TriageItem
from src.config import load_editorial_model_config, load_story_analysis_model_config
from src.db.errors import DuplicateArticleError
from src.db.models import AnalyzedFeed, RawArticle
from src.scrapers.body import ArticleBodyFetcher
from src.scrapers.feeds import (
    DEFAULT_ARTICLE_MAX_AGE_HOURS,
    DEFAULT_FULL_TEXT_MIN_CHARS,
    DEFAULT_STALE_FEED_HOURS,
    FeedIngestor,
    IngestResult,
    SourceSpec,
)
from src.utils.text import GENERIC_ACRONYMS
from src.utils.urls import canonicalize_url_for_dedup, host_allowed_for_base
from src.utils.validators import validate_sources_config

logger = logging.getLogger(__name__)

_PAKISTAN_TZ = ZoneInfo("Asia/Karachi")

_SINGLE_SOURCE_ALLOWED_CATEGORIES = {
    "security",
    "economy",
    "politics",
    "city",
    "health",
    "education",
}
_HIGH_IMPACT_LABELS = {"🛡️ SAFETY", "⚡ UTILITIES", "💳 WALLET", "🚦 COMMUTE", "🏛️ GOVERNANCE"}
_IMPACT_LINE_FALLBACKS: Dict[str, str] = {
    "💳 WALLET": "This could quickly affect household costs, prices, or business planning in Pakistan today.",
    "🚦 COMMUTE": "This could disrupt travel, traffic, or daily routines for people in Pakistan today.",
    "🛡️ SAFETY": "This could affect public safety, movement, or official security measures in Pakistan today.",
    "🏢 WORK": "This could affect work routines, office activity, or business confidence in Pakistan today.",
    "⚡ UTILITIES": "This could affect fuel, power, or other essential services people rely on in Pakistan today.",
    "🏛️ GOVERNANCE": "This could affect public decisions, rules, or political stability that shape daily life in Pakistan today.",
}
_WHAT_TO_WATCH_FALLBACKS: Dict[str, str] = {
    "economy": "Watch for the next official economic update, market reaction, or policy move over the next 24 hours.",
    "politics": "Watch for the next official statement, court move, or government decision over the next 24 hours.",
    "city": "Watch for local authority advisories and any disruption updates over the next 24 hours.",
    "education": "Watch for education department notices or schedule changes over the next 24 hours.",
    "health": "Watch for the next health department or hospital update over the next 24 hours.",
    "security": "Watch for the next police, military, or interior ministry update over the next 24 hours.",
    "international": "Watch for the next diplomatic statement or cross-border development over the next 24 hours.",
    "technology": "Watch for the next official policy or service update over the next 24 hours.",
    "other": "Watch for the next verified official update over the next 24 hours.",
}
_TOPLINE_BUCKET_SCORES: Dict[str, int] = {
    "lead": 4,
    "topline": 3,
    "secondary": 2,
    "tail": 1,
}
_SOURCE_PROMINENCE_FALLBACKS: Dict[str, int] = {
    "dawn": 10,
    "geo": 10,
    "tribune": 10,
    "thenews": 10,
    "reuters_pk": 12,
    "business_recorder": 10,
}

# Source count at which a candidate stops being collapsible into another card's
# story family. Three independent publishers is the same bar the corroboration
# oracle in `derive_expectations.py` uses to call something a must-have, so a
# story that clears it cannot be a presentation-layer duplicate.
_STORY_FAMILY_CORROBORATION_FLOOR = 3


# Facts the editor is given about a candidate. Deliberately not a score: the
# fifteen-term, six-penalty `_candidate_publish_score` it replaces saturated at
# 100 for every published card once the pool grew to ~300 articles, so ranking
# between candidates had stopped meaning anything at all (I-4).
#
# Ordering is lexicographic over these fields rather than a weighted sum. A
# tuple cannot saturate, and every position in the brief is attributable to one
# named fact instead of an unattributable integer.
@dataclass(frozen=True)
class CandidateEvidence:
    source_count: int
    article_count: int
    prominence_score: int
    lead_sources: int
    prominent_source_count: int
    bucket_score: int
    hours_since_latest: float
    category: str
    impact_labels: tuple[str, ...]
    story_type: Optional[str]
    pk_relevance: Optional[str]
    triage_confidence: float

    # hard_news first: a development that happened outranks colour about it.
    # routine sits below hard news but above nothing: it is a real development
    # that an institution announced about itself, and the editor is told to
    # make it earn a slot rather than being denied one deterministically.
    _STORY_TYPE_RANK = {"hard_news": 3, "routine": 1, None: 1}
    # A Pakistani story outranks a foreign one whatever knock-on the foreign
    # one claims. Ranking local below foreign_with_pk_effect pushed a Karachi
    # court story out of the golden day's brief in favour of an Nvidia server
    # pricing report, which is the wrong answer for a Pakistan morning brief.
    _PK_RELEVANCE_RANK = {
        "national": 3,
        "local": 2,
        "foreign_with_pk_effect": 1,
        "foreign": 0,
    }

    def ranking_key(self) -> tuple:
        """Order candidates when no editor is available to do it."""
        return (
            -self._STORY_TYPE_RANK.get(self.story_type, 0),
            -self._PK_RELEVANCE_RANK.get(self.pk_relevance, 0),
            -self.source_count,
            -self.prominence_score,
            -self.lead_sources,
            self.hours_since_latest,
            -self.article_count,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_count": self.source_count,
            "article_count": self.article_count,
            "prominence_score": self.prominence_score,
            "lead_sources": self.lead_sources,
            "prominent_source_count": self.prominent_source_count,
            "bucket_score": self.bucket_score,
            "hours_since_latest": round(self.hours_since_latest, 1),
            "category": self.category,
            "impact_labels": list(self.impact_labels),
            "story_type": self.story_type,
            "pk_relevance": self.pk_relevance,
            "triage_confidence": round(self.triage_confidence, 2),
        }



@dataclass(frozen=True)
class PipelineConfig:
    sources_yaml: Path
    max_articles_per_source: int = 40
    stale_feed_hours: int = DEFAULT_STALE_FEED_HOURS
    article_max_age_hours: int = DEFAULT_ARTICLE_MAX_AGE_HOURS
    full_text_min_chars: int = DEFAULT_FULL_TEXT_MIN_CHARS
    # One request per text on the free tier, capped at 100/minute.
    embedding_batch_size: int = 50
    embedding_backfill_limit: int = 100
    # 1, not 2: a single-article story must reach the (strict) single-source
    # publish gate instead of being discarded before it is ever considered.
    min_cluster_size: int = 1
    min_clusters: int = 2
    max_noise_ratio: float = 0.3
    consensus_min_agreement_ratio: float = 0.66
    max_confirmed_facts: int = 8
    max_debated_claims: int = 12
    # Must comfortably exceed the clusters a day produces, or the analysis
    # stage silently drops the remainder. A 2026-08-25 run produced 570.
    analyze_recent_clusters_limit: int = 1200
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
    # Deterministic event-grouping gates.
    # 36h, deliberately equal to `article_max_age_hours` (config/sources.yaml).
    # A window *narrower* than the ingest window is a structural ceiling on the
    # biggest stories: two articles can sit in the same pool, embed at 0.97, pass
    # every overlap gate, and still be barred from one cluster purely by age gap.
    # Measured on 2026-08-27, where the PIMS hospital fire ran 30.5h from the
    # blaze to the funerals: at 18h it split into a 4-article/2-source cluster
    # headed by the fire and a separate 5-article/4-source cluster headed by the
    # burials, so the day's biggest story showed the editor 2-source
    # corroboration. At 36h it is one 8-article/5-source cluster under the right
    # headline. Swept over all three fixtures at 18/24/30/36: `merged-in` (the
    # worse error) never rose and fell 9->7 on 2026-08-27, split fell 38->33,
    # recall was unchanged. Do not narrow this without re-running that sweep.
    event_group_max_time_delta_hours: int = 36
    # 0.92, not 0.80. Measured on both golden days 2026-08-25: Pakistani
    # political wire copy embeds into a narrow band, where two reports of the
    # *same* event sit at 0.95-0.97 and two *different* events in the same
    # domain sit around 0.82. A floor of 0.80 is below both, so everything
    # political chained together through single linkage.
    #
    # The cost was not subtle. One live cluster held 14 articles from 7 sources
    # and four unrelated events - Imran Khan's hospital transfer, the Munir
    # visit to Iran, a PM meeting and a Turkiye FMs call - and was represented
    # by the single-article FM call, so the day's two biggest stories were
    # invisible to the editor while a minor one inherited their corroboration.
    #
    # Sweep over both fixtures, counting articles in the wrong group
    # (`scripts/eval_golden_day.py --cluster-report` reports the same metric):
    #
    #   pair   merged-in (worse)   split-apart   total
    #   0.80          125               40        165
    #   0.90           47               16         63
    #   0.92           15               25         40
    #   0.94            0               61         61
    #
    # 0.92 minimises the total and, more importantly, the merge error - a
    # merged story is one the editor never sees, where a split one appears as
    # two candidates it can choose between and the duplicate-event check
    # guards. Past 0.92 single events start shattering.
    event_group_min_pair_similarity: float = 0.92
    event_group_min_headline_overlap: float = 0.20
    event_group_min_entity_overlap: float = 0.15
    enable_triage_llm: bool = True
    triage_batch_size: int = 50
    enable_adjudication_llm: bool = True
    max_adjudication_pairs: int = 24
    enable_editorial_llm: bool = False
    editorial_candidate_limit: int = 30
    editorial_max_stories: int = 12
    enable_story_analysis_llm: bool = False


@dataclass
class PipelineStats:
    run_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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
    candidates_analyzed: int = 0
    candidates_publishable: int = 0
    editorial_selected: int = 0
    short_brief_reason: str = ""
    stage_seconds: Dict[str, float] = field(default_factory=dict)
    analyze_failures: int = 0
    pruned_articles: int = 0
    pruned_clusters: int = 0
    pruned_feeds: int = 0
    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    source_article_counts: Dict[str, int] = field(default_factory=dict)
    # Discovered, not inserted. A source whose articles are all already stored
    # inserts nothing on a re-run, which is not the same as a source that
    # returned nothing - conflating the two marked all eight sources degraded
    # on any second run of the hour.
    source_discovered_counts: Dict[str, int] = field(default_factory=dict)
    degraded_sources: List[str] = field(default_factory=list)
    endpoint_health: List[Dict[str, Any]] = field(default_factory=list)
    lazy_body_fetches: int = 0
    lazy_body_fetch_failures: int = 0
    triage_articles: int = 0
    triage_calls: int = 0
    triage_failures: int = 0
    triage_unresolved: int = 0
    embedding_unresolved: int = 0
    triage_persist_failures: int = 0
    triage_status: str = "disabled"
    embedding_status: str = "ok"
    adjudicated_pairs: int = 0
    adjudicated_merges: int = 0
    adjudication_calls: int = 0
    adjudication_failures: int = 0
    editorial_status: str = "disabled"
    story_analysis_status: str = "disabled"
    story_analysis_calls: int = 0
    story_analysis_successes: int = 0
    story_analysis_question_rejections: int = 0
    story_analysis_fallbacks: int = 0
    story_analysis_failures: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "run_started_at": self.run_started_at.isoformat(),
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
            "candidates_analyzed": self.candidates_analyzed,
            "candidates_publishable": self.candidates_publishable,
            "editorial_selected": self.editorial_selected,
            "short_brief_reason": self.short_brief_reason,
            "stage_seconds": dict(self.stage_seconds),
            "analyze_failures": self.analyze_failures,
            "pruned_articles": self.pruned_articles,
            "pruned_clusters": self.pruned_clusters,
            "pruned_feeds": self.pruned_feeds,
            "sources_attempted": self.sources_attempted,
            "sources_succeeded": self.sources_succeeded,
            "sources_failed": self.sources_failed,
            "source_article_counts": dict(self.source_article_counts),
            "source_discovered_counts": dict(self.source_discovered_counts),
            "degraded_sources": list(self.degraded_sources),
            "endpoint_health": [dict(row) for row in self.endpoint_health],
            "lazy_body_fetches": self.lazy_body_fetches,
            "lazy_body_fetch_failures": self.lazy_body_fetch_failures,
            "triage_articles": self.triage_articles,
            "triage_calls": self.triage_calls,
            "triage_failures": self.triage_failures,
            "triage_unresolved": self.triage_unresolved,
            "embedding_unresolved": self.embedding_unresolved,
            "triage_persist_failures": self.triage_persist_failures,
            "triage_status": self.triage_status,
            "embedding_status": self.embedding_status,
            "adjudicated_pairs": self.adjudicated_pairs,
            "adjudicated_merges": self.adjudicated_merges,
            "adjudication_calls": self.adjudication_calls,
            "adjudication_failures": self.adjudication_failures,
            "editorial_status": self.editorial_status,
            "story_analysis_status": self.story_analysis_status,
            "story_analysis_calls": self.story_analysis_calls,
            "story_analysis_successes": self.story_analysis_successes,
            "story_analysis_question_rejections": self.story_analysis_question_rejections,
            "story_analysis_fallbacks": self.story_analysis_fallbacks,
            "story_analysis_failures": self.story_analysis_failures,
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
        db,
        ingestor: Optional[FeedIngestor] = None,
        embedder: Optional[GeminiEmbeddingProvider] = None,
        clusterer: Optional[object] = None,
        analyzer: Optional[AnalysisService] = None,
        editorial_service: Optional[object] = None,
        body_fetcher: Optional[ArticleBodyFetcher] = None,
        triage_service: Optional[object] = None,
        adjudicator: Optional[object] = None,
        story_analysis_service: Optional[object] = None,
    ):
        self.config = config
        self.db = db
        self.ingestor = ingestor
        self._previous_edition_cache: Optional[tuple[frozenset[tuple[str, str]], Optional[datetime]]] = None
        self.body_fetcher = body_fetcher
        self.embedder = embedder
        self.clusterer = clusterer
        self.analyzer = analyzer
        self.editorial_service = editorial_service
        self.triage_service = triage_service
        self.adjudicator = adjudicator
        self.story_analysis_service = story_analysis_service
        # Identifies the brief this run publishes; see _stamp_brief_run.
        self.run_started_at = datetime.now(timezone.utc)

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
        return host_allowed_for_base(url, base_url)

    def _get_ingestor(self, sources_config: Dict[str, Any]) -> FeedIngestor:
        if self.ingestor is None:
            self.ingestor = FeedIngestor(
                SourceSpec.from_config(sources_config),
                stale_feed_hours=self.config.stale_feed_hours,
                article_max_age_hours=self.config.article_max_age_hours,
                full_text_min_chars=self.config.full_text_min_chars,
                max_articles_per_source=self.config.max_articles_per_source,
            )
        return self.ingestor

    def _get_body_fetcher(self) -> ArticleBodyFetcher:
        if self.body_fetcher is None:
            self.body_fetcher = ArticleBodyFetcher(
                min_chars=self.config.full_text_min_chars
            )
        return self.body_fetcher

    def _get_embedder(self) -> Optional[GeminiEmbeddingProvider]:
        """The embedder, or None when it cannot be built.

        Without an API key this raised straight out of the run: the pipeline
        crashed with a traceback rather than finishing and recording why, so
        /health had nothing to report and only looked wrong 28 hours later when
        the heartbeat went stale. No embeddings means no new cards, which is a
        real answer - it just has to be said out loud.
        """
        if self.embedder is None:
            try:
                self.embedder = GeminiEmbeddingProvider()
            except EmbeddingError as exc:
                logger.warning("Embedding provider unavailable: %s", exc)
                return None
        return self.embedder

    def _get_adjudicator(self) -> Optional[object]:
        if self.adjudicator is not None:
            return self.adjudicator
        if not self.config.enable_adjudication_llm:
            return None
        try:
            self.adjudicator = GeminiAdjudicationService()
        except AdjudicationError as exc:
            logger.warning("Adjudication service unavailable: %s", exc)
            return None
        return self.adjudicator

    def _get_grouping_service(self) -> object:
        if self.clusterer is None:
            self.clusterer = EventGroupingService(
                adjudicator=self._get_adjudicator(),
                max_adjudication_pairs=self.config.max_adjudication_pairs,
                min_cluster_size=self.config.min_cluster_size,
                max_time_delta_hours=self.config.event_group_max_time_delta_hours,
                min_pair_similarity=self.config.event_group_min_pair_similarity,
                min_group_centroid_similarity=self.config.min_member_similarity_to_centroid,
                min_group_avg_similarity=self.config.min_intra_cluster_similarity,
                min_headline_overlap=self.config.event_group_min_headline_overlap,
                min_entity_overlap=self.config.event_group_min_entity_overlap,
            )
        return self.clusterer

    def _get_analyzer(self) -> AnalysisService:
        if self.analyzer is None:
            if (
                self.config.consensus_min_agreement_ratio <= 0
                or self.config.consensus_min_agreement_ratio > 1
            ):
                raise ValueError("consensus_min_agreement_ratio must be in (0, 1]")
            extractor = EntityExtractor()
            detector = ConsensusDetector(
                min_agreement_ratio=self.config.consensus_min_agreement_ratio
            )
            self.analyzer = AnalysisService(
                entity_extractor=extractor,
                consensus_detector=detector,
                max_confirmed_facts=self.config.max_confirmed_facts,
                max_debated_claims=self.config.max_debated_claims,
            )
        return self.analyzer

    def _get_triage_service(self) -> Optional[object]:
        if self.triage_service is not None:
            return self.triage_service
        if not self.config.enable_triage_llm:
            return None
        try:
            self.triage_service = GeminiTriageService(batch_size=self.config.triage_batch_size)
        except TriageError as exc:
            logger.warning("Triage service unavailable: %s", exc)
            return None
        return self.triage_service

    def _get_editorial_service(self) -> Optional[object]:
        if self.editorial_service is not None:
            return self.editorial_service
        if not self.config.enable_editorial_llm:
            return None

        models = load_editorial_model_config()
        try:
            self.editorial_service = GeminiMorningBriefService(
                api_key=models.gemini_api_key or None,
                model=models.gemini_model,
            )
        except EditorialError as exc:
            # No provider means no brief. The run records editorial_status and
            # /health says so, rather than the gap being filled with templates.
            logger.warning("No editorial provider is available: %s", exc)
            return None
        return self.editorial_service

    def _get_story_analysis_service(self) -> Optional[object]:
        if self.story_analysis_service is not None:
            return self.story_analysis_service
        if not self.config.enable_story_analysis_llm:
            return None

        models = load_story_analysis_model_config()
        try:
            self.story_analysis_service = GeminiStoryAnalysisService(
                api_key=models.gemini_api_key or None,
                model=models.gemini_model,
            )
        except StoryAnalysisError as exc:
            logger.warning("No story-analysis provider is available: %s", exc)
            return None
        return self.story_analysis_service

    # ---------------------------------------------------------------------
    # Phases
    # ---------------------------------------------------------------------

    def scrape_and_insert(self) -> tuple[PipelineStats, List[RawArticle]]:
        stats = PipelineStats()
        dedup_index = SimHashIndex(SimHashIndexConfig(bands=self.config.dedup_bands))
        shingles_by_id: Dict[str, set[int]] = {}
        recent_urls: set[str] = set()
        dedup_started_at = time.perf_counter()
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=self.config.dedup_lookback_hours)
            recent = self.db.get_articles_since(since=since, limit=2000)
            for a in recent:
                doc_id = str(a.id)
                text = f"{a.headline}. {a.main_text[:1000]}"
                fp = simhash64(text)
                dedup_index.add(doc_id, fp)
                shingles_by_id[doc_id] = shingle_hashes(text)
                recent_urls.add(canonicalize_url_for_dedup(str(a.url)))
            logger.info(
                "Dedup preload complete: recent_articles=%d lookback_hours=%d duration=%.2fs",
                len(recent),
                self.config.dedup_lookback_hours,
                time.perf_counter() - dedup_started_at,
            )
        except Exception as e:
            logger.warning("Dedup index build skipped (fetch failed): %s", e)
        sources_cfg = self.load_sources_config(self.config.sources_yaml)
        specs = SourceSpec.from_config(sources_cfg)
        configured_default_max = int(
            (sources_cfg.get("scraping_config") or {}).get("max_articles_per_source", 0) or 0
        )
        max_per_source = int(self.config.max_articles_per_source or configured_default_max or 40)
        logger.info(
            "Ingest stage starting: enabled_sources=%d endpoints=%d max_articles_per_source=%d",
            len(specs),
            sum(len(spec.feed_urls) + len(spec.sitemap_urls) for spec in specs),
            max_per_source,
        )

        stats.sources_attempted = len(specs)
        ingestor = self._get_ingestor(sources_cfg)
        inserted_articles: List[RawArticle] = []

        try:
            result: IngestResult = ingestor.run()
        except Exception as e:
            logger.exception("Ingest failed: %s", e)
            stats.sources_failed = len(specs)
            stats.degraded_sources = [f"{spec.name}:ingest:failed" for spec in specs]
            return stats, inserted_articles

        stats.endpoint_health = [report.as_dict() for report in result.reports]
        for label in result.degraded_labels:
            if label not in stats.degraded_sources:
                stats.degraded_sources.append(label)
        stats.scraped = len(result.articles)

        healthy_sources = {report.source for report in result.reports if report.is_healthy}
        stats.sources_succeeded = sum(1 for spec in specs if spec.name in healthy_sources)
        stats.sources_failed = len(specs) - stats.sources_succeeded

        grouped = result.articles_by_source()
        for spec in specs:
            source_started_at = time.perf_counter()
            source_articles = grouped.get(spec.name, [])
            source_inserted = 0
            source_duplicates = 0
            source_near_duplicates = 0
            # Usable = on-domain and dated, whether or not it was new. This is
            # what "is this source working?" actually asks.
            source_usable = 0

            for article in source_articles:
                if spec.url and not self._host_allowed(article.url, spec.url):
                    logger.warning("Skipping off-domain url for %s: %s", spec.name, article.url)
                    continue
                if article.publish_date is None:
                    logger.warning(
                        "Skipping article with missing publish_date for %s: %s",
                        spec.name,
                        article.url,
                    )
                    continue
                source_usable += 1
                if canonicalize_url_for_dedup(str(article.url)) in recent_urls:
                    stats.duplicates += 1
                    source_duplicates += 1
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
                    source_near_duplicates += 1
                    is_near_dup = True
                    break
                if is_near_dup:
                    continue
                try:
                    self.db.insert_article(article)
                    inserted_articles.append(article)
                    stats.inserted += 1
                    source_inserted += 1
                    doc_id = str(article.id)
                    dedup_index.add(doc_id, fp)
                    shingles_by_id[doc_id] = article_shingles
                    recent_urls.add(canonicalize_url_for_dedup(str(article.url)))
                except DuplicateArticleError:
                    stats.duplicates += 1
                    source_duplicates += 1
                except Exception as e:
                    stats.insert_failures += 1
                    logger.warning("Insert failed (%s): %s", article.url, e)

            logger.info(
                "Source %s complete: discovered=%d inserted=%d duplicates=%d near_duplicates=%d duration=%.2fs",
                spec.name,
                len(source_articles),
                source_inserted,
                source_duplicates,
                source_near_duplicates,
                time.perf_counter() - source_started_at,
            )
            stats.source_article_counts[spec.name] = source_inserted
            stats.source_discovered_counts[spec.name] = source_usable
            # Degrade on whether the source yielded anything *usable*, not on
            # whether anything was *new*. This used to test `source_inserted`,
            # so a second run in the same hour - when every article is already
            # stored - marked all eight sources degraded and reported
            # near-zero article counts. A source whose every item is a known
            # duplicate is healthy; one whose every item is undated is not.
            if not source_usable and spec.name not in stats.degraded_sources:
                stats.degraded_sources.append(spec.name)

        return stats, inserted_articles

    def triage_articles(self, articles: Sequence[RawArticle], stats: PipelineStats) -> None:
        """
        Decide what each article is about, in batches of ~50.

        Runs on articles rather than clusters: 300 articles at 50 per call is
        6-8 requests, where 187 clusters would be an order of magnitude more.
        The verdict is persisted on the article so a re-run does not re-pay.
        """
        pending = [a for a in articles if article_triage(a) is None]
        if not pending:
            if articles:
                stats.triage_status = "ok"
            return

        service = self._get_triage_service()
        if service is None:
            stats.triage_status = "unavailable"
            stats.triage_failures += len(pending)
            logger.warning(
                "Triage unavailable for %d articles; they cannot reach the brief",
                len(pending),
            )
            return

        items = [
            TriageItem(
                key=str(article.id),
                source=article.source,
                headline=article.headline or "",
                summary=(article.main_text or "")[:400],
                publisher_categories=list((article.metadata or {}).get("publisher_categories") or []),
                url=canonicalize_url_for_dedup(str(article.url)),
            )
            for article in pending
        ]

        result = service.triage(items)
        stats.triage_calls += int(result.calls)
        stats.triage_failures += int(result.failures)

        by_id = {str(article.id): article for article in pending}
        updates: List[tuple[UUID, Dict[str, Any]]] = []
        for key, verdict in result.verdicts.items():
            article = by_id.get(key)
            if article is None:
                continue
            metadata = dict(article.metadata or {})
            metadata["triage"] = verdict.as_dict()
            article.metadata = metadata
            stats.triage_articles += 1
            updates.append((article.id, metadata))

        for offset in range(0, len(updates), 50):
            batch = updates[offset : offset + 50]
            bulk = getattr(self.db, "update_article_metadata_batch", None)
            if callable(bulk):
                try:
                    bulk(batch)
                    continue
                except Exception as exc:
                    logger.warning("Triage batch write failed; retrying rows: %s", exc)
            for article_id, metadata in batch:
                try:
                    self.db.update_article_metadata(article_id, metadata)
                except Exception as exc:
                    stats.triage_persist_failures += 1
                    logger.warning("Failed persisting triage verdict for %s: %s", article_id, exc)

        if stats.triage_articles <= 0:
            stats.triage_status = "unavailable"
        elif len(result.verdicts) < len(pending):
            stats.triage_status = "degraded"
        else:
            stats.triage_status = "ok"

    def triage_backfill(self, stats: PipelineStats) -> None:
        """Triage articles from earlier runs that never got a verdict."""
        since = datetime.now(timezone.utc) - timedelta(hours=self.config.cluster_lookback_hours)
        try:
            recent = self.db.get_articles_with_embeddings_since(since=since, limit=None)
        except Exception as e:
            logger.warning("Triage backfill fetch failed: %s", e)
            self.reconcile_processing_health(stats)
            return
        pending = [a for a in recent if article_triage(a) is None]
        if pending:
            self.triage_articles(pending, stats)
        self.reconcile_processing_health(stats)

    def reconcile_processing_health(self, stats: PipelineStats) -> None:
        """Judge the final persisted window, not failures from recovered attempts."""
        since = datetime.now(timezone.utc) - timedelta(hours=self.config.cluster_lookback_hours)
        try:
            articles = self.db.get_articles_since(since=since, limit=2000)
        except Exception as exc:
            stats.embedding_status = "unavailable"
            stats.triage_status = "unavailable"
            logger.warning("Cannot verify persisted processing state: %s", exc)
            return
        if len(articles) >= 2000:
            # A capped query cannot prove that earlier rows were processed.
            stats.embedding_status = "degraded"
            stats.triage_status = "degraded"
            logger.warning("Processing health window reached its 2000 article verification cap")
            return
        stats.embedding_unresolved = sum(article.embedding is None for article in articles)
        embedded = [article for article in articles if article.embedding is not None]
        stats.triage_unresolved = sum(article_triage(article) is None for article in embedded)
        stats.triage_articles = sum(article_triage(article) is not None for article in embedded)
        stats.embedding_status = "ok" if stats.embedding_unresolved == 0 else "degraded"
        if not embedded and articles:
            stats.triage_status = "unavailable"
        else:
            stats.triage_status = "ok" if stats.triage_unresolved == 0 else "degraded"

    def embed_articles(self, articles: Sequence[RawArticle], stats: PipelineStats) -> None:
        to_embed = [a for a in articles if a.embedding is None]
        if not to_embed:
            return

        embedder = self._get_embedder()
        if embedder is None:
            # embed_backfill re-fetches the same unembedded rows, so counting
            # on every call would report twice the articles that exist.
            if stats.embedding_status != "unavailable":
                stats.embed_failures += len(to_embed)
            stats.embedding_status = "unavailable"
            logger.warning(
                "Skipping %d articles: no embedding provider, so nothing new can cluster",
                len(to_embed),
            )
            return
        batch_size = max(1, int(self.config.embedding_batch_size))

        # Chunked and persisted as we go: the embedding API bills per text and
        # rate-limits per minute, so a 300-article day will occasionally trip a
        # 429 partway through. Earlier chunks must survive that.
        for start in range(0, len(to_embed), batch_size):
            chunk = to_embed[start : start + batch_size]
            texts = [f"{a.headline}. {a.main_text[:500]}" for a in chunk]
            try:
                result = embedder.embed_batch(texts, batch_size=batch_size)
                if len(result.embeddings) != len(chunk):
                    raise ValueError("Embedding provider returned an incomplete chunk")
            except Exception as e:
                stats.embed_failures += len(chunk)
                logger.warning(
                    "Embedding failed for %d/%d articles (offset %d): %s",
                    len(chunk),
                    len(to_embed),
                    start,
                    e,
                )
                continue

            updates = []
            for idx, article in enumerate(chunk):
                emb = result.embeddings[idx].tolist()
                article.embedding = emb
                updates.append((article.id, emb))
            bulk = getattr(self.db, "update_article_embeddings_batch", None)
            if callable(bulk):
                try:
                    bulk(updates)
                    stats.embedded += len(updates)
                    continue
                except Exception as exc:
                    logger.warning("Embedding batch write failed; retrying rows: %s", exc)
            for article_id, emb in updates:
                try:
                    self.db.update_article_embedding(article_id, emb)
                    stats.embedded += 1
                except Exception as exc:
                    stats.embed_failures += 1
                    logger.warning("Failed updating embedding for %s: %s", article_id, exc)

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

    @staticmethod
    def _labels_to_groups(result: ClusteringResult) -> List[List[int]]:
        groups: List[List[int]] = []
        for label in sorted({int(x) for x in result.labels}):
            if label == -1:
                continue
            indices = np.where(result.labels == label)[0]
            groups.append([int(index) for index in indices])
        return groups

    def _group_candidates(
        self,
        grouping_service: object,
        candidates: Sequence[RawArticle],
    ) -> tuple[str, List[List[int]]]:
        if hasattr(grouping_service, "group_articles"):
            result = grouping_service.group_articles(candidates)
            if not isinstance(result, EventGroupingResult):
                raise TypeError("group_articles() must return EventGroupingResult")
            return result.algorithm_used, [list(group.indices) for group in result.groups]

        if hasattr(grouping_service, "cluster"):
            embeddings = np.array([article.embedding for article in candidates], dtype=np.float32)
            result = grouping_service.cluster(embeddings)
            if not isinstance(result, ClusteringResult):
                raise TypeError("cluster() must return ClusteringResult")
            return result.algorithm_used, self._labels_to_groups(result)

        raise TypeError("Grouping service must define group_articles() or cluster()")

    def cluster_unclustered_articles(
        self, stats: PipelineStats, limit: Optional[int] = None
    ) -> List[UUID]:
        """
        Cluster DB articles with embeddings but no cluster_id.

        Returns:
            List of created cluster UUIDs (noise excluded).
        """
        since = datetime.now(timezone.utc) - timedelta(hours=self.config.cluster_lookback_hours)
        atomic_replace = self.config.recluster_recent_window and callable(
            getattr(self.db, "replace_recent_clusters", None)
        )
        candidates = (
            self.db.get_articles_with_embeddings_since(since=since, limit=limit)
            if atomic_replace else self.db.get_articles_without_clusters_since(since=since, limit=limit)
        )
        candidates = [a for a in candidates if a.embedding is not None]
        if len(candidates) < max(1, self.config.min_cluster_size):
            return []

        embeddings_raw = np.array([a.embedding for a in candidates], dtype=np.float32)
        norms = np.linalg.norm(embeddings_raw, axis=1, keepdims=True)
        norms = np.where(norms <= 0, 1.0, norms)
        embeddings = embeddings_raw / norms
        grouping_service = self._get_grouping_service()
        algorithm_used, grouped_indices = self._group_candidates(grouping_service, candidates)
        self._record_adjudication_stats(grouping_service, stats)

        created_cluster_ids: List[UUID] = []
        planned_clusters: List[Dict[str, Any]] = []
        stats.clustered_articles += len(candidates)

        for indices in grouped_indices:
            cluster_articles_all = [candidates[i] for i in indices]
            if len(cluster_articles_all) < self.config.min_cluster_size:
                continue

            cluster_id = uuid4()
            cluster_embeddings = embeddings[np.array(indices, dtype=np.int64)].astype(np.float32)

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

            if atomic_replace:
                planned_clusters.append({
                    "id": str(cluster_id),
                    "article_ids": [str(article.id) for article in kept_articles],
                    "centroid_embedding": centroid,
                    "algorithm_used": algorithm_used,
                })
                created_cluster_ids.append(cluster_id)
                continue

            try:
                self.db.create_cluster(
                    cluster_id=cluster_id,
                    article_ids=[a.id for a in kept_articles],
                    centroid_embedding=centroid,
                    algorithm_used=algorithm_used,
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
                    stats.cluster_failures += 1
                    logger.warning("Failed assigning %s to %s: %s", article.id, cluster_id, e)

            # Persist similarity for observability without schema changes.
            # We store it on the feed metadata later; keep local for now.
            logger.info(
                "Cluster %s: %d grouped articles (kept=%d), similarity=%.3f algorithm=%s",
                cluster_id,
                len(indices),
                len(kept_articles),
                similarity,
                algorithm_used,
            )

        if atomic_replace:
            # One database transaction replaces the complete lookback graph.
            # A failed RPC leaves the former assignments intact for recovery.
            result = self.db.replace_recent_clusters(since, planned_clusters)
            stats.clusters_removed_for_recluster += int(result.get("removed", 0))
            stats.cluster_assignments_cleared += int(result.get("cleared", 0))
            stats.clusters_created += len(planned_clusters)
        return created_cluster_ids

    @staticmethod
    def _record_adjudication_stats(grouping_service: object, stats: PipelineStats) -> None:
        result = getattr(grouping_service, "last_adjudication", None)
        if result is None:
            return
        stats.adjudicated_pairs += len(getattr(result, "verdicts", {}) or {})
        stats.adjudicated_merges += int(getattr(result, "merged", 0) or 0)
        stats.adjudication_calls += int(getattr(result, "calls", 0) or 0)
        stats.adjudication_failures += int(getattr(result, "failures", 0) or 0)

    def remediate_recent_clusters(self, stats: PipelineStats) -> None:
        """Re-cluster recent embedded articles to recover from poor historical clusters.

        It deletes clusters, never published cards. It used to delete the
        matching `analyzed_feed` rows too, which was survivable while a failed
        editorial pass still wrote template cards - but once an outage
        publishes nothing (see `analyze_clusters_missing_feed`), the two
        together destroy the standing brief and replace it with nothing. A
        drill on 2026-08-25 did exactly that: remediation removed the day's
        eight cards, the editorial stage then published none, and `/api/feed`
        fell back to seven rows from two days earlier.

        Leaving the rows in place costs nothing. `metadata.brief_run_at` is
        what decides which rows are the brief, so a superseded row is already
        invisible to `/api/feed`, and `prune_old_data` clears it out on the
        retention window.
        """
        if not self.config.recluster_recent_window:
            return
        if callable(getattr(self.db, "replace_recent_clusters", None)):
            return  # The next grouping pass performs replacement atomically.

        since = datetime.now(timezone.utc) - timedelta(hours=self.config.cluster_lookback_hours)
        try:
            # Remediation clears the whole bounded lookback window, so it must
            # also load that whole window. A 500-row cap previously cleared
            # assignments for rows it never regrouped and stranded hundreds.
            recent_embedded = self.db.get_articles_with_embeddings_since(since=since, limit=None)
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
                self.db.delete_cluster(cluster_id)
                stats.clusters_removed_for_recluster += 1
            except Exception as e:
                logger.warning("Failed deleting cluster %s during remediation: %s", cluster_id, e)

    def analyze_clusters_missing_feed(
        self,
        stats: PipelineStats,
        cluster_ids: Optional[Sequence[UUID]] = None,
    ) -> List[UUID]:
        analyzer = self._get_analyzer()
        editorial = self._get_editorial_service()

        limit = int(self.config.analyze_recent_clusters_limit)
        # Biggest first, not newest first. The limit truncates, and ordered by
        # creation time it discarded whichever clusters happened to be written
        # last - which has nothing to do with whether anyone should read them.
        if cluster_ids is None:
            clusters = self.db.get_all_clusters(limit=limit, order="size")
        else:
            # A normal run knows exactly which clusters it just rebuilt. Load
            # the complete retained set and keep only those IDs so older large
            # clusters cannot consume the analysis cap ahead of today's small
            # but important events.
            wanted = set(cluster_ids)
            clusters = [
                cluster
                for cluster in self.db.get_all_clusters(limit=None, order="size")
                if cluster.id in wanted
            ]
        if cluster_ids is None and len(clusters) >= limit:
            # Not fatal - size ordering means what falls off the end is the
            # least-corroborated - but it must not be silent. Raising the
            # similarity threshold to 0.92 took one day from 268 clusters to
            # 570, and a limit of 200 then hid the day's two biggest stories.
            logger.warning(
                "Cluster analysis hit its limit of %d; smaller clusters were not "
                "considered. Raise PipelineConfig.analyze_recent_clusters_limit "
                "if this persists.",
                limit,
            )
        # One bounded read replaces one Supabase round-trip per cluster. If a
        # batch fails, fall back to the per-cluster path so one bad read cannot
        # discard the whole editorial candidate set.
        articles_by_id: Dict[UUID, RawArticle] = {}
        article_ids = list(dict.fromkeys(aid for cluster in clusters for aid in cluster.article_ids))
        try:
            for offset in range(0, len(article_ids), 200):
                for article in self.db.get_articles_by_ids(article_ids[offset : offset + 200]):
                    articles_by_id[article.id] = article
        except Exception as exc:
            articles_by_id = {}
            logger.warning("Bulk cluster article read failed; using isolated reads: %s", exc)
        inserted_feed_ids: List[UUID] = []
        candidates: List[ClusterEditorialCandidate] = []
        rejected_by_publish_gate = 0
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
                has_existing_feed = (
                    self.db.analyzed_feed_exists(cluster.id) if cluster_ids is None else False
                )
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
                articles = [articles_by_id[aid] for aid in cluster.article_ids] if all(
                    aid in articles_by_id for aid in cluster.article_ids
                ) else self.db.get_articles_by_ids(cluster.article_ids)
                feed = analyzer.analyze_cluster(cluster.id, articles)
                editorial_articles = self._select_editorial_articles(articles)
                candidates.append(
                    ClusterEditorialCandidate(
                        cluster_id=cluster.id,
                        base_feed=feed,
                        representative_article=analyzer.choose_representative_article(editorial_articles),
                        articles=tuple(editorial_articles),
                        algorithm_used=cluster.algorithm_used,
                        avg_similarity=self._compute_cluster_avg_similarity(editorial_articles),
                        min_member_similarity=self._compute_cluster_min_similarity(editorial_articles),
                    )
                )
            except Exception as e:
                stats.analyze_failures += 1
                logger.exception("Failed analyzing cluster %s: %s", cluster.id, e)

        publishable_candidates: List[ClusterEditorialCandidate] = []
        stats.candidates_analyzed = len(candidates)
        for candidate in candidates:
            evidence = self._candidate_evidence(candidate)
            prominence = self._candidate_publisher_topline(candidate)
            metadata = dict(candidate.base_feed.metadata or {})
            metadata["evidence"] = evidence.as_dict()
            metadata["publisher_topline_score"] = prominence["score"]
            metadata["publisher_topline_sources"] = prominence["sources"]
            metadata["publisher_topline_lead_sources"] = prominence["lead_sources"]
            metadata["publisher_topline_source_count"] = prominence["source_count"]
            metadata["publisher_topline_bucket_score"] = prominence["bucket_score"]
            metadata["selection_mode"] = "national_topline"
            candidate.base_feed.metadata = metadata

            allowed, reason = self._passes_hard_gates(candidate)
            if not allowed:
                rejected_by_publish_gate += 1
                # One named reason, not an unattributable integer.
                logger.info(
                    "Rejecting candidate %s before editorial: %s (sources=%d headline=%s)",
                    candidate.cluster_id,
                    reason,
                    evidence.source_count,
                    candidate.base_feed.headline,
                )
                continue
            publishable_candidates.append(candidate)
        stats.candidates_publishable = len(publishable_candidates)

        if rejected_by_publish_gate:
            logger.info(
                "Publish gate filtered %d/%d analyzed candidates before editorial review",
                rejected_by_publish_gate,
                len(candidates),
            )

        ranked_publishable_candidates = self._rank_publishable_candidates(publishable_candidates)
        story_limit = self._effective_story_limit(
            ranked_publishable_candidates,
            configured_limit=self.config.editorial_max_stories,
        )
        fallback_candidates = self._select_diverse_candidates(
            ranked_publishable_candidates,
            max_items=story_limit,
        )

        editorial_result: Dict[UUID, Any] | None = None
        if editorial and publishable_candidates:
            limited_candidates = ranked_publishable_candidates[
                : max(1, int(self.config.editorial_candidate_limit))
            ]
            self._hydrate_representative_bodies(limited_candidates, stats)
            try:
                editorial_result = editorial.review_clusters(
                    limited_candidates,
                    max_stories=self.config.editorial_max_stories,
                )
                stats.editorial_status = "ok" if editorial_result else "degraded"
                stats.editorial_selected = len(editorial_result or {})
            except EditorialError as exc:
                # No silent mixing of template copy into the brief: the run
                # records that the editor was unreachable and /health says so.
                stats.editorial_status = "unavailable"
                logger.warning("Editorial review failed: %s", exc)
        elif not editorial:
            # "Switched off on purpose" and "was meant to run and could not"
            # are different states and must not share one code path. The
            # golden-day harness runs with the editor disabled deliberately, to
            # score selection and ordering without spending LLM calls; a
            # production run with no reachable provider is an outage.
            stats.editorial_status = (
                "unavailable" if self.config.enable_editorial_llm else "disabled"
            )

        if editorial_result:
            selected_story_by_cluster = {
                candidate.cluster_id: editorial_result[candidate.cluster_id]
                for candidate in publishable_candidates
                if candidate.cluster_id in editorial_result
            }
            preferred_candidates = sorted(
                (
                    candidate
                    for candidate in publishable_candidates
                    if candidate.cluster_id in selected_story_by_cluster
                ),
                key=lambda row: (
                    -int(selected_story_by_cluster[row.cluster_id].priority),
                    *self._candidate_evidence(row).ranking_key(),
                    row.cluster_id.hex,
                ),
            )
            # Ship what the editor produced. The retries inside review_clusters
            # are the answer to a short pass; padding the count with static
            # dictionary copy is what this replaces (I-5) — twelve cards with
            # two templates read worse than ten the editor stood behind.
            final_candidates = self._select_diverse_candidates(
                preferred_candidates,
                max_items=min(story_limit, len(preferred_candidates)),
            )
            stats.feeds_rejected_editorial += max(
                0, len(publishable_candidates) - len(final_candidates)
            )
            if len(final_candidates) < int(self.config.editorial_max_stories):
                logger.info(
                    "Editorial produced %d cards against a cap of %d; shipping as-is",
                    len(final_candidates),
                    self.config.editorial_max_stories,
                )

            story_analysis = self._get_story_analysis_service()
            current_articles: List[RawArticle] = []
            if story_analysis is not None:
                stats.story_analysis_status = "ok"
                try:
                    cutoff = self.run_started_at - timedelta(
                        hours=self.config.article_max_age_hours
                    )
                    # get_articles_since filters on scraped_at, so a second run
                    # in the same day pulls in the first run's scrapes whatever
                    # their publish dates. The contract names a 36h window on
                    # the story's own timestamp, so apply that too.
                    current_articles = [
                        article
                        for article in self.db.get_articles_since(since=cutoff, limit=2000)
                        if trusted_article_timestamp(article) >= cutoff
                    ]
                except Exception as exc:
                    # Primary event reports remain sufficient for a useful
                    # analysis. Losing optional context should flatten the
                    # output, not cost the card.
                    logger.warning(
                        "Related story-analysis context unavailable; using primary reports: %s",
                        exc,
                    )
            elif self.config.enable_story_analysis_llm:
                stats.story_analysis_status = "unavailable"

            consecutive_provider_failures = 0
            circuit_open = False

            for candidate in final_candidates:
                story = selected_story_by_cluster[candidate.cluster_id]
                try:
                    merged_feed = merge_editorial_story(
                        candidate, story, model_name=editorial.model
                    )
                    if story_analysis is not None and not circuit_open:
                        story_input = build_story_analysis_input(
                            cluster_id=str(candidate.cluster_id),
                            selected_headline=merged_feed.headline,
                            primary_articles=candidate.articles,
                            current_articles=current_articles,
                        )
                        try:
                            generated = None
                            validated = None
                            for validation_attempt in range(2):
                                generated = story_analysis.analyze(story_input)
                                stats.story_analysis_calls += max(
                                    1,
                                    int(
                                        getattr(story_analysis, "last_call_count", 1)
                                        or 1
                                    ),
                                )
                                try:
                                    validated = validate_story_analysis(
                                        generated, story_input
                                    )
                                    break
                                except StoryAnalysisValidationError as exc:
                                    if validation_attempt:
                                        raise
                                    logger.warning(
                                        "Story analysis failed evidence validation for cluster %s; "
                                        "retrying once with the same source packet: %s",
                                        candidate.cluster_id,
                                        exc,
                                    )
                            if validated is None:
                                raise StoryAnalysisValidationError(
                                    "analysis_missing_after_validation_retry"
                                )
                            metadata = dict(merged_feed.metadata or {})
                            metadata["story_analysis"] = validated.to_metadata(
                                model=str(getattr(story_analysis, "model", "injected"))
                            )
                            merged_feed.metadata = metadata
                            stats.story_analysis_successes += 1
                            if validated.status == "question_dropped":
                                stats.story_analysis_question_rejections += 1
                            consecutive_provider_failures = 0
                        except StoryAnalysisValidationError as exc:
                            stats.story_analysis_failures += 1
                            stats.story_analysis_fallbacks += 1
                            self._set_story_analysis_fallback(
                                merged_feed,
                                reason="validation_failed",
                                errors=str(exc).split(","),
                                model=str(getattr(story_analysis, "model", "injected")),
                                rejected=generated,
                            )
                            consecutive_provider_failures = 0
                            logger.warning(
                                "Story analysis rejected for cluster %s: %s",
                                candidate.cluster_id,
                                exc,
                            )
                        except StoryAnalysisError as exc:
                            stats.story_analysis_calls += max(
                                1,
                                int(
                                    getattr(exc, "calls", 0)
                                    or getattr(story_analysis, "last_call_count", 0)
                                    or 1
                                ),
                            )
                            stats.story_analysis_failures += 1
                            stats.story_analysis_fallbacks += 1
                            consecutive_provider_failures += 1
                            self._set_story_analysis_fallback(
                                merged_feed,
                                reason="provider_failed",
                                errors=[str(exc)],
                                model=str(getattr(story_analysis, "model", "injected")),
                            )
                            logger.warning(
                                "Story analysis failed for cluster %s: %s",
                                candidate.cluster_id,
                                exc,
                            )
                            if consecutive_provider_failures >= 3:
                                circuit_open = True
                                logger.warning(
                                    "Story-analysis circuit opened after %d consecutive failures",
                                    consecutive_provider_failures,
                                )
                    elif self.config.enable_story_analysis_llm:
                        stats.story_analysis_fallbacks += 1
                        reason = "circuit_open" if circuit_open else "provider_unavailable"
                        self._set_story_analysis_fallback(
                            merged_feed,
                            reason=reason,
                            errors=[reason],
                            model=str(getattr(story_analysis, "model", "unavailable")),
                        )
                    merged_feed.created_at = datetime.now(timezone.utc)
                    self._stamp_brief_run(merged_feed)
                    feed_id = self.db.insert_analyzed_feed(merged_feed)
                    inserted_feed_ids.append(feed_id)
                    stats.feeds_inserted += 1
                except Exception as e:
                    stats.analyze_failures += 1
                    logger.exception(
                        "Failed inserting editorial feed for cluster %s: %s", candidate.cluster_id, e
                    )

            if story_analysis is not None:
                if final_candidates and stats.story_analysis_successes == 0:
                    stats.story_analysis_status = "unavailable"
                elif (
                    stats.story_analysis_fallbacks
                    or stats.story_analysis_question_rejections
                ):
                    stats.story_analysis_status = "partial"
                else:
                    stats.story_analysis_status = "ok"
            if stats.feeds_inserted < 6:
                stats.short_brief_reason = (
                    "fewer_than_six_eligible_candidates" if stats.candidates_publishable < 6
                    else "editorial_selected_fewer_than_six" if stats.editorial_selected < 6
                    else "post_editorial_filter_or_write"
                )
            return inserted_feed_ids

        # Reached with no editor. What happens next depends on *why*.
        #
        # An outage publishes nothing. A drill on 2026-08-25 showed what the old
        # behaviour meant in practice: with no GEMINI_API_KEY the run replaced a
        # real brief with twelve cards reading "This could affect public life in
        # Pakistan today and is worth tracking closely", stamped with today's
        # brief_run_at and served under "Today's brief". Publishing nothing is
        # strictly better - the previous run's rows keep their stamp,
        # `/api/feed` goes on serving them, `is_fresh` turns false after twenty
        # hours, and the UI says "Latest brief". Yesterday's real journalism,
        # honestly labelled, beats today's filler dressed as news.
        #
        # The editor being switched off is a different thing. The golden-day
        # harness does exactly that, to score selection and ordering offline,
        # and it needs cards to score.
        if stats.editorial_status == "unavailable":
            if fallback_candidates:
                logger.warning(
                    "No editorial provider available; publishing nothing rather than "
                    "%d cards of template copy. The previous brief stands and will "
                    "be served as stale.",
                    len(fallback_candidates),
                )
            return inserted_feed_ids

        if fallback_candidates:
            logger.info(
                "Editorial LLM disabled; writing %d deterministic cards",
                len(fallback_candidates),
            )

        for candidate in fallback_candidates:
            try:
                fallback_feed = self._ensure_renderable_brief_copy(candidate)
                fallback_feed.created_at = datetime.now(timezone.utc)
                self._stamp_brief_run(fallback_feed)
                feed_id = self.db.insert_analyzed_feed(fallback_feed)
                inserted_feed_ids.append(feed_id)
                stats.feeds_inserted += 1
            except Exception as e:
                stats.analyze_failures += 1
                logger.exception("Failed inserting deterministic feed for cluster %s: %s", candidate.cluster_id, e)

        return inserted_feed_ids

    def _stamp_brief_run(self, feed: AnalyzedFeed) -> None:
        """Mark which run published this card.

        The brief is what the latest run published, but analyzed_feed rows
        accumulate: a cluster the editor drops keeps its row from the previous
        run. A live check found the API serving eleven cards for an eight-card
        brief, two of them the same Tehran story under two headlines from two
        runs - the one thing a finite brief must never do. The API serves only
        the newest stamp.
        """
        metadata = dict(feed.metadata or {})
        metadata["brief_run_at"] = self.run_started_at.isoformat()
        feed.metadata = metadata

    @staticmethod
    def _set_story_analysis_fallback(
        feed: AnalyzedFeed,
        *,
        reason: str,
        errors: Sequence[str],
        model: str,
        rejected: Optional[object] = None,
    ) -> None:
        """Record the fallback, and keep what was rejected.

        Only the error *name* used to survive, so a rejection could not be
        explained afterwards: diagnosing the one live fallback meant re-running
        Gemini to reconstruct the text it had produced. The rejected copy is
        stored under a key nothing renders - the detail route strips it before
        the DTO and the feed route strips story_analysis wholesale.
        """
        metadata = dict(feed.metadata or {})
        metadata["story_analysis"] = {
            "analysis": None,
            "question": None,
            "question_basis": "none",
            "claims": [],
            "question_supporting_article_ids": [],
            "related_article_ids": [],
            "model": model,
            "status": "fallback",
            "fallback_reason": reason,
            "validation_errors": [str(error) for error in errors if str(error).strip()],
        }
        if rejected is not None:
            metadata["story_analysis"]["rejected"] = {
                "analysis": str(getattr(rejected, "analysis", "") or "")[:2000],
                "question": (
                    str(getattr(rejected, "question", "") or "")[:800] or None
                ),
                "question_basis": str(
                    getattr(getattr(rejected, "question_basis", None), "value", "")
                    or ""
                )
                or None,
            }
        feed.metadata = metadata

    def _hydrate_representative_bodies(
        self,
        candidates: Sequence[ClusterEditorialCandidate],
        stats: PipelineStats,
    ) -> None:
        """
        Fetch bodies for shortlisted stories whose representative has none.

        This is the only place a page is fetched. Tier B articles reach here
        with a headline alone, which was enough to prove the story is being
        covered; it is not enough to write a card from. Bounded by
        `editorial_candidate_limit`, so it costs roughly a dozen requests.
        """
        if not candidates:
            return

        fetcher = self._get_body_fetcher()
        for candidate in candidates:
            article = candidate.representative_article
            if article is None or not fetcher.needs_body(article):
                continue
            try:
                hydrated = fetcher.hydrate(article)
            except Exception as e:
                logger.warning("Lazy body fetch raised for %s: %s", article.url, e)
                stats.lazy_body_fetch_failures += 1
                continue
            if not hydrated:
                stats.lazy_body_fetch_failures += 1
                continue
            stats.lazy_body_fetches += 1
            try:
                self.db.update_article_body(
                    article.id, article.main_text, article.metadata
                )
            except Exception as e:
                # The in-memory upgrade still benefits this run's editorial pass.
                logger.warning("Failed persisting fetched body for %s: %s", article.url, e)

    @staticmethod
    def _effective_story_limit(items: Sequence[object], configured_limit: int = 12) -> int:
        if not items:
            return 0
        return max(1, min(int(configured_limit), len(items)))

    def _ensure_renderable_brief_copy(self, candidate: ClusterEditorialCandidate) -> AnalyzedFeed:
        feed = candidate.base_feed.model_copy(deep=True)
        metadata = dict(feed.metadata or {})

        why_it_matters = str(metadata.get("why_it_matters") or "").strip()
        if not why_it_matters:
            impact_label = next(
                (label for label in feed.impact_labels or [] if label in _IMPACT_LINE_FALLBACKS),
                None,
            )
            metadata["why_it_matters"] = _IMPACT_LINE_FALLBACKS.get(
                impact_label or "",
                "This could affect public life in Pakistan today and is worth tracking closely.",
            )
            metadata["impact_line"] = metadata["why_it_matters"]

        what_to_watch = str(metadata.get("what_to_watch") or "").strip()
        if not what_to_watch:
            metadata["what_to_watch"] = _WHAT_TO_WATCH_FALLBACKS.get(
                str(feed.category),
                _WHAT_TO_WATCH_FALLBACKS["other"],
            )

        metadata.setdefault("selection_reason", "Included through deterministic publish fallback.")
        metadata["copy_generation_mode"] = "deterministic_fallback"
        metadata["llm_augmented"] = bool(metadata.get("llm_augmented"))
        feed.metadata = metadata
        return feed

    @staticmethod
    def _candidate_tag(candidate: ClusterEditorialCandidate) -> str:
        return str(candidate.base_feed.category or "other")

    def _select_editorial_articles(self, articles: Sequence[RawArticle], max_articles: int = 8) -> List[RawArticle]:
        if len(articles) <= max_articles:
            return list(articles)

        ordered = sorted(
            articles,
            key=lambda article: (
                -trusted_article_timestamp(article).timestamp(),
                article.source,
                article.url,
            ),
        )
        selected: List[RawArticle] = []
        seen_sources: set[str] = set()

        for article in ordered:
            if article.source in seen_sources:
                continue
            selected.append(article)
            seen_sources.add(article.source)
            if len(selected) >= max_articles:
                return selected

        for article in ordered:
            if article in selected:
                continue
            selected.append(article)
            if len(selected) >= max_articles:
                break

        return selected

    def _select_diverse_candidates(
        self,
        ranked_candidates: Sequence[ClusterEditorialCandidate],
        *,
        max_items: int,
        preferred_cluster_ids: Optional[Sequence[UUID]] = None,
    ) -> List[ClusterEditorialCandidate]:
        if max_items <= 0 or not ranked_candidates:
            return []

        lookup = {candidate.cluster_id: candidate for candidate in ranked_candidates}
        ordered: List[ClusterEditorialCandidate] = []
        seen_ids: set[UUID] = set()

        for cluster_id in preferred_cluster_ids or ():
            candidate = lookup.get(cluster_id)
            if candidate is None or candidate.cluster_id in seen_ids:
                continue
            ordered.append(candidate)
            seen_ids.add(candidate.cluster_id)

        for candidate in ranked_candidates:
            if candidate.cluster_id in seen_ids:
                continue
            ordered.append(candidate)
            seen_ids.add(candidate.cluster_id)

        selected: List[ClusterEditorialCandidate] = []
        selected_ids: set[UUID] = set()
        selected_story_families: set[str] = set()
        tag_counts: Dict[str, int] = {}

        for candidate in ordered:
            tag = self._candidate_tag(candidate)
            if tag_counts.get(tag, 0) >= 3:
                continue
            family_cues = self._candidate_story_family_cues(candidate)
            repeated = family_cues & selected_story_families
            # A story several publishers independently ran is not a
            # presentation-layer duplicate, whatever institution its headlines
            # name. This check exists to collapse thin follow-ups - a
            # condolence, an official's regret, a taskforce statement - and it
            # was silently deleting the day's third-best-corroborated story:
            # a province-wide hospital safety audit carried by four publishers,
            # suppressed behind the fire that prompted it purely because a
            # member headline said "PIMS". Judge it by the same corroboration
            # the rest of selection runs on.
            if repeated and (
                self._candidate_evidence(candidate).source_count
                < _STORY_FAMILY_CORROBORATION_FLOOR
            ):
                logger.info(
                    "Skipping cluster %s as a repeated brief storyline (%s)",
                    candidate.cluster_id,
                    ",".join(sorted(repeated)),
                )
                continue
            selected.append(candidate)
            selected_ids.add(candidate.cluster_id)
            selected_story_families.update(family_cues)
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if len(selected) >= max_items:
                break

        economy_candidate = next(
            (candidate for candidate in ordered if self._candidate_tag(candidate) == "economy"),
            None,
        )
        if economy_candidate is not None and economy_candidate.cluster_id not in selected_ids:
            if len(selected) < max_items:
                selected.append(economy_candidate)
            else:
                for index in range(len(selected) - 1, -1, -1):
                    if self._candidate_tag(selected[index]) == "economy":
                        continue
                    selected[index] = economy_candidate
                    break

        return selected[:max_items]

    @staticmethod
    def _candidate_story_family_cues(
        candidate: ClusterEditorialCandidate,
    ) -> set[str]:
        """Named institutions that should appear only once in a finite brief.

        Event clustering intentionally keeps a tragedy, a later dismissal and
        a parliamentary inquiry separate. That is correct for provenance but
        can still produce three cards about one incident. Acronyms such as
        PIMS provide a conservative story-family key for the presentation
        layer without loosening event identity underneath.
        """
        headlines = [
            candidate.base_feed.headline,
            candidate.representative_article.headline,
            *(article.headline for article in candidate.articles),
        ]
        return {
            token.casefold()
            for headline in headlines
            for token in re.findall(r"\b[A-Z][A-Z0-9-]{2,}\b", headline or "")
            if token not in GENERIC_ACRONYMS
        }

    def _rank_publishable_candidates(
        self, candidates: Sequence[ClusterEditorialCandidate]
    ) -> List[ClusterEditorialCandidate]:
        return sorted(
            candidates,
            key=lambda candidate: (
                *self._candidate_evidence(candidate).ranking_key(),
                candidate.cluster_id.hex,
            ),
        )

    @staticmethod
    def _article_prominence_score(article: RawArticle) -> int:
        metadata = article.metadata or {}
        try:
            score = max(0, int(metadata.get("source_prominence_score", 0) or 0))
        except Exception:
            score = 0
        if score > 0:
            return score
        return _SOURCE_PROMINENCE_FALLBACKS.get(article.source, 0)

    def _candidate_publisher_topline(self, candidate: ClusterEditorialCandidate) -> Dict[str, Any]:
        strongest_by_source: Dict[str, int] = {}
        bucket_score = 0
        for article in candidate.articles:
            prominence = self._article_prominence_score(article)
            strongest_by_source[article.source] = max(strongest_by_source.get(article.source, 0), prominence)
            bucket = str((article.metadata or {}).get("topline_bucket", "tail"))
            bucket_score += _TOPLINE_BUCKET_SCORES.get(bucket, 1)

        score = min(sum(strongest_by_source.values()), 42)
        lead_sources = sum(1 for value in strongest_by_source.values() if value >= 18)
        sources = sorted(source for source, value in strongest_by_source.items() if value >= 10)
        return {
            "score": score,
            "lead_sources": lead_sources,
            "source_count": len(sources),
            "sources": sources,
            "bucket_score": bucket_score,
        }

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

    @staticmethod
    def _candidate_latest_timestamp(candidate: ClusterEditorialCandidate) -> datetime:
        timestamps = [trusted_article_timestamp(article) for article in candidate.articles]
        latest = max(timestamps) if timestamps else candidate.representative_article.scraped_at
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return latest

    def _candidate_evidence(self, candidate: ClusterEditorialCandidate) -> CandidateEvidence:
        """Gather the facts about a candidate. No weighting, no thresholds."""
        feed = candidate.base_feed
        prominence = self._candidate_publisher_topline(candidate)
        triage = aggregate_triage(candidate.articles, candidate.representative_article)
        hours = (
            datetime.now(timezone.utc) - self._candidate_latest_timestamp(candidate)
        ).total_seconds() / 3600.0

        return CandidateEvidence(
            source_count=len(feed.source_attribution or {}),
            article_count=len(candidate.articles),
            prominence_score=int(prominence["score"]),
            lead_sources=int(prominence["lead_sources"]),
            prominent_source_count=int(prominence["source_count"]),
            bucket_score=int(prominence["bucket_score"]),
            hours_since_latest=max(0.0, hours),
            category=str(feed.category),
            impact_labels=tuple(feed.impact_labels or []),
            story_type=triage.story_type,
            pk_relevance=triage.pk_relevance,
            triage_confidence=float(triage.confidence),
        )

    @staticmethod
    def _parse_brief_stamp(raw: Any) -> Optional[datetime]:
        """Read a `brief_run_at` back as an aware UTC datetime."""
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if not isinstance(raw, str) or not raw.strip():
            return None
        text = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _representative_key(source: Any, headline: Any) -> tuple[str, str]:
        """Identify the reporting a card was built on, stably across runs.

        Cluster ids cannot do this job: they are regenerated every run, so the
        same story carried two different ids on consecutive days and
        `analyzed_feed_exists(cluster.id)` never matched. Headlines cannot
        either - the editor rewrites them, and it published "PM Shehbaz directs
        no area to face more than two hours of load-shedding" one day and
        "Prime Minister Shehbaz Sharif directs two-hour limit on electricity"
        the next, off the identical article. The representative article is the
        thing that actually held still.
        """
        return (
            " ".join(str(source or "").split()).lower(),
            " ".join(str(headline or "").split()).lower(),
        )

    def _previous_edition(self) -> tuple[frozenset[tuple[str, str]], Optional[datetime]]:
        """What the last published brief was built on, and when it ran.

        Computed once per run and cached. Fails open: a database that will not
        answer costs us a possible repeat, which is far cheaper than losing the
        edition.
        """
        if self._previous_edition_cache is not None:
            return self._previous_edition_cache

        keys: set[tuple[str, str]] = set()
        ran_at: Optional[datetime] = None
        try:
            rows = self.db.get_analyzed_feed(limit=60)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not read the previous edition; repeats unguarded: %s", exc)
            self._previous_edition_cache = (frozenset(), None)
            return self._previous_edition_cache

        stamps = []
        for row in rows:
            raw = (getattr(row, "metadata", None) or {}).get("brief_run_at")
            parsed = self._parse_brief_stamp(raw)
            if parsed is not None:
                stamps.append(parsed)
        if stamps:
            ran_at = max(stamps)
            for row in rows:
                metadata = getattr(row, "metadata", None) or {}
                raw = metadata.get("brief_run_at")
                parsed = self._parse_brief_stamp(raw)
                if parsed is None or parsed != ran_at:
                    continue
                keys.add(
                    self._representative_key(
                        metadata.get("representative_source"),
                        metadata.get("representative_headline"),
                    )
                )

        self._previous_edition_cache = (frozenset(keys), ran_at)
        if keys:
            logger.info(
                "Previous edition: %d cards published at %s; repeats suppressed unless reported on since",
                len(keys),
                ran_at.isoformat() if ran_at else "unknown",
            )
        return self._previous_edition_cache

    def _repeats_previous_edition(self, candidate: ClusterEditorialCandidate) -> bool:
        """Is this the previous edition's card again, with nothing new since?

        Two conditions, and the second is what keeps a running story alive. A
        brief must be able to lead with a story that is still developing - the
        36h ingest window exists for exactly that - so a candidate carrying any
        reporting filed since the last brief ran is never suppressed, however
        familiar it looks. What is suppressed is the case with no second
        condition to satisfy: the same article, re-clustered, re-selected and
        re-headlined, with nothing having happened in between. On 2026-09-12
        that put two of four cards in front of a reader who had read them the
        morning before, one of them under a byte-identical headline.
        """
        published, ran_at = self._previous_edition()
        if not published or ran_at is None:
            return False

        # Only a *previous day's* brief can make a story old news. A re-run of
        # the same morning is not a new edition to the reader, and treating it
        # as one inverts the gate: on 2026-09-14 a manual run 22 minutes after
        # the scheduled one suppressed two cards for having no fresh reporting
        # since - in 22 minutes, of course there was none - and published four
        # where it had six to offer. The reader sees one brief a day; the
        # comparison has to be to the last one they could actually have read.
        now = datetime.now(timezone.utc)
        if ran_at.astimezone(_PAKISTAN_TZ).date() == now.astimezone(_PAKISTAN_TZ).date():
            return False

        key = self._representative_key(
            candidate.representative_article.source,
            candidate.representative_article.headline,
        )
        if key not in published:
            return False

        return self._candidate_latest_timestamp(candidate) <= ran_at

    def _passes_hard_gates(self, candidate: ClusterEditorialCandidate) -> tuple[bool, str]:
        """
        The only deterministic exclusions left, and the only ones that should be.

        Everything here is mechanical and must never be negotiable. Judgement
        about what deserves the brief belongs to the editor, which now receives
        facts instead of competing with a score that had already discarded the
        candidate before it ever saw it.
        """
        evidence = self._candidate_evidence(candidate)

        # Hard category exclusions.
        if evidence.category in {"sports", "entertainment"}:
            return False, f"excluded category {evidence.category}"
        if evidence.story_type in {"opinion", "advertorial", "sport", "entertainment"}:
            return False, f"excluded story type {evidence.story_type}"
        if evidence.pk_relevance == "foreign":
            return False, "no Pakistan relevance"

        # A cluster triage never saw cannot be described honestly, so it is not
        # published; the run's triage_status already records why.
        if evidence.story_type is None:
            return False, "no triage verdict"

        # Staleness window.
        if evidence.hours_since_latest > float(self.config.article_max_age_hours):
            return False, f"stale by {evidence.hours_since_latest:.0f}h"

        # Already in the reader's hands, with nothing reported since.
        if self._repeats_previous_edition(candidate):
            return False, "published in the previous edition, nothing new since"

        return True, ""

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
        stage_started = time.perf_counter()
        logger.info(
            "Pipeline run started "
            "(max_articles_per_source=%d, embedding_backfill_limit=%d, cluster_lookback_hours=%d)",
            self.config.max_articles_per_source,
            self.config.embedding_backfill_limit,
            self.config.cluster_lookback_hours,
        )
        stats, inserted_articles = self.scrape_and_insert()
        stats.run_started_at = self.run_started_at
        stats.stage_seconds["ingest"] = round(time.perf_counter() - stage_started, 2)
        stage_started = time.perf_counter()
        logger.info(
            "Ingest+insert complete: discovered=%d inserted=%d duplicates=%d near_duplicates=%d failures=%d",
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
        stats.stage_seconds["embedding"] = round(time.perf_counter() - stage_started, 2)
        stage_started = time.perf_counter()
        logger.info(
            "Embedding complete: embedded=%d embed_failures=%d",
            stats.embedded,
            stats.embed_failures,
        )

        # Triage runs on articles, before grouping, so the verdict is available
        # to the publish gates and the editor alike.
        self.triage_articles(inserted_articles, stats)
        self.triage_backfill(stats)
        stats.stage_seconds["triage"] = round(time.perf_counter() - stage_started, 2)
        stage_started = time.perf_counter()
        logger.info(
            "Triage complete: articles=%d calls=%d failures=%d status=%s",
            stats.triage_articles,
            stats.triage_calls,
            stats.triage_failures,
            stats.triage_status,
        )

        # Re-cluster recent window to remediate historical low-quality clusters.
        self.remediate_recent_clusters(stats)
        # Clustering uses DB state so it can resume after partial failures.
        created_cluster_ids = self.cluster_unclustered_articles(stats)
        stats.stage_seconds["grouping"] = round(time.perf_counter() - stage_started, 2)
        stage_started = time.perf_counter()
        logger.info(
            "Clustering complete: clustered_articles=%d clusters_created=%d cluster_failures=%d "
            "rejected_low_similarity=%d adjudicated=%d merged=%d",
            stats.clustered_articles,
            stats.clusters_created,
            stats.cluster_failures,
            stats.clusters_rejected_low_similarity,
            stats.adjudicated_pairs,
            stats.adjudicated_merges,
        )

        # Analysis also uses DB state and avoids duplicate feed items per cluster.
        self.analyze_clusters_missing_feed(
            stats,
            cluster_ids=created_cluster_ids or None,
        )
        stats.stage_seconds["editorial_and_cards"] = round(time.perf_counter() - stage_started, 2)
        logger.info(
            "Analysis complete: feeds_inserted=%d feeds_replaced=%d feeds_rejected_editorial=%d "
            "analyze_failures=%d editorial_status=%s story_analysis_status=%s",
            stats.feeds_inserted,
            stats.feeds_replaced,
            stats.feeds_rejected_editorial,
            stats.analyze_failures,
            stats.editorial_status,
            stats.story_analysis_status,
        )
        self.prune_old_data(stats)

        try:
            if self.body_fetcher is not None:
                self.body_fetcher.close()
        except Exception:
            pass

        logger.info("Pipeline run summary: %s", stats.as_dict())
        return stats


def default_config(
    sources_yaml: Path | str = "backend/config/sources.yaml",
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

    enable_editorial_llm = os.getenv("SAAF_ENABLE_EDITORIAL_LLM", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    enable_triage_llm = os.getenv("SAAF_ENABLE_TRIAGE_LLM", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    enable_adjudication_llm = os.getenv("SAAF_ENABLE_ADJUDICATION_LLM", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    # Re-enabled 2026-08-27 after the guard layer was rebuilt and measured.
    # It was switched off first: the env default said "1" while
    # PipelineConfig.enable_story_analysis_llm said False, so the feature ran
    # in every production run and in no offline one, on validators that did
    # not work. What the fixed guards do on live data: 8 of 8 cards publish,
    # zero questions wrongly dropped, and the two analyses rejected were both
    # rejected correctly - one turned a publication date into an event date,
    # the other carried a reserves figure whose unit the supplied report never
    # states. A rejection costs a card its analysis, never the card.
    enable_story_analysis_llm = os.getenv("SAAF_ENABLE_STORY_ANALYSIS_LLM", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    def _env_is_set(name: str) -> bool:
        return bool((os.getenv(name) or "").strip())

    def _low_cost_ceiling(name: str, value: int, ceiling: int) -> int:
        """Apply a low-cost ceiling to a *default*, never to an explicit request.

        This used to be a bare `min()`, and it silently discarded configuration
        an operator had deliberately written. The scheduled workflow set
        SAAF_MAX_ARTICLES_PER_SOURCE=40 next to SAAF_LOW_COST_MODE=1 and got
        25, with nothing in the log to say so. The consequences ran the whole
        length of the pipeline: 200 articles instead of ~320, 171 clusters
        instead of the ~320 the selection thresholds were measured against, and
        - because the candidate shortlist was clamped the same silent way - an
        editor that saw 24 candidates, exhausted all 24 by its second attempt
        and had nothing deeper to retry against. Three consecutive live briefs
        shipped at 4, 4 and 5 cards against a floor of 6, filled out from the
        weak tail. Explicit beats implicit, and either way it is logged.
        """
        if value <= ceiling:
            return value
        if _env_is_set(name):
            logger.info(
                "Low-cost mode: keeping explicit %s=%d (would otherwise cap at %d)",
                name,
                value,
                ceiling,
            )
            return value
        logger.info("Low-cost mode: %s lowered from %d to %d", name, value, ceiling)
        return ceiling

    low_cost_mode = os.getenv("SAAF_LOW_COST_MODE", "0").strip().lower() in {"1", "true", "yes"}
    max_articles_per_source = _env_int("SAAF_MAX_ARTICLES_PER_SOURCE", 40)
    embedding_backfill_limit = _env_int("SAAF_EMBEDDING_BACKFILL_LIMIT", 100)
    editorial_candidate_limit = _env_int("SAAF_EDITORIAL_CANDIDATE_LIMIT", 30)
    editorial_max_stories = _env_int("SAAF_EDITORIAL_MAX_STORIES", 12)
    if low_cost_mode:
        max_articles_per_source = _low_cost_ceiling(
            "SAAF_MAX_ARTICLES_PER_SOURCE", max_articles_per_source, 25
        )
        embedding_backfill_limit = _low_cost_ceiling(
            "SAAF_EMBEDDING_BACKFILL_LIMIT", embedding_backfill_limit, 50
        )
        editorial_candidate_limit = _low_cost_ceiling(
            "SAAF_EDITORIAL_CANDIDATE_LIMIT", editorial_candidate_limit, 24
        )
        editorial_max_stories = _low_cost_ceiling(
            "SAAF_EDITORIAL_MAX_STORIES", editorial_max_stories, 12
        )

    return PipelineConfig(
        sources_yaml=Path(sources_yaml),
        enable_triage_llm=enable_triage_llm,
        enable_adjudication_llm=enable_adjudication_llm,
        enable_editorial_llm=enable_editorial_llm,
        enable_story_analysis_llm=enable_story_analysis_llm,
        max_articles_per_source=max_articles_per_source,
        embedding_backfill_limit=embedding_backfill_limit,
        editorial_candidate_limit=editorial_candidate_limit,
        editorial_max_stories=editorial_max_stories,
    )
