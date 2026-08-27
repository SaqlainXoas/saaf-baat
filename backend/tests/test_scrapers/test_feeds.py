"""
Tests for the RSS + news-sitemap ingest.

Offline: every endpoint is served from an in-test fixture through the injected
fetcher, and "now" is injected too, so the freshness gate is exercised with
exact ages rather than wall-clock luck.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.scrapers.feeds import (
    BODY_FULL,
    BODY_HEADLINE_ONLY,
    BODY_SUMMARY,
    CHANNEL_RSS,
    CHANNEL_SITEMAP,
    STATUS_EMPTY,
    STATUS_NO_DATES,
    STATUS_OK,
    STATUS_STALE,
    STATUS_UNREACHABLE,
    FeedIngestor,
    SourceSpec,
)

NOW = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
LONG_BODY = "Pakistan economic policy detail. " * 40  # ~1300 chars


def rfc822(moment: datetime) -> str:
    return moment.strftime("%a, %d %b %Y %H:%M:%S +0000")


def rss(items, *, title="Feed") -> bytes:
    entries = []
    for item in items:
        categories = "".join(f"<category>{c}</category>" for c in item.get("categories", []))
        body = item.get("body")
        content = (
            f"<content:encoded><![CDATA[{body}]]></content:encoded>" if body else ""
        )
        entries.append(
            f"""<item>
              <title>{item['title']}</title>
              <link>{item['link']}</link>
              <pubDate>{rfc822(item['published'])}</pubDate>
              {categories}
              {content}
            </item>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
      <channel><title>{title}</title>{''.join(entries)}</channel>
    </rss>""".encode()


def sitemap(items, *, cdata_titles: bool = False) -> bytes:
    urls = []
    for item in items:
        published = item.get("published")
        date_tag = (
            f"<news:publication_date>{published.isoformat()}</news:publication_date>"
            if published
            else ""
        )
        title = f"<![CDATA[{item['title']}]]>" if cdata_titles else item["title"]
        urls.append(
            f"""<url>
              <loc>{item['link']}</loc>
              <news:news>
                {date_tag}
                <news:title>{title}</news:title>
              </news:news>
            </url>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      {''.join(urls)}
    </urlset>""".encode()


def make_ingestor(sources, payloads, **kwargs) -> FeedIngestor:
    def fetcher(url):
        payload = payloads.get(url)
        if payload is None:
            return 404, b""
        if isinstance(payload, tuple):
            return payload
        return 200, payload

    return FeedIngestor(sources, fetcher=fetcher, now=lambda: NOW, **kwargs)


DAWN = SourceSpec(
    name="dawn",
    url="https://www.dawn.com",
    tier="A",
    feed_urls=("https://www.dawn.com/feeds/pakistan",),
)
GEO = SourceSpec(
    name="geo",
    url="https://www.geo.tv",
    tier="B",
    feed_urls=("https://www.geo.tv/rss/1/1",),
    sitemap_urls=("https://www.geo.tv/news.xml",),
)


class TestHealthGate:
    def test_stale_feed_is_quarantined_and_contributes_nothing(self):
        """The trap: HTTP 200, well-formed, 9 months old."""
        payload = rss(
            [
                {
                    "title": "November headline",
                    "link": "https://www.dawn.com/news/1",
                    "published": NOW - timedelta(days=276),
                    "body": LONG_BODY,
                }
            ]
        )
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: payload}).run()

        report = result.reports[0]
        assert report.status == STATUS_STALE
        assert report.newest_age_hours == pytest.approx(276 * 24, rel=0.01)
        assert report.item_count == 0
        assert result.articles == []
        assert result.degraded_labels == ["dawn:rss:STALE"]

    def test_feed_at_the_threshold_is_still_accepted(self):
        payload = rss(
            [
                {
                    "title": "Just inside the window",
                    "link": "https://www.dawn.com/news/1",
                    "published": NOW - timedelta(hours=47),
                    "body": LONG_BODY,
                }
            ]
        )
        result = make_ingestor(
            [DAWN], {DAWN.feed_urls[0]: payload}, article_max_age_hours=48
        ).run()

        assert result.reports[0].status == STATUS_OK
        assert len(result.articles) == 1

    def test_feed_without_dates_is_quarantined(self):
        payload = b"""<?xml version="1.0"?><rss version="2.0"><channel>
          <item><title>Undated</title><link>https://www.dawn.com/news/1</link></item>
        </channel></rss>"""
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: payload}).run()

        assert result.reports[0].status == STATUS_NO_DATES
        assert result.articles == []

    def test_sitemap_without_publication_dates_is_quarantined(self):
        payload = sitemap([{"title": "No date", "link": "https://www.geo.tv/latest/1"}])
        result = make_ingestor(
            [GEO],
            {GEO.feed_urls[0]: (404, b""), GEO.sitemap_urls[0]: payload},
        ).run()

        sitemap_report = next(r for r in result.reports if r.channel == CHANNEL_SITEMAP)
        assert sitemap_report.status == STATUS_NO_DATES
        assert result.articles == []

    def test_unreachable_and_empty_endpoints_are_reported_not_raised(self):
        empty = b"""<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>"""
        result = make_ingestor(
            [DAWN, GEO],
            {DAWN.feed_urls[0]: (500, b""), GEO.feed_urls[0]: empty},
        ).run()

        by_url = {report.url: report.status for report in result.reports}
        assert by_url[DAWN.feed_urls[0]] == STATUS_UNREACHABLE
        assert by_url[GEO.feed_urls[0]] == STATUS_EMPTY
        assert by_url[GEO.sitemap_urls[0]] == STATUS_UNREACHABLE

    def test_a_healthy_feed_still_drops_its_own_old_items(self):
        payload = rss(
            [
                {
                    "title": "Fresh story",
                    "link": "https://www.dawn.com/news/fresh",
                    "published": NOW - timedelta(hours=2),
                    "body": LONG_BODY,
                },
                {
                    "title": "Archive story",
                    "link": "https://www.dawn.com/news/old",
                    "published": NOW - timedelta(hours=40),
                    "body": LONG_BODY,
                },
            ]
        )
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: payload}).run()

        assert result.reports[0].status == STATUS_OK
        assert [a.headline for a in result.articles] == ["Fresh story"]


class TestArticleConversion:
    def test_full_rss_body_becomes_a_full_article(self):
        payload = rss(
            [
                {
                    "title": "Rupee steadies against dollar",
                    "link": "https://www.dawn.com/news/1",
                    "published": NOW - timedelta(hours=1),
                    "body": LONG_BODY,
                    "categories": ["Business", "Markets"],
                }
            ]
        )
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: payload}).run()

        article = result.articles[0]
        assert article.source == "dawn"
        assert article.metadata["body_status"] == BODY_FULL
        assert article.metadata["source_tier"] == "A"
        assert article.metadata["publisher_categories"] == ["Business", "Markets"]
        assert len(article.main_text) > 600

    def test_short_summary_is_labelled_summary(self):
        payload = rss(
            [
                {
                    "title": "Cabinet meets",
                    "link": "https://www.geo.tv/latest/1",
                    "published": NOW - timedelta(hours=1),
                    "body": "The federal cabinet met on Monday to review the gas tariff proposal.",
                }
            ]
        )
        result = make_ingestor(
            [GEO], {GEO.feed_urls[0]: payload, GEO.sitemap_urls[0]: (404, b"")}
        ).run()

        assert result.articles[0].metadata["body_status"] == BODY_SUMMARY

    def test_sitemap_only_item_keeps_the_headline_as_its_text(self):
        payload = sitemap(
            [
                {
                    "title": "Karachi water supply restored after main burst",
                    "link": "https://www.geo.tv/latest/2",
                    "published": NOW - timedelta(hours=3),
                }
            ]
        )
        result = make_ingestor(
            [GEO], {GEO.feed_urls[0]: (404, b""), GEO.sitemap_urls[0]: payload}
        ).run()

        article = result.articles[0]
        assert article.metadata["body_status"] == BODY_HEADLINE_ONLY
        assert article.main_text == article.headline
        assert article.metadata["discovery_origin"] == CHANNEL_SITEMAP

    def test_off_domain_links_are_dropped(self):
        payload = rss(
            [
                {
                    "title": "Sponsored offer you cannot refuse",
                    "link": "https://ads.example.com/promo",
                    "published": NOW - timedelta(hours=1),
                    "body": LONG_BODY,
                },
                {
                    "title": "Real story",
                    "link": "https://www.dawn.com/news/real",
                    "published": NOW - timedelta(hours=1),
                    "body": LONG_BODY,
                },
            ]
        )
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: payload}).run()

        assert [a.headline for a in result.articles] == ["Real story"]

    def test_cdata_wrapped_sitemap_titles_survive(self):
        """
        Regression: nation.com.pk wraps sitemap titles in CDATA. Stripping the
        wrapper as a tag deleted the headline too, which silently discarded
        every item from that channel.
        """
        payload = sitemap(
            [
                {
                    "title": "Fixing Pakistan's governance crisis starts with local government",
                    "link": "https://www.geo.tv/latest/7",
                    "published": NOW - timedelta(hours=2),
                }
            ],
            cdata_titles=True,
        )
        result = make_ingestor(
            [GEO], {GEO.feed_urls[0]: (404, b""), GEO.sitemap_urls[0]: payload}
        ).run()

        assert [a.headline for a in result.articles] == [
            "Fixing Pakistan's governance crisis starts with local government"
        ]

    def test_cdata_wrapped_rss_bodies_survive(self):
        payload = rss(
            [
                {
                    "title": "Rupee steadies",
                    "link": "https://www.dawn.com/news/1",
                    "published": NOW - timedelta(hours=1),
                    "body": LONG_BODY,
                }
            ]
        )
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: payload}).run()
        assert "CDATA" not in result.articles[0].main_text
        assert result.articles[0].main_text.startswith("Pakistan economic policy detail.")

    def test_items_without_a_headline_are_dropped(self):
        payload = rss(
            [
                {
                    "title": "",
                    "link": "https://www.dawn.com/news/1",
                    "published": NOW - timedelta(hours=1),
                    "body": LONG_BODY,
                }
            ]
        )
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: payload}).run()
        assert result.articles == []


class TestProminenceMetadata:
    """Selection reads source_prominence_score and topline_bucket; keep them true."""

    @pytest.mark.parametrize(
        "rank,expected_bucket,expected_score",
        [(0, "lead", 24), (1, "lead", 24), (3, "topline", 18), (6, "secondary", 10), (20, "tail", 4)],
    )
    def test_rss_position_maps_to_the_feed_column(self, rank, expected_bucket, expected_score):
        items = [
            {
                "title": f"Story {index}",
                "link": f"https://www.dawn.com/news/{index}",
                "published": NOW - timedelta(hours=1),
                "body": LONG_BODY,
            }
            for index in range(rank + 1)
        ]
        result = make_ingestor([DAWN], {DAWN.feed_urls[0]: rss(items)}).run()

        article = next(a for a in result.articles if a.headline == f"Story {rank}")
        assert article.metadata["topline_bucket"] == expected_bucket
        assert article.metadata["source_prominence_score"] == expected_score

    def test_sitemap_position_maps_to_the_lower_unranked_column(self):
        payload = sitemap(
            [
                {
                    "title": "Top of the sitemap",
                    "link": "https://www.geo.tv/latest/1",
                    "published": NOW - timedelta(hours=1),
                }
            ]
        )
        result = make_ingestor(
            [GEO], {GEO.feed_urls[0]: (404, b""), GEO.sitemap_urls[0]: payload}
        ).run()

        article = result.articles[0]
        assert article.metadata["topline_bucket"] == "lead"
        assert article.metadata["source_prominence_score"] == 18


class TestCrossChannelMerge:
    def test_the_record_with_body_text_wins(self):
        url = "https://www.geo.tv/latest/1-cabinet"
        feed = rss(
            [
                {
                    "title": "Cabinet approves tariff",
                    "link": url,
                    "published": NOW - timedelta(hours=2),
                    "body": LONG_BODY,
                    "categories": ["Pakistan"],
                }
            ]
        )
        smap = sitemap(
            [{"title": "Cabinet approves tariff", "link": url, "published": NOW - timedelta(hours=2)}]
        )
        result = make_ingestor(
            [GEO], {GEO.feed_urls[0]: feed, GEO.sitemap_urls[0]: smap}
        ).run()

        assert len(result.articles) == 1
        article = result.articles[0]
        assert article.metadata["discovery_origin"] == CHANNEL_RSS
        assert article.metadata["body_status"] == BODY_FULL
        assert article.metadata["publisher_categories"] == ["Pakistan"]

    def test_urls_differing_only_by_www_or_trailing_slash_are_one_article(self):
        feed = rss(
            [
                {
                    "title": "Same story",
                    "link": "https://www.geo.tv/latest/9-same/",
                    "published": NOW - timedelta(hours=2),
                    "body": LONG_BODY,
                }
            ]
        )
        smap = sitemap(
            [
                {
                    "title": "Same story",
                    "link": "https://geo.tv/latest/9-same",
                    "published": NOW - timedelta(hours=2),
                }
            ]
        )
        result = make_ingestor(
            [GEO], {GEO.feed_urls[0]: feed, GEO.sitemap_urls[0]: smap}
        ).run()

        assert len(result.articles) == 1

    def test_a_dead_feed_does_not_stop_the_sitemap_rescuing_the_source(self):
        """thenews: RSS frozen at November 2025, sitemap current."""
        stale_feed = rss(
            [
                {
                    "title": "Ancient",
                    "link": "https://www.geo.tv/latest/old",
                    "published": NOW - timedelta(days=276),
                    "body": LONG_BODY,
                }
            ]
        )
        fresh_sitemap = sitemap(
            [
                {
                    "title": "Today's story",
                    "link": "https://www.geo.tv/latest/new",
                    "published": NOW - timedelta(hours=1),
                }
            ]
        )
        result = make_ingestor(
            [GEO], {GEO.feed_urls[0]: stale_feed, GEO.sitemap_urls[0]: fresh_sitemap}
        ).run()

        assert result.degraded_labels == ["geo:rss:STALE"]
        assert [a.headline for a in result.articles] == ["Today's story"]


class TestPerSourceCap:
    def test_cap_keeps_the_newest_articles(self):
        items = [
            {
                "title": f"Story {hours}h",
                "link": f"https://www.dawn.com/news/{hours}",
                "published": NOW - timedelta(hours=hours),
                "body": LONG_BODY,
            }
            for hours in (1, 2, 3, 4, 5)
        ]
        result = make_ingestor(
            [DAWN], {DAWN.feed_urls[0]: rss(items)}, max_articles_per_source=2
        ).run()

        assert [a.headline for a in result.articles] == ["Story 1h", "Story 2h"]

    def test_cap_is_applied_per_source_not_globally(self):
        dawn_feed = rss(
            [
                {
                    "title": f"Dawn {i}",
                    "link": f"https://www.dawn.com/news/{i}",
                    "published": NOW - timedelta(hours=i + 1),
                    "body": LONG_BODY,
                }
                for i in range(4)
            ]
        )
        geo_feed = rss(
            [
                {
                    "title": f"Geo {i}",
                    "link": f"https://www.geo.tv/latest/{i}",
                    "published": NOW - timedelta(hours=i + 1),
                    "body": LONG_BODY,
                }
                for i in range(4)
            ]
        )
        result = make_ingestor(
            [DAWN, GEO],
            {
                DAWN.feed_urls[0]: dawn_feed,
                GEO.feed_urls[0]: geo_feed,
                GEO.sitemap_urls[0]: (404, b""),
            },
            max_articles_per_source=2,
        ).run()

        grouped = result.articles_by_source()
        assert len(grouped["dawn"]) == 2
        assert len(grouped["geo"]) == 2


class TestSourceSpec:
    def test_from_config_reads_only_enabled_sources(self):
        specs = SourceSpec.from_config(
            {
                "sources": {
                    "dawn": {
                        "url": "https://www.dawn.com",
                        "tier": "a",
                        "feed_urls": ["https://www.dawn.com/feeds/pakistan"],
                        "sitemap_urls": ["https://www.dawn.com/feeds/sitemap"],
                        "enabled": True,
                    },
                    "samaa": {
                        "url": "https://www.samaa.tv",
                        "tier": "B",
                        "feed_urls": [],
                        "enabled": False,
                    },
                }
            }
        )

        assert [spec.name for spec in specs] == ["dawn"]
        assert specs[0].tier == "A"
        assert specs[0].sitemap_urls == ("https://www.dawn.com/feeds/sitemap",)

    def test_no_endpoints_means_no_work_and_no_crash(self):
        result = FeedIngestor([]).run()
        assert result.articles == []
        assert result.reports == []


class TestRealConfig:
    def test_shipped_sources_yaml_builds_specs(self):
        from pathlib import Path

        import yaml

        config = yaml.safe_load(
            (Path(__file__).resolve().parents[2] / "config" / "sources.yaml").read_text(
                encoding="utf-8"
            )
        )
        specs = SourceSpec.from_config(config)
        by_name = {spec.name: spec for spec in specs}

        assert "ary" in by_name, "ary should be enabled — its RSS was always healthy"
        assert by_name["thenews"].feed_urls == (), "thenews RSS is frozen at Nov 2025"
        assert by_name["thenews"].sitemap_urls, "thenews is recoverable via sitemap"
        assert "samaa" not in by_name
        assert {by_name[n].tier for n in ("dawn", "tribune", "brecorder")} == {"A"}
        assert not any(
            "rss/1/53" in url for spec in specs for url in spec.feed_urls
        ), "geo rss/1/53 served 295-day-old news and must stay unconfigured"
