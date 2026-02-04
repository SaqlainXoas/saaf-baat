"""
Agents module for Saaf Baat news intelligence pipeline.

Contains:
- embeddings: Text embedding generation (Gemini)
- clustering: Article clustering into stories (HDBSCAN + DBSCAN)
- analysis: Entity extraction, consensus detection, and classification (spaCy + rules)
"""
from src.agents.embeddings import (
    GeminiEmbeddingProvider,
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

from src.agents.analysis import (
    EntityExtractor,
    ConsensusDetector,
    RuleBasedClassifier,
    AnalysisService,
)

__all__ = [
    # Embeddings
    "GeminiEmbeddingProvider",
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
    # Analysis
    "EntityExtractor",
    "ConsensusDetector",
    "RuleBasedClassifier",
    "AnalysisService",
]
