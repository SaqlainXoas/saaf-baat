"""
Test suite for utility validators.

Tests written BEFORE implementation (TDD approach).
"""


class TestArticleValidation:
    """Test article structure validation."""

    def test_validate_complete_article(self, sample_article):
        """Test validation of a complete article."""
        from utils.validators import validate_article_structure

        result = validate_article_structure(sample_article)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_missing_required_fields(self):
        """Test validation fails when required fields are missing."""
        from utils.validators import validate_article_structure

        incomplete_article = {
            "source": "dawn",
            "url": "https://example.com",
        }

        result = validate_article_structure(incomplete_article)
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert any("headline" in error for error in result["errors"])

    def test_validate_invalid_url(self):
        """Test validation fails for invalid URLs."""
        from utils.validators import validate_article_structure

        article = {
            "source": "dawn",
            "url": "not-a-valid-url",
            "headline": "Test",
            "main_text": "Text",
        }

        result = validate_article_structure(article)
        assert result["valid"] is False
        assert any("url" in error.lower() for error in result["errors"])

    def test_validate_empty_text(self):
        """Test validation fails for empty main text."""
        from utils.validators import validate_article_structure

        article = {
            "source": "dawn",
            "url": "https://example.com/article",
            "headline": "Test Headline",
            "main_text": "",
        }

        result = validate_article_structure(article)
        assert result["valid"] is False
        assert any("main_text" in error for error in result["errors"])


class TestConfigValidation:
    """Test configuration validation."""

    def test_validate_sources_config(self, sources_config):
        """Test sources configuration validation."""
        from utils.validators import validate_sources_config

        result = validate_sources_config(sources_config)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_classification_config(self, classification_config):
        """Test classification configuration validation."""
        from utils.validators import validate_classification_config

        result = validate_classification_config(classification_config)
        assert result["valid"] is True
        assert len(result["errors"]) == 0
