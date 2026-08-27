from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.agents.editorial import (
    MAX_SHORT_PASS_ATTEMPTS,
    ClusterEditorialCandidate,
    EditorialError,
    EditorialResponse,
    EditorialStory,
    _log_thin_admissions,
    _normalize_editorial_payload,
    build_editorial_user_prompt,
    merge_editorial_story,
    review_with_short_pass_retries,
)
from src.agents.editorial_gemini import GeminiMorningBriefService, _gemini_response_schema
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


def test_editorial_candidate_prompt_uses_publisher_timestamps():
    """The feed states the date directly; the old skew guessing is gone (I-6)."""
    candidate = _build_candidate()
    row = candidate.to_prompt_dict()

    assert row["latest_publish_date"] is not None
    assert row["earliest_publish_date"] is not None
    assert "suspicious_publish_dates" not in row


def test_editorial_user_prompt_describes_the_range_as_typical_not_required():
    prompt = json.loads(build_editorial_user_prompt([{"cluster_id": "abc"}], max_stories=12))
    rules = prompt["selection_rules"]

    # Floor 6, not 10. An ordinary Pakistani news day does not hold ten stories
    # that change something for someone; a heavy one can hold twelve.
    assert prompt["typical_story_range"] == {"min": 6, "max": 12}
    # The range is a description of a full news day, not a quota to reach: the
    # old "aim for at least ten" wording pushed the editor into the weak tail.
    assert any("not a quota" in rule for rule in rules)
    assert any("never pad the count" in rule for rule in rules)


def test_editorial_user_prompt_floor_never_exceeds_the_cap():
    prompt = json.loads(build_editorial_user_prompt([{"cluster_id": "abc"}], max_stories=4))

    assert prompt["typical_story_range"] == {"min": 4, "max": 4}


def test_editorial_user_prompt_forbids_restating_the_headline():
    """The impact line is the product's middle third; a summary is not one."""
    rules = json.loads(build_editorial_user_prompt([{"cluster_id": "abc"}], max_stories=12))["selection_rules"]

    assert any("never restate the headline" in rule for rule in rules)
    assert any("name the people" in rule for rule in rules)
    # Syndication is not importance: a ministry press release every publisher
    # reprinted is still a card with no reader in it.
    assert any("Syndication is not importance" in rule for rule in rules)
    assert any("routine" in rule for rule in rules)
    assert any("evidence.pk_relevance" in rule for rule in rules)
    # publisher_topline_score scored a food-inspection drive above a national
    # story on the live run, so it is a tiebreak now, not a strong signal.
    assert any("only to break a tie" in rule for rule in rules)


def test_editorial_prompt_carries_the_candidate_evidence():
    """CandidateEvidence was written to metadata and shown to nobody."""
    candidate = _build_candidate()
    candidate.base_feed.metadata = dict(candidate.base_feed.metadata or {})
    candidate.base_feed.metadata["evidence"] = {
        "source_count": 6,
        "story_type": "routine",
        "pk_relevance": "national",
        "hours_since_latest": 2.5,
    }

    row = candidate.to_prompt_dict()

    assert row["evidence"]["source_count"] == 6
    assert row["evidence"]["story_type"] == "routine"
    assert "deterministic_publish_score" not in row, "dead since the publish score was deleted"


def test_compact_prompt_keeps_only_the_evidence_the_editor_decides_on():
    """Thirty full evidence blocks pushed the Groq payload past its limit."""
    candidate = _build_candidate()
    candidate.base_feed.metadata = dict(candidate.base_feed.metadata or {})
    candidate.base_feed.metadata["evidence"] = {
        "source_count": 3,
        "prominence_score": 22,
        "bucket_score": 7,
        "triage_confidence": 0.82,
        "story_type": "hard_news",
        "pk_relevance": "national",
        "hours_since_latest": 3.2,
    }

    full = candidate.to_prompt_dict()
    compact = candidate.to_prompt_dict(compact=True)

    assert set(compact["evidence"]) == {
        "source_count",
        "story_type",
        "pk_relevance",
        "hours_since_latest",
    }
    assert compact["evidence"]["pk_relevance"] == "national"
    assert full["evidence"]["prominence_score"] == 22
    assert "avg_similarity" in full and "avg_similarity" not in compact
    assert len(json.dumps(compact)) < len(json.dumps(full))


