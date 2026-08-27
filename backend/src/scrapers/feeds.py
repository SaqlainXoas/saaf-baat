"""
RSS + news-sitemap ingest.

Two independent discovery channels, health-gated:

  1. Publisher RSS feeds — Tier A publishers ship the full article body in
     ``content:encoded``, so no page fetch is needed at all.
  2. Google-News sitemaps — an explicit, dated 48h index that rescues sources
     whose RSS is dead and finds stories RSS misses.

Every endpoint is gated on the age of its newest item before a single article
is accepted. Two live endpoints return HTTP 200 with well-formed feeds of
~9-month-old news; nothing else in the response signals the problem, so this
gate is the safety mechanism of the whole layer, not an optimisation.

Ported from ``scripts/research/prototype_ingest.py``, which proved the design
end to end against the real sources.
"""

from __future__ import annotations

import html as html_mod
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import feedparser
import requests

from src.db.models import RawArticle
from src.utils.urls import canonicalize_url_for_dedup, host_allowed_for_base

logger = logging.getLogger(__name__)


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_STALE_FEED_HOURS = 48
DEFAULT_ARTICLE_MAX_AGE_HOURS = 36
DEFAULT_FULL_TEXT_MIN_CHARS = 600
DEFAULT_MAX_WORKERS = 16
DEFAULT_TIMEOUT = 25.0

CHANNEL_RSS = "rss"
CHANNEL_SITEMAP = "sitemap"

STATUS_OK = "ok"
STATUS_STALE = "STALE"
STATUS_NO_DATES = "no-dates"
STATUS_EMPTY = "empty"
STATUS_UNREACHABLE = "unreachable"

# Discovery prominence, preserved from the retired HTML scraper so the
# selection layer keeps reading the same two metadata keys with the same
# meaning. RSS position is a real editorial signal (it is the publisher's own
# ordering); a Google-News sitemap is reverse-chronological rather than ranked,
# so it maps onto the lower, unranked-discovery column.
_PROMINENCE_BUCKETS: Tuple[Tuple[int, str, Dict[str, int]], ...] = (
    (1, "lead", {CHANNEL_RSS: 24, CHANNEL_SITEMAP: 18}),
    (4, "topline", {CHANNEL_RSS: 18, CHANNEL_SITEMAP: 13}),
    (8, "secondary", {CHANNEL_RSS: 10, CHANNEL_SITEMAP: 7}),
)
_TAIL_PROMINENCE: Dict[str, int] = {CHANNEL_RSS: 4, CHANNEL_SITEMAP: 2}

BODY_FULL = "full"
BODY_SUMMARY = "summary"
BODY_HEADLINE_ONLY = "headline_only"

# (status_code, payload). status_code 0 means the request never completed.
FetchResult = Tuple[int, bytes]
Fetcher = Callable[[str], FetchResult]
Clock = Callable[[], datetime]


_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def clean(raw: str) -> str:
    """
    Strip tags and collapse whitespace in publisher-supplied markup.

    CDATA sections are unwrapped rather than stripped: several publishers wrap
    sitemap titles in CDATA, and a naive tag strip deletes the headline along
    with its wrapper, which silently discards the whole item.
    """
    unwrapped = _CDATA_RE.sub(r"\1", raw or "")
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", unwrapped))).strip()


def entry_body(entry: Any) -> str:
    """Return the longest body-ish field an RSS entry offers."""
    best = ""
    for key in ("content", "summary", "description"):
        value = entry.get(key)
        if isinstance(value, list) and value:
            value = value[0].get("value", "")
        if isinstance(value, dict):
            value = value.get("value", "")
        if isinstance(value, str) and len(value) > len(best):
            best = value
    return clean(best)


def entry_date(entry: Any) -> Optional[datetime]:
    """Return the publisher-supplied timestamp for an RSS entry, as UTC."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if not parsed:
            continue
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def default_fetcher(url: str, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:
    """Plain GET with a real User-Agent. Never raises."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except Exception as exc:
        logger.warning("Endpoint fetch failed for %s: %s", url, exc)
        return 0, b""
    return int(response.status_code), response.content


@dataclass(frozen=True)
class SourceSpec:
    """One configured publisher and its endpoints."""

    name: str
    url: str
    tier: str
    feed_urls: Tuple[str, ...] = ()
    sitemap_urls: Tuple[str, ...] = ()

    @classmethod
    def from_config(cls, sources_config: Dict[str, Any]) -> List["SourceSpec"]:
        """Build specs for the enabled sources in a parsed ``sources.yaml``."""
        specs: List[SourceSpec] = []
        for name, spec in (sources_config.get("sources") or {}).items():
            if not (spec or {}).get("enabled", False):
                continue
            specs.append(
                cls(
                    name=str(name),
                    url=str(spec.get("url") or ""),
                    tier=str(spec.get("tier") or "B").upper(),
                    feed_urls=tuple(str(u) for u in (spec.get("feed_urls") or [])),
                    sitemap_urls=tuple(str(u) for u in (spec.get("sitemap_urls") or [])),
                )
            )
        return specs


