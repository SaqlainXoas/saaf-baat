"""
Agents module for Saaf Baat news intelligence pipeline.

Contains:
- embeddings: Text embedding generation (Gemini)
- clustering: Event grouping + legacy clustering utilities
- analysis: Entity extraction, consensus detection, and classification (spaCy + rules)
"""
from src.agents.analysis import (
    AnalysisService,
    ConsensusDetector,
    EntityExtractor,
)
from src.agents.clustering import (
    ClusteringError,
    ClusteringResult,
    EventGroup,
    EventGroupingResult,
    EventGroupingService,
    calculate_centroid,
    calculate_intra_cluster_similarity,
    find_representative_article,
)
from src.agents.embeddings import (
    EmbeddingError,
    EmbeddingResult,
    GeminiEmbeddingProvider,
)

__all__ = [
    # Embeddings
    "GeminiEmbeddingProvider",
    "EmbeddingResult",
    "EmbeddingError",
    # Clustering
    "EventGroup",
    "EventGroupingResult",
    "EventGroupingService",
    "ClusteringResult",
    "ClusteringError",
    "calculate_centroid",
    "find_representative_article",
    "calculate_intra_cluster_similarity",
    # Analysis
    "EntityExtractor",
    "ConsensusDetector",
    "AnalysisService",
]
