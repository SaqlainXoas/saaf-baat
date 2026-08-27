"""
Saaf Baat ingest.

Two deterministic layers, and nothing else:

  Discovery — `FeedIngestor` reads publisher RSS feeds and Google-News
              sitemaps in parallel, quarantines any endpoint whose newest item
              is stale, and merges the two channels on canonical URL.
  Body      — `ArticleBodyFetcher` fetches and extracts a page, but only for a
              selected story whose feed record carried no usable text.

There is no HTML section discovery, no browser fallback, and no parser
ensemble: the publishers already hand over structured, dated, full-text
content, and the failure modes that remain (staleness, blocking) are not
extraction problems.
"""

from src.scrapers.body import ArticleBodyFetcher, BodyFetchStats
from src.scrapers.feeds import (
    EndpointReport,
    FeedIngestor,
    IngestResult,
    SourceSpec,
)
from src.scrapers.network import InvalidURLError, StealthFetcher

__all__ = [
    "ArticleBodyFetcher",
    "BodyFetchStats",
    "EndpointReport",
    "FeedIngestor",
    "IngestResult",
    "SourceSpec",
    "StealthFetcher",
    "InvalidURLError",
]
