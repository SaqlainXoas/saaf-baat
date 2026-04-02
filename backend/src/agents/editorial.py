from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.db.models import AnalyzedFeed, RawArticle

logger = logging.getLogger(__name__)


VALID_CATEGORIES = (
    "economy",
    "politics",
    "city",
    "education",
    "health",
    "sports",
    "technology",
    "entertainment",
    "security",
    "international",
    "other",
)

VALID_IMPACT_LABELS = (
    "💳 WALLET",
    "🚦 COMMUTE",
    "🛡️ SAFETY",
    "🏢 WORK",
    "⚡ UTILITIES",
    "🏛️ GOVERNANCE",
)


class EditorialError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClusterEditorialCandidate:
    cluster_id: UUID
    base_feed: AnalyzedFeed
    representative_article: RawArticle
    articles: Sequence[RawArticle]
    algorithm_used: str
    avg_similarity: Optional[float]
    min_member_similarity: Optional[float]

    def to_prompt_dict(self) -> Dict[str, Any]:
        publish_dates = [a.publish_date for a in self.articles if a.publish_date is not None]
        latest_publish = max(publish_dates).isoformat() if publish_dates else None
        earliest_publish = min(publish_dates).isoformat() if publish_dates else None
        source_names = sorted({a.source for a in self.articles})

        supporting_headlines: List[str] = []
        for article in self.articles:
            headline = (article.headline or "").strip()
            if headline and headline not in supporting_headlines:
                supporting_headlines.append(headline)

        confirmed = [ent.text for ent in list(self.base_feed.confirmed_facts or [])[:5]]
        debated = [ent.text for ent in list(self.base_feed.debated_claims or [])[:5]]

        return {
            "cluster_id": str(self.cluster_id),
            "algorithm_used": self.algorithm_used,
            "cluster_size": len(self.articles),
            "sources": source_names,
            "source_counts": dict(self.base_feed.source_attribution or {}),
            "latest_publish_date": latest_publish,
            "earliest_publish_date": earliest_publish,
            "representative_source": self.representative_article.source,
            "representative_headline": self.representative_article.headline,
            "representative_excerpt": _truncate(self.representative_article.main_text, 700),
            "supporting_headlines": supporting_headlines[:5],
            "deterministic_category": str(self.base_feed.category),
            "deterministic_impact_labels": list(self.base_feed.impact_labels or []),
            "deterministic_summary": self.base_feed.summary or "",
            "confirmed_facts": confirmed,
            "debated_claims": debated,
            "avg_similarity": _round_or_none(self.avg_similarity),
            "min_member_similarity": _round_or_none(self.min_member_similarity),
        }


