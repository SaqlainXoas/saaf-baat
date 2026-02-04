"""
Playwright-based scraper for JavaScript-heavy sites.

Used for sites that require JavaScript execution to render content.
Examples: Geo News, some modern news sites with infinite scroll.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

from src.db.models import RawArticle
from src.scrapers.base import (
    BaseScraper,
    ContentExtractionError,
    InvalidURLError,
    ScrapingError,
    TimeoutError,
)


logger = logging.getLogger(__name__)


class PlaywrightScraper(BaseScraper):
    """
    Scraper using Playwright for JavaScript-heavy sites.
    
    Features:
    - Full JavaScript execution
    - Scroll behavior for lazy-loaded content
    - Screenshot capability for debugging
    - Headless mode for efficiency
    """
    
    def __init__(
        self,
        source: str,
        base_url: Optional[str] = None,
        headless: bool = True,
        scroll_depth: int = 3,
        wait_for_selector: Optional[str] = None,
        **kwargs: Any,
    ):
        """
        Initialize Playwright scraper.
        
        Args:
            source: News source name
            base_url: Base URL of the news site
            headless: Run browser in headless mode
            scroll_depth: Number of scroll actions for lazy loading
            wait_for_selector: CSS selector to wait for before extraction
            **kwargs: Additional args passed to BaseScraper
        """
        super().__init__(source=source, **kwargs)
        self.base_url = base_url
        self.headless = headless
        self.scroll_depth = scroll_depth
        self.wait_for_selector = wait_for_selector
        
        self._playwright: Any = None
        self._browser: Optional[Browser] = None
    
    def _get_browser(self) -> Browser:
        """Lazy-initialize Playwright browser."""
        if self._browser is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ]
            )
            logger.info("Playwright browser started")
        return self._browser
    
    def close(self) -> None:
        """Close browser and Playwright resources."""
        super().close()
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        logger.info("Playwright resources closed")
    
    def extract_article(self, url: str) -> RawArticle:
        """
        Extract article content using Playwright.
        
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
            
            browser = self._get_browser()
            context = browser.new_context(
                user_agent=self._get_user_agent(),
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            
            try:
                # Navigate to page
                page.goto(url, timeout=int(self.timeout * 1000), wait_until="domcontentloaded")
                self._request_count += 1
                
                # Wait for content to load
                if self.wait_for_selector:
                    try:
                        page.wait_for_selector(self.wait_for_selector, timeout=10000)
                    except PlaywrightTimeout:
                        logger.warning(f"Timeout waiting for selector: {self.wait_for_selector}")
                
                # Scroll for lazy-loaded content
                self._scroll_page(page)
                
                # Extract content
                headline = self._extract_headline(page)
                main_text = self._extract_main_text(page)
                author = self._extract_author(page)
                publish_date = self._extract_publish_date(page)
                
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
                
            finally:
                page.close()
                context.close()
            
        except InvalidURLError:
            raise
        except ContentExtractionError:
            raise
        except PlaywrightTimeout as e:
            self._error_count += 1
            raise TimeoutError(f"Playwright timeout: {url} - {e}")
        except Exception as e:
            self._error_count += 1
            logger.error(f"Error extracting {url}: {e}")
            raise ContentExtractionError(f"Failed to extract article: {url} - {e}")
    
    def get_article_urls(self, section_url: str) -> List[str]:
        """
        Extract article URLs from a section page using Playwright.
        
        Args:
            section_url: Section/category page URL
            
        Returns:
            List of article URLs
        """
        try:
            # Enforce rate limit
            self._enforce_rate_limit()
            
            browser = self._get_browser()
            context = browser.new_context(
                user_agent=self._get_user_agent(),
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            
            try:
                page.goto(section_url, timeout=int(self.timeout * 1000), wait_until="domcontentloaded")
                self._request_count += 1
                
                # Scroll for lazy-loaded content
                self._scroll_page(page)
                
                # Get all links
                links = page.query_selector_all("a[href]")
                
                urls: List[str] = []
                for link in links:
                    href = link.get_attribute("href")
                    if href and self._is_article_url(href):
                        full_url = urljoin(section_url, href)
                        if full_url not in urls:
                            urls.append(full_url)
                
                logger.info(f"Found {len(urls)} article URLs from {section_url}")
                return urls
                
            finally:
                page.close()
                context.close()
            
        except Exception as e:
            logger.error(f"Failed to get URLs from {section_url}: {e}")
            return []
    
    def _scroll_page(self, page: Page) -> None:
        """Scroll page to trigger lazy-loaded content."""
        for i in range(self.scroll_depth):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)  # Wait for content to load
            logger.debug(f"Scroll {i + 1}/{self.scroll_depth}")
    
    def _extract_headline(self, page: Page) -> Optional[str]:
        """Extract headline from page."""
        # Try common headline selectors
        selectors = [
            "h1.article-title",
            "h1.post-title",
            "h1.entry-title",
            "article h1",
            ".article-header h1",
            ".story-headline",
            "h1",
        ]
        
        for selector in selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    text = element.inner_text()
                    if text and len(text) > 10:
                        return self._clean_text(text)
            except Exception:
                continue
        
        # Fallback to title tag
        try:
            title = page.title()
            if title:
                # Remove site name from title
                title = re.sub(r"\s*[\|\-–—]\s*[^|\-–—]+$", "", title)
                return self._clean_text(title)
        except Exception:
            pass
        
        return None
    
    def _extract_main_text(self, page: Page) -> Optional[str]:
        """Extract main article text from page."""
        # Try common article body selectors
        selectors = [
            "article .content",
            "article .article-body",
            ".article-content",
            ".post-content",
            ".entry-content",
            ".story-body",
            "article p",
            ".article-text",
        ]
        
        for selector in selectors:
            try:
                elements = page.query_selector_all(selector)
                if elements:
                    texts = []
                    for el in elements:
                        text = el.inner_text()
                        if text and len(text) > 20:
                            texts.append(text)
                    
                    if texts:
                        combined = "\n\n".join(texts)
                        if len(combined) > 100:
                            return self._clean_text(combined)
            except Exception:
                continue
        
        # Fallback: try to get all paragraph text
        try:
            paragraphs = page.query_selector_all("p")
            texts = []
            for p in paragraphs:
                text = p.inner_text()
                if text and len(text) > 50:
                    texts.append(text)
            
            if texts:
                return self._clean_text("\n\n".join(texts))
        except Exception:
            pass
        
        return None
    
    def _extract_author(self, page: Page) -> Optional[str]:
        """Extract author from page."""
        selectors = [
            ".author-name",
            ".byline",
            ".post-author",
            "[rel='author']",
            ".article-author",
            "meta[name='author']",
        ]
        
        for selector in selectors:
            try:
                if selector.startswith("meta"):
                    element = page.query_selector(selector)
                    if element:
                        author = element.get_attribute("content")
                        if author:
                            return self._clean_author(author)
                else:
                    element = page.query_selector(selector)
                    if element:
                        author = element.inner_text()
                        if author:
                            return self._clean_author(author)
            except Exception:
                continue
        
        return None
    
    def _extract_publish_date(self, page: Page) -> Optional[datetime]:
        """Extract publish date from page."""
        # Try meta tags first
        meta_selectors = [
            "meta[property='article:published_time']",
            "meta[name='publish-date']",
            "meta[name='date']",
            "time[datetime]",
        ]
        
        for selector in meta_selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    date_str = (
                        element.get_attribute("content")
                        or element.get_attribute("datetime")
                    )
                    if date_str:
                        return self._parse_date(date_str)
            except Exception:
                continue
        
        # Try date elements
        date_selectors = [
            ".publish-date",
            ".post-date",
            ".article-date",
            ".entry-date",
        ]
        
        for selector in date_selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    date_str = element.inner_text()
                    if date_str:
                        return self._parse_date(date_str)
            except Exception:
                continue
        
        return None
    
    def _is_article_url(self, url: str) -> bool:
        """Check if URL looks like an article URL."""
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
        
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) >= 2:
            return True
        
        return False
    
    def _clean_text(self, text: Optional[str]) -> Optional[str]:
        """Clean and normalize extracted text."""
        if not text:
            return None
        
        text = re.sub(r"\s+", " ", text).strip()
        
        boilerplate_patterns = [
            r"^(advertisement|sponsored|promoted)[\s\-:]+",
            r"(read more|continue reading|related articles?)[\s:]*$",
            r"^\d+ (min|minute)s? read\s*",
            r"share (on|this article):?.*$",
        ]
        
        for pattern in boilerplate_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        
        return text if text else None
    
    def _clean_author(self, author: str) -> Optional[str]:
        """Clean author name."""
        author = re.sub(r"^(by|written by|reported by)[\s:]+", "", author, flags=re.IGNORECASE)
        author = re.sub(r"\S+@\S+\.\S+", "", author).strip()
        return author if author and len(author) > 2 else None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        date_str = date_str.strip()
        
        # Common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str[:len(fmt)], fmt)
            except (ValueError, IndexError):
                continue
        
        return None
    
    def take_screenshot(self, url: str, path: str) -> None:
        """
        Take screenshot of page for debugging.
        
        Args:
            url: URL to screenshot
            path: File path to save screenshot
        """
        browser = self._get_browser()
        context = browser.new_context(
            user_agent=self._get_user_agent(),
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        
        try:
            page.goto(url, timeout=int(self.timeout * 1000))
            page.screenshot(path=path, full_page=True)
            logger.info(f"Screenshot saved: {path}")
        finally:
            page.close()
            context.close()
