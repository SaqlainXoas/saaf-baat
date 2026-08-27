"""
Batched LLM triage: what a story is about, and who it affects.

This replaces `config/classification_rules.yaml` and `RuleBasedClassifier`.
A 390-line keyword file cannot know that degraded national internet is a
utilities story with wide public impact, or that a festival stampede is hard
news while a blossom-season piece is a feature. A model reading the headline
can, and at ~50 headlines per request the whole day costs 6-8 calls.

The ingest layer stays LLM-free: triage runs after articles are stored.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.agents.editorial import VALID_CATEGORIES, VALID_IMPACT_LABELS
from src.agents.rate_limit import is_rate_limit_message, retry_after_seconds

logger = logging.getLogger(__name__)

DEFAULT_TRIAGE_BATCH_SIZE = 50
DEFAULT_TRIAGE_MAX_RETRIES = 4

# What kind of piece this is. `story_type` is the part that actually replaces
# _SOFT_FEATURE_HEADLINE_PATTERNS: substring-matching "festival" and "spring"
# demotes a stampede and misses every soft feature phrased differently.
VALID_STORY_TYPES = (
    "hard_news",
    "routine",
    "feature",
    "opinion",
    "advertorial",
    "sport",
    "entertainment",
)

# How much of Pakistan this touches.
VALID_PK_RELEVANCE = (
    "national",
    "local",
    "foreign_with_pk_effect",
    "foreign",
)

TRIAGE_SYSTEM_PROMPT = """You triage Pakistani news headlines for a daily morning brief.

For each item you receive, decide four things:

- category: what desk the story belongs to.
- impact_labels: which parts of an ordinary Pakistani's day this touches. Zero
  labels is a valid answer. Do not reach for a label that is not really there.
- story_type: hard_news for a development that happened; routine for an
  institution publicising its own ordinary activity - licence and inspection
  tallies, campaign and enrolment totals, transfers and postings, ceremonial
  visits and calls-on, programme announcements that decide nothing new;
  feature for colour, travel, lifestyle, profiles and seasonal pieces; opinion
  for columns and commentary; advertorial for corporate puffery, MoU signings
  and anniversaries; sport and entertainment for those beats regardless of how
  they are written.
  Judge the substance, not the vocabulary: a stampede at a festival is
  hard_news, and a national award with real political weight is hard_news.
  routine is about the absence of a decision or a consequence, not about who
  issued the statement: a food authority publishing its weekly inspection count
  is routine, a food authority shutting down a national chain is hard_news.
- pk_relevance: national when it matters across Pakistan; local when it is one
  city or district; foreign_with_pk_effect when an overseas development has a
  clear, concrete effect on Pakistan; foreign otherwise.

confidence is your own certainty from 0 to 1, not the story's importance.

