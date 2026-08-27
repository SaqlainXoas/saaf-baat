"""Tests for the lazy article-body fetch."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.db.models import RawArticle
from src.scrapers.body import ArticleBodyFetcher

LONG_TEXT = "Federal cabinet approved the revised gas tariff schedule on Monday. " * 20


class StubFetcher:
    """Stands in for StealthFetcher."""

    def __init__(self, responses=None, raises=False):
        self._responses = responses or {}
        self._raises = raises
        self.calls: list[str] = []

    def fetch(self, url: str):
        self.calls.append(url)
        if self._raises:
            raise RuntimeError("blocked")
        return self._responses.get(url)


def make_article(main_text: str, body_status: str = "headline_only") -> RawArticle:
    return RawArticle(
        source="geo",
        url="https://www.geo.tv/latest/1-cabinet-approves-gas-tariff",
        headline="Cabinet approves gas tariff revision",
        main_text=main_text,
        publish_date=datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc),
        metadata={"body_status": body_status},
    )


@pytest.fixture
def extraction(monkeypatch):
    """Control trafilatura so these tests stay about the fetch policy."""
    extracted = {"text": LONG_TEXT}

    def fake_extract(html, **kwargs):
        return extracted["text"] if html else None

    monkeypatch.setattr("src.scrapers.body.trafilatura.extract", fake_extract)
    return extracted


class TestNeedsBody:
    def test_full_articles_are_left_alone(self):
        article = make_article(LONG_TEXT, body_status="full")
        assert ArticleBodyFetcher(StubFetcher()).needs_body(article) is False

    def test_headline_only_articles_need_a_body(self):
        assert ArticleBodyFetcher(StubFetcher()).needs_body(make_article("Short headline")) is True

    def test_a_summary_shorter_than_the_floor_still_needs_a_body(self):
        article = make_article("Two sentence summary of the story. " * 3, body_status="summary")
        assert ArticleBodyFetcher(StubFetcher()).needs_body(article) is True


class TestHydrate:
    def test_fills_in_the_body_and_marks_it_full(self, extraction):
        article = make_article("Cabinet approves gas tariff revision")
        fetcher = ArticleBodyFetcher(StubFetcher({str(article.url): "<html>...</html>"}))

        assert fetcher.hydrate(article) is True
        assert article.main_text == LONG_TEXT.strip()
        assert article.metadata["body_status"] == "full"
        assert article.metadata["body_source"] == "lazy_fetch"
        assert fetcher.stats.hydrated == 1

    def test_content_hash_is_not_rewritten(self, extraction):
        article = make_article("Cabinet approves gas tariff revision")
        original_hash = article.content_hash
        fetcher = ArticleBodyFetcher(StubFetcher({str(article.url): "<html>...</html>"}))

        fetcher.hydrate(article)

        assert article.content_hash == original_hash

    def test_a_blocked_fetch_leaves_the_article_untouched(self, extraction):
        article = make_article("Cabinet approves gas tariff revision")
        fetcher = ArticleBodyFetcher(StubFetcher({}))  # returns None, like a 403

        assert fetcher.hydrate(article) is False
        assert article.main_text == "Cabinet approves gas tariff revision"
        assert fetcher.stats.failed == 1

    def test_a_raising_fetcher_is_swallowed(self, extraction):
        article = make_article("Cabinet approves gas tariff revision")
        fetcher = ArticleBodyFetcher(StubFetcher(raises=True))

        assert fetcher.hydrate(article) is False
        assert fetcher.stats.failed == 1

    def test_thin_extraction_is_rejected(self, extraction):
        extraction["text"] = "Subscribe to continue reading."
        article = make_article("Cabinet approves gas tariff revision")
        fetcher = ArticleBodyFetcher(StubFetcher({str(article.url): "<html>...</html>"}))

        assert fetcher.hydrate(article) is False
        assert article.metadata["body_status"] == "headline_only"

    def test_a_full_article_is_never_fetched(self, extraction):
        article = make_article(LONG_TEXT, body_status="full")
        stub = StubFetcher({str(article.url): "<html>...</html>"})

        assert ArticleBodyFetcher(stub).hydrate(article) is False
        assert stub.calls == []
