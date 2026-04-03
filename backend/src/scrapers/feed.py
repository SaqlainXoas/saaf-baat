"""RSS/Atom feed URL discovery — Tier 1 of URL discovery pipeline."""

import logging
from typing import List, Optional

import feedparser

from src.utils.urls import host_allowed_for_base

logger = logging.getLogger(__name__)


class FeedDiscoverer:
    """Discover article URLs from RSS/Atom feeds.

    Used as the primary URL discovery method before falling back
    to HTML scraping + regex extraction.
    """

    def __init__(self, feed_url: str, base_url: Optional[str] = None):
        self.feed_url = feed_url
        self.base_url = base_url

    def discover(self) -> List[str]:
        """Parse feed and return unique article URLs.

        Returns empty list on any failure — caller falls back to HTML scraping.
        """
        try:
            feed = feedparser.parse(self.feed_url)
            seen = set()
            urls = []
            for entry in feed.entries:
                link = getattr(entry, "link", None)
                if not link:
                    continue
                if self.base_url and not host_allowed_for_base(link, self.base_url):
                    continue
                if link not in seen:
                    seen.add(link)
                    urls.append(link)
            return urls
        except Exception as e:
            logger.warning(f"Feed discovery failed for {self.feed_url}: {e}")
            return []
