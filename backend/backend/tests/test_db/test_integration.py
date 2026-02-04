"""
Integration tests for Supabase database operations.

These tests run against a REAL Supabase instance.
Requires SUPABASE_URL and SUPABASE_KEY environment variables.

Run with: pytest tests/test_db/test_integration.py -m integration

Note: Tests use test_mode=True for automatic cleanup.
"""

import os
import time
import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.db.client import (
    SupabaseClient,
    DatabaseError,
    DuplicateArticleError,
    NotFoundError,
)
from src.db.models import (
    RawArticle,
    Cluster,
    AnalyzedFeed,
    Category,
    ImpactLabel,
    ExtractedEntity,
    EntityType,
)


# Skip all tests in this module if no Supabase credentials
pytestmark = pytest.mark.integration


def has_supabase_credentials():
    """Check if Supabase credentials are available."""
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))


@pytest.fixture(scope="module")
def db_client():
    """
    Create a real Supabase client for integration tests.
    Uses test_mode=True for automatic cleanup.
    """
    if not has_supabase_credentials():
        pytest.skip("Supabase credentials not available")
    
    client = SupabaseClient(test_mode=True)
    yield client
    
    # Cleanup after all tests
    client.cleanup_test_data()


@pytest.fixture
def sample_article():
    """Create a unique sample article for each test."""
    unique_id = str(uuid4())[:8]
    return RawArticle(
        source="test_source",
        url=f"https://test.com/article-{unique_id}",
        headline=f"Test Article {unique_id}",
        main_text="This is test article content. " * 10,
        author="Test Author",
        publish_date=datetime.utcnow(),
    )


def create_test_article(index: int = 0, **kwargs) -> RawArticle:
    """Helper to create unique test articles."""
    unique_id = f"{uuid4()}"[:8]
    defaults = {
        "source": "test_source",
        "url": f"https://test.com/article-{unique_id}-{index}",
        "headline": f"Test Article {index} - {unique_id}",
        "main_text": f"This is test content for article {index}. " * 10,
    }
    defaults.update(kwargs)
    return RawArticle(**defaults)


# ============================================
# Connection Tests
# ============================================

class TestConnection:
    """Tests for database connection."""
    
    def test_client_connects_successfully(self, db_client):
        """Test that client can connect to Supabase."""
        assert db_client.is_connected() is True
    
    def test_tables_exist(self, db_client):
        """Verify required tables exist in database."""
        assert db_client.table_exists("raw_articles") is True
        assert db_client.table_exists("clusters") is True
        assert db_client.table_exists("analyzed_feed") is True


# ============================================
# Article CRUD Tests
# ============================================

