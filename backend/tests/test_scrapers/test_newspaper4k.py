"""
Unit tests for Newspaper4k scraper.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.newspaper4k_scraper import Newspaper4kScraper
from src.scrapers.base import ContentExtractionError, InvalidURLError
from src.db.models import RawArticle


class TestNewspaper4kInit:
    """Test Newspaper4k scraper initialization."""
    
    def test_default_initialization(self):
        """Test scraper initializes with default values."""
        scraper = Newspaper4kScraper(source="dawn")
        
        assert scraper.source == "dawn"
        assert scraper.language == "en"
        assert scraper.base_url is None
    
    def test_custom_initialization(self):
        """Test scraper initializes with custom values."""
        scraper = Newspaper4kScraper(
            source="express",
            base_url="https://tribune.com.pk",
            language="ur",
            rate_limit=2.0,
        )
        
        assert scraper.source == "express"
        assert scraper.base_url == "https://tribune.com.pk"
        assert scraper.language == "ur"
        assert scraper.rate_limit == 2.0


class TestArticleExtraction:
    """Test article extraction functionality."""
    
    def test_extract_article_success(self):
        """Test successful article extraction."""
        scraper = Newspaper4kScraper(source="dawn", rate_limit=0)
        
        # Mock newspaper Article
        mock_article = MagicMock()
        mock_article.title = "Test Headline for Article"
        mock_article.text = "This is test content " * 20
        mock_article.authors = ["Test Author"]
        mock_article.publish_date = datetime(2026, 2, 3, 10, 0, 0)
        
        with patch("src.scrapers.newspaper4k_scraper.NewspaperArticle") as MockArticle:
            MockArticle.return_value = mock_article
            
            article = scraper.extract_article("https://dawn.com/news/12345")
            
            assert article.source == "dawn"
            assert article.url == "https://dawn.com/news/12345"
            assert article.headline == "Test Headline for Article"
            assert "test content" in article.main_text
            assert article.author == "Test Author"
            assert article.publish_date == datetime(2026, 2, 3, 10, 0, 0)
    
    def test_extract_article_no_headline(self):
        """Test extraction fails when no headline found."""
        scraper = Newspaper4kScraper(source="dawn", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.title = ""
        mock_article.text = "Content here"
        mock_article.authors = []
        mock_article.publish_date = None
        
        with patch("src.scrapers.newspaper4k_scraper.NewspaperArticle") as MockArticle:
            MockArticle.return_value = mock_article
            
            with pytest.raises(ContentExtractionError):
                scraper.extract_article("https://dawn.com/news/12345")
    
    def test_extract_article_insufficient_content(self):
        """Test extraction fails when content too short."""
        scraper = Newspaper4kScraper(source="dawn", rate_limit=0)
        
        mock_article = MagicMock()
        mock_article.title = "Valid Headline"
        mock_article.text = "Short"  # Too short
        mock_article.authors = []
        mock_article.publish_date = None
        
        with patch("src.scrapers.newspaper4k_scraper.NewspaperArticle") as MockArticle:
            MockArticle.return_value = mock_article
            
            with pytest.raises(ContentExtractionError):
                scraper.extract_article("https://dawn.com/news/12345")
    
    def test_invalid_url_rejected(self):
        """Test invalid URL format is rejected."""
        scraper = Newspaper4kScraper(source="dawn", rate_limit=0)
        
        with pytest.raises(InvalidURLError):
            scraper.extract_article("not-a-valid-url")
        
        with pytest.raises(InvalidURLError):
            scraper.extract_article("ftp://invalid-scheme.com")


class TestUrlDetection:
    """Test article URL detection logic."""
    
    @pytest.fixture
    def scraper(self):
        return Newspaper4kScraper(source="test", rate_limit=0)
    
    def test_article_url_patterns_detected(self, scraper):
        """Test article-like URLs are detected."""
        article_urls = [
            "https://dawn.com/news/12345",
            "https://tribune.com/2026/02/03/article-title",
            "https://geo.tv/story/test-article",
            "https://news.com/post/article-name",
            "https://example.com/section/subsection/article-123.html",
            "https://example.com/section/article-456/",
        ]
        
        for url in article_urls:
            assert scraper._is_article_url(url) is True, f"Should detect: {url}"
    
    def test_non_article_urls_filtered(self, scraper):
        """Test non-article URLs are filtered out."""
        non_article_urls = [
            "#anchor",
            "javascript:void(0)",
            "mailto:test@example.com",
            "/category/politics",
            "/tag/economy",
            "/author/john-doe",
            "/page/2",
            "/search?q=test",
            "/login",
            "/about",
            "https://facebook.com/share",
            "https://twitter.com/intent",
            "/document.pdf",
            "/image.jpg",
        ]
        
        for url in non_article_urls:
            assert scraper._is_article_url(url) is False, f"Should filter: {url}"


class TestTextCleaning:
    """Test text cleaning functionality."""
    
    @pytest.fixture
    def scraper(self):
        return Newspaper4kScraper(source="test")
    
    def test_whitespace_normalization(self, scraper):
        """Test extra whitespace is normalized."""
        text = "This   is   a   test\n\nwith   extra    spaces"
        cleaned = scraper._clean_text(text)
        assert cleaned == "This is a test with extra spaces"
    
    def test_boilerplate_removal(self, scraper):
        """Test common boilerplate is removed."""
        texts = [
            ("Advertisement: This is content", "This is content"),
            ("Sponsored: Product review", "Product review"),
            ("Content here Read More", "Content here"),
            ("3 min read Article content", "Article content"),
        ]
        
        for original, expected in texts:
            cleaned = scraper._clean_text(original)
            assert cleaned == expected, f"Failed for: {original}"
    
    def test_none_handling(self, scraper):
        """Test None input returns None."""
        assert scraper._clean_text(None) is None
        assert scraper._clean_text("") is None


class TestAuthorExtraction:
    """Test author extraction and cleaning."""
    
    @pytest.fixture
    def scraper(self):
        return Newspaper4kScraper(source="test")
    
    def test_author_extraction(self, scraper):
        """Test basic author extraction."""
        mock_article = MagicMock()
        mock_article.authors = ["John Doe"]
        
        author = scraper._extract_author(mock_article)
        assert author == "John Doe"
    
    def test_author_prefix_removal(self, scraper):
        """Test 'by' prefix is removed."""
        mock_article = MagicMock()
        mock_article.authors = ["By Jane Smith"]
        
        author = scraper._extract_author(mock_article)
        assert author == "Jane Smith"
    
    def test_empty_authors(self, scraper):
        """Test empty authors returns None."""
        mock_article = MagicMock()
        mock_article.authors = []
        
        author = scraper._extract_author(mock_article)
        assert author is None
    
    def test_email_removal(self, scraper):
        """Test email addresses are removed from author."""
        mock_article = MagicMock()
        mock_article.authors = ["John Doe john@example.com"]
        
        author = scraper._extract_author(mock_article)
        assert author == "John Doe"
        assert "@" not in author


class TestGetArticleUrls:
    """Test article URL extraction from section pages."""
    
    def test_get_urls_from_section(self):
        """Test extracting URLs from section page."""
        scraper = Newspaper4kScraper(source="test", rate_limit=0)
        
        html = """
        <html>
        <body>
            <a href="https://example.com/news/12345">Article 1</a>
            <a href="/2026/02/03/article-2">Article 2</a>
            <a href="#section">Anchor</a>
            <a href="/category/politics">Category</a>
        </body>
        </html>
        """
        
        with patch.object(scraper, 'fetch_page', return_value=html):
            urls = scraper.get_article_urls("https://example.com/news")
        
        assert len(urls) == 2
        assert "https://example.com/news/12345" in urls
        assert "https://example.com/2026/02/03/article-2" in urls
    
    def test_duplicate_urls_removed(self):
        """Test duplicate URLs are removed."""
        scraper = Newspaper4kScraper(source="test", rate_limit=0)
        
        html = """
        <html>
        <body>
            <a href="https://example.com/news/12345">Article 1</a>
            <a href="https://example.com/news/12345">Same Article</a>
            <a href="https://example.com/news/12345">Again</a>
        </body>
        </html>
        """
        
        with patch.object(scraper, 'fetch_page', return_value=html):
            urls = scraper.get_article_urls("https://example.com/news")
        
        assert len(urls) == 1