class EditorialStory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    priority: int = Field(ge=0, le=100)
    headline: str = Field(min_length=8, max_length=180)
    summary: str = Field(min_length=24, max_length=320)
    category: str
    impact_labels: List[str] = Field(min_length=1, max_length=3)
    why_it_matters: str = Field(min_length=16, max_length=220)
    what_to_watch: str = Field(min_length=12, max_length=180)
    public_impact: str
    story_tags: List[str] = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0, le=1)
    selection_reason: str = Field(min_length=12, max_length=220)

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {value}")
        return value

    @field_validator("impact_labels")
    @classmethod
    def _validate_impact_labels(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        for item in value:
            if item not in VALID_IMPACT_LABELS:
                raise ValueError(f"Invalid impact label: {item}")
            if item not in cleaned:
                cleaned.append(item)
        return cleaned[:3]

    @field_validator("public_impact")
    @classmethod
    def _validate_public_impact(cls, value: str) -> str:
        if value not in {"high", "medium", "watch"}:
            raise ValueError(f"Invalid public_impact: {value}")
        return value

    @field_validator("story_tags")
    @classmethod
    def _validate_tags(cls, value: List[str]) -> List[str]:
        tags = [tag.strip() for tag in value if tag and tag.strip()]
        if not tags:
            raise ValueError("story_tags must contain at least one tag")
        return tags[:4]


class EditorialResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stories: List[EditorialStory] = Field(..., max_length=9)
    omitted_cluster_ids: List[str]


class GroqMorningBriefService:
    DEFAULT_MODEL = "openai/gpt-oss-120b"
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
        client: Optional[httpx.Client] = None,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = (model or os.getenv("SAAF_EDITORIAL_LLM_MODEL") or self.DEFAULT_MODEL).strip()
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)

        if not self.api_key:
            raise EditorialError("Missing GROQ_API_KEY for editorial review")

    def review_clusters(
        self,
        candidates: Sequence[ClusterEditorialCandidate],
        *,
        max_stories: int = 9,
    ) -> Dict[UUID, EditorialStory]:
        if not candidates:
            return {}

        candidate_lookup = {str(candidate.cluster_id): candidate for candidate in candidates}
        candidate_rows = [candidate.to_prompt_dict() for candidate in candidates]
        system_prompt = (
            "You are the Saaf Baat editorial desk. Build a finite Pakistan morning brief.\n"
            "Select only the most important stories that an ordinary person in Pakistan should know this morning.\n"
            "Use only the provided evidence. Do not invent facts. Exclude gossip, celebrity, soft lifestyle, sports unless nationally consequential, and foreign stories unless the effect on Pakistan is clear.\n"
            "Prefer public-impact stories in governance, economy, security, utilities, transport, health, education, or major city life.\n"
            "When evidence is thin or ambiguous, omit the cluster.\n"
            "Headlines and summaries must be clean, calm, concrete, and non-sensational.\n"
            "Return valid JSON only."
        )
        user_prompt = json.dumps(
            {
                "task": "Select and format the morning brief.",
                "max_stories": max(1, min(int(max_stories), 9)),
                "selection_rules": [
                    "Return at most max_stories items in stories.",
                    "Each story must map to exactly one provided cluster_id.",
                    "Use impact_labels only from the allowed set.",
                    "Prefer Pakistan relevance and public impact over novelty.",
                    "Summary should explain what happened and why it matters in 1-2 sentences.",
                    "why_it_matters and what_to_watch must stay grounded in provided evidence.",
                ],
                "candidates": candidate_rows,
            },
            ensure_ascii=False,
        )

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            body = self._post_completion(
                payload
                | {
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "saaf_baat_editorial_brief",
                            "strict": True,
                            "schema": EditorialResponse.model_json_schema(),
                        },
                    }
                }
            )
            parsed = self._parse_response(body, candidate_lookup)
        except httpx.HTTPStatusError as exc:
            if exc.response is None or exc.response.status_code != 400:
                raise EditorialError(f"Groq editorial request failed: {exc}") from exc
            logger.warning(
                "Strict Groq schema mode failed, retrying with json_object mode: %s",
                _truncate(exc.response.text, 240),
            )
            try:
                body = self._post_completion(payload | {"response_format": {"type": "json_object"}})
                parsed = self._parse_response(body, candidate_lookup)
            except Exception as fallback_exc:
                raise EditorialError(f"Groq editorial fallback failed: {fallback_exc}") from fallback_exc
        except Exception as exc:
            raise EditorialError(f"Groq editorial request failed: {exc}") from exc

        by_cluster: Dict[UUID, EditorialStory] = {}
        allowed_ids = {candidate.cluster_id for candidate in candidates}
        for story in parsed.stories:
            try:
                cluster_id = UUID(story.cluster_id)
            except ValueError:
                logger.warning("Ignoring editorial story with invalid cluster_id=%s", story.cluster_id)
                continue
            if cluster_id not in allowed_ids:
                logger.warning("Ignoring editorial story for unknown cluster_id=%s", cluster_id)
                continue
            if cluster_id in by_cluster:
                continue
            by_cluster[cluster_id] = story

        return by_cluster

    def _post_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._client.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _parse_response(
        body: Dict[str, Any],
        candidate_lookup: Optional[Dict[str, ClusterEditorialCandidate]] = None,
    ) -> EditorialResponse:
        try:
            content = body["choices"][0]["message"]["content"]
            cleaned = str(content).strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                cleaned = cleaned.replace("json\n", "", 1).strip()
            payload = json.loads(cleaned)
            normalized = _normalize_editorial_payload(payload, candidate_lookup or {})
            return EditorialResponse.model_validate(normalized)
        except Exception as exc:
            raise EditorialError(f"Groq editorial response parsing failed: {exc}") from exc


