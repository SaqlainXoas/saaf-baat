"""
Story grouping utilities for Saaf Baat.

The production path now uses deterministic event grouping built from strict
time, embedding, and lexical/entity overlap signals. Legacy density-clustering
helpers remain available for tests and comparison, but they are no longer the
main story-formation mechanism.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from numpy.typing import NDArray

from src.db.models import RawArticle

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_NUMERIC_CUE_RE = re.compile(
    r"\b\d[\d,./-]*(?:%|bn|m|million|billion|crore|lakh|rs|pkr|usd)?\b",
    re.IGNORECASE,
)
_PROPER_TOKEN_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
_STOPWORDS = {
    "about",
    "after",
    "amid",
    "and",
    "are",
    "around",
    "as",
    "at",
    "be",
    "been",
    "begins",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "its",
    "more",
    "new",
    "of",
    "on",
    "over",
    "says",
    "say",
    "that",
    "the",
    "their",
    "this",
    "to",
    "under",
    "up",
    "was",
    "with",
}


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _tokenize(text: str) -> Set[str]:
    return {
        token
        for token in _TOKEN_RE.findall((text or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _headline_tokens(article: RawArticle) -> Set[str]:
    return _tokenize(article.headline)


def _entity_cues(article: RawArticle) -> Set[str]:
    text = _normalize_ws(f"{article.headline}. {article.main_text[:240]}")
    cues: Set[str] = set()
    for match in _ACRONYM_RE.findall(text):
        cues.add(match.lower())
    for match in _NUMERIC_CUE_RE.findall(text):
        cues.add(match.lower())
    for match in _PROPER_TOKEN_RE.findall(text):
        token = match.lower()
        if token not in _STOPWORDS:
            cues.add(token)
    return cues


def _set_overlap(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return float(len(left & right) / len(union))


def publish_date_skew_hours(article: RawArticle) -> float | None:
    scraped = article.scraped_at
    if scraped.tzinfo is None:
        scraped = scraped.replace(tzinfo=timezone.utc)

    published = article.publish_date
    if published is None:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)

    return abs((scraped - published).total_seconds()) / 3600.0


def trusted_article_timestamp(article: RawArticle, max_publish_skew_hours: int = 72) -> datetime:
    scraped = article.scraped_at
    if scraped.tzinfo is None:
        scraped = scraped.replace(tzinfo=timezone.utc)

    skew_hours = publish_date_skew_hours(article)
    if skew_hours is None:
        return scraped
    if skew_hours > max_publish_skew_hours:
        return scraped
    published = article.publish_date
    if published is None:
        return scraped
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published


# ============================================================================
# Exceptions
# ============================================================================

class ClusteringError(Exception):
    """Base exception for clustering errors."""
    pass


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ClusteringResult:
    """Result of clustering operation."""
    
    labels: NDArray[np.int64]
    """Cluster labels for each input point. -1 indicates noise."""
    
    algorithm_used: str
    """Name of the algorithm that produced these results."""
    
    num_clusters: int
    """Number of clusters found (excluding noise)."""
    
    noise_ratio: float
    """Ratio of points classified as noise (0.0 to 1.0)."""
    
    @classmethod
    def from_labels(cls, labels: NDArray[np.int64], algorithm: str) -> "ClusteringResult":
        """Create result from labels array."""
        unique_labels = set(labels)
        num_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        noise_count = np.sum(labels == -1)
        noise_ratio = noise_count / len(labels) if len(labels) > 0 else 0.0
        
        return cls(
            labels=labels,
            algorithm_used=algorithm,
            num_clusters=num_clusters,
            noise_ratio=noise_ratio
        )


@dataclass(frozen=True)
class EventGroup:
    """A tight, event-level article group."""

    indices: Tuple[int, ...]
    centroid: NDArray[np.float32]
    avg_similarity: float
    min_member_similarity: float


@dataclass(frozen=True)
class EventGroupingResult:
    """Deterministic event-grouping output."""

    labels: NDArray[np.int64]
    groups: List[EventGroup]
    algorithm_used: str
    num_clusters: int
    noise_ratio: float


@dataclass(frozen=True)
class _PreparedArticle:
    index: int
    event_time: datetime
    headline_tokens: Set[str]
    entity_cues: Set[str]


# ============================================================================
# HDBSCAN Clusterer
# ============================================================================

class HDBSCANClusterer:
    """
    HDBSCAN clustering for news articles.
    
    HDBSCAN is the primary clustering algorithm because:
    - Automatically determines number of clusters
    - Handles varying cluster densities (breaking news vs minor stories)
    - Identifies outliers/noise naturally
    - Works well with precomputed cosine distance for text embeddings
    """
    
    def __init__(
        self,
        min_cluster_size: int = 3,
        min_samples: int = 2,
        metric: str = "cosine",
        cluster_selection_epsilon: float = 0.0,
    ):
        """
        Initialize HDBSCAN clusterer.
        
        Args:
            min_cluster_size: Minimum articles to form a cluster (story).
            min_samples: Core point threshold for density estimation.
            metric: Distance metric ('cosine' recommended for embeddings).
            cluster_selection_epsilon: Distance threshold for flat clustering.
        """
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.metric = metric
        self.cluster_selection_epsilon = cluster_selection_epsilon
        self._model = None
    
    def fit_predict(self, embeddings: NDArray[np.float32]) -> NDArray[np.int64]:
        """
        Cluster embeddings and return labels.
        
        Args:
            embeddings: Array of shape (n_samples, n_features).
            
        Returns:
            Array of cluster labels. -1 indicates noise/outlier.
            
        Raises:
            ClusteringError: If embeddings are empty.
        """
        if len(embeddings) == 0:
            raise ClusteringError("Cannot cluster empty embeddings array")
        
        # Handle single point - it's always noise
        if len(embeddings) == 1:
            return np.array([-1], dtype=np.int64)
        
        try:
            import hdbscan
        except ImportError:
            raise ClusteringError(
                "hdbscan package not installed. Run: pip install hdbscan"
            )
        
        # For cosine distance, compute precomputed distance matrix
        # HDBSCAN's BallTree doesn't support cosine directly
        if self.metric == "cosine":
            from sklearn.metrics.pairwise import cosine_distances
            # HDBSCAN requires float64 for precomputed distances
            distance_matrix = cosine_distances(embeddings).astype(np.float64)
            
            self._model = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric="precomputed",
                cluster_selection_epsilon=self.cluster_selection_epsilon,
            )
            labels = self._model.fit_predict(distance_matrix)
        else:
            self._model = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric=self.metric,
                cluster_selection_epsilon=self.cluster_selection_epsilon,
            )
            labels = self._model.fit_predict(embeddings)
        
        return labels.astype(np.int64)


# ============================================================================
# DBSCAN Clusterer (Fallback)
# ============================================================================

class DBSCANClusterer:
    """
    DBSCAN clustering as fallback when HDBSCAN quality is poor.
    
    DBSCAN is simpler and can work better on certain data distributions,
    especially when clusters are more uniform in density.
    """
    
    def __init__(
        self,
        eps: float = 0.3,
        min_samples: int = 2,
        metric: str = "cosine",
    ):
        """
        Initialize DBSCAN clusterer.
        
        Args:
            eps: Maximum distance between points in same neighborhood.
                 For cosine metric, 0.3 means similarity > 0.7.
            min_samples: Minimum points to form a core point.
            metric: Distance metric ('cosine' recommended for embeddings).
        """
        self.eps = eps
        self.min_samples = min_samples
        self.metric = metric
        self._model = None
    
    def fit_predict(self, embeddings: NDArray[np.float32]) -> NDArray[np.int64]:
        """
        Cluster embeddings and return labels.
        
        Args:
            embeddings: Array of shape (n_samples, n_features).
            
        Returns:
            Array of cluster labels. -1 indicates noise/outlier.
            
        Raises:
            ClusteringError: If embeddings are empty.
        """
        if len(embeddings) == 0:
            raise ClusteringError("Cannot cluster empty embeddings array")
        
        # Handle single point - it's always noise
        if len(embeddings) == 1:
            return np.array([-1], dtype=np.int64)
        
        try:
            from sklearn.cluster import DBSCAN
        except ImportError:
            raise ClusteringError(
                "scikit-learn not installed. Run: pip install scikit-learn"
            )
        
        self._model = DBSCAN(
            eps=self.eps,
            min_samples=self.min_samples,
            metric=self.metric,
        )
        
        labels = self._model.fit_predict(embeddings)
        
        return labels.astype(np.int64)


# ============================================================================
# Clustering Service
# ============================================================================

class ClusteringService:
    """
    Unified clustering service with quality validation and automatic fallback.
    
    Uses HDBSCAN as primary algorithm, falls back to DBSCAN if quality
    thresholds are not met.
    """
    
    def __init__(
        self,
        # For a small news aggregator (tens-hundreds of docs/run), it is normal to
        # produce just 1 coherent cluster and lots of noise. Downstream pipeline
        # guardrails enforce story coherence, so these checks should not zero out
        # all labels.
        min_clusters: int = 1,
        max_noise_ratio: float = 0.95,
        min_cluster_size: int = 3,
        hdbscan_params: Optional[Dict] = None,
        dbscan_params: Optional[Dict] = None,
    ):
        """
        Initialize clustering service.
        
        Args:
            min_clusters: Minimum acceptable number of clusters.
            max_noise_ratio: Maximum acceptable noise ratio (0.0-1.0).
            min_cluster_size: Minimum articles per cluster.
            hdbscan_params: Custom parameters for HDBSCAN.
            dbscan_params: Custom parameters for DBSCAN.
        """
        self.min_clusters = min_clusters
        self.max_noise_ratio = max_noise_ratio
        self.min_cluster_size = min_cluster_size
        
        self.primary_algorithm = "hdbscan"
        self.fallback_algorithm = "dbscan"
        
        # Initialize clusterers
        hdbscan_config = {"min_cluster_size": min_cluster_size}
        if hdbscan_params:
            hdbscan_config.update(hdbscan_params)
        self._hdbscan = HDBSCANClusterer(**hdbscan_config)
        
        dbscan_config = {"min_samples": 2}
        if dbscan_params:
            dbscan_config.update(dbscan_params)
        self._dbscan = DBSCANClusterer(**dbscan_config)
    
    def _is_quality_clustering(self, labels: NDArray[np.int64]) -> bool:
        """
        Check if clustering result meets quality thresholds.
        
        Quality criteria:
        - At least min_clusters distinct clusters
        - Noise ratio below max_noise_ratio
        
        Args:
            labels: Cluster labels array.
            
        Returns:
            True if quality is acceptable, False otherwise.
        """
        if len(labels) == 0:
            return False
        
        # Count clusters (excluding noise label -1)
        unique_labels = set(labels)
        num_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        
        # Calculate noise ratio
        noise_count = np.sum(labels == -1)
        noise_ratio = noise_count / len(labels)
        
        # Check thresholds
        if num_clusters < self.min_clusters:
            logger.debug(
                f"Quality check failed: {num_clusters} clusters < {self.min_clusters} min"
            )
            return False
        
        if noise_ratio > self.max_noise_ratio:
            logger.debug(
                f"Quality check failed: {noise_ratio:.2f} noise > {self.max_noise_ratio} max"
            )
            return False
        
        return True
    
    def cluster(self, embeddings: NDArray[np.float32]) -> ClusteringResult:
        """
        Cluster embeddings with automatic fallback.
        
        Tries HDBSCAN first. If quality is poor, falls back to DBSCAN.
        
        Args:
            embeddings: Array of shape (n_samples, n_features).
            
        Returns:
            ClusteringResult with labels and metadata.
        """
        if len(embeddings) == 0:
            raise ClusteringError("Cannot cluster empty embeddings array")

        hdbscan_labels: Optional[NDArray[np.int64]] = None

        # Try primary algorithm (HDBSCAN)
        try:
            labels = self._hdbscan.fit_predict(embeddings)
            hdbscan_labels = labels

            if self._is_quality_clustering(labels):
                logger.info(
                    f"HDBSCAN clustering successful: "
                    f"{len(set(labels)) - (1 if -1 in labels else 0)} clusters"
                )
                return ClusteringResult.from_labels(labels, self.primary_algorithm)

            logger.info("HDBSCAN clustering produced low-quality output, trying DBSCAN fallback")

        except Exception as e:
            logger.warning(f"HDBSCAN failed: {e}, trying DBSCAN fallback")

        # Fallback to DBSCAN
        try:
            labels = self._dbscan.fit_predict(embeddings)
            if self._is_quality_clustering(labels):
                logger.info(
                    f"DBSCAN fallback accepted: "
                    f"{len(set(labels)) - (1 if -1 in labels else 0)} clusters"
                )
                return ClusteringResult.from_labels(labels, self.fallback_algorithm)

            # Do not discard the labels. Downstream pipeline guardrails enforce semantic
            # coherence and will reject mixed-topic clusters.
            logger.warning(
                "DBSCAN output failed quality checks (clusters=%d, noise=%.2f). Returning labels anyway.",
                len(set(labels)) - (1 if -1 in set(labels) else 0),
                float(np.sum(labels == -1) / len(labels)),
            )
            return ClusteringResult.from_labels(labels, f"{self.fallback_algorithm}_low_quality")

        except Exception as e:
            if hdbscan_labels is not None:
                logger.warning("DBSCAN failed (%s); returning HDBSCAN labels anyway", e)
                return ClusteringResult.from_labels(hdbscan_labels, f"{self.primary_algorithm}_unvalidated")

            logger.error(f"Both clustering algorithms failed: {e}")
            raise ClusteringError(f"Clustering failed: {e}")


class EventGroupingService:
    """
    Deterministic event grouping for production story formation.

    Articles only join the same group when multiple signals agree:
    - close event time window
    - strong embedding similarity
    - meaningful headline/entity overlap
    - merged group remains semantically tight
    """

    def __init__(
        self,
        min_cluster_size: int = 2,
        max_time_delta_hours: int = 18,
        min_pair_similarity: float = 0.80,
        min_group_centroid_similarity: float = 0.76,
        min_group_avg_similarity: float = 0.74,
        min_headline_overlap: float = 0.20,
        min_entity_overlap: float = 0.15,
        max_publish_skew_hours: int = 72,
        max_required_supporting_members: int = 3,
    ):
        self.min_cluster_size = min_cluster_size
        self.max_time_delta_hours = max_time_delta_hours
        self.min_pair_similarity = min_pair_similarity
        self.min_group_centroid_similarity = min_group_centroid_similarity
        self.min_group_avg_similarity = min_group_avg_similarity
        self.min_headline_overlap = min_headline_overlap
        self.min_entity_overlap = min_entity_overlap
        self.max_publish_skew_hours = max_publish_skew_hours
        self.max_required_supporting_members = max(1, int(max_required_supporting_members))

    @staticmethod
    def _normalize_embeddings(articles: Sequence[RawArticle]) -> NDArray[np.float32]:
        rows: List[NDArray[np.float32]] = []
        dims: Optional[int] = None
        for article in articles:
            if article.embedding is None:
                raise ClusteringError("All grouped articles must have embeddings")
            vec = np.asarray(article.embedding, dtype=np.float32)
            if vec.ndim != 1 or vec.size == 0:
                raise ClusteringError("Embeddings must be 1D non-empty vectors")
            if dims is None:
                dims = int(vec.size)
            elif int(vec.size) != dims:
                raise ClusteringError("All embeddings must have the same dimensions")
            norm = float(np.linalg.norm(vec))
            if norm <= 0:
                raise ClusteringError("Embeddings must have non-zero norm")
            rows.append(vec / norm)
        if not rows:
            raise ClusteringError("Cannot group an empty article sequence")
        return np.vstack(rows)

    def _prepare_articles(self, articles: Sequence[RawArticle]) -> List[_PreparedArticle]:
        return [
            _PreparedArticle(
                index=index,
                event_time=trusted_article_timestamp(article, self.max_publish_skew_hours),
                headline_tokens=_headline_tokens(article),
                entity_cues=_entity_cues(article),
            )
            for index, article in enumerate(articles)
        ]

    def _time_window_ok(
        self,
        candidate: _PreparedArticle,
        group: Sequence[int],
        prepared: Sequence[_PreparedArticle],
    ) -> bool:
        timestamps = [prepared[idx].event_time for idx in group]
        timestamps.append(candidate.event_time)
        span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0
        return span_hours <= float(self.max_time_delta_hours)

    def _pair_overlap(
        self,
        left: _PreparedArticle,
        right: _PreparedArticle,
    ) -> Tuple[float, float]:
        return (
            _set_overlap(left.headline_tokens, right.headline_tokens),
            _set_overlap(left.entity_cues, right.entity_cues),
        )

    def _has_required_overlap(
        self,
        headline_overlap: float,
        entity_overlap: float,
        shared_cues: int,
    ) -> bool:
        if shared_cues < 2:
            return False
        return (
            headline_overlap >= self.min_headline_overlap
            or entity_overlap >= self.min_entity_overlap
            or (
                headline_overlap >= max(0.15, self.min_headline_overlap * 0.75)
                and entity_overlap >= max(0.15, self.min_entity_overlap)
            )
        )

    def _group_quality(
        self,
        indices: Sequence[int],
        embeddings: NDArray[np.float32],
    ) -> Tuple[NDArray[np.float32], float, float]:
        group_embeddings = embeddings[np.array(indices, dtype=np.int64)]
        centroid = calculate_centroid(group_embeddings)
        similarities = group_embeddings @ centroid
        min_member_similarity = float(np.min(similarities)) if len(similarities) else 1.0
        avg_similarity = float(calculate_intra_cluster_similarity(group_embeddings))
        return centroid, avg_similarity, min_member_similarity

    def _required_support(self, group_size: int) -> int:
        if group_size <= 2:
            return 1
        if group_size <= 6:
            return min(2, self.max_required_supporting_members)
        return min(3, self.max_required_supporting_members)

    def _pair_is_compatible(
        self,
        left_idx: int,
        right_idx: int,
        embeddings: NDArray[np.float32],
        prepared: Sequence[_PreparedArticle],
    ) -> Tuple[bool, float, float, float]:
        similarity = float(embeddings[left_idx] @ embeddings[right_idx])
        if similarity < self.min_pair_similarity:
            return False, similarity, 0.0, 0.0

        headline_overlap, entity_overlap = self._pair_overlap(
            prepared[left_idx],
            prepared[right_idx],
        )
        shared_cues = len(
            (prepared[left_idx].headline_tokens & prepared[right_idx].headline_tokens)
            | (prepared[left_idx].entity_cues & prepared[right_idx].entity_cues)
        )
        compatible = self._has_required_overlap(headline_overlap, entity_overlap, shared_cues)
        return compatible, similarity, headline_overlap, entity_overlap

    def _candidate_score(
        self,
        article_index: int,
        group: Sequence[int],
        embeddings: NDArray[np.float32],
        prepared: Sequence[_PreparedArticle],
    ) -> Optional[float]:
        candidate = prepared[article_index]
        if not self._time_window_ok(candidate, group, prepared):
            return None

        compatible_members = 0
        pair_max = 0.0
        headline_overlap = 0.0
        entity_overlap = 0.0
        for member_idx in group:
            compatible, pair_similarity, pair_headline_overlap, pair_entity_overlap = (
                self._pair_is_compatible(article_index, member_idx, embeddings, prepared)
            )
            if not compatible:
                continue
            compatible_members += 1
            pair_max = max(pair_max, pair_similarity)
            headline_overlap = max(headline_overlap, pair_headline_overlap)
            entity_overlap = max(entity_overlap, pair_entity_overlap)

        if compatible_members < self._required_support(len(group)):
            return None

        merged_indices = [*group, article_index]
        centroid, avg_similarity, min_member_similarity = self._group_quality(
            merged_indices,
            embeddings,
        )
        centroid_similarity = float(embeddings[article_index] @ centroid)
        if centroid_similarity < self.min_group_centroid_similarity:
            return None
        if avg_similarity < self.min_group_avg_similarity:
            return None
        if min_member_similarity < self.min_group_centroid_similarity:
            return None

        return (
            pair_max * 0.45
            + centroid_similarity * 0.35
            + headline_overlap * 0.12
            + entity_overlap * 0.08
            + min(compatible_members, 3) * 0.02
        )

    def _try_merge_groups(
        self,
        groups: List[List[int]],
        embeddings: NDArray[np.float32],
        prepared: Sequence[_PreparedArticle],
    ) -> List[List[int]]:
        merged = [list(group) for group in groups]
        changed = True
        while changed:
            changed = False
            best_pair: Optional[Tuple[int, int, float]] = None
            for left_idx in range(len(merged)):
                for right_idx in range(left_idx + 1, len(merged)):
                    left = merged[left_idx]
                    right = merged[right_idx]
                    if not left or not right:
                        continue
                    if not all(self._time_window_ok(prepared[idx], left, prepared) for idx in right):
                        continue
                    if not all(self._time_window_ok(prepared[idx], right, prepared) for idx in left):
                        continue

                    cross_pair_max = 0.0
                    headline_overlap = 0.0
                    entity_overlap = 0.0
                    left_supported = set()
                    right_supported = set()
                    for left_article in left:
                        for right_article in right:
                            compatible, similarity, pair_headline_overlap, pair_entity_overlap = (
                                self._pair_is_compatible(
                                    left_article,
                                    right_article,
                                    embeddings,
                                    prepared,
                                )
                            )
                            if not compatible:
                                continue
                            cross_pair_max = max(cross_pair_max, similarity)
                            headline_overlap = max(headline_overlap, pair_headline_overlap)
                            entity_overlap = max(entity_overlap, pair_entity_overlap)
                            left_supported.add(left_article)
                            right_supported.add(right_article)

                    if cross_pair_max < self.min_pair_similarity:
                        continue
                    if len(left_supported) < self._required_support(len(left)):
                        continue
                    if len(right_supported) < self._required_support(len(right)):
                        continue

                    combined = [*left, *right]
                    _centroid, avg_similarity, min_member_similarity = self._group_quality(
                        combined,
                        embeddings,
                    )
                    if avg_similarity < self.min_group_avg_similarity:
                        continue
                    if min_member_similarity < self.min_group_centroid_similarity:
                        continue

                    merge_score = cross_pair_max * 0.7 + max(headline_overlap, entity_overlap) * 0.3
                    if best_pair is None or merge_score > best_pair[2]:
                        best_pair = (left_idx, right_idx, merge_score)

            if best_pair is None:
                continue

            left_idx, right_idx, _score = best_pair
            merged[left_idx].extend(merged[right_idx])
            merged[left_idx] = sorted(set(merged[left_idx]))
            del merged[right_idx]
            changed = True

        return merged

    def group_articles(self, articles: Sequence[RawArticle]) -> EventGroupingResult:
        if not articles:
            raise ClusteringError("Cannot group an empty article sequence")

        embeddings = self._normalize_embeddings(articles)
        prepared = self._prepare_articles(articles)
        order = sorted(
            range(len(articles)),
            key=lambda idx: (
                -prepared[idx].event_time.timestamp(),
                articles[idx].source,
                articles[idx].url,
            ),
        )

        groups: List[List[int]] = []
        for article_index in order:
            best_group_index: Optional[int] = None
            best_score = float("-inf")
            for group_index, group in enumerate(groups):
                candidate_score = self._candidate_score(article_index, group, embeddings, prepared)
                if candidate_score is None:
                    continue
                if candidate_score > best_score:
                    best_score = candidate_score
                    best_group_index = group_index
            if best_group_index is None:
                groups.append([article_index])
            else:
                groups[best_group_index].append(article_index)

        groups = self._try_merge_groups(groups, embeddings, prepared)

        labels = np.full(len(articles), -1, dtype=np.int64)
        event_groups: List[EventGroup] = []
        valid_groups = [sorted(group) for group in groups if len(group) >= self.min_cluster_size]
        valid_groups.sort(key=lambda group: (prepared[group[0]].event_time, group[0]), reverse=True)

        for label, group in enumerate(valid_groups):
            centroid, avg_similarity, min_member_similarity = self._group_quality(group, embeddings)
            if avg_similarity < self.min_group_avg_similarity:
                continue
            if min_member_similarity < self.min_group_centroid_similarity:
                continue
            event_groups.append(
                EventGroup(
                    indices=tuple(group),
                    centroid=centroid,
                    avg_similarity=avg_similarity,
                    min_member_similarity=min_member_similarity,
                )
            )
            for index in group:
                labels[index] = label

        noise_ratio = float(np.sum(labels == -1) / len(labels)) if len(labels) else 0.0
        return EventGroupingResult(
            labels=labels,
            groups=event_groups,
            algorithm_used="event_graph",
            num_clusters=len(event_groups),
            noise_ratio=noise_ratio,
        )


# ============================================================================
# Cluster Analysis Functions
# ============================================================================

def calculate_centroid(embeddings: NDArray[np.float32]) -> NDArray[np.float32]:
    """
    Calculate normalized centroid of embeddings.
    
    Args:
        embeddings: Array of shape (n_samples, n_features).
        
    Returns:
        Normalized centroid vector of shape (n_features,).
    """
    if len(embeddings) == 0:
        raise ValueError("Cannot calculate centroid of empty array")
    
    # Calculate mean
    centroid = np.mean(embeddings, axis=0)
    
    # Normalize for cosine similarity
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    
    return centroid.astype(np.float32)


def find_representative_article(
    embeddings: NDArray[np.float32],
    centroid: NDArray[np.float32],
) -> int:
    """
    Find index of article closest to cluster centroid.
    
    Args:
        embeddings: Array of shape (n_samples, n_features).
        centroid: Centroid vector of shape (n_features,).
        
    Returns:
        Index of the most representative article.
    """
    if len(embeddings) == 0:
        raise ValueError("Cannot find representative of empty array")
    
    # Calculate cosine similarities (dot product for normalized vectors)
    similarities = embeddings @ centroid
    
    # Return index of highest similarity
    return int(np.argmax(similarities))


def calculate_intra_cluster_similarity(
    embeddings: NDArray[np.float32],
) -> float:
    """
    Calculate average pairwise cosine similarity within cluster.
    
    Args:
        embeddings: Array of shape (n_samples, n_features).
        
    Returns:
        Average similarity (0.0 to 1.0). Returns 1.0 for single point.
    """
    n = len(embeddings)
    
    if n == 0:
        raise ValueError("Cannot calculate similarity of empty array")
    
    if n == 1:
        return 1.0  # Single point has perfect "similarity"
    
    # Calculate all pairwise similarities using matrix multiplication
    # For normalized vectors, similarity = dot product
    similarity_matrix = embeddings @ embeddings.T
    
    # Extract upper triangle (excluding diagonal) for unique pairs
    upper_indices = np.triu_indices(n, k=1)
    pairwise_similarities = similarity_matrix[upper_indices]
    
    # Return average
    return float(np.mean(pairwise_similarities))


# ============================================================================
# Cluster Mapping
# ============================================================================

def create_cluster_mapping(
    article_ids: List[str],
    labels: NDArray[np.int64],
    embeddings: NDArray[np.float32],
) -> Dict[str, Dict]:
    """
    Create mapping from cluster IDs to article data.
    
    Args:
        article_ids: List of article identifiers.
        labels: Cluster labels for each article.
        embeddings: Embeddings array.
        
    Returns:
        Dict mapping cluster_id to:
        - article_ids: List of article IDs in cluster
        - centroid: Cluster centroid embedding
        - similarity: Intra-cluster similarity score
    """
    if len(article_ids) != len(labels) or len(article_ids) != len(embeddings):
        raise ValueError("article_ids, labels, and embeddings must have same length")
    
    mapping: Dict[str, Dict] = {}
    
    # Get unique cluster labels (excluding noise)
    unique_labels = set(labels)
    cluster_labels = [l for l in unique_labels if l != -1]
    
    for cluster_label in cluster_labels:
        # Get indices for this cluster
        indices = np.where(labels == cluster_label)[0]
        
        # Get article IDs
        cluster_article_ids = [article_ids[i] for i in indices]
        
        # Get embeddings for this cluster
        cluster_embeddings = embeddings[indices]
        
        # Calculate centroid
        centroid = calculate_centroid(cluster_embeddings)
        
        # Calculate intra-cluster similarity
        similarity = calculate_intra_cluster_similarity(cluster_embeddings)
        
        # Create cluster ID
        cluster_id = f"cluster-{cluster_label}"
        
        mapping[cluster_id] = {
            "article_ids": cluster_article_ids,
            "centroid": centroid,
            "similarity": similarity,
        }
    
    return mapping


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    # Exceptions
    "ClusteringError",
    # Classes
    "ClusteringResult",
    "EventGroup",
    "EventGroupingResult",
    "EventGroupingService",
    "HDBSCANClusterer",
    "DBSCANClusterer",
    "ClusteringService",
    # Functions
    "calculate_centroid",
    "find_representative_article",
    "calculate_intra_cluster_similarity",
    "create_cluster_mapping",
]
