"""
Database module for Saaf Baat.

Exports:
- SupabaseClient: Main client for database operations
- Models: RawArticle, Cluster, AnalyzedFeed
- Enums: Category, ImpactLabel, EntityType
- Exceptions: DatabaseError, DuplicateArticleError, NotFoundError, DBConnectionError
"""

from .client import (
    SupabaseClient,
    DatabaseError,
    DuplicateArticleError,
    NotFoundError,
    DBConnectionError,
)
from .models import (
    RawArticle,
    Cluster,
    AnalyzedFeed,
    Category,
    ImpactLabel,
    EntityType,
    ExtractedEntity,
    SourceAttribution,
    ArticleList,
    ClusterList,
    FeedList,
)

__all__ = [
    # Client
    "SupabaseClient",
    # Models
    "RawArticle",
    "Cluster",
    "AnalyzedFeed",
    "ExtractedEntity",
    "SourceAttribution",
    # Enums
    "Category",
    "ImpactLabel",
    "EntityType",
    # Type aliases
    "ArticleList",
    "ClusterList",
    "FeedList",
    # Exceptions
    "DatabaseError",
    "DuplicateArticleError",
    "NotFoundError",
    "DBConnectionError",
]
