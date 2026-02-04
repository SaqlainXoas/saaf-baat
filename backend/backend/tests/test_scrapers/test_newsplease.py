"""
Unit tests for News-please scraper.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.newsplease_scraper import NewsPleaseScraaper
from src.scrapers.base import ContentExtractionError, InvalidURLError
from src.db.models import RawArticle


class TestNewsPleaseInit:
    """Test News-please scraper initialization."""
    
    def test_default_initialization(self):
        """Test scraper initializes with default values."""
        scraper = NewsPleaseScraaper(source="dawn")
        
        assert scraper.source == "dawn"
        assert scraper.base_url is None
    
    def test_custom_initialization(self):
        """Test scraper initializes with custom values."""
        scraper = NewsPleaseScraaper(
            source="express",
            base_url="https://tribune.com.pk",
            rate_limit=2.0,
        )
        
        assert scraper.source == "express"
        assert scraper.base_url == "https://tribune.com.pk"
        assert scraper.rate_limit == 2.0


class TestArticleExtraction:
    """Test article extraction functionality."""
    
    def test_extract_article_success(self):
        """Test successful article extraction."""
        scraper = NewsPleaseScraaper(source="dawn", rate_limit=0)
        
        # Mock news-please result
        mock_article = MagicMock()
        mock_article.title = "Test Headline for Article"
        mock_article.maintext = "This is test content " * 20
        mock_article.authors = ["Test Author"]
        mock_article.date_publish = datetime(2026, 2, 3, 10, 0, 0)
        
        with patch("src.scrapers.newsplease_scraper.NewsPlease") as MockNewsPlease:
            MockNewsPlease.from_url.return_value = mock_article
            
            article = scraper.extract_article("https://dawn.com/news/12345")
            
            assert article.source == "dawn"
            assert article.url == "https://dawn.com/news/12345"
            assert article.headline == "Test Headline for Article"
            assert "test content" in article.main_text
            assert article.author == "Test Author"
            assert article.publish_date == datetime(2026, 2, 3, 10, 0, 0)
    
    def test_extract_article_no_headline(self):
        """Test extraction fails when no headline found."""
        scraper = NewsPleaseScraaper(source="dawn", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.title = ""
        mock_article.maintext = "Content here"
        mock_article.authors = []
        mock_article.date_publish = None
        
        with patch("src.scrapers.newsplease_scraper.NewsPlease") as MockNewsPlease:
            MockNewsPlease.from_url.return_value = mock_article
            
            with pytest.raises(ContentExtractionError):
                scraper.extract_article("https://dawn.com/news/12345")
    
    def test_extract_article_insufficient_content(self):
        """Test extraction fails when content too short."""
        scraper = NewsPleaseScraaper(source="dawn", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.title = "Valid Headline"
        mock_article.maintext = "Short"  # Too short
        mock_article.authors = []
        mock_article.date_publish = None
        
        with patch("src.scrapers.newsplease_scraper.NewsPlease") as MockNewsPlease:
            MockNewsPlease.from_url.return_value = mock_article
            
            with pytest.raises(ContentExtractionError):
                scraper.extract_article("https://dawn.com/news/12345")
    
    def test_invalid_url_rejected(self):
        """Test invalid URL format is rejected."""
        scraper = NewsPleaseScraaper(source="dawn", rate_limit=0)
        
        with pytest.raises(InvalidURLError):
            scraper.extract_article("not-a-valid-url")
    
    def test_news_please_returns_none(self):
        """Test handling when news-please returns None."""
        scraper = NewsPleaseScraaper(source="dawn", rate_limit=0)
        
        with patch("src.scrapers.newsplease_scraper.NewsPlease") as MockNewsPlease:
            MockNewsPlease.from_url.return_value = None
            
            with pytest.raises(ContentExtractionError, match="returned None"):
                scraper.extract_article("https://dawn.com/news/12345")


class TestTextCleaning:
    """Test text cleaning methods."""
    
    def test_whitespace_normalization(self):
        """Test multiple spaces are collapsed."""
        scraper = NewsPleaseScraaper(source="test", rate_limit=0)
        
        result = scraper._clean_text("Test    multiple   spaces")
        assert result == "Test multiple spaces"
    
    def test_newline_handling(self):
        """Test newlines are handled."""
        scraper = NewsPleaseScraaper(source="test", rate_limit=0)
        
        result = scraper._clean_text("Line1\n\n\nLine2")
        assert "Line1" in result and "Line2" in result
    
    def test_none_handling(self):
        """Test None input returns None."""
        scraper = NewsPleaseScraaper(source="test", rate_limit=0)
        
        result = scraper._clean_text(None)
        assert result is None


class TestAuthorExtraction:
    """Test author extraction."""
    
    def test_author_extraction_from_list(self):
        """Test author is extracted from list."""
        scraper = NewsPleaseScraaper(source="test", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.authors = ["John Doe", "Jane Smith"]
        
        result = scraper._extract_author(mock_article)
        assert result == "John Doe"
    
    def test_empty_authors(self):
        """Test empty authors returns None."""
        scraper = NewsPleaseScraaper(source="test", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.authors = []
        
        result = scraper._extract_author(mock_article)
        assert result is None


class TestPublishDateExtraction:
    """Test publish date extraction."""
    
    def test_date_extraction(self):
        """Test date is extracted."""
        scraper = NewsPleaseScraaper(source="test", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.date_publish = datetime(2026, 1, 15, 12, 0, 0)
        
        result = scraper._extract_publish_date(mock_article)
        assert result == datetime(2026, 1, 15, 12, 0, 0)
    
    def test_no_date_returns_none(self):
        """Test missing date returns None."""
        scraper = NewsPleaseScraaper(source="test", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.date_publish = None
        
        result = scraper._extract_publish_date(mock_article)
        assert result is None


class TestGetArticleUrls:
    """Test URL extraction from section pages."""
    
    def test_get_urls_from_section(self):
        """Test extracting article URLs from section page."""
        scraper = NewsPleaseScraaper(
            source="dawn", 
            base_url="https://dawn.com",
            rate_limit=0
        )
        
        html_content = """
        <html>
            <body>
                <a href="/news/12345/article-one">Article One</a>
                <a href="/news/12346/article-two">Article Two</a>
                <a href="/about">About</a>
            </body>
        </html>
        """
        
        # Mock fetch_page method (not _fetch_html)
        with patch.object(scraper, 'fetch_page', return_value=html_content):
            urls = scraper.get_article_urls("https://dawn.com/world")
            
            # Should find article URLs
            assert any("/news/" in url for url in urls)
    
    def test_empty_section_page(self):
        """Test handling empty section page."""
        scraper = NewsPleaseScraaper(
            source="dawn",
            base_url="https://dawn.com", 
            rate_limit=0
        )
        
        with patch.object(scraper, 'fetch_page', return_value="<html></html>"):
            urls = scraper.get_article_urls("https://dawn.com/section")
            assert urls == []


class TestUrlDetection:
    """Test article URL detection logic."""
    
    @pytest.fixture
    def scraper(self):
        return NewsPleaseScraaper(source="test", rate_limit=0)
    
    def test_article_url_patterns_detected(self, scraper):
        """Test article-like URLs are detected."""
        article_urls = [
            "/news/123/some-headline",
            "/story/45678/another-headline",
            "/article/999/third-headline",
            "/2024/01/15/headline",
        ]
        
        for url in article_urls:
            assert scraper._is_article_url(url), f"Should detect: {url}"
    
    def test_non_article_urls_filtered(self, scraper):
        """Test non-article URLs are filtered."""
        non_article_urls = [
            "/about",
            "/contact",
            "/category/world",
            "/tag/politics",
            "/search?q=test",
            "/login",
            "/subscribe",
        ]
        
        for url in non_article_urls:
            assert not scraper._is_article_url(url), f"Should filter: {url}"
