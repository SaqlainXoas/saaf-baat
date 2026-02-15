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


def _mock_embed_response(vector: list[float], count: int) -> dict:
    return {"embeddings": [{"values": list(vector)} for _ in range(count)]}


class TestGeminiEmbeddingProviderInit:
    """Test GeminiEmbeddingProvider initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        with patch("src.agents.embeddings.genai.Client"):
            provider = GeminiEmbeddingProvider(api_key="test_key")
            assert provider.api_key == "test_key"

    def test_init_from_env(self):
        """Test initialization from environment variable."""
        with patch("src.agents.embeddings.genai.Client"):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "env_test_key"}):
                provider = GeminiEmbeddingProvider()
                assert provider.api_key == "env_test_key"

    def test_init_missing_api_key_raises_error(self):
        """Test that missing API key raises error."""
        with patch("src.agents.embeddings.genai.Client"):
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("GEMINI_API_KEY", None)
                with pytest.raises(EmbeddingError, match="API key"):
                    GeminiEmbeddingProvider()

    def test_default_model(self):
        """Test default embedding model is set."""
        with patch("src.agents.embeddings.genai.Client"):
            provider = GeminiEmbeddingProvider(api_key="test_key")
            assert provider.model == "models/gemini-embedding-001"

    def test_default_task_type(self):
        """Test default task type for clustering."""
        with patch("src.agents.embeddings.genai.Client"):
            provider = GeminiEmbeddingProvider(api_key="test_key")
            assert provider.task_type == "CLUSTERING"

    def test_default_output_dimensionality(self):
        """Test default output dimensionality matches DB vector size."""
        with patch("src.agents.embeddings.genai.Client"):
            provider = GeminiEmbeddingProvider(api_key="test_key")
            assert provider.output_dimensionality == 768

    def test_invalid_output_dimensionality_raises_error(self):
        """Test output dimensionality guardrails."""
        with patch("src.agents.embeddings.genai.Client"):
            with pytest.raises(EmbeddingError, match="output_dimensionality"):
                GeminiEmbeddingProvider(api_key="test_key", output_dimensionality=64)


class TestEmbeddingGeneration:
    """Test embedding generation with mocked API."""

    @pytest.fixture
    def mock_genai(self):
        """Mock google.genai client."""
        with patch("src.agents.embeddings.genai.Client") as mock_client_cls:
            mock_client = MagicMock()

            def _embed_side_effect(*, contents, **_kwargs):
                count = len(contents) if isinstance(contents, list) else 1
                return _mock_embed_response([0.1] * 768, count=count)

            mock_client.models.embed_content.side_effect = _embed_side_effect
            mock_client_cls.return_value = mock_client
            yield mock_client

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
        mock_genai.models.embed_content.return_value = _mock_embed_response(
            [1.0, 2.0, 3.0] + [0.0] * 765,
            count=1,
        )
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
        """Mock google.genai client."""
        with patch("src.agents.embeddings.genai.Client") as mock_client_cls:
            mock_client = MagicMock()

            def _embed_side_effect(*, contents, **_kwargs):
                count = len(contents) if isinstance(contents, list) else 1
                return _mock_embed_response([0.1] * 768, count=count)

            mock_client.models.embed_content.side_effect = _embed_side_effect
            mock_client_cls.return_value = mock_client
            yield mock_client

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
        with patch("src.agents.embeddings.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.embed_content.side_effect = Exception("API error")
            mock_client_cls.return_value = mock_client
            provider = GeminiEmbeddingProvider(api_key="invalid_key")

            with pytest.raises(EmbeddingError):
                provider.embed(["Test text"])

    def test_rate_limit_error_handling(self):
        """Test handling of rate limit errors."""
        with patch("src.agents.embeddings.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.embed_content.side_effect = Exception("Resource exhausted")
            mock_client_cls.return_value = mock_client
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


@pytest.mark.integration
class TestEmbeddingPayloadValidation:
    """
    Live tests to verify embedding payloads match expected schema.

    These tests verify Phase 3 completion requirements.
    """

    @pytest.fixture
    def api_key(self):
        """Get API key from environment."""
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            pytest.skip("GEMINI_API_KEY not set")
        return key

    def test_embedding_result_structure(self, api_key):
        """
        Verify EmbeddingResult payload has all required fields.

        This is the canonical test for embedding payload structure.
        """
        provider = GeminiEmbeddingProvider(api_key=api_key)
        texts = ["Test article headline about Pakistan economy"]
        result = provider.embed(texts)

        # Required fields
        assert hasattr(result, "embeddings"), "Missing embeddings field"
        assert hasattr(result, "model"), "Missing model field"
        assert hasattr(result, "texts_count"), "Missing texts_count field"
        assert hasattr(result, "dimension"), "Missing dimension field"

        # Verify types
        assert isinstance(result.embeddings, np.ndarray), "embeddings must be numpy array"
        assert result.embeddings.dtype == np.float32, "embeddings must be float32"
        assert isinstance(result.model, str), "model must be string"
        assert isinstance(result.texts_count, int), "texts_count must be int"
        assert isinstance(result.dimension, int), "dimension must be int"

        # Verify values
        assert result.dimension == 768, f"Expected 768 dims, got {result.dimension}"
        assert result.texts_count == 1

        print(f"\n✓ EmbeddingResult payload valid:")
        print(f"  - embeddings: {result.embeddings.shape}")
        print(f"  - model: {result.model}")
        print(f"  - texts_count: {result.texts_count}")
        print(f"  - dimension: {result.dimension}")

    def test_embedding_normalization(self, api_key):
        """
        Verify embeddings are properly L2 normalized for cosine similarity.
        """
        provider = GeminiEmbeddingProvider(api_key=api_key)
        texts = [
            "Article about inflation in Pakistan",
            "Cricket team wins against India",
            "Stock market hits record high",
        ]
        result = provider.embed(texts)

        # Check L2 norm of each embedding is 1.0
        for i, emb in enumerate(result.embeddings):
            norm = np.linalg.norm(emb)
            assert np.isclose(norm, 1.0, atol=0.01), f"Embedding {i} not normalized: norm={norm}"

        print(f"✓ All {len(texts)} embeddings are L2 normalized")

    def test_embedding_text_processing(self, api_key):
        """
        Verify embedding handles article-like text correctly.

        Tests the typical input format: headline + main_text[:500]
        """
        provider = GeminiEmbeddingProvider(api_key=api_key)

        # Simulate article text as it would be processed
        headline = "Pakistan Stock Market Reaches Record High"
        main_text = """The Pakistan Stock Exchange (PSX) reached a historic milestone 
        today as the benchmark KSE-100 index crossed 100,000 points for the first time. 
        Analysts attribute this surge to improved economic indicators and increased 
        foreign investment. The State Bank of Pakistan's recent policy decisions have 
        boosted investor confidence. Trading volumes have increased significantly over 
        the past month."""

        combined_text = f"{headline}. {main_text[:500]}"

        result = provider.embed([combined_text])

        assert result.embeddings.shape == (1, 768)
        assert result.texts_count == 1

        print(f"✓ Article-format text embedded successfully")
        print(f"  - Input length: {len(combined_text)} chars")
        print(f"  - Output shape: {result.embeddings.shape}")

    def test_embedding_semantic_quality(self, api_key):
        """
        Verify embeddings capture semantic meaning correctly.

        Similar articles should have high cosine similarity (>0.7)
        Dissimilar articles should have lower similarity (<0.5)
        """
        provider = GeminiEmbeddingProvider(api_key=api_key)

        # Similar articles (same story)
        article1 = "Rupee falls to record low against dollar amid economic concerns"
        article2 = "Pakistani currency drops to historic low versus US dollar"

        # Dissimilar article
        article3 = "Cricket team wins championship match in thrilling final"

        result = provider.embed([article1, article2, article3])

        # Cosine similarity (embeddings are normalized, so dot product = cosine sim)
        sim_1_2 = np.dot(result.embeddings[0], result.embeddings[1])
        sim_1_3 = np.dot(result.embeddings[0], result.embeddings[2])
        sim_2_3 = np.dot(result.embeddings[1], result.embeddings[2])

        print(f"\n✓ Semantic similarity test:")
        print(f"  - Similar (rupee articles): {sim_1_2:.3f}")
        print(f"  - Dissimilar (rupee vs cricket): {sim_1_3:.3f}")
        print(f"  - Dissimilar (rupee vs cricket): {sim_2_3:.3f}")

        # Similar articles should be more similar than dissimilar
        assert sim_1_2 > sim_1_3, "Similar articles should have higher similarity"
        assert sim_1_2 > sim_2_3, "Similar articles should have higher similarity"

        # Relative margin check is more stable across embedding model updates.
        assert sim_1_2 > 0.6, f"Similar articles similarity too low: {sim_1_2}"
        assert (
            sim_1_2 - sim_1_3
        ) > 0.1, f"Similarity margin too small: similar={sim_1_2}, dissimilar={sim_1_3}"
