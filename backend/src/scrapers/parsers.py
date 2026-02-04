"""
Content Parser Ensemble for the Hybrid Scraping Architecture.

Implements the "Smart Waterfall" parsing strategy:
1. Trafilatura (primary) - Quality check: text > 200 chars + date
2. Newspaper4k (metadata specialist) - Merge author/date if trafilatura missed
3. Readability-lxml (safety net) - Fallback for messy HTML
"""

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import trafilatura
from trafilatura import extract as trafilatura_extract
from trafilatura.metadata import extract_metadata as trafilatura_extract_metadata
from newspaper import Article as NewspaperArticle
from readability import Document as ReadabilityDocument
from bs4 import BeautifulSoup

from src.scrapers.dtos import ScrapedArticle


class ContentParser:
    """
    Parser ensemble that combines trafilatura, newspaper4k, and readability-lxml.

    Uses a "Smart Waterfall" strategy:
    1. Try trafilatura first (best for clean text extraction)
    2. If trafilatura misses metadata, supplement with newspaper4k
    3. If both fail to get sufficient text, use readability-lxml as safety net

    Example:
        parser = ContentParser()
        article = parser.parse(html, "https://www.dawn.com/news/12345")
        if article.is_valid():
            # Use the article
            pass
    """

    # Quality threshold for text content (characters)
    MIN_TEXT_LENGTH = 200

    def __init__(self, min_text_length: int = 200):
        """
        Initialize ContentParser.

        Args:
            min_text_length: Minimum text length to consider extraction successful (default: 200)
        """
        self.MIN_TEXT_LENGTH = min_text_length

    def parse(self, html: str, url: str) -> ScrapedArticle:
        """
        Parse HTML and extract article content using the parser ensemble.

        Args:
            html: Raw HTML string to parse
            url: Original URL (used for metadata and source_domain)

        Returns:
            ScrapedArticle with extracted content (may be empty if all parsers fail)
        """
        source_domain = urlparse(url).netloc

        # Track which parsers were used
        parsers_used: List[str] = []

        # Initialize result containers
        title = ""
        text = ""
        authors: List[str] = []
        date_published: Optional[datetime] = None

        # === ATTEMPT 1: Trafilatura (Primary) ===
        traf_title, traf_text, traf_authors, traf_date = self._try_trafilatura(html, url)

        if traf_text and len(traf_text) >= self.MIN_TEXT_LENGTH:
            # Trafilatura got good text
            title = traf_title or ""
            text = traf_text
            authors = traf_authors
            date_published = traf_date
            parsers_used.append("trafilatura")

            # If trafilatura got text but missed date, try newspaper4k for date
            if not date_published:
                np_title, np_text, np_authors, np_date = self._try_newspaper4k(html, url)
                if np_date:
                    date_published = np_date
                    parsers_used.append("newspaper4k_date")
                # Also grab authors if trafilatura missed them
                if not authors and np_authors:
                    authors = np_authors
                    if "newspaper4k_date" not in parsers_used:
                        parsers_used.append("newspaper4k_metadata")

        else:
            # === ATTEMPT 2: Newspaper4k (Fallback) ===
            np_title, np_text, np_authors, np_date = self._try_newspaper4k(html, url)

            if np_text and len(np_text) >= self.MIN_TEXT_LENGTH:
                title = np_title or traf_title or ""
                text = np_text
                authors = np_authors or traf_authors
                date_published = np_date or traf_date
                parsers_used.append("newspaper4k")

            else:
                # === ATTEMPT 3: Readability-lxml (Safety Net) ===
                read_title, read_text = self._try_readability(html)

                if read_text and len(read_text) >= self.MIN_TEXT_LENGTH:
                    title = read_title or np_title or traf_title or ""
                    text = read_text
                    # Readability doesn't extract authors/dates, use from earlier attempts
                    authors = np_authors or traf_authors or []
                    date_published = np_date or traf_date
                    parsers_used.append("readability")

                else:
                    # All parsers failed - use best available
                    title = traf_title or np_title or read_title or ""
                    text = traf_text or np_text or read_text or ""
                    authors = traf_authors or np_authors or []
                    date_published = traf_date or np_date
                    parsers_used.append("none")

        # Build parser_used string
        parser_used = "+".join(parsers_used) if parsers_used else "none"

        return ScrapedArticle(
            title=title,
            text=text,
            authors=authors,
            date_published=date_published,
            source_domain=source_domain,
            parser_used=parser_used,
        )

    def _try_trafilatura(
        self, html: str, url: str
    ) -> Tuple[str, str, List[str], Optional[datetime]]:
        """
        Attempt extraction using trafilatura.

        Returns:
            Tuple of (title, text, authors, date_published)
        """
        title = ""
        text = ""
        authors: List[str] = []
        date_published: Optional[datetime] = None

        try:
            # Extract main text content
            text = trafilatura_extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_recall=True,
            ) or ""

            # Extract metadata
            metadata = trafilatura_extract_metadata(html)

            if metadata:
                title = metadata.title or ""

                # Parse date
                if metadata.date:
                    date_published = self._parse_date(metadata.date)

                # Parse author
                if metadata.author:
                    authors = self._parse_authors(metadata.author)

        except Exception:
            # Trafilatura failed, return empty
            pass

        return title, text, authors, date_published

    def _try_newspaper4k(
        self, html: str, url: str
    ) -> Tuple[str, str, List[str], Optional[datetime]]:
        """
        Attempt extraction using newspaper4k.

        Returns:
            Tuple of (title, text, authors, date_published)
        """
        title = ""
        text = ""
        authors: List[str] = []
        date_published: Optional[datetime] = None

        try:
            article = NewspaperArticle(url)
            article.set_html(html)
            article.parse()

            title = article.title or ""
            text = article.text or ""
            authors = list(article.authors) if article.authors else []
            date_published = article.publish_date

        except Exception:
            # Newspaper4k failed, return empty
            pass

        return title, text, authors, date_published

    def _try_readability(self, html: str) -> Tuple[str, str]:
        """
        Attempt extraction using readability-lxml.

        Returns:
            Tuple of (title, text) - readability doesn't extract authors/dates
        """
        title = ""
        text = ""

        try:
            doc = ReadabilityDocument(html)
            title = doc.title() or ""

            # Get summary and strip HTML tags
            summary_html = doc.summary() or ""
            text = self._strip_html_tags(summary_html)

        except Exception:
            # Readability failed, return empty
            pass

        return title, text

    def _strip_html_tags(self, html: str) -> str:
        """
        Strip HTML tags from string, keeping only text content.

        Args:
            html: HTML string to clean

        Returns:
            Plain text with HTML tags removed
        """
        try:
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(separator=" ", strip=True)
            # Normalize whitespace
            text = re.sub(r"\s+", " ", text).strip()
            return text
        except Exception:
            # Fallback: simple regex
            return re.sub(r"<[^>]+>", "", html).strip()

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string into datetime object.

        Handles various formats including ISO 8601.

        Args:
            date_str: Date string to parse

        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None

        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",      # ISO 8601 with timezone
            "%Y-%m-%dT%H:%M:%SZ",        # ISO 8601 UTC
            "%Y-%m-%dT%H:%M:%S",         # ISO 8601 without timezone
            "%Y-%m-%d %H:%M:%S",         # Common datetime
            "%Y-%m-%d",                  # Date only
            "%B %d, %Y",                 # "February 04, 2026"
            "%d %B %Y",                  # "04 February 2026"
            "%b %d, %Y",                 # "Feb 04, 2026"
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                return self._normalize_to_utc(parsed)
            except ValueError:
                continue

        # Try dateutil as fallback
        try:
            from dateutil import parser as dateutil_parser
            parsed = dateutil_parser.parse(date_str)
            return self._normalize_to_utc(parsed)
        except Exception:
            pass

        return None

    def _normalize_to_utc(self, dt: datetime) -> datetime:
        """
        Normalize datetime to UTC.

        If datetime is naive, assume PKT (UTC+5) before converting to UTC.
        """
        if dt.tzinfo is None:
            pkt = timezone(timedelta(hours=5))
            dt = dt.replace(tzinfo=pkt)
        return dt.astimezone(timezone.utc)

    def _parse_authors(self, author_str: str) -> List[str]:
        """
        Parse author string into list of author names.

        Handles comma-separated, "and"-separated, and single authors.

        Args:
            author_str: Author string to parse

        Returns:
            List of author names
        """
        if not author_str:
            return []

        # Remove common prefixes
        author_str = re.sub(r"^(By|by|BY)\s+", "", author_str.strip())

        # Split by comma or "and"
        authors = re.split(r",\s*|\s+and\s+", author_str)

        # Clean up each author
        authors = [a.strip() for a in authors if a.strip()]

        return authors
