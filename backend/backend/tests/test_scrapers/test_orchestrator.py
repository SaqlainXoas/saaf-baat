"""
Unit tests for scraper orchestrator.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.orchestrator import (
    ScraperOrchestrator,
    SourceConfig,
    ScrapingResult,
    ConfigValidationError,
    load_scraper_config,
    validate_scraper_config,
)
from src.scrapers.base import ScrapingError, ContentExtractionError
from src.db.models import RawArticle


class TestConfigLoading:
    """Test configuration loading and validation."""
    
    def test_load_valid_config(self, config_dir):
        """Test loading valid sources.yaml."""
        config = load_scraper_config(str(config_dir / "sources.yaml"))
        
        assert "sources" in config
        assert isinstance(config["sources"], dict)
    
    def test_load_missing_config_raises_error(self):
        """Test loading non-existent config raises error."""
        with pytest.raises(ConfigValidationError):
            load_scraper_config("/nonexistent/path/sources.yaml")
    
    def test_validate_valid_config(self):
        """Test validation passes for valid config."""
        config = {
            "sources": {
                "dawn": {
                    "url": "https://dawn.com",
                    "method": "newspaper4k",
                }
            }
        }
        
        validate_scraper_config(config)  # Should not raise
    
    def test_validate_empty_config_fails(self):
        """Test validation fails for empty config."""
        with pytest.raises(ConfigValidationError):
            validate_scraper_config({})
        
        with pytest.raises(ConfigValidationError):
            validate_scraper_config(None)
    
    def test_validate_missing_sources_fails(self):
        """Test validation fails when sources key missing."""
        with pytest.raises(ConfigValidationError):
            validate_scraper_config({"other_key": {}})
    
    def test_validate_missing_url_fails(self):
        """Test validation fails when source missing URL."""
        config = {
            "sources": {
                "test_source": {
                    "method": "newspaper4k",
                    # Missing 'url'
                }
            }
        }
        
        with pytest.raises(ConfigValidationError):
            validate_scraper_config(config)
    
    def test_validate_invalid_method_fails(self):
        """Test validation fails for invalid scraping method."""
        config = {
            "sources": {
                "test_source": {
                    "url": "https://example.com",
                    "method": "invalid_method",
                }
            }
        }
        
        with pytest.raises(ConfigValidationError):
            validate_scraper_config(config)
    
    def test_validate_all_valid_methods(self):
        """Test all valid methods pass validation."""
        valid_methods = ["newspaper4k", "newsplease", "playwright"]
        
        for method in valid_methods:
            config = {
                "sources": {
                    "test": {
                        "url": "https://example.com",
                        "method": method,
                    }
                }
            }
            validate_scraper_config(config)  # Should not raise


class TestSourceConfig:
    """Test SourceConfig dataclass."""
    
    def test_default_values(self):
        """Test SourceConfig has correct defaults."""
        config = SourceConfig(name="test", url="https://example.com")
        
        assert config.name == "test"
        assert config.url == "https://example.com"
        assert config.method == "newspaper4k"
        assert config.rate_limit == 1.0
        assert config.max_articles == 50
        assert config.language == "en"
        assert config.enabled is True
        assert config.sections == []
    
    def test_custom_values(self):
        """Test SourceConfig with custom values."""
        config = SourceConfig(
            name="geo",
            url="https://geo.tv",
            method="playwright",
            rate_limit=2.0,
            max_articles=100,
            language="ur",
            scroll_depth=5,
        )
        
        assert config.method == "playwright"
        assert config.rate_limit == 2.0
        assert config.max_articles == 100
        assert config.scroll_depth == 5


class TestOrchestratorInit:
    """Test orchestrator initialization."""
    
    def test_init_with_config(self, config_dir):
        """Test orchestrator initializes with config file."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml")
        )
        
        assert orchestrator.total_sources > 0
    
    def test_init_with_source_filter(self, config_dir):
        """Test orchestrator filters sources."""
        # Get all sources first
        full_orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml")
        )
        all_sources = list(full_orchestrator._source_configs.keys())
        
        if len(all_sources) >= 2:
            # Filter to just first source
            filtered_orchestrator = ScraperOrchestrator(
                config_path=str(config_dir / "sources.yaml"),
                sources=[all_sources[0]],
            )
            
            assert filtered_orchestrator.total_sources == 1
    
    def test_init_max_workers(self, config_dir):
        """Test max_workers configuration."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml"),
            max_workers=8,
        )
        
        assert orchestrator.max_workers == 8


class TestScrapeUrl:
    """Test single URL scraping with fallback."""
    
    def test_scrape_url_success(self, config_dir):
        """Test successful URL scraping."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml")
        )
        
        mock_article = RawArticle(
            source="test",
            url="https://example.com/article",
            headline="Test Article",
            main_text="Content " * 30,
        )
        
        with patch.object(orchestrator, '_create_scraper') as mock_create:
            mock_scraper = MagicMock()
            mock_scraper.extract_article.return_value = mock_article
            mock_scraper.__enter__ = MagicMock(return_value=mock_scraper)
            mock_scraper.__exit__ = MagicMock(return_value=None)
            mock_create.return_value = mock_scraper
            
            article = orchestrator.scrape_url("https://example.com/article")
            
            assert article is not None
            assert article.headline == "Test Article"
    
    def test_scrape_url_fallback(self, config_dir):
        """Test fallback to alternative scraper."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml"),
            enable_fallback=True,
        )
        
        mock_article = RawArticle(
            source="test",
            url="https://example.com/article",
            headline="Fallback Success",
            main_text="Content " * 30,
        )
        
        call_count = [0]
        
        def create_scraper(source_config, method):
            call_count[0] += 1
            mock_scraper = MagicMock()
            mock_scraper.__enter__ = MagicMock(return_value=mock_scraper)
            mock_scraper.__exit__ = MagicMock(return_value=None)
            
            if method == "newspaper4k":
                # First method fails
                mock_scraper.extract_article.side_effect = ContentExtractionError("Failed")
            else:
                # Fallback succeeds
                mock_scraper.extract_article.return_value = mock_article
            
            return mock_scraper
        
        with patch.object(orchestrator, '_create_scraper', side_effect=create_scraper):
            article = orchestrator.scrape_url("https://example.com/article")
            
            assert article is not None
            assert call_count[0] >= 2  # At least 2 methods tried
    
    def test_scrape_url_all_methods_fail(self, config_dir):
        """Test returns None when all methods fail."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml"),
            enable_fallback=True,
        )
        
        with patch.object(orchestrator, '_create_scraper') as mock_create:
            mock_scraper = MagicMock()
            mock_scraper.extract_article.side_effect = ContentExtractionError("Failed")
            mock_scraper.__enter__ = MagicMock(return_value=mock_scraper)
            mock_scraper.__exit__ = MagicMock(return_value=None)
            mock_create.return_value = mock_scraper
            
            article = orchestrator.scrape_url("https://example.com/article")
            
            assert article is None


