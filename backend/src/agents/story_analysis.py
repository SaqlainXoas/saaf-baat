from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.agents.clustering import trusted_article_timestamp
from src.db.models import RawArticle
from src.utils.text import split_sentences

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "config" / "story_analysis_prompt.md"
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{2,}\b")
_PROPER_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Pakistani reporting writes money as `Rs22bn`, `Rs 22 billion`, `Rs483,036` and
# `30 million rupees`, often in the same paragraph. The old pattern required a
# `\b` immediately before the first digit, which a glued currency prefix
# destroys (`Rs22bn` -> no match at all) and which a comma-grouped figure
# survives only from its last group (`Rs483,036` -> `036`, so `Rs912,036`
# validated it). The lookbehind anchors the whole match instead, and the
# currency prefix is part of the match rather than a boundary in the middle of
# it.
# `\d[\d,]*` swallowed any run of digits and commas, so "1,2,3" became the
# single value 123 and "August 5,2026" became 52026 - a false-accept surface in
# both directions. Commas are now only a thousands separator.
_NUMBER_RE = re.compile(
    r"(?i)(?<![\w.])(?:(?:rs|pkr|usd)\.?\s*)?"
    r"(?:\d{1,3}(?:,\d{3})+(?![\d,])|\d+)(?:\.\d+)?"
    r"(?:\s*(?:billion|million|percent|per\s+cent|crore|lakh|%|(?:bn|m)\b))?"
)
# A source writing a period as `2007-09` supports an output that expands it to
# "2007 and 2009". Expansion is applied to the SOURCE side only - an output
# range must still find both of its endpoints in the reporting.
_YEAR_RANGE_RE = re.compile(r"(?<!\d)(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})(?!\d)")
# A shared name is not a shared story. Replaying the live window showed junk
# context sitting at 0.70-0.89 cosine against the primary reports while
# genuinely on-topic context sat well above; unrelated same-domain events on
# this corpus embed around 0.82 (the same measurement that puts
# `event_group_min_pair_similarity` at 0.92). This floor is deliberately below
# the grouping threshold - context is meant to be adjacent, not the same event.
_RELATED_MIN_SIMILARITY = 0.86
# Months are matched in both their written and abbreviated forms and reduced to
# a three-letter key, so "Sept 16" in the reporting supports "September 16" in
# the output. Dawn writes "Sept 16" and the model wrote "September 16"; the
# figure check treated that as a fabricated date and discarded the claim.
# Weekdays stay full-word: `sat`, `mon` and `wed` are ordinary English.
_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_DATE_WORD_RE = re.compile(
    r"(?i)\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec|"
    + "|".join(month for month in _MONTHS if month != "may")
    + r")\.?\b"
)
# "may" is the one month that is also an everyday English word, and treating it
# as a date discarded a live analysis over "the party may expand its protest".
# It counts only when it is shaped like a date.
_MAY_DATE_RE = re.compile(r"(?i)(?:\b\d{1,2}(?:st|nd|rd|th)?\s+may\b|\bmay\s+\d{1,4}\b)")

