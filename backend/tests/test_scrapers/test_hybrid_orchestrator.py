"""
TDD Tests for Hybrid Scraper Orchestrator.

These tests verify the integration of StealthFetcher + ContentParser
with Playwright as Tier 2 fallback.

Run with: pytest tests/test_scrapers/test_hybrid_orchestrator.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock


class TestHybridOrchestratorBasicFlow:
    """Tests for basic orchestrator flow: StealthFetcher -> ContentParser."""

    def test_scrape_url_uses_stealth_fetcher_first(self):
        """Orchestrator should use StealthFetcher for initial fetch."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            mock_fetcher.fetch.return_value = "<html><body>Test</body></html>"

            with patch.object(orchestrator, '_content_parser') as mock_parser:
                mock_result = MagicMock()
                mock_result.is_valid.return_value = True
                mock_result.text = "Valid content " * 50
                mock_parser.parse.return_value = mock_result

                orchestrator.scrape_url("https://example.com/article")

        # Verify StealthFetcher was called
        mock_fetcher.fetch.assert_called_once_with("https://example.com/article")

    def test_scrape_url_parses_html_with_content_parser(self):
        """Orchestrator should pass fetched HTML to ContentParser."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        test_html = "<html><body><h1>Test Article</h1><p>Content here.</p></body></html>"

        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            mock_fetcher.fetch.return_value = test_html

            with patch.object(orchestrator, '_content_parser') as mock_parser:
                mock_result = MagicMock()
                mock_result.is_valid.return_value = True
                mock_parser.parse.return_value = mock_result

                orchestrator.scrape_url("https://example.com/article")

        # Verify ContentParser was called with the HTML
        mock_parser.parse.assert_called_once()
        call_args = mock_parser.parse.call_args
        assert test_html in call_args[0]  # HTML should be first argument

    def test_scrape_url_returns_raw_article(self):
        """Orchestrator should return RawArticle on success."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator
        from src.db.models import RawArticle

        orchestrator = HybridOrchestrator()

        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            mock_fetcher.fetch.return_value = "<html><body>Test</body></html>"

            with patch.object(orchestrator, '_content_parser') as mock_parser:
                from src.scrapers.dtos import ScrapedArticle
                mock_result = ScrapedArticle(
                    title="Test Article Title",
                    text="Content " * 50,
                    authors=["Test Author"],
                    date_published=datetime.now(timezone.utc),
                    source_domain="example.com",
                    parser_used="trafilatura",
                )
                mock_parser.parse.return_value = mock_result

                result = orchestrator.scrape_url(
                    "https://example.com/article",
                    source="example"
                )

        assert isinstance(result, RawArticle)
        assert result.headline == "Test Article Title"
        assert result.source == "example"


class TestHybridOrchestratorTier2Fallback:
    """Tests for Playwright fallback when stealth fetch fails."""

    def test_playwright_fallback_on_stealth_failure(self):
        """When StealthFetcher returns None, use Playwright."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            mock_fetcher.fetch.return_value = None  # Stealth failed

            with patch.object(orchestrator, '_fetch_with_playwright') as mock_playwright:
                mock_playwright.return_value = "<html><body>Playwright content</body></html>"

                with patch.object(orchestrator, '_content_parser') as mock_parser:
                    mock_result = MagicMock()
                    mock_result.is_valid.return_value = True
                    mock_result.text = "Valid " * 50
                    mock_parser.parse.return_value = mock_result

                    orchestrator.scrape_url("https://blocked-site.com/article")

        # Verify Playwright fallback was called
        mock_playwright.assert_called_once()

    def test_playwright_fallback_on_empty_content(self):
        """When ContentParser returns invalid content, try Playwright."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            mock_fetcher.fetch.return_value = "<html>Blocked page</html>"

            with patch.object(orchestrator, '_content_parser') as mock_parser:
                # First parse returns invalid
                invalid_result = MagicMock()
                invalid_result.is_valid.return_value = False
                invalid_result.text = ""

                # Second parse (from playwright) returns valid
                valid_result = MagicMock()
                valid_result.is_valid.return_value = True
                valid_result.text = "Good content " * 50

                mock_parser.parse.side_effect = [invalid_result, valid_result]

                with patch.object(orchestrator, '_fetch_with_playwright') as mock_playwright:
                    mock_playwright.return_value = "<html>Real content</html>"

                    orchestrator.scrape_url("https://js-heavy-site.com/article")

        # Verify Playwright was triggered
        mock_playwright.assert_called_once()

    def test_returns_none_when_all_methods_fail(self):
        """When both stealth and playwright fail, return None."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            mock_fetcher.fetch.return_value = None

            with patch.object(orchestrator, '_fetch_with_playwright') as mock_playwright:
                mock_playwright.return_value = None  # Playwright also failed

                result = orchestrator.scrape_url("https://totally-blocked.com/article")

        assert result is None


class TestHybridOrchestratorPlaywrightStealth:
    """Tests for playwright-stealth integration."""

    def test_playwright_uses_stealth_plugin(self):
        """Playwright should use playwright-stealth to avoid detection."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        # This test verifies the stealth plugin is applied
        # by checking that Stealth().apply_stealth_sync is called during playwright setup
        with patch("src.scrapers.hybrid_orchestrator.sync_playwright") as mock_pw:
            mock_browser = MagicMock()
            mock_context = MagicMock()
            mock_page = MagicMock()
            mock_page.content.return_value = "<html>Content</html>"

            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page

            mock_pw_instance = MagicMock()
            mock_pw_instance.chromium.launch.return_value = mock_browser
            mock_pw.return_value.start.return_value = mock_pw_instance

            with patch("src.scrapers.hybrid_orchestrator.Stealth") as mock_stealth_class:
                mock_stealth_instance = MagicMock()
                mock_stealth_class.return_value = mock_stealth_instance

                orchestrator._fetch_with_playwright("https://example.com")

                # Verify Stealth was instantiated
                mock_stealth_class.assert_called_once()
                # Verify apply_stealth_sync was called with the page
                mock_stealth_instance.apply_stealth_sync.assert_called_once()