class TestArticleCRUD:
    """Integration tests for article CRUD operations."""
    
    def test_insert_and_retrieve_article(self, db_client, sample_article):
        """Test basic article insert and retrieve."""
        # Insert
        article_id = db_client.insert_article(sample_article)
        assert article_id is not None
        
        # Retrieve
        retrieved = db_client.get_article_by_id(article_id)
        assert retrieved.headline == sample_article.headline
        assert retrieved.source == sample_article.source
        assert retrieved.url == sample_article.url
    
    def test_unique_constraint_on_url(self, db_client):
        """Ensure duplicate URLs are rejected."""
        unique_url = f"https://test.com/unique-{uuid4()}"
        
        article1 = create_test_article(url=unique_url)
        article2 = create_test_article(url=unique_url)  # Same URL
        
        db_client.insert_article(article1)
        
        with pytest.raises(DuplicateArticleError):
            db_client.insert_article(article2)
    
    def test_batch_insert_articles(self, db_client):
        """Test inserting multiple articles efficiently."""
        articles = [create_test_article(i) for i in range(10)]
        
        start_time = time.time()
        result = db_client.batch_insert_articles(articles)
        duration = time.time() - start_time
        
        assert len(result) == 10
        assert duration < 10.0  # Should complete in reasonable time
    
    def test_get_articles_by_source(self, db_client):
        """Test filtering articles by source."""
        unique_source = f"test_source_{uuid4()}"[:20]
        
        # Insert articles with unique source
        articles = [
            create_test_article(i, source=unique_source)
            for i in range(3)
        ]
        db_client.batch_insert_articles(articles)
        
        # Retrieve by source
        results = db_client.get_articles_by_source(unique_source)
        
        assert len(results) >= 3
        assert all(a.source == unique_source for a in results)
    
    def test_get_articles_in_date_range(self, db_client):
        """Test date-based filtering."""
        # Insert articles with specific dates
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        article = create_test_article(publish_date=yesterday)
        db_client.insert_article(article)
        
        # Query for date range
        start = (yesterday - timedelta(hours=1)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        
        results = db_client.get_articles_in_date_range(start, end)
        
        assert len(results) >= 1
    
    def test_update_article_embedding(self, db_client, sample_article):
        """Test updating article embedding vector."""
        article_id = db_client.insert_article(sample_article)
        
        # Update embedding
        embedding = [0.1] * 768
        db_client.update_article_embedding(article_id, embedding)
        
        # Note: Can't easily verify embedding was stored without RPC
        # The test passes if no exception is raised
    
    def test_assign_article_to_cluster(self, db_client, sample_article):
        """Test assigning article to a cluster."""
        article_id = db_client.insert_article(sample_article)
        cluster_id = db_client.create_cluster(article_ids=[article_id])
        
        # Assign to cluster
        db_client.assign_to_cluster(article_id, cluster_id)
        
        # Verify
        retrieved = db_client.get_article_by_id(article_id)
        assert str(retrieved.cluster_id) == str(cluster_id)
    
    def test_article_not_found_raises_error(self, db_client):
        """Test that retrieving non-existent article raises NotFoundError."""
        fake_id = uuid4()
        
        with pytest.raises(NotFoundError):
            db_client.get_article_by_id(fake_id)


# ============================================
# Cluster Operations Tests
# ============================================

class TestClusterOperations:
    """Integration tests for cluster operations."""
    
    def test_create_and_retrieve_cluster(self, db_client):
        """Test creating and retrieving a cluster."""
        # Create articles first
        articles = [create_test_article(i) for i in range(3)]
        article_ids = db_client.batch_insert_articles(articles)
        
        # Create cluster
        cluster_id = db_client.create_cluster(
            article_ids=article_ids,
            algorithm_used="hdbscan"
        )
        
        # Retrieve
        cluster = db_client.get_cluster_by_id(cluster_id)
        
        assert cluster.cluster_size == 3
        assert cluster.algorithm_used == "hdbscan"
        assert len(cluster.article_ids) == 3
    
    def test_create_cluster_with_centroid(self, db_client):
        """Test creating cluster with centroid embedding."""
        article = create_test_article()
        article_id = db_client.insert_article(article)
        
        centroid = [0.5] * 768
        cluster_id = db_client.create_cluster(
            article_ids=[article_id],
            centroid_embedding=centroid
        )
        
        assert cluster_id is not None
    
    def test_get_all_clusters(self, db_client):
        """Test retrieving all clusters."""
        # Create a cluster
        article = create_test_article()
        article_id = db_client.insert_article(article)
        db_client.create_cluster(article_ids=[article_id])
        
        # Get all clusters
        clusters = db_client.get_all_clusters()
        
        assert len(clusters) >= 1
        assert all(isinstance(c, Cluster) for c in clusters)
    
    def test_update_cluster_articles(self, db_client):
        """Test updating articles in a cluster."""
        # Create initial cluster
        articles = [create_test_article(i) for i in range(2)]
        article_ids = db_client.batch_insert_articles(articles)
        cluster_id = db_client.create_cluster(article_ids=article_ids)
        
        # Add new article
        new_article = create_test_article(99)
        new_article_id = db_client.insert_article(new_article)
        
        # Update cluster
        updated_ids = article_ids + [new_article_id]
        db_client.update_cluster_articles(cluster_id, updated_ids)
        
        # Verify
        cluster = db_client.get_cluster_by_id(cluster_id)
        assert cluster.cluster_size == 3


# ============================================
# Analyzed Feed Tests
# ============================================

class TestAnalyzedFeedOperations:
    """Integration tests for analyzed feed operations."""
    
    def test_insert_and_retrieve_analyzed_feed(self, db_client):
        """Test creating and retrieving analyzed feed item."""
        # Create cluster first
        article = create_test_article()
        article_id = db_client.insert_article(article)
        cluster_id = db_client.create_cluster(article_ids=[article_id])
        
        # Create feed item
        feed = AnalyzedFeed(
            cluster_id=cluster_id,
            headline="Test Story: Major Economic Update",
            category=Category.ECONOMY,
            confirmed_facts=[
                ExtractedEntity(text="State Bank", type=EntityType.ORG, sources=3),
            ],
            debated_claims=[
                ExtractedEntity(text="Rs 100", type=EntityType.MONEY, sources=1),
            ],
            impact_labels=[ImpactLabel.WALLET, ImpactLabel.GOVERNANCE],
            source_attribution={"dawn": 2, "tribune": 1},
            classification_confidence=0.92,
        )
        
        feed_id = db_client.insert_analyzed_feed(feed)
        
        # Retrieve
        retrieved = db_client.get_analyzed_feed_by_id(feed_id)
        
        assert retrieved.headline == "Test Story: Major Economic Update"
        assert retrieved.category == "economy"
        assert len(retrieved.confirmed_facts) == 1
        assert len(retrieved.debated_claims) == 1
        assert len(retrieved.impact_labels) == 2
    
    def test_get_feed_filtered_by_category(self, db_client):
        """Test filtering feed by category."""
        # Create cluster
        article = create_test_article()
        article_id = db_client.insert_article(article)
        cluster_id = db_client.create_cluster(article_ids=[article_id])
        
        # Create feed item with specific category
        feed = AnalyzedFeed(
            cluster_id=cluster_id,
            headline="Politics Story",
            category=Category.POLITICS,
        )
        db_client.insert_analyzed_feed(feed)
        
        # Filter by category
        results = db_client.get_analyzed_feed(category="politics")
        
        assert all(f.category == "politics" for f in results)
    
    def test_get_feed_filtered_by_impact_label(self, db_client):
        """Test filtering feed by impact label."""
        # Create cluster
        article = create_test_article()
        article_id = db_client.insert_article(article)
        cluster_id = db_client.create_cluster(article_ids=[article_id])
        
        # Create feed item with WALLET impact
        feed = AnalyzedFeed(
            cluster_id=cluster_id,
            headline="Financial Story",
            category=Category.ECONOMY,
            impact_labels=[ImpactLabel.WALLET],
        )
        db_client.insert_analyzed_feed(feed)
        
        # Filter by impact label
        results = db_client.get_analyzed_feed(impact_label="💳 WALLET")
        
        assert len(results) >= 1


# ============================================
# Full Lifecycle Tests
# ============================================

class TestFullLifecycle:
    """End-to-end lifecycle tests."""
    
    def test_full_article_lifecycle(self, db_client):
        """Test complete article flow: insert -> retrieve -> update -> assign."""
        # 1. Insert
        article = create_test_article()
        article_id = db_client.insert_article(article)
        assert article_id is not None
        
        # 2. Retrieve
        retrieved = db_client.get_article_by_id(article_id)
        assert retrieved.headline == article.headline
        
        # 3. Create cluster and assign
        cluster_id = db_client.create_cluster(article_ids=[article_id])
        db_client.assign_to_cluster(article_id, cluster_id)
        
        # 4. Verify assignment
        updated = db_client.get_article_by_id(article_id)
        assert str(updated.cluster_id) == str(cluster_id)
    
    def test_full_pipeline_simulation(self, db_client):
        """Simulate full pipeline: scrape -> cluster -> analyze -> feed."""
        # Step 1: "Scrape" articles
        articles = [
            create_test_article(0, source="dawn", headline="Economy News from Dawn"),
            create_test_article(1, source="tribune", headline="Economy News from Tribune"),
            create_test_article(2, source="express", headline="Economy News from Express"),
        ]
        article_ids = db_client.batch_insert_articles(articles)
        assert len(article_ids) == 3
        
        # Step 2: Create cluster
        cluster_id = db_client.create_cluster(
            article_ids=article_ids,
            algorithm_used="hdbscan"
        )
        
        # Step 3: Assign articles to cluster
        for aid in article_ids:
            db_client.assign_to_cluster(aid, cluster_id)
        
        # Step 4: Create analyzed feed
        feed = AnalyzedFeed(
            cluster_id=cluster_id,
            headline="Economic Update: Multi-Source Coverage",
            category=Category.ECONOMY,
            confirmed_facts=[
                ExtractedEntity(text="Economy", type=EntityType.MISC, sources=3),
            ],
            impact_labels=[ImpactLabel.WALLET],
            source_attribution={"dawn": 1, "tribune": 1, "express": 1},
        )
        feed_id = db_client.insert_analyzed_feed(feed)
        
        # Verify end result
        final_feed = db_client.get_analyzed_feed_by_id(feed_id)
        assert final_feed.headline == "Economic Update: Multi-Source Coverage"
        assert "dawn" in final_feed.source_attribution
        
        # Verify cluster
        final_cluster = db_client.get_cluster_by_id(cluster_id)
        assert final_cluster.cluster_size == 3


# ============================================
# Performance Tests
# ============================================

class TestPerformance:
    """Performance-related integration tests."""
    
    def test_batch_insert_50_articles_under_5_seconds(self, db_client):
        """Test that batch inserting 50 articles completes quickly."""
        articles = [create_test_article(i) for i in range(50)]
        
        start_time = time.time()
        result = db_client.batch_insert_articles(articles)
        duration = time.time() - start_time
        
        assert len(result) == 50
        assert duration < 5.0, f"Batch insert took {duration:.2f}s, expected < 5s"
    
    def test_retrieve_recent_articles_fast(self, db_client):
        """Test that retrieving recent articles is fast."""
        start_time = time.time()
        results = db_client.get_recent_articles(limit=50)
        duration = time.time() - start_time
        
        assert duration < 2.0, f"Query took {duration:.2f}s, expected < 2s"
