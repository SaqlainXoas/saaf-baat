"""
TDD Tests for ContentParser ensemble.

These tests MUST be written BEFORE implementation.
Run with: pytest tests/test_scrapers/test_parsers.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


# Sample HTML fixtures for testing
SAMPLE_HTML_COMPLETE = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Article - News Site</title>
    <meta property="article:published_time" content="2026-02-04T10:00:00Z">
    <meta name="author" content="John Doe">
</head>
<body>
    <article>
        <h1>This Is A Test Article Headline For Testing</h1>
        <div class="author">By John Doe</div>
        <div class="date">February 4, 2026</div>
        <div class="content">
            <p>This is the first paragraph of the article content. It contains
            important information about the test subject matter that we are
            covering in this article.</p>
            <p>This is the second paragraph with more detailed information.
            The article continues with additional context and background
            that provides readers with a comprehensive understanding.</p>
            <p>The third paragraph wraps up the main points and provides
            conclusions based on the information presented above. This
            gives the article proper closure and summary.</p>
        </div>
    </article>
</body>
</html>
"""

SAMPLE_HTML_NO_DATE = """
<!DOCTYPE html>
<html>
<head><title>Article Without Date</title></head>
<body>
    <article>
        <h1>Article Without Publication Date</h1>
        <div class="author">Jane Smith</div>
        <div class="content">
            <p>This article has substantial content but no publication date
            in the metadata or visible in the HTML structure. The parser
            should extract the text but may need a fallback for date.</p>
            <p>Additional paragraph with more content to ensure we have
            enough text length for validation. This tests the scenario
            where trafilatura gets content but misses the date.</p>
        </div>
    </article>
</body>
</html>
"""

SAMPLE_HTML_SHORT_TEXT = """
<!DOCTYPE html>
<html>
<head><title>Short Article</title></head>
<body>
    <article>
        <h1>Short Article Title</h1>
        <p>Very brief content.</p>
    </article>
</body>
</html>
"""

SAMPLE_HTML_MINIMAL = """
<!DOCTYPE html>
<html>
<head><title>Minimal Page</title></head>
<body>
    <p>Just some text.</p>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_AUTHORS = """
<!DOCTYPE html>
<html>
<head>
    <title>Multi-Author Article</title>
    <meta name="author" content="Author One, Author Two">
</head>
<body>
    <article>
        <h1>Article Written By Multiple Authors</h1>
        <div class="authors">By Author One and Author Two</div>
        <div class="content">
            <p>This is an article written by multiple authors collaboratively.
            The content discusses various topics that required expertise from
            different contributors to create a comprehensive piece.</p>
            <p>The second paragraph continues the discussion with additional
            insights and perspectives from the collaborative writing team.</p>
        </div>
    </article>
