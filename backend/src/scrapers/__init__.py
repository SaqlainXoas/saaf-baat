"""
Saaf Baat scraping system.

Three-tier architecture:
  Tier 1 — URL Discovery:  FeedDiscoverer (RSS) → HTML scrape + regex
  Tier 2 — Content Fetch:  StealthFetcher (curl_cffi) → Playwright (session-reused)
  Tier 3 — Content Parse:  ContentParser (trafilatura → newspaper4k → readability)
"""
from src.scrapers.network import StealthFetcher, InvalidURLError
from src.scrapers.parsers import ContentParser
from src.scrapers.dtos import ScrapedArticle
from src.scrapers.hybrid_orchestrator import HybridOrchestrator
from src.scrapers.feed import FeedDiscoverer

__all__ = [
    "HybridOrchestrator",
    "StealthFetcher",
    "ContentParser",
    "ScrapedArticle",
    "InvalidURLError",
    "FeedDiscoverer",
]