def test_json_object_mode_accepts_a_bare_story_array():
    """A live run lost a whole editorial pass to a top-level list payload."""
    candidate = _build_candidate()
    lookup = {str(candidate.cluster_id): candidate}
    payload = [
        {
            "cluster_id": str(candidate.cluster_id),
            "priority": 88,
            "headline": "A clear headline about a real Pakistani development today",
            "impact_line": "Commuters on the Peshawar northern bypass lose the bridge from today.",
            "category": "city",
            "impact_labels": ["\U0001f6a6 COMMUTE"],
            "what_to_watch": "Watch for the reopening date the NHA gives.",
            "public_impact": "high",
            "story_tags": ["peshawar"],
            "confidence": 0.9,
            "selection_reason": "Selected for direct commuter impact.",
        }
    ]

    normalized = _normalize_editorial_payload(payload, lookup)

    assert len(normalized["stories"]) == 1


def test_editorial_prompt_evidence_defaults_to_empty():
    row = _build_candidate().to_prompt_dict()

    assert row["evidence"] == {}




# ---------------------------------------------------------------------------
# The short-pass retry, tested against the shared helper rather than a
# provider. It is the collapse guard that replaced padding the brief with
# template cards, so it must hold whichever model is writing.
# ---------------------------------------------------------------------------


def _story_payload(cluster_id: str, *, priority: int = 90, **overrides) -> dict:
    payload = {
        "cluster_id": cluster_id,
        "priority": priority,
        "headline": "A clear headline about a real Pakistani development today",
        "impact_line": "Drivers pay 20 percent more on the Swat Expressway from today.",
        "category": "economy",
        "impact_labels": ["\U0001f4b3 WALLET"],
        "what_to_watch": "Watch the toll notification due on Thursday.",
        "public_impact": "high",
        "story_tags": ["pakistan"],
        "confidence": 0.9,
        "selection_reason": "Selected for national relevance.",
    }
    payload.update(overrides)
    return payload


def _editor_returning(counts):
    """A fake editor yielding `counts[i]` stories on the i-th attempt."""
    windows = []

    def review_once(candidates):
        take = counts[min(len(windows), len(counts) - 1)]
        windows.append(len(candidates))
        stories = [
            _story_payload(str(candidate.cluster_id), priority=90 - index)
            for index, candidate in enumerate(candidates[:take])
        ]
        return EditorialResponse.model_validate({"stories": stories, "omitted_cluster_ids": []})

    return review_once, windows


def test_a_collapsed_pass_is_retried_against_deeper_candidates():
    """A rejected top-of-list is exactly when the editor needs to see further down."""
    candidates = [_build_candidate() for _ in range(30)]
    review_once, windows = _editor_returning([1, 1, 12])

    result = review_with_short_pass_retries(review_once, candidates, max_stories=12)

    assert windows == [18, 26, 30], "each retry looks deeper into the ranked candidates"
    assert windows[0] > 12, "the first pass must see more candidates than the story cap"
    assert len(result) == 12


def test_a_confident_short_brief_costs_one_call():
    """Seven stories the editor stands behind is an answer, not a short pass.

    The retry floor used to be ten, so a brief the editor deliberately kept
    short was retried against deeper candidates until the count was reached.
    That is how licence tallies and inspection drives got into the brief.
    """
    candidates = [_build_candidate() for _ in range(30)]
    review_once, windows = _editor_returning([7])

    result = review_with_short_pass_retries(review_once, candidates, max_stories=12)

    assert len(windows) == 1, "a deliberately short brief is not retried into the weak tail"
    assert len(result) == 7


def test_a_full_brief_on_the_first_pass_costs_one_call():
    candidates = [_build_candidate() for _ in range(30)]
    review_once, windows = _editor_returning([12])

    result = review_with_short_pass_retries(review_once, candidates, max_stories=12)

    assert len(windows) == 1
    assert len(result) == 12


def test_the_editor_ships_what_it_produced_rather_than_failing():
    """After the retries, what the editor produced is the brief."""
    candidates = [_build_candidate() for _ in range(30)]
    review_once, windows = _editor_returning([1])

    result = review_with_short_pass_retries(review_once, candidates, max_stories=12)

    assert len(windows) == MAX_SHORT_PASS_ATTEMPTS
    assert len(result) == 1


def test_a_provider_error_on_every_attempt_is_raised_not_swallowed():
    candidates = [_build_candidate() for _ in range(30)]

    def review_once(_candidates):
        raise EditorialError("provider unreachable")

    with pytest.raises(EditorialError, match="provider unreachable"):
        review_with_short_pass_retries(review_once, candidates, max_stories=12)


