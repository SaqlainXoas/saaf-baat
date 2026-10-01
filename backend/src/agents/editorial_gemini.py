from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional, Sequence
from uuid import UUID

from src.agents.editorial import (
    COMPACT_PROMPT_CANDIDATE_THRESHOLD,
    DEFAULT_MAX_STORIES,
    EDITORIAL_SYSTEM_PROMPT,
    ClusterEditorialCandidate,
    EditorialError,
    EditorialResponse,
    EditorialStory,
    EditorialStoryRepair,
    build_editorial_repair_user_prompt,
    build_editorial_user_prompt,
    review_with_short_pass_retries,
)
from src.agents.rate_limit import is_daily_quota_message, is_retryable_message, retry_delay_seconds

logger = logging.getLogger(__name__)

# Enough to outlast a brief provider blip without stalling the run.
_PROVIDER_ATTEMPTS = 4
_PROVIDER_MAX_BACKOFF = 30.0


_GEMINI_SCHEMA_ALLOWED_KEYS = {
    "anyOf",
    "default",
    "description",
    "enum",
    "example",
    "format",
    "items",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "nullable",
    "pattern",
    "properties",
    "propertyOrdering",
    "required",
    "title",
    "type",
    "$defs",
    "$ref",
}


class GeminiMorningBriefService:
    """
    Gemini-first editorial service using structured JSON output.

    Gemini API structured output uses:
    - response_mime_type = application/json
    - response_schema = Pydantic model / JSON schema
    """

    DEFAULT_MODEL = "gemini-3.5-flash-lite"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[object] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = (model or os.getenv("SAAF_EDITORIAL_GEMINI_MODEL") or self.DEFAULT_MODEL).strip()
        if not self.api_key:
            raise EditorialError("Missing GEMINI_API_KEY for Gemini editorial review")

        self._genai_types = None
        if client is not None:
            self._client = client
            return

        try:
            from google import genai  # type: ignore
            from google.genai import types as genai_types  # type: ignore
        except Exception as exc:
            raise EditorialError(
                "google-genai is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc

        self._client = genai.Client(api_key=self.api_key)
        self._genai_types = genai_types

    def review_clusters(
        self,
        candidates: Sequence[ClusterEditorialCandidate],
        *,
        max_stories: int = DEFAULT_MAX_STORIES,
    ) -> Dict[UUID, EditorialStory]:
        """The editorial pass, with a collapsed brief retried against a deeper slice."""
        return review_with_short_pass_retries(
            lambda window: self._review_once(window, max_stories=max_stories),
            candidates,
            max_stories=max_stories,
            repair_story=self._repair_rejected_story,
        )

    def _generate_with_retry(self, user_prompt: str, config: Any) -> Any:
        """Send the editorial request, retrying a server that is merely busy.

        Embeddings have had this since Phase 1; the editor never did, so a
        provider hiccup was indistinguishable from a malformed request. On
        2026-09-14 the second pass got a bare `503 UNAVAILABLE`, the short-pass
        loop treated it as fatal, and the brief shipped the four cards the
        first pass had grounded. A 503 means "ask again", and now it does.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, _PROVIDER_ATTEMPTS + 1):
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001 - the provider raises bare types
                last_exc = exc
                message = str(exc)
                if (not is_retryable_message(message) or is_daily_quota_message(message)
                        or attempt == _PROVIDER_ATTEMPTS):
                    raise EditorialError(f"Gemini editorial request failed: {exc}") from exc
                delay = min(retry_delay_seconds(message, attempt - 1), 120.0)
                logger.warning(
                    "Editorial request failed (attempt %d/%d); retrying in %.1fs: %s",
                    attempt,
                    _PROVIDER_ATTEMPTS,
                    delay,
                    message,
                )
                time.sleep(delay)
        raise EditorialError(f"Gemini editorial request failed: {last_exc}")

    def _review_once(
        self,
        candidates: Sequence[ClusterEditorialCandidate],
        *,
        max_stories: int,
    ) -> EditorialResponse:
        candidate_lookup = {str(candidate.cluster_id): candidate for candidate in candidates}
        # At thirty candidates the full excerpts are tokens spent on detail the
        # editor does not decide on.
        compact = len(candidates) > COMPACT_PROMPT_CANDIDATE_THRESHOLD
        candidate_rows = [candidate.to_prompt_dict(compact=compact) for candidate in candidates]

        system_prompt = EDITORIAL_SYSTEM_PROMPT
        user_prompt = build_editorial_user_prompt(candidate_rows, max_stories=max_stories)

        config = {
            "system_instruction": system_prompt,
            "temperature": 0,
            "response_mime_type": "application/json",
            # google-genai==1.0.0 expects `response_schema`, but its Schema model
            # rejects fields like additionalProperties that Pydantic emits by default.
            "response_schema": _gemini_response_schema(EditorialResponse),
        }
        if self._genai_types is not None:
            config = self._genai_types.GenerateContentConfig(**config)

        response = self._generate_with_retry(user_prompt, config)

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, EditorialResponse):
            return parsed
        if isinstance(parsed, dict):
            normalized = _normalize_editorial_payload(parsed, candidate_lookup)
            # This used to be an unguarded model_validate: a live run on
            # 2026-09-24 got an impact_line one character over the 220-char
            # limit on the third retry attempt, and the resulting
            # ValidationError escaped uncaught, killing the whole pipeline
            # run instead of being treated like any other malformed
            # attempt the retry loop already knows how to move past.
            try:
                return EditorialResponse.model_validate(normalized)
            except Exception as exc:
                raise EditorialError(f"Gemini editorial response failed validation: {exc}") from exc

        text = getattr(response, "text", None)
        if not text or not str(text).strip():
            raise EditorialError("Gemini editorial response was empty")

        try:
            parsed_response = EditorialResponse.model_validate_json(str(text))
        except Exception as exc:
            # One more chance: Gemini may return JSON but with minor inconsistencies
            # that our normalizer can fix.
            try:
                payload = json.loads(str(text))
            except Exception:
                raise EditorialError(f"Gemini editorial response parsing failed: {exc}") from exc
            normalized = _normalize_editorial_payload(payload, candidate_lookup)
            try:
                parsed_response = EditorialResponse.model_validate(normalized)
            except Exception as validate_exc:
                raise EditorialError(
                    f"Gemini editorial response failed validation: {validate_exc}"
                ) from validate_exc

        return parsed_response

    def _repair_rejected_story(
        self,
        story: EditorialStory,
        candidate: ClusterEditorialCandidate,
        cause: str,
        token: str,
    ) -> Optional[EditorialStory]:
        """One targeted rewrite of a story the grounding check rejected.

        Only headline/impact_line/what_to_watch are ever accepted back from
        this call - category, priority, impact_labels, story_tags, confidence
        and selection_reason are always taken from the original selection, so
        a repair can only fix wording, never smuggle in a different story or
        a different editorial judgement.
        """
        user_prompt = build_editorial_repair_user_prompt(story, candidate, cause, token)
        config: Any = {
            "system_instruction": EDITORIAL_SYSTEM_PROMPT,
            "temperature": 0,
            "response_mime_type": "application/json",
            "response_schema": _gemini_response_schema(EditorialStoryRepair),
        }
        if self._genai_types is not None:
            config = self._genai_types.GenerateContentConfig(**config)

        try:
            response = self._generate_with_retry(user_prompt, config)
        except EditorialError as exc:
            logger.warning("Grounding repair request failed for cluster_id=%s: %s", story.cluster_id, exc)
            return None

        payload = self._extract_repair_payload(response)
        if payload is None:
            logger.warning("Grounding repair response was unusable for cluster_id=%s", story.cluster_id)
            return None

        try:
            repair = EditorialStoryRepair.model_validate(payload)
        except Exception as exc:
            logger.warning("Grounding repair response failed validation for cluster_id=%s: %s", story.cluster_id, exc)
            return None

        # Only the three repaired fields cross over; everything else is the
        # original editorial judgement, untouched by the repair call.
        return story.model_copy(
            update={
                "headline": repair.headline,
                "impact_line": repair.impact_line,
                "what_to_watch": repair.what_to_watch,
            }
        )

    @staticmethod
    def _extract_repair_payload(response: Any) -> Optional[Dict[str, Any]]:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, EditorialStoryRepair):
            return parsed.model_dump()
        if isinstance(parsed, dict):
            return parsed

        text = getattr(response, "text", None)
        if not text or not str(text).strip():
            return None
        try:
            payload = json.loads(str(text))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None


def _normalize_editorial_payload(payload: Dict[str, Any], candidate_lookup: Dict[str, ClusterEditorialCandidate]) -> Dict[str, Any]:
    # Reuse the canonical normalization from src.agents.editorial (kept private there).
    # Import locally to avoid circular dependency at module import time.
    from src.agents.editorial import _normalize_editorial_payload as _normalize  # type: ignore

    return _normalize(payload, candidate_lookup)


def _gemini_response_schema(model: type) -> Dict[str, Any]:
    return _sanitize_schema_dict(model.model_json_schema())


def _sanitize_schema_dict(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        return schema

    cleaned: Dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _GEMINI_SCHEMA_ALLOWED_KEYS:
            continue
        if key == "default" and value is not None:
            continue
        if key in {"properties", "$defs"} and isinstance(value, dict):
            cleaned[key] = {name: _sanitize_schema_dict(sub) for name, sub in value.items()}
            continue
        if key in {"items"} and isinstance(value, dict):
            cleaned[key] = _sanitize_schema_dict(value)
            continue
        if key == "anyOf" and isinstance(value, list):
            cleaned[key] = [_sanitize_schema_dict(item) if isinstance(item, dict) else item for item in value]
            continue
        cleaned[key] = value
    return cleaned


__all__ = ["GeminiMorningBriefService"]
