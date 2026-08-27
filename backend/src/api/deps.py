"""Shared FastAPI dependencies.

`get_db` used to be defined and `lru_cache`d separately in `routes/feed.py`,
`routes/stories.py` and `routes/health.py`, so a process held three independent
database clients (I-11). One cached client, imported by every route, is enough.

`/health` deliberately does not want the 503: it reports `database:
disconnected` and a reason rather than failing the request that exists to tell
you the database is down. That is `get_db_or_none`.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from src.db.factory import create_db_client


@lru_cache(maxsize=1)
def _client():
    return create_db_client()


def get_db():
    try:
        return _client()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc


def get_db_or_none():
    """The health check reports a dead database; it does not 503 over one."""
    return _client()
