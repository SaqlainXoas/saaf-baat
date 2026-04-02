from __future__ import annotations

import json
from uuid import uuid4

import httpx

from src.agents.editorial import (
    ClusterEditorialCandidate,
    EditorialStory,
    GroqMorningBriefService,
    merge_editorial_story,
)
from src.db.models import AnalyzedFeed, RawArticle


def _build_candidate() -> ClusterEditorialCandidate:
    cluster_id = uuid4()
    article = RawArticle(
        source="dawn",
        url="https://example.com/story",
        headline="Government weighs fuel subsidy changes",
        main_text=("Pakistan fuel subsidy budget IMF " * 30),
        embedding=[1.0, 0.0, 0.0],
    )
    feed = AnalyzedFeed(
        cluster_id=cluster_id,
        headline=article.headline,
        summary="Deterministic summary",
        category="economy",
        impact_labels=["💳 WALLET"],
        source_attribution={"dawn": 1},
    )
    return ClusterEditorialCandidate(
        cluster_id=cluster_id,
        base_feed=feed,
        representative_article=article,
        articles=(article,),
        algorithm_used="singleton",
        avg_similarity=1.0,
        min_member_similarity=1.0,
    )


def test_groq_editorial_service_parses_structured_response():
    candidate = _build_candidate()
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "stories": [
                                {
                                    "cluster_id": str(candidate.cluster_id),
                                    "priority": 88,
                                    "headline": "Fuel subsidy fight moves back to centre-stage",
                                    "summary": "The government is weighing fuel-subsidy changes while dealing with IMF pressure and rising costs. The decision could quickly affect household budgets and transport expenses.",
                                    "category": "economy",
                                    "impact_labels": ["💳 WALLET", "🏛️ GOVERNANCE"],
                                    "why_it_matters": "Fuel pricing decisions can directly change household costs and business expenses.",
                                    "what_to_watch": "Watch for a final decision from the finance ministry and any IMF-linked revision.",
                                    "public_impact": "high",
                                    "story_tags": ["fuel", "subsidy", "imf"],
                                    "confidence": 0.86,
                                    "selection_reason": "High public impact with direct consumer cost implications.",
                                }
                            ],
                            "omitted_cluster_ids": [],
                        }
                    )
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.groq.com/openai/v1/chat/completions")
        body = json.loads(request.content.decode("utf-8"))
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(200, json=response_payload)

    service = GroqMorningBriefService(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = service.review_clusters([candidate], max_stories=5)

    assert candidate.cluster_id in result
    assert result[candidate.cluster_id].priority == 88
    assert result[candidate.cluster_id].category == "economy"


def test_merge_editorial_story_overrides_card_fields_and_sets_metadata():
    candidate = _build_candidate()
    story = EditorialStory(
        cluster_id=str(candidate.cluster_id),
        priority=91,
        headline="Centre weighs new fuel move",
        summary="Officials are revisiting fuel pricing and subsidy options amid budget pressure. Any move could affect transport and household costs quickly.",
        category="economy",
        impact_labels=["💳 WALLET"],
        why_it_matters="Fuel pricing quickly passes through to consumers and businesses.",
        what_to_watch="Watch for a cabinet or finance ministry announcement.",
        public_impact="high",
        story_tags=["fuel", "budget"],
        confidence=0.84,
        selection_reason="Clear household cost impact.",
    )

    merged = merge_editorial_story(candidate, story, model_name="openai/gpt-oss-120b")

    assert merged.headline == "Centre weighs new fuel move"
    assert merged.summary.startswith("Officials are revisiting fuel pricing")
    assert merged.metadata["editorial_model"] == "openai/gpt-oss-120b"
    assert merged.metadata["editorial_priority"] == 91
    assert merged.metadata["llm_augmented"] is True