class TestHybridOrchestratorSectionURLs:
    """Tests for proper section URL construction."""

    def test_section_urls_joined_with_base_url(self):
        """Section names should be properly joined with base URL."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        base_url = "https://www.dawn.com"
        sections = ["latest-news", "pakistan", "business"]

        urls = orchestrator._build_section_urls(base_url, sections)

        assert len(urls) == 3
        assert "https://www.dawn.com/latest-news" in urls
        assert "https://www.dawn.com/pakistan" in urls
        assert "https://www.dawn.com/business" in urls

    def test_section_urls_handles_trailing_slash(self):
        """Should handle base URLs with trailing slashes."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        base_url = "https://www.dawn.com/"
        sections = ["news"]

        urls = orchestrator._build_section_urls(base_url, sections)

        # Should not have double slashes
        assert "https://www.dawn.com/news" in urls
        assert "//news" not in urls[0]

    def test_section_urls_handles_full_urls(self):
        """If section is already a full URL, use as-is."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        base_url = "https://www.dawn.com"
        sections = ["https://www.dawn.com/special-page", "pakistan"]

        urls = orchestrator._build_section_urls(base_url, sections)

        assert "https://www.dawn.com/special-page" in urls
        assert "https://www.dawn.com/pakistan" in urls


class TestHybridOrchestratorArticleURLExtraction:
    """Tests for extracting article URLs from section pages."""

    def test_extracts_article_urls_from_section_html(self):
        """Should extract article URLs from section page HTML."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        section_html = """
        <html>
        <body>
            <a href="/news/12345/article-one">Article One</a>
            <a href="/news/12346/article-two">Article Two</a>
            <a href="/about">About Us</a>
            <a href="/news/12347/article-three">Article Three</a>
        </body>
        </html>
        """

        urls = orchestrator._extract_article_urls(
            section_html,
            base_url="https://www.dawn.com",
            source="dawn"
        )

        # Should extract article URLs (contain /news/ with numbers)
        assert len(urls) >= 3
        assert any("/news/12345" in url for url in urls)

    def test_deduplicates_article_urls(self):
        """Should remove duplicate URLs."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        section_html = """
        <html>
        <body>
            <a href="/news/12345/article">Article</a>
            <a href="/news/12345/article">Article (duplicate)</a>
            <a href="/news/12346/other">Other</a>
        </body>
        </html>
        """

        urls = orchestrator._extract_article_urls(
            section_html,
            base_url="https://www.dawn.com",
            source="dawn"
        )

        # Should have unique URLs only
        assert len(urls) == len(set(urls))


class TestHybridOrchestratorBatchScraping:
    """Tests for batch scraping functionality."""

    def test_scrape_source_returns_list_of_articles(self):
        """scrape_source should return list of RawArticles."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator
        from src.db.models import RawArticle

        orchestrator = HybridOrchestrator()

        # Mock the internal methods
        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            # Section page HTML
            section_html = """
            <html><body>
                <a href="/news/1/article-1">Article 1</a>
                <a href="/news/2/article-2">Article 2</a>
            </body></html>
            """
            # Article page HTML
            article_html = "<html><body><h1>Title</h1><p>" + ("Content " * 50) + "</p></body></html>"

            mock_fetcher.fetch.side_effect = [section_html, article_html, article_html]

            with patch.object(orchestrator, '_content_parser') as mock_parser:
                from src.scrapers.dtos import ScrapedArticle
                mock_article = ScrapedArticle(
                    title="Test Title",
                    text="Content " * 50,
                    authors=[],
                    date_published=None,
                    source_domain="dawn.com",
                    parser_used="trafilatura",
                )
                mock_parser.parse.return_value = mock_article

                results = orchestrator.scrape_source(
                    source="dawn",
                    base_url="https://www.dawn.com",
                    sections=["latest-news"],
                    max_articles=2,
                )

        assert isinstance(results, list)
        for article in results:
            assert isinstance(article, RawArticle)


