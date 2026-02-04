"""
Tests for Supabase client operations.

Tests:
- Client initialization and connection
- Article CRUD operations
- Cluster operations
- Analyzed feed operations
- Error handling and retries

Note: These tests use mocking for unit tests. 
Integration tests with real Supabase are in test_integration.py
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4, UUID

from src.db.client import (
    SupabaseClient,
    DatabaseError,
    DuplicateArticleError,
    NotFoundError,
    DBConnectionError,
)
from src.db.models import RawArticle, Cluster, AnalyzedFeed, Category


# ============================================
# Fixtures
# ============================================

@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    with patch('src.db.client.create_client') as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        yield mock_client


@pytest.fixture
def db_client(mock_supabase_client):
    """Create a SupabaseClient with mocked underlying client."""
    with patch.dict('os.environ', {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    }):
        client = SupabaseClient(test_mode=True)
        return client


@pytest.fixture
def sample_article():
    """Create a sample article for testing."""
    return RawArticle(
        source="dawn",
        url="https://dawn.com/news/test-article-123",
        headline="Test Article Headline",
        main_text="This is the main content of the test article. " * 5,
        publish_date=datetime(2026, 2, 3, 10, 0, 0),
    )


@pytest.fixture
def sample_cluster():
    """Create a sample cluster for testing."""
    return Cluster(
        article_ids=[uuid4(), uuid4(), uuid4()],
        algorithm_used="hdbscan",
        avg_similarity=0.85,
    )


@pytest.fixture
def sample_feed():
    """Create a sample analyzed feed for testing."""
    return AnalyzedFeed(
        cluster_id=uuid4(),
        headline="Test Story Headline",
        category=Category.ECONOMY,
        impact_labels=["💳 WALLET"],
        source_attribution={"dawn": 2, "tribune": 1},
    )


# ============================================
# Client Initialization Tests
# ============================================

class TestClientInitialization:
    """Tests for SupabaseClient initialization."""
    
    def test_init_with_env_vars(self, mock_supabase_client):
        """Test initialization with environment variables."""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test-key'
        }):
            client = SupabaseClient()
            assert client.url == 'https://test.supabase.co'
            assert client.key == 'test-key'
    
    def test_init_with_explicit_credentials(self, mock_supabase_client):
        """Test initialization with explicit credentials."""
        client = SupabaseClient(
            url='https://custom.supabase.co',
            key='custom-key'
        )
        assert client.url == 'https://custom.supabase.co'
        assert client.key == 'custom-key'
    
    def test_init_missing_credentials_raises_error(self):
        """Test that missing credentials raises DBConnectionError."""
        with patch.dict('os.environ', {}, clear=True):
            # Clear any existing env vars
            import os
            if 'SUPABASE_URL' in os.environ:
                del os.environ['SUPABASE_URL']
            if 'SUPABASE_KEY' in os.environ:
                del os.environ['SUPABASE_KEY']
            
            with pytest.raises(DBConnectionError) as exc_info:
                SupabaseClient(url=None, key=None)
            
            assert "Missing Supabase credentials" in str(exc_info.value)
    
    def test_test_mode_flag(self, mock_supabase_client):
        """Test that test_mode flag is set correctly."""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test-key'
        }):
            client = SupabaseClient(test_mode=True)
            assert client.test_mode is True
            
            client2 = SupabaseClient(test_mode=False)
            assert client2.test_mode is False


class TestConnectionRetry:
    """Tests for connection retry logic."""
    
    def test_connection_retry_on_failure(self):
        """Test that client retries on connection failure."""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test-key'
        }):
            with patch('src.db.client.create_client') as mock_create:
                # Fail first 2 times, succeed on 3rd
                mock_create.side_effect = [
                    Exception("Connection failed"),
                    Exception("Connection failed"),
                    MagicMock(),
                ]
                
                client = SupabaseClient(max_retries=3, retry_delay=0.01)
                _ = client.client  # Trigger lazy connection
                
                assert mock_create.call_count == 3
    
    def test_connection_failure_after_max_retries(self):
        """Test that DBConnectionError is raised after max retries."""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test-key'
        }):
            with patch('src.db.client.create_client') as mock_create:
                mock_create.side_effect = Exception("Connection failed")
                
                client = SupabaseClient(max_retries=2, retry_delay=0.01)
                
                with pytest.raises(DBConnectionError) as exc_info:
                    _ = client.client
                
                assert "Failed to connect after 2 attempts" in str(exc_info.value)


# ============================================
# Article Operations Tests
# ============================================

class TestArticleOperations:
    """Tests for article CRUD operations."""
    
    def test_insert_article_success(self, db_client, mock_supabase_client, sample_article):
        """Test successful article insertion."""
        article_id = str(uuid4())
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": article_id}]
        )
        
        result = db_client.insert_article(sample_article)
        
        assert isinstance(result, UUID)
        assert str(result) == article_id
    
    def test_insert_article_duplicate_raises_error(self, db_client, mock_supabase_client, sample_article):
        """Test that inserting duplicate article raises DuplicateArticleError."""
        mock_supabase_client.table.return_value.insert.return_value.execute.side_effect = \
            Exception("duplicate key value violates unique constraint")
        
        with pytest.raises(DuplicateArticleError):
            db_client.insert_article(sample_article)
    
    def test_batch_insert_articles(self, db_client, mock_supabase_client):
        """Test batch insertion of multiple articles."""
        articles = [
            RawArticle(
                source="dawn",
                url=f"https://dawn.com/article-{i}",
                headline=f"Article {i}",
                main_text="Content " * 20,
            )
            for i in range(5)
        ]
        
        # Mock successful batch insert
        mock_response = Mock(data=[{"id": str(uuid4())} for _ in range(5)])
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = mock_response
        
        result = db_client.batch_insert_articles(articles)
        
        assert len(result) == 5
        assert all(isinstance(id, UUID) for id in result)
    
    def test_batch_insert_empty_list(self, db_client):
        """Test batch insert with empty list returns empty list."""
        result = db_client.batch_insert_articles([])
        assert result == []
    
    def test_get_article_by_id(self, db_client, mock_supabase_client):
        """Test retrieving article by ID."""
        article_id = uuid4()
        mock_data = {
            "id": str(article_id),
            "source": "dawn",
            "url": "https://dawn.com/article",
            "headline": "Test Headline",
            "main_text": "Content " * 20,
            "content_hash": "a" * 64,
            "scraped_at": "2026-02-03T10:00:00Z",
        }
        
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_data)
        
        result = db_client.get_article_by_id(article_id)
        
        assert isinstance(result, RawArticle)
        assert result.source == "dawn"
    
    def test_get_article_not_found(self, db_client, mock_supabase_client):
        """Test that NotFoundError is raised for non-existent article."""
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = \
            Exception("PGRST116")
        
        with pytest.raises(NotFoundError):
            db_client.get_article_by_id(uuid4())
    
    def test_get_articles_by_source(self, db_client, mock_supabase_client):
        """Test getting articles by source."""
        mock_data = [
            {
                "id": str(uuid4()),
                "source": "dawn",
                "url": f"https://dawn.com/article-{i}",
                "headline": f"Headline {i}",
                "main_text": "Content " * 20,
                "content_hash": "a" * 64,
                "scraped_at": "2026-02-03T10:00:00Z",
            }
            for i in range(3)
        ]
        
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = Mock(data=mock_data)
        
        result = db_client.get_articles_by_source("dawn")
        
        assert len(result) == 3
        assert all(a.source == "dawn" for a in result)
    
    def test_get_articles_in_date_range(self, db_client, mock_supabase_client):
        """Test getting articles in date range."""
        mock_data = [
            {
                "id": str(uuid4()),
                "source": "dawn",
                "url": "https://dawn.com/article",
                "headline": "Headline",
                "main_text": "Content " * 20,
                "content_hash": "a" * 64,
                "publish_date": "2026-02-02T10:00:00Z",
                "scraped_at": "2026-02-03T10:00:00Z",
            }
        ]
        
        mock_supabase_client.table.return_value.select.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value = Mock(data=mock_data)
        
        result = db_client.get_articles_in_date_range("2026-02-01", "2026-02-03")
        
        assert len(result) == 1
    
    def test_update_article_embedding(self, db_client, mock_supabase_client):
        """Test updating article embedding."""
        article_id = uuid4()
        embedding = [0.1] * 768
        
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.execute.return_value = Mock()
        
        # Should not raise
        db_client.update_article_embedding(article_id, embedding)
        
        mock_supabase_client.table.return_value.update.assert_called_once()
    
    def test_assign_to_cluster(self, db_client, mock_supabase_client):
        """Test assigning article to cluster."""
        article_id = uuid4()
        cluster_id = uuid4()
        
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.execute.return_value = Mock()
        
        db_client.assign_to_cluster(article_id, cluster_id)
        
        mock_supabase_client.table.return_value.update.assert_called_once()


# ============================================
# Cluster Operations Tests
# ============================================

class TestClusterOperations:
    """Tests for cluster operations."""
    
    def test_create_cluster(self, db_client, mock_supabase_client):
        """Test creating a new cluster."""
        cluster_id = str(uuid4())
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": cluster_id}]
        )
        
        result = db_client.create_cluster(
            article_ids=[uuid4(), uuid4()],
            algorithm_used="hdbscan"
        )
        
        assert isinstance(result, UUID)
    
    def test_create_cluster_with_centroid(self, db_client, mock_supabase_client):
        """Test creating cluster with centroid embedding."""
        cluster_id = str(uuid4())
        centroid = [0.1] * 768
        
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": cluster_id}]
        )
        
        result = db_client.create_cluster(
            article_ids=[uuid4()],
            centroid_embedding=centroid
        )
        
        assert isinstance(result, UUID)
    
    def test_get_cluster_by_id(self, db_client, mock_supabase_client):
        """Test retrieving cluster by ID."""
        cluster_id = uuid4()
        article_ids = [str(uuid4()), str(uuid4())]
        
        mock_data = {
            "id": str(cluster_id),
            "article_ids": article_ids,
            "cluster_size": 2,
            "algorithm_used": "hdbscan",
            "created_at": "2026-02-03T10:00:00Z",
            "updated_at": "2026-02-03T10:00:00Z",
        }
        
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_data)
        
        result = db_client.get_cluster_by_id(cluster_id)
        
        assert isinstance(result, Cluster)
        assert len(result.article_ids) == 2
    
    def test_get_all_clusters(self, db_client, mock_supabase_client):
        """Test getting all clusters."""
        mock_data = [
            {
                "id": str(uuid4()),
                "article_ids": [str(uuid4())],
                "cluster_size": 1,
                "algorithm_used": "hdbscan",
                "created_at": "2026-02-03T10:00:00Z",
                "updated_at": "2026-02-03T10:00:00Z",
            }
            for _ in range(3)
        ]
        
        mock_supabase_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = Mock(data=mock_data)
        
        result = db_client.get_all_clusters()
        
        assert len(result) == 3
        assert all(isinstance(c, Cluster) for c in result)
    
    def test_update_cluster_articles(self, db_client, mock_supabase_client):
        """Test updating cluster article list."""
        cluster_id = uuid4()
        article_ids = [uuid4(), uuid4(), uuid4()]
        
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.execute.return_value = Mock()
        
        db_client.update_cluster_articles(cluster_id, article_ids)
        
        mock_supabase_client.table.return_value.update.assert_called_once()


# ============================================
# Analyzed Feed Operations Tests
# ============================================

class TestAnalyzedFeedOperations:
    """Tests for analyzed feed operations."""
    
    def test_insert_analyzed_feed(self, db_client, mock_supabase_client, sample_feed):
        """Test inserting analyzed feed item."""
        feed_id = str(uuid4())
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": feed_id}]
        )
        
        result = db_client.insert_analyzed_feed(sample_feed)
        
        assert isinstance(result, UUID)
    
    def test_insert_analyzed_feed_from_dict(self, db_client, mock_supabase_client):
        """Test inserting analyzed feed from dictionary."""
        feed_dict = {
            "cluster_id": uuid4(),
            "headline": "Test Headline",
            "category": "economy",
            "impact_labels": ["💳 WALLET"],
        }
        
        feed_id = str(uuid4())
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": feed_id}]
        )
        
        result = db_client.insert_analyzed_feed(feed_dict)
        
        assert isinstance(result, UUID)
    
    def test_get_analyzed_feed_by_id(self, db_client, mock_supabase_client):
        """Test retrieving feed item by ID."""
        feed_id = uuid4()
        mock_data = {
            "id": str(feed_id),
            "cluster_id": str(uuid4()),
            "headline": "Test Headline",
            "category": "economy",
            "confirmed_facts": [],
            "debated_claims": [],
            "impact_labels": ["💳 WALLET"],
            "source_attribution": {},
            "created_at": "2026-02-03T10:00:00Z",
        }
        
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_data)
        
        result = db_client.get_analyzed_feed_by_id(feed_id)
        
        assert isinstance(result, AnalyzedFeed)
        assert result.category == "economy"
    
    def test_get_analyzed_feed_with_filters(self, db_client, mock_supabase_client):
        """Test getting feed with category filter."""
        mock_data = [
            {
                "id": str(uuid4()),
                "cluster_id": str(uuid4()),
                "headline": "Economy News",
                "category": "economy",
                "confirmed_facts": [],
                "debated_claims": [],
                "impact_labels": [],
                "source_attribution": {},
                "created_at": "2026-02-03T10:00:00Z",
            }
        ]
        
        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.contains.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.execute.return_value = Mock(data=mock_data)
        mock_supabase_client.table.return_value.select.return_value = mock_query
        
        result = db_client.get_analyzed_feed(category="economy")
        
        assert len(result) == 1
        assert result[0].category == "economy"


# ============================================
# Utility Operations Tests
# ============================================

class TestUtilityOperations:
    """Tests for utility operations."""
    
    def test_is_connected_success(self, db_client, mock_supabase_client):
        """Test connection check when connected."""
        mock_supabase_client.table.return_value.select.return_value.limit.return_value.execute.return_value = Mock()
        
        assert db_client.is_connected() is True
    
    def test_is_connected_failure(self, db_client, mock_supabase_client):
        """Test connection check when disconnected."""
        mock_supabase_client.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception("Connection lost")
        
        assert db_client.is_connected() is False
    
    def test_table_exists_true(self, db_client, mock_supabase_client):
        """Test table existence check for existing table."""
        mock_supabase_client.table.return_value.select.return_value.limit.return_value.execute.return_value = Mock()
        
        assert db_client.table_exists("raw_articles") is True
    
    def test_table_exists_false(self, db_client, mock_supabase_client):
        """Test table existence check for non-existing table."""
        mock_supabase_client.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception("Table not found")
        
        assert db_client.table_exists("nonexistent_table") is False


# ============================================
# Test Mode & Cleanup Tests
# ============================================

class TestCleanup:
    """Tests for test mode cleanup functionality."""
    
    def test_cleanup_tracks_inserted_articles(self, db_client, mock_supabase_client, sample_article):
        """Test that test mode tracks inserted articles."""
        article_id = str(uuid4())
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": article_id}]
        )
        
        db_client.insert_article(sample_article)
        
        assert article_id in db_client._test_article_ids
    
    def test_cleanup_tracks_inserted_clusters(self, db_client, mock_supabase_client):
        """Test that test mode tracks inserted clusters."""
        cluster_id = str(uuid4())
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{"id": cluster_id}]
        )
        
        db_client.create_cluster(article_ids=[uuid4()])
        
        assert cluster_id in db_client._test_cluster_ids
    
    def test_cleanup_test_data(self, db_client, mock_supabase_client):
        """Test cleanup removes tracked test data."""
        # Add some test IDs
        db_client._test_article_ids = ["article-1", "article-2"]
        db_client._test_cluster_ids = ["cluster-1"]
        db_client._test_feed_ids = ["feed-1"]
        
        # Mock delete operations
        mock_supabase_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = Mock()
        
        db_client.cleanup_test_data()
        
        assert len(db_client._test_article_ids) == 0
        assert len(db_client._test_cluster_ids) == 0
        assert len(db_client._test_feed_ids) == 0
    
    def test_cleanup_skipped_when_not_test_mode(self, mock_supabase_client):
        """Test that cleanup is skipped when not in test mode."""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test-key'
        }):
            client = SupabaseClient(test_mode=False)
            client._test_article_ids = ["article-1"]
            
            client.cleanup_test_data()
            
            # Should not have called delete
            mock_supabase_client.table.return_value.delete.assert_not_called()
