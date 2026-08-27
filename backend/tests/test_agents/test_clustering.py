"""
Tests for clustering module.

TDD approach: Tests written BEFORE implementation.
Event grouping: the deterministic story-formation path
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import numpy as np
import pytest

from src.db.models import RawArticle

# These imports will fail until we implement the module
# That's expected for TDD - write tests first!


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def synthetic_cluster_embeddings():
    """
    Create synthetic embeddings for 3 distinct clusters.
    Each cluster has articles about different topics that should cluster together.
    """
    np.random.seed(42)

    # Cluster 1: 5 articles (similar to each other)
    cluster1_center = np.array([1.0, 0.0, 0.0, 0.0])
    cluster1 = cluster1_center + np.random.randn(5, 4) * 0.1

    # Cluster 2: 4 articles
    cluster2_center = np.array([0.0, 1.0, 0.0, 0.0])
    cluster2 = cluster2_center + np.random.randn(4, 4) * 0.1

    # Cluster 3: 3 articles
    cluster3_center = np.array([0.0, 0.0, 1.0, 0.0])
    cluster3 = cluster3_center + np.random.randn(3, 4) * 0.1

    embeddings = np.vstack([cluster1, cluster2, cluster3])

    # Normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms

    return embeddings.astype(np.float32)


@pytest.fixture
def embeddings_with_outliers():
    """Create embeddings with clear outliers that should be noise."""
    np.random.seed(42)

    # 2 tight clusters of 4 each
    cluster1_center = np.array([1.0, 0.0, 0.0, 0.0])
    cluster1 = cluster1_center + np.random.randn(4, 4) * 0.05

    cluster2_center = np.array([0.0, 1.0, 0.0, 0.0])
    cluster2 = cluster2_center + np.random.randn(4, 4) * 0.05

    # 2 outliers - random directions
    outlier1 = np.array([[0.3, 0.3, 0.5, 0.7]])
    outlier2 = np.array([[0.7, 0.2, 0.5, 0.4]])

    embeddings = np.vstack([cluster1, cluster2, outlier1, outlier2])

    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms

    return embeddings.astype(np.float32)


@pytest.fixture
def varying_density_embeddings():
    """Create embeddings with varying cluster densities."""
    np.random.seed(42)

    # Large cluster: 15 articles
    large_center = np.array([1.0, 0.0, 0.0, 0.0])
    large_cluster = large_center + np.random.randn(15, 4) * 0.1

    # Small cluster: 3 articles
    small_center = np.array([0.0, 1.0, 0.0, 0.0])
    small_cluster = small_center + np.random.randn(3, 4) * 0.1

    embeddings = np.vstack([large_cluster, small_cluster])

    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms

    return embeddings.astype(np.float32)


@pytest.fixture
def tight_cluster_embeddings():
    """Create a tight cluster with high intra-similarity."""
    np.random.seed(42)
    center = np.array([1.0, 0.0, 0.0, 0.0])
    cluster = center + np.random.randn(5, 4) * 0.02  # Very tight
    norms = np.linalg.norm(cluster, axis=1, keepdims=True)
    return (cluster / norms).astype(np.float32)


@pytest.fixture
def loose_cluster_embeddings():
    """Create a loose cluster with low intra-similarity."""
    np.random.seed(42)
    center = np.array([1.0, 0.0, 0.0, 0.0])
    cluster = center + np.random.randn(5, 4) * 0.5  # Very loose
    norms = np.linalg.norm(cluster, axis=1, keepdims=True)
    return (cluster / norms).astype(np.float32)


def _article(
    idx: int,
    headline: str,
    body: str,
    *,
    source: str = "dawn",
    publish_date: datetime | None = None,
    scraped_at: datetime | None = None,
    embedding: list[float] | None = None,
) -> RawArticle:
    return RawArticle(
        id=uuid4(),
        source=source,
        url=f"https://example.com/article-{idx}",
        headline=headline,
        main_text=body,
        publish_date=publish_date,
        scraped_at=scraped_at or datetime.now(timezone.utc),
        embedding=embedding,
    )


class TestEventGroupingService:
    def test_groups_same_event_across_sources(self):
        from src.agents.clustering import EventGroupingService

        now = datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc)
        articles = [
            _article(
                1,
                "IMF approves tranche for Pakistan",
                "Pakistan IMF tranche approved in Washington after talks.",
                source="dawn",
                publish_date=now,
                embedding=[1.0, 0.0, 0.0],
            ),
            _article(
                2,
                "Pakistan wins IMF tranche approval",
                "Finance officials say the IMF programme review ended positively.",
                source="tribune",
                publish_date=now + timedelta(hours=1),
                embedding=[0.98, 0.05, 0.0],
            ),
            _article(
                3,
                "Karachi rain emergency declared after heavy showers",
                "Karachi authorities declared an emergency after rain hit the city.",
                source="geo",
                publish_date=now + timedelta(hours=1),
                embedding=[0.0, 1.0, 0.0],
            ),
        ]

        service = EventGroupingService(min_cluster_size=2)
        result = service.group_articles(articles)

        assert result.algorithm_used == "event_graph"
        assert result.num_clusters == 1
        assert len(result.groups[0].indices) == 2
        assert set(result.groups[0].indices) == {0, 1}
        assert result.labels[2] == -1

    def test_does_not_chain_related_but_distinct_events(self):
        from src.agents.clustering import EventGroupingService

        now = datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc)
        articles = [
            _article(
                1,
                "Karachi rain emergency declared in city",
                "Karachi rain triggers emergency measures in low-lying areas.",
                source="dawn",
                publish_date=now,
                embedding=[1.0, 0.0, 0.0],
            ),
            _article(
                2,
                "Heavy Karachi rain disrupts traffic after emergency",
                "Traffic slowed after heavy rain in Karachi and officials warned residents.",
                source="tribune",
                publish_date=now + timedelta(hours=1),
                embedding=[0.96, 0.18, 0.0],
            ),
            _article(
                3,
                "Karachi stock market gains after banking rally",
                "Banking stocks lifted the Karachi market during a volatile session.",
                source="geo",
                publish_date=now + timedelta(hours=2),
                embedding=[0.90, 0.30, 0.0],
            ),
        ]

        service = EventGroupingService(min_cluster_size=2, min_pair_similarity=0.75)
        result = service.group_articles(articles)

        assert result.num_clusters == 1
        assert set(result.groups[0].indices) == {0, 1}
        assert result.labels[2] == -1

    def test_grouping_trusts_the_publisher_date(self):
        """
        I-6: the skew heuristics are gone, so the publisher date is the event time.

        They existed to rescue an article whose stored date was months stale by
        falling back to scraped_at. Ingest now drops any item outside the
        freshness window and quarantines any endpoint whose newest item is
        stale, so that article cannot reach grouping — and two articles a month
        apart are two events, which is what the window should say.
        """
        from src.agents.clustering import EventGroupingService, trusted_article_timestamp

        now = datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc)
        fresh = [
            _article(
                1,
                "IMF approves review for Pakistan",
                "The IMF approved a review for Pakistan in Washington.",
                source="dawn",
                publish_date=now - timedelta(hours=2),
                scraped_at=now,
                embedding=[1.0, 0.0, 0.0],
            ),
            _article(
                2,
                "Pakistan clears IMF review",
                "Officials said the IMF review was cleared after talks in Washington.",
                source="tribune",
                publish_date=now - timedelta(hours=1),
                scraped_at=now,
                embedding=[0.99, 0.03, 0.0],
            ),
        ]

        result = EventGroupingService(min_cluster_size=2).group_articles(fresh)

        assert trusted_article_timestamp(fresh[0]) == fresh[0].publish_date
        assert result.num_clusters == 1
        assert set(result.groups[0].indices) == {0, 1}

    def test_articles_a_month_apart_are_not_one_event(self):
        from src.agents.clustering import EventGroupingService

        now = datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc)
        articles = [
            _article(
                1,
                "IMF approves review for Pakistan",
                "The IMF approved a review for Pakistan in Washington.",
                source="dawn",
                publish_date=now - timedelta(days=30),
                scraped_at=now,
                embedding=[1.0, 0.0, 0.0],
            ),
            _article(
                2,
                "Pakistan clears IMF review",
                "Officials said the IMF review was cleared after talks in Washington.",
                source="tribune",
                publish_date=now,
                scraped_at=now,
                embedding=[0.99, 0.03, 0.0],
            ),
        ]

        result = EventGroupingService(min_cluster_size=2).group_articles(articles)

        assert result.num_clusters == 0


    def test_large_group_requires_support_from_multiple_members(self):
        from src.agents.clustering import EventGroupingService

        now = datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc)
        articles = [
            _article(
                1,
                "Karachi rain emergency declared after heavy downpour",
                "Karachi emergency declared after heavy rain flooded roads and drains.",
                source="dawn",
                publish_date=now,
                embedding=[1.0, 0.0, 0.0],
            ),
            _article(
                2,
                "Heavy rain puts Karachi on emergency footing",
                "Officials put Karachi on emergency footing as rain disrupted traffic.",
                source="tribune",
                publish_date=now + timedelta(minutes=30),
                embedding=[0.99, 0.05, 0.0],
            ),
            _article(
                3,
                "Karachi emergency centres activated after rain spell",
                "Emergency centres were activated in Karachi after another rain spell.",
                source="geo",
                publish_date=now + timedelta(hours=1),
                embedding=[0.98, 0.08, 0.0],
            ),
            _article(
                4,
                "Karachi budget meeting reviews tax plan",
                "Officials in Karachi reviewed a tax plan and budget targets during a meeting.",
                source="dawn",
                publish_date=now + timedelta(hours=1),
                embedding=[0.94, 0.20, 0.0],
            ),
        ]

        service = EventGroupingService(min_cluster_size=2, min_pair_similarity=0.80)
        result = service.group_articles(articles)

        assert result.num_clusters == 1
        assert set(result.groups[0].indices) == {0, 1, 2}
        assert result.labels[3] == -1

    def test_same_source_articles_without_headline_overlap_do_not_group(self):
        from src.agents.clustering import EventGroupingService

        now = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
        articles = [
            _article(
                1,
                "FO rejects claims of sheltering Iranian aircraft",
                "Pakistan rejected claims about sheltering Iranian aircraft during peace efforts.",
                source="tribune",
                publish_date=now,
                embedding=[1.0, 0.0, 0.0],
            ),
            _article(
                2,
                "Pakistan, Azerbaijan reaffirm strong ties",
                "Pakistan and Azerbaijan reaffirmed cooperation across several sectors.",
                source="tribune",
                publish_date=now + timedelta(minutes=20),
                embedding=[0.97, 0.05, 0.0],
            ),
        ]

        service = EventGroupingService(min_cluster_size=2, min_pair_similarity=0.80)
        result = service.group_articles(articles)

        assert result.num_clusters == 0
        assert list(result.labels) == [-1, -1]


# ============================================================================
# Cluster Analysis Tests
# ============================================================================

class TestClusterAnalysis:
    """Tests for cluster analysis utilities."""

    def test_calculate_centroid(self):
        """Test centroid calculation for cluster."""
        from src.agents.clustering import calculate_centroid

        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.8, 0.2, 0.0]
        ], dtype=np.float32)

        centroid = calculate_centroid(embeddings)

        # Centroid should be normalized
        norm = np.linalg.norm(centroid)
        assert np.isclose(norm, 1.0, atol=0.01)

        # Should be in the direction of mean
        mean = np.mean(embeddings, axis=0)
        mean_normalized = mean / np.linalg.norm(mean)
        assert np.allclose(centroid, mean_normalized, atol=0.01)

    def test_calculate_centroid_single_point(self):
        """Test centroid of single point is the point itself."""
        from src.agents.clustering import calculate_centroid

        single = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        centroid = calculate_centroid(single)

        assert np.allclose(centroid, single[0], atol=0.01)

    def test_find_representative_article(self):
        """Find article closest to cluster centroid."""
        from src.agents.clustering import calculate_centroid, find_representative_article

        # Create embeddings where the first one is clearly at cluster center
        # and others are dispersed around it
        embeddings = np.array([
            [1.0, 0.0, 0.0],   # Article 0: at center
            [0.8, 0.5, 0.3],   # Article 1: off-center
            [0.7, 0.6, 0.4]    # Article 2: even more off-center
        ], dtype=np.float32)

        # Normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms

        centroid = calculate_centroid(embeddings)
        rep_index = find_representative_article(embeddings, centroid)

        # The representative should be the one closest to centroid
        # Calculate actual distances to verify
        similarities = embeddings @ centroid
        expected_rep = int(np.argmax(similarities))

        assert rep_index == expected_rep

    def test_intra_cluster_similarity_tight(self, tight_cluster_embeddings):
        """Test tight cluster has high intra-similarity."""
        from src.agents.clustering import calculate_intra_cluster_similarity

        similarity = calculate_intra_cluster_similarity(tight_cluster_embeddings)

        # Tight cluster should have high similarity
        assert similarity > 0.9

    def test_intra_cluster_similarity_loose(self, loose_cluster_embeddings):
        """Test loose cluster has lower intra-similarity."""
        from src.agents.clustering import calculate_intra_cluster_similarity

        similarity = calculate_intra_cluster_similarity(loose_cluster_embeddings)

        # Loose cluster should have lower similarity (but still positive)
        assert 0.0 < similarity < 0.9

    def test_tight_vs_loose_similarity(self, tight_cluster_embeddings, loose_cluster_embeddings):
        """Compare similarity of tight vs loose clusters."""
        from src.agents.clustering import calculate_intra_cluster_similarity

        tight_sim = calculate_intra_cluster_similarity(tight_cluster_embeddings)
        loose_sim = calculate_intra_cluster_similarity(loose_cluster_embeddings)

        assert tight_sim > loose_sim

    def test_single_article_similarity(self):
        """Single article cluster has perfect similarity."""
        from src.agents.clustering import calculate_intra_cluster_similarity

        single = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        similarity = calculate_intra_cluster_similarity(single)

        # Single point has perfect "similarity" (no pairs to compare)
        assert similarity == 1.0


