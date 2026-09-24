from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db  # re-exported: tests override by this object
from src.api.dtos import FeedResponseDTO, SourceCountDTO, StoryCardDTO
from src.db.errors import DatabaseError

router = APIRouter()
_FRESH_BRIEF_WINDOW = timedelta(hours=20)
_PAKISTAN_TZ = ZoneInfo("Asia/Karachi")
_MORNING_EDITION_HOUR = 5


# Every card must carry a why-it-matters line. This is the API contract the
# homepage used to enforce with a silent render-time filter, which quietly
# shrank the brief whenever the backend regressed (I-7). Guaranteeing it here
# means a regression shows up as a flat card, not as missing stories.
_IMPACT_LINE_LAST_RESORT = (
    "This could affect public life in Pakistan today and is worth tracking closely."
)


def _to_story_card(feed) -> StoryCardDTO:
    sources = [
        SourceCountDTO(source=src, count=int(cnt))
        for src, cnt in sorted((feed.source_attribution or {}).items(), key=lambda x: (-int(x[1]), x[0]))
    ]
    metadata = dict(feed.metadata or {})
    # The homepage carries no analysis and no question, but the whole
    # story_analysis blob rode along inside metadata - 46% of a 34KB payload,
    # internal claim evidence included. The detail route serves what the UI
    # actually reads, as typed fields.
    metadata.pop("story_analysis", None)
    why_it_matters = str(metadata.get("why_it_matters") or "").strip()
    if not why_it_matters:
        metadata["why_it_matters"] = _IMPACT_LINE_LAST_RESORT
        metadata["why_it_matters_source"] = "api_contract_default"

    return StoryCardDTO(
        story_id=feed.cluster_id,
        created_at=feed.created_at,
        headline=feed.headline,
        snippet=feed.summary or "",
        category=str(feed.category),
        impact_labels=list(feed.impact_labels or []),
        sources=sources,
        metadata=metadata,
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
        # Was deterministic_publish_score, which saturated at 100 for every
        # published card and so ordered nothing. Source breadth is a fact.
        -len(feed.source_attribution or {}),
        -created_at.timestamp(),
        str(feed.cluster_id),
    )


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_fresh(
    generated_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    edition_hour: int = _MORNING_EDITION_HOUR,
) -> bool:
    if generated_at is None:
        return False
    generated_utc = _normalize_utc(generated_at)
    current_utc = _normalize_utc(now or datetime.now(timezone.utc))
    age = current_utc - generated_utc
    generated_pkt = generated_utc.astimezone(_PAKISTAN_TZ)
    current_pkt = current_utc.astimezone(_PAKISTAN_TZ)
    return (
        timedelta(0) <= age <= _FRESH_BRIEF_WINDOW
        and generated_pkt.date() == current_pkt.date()
        and generated_pkt.hour >= int(edition_hour)
    )


def _latest_brief_only(feeds):
    """Serve one brief, not an accumulation of every run's leftovers.

    A cluster the editor drops keeps its analyzed_feed row from the previous
    run, so the feed grew across runs: a live check served eleven cards for an
    eight-card brief, two of them the same story under two headlines written a
    few hours apart. Each published card carries the run that produced it, and
    only the newest run is the brief. Rows predating the stamp are, by
    definition, from an older run.
    """
    stamps = {
        str((feed.metadata or {}).get("brief_run_at") or "")
        for feed in feeds
    }
    stamps.discard("")
    if not stamps:
        return list(feeds)
    latest = max(stamps)
    return [feed for feed in feeds if str((feed.metadata or {}).get("brief_run_at") or "") == latest]


@router.get("/feed", response_model=FeedResponseDTO)
def get_feed(
    category: Optional[str] = None,
    impact_label: Optional[str] = None,
    limit: int = Query(default=30, ge=1, le=200),
    db=Depends(get_db),
) -> FeedResponseDTO:
    try:
        feeds = db.get_analyzed_feed(category=category, impact_label=impact_label, limit=limit)
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    feeds = _latest_brief_only(feeds)
    feeds = sorted(feeds, key=_story_sort_key)
    generated_at = max((_normalize_utc(feed.created_at) for feed in feeds), default=None)
    return FeedResponseDTO(
        generated_at=generated_at,
        is_fresh=_is_fresh(generated_at),
        stories=[_to_story_card(feed) for feed in feeds],
    )
