"""
Hybrid Scraper Orchestrator for the Saaf Baat news scraping system.

Combines StealthFetcher (curl_cffi) with ContentParser (trafilatura/newspaper4k/readability)
and uses Playwright as a Tier 2 fallback for sites that require JavaScript rendering.

Architecture:
    Tier 1 — URL Discovery:  FeedDiscoverer (RSS) → HTML scrape + regex (fallback)
    Tier 2 — Content Fetch:  StealthFetcher (curl_cffi) → Playwright (session-reused)
    Tier 3 — Content Parse:  ContentParser (trafilatura → newspaper4k → readability)
"""

import re
import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from src.scrapers.network import StealthFetcher
from src.scrapers.parsers import ContentParser
from src.scrapers.dtos import ScrapedArticle
from src.scrapers.feed import FeedDiscoverer
from src.db.models import RawArticle


logger = logging.getLogger(__name__)


class HybridOrchestrator:
    """
    Orchestrates the hybrid scraping pipeline.

    Flow:
    1. URL Discovery: FeedDiscoverer (RSS) with HTML scrape fallback
    2. Content Fetch: StealthFetcher (curl_cffi) with Playwright session-reuse fallback
    3. Content Parse: ContentParser (trafilatura → newspaper4k → readability)
    4. Deduplication: content_hash checked before appending each article

    Example:
        orchestrator = HybridOrchestrator()
        articles = orchestrator.scrape_source(
            source="dawn",
            base_url="https://www.dawn.com",
            sections=["latest-news"],
            feed_url="https://www.dawn.com/feeds/latest-news",
        )
        orchestrator.close()
    """

    # Patterns that indicate article URLs
    ARTICLE_URL_PATTERNS = [
        r"/news/\d+",           # Dawn: /news/12345
        r"/story/\d+",          # Tribune: /story/12345
        r"/\d{4}/\d{2}/\d{2}/", # Date-based: /2026/02/04/
        r"-\d+\.html?$",        # Numeric suffix: article-12345.html
        r"/post/\d+",           # Generic post
        r"/article/\d+",        # Generic article
    ]

    def __init__(
        self,
        stealth_fetcher: Optional[StealthFetcher] = None,
        content_parser: Optional[ContentParser] = None,
        enable_playwright_fallback: bool = True,
        playwright_timeout: int = 30000,
        scroll_depth: int = 3,
    ):
        self._stealth_fetcher = stealth_fetcher or StealthFetcher()
        self._content_parser = content_parser or ContentParser()
        self._enable_playwright_fallback = enable_playwright_fallback
        self._playwright_timeout = playwright_timeout
        self.scroll_depth = scroll_depth

        # Playwright session (reused across calls)
        self._playwright = None
        self._browser = None

        # Statistics
        self._articles_scraped = 0
        self._playwright_fallback_count = 0

    def scrape_url(
        self,
        url: str,
        source: str = "unknown",
    ) -> Optional[RawArticle]:
        """
        Scrape a single article URL and return RawArticle.

        Args:
            url: The article URL to scrape
            source: Source identifier (e.g., "dawn", "tribune")

        Returns:
            RawArticle on success, None on failure
        """
        # Step 1: Try StealthFetcher
        html = self._stealth_fetcher.fetch(url)

        scraped_article: Optional[ScrapedArticle] = None

        if html:
            # Step 2: Parse with ContentParser
            scraped_article = self._content_parser.parse(html, url)

            if scraped_article and scraped_article.is_valid():
                # Success with stealth fetch
                self._articles_scraped += 1
                return scraped_article.to_raw_article(url=url, source=source)

        # Step 3: Playwright fallback
        if self._enable_playwright_fallback:
            logger.info(f"Falling back to Playwright for: {url}")
            self._playwright_fallback_count += 1

            playwright_html = self._fetch_with_playwright(url)
            if playwright_html:
                scraped_article = self._content_parser.parse(playwright_html, url)

                if scraped_article and scraped_article.is_valid():
                    self._articles_scraped += 1
                    return scraped_article.to_raw_article(url=url, source=source)

        # All methods failed
        logger.warning(f"Failed to scrape: {url}")
        return None

    def scrape_source(
        self,
        source: str,
        base_url: str,
        sections: List[str],
        max_articles: int = 50,
        feed_url: Optional[str] = None,
    ) -> List[RawArticle]:
        """
        Scrape articles from a news source.

        URL discovery order:
        1. If feed_url provided, try FeedDiscoverer (RSS/Atom)
        2. If feed returns no URLs, fall back to HTML section scraping

        Each scraped article is deduplicated by content_hash before appending.
        """
        articles: List[RawArticle] = []
        seen_urls: set = set()
        seen_hashes: set = set()

        # Tier 1: RSS feed discovery
        article_urls: List[str] = []
        if feed_url:
            article_urls = FeedDiscoverer(feed_url).discover()
            if article_urls:
                logger.info(f"Feed discovery returned {len(article_urls)} URLs for {source}")

        if article_urls:
            # Use feed-discovered URLs directly
            for article_url in article_urls:
                if len(articles) >= max_articles:
                    break
                if article_url in seen_urls:
                    continue
                seen_urls.add(article_url)

                article = self.scrape_url(article_url, source=source)
                if article and article.content_hash not in seen_hashes:
                    seen_hashes.add(article.content_hash)
                    articles.append(article)
        else:
            # Fallback: HTML section scraping
            section_urls = self._build_section_urls(base_url, sections)

            for section_url in section_urls:
                if len(articles) >= max_articles:
                    break

                section_html = self._stealth_fetcher.fetch(section_url)
                if not section_html:
                    continue

                extracted_urls = self._extract_article_urls(section_html, base_url, source)

                for article_url in extracted_urls:
                    if len(articles) >= max_articles:
                        break
                    if article_url in seen_urls:
                        continue
                    seen_urls.add(article_url)

                    article = self.scrape_url(article_url, source=source)
                    if article and article.content_hash not in seen_hashes:
                        seen_hashes.add(article.content_hash)
                        articles.append(article)

        return articles

    def _get_browser(self):
        """Lazy-initialize and return the reused Chromium browser."""
        if self._browser is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        return self._browser

    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """
        Fetch page HTML using a session-reused Playwright browser with stealth.

        Browser is launched once and reused across calls. Each call gets a
        fresh context + page, scrolls to trigger lazy-loaded content, then
        closes only the page and context (not the browser).
        """
        try:
            browser = self._get_browser()
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            stealth = Stealth()
            stealth.apply_stealth_sync(page)

            page.goto(url, timeout=self._playwright_timeout)
            page.wait_for_load_state("networkidle", timeout=self._playwright_timeout)

            # Scroll to trigger lazy-loaded content
            for _ in range(self.scroll_depth):
                page.evaluate("window.scrollBy(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(100)

            html = page.content()

            page.close()
            context.close()
            return html

        except Exception as e:
            logger.error(f"Playwright fetch failed for {url}: {e}")
            return None

    def close(self) -> None:
        """Shut down the reused Playwright browser and session."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def _build_section_urls(self, base_url: str, sections: List[str]) -> List[str]:
        """
        Build full section URLs from base URL and section paths.

        Handles:
        - Section paths like "latest-news" -> "https://site.com/latest-news"
        - Full URLs passed through unchanged
        - Trailing slashes on base URL

        Args:
            base_url: Base URL of the site (e.g., "https://www.dawn.com")
            sections: List of section paths or full URLs

        Returns:
            List of full section URLs
        """
        urls = []
        base_url = base_url.rstrip("/")

        for section in sections:
            if section.startswith("http://") or section.startswith("https://"):
                # Already a full URL
                urls.append(section)
            else:
                # Join with base URL
                section = section.lstrip("/")
                full_url = f"{base_url}/{section}"
                urls.append(full_url)

        return urls

    def _extract_article_urls(
        self,
        html: str,
        base_url: str,
        source: str,
    ) -> List[str]:
        """
        Extract article URLs from a section/listing page.

        Args:
            html: HTML of the section page
            base_url: Base URL for resolving relative links
            source: Source identifier for source-specific patterns

        Returns:
            List of unique article URLs
        """
        urls: List[str] = []
        seen: set = set()

        try:
            soup = BeautifulSoup(html, "lxml")

            for link in soup.find_all("a", href=True):
                href = link["href"]

                # Resolve relative URLs
                if not href.startswith("http"):
                    href = urljoin(base_url, href)

                # Check if it looks like an article URL
                if self._is_article_url(href):
                    if href not in seen:
                        seen.add(href)
                        urls.append(href)

        except Exception as e:
            logger.error(f"Error extracting URLs: {e}")

        return urls

    def _is_article_url(self, url: str) -> bool:
        """
        Check if a URL looks like an article URL.

        Args:
            url: URL to check

        Returns:
            True if URL matches article patterns
        """
        for pattern in self.ARTICLE_URL_PATTERNS:
            if re.search(pattern, url):
                return True
        return False

    def get_stats(self) -> Dict:
        """
        Get scraping statistics.

        Returns:
            Dictionary with scraping statistics
        """
        return {
            "articles_scraped": self._articles_scraped,
            "playwright_fallback_count": self._playwright_fallback_count,
            "fetcher_stats": self._stealth_fetcher.get_stats(),
        }

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._articles_scraped = 0
        self._playwright_fallback_count = 0
        self._stealth_fetcher.reset_stats()
