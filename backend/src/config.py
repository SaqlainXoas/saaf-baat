from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EditorialModelConfig:
    gemini_api_key: str
    gemini_model: str


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def load_editorial_model_config() -> EditorialModelConfig:
    """
    Central place to control editorial LLM selection.

    - Gemini is the single editorial model (Gemini API / AI Studio).
    """

    gemini_api_key = _env("GEMINI_API_KEY")
    gemini_model = _env("SAAF_EDITORIAL_GEMINI_MODEL") or "gemini-3.1-flash-lite-preview"

    return EditorialModelConfig(
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )
