"""
Base scraper class for Saaf Baat news scraping system.

Provides common functionality:
- Rate limiting
- Retry logic
- User agent rotation
- Error handling
"""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx

from src.db.models import RawArticle


logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    """Base exception for scraping errors."""
    pass


class InvalidURLError(ScrapingError):
    """URL is invalid or not reachable."""
    pass


class RateLimitError(ScrapingError):
    """Rate limit exceeded."""
    pass


class ContentExtractionError(ScrapingError):
    """Failed to extract content from page."""
    pass


class TimeoutError(ScrapingError):
    """Request timed out."""
    pass


# Common user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.
    
    Provides:
    - Rate limiting between requests
    - Automatic retry on failures
    - User agent rotation
    - Common error handling
    
    Subclasses must implement:
    - extract_article(url) -> RawArticle
    - get_article_urls(section_url) -> List[str]
    """
    
    def __init__(
        self,
        source: str,
        rate_limit: float = 1.0,
        max_retries: int = 3,
        timeout: float = 30.0,
        rotate_user_agent: bool = True,
    ):
        """
        Initialize base scraper.
        
        Args:
            source: Name of the news source (e.g., "dawn", "tribune")
            rate_limit: Minimum seconds between requests
            max_retries: Number of retries on transient failures
            timeout: Request timeout in seconds
            rotate_user_agent: Whether to rotate user agents
        """
        self.source = source
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.timeout = timeout
        self.rotate_user_agent = rotate_user_agent
        
        self._last_request_time: float = 0.0
        self._user_agent_index: int = 0
        self._request_count: int = 0
        self._error_count: int = 0
        
        # HTTP client with connection pooling
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        """Lazy-initialize HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                http2=True,
            )
        return self._client
    
    def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._client is not None:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "BaseScraper":
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
    
    def _get_user_agent(self) -> str:
        """Get next user agent for rotation."""
        if self.rotate_user_agent:
            self._user_agent_index = (self._user_agent_index + 1) % len(USER_AGENTS)
            return USER_AGENTS[self._user_agent_index]
        return USER_AGENTS[0]
    
    def _enforce_rate_limit(self) -> None:
        """Wait if necessary to respect rate limit."""
        if self.rate_limit <= 0:
            return
        
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with user agent."""
        return {
            "User-Agent": self._get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ur;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    
    def fetch_page(self, url: str) -> str:
        """
        Fetch page content with retry logic and rate limiting.
        
        Args:
            url: URL to fetch
            
        Returns:
            HTML content as string
            
        Raises:
            InvalidURLError: URL is not reachable
            TimeoutError: Request timed out after retries
            ScrapingError: Other errors
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.max_retries):
            try:
                self._enforce_rate_limit()
                
                response = self.client.get(url, headers=self._get_headers())
                self._request_count += 1
                
                if response.status_code == 429:
                    # Rate limited by server
                    wait_time = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited by server, waiting {wait_time}s")
                    time.sleep(wait_time)
                    raise RateLimitError(f"Rate limited: {url}")
                
                if response.status_code == 404:
                    raise InvalidURLError(f"URL not found: {url}")
                
                if response.status_code >= 400:
                    raise ScrapingError(f"HTTP {response.status_code}: {url}")
                
                logger.debug(f"Fetched {url} (attempt {attempt + 1})")
                return response.text
                
            except httpx.TimeoutException as e:
                last_error = e
                self._error_count += 1
                logger.warning(f"Timeout on {url} (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 2)  # Exponential backoff
                    
            except httpx.ConnectError as e:
                last_error = e
                self._error_count += 1
                logger.warning(f"Connection error on {url} (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                    
            except (InvalidURLError, RateLimitError):
                raise
                
            except Exception as e:
                last_error = e
                self._error_count += 1
                logger.warning(f"Error fetching {url}: {e} (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 2)
        
        if isinstance(last_error, httpx.TimeoutException):
            raise TimeoutError(f"Timeout after {self.max_retries} attempts: {url}")
        raise ScrapingError(f"Failed after {self.max_retries} attempts: {url} - {last_error}")
    
    @abstractmethod
    def extract_article(self, url: str) -> RawArticle:
        """
        Extract article content from URL.
        
        Args:
            url: Article URL to scrape
            
        Returns:
            RawArticle with extracted content
            
        Raises:
            ContentExtractionError: Failed to extract content
            InvalidURLError: URL is not valid
        """
        pass
    
    @abstractmethod
    def get_article_urls(self, section_url: str) -> List[str]:
        """
        Get list of article URLs from a section/category page.
        
        Args:
            section_url: URL of news section (e.g., "https://dawn.com/latest")
            
        Returns:
            List of article URLs
        """
        pass
    
    def scrape_section(self, section_url: str, max_articles: int = 50) -> List[RawArticle]:
        """
        Scrape all articles from a section page.
        
        Args:
            section_url: URL of news section
            max_articles: Maximum articles to scrape
            
        Returns:
            List of successfully scraped articles
        """
        articles: List[RawArticle] = []
        
        try:
            urls = self.get_article_urls(section_url)
            logger.info(f"Found {len(urls)} article URLs in {section_url}")
            
            for url in urls[:max_articles]:
                try:
                    article = self.extract_article(url)
                    articles.append(article)
                    logger.debug(f"Scraped: {article.headline[:50]}...")
                except Exception as e:
                    logger.warning(f"Failed to scrape {url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get URLs from {section_url}: {e}")
        
        logger.info(f"Successfully scraped {len(articles)} articles from {section_url}")
        return articles
    
    def validate_article(self, article: RawArticle) -> bool:
        """
        Validate extracted article has required content.
        
        Args:
            article: Article to validate
            
        Returns:
            True if article is valid
        """
        if not article.headline or len(article.headline) < 10:
            return False
        if not article.main_text or len(article.main_text) < 100:
            return False
        if not article.url:
            return False
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scraper statistics."""
        return {
            "source": self.source,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "success_rate": (
                (self._request_count - self._error_count) / self._request_count
                if self._request_count > 0
                else 0.0
            ),
        }
