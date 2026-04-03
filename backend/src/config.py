from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EditorialModelConfig:
    gemini_api_key: str
    groq_api_key: str
    gemini_model: str
    groq_model: str


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def load_editorial_model_config() -> EditorialModelConfig:
    """
    Central place to control editorial LLM selection.

    - Gemini is the primary editorial model (Gemini API / AI Studio).
    - Groq is the fallback.
    """

    gemini_api_key = _env("GEMINI_API_KEY")
    groq_api_key = _env("GROQ_API_KEY")

    gemini_model = _env("SAAF_EDITORIAL_GEMINI_MODEL") or "gemini-3.1-flash-lite-preview"

    # Backward-compatible: keep the prior env var as a fallback.
    groq_model = _env("SAAF_EDITORIAL_GROQ_MODEL") or _env("SAAF_EDITORIAL_LLM_MODEL") or "openai/gpt-oss-120b"

    return EditorialModelConfig(
        gemini_api_key=gemini_api_key,
        groq_api_key=groq_api_key,
        gemini_model=gemini_model,
        groq_model=groq_model,
    )