_GENERIC_ANCHORS = {
    "pakistan",
    "pakistani",
    "islamabad",
    "karachi",
    "lahore",
    "government",
    "health",
    "minister",
    "ministry",
    "official",
    "officials",
    "president",
    "prime",
    "pm",
    "court",
    "police",
    "hospital",
    "report",
    "reports",
    "today",
    "national",
    "federal",
    "province",
    "provincial",
    "security",
    "senate",
    "assembly",
    "committee",
    # Added 2026-08-27. A replay of the live 449-article window admitted junk
    # on 6 of 8 cards through exactly these words: `economy` matched an
    # Uzbekistan/SCO piece to the gas-subsidy card, `supreme` matched four
    # Imran Khan hospital stories to the ghee penalty, `chief` matched a
    # Punjab police purge to the Foreign Office card.
    "after",
    "against",
    "balochistan",
    "chief",
    "claims",
    "economy",
    "finding",
    "findings",
    "foreign",
    "orders",
    "price",
    "prices",
    "punjab",
    "sindh",
    "supreme",
    # The editorial category vocabulary. A subject area is never a story
    # identity, and these words appear capitalised in ordinary headlines
    # ("fire safety audits", "Politics desk") as readily as in a tag list.
    "city",
    "education",
    "entertainment",
    "international",
    "politics",
    "safety",
    "sports",
    "technology",
}
_TOKEN_STOPWORDS = _GENERIC_ANCHORS | {
    "about",
    "after",
    "against",
    "amid",
    "and",
    "from",
    "into",
    "over",
    "says",
    "that",
    "their",
    "the",
    "this",
    "with",
}
_KNOWN_PUBLISHERS = {
    "app": ("app", "associated press of pakistan"),
    "ary": ("ary", "ary news"),
    "brecorder": ("business recorder", "brecorder"),
    "dawn": ("dawn",),
    "geo": ("geo", "geo news"),
    "nation": ("nation", "the nation"),
    "thenews": ("the news", "thenews"),
    "tribune": ("tribune", "express tribune"),
}
_PUBLISHER_CUE = (
    r"(?:reports?|reported|reporting|says?|said|writes?|wrote|notes?|noted|"
    r"carry|carries|carried|adds?|added|quotes?|quoted|describes?|described|"
    r"attributes?|attributed|confirms?|confirmed)"
)
_FORBIDDEN_CONCLUSIONS = (
    "corrupt",
    "corruption",
    "lied",
    "lying",
    "cover-up",
    "cover up",
    "covered up",
    "ignored",
    "never happened",
    "never occurred",
)
# Never a pass on their own - see _question_is_specific. `safety` and `record`
# were removed outright: `safety` is what let the prompt's own canonical BAD
# question through, and `record` is already the source-independence signal.
# An accusation someone else made, reported as theirs. The prompt requires
# accusatory claims to be attributed, so an attributed sentence cannot be the
# model inferring guilt on its own account.
_ATTRIBUTION_CUE_RE = re.compile(
    r"\b(?:alleged|allegedly|allegations?|accus\w+|claim\w*|said|says|"
    r"according to|reports?|reported|criticis\w+|criticiz\w+|denied|denies|"
    r"denying|argued|argues|told|testified|complain\w+|opposition)\b"
)
_QUESTION_SPECIFIC_TERMS = {
    "audit",
    "budget",
    "closed",
    "delay",
    "exempt",
    "funding",
    "independent",
    "inspection",
    "protected",
    "obstruction",
    "previous",
    # Added after a live rejection: "What specific metrics or income thresholds
    # will define these vulnerable segments?" carried no figure and no name
    # outside the story's own subject, so it read as generic. Two of these are
    # still required, and the canonical BAD question contains none of them.
    "criteria",
    "deadline",
    "eligibility",
    "metric",
    "metrics",
    "threshold",
    "thresholds",
    "timeline",
    "tariff",
    "verification",
    "violations",
    "warning",
    "warnings",
}


class QuestionBasis(str, Enum):
    DOCUMENTED_WARNING = "documented_warning"
    RESOURCES_VS_OUTCOME = "resources_vs_outcome"
    SOURCE_INDEPENDENCE = "source_independence"
    RESPONSIBILITY_GAP = "responsibility_gap"
    MISSING_PUBLIC_INFORMATION = "missing_public_information"
    NONE = "none"


class StoryAnalysisClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=4, max_length=600)
    supporting_article_ids: List[str] = Field(min_length=1, max_length=12)

    @field_validator("supporting_article_ids")
    @classmethod
    def _dedupe_ids(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


class StoryAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: str = Field(
        min_length=40,
        max_length=1800,
        description=(
            "Factual synthesis. If every cited claim comes from one publisher, "
            "name that publisher explicitly in the first sentence."
        ),
    )
    question: Optional[str] = Field(default=None, max_length=700)
    question_basis: QuestionBasis = QuestionBasis.NONE
    claims: List[StoryAnalysisClaim] = Field(min_length=1, max_length=12)
    question_supporting_article_ids: List[str] = Field(default_factory=list, max_length=12)

    @field_validator("analysis")
    @classmethod
    def _clean_analysis(cls, value: str) -> str:
        return _normalize_ws(value)

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: Optional[str]) -> Optional[str]:
        clean = _normalize_ws(value or "")
        return clean or None

    @field_validator("question_supporting_article_ids")
    @classmethod
    def _clean_question_ids(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @model_validator(mode="after")
    def _question_contract(self) -> "StoryAnalysisResponse":
        if self.question is None:
            if self.question_basis != QuestionBasis.NONE:
                raise ValueError("question_basis must be none when question is null")
            if self.question_supporting_article_ids:
                raise ValueError("question support must be empty when question is null")
        elif self.question_basis == QuestionBasis.NONE:
            raise ValueError("question_basis cannot be none when question is present")
        return self


class StoryAnalysisError(RuntimeError):
    def __init__(self, message: str, *, calls: int = 0):
        super().__init__(message)
        self.calls = int(calls)


class StoryAnalysisValidationError(StoryAnalysisError):
    pass


@dataclass(frozen=True)
class StoryAnalysisArticle:
    article_id: str
    role: str
    publisher: str
    url: str
    headline: str
    publish_time: Optional[str]
    body_status: str
    content: str

    @classmethod
    def from_raw(cls, article: RawArticle, *, role: str, content_limit: int) -> "StoryAnalysisArticle":
        metadata = dict(article.metadata or {})
        body_status = str(metadata.get("body_status") or "").strip().lower()
        if body_status not in {"full", "summary", "headline_only"}:
            body_status = "full" if len(article.main_text or "") >= 800 else "summary"
        content = _normalize_ws(article.main_text or article.headline)
        if content_limit <= 0:
            # A budget of zero means "no room left", not "no limit". The old
            # test emitted the article in full at exactly the point the budget
            # ran out. The headline still reaches the prompt.
            content = ""
        elif len(content) > content_limit:
            content = content[: content_limit - 1].rstrip() + "…"
        publish_time = article.publish_date.isoformat() if article.publish_date else None
        return cls(
            article_id=str(article.id),
            role=role,
            publisher=article.source,
            url=article.url,
            headline=_normalize_ws(article.headline),
            publish_time=publish_time,
            body_status=body_status,
            content=content,
        )

    def evidence_text(self) -> str:
        return _normalize_ws(f"{self.headline}. {self.content}")

    def to_prompt_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "role": self.role,
            "publisher": self.publisher,
            "url": self.url,
            "headline": self.headline,
            "article_publish_time_not_event_date": self.publish_time,
            "body_status": self.body_status,
            "content": self.content,
        }


@dataclass(frozen=True)
class StoryAnalysisInput:
    cluster_id: str
    selected_headline: str
    articles: tuple[StoryAnalysisArticle, ...]

    @property
    def allowed_article_ids(self) -> set[str]:
        return {article.article_id for article in self.articles}

    @property
    def primary_articles(self) -> tuple[StoryAnalysisArticle, ...]:
        return tuple(article for article in self.articles if article.role == "primary_event")

    @property
    def related_articles(self) -> tuple[StoryAnalysisArticle, ...]:
        return tuple(article for article in self.articles if article.role == "related_current_context")


@dataclass(frozen=True)
class ValidatedStoryAnalysis:
    analysis: str
    question: Optional[str]
    question_basis: str
    claims: tuple[Dict[str, Any], ...]
    question_supporting_article_ids: tuple[str, ...]
    related_article_ids: tuple[str, ...]
    status: str
    validation_errors: tuple[str, ...] = ()
    # The question the model wrote, when validation dropped it. Kept so a
    # rejection can be explained from the DB instead of by re-running Gemini.
    # Nothing renders it: both API routes strip it before the DTO.
    rejected_question: Optional[str] = None
    rejected_question_basis: Optional[str] = None

    def to_metadata(self, *, model: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "analysis": self.analysis,
            "question": self.question,
            "question_basis": self.question_basis,
            "claims": [dict(claim) for claim in self.claims],
            "question_supporting_article_ids": list(self.question_supporting_article_ids),
            "related_article_ids": list(self.related_article_ids),
            "model": model,
            "status": self.status,
            "validation_errors": list(self.validation_errors),
        }
        if self.rejected_question:
            payload["rejected"] = {
                "question": self.rejected_question,
                "question_basis": self.rejected_question_basis,
            }
        return payload


@lru_cache(maxsize=1)
def load_story_analysis_system_prompt() -> str:
    text = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    marker = "## Prompt"
    return text.split(marker, 1)[1].strip() if marker in text else text


