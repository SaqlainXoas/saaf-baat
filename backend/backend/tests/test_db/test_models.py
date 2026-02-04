"""
Tests for database Pydantic models.

Tests:
- RawArticle validation and content hash generation
- Cluster model with article management
- AnalyzedFeed model with entity handling
"""

import pytest
from datetime import datetime
from uuid import UUID, uuid4

from src.db.models import (
    RawArticle,
    Cluster,
    AnalyzedFeed,
    Category,
    ImpactLabel,
    EntityType,
    ExtractedEntity,
)
from pydantic import ValidationError


class TestRawArticleModel:
    """Tests for RawArticle Pydantic model."""
    
    def test_valid_article_creation(self):
        """Test creating a valid article with all required fields."""
        article = RawArticle(
            source="dawn",
            url="https://dawn.com/news/article-123",
            headline="Test Headline for Article",
            main_text="This is the main content of the article. " * 5,  # > 50 chars
            publish_date=datetime(2026, 2, 3, 10, 0, 0),
        )
        
        assert article.source == "dawn"
        assert article.url == "https://dawn.com/news/article-123"
        assert article.headline == "Test Headline for Article"
        assert article.publish_date == datetime(2026, 2, 3, 10, 0, 0)
        assert isinstance(article.id, UUID)
    
    def test_content_hash_generation(self):
        """Ensure content hash is generated for deduplication."""
        article = RawArticle(
            source="dawn",
            url="https://dawn.com/article",
            headline="Test Headline",
            main_text="Article content that is sufficiently long for validation purposes.",
            publish_date=datetime(2026, 2, 3, 10, 0, 0),
        )
        
        assert article.content_hash is not None
        assert len(article.content_hash) == 64  # SHA-256 hash
    
    def test_same_content_same_hash(self):
        """Verify identical content produces identical hash."""
        article1 = RawArticle(
            source="dawn",
            url="https://dawn.com/article1",
            headline="Same Headline",
            main_text="Same content that is sufficiently long for validation purposes.",
        )
        
        article2 = RawArticle(
            source="tribune",  # Different source
            url="https://tribune.com/article2",  # Different URL
            headline="Same Headline",  # Same headline
            main_text="Same content that is sufficiently long for validation purposes.",  # Same content
        )
        
        # Same content should produce same hash (for deduplication)
        assert article1.content_hash == article2.content_hash
    
    def test_different_content_different_hash(self):
        """Verify different content produces different hash."""
        article1 = RawArticle(
            source="dawn",
            url="https://dawn.com/article1",
            headline="Headline One",
            main_text="Content one that is sufficiently long for validation purposes.",
        )
        
        article2 = RawArticle(
            source="dawn",
            url="https://dawn.com/article2",
            headline="Headline Two",
            main_text="Content two that is sufficiently long for validation purposes.",
        )
        
        assert article1.content_hash != article2.content_hash
    
    def test_invalid_url_rejected(self):
        """Test that invalid URLs are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RawArticle(
                source="dawn",
                url="invalid-url-without-protocol",
                headline="Test Headline",
                main_text="Article content that is sufficiently long for validation.",
            )
        
        assert "URL must start with http://" in str(exc_info.value)
    
    def test_empty_source_rejected(self):
        """Test that empty source is rejected."""
        with pytest.raises(ValidationError):
            RawArticle(
                source="",
                url="https://dawn.com/article",
                headline="Test Headline",
                main_text="Article content that is sufficiently long for validation.",
            )
    
    def test_empty_headline_rejected(self):
        """Test that empty headline is rejected."""
        with pytest.raises(ValidationError):
            RawArticle(
                source="dawn",
                url="https://dawn.com/article",
                headline="",
                main_text="Article content that is sufficiently long for validation.",
            )
    
    def test_short_main_text_rejected(self):
        """Test that main_text shorter than 50 chars is rejected."""
        with pytest.raises(ValidationError):
            RawArticle(
                source="dawn",
                url="https://dawn.com/article",
                headline="Test Headline",
                main_text="Too short",  # < 50 chars
            )
    
    def test_to_db_dict_conversion(self):
        """Test conversion to database dictionary."""
        article = RawArticle(
            source="dawn",
            url="https://dawn.com/article",
            headline="Test Headline",
            main_text="Article content that is sufficiently long for validation purposes.",
        )
        
        db_dict = article.to_db_dict()
        
        assert isinstance(db_dict["id"], str)  # UUID converted to string
        assert db_dict["source"] == "dawn"
        assert db_dict["url"] == "https://dawn.com/article"
        assert "embedding" not in db_dict  # Excluded from db_dict
    
    def test_optional_fields(self):
        """Test that optional fields work correctly."""
        article = RawArticle(
            source="dawn",
            url="https://dawn.com/article",
            headline="Test Headline",
            main_text="Article content that is sufficiently long for validation purposes.",
            author="John Doe",
            metadata={"category": "politics"},
        )
        
        assert article.author == "John Doe"
        assert article.metadata == {"category": "politics"}
        assert article.cluster_id is None
        assert article.embedding is None


class TestClusterModel:
    """Tests for Cluster Pydantic model."""
    
    def test_valid_cluster_creation(self):
        """Test creating a valid cluster."""
        cluster = Cluster(
            article_ids=[uuid4(), uuid4(), uuid4()],
            algorithm_used="hdbscan",
        )
        
        assert isinstance(cluster.id, UUID)
        assert len(cluster.article_ids) == 3
        assert cluster.cluster_size == 3
        assert cluster.algorithm_used == "hdbscan"
    
    def test_cluster_size_auto_update(self):
        """Test that cluster_size auto-updates based on article_ids."""
        cluster = Cluster(article_ids=[uuid4() for _ in range(5)])
        
        assert cluster.cluster_size == 5
    
    def test_add_article_to_cluster(self):
        """Test adding an article to cluster."""
        cluster = Cluster(article_ids=[uuid4(), uuid4()])
        initial_size = cluster.cluster_size
        
        new_article_id = uuid4()
        cluster.add_article(new_article_id)
        
        assert cluster.cluster_size == initial_size + 1
        assert new_article_id in cluster.article_ids
    
    def test_add_duplicate_article_ignored(self):
        """Test that adding duplicate article is ignored."""
        article_id = uuid4()
        cluster = Cluster(article_ids=[article_id])
        
        cluster.add_article(article_id)  # Try to add same article again
        
        assert cluster.cluster_size == 1  # Should not increase
    
    def test_remove_article_from_cluster(self):
        """Test removing an article from cluster."""
        article_ids = [uuid4() for _ in range(3)]
        cluster = Cluster(article_ids=article_ids)
        
        cluster.remove_article(article_ids[0])
        
        assert cluster.cluster_size == 2
        assert article_ids[0] not in cluster.article_ids
    
    def test_empty_cluster(self):
        """Test creating an empty cluster."""
        cluster = Cluster()
        
        assert cluster.cluster_size == 0
        assert cluster.article_ids == []
    
    def test_similarity_validation(self):
        """Test that avg_similarity must be between 0 and 1."""
        # Valid similarity
        cluster = Cluster(avg_similarity=0.85)
        assert cluster.avg_similarity == 0.85
        
        # Invalid similarity > 1
        with pytest.raises(ValidationError):
            Cluster(avg_similarity=1.5)
        
        # Invalid similarity < 0
        with pytest.raises(ValidationError):
            Cluster(avg_similarity=-0.1)
    
    def test_to_db_dict_conversion(self):
        """Test conversion to database dictionary."""
        article_ids = [uuid4(), uuid4()]
        cluster = Cluster(article_ids=article_ids)
        
        db_dict = cluster.to_db_dict()
        
        assert isinstance(db_dict["id"], str)
        assert all(isinstance(aid, str) for aid in db_dict["article_ids"])
        assert "centroid_embedding" not in db_dict


class TestAnalyzedFeedModel:
    """Tests for AnalyzedFeed Pydantic model."""
    
    def test_valid_feed_creation(self):
        """Test creating a valid analyzed feed item."""
        feed = AnalyzedFeed(
            cluster_id=uuid4(),
            headline="Rupee falls to record low against dollar",
            category=Category.ECONOMY,
            impact_labels=[ImpactLabel.WALLET, ImpactLabel.GOVERNANCE],
            source_attribution={"dawn": 3, "tribune": 2},
        )
        
        assert isinstance(feed.id, UUID)
        assert feed.headline == "Rupee falls to record low against dollar"
        assert feed.category == "economy"
        assert len(feed.impact_labels) == 2
    
    def test_confirmed_facts_and_debated_claims(self):
        """Test adding confirmed facts and debated claims."""
        confirmed = [
            ExtractedEntity(text="State Bank", type=EntityType.ORG, sources=5),
            ExtractedEntity(text="Islamabad", type=EntityType.GPE, sources=5),
        ]
        debated = [
            ExtractedEntity(text="Rs 100", type=EntityType.MONEY, sources=2),
            ExtractedEntity(text="Rs 105", type=EntityType.MONEY, sources=3),
        ]
        
        feed = AnalyzedFeed(
            cluster_id=uuid4(),
            headline="Currency update",
            category=Category.ECONOMY,
            confirmed_facts=confirmed,
            debated_claims=debated,
        )
        
        assert len(feed.confirmed_facts) == 2
        assert len(feed.debated_claims) == 2
        assert feed.confirmed_facts[0].text == "State Bank"
    
    def test_valid_categories(self):
        """Test all valid category values."""
        valid_categories = [
            Category.ECONOMY,
            Category.POLITICS,
            Category.CITY,
            Category.EDUCATION,
            Category.HEALTH,
            Category.SPORTS,
            Category.TECHNOLOGY,
            Category.ENTERTAINMENT,
            Category.OTHER,
        ]
        
        for category in valid_categories:
            feed = AnalyzedFeed(
                cluster_id=uuid4(),
                headline="Test",
                category=category,
            )
            assert feed.category is not None
    
    def test_classification_confidence_validation(self):
        """Test that classification_confidence must be between 0 and 1."""
        # Valid confidence
        feed = AnalyzedFeed(
            cluster_id=uuid4(),
            headline="Test",
            category=Category.ECONOMY,
            classification_confidence=0.92,
        )
        assert feed.classification_confidence == 0.92
        
        # Invalid confidence > 1
        with pytest.raises(ValidationError):
            AnalyzedFeed(
                cluster_id=uuid4(),
                headline="Test",
                category=Category.ECONOMY,
                classification_confidence=1.5,
            )
    
    def test_to_db_dict_and_from_db_dict(self):
        """Test round-trip conversion to/from database dict."""
        original = AnalyzedFeed(
            cluster_id=uuid4(),
            headline="Test headline",
            category=Category.POLITICS,
            confirmed_facts=[
                ExtractedEntity(text="PM", type=EntityType.PERSON, sources=4),
            ],
            impact_labels=[ImpactLabel.GOVERNANCE],
        )
        
        # Convert to DB dict
        db_dict = original.to_db_dict()
        
        # Simulate loading from DB (string UUIDs)
        db_dict["id"] = str(original.id)
        db_dict["cluster_id"] = str(original.cluster_id)
        
        # Convert back from DB dict
        restored = AnalyzedFeed.from_db_dict(db_dict)
        
        assert restored.headline == original.headline
        assert restored.category == original.category
        assert len(restored.confirmed_facts) == 1
    
    def test_empty_headline_rejected(self):
        """Test that empty headline is rejected."""
        with pytest.raises(ValidationError):
            AnalyzedFeed(
                cluster_id=uuid4(),
                headline="",
                category=Category.ECONOMY,
            )


class TestExtractedEntity:
    """Tests for ExtractedEntity model."""
    
    def test_valid_entity_creation(self):
        """Test creating a valid entity."""
        entity = ExtractedEntity(
            text="Imran Khan",
            type=EntityType.PERSON,
            sources=5,
        )
        
        assert entity.text == "Imran Khan"
        assert entity.type == "PERSON"
        assert entity.sources == 5
    
    def test_default_source_count(self):
        """Test default source count is 1."""
        entity = ExtractedEntity(
            text="Islamabad",
            type=EntityType.GPE,
        )
        
        assert entity.sources == 1
    
    def test_all_entity_types(self):
        """Test all valid entity types."""
        types = [
            EntityType.PERSON,
            EntityType.ORG,
            EntityType.GPE,
            EntityType.DATE,
            EntityType.MONEY,
            EntityType.EVENT,
            EntityType.MISC,
        ]
        
        for entity_type in types:
            entity = ExtractedEntity(text="Test", type=entity_type)
            assert entity.type is not None
