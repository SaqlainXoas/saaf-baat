"""
Database backend selection.

Local SQLite is the default so the product runs with no external service.
`SAAF_DB_BACKEND=supabase` switches to the hosted Postgres client. Every
caller should go through `create_db_client()` rather than naming a concrete
client, so a future Postgres swap touches this file only.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .errors import DBConnectionError

logger = logging.getLogger(__name__)

SQLITE = "sqlite"
SUPABASE = "supabase"


def configured_backend() -> str:
    """Return the selected backend name, defaulting to sqlite."""
    raw = (os.getenv("SAAF_DB_BACKEND") or "").strip().lower()
    if raw in {SUPABASE, "postgres", "postgresql"}:
        return SUPABASE
    return SQLITE


def create_db_client(**kwargs: Any):
    """
    Build the configured database client.

    Keyword arguments are forwarded to the client constructor, so callers can
    still pass `test_mode=True`.
    """
    backend = configured_backend()

    if backend == SUPABASE:
        from .client import SupabaseClient

        logger.info("Using Supabase database backend")
        return SupabaseClient(**kwargs)

    from .sqlite_client import SqliteClient, default_sqlite_path

    logger.info("Using local SQLite database backend at %s", default_sqlite_path())
    return SqliteClient(**kwargs)


__all__ = ["create_db_client", "configured_backend", "SQLITE", "SUPABASE", "DBConnectionError"]
