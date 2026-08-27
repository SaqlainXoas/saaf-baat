from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from src.agents.clustering import trusted_article_timestamp
from src.api.deps import get_db  # re-exported: tests override by this object
from src.api.dtos import SourceCountDTO, StoryArticleDTO, StoryDetailDTO
from src.db.errors import DatabaseError, NotFoundError

router = APIRouter()
_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
_PKT = timezone(timedelta(hours=5))
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "amid",
    "after",
    "this",
    "that",
    "over",
    "under",
    "about",
    # A second "into" sat here. It is a set, so the duplicate was inert - but it
    # means a word someone meant to add never was. Removing the duplicate rather
    # than guessing the intended word: this list feeds headline tokenisation, and
    # a guessed stopword would silently change what related stories match.
    "their",
    "his",
    "her",
    "its",
    "our",
    "your",
    "while",
    "through",
    "following",
    "announces",
    "announce",
    "report",
    "reports",
}


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _published_on(value: datetime | None) -> date | None:
    aware = _as_aware_utc(value)
    if aware is None:
        return None
    return aware.astimezone(_PKT).date()


def _looks_like_date_only_publish_date(article) -> bool:
    precision = str((article.metadata or {}).get("publish_date_precision") or "").strip().lower()
    if precision in {"date", "day"}:
        return True

    publish_date = _as_aware_utc(article.publish_date)
    if publish_date is None:
        return False
    return publish_date.timetz().replace(tzinfo=None) == time(19, 0)


def _story_article_dto(article) -> StoryArticleDTO:
    if article.publish_date is None:
        return StoryArticleDTO(
            id=article.id,
            source=article.source,
            headline=article.headline,
            url=article.url,
            publish_date=None,
            published_on=None,
            publish_date_status="missing",
        )

    if _looks_like_date_only_publish_date(article):
        return StoryArticleDTO(
            id=article.id,
            source=article.source,
            headline=article.headline,
            url=article.url,
            publish_date=None,
            published_on=_published_on(article.publish_date),
            publish_date_status="date_only",
        )

    return StoryArticleDTO(
        id=article.id,
        source=article.source,
        headline=article.headline,
        url=article.url,
        publish_date=article.publish_date,
        published_on=_published_on(article.publish_date),
        publish_date_status="precise",
    )


def _trusted_sort_timestamp(article) -> float:
    return trusted_article_timestamp(article).timestamp()


def _story_analysis_metadata(feed) -> dict:
    value = dict(feed.metadata or {}).get("story_analysis")
    return dict(value) if isinstance(value, dict) else {}


# Internal validation evidence, and the rejected copy kept for diagnosis. The
# reader gets `analysis`, `question` and `analysis_sources` as typed fields;
# none of these keys were ever rendered, and `rejected` must never be.
_PRIVATE_ANALYSIS_KEYS = (
    "claims",
    "question_supporting_article_ids",
    "rejected",
)


def _public_metadata(feed) -> dict:
    metadata = dict(feed.metadata or {})
    story_analysis = metadata.get("story_analysis")
    if isinstance(story_analysis, dict):
        metadata["story_analysis"] = {
            key: value
            for key, value in story_analysis.items()
            if key not in _PRIVATE_ANALYSIS_KEYS
        }
    return metadata


def _to_story_detail(feed, articles, analysis_sources=()) -> StoryDetailDTO:
    source_attribution = dict(feed.source_attribution or {})
    if not source_attribution:
        for article in articles:
            source_attribution[article.source] = source_attribution.get(article.source, 0) + 1

    sources = [
        SourceCountDTO(source=src, count=int(cnt))
        for src, cnt in sorted(source_attribution.items(), key=lambda x: (-int(x[1]), x[0]))
    ]
    story_analysis = _story_analysis_metadata(feed)
    analysis = str(story_analysis.get("analysis") or "").strip() or None
    question = str(story_analysis.get("question") or "").strip() or None
    return StoryDetailDTO(
        story_id=feed.cluster_id,
        created_at=feed.created_at,
        headline=feed.headline,
        snippet=feed.summary or "",
        category=str(feed.category),
        impact_labels=list(feed.impact_labels or []),
        sources=sources,
        metadata=_public_metadata(feed),
        analysis=analysis,
        question=question,
        articles=[_story_article_dto(a) for a in articles],
        analysis_sources=[_story_article_dto(a) for a in analysis_sources],
    )


def _keywords(*parts: str) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for match in _TOKEN_RE.findall(part or ""):
            token = match.lower().strip("'")
            if len(token) < 4 or token in _STOPWORDS or token.isdigit():
                continue
            tokens.add(token)
    return tokens


def _filter_relevant_articles(feed, articles):
    if len(articles) <= 1:
        return articles

    metadata = dict(feed.metadata or {})
    tag_text = " ".join(str(tag) for tag in metadata.get("story_tags", []) if tag)
    story_tokens = _keywords(feed.headline, feed.summary or "", tag_text)
    if not story_tokens:
        return articles

    relevant = []
    for article in articles:
        overlap = len(_keywords(article.headline) & story_tokens)
        if overlap >= 2:
            relevant.append(article)

    return relevant or articles


@router.get("/stories/{cluster_id}", response_model=StoryDetailDTO)
def get_story(
    cluster_id: UUID,
    db=Depends(get_db),
) -> StoryDetailDTO:
    try:
        feed = db.get_analyzed_feed_by_cluster_id(cluster_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Story not found") from None
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc

    try:
        cluster = db.get_cluster_by_id(cluster_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Cluster not found") from None
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc

    try:
        articles = db.get_articles_by_ids(cluster.article_ids)
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
    # Most useful ordering: newest trusted timestamp first, then by source.
    articles = sorted(
        articles,
        key=lambda a: (
            -_trusted_sort_timestamp(a),
            a.source,
            a.url,
        ),
    )
    articles = _filter_relevant_articles(feed, articles)

    story_analysis = _story_analysis_metadata(feed)
    primary_ids = {str(article.id) for article in articles}
    related_ids = [
        str(article_id)
        for article_id in list(story_analysis.get("related_article_ids") or [])[:20]
        if str(article_id) not in primary_ids
    ]
    analysis_sources = []
    if related_ids:
        try:
            analysis_sources = db.get_articles_by_ids(related_ids)
        except DatabaseError as exc:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
        analysis_sources = sorted(
            analysis_sources,
            key=lambda a: (-_trusted_sort_timestamp(a), a.source, a.url),
        )
    return _to_story_detail(feed, articles, analysis_sources)