@dataclass(frozen=True)
class EndpointReport:
    """Health of a single feed or sitemap endpoint for one run."""

    source: str
    channel: str
    url: str
    status: str
    newest_age_hours: Optional[float] = None
    item_count: int = 0

    @property
    def is_healthy(self) -> bool:
        return self.status == STATUS_OK

    @property
    def label(self) -> str:
        return f"{self.source}:{self.channel}:{self.status}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "channel": self.channel,
            "url": self.url,
            "status": self.status,
            "newest_age_hours": self.newest_age_hours,
            "item_count": self.item_count,
        }


@dataclass(frozen=True)
class DiscoveredItem:
    """One article as discovered, before conversion to a RawArticle."""

    source: str
    tier: str
    channel: str
    url: str
    canonical_url: str
    headline: str
    body: str
    published: datetime
    categories: Tuple[str, ...]
    discovery_rank: int
    endpoint: str


@dataclass
class IngestResult:
    articles: List[RawArticle] = field(default_factory=list)
    reports: List[EndpointReport] = field(default_factory=list)
    discovery_seconds: float = 0.0

    @property
    def quarantined(self) -> List[EndpointReport]:
        return [report for report in self.reports if not report.is_healthy]

    @property
    def degraded_labels(self) -> List[str]:
        return [report.label for report in self.quarantined]

    def articles_by_source(self) -> Dict[str, List[RawArticle]]:
        grouped: Dict[str, List[RawArticle]] = {}
        for article in self.articles:
            grouped.setdefault(article.source, []).append(article)
        return grouped


