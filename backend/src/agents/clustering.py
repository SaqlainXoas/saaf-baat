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
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from numpy.typing import NDArray

from src.db.models import RawArticle
from src.utils.timestamps import trusted_article_timestamp

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
_GENERIC_EVENT_CUES = {
    "audit",
    "audits",
    "fire",
    "government",
    "govt",
    "health",
    "hospital",
    "hospitals",
    "inspection",
    "inspections",
    "order",
    "ordered",
    "orders",
    "review",
    "reviews",
    "report",
    "reports",
    "safety",
}


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _tokenize(text: str) -> Set[str]:
    return {
        token
        for token in _TOKEN_RE.findall((text or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _event_core_headline(headline: str) -> str:
    """Remove incident context that is not the event asserted by a headline.

    "After the PIMS fire, Punjab orders hospital inspections" is an inspection
    story, not another report of the fire.  Treating every word as event
    identity allowed causal follow-ups to bridge otherwise separate groups.
    """
    text = _normalize_ws(headline)
    leading = re.match(r"(?i)^(?:after|following)\s+[^,:;]{3,120}[,:]\s+(.+)$", text)
    if leading:
        text = leading.group(1).strip()

    prefix, separator, suffix = text.partition(":")
    if separator and re.search(
        r"(?i)\b(?:fire|blaze|blast|crash|flood|killing|death|tragedy)\b", prefix
    ) and re.search(
        r"(?i)\b(?:audit|inspect|launch|order|review|seek|start|survey)\w*\b", suffix
    ):
        text = suffix.strip()

    caused = re.match(
        r"(?i)^(.+?\b(?:fire|blaze|blast|crash|flood|killing|death|tragedy))\s+"
        r"(?:prompts?|sparks?|triggers?)\s+(.+)$",
        text,
    )
    if caused:
        text = caused.group(2).strip()

    trailing = re.match(r"(?i)^(.+?)\s+(?:after|following)\s+[^,;:]{3,120}$", text)
    if trailing and re.search(
        r"(?i)\b(?:audit|inspect|launch|order|review|seek|start|survey)\w*\b",
        trailing.group(1),
    ):
        text = trailing.group(1).strip()
    return text


def _headline_tokens(article: RawArticle) -> Set[str]:
    return _tokenize(_event_core_headline(article.headline))


def _entity_cues(article: RawArticle) -> Set[str]:
    # Body intros routinely recap the event that caused a new action.  Those
    # names are context, not proof that the action and incident are one event.
    text = _event_core_headline(article.headline)
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
    source: str
    event_time: datetime
    headline_tokens: Set[str]
    entity_cues: Set[str]


# ============================================================================
# Event grouping
# ============================================================================

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
        min_cluster_size: int = 1,
        max_time_delta_hours: int = 18,
        min_pair_similarity: float = 0.80,
        min_group_centroid_similarity: float = 0.76,
        min_group_avg_similarity: float = 0.74,
        min_headline_overlap: float = 0.20,
        min_entity_overlap: float = 0.15,
        max_publish_skew_hours: int = 36,
        max_required_supporting_members: int = 3,
        adjudicator: Optional[object] = None,
        adjudication_band_below: float = 0.06,
        adjudication_band_above: float = 0.04,
        max_adjudication_pairs: int = 24,
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
        # Injected, not constructed: this module stays LLM-free and merely
        # consults a callable for the pairs its own signals cannot settle.
        self.adjudicator = adjudicator
        self.adjudication_band_below = float(adjudication_band_below)
        self.adjudication_band_above = float(adjudication_band_above)
        self.max_adjudication_pairs = int(max_adjudication_pairs)
        self._adjudicated: Dict[Tuple[int, int], bool] = {}
        self.last_adjudication: Optional[object] = None

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
                source=article.source,
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
        pair_key = (min(left_idx, right_idx), max(left_idx, right_idx))
        if similarity < self.min_pair_similarity and not self._adjudicated.get(pair_key):
            return False, similarity, 0.0, 0.0

        headline_overlap, entity_overlap = self._pair_overlap(
            prepared[left_idx],
            prepared[right_idx],
        )
        if (
            prepared[left_idx].source == prepared[right_idx].source
            and not (prepared[left_idx].headline_tokens & prepared[right_idx].headline_tokens)
        ):
            return False, similarity, headline_overlap, entity_overlap
        shared = (
            (prepared[left_idx].headline_tokens & prepared[right_idx].headline_tokens)
            | (prepared[left_idx].entity_cues & prepared[right_idx].entity_cues)
        )
        distinctive_shared = len(shared - _GENERIC_EVENT_CUES)
        if (
            prepared[left_idx].source == prepared[right_idx].source
            and distinctive_shared < 2
        ):
            # Two separate articles from one newsroom need stronger identity
            # than the shared subject alone. This keeps a PIMS rescue-delay
            # report separate from a PIMS historic-violations report.
            return False, similarity, headline_overlap, entity_overlap
        # One distinctive owner plus several matching action cues is enough
        # ("Maritime ... safety audits"). Generic action cues alone are not
        # ("Punjab ... safety audits" vs "Maritime ... safety audits").
        shared_cues = (
            2
            if distinctive_shared == 1 and len(shared) >= 3 and headline_overlap >= 0.20
            else distinctive_shared
        )
        compatible = self._has_required_overlap(headline_overlap, entity_overlap, shared_cues)
        verdict = self._adjudicated.get((min(left_idx, right_idx), max(left_idx, right_idx)))
        if verdict is not None:
            # Only reached for pairs the band pre-pass judged ambiguous. The
            # group coherence gates downstream still get their veto.
            compatible = bool(verdict)
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

    def _collect_ambiguous_pairs(
        self,
        articles: Sequence[RawArticle],
        embeddings: NDArray[np.float32],
        prepared: Sequence[_PreparedArticle],
    ) -> List[object]:
        """
        Find the pairs the deterministic signals disagree about.

        Two signals decide a pair: embedding similarity, and headline/entity
        overlap. Where both agree the deterministic answer stands and costs
        nothing. Where they disagree *and* similarity sits in a narrow band
        around the threshold, the current code silently prefers "different
        events" — that is the coin flip worth spending a call on.
        """
        from src.agents.adjudication import AdjudicationPair

        low = self.min_pair_similarity - self.adjudication_band_below
        high = self.min_pair_similarity + self.adjudication_band_above

        scored: List[Tuple[float, object]] = []
        for left in range(len(articles)):
            for right in range(left + 1, len(articles)):
                similarity = float(embeddings[left] @ embeddings[right])
                if not (low <= similarity <= high):
                    continue
                if not self._time_window_ok(prepared[right], [left], prepared):
                    continue

                headline_overlap, entity_overlap = self._pair_overlap(prepared[left], prepared[right])
                shared_headline_tokens = (
                    prepared[left].headline_tokens & prepared[right].headline_tokens
                )
                shared = shared_headline_tokens | (
                    prepared[left].entity_cues & prepared[right].entity_cues
                )
                distinctive_shared = len(shared - _GENERIC_EVENT_CUES)
                shared_cues = (
                    2
                    if distinctive_shared == 1
                    and len(shared) >= 3
                    and headline_overlap >= 0.20
                    else distinctive_shared
                )
                overlap_says_same = self._has_required_overlap(
                    headline_overlap, entity_overlap, shared_cues
                )
                similarity_says_same = similarity >= self.min_pair_similarity
                if overlap_says_same == similarity_says_same:
                    continue

                # Two distinctive *headline* tokens, not shared cues: entity
                # overlap is dominated by generic names on this corpus, so it
                # cannot tell a near-miss from two unrelated Pakistani stories.
                #
                # Measured on the golden day, over the same 120 articles:
                #   no floor                -> 24 pairs, model answered
                #                              "different" to all 24
                #   >= 1 shared headline    -> 51 pairs, mostly sharing only
                #                              the token "pakistan"
                #   >= 2 shared headlines   -> 2 pairs, both real near-misses
                #                              ([iran, sanctions], [kills, two])
                # Anything looser spends the budget confirming what the
                # deterministic gates already had right.
                if len(shared_headline_tokens) < 2:
                    continue

                scored.append(
                    (
                        float(len(shared_headline_tokens)) + headline_overlap,
                        AdjudicationPair(
                            left_index=left,
                            right_index=right,
                            left_source=articles[left].source,
                            left_headline=articles[left].headline or "",
                            right_source=articles[right].source,
                            right_headline=articles[right].headline or "",
                            similarity=similarity,
                            headline_overlap=headline_overlap,
                            entity_overlap=entity_overlap,
                            left_url=str(articles[left].url),
                            right_url=str(articles[right].url),
                        ),
                    )
                )

        # Strongest corroborating evidence first: those are the pairs where
        # the deterministic split is most likely to be the wrong call.
        scored.sort(key=lambda row: -row[0])
        return [pair for _distance, pair in scored[: self.max_adjudication_pairs]]

    def _run_adjudication(
        self,
        articles: Sequence[RawArticle],
        embeddings: NDArray[np.float32],
        prepared: Sequence[_PreparedArticle],
    ) -> None:
        self._adjudicated = {}
        self.last_adjudication = None
        if self.adjudicator is None:
            return

        pairs = self._collect_ambiguous_pairs(articles, embeddings, prepared)
        if not pairs:
            return

        try:
            result = self.adjudicator.adjudicate(pairs)
        except Exception as exc:
            # An adjudication outage must not take the run down: without
            # verdicts the deterministic answer stands, which is today's
            # behaviour.
            logger.warning("Adjudication unavailable, keeping deterministic grouping: %s", exc)
            return

        self._adjudicated = dict(result.verdicts)
        self.last_adjudication = result
        logger.info(
            "Adjudicated %d ambiguous pairs in %d calls: %d merged, %d failed",
            len(pairs),
            int(getattr(result, "calls", 0)),
            int(getattr(result, "merged", 0)),
            int(getattr(result, "failures", 0)),
        )

    def group_articles(self, articles: Sequence[RawArticle]) -> EventGroupingResult:
        if not articles:
            raise ClusteringError("Cannot group an empty article sequence")

        embeddings = self._normalize_embeddings(articles)
        prepared = self._prepare_articles(articles)
        self._run_adjudication(articles, embeddings, prepared)
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

__all__ = [
    # Exceptions
    "ClusteringError",
    # Classes
    "ClusteringResult",
    "EventGroup",
    "EventGroupingResult",
    "EventGroupingService",
    # Functions
    "calculate_centroid",
    "find_representative_article",
    "calculate_intra_cluster_similarity",
    "trusted_article_timestamp",
]
