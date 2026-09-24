"""
Gemini Embedding Provider for generating text embeddings.

Uses Google's gemini-embedding-001 model with 768 output dimensions
to match pgvector VECTOR(768) columns in the database schema.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from src.agents.rate_limit import is_daily_quota_message, is_retryable_message, retry_delay_seconds

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - handled by runtime guard
    genai = None
    types = None


logger = logging.getLogger(__name__)


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

    Uses gemini-embedding-001 with CLUSTERING task type for clustering.
    Output dimensionality defaults to 768 to match DB schema.
    """

    DEFAULT_MODEL = "models/gemini-embedding-001"
    DEFAULT_TASK_TYPE = "CLUSTERING"
    DEFAULT_OUTPUT_DIMENSIONALITY = 768
    MIN_OUTPUT_DIMENSIONALITY = 128
    MAX_OUTPUT_DIMENSIONALITY = 3072
    # The free tier bills one request per *text*, not per batch call, and caps
    # it at 100 per minute. A 300-article day exceeds that in a single call, so
    # batches must be paced rather than fired back to back.
    DEFAULT_REQUESTS_PER_MINUTE = 100
    DEFAULT_MAX_RETRIES = 4

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        task_type: str | None = None,
        output_dimensionality: int | None = None,
        rate_limit_delay: float = 0.0,
        requests_per_minute: int | None = None,
        max_retries: int | None = None,
    ):
        """
        Initialize Gemini embedding provider.

        Args:
            api_key: Gemini API key. Defaults to GEMINI_API_KEY env var.
            model: Embedding model to use. Defaults to gemini-embedding-001.
            task_type: Task type for embeddings. Defaults to CLUSTERING.
            output_dimensionality: Embedding dimension. Defaults to 768.
            rate_limit_delay: Delay between batch API calls in seconds.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise EmbeddingError(
                "Gemini API key not provided. Set GEMINI_API_KEY environment variable."
            )
        if genai is None or types is None:
            raise EmbeddingError(
                "google-genai is not installed. Run `pip install -r backend/requirements.txt`."
            )

        self.model = model or self.DEFAULT_MODEL
        self.task_type = task_type or self.DEFAULT_TASK_TYPE
        self.output_dimensionality = (
            output_dimensionality
            if output_dimensionality is not None
            else self.DEFAULT_OUTPUT_DIMENSIONALITY
        )
        if not (
            self.MIN_OUTPUT_DIMENSIONALITY
            <= self.output_dimensionality
            <= self.MAX_OUTPUT_DIMENSIONALITY
        ):
            raise EmbeddingError(
                "output_dimensionality must be between "
                f"{self.MIN_OUTPUT_DIMENSIONALITY} and {self.MAX_OUTPUT_DIMENSIONALITY}"
            )
        self.rate_limit_delay = rate_limit_delay
        self.requests_per_minute = int(
            requests_per_minute
            if requests_per_minute is not None
            else _env_int("SAAF_EMBEDDING_RPM", self.DEFAULT_REQUESTS_PER_MINUTE)
        )
        self.max_retries = max(1, int(max_retries or self.DEFAULT_MAX_RETRIES))
        self._last_batch_size = 0

        self._client = genai.Client(api_key=self.api_key)

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

        try:
            result = self._client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=self.task_type,
                    output_dimensionality=self.output_dimensionality,
                ),
            )
            embeddings = self._extract_embeddings(result, expected_count=len(texts))
        except Exception as e:
            error_msg = str(e).lower()
            # The API says RESOURCE_EXHAUSTED with an underscore; matching only
            # the spaced form let real 429s through as generic failures, which
            # skipped the retry path entirely.
            if any(
                marker in error_msg
                for marker in (
                    "resource exhausted",
                    "resource_exhausted",
                    "rate limit",
                    "quota",
                    "429",
                )
            ):
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
            if self._last_batch_size:
                delay = max(self.rate_limit_delay, self._pace_seconds(self._last_batch_size))
                if delay > 0:
                    time.sleep(delay)
            result = self._embed_with_retry(batch)
            all_embeddings.append(result.embeddings)
            self._last_batch_size = len(batch)
        combined = np.vstack(all_embeddings)
        return EmbeddingResult(
            embeddings=combined,
            model=self.model,
            texts_count=len(texts),
        )

    def _pace_seconds(self, batch_size: int) -> float:
        """Seconds to wait so the next batch stays inside the per-minute quota."""
        if self.requests_per_minute <= 0:
            return 0.0
        return 60.0 * batch_size / float(self.requests_per_minute)

    def _embed_with_retry(self, batch: list[str]) -> EmbeddingResult:
        """Embed one batch, waiting out rate limits rather than failing the run."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self.embed(batch)
            except (RateLimitError, EmbeddingError) as exc:
                last_error = exc
                message = str(exc)
                if (attempt == self.max_retries - 1 or is_daily_quota_message(message)
                        or not is_retryable_message(message)):
                    break
                delay = retry_delay_seconds(message, attempt)
                if _retry_after_seconds(message) is not None:
                    delay += 1.0
                if isinstance(exc, RateLimitError):
                    delay = max(delay, self._pace_seconds(len(batch)))
                delay = min(delay, 120.0)
                logger.warning(
                    "Embedding temporarily unavailable (attempt %d/%d); waiting %.1fs",
                    attempt + 1,
                    self.max_retries,
                    delay,
                )
                time.sleep(max(1.0, delay))
        raise last_error if last_error else EmbeddingError("Embedding failed")

    def _normalize(self, embeddings: np.ndarray) -> np.ndarray:
        """L2 normalize embeddings for cosine similarity."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return embeddings / norms

    def _extract_embeddings(self, result: dict | object, expected_count: int) -> list[list[float]]:
        """Extract one embedding per text from SDK response object."""
        if expected_count <= 0:
            raise EmbeddingError("expected_count must be positive")

        # New SDK shape: {"embeddings": [{"values": [...]}, ...]}
        if isinstance(result, dict):
            rows = result.get("embeddings")
            if isinstance(rows, list):
                vectors = [self._coerce_vector(row) for row in rows]
                if len(vectors) == expected_count:
                    return vectors

            # Backward-compat shape for tests/mocks: {"embedding": [...]}
            single = result.get("embedding")
            if single is not None and expected_count == 1:
                return [self._coerce_vector(single)]

        rows_obj = getattr(result, "embeddings", None)
        if isinstance(rows_obj, Iterable):
            vectors = [self._coerce_vector(row) for row in rows_obj]
            if len(vectors) == expected_count:
                return vectors

        single_obj = getattr(result, "embedding", None)
        if single_obj is not None and expected_count == 1:
            return [self._coerce_vector(single_obj)]

        raise EmbeddingError("Embedding response missing expected embedding vectors")

    @staticmethod
    def _coerce_vector(row: Any) -> list[float]:
        """Convert row-like SDK payload into a list[float]."""
        if isinstance(row, list):
            return [float(v) for v in row]
        if isinstance(row, tuple):
            return [float(v) for v in row]
        if isinstance(row, dict):
            values = row.get("values") or row.get("embedding")
            if values is not None:
                return [float(v) for v in values]
        values_attr = getattr(row, "values", None)
        if values_attr is not None:
            return [float(v) for v in values_attr]
        embedding_attr = getattr(row, "embedding", None)
        if embedding_attr is not None:
            return [float(v) for v in embedding_attr]
        raise EmbeddingError("Embedding row is missing vector values")


def _retry_after_seconds(message: str) -> float | None:
    """Pull the server's own retry hint out of a rate-limit message."""
    match = re.search(r"[Pp]lease retry in ([0-9.]+)s", message)
    if not match:
        match = re.search(r"'retryDelay': '(\d+)s'", message)
    if not match:
        return None
    try:
        return float(match.group(1)) + 1.0
    except ValueError:
        return None


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
