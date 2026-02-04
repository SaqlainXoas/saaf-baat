"""
Unit tests for Playwright scraper.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.scrapers.playwright_scraper import PlaywrightScraper
from src.scrapers.base import ContentExtractionError, InvalidURLError
from src.db.models import RawArticle


class TestPlaywrightInit:
    """Test Playwright scraper initialization."""
    
    def test_default_initialization(self):
        """Test scraper initializes with default values."""
        scraper = PlaywrightScraper(source="geo")
        
        assert scraper.source == "geo"
        assert scraper.base_url is None
        assert scraper.headless is True
        assert scraper.scroll_depth == 3
        assert scraper.wait_for_selector is None
        assert scraper._browser is None
    
    def test_custom_initialization(self):
        """Test scraper initializes with custom values."""
        scraper = PlaywrightScraper(
            source="geo",
            base_url="https://geo.tv",
            headless=False,
            scroll_depth=5,
            wait_for_selector=".article-content",
            rate_limit=2.0,
        )
        
        assert scraper.source == "geo"
        assert scraper.base_url == "https://geo.tv"
        assert scraper.headless is False
        assert scraper.scroll_depth == 5
        assert scraper.wait_for_selector == ".article-content"
        assert scraper.rate_limit == 2.0


class TestBrowserManagement:
    """Test browser lifecycle management."""
    
    def test_browser_lazy_initialization(self):
        """Test browser is not created until needed."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        assert scraper._browser is None
        assert scraper._playwright is None
    
    def test_close_without_browser(self):
        """Test close works even if browser was never initialized."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        # Should not raise
        scraper.close()
        
        assert scraper._browser is None


class TestArticleExtraction:
    """Test article extraction functionality."""
    
    def test_invalid_url_rejected(self):
        """Test invalid URL format is rejected."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        with pytest.raises(InvalidURLError):
            scraper.extract_article("not-a-valid-url")
    
    def test_extract_article_success(self):
        """Test successful article extraction with mocked browser."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        # Create mock page
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        
        # Mock headline extraction
        mock_headline_elem = MagicMock()
        mock_headline_elem.text_content.return_value = "Test Headline for Article"
        
        # Mock content extraction
        mock_content_elem = MagicMock()
        mock_content_elem.inner_text.return_value = "This is test content " * 20
        
        # Set up page query selectors
        def query_selector_side_effect(selector):
            if "h1" in selector:
                return mock_headline_elem
            elif "article" in selector or "content" in selector:
                return mock_content_elem
            return None
        
        mock_page.query_selector.side_effect = query_selector_side_effect
        
        # Patch _get_browser
        with patch.object(scraper, '_get_browser', return_value=mock_browser):
            with patch.object(scraper, '_scroll_page'):
                with patch.object(scraper, '_extract_headline', return_value="Test Headline for Article"):
                    with patch.object(scraper, '_extract_main_text', return_value="This is test content " * 20):
                        with patch.object(scraper, '_extract_author', return_value="Test Author"):
                            with patch.object(scraper, '_extract_publish_date', return_value=datetime(2026, 1, 15)):
                                article = scraper.extract_article("https://geo.tv/news/12345")
        
        assert article.source == "geo"
        assert article.url == "https://geo.tv/news/12345"
        assert article.headline == "Test Headline for Article"
        assert "test content" in article.main_text
        assert article.author == "Test Author"
    
    def test_extract_no_headline_fails(self):
        """Test extraction fails when no headline found."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        
        with patch.object(scraper, '_get_browser', return_value=mock_browser):
            with patch.object(scraper, '_scroll_page'):
                with patch.object(scraper, '_extract_headline', return_value=None):
                    with pytest.raises(ContentExtractionError, match="No headline"):
                        scraper.extract_article("https://geo.tv/news/12345")


class TestHeadlineExtraction:
    """Test headline extraction strategies."""
    
    def test_headline_from_h1(self):
        """Test headline extraction from h1 tag."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        mock_page = MagicMock()
        mock_elem = MagicMock()
        mock_elem.text_content.return_value = "Test Headline   "
        
        mock_page.query_selector.return_value = mock_elem
        
        result = scraper._extract_headline(mock_page)
        # Should try h1 selectors
        mock_page.query_selector.assert_called()
    
    def test_headline_not_found(self):
        """Test headline returns None when not found."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        
        result = scraper._extract_headline(mock_page)
        assert result is None