def select_primary_articles(
    articles: Sequence[RawArticle], *, max_articles: int = 12, max_per_publisher: int = 2
) -> List[RawArticle]:
    """Pick the event's reports, publisher breadth first.

    Sorting by recency under a per-publisher cap is not the same as
    prioritising diversity: with 7 publishers and 12 slots it gave six
    publishers two each and dropped the seventh publisher's only report
    because it was the oldest. Every publisher gets its best report before any
    publisher gets a second.
    """
    ordered = sorted(
        articles,
        key=lambda article: (
            -trusted_article_timestamp(article).timestamp(),
            article.source,
            article.url,
        ),
    )
    by_publisher: Dict[str, List[RawArticle]] = {}
    for article in ordered:
        by_publisher.setdefault(article.source, []).append(article)

    selected: List[RawArticle] = []
    for rank in range(max(1, int(max_per_publisher))):
        for publisher in sorted(by_publisher):
            if len(selected) >= max_articles:
                rank = int(max_per_publisher)
                break
            bucket = by_publisher[publisher]
            if rank < len(bucket):
                selected.append(bucket[rank])
    # Round-robin decides *which* reports; the prompt still reads newest first.
    return sorted(
        selected[:max_articles],
        key=lambda article: (
            -trusted_article_timestamp(article).timestamp(),
            article.source,
            article.url,
        ),
    )


def find_related_articles(
    primary_articles: Sequence[RawArticle],
    current_articles: Sequence[RawArticle],
    *,
    selected_headline: str,
    max_articles: int = 20,
    max_per_publisher: int = 4,
    max_per_cluster: int = 2,
) -> List[RawArticle]:
    """Same-window reporting that genuinely helps explain this event.

    `story_tags` used to feed the anchor set and no longer do: they are
    editorial category labels - `Economy`, `Politics`, `Safety` - and generic
    by design, so `Economy` was matching an Uzbekistan/SCO report onto the gas
    subsidy card. Anchors now come from the headlines alone, and a shared
    anchor is necessary but no longer sufficient: a candidate must also clear
    _RELATED_MIN_SIMILARITY.
    """
    if not primary_articles:
        return []
    primary_ids = {str(article.id) for article in primary_articles}
    primary_cluster_ids = {str(article.cluster_id) for article in primary_articles if article.cluster_id}
    headlines = [selected_headline, *(article.headline for article in primary_articles)]
    anchor_text = " ".join(headlines)
    anchors = _core_anchors(headlines)
    if not anchors:
        return []

    primary_vectors = [_normalised_embedding(article.embedding) for article in primary_articles]
    primary_vectors = [vector for vector in primary_vectors if vector is not None]
    primary_tokens = _content_tokens(anchor_text)
    ranked: List[tuple[float, int, int, float, RawArticle]] = []

    for article in current_articles:
        if str(article.id) in primary_ids:
            continue
        if article.cluster_id and str(article.cluster_id) in primary_cluster_ids:
            continue
        candidate_text = f"{article.headline}. {(article.main_text or '')[:400]}"
        shared_anchors = anchors & _distinctive_anchors(candidate_text)
        if not shared_anchors:
            continue
        vector = _normalised_embedding(article.embedding)
        if vector is None or not primary_vectors:
            # Similarity used only to sort, so an unembedded candidate scored
            # 0.0 and still made the list whenever the caps left room.
            continue
        similarity = max(float(vector @ primary) for primary in primary_vectors)
        if similarity < _RELATED_MIN_SIMILARITY:
            continue
        token_overlap = len(primary_tokens & _content_tokens(article.headline))
        timestamp = trusted_article_timestamp(article).timestamp()
        ranked.append((similarity, len(shared_anchors), token_overlap, timestamp, article))

    ranked.sort(key=lambda row: (-row[0], -row[1], -row[2], -row[3], row[4].url))
    selected: List[RawArticle] = []
    publisher_counts: Counter[str] = Counter()
    cluster_counts: Counter[str] = Counter()
    for _similarity, _anchors, _tokens, _timestamp, article in ranked:
        cluster_key = str(article.cluster_id) if article.cluster_id else f"article:{article.id}"
        if publisher_counts[article.source] >= max_per_publisher:
            continue
        if cluster_counts[cluster_key] >= max_per_cluster:
            continue
        selected.append(article)
        publisher_counts[article.source] += 1
        cluster_counts[cluster_key] += 1
        if len(selected) >= max_articles:
            break
    return selected


def build_story_analysis_input(
    *,
    cluster_id: str,
    selected_headline: str,
    primary_articles: Sequence[RawArticle],
    current_articles: Sequence[RawArticle],
    total_content_limit: int = 60_000,
) -> StoryAnalysisInput:
    primary = select_primary_articles(primary_articles)
    related = find_related_articles(
        primary,
        current_articles,
        selected_headline=selected_headline,
    )
    rows: List[StoryAnalysisArticle] = []
    remaining = max(0, int(total_content_limit))
    for article, role, per_article_limit in [
        *((article, "primary_event", 5_000) for article in primary),
        *((article, "related_current_context", 1_500) for article in related),
    ]:
        if remaining <= 0 and role == "related_current_context":
            break
        allowed = min(per_article_limit, remaining) if remaining > 0 else 0
        row = StoryAnalysisArticle.from_raw(article, role=role, content_limit=allowed)
        rows.append(row)
        remaining = max(0, remaining - len(row.content))
    return StoryAnalysisInput(
        cluster_id=str(cluster_id),
        selected_headline=_normalize_ws(selected_headline),
        articles=tuple(rows),
    )