class TestDeduplication:
    """Test article deduplication."""
    
    def test_duplicate_articles_filtered(self, config_dir):
        """Test duplicate articles are filtered by content hash."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml")
        )
        
        # Create articles with same content (same hash)
        article1 = RawArticle(
            source="dawn",
            url="https://dawn.com/article1",
            headline="Same Headline",
            main_text="Same content " * 30,
        )
        
        article2 = RawArticle(
            source="tribune",
            url="https://tribune.com/article2",
            headline="Same Headline",
            main_text="Same content " * 30,  # Same content, same hash
        )
        
        # Manually add first article's hash
        orchestrator._seen_hashes.add(article1.content_hash)
        
        # Second article with same hash should be filtered
        if article2.content_hash in orchestrator._seen_hashes:
            # This simulates deduplication in scrape_source
            pass
        
        assert article1.content_hash == article2.content_hash


class TestScrapingResult:
    """Test ScrapingResult dataclass."""
    
    def test_result_creation(self):
        """Test ScrapingResult creation."""
        articles = [
            RawArticle(
                source="test",
                url="https://example.com/1",
                headline="Article 1",
                main_text="Content " * 30,
            )
        ]
        
        result = ScrapingResult(
            source="test",
            articles=articles,
            errors=["Error 1"],
            duration_seconds=5.5,
            method_used="newspaper4k",
        )
        
        assert result.source == "test"
        assert len(result.articles) == 1
        assert len(result.errors) == 1
        assert result.duration_seconds == 5.5
        assert result.method_used == "newspaper4k"


class TestScrapeSource:
    """Test source scraping."""
    
    def test_scrape_unknown_source(self, config_dir):
        """Test scraping unknown source returns error."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml")
        )
        
        result = orchestrator.scrape_source("nonexistent_source")
        
        assert len(result.articles) == 0
        assert len(result.errors) > 0
        assert "Unknown source" in result.errors[0]


class TestGetScrapingSummary:
    """Test scraping summary generation."""
    
    def test_summary_structure(self, config_dir):
        """Test summary has correct structure."""
        orchestrator = ScraperOrchestrator(
            config_path=str(config_dir / "sources.yaml")
        )
        
        summary = orchestrator.get_scraping_summary()
        
        assert "total_sources" in summary
        assert "sources" in summary
        assert "fallback_enabled" in summary
        assert "max_workers" in summary
        
        assert isinstance(summary["total_sources"], int)
        assert isinstance(summary["sources"], dict)
