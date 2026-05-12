from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import Depends
from fastapi import APIRouter

from src.db.client import SupabaseClient

router = APIRouter()
_BACKEND_DIR = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def get_db() -> SupabaseClient:
    return SupabaseClient()


def _parse_iso_datetime(value: object) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _heartbeat_file() -> Path:
    env_path = (os.getenv("SAAF_PIPELINE_HEARTBEAT_FILE") or "").strip()
    if not env_path:
        return _BACKEND_DIR / ".pipeline_heartbeat.json"
    path = Path(env_path)
    if path.is_absolute():
        return path
    return _BACKEND_DIR.parent / path


def _load_heartbeat_payload() -> dict[str, object]:
    path = _heartbeat_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/health")
def health(db: SupabaseClient = Depends(get_db)) -> dict[str, object]:
    db_connected = False
    latest_feed_created_at: Optional[datetime] = None
    heartbeat = _load_heartbeat_payload()
    last_run_at = _parse_iso_datetime(heartbeat.get("last_run_at"))
    last_successful_run_at = _parse_iso_datetime(heartbeat.get("last_successful_run_at"))
    degraded_sources = [
        str(source)
        for source in list(heartbeat.get("degraded_sources") or [])
        if str(source).strip()
    ]
    source_article_counts = {
        str(source): int(count)
        for source, count in dict(heartbeat.get("source_article_counts") or {}).items()
        if str(source).strip()
    }

    try:
        db_connected = db.is_connected()
    except Exception:
        db_connected = False

    if db_connected:
        try:
            latest = db.get_analyzed_feed(limit=1, published_only=False)
            if latest:
                latest_feed_created_at = latest[0].created_at
        except Exception:
            latest_feed_created_at = None

    last_successful_pipeline_run_at = last_successful_run_at or latest_feed_created_at
    if last_successful_pipeline_run_at is None:
        pipeline_is_stale = True
    else:
        age_seconds = max(
            0.0,
            (datetime.utcnow() - _to_utc_naive(last_successful_pipeline_run_at)).total_seconds(),
        )
        pipeline_is_stale = age_seconds >= 28 * 3600

    return {
        "status": "ok" if db_connected else "degraded",
        "database": "connected" if db_connected else "disconnected",
        "latest_feed_created_at": latest_feed_created_at,
        "last_run_at": last_run_at,
        "last_successful_run_at": last_successful_pipeline_run_at,
        "degraded_sources": degraded_sources,
        "source_article_counts": source_article_counts,
        "pipeline_stale_after_hours": 28,
        "pipeline_is_stale": pipeline_is_stale,
    }
