"""
Database exceptions shared by every storage backend.

Kept in their own module so the SQLite client does not have to import the
Supabase client (and therefore the `supabase` package) just to raise errors.
"""
from __future__ import annotations


class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class DBConnectionError(DatabaseError):
    """Failed to connect to database."""
    pass


class DuplicateArticleError(DatabaseError):
    """Article with same URL or content_hash already exists."""
    pass


class NotFoundError(DatabaseError):
    """Requested record not found."""
    pass


__all__ = [
    "DatabaseError",
    "DBConnectionError",
    "DuplicateArticleError",
    "NotFoundError",
]