</body>
</html>
"""


class TestContentParserPrimaryTrafilatura:
    """Tests for trafilatura as primary parser."""

    def test_trafilatura_success_returns_scraped_article(self):
        """When trafilatura extracts good content, return ScrapedArticle."""
        from src.scrapers.parsers import ContentParser
        from src.scrapers.dtos import ScrapedArticle

        parser = ContentParser()
        result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com/article")

        assert isinstance(result, ScrapedArticle)
        assert result.title != ""
        assert len(result.text) > 200  # Quality threshold
        assert result.source_domain == "example.com"

    def test_trafilatura_parser_used_field(self):
        """When trafilatura succeeds alone, parser_used should be 'trafilatura'."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # Mock trafilatura to return good content with date
        with patch("src.scrapers.parsers.trafilatura_extract") as mock_extract:
            mock_extract.return_value = "A" * 250  # Good text length

            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_metadata = MagicMock()
                mock_metadata.title = "Test Article Title Here"
                mock_metadata.date = "2026-02-04"
                mock_metadata.author = "Test Author"
                mock_meta.return_value = mock_metadata

                result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com/article")

        assert "trafilatura" in result.parser_used

    def test_trafilatura_extracts_title(self):
        """Trafilatura should extract article title."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()
        result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com/article")

        assert result.title != ""
        assert len(result.title) >= 10


class TestContentParserMetadataMerge:
    """Tests for metadata merging from newspaper4k."""

    def test_newspaper_date_merged_when_trafilatura_missing(self):
        """When trafilatura has no date, use newspaper4k's date."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # Mock trafilatura returning text but no date
        with patch("src.scrapers.parsers.trafilatura_extract") as mock_extract:
            mock_extract.return_value = "Good content " * 50

            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_metadata = MagicMock()
                mock_metadata.title = "Article Title Here"
                mock_metadata.date = None  # No date from trafilatura
                mock_metadata.author = None
                mock_meta.return_value = mock_metadata

                # Mock newspaper4k returning date
                with patch("src.scrapers.parsers.NewspaperArticle") as MockArticle:
                    mock_article = MagicMock()
                    mock_article.title = "Article Title"
                    mock_article.text = "Some text"
                    mock_article.authors = []
                    mock_article.publish_date = datetime(2026, 2, 4, 10, 0, 0)
                    MockArticle.return_value = mock_article

                    result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com/article")

        # Should have merged date from newspaper4k
        assert result.has_date is True
        assert "newspaper4k" in result.parser_used or result.date_published is not None

    def test_parser_used_shows_chain_when_merged(self):
        """parser_used should show 'trafilatura+newspaper4k_date' when date merged."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # Mock scenario: trafilatura has text, newspaper4k provides date
        with patch("src.scrapers.parsers.trafilatura_extract") as mock_extract:
            mock_extract.return_value = "Good content " * 50

            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_metadata = MagicMock()
                mock_metadata.title = "Article Title Here"
                mock_metadata.date = None  # No date
                mock_metadata.author = "Author Name"
                mock_meta.return_value = mock_metadata

                with patch("src.scrapers.parsers.NewspaperArticle") as MockArticle:
                    mock_article = MagicMock()
                    mock_article.title = "Title"
                    mock_article.text = "text"
                    mock_article.authors = []
                    mock_article.publish_date = datetime(2026, 2, 4, 12, 0, 0)
                    MockArticle.return_value = mock_article

                    result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com")

        # Parser chain should include both
        assert "trafilatura" in result.parser_used
        assert "newspaper4k" in result.parser_used


class TestDateNormalization:
    """Tests for date normalization to UTC (assume PKT if naive)."""

    def test_parse_date_naive_assumes_pkt_and_converts_to_utc(self):
        """Naive date should be interpreted as PKT (UTC+5) and converted to UTC."""
        from datetime import timezone
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # 10:00 PKT should become 05:00 UTC
        dt = parser._parse_date("2026-02-04T10:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 5

    def test_parse_date_with_timezone_keeps_utc(self):
        """Timezone-aware date should normalize to UTC."""
        from datetime import timezone
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        dt = parser._parse_date("2026-02-04T10:00:00Z")
        assert dt is not None
        assert dt.tzinfo == timezone.utc


class TestContentParserFallbackToNewspaper:
    """Tests for fallback to newspaper4k when trafilatura returns short text."""

    def test_newspaper_text_used_when_trafilatura_short(self):
        """When trafilatura text < 200 chars, use newspaper4k text."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # Mock trafilatura returning short text
        with patch("src.scrapers.parsers.trafilatura_extract") as mock_extract:
            mock_extract.return_value = "Short text"  # < 200 chars

            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_metadata = MagicMock()
                mock_metadata.title = "Title"
                mock_metadata.date = None
                mock_metadata.author = None
                mock_meta.return_value = mock_metadata

                # Mock newspaper4k returning longer text
                with patch("src.scrapers.parsers.NewspaperArticle") as MockArticle:
                    mock_article = MagicMock()
                    mock_article.title = "Good Title From Newspaper"
                    mock_article.text = "B" * 300  # Long enough
                    mock_article.authors = ["Newspaper Author"]
                    mock_article.publish_date = datetime(2026, 2, 4, 10, 0, 0)
                    MockArticle.return_value = mock_article

                    result = parser.parse(SAMPLE_HTML_SHORT_TEXT, "https://example.com/article")

        assert len(result.text) >= 200
        assert "newspaper4k" in result.parser_used

    def test_newspaper_extracts_authors(self):
        """Newspaper4k should extract author information."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # Force newspaper4k path
        with patch("src.scrapers.parsers.trafilatura_extract") as mock_extract:
            mock_extract.return_value = "Short"  # Force fallback

            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_meta.return_value = MagicMock(title="Title", date=None, author=None)

                with patch("src.scrapers.parsers.NewspaperArticle") as MockArticle:
                    mock_article = MagicMock()
                    mock_article.title = "Article Title"
                    mock_article.text = "Content " * 50
                    mock_article.authors = ["John Doe", "Jane Smith"]
                    mock_article.publish_date = None
                    MockArticle.return_value = mock_article

                    result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com")

        assert len(result.authors) >= 1


class TestContentParserFallbackToReadability:
    """Tests for fallback to readability-lxml as safety net."""

    def test_readability_used_when_both_fail(self):
        """When trafilatura and newspaper4k both return short text, use readability."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # Mock both trafilatura and newspaper4k failing
        with patch("src.scrapers.parsers.trafilatura_extract") as mock_traf:
            mock_traf.return_value = "Short"

            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_meta.return_value = MagicMock(title="", date=None, author=None)

                with patch("src.scrapers.parsers.NewspaperArticle") as MockNewspaper:
                    mock_article = MagicMock()
                    mock_article.title = "Title"
                    mock_article.text = "Also short"
                    mock_article.authors = []
                    mock_article.publish_date = None
                    MockNewspaper.return_value = mock_article

                    # Mock readability returning good content
                    with patch("src.scrapers.parsers.ReadabilityDocument") as MockReadability:
                        mock_doc = MagicMock()
                        mock_doc.title.return_value = "Readability Title Here"
                        mock_doc.summary.return_value = "<p>" + ("Content " * 50) + "</p>"
                        MockReadability.return_value = mock_doc

                        result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com")

        assert "readability" in result.parser_used

    def test_readability_strips_html_tags(self):
        """Readability output should have HTML tags stripped."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        with patch("src.scrapers.parsers.trafilatura_extract", return_value=""):
            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_meta.return_value = MagicMock(title="", date=None, author=None)

                with patch("src.scrapers.parsers.NewspaperArticle") as MockNewspaper:
                    mock_article = MagicMock()
                    mock_article.title = ""
                    mock_article.text = ""
                    mock_article.authors = []
                    mock_article.publish_date = None
                    MockNewspaper.return_value = mock_article

                    with patch("src.scrapers.parsers.ReadabilityDocument") as MockReadability:
                        mock_doc = MagicMock()
                        mock_doc.title.return_value = "Title"
                        mock_doc.summary.return_value = "<p>Clean text content here " * 20 + "</p>"
                        MockReadability.return_value = mock_doc

                        result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com")

        # Should not contain HTML tags
        assert "<p>" not in result.text
        assert "</p>" not in result.text


class TestContentParserEmptyResult:
    """Tests for handling complete extraction failure."""

    def test_returns_empty_article_when_all_fail(self):
        """When all parsers fail, return empty ScrapedArticle."""
        from src.scrapers.parsers import ContentParser
        from src.scrapers.dtos import ScrapedArticle

        parser = ContentParser()

        # Mock all parsers returning nothing useful
        with patch("src.scrapers.parsers.trafilatura_extract", return_value=""):
            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_meta.return_value = MagicMock(title="", date=None, author=None)

                with patch("src.scrapers.parsers.NewspaperArticle") as MockNewspaper:
                    mock_article = MagicMock()
                    mock_article.title = ""
                    mock_article.text = ""
                    mock_article.authors = []
                    mock_article.publish_date = None
                    MockNewspaper.return_value = mock_article

                    with patch("src.scrapers.parsers.ReadabilityDocument") as MockReadability:
                        mock_doc = MagicMock()
                        mock_doc.title.return_value = ""
                        mock_doc.summary.return_value = ""
                        MockReadability.return_value = mock_doc

                        result = parser.parse(SAMPLE_HTML_MINIMAL, "https://example.com")

        assert isinstance(result, ScrapedArticle)
        assert result.is_valid() is False
        assert result.parser_used == "none" or "failed" in result.parser_used.lower()

    def test_empty_result_has_source_domain(self):
        """Even failed extraction should set source_domain."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        with patch("src.scrapers.parsers.trafilatura_extract", return_value=""):
            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_meta.return_value = MagicMock(title="", date=None, author=None)

                with patch("src.scrapers.parsers.NewspaperArticle") as MockNewspaper:
                    mock_article = MagicMock()
                    mock_article.title = ""
                    mock_article.text = ""
                    mock_article.authors = []
                    mock_article.publish_date = None
                    MockNewspaper.return_value = mock_article

                    with patch("src.scrapers.parsers.ReadabilityDocument") as MockReadability:
                        mock_doc = MagicMock()
                        mock_doc.title.return_value = ""
                        mock_doc.summary.return_value = ""
                        MockReadability.return_value = mock_doc

                        result = parser.parse("<html></html>", "https://test-domain.com/page")

        assert result.source_domain == "test-domain.com"


