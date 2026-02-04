"""
Data Transfer Objects for the Hybrid Scraping Architecture.

ScrapedArticle is the unified output from the parser ensemble,
designed to be converted to RawArticle for database storage.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from src.db.models import RawArticle


@dataclass
class ScrapedArticle:
    """
    Unified article representation from the parser ensemble.

    This DTO captures the output from trafilatura, newspaper4k, or readability-lxml
    parsers and provides conversion to RawArticle for database storage.

    Attributes:
        title: Article headline/title
        text: Main article body text
        authors: List of author names (can be empty)
        date_published: Publication date (can be None if extraction failed)
        source_domain: Domain the article was scraped from (e.g., "dawn.com")
        parser_used: Which parser(s) extracted the content (e.g., "trafilatura+newspaper4k_date")
    """

    title: str
    text: str
    authors: List[str]
    date_published: Optional[datetime]
    source_domain: str
    parser_used: str

    # Validation thresholds
    MIN_TITLE_LENGTH: int = field(default=10, repr=False, compare=False)
    MIN_TEXT_LENGTH: int = field(default=50, repr=False, compare=False)

    @property
    def text_length(self) -> int:
        """Return the length of the article text."""
        return len(self.text)

    @property
    def has_date(self) -> bool:
        """Return True if date_published is set."""
        return self.date_published is not None

    def is_valid(self) -> bool:
        """
        Check if the article meets minimum quality thresholds.

        Returns:
            True if title >= 10 chars AND text >= 50 chars
        """
        return (
            len(self.title) >= self.MIN_TITLE_LENGTH
            and len(self.text) >= self.MIN_TEXT_LENGTH
        )

    def to_raw_article(self, url: str, source: str) -> RawArticle:
        """
        Convert ScrapedArticle to RawArticle for database storage.

        Args:
            url: The original URL the article was scraped from
            source: The source identifier (e.g., "dawn", "tribune")

        Returns:
            RawArticle instance ready for database insertion
        """
        # Build metadata dict with parser info and all authors
        metadata = {
            "parser_used": self.parser_used,
            "source_domain": self.source_domain,
        }

        # Store all authors in metadata (RawArticle.author is single string)
        if self.authors:
            metadata["all_authors"] = self.authors

        return RawArticle(
            source=source,
            url=url,
            headline=self.title,
            main_text=self.text,
            author=self.authors[0] if self.authors else None,
            publish_date=self.date_published,
            metadata=metadata,
        )

    @classmethod
    def create_empty(cls, source_domain: str) -> "ScrapedArticle":
        """
        Factory method to create an empty/failed article.

        Used when all parsers fail to extract content.

        Args:
            source_domain: The domain that was attempted

        Returns:
            ScrapedArticle with empty values and parser_used="none"
        """
        return cls(
            title="",
            text="",
            authors=[],
            date_published=None,
            source_domain=source_domain,
            parser_used="none",
        )

    @classmethod
    def from_url(
        cls,
        url: str,
        title: str,
        text: str,
        authors: List[str],
        date_published: Optional[datetime],
        parser_used: str,
    ) -> "ScrapedArticle":
        """
        Factory method that extracts source_domain from URL.

        Args:
            url: The article URL
            title: Article headline
            text: Article body text
            authors: List of author names
            date_published: Publication date or None
            parser_used: Parser chain used

        Returns:
            ScrapedArticle with source_domain extracted from URL
        """
        parsed = urlparse(url)
        source_domain = parsed.netloc

        return cls(
            title=title,
            text=text,
            authors=authors,
            date_published=date_published,
            source_domain=source_domain,
            parser_used=parser_used,
        )