def test_a_story_without_what_to_watch_keeps_its_card_and_loses_the_line():
    """Optional, and never templated.

    A missing watch line used to become "Watch for the next official update."
    - template copy in an LLM-written brief - and then dropped the whole story
    instead, which was too far the other way. Measured on a live brief, 6 of 7
    of these lines only said that something else would happen later. A story
    with nothing real to watch keeps its card and loses the line.
    """
    candidate = _build_candidate()
    lookup = {str(candidate.cluster_id): candidate}
    payload = {
        "stories": [
            {k: v for k, v in _story_payload(str(candidate.cluster_id)).items() if k != "what_to_watch"}
        ]
    }

    normalized = _normalize_editorial_payload(payload, lookup)

    assert len(normalized["stories"]) == 1
    assert normalized["stories"][0]["what_to_watch"] == ""
    assert normalized["stories"][0]["impact_line"]


def test_a_missing_impact_line_still_drops_the_story():
    """The impact line is the card's reason to exist; the watch line is not."""
    candidate = _build_candidate()
    lookup = {str(candidate.cluster_id): candidate}
    payload = {
        "stories": [
            {k: v for k, v in _story_payload(str(candidate.cluster_id)).items() if k != "impact_line"}
        ]
    }

    assert _normalize_editorial_payload(payload, lookup)["stories"] == []


def test_the_editorial_response_schema_is_one_gemini_accepts():
    """A live run lost the whole editorial pass to a bare 400 INVALID_ARGUMENT.

    The cause was an `enum` inside `impact_labels.items`. Gemini accepts the
    identical construct in the smaller triage schema and accepts the `category`
    and `public_impact` enums here, so the limit is this schema's size. The
    allowed labels moved into the user prompt; the validator still rejects
    anything outside the set.
    """
    from src.agents.editorial import VALID_CATEGORIES, VALID_IMPACT_LABELS
    from src.agents.editorial_gemini import _gemini_response_schema

    props = _gemini_response_schema(EditorialResponse)["$defs"]["EditorialStory"]["properties"]

    assert props["category"]["enum"] == list(VALID_CATEGORIES)
    assert props["public_impact"]["enum"] == ["high", "medium", "watch"]
    assert "enum" not in props["impact_labels"]["items"]

    prompt = json.loads(build_editorial_user_prompt([{"cluster_id": "abc"}], max_stories=12))
    assert prompt["allowed_impact_labels"] == list(VALID_IMPACT_LABELS)
    assert prompt["allowed_categories"] == list(VALID_CATEGORIES)

    with pytest.raises(ValidationError):
        EditorialStory(
            cluster_id="abc",
            priority=80,
            headline="A clear headline about a real Pakistani development today",
            impact_line="Drivers pay 20 percent more on the Swat Expressway from today.",
            category="economy",
            impact_labels=["NOT A LABEL"],
            what_to_watch="Watch the toll notification due on Thursday.",
            public_impact="high",
            story_tags=["pakistan"],
            confidence=0.9,
            selection_reason="Selected for national relevance.",
        )


def _evidence_candidate(source_count: int, relevance: str, headline: str) -> ClusterEditorialCandidate:
    candidate = _build_candidate()
    candidate.base_feed.headline = headline
    candidate.base_feed.metadata = {
        "evidence": {"source_count": source_count, "pk_relevance": relevance}
    }
    return candidate


def test_thin_admission_accounting_reports_only_thin_cards(caplog):
    """A warning that fires on every card is noise, not accounting.

    Comparing each published card against the single best-corroborated dropped
    candidate warned on 8 of 8 cards in a live run, burying the one line worth
    reading. Only a card below the corroboration floor is reported.
    """
    thin = _evidence_candidate(2, "national", "SC upholds Rs30m penalty on ghee association")
    strong = _evidence_candidate(5, "national", "Fourteen newborns killed in hospital fire")
    dropped = _evidence_candidate(7, "national", "Pakistan and Kuwait reaffirm defence ties")
    published = {thin.cluster_id: None, strong.cluster_id: None}

    with caplog.at_level("WARNING", logger="src.agents.editorial"):
        _log_thin_admissions([thin, strong, dropped], published)

    warnings = [record.getMessage() for record in caplog.records]
    assert len(warnings) == 1
    assert "ghee association" in warnings[0]
    assert "Kuwait" in warnings[0]


def test_thin_admission_accounting_is_silent_when_nothing_national_was_dropped(caplog):
    thin = _evidence_candidate(2, "national", "SC upholds Rs30m penalty on ghee association")
    foreign = _evidence_candidate(7, "foreign", "Flooding in Nepal kills hundreds")

    with caplog.at_level("WARNING", logger="src.agents.editorial"):
        _log_thin_admissions([thin, foreign], {thin.cluster_id: None})

    assert not [r for r in caplog.records if "published a" in r.getMessage()]
