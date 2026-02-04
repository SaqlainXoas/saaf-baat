"""
Pydantic models for Saaf Baat database entities.

Models:
- RawArticle: Scraped article before processing
- Cluster: Group of related articles
- AnalyzedFeed: Processed story for frontend display
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class Category(str, Enum):
    """Valid article categories."""
    ECONOMY = "economy"
    POLITICS = "politics"
    CITY = "city"
    EDUCATION = "education"
    HEALTH = "health"
    SPORTS = "sports"
    TECHNOLOGY = "technology"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class ImpactLabel(str, Enum):
    """Impact labels indicating relevance to user's life."""
    WALLET = "💳 WALLET"
    COMMUTE = "🚦 COMMUTE"
    SAFETY = "🛡️ SAFETY"
    WORK = "🏢 WORK"
    UTILITIES = "⚡ UTILITIES"
    GOVERNANCE = "🏛️ GOVERNANCE"


class EntityType(str, Enum):
    """Named entity types from NLP extraction."""
    PERSON = "PERSON"
    ORG = "ORG"
    GPE = "GPE"  # Geo-Political Entity (cities, countries)
    DATE = "DATE"
    MONEY = "MONEY"
    EVENT = "EVENT"
    MISC = "MISC"


class ExtractedEntity(BaseModel):
    """An entity extracted from article text."""
    text: str
    type: EntityType
    sources: int = 1  # Number of sources mentioning this entity
    
    model_config = ConfigDict(use_enum_values=True)


class SourceAttribution(BaseModel):
    """Attribution of articles to their sources."""
    source: str
    count: int
    article_ids: List[UUID] = Field(default_factory=list)


class RawArticle(BaseModel):
    """
    Represents a scraped news article before processing.
    
    The content_hash is auto-generated from headline + main_text
    to enable deduplication across sources.
    """
    id: UUID = Field(default_factory=uuid4)
    source: str = Field(..., min_length=1, description="News source identifier (e.g., 'dawn', 'tribune')")
    url: str = Field(..., description="Original article URL")
    headline: str = Field(..., min_length=1, description="Article headline/title")
    main_text: str = Field(..., min_length=50, description="Article body content")
    author: Optional[str] = None
    publish_date: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    content_hash: str = Field(default="", description="SHA-256 hash for deduplication")
    cluster_id: Optional[UUID] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
        validate_assignment=True,
    )
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL is valid format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v
    
    @model_validator(mode="after")
    def generate_content_hash(self) -> "RawArticle":
        """Auto-generate content hash from headline and main_text."""
        if not self.content_hash:
            content = f"{self.headline}{self.main_text}"
            self.content_hash = hashlib.sha256(content.encode()).hexdigest()
        return self
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        data = self.model_dump(exclude={"embedding"})
        # Convert UUID to string for JSON serialization
        data["id"] = str(data["id"])
        if data["cluster_id"]:
            data["cluster_id"] = str(data["cluster_id"])
        # Convert datetime to ISO string for JSON serialization
        if data.get("publish_date"):
            data["publish_date"] = data["publish_date"].isoformat()
        if data.get("scraped_at"):
            data["scraped_at"] = data["scraped_at"].isoformat()
        return data


class Cluster(BaseModel):
    """
    Represents a group of related articles about the same story.
    
    Clusters are formed by the embedding + clustering pipeline
    and contain references to all articles in the group.
    """
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    article_ids: List[UUID] = Field(default_factory=list)
    centroid_embedding: Optional[List[float]] = None
    representative_article_id: Optional[UUID] = None
    cluster_size: int = Field(default=0, ge=0)
    avg_similarity: Optional[float] = Field(default=None, ge=0, le=1)
    algorithm_used: str = "hdbscan"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )
    
    @model_validator(mode="after")
    def update_cluster_size(self) -> Cluster:
        """Auto-update cluster size based on article_ids."""
        object.__setattr__(self, 'cluster_size', len(self.article_ids))
        return self
    
    def add_article(self, article_id: UUID) -> None:
        """Add an article to the cluster."""
        if article_id not in self.article_ids:
            self.article_ids.append(article_id)
            object.__setattr__(self, 'cluster_size', len(self.article_ids))
            object.__setattr__(self, 'updated_at', datetime.utcnow())
    
    def remove_article(self, article_id: UUID) -> None:
        """Remove an article from the cluster."""
        if article_id in self.article_ids:
            self.article_ids.remove(article_id)
            object.__setattr__(self, 'cluster_size', len(self.article_ids))
            object.__setattr__(self, 'updated_at', datetime.utcnow())
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        data = self.model_dump(exclude={"centroid_embedding"})
        data["id"] = str(data["id"])
        data["article_ids"] = [str(aid) for aid in data["article_ids"]]
        if data["representative_article_id"]:
            data["representative_article_id"] = str(data["representative_article_id"])
        # Convert datetime to ISO string for JSON serialization
        if data.get("created_at"):
            data["created_at"] = data["created_at"].isoformat()
        if data.get("updated_at"):
            data["updated_at"] = data["updated_at"].isoformat()
        return data


class AnalyzedFeed(BaseModel):
    """
    Represents a fully processed story ready for frontend display.
    
    Contains:
    - Headline and summary
    - Category classification
    - Confirmed facts (entities in ALL articles)
    - Debated claims (entities in SOME articles)
    - Impact labels
    - Source attribution
    """
    id: UUID = Field(default_factory=uuid4)
    cluster_id: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    headline: str = Field(..., min_length=1)
    summary: Optional[str] = None
    category: Category
    confirmed_facts: List[ExtractedEntity] = Field(default_factory=list)
    debated_claims: List[ExtractedEntity] = Field(default_factory=list)
    impact_labels: List[ImpactLabel] = Field(default_factory=list)
    source_attribution: Dict[str, int] = Field(default_factory=dict)
    entity_counts: Dict[str, int] = Field(default_factory=dict)
    classification_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    is_published: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
        use_enum_values=True,
        validate_assignment=True,
    )
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        data = self.model_dump()
        data["id"] = str(data["id"])
        data["cluster_id"] = str(data["cluster_id"])
        # Convert datetime to ISO string for JSON serialization
        if data.get("created_at"):
            data["created_at"] = data["created_at"].isoformat()
        # Convert entities to plain dicts
        data["confirmed_facts"] = [e.model_dump() if isinstance(e, BaseModel) else e for e in self.confirmed_facts]
        data["debated_claims"] = [e.model_dump() if isinstance(e, BaseModel) else e for e in self.debated_claims]
        return data
    
    @classmethod
    def from_db_dict(cls, data: Dict[str, Any]) -> AnalyzedFeed:
        """Create instance from database record."""
        # Convert entity dicts back to ExtractedEntity
        if data.get("confirmed_facts"):
            data["confirmed_facts"] = [
                ExtractedEntity(**e) if isinstance(e, dict) else e 
                for e in data["confirmed_facts"]
            ]
        if data.get("debated_claims"):
            data["debated_claims"] = [
                ExtractedEntity(**e) if isinstance(e, dict) else e 
                for e in data["debated_claims"]
            ]
        return cls(**data)


# Type aliases for clarity
ArticleList = List[RawArticle]
ClusterList = List[Cluster]
FeedList = List[AnalyzedFeed]
