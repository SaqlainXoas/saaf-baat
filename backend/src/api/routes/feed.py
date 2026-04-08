from __future__ import annotations

from functools import lru_cache
from datetime import timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dtos import SourceCountDTO, StoryCardDTO
from src.api.entity_sanitizer import MAX_CONFIRMED_FACTS, MAX_DEBATED_CLAIMS, to_entity_dtos
from src.db.client import DatabaseError, SupabaseClient

router = APIRouter()


@lru_cache(maxsize=1)
def get_db() -> SupabaseClient:
    try:
        return SupabaseClient()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")


def _to_story_card(feed) -> StoryCardDTO:
    sources = [
        SourceCountDTO(source=src, count=int(cnt))
        for src, cnt in sorted((feed.source_attribution or {}).items(), key=lambda x: (-int(x[1]), x[0]))
    ]
    return StoryCardDTO(
        story_id=feed.cluster_id,
        created_at=feed.created_at,
        headline=feed.headline,
        snippet=feed.summary or "",
        category=str(feed.category),
        impact_labels=list(feed.impact_labels or []),
        confirmed_facts=to_entity_dtos(feed.confirmed_facts, MAX_CONFIRMED_FACTS),
        debated_claims=to_entity_dtos(feed.debated_claims, MAX_DEBATED_CLAIMS),
        sources=sources,
        metadata=dict(feed.metadata or {}),
    )


def _metadata_int(feed, key: str) -> int:
    raw = (feed.metadata or {}).get(key, 0)
    try:
        return int(raw)
    except Exception:
        return 0


def _story_sort_key(feed) -> tuple[float, float, float, str]:
    created_at = feed.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (
        -_metadata_int(feed, "editorial_priority"),
        -_metadata_int(feed, "deterministic_publish_score"),
        -created_at.timestamp(),
        str(feed.cluster_id),
    )


@router.get("/feed", response_model=list[StoryCardDTO])
def get_feed(
    category: Optional[str] = None,
    impact_label: Optional[str] = None,
    limit: int = Query(default=30, ge=1, le=200),
    db: SupabaseClient = Depends(get_db),
) -> list[StoryCardDTO]:
    try:
        feeds = db.get_analyzed_feed(category=category, impact_label=impact_label, limit=limit)
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
    feeds = sorted(feeds, key=_story_sort_key)
    return [_to_story_card(f) for f in feeds]
