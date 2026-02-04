"""
Gemini Embedding Provider for generating text embeddings.

Uses Google's text-embedding-004 model optimized for clustering tasks.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import google.generativeai as genai
import numpy as np


class EmbeddingError(Exception):
    """Base exception for embedding errors."""

    pass


class RateLimitError(EmbeddingError):
    """Exception raised when API rate limit is hit."""

    pass


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    embeddings: np.ndarray
    model: str
    texts_count: int

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self.embeddings.shape[1] if len(self.embeddings.shape) > 1 else 0


class GeminiEmbeddingProvider:
    """
    Embedding provider using Google Gemini API.

    Uses text-embedding-004 model with CLUSTERING task type for optimal
    clustering results.
    """

    DEFAULT_MODEL = "models/text-embedding-004"
    DEFAULT_TASK_TYPE = "CLUSTERING"
    EMBEDDING_DIMENSION = 768

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        task_type: str | None = None,
        rate_limit_delay: float = 0.0,
    ):
        """
        Initialize Gemini embedding provider.

        Args:
            api_key: Gemini API key. Defaults to GEMINI_API_KEY env var.
            model: Embedding model to use. Defaults to text-embedding-004.
            task_type: Task type for embeddings. Defaults to CLUSTERING.
            rate_limit_delay: Delay between batch API calls in seconds.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise EmbeddingError("Gemini API key not provided. Set GEMINI_API_KEY environment variable.")

        self.model = model or self.DEFAULT_MODEL
        self.task_type = task_type or self.DEFAULT_TASK_TYPE
        self.rate_limit_delay = rate_limit_delay

        genai.configure(api_key=self.api_key)

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed.

        Returns:
            EmbeddingResult with normalized embeddings.

        Raises:
            EmbeddingError: If embedding generation fails.
            RateLimitError: If API rate limit is exceeded.
        """
        if not texts:
            raise EmbeddingError("Cannot embed empty text list")

        embeddings = []
        try:
            for text in texts:
                result = genai.embed_content(
                    model=self.model,
                    content=text,
                    task_type=self.task_type,
                )
                embeddings.append(result["embedding"])
        except Exception as e:
            error_msg = str(e).lower()
            if "resource exhausted" in error_msg or "rate limit" in error_msg:
                raise RateLimitError(f"API rate limit exceeded: {e}") from e
            raise EmbeddingError(f"Failed to generate embeddings: {e}") from e

        embeddings_array = np.array(embeddings, dtype=np.float32)
        normalized = self._normalize(embeddings_array)

        return EmbeddingResult(
            embeddings=normalized,
            model=self.model,
            texts_count=len(texts),
        )

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> EmbeddingResult:
        """
        Generate embeddings in batches with rate limiting.

        Args:
            texts: List of texts to embed.
            batch_size: Number of texts per batch.

        Returns:
            EmbeddingResult with all embeddings.
        """
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = self.embed(batch)
            all_embeddings.append(result.embeddings)

            if i + batch_size < len(texts) and self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

        combined = np.vstack(all_embeddings)
        return EmbeddingResult(
            embeddings=combined,
            model=self.model,
            texts_count=len(texts),
        )

    def _normalize(self, embeddings: np.ndarray) -> np.ndarray:
        """L2 normalize embeddings for cosine similarity."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return embeddings / norms