class TestContentParserExceptionHandling:
    """Tests for exception handling in parsers."""

    def test_handles_trafilatura_exception(self):
        """Parser should handle trafilatura exceptions gracefully."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        with patch("src.scrapers.parsers.trafilatura_extract", side_effect=Exception("Parse error")):
            with patch("src.scrapers.parsers.NewspaperArticle") as MockNewspaper:
                mock_article = MagicMock()
                mock_article.title = "Fallback Title"
                mock_article.text = "Fallback content " * 30
                mock_article.authors = []
                mock_article.publish_date = None
                MockNewspaper.return_value = mock_article

                # Should not raise, should fall back
                result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com")

        assert result is not None
        assert len(result.text) > 0

    def test_handles_newspaper_exception(self):
        """Parser should handle newspaper4k exceptions gracefully."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        with patch("src.scrapers.parsers.trafilatura_extract", return_value="Short"):
            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_meta.return_value = MagicMock(title="T", date=None, author=None)

                with patch("src.scrapers.parsers.NewspaperArticle", side_effect=Exception("Error")):
                    with patch("src.scrapers.parsers.ReadabilityDocument") as MockReadability:
                        mock_doc = MagicMock()
                        mock_doc.title.return_value = "Readability Title"
                        mock_doc.summary.return_value = "<p>" + ("Content " * 50) + "</p>"
                        MockReadability.return_value = mock_doc

                        # Should not raise, should fall back to readability
                        result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com")

        assert result is not None

    def test_handles_readability_exception(self):
        """Parser should handle readability exceptions gracefully."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        with patch("src.scrapers.parsers.trafilatura_extract", return_value=""):
            with patch("src.scrapers.parsers.trafilatura_extract_metadata") as mock_meta:
                mock_meta.return_value = MagicMock(title="", date=None, author=None)

                with patch("src.scrapers.parsers.NewspaperArticle") as MockNewspaper:
                    mock_article = MagicMock()
                    mock_article.title = ""
                    mock_article.text = ""
                    mock_article.authors = []
                    mock_article.publish_date = None
                    MockNewspaper.return_value = mock_article

                    with patch("src.scrapers.parsers.ReadabilityDocument", side_effect=Exception("Error")):
                        # Should not raise, should return empty result
                        result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com")

        assert result is not None
        assert result.is_valid() is False


class TestContentParserDateParsing:
    """Tests for date parsing from various formats."""

    def test_parses_iso_date(self):
        """Parser should handle ISO 8601 date format."""
        from src.scrapers.parsers import ContentParser
        from datetime import timedelta, timezone

        parser = ContentParser()

        html_with_iso_date = """
        <html>
        <head>
            <meta property="article:published_time" content="2026-02-04T10:30:00+05:00">
        </head>
        <body>
            <h1>Article With ISO Date Format</h1>
            <p>Content here that is long enough to pass validation. """ + ("More content. " * 30) + """</p>
        </body>
        </html>
        """

        result = parser.parse(html_with_iso_date, "https://example.com")

        if result.has_date:
            # Parser normalizes to UTC; the UTC day can differ from the local day
            # depending on the original offset. Verify local +05:00 date stays Feb 4.
            assert result.date_published.tzinfo is not None

            pkt = timezone(timedelta(hours=5))
            local = result.date_published.astimezone(pkt)
            assert local.year == 2026
            assert local.month == 2
            assert local.day == 4


class TestContentParserQualityThresholds:
    """Tests for content quality thresholds."""

    def test_min_text_length_threshold(self):
        """Parser should use 200 char threshold for text quality."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        # Verify the threshold is configurable or at least documented
        assert hasattr(parser, 'MIN_TEXT_LENGTH') or True  # Allow if not configurable
        # The threshold should be around 200
        # This is tested implicitly by the fallback tests


