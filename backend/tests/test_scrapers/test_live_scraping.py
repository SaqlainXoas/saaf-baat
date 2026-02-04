"""
Live integration tests for scrapers.

These tests hit real news websites to verify scraping works end-to-end.
Run with: pytest -m integration tests/test_scrapers/test_live_scraping.py -v

WARNING: These tests make real HTTP requests to news websites.
         Run sparingly to avoid rate limiting.
         
Uses the HybridOrchestrator with StealthFetcher (curl_cffi) and ContentParser
(trafilatura/newspaper4k/readability) for reliable scraping that bypasses 
bot detection on Pakistani news sites.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.scrapers.hybrid_orchestrator import HybridOrchestrator
from src.scrapers.network import StealthFetcher
from src.scrapers.parsers import ContentParser
from src.scrapers.dtos import ScrapedArticle
from src.db.models import RawArticle


# ============================================================================
# Test Article URLs
# ============================================================================

TEST_SOURCES = {
    "dawn": {
        "base_url": "https://www.dawn.com",
        "sections": ["latest-news", "pakistan", "business"],
        "sample_article_pattern": "/news/",
    },
    "tribune": {
        "base_url": "https://tribune.com.pk",
        "sections": ["latest", "pakistan", "business"],
        "sample_article_pattern": "/story/",
    },
    "geo": {
        "base_url": "https://www.geo.tv",
        "sections": ["latest-news", "pakistan"],
        "sample_article_pattern": "/",
    },
}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sources_config():
    """Load sources configuration."""
    config_path = Path(__file__).parent.parent.parent / "config" / "sources.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def hybrid_orchestrator():
    """Create HybridOrchestrator for testing."""
    return HybridOrchestrator()


@pytest.fixture
def stealth_fetcher():
    """Create StealthFetcher for testing."""
    return StealthFetcher()


@pytest.fixture
def content_parser():
    """Create ContentParser for testing."""
    return ContentParser()


# ============================================================================
# Live Scraping Tests - StealthFetcher
# ============================================================================

@pytest.mark.integration
class TestStealthFetcherLive:
    """Live tests for StealthFetcher with real Pakistani news sites."""
    
    def test_fetch_dawn_homepage(self, stealth_fetcher):
        """
        Test fetching Dawn homepage with stealth.
        
        Dawn has Cloudflare protection - StealthFetcher should bypass it.
        """
        url = "https://www.dawn.com/latest-news"
        
        html = stealth_fetcher.fetch(url)
        
        assert html is not None, "Failed to fetch Dawn homepage"
        assert len(html) > 1000, "HTML content too short"
        assert "dawn" in html.lower(), "HTML doesn't appear to be from Dawn"
        
        stats = stealth_fetcher.get_stats()
        print(f"\n✓ Fetched Dawn homepage")
        print(f"  - HTML size: {len(html):,} bytes")
        print(f"  - Requests made: {stats['total_requests']}")
        print(f"  - Successful: {stats['successful_requests']}")
    
    def test_fetch_tribune_homepage(self, stealth_fetcher):
        """Test fetching Tribune homepage."""
        url = "https://tribune.com.pk/latest"
        
        html = stealth_fetcher.fetch(url)
        
        assert html is not None, "Failed to fetch Tribune homepage"
        assert len(html) > 1000, "HTML content too short"
        
        print(f"\n✓ Fetched Tribune homepage: {len(html):,} bytes")
    
    def test_fetch_geo_homepage(self, stealth_fetcher):
        """Test fetching Geo TV homepage."""
        url = "https://www.geo.tv/latest-news"
        
        html = stealth_fetcher.fetch(url)
        
        assert html is not None, "Failed to fetch Geo homepage"
        assert len(html) > 1000, "HTML content too short"
        
        print(f"\n✓ Fetched Geo homepage: {len(html):,} bytes")
    
    def test_fetch_all_sources_success_rate(self, stealth_fetcher):
        """
        Test fetching all configured sources.
        
        Success rate should be >= 80% for production viability.
        """
        test_urls = [
            "https://www.dawn.com/latest-news",
            "https://tribune.com.pk/latest",
            "https://www.geo.tv/latest-news",
        ]
        
        successes = 0
        for url in test_urls:
            html = stealth_fetcher.fetch(url)
            if html and len(html) > 1000:
                successes += 1
                print(f"  ✓ {url}: {len(html):,} bytes")
            else:
                print(f"  ✗ {url}: failed")
        
        success_rate = successes / len(test_urls)
        print(f"\n📊 Success rate: {success_rate:.0%} ({successes}/{len(test_urls)})")
        
        assert success_rate >= 0.8, f"Success rate too low: {success_rate:.0%}"


# ============================================================================
# Live Scraping Tests - ContentParser
# ============================================================================

@pytest.mark.integration
class TestContentParserLive:
    """Live tests for ContentParser with real article HTML."""
    
    def test_parse_dawn_article(self, stealth_fetcher, content_parser):
        """Test parsing a real Dawn article."""
        # First fetch an article URL from the section page
        section_html = stealth_fetcher.fetch("https://www.dawn.com/latest-news")
        assert section_html, "Failed to fetch Dawn section"
        
        # Find an article URL
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(section_html, "html.parser")
        article_link = soup.find("a", href=lambda x: x and "/news/" in x and x.startswith("https://"))
        
        if not article_link:
            # Try relative links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "/news/" in href and href.startswith("/"):
                    article_url = f"https://www.dawn.com{href}"
                    break
            else:
                pytest.skip("No article URLs found on Dawn")
        else:
            article_url = article_link["href"]
        
        # Fetch and parse the article
        article_html = stealth_fetcher.fetch(article_url)
        assert article_html, f"Failed to fetch article: {article_url}"
        
        parsed = content_parser.parse(article_html, article_url)
        
        assert parsed is not None, "Failed to parse Dawn article"
        assert parsed.title, "Missing title"
        assert len(parsed.title) >= 10, f"Title too short: {parsed.title}"
        assert parsed.text, "Missing text"
        assert len(parsed.text) >= 200, f"Text too short: {len(parsed.text)} chars"
        
        print(f"\n✓ Parsed Dawn article:")
        print(f"  - Title: {parsed.title[:60]}...")
        print(f"  - Text: {len(parsed.text):,} chars")
        print(f"  - Authors: {parsed.authors}")
        print(f"  - Parser: {parsed.parser_used}")
    
    def test_parse_tribune_article(self, stealth_fetcher, content_parser):
        """Test parsing a real Tribune article."""
        section_html = stealth_fetcher.fetch("https://tribune.com.pk/latest")
        assert section_html, "Failed to fetch Tribune section"
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(section_html, "html.parser")
        
        # Find article URLs
        article_url = None
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/story/" in href:
                if href.startswith("http"):
                    article_url = href
                else:
                    article_url = f"https://tribune.com.pk{href}"
                break
        
        if not article_url:
            pytest.skip("No article URLs found on Tribune")
        
        article_html = stealth_fetcher.fetch(article_url)
        assert article_html, f"Failed to fetch article: {article_url}"
        
        parsed = content_parser.parse(article_html, article_url)
        
        assert parsed is not None, "Failed to parse Tribune article"
        assert parsed.title, "Missing title"
        assert parsed.text, "Missing text"
        assert len(parsed.text) >= 100, f"Text too short: {len(parsed.text)} chars"
        
        print(f"\n✓ Parsed Tribune article:")
        print(f"  - Title: {parsed.title[:60]}...")
        print(f"  - Text: {len(parsed.text):,} chars")
        print(f"  - Parser: {parsed.parser_used}")


# ============================================================================
# Live Scraping Tests - HybridOrchestrator
# ============================================================================

@pytest.mark.integration
class TestHybridOrchestratorLive:
    """Live tests for the full HybridOrchestrator pipeline."""
    
    def test_scrape_dawn_article(self, hybrid_orchestrator):
        """
        E2E test: Scrape a single Dawn article.
        
        Tests the complete pipeline:
        StealthFetcher → ContentParser → RawArticle
        """
        # Get an article URL first
        orchestrator = hybrid_orchestrator
        section_urls = orchestrator._build_section_urls(
            "https://www.dawn.com", 
            ["latest-news"]
        )
        
        fetcher = StealthFetcher()
        section_html = fetcher.fetch(section_urls[0])
        assert section_html, "Failed to fetch Dawn section"
        
        article_urls = orchestrator._extract_article_urls(
            section_html, 
            "https://www.dawn.com",
            "dawn"
        )
        assert article_urls, "No article URLs found"
        
        # Scrape the first article
        article = orchestrator.scrape_url(article_urls[0], "dawn")
        
        assert article is not None, "Failed to scrape Dawn article"
        assert isinstance(article, RawArticle)
        assert article.source == "dawn"
        assert article.headline, "Missing headline"
        assert len(article.headline) >= 10, "Headline too short"
        assert article.main_text, "Missing main text"
        assert len(article.main_text) >= 50, "Main text too short"
        assert article.content_hash, "Missing content hash"
        assert len(article.content_hash) == 64, "Invalid hash length"
        
        print(f"\n✓ Scraped Dawn article:")
        print(f"  - Headline: {article.headline[:60]}...")
        print(f"  - Text: {len(article.main_text):,} chars")
        print(f"  - URL: {article.url}")
        print(f"  - Hash: {article.content_hash[:16]}...")
    
    def test_scrape_tribune_article(self, hybrid_orchestrator):
        """E2E test: Scrape a single Tribune article."""
        orchestrator = hybrid_orchestrator
        section_urls = orchestrator._build_section_urls(
            "https://tribune.com.pk", 
            ["latest"]
        )
        
        fetcher = StealthFetcher()
        section_html = fetcher.fetch(section_urls[0])
        assert section_html, "Failed to fetch Tribune section"
        
        article_urls = orchestrator._extract_article_urls(
            section_html, 
            "https://tribune.com.pk",
            "tribune"
        )
        assert article_urls, "No article URLs found"
        
        article = orchestrator.scrape_url(article_urls[0], "tribune")
        
        assert article is not None, "Failed to scrape Tribune article"
        assert isinstance(article, RawArticle)
        assert article.source == "tribune"
        assert article.headline
        assert article.main_text
        assert len(article.main_text) >= 50
        
        print(f"\n✓ Scraped Tribune article: {article.headline[:60]}...")
    
    def test_scrape_multiple_articles(self, hybrid_orchestrator):
        """
        Test scraping multiple articles from Dawn.
        
        Verifies:
        - Can scrape 3+ articles
        - All articles have required fields
        - Rate limiting is respected
        """
        orchestrator = hybrid_orchestrator
        fetcher = StealthFetcher()
        
        section_html = fetcher.fetch("https://www.dawn.com/latest-news")
        assert section_html, "Failed to fetch Dawn section"
        
        article_urls = orchestrator._extract_article_urls(
            section_html, 
            "https://www.dawn.com",
            "dawn"
        )
        
        assert len(article_urls) >= 3, f"Not enough articles: {len(article_urls)}"
        
        articles = []
        start_time = time.time()
        
        for url in article_urls[:5]:  # Try up to 5
            article = orchestrator.scrape_url(url, "dawn")
            if article:
                articles.append(article)
                if len(articles) >= 3:
                    break
        
        duration = time.time() - start_time
        
        assert len(articles) >= 3, f"Only scraped {len(articles)} articles"
        
        # Verify all articles
        for article in articles:
            assert article.headline
            assert article.main_text
            assert article.content_hash
        
        # Check for uniqueness (no duplicates)
        hashes = [a.content_hash for a in articles]
        assert len(hashes) == len(set(hashes)), "Duplicate articles found"
        
        print(f"\n✓ Scraped {len(articles)} articles in {duration:.2f}s")
        for i, a in enumerate(articles):
            print(f"  {i+1}. {a.headline[:50]}...")
    
    def test_scrape_source_batch(self, hybrid_orchestrator):
        """
        Test batch scraping a full source.
        
        Uses scrape_source() to scrape multiple sections.
        """
        articles = hybrid_orchestrator.scrape_source(
            source="dawn",
            base_url="https://www.dawn.com",
            sections=["latest-news"],
            max_articles=5,
        )
        
        assert len(articles) >= 1, "No articles scraped"
        
        print(f"\n✓ Batch scraped {len(articles)} Dawn articles")
        
        # Verify all articles
        for article in articles:
            assert isinstance(article, RawArticle)
            assert article.source == "dawn"
            assert article.headline
            assert article.main_text
    
    def test_scrape_all_sources(self, hybrid_orchestrator, sources_config):
        """
        E2E test: Scrape from all configured sources.
        
        This is the key test for production viability.
        """
        all_articles = []
        source_results = {}
        
        for source_name, config in sources_config.get("sources", {}).items():
            if not config.get("enabled", True):
                continue
            
            # Config uses 'url' not 'base_url'
            base_url = config.get("url") or config.get("base_url")
            sections = config.get("sections", [])
            
            if not base_url or not sections:
                continue
            
            try:
                articles = hybrid_orchestrator.scrape_source(
                    source=source_name,
                    base_url=base_url,
                    sections=sections[:2],  # Limit sections for testing
                    max_articles=3,
                )
                
                all_articles.extend(articles)
                source_results[source_name] = len(articles)
                
                print(f"  {source_name}: {len(articles)} articles")
            except Exception as e:
                print(f"  {source_name}: ERROR - {e}")
                source_results[source_name] = 0
        
        total_sources = len(source_results)
        successful_sources = sum(1 for count in source_results.values() if count > 0)
        success_rate = successful_sources / total_sources if total_sources > 0 else 0
        
        print(f"\n📊 Multi-Source Scraping Results:")
        print(f"   - Total articles: {len(all_articles)}")
        print(f"   - Successful sources: {successful_sources}/{total_sources}")
        print(f"   - Success rate: {success_rate:.0%}")
        
        # At least 60% of sources should succeed (accounting for occasional blocks)
        assert success_rate >= 0.6 or len(all_articles) >= 3, f"Success rate too low: {success_rate:.0%}"


# ============================================================================
# Payload Validation Tests
# ============================================================================

@pytest.mark.integration
class TestPayloadValidation:
    """Tests to verify scraped article payloads match expected schema."""
    
    def test_raw_article_payload_complete(self, hybrid_orchestrator):
        """
        Verify all required fields are present in scraped article.
        """
        fetcher = StealthFetcher()
        section_html = fetcher.fetch("https://www.dawn.com/latest-news")
        
        if not section_html:
            pytest.skip("Failed to fetch Dawn section")
        
        article_urls = hybrid_orchestrator._extract_article_urls(
            section_html, 
            "https://www.dawn.com",
            "dawn"
        )
        
        if not article_urls:
            pytest.skip("No articles available")
        
        article = hybrid_orchestrator.scrape_url(article_urls[0], "dawn")
        
        if not article:
            pytest.skip("Failed to scrape article")
        
        # Required fields per models.py
        required_fields = {
            "id": "UUID - auto-generated",
            "source": "string - news source identifier",
            "url": "string - original article URL",
            "headline": "string - article title",
            "main_text": "string - article body",
            "content_hash": "string - SHA-256 hash",
            "scraped_at": "datetime - when scraped",
        }
        
        print("\n📋 Article Payload Validation:")
        print("-" * 50)
        
        # Check required fields
        for field, description in required_fields.items():
            value = getattr(article, field, None)
            assert value is not None, f"Required field '{field}' is None"
            print(f"  ✓ {field}: {type(value).__name__} = {str(value)[:50]}...")
        
        # Validate specific constraints
        assert len(article.headline) >= 1, "Headline too short"
        assert len(article.main_text) >= 50, "Main text must be >=50 chars"
        assert len(article.content_hash) == 64, "Content hash must be 64 chars"
        assert article.url.startswith("https://"), "URL must use HTTPS"
    
    def test_raw_article_to_db_dict(self, hybrid_orchestrator):
        """
        Verify to_db_dict() produces valid database payload.
        """
        fetcher = StealthFetcher()
        section_html = fetcher.fetch("https://www.dawn.com/latest-news")
        
        if not section_html:
            pytest.skip("Failed to fetch Dawn section")
        
        article_urls = hybrid_orchestrator._extract_article_urls(
            section_html, 
            "https://www.dawn.com",
            "dawn"
        )
        
        if not article_urls:
            pytest.skip("No articles available")
        
        article = hybrid_orchestrator.scrape_url(article_urls[0], "dawn")
        
        if not article:
            pytest.skip("Failed to scrape article")
        
        db_dict = article.to_db_dict()
        
        # Should be a plain dict
        assert isinstance(db_dict, dict)
        
        # UUID should be string for JSON
        assert isinstance(db_dict["id"], str)
        assert len(db_dict["id"]) == 36  # UUID format
        
        # Required fields should be present
        assert "source" in db_dict
        assert "url" in db_dict
        assert "headline" in db_dict
        assert "main_text" in db_dict
        assert "content_hash" in db_dict
        
        print(f"\n✓ to_db_dict() payload valid with {len(db_dict)} fields")


# ============================================================================
# Scrape-to-Database E2E Tests
# ============================================================================

@pytest.mark.integration
class TestScrapeToDatabase:
    """
    End-to-end tests for scraping articles and storing in database.
    
    These tests verify the complete pipeline:
    scrape → validate → store in Supabase
    """
    
    def test_scrape_and_store_single_article(self, hybrid_orchestrator):
        """
        E2E: Scrape single article and store in database.
        """
        from src.db.client import SupabaseClient
        
        # Scrape a real article
        fetcher = StealthFetcher()
        section_html = fetcher.fetch("https://www.dawn.com/latest-news")
        
        if not section_html:
            pytest.skip("Failed to fetch Dawn section")
        
        article_urls = hybrid_orchestrator._extract_article_urls(
            section_html, 
            "https://www.dawn.com",
            "dawn"
        )
        
        if not article_urls:
            pytest.skip("No articles found")
        
        article = hybrid_orchestrator.scrape_url(article_urls[0], "dawn")
        
        if not article:
            pytest.skip("Failed to scrape article")
        
        # Modify URL to make it unique for test
        unique_id = uuid.uuid4().hex[:8]
        article.url = f"{article.url}#test-{unique_id}"
        article.source = "integration_test"
        
        # Connect to Supabase
        db = SupabaseClient(test_mode=True)
        
        try:
            # Insert article
            article_id = db.insert_article(article)
            assert article_id is not None, "Failed to get article ID"
            print(f"\n✓ Inserted article: {article_id}")
            
            # Retrieve and verify
            retrieved = db.get_article_by_id(article_id)
            assert retrieved is not None, "Failed to retrieve article"
            assert retrieved.headline == article.headline
            assert retrieved.source == "integration_test"
            assert retrieved.content_hash == article.content_hash
            print(f"✓ Retrieved and verified: {retrieved.headline[:40]}...")
            
        finally:
            # Cleanup
            db.cleanup_test_data()
            print("✓ Cleanup complete")
    
    def test_scrape_and_store_batch(self, hybrid_orchestrator):
        """
        E2E: Scrape multiple articles and batch store in database.
        """
        from src.db.client import SupabaseClient
        
        # Scrape multiple articles
        articles = hybrid_orchestrator.scrape_source(
            source="dawn",
            base_url="https://www.dawn.com",
            sections=["latest-news"],
            max_articles=3,
        )
        
        if not articles:
            pytest.skip("No articles scraped")
        
        # Modify for test isolation
        unique_id = uuid.uuid4().hex[:8]
        for i, article in enumerate(articles):
            article.url = f"{article.url}#batch-{unique_id}-{i}"
            article.source = "integration_test"
        
        db = SupabaseClient(test_mode=True)
        
        try:
            # Batch insert
            inserted_ids = db.batch_insert_articles(articles)
            
            assert len(inserted_ids) >= len(articles), \
                f"Expected {len(articles)} inserts, got {len(inserted_ids)}"
            print(f"\n✓ Batch inserted {len(inserted_ids)} articles")
            
            # Verify each article
            for article_id in inserted_ids[:3]:
                retrieved = db.get_article_by_id(article_id)
                assert retrieved is not None
                assert retrieved.source == "integration_test"
            
            print(f"✓ Verified articles in database")
            
        finally:
            db.cleanup_test_data()
            print("✓ Cleanup complete")
    
    def test_live_scrape_full_pipeline(self, hybrid_orchestrator, sources_config):
        """
        E2E: Full production pipeline test.
        
        Scrape from all sources and store in database.
        """
        from src.db.client import SupabaseClient
        
        all_articles = []
        unique_id = uuid.uuid4().hex[:8]
        
        # Scrape from first 2 enabled sources
        sources_tested = 0
        for source_name, config in sources_config.get("sources", {}).items():
            if not config.get("enabled", True):
                continue
            if sources_tested >= 2:
                break
            
            # Config uses 'url' not 'base_url'
            base_url = config.get("url") or config.get("base_url")
            sections = config.get("sections", [])
            
            if not base_url or not sections:
                continue
            
            try:
                articles = hybrid_orchestrator.scrape_source(
                    source=source_name,
                    base_url=base_url,
                    sections=sections[:1],
                    max_articles=2,
                )
                
                # Modify for test isolation
                for i, article in enumerate(articles):
                    article.url = f"{article.url}#pipeline-{unique_id}-{i}"
                    article.source = "integration_test"
                
                all_articles.extend(articles)
                sources_tested += 1
            except Exception as e:
                print(f"  {source_name}: ERROR - {e}")
        
        if not all_articles:
            pytest.skip("No articles scraped from any source")
        
        # Store in database
        db = SupabaseClient(test_mode=True)
        
        try:
            inserted_ids = db.batch_insert_articles(all_articles)
            
            print(f"\n📊 Full Pipeline Results:")
            print(f"   - Articles scraped: {len(all_articles)}")
            print(f"   - Articles stored: {len(inserted_ids)}")
            
            # Verify storage
            assert len(inserted_ids) >= 1, "No articles stored"
            
            # Verify retrieval
            for article_id in inserted_ids[:2]:
                retrieved = db.get_article_by_id(article_id)
                assert retrieved is not None
                assert retrieved.headline
                assert retrieved.main_text
            
            print("✓ Full pipeline test passed")
            
        finally:
            db.cleanup_test_data()


# ============================================================================
# Statistics and Metrics Tests
# ============================================================================

@pytest.mark.integration
class TestScrapingMetrics:
    """Tests for scraping statistics and metrics."""
    
    def test_orchestrator_statistics(self, hybrid_orchestrator):
        """Test that orchestrator tracks scraping statistics."""
        # Scrape some articles
        articles = hybrid_orchestrator.scrape_source(
            source="dawn",
            base_url="https://www.dawn.com",
            sections=["latest-news"],
            max_articles=3,
        )
        
        stats = hybrid_orchestrator.get_stats()
        
        print(f"\n📊 Orchestrator Stats:")
        print(f"   - Articles scraped: {stats.get('articles_scraped', 0)}")
        print(f"   - Playwright fallbacks: {stats.get('playwright_fallback_count', 0)}")
        print(f"   - Fetcher requests: {stats.get('fetcher_stats', {}).get('total_requests', 0)}")
        
        assert "articles_scraped" in stats
        assert stats["articles_scraped"] > 0


# ============================================================================
# Run info
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
