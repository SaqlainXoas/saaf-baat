"""
Agents module for Saaf Baat news intelligence pipeline.

Contains:
- embeddings: Text embedding generation (Gemini + local fallback)
- clustering: Article clustering into stories (HDBSCAN + DBSCAN)
"""
from src.agents.embeddings import (
    GeminiEmbeddingProvider,
    LocalEmbeddingProvider,
    EmbeddingService,
    EmbeddingResult,
    EmbeddingError,
)

from src.agents.clustering import (
    HDBSCANClusterer,
    DBSCANClusterer,
    ClusteringService,
    ClusteringResult,
    ClusteringError,
    calculate_centroid,
    find_representative_article,
    calculate_intra_cluster_similarity,
    create_cluster_mapping,
)

__all__ = [
    # Embeddings
    "GeminiEmbeddingProvider",
    "LocalEmbeddingProvider",
    "EmbeddingService",
    "EmbeddingResult",
    "EmbeddingError",
    # Clustering
    "HDBSCANClusterer",
    "DBSCANClusterer",
    "ClusteringService",
    "ClusteringResult",
    "ClusteringError",
    "calculate_centroid",
    "find_representative_article",
    "calculate_intra_cluster_similarity",
    "create_cluster_mapping",
]
