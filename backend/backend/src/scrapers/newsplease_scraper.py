"""
News-please based scraper as fallback.

Used when newspaper4k fails or returns incomplete data.
Provides same interface for interchangeability.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from newsplease import NewsPlease

from src.db.models import RawArticle
from src.scrapers.base import (
    BaseScraper,
    ContentExtractionError,
    InvalidURLError,
    ScrapingError,
)


logger = logging.getLogger(__name__)


class NewsPleaseScraaper(BaseScraper):
    """
    Fallback scraper using news-please library.
    
    Used when newspaper4k fails. News-please has different
    extraction algorithms that may work better for some sites.
    """
    
    def __init__(
        self,
        source: str,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        """
        Initialize news-please scraper.
        
        Args:
            source: News source name
            base_url: Base URL of the news site
            **kwargs: Additional args passed to BaseScraper
        """
        super().__init__(source=source, **kwargs)
        self.base_url = base_url
    
    def extract_article(self, url: str) -> RawArticle:
        """
        Extract article content using news-please.
        
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
            
            # Enforce rate limit
            self._enforce_rate_limit()
            
            # Extract using news-please
            article = NewsPlease.from_url(url, timeout=self.timeout)
            self._request_count += 1
            
            if article is None:
                raise ContentExtractionError(f"news-please returned None: {url}")
            
            # Extract data
            headline = self._clean_text(article.title)
            main_text = self._clean_text(article.maintext)
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
        """Check if URL looks like an article URL."""
        # Skip common non-article patterns
        skip_patterns = [
            r"^#",
            r"^javascript:",
            r"^mailto:",
            r"/category/",
            r"/tag/",
            r"/author/",
            r"/page/\d+",
            r"/search",
            r"/login",
            r"/register",
            r"/contact",
            r"/about",
            r"/privacy",
            r"/terms",
            r"\.pdf$",
            r"\.jpg$",
            r"\.png$",
            r"facebook\.com",
            r"twitter\.com",
            r"instagram\.com",
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # Check for article-like patterns
        article_patterns = [
            r"/news/\d+",
            r"/\d{4}/\d{2}/\d{2}/",
            r"article",
            r"/story/",
            r"/post/",
            r"-\d+\.html?$",
            r"-\d+/?$",
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
    
    def _extract_author(self, article: Any) -> Optional[str]:
        """Extract and clean author name."""
        authors = getattr(article, "authors", None)
        if not authors:
            return None
        
        if isinstance(authors, list) and authors:
            author = authors[0].strip()
        elif isinstance(authors, str):
            author = authors.strip()
        else:
            return None
        
        # Remove common prefixes
        author = re.sub(r"^(by|written by|reported by)[\s:]+", "", author, flags=re.IGNORECASE)
        
        # Remove email-like patterns
        author = re.sub(r"\S+@\S+\.\S+", "", author).strip()
        
        return author if author and len(author) > 2 else None
    
    def _extract_publish_date(self, article: Any) -> Optional[datetime]:
        """Extract publish date from article."""
        date_published = getattr(article, "date_publish", None)
        if date_published:
            if isinstance(date_published, datetime):
                return date_published
            try:
                return datetime.fromisoformat(str(date_published))
            except (ValueError, TypeError):
                pass
        return None
