from __future__ import annotations

import json
import logging
import os
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
    build_editorial_user_prompt,
    review_with_short_pass_retries,
)

logger = logging.getLogger(__name__)


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

    DEFAULT_MODEL = "gemini-3.1-flash-lite"

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
        )

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

        try:
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
            response = self._client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:
            raise EditorialError(f"Gemini editorial request failed: {exc}") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, EditorialResponse):
            return parsed
        if isinstance(parsed, dict):
            normalized = _normalize_editorial_payload(parsed, candidate_lookup)
            return EditorialResponse.model_validate(normalized)

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
            parsed_response = EditorialResponse.model_validate(normalized)

        return parsed_response


def _normalize_editorial_payload(payload: Dict[str, Any], candidate_lookup: Dict[str, ClusterEditorialCandidate]) -> Dict[str, Any]:
    # Reuse the canonical normalization from src.agents.editorial (kept private there).
    # Import locally to avoid circular dependency at module import time.
    from src.agents.editorial import _normalize_editorial_payload as _normalize  # type: ignore

    return _normalize(payload, candidate_lookup)


def _gemini_response_schema(model: type[EditorialResponse]) -> Dict[str, Any]:
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
