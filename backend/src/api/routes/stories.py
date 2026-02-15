from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from src.api.dtos import SourceCountDTO, StoryArticleDTO, StoryDetailDTO
from src.api.entity_sanitizer import MAX_CONFIRMED_FACTS, MAX_DEBATED_CLAIMS, to_entity_dtos
from src.db.client import DatabaseError, NotFoundError, SupabaseClient

router = APIRouter()


@lru_cache(maxsize=1)
def get_db() -> SupabaseClient:
    try:
        return SupabaseClient()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")


def _to_story_detail(feed, articles) -> StoryDetailDTO:
    source_attribution = dict(feed.source_attribution or {})
    if not source_attribution:
        for article in articles:
            source_attribution[article.source] = source_attribution.get(article.source, 0) + 1

    sources = [
        SourceCountDTO(source=src, count=int(cnt))
        for src, cnt in sorted(source_attribution.items(), key=lambda x: (-int(x[1]), x[0]))
    ]
    return StoryDetailDTO(
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
        articles=[
            StoryArticleDTO(
                id=a.id,
                source=a.source,
                headline=a.headline,
                url=a.url,
                publish_date=a.publish_date,
            )
            for a in articles
        ],
    )


@router.get("/stories/{cluster_id}", response_model=StoryDetailDTO)
def get_story(
    cluster_id: UUID,
    db: SupabaseClient = Depends(get_db),
) -> StoryDetailDTO:
    try:
        feed = db.get_analyzed_feed_by_cluster_id(cluster_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Story not found")
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

    try:
        cluster = db.get_cluster_by_id(cluster_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Cluster not found")
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

    try:
        articles = db.get_articles_by_ids(cluster.article_ids)
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
    # Most useful ordering: newest publish_date first, then by source.
    articles = sorted(
        articles,
        key=lambda a: (
            a.publish_date is None,
            -(a.publish_date.timestamp() if a.publish_date else 0),
            a.source,
            a.url,
        ),
    )
    return _to_story_detail(feed, articles)
