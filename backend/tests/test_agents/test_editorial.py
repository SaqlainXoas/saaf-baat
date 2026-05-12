from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

from src.agents.editorial import (
    ClusterEditorialCandidate,
    EditorialStory,
    EditorialResponse,
    GroqMorningBriefService,
    build_editorial_user_prompt,
    merge_editorial_story,
)
from src.agents.editorial_gemini import GeminiMorningBriefService, _gemini_response_schema
from src.agents.editorial_router import EditorialRouterService
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
                                    "impact_line": "Fuel pricing decisions can directly change household costs and business expenses.",
                                    "category": "economy",
                                    "impact_labels": ["💳 WALLET", "🏛️ GOVERNANCE"],
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
        schema = body["response_format"]["json_schema"]["schema"]
        assert set(schema["required"]) == set(schema["properties"].keys())
        # Nested object schemas should also follow the same rule.
        story_schema = schema["properties"]["stories"]["items"]
        if "$ref" in story_schema:
            ref = story_schema["$ref"]
            assert ref.startswith("#/$defs/")
            def_name = ref.split("/")[-1]
            story_schema = schema["$defs"][def_name]
        assert set(story_schema["required"]) == set(story_schema["properties"].keys())
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
        impact_line="Fuel pricing quickly passes through to consumers and businesses.",
        category="economy",
        impact_labels=["💳 WALLET"],
        what_to_watch="Watch for a cabinet or finance ministry announcement.",
        public_impact="high",
        story_tags=["fuel", "budget"],
        confidence=0.84,
        selection_reason="Clear household cost impact.",
    )

    merged = merge_editorial_story(candidate, story, model_name="openai/gpt-oss-120b")

    assert merged.headline == "Centre weighs new fuel move"
    assert merged.summary == "Deterministic summary"
    assert merged.metadata["editorial_model"] == "openai/gpt-oss-120b"
    assert merged.metadata["editorial_priority"] == 91
    assert merged.metadata["llm_augmented"] is True