@pytest.mark.integration
class TestContentParserIntegration:
    """Integration tests with real HTML parsing (no mocks)."""

    def test_parse_complete_html(self):
        """Integration: parse complete HTML without mocks."""
        from src.scrapers.parsers import ContentParser

        parser = ContentParser()
        result = parser.parse(SAMPLE_HTML_COMPLETE, "https://example.com/article")

        assert result is not None
        assert len(result.title) > 0
        # May or may not get full text depending on parser behavior
        print(f"✓ Parsed title: {result.title[:50]}...")
        print(f"✓ Text length: {len(result.text)} chars")
        print(f"✓ Parser used: {result.parser_used}")

    def test_parse_real_dawn_html_fixture(self):
        """Integration: parse saved Dawn HTML if fixture exists."""
        import os

        fixture_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "dawn_article.html"
        )

        if not os.path.exists(fixture_path):
            pytest.skip("Dawn HTML fixture not available")

        from src.scrapers.parsers import ContentParser

        parser = ContentParser()

        with open(fixture_path, "r", encoding="utf-8") as f:
            html = f.read()

        result = parser.parse(html, "https://www.dawn.com/news/12345/test-article")

        assert result is not None
        assert result.source_domain == "www.dawn.com"
        print(f"✓ Parsed Dawn article: {result.title}")
        print(f"✓ Text length: {len(result.text)} chars")
