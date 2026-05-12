from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.agents.clustering import publish_date_skew_hours, trusted_article_timestamp
from src.db.models import AnalyzedFeed, RawArticle

logger = logging.getLogger(__name__)
# Prompt lives in config/editorial_prompt.md — update there first
_EDITORIAL_PROMPT_PATH = Path(__file__).resolve().parents[2] / "config" / "editorial_prompt.md"


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


@lru_cache(maxsize=1)
def _load_editorial_system_prompt() -> str:
    text = _EDITORIAL_PROMPT_PATH.read_text(encoding="utf-8").strip()
    marker = "## Prompt"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    return text


EDITORIAL_SYSTEM_PROMPT = _load_editorial_system_prompt()


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
        trusted_timestamps = [trusted_article_timestamp(article) for article in self.articles]
        latest_publish = max(trusted_timestamps).isoformat() if trusted_timestamps else None
        earliest_publish = min(trusted_timestamps).isoformat() if trusted_timestamps else None
        source_names = sorted({a.source for a in self.articles})
        suspicious_publish_dates = 0
        for article in self.articles:
            skew_hours = publish_date_skew_hours(article)
            if skew_hours is not None and skew_hours > 72:
                suspicious_publish_dates += 1

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
            "suspicious_publish_dates": suspicious_publish_dates,
            "representative_source": self.representative_article.source,
            "representative_headline": self.representative_article.headline,
            "representative_excerpt": _truncate(self.representative_article.main_text, 700),
            "supporting_headlines": supporting_headlines[:5],
            "deterministic_category": str(self.base_feed.category),
            "deterministic_impact_labels": list(self.base_feed.impact_labels or []),
            "deterministic_summary": self.base_feed.summary or "",
            "deterministic_publish_score": int((self.base_feed.metadata or {}).get("deterministic_publish_score", 0) or 0),
            "publisher_topline_score": int((self.base_feed.metadata or {}).get("publisher_topline_score", 0) or 0),
            "publisher_topline_sources": list((self.base_feed.metadata or {}).get("publisher_topline_sources", [])),
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
    impact_line: str = Field(min_length=16, max_length=220)
    category: str
    impact_labels: List[str] = Field(min_length=1, max_length=3)
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
    omitted_cluster_ids: List[str] = Field(default_factory=list)


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
        system_prompt = EDITORIAL_SYSTEM_PROMPT
        user_prompt = build_editorial_user_prompt(candidate_rows, max_stories=max_stories)

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            # Groq strict json_schema mode currently validates that each object schema includes a
            # `required` array listing every key in `properties` (even if a field is "optional"
            # in our internal Pydantic model). We keep our Pydantic models flexible for parsing,
            # but send a stricter, Groq-compatible schema in the request.
            strict_schema = _groq_strict_json_schema(EditorialResponse.model_json_schema())
            body = self._post_completion(
                payload
                | {
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "saaf_baat_editorial_brief",
                            "strict": True,
                            "schema": strict_schema,
                        },
                    }
                }
            )
            parsed = self._parse_response(body, candidate_lookup)
        except httpx.HTTPStatusError as exc:
            if exc.response is None or exc.response.status_code != 400:
                raise EditorialError(f"Groq editorial request failed: {exc}") from exc
            # If Groq strict mode produced a candidate JSON but rejected it for schema mismatch,
            # the 400 body often includes a `failed_generation` payload. We can salvage that
            # payload locally (normalization + Pydantic validation) without spending another
            # API call (and without risking a 429 on fallback).
            salvaged = _salvage_failed_generation(exc.response, candidate_lookup)
            if salvaged is not None:
                parsed = salvaged
            else:
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
    feed.category = story.category
    feed.impact_labels = story.impact_labels

    metadata = dict(feed.metadata or {})
    metadata.update(
        {
            "editorial_model": model_name,
            "editorial_priority": int(story.priority),
            "editorial_confidence": float(story.confidence),
            "editorial_grade": story.public_impact,
            "impact_line": story.impact_line.strip(),
            "why_it_matters": story.impact_line.strip(),
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


def build_editorial_user_prompt(candidate_rows: Sequence[Dict[str, Any]], *, max_stories: int) -> str:
    target_cap = max(1, min(int(max_stories), 9))
    target_floor = min(5, target_cap)
    return json.dumps(
        {
            "task": "Select and format the morning brief.",
            "target_story_range": {"min": target_floor, "max": target_cap},
            "max_stories": target_cap,
            "selection_rules": [
                "Return at most max_stories items in stories.",
                "Aim to return at least target_story_range.min stories when enough candidates clearly support a Pakistan morning brief.",
                "Each story must map to exactly one provided cluster_id.",
                "headline must be 10-12 words, active voice, and direct.",
                "impact_line must be one sentence on why the story matters to an ordinary person in Pakistan today.",
                "what_to_watch must be one sentence on the next concrete development to follow.",
                "Use impact_labels only from the allowed set.",
                "Prefer Pakistan relevance, nationally dominant developments, and direct public impact over novelty, symbolism, or feature value.",
                "Prefer hard-news developments over profiles, travel, lifestyle, seasonal, or commentary-style pieces.",
                "Use publisher_topline_score and publisher_topline_sources as strong signals for what belongs near the top of the brief.",
                "Do not let an isolated incident lead the brief if a broader governance, economy, utilities, diplomacy, weather, or public-life story has stronger publisher topline support.",
                "impact_line and what_to_watch must stay grounded in provided evidence.",
                "Never use passive voice.",
                "Never write vague attribution like 'sources say'.",
                "If you cannot write a confident impact_line, omit the cluster.",
                "Treat suspicious_publish_dates as a warning signal, not a reason by itself to invent or exaggerate freshness.",
            ],
            "candidates": list(candidate_rows),
        },
        ensure_ascii=False,
    )


def _truncate(text: str, limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _round_or_none(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _groq_strict_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a JSON Schema dict into the shape Groq strict mode accepts.

    Observed Groq validation constraint:
    - For any object schema with `properties`, `required` must be supplied and must include
      *every* key in `properties`.

    We apply this recursively to nested object schemas (including those inside arrays and anyOf).
    """

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            # Recurse first so nested nodes are normalized.
            for key, value in list(node.items()):
                if isinstance(value, (dict, list)):
                    node[key] = _walk(value)

            properties = node.get("properties")
            if isinstance(properties, dict) and properties:
                keys = list(properties.keys())
                node["required"] = keys
                # Make sure objects are closed unless explicitly configured otherwise.
                node.setdefault("additionalProperties", False)

            return node

        if isinstance(node, list):
            return [_walk(item) for item in node]

        return node

    # Work on a deep copy to avoid mutating the original schema reference.
    return _walk(json.loads(json.dumps(schema)))


def _salvage_failed_generation(
    response: httpx.Response,
    candidate_lookup: Dict[str, ClusterEditorialCandidate],
) -> Optional[EditorialResponse]:
    """
    Try to salvage Groq strict-mode 400s that include `failed_generation`.

    Groq can return 400 even when it generated JSON (e.g. missing a required property). In that
    case, the response JSON may include an `error.failed_generation` field. We can parse it,
    normalize, and validate locally to avoid an immediate second API request (which is also where
    429 rate limits often appear).
    """
    try:
        data = response.json()
    except Exception:
        return None

    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return None

    failed = error.get("failed_generation")
    if not failed:
        return None

    try:
        payload = json.loads(str(failed))
        normalized = _normalize_editorial_payload(payload, candidate_lookup)
        return EditorialResponse.model_validate(normalized)
    except Exception:
        return None


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

        impact_line = str(item.get("impact_line") or item.get("why_it_matters") or "").strip()
        if not impact_line:
            continue
        what_to_watch = item.get("what_to_watch") or "Watch for the next official update."
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.65

        normalized_stories.append(
            {
                "cluster_id": cluster_id,
                "priority": int(priority),
                "headline": item.get("headline") or base_feed.headline,
                "impact_line": impact_line,
                "category": category,
                "impact_labels": impact_labels,
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
