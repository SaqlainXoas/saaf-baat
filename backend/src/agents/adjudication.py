"""
LLM adjudication for the split/merge pairs the deterministic gates cannot call.

Event grouping asks two questions of every pair: are the embeddings close, and
do the headlines and entities overlap. When both agree, the deterministic
answer is trustworthy and no model is consulted. When they disagree inside a
narrow band around the similarity threshold, the current code silently prefers
"different events" — a coin flip dressed as a rule. Those pairs, and only
those, come here.

The adjudicator proposes; it never disposes. A `same_event` verdict makes a
pair eligible to merge, and the group coherence gates still run afterwards, so
a wrong verdict cannot create an incoherent cluster.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from src.agents.rate_limit import is_retryable_message, retry_delay_seconds

logger = logging.getLogger(__name__)

DEFAULT_ADJUDICATION_BATCH_SIZE = 8
DEFAULT_MAX_ADJUDICATION_PAIRS = 24
DEFAULT_ADJUDICATION_MAX_RETRIES = 3

ADJUDICATION_SYSTEM_PROMPT = """You decide whether two Pakistani news articles describe the same event.

Same event means the same underlying development: the same announcement, the
same incident, the same decision, the same meeting. Two outlets covering one
press conference are the same event.

Different events means two separate developments, even when they share a topic,
a person, or a place. Two separate bomb blasts are different events. A policy
announcement and a later reaction to it are different events. A weekly rupee
report and a monthly inflation report are different events.

When you genuinely cannot tell from the headlines given, answer different: a
brief that splits one story into two cards is a smaller failure than one that
merges two stories into a card that misdescribes both.