def test_groq_strict_400_with_failed_generation_is_salvaged_without_fallback_call():
    candidate = _build_candidate()

    # Simulate Groq strict-mode 400 that still contains a usable JSON generation
    # (but missing omitted_cluster_ids, which strict schema requires).
    failed_generation = {
        "stories": [
            {
                "cluster_id": str(candidate.cluster_id),
                "priority": 88,
                "headline": "Fuel subsidy fight moves back to centre-stage",
                "impact_line": "Fuel pricing decisions can directly change household costs and business expenses.",
                "category": "economy",
                "impact_labels": ["💳 WALLET", "🏛️ GOVERNANCE"],
                "what_to_watch": "Watch for a final decision from the finance ministry and any IMF-linked revision.",
                "public_impact": "high",
                "story_tags": ["fuel", "subsidy", "imf"],
                "confidence": 0.86,
                "selection_reason": "High public impact with direct consumer cost implications.",
            }
        ]
    }

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        calls.append(body)
        # First call is strict schema request; return 400 with failed_generation.
        if len(calls) == 1:
            assert body["response_format"]["json_schema"]["strict"] is True
            return httpx.Response(
                400,
                json={"error": {"message": "schema mismatch", "failed_generation": json.dumps(failed_generation)}},
            )
        # If we ever hit fallback, the test should fail.
        raise AssertionError("Expected salvage without fallback request")

    service = GroqMorningBriefService(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = service.review_clusters([candidate], max_stories=5)

    assert len(calls) == 1
    assert candidate.cluster_id in result


def test_gemini_editorial_service_uses_application_json_schema_config_and_parses():
    candidate = _build_candidate()
    expected = {
        "stories": [
            {
                "cluster_id": str(candidate.cluster_id),
                "priority": 80,
                "headline": "Fuel subsidy fight moves back to centre-stage",
                "impact_line": "Fuel pricing shifts pass through to households and businesses.",
                "category": "economy",
                "impact_labels": ["💳 WALLET"],
                "what_to_watch": "Watch for a finance ministry decision and any IMF-linked revision.",
                "public_impact": "high",
                "story_tags": ["fuel", "subsidy"],
                "confidence": 0.8,
                "selection_reason": "Direct cost-of-living impact.",
            }
        ],
        "omitted_cluster_ids": [],
    }

    class _FakeResponse:
        def __init__(self, text: str):
            self.text = text

    class _FakeModels:
        def __init__(self):
            self.last = None

        def generate_content(self, *, model: str, contents: object, config: dict) -> _FakeResponse:
            self.last = {"model": model, "contents": contents, "config": config}
            return _FakeResponse(json.dumps(expected))

    class _FakeClient:
        def __init__(self):
            self.models = _FakeModels()

    fake_client = _FakeClient()
    service = GeminiMorningBriefService(api_key="test-key", model="gemini-3.1-flash-lite-preview", client=fake_client)
    result = service.review_clusters([candidate], max_stories=5)

    assert candidate.cluster_id in result
    assert fake_client.models.last["config"]["response_mime_type"] == "application/json"
    schema = fake_client.models.last["config"]["response_schema"]
    assert schema["type"] == "object"
    assert "additionalProperties" not in json.dumps(schema)


def test_gemini_editorial_service_uses_parsed_response_when_available():
    candidate = _build_candidate()
    parsed = {
        "stories": [
            {
                "cluster_id": str(candidate.cluster_id),
                "priority": 77,
                "headline": "Parsed editorial headline",
                "impact_line": "Fuel costs matter to households.",
                "category": "economy",
                "impact_labels": ["💳 WALLET"],
                "what_to_watch": "Watch for the final policy decision.",
                "public_impact": "high",
                "story_tags": ["fuel"],
                "confidence": 0.77,
                "selection_reason": "Parsed branch coverage.",
            }
        ],
        "omitted_cluster_ids": [],
    }

    class _FakeResponse:
        def __init__(self):
            from src.agents.editorial import EditorialResponse

            self.parsed = EditorialResponse.model_validate(parsed)
            self.text = ""

    class _FakeModels:
        def generate_content(self, *, model: str, contents: object, config: dict) -> _FakeResponse:
            return _FakeResponse()

    class _FakeClient:
        def __init__(self):
            self.models = _FakeModels()

    service = GeminiMorningBriefService(api_key="test-key", client=_FakeClient())
    result = service.review_clusters([candidate], max_stories=5)

    assert result[candidate.cluster_id].headline == "Parsed editorial headline"


def test_gemini_response_schema_strips_additional_properties_for_sdk_compatibility():
    editorial_schema = _gemini_response_schema(EditorialResponse)
    dumped = json.dumps(editorial_schema)
    assert "additionalProperties" not in dumped


def test_editorial_candidate_prompt_uses_trusted_timestamps_and_flags_suspicious_publish_dates():
    cluster_id = uuid4()
    now = datetime.now(timezone.utc)
    article = RawArticle(
        source="dawn",
        url="https://example.com/stale-story",
        headline="Heavy rain disrupts highway traffic",
        main_text=("rain highway traffic emergency " * 30),
        publish_date=now - timedelta(days=400),
        scraped_at=now,
        embedding=[1.0, 0.0, 0.0],
    )
    feed = AnalyzedFeed(
        cluster_id=cluster_id,
        headline=article.headline,
        summary="Deterministic summary",
        category="city",
        impact_labels=["🚦 COMMUTE"],
        source_attribution={"dawn": 1},
    )
    candidate = ClusterEditorialCandidate(
        cluster_id=cluster_id,
        base_feed=feed,
        representative_article=article,
        articles=(article,),
        algorithm_used="singleton",
        avg_similarity=1.0,
        min_member_similarity=1.0,
    )

    prompt_row = candidate.to_prompt_dict()

    assert prompt_row["latest_publish_date"] == now.isoformat()
    assert prompt_row["earliest_publish_date"] == now.isoformat()
    assert prompt_row["suspicious_publish_dates"] == 1


def test_editorial_user_prompt_targets_five_to_nine_when_cap_allows():
    prompt = json.loads(build_editorial_user_prompt([{"cluster_id": "abc"}], max_stories=9))

    assert prompt["target_story_range"] == {"min": 5, "max": 9}
    assert any("Aim to return at least target_story_range.min stories" in rule for rule in prompt["selection_rules"])


def test_editorial_router_uses_gemini_first_then_groq_on_failure():
    candidate = _build_candidate()

    class _GeminiStub:
        model = "gemini-3.1-flash-lite-preview"

        def review_clusters(self, candidates, *, max_stories: int = 9):
            raise RuntimeError("gemini down")

    class _GroqStub:
        model = "openai/gpt-oss-120b"

        def review_clusters(self, candidates, *, max_stories: int = 9):
            return {candidates[0].cluster_id: EditorialStory(**{
                "cluster_id": str(candidates[0].cluster_id),
                "priority": 70,
                "headline": "Fallback headline",
                "impact_line": "Matters because it hits wallets.",
                "category": "economy",
                "impact_labels": ["💳 WALLET"],
                "what_to_watch": "Watch for the official update.",
                "public_impact": "high",
                "story_tags": ["fallback"],
                "confidence": 0.7,
                "selection_reason": "Fallback selection.",
            })}

    router = EditorialRouterService(gemini=_GeminiStub(), groq=_GroqStub())
    out = router.review_clusters([candidate], max_stories=5)
    assert candidate.cluster_id in out
    assert router.model == "openai/gpt-oss-120b"
