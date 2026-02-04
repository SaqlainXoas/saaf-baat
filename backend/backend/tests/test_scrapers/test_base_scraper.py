"""
Unit tests for base scraper class.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, PropertyMock

import httpx
import pytest

from src.scrapers.base import (
    BaseScraper,
    ScrapingError,
    InvalidURLError,
    RateLimitError,
    ContentExtractionError,
    TimeoutError,
    USER_AGENTS,
)
from src.db.models import RawArticle


# Concrete implementation for testing abstract base class
class ConcreteScraper(BaseScraper):
    """Concrete scraper for testing BaseScraper functionality."""
    
    def extract_article(self, url: str) -> RawArticle:
        return RawArticle(
            source=self.source,
            url=url,
            headline="Test Headline",
            main_text="Test content " * 20,  # Sufficient length
        )
    
    def get_article_urls(self, section_url: str):
        return ["https://example.com/article1", "https://example.com/article2"]


class TestBaseScraperInit:
    """Test BaseScraper initialization."""
    
    def test_default_initialization(self):
        """Test scraper initializes with default values."""
        scraper = ConcreteScraper(source="test")
        
        assert scraper.source == "test"
        assert scraper.rate_limit == 1.0
        assert scraper.max_retries == 3
        assert scraper.timeout == 30.0
        assert scraper.rotate_user_agent is True
    
    def test_custom_initialization(self):
        """Test scraper initializes with custom values."""
        scraper = ConcreteScraper(
            source="test",
            rate_limit=2.0,
            max_retries=5,
            timeout=60.0,
            rotate_user_agent=False,
        )
        
        assert scraper.rate_limit == 2.0
        assert scraper.max_retries == 5
        assert scraper.timeout == 60.0
        assert scraper.rotate_user_agent is False
    
    def test_context_manager(self):
        """Test scraper works as context manager."""
        with ConcreteScraper(source="test") as scraper:
            assert scraper.source == "test"


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limiting_enforced(self):
        """Ensure scraper respects rate limits."""
        scraper = ConcreteScraper(source="test", rate_limit=0.5)
        
        # Mock the client to avoid actual requests
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>test</html>"
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        scraper._client = mock_client
        
        start = time.time()
        scraper.fetch_page("https://example.com/page1")
        scraper.fetch_page("https://example.com/page2")
        duration = time.time() - start
        
        assert duration >= 0.5  # Should wait at least rate_limit seconds
    
    def test_no_rate_limit_when_zero(self):
        """Test no delay when rate limit is 0."""
        scraper = ConcreteScraper(source="test", rate_limit=0.0)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>test</html>"
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        scraper._client = mock_client
        
        start = time.time()
        scraper.fetch_page("https://example.com/page1")
        scraper.fetch_page("https://example.com/page2")
        duration = time.time() - start
        
        assert duration < 0.3  # Should be fast without rate limit


class TestUserAgentRotation:
    """Test user agent rotation."""
    
    def test_user_agent_rotation_enabled(self):
        """Verify user agent is rotated when enabled."""
        scraper = ConcreteScraper(source="test", rotate_user_agent=True)
        
        agents = set()
        for _ in range(len(USER_AGENTS) * 2):
            agents.add(scraper._get_user_agent())
        
        # Should have cycled through multiple agents
        assert len(agents) > 1
    
    def test_user_agent_rotation_disabled(self):
        """Verify user agent stays same when rotation disabled."""
        scraper = ConcreteScraper(source="test", rotate_user_agent=False)
        
        agent1 = scraper._get_user_agent()
        agent2 = scraper._get_user_agent()
        agent3 = scraper._get_user_agent()
        
        assert agent1 == agent2 == agent3


class TestRetryLogic:
    """Test automatic retry on failures."""
    
    def test_retry_on_timeout(self):
        """Test automatic retry on network timeout."""
        scraper = ConcreteScraper(source="test", max_retries=3, rate_limit=0)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>success</html>"
        
        mock_client = MagicMock()
        # Fail twice, succeed on third
        mock_client.get.side_effect = [
            httpx.TimeoutException("timeout"),
            httpx.TimeoutException("timeout"),
            mock_response,
        ]
        scraper._client = mock_client
        
        result = scraper.fetch_page("https://example.com")
        assert result == "<html>success</html>"
        assert mock_client.get.call_count == 3
    
    def test_raises_after_max_retries(self):
        """Test raises TimeoutError after max retries exhausted."""
        scraper = ConcreteScraper(source="test", max_retries=3, rate_limit=0)
        
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        scraper._client = mock_client
        
        with pytest.raises(TimeoutError):
            scraper.fetch_page("https://example.com")
        
        assert mock_client.get.call_count == 3
    
    def test_retry_on_connection_error(self):
        """Test retry on connection errors."""
        scraper = ConcreteScraper(source="test", max_retries=2, rate_limit=0)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>success</html>"
        
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            httpx.ConnectError("connection failed"),
            mock_response,
        ]
        scraper._client = mock_client
        
        result = scraper.fetch_page("https://example.com")
        assert result == "<html>success</html>"


class TestHTTPStatusHandling:
    """Test HTTP status code handling."""
    
    def test_404_raises_invalid_url_error(self):
        """Test 404 response raises InvalidURLError."""
        scraper = ConcreteScraper(source="test", rate_limit=0)
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        scraper._client = mock_client
        
        with pytest.raises(InvalidURLError):
            scraper.fetch_page("https://example.com/not-found")
    
    def test_429_rate_limit_handling(self):
        """Test 429 rate limit response is handled."""
        scraper = ConcreteScraper(source="test", rate_limit=0, max_retries=2)
        
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"Retry-After": "1"}
        
        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.text = "<html>success</html>"
        
        mock_client = MagicMock()
        mock_client.get.side_effect = [mock_response_429, mock_response_200]
        scraper._client = mock_client
        
        # Should raise RateLimitError on first try
        with pytest.raises(RateLimitError):
            scraper.fetch_page("https://example.com")
    
    def test_500_error_handling(self):
        """Test 5xx server errors are handled."""
        scraper = ConcreteScraper(source="test", rate_limit=0, max_retries=1)
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        scraper._client = mock_client
        
        with pytest.raises(ScrapingError):
            scraper.fetch_page("https://example.com")


class TestArticleValidation:
    """Test article validation."""
    
    def test_valid_article(self):
        """Test validation passes for valid article."""
        scraper = ConcreteScraper(source="test")
        
        article = RawArticle(
            source="test",
            url="https://example.com/article",
            headline="Valid Headline Here",
            main_text="This is valid content " * 10,
        )
        
        assert scraper.validate_article(article) is True
    
    def test_invalid_short_headline(self):
        """Test validation fails for short headline."""
        scraper = ConcreteScraper(source="test")
        
        # Create article with short headline but valid main_text
        article = RawArticle(
            source="test",
            url="https://example.com/article",
            headline="Short",
            main_text="This is valid content " * 10,
        )
        
        assert scraper.validate_article(article) is False
    
    def test_invalid_short_content_validation(self):
        """Test validation method catches short content."""
        scraper = ConcreteScraper(source="test")
        
        # We can't create an article with short main_text due to model validation,
        # so test the validate_article logic directly with a mock
        mock_article = MagicMock()
        mock_article.headline = "Valid Headline Here"
        mock_article.main_text = "Short"  # Too short
        mock_article.url = "https://example.com/article"
        
        assert scraper.validate_article(mock_article) is False


class TestScraperStats:
    """Test scraper statistics tracking."""
    
    def test_stats_tracking(self):
        """Test request and error counting."""
        scraper = ConcreteScraper(source="test", rate_limit=0)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>test</html>"
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        scraper._client = mock_client
        
        scraper.fetch_page("https://example.com/1")
        scraper.fetch_page("https://example.com/2")
        
        stats = scraper.get_stats()
        assert stats["source"] == "test"
        assert stats["request_count"] == 2
        assert stats["error_count"] == 0
        assert stats["success_rate"] == 1.0
    
    def test_error_stats(self):
        """Test error statistics are tracked."""
        scraper = ConcreteScraper(source="test", rate_limit=0, max_retries=1)
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        scraper._client = mock_client
        
        try:
            scraper.fetch_page("https://example.com")
        except InvalidURLError:
            pass
        
        stats = scraper.get_stats()
        assert stats["request_count"] == 1
