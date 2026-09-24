from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends

from src.api.deps import get_db_or_none as get_db

router = APIRouter()
_BACKEND_DIR = Path(__file__).resolve().parents[3]


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


def _heartbeat_timestamp(heartbeat: dict[str, object], *keys: str) -> Optional[datetime]:
    for key in keys:
        parsed = _parse_iso_datetime(heartbeat.get(key))
        if parsed is not None:
            return parsed
    return None


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/health")
def health(db=Depends(get_db)) -> dict[str, object]:
    db_connected = False
    latest_feed_created_at: Optional[datetime] = None
    heartbeat = _load_heartbeat_payload()
    if os.getenv("SAAF_DB_BACKEND") == "supabase" and db is not None:
        try:
            result = db.client.table("pipeline_state").select("payload").eq("id", "daily").limit(1).execute()
            heartbeat = result.data[0]["payload"] if result.data else {}
        except Exception:
            heartbeat = {}
    last_run_at = _heartbeat_timestamp(heartbeat, "last_run_at")
    last_successful_run_at = _heartbeat_timestamp(
        heartbeat,
        "last_successful_run_at",
        "last_successful_pipeline_run_at",
    )
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
    # The pipeline records whether each LLM stage actually ran. Total editorial
    # unavailability used to be invisible: the brief silently filled with
    # template copy and looked merely flat (I-5). It is reported here instead.
    stats = dict(heartbeat.get("stats") or {})
    publication_status = str(stats.get("publication_status") or "unknown")
    editorial_status = str(stats.get("editorial_status") or "unknown")
    story_analysis_status = str(stats.get("story_analysis_status") or "unknown")
    triage_status = str(stats.get("triage_status") or "unknown")
    embedding_status = str(stats.get("embedding_status") or "unknown")
    llm_calls = {
        "triage": int(stats.get("triage_calls") or 0),
        "adjudication": int(stats.get("adjudication_calls") or 0),
        "story_analysis": int(stats.get("story_analysis_calls") or 0),
    }
    # Calls alone cannot distinguish "ran eight times and worked" from "ran
    # eight times and fell back on every one". The pipeline records all five
    # and they reach .pipeline_heartbeat.json; only the call count reached the
    # endpoint, so the health surface was thinner than the contract.
    story_analysis_counts = {
        "calls": int(stats.get("story_analysis_calls") or 0),
        "successes": int(stats.get("story_analysis_successes") or 0),
        "question_rejections": int(stats.get("story_analysis_question_rejections") or 0),
        "fallbacks": int(stats.get("story_analysis_fallbacks") or 0),
        "failures": int(stats.get("story_analysis_failures") or 0),
    }

    endpoint_health = [
        dict(row) for row in list(heartbeat.get("endpoint_health") or []) if isinstance(row, dict)
    ]
    quarantined_endpoints = [
        str(row.get("url") or "")
        for row in endpoint_health
        if str(row.get("status") or "") != "ok"
    ]

    try:
        db_connected = db.is_connected()
    except Exception:
        db_connected = False

    if db_connected:
        try:
            latest = db.get_analyzed_feed(limit=1, published_only=True)
            if latest:
                latest_feed_created_at = latest[0].created_at
        except Exception:
            latest_feed_created_at = None

    last_successful_run_source = "none"
    if last_successful_run_at is not None:
        last_successful_pipeline_run_at = last_successful_run_at
        last_successful_run_source = "heartbeat"
    elif latest_feed_created_at is not None:
        last_successful_pipeline_run_at = latest_feed_created_at
        last_successful_run_source = "latest_feed_created_at"
    else:
        last_successful_pipeline_run_at = None

    if last_successful_pipeline_run_at is None:
        pipeline_is_stale = True
    else:
        age_seconds = max(
            0.0,
            (datetime.utcnow() - _to_utc_naive(last_successful_pipeline_run_at)).total_seconds(),
        )
        pipeline_is_stale = age_seconds >= 28 * 3600

    if not db_connected:
        pipeline_status_reason = "Database unavailable; pipeline freshness cannot be confirmed."
    elif publication_status == "failed":
        pipeline_status_reason = "The last hosted edition could not be published; the previous edition remains available."
    elif editorial_status == "unavailable":
        pipeline_status_reason = (
            "No editorial provider was reachable on the last run, so it published "
            "nothing and the previous brief still stands. It will be served as "
            "stale rather than replaced with template copy."
        )
    elif story_analysis_status in {"partial", "unavailable"}:
        pipeline_status_reason = (
            f"Story analysis was {story_analysis_status} on the last run. "
            "The factual cards remain available, but one or more detail pages "
            "fell back to their short snippets."
        )
    elif embedding_status in {"unavailable", "degraded"}:
        pipeline_status_reason = (
            f"Embedding was {embedding_status} on the last run; some new reports "
            "could not be grouped into stories."
        )
    elif triage_status in {"unavailable", "degraded"}:
        # An article triage never saw is not publishable, so a bad triage run
        # shrinks the brief rather than breaking it - which is exactly why it
        # has to be said out loud. This used to report status "ok".
        pipeline_status_reason = (
            f"Triage was {triage_status} on the last run; untriaged clusters "
            "could not be published, so the brief may be short."
        )
    elif last_successful_run_source == "heartbeat":
        if pipeline_is_stale:
            pipeline_status_reason = "Pipeline heartbeat is older than the 28-hour freshness window."
        else:
            pipeline_status_reason = "Pipeline heartbeat is within the 28-hour freshness window."
    elif last_successful_run_source == "latest_feed_created_at":
        if pipeline_is_stale:
            pipeline_status_reason = (
                "Pipeline heartbeat is missing; newest analyzed feed row is older than the 28-hour freshness window."
            )
        else:
            pipeline_status_reason = (
                "Pipeline heartbeat is missing; using newest analyzed feed row as the fallback freshness signal."
            )
    else:
        pipeline_status_reason = "No pipeline heartbeat or analyzed feed rows were found."

    # Triage counts too. It was reported but excluded from the verdict, so a
    # run where triage failed on every batch - and therefore published nothing
    # it could describe honestly - still answered "ok".
    degraded = (
        not db_connected
        or pipeline_is_stale
        or publication_status == "failed"
        or editorial_status in {"unavailable", "degraded"}
        or story_analysis_status in {"partial", "unavailable"}
        or triage_status in {"unavailable", "degraded"}
        or embedding_status in {"unavailable", "degraded"}
    )

    return {
        "status": "ok" if not degraded else "degraded",
        "database": "connected" if db_connected else "disconnected",
        "latest_feed_created_at": latest_feed_created_at,
        "last_run_at": last_run_at,
        "run_started_at": _heartbeat_timestamp(heartbeat, "run_started_at"),
        "edition_date": heartbeat.get("edition_date"),
        "last_successful_run_at": last_successful_pipeline_run_at,
        "last_successful_run_source": last_successful_run_source,
        "degraded_sources": degraded_sources,
        "source_article_counts": source_article_counts,
        "endpoint_health": endpoint_health,
        "quarantined_endpoint_count": len(quarantined_endpoints),
        "pipeline_stale_after_hours": 28,
        "pipeline_is_stale": pipeline_is_stale,
        "pipeline_status_reason": pipeline_status_reason,
        "publication_status": publication_status,
        "editorial_status": editorial_status,
        "story_analysis_status": story_analysis_status,
        "story_analysis": story_analysis_counts,
        "triage_status": triage_status,
        "embedding_status": embedding_status,
        "llm_calls": llm_calls,
        "processing_unresolved": {
            "embeddings": int(stats.get("embedding_unresolved") or 0),
            "triage": int(stats.get("triage_unresolved") or 0),
        },
        "candidate_counts": {
            "analyzed": int(stats.get("candidates_analyzed") or 0),
            "eligible": int(stats.get("candidates_publishable") or 0),
            "selected": int(stats.get("editorial_selected") or 0),
            "cards": int(stats.get("feeds_inserted") or 0),
        },
        "short_brief_reason": stats.get("short_brief_reason") or None,
        "stage_seconds": dict(stats.get("stage_seconds") or {}),
    }
