from __future__ import annotations

from functools import lru_cache
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from src.api.dtos import EntityDTO, SourceCountDTO, StoryArticleDTO, StoryDetailDTO
from src.db.client import NotFoundError, SupabaseClient

router = APIRouter()


@lru_cache(maxsize=1)
def get_db() -> SupabaseClient:
    return SupabaseClient()


def _to_story_detail(feed, articles) -> StoryDetailDTO:
    sources = [
        SourceCountDTO(source=src, count=int(cnt))
        for src, cnt in sorted((feed.source_attribution or {}).items(), key=lambda x: (-int(x[1]), x[0]))
    ]
    return StoryDetailDTO(
        story_id=feed.cluster_id,
        created_at=feed.created_at,
        headline=feed.headline,
        snippet=feed.summary or "",
        category=str(feed.category),
        impact_labels=list(feed.impact_labels or []),
        confirmed_facts=[EntityDTO(**e.model_dump()) for e in (feed.confirmed_facts or [])],
        debated_claims=[EntityDTO(**e.model_dump()) for e in (feed.debated_claims or [])],
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

    try:
        cluster = db.get_cluster_by_id(cluster_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Cluster not found")

    articles = db.get_articles_by_ids(cluster.article_ids)
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

