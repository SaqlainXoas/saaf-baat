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


def _load_heartbeat_timestamp() -> Optional[datetime]:
    path = _heartbeat_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _parse_iso_datetime(payload.get("last_successful_pipeline_run_at"))


def _stale_after_hours() -> int:
    raw = (os.getenv("SAAF_FEED_STALE_AFTER_HOURS") or "6").strip()
    try:
        value = int(raw)
        return value if value > 0 else 6
    except ValueError:
        return 6


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/health")
def health(db: SupabaseClient = Depends(get_db)) -> dict[str, object]:
    db_connected = False
    latest_feed_created_at: Optional[datetime] = None
    last_successful_pipeline_run_at: Optional[datetime] = None

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

    last_successful_pipeline_run_at = _load_heartbeat_timestamp() or latest_feed_created_at
    stale_after = _stale_after_hours()
    if last_successful_pipeline_run_at is None:
        pipeline_is_stale = True
    else:
        age_seconds = max(
            0.0,
            (datetime.utcnow() - _to_utc_naive(last_successful_pipeline_run_at)).total_seconds(),
        )
        pipeline_is_stale = age_seconds >= stale_after * 3600

    return {
        "status": "ok" if db_connected else "degraded",
        "database": "connected" if db_connected else "disconnected",
        "latest_feed_created_at": latest_feed_created_at,
        "last_successful_pipeline_run_at": last_successful_pipeline_run_at,
        "pipeline_stale_after_hours": stale_after,
        "pipeline_is_stale": pipeline_is_stale,
    }
