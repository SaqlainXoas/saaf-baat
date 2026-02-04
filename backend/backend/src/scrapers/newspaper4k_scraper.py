"""
Newspaper4k-based scraper for static news sites.

Primary scraper that handles most Pakistani news sources.
Uses newspaper4k library for article extraction.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from newspaper import Article as NewspaperArticle
from newspaper import Config as NewspaperConfig

from src.db.models import RawArticle
from src.scrapers.base import (
    BaseScraper,
    ContentExtractionError,
    InvalidURLError,
    ScrapingError,
)


logger = logging.getLogger(__name__)


class Newspaper4kScraper(BaseScraper):
    """
    Scraper using newspaper4k library.
    
    Works well for static news sites with standard HTML structure.
    Handles:
    - Article extraction (headline, body, author, date)
    - Image extraction
    - Encoding issues (Urdu/English mixed content)
    """
    
    def __init__(
        self,
        source: str,
        base_url: Optional[str] = None,
        language: str = "en",
        **kwargs: Any,
    ):
        """
        Initialize Newspaper4k scraper.
        
        Args:
            source: News source name
            base_url: Base URL of the news site
            language: Primary language (en, ur)
            **kwargs: Additional args passed to BaseScraper
        """
        super().__init__(source=source, **kwargs)
        self.base_url = base_url
        self.language = language
        
        # Configure newspaper4k
        self._config = NewspaperConfig()
        self._config.browser_user_agent = self._get_user_agent()
        self._config.request_timeout = self.timeout
        self._config.fetch_images = False  # Skip images for speed
        self._config.memoize_articles = False
        self._config.language = language
    
    def extract_article(self, url: str) -> RawArticle:
        """
        Extract article content using newspaper4k.
        
        Args:
            url: Article URL
            
        Returns:
            RawArticle with extracted content
            
        Raises:
            ContentExtractionError: Failed to extract content
            InvalidURLError: URL is not valid
        """
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise InvalidURLError(f"Invalid URL format: {url}")
            if parsed.scheme not in ("http", "https"):
                raise InvalidURLError(f"Invalid URL scheme: {url}")
            
            # Update config with fresh user agent
            self._config.browser_user_agent = self._get_user_agent()
            
            # Fetch and parse article
            article = NewspaperArticle(url, config=self._config)
            
            # Enforce rate limit before download
            self._enforce_rate_limit()
            
            article.download()
            self._request_count += 1
            
            article.parse()
            
            # Extract data
            headline = self._clean_text(article.title)
            main_text = self._clean_text(article.text)
            author = self._extract_author(article)
            publish_date = self._extract_publish_date(article)
            
            # Validate extracted content
            if not headline:
                raise ContentExtractionError(f"No headline found: {url}")
            if not main_text or len(main_text) < 50:
                raise ContentExtractionError(f"Insufficient content: {url}")
            
            return RawArticle(
                source=self.source,
                url=url,
                headline=headline,
                main_text=main_text,
                author=author,
                publish_date=publish_date,
            )
            
        except InvalidURLError:
            raise
        except ContentExtractionError:
            raise
        except Exception as e:
            self._error_count += 1
            logger.error(f"Error extracting {url}: {e}")
            raise ContentExtractionError(f"Failed to extract article: {url} - {e}")
    
    def get_article_urls(self, section_url: str) -> List[str]:
        """
        Extract article URLs from a section page.
        
        Uses BeautifulSoup to find links that look like articles.
        
        Args:
            section_url: Section/category page URL
            
        Returns:
            List of article URLs
        """
        try:
            from bs4 import BeautifulSoup
            
            html = self.fetch_page(section_url)
            soup = BeautifulSoup(html, "lxml")
            
            urls: List[str] = []
            
            # Find all links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                
                # Skip non-article links
                if self._is_article_url(href):
                    # Make absolute URL
                    full_url = urljoin(section_url, href)
                    if full_url not in urls:
                        urls.append(full_url)
            
            logger.info(f"Found {len(urls)} article URLs from {section_url}")
            return urls
            
        except Exception as e:
            logger.error(f"Failed to get URLs from {section_url}: {e}")
            return []
    
    def _is_article_url(self, url: str) -> bool:
        """
        Check if URL looks like an article URL.
        
        Filters out navigation, category, and other non-article URLs.
        """
        # Skip common non-article patterns
        skip_patterns = [
            r"^#",                           # Anchors
            r"^javascript:",                 # JavaScript links
            r"^mailto:",                     # Email links
            r"/category/",                   # Category pages
            r"/tag/",                        # Tag pages
            r"/author/",                     # Author pages
            r"/page/\d+",                    # Pagination
            r"/search",                      # Search pages
            r"/login",                       # Login pages
            r"/register",                    # Registration
            r"/contact",                     # Contact pages
            r"/about",                       # About pages
            r"/privacy",                     # Privacy policy
            r"/terms",                       # Terms of service
            r"\.pdf$",                       # PDF files
            r"\.jpg$",                       # Images
            r"\.png$",                       # Images
            r"facebook\.com",                # Social links
            r"twitter\.com",                 # Social links
            r"instagram\.com",               # Social links
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # Check for article-like patterns
        article_patterns = [
            r"/news/\d+",                    # /news/12345
            r"/\d{4}/\d{2}/\d{2}/",          # /2024/02/03/
            r"article",                      # Contains 'article'
            r"/story/",                      # /story/
            r"/post/",                       # /post/
            r"-\d+\.html?$",                 # ending in -12345.html
            r"-\d+/?$",                      # ending in -12345/
        ]
        
        for pattern in article_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        
        # If URL has significant path depth, might be article
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) >= 2:
            return True
        
        return False
    
    def _clean_text(self, text: Optional[str]) -> Optional[str]:
        """Clean and normalize extracted text."""
        if not text:
            return None
        
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text).strip()
        
        # Remove common boilerplate
        boilerplate_patterns = [
            r"^(advertisement|sponsored|promoted)[\s\-:]+",
            r"(read more|continue reading|related articles?)[\s:]*$",
            r"^\d+ (min|minute)s? read\s*",
            r"share (on|this article):?.*$",
        ]
        
        for pattern in boilerplate_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        
        return text if text else None
    
    def _extract_author(self, article: NewspaperArticle) -> Optional[str]:
        """Extract and clean author name."""
        authors = article.authors
        if not authors:
            return None
        
        # Take first author, clean it
        author = authors[0].strip()
        
        # Remove common prefixes
        author = re.sub(r"^(by|written by|reported by)[\s:]+", "", author, flags=re.IGNORECASE)
        
        # Remove email-like patterns
        author = re.sub(r"\S+@\S+\.\S+", "", author).strip()
        
        return author if author and len(author) > 2 else None
    
    def _extract_publish_date(self, article: NewspaperArticle) -> Optional[datetime]:
        """Extract publish date from article."""
        if article.publish_date:
            if isinstance(article.publish_date, datetime):
                return article.publish_date
            try:
                return datetime.fromisoformat(str(article.publish_date))
            except (ValueError, TypeError):
                pass
        return None
