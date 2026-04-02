"""
Stealth Network Layer for the Hybrid Scraping Architecture.

Uses curl_cffi with Chrome browser impersonation to bypass
Cloudflare and other anti-bot protections.
"""

import os
import random
import time
from typing import Dict, Optional
from urllib.parse import urlparse

from curl_cffi import requests


class InvalidURLError(Exception):
    """Raised when URL scheme is invalid."""
    pass


class StealthFetcher:
    """
    Stealth HTTP fetcher using curl_cffi with browser impersonation.

    Features:
    - Chrome 110 browser fingerprint impersonation
    - Automatic retry with exponential backoff on 403/429/5xx
    - Realistic browser headers with dynamic Referer
    - Random delays between requests to avoid detection
    - Request statistics tracking

    Example:
        fetcher = StealthFetcher()
        html = fetcher.fetch("https://www.dawn.com/news/12345")
        if html:
            # Process HTML
            pass
    """

    # Retry-able HTTP status codes
    RETRY_STATUS_CODES = {403, 429, 500, 502, 503, 504}

    def __init__(
        self,
        max_retries: int | None = None,
        base_delay: float | None = None,
        min_delay: float | None = None,
        max_delay: float | None = None,
        timeout: float | None = None,
    ):
        """
        Initialize StealthFetcher.

        Args:
            max_retries: Maximum retry attempts on failure (default: 3)
            base_delay: Base delay for exponential backoff in seconds (default: 1.0)
            min_delay: Minimum delay between requests in seconds (default: 1.0)
            max_delay: Maximum delay between requests in seconds (default: 3.0)
            timeout: Request timeout in seconds (default: 30.0)
        """
        self.max_retries = int(
            max_retries
            if max_retries is not None
            else _env_int("SAAF_SCRAPER_MAX_RETRIES", 3)
        )
        self.base_delay = float(
            base_delay
            if base_delay is not None
            else _env_float("SAAF_SCRAPER_BASE_DELAY", 1.0)
        )
        self.min_delay = float(
            min_delay
            if min_delay is not None
            else _env_float("SAAF_SCRAPER_MIN_DELAY", 1.0)
        )
        self.max_delay = float(
            max_delay
            if max_delay is not None
            else _env_float("SAAF_SCRAPER_MAX_DELAY", 3.0)
        )
        self.timeout = float(
            timeout
            if timeout is not None
            else _env_float("SAAF_SCRAPER_TIMEOUT", 30.0)
        )

        if self.max_retries <= 0:
            self.max_retries = 3
        if self.base_delay < 0:
            self.base_delay = 1.0
        if self.min_delay < 0:
            self.min_delay = 0.0
        if self.max_delay < self.min_delay:
            self.max_delay = self.min_delay
        if self.timeout <= 0:
            self.timeout = 30.0

        # Track last request time for rate limiting
        self._last_request_time: Optional[float] = None

        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_retries = 0

    def fetch(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from URL using stealth browser impersonation.

        Args:
            url: The URL to fetch

        Returns:
            HTML string on success, None on failure after all retries

        Raises:
            InvalidURLError: If URL scheme is not http or https
        """
        # Validate URL scheme
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise InvalidURLError(f"Invalid URL scheme: {parsed.scheme}. Must be http or https.")

        # Apply rate limiting delay
        self._apply_rate_limit()

        # Build request headers
        headers = self._build_headers(url)

        # Attempt fetch with retries
        for attempt in range(self.max_retries):
            self._total_requests += 1

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    impersonate="chrome110",
                )

                # Check for retry-able status codes
                if response.status_code in self.RETRY_STATUS_CODES:
                    self._total_retries += 1

                    # Check for Retry-After header
                    retry_after = self._get_retry_after(response)

                    if attempt < self.max_retries - 1:
                        # Calculate delay with exponential backoff
                        if retry_after:
                            delay = retry_after
                        else:
                            delay = self.base_delay * (2 ** attempt)

                        time.sleep(delay)
                        continue

                # Success
                if response.status_code == 200:
                    self._successful_requests += 1
                    self._last_request_time = time.time()
                    return response.text

                # Non-retryable error
                response.raise_for_status()

            except ConnectionError:
                self._total_retries += 1
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue

            except Exception:
                self._total_retries += 1
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue

        # All retries exhausted
        self._failed_requests += 1
        return None

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting delay between requests."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            required_delay = self._get_random_delay()

            if elapsed < required_delay:
                time.sleep(required_delay - elapsed)

        self._last_request_time = time.time()

    def _get_random_delay(self) -> float:
        """Get a random delay within the configured range."""
        return random.uniform(self.min_delay, self.max_delay)

    def _build_headers(self, url: str) -> Dict[str, str]:
        """
        Build realistic browser headers for the request.

        Args:
            url: The URL being requested (used to set Referer)

        Returns:
            Dictionary of HTTP headers
        """
        parsed = urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"

        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Referer": referer,
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="110", "Google Chrome";v="110"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def _get_retry_after(self, response) -> Optional[float]:
        """
        Extract Retry-After header value in seconds.

        Args:
            response: The HTTP response object

        Returns:
            Delay in seconds, or None if header not present
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                # Retry-After might be a date string, ignore for now
                pass
        return None

    def get_stats(self) -> Dict[str, int]:
        """
        Get request statistics.

        Returns:
            Dictionary with total_requests, successful_requests,
            failed_requests, and total_retries
        """
        return {
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "total_retries": self._total_retries,
        }

    def reset_stats(self) -> None:
        """Reset all statistics counters."""
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_retries = 0


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
