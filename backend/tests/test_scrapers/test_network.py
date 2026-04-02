"""
TDD Tests for StealthFetcher network layer.

These tests MUST be written BEFORE implementation.
Run with: pytest tests/test_scrapers/test_network.py -v
"""

import pytest
import time
from unittest.mock import patch, MagicMock, PropertyMock
from typing import Optional


class TestStealthFetcherBasicFunctionality:
    """Tests for basic StealthFetcher functionality."""

    def test_default_settings_are_tuned_for_bounded_morning_runs(self):
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher()

        assert fetcher.max_retries == 2
        assert fetcher.base_delay == 0.75
        assert fetcher.min_delay == 0.25
        assert fetcher.max_delay == 0.75
        assert fetcher.timeout == 20.0

    def test_fetch_returns_html_string_on_success(self):
        """fetch() should return HTML string when request succeeds."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><h1>Test</h1></body></html>"

        with patch("src.scrapers.network.requests.get", return_value=mock_response):
            result = fetcher.fetch("https://example.com/article")

        assert result is not None
        assert isinstance(result, str)
        assert "<html>" in result

    def test_fetch_returns_none_on_persistent_failure(self):
        """fetch() should return None after max retries exhausted."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(max_retries=3)

        # Mock persistent 403 response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")

        with patch("src.scrapers.network.requests.get", return_value=mock_response):
            result = fetcher.fetch("https://blocked-site.com/article")

        assert result is None

    def test_fetch_validates_url_scheme(self):
        """fetch() should reject URLs without http/https scheme."""
        from src.scrapers.network import StealthFetcher, InvalidURLError

        fetcher = StealthFetcher()

        with pytest.raises(InvalidURLError):
            fetcher.fetch("ftp://invalid-scheme.com")

        with pytest.raises(InvalidURLError):
            fetcher.fetch("not-a-url")


class TestStealthFetcherRetryBehavior:
    """Tests for retry logic in StealthFetcher."""

    def test_retries_on_403_forbidden(self):
        """fetch() should retry on 403 Forbidden response."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(max_retries=3, base_delay=0.01)

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            if call_count[0] < 3:
                mock_response.status_code = 403
                mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
            else:
                mock_response.status_code = 200
                mock_response.text = "<html>Success</html>"
                mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            result = fetcher.fetch("https://example.com")

        assert call_count[0] == 3  # Tried 3 times
        assert result is not None
        assert "Success" in result

    def test_retries_on_429_rate_limit(self):
        """fetch() should retry on 429 Too Many Requests."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(max_retries=3, base_delay=0.01)

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            if call_count[0] < 2:
                mock_response.status_code = 429
                mock_response.headers = {"Retry-After": "1"}
                mock_response.raise_for_status.side_effect = Exception("429 Rate Limited")
            else:
                mock_response.status_code = 200
                mock_response.text = "<html>Success after rate limit</html>"
                mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            result = fetcher.fetch("https://example.com")

        assert call_count[0] == 2
        assert result is not None

    def test_retries_on_connection_error(self):
        """fetch() should retry on connection errors."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(max_retries=3, base_delay=0.01)

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("Connection failed")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "<html>Success</html>"
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            result = fetcher.fetch("https://example.com")

        assert call_count[0] == 3
        assert result is not None

    def test_exponential_backoff_timing(self):
        """fetch() should use exponential backoff between retries."""
        from src.scrapers.network import StealthFetcher

        # Base delay of 0.1s for faster testing
        fetcher = StealthFetcher(max_retries=3, base_delay=0.1)

        retry_times = []

        def mock_get(*args, **kwargs):
            retry_times.append(time.time())
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.raise_for_status.side_effect = Exception("503 Service Unavailable")
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            fetcher.fetch("https://example.com")

        # Should have 3 attempts
        assert len(retry_times) == 3

        # Check delays are increasing (exponential backoff)
        # Delay between attempt 1 and 2 should be less than delay between 2 and 3
        if len(retry_times) >= 3:
            delay_1_2 = retry_times[1] - retry_times[0]
            delay_2_3 = retry_times[2] - retry_times[1]
            # With some tolerance for execution time variance
            assert delay_2_3 >= delay_1_2 * 0.8  # Second delay should be >= first

    def test_respects_retry_after_header(self):
        """fetch() should respect Retry-After header on 429 responses."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(max_retries=2, base_delay=0.01)

        retry_times = []

        def mock_get(*args, **kwargs):
            retry_times.append(time.time())
            mock_response = MagicMock()
            if len(retry_times) == 1:
                mock_response.status_code = 429
                mock_response.headers = {"Retry-After": "0.2"}  # 200ms
                mock_response.raise_for_status.side_effect = Exception("429")
            else:
                mock_response.status_code = 200
                mock_response.text = "<html>Success</html>"
                mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            result = fetcher.fetch("https://example.com")

        assert len(retry_times) == 2
        # Should have waited at least 0.2 seconds (with some tolerance)
        actual_delay = retry_times[1] - retry_times[0]
        assert actual_delay >= 0.15  # Allow some tolerance