def build_story_analysis_user_prompt(story_input: StoryAnalysisInput) -> str:
    return json.dumps(
        {
            "task": "Write the factual analysis and, only when justified, a specific accountability question.",
            "cluster_id": story_input.cluster_id,
            "selected_headline": story_input.selected_headline,
            "articles": [article.to_prompt_dict() for article in story_input.articles],
        },
        ensure_ascii=False,
    )


def validate_story_analysis(
    response: StoryAnalysisResponse,
    story_input: StoryAnalysisInput,
) -> ValidatedStoryAnalysis:
    allowed = story_input.allowed_article_ids
    by_id = {article.article_id: article for article in story_input.articles}
    analysis_errors: List[str] = []
    question_errors: List[str] = []

    if not story_input.primary_articles:
        analysis_errors.append("missing_primary_articles")
    if _contains_forbidden_conclusion(response.analysis):
        analysis_errors.append("unsupported_conclusion_in_analysis")

    all_evidence = " ".join(article.evidence_text() for article in story_input.articles)
    # Figures in the analysis are checked against the event's own reporting
    # plus only the context a claim actually cites - not the whole supplied
    # pool. Pooling every related article grew the accepted token set on one
    # live card from 14 values to 33, admitting `2640`, `54%` and `4244` from
    # a food-inspection story into a hospital-safety analysis.
    claim_cited_ids = {
        str(article_id)
        for claim in response.claims
        for article_id in claim.supporting_article_ids
    }
    analysis_evidence = " ".join(
        article.evidence_text()
        for article in story_input.articles
        if article.role == "primary_event" or article.article_id in claim_cited_ids
    )
    if not _tokens_supported(response.analysis, analysis_evidence):
        analysis_errors.append("unsupported_number_or_date_in_analysis")

    cited_article_ids: set[str] = set()
    for claim in response.claims:
        support_ids = list(claim.supporting_article_ids)
        if not support_ids or any(article_id not in allowed for article_id in support_ids):
            analysis_errors.append("unknown_claim_support")
            continue
        cited_article_ids.update(support_ids)
        support_text = " ".join(by_id[article_id].evidence_text() for article_id in support_ids)
        if not _tokens_supported(claim.text, support_text):
            analysis_errors.append("unsupported_number_or_date_in_claim")

    cited_publishers = {by_id[article_id].publisher for article_id in cited_article_ids}
    if len(cited_publishers) == 1:
        source = next(iter(cited_publishers))
        aliases = _KNOWN_PUBLISHERS.get(source, (source.replace("_", " "),))
        lowered = response.analysis.lower()
        if not any(alias in lowered for alias in aliases):
            analysis_errors.append("missing_single_source_attribution")

    # Recorded, never fatal. A wrong publisher name is a copy defect - every
    # fact in the analysis is still validated against the supplied evidence by
    # the checks above - while discarding the analysis costs the reader the
    # whole card body. It reaches /health through validation_errors instead.
    named_publishers = _named_publishers(response.analysis)
    supplied_publishers = {article.publisher for article in story_input.articles}
    soft_errors: List[str] = []
    if any(source not in supplied_publishers for source in named_publishers):
        soft_errors.append("unknown_publisher_in_analysis")

    question = response.question
    question_ids = list(response.question_supporting_article_ids)
    if question is not None:
        story_core_anchors = _core_anchors(
            [story_input.selected_headline, *(a.headline for a in story_input.primary_articles)]
        )
        question_support = all_evidence
        if not question_ids or any(article_id not in allowed for article_id in question_ids):
            question_errors.append("unknown_question_support")
        else:
            question_support = " ".join(by_id[article_id].evidence_text() for article_id in question_ids)
            if not _tokens_supported(question, question_support):
                question_errors.append("unsupported_number_or_date_in_question")
            # Against ALL supplied evidence, not just the articles the model
            # happened to cite. The contract bars a subject that was never
            # supplied to this call; scoping it to the cited subset rejected
            # 40% of live questions, including the contract's own canonical
            # "six publishers are not six independent sources" case.
            if not _proper_phrases_supported(question, all_evidence):
                question_errors.append("unsupported_named_subject_in_question")
        if _contains_forbidden_conclusion(question):
            question_errors.append("unsupported_conclusion_in_question")
        if not _question_is_specific(
            question,
            response.question_basis,
            question_support,
            core_anchors=story_core_anchors,
        ):
            question_errors.append("generic_question")

    if analysis_errors:
        raise StoryAnalysisValidationError(
            ",".join(dict.fromkeys(analysis_errors)),
            calls=0,
        )

    uncovered = _uncovered_factual_sentences(response.analysis, response.claims)
    if uncovered:
        # Log-only. Nothing checks that every factual sentence is covered by a
        # claim, so a sentence the model chose not to cite is unvalidated. The
        # threshold for making this fatal is unproven, and a wrong one costs a
        # card - so it is reported, not enforced.
        logger.info(
            "Story analysis for cluster %s left %d factual sentence(s) uncovered by any claim: %s",
            story_input.cluster_id,
            len(uncovered),
            " | ".join(sentence[:120] for sentence in uncovered[:3]),
        )

    question_status = "ok"
    rejected_question: Optional[str] = None
    rejected_question_basis: Optional[str] = None
    if question_errors:
        rejected_question = question
        rejected_question_basis = response.question_basis.value
        question = None
        question_ids = []
        question_status = "question_dropped"
    recorded_errors = tuple(dict.fromkeys([*question_errors, *soft_errors]))

    cited = {
        article_id
        for claim in response.claims
        for article_id in claim.supporting_article_ids
    } | set(question_ids)
    related_ids = tuple(
        article.article_id
        for article in story_input.related_articles
        if article.article_id in cited
    )
    return ValidatedStoryAnalysis(
        analysis=response.analysis,
        question=question,
        question_basis=(response.question_basis.value if question else QuestionBasis.NONE.value),
        claims=tuple(claim.model_dump() for claim in response.claims),
        question_supporting_article_ids=tuple(question_ids),
        related_article_ids=related_ids,
        status=question_status,
        validation_errors=recorded_errors,
        rejected_question=rejected_question,
        rejected_question_basis=rejected_question_basis,
    )