class TestHybridOrchestratorStatistics:
    """Tests for scraping statistics."""

    def test_tracks_scraping_stats(self):
        """Orchestrator should track scraping statistics."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        with patch.object(orchestrator, '_stealth_fetcher') as mock_fetcher:
            mock_fetcher.fetch.return_value = "<html>Test</html>"
            mock_fetcher.get_stats.return_value = {
                "total_requests": 5,
                "successful_requests": 4,
                "failed_requests": 1,
            }

            with patch.object(orchestrator, '_content_parser') as mock_parser:
                from src.scrapers.dtos import ScrapedArticle
                mock_result = ScrapedArticle(
                    title="Title", text="Content " * 50, authors=[],
                    date_published=None, source_domain="test.com",
                    parser_used="trafilatura",
                )
                mock_parser.parse.return_value = mock_result

                orchestrator.scrape_url("https://example.com", source="test")

        stats = orchestrator.get_stats()
        assert "fetcher_stats" in stats


@pytest.mark.integration
class TestHybridOrchestratorIntegration:
    """Integration tests with real network calls."""

    def test_scrape_httpbin_html(self):
        """Integration: scrape httpbin.org HTML page."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        result = orchestrator.scrape_url(
            "https://httpbin.org/html",
            source="httpbin"
        )

        # httpbin returns simple HTML, may not pass content validation
        # but should not crash
        if result:
            print(f"✓ Scraped httpbin: {result.headline[:50] if result.headline else 'No title'}...")

    @pytest.mark.slow
    def test_scrape_dawn_article(self):
        """Integration: attempt to scrape a Dawn article."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        # Use a known stable article URL
        result = orchestrator.scrape_url(
            "https://www.dawn.com/news/1884361",
            source="dawn"
        )

        if result:
            assert result.source == "dawn"
            assert len(result.headline) > 10
            assert len(result.main_text) > 50
            print(f"✓ Scraped Dawn article: {result.headline[:50]}...")
            print(f"✓ Content length: {len(result.main_text)} chars")
        else:
            pytest.skip("Dawn article could not be scraped - may be blocked")

    @pytest.mark.slow
    def test_scrape_tribune_article(self):
        """Integration: attempt to scrape a Tribune article."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        result = orchestrator.scrape_url(
            "https://tribune.com.pk/story/2520000/test-article",
            source="tribune"
        )

        if result:
            assert result.source == "tribune"
            print(f"✓ Scraped Tribune: {result.headline[:50]}...")
        else:
            pytest.skip("Tribune article could not be scraped")