class TestStealthFetcherBrowserImpersonation:
    """Tests for browser impersonation in StealthFetcher."""

    def test_uses_chrome110_impersonation(self):
        """fetch() should use impersonate='chrome110' for curl_cffi."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher()

        captured_kwargs = {}

        def mock_get(url, **kwargs):
            captured_kwargs.update(kwargs)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "<html>Test</html>"
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            fetcher.fetch("https://example.com")

        assert captured_kwargs.get("impersonate") == "chrome110"

    def test_includes_realistic_headers(self):
        """fetch() should include realistic browser headers."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher()

        captured_kwargs = {}

        def mock_get(url, **kwargs):
            captured_kwargs.update(kwargs)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "<html>Test</html>"
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            fetcher.fetch("https://www.dawn.com/news/12345")

        headers = captured_kwargs.get("headers", {})

        # Should have Accept header
        assert "Accept" in headers
        assert "text/html" in headers["Accept"]

        # Should have Accept-Language
        assert "Accept-Language" in headers

    def test_includes_referer_header(self):
        """fetch() should include Referer header based on URL domain."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher()

        captured_kwargs = {}

        def mock_get(url, **kwargs):
            captured_kwargs.update(kwargs)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "<html>Test</html>"
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            fetcher.fetch("https://www.dawn.com/news/12345/article-slug")

        headers = captured_kwargs.get("headers", {})

        # Should have Referer pointing to the domain homepage
        assert "Referer" in headers
        assert "dawn.com" in headers["Referer"]


class TestStealthFetcherRateLimiting:
    """Tests for rate limiting in StealthFetcher."""

    def test_enforces_minimum_delay_between_requests(self):
        """fetch() should wait between consecutive requests."""
        from src.scrapers.network import StealthFetcher

        # Use 0.2 second minimum delay for testing
        fetcher = StealthFetcher(min_delay=0.2, max_delay=0.3)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Test</html>"
        mock_response.raise_for_status = MagicMock()

        request_times = []

        def mock_get(*args, **kwargs):
            request_times.append(time.time())
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            fetcher.fetch("https://example.com/page1")
            fetcher.fetch("https://example.com/page2")
            fetcher.fetch("https://example.com/page3")

        assert len(request_times) == 3

        # Check delays between requests
        delay_1_2 = request_times[1] - request_times[0]
        delay_2_3 = request_times[2] - request_times[1]

        # Should have waited at least min_delay (with some tolerance)
        assert delay_1_2 >= 0.15
        assert delay_2_3 >= 0.15

    def test_random_delay_within_range(self):
        """fetch() should use random delay within configured range."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(min_delay=1.0, max_delay=3.0)

        # Access internal delay calculation
        delays = [fetcher._get_random_delay() for _ in range(10)]

        for delay in delays:
            assert 1.0 <= delay <= 3.0

        # Check there's some variance (not all the same)
        assert len(set(delays)) > 1


class TestStealthFetcherStatistics:
    """Tests for request statistics tracking."""

    def test_tracks_request_count(self):
        """StealthFetcher should track total requests made."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(min_delay=0, max_delay=0)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Test</html>"
        mock_response.raise_for_status = MagicMock()

        with patch("src.scrapers.network.requests.get", return_value=mock_response):
            fetcher.fetch("https://example.com/1")
            fetcher.fetch("https://example.com/2")
            fetcher.fetch("https://example.com/3")

        stats = fetcher.get_stats()
        assert stats["total_requests"] == 3

    def test_tracks_success_count(self):
        """StealthFetcher should track successful requests."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(min_delay=0, max_delay=0, max_retries=1, base_delay=0)

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            if call_count[0] == 2:  # Second request fails
                mock_response.status_code = 500
                mock_response.raise_for_status.side_effect = Exception("500")
            else:
                mock_response.status_code = 200
                mock_response.text = "<html>Success</html>"
                mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            fetcher.fetch("https://example.com/1")  # Success
            fetcher.fetch("https://example.com/2")  # Fail
            fetcher.fetch("https://example.com/3")  # Success

        stats = fetcher.get_stats()
        assert stats["successful_requests"] == 2
        assert stats["failed_requests"] == 1

    def test_tracks_retry_count(self):
        """StealthFetcher should track total retry attempts."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(min_delay=0, max_delay=0, max_retries=3, base_delay=0.01)

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            if call_count[0] < 3:
                mock_response.status_code = 503
                mock_response.raise_for_status.side_effect = Exception("503")
            else:
                mock_response.status_code = 200
                mock_response.text = "<html>Success</html>"
                mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("src.scrapers.network.requests.get", side_effect=mock_get):
            fetcher.fetch("https://example.com")

        stats = fetcher.get_stats()
        assert stats["total_retries"] == 2  # 2 retries before success


@pytest.mark.integration
class TestStealthFetcherIntegration:
    """Integration tests against real sites (marked for selective running)."""

    def test_fetch_httpbin_returns_html(self):
        """Integration: fetch from httpbin.org should return response."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(min_delay=0.5, max_delay=1.0)

        result = fetcher.fetch("https://httpbin.org/html")

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 100
        # httpbin.org/html returns a simple HTML page
        assert "<html>" in result.lower() or "<!doctype" in result.lower()

    def test_fetch_example_com(self):
        """Integration: fetch from example.com should work."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(min_delay=0.5, max_delay=1.0)

        result = fetcher.fetch("https://example.com")

        assert result is not None
        assert "Example Domain" in result

    @pytest.mark.slow
    def test_fetch_dawn_homepage(self):
        """Integration: attempt to fetch Dawn.com homepage."""
        from src.scrapers.network import StealthFetcher

        fetcher = StealthFetcher(
            min_delay=1.0,
            max_delay=2.0,
            max_retries=3,
            base_delay=2.0,
        )

        result = fetcher.fetch("https://www.dawn.com")

        # May be blocked, but should not crash
        if result is not None:
            assert isinstance(result, str)
            assert len(result) > 1000
            print(f"✓ Dawn homepage fetched successfully ({len(result)} chars)")
        else:
            pytest.skip("Dawn.com blocked request - this is expected behavior")
