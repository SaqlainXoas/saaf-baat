"""
Tests for Gemini Embedding Provider.

Following TDD: These tests are written BEFORE implementation.
"""
from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.agents.embeddings import (
    EmbeddingError,
    EmbeddingResult,
    GeminiEmbeddingProvider,
    RateLimitError,
)


class TestGeminiEmbeddingProviderInit:
    """Test GeminiEmbeddingProvider initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        with patch("src.agents.embeddings.genai"):
            provider = GeminiEmbeddingProvider(api_key="test_key")
            assert provider.api_key == "test_key"

    def test_init_from_env(self):
        """Test initialization from environment variable."""
        with patch("src.agents.embeddings.genai"):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "env_test_key"}):
                provider = GeminiEmbeddingProvider()
                assert provider.api_key == "env_test_key"

    def test_init_missing_api_key_raises_error(self):
        """Test that missing API key raises error."""
        with patch("src.agents.embeddings.genai"):
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("GEMINI_API_KEY", None)
                with pytest.raises(EmbeddingError, match="API key"):
                    GeminiEmbeddingProvider()

    def test_default_model(self):
        """Test default embedding model is set."""
        with patch("src.agents.embeddings.genai"):
            provider = GeminiEmbeddingProvider(api_key="test_key")
            assert provider.model == "models/text-embedding-004"

    def test_default_task_type(self):
        """Test default task type for clustering."""
        with patch("src.agents.embeddings.genai"):
            provider = GeminiEmbeddingProvider(api_key="test_key")
            assert provider.task_type == "CLUSTERING"


class TestEmbeddingGeneration:
    """Test embedding generation with mocked API."""

    @pytest.fixture
    def mock_genai(self):
        """Mock google.generativeai module."""
        with patch("src.agents.embeddings.genai") as mock:
            mock.embed_content.return_value = {"embedding": [0.1] * 768}
            yield mock

    def test_embed_single_text(self, mock_genai):
        """Test embedding a single text."""
        provider = GeminiEmbeddingProvider(api_key="test_key")
        result = provider.embed(["Test text for embedding"])

        assert isinstance(result, EmbeddingResult)
        assert result.embeddings.shape == (1, 768)

    def test_embed_multiple_texts(self, mock_genai):
        """Test embedding multiple texts."""
        provider = GeminiEmbeddingProvider(api_key="test_key")
        texts = ["Text one", "Text two", "Text three"]
        result = provider.embed(texts)

        assert result.embeddings.shape == (3, 768)

    def test_embed_empty_list_raises_error(self, mock_genai):
        """Test that empty text list raises error."""
        provider = GeminiEmbeddingProvider(api_key="test_key")
        with pytest.raises(EmbeddingError, match="empty"):
            provider.embed([])

    def test_embeddings_are_normalized(self, mock_genai):
        """Test that embeddings are L2 normalized."""
        mock_genai.embed_content.return_value = {"embedding": [1.0, 2.0, 3.0] + [0.0] * 765}
        provider = GeminiEmbeddingProvider(api_key="test_key")
        result = provider.embed(["Test text"])

        norm = np.linalg.norm(result.embeddings[0])
        assert np.isclose(norm, 1.0, atol=0.01)

    def test_embed_returns_float32(self, mock_genai):
        """Test embeddings are returned as float32."""
        provider = GeminiEmbeddingProvider(api_key="test_key")
        result = provider.embed(["Test text"])
        assert result.embeddings.dtype == np.float32


class TestBatchProcessing:
    """Test batch processing."""

    @pytest.fixture
    def mock_genai(self):
        """Mock google.generativeai module."""
        with patch("src.agents.embeddings.genai") as mock:
            mock.embed_content.return_value = {"embedding": [0.1] * 768}
            yield mock

    def test_batch_embed_processes_all(self, mock_genai):
        """Test that all texts are embedded."""
        provider = GeminiEmbeddingProvider(api_key="test_key")
        texts = [f"Text {i}" for i in range(100)]
        result = provider.embed_batch(texts, batch_size=25)

        assert result.embeddings.shape == (100, 768)

    def test_batch_embed_with_rate_limiting(self, mock_genai):
        """Test rate limiting between batches."""
        provider = GeminiEmbeddingProvider(api_key="test_key", rate_limit_delay=0.1)
        texts = [f"Text {i}" for i in range(20)]

        start = time.time()
        result = provider.embed_batch(texts, batch_size=10)
        duration = time.time() - start

        # Should have at least one delay between batches
        assert duration >= 0.1
        assert result.embeddings.shape == (20, 768)


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_api_error_raises_embedding_error(self):
        """Test that API errors raise EmbeddingError."""
        with patch("src.agents.embeddings.genai") as mock_genai:
            mock_genai.embed_content.side_effect = Exception("API error")
            provider = GeminiEmbeddingProvider(api_key="invalid_key")

            with pytest.raises(EmbeddingError):
                provider.embed(["Test text"])

    def test_rate_limit_error_handling(self):
        """Test handling of rate limit errors."""
        with patch("src.agents.embeddings.genai") as mock_genai:
            mock_genai.embed_content.side_effect = Exception("Resource exhausted")
            provider = GeminiEmbeddingProvider(api_key="test_key")

            with pytest.raises(RateLimitError):
                provider.embed(["Test text"])


class TestEmbeddingResult:
    """Test EmbeddingResult dataclass."""

    def test_result_properties(self):
        """Test result contains correct properties."""
        embeddings = np.array([[0.1] * 768], dtype=np.float32)
        result = EmbeddingResult(
            embeddings=embeddings,
            model="test-model",
            texts_count=1,
        )

        assert result.embeddings.shape == (1, 768)
        assert result.model == "test-model"
        assert result.texts_count == 1
        assert result.dimension == 768


@pytest.mark.integration
class TestGeminiIntegration:
    """Integration tests with real Gemini API."""

    @pytest.fixture
    def api_key(self):
        """Get API key from environment."""
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            pytest.skip("GEMINI_API_KEY not set")
        return key

    def test_real_embedding_generation(self, api_key):
        """Test real embedding generation."""
        provider = GeminiEmbeddingProvider(api_key=api_key)
        texts = ["Rupee falls to record low against dollar"]
        result = provider.embed(texts)

        assert result.embeddings.shape == (1, 768)
        assert result.embeddings.dtype == np.float32
        norms = np.linalg.norm(result.embeddings, axis=1)
        assert np.allclose(norms, 1.0, atol=0.01)

    def test_similar_texts_high_similarity(self, api_key):
        """Test similar texts have high cosine similarity."""
        provider = GeminiEmbeddingProvider(api_key=api_key)

        text1 = "Inflation rises to 30 percent in Pakistan"
        text2 = "Pakistan's inflation rate reaches 30 percent"
        text3 = "Cricket match postponed due to rain"

        result = provider.embed([text1, text2, text3])

        sim_1_2 = np.dot(result.embeddings[0], result.embeddings[1])
        sim_1_3 = np.dot(result.embeddings[0], result.embeddings[2])

        assert sim_1_2 > sim_1_3
        assert sim_1_2 > 0.7

    def test_real_batch_embedding(self, api_key):
        """Test batch embedding with real API."""
        provider = GeminiEmbeddingProvider(api_key=api_key)
        texts = [f"Article {i} about economy and inflation" for i in range(5)]
        result = provider.embed_batch(texts, batch_size=3)

        assert result.embeddings.shape == (5, 768)