def merge_editorial_story(
    candidate: ClusterEditorialCandidate,
    story: EditorialStory,
    *,
    model_name: str,
) -> AnalyzedFeed:
    feed = candidate.base_feed.model_copy(deep=True)
    feed.headline = story.headline.strip()
    feed.summary = story.summary.strip()
    feed.category = story.category
    feed.impact_labels = story.impact_labels

    metadata = dict(feed.metadata or {})
    metadata.update(
        {
            "editorial_model": model_name,
            "editorial_priority": int(story.priority),
            "editorial_confidence": float(story.confidence),
            "editorial_grade": story.public_impact,
            "why_it_matters": story.why_it_matters.strip(),
            "what_to_watch": story.what_to_watch.strip(),
            "story_tags": list(story.story_tags),
            "selection_reason": story.selection_reason.strip(),
            "cluster_algorithm": candidate.algorithm_used,
            "cluster_avg_similarity": _round_or_none(candidate.avg_similarity),
            "cluster_min_member_similarity": _round_or_none(candidate.min_member_similarity),
            "representative_source": candidate.representative_article.source,
            "representative_headline": candidate.representative_article.headline,
            "llm_augmented": True,
        }
    )
    feed.metadata = metadata
    return feed


def _truncate(text: str, limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _round_or_none(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _normalize_editorial_payload(
    payload: Dict[str, Any],
    candidate_lookup: Dict[str, ClusterEditorialCandidate],
) -> Dict[str, Any]:
    stories = payload.get("stories")
    if not isinstance(stories, list):
        stories = []

    normalized_stories: List[Dict[str, Any]] = []
    for item in stories:
        if not isinstance(item, dict):
            continue
        cluster_id = str(item.get("cluster_id") or "").strip()
        if not cluster_id:
            continue
        candidate = candidate_lookup.get(cluster_id)
        if candidate is None:
            continue

        base_feed = candidate.base_feed
        priority = item.get("priority")
        if not isinstance(priority, int):
            priority = min(95, max(50, 45 + (10 * len(candidate.articles))))

        impact_labels = item.get("impact_labels")
        if not isinstance(impact_labels, list):
            impact_labels = []
        impact_labels = [label for label in impact_labels if label in VALID_IMPACT_LABELS]
        if not impact_labels:
            impact_labels = list(base_feed.impact_labels or ["🏛️ GOVERNANCE"])

        category = item.get("category") or str(base_feed.category)
        if category not in VALID_CATEGORIES:
            category = str(base_feed.category)
        public_impact = item.get("public_impact")
        if public_impact not in {"high", "medium", "watch"}:
            public_impact = "high" if priority >= 80 else "medium"
        story_tags = item.get("story_tags")
        if not isinstance(story_tags, list) or not story_tags:
            story_tags = _default_story_tags(candidate)

        summary = item.get("summary") or base_feed.summary or candidate.representative_article.headline
        why_it_matters = item.get("why_it_matters") or summary
        what_to_watch = item.get("what_to_watch") or "Watch for the next official update."
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.65

        normalized_stories.append(
            {
                "cluster_id": cluster_id,
                "priority": int(priority),
                "headline": item.get("headline") or base_feed.headline,
                "summary": summary,
                "category": category,
                "impact_labels": impact_labels,
                "why_it_matters": why_it_matters,
                "what_to_watch": what_to_watch,
                "public_impact": public_impact,
                "story_tags": story_tags,
                "confidence": float(confidence),
                "selection_reason": item.get("selection_reason") or "Selected by editorial review.",
            }
        )

    omitted = payload.get("omitted_cluster_ids")
    if not isinstance(omitted, list):
        omitted = []

    return {
        "stories": normalized_stories,
        "omitted_cluster_ids": [str(item) for item in omitted if item],
    }


def _default_story_tags(candidate: ClusterEditorialCandidate) -> List[str]:
    tags: List[str] = []
    tags.append(str(candidate.base_feed.category))
    for fact in candidate.base_feed.confirmed_facts[:2]:
        text = fact.text.strip().lower().replace(" ", "-")
        if text and text not in tags:
            tags.append(text)
    if len(tags) == 1:
        tags.append(candidate.representative_article.source)
    return tags[:4]


__all__ = [
    "ClusterEditorialCandidate",
    "EditorialError",
    "EditorialStory",
    "GroqMorningBriefService",
    "merge_editorial_story",
]
