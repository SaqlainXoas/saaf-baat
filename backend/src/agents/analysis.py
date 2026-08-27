"""
NLP analysis for Saaf Baat: entities, consensus, and triage aggregation.

This module writes no prose. It focuses on transparent signals:
- Named entities mentioned across sources
- Agreement vs partial agreement across sources
- Category + impact labels aggregated from the per-article triage verdicts
  (`agents/triage.py`), which replaced a 390-line keyword file
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

import numpy as np

from src.agents.clustering import calculate_centroid, find_representative_article
from src.db.models import AnalyzedFeed, ExtractedEntity, RawArticle
from src.utils.text import split_sentences

# Labels we keep for MVP (English-only).
DEFAULT_ALLOWED_ENTITY_LABELS = {"PERSON", "ORG", "GPE", "DATE", "MONEY", "EVENT"}



def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def build_snippet(text: str, max_chars: int = 240) -> str:
    """
    Build a short, deterministic snippet for the AnalyzedFeed.summary field.

    MVP goal: fill the product card without LLM summaries.
    """
    clean = _collapse_ws(text)
    if not clean:
        return ""

    # Prefer the first 1–2 sentences if punctuation exists.
    sentences = split_sentences(clean)
    if len(sentences) >= 2:
        snippet = f"{sentences[0]} {sentences[1]}"
    else:
        snippet = clean

    if len(snippet) <= max_chars:
        return snippet

    # Take the most whole sentences that fit. This snippet is what a detail
    # page shows when the analysis is unavailable, and a wire lede cut
    # mid-clause reads as a truncation bug rather than as an excerpt.
    whole = ""
    for sentence in sentences:
        candidate = f"{whole} {sentence}".strip()
        if len(candidate) > max_chars:
            break
        whole = candidate
    if whole:
        return whole

    # Even the first sentence is too long. Fall back to the last clause break
    # rather than stopping mid-clause: "...cooking oil producers…" reads as an
    # excerpt, "...engaged in…" reads as a bug.
    truncated = snippet[: max_chars + 1]
    clause = max(truncated.rfind(mark) for mark in (",", ";", ":", "—", "–"))
    if clause >= max_chars // 2:
        return f"{truncated[:clause].rstrip()}…"
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    truncated = truncated.rstrip(" .,:;")
    return f"{truncated}…"


# Strip leading articles so "The IMF" and "IMF" share a key across sources.
_LEADING_ARTICLES = ("the ", "a ", "an ")

# Qualifiers to strip from MONEY entities so "$16.4bn" and "approximately $16.4bn" merge.
_MONEY_QUALIFIERS = ("approximately ", "about ", "around ", "nearly ", "over ", "almost ", "up to ")


def _entity_key(text: str, label: str) -> Tuple[str, str]:
    normalized = _collapse_ws(text).lower()
    for prefix in _LEADING_ARTICLES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    if label == "MONEY":
        for qual in _MONEY_QUALIFIERS:
            if normalized.startswith(qual):
                normalized = normalized[len(qual):]
                break
        normalized = normalized.lstrip("$£€¥")
    return (normalized, label)


def _upper_score(text: str) -> int:
    # Prefer "Pakistan" over "pakistan", "IMF" over "Imf", etc.
    return sum(1 for c in text if c.isupper())


@dataclass(frozen=True)
class ConsensusResult:
    confirmed_facts: List[ExtractedEntity]
    debated_claims: List[ExtractedEntity]



class EntityExtractor:
    """Extract named entities using a spaCy pipeline.

    For production we default to loading `en_core_web_sm`. For tests we allow
    injecting an `nlp` object to avoid external downloads.
    """

    def __init__(
        self,
        nlp=None,
        model_name: str = "en_core_web_sm",
        allowed_labels: Optional[Iterable[str]] = None,
    ):
        self.allowed_labels = set(allowed_labels or DEFAULT_ALLOWED_ENTITY_LABELS)

        if nlp is not None:
            self.nlp = nlp
            return

        try:
            import spacy  # type: ignore
        except ImportError as e:
            raise RuntimeError("spaCy is required for entity extraction") from e

        try:
            self.nlp = spacy.load(model_name)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load spaCy model '{model_name}'. Install it (e.g. "
                f"`python -m spacy download {model_name}`)."
            ) from e

    def extract(self, text: str) -> List[ExtractedEntity]:
        # Normalize whitespace before NLP so weird tokenizers don't produce space tokens,
        # and so patterns match consistently across sources.
        doc = self.nlp(_collapse_ws(text or ""))

        best_by_key: Dict[Tuple[str, str], str] = {}

        for ent in getattr(doc, "ents", []):
            label = getattr(ent, "label_", "")
            if label not in self.allowed_labels:
                continue

            display = _collapse_ws(getattr(ent, "text", ""))
            if not display:
                continue

            key = _entity_key(display, label)
            prev = best_by_key.get(key)
            if prev is None or _upper_score(display) > _upper_score(prev):
                best_by_key[key] = display

        # Emit in stable order for predictable tests/UI.
        entities: List[ExtractedEntity] = []
        for (_norm, label), display in sorted(best_by_key.items(), key=lambda x: (x[0][1], x[1].lower())):
            entities.append(ExtractedEntity(text=display, type=label, sources=1))
        return entities


class ConsensusDetector:
    """Detect agreement across sources using entity overlap."""

    def __init__(self, min_agreement_ratio: float = 1.0):
        if min_agreement_ratio <= 0 or min_agreement_ratio > 1:
            raise ValueError("min_agreement_ratio must be in (0, 1]")
        self.min_agreement_ratio = min_agreement_ratio

    def analyze(self, entities_by_article: Sequence[Sequence[ExtractedEntity]]) -> ConsensusResult:
        n_articles = len(entities_by_article)
        if n_articles == 0:
            return ConsensusResult(confirmed_facts=[], debated_claims=[])

        threshold = int(math.ceil(self.min_agreement_ratio * n_articles))

        doc_counts: Dict[Tuple[str, str], int] = {}
        best_display: Dict[Tuple[str, str], str] = {}

        for per_article in entities_by_article:
            seen_keys = set()
            for ent in per_article:
                label = ent.type  # may be Enum or str; pydantic config uses values
                display = _collapse_ws(ent.text)
                key = _entity_key(display, str(label))
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                doc_counts[key] = doc_counts.get(key, 0) + 1

                prev = best_display.get(key)
                if prev is None or _upper_score(display) > _upper_score(prev):
                    best_display[key] = display

        confirmed: List[ExtractedEntity] = []
        debated: List[ExtractedEntity] = []

        for key, count in doc_counts.items():
            _norm, label = key
            display = best_display[key]
            item = ExtractedEntity(text=display, type=label, sources=count)
            if count >= threshold:
                confirmed.append(item)
            else:
                debated.append(item)

        def _sort_key(e: ExtractedEntity):
            return (-int(e.sources), str(e.type), e.text.lower())

        confirmed.sort(key=_sort_key)
        debated.sort(key=_sort_key)

        return ConsensusResult(confirmed_facts=confirmed, debated_claims=debated)


# ---------------------------------------------------------------------------
# Triage aggregation
# ---------------------------------------------------------------------------

# Most-relevant wins when a cluster's members disagree: a story one outlet
# frames locally and another nationally is a national story.
_PK_RELEVANCE_RANK = {
    "national": 3,
    "local": 2,
    "foreign_with_pk_effect": 1,
    "foreign": 0,
}


@dataclass(frozen=True)
class ClusterTriage:
    """What the per-article triage verdicts say about a cluster as a whole."""

    category: str
    impact_labels: List[str]
    confidence: float
    story_type: Optional[str]
    pk_relevance: Optional[str]
    verdict_count: int

    @property
    def has_verdicts(self) -> bool:
        return self.verdict_count > 0

    def as_metadata(self) -> Dict[str, object]:
        return {
            "category": self.category,
            "impact_labels": list(self.impact_labels),
            "story_type": self.story_type,
            "pk_relevance": self.pk_relevance,
            "confidence": round(float(self.confidence), 3),
            "verdict_count": int(self.verdict_count),
        }


def article_triage(article: RawArticle) -> Optional[Dict[str, object]]:
    """Read the triage verdict persisted on an article, if it has one."""
    verdict = (article.metadata or {}).get("triage")
    return verdict if isinstance(verdict, dict) else None


def aggregate_triage(
    articles: Sequence[RawArticle],
    representative: Optional[RawArticle] = None,
) -> ClusterTriage:
    """
    Combine per-article verdicts into one verdict for the cluster.

    A cluster with no verdicts at all is a real state, not an error: it means
    triage was unavailable or skipped these articles. It returns `other` with
    zero confidence and no story_type, and the hard gates drop it rather than
    guessing.
    """
    verdicts = [(a, article_triage(a)) for a in articles]
    verdicts = [(a, v) for a, v in verdicts if v]
    if not verdicts:
        return ClusterTriage(
            category="other",
            impact_labels=[],
            confidence=0.0,
            story_type=None,
            pk_relevance=None,
            verdict_count=0,
        )

    representative_verdict = article_triage(representative) if representative is not None else None

    category_weight: Dict[str, float] = {}
    label_weight: Dict[str, float] = {}
    confidences: List[float] = []
    story_types: set[str] = set()
    best_relevance: Optional[str] = None

    for _article, verdict in verdicts:
        confidence = float(verdict.get("confidence") or 0.0)
        confidences.append(confidence)

        category = str(verdict.get("category") or "other")
        # A floor of 0.1 keeps a unanimous set of low-confidence verdicts from
        # collapsing to a zero-weight tie.
        category_weight[category] = category_weight.get(category, 0.0) + max(confidence, 0.1)

        for label in verdict.get("impact_labels") or []:
            label_weight[str(label)] = label_weight.get(str(label), 0.0) + max(confidence, 0.1)

        story_type = verdict.get("story_type")
        if story_type:
            story_types.add(str(story_type))

        relevance = verdict.get("pk_relevance")
        if relevance and (
            best_relevance is None
            or _PK_RELEVANCE_RANK.get(str(relevance), -1) > _PK_RELEVANCE_RANK.get(best_relevance, -1)
        ):
            best_relevance = str(relevance)

    top_weight = max(category_weight.values())
    tied = sorted(cat for cat, weight in category_weight.items() if weight >= top_weight - 1e-9)
    if len(tied) > 1 and representative_verdict:
        # The representative is the article the card will be written from, so
        # its reading breaks the tie.
        rep_category = str(representative_verdict.get("category") or "")
        category = rep_category if rep_category in tied else tied[0]
    else:
        category = tied[0]

    impact_labels = [
        label
        for label, _weight in sorted(label_weight.items(), key=lambda row: (-row[1], row[0]))
    ][:3]

    # Covered as hard news anywhere means hard news: one outlet running colour
    # alongside does not make the development a feature.
    story_type = "hard_news" if "hard_news" in story_types else (
        sorted(story_types)[0] if story_types else None
    )

    return ClusterTriage(
        category=category,
        impact_labels=impact_labels,
        confidence=float(sum(confidences) / len(confidences)),
        story_type=story_type,
        pk_relevance=best_relevance,
        verdict_count=len(verdicts),
    )


class AnalysisService:
    """Build an AnalyzedFeed record from a cluster of RawArticles."""

    def __init__(
        self,
        entity_extractor: EntityExtractor,
        consensus_detector: ConsensusDetector,
        headline_source_priority: Optional[List[str]] = None,
        max_confirmed_facts: int = 8,
        max_debated_claims: int = 12,
    ):
        self.entity_extractor = entity_extractor
        self.consensus_detector = consensus_detector
        if max_confirmed_facts <= 0:
            raise ValueError("max_confirmed_facts must be positive")
        if max_debated_claims <= 0:
            raise ValueError("max_debated_claims must be positive")
        self.max_confirmed_facts = max_confirmed_facts
        self.max_debated_claims = max_debated_claims
        self.headline_source_priority = headline_source_priority or [
            "dawn", "tribune", "thenews", "geo", "ary"
        ]

    @staticmethod
    def _limit_entities(entities: Sequence[ExtractedEntity], limit: int) -> List[ExtractedEntity]:
        ranked = sorted(entities, key=lambda e: (-int(e.sources), str(e.type), e.text.lower()))
        return list(ranked[:limit])

    def _choose_headline(self, articles: Sequence[RawArticle]) -> str:
        by_source: Dict[str, List[RawArticle]] = {}
        for a in articles:
            by_source.setdefault(a.source, []).append(a)

        for src in self.headline_source_priority:
            if src in by_source:
                # Prefer the longest headline from the preferred source.
                return sorted(by_source[src], key=lambda a: (-len(a.headline or ""), a.url))[0].headline

        # Fallback: longest headline overall.
        return sorted(articles, key=lambda a: (-len(a.headline or ""), a.url))[0].headline

    def _choose_snippet_text(self, articles: Sequence[RawArticle]) -> str:
        # Use the same source-priority approach as headline selection.
        by_source: Dict[str, List[RawArticle]] = {}
        for a in articles:
            by_source.setdefault(a.source, []).append(a)

        for src in self.headline_source_priority:
            if src in by_source:
                chosen = sorted(by_source[src], key=lambda a: (-len(a.main_text or ""), a.url))[0]
                return chosen.main_text or ""

        # Fallback: longest body overall.
        return sorted(articles, key=lambda a: (-len(a.main_text or ""), a.url))[0].main_text or ""

    @staticmethod
    def _normalized_embedding_matrix(articles: Sequence[RawArticle]) -> Optional[np.ndarray]:
        vectors: List[np.ndarray] = []
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
            vectors.append(vec / norm)

        if not vectors:
            return None
        return np.vstack(vectors)

    def _choose_representative_article(self, articles: Sequence[RawArticle]) -> RawArticle:
        embeddings = self._normalized_embedding_matrix(articles)
        if embeddings is None:
            return sorted(
                articles,
                key=lambda a: (
                    self.headline_source_priority.index(a.source)
                    if a.source in self.headline_source_priority else len(self.headline_source_priority),
                    -len(a.headline or ""),
                    a.url,
                ),
            )[0]

        centroid = calculate_centroid(embeddings)
        representative_index = find_representative_article(embeddings, centroid)
        return articles[representative_index]

    def choose_representative_article(self, articles: Sequence[RawArticle]) -> RawArticle:
        return self._choose_representative_article(articles)

    def analyze_cluster(self, cluster_id: UUID, articles: Sequence[RawArticle]) -> AnalyzedFeed:
        if not articles:
            raise ValueError("Cannot analyze empty cluster")

        representative = self._choose_representative_article(articles)
        headline = representative.headline or self._choose_headline(articles)
        summary = build_snippet(representative.main_text or self._choose_snippet_text(articles))

        triage = aggregate_triage(articles, representative)

        # Entity extraction + consensus uses per-article entities.
        entities_by_article = [self.entity_extractor.extract(a.main_text or "") for a in articles]
        consensus = self.consensus_detector.analyze(entities_by_article)
        confirmed_facts = self._limit_entities(consensus.confirmed_facts, self.max_confirmed_facts)
        debated_claims = self._limit_entities(consensus.debated_claims, self.max_debated_claims)

        source_attribution: Dict[str, int] = {}
        for a in articles:
            source_attribution[a.source] = source_attribution.get(a.source, 0) + 1

        entity_counts: Dict[str, int] = {}
        for ent in confirmed_facts + debated_claims:
            entity_counts[ent.text] = int(ent.sources)

        return AnalyzedFeed(
            cluster_id=cluster_id,
            headline=headline,
            summary=summary or None,
            category=triage.category,
            confirmed_facts=confirmed_facts,
            debated_claims=debated_claims,
            impact_labels=triage.impact_labels,
            source_attribution=source_attribution,
            entity_counts=entity_counts,
            classification_confidence=triage.confidence,
            metadata={"triage": triage.as_metadata()},
        )


__all__ = [
    "AnalysisService",
    "ClusterTriage",
    "ConsensusDetector",
    "ConsensusResult",
    "EntityExtractor",
    "aggregate_triage",
    "article_triage",
]