def _uncovered_factual_sentences(
    analysis: str, claims: Sequence[StoryAnalysisClaim]
) -> List[str]:
    """Sentences carrying a figure, date or name that no claim restates."""
    claim_text = " ".join(claim.text for claim in claims).lower()
    claim_tokens = set(_evidence_tokens(claim_text)) | {
        phrase.lower() for phrase in _question_phrases(" ".join(claim.text for claim in claims))
    }
    uncovered: List[str] = []
    for sentence in split_sentences(_normalize_ws(analysis)):
        particulars = set(_evidence_tokens(sentence)) | _question_phrases(sentence)
        if not particulars:
            continue
        if particulars & claim_tokens:
            continue
        uncovered.append(sentence)
    return uncovered


def _normalised_embedding(value: Optional[Sequence[float]]) -> Optional[np.ndarray]:
    if not value:
        return None
    vector = np.asarray(value, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if vector.ndim != 1 or vector.size == 0 or not math.isfinite(norm) or norm <= 0:
        return None
    return vector / norm


def _core_anchors(headlines: Sequence[str]) -> set[str]:
    """Anchors that identify *this* story, not one report of it.

    A shared name alone is far too weak on this corpus. Measured over the live
    449-article window: a Punjab police-purge story and a Hong Kong summit
    invitation both reached the hospital-safety card through `maryam`, a
    Diplomatic Enclave review reached the security-operations card through
    `interior`, and a Saudi-envoy courtesy note reached the Foreign Office card
    through `office` - each on an anchor carried by a single primary headline.
    Requiring the anchor to appear in at least half the primary headlines drops
    all of those and keeps `pims`, `iran`, `gold` and `pvma`, which is the
    separation a similarity floor alone cannot make: the PIMS Rs22bn report
    that the analysis genuinely needs sits at 0.873, *below* the junk.
    """
    documents = [headline for headline in headlines if (headline or "").strip()]
    if not documents:
        return set()
    counts: Counter[str] = Counter()
    for document in documents:
        counts.update(_distinctive_anchors(document))
    required = max(1, math.ceil(len(documents) / 2))
    return {anchor for anchor, seen in counts.items() if seen >= required}


def _distinctive_anchors(text: str) -> set[str]:
    """Names specific enough to identify a story, not a subject area.

    Filtered against _TOKEN_STOPWORDS rather than _GENERIC_ANCHORS: the latter
    is the 30-word geography/office list, so ordinary sentence words like
    `after` and `against` were counting as distinctive story anchors.
    """
    anchors = {match.lower() for match in _ACRONYM_RE.findall(text or "")}
    anchors.update(match.lower() for match in _PROPER_RE.findall(text or ""))
    return {anchor for anchor in anchors if anchor not in _TOKEN_STOPWORDS and len(anchor) >= 3}


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall((text or "").lower())
        if len(token) >= 4 and token not in _TOKEN_STOPWORDS
    }


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_evidence(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace(",", "")).strip()


