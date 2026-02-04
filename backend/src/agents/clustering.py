"""
Clustering module for grouping related news articles into stories.

Implements HDBSCAN (primary) and DBSCAN (fallback) clustering algorithms
with quality validation and automatic fallback.

Phase 4: Clustering Pipeline
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class ClusteringError(Exception):
    """Base exception for clustering errors."""
    pass


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ClusteringResult:
    """Result of clustering operation."""
    
    labels: NDArray[np.int64]
    """Cluster labels for each input point. -1 indicates noise."""
    
    algorithm_used: str
    """Name of the algorithm that produced these results."""
    
    num_clusters: int
    """Number of clusters found (excluding noise)."""
    
    noise_ratio: float
    """Ratio of points classified as noise (0.0 to 1.0)."""
    
    @classmethod
    def from_labels(cls, labels: NDArray[np.int64], algorithm: str) -> "ClusteringResult":
        """Create result from labels array."""
        unique_labels = set(labels)
        num_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        noise_count = np.sum(labels == -1)
        noise_ratio = noise_count / len(labels) if len(labels) > 0 else 0.0
        
        return cls(
            labels=labels,
            algorithm_used=algorithm,
            num_clusters=num_clusters,
            noise_ratio=noise_ratio
        )


# ============================================================================
# HDBSCAN Clusterer
# ============================================================================

class HDBSCANClusterer:
    """
    HDBSCAN clustering for news articles.
    
    HDBSCAN is the primary clustering algorithm because:
    - Automatically determines number of clusters
    - Handles varying cluster densities (breaking news vs minor stories)
    - Identifies outliers/noise naturally
    - Works well with precomputed cosine distance for text embeddings
    """
    
    def __init__(
        self,
        min_cluster_size: int = 3,
        min_samples: int = 2,
        metric: str = "cosine",
        cluster_selection_epsilon: float = 0.0,
    ):
        """
        Initialize HDBSCAN clusterer.
        
        Args:
            min_cluster_size: Minimum articles to form a cluster (story).
            min_samples: Core point threshold for density estimation.
            metric: Distance metric ('cosine' recommended for embeddings).
            cluster_selection_epsilon: Distance threshold for flat clustering.
        """
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.metric = metric
        self.cluster_selection_epsilon = cluster_selection_epsilon
        self._model = None
    
    def fit_predict(self, embeddings: NDArray[np.float32]) -> NDArray[np.int64]:
        """
        Cluster embeddings and return labels.
        
        Args:
            embeddings: Array of shape (n_samples, n_features).
            
        Returns:
            Array of cluster labels. -1 indicates noise/outlier.
            
        Raises:
            ClusteringError: If embeddings are empty.
        """
        if len(embeddings) == 0:
            raise ClusteringError("Cannot cluster empty embeddings array")
        
        # Handle single point - it's always noise
        if len(embeddings) == 1:
            return np.array([-1], dtype=np.int64)
        
        try:
            import hdbscan
        except ImportError:
            raise ClusteringError(
                "hdbscan package not installed. Run: pip install hdbscan"
            )
        
        # For cosine distance, compute precomputed distance matrix
        # HDBSCAN's BallTree doesn't support cosine directly
        if self.metric == "cosine":
            from sklearn.metrics.pairwise import cosine_distances
            # HDBSCAN requires float64 for precomputed distances
            distance_matrix = cosine_distances(embeddings).astype(np.float64)
            
            self._model = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric="precomputed",
                cluster_selection_epsilon=self.cluster_selection_epsilon,
            )
            labels = self._model.fit_predict(distance_matrix)
        else:
            self._model = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric=self.metric,
                cluster_selection_epsilon=self.cluster_selection_epsilon,
            )
            labels = self._model.fit_predict(embeddings)
        
        return labels.astype(np.int64)


# ============================================================================
# DBSCAN Clusterer (Fallback)
# ============================================================================

class DBSCANClusterer:
    """
    DBSCAN clustering as fallback when HDBSCAN quality is poor.
    
    DBSCAN is simpler and can work better on certain data distributions,
    especially when clusters are more uniform in density.
    """
    
    def __init__(
        self,
        eps: float = 0.3,
        min_samples: int = 2,
        metric: str = "cosine",
    ):
        """
        Initialize DBSCAN clusterer.
        
        Args:
            eps: Maximum distance between points in same neighborhood.
                 For cosine metric, 0.3 means similarity > 0.7.
            min_samples: Minimum points to form a core point.
            metric: Distance metric ('cosine' recommended for embeddings).
        """
        self.eps = eps
        self.min_samples = min_samples
        self.metric = metric
        self._model = None
    
    def fit_predict(self, embeddings: NDArray[np.float32]) -> NDArray[np.int64]:
        """
        Cluster embeddings and return labels.
        
        Args:
            embeddings: Array of shape (n_samples, n_features).
            
        Returns:
            Array of cluster labels. -1 indicates noise/outlier.
            
        Raises:
            ClusteringError: If embeddings are empty.
        """
        if len(embeddings) == 0:
            raise ClusteringError("Cannot cluster empty embeddings array")
        
        # Handle single point - it's always noise
        if len(embeddings) == 1:
            return np.array([-1], dtype=np.int64)
        
        try:
            from sklearn.cluster import DBSCAN
        except ImportError:
            raise ClusteringError(
                "scikit-learn not installed. Run: pip install scikit-learn"
            )
        
        self._model = DBSCAN(
            eps=self.eps,
            min_samples=self.min_samples,
            metric=self.metric,
        )
        
        labels = self._model.fit_predict(embeddings)
        
        return labels.astype(np.int64)


# ============================================================================
# Clustering Service
# ============================================================================

class ClusteringService:
    """
    Unified clustering service with quality validation and automatic fallback.
    
    Uses HDBSCAN as primary algorithm, falls back to DBSCAN if quality
    thresholds are not met.
    """
    
    def __init__(
        self,
        min_clusters: int = 2,
        max_noise_ratio: float = 0.3,
        min_cluster_size: int = 3,
        hdbscan_params: Optional[Dict] = None,
        dbscan_params: Optional[Dict] = None,
    ):
        """
        Initialize clustering service.
        
        Args:
            min_clusters: Minimum acceptable number of clusters.
            max_noise_ratio: Maximum acceptable noise ratio (0.0-1.0).
            min_cluster_size: Minimum articles per cluster.
            hdbscan_params: Custom parameters for HDBSCAN.
            dbscan_params: Custom parameters for DBSCAN.
        """
        self.min_clusters = min_clusters
        self.max_noise_ratio = max_noise_ratio
        self.min_cluster_size = min_cluster_size
        
        self.primary_algorithm = "hdbscan"
        self.fallback_algorithm = "dbscan"
        
        # Initialize clusterers
        hdbscan_config = {"min_cluster_size": min_cluster_size}
        if hdbscan_params:
            hdbscan_config.update(hdbscan_params)
        self._hdbscan = HDBSCANClusterer(**hdbscan_config)
        
        dbscan_config = {"min_samples": 2}
        if dbscan_params:
            dbscan_config.update(dbscan_params)
        self._dbscan = DBSCANClusterer(**dbscan_config)
    
    def _is_quality_clustering(self, labels: NDArray[np.int64]) -> bool:
        """
        Check if clustering result meets quality thresholds.
        
        Quality criteria:
        - At least min_clusters distinct clusters
        - Noise ratio below max_noise_ratio
        
        Args:
            labels: Cluster labels array.
            
        Returns:
            True if quality is acceptable, False otherwise.
        """
        if len(labels) == 0:
            return False
        
        # Count clusters (excluding noise label -1)
        unique_labels = set(labels)
        num_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        
        # Calculate noise ratio
        noise_count = np.sum(labels == -1)
        noise_ratio = noise_count / len(labels)
        
        # Check thresholds
        if num_clusters < self.min_clusters:
            logger.debug(
                f"Quality check failed: {num_clusters} clusters < {self.min_clusters} min"
            )
            return False
        
        if noise_ratio > self.max_noise_ratio:
            logger.debug(
                f"Quality check failed: {noise_ratio:.2f} noise > {self.max_noise_ratio} max"
            )
            return False
        
        return True
    
    def cluster(self, embeddings: NDArray[np.float32]) -> ClusteringResult:
        """
        Cluster embeddings with automatic fallback.
        
        Tries HDBSCAN first. If quality is poor, falls back to DBSCAN.
        
        Args:
            embeddings: Array of shape (n_samples, n_features).
            
        Returns:
            ClusteringResult with labels and metadata.
        """
        if len(embeddings) == 0:
            raise ClusteringError("Cannot cluster empty embeddings array")
        
        # Try primary algorithm (HDBSCAN)
        try:
            labels = self._hdbscan.fit_predict(embeddings)
            
            if self._is_quality_clustering(labels):
                logger.info(
                    f"HDBSCAN clustering successful: "
                    f"{len(set(labels)) - (1 if -1 in labels else 0)} clusters"
                )
                return ClusteringResult.from_labels(labels, self.primary_algorithm)
            
            logger.info("HDBSCAN quality check failed, trying DBSCAN fallback")
            
        except Exception as e:
            logger.warning(f"HDBSCAN failed: {e}, trying DBSCAN fallback")
        
        # Fallback to DBSCAN
        try:
            labels = self._dbscan.fit_predict(embeddings)
            
            logger.info(
                f"DBSCAN fallback: "
                f"{len(set(labels)) - (1 if -1 in labels else 0)} clusters"
            )
            return ClusteringResult.from_labels(labels, self.fallback_algorithm)
            
        except Exception as e:
            logger.error(f"Both clustering algorithms failed: {e}")
            raise ClusteringError(f"Clustering failed: {e}")


# ============================================================================
# Cluster Analysis Functions
# ============================================================================

def calculate_centroid(embeddings: NDArray[np.float32]) -> NDArray[np.float32]:
    """
    Calculate normalized centroid of embeddings.
    
    Args:
        embeddings: Array of shape (n_samples, n_features).
        
    Returns:
        Normalized centroid vector of shape (n_features,).
    """
    if len(embeddings) == 0:
        raise ValueError("Cannot calculate centroid of empty array")
    
    # Calculate mean
    centroid = np.mean(embeddings, axis=0)
    
    # Normalize for cosine similarity
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    
    return centroid.astype(np.float32)


def find_representative_article(
    embeddings: NDArray[np.float32],
    centroid: NDArray[np.float32],
) -> int:
    """
    Find index of article closest to cluster centroid.
    
    Args:
        embeddings: Array of shape (n_samples, n_features).
        centroid: Centroid vector of shape (n_features,).
        
    Returns:
        Index of the most representative article.
    """
    if len(embeddings) == 0:
        raise ValueError("Cannot find representative of empty array")
    
    # Calculate cosine similarities (dot product for normalized vectors)
    similarities = embeddings @ centroid
    
    # Return index of highest similarity
    return int(np.argmax(similarities))


def calculate_intra_cluster_similarity(
    embeddings: NDArray[np.float32],
) -> float:
    """
    Calculate average pairwise cosine similarity within cluster.
    
    Args:
        embeddings: Array of shape (n_samples, n_features).
        
    Returns:
        Average similarity (0.0 to 1.0). Returns 1.0 for single point.
    """
    n = len(embeddings)
    
    if n == 0:
        raise ValueError("Cannot calculate similarity of empty array")
    
    if n == 1:
        return 1.0  # Single point has perfect "similarity"
    
    # Calculate all pairwise similarities using matrix multiplication
    # For normalized vectors, similarity = dot product
    similarity_matrix = embeddings @ embeddings.T
    
    # Extract upper triangle (excluding diagonal) for unique pairs
    upper_indices = np.triu_indices(n, k=1)
    pairwise_similarities = similarity_matrix[upper_indices]
    
    # Return average
    return float(np.mean(pairwise_similarities))


# ============================================================================
# Cluster Mapping
# ============================================================================

def create_cluster_mapping(
    article_ids: List[str],
    labels: NDArray[np.int64],
    embeddings: NDArray[np.float32],
) -> Dict[str, Dict]:
    """
    Create mapping from cluster IDs to article data.
    
    Args:
        article_ids: List of article identifiers.
        labels: Cluster labels for each article.
        embeddings: Embeddings array.
        
    Returns:
        Dict mapping cluster_id to:
        - article_ids: List of article IDs in cluster
        - centroid: Cluster centroid embedding
        - similarity: Intra-cluster similarity score
    """
    if len(article_ids) != len(labels) or len(article_ids) != len(embeddings):
        raise ValueError("article_ids, labels, and embeddings must have same length")
    
    mapping: Dict[str, Dict] = {}
    
    # Get unique cluster labels (excluding noise)
    unique_labels = set(labels)
    cluster_labels = [l for l in unique_labels if l != -1]
    
    for cluster_label in cluster_labels:
        # Get indices for this cluster
        indices = np.where(labels == cluster_label)[0]
        
        # Get article IDs
        cluster_article_ids = [article_ids[i] for i in indices]
        
        # Get embeddings for this cluster
        cluster_embeddings = embeddings[indices]
        
        # Calculate centroid
        centroid = calculate_centroid(cluster_embeddings)
        
        # Calculate intra-cluster similarity
        similarity = calculate_intra_cluster_similarity(cluster_embeddings)
        
        # Create cluster ID
        cluster_id = f"cluster-{cluster_label}"
        
        mapping[cluster_id] = {
            "article_ids": cluster_article_ids,
            "centroid": centroid,
            "similarity": similarity,
        }
    
    return mapping


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    # Exceptions
    "ClusteringError",
    # Classes
    "ClusteringResult",
    "HDBSCANClusterer",
    "DBSCANClusterer",
    "ClusteringService",
    # Functions
    "calculate_centroid",
    "find_representative_article",
    "calculate_intra_cluster_similarity",
    "create_cluster_mapping",
]