class FeedIngestor:
    """
    Read every configured endpoint, gate it on freshness, and return articles.

    The fetcher and the clock are injectable so a recorded day can be replayed
    through the real parse/gate/dedup path (see the golden-day harness).
    """

    def __init__(
        self,
        sources: Sequence[SourceSpec],
        *,
        fetcher: Optional[Fetcher] = None,
        now: Optional[Clock] = None,
        stale_feed_hours: int = DEFAULT_STALE_FEED_HOURS,
        article_max_age_hours: int = DEFAULT_ARTICLE_MAX_AGE_HOURS,
        full_text_min_chars: int = DEFAULT_FULL_TEXT_MIN_CHARS,
        max_articles_per_source: Optional[int] = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.sources = list(sources)
        self._fetch = fetcher or (lambda url: default_fetcher(url, timeout))
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.stale_feed_hours = int(stale_feed_hours)
        self.article_max_age_hours = int(article_max_age_hours)
        self.full_text_min_chars = int(full_text_min_chars)
        self.max_articles_per_source = (
            int(max_articles_per_source) if max_articles_per_source else None
        )
        self.max_workers = max(1, int(max_workers))

    # ------------------------------------------------------------------
    # Endpoint readers
    # ------------------------------------------------------------------

    def read_rss(self, source: SourceSpec, url: str) -> Tuple[EndpointReport, List[DiscoveredItem]]:
        now = self._now()
        status_code, payload = self._fetch(url)
        if status_code != 200 or not payload:
            return self._report(source, CHANNEL_RSS, url, STATUS_UNREACHABLE), []

        entries = feedparser.parse(payload).entries or []
        if not entries:
            return self._report(source, CHANNEL_RSS, url, STATUS_EMPTY), []

        dates = [d for d in (entry_date(entry) for entry in entries) if d]
        if not dates:
            return self._report(source, CHANNEL_RSS, url, STATUS_NO_DATES), []

        newest_age = min(self._age_hours(now, d) for d in dates)
        if newest_age > self.stale_feed_hours:
            return (
                self._report(source, CHANNEL_RSS, url, STATUS_STALE, newest_age),
                [],
            )

        items: List[DiscoveredItem] = []
        for rank, entry in enumerate(entries):
            published = entry_date(entry)
            if published is None:
                continue
            if (now - published) > timedelta(hours=self.article_max_age_hours):
                continue
            link = entry.get("link")
            headline = clean(entry.get("title", ""))
            item = self._build_item(
                source=source,
                channel=CHANNEL_RSS,
                endpoint=url,
                link=link,
                headline=headline,
                body=entry_body(entry),
                published=published,
                categories=[t.get("term", "") for t in (entry.get("tags") or [])][:4],
                rank=rank,
            )
            if item is not None:
                items.append(item)

        return (
            self._report(source, CHANNEL_RSS, url, STATUS_OK, newest_age, len(items)),
            items,
        )

    def read_sitemap(
        self, source: SourceSpec, url: str
    ) -> Tuple[EndpointReport, List[DiscoveredItem]]:
        now = self._now()
        status_code, payload = self._fetch(url)
        if status_code != 200 or not payload:
            return self._report(source, CHANNEL_SITEMAP, url, STATUS_UNREACHABLE), []

        body = payload.decode("utf-8", errors="replace")
        blocks = re.findall(r"<url>(.*?)</url>", body, re.S)
        items: List[DiscoveredItem] = []
        ages: List[float] = []
        rank = 0

        for block in blocks:
            loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", block)
            if not loc:
                continue
            published = _parse_sitemap_date(block)
            if published is None:
                continue
            age = self._age_hours(now, published)
            ages.append(age)
            if age > self.article_max_age_hours:
                rank += 1
                continue
            title_match = re.search(r"<news:title>\s*(.*?)\s*</news:title>", block, re.S)
            item = self._build_item(
                source=source,
                channel=CHANNEL_SITEMAP,
                endpoint=url,
                link=loc.group(1),
                headline=clean(title_match.group(1)) if title_match else "",
                body="",
                published=published,
                categories=[],
                rank=rank,
            )
            rank += 1
            if item is not None:
                items.append(item)

        if not ages:
            return self._report(source, CHANNEL_SITEMAP, url, STATUS_NO_DATES), []

        newest_age = min(ages)
        if newest_age > self.stale_feed_hours:
            return (
                self._report(source, CHANNEL_SITEMAP, url, STATUS_STALE, newest_age),
                [],
            )
        return (
            self._report(source, CHANNEL_SITEMAP, url, STATUS_OK, newest_age, len(items)),
            items,
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> IngestResult:
        jobs: List[Tuple[SourceSpec, str, str]] = []
        for source in self.sources:
            for url in source.feed_urls:
                jobs.append((source, CHANNEL_RSS, url))
            for url in source.sitemap_urls:
                jobs.append((source, CHANNEL_SITEMAP, url))

        if not jobs:
            return IngestResult()

        started = _monotonic()
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(jobs))) as pool:
            outcomes = list(pool.map(self._run_job, jobs))
        discovery_seconds = _monotonic() - started

        reports = [report for report, _items in outcomes]
        merged = self._merge(outcomes)
        articles = self._to_articles(merged)

        for report in reports:
            if report.is_healthy:
                logger.info(
                    "Endpoint ok: %s %s newest=%.1fh items=%d",
                    report.source,
                    report.channel,
                    report.newest_age_hours or 0.0,
                    report.item_count,
                )
            else:
                logger.warning(
                    "Endpoint quarantined: %s %s status=%s newest=%s url=%s",
                    report.source,
                    report.channel,
                    report.status,
                    report.newest_age_hours,
                    report.url,
                )

        logger.info(
            "Ingest complete: endpoints=%d quarantined=%d articles=%d duration=%.2fs",
            len(reports),
            sum(1 for report in reports if not report.is_healthy),
            len(articles),
            discovery_seconds,
        )
        return IngestResult(
            articles=articles,
            reports=reports,
            discovery_seconds=discovery_seconds,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_job(
        self, job: Tuple[SourceSpec, str, str]
    ) -> Tuple[EndpointReport, List[DiscoveredItem]]:
        source, channel, url = job
        try:
            if channel == CHANNEL_RSS:
                return self.read_rss(source, url)
            return self.read_sitemap(source, url)
        except Exception as exc:
            logger.exception("Endpoint read crashed for %s (%s): %s", url, channel, exc)
            return self._report(source, channel, url, STATUS_UNREACHABLE), []

    @staticmethod
    def _report(
        source: SourceSpec,
        channel: str,
        url: str,
        status: str,
        newest_age_hours: Optional[float] = None,
        item_count: int = 0,
    ) -> EndpointReport:
        return EndpointReport(
            source=source.name,
            channel=channel,
            url=url,
            status=status,
            newest_age_hours=round(newest_age_hours, 1) if newest_age_hours is not None else None,
            item_count=item_count,
        )

    @staticmethod
    def _age_hours(now: datetime, published: datetime) -> float:
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return (now - published).total_seconds() / 3600.0

    def _build_item(
        self,
        *,
        source: SourceSpec,
        channel: str,
        endpoint: str,
        link: Optional[str],
        headline: str,
        body: str,
        published: datetime,
        categories: Sequence[str],
        rank: int,
    ) -> Optional[DiscoveredItem]:
        if not link or not headline:
            return None
        link = link.strip()
        if not link.startswith(("http://", "https://")):
            return None
        if source.url and not host_allowed_for_base(link, source.url):
            logger.debug("Dropping off-domain link for %s: %s", source.name, link)
            return None
        return DiscoveredItem(
            source=source.name,
            tier=source.tier,
            channel=channel,
            url=link,
            canonical_url=canonicalize_url_for_dedup(link),
            headline=headline,
            body=body,
            published=published,
            categories=tuple(c for c in categories if c),
            discovery_rank=max(0, int(rank)),
            endpoint=endpoint,
        )

    @staticmethod
    def _merge(
        outcomes: Sequence[Tuple[EndpointReport, List[DiscoveredItem]]],
    ) -> List[DiscoveredItem]:
        """
        Collapse the two channels on canonical URL.

        The record carrying body text wins; RSS wins ties, because it also
        carries publisher categories and a real feed position.
        """
        merged: Dict[str, DiscoveredItem] = {}
        for _report, items in outcomes:
            for item in items:
                existing = merged.get(item.canonical_url)
                if existing is None:
                    merged[item.canonical_url] = item
                    continue
                if len(item.body) > len(existing.body) or (
                    len(item.body) == len(existing.body)
                    and item.channel == CHANNEL_RSS
                    and existing.channel != CHANNEL_RSS
                ):
                    categories = item.categories or existing.categories
                    merged[item.canonical_url] = replace_categories(item, categories)
        return list(merged.values())

    def _to_articles(self, items: Sequence[DiscoveredItem]) -> List[RawArticle]:
        by_source: Dict[str, List[DiscoveredItem]] = {}
        for item in items:
            by_source.setdefault(item.source, []).append(item)

        articles: List[RawArticle] = []
        for source_name, source_items in by_source.items():
            # Newest first, RSS ahead of sitemap, so a per-source cap keeps the
            # freshest and best-bodied records.
            source_items.sort(
                key=lambda item: (
                    -item.published.timestamp(),
                    0 if item.channel == CHANNEL_RSS else 1,
                    item.discovery_rank,
                )
            )
            if self.max_articles_per_source:
                source_items = source_items[: self.max_articles_per_source]
            for item in source_items:
                article = self._to_article(item)
                if article is not None:
                    articles.append(article)
            logger.info(
                "Source %s: %d articles after cap", source_name, len(source_items)
            )
        return articles

    def _to_article(self, item: DiscoveredItem) -> Optional[RawArticle]:
        body = item.body.strip()
        if len(body) >= self.full_text_min_chars:
            body_status = BODY_FULL
            main_text = body
        elif len(body) > len(item.headline):
            body_status = BODY_SUMMARY
            main_text = body
        else:
            # Tier B corroboration record: the headline is the signal. The body
            # is fetched lazily, and only if this article is ever selected.
            body_status = BODY_HEADLINE_ONLY
            main_text = item.headline

        bucket, prominence = _prominence(item.channel, item.discovery_rank)
        try:
            return RawArticle(
                source=item.source,
                url=item.url,
                headline=item.headline,
                main_text=main_text,
                publish_date=item.published,
                metadata={
                    "discovery_origin": item.channel,
                    "discovery_rank": item.discovery_rank,
                    "discovery_endpoint": item.endpoint,
                    "source_prominence_score": prominence,
                    "topline_bucket": bucket,
                    "source_tier": item.tier,
                    "publisher_categories": list(item.categories),
                    "body_status": body_status,
                },
            )
        except Exception as exc:
            logger.warning("Skipping malformed article %s: %s", item.url, exc)
            return None


def replace_categories(item: DiscoveredItem, categories: Sequence[str]) -> DiscoveredItem:
    """Return ``item`` with merged publisher categories (frozen dataclass)."""
    if tuple(categories) == item.categories:
        return item
    return DiscoveredItem(
        source=item.source,
        tier=item.tier,
        channel=item.channel,
        url=item.url,
        canonical_url=item.canonical_url,
        headline=item.headline,
        body=item.body,
        published=item.published,
        categories=tuple(categories),
        discovery_rank=item.discovery_rank,
        endpoint=item.endpoint,
    )


def _prominence(channel: str, rank: int) -> Tuple[str, int]:
    for cutoff, bucket, scores in _PROMINENCE_BUCKETS:
        if rank <= cutoff:
            return bucket, scores.get(channel, _TAIL_PROMINENCE.get(channel, 2))
    return "tail", _TAIL_PROMINENCE.get(channel, 2)


def _parse_sitemap_date(block: str) -> Optional[datetime]:
    match = re.search(
        r"<news:publication_date>\s*([^<]+?)\s*</news:publication_date>", block
    )
    if not match:
        return None
    try:
        published = datetime.fromisoformat(match.group(1).strip().replace("Z", "+00:00"))
    except Exception:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published


def _monotonic() -> float:
    import time

    return time.perf_counter()
