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

import yaml

from src.db.models import AnalyzedFeed, ExtractedEntity, RawArticle


# Labels we keep for MVP (English-only).
DEFAULT_ALLOWED_ENTITY_LABELS = {"PERSON", "ORG", "GPE", "DATE", "MONEY", "EVENT"}


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _entity_key(text: str, label: str) -> Tuple[str, str]:
    # Key is case-insensitive but type-sensitive.
    return (_collapse_ws(text).lower(), label)


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

    def __init__(self, rules: dict):
        self.rules = rules or {}
        self.categories = (self.rules.get("categories") or {}).copy()
        self.impact_labels = (self.rules.get("impact_labels") or {}).copy()
        self.config = (self.rules.get("classification_config") or {}).copy()

        self.max_impact = int(self.config.get("max_impact_labels_per_article", 3))

    @classmethod
    def from_yaml(cls, path: Path) -> "RuleBasedClassifier":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(rules=data)

    def classify_text(self, text: str) -> ClassificationResult:
        text_l = (text or "").lower()

        cat_scores: Dict[str, float] = {}
        for cat, spec in self.categories.items():
            keywords = spec.get("keywords") or []
            weight = float(spec.get("weight", 1.0))
            score = sum(1 for kw in keywords if kw and str(kw).lower() in text_l) * weight
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

        impact_scores: List[Tuple[str, float]] = []
        for label, spec in self.impact_labels.items():
            keywords = spec.get("keywords") or []
            weight = float(spec.get("weight", 1.0))
            score = sum(1 for kw in keywords if kw and str(kw).lower() in text_l) * weight
            if score > 0:
                impact_scores.append((label, score))

        impact_scores.sort(key=lambda x: (-x[1], x[0]))
        impacts = [lbl for (lbl, _s) in impact_scores[: self.max_impact]]

        return ClassificationResult(category=top_cat, impact_labels=impacts, confidence=confidence)


class AnalysisService:
    """Build an AnalyzedFeed record from a cluster of RawArticles."""

    def __init__(
        self,
        entity_extractor: EntityExtractor,
        consensus_detector: ConsensusDetector,
        classifier: RuleBasedClassifier,
        headline_source_priority: Optional[List[str]] = None,
    ):
        self.entity_extractor = entity_extractor
        self.consensus_detector = consensus_detector
        self.classifier = classifier
        self.headline_source_priority = headline_source_priority or ["dawn", "tribune", "geo"]

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

    def analyze_cluster(self, cluster_id: UUID, articles: Sequence[RawArticle]) -> AnalyzedFeed:
        if not articles:
            raise ValueError("Cannot analyze empty cluster")

        headline = self._choose_headline(articles)

        # Classification uses all headlines + short snippets for signal.
        cluster_text = " ".join(
            [f"{a.headline}. {a.main_text[:500]}" for a in articles if a.headline and a.main_text]
        )
        cls = self.classifier.classify_text(cluster_text)

        # Entity extraction + consensus uses per-article entities.
        entities_by_article = [self.entity_extractor.extract(a.main_text or "") for a in articles]
        consensus = self.consensus_detector.analyze(entities_by_article)

        source_attribution: Dict[str, int] = {}
        for a in articles:
            source_attribution[a.source] = source_attribution.get(a.source, 0) + 1

        entity_counts: Dict[str, int] = {}
        for ent in consensus.confirmed_facts + consensus.debated_claims:
            entity_counts[ent.text] = int(ent.sources)

        return AnalyzedFeed(
            cluster_id=cluster_id,
            headline=headline,
            summary=None,
            category=cls.category,
            confirmed_facts=consensus.confirmed_facts,
            debated_claims=consensus.debated_claims,
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
