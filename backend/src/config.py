from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EditorialModelConfig:
    gemini_api_key: str
    gemini_model: str


@dataclass(frozen=True)
class StoryAnalysisModelConfig:
    gemini_api_key: str
    gemini_model: str


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def load_editorial_model_config() -> EditorialModelConfig:
    """
    Central place to control editorial LLM selection.

    Gemini is the only editorial model. Groq was removed on 2026-08-25: its
    free tier allows 8,000 tokens per minute for `openai/gpt-oss-120b`, prompt
    and completion together, which a ten-to-twelve card brief over a thirty
    candidate shortlist does not fit inside. Every run spent a 413, a rate-limit
    wait and a fall-through before Gemini produced the brief anyway.
    """

    return EditorialModelConfig(
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("SAAF_EDITORIAL_GEMINI_MODEL") or "gemini-3.5-flash-lite",
    )


def load_story_analysis_model_config() -> StoryAnalysisModelConfig:
    return StoryAnalysisModelConfig(
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("SAAF_STORY_ANALYSIS_MODEL") or "gemini-3.5-flash-lite",
    )