Answer every pair you are given, by its id. Return valid JSON only."""


@dataclass(frozen=True)
class AdjudicationPair:
    """One borderline pair put to the model."""

    left_index: int
    right_index: int
    left_source: str
    left_headline: str
    right_source: str
    right_headline: str
    similarity: float
    headline_overlap: float
    entity_overlap: float
    # Not sent to the model: the stable identity a recorded golden-day verdict
    # is keyed by, where the indices are ingest-order dependent.
    left_url: str = ""
    right_url: str = ""

    @property
    def key(self) -> Tuple[int, int]:
        return (min(self.left_index, self.right_index), max(self.left_index, self.right_index))

    def to_prompt_dict(self, pair_id: str) -> Dict[str, Any]:
        return {
            "id": pair_id,
            "a": {"source": self.left_source, "headline": self.left_headline},
            "b": {"source": self.right_source, "headline": self.right_headline},
            "embedding_similarity": round(float(self.similarity), 3),
            "headline_overlap": round(float(self.headline_overlap), 3),
            "entity_overlap": round(float(self.entity_overlap), 3),
        }


class AdjudicationVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    same_event: bool
    confidence: float = Field(default=0.5, ge=0, le=1)


class AdjudicationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: List[AdjudicationVerdict] = Field(default_factory=list)


class AdjudicationError(RuntimeError):
    pass


@dataclass
class AdjudicationResult:
    """Verdicts keyed by article-index pair, plus what the pass cost."""

    verdicts: Dict[Tuple[int, int], bool] = field(default_factory=dict)
    calls: int = 0
    failures: int = 0
    merged: int = 0

    def __post_init__(self) -> None:
        self.merged = sum(1 for value in self.verdicts.values() if value)


class GeminiAdjudicationService:
    """Split/merge adjudication over the Gemini structured-output API."""

    DEFAULT_MODEL = "gemini-3.1-flash-lite"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[object] = None,
        batch_size: int = DEFAULT_ADJUDICATION_BATCH_SIZE,
        max_retries: int = DEFAULT_ADJUDICATION_MAX_RETRIES,
        sleep: Any = time.sleep,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = (model or os.getenv("SAAF_ADJUDICATION_MODEL") or self.DEFAULT_MODEL).strip()
        self.batch_size = max(1, int(batch_size))
        self.max_retries = max(1, int(max_retries))
        self._sleep = sleep
        self._genai_types = None

        if client is not None:
            self._client = client
            return

        if not self.api_key:
            raise AdjudicationError("Missing GEMINI_API_KEY for adjudication")

        try:
            from google import genai  # type: ignore
            from google.genai import types as genai_types  # type: ignore
        except Exception as exc:
            raise AdjudicationError(
                "google-genai is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc

        self._client = genai.Client(api_key=self.api_key)
        self._genai_types = genai_types

    def adjudicate(self, pairs: Sequence[AdjudicationPair]) -> AdjudicationResult:
        """Resolve every pair; a failed batch leaves its pairs undecided."""
        result = AdjudicationResult()
        if not pairs:
            return result

        for start in range(0, len(pairs), self.batch_size):
            batch = list(pairs[start : start + self.batch_size])
            try:
                verdicts = self._adjudicate_batch_with_retry(batch)
                result.calls += 1
            except AdjudicationError as exc:
                result.calls += 1
                result.failures += len(batch)
                logger.warning("Adjudication failed for %d pairs: %s", len(batch), exc)
                continue
            result.verdicts.update(verdicts)

        result.merged = sum(1 for value in result.verdicts.values() if value)
        return result

    def _adjudicate_batch_with_retry(
        self, batch: Sequence[AdjudicationPair]
    ) -> Dict[Tuple[int, int], bool]:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                return self._adjudicate_batch(batch)
            except AdjudicationError as exc:
                last_error = exc
                message = str(exc)
                if not is_retryable_message(message) or attempt == self.max_retries - 1:
                    break
                delay = retry_delay_seconds(message, attempt)
                logger.warning(
                    "Adjudication request failed (attempt %d/%d); retrying in %.1fs: %s",
                    attempt + 1,
                    self.max_retries,
                    delay,
                    message,
                )
                self._sleep(max(1.0, delay))
        raise last_error if last_error else AdjudicationError("Adjudication failed")

    def _adjudicate_batch(self, batch: Sequence[AdjudicationPair]) -> Dict[Tuple[int, int], bool]:
        by_id = {f"p{index}": pair for index, pair in enumerate(batch)}
        user_prompt = build_adjudication_user_prompt(by_id)

        config: Any = {
            "system_instruction": ADJUDICATION_SYSTEM_PROMPT,
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
            raise AdjudicationError(f"Adjudication request failed: {exc}") from exc

        verdicts: Dict[Tuple[int, int], bool] = {}
        for verdict in _parse_adjudication_response(response):
            pair = by_id.get(verdict.id)
            if pair is None:
                logger.warning("Ignoring adjudication verdict for unknown id=%s", verdict.id)
                continue
            verdicts[pair.key] = bool(verdict.same_event)
        return verdicts


def build_adjudication_user_prompt(by_id: Dict[str, AdjudicationPair]) -> str:
    return json.dumps(
        {
            "task": "For each pair, decide whether a and b describe the same event.",
            "pairs": [pair.to_prompt_dict(pair_id) for pair_id, pair in by_id.items()],
        },
        ensure_ascii=False,
    )


def _parse_adjudication_response(response: Any) -> List[AdjudicationVerdict]:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, AdjudicationResponse):
        return list(parsed.verdicts)

    payload: Any = parsed
    if not isinstance(payload, dict):
        text = getattr(response, "text", None)
        if not text or not str(text).strip():
            raise AdjudicationError("Adjudication response was empty")
        cleaned = str(text).strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").replace("json\n", "", 1).strip()
        try:
            payload = json.loads(cleaned)
        except Exception as exc:
            raise AdjudicationError(f"Adjudication response parsing failed: {exc}") from exc

    rows = payload.get("verdicts") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise AdjudicationError("Adjudication response contained no verdicts")

    verdicts: List[AdjudicationVerdict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            verdicts.append(AdjudicationVerdict.model_validate(row))
        except Exception as exc:
            logger.warning("Discarding malformed adjudication verdict %s: %s", row.get("id"), exc)
    return verdicts


def _gemini_response_schema() -> Dict[str, Any]:
    from src.agents.editorial_gemini import _sanitize_schema_dict  # local: avoids cycle

    return _sanitize_schema_dict(AdjudicationResponse.model_json_schema())


__all__ = [
    "AdjudicationError",
    "AdjudicationPair",
    "AdjudicationResult",
    "AdjudicationVerdict",
    "GeminiAdjudicationService",
    "build_adjudication_user_prompt",
]
