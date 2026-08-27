"""
Live integration tests for the ingest layer.

These hit the real publisher endpoints. Run with:
    pytest -m integration tests/test_scrapers/test_live_scraping.py -v

They answer the questions a green unit suite cannot: are the configured
endpoints actually alive today, is the health gate firing on the ones that are
not, and does a Tier A feed still ship the full article body?
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from src.db.factory import create_db_client
from src.db.models import RawArticle
from src.scrapers.body import ArticleBodyFetcher
from src.scrapers.feeds import (
    BODY_FULL,
    CHANNEL_RSS,
    STATUS_OK,
    FeedIngestor,
    SourceSpec,
)
from src.scrapers.network import StealthFetcher

_BACKEND_DIR = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def source_specs() -> list[SourceSpec]:
    config = yaml.safe_load((_BACKEND_DIR / "config" / "sources.yaml").read_text(encoding="utf-8"))
    return SourceSpec.from_config(config)


@pytest.fixture(scope="module")
def live_result(source_specs):
    return FeedIngestor(source_specs, max_articles_per_source=40).run()


class TestLiveEndpointHealth:
    def test_most_endpoints_are_reachable_and_fresh(self, live_result):
        healthy = [r for r in live_result.reports if r.status == STATUS_OK]
        assert live_result.reports, "no endpoints were probed"
        assert len(healthy) >= len(live_result.reports) // 2, (
            "more than half of the configured endpoints are unhealthy: "
            f"{[r.label for r in live_result.quarantined]}"
        )

    def test_quarantined_endpoints_contribute_no_articles(self, live_result):
        for report in live_result.quarantined:
            assert report.item_count == 0, f"{report.label} leaked {report.item_count} items"

    def test_every_source_reports_at_least_one_endpoint(self, live_result, source_specs):
        reported = {report.source for report in live_result.reports}
        assert reported == {spec.name for spec in source_specs}


class TestLiveArticleQuality:
    def test_pool_is_materially_larger_than_the_old_scraper(self, live_result):
        # The HTML scraper managed ~30 articles per run across three sources.
        assert len(live_result.articles) >= 100, len(live_result.articles)

    def test_every_article_is_fresh_and_dated(self, live_result):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        for article in live_result.articles:
            assert article.publish_date is not None
            published = article.publish_date
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            assert published >= cutoff, f"{article.url} is stale: {published}"

    def test_tier_a_sources_ship_full_bodies_in_rss(self, live_result):
        bodies = [
            len(article.main_text)
            for article in live_result.articles
            if (article.metadata or {}).get("source_tier") == "A"
            and (article.metadata or {}).get("body_status") == BODY_FULL
            and (article.metadata or {}).get("discovery_origin") == CHANNEL_RSS
        ]
        assert len(bodies) >= 20, f"only {len(bodies)} Tier A full-text articles"
        assert statistics.median(bodies) >= 1000

    def test_articles_carry_the_metadata_selection_reads(self, live_result):
        for article in live_result.articles[:50]:
            metadata = article.metadata or {}
            assert metadata["source_prominence_score"] > 0
            assert metadata["topline_bucket"] in {"lead", "topline", "secondary", "tail"}
            assert metadata["body_status"] in {"full", "summary", "headline_only"}


class TestLiveBodyFetch:
    def test_hydrates_a_headline_only_article(self, live_result):
        fetcher = ArticleBodyFetcher()
        thin = [a for a in live_result.articles if fetcher.needs_body(a)]
        if not thin:
            pytest.skip("every discovered article already carried a usable body")

        for article in thin[:5]:
            if fetcher.hydrate(article):
                assert len(article.main_text) >= fetcher.min_chars
                assert (article.metadata or {}).get("body_status") == BODY_FULL
                return
        pytest.skip("no body could be fetched from the first five thin articles")


class TestLiveStealthFetcher:
    def test_fetches_a_publisher_homepage(self):
        html = StealthFetcher().fetch("https://www.dawn.com")
        assert html and len(html) > 1000


class TestLiveIngestToDatabase:
    def test_discovered_articles_round_trip_through_the_db(self, live_result, tmp_path, monkeypatch):
        monkeypatch.setenv("SAAF_DB_BACKEND", "sqlite")
        monkeypatch.setenv("SAAF_SQLITE_PATH", str(tmp_path / "live.db"))
        db = create_db_client()
        try:
            stored = 0
            for article in live_result.articles[:10]:
                db.insert_article(article)
                stored += 1
            assert stored == 10
            loaded = db.get_recent_articles(limit=10)
            assert len(loaded) == 10
            assert all(isinstance(row, RawArticle) for row in loaded)
            assert all(row.metadata.get("discovery_origin") for row in loaded)
        finally:
            db.close()