Return one verdict for every key you were given, using the exact key string.
Use only the allowed values. Return valid JSON only."""


@dataclass(frozen=True)
class TriageItem:
    """One article presented to triage."""

    key: str
    source: str
    headline: str
    summary: str = ""
    publisher_categories: Sequence[str] = ()
    # Not sent to the model: it is the stable identity a recorded golden-day
    # verdict is keyed by, where `key` is a per-run UUID.
    url: str = ""

    def to_prompt_dict(self, wire_key: str) -> Dict[str, Any]:
        return {
            "key": wire_key,
            "source": self.source,
            "headline": self.headline,
            "summary": _truncate(self.summary, 220),
            "publisher_categories": list(self.publisher_categories)[:4],
        }


class TriageVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The allowed values belong in the schema, not only in the validators.
    # Without them the schema said "type": "string" and the model was free to
    # answer `category: "opinion"` - a story_type - which discarded the verdict
    # and, on a live run, took triage_status to "degraded". A structured-output
    # model cannot emit a value the enum does not contain.
    key: str
    category: str = Field(json_schema_extra={"enum": list(VALID_CATEGORIES)})
    impact_labels: List[str] = Field(
        default_factory=list,
        max_length=3,
        json_schema_extra={"items": {"type": "string", "enum": list(VALID_IMPACT_LABELS)}},
    )
    story_type: str = Field(json_schema_extra={"enum": list(VALID_STORY_TYPES)})
    pk_relevance: str = Field(json_schema_extra={"enum": list(VALID_PK_RELEVANCE)})
    confidence: float = Field(ge=0, le=1)

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {value}")
        return value

    @field_validator("impact_labels")
    @classmethod
    def _validate_impact_labels(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        for item in value or []:
            if item in VALID_IMPACT_LABELS and item not in cleaned:
                cleaned.append(item)
        return cleaned[:3]

    @field_validator("story_type")
    @classmethod
    def _validate_story_type(cls, value: str) -> str:
        if value not in VALID_STORY_TYPES:
            raise ValueError(f"Invalid story_type: {value}")
        return value

    @field_validator("pk_relevance")
    @classmethod
    def _validate_pk_relevance(cls, value: str) -> str:
        if value not in VALID_PK_RELEVANCE:
            raise ValueError(f"Invalid pk_relevance: {value}")
        return value

    def as_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "impact_labels": list(self.impact_labels),
            "story_type": self.story_type,
            "pk_relevance": self.pk_relevance,
            "confidence": round(float(self.confidence), 3),
        }


class TriageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: List[TriageVerdict] = Field(default_factory=list)


class TriageError(RuntimeError):
    pass


@dataclass
class TriageResult:
    """What one triage pass produced, including what it failed to cover."""

    verdicts: Dict[str, TriageVerdict]
    calls: int = 0
    failures: int = 0
    missing_keys: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.missing_keys is None:
            self.missing_keys = []


class GeminiTriageService:
    """Headline triage over the Gemini structured-output API."""

    DEFAULT_MODEL = "gemini-3.1-flash-lite"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[object] = None,
        batch_size: int = DEFAULT_TRIAGE_BATCH_SIZE,
        max_retries: int = DEFAULT_TRIAGE_MAX_RETRIES,
        sleep: Any = time.sleep,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = (model or os.getenv("SAAF_TRIAGE_MODEL") or self.DEFAULT_MODEL).strip()
        self.batch_size = max(1, int(batch_size))
        self.max_retries = max(1, int(max_retries))
        self._sleep = sleep
        self._genai_types = None

        if client is not None:
            self._client = client
            return

        if not self.api_key:
            raise TriageError("Missing GEMINI_API_KEY for triage")

        try:
            from google import genai  # type: ignore
            from google.genai import types as genai_types  # type: ignore
        except Exception as exc:
            raise TriageError(
                "google-genai is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc

        self._client = genai.Client(api_key=self.api_key)
        self._genai_types = genai_types

    def triage(self, items: Sequence[TriageItem]) -> TriageResult:
        """
        Triage every item, batched.

        A batch that fails after its retries is recorded rather than raised:
        one bad batch should cost its own articles, not the whole run.
        """
        result = TriageResult(verdicts={}, calls=0, failures=0, missing_keys=[])
        if not items:
            return result

        for start in range(0, len(items), self.batch_size):
            batch = list(items[start : start + self.batch_size])
            try:
                verdicts = self._triage_batch_with_retry(batch)
                result.calls += 1
            except TriageError as exc:
                result.calls += 1
                result.failures += len(batch)
                result.missing_keys.extend(item.key for item in batch)
                logger.warning(
                    "Triage failed for %d/%d items (offset %d): %s",
                    len(batch),
                    len(items),
                    start,
                    exc,
                )
                continue

            allowed = {item.key for item in batch}
            for verdict in verdicts:
                if verdict.key not in allowed:
                    logger.warning("Ignoring triage verdict for unknown key=%s", verdict.key)
                    continue
                result.verdicts[verdict.key] = verdict

            uncovered = [item.key for item in batch if item.key not in result.verdicts]
            if uncovered:
                result.failures += len(uncovered)
                result.missing_keys.extend(uncovered)
                logger.warning("Triage returned no verdict for %d items", len(uncovered))

        return result

    def _triage_batch_with_retry(self, batch: Sequence[TriageItem]) -> List[TriageVerdict]:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                return self._triage_batch(batch)
            except TriageError as exc:
                last_error = exc
                if not is_rate_limit_message(str(exc)) or attempt == self.max_retries - 1:
                    break
                delay = retry_after_seconds(str(exc))
                if delay is None:
                    delay = 2.0 * (2**attempt)
                logger.warning(
                    "Triage rate limited (attempt %d/%d); waiting %.1fs",
                    attempt + 1,
                    self.max_retries,
                    delay,
                )
                self._sleep(max(1.0, delay))
        raise last_error if last_error else TriageError("Triage failed")

    def _triage_batch(self, batch: Sequence[TriageItem]) -> List[TriageVerdict]:
        by_wire_key = dict(zip(wire_keys(batch), batch))
        user_prompt = build_triage_user_prompt(batch)
        config: Any = {
            "system_instruction": TRIAGE_SYSTEM_PROMPT,
            "temperature": 0,
            "response_mime_type": "application/json",
            "response_schema": _gemini_response_schema(),
        }
        if self._genai_types is not None:
            config = self._genai_types.GenerateContentConfig(**config)

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:
            raise TriageError(f"Triage request failed: {exc}") from exc

        verdicts: List[TriageVerdict] = []
        for verdict in _parse_triage_response(response):
            item = by_wire_key.get(verdict.key)
            if item is None:
                logger.warning("Ignoring triage verdict for unknown key=%s", verdict.key)
                continue
            verdicts.append(verdict.model_copy(update={"key": item.key}))
        return verdicts


def wire_keys(items: Sequence[TriageItem]) -> List[str]:
    """
    Short, opaque keys for the request.

    Caller keys are UUIDs or URLs. Echoing a 70-character URL back for every
    item burns tokens and invites near-miss mismatches (a live capture lost a
    verdict to a single normalised URL); "i7" cannot be mangled that way.
    """
    return [f"i{index}" for index in range(len(items))]


def build_triage_user_prompt(items: Sequence[TriageItem]) -> str:
    keys = wire_keys(items)
    return json.dumps(
        {
            "task": "Triage each item.",
            "allowed_categories": list(VALID_CATEGORIES),
            "allowed_impact_labels": list(VALID_IMPACT_LABELS),
            "allowed_story_types": list(VALID_STORY_TYPES),
            "allowed_pk_relevance": list(VALID_PK_RELEVANCE),
            "items": [item.to_prompt_dict(key) for item, key in zip(items, keys)],
        },
        ensure_ascii=False,
    )


def _parse_triage_response(response: Any) -> List[TriageVerdict]:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, TriageResponse):
        return list(parsed.verdicts)

    payload: Any = parsed
    if not isinstance(payload, dict):
        text = getattr(response, "text", None)
        if not text or not str(text).strip():
            raise TriageError("Triage response was empty")
        try:
            payload = json.loads(_strip_code_fence(str(text)))
        except Exception as exc:
            raise TriageError(f"Triage response parsing failed: {exc}") from exc

    # A model that returns a bare list instead of the wrapper object is still
    # answering the question; accept it rather than discarding 50 verdicts.
    rows = payload.get("verdicts") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise TriageError("Triage response contained no verdicts")

    verdicts: List[TriageVerdict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            verdicts.append(TriageVerdict.model_validate(row))
        except Exception as exc:
            logger.warning("Discarding malformed triage verdict %s: %s", row.get("key"), exc)
    return verdicts


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).strip()
    return cleaned


def _truncate(text: str, limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _gemini_response_schema() -> Dict[str, Any]:
    from src.agents.editorial_gemini import _sanitize_schema_dict  # local: avoids cycle

    return _sanitize_schema_dict(TriageResponse.model_json_schema())


__all__ = [
    "GeminiTriageService",
    "TriageError",
    "TriageItem",
    "TriageResult",
    "TriageVerdict",
    "VALID_PK_RELEVANCE",
    "VALID_STORY_TYPES",
    "build_triage_user_prompt",
    "wire_keys",
]