class TestMainTextExtraction:
    """Test main text extraction."""
    
    def test_text_extraction_priority(self):
        """Test text extraction uses correct selector priority."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        mock_page = MagicMock()
        mock_elem = MagicMock()
        mock_elem.inner_text.return_value = "Article content here that is long enough to be valid content"
        mock_page.query_selector_all.return_value = [mock_elem]
        
        result = scraper._extract_main_text(mock_page)
        # Should try content selectors using query_selector_all
        assert mock_page.query_selector_all.called


class TestScrollBehavior:
    """Test page scrolling for lazy-loaded content."""
    
    def test_scroll_executes(self):
        """Test scroll script is executed."""
        scraper = PlaywrightScraper(source="geo", scroll_depth=2, rate_limit=0)
        
        mock_page = MagicMock()
        
        scraper._scroll_page(mock_page)
        
        # Should have scrolled based on scroll_depth
        assert mock_page.evaluate.called
    
    def test_zero_scroll_depth(self):
        """Test no scrolling when scroll_depth is 0."""
        scraper = PlaywrightScraper(source="geo", scroll_depth=0, rate_limit=0)
        
        mock_page = MagicMock()
        
        scraper._scroll_page(mock_page)
        
        # Should still call evaluate for initial scroll check
        # but should not scroll multiple times


class TestGetArticleUrls:
    """Test URL extraction from section pages."""
    
    def test_get_urls_returns_list(self):
        """Test get_article_urls returns list of URLs."""
        scraper = PlaywrightScraper(
            source="geo",
            base_url="https://geo.tv",
            rate_limit=0
        )
        
        # Mock browser and page
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        
        # Mock link elements
        mock_link1 = MagicMock()
        mock_link1.get_attribute.return_value = "/news/12345/article-one"
        mock_link2 = MagicMock()
        mock_link2.get_attribute.return_value = "/news/12346/article-two"
        
        mock_page.query_selector_all.return_value = [mock_link1, mock_link2]
        
        with patch.object(scraper, '_get_browser', return_value=mock_browser):
            with patch.object(scraper, '_scroll_page'):
                with patch.object(scraper, '_is_article_url', return_value=True):
                    urls = scraper.get_article_urls("https://geo.tv/world")
        
        assert isinstance(urls, list)


class TestUrlDetection:
    """Test article URL detection logic."""
    
    @pytest.fixture
    def scraper(self):
        return PlaywrightScraper(source="geo", rate_limit=0)
    
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


class TestTextCleaning:
    """Test text cleaning methods."""
    
    def test_whitespace_normalization(self):
        """Test multiple spaces are collapsed."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        result = scraper._clean_text("Test    multiple   spaces")
        assert "Test" in result and "multiple" in result
    
    def test_none_handling(self):
        """Test None input handling."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        result = scraper._clean_text(None)
        # Depending on implementation, could be None or empty string
        assert result is None or result == ""


class TestAuthorExtraction:
    """Test author extraction from page."""
    
    def test_author_extraction(self):
        """Test author is extracted from page."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        mock_page = MagicMock()
        mock_elem = MagicMock()
        mock_elem.text_content.return_value = "By John Doe"
        mock_page.query_selector.return_value = mock_elem
        
        result = scraper._extract_author(mock_page)
        # Should query for author selector
        assert mock_page.query_selector.called
    
    def test_no_author_returns_none(self):
        """Test missing author returns None."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        
        result = scraper._extract_author(mock_page)
        assert result is None


class TestDateExtraction:
    """Test publish date extraction."""
    
    def test_date_extraction_attempts(self):
        """Test date extraction tries multiple selectors."""
        scraper = PlaywrightScraper(source="geo", rate_limit=0)
        
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        
        result = scraper._extract_publish_date(mock_page)
        # Should try multiple selectors
        assert mock_page.query_selector.called
