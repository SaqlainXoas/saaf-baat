"""
TDD Tests for ScrapedArticle DTO.

These tests MUST be written BEFORE implementation.
Run with: pytest tests/test_scrapers/test_dtos.py -v
"""

import pytest
from datetime import datetime, timezone
from typing import List


class TestScrapedArticleDataclass:
    """Tests for ScrapedArticle dataclass structure and validation."""

    def test_scraped_article_has_required_fields(self):
        """ScrapedArticle must have all required fields."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="Test Headline for Article",
            text="This is the main content of the article. " * 10,  # >200 chars
            authors=["John Doe", "Jane Smith"],
            date_published=datetime(2026, 2, 4, 10, 0, 0, tzinfo=timezone.utc),
            source_domain="dawn.com",
            parser_used="trafilatura",
        )

        assert article.title == "Test Headline for Article"
        assert "main content" in article.text
        assert article.authors == ["John Doe", "Jane Smith"]
        assert article.date_published.year == 2026
        assert article.source_domain == "dawn.com"
        assert article.parser_used == "trafilatura"

    def test_scraped_article_authors_can_be_empty_list(self):
        """Authors field can be an empty list when no author found."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="Test Headline",
            text="Content " * 20,
            authors=[],
            date_published=None,
            source_domain="tribune.com.pk",
            parser_used="newspaper4k",
        )

        assert article.authors == []
        assert isinstance(article.authors, list)

    def test_scraped_article_date_can_be_none(self):
        """date_published can be None when date extraction fails."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="No Date Article",
            text="This article has no publish date. " * 10,
            authors=["Author"],
            date_published=None,
            source_domain="geo.tv",
            parser_used="readability",
        )

        assert article.date_published is None

    def test_scraped_article_parser_used_tracks_chain(self):
        """parser_used field should track the parser chain used."""
        from src.scrapers.dtos import ScrapedArticle

        # Single parser
        article1 = ScrapedArticle(
            title="Test", text="Content " * 20, authors=[],
            date_published=None, source_domain="test.com",
            parser_used="trafilatura",
        )
        assert article1.parser_used == "trafilatura"

        # Parser chain (trafilatura got text, newspaper4k got date)
        article2 = ScrapedArticle(
            title="Test", text="Content " * 20, authors=[],
            date_published=datetime.now(timezone.utc), source_domain="test.com",
            parser_used="trafilatura+newspaper4k_date",
        )
        assert "trafilatura" in article2.parser_used
        assert "newspaper4k" in article2.parser_used


class TestScrapedArticleToRawArticle:
    """Tests for conversion from ScrapedArticle to RawArticle."""

    def test_to_raw_article_returns_raw_article_instance(self):
        """to_raw_article() must return a RawArticle instance."""
        from src.scrapers.dtos import ScrapedArticle
        from src.db.models import RawArticle

        scraped = ScrapedArticle(
            title="Conversion Test Article",
            text="This is the article content for testing conversion. " * 5,
            authors=["Test Author"],
            date_published=datetime(2026, 2, 4, 12, 0, 0, tzinfo=timezone.utc),
            source_domain="dawn.com",
            parser_used="trafilatura",
        )

        raw = scraped.to_raw_article(
            url="https://www.dawn.com/news/12345/conversion-test",
            source="dawn",
        )

        assert isinstance(raw, RawArticle)

    def test_to_raw_article_maps_title_to_headline(self):
        """title field should map to headline in RawArticle."""
        from src.scrapers.dtos import ScrapedArticle

        scraped = ScrapedArticle(
            title="This Is The Headline",
            text="Article content here. " * 10,
            authors=["Author"],
            date_published=None,
            source_domain="tribune.com.pk",
            parser_used="newspaper4k",
        )

        raw = scraped.to_raw_article(
            url="https://tribune.com.pk/story/12345",
            source="tribune",
        )

        assert raw.headline == "This Is The Headline"

    def test_to_raw_article_maps_text_to_main_text(self):
        """text field should map to main_text in RawArticle."""
        from src.scrapers.dtos import ScrapedArticle

        content = "This is the main article body with important news. " * 5
        scraped = ScrapedArticle(
            title="Test",
            text=content,
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        raw = scraped.to_raw_article(url="https://test.com/article", source="test")

        assert raw.main_text == content

    def test_to_raw_article_maps_first_author(self):
        """First author should map to author field in RawArticle."""
        from src.scrapers.dtos import ScrapedArticle

        scraped = ScrapedArticle(
            title="Multi Author Article",
            text="Content " * 20,
            authors=["Primary Author", "Secondary Author", "Third Author"],
            date_published=None,
            source_domain="test.com",
            parser_used="newspaper4k",
        )

        raw = scraped.to_raw_article(url="https://test.com/article", source="test")

        assert raw.author == "Primary Author"

    def test_to_raw_article_handles_empty_authors(self):
        """Empty authors list should result in None author."""
        from src.scrapers.dtos import ScrapedArticle

        scraped = ScrapedArticle(
            title="No Author Article",
            text="Content " * 20,
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="readability",
        )

        raw = scraped.to_raw_article(url="https://test.com/article", source="test")

        assert raw.author is None

    def test_to_raw_article_maps_date_published(self):
        """date_published should map to publish_date in RawArticle."""
        from src.scrapers.dtos import ScrapedArticle

        pub_date = datetime(2026, 2, 4, 15, 30, 0, tzinfo=timezone.utc)
        scraped = ScrapedArticle(
            title="Dated Article",
            text="Content " * 20,
            authors=[],
            date_published=pub_date,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        raw = scraped.to_raw_article(url="https://test.com/article", source="test")

        assert raw.publish_date == pub_date

    def test_to_raw_article_generates_content_hash(self):
        """RawArticle should have auto-generated content_hash."""
        from src.scrapers.dtos import ScrapedArticle

        scraped = ScrapedArticle(
            title="Hash Test Article",
            text="Unique content for hash generation. " * 5,
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        raw = scraped.to_raw_article(url="https://test.com/hash-test", source="test")

        assert raw.content_hash is not None
        assert len(raw.content_hash) == 64  # SHA-256 hex digest

    def test_to_raw_article_stores_parser_used_in_metadata(self):
        """parser_used should be stored in RawArticle metadata dict."""
        from src.scrapers.dtos import ScrapedArticle

        scraped = ScrapedArticle(
            title="Metadata Test",
            text="Content " * 20,
            authors=["Author"],
            date_published=None,
            source_domain="dawn.com",
            parser_used="trafilatura+newspaper4k_date",
        )

        raw = scraped.to_raw_article(url="https://dawn.com/news/12345", source="dawn")

        assert "parser_used" in raw.metadata
        assert raw.metadata["parser_used"] == "trafilatura+newspaper4k_date"

    def test_to_raw_article_stores_all_authors_in_metadata(self):
        """All authors should be stored in metadata for reference."""
        from src.scrapers.dtos import ScrapedArticle

        scraped = ScrapedArticle(
            title="Multi Author",
            text="Content " * 20,
            authors=["Author One", "Author Two", "Author Three"],
            date_published=None,
            source_domain="test.com",
            parser_used="newspaper4k",
        )

        raw = scraped.to_raw_article(url="https://test.com/multi", source="test")

        assert "all_authors" in raw.metadata
        assert raw.metadata["all_authors"] == ["Author One", "Author Two", "Author Three"]

    def test_to_raw_article_sets_source_correctly(self):
        """source parameter should be set on RawArticle."""
        from src.scrapers.dtos import ScrapedArticle

        scraped = ScrapedArticle(
            title="Source Test",
            text="Content " * 20,
            authors=[],
            date_published=None,
            source_domain="www.dawn.com",
            parser_used="trafilatura",
        )

        raw = scraped.to_raw_article(
            url="https://www.dawn.com/news/12345",
            source="dawn",
        )

        assert raw.source == "dawn"

    def test_to_raw_article_sets_url_correctly(self):
        """url parameter should be set on RawArticle."""
        from src.scrapers.dtos import ScrapedArticle

        test_url = "https://tribune.com.pk/story/2345/test-article"
        scraped = ScrapedArticle(
            title="URL Test",
            text="Content " * 20,
            authors=[],
            date_published=None,
            source_domain="tribune.com.pk",
            parser_used="newspaper4k",
        )

        raw = scraped.to_raw_article(url=test_url, source="tribune")

        assert raw.url == test_url


class TestScrapedArticleValidation:
    """Tests for ScrapedArticle content validation."""

    def test_is_valid_returns_true_for_good_content(self):
        """is_valid() should return True when title ≥10 chars and text ≥50 chars."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="This is a valid headline with enough characters",
            text="This is valid article content. " * 10,  # Well over 50 chars
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        assert article.is_valid() is True

    def test_is_valid_returns_false_for_short_title(self):
        """is_valid() should return False when title < 10 chars."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="Short",  # Only 5 chars
            text="This is valid content. " * 10,
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        assert article.is_valid() is False

    def test_is_valid_returns_false_for_short_text(self):
        """is_valid() should return False when text < 50 chars."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="This is a valid headline",
            text="Too short",  # Only ~9 chars
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        assert article.is_valid() is False

    def test_is_valid_returns_false_for_empty_title(self):
        """is_valid() should return False for empty title."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="",
            text="This is valid content. " * 10,
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        assert article.is_valid() is False

    def test_is_valid_returns_false_for_empty_text(self):
        """is_valid() should return False for empty text."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle(
            title="Valid Headline Here",
            text="",
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        assert article.is_valid() is False

    def test_text_length_property(self):
        """text_length property should return length of text."""
        from src.scrapers.dtos import ScrapedArticle

        content = "A" * 500
        article = ScrapedArticle(
            title="Test",
            text=content,
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        assert article.text_length == 500

    def test_has_date_property(self):
        """has_date property should return True when date_published is set."""
        from src.scrapers.dtos import ScrapedArticle

        article_with_date = ScrapedArticle(
            title="Test Headline",
            text="Content " * 20,
            authors=[],
            date_published=datetime.now(timezone.utc),
            source_domain="test.com",
            parser_used="trafilatura",
        )

        article_without_date = ScrapedArticle(
            title="Test Headline",
            text="Content " * 20,
            authors=[],
            date_published=None,
            source_domain="test.com",
            parser_used="trafilatura",
        )

        assert article_with_date.has_date is True
        assert article_without_date.has_date is False


class TestScrapedArticleFactory:
    """Tests for ScrapedArticle factory methods."""

    def test_create_empty_returns_article_with_empty_values(self):
        """create_empty() factory should return article with empty/default values."""
        from src.scrapers.dtos import ScrapedArticle

        empty = ScrapedArticle.create_empty(source_domain="failed.com")

        assert empty.title == ""
        assert empty.text == ""
        assert empty.authors == []
        assert empty.date_published is None
        assert empty.source_domain == "failed.com"
        assert empty.parser_used == "none"
        assert empty.is_valid() is False

    def test_from_url_extracts_domain(self):
        """from_url() should extract source_domain from URL."""
        from src.scrapers.dtos import ScrapedArticle

        article = ScrapedArticle.from_url(
            url="https://www.dawn.com/news/12345/article-slug",
            title="Test Article",
            text="Content " * 20,
            authors=[],
            date_published=None,
            parser_used="trafilatura",
        )

        assert article.source_domain == "www.dawn.com"
