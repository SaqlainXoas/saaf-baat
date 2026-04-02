"""
NLP analysis for Saaf Baat: entities, consensus, and rule-based classification.

This module intentionally avoids any LLM-generated summaries. It focuses on
transparent signals:
- Named entities mentioned across sources
- Agreement vs partial agreement across sources
- Keyword-based category + impact labels from YAML rules
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

import numpy as np
import yaml

from src.agents.clustering import calculate_centroid, find_representative_article
from src.db.models import AnalyzedFeed, ExtractedEntity, RawArticle


# Labels we keep for MVP (English-only).
DEFAULT_ALLOWED_ENTITY_LABELS = {"PERSON", "ORG", "GPE", "DATE", "MONEY", "EVENT"}

# When keyword matching produces zero impact hits, derive a default badge from
# the story category.  Ensures every categorised card shows at least one signal.
_CATEGORY_IMPACT_FALLBACK: Dict[str, str] = {
    "economy": "💳 WALLET",
    "politics": "🏛️ GOVERNANCE",
    "security": "🛡️ SAFETY",
    "city": "🚦 COMMUTE",
    "education": "🏛️ GOVERNANCE",
    "health": "🛡️ SAFETY",
    "international": "🏛️ GOVERNANCE",
}


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def build_snippet(text: str, max_chars: int = 240) -> str:
    """
    Build a short, deterministic snippet for the AnalyzedFeed.summary field.

    MVP goal: fill the product card without LLM summaries.
    """
    clean = _collapse_ws(text)
    if not clean:
        return ""

    # Prefer the first 1–2 sentences if punctuation exists.
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(clean) if s.strip()]
    if len(sentences) >= 2:
        snippet = f"{sentences[0]} {sentences[1]}"
    else:
        snippet = clean

    if len(snippet) <= max_chars:
        return snippet

    # Truncate at a word boundary and add ellipsis.
    truncated = snippet[: max_chars + 1]
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


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    impact_labels: List[str]
    confidence: float


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


class RuleBasedClassifier:
    """Transparent keyword-based classifier (YAML-driven)."""

    _CATEGORY_HEADLINE_WEIGHT = 2.0
    _IMPACT_HEADLINE_WEIGHT = 1.5

    def __init__(self, rules: dict):
        self.rules = rules or {}
        self.categories = (self.rules.get("categories") or {}).copy()
        self.impact_labels = (self.rules.get("impact_labels") or {}).copy()
        self.config = (self.rules.get("classification_config") or {}).copy()

        self.max_impact = int(self.config.get("max_impact_labels_per_article", 3))

        # Pre-compile word-boundary patterns so substring false-positives are
        # avoided (e.g. "signal" inside "signals", "power" inside "powers").
        self._cat_patterns: Dict[str, Tuple[List[re.Pattern], float]] = {}
        for cat, spec in self.categories.items():
            kws = spec.get("keywords") or []
            w = float(spec.get("weight", 1.0))
            self._cat_patterns[cat] = (
                [re.compile(r"\b" + re.escape(str(k).lower()) + r"\b") for k in kws if k],
                w,
            )

        self._impact_patterns: Dict[str, Tuple[List[re.Pattern], float]] = {}
        for label, spec in self.impact_labels.items():
            kws = spec.get("keywords") or []
            w = float(spec.get("weight", 1.0))
            self._impact_patterns[label] = (
                [re.compile(r"\b" + re.escape(str(k).lower()) + r"\b") for k in kws if k],
                w,
            )

    @classmethod
    def from_yaml(cls, path: Path) -> "RuleBasedClassifier":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(rules=data)

    @staticmethod
    def _match_count(patterns: Sequence[re.Pattern], text: str) -> int:
        if not text:
            return 0
        return sum(1 for pattern in patterns if pattern.search(text))

    def classify_parts(self, headline: str, text: str) -> ClassificationResult:
        headline_l = (headline or "").lower()
        text_l = (text or "").lower()

        cat_scores: Dict[str, float] = {}
        for cat, (patterns, weight) in self._cat_patterns.items():
            headline_hits = self._match_count(patterns, headline_l)
            body_hits = self._match_count(patterns, text_l)
            score = (
                headline_hits * self._CATEGORY_HEADLINE_WEIGHT
                + body_hits
            ) * weight
            if score > 0:
                cat_scores[cat] = score

        if not cat_scores:
            top_cat = "other"
            top_score = 0.0
        else:
            # Deterministic tie-break: higher score then name.
            top_cat, top_score = sorted(cat_scores.items(), key=lambda x: (-x[1], x[0]))[0]

        # Confidence is a simple bounded function of the score.
        confidence = 0.0 if top_score <= 0 else min(1.0, float(top_score) / 5.0)

        min_conf = float(self.config.get("min_confidence", 0.0))
        if confidence < min_conf:
            top_cat = "other"
            confidence = 0.0

        impact_scores: List[Tuple[str, float]] = []
        for label, (patterns, weight) in self._impact_patterns.items():
            headline_hits = self._match_count(patterns, headline_l)
            body_hits = self._match_count(patterns, text_l)
            score = (
                headline_hits * self._IMPACT_HEADLINE_WEIGHT
                + body_hits
            ) * weight
            if score > 0:
                impact_scores.append((label, score))

        impact_scores.sort(key=lambda x: (-x[1], x[0]))
        impacts = [lbl for (lbl, _s) in impact_scores[: self.max_impact]]

        # Fallback: derive one impact badge from the category so every
        # categorised card shows at least one life-impact signal.
        if not impacts and top_cat in _CATEGORY_IMPACT_FALLBACK:
            impacts = [_CATEGORY_IMPACT_FALLBACK[top_cat]]

        return ClassificationResult(category=top_cat, impact_labels=impacts, confidence=confidence)

    def classify_text(self, text: str) -> ClassificationResult:
        return self.classify_parts("", text)


class AnalysisService:
    """Build an AnalyzedFeed record from a cluster of RawArticles."""

    def __init__(
        self,
        entity_extractor: EntityExtractor,
        consensus_detector: ConsensusDetector,
        classifier: RuleBasedClassifier,
        headline_source_priority: Optional[List[str]] = None,
        max_confirmed_facts: int = 8,
        max_debated_claims: int = 12,
    ):
        self.entity_extractor = entity_extractor
        self.consensus_detector = consensus_detector
        self.classifier = classifier
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

        other_headlines = " ".join(
            [a.headline for a in articles if a.id != representative.id and a.headline]
        )
        classification_text = f"{representative.main_text} {other_headlines}"
        cls = self.classifier.classify_parts(representative.headline, classification_text)

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
            category=cls.category,
            confirmed_facts=confirmed_facts,
            debated_claims=debated_claims,
            impact_labels=cls.impact_labels,
            source_attribution=source_attribution,
            entity_counts=entity_counts,
            classification_confidence=cls.confidence,
        )


__all__ = [
    "ConsensusResult",
    "ClassificationResult",
    "EntityExtractor",
    "ConsensusDetector",
    "RuleBasedClassifier",
    "AnalysisService",
]
