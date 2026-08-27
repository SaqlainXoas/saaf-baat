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


class TestSourcesConfigSchema:
    """The RSS/sitemap schema: tier + endpoints, no HTML sections."""

    def _config(self, **overrides):
        from copy import deepcopy

        base = {
            "sources": {
                "dawn": {
                    "url": "https://www.dawn.com",
                    "tier": "A",
                    "feed_urls": ["https://www.dawn.com/feeds/pakistan"],
                    "sitemap_urls": [],
                    "enabled": True,
                },
                "geo": {
                    "url": "https://www.geo.tv",
                    "tier": "B",
                    "feed_urls": [],
                    "sitemap_urls": ["https://www.geo.tv/news.xml"],
                    "enabled": True,
                },
            }
        }
        config = deepcopy(base)
        config["sources"]["dawn"].update(overrides)
        return config

    def test_valid_config_passes(self):
        from utils.validators import validate_sources_config

        assert validate_sources_config(self._config())["valid"] is True

    def test_missing_tier_is_rejected(self):
        from utils.validators import validate_sources_config

        config = self._config()
        del config["sources"]["dawn"]["tier"]
        result = validate_sources_config(config)
        assert result["valid"] is False
        assert any("tier" in error for error in result["errors"])

    def test_unknown_tier_is_rejected(self):
        from utils.validators import validate_sources_config

        result = validate_sources_config(self._config(tier="C"))
        assert result["valid"] is False

    def test_enabled_source_without_endpoints_is_rejected(self):
        from utils.validators import validate_sources_config

        result = validate_sources_config(self._config(feed_urls=[], sitemap_urls=[]))
        assert result["valid"] is False
        assert any("no feed_urls or sitemap_urls" in error for error in result["errors"])

    def test_disabled_source_without_endpoints_is_allowed(self):
        from utils.validators import validate_sources_config

        result = validate_sources_config(
            self._config(enabled=False, feed_urls=[], sitemap_urls=[])
        )
        assert result["valid"] is True

    def test_endpoint_lists_must_be_lists(self):
        from utils.validators import validate_sources_config

        result = validate_sources_config(self._config(feed_urls="https://one.example"))
        assert result["valid"] is False
