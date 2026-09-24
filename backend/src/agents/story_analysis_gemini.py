from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

from src.agents.editorial_gemini import _sanitize_schema_dict
from src.agents.rate_limit import is_daily_quota_message, is_retryable_message, retry_delay_seconds
from src.agents.story_analysis import (
    StoryAnalysisError,
    StoryAnalysisInput,
    StoryAnalysisResponse,
    build_story_analysis_user_prompt,
    load_story_analysis_system_prompt,
)

logger = logging.getLogger(__name__)


class GeminiStoryAnalysisService:
    DEFAULT_MODEL = "gemini-3.5-flash-lite"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[object] = None,
        max_attempts: int = 2,
        sleep: Any = time.sleep,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = (
            model
            or os.getenv("SAAF_STORY_ANALYSIS_MODEL")
            or self.DEFAULT_MODEL
        ).strip()
        self.max_attempts = max(1, int(max_attempts))
        self._sleep = sleep
        self._genai_types = None
        self.last_call_count = 0

        if client is not None:
            self._client = client
            return
        if not self.api_key:
            raise StoryAnalysisError("Missing GEMINI_API_KEY for story analysis")
        try:
            from google import genai  # type: ignore
            from google.genai import types as genai_types  # type: ignore
        except Exception as exc:
            raise StoryAnalysisError(
                "google-genai is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc
        self._client = genai.Client(api_key=self.api_key)
        self._genai_types = genai_types

    def analyze(self, story_input: StoryAnalysisInput) -> StoryAnalysisResponse:
        self.last_call_count = 0
        last_error: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            self.last_call_count += 1
            try:
                return self._analyze_once(story_input)
            except StoryAnalysisError as exc:
                last_error = exc
                if attempt == self.max_attempts - 1:
                    break
                message = str(exc)
                if is_daily_quota_message(message):
                    break
                if is_retryable_message(message):
                    delay = retry_delay_seconds(message, attempt)
                else:
                    delay = 2.0 * (2**attempt)
                logger.warning(
                    "Story analysis attempt %d/%d failed; waiting %.1fs: %s",
                    attempt + 1,
                    self.max_attempts,
                    delay,
                    exc,
                )
                self._sleep(max(1.0, delay))
        raise StoryAnalysisError(
            f"Gemini story analysis failed: {last_error}", calls=self.last_call_count
        )

    def _analyze_once(self, story_input: StoryAnalysisInput) -> StoryAnalysisResponse:
        config: Any = {
            "system_instruction": load_story_analysis_system_prompt(),
            "temperature": 0,
            "response_mime_type": "application/json",
            "response_schema": _sanitize_schema_dict(StoryAnalysisResponse.model_json_schema()),
        }
        if self._genai_types is not None:
            config = self._genai_types.GenerateContentConfig(**config)
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=build_story_analysis_user_prompt(story_input),
                config=config,
            )
        except Exception as exc:
            raise StoryAnalysisError(f"Gemini request failed: {exc}") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, StoryAnalysisResponse):
            return parsed
        if isinstance(parsed, dict):
            try:
                return StoryAnalysisResponse.model_validate(parsed)
            except Exception as exc:
                raise StoryAnalysisError(f"Story analysis response validation failed: {exc}") from exc

        text = getattr(response, "text", None)
        if not text or not str(text).strip():
            raise StoryAnalysisError("Gemini story analysis response was empty")
        try:
            payload = json.loads(str(text))
            return StoryAnalysisResponse.model_validate(payload)
        except Exception as exc:
            raise StoryAnalysisError(f"Story analysis response parsing failed: {exc}") from exc


__all__ = ["GeminiStoryAnalysisService"]