class TestHybridOrchestratorContentHashDedup:
    """Tests for content-hash deduplication in scrape_source."""

    def test_scrape_source_deduplicates_by_content_hash(self):
        """Two different URLs produce articles with same content_hash — only one kept."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator
        from src.db.models import RawArticle

        orchestrator = HybridOrchestrator()

        # Two articles with identical headline + text → same content_hash
        shared_headline = "Duplicate Headline For Dedup Test"
        shared_text = "Same content repeated here " * 50

        article_a = RawArticle(
            source="dawn",
            url="https://www.dawn.com/news/1001",
            headline=shared_headline,
            main_text=shared_text,
        )
        article_b = RawArticle(
            source="dawn",
            url="https://www.dawn.com/news/1002",
            headline=shared_headline,
            main_text=shared_text,
        )
        assert article_a.content_hash == article_b.content_hash

        call_count = {"n": 0}

        def mock_scrape_url(url, source="unknown"):
            call_count["n"] += 1
            return article_a if call_count["n"] == 1 else article_b

        with patch.object(orchestrator, "scrape_url", side_effect=mock_scrape_url):
            with patch.object(orchestrator, "_stealth_fetcher") as mock_fetcher:
                section_html = """
                <html><body>
                    <a href="/news/1001/first-article">First</a>
                    <a href="/news/1002/second-article">Second</a>
                </body></html>
                """
                mock_fetcher.fetch.return_value = section_html

                results = orchestrator.scrape_source(
                    source="dawn",
                    base_url="https://www.dawn.com",
                    sections=["latest-news"],
                    max_articles=50,
                )

        assert len(results) == 1


class TestHybridOrchestratorFeedDiscovery:
    """Tests for feed-first URL discovery in scrape_source."""

    def test_scrape_source_uses_feed_url_when_provided(self):
        """feed_url given and FeedDiscoverer returns URLs — HTML scraping not called."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator
        from src.db.models import RawArticle

        orchestrator = HybridOrchestrator()

        mock_article = RawArticle(
            source="dawn",
            url="https://www.dawn.com/news/1001",
            headline="Feed-discovered article headline",
            main_text="Article body content here " * 50,
        )

        with patch("src.scrapers.hybrid_orchestrator.FeedDiscoverer") as MockFeedDisc:
            MockFeedDisc.return_value.discover.return_value = [
                "https://www.dawn.com/news/1001",
            ]

            with patch.object(orchestrator, "scrape_url", return_value=mock_article):
                with patch.object(orchestrator, "_stealth_fetcher") as mock_fetcher:
                    results = orchestrator.scrape_source(
                        source="dawn",
                        base_url="https://www.dawn.com",
                        sections=["latest-news"],
                        feed_url="https://www.dawn.com/feeds/latest-news",
                    )

        MockFeedDisc.assert_called_once_with("https://www.dawn.com/feeds/latest-news")
        MockFeedDisc.return_value.discover.assert_called_once()
        # Section page fetching was NOT called
        mock_fetcher.fetch.assert_not_called()
        assert len(results) == 1

    def test_scrape_source_falls_back_to_html_when_feed_empty(self):
        """FeedDiscoverer returns [] — falls back to HTML section scraping."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator
        from src.db.models import RawArticle

        orchestrator = HybridOrchestrator()

        mock_article = RawArticle(
            source="dawn",
            url="https://www.dawn.com/news/1001",
            headline="Fallback article headline here",
            main_text="Fallback body content here " * 50,
        )

        with patch("src.scrapers.hybrid_orchestrator.FeedDiscoverer") as MockFeedDisc:
            MockFeedDisc.return_value.discover.return_value = []  # empty feed

            with patch.object(orchestrator, "_stealth_fetcher") as mock_fetcher:
                section_html = """
                <html><body>
                    <a href="/news/1001/fallback-article">Article</a>
                </body></html>
                """
                mock_fetcher.fetch.return_value = section_html

                with patch.object(orchestrator, "scrape_url", return_value=mock_article):
                    results = orchestrator.scrape_source(
                        source="dawn",
                        base_url="https://www.dawn.com",
                        sections=["latest-news"],
                        feed_url="https://www.dawn.com/feeds/latest-news",
                    )

        # Section page fetch was called (HTML fallback triggered)
        mock_fetcher.fetch.assert_called()
        assert len(results) == 1


class TestHybridOrchestratorPlaywrightSessionReuse:
    """Tests for Playwright browser session reuse and scrolling."""

    def test_playwright_reuses_browser_across_calls(self):
        """Call _fetch_with_playwright twice — chromium.launch() called only once."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html>Content</html>"
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser

        with patch("src.scrapers.hybrid_orchestrator.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = mock_pw_instance

            with patch("src.scrapers.hybrid_orchestrator.Stealth"):
                orchestrator._fetch_with_playwright("https://example.com/page-1")
                orchestrator._fetch_with_playwright("https://example.com/page-2")

        # Browser launched only once — reused on second call
        mock_pw_instance.chromium.launch.assert_called_once()

    def test_playwright_scrolls_before_capturing(self):
        """page.evaluate (scroll) is called scroll_depth times before page.content()."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator(scroll_depth=3)

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html>Content</html>"
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser

        with patch("src.scrapers.hybrid_orchestrator.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = mock_pw_instance

            with patch("src.scrapers.hybrid_orchestrator.Stealth"):
                orchestrator._fetch_with_playwright("https://example.com")

        calls = mock_page.method_calls
        evaluate_indices = [i for i, c in enumerate(calls) if c[0] == "evaluate"]
        content_indices = [i for i, c in enumerate(calls) if c[0] == "content"]

        assert len(evaluate_indices) == 3  # scroll_depth=3
        assert len(content_indices) == 1
        # All scrolls happened before content capture
        assert max(evaluate_indices) < min(content_indices)

    def test_close_shuts_down_browser(self):
        """After close(), browser.close() and playwright.stop() are called."""
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator

        orchestrator = HybridOrchestrator()

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html></html>"
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser

        with patch("src.scrapers.hybrid_orchestrator.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = mock_pw_instance

            with patch("src.scrapers.hybrid_orchestrator.Stealth"):
                orchestrator._fetch_with_playwright("https://example.com")
                orchestrator.close()

        mock_browser.close.assert_called_once()
        mock_pw_instance.stop.assert_called_once()
