"""TDD tests for FeedDiscoverer — RSS/Atom feed URL discovery.

All tests are unit tests with mocked feedparser — no network calls.

Run with: pytest tests/test_scrapers/test_feed.py -v
"""

from unittest.mock import patch, MagicMock


class TestFeedDiscoverer:
    """Unit tests for FeedDiscoverer with mocked feedparser."""

    def test_discover_returns_urls_from_valid_feed(self):
        """Mock feedparser with 3 entries, verify 3 URLs returned."""
        from src.scrapers.feed import FeedDiscoverer

        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(link="https://www.dawn.com/news/1001"),
            MagicMock(link="https://www.dawn.com/news/1002"),
            MagicMock(link="https://www.dawn.com/news/1003"),
        ]

        with patch("src.scrapers.feed.feedparser.parse", return_value=mock_feed):
            discoverer = FeedDiscoverer("https://www.dawn.com/feeds/latest-news")
            urls = discoverer.discover()

        assert len(urls) == 3
        assert "https://www.dawn.com/news/1001" in urls
        assert "https://www.dawn.com/news/1002" in urls
        assert "https://www.dawn.com/news/1003" in urls

    def test_discover_returns_empty_on_invalid_feed(self):
        """Mock feedparser returning empty entries list."""
        from src.scrapers.feed import FeedDiscoverer

        mock_feed = MagicMock()
        mock_feed.entries = []

        with patch("src.scrapers.feed.feedparser.parse", return_value=mock_feed):
            discoverer = FeedDiscoverer("https://invalid.example.com/feed")
            urls = discoverer.discover()

        assert urls == []

    def test_discover_handles_entries_without_link(self):
        """Entries missing link field are skipped."""
        from src.scrapers.feed import FeedDiscoverer

        entry_with_link = MagicMock(link="https://www.dawn.com/news/1001")

        # MagicMock with spec=[] has no attributes, so getattr returns None
        entry_without_link = MagicMock(spec=[])

        mock_feed = MagicMock()
        mock_feed.entries = [entry_with_link, entry_without_link]

        with patch("src.scrapers.feed.feedparser.parse", return_value=mock_feed):
            discoverer = FeedDiscoverer("https://www.dawn.com/feeds/latest-news")
            urls = discoverer.discover()

        assert urls == ["https://www.dawn.com/news/1001"]

    def test_discover_returns_empty_on_parse_error(self):
        """feedparser raises exception, returns [] not crash."""
        from src.scrapers.feed import FeedDiscoverer

        with patch("src.scrapers.feed.feedparser.parse", side_effect=Exception("Network error")):
            discoverer = FeedDiscoverer("https://www.dawn.com/feeds/latest-news")
            urls = discoverer.discover()

        assert urls == []

    def test_discover_deduplicates_urls(self):
        """Two entries with same link produce one URL in output."""
        from src.scrapers.feed import FeedDiscoverer

        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(link="https://www.dawn.com/news/1001"),
            MagicMock(link="https://www.dawn.com/news/1001"),  # duplicate
            MagicMock(link="https://www.dawn.com/news/1002"),
        ]

        with patch("src.scrapers.feed.feedparser.parse", return_value=mock_feed):
            discoverer = FeedDiscoverer("https://www.dawn.com/feeds/latest-news")
            urls = discoverer.discover()

        assert len(urls) == 2
        assert urls.count("https://www.dawn.com/news/1001") == 1