def _evidence_tokens(text: str) -> List[str]:
    tokens = [match.group(0) for match in _NUMBER_RE.finditer(text or "")]
    tokens.extend(match.group(0) for match in _DATE_WORD_RE.finditer(text or ""))
    tokens.extend("may" for _ in _MAY_DATE_RE.finditer(text or ""))
    return [_canonical_evidence_token(token) for token in tokens if _canonical_evidence_token(token)]


def _source_evidence_tokens(text: str) -> set[str]:
    """What the supplied reporting can support, including expanded year ranges."""
    tokens = set(_evidence_tokens(text))
    for match in _YEAR_RANGE_RE.finditer(text or ""):
        start = int(match.group(1))
        raw_end = match.group(2)
        end = int(raw_end)
        if len(raw_end) == 2:
            end = (start // 100) * 100 + end
            if end < start:
                end += 100
        tokens.add(str(start))
        tokens.add(str(end))
    return tokens


def _canonical_evidence_token(token: str) -> str:
    """Reduce a figure to its magnitude, dropping the currency marker.

    `Rs22bn`, `Rs 22 billion` and `22 billion rupees` are the same number. If
    the marker stayed in the token they would canonicalise three ways and a
    correct sentence would fail against its own source.
    """
    compact = re.sub(r"\s+", "", _normalize_evidence(token))
    compact = re.sub(r"^(?:rs|pkr|usd)\.?", "", compact)
    compact = compact.replace("billion", "bn").replace("million", "m")
    compact = compact.replace("percent", "%")
    compact = compact.rstrip(".")
    if compact.isalpha():
        for month in _MONTHS:
            if month.startswith(compact) or compact.startswith(month):
                return month[:3]
        return compact
    return _canonical_magnitude(compact)


# Reporting mixes scales freely: APP writes reserves in millions on the same
# day Business Recorder writes them in billions, and "Rs2.1 million" and
# "Rs21 lakh" are the same fee. Reducing a figure to its magnitude makes those
# one token. It is stricter than string matching, not looser - `22bn` and
# `22m` remain different values, and a bare number keeps no scale at all.
_SCALES = {"bn": 10**9, "crore": 10**7, "m": 10**6, "lakh": 10**5}


def _canonical_magnitude(token: str) -> str:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(bn|crore|m|lakh)", token)
    if not match:
        return token
    value = float(match.group(1)) * _SCALES[match.group(2)]
    return format(value, ".6f").rstrip("0").rstrip(".")


def _tokens_supported(output: str, source_text: str) -> bool:
    return set(_evidence_tokens(output)).issubset(_source_evidence_tokens(source_text))


def _contains_forbidden_conclusion(text: str) -> bool:
    """Does the text assert culpability in its own voice?

    Checked per sentence, and a sentence that attributes is exempt. The bare
    word search treated "Opposition members raised allegations of corruption
    within the Land Department" as the model concluding corruption, and
    discarded the whole analysis - even though the prompt explicitly asks for
    accusatory claims to be *attributed*, which is what that sentence does.
    """
    for sentence in split_sentences(_normalize_ws(text)):
        lowered = sentence.lower()
        if _ATTRIBUTION_CUE_RE.search(lowered):
            continue
        for term in _FORBIDDEN_CONCLUSIONS:
            if " " in term or "-" in term:
                if term in lowered:
                    return True
                continue
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                return True
    return False


def _named_publishers(text: str) -> set[str]:
    """Publishers the analysis actually attributes something to.

    Matching bare lowercase aliases treated "an e-pension app", "across the
    nation" and "at dawn on Thursday" as publisher attributions - and because
    the resulting error was analysis-level, an ordinary English sentence could
    discard the whole analysis. An attribution is now required to look like
    one: the name in its published casing, next to a reporting verb or behind
    "according to".
    """
    body = text or ""
    found: set[str] = set()
    for source, aliases in _KNOWN_PUBLISHERS.items():
        for alias in aliases:
            forms = {alias.title(), alias.upper()}
            for form in forms:
                escaped = re.escape(form)
                if re.search(rf"\b{escaped}\b\W+(?:\w+\W+){{0,2}}{_PUBLISHER_CUE}\b", body) or re.search(
                    rf"\baccording to\s+(?:the\s+)?{escaped}\b", body, re.IGNORECASE
                ):
                    found.add(source)
                    break
            if source in found:
                break
    return found


_QUESTION_IGNORED_PHRASES = {
        "according",
        "after",
        "before",
        "despite",
        "given",
        "how",
        "if",
        "since",
        "six",
        "the",
        "these",
        "this",
        "what",
        "when",
        "where",
        "whether",
        "which",
    "while",
    "why",
}


def _question_phrases(text: str) -> set[str]:
    """Names the text introduces, ignoring words capitalised only by position.

    `_PROPER_RE` matches any capitalised word, so every sentence opener looked
    like a proper noun and was checked against the evidence. A hand-written
    ignore list cannot keep up with that: it held `Given`, `Six` and `Which`,
    and the first live question it met opened with `Multiple` - which is how
    the contract's own canonical source-independence question was thrown away.
    A capitalised word counts only when it appears somewhere other than the
    start of a sentence. Acronyms always count.
    """
    body = text or ""
    phrases = {match.lower() for match in _ACRONYM_RE.findall(body)}
    for match in _PROPER_RE.finditer(body):
        if _starts_a_sentence(body, match.start()):
            continue
        phrases.add(match.group(0).lower())
    return {
        phrase
        for phrase in phrases
        if phrase not in _QUESTION_IGNORED_PHRASES and phrase not in _GENERIC_ANCHORS
    }


def _starts_a_sentence(text: str, index: int) -> bool:
    prefix = text[:index].rstrip(" \t\n\r\"'“‘([")
    return not prefix or prefix[-1] in ".!?:;"


def _phrase_in_support(phrase: str, support: str) -> bool:
    # Word-bounded: a bare substring test let `Nation` match `national`.
    return re.search(rf"\b{re.escape(phrase)}\b", support) is not None


def _proper_phrases_supported(question: str, support_text: str) -> bool:
    support = _normalize_evidence(support_text)
    return all(_phrase_in_support(phrase, support) for phrase in _question_phrases(question))


def _question_is_specific(
    question: str,
    basis: QuestionBasis,
    support_text: str,
    *,
    core_anchors: Optional[set[str]] = None,
) -> bool:
    """Does the question reuse a concrete particular from the reporting?

    Membership in a keyword list is not evidence. The old guard passed the
    prompt's own canonical BAD question on the single word `safety`, and passed
    anything containing an acronym - so "Why do such tragedies keep happening in
    PIMS?" counted as specific because it named the story's own subject.

    A question qualifies by carrying a figure or date the support also carries,
    by naming something the support names that is *not* simply the story's
    subject, by making the source-independence argument, or by combining at
    least two of the narrow accountability terms. One of those terms alone is
    not enough - that is precisely how the BAD example got through.
    """
    lowered = (question or "").lower()
    support = _normalize_evidence(support_text)

    if set(_evidence_tokens(question)) & _source_evidence_tokens(support_text):
        return True

    subject = core_anchors or set()
    if any(
        _phrase_in_support(phrase, support)
        for phrase in _question_phrases(question)
        if phrase not in subject
    ):
        return True

    if basis == QuestionBasis.SOURCE_INDEPENDENCE and any(
        term in lowered for term in ("independent", "independently", "verification")
    ):
        return True

    return sum(1 for term in _QUESTION_SPECIFIC_TERMS if term in lowered) >= 2


__all__ = [
    "QuestionBasis",
    "StoryAnalysisArticle",
    "StoryAnalysisClaim",
    "StoryAnalysisError",
    "StoryAnalysisInput",
    "StoryAnalysisResponse",
    "StoryAnalysisValidationError",
    "ValidatedStoryAnalysis",
    "build_story_analysis_input",
    "build_story_analysis_user_prompt",
    "find_related_articles",
    "load_story_analysis_system_prompt",
    "select_primary_articles",
    "validate_story_analysis",
]
