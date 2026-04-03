from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Sequence
from uuid import UUID

from src.agents.editorial import ClusterEditorialCandidate, EditorialError, EditorialStory, GroqMorningBriefService
from src.agents.editorial_gemini import GeminiMorningBriefService

logger = logging.getLogger(__name__)


@dataclass
class EditorialRouterService:
    """
    Try editorial providers in priority order:
    1) Gemini (primary)
    2) Groq (fallback)

    The orchestrator expects an object with:
    - review_clusters(...)
    - model (string) used for metadata
    """

    gemini: Optional[GeminiMorningBriefService] = None
    groq: Optional[GroqMorningBriefService] = None

    # last successful model name used for review_clusters
    model: str = "unknown"

    def review_clusters(
        self,
        candidates: Sequence[ClusterEditorialCandidate],
        *,
        max_stories: int = 9,
    ) -> Dict[UUID, EditorialStory]:
        last_exc: Optional[Exception] = None

        if self.gemini is not None:
            try:
                result = self.gemini.review_clusters(candidates, max_stories=max_stories)
                self.model = self.gemini.model
                return result
            except Exception as exc:
                last_exc = exc
                logger.warning("Gemini editorial failed, attempting Groq fallback: %s", exc)

        if self.groq is not None:
            try:
                result = self.groq.review_clusters(candidates, max_stories=max_stories)
                self.model = self.groq.model
                return result
            except Exception as exc:
                last_exc = exc
                logger.warning("Groq editorial failed: %s", exc)

        if last_exc is None:
            raise EditorialError("No editorial provider configured")
        raise EditorialError(str(last_exc)) from last_exc


__all__ = ["EditorialRouterService"]

