"""
Saaf Baat scraping system.

Multi-tier scraping architecture:
1. Newspaper4k (primary) - Fast, works for most static sites
2. News-please (fallback) - Alternative extraction algorithms
3. Playwright (JS-heavy) - Full browser for dynamic content
"""
from src.scrapers.base import (
    BaseScraper,
    ScrapingError,
    InvalidURLError,
    RateLimitError,
    ContentExtractionError,
    TimeoutError,
)
from src.scrapers.newspaper4k_scraper import Newspaper4kScraper
from src.scrapers.newsplease_scraper import NewsPleaseScraaper
from src.scrapers.playwright_scraper import PlaywrightScraper
from src.scrapers.orchestrator import (
    ScraperOrchestrator,
    SourceConfig,
    ScrapingResult,
    ConfigValidationError,
    load_scraper_config,
    validate_scraper_config,
)


__all__ = [
    # Base
    "BaseScraper",
    "ScrapingError",
    "InvalidURLError",
    "RateLimitError",
    "ContentExtractionError",
    "TimeoutError",
    # Scrapers
    "Newspaper4kScraper",
    "NewsPleaseScraaper",
    "PlaywrightScraper",
    # Orchestrator
    "ScraperOrchestrator",
    "SourceConfig",
    "ScrapingResult",
    "ConfigValidationError",
    "load_scraper_config",
    "validate_scraper_config",
]