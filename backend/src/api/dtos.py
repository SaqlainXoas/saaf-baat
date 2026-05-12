from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EntityDTO(BaseModel):
    text: str
    type: str
    sources: int = 1


class SourceCountDTO(BaseModel):
    source: str
    count: int


class StoryCardDTO(BaseModel):
    story_id: UUID = Field(..., description="Cluster ID backing this story")
    created_at: datetime
    headline: str
    snippet: str
    category: str
    impact_labels: List[str] = Field(default_factory=list)
    sources: List[SourceCountDTO] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StoryArticleDTO(BaseModel):
    id: UUID
    source: str
    headline: str
    url: str
    publish_date: Optional[datetime] = None


class StoryDetailDTO(StoryCardDTO):
    articles: List[StoryArticleDTO] = Field(default_factory=list)


class FeedResponseDTO(BaseModel):
    generated_at: Optional[datetime] = None
    is_fresh: bool = False
    stories: List[StoryCardDTO] = Field(default_factory=list)
