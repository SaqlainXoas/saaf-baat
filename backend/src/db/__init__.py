"""
Database module for Saaf Baat.

Exports:
- create_db_client: Build the configured client (SQLite by default)
- SqliteClient: Local-file client (default backend)
- SupabaseClient: Hosted Postgres client (opt-in via SAAF_DB_BACKEND=supabase)
- Models: RawArticle, Cluster, AnalyzedFeed
- Enums: Category, ImpactLabel, EntityType
- Exceptions: DatabaseError, DuplicateArticleError, NotFoundError, DBConnectionError
"""

from .client import SupabaseClient
from .errors import (
    DatabaseError,
    DBConnectionError,
    DuplicateArticleError,
    NotFoundError,
)
from .factory import configured_backend, create_db_client
from .models import (
    AnalyzedFeed,
    ArticleList,
    Category,
    Cluster,
    ClusterList,
    EntityType,
    ExtractedEntity,
    FeedList,
    ImpactLabel,
    RawArticle,
    SourceAttribution,
)
from .sqlite_client import SqliteClient

__all__ = [
    # Client
    "create_db_client",
    "configured_backend",
    "SqliteClient",
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
