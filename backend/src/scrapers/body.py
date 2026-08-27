"""
Lazy article-body fetch.

Tier A publishers ship the full article in RSS, and Tier B articles exist only
to answer "is anyone else covering this?" — a headline answers that. So a page
fetch is needed for exactly one case: an article that has been *selected* for
the brief while carrying no usable body.

That makes this the rare path, not the hot one: roughly a dozen fetches per
run instead of one per article. It keeps ``StealthFetcher``'s rate limiting and
browser-realistic headers, and extracts with trafilatura alone — the parser
ensemble and the Playwright fallback are gone.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import trafilatura

from src.db.models import RawArticle
from src.scrapers.feeds import BODY_FULL, DEFAULT_FULL_TEXT_MIN_CHARS
from src.scrapers.network import StealthFetcher

logger = logging.getLogger(__name__)


@dataclass
class BodyFetchStats:
    attempted: int = 0
    hydrated: int = 0
    failed: int = 0


class ArticleBodyFetcher:
    """Fetch and extract a single article body, on demand."""

    def __init__(
        self,
        stealth_fetcher: Optional[StealthFetcher] = None,
        *,
        min_chars: int = DEFAULT_FULL_TEXT_MIN_CHARS,
    ):
        self._fetcher = stealth_fetcher or StealthFetcher()
        self.min_chars = int(min_chars)
        self.stats = BodyFetchStats()

    def fetch_body(self, url: str) -> Optional[str]:
        """Return extracted article text, or None if it is missing or thin."""
        try:
            html = self._fetcher.fetch(url)
        except Exception as exc:
            logger.warning("Body fetch failed for %s: %s", url, exc)
            return None
        if not html:
            return None

        try:
            text = trafilatura.extract(html, include_comments=False) or ""
        except Exception as exc:
            logger.warning("Body extraction failed for %s: %s", url, exc)
            return None

        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < self.min_chars:
            return None
        return text

    def needs_body(self, article: RawArticle) -> bool:
        metadata = article.metadata or {}
        if str(metadata.get("body_status") or "") == BODY_FULL:
            return False
        return len(article.main_text or "") < self.min_chars

    def hydrate(self, article: RawArticle) -> bool:
        """
        Fill in ``article.main_text`` from the live page when it is thin.

        Returns True when the article was improved. The article's
        ``content_hash`` is deliberately left alone: it is the row's dedup
        identity and must stay stable across a body upgrade.
        """
        if not self.needs_body(article):
            return False

        self.stats.attempted += 1
        text = self.fetch_body(str(article.url))
        if not text:
            self.stats.failed += 1
            logger.info("Lazy body fetch produced nothing usable for %s", article.url)
            return False

        article.main_text = text
        article.metadata = {
            **(article.metadata or {}),
            "body_status": BODY_FULL,
            "body_source": "lazy_fetch",
        }
        self.stats.hydrated += 1
        return True

    def close(self) -> None:
        """Present for symmetry with the retired scraper; nothing to release."""
        return None
