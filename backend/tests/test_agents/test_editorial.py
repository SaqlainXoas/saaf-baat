from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.agents.editorial import (
    MAX_SHORT_PASS_ATTEMPTS,
    ClusterEditorialCandidate,
    EditorialError,
    EditorialResponse,
    EditorialStory,
    _derive_what_to_watch,
    _log_thin_admissions,
    _normalize_editorial_payload,
    _stories_by_cluster_id,
    build_editorial_user_prompt,
    merge_editorial_story,
    review_with_short_pass_retries,
)
from src.agents.editorial_gemini import GeminiMorningBriefService, _gemini_response_schema
from src.agents.rate_limit import is_retryable_message
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


@pytest.mark.parametrize(
    ("evidence", "headline", "impact"),
    [
        (
            "The Green Certificate system was suspended pending review.",
            "Punjab suspends Green Certificate system",
            "Property buyers face a six-month halt in transactions from today.",
        ),
        (
            "Punjab ordered fire safety audits at government hospitals.",
            "Punjab orders hospital fire safety audits",
            "Patients face service disruptions while the hospital audits continue.",
        ),
        (
            "The minister called for a uniform gas policy and proposed ending categories.",
            "Government moves to replace household gas categories",
            "Households must track a proposed change to gas categories.",
        ),
    ],
)
def test_editorial_gate_rejects_unsupported_consequences(evidence, headline, impact):
    candidate = _build_candidate()
    candidate.representative_article.headline = headline
    candidate.representative_article.main_text = evidence
    candidate.base_feed.headline = headline
    story = EditorialStory(
        cluster_id=str(candidate.cluster_id),
        priority=80,
        headline=headline,
        impact_line=impact,
        category="economy",
        impact_labels=["💳 WALLET"],
        public_impact="high",
        story_tags=["policy"],
        confidence=0.8,
        selection_reason="Direct reported public impact.",
    )

    accepted, rejected = _stories_by_cluster_id(
        EditorialResponse(stories=[story]), [candidate]
    )
    assert accepted == {}
    assert rejected == {candidate.cluster_id}


def test_merge_repairs_truncated_unit_and_derives_concrete_watch_date():
    candidate = _build_candidate()
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)
    candidate.representative_article.headline = (
        "Government cuts diesel price by 19 paise before September 3 strike"
    )
    candidate.representative_article.main_text = (
        "Diesel was cut by 19 paise. Transporters scheduled a nationwide strike for September 3."
    )
    story = EditorialStory(
        cluster_id=str(candidate.cluster_id),
        priority=90,
        headline="Government cuts diesel by 19",
        impact_line="Drivers pay the newly reported diesel price from today.",
        category="economy",
        impact_labels=["💳 WALLET"],
        public_impact="high",
        story_tags=["fuel"],
        confidence=0.9,
        selection_reason="A direct change in transport costs.",
    )

    merged = merge_editorial_story(candidate, story, model_name="test-model")

    assert merged.headline == "Government cuts diesel by 19 paise"
    assert merged.metadata["what_to_watch"] == "The strike is scheduled for September 3."


def test_what_to_watch_does_not_resurface_a_past_event_date():
    candidate = _build_candidate()
    candidate.representative_article.publish_date = datetime(2026, 8, 29, tzinfo=timezone.utc)
    candidate.representative_article.main_text = (
        "The election was held on August 24 and the new prime minister has taken oath."
    )

    assert _derive_what_to_watch(None, candidate) == ""
    assert (
        _derive_what_to_watch("The election is scheduled for August 24.", candidate)
        == ""
    )


def test_what_to_watch_rejects_a_subjectless_sentence():
    """Regression: a live PSX card shipped 'The meeting is scheduled for
    September 16.' - a bare event and date with no one named. The source
    sentence that produced it never named who called the meeting or what it
    was about, so it must be rejected rather than templated as-is.
    """
    candidate = _build_candidate()
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)
    candidate.representative_article.main_text = (
        "Selling pressure hit the market today. The meeting is scheduled for September 16."
    )

    assert _derive_what_to_watch(None, candidate) == ""


def test_what_to_watch_rejects_a_subject_unrelated_to_the_story():
    """Regression: a live PSX card's watch line was lifted from a sentence
    about a U.S. Federal Reserve rate decision, cited only as market-context
    boilerplate inside the PSX article. It named a real subject ("CME"), and
    the naive '.' splitter used to cut the sentence right after "U.S." - but
    neither should be enough, because nothing in it is about this story.
    """
    candidate = _build_candidate()
    candidate.base_feed.headline = "Pakistan Stock Exchange sheds over 1,000 points"
    candidate.representative_article.headline = "PSX: Stocks shed over 1,000 points in"
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)
    candidate.representative_article.main_text = (
        "Selling pressure hit the market. Fed funds futures are pricing an implied "
        "67% probability of a 25-basis-point increase in benchmark borrowing costs "
        "at the U.S. central bank's two-day meeting ending on September 16, compared "
        "to a 39.6% chance a week ago, according to the CME Group's FedWatch tool."
    )

    assert _derive_what_to_watch(None, candidate) == ""


def test_what_to_watch_accepts_a_sentence_naming_a_subject():
    candidate = _build_candidate()
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)
    candidate.representative_article.main_text = (
        "Selling pressure hit the market today. "
        "The Petroleum Division holds a subsidy review meeting on September 16."
    )

    assert (
        _derive_what_to_watch(None, candidate)
        == "The meeting is scheduled for September 16."
    )


def test_a_model_supplied_bare_date_is_not_a_watch_line():
    """Regression: a live card rendered 'What to watch: October 27'.

    The model-supplied path only checked that the date had not already passed,
    so a string naming nobody and nothing shipped verbatim - while the derived
    path beside it had required a subject all along.
    """
    candidate = _build_candidate()
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)

    assert _derive_what_to_watch("October 27", candidate) == ""


def test_a_model_supplied_line_must_still_be_about_this_story():
    candidate = _build_candidate()
    candidate.base_feed.headline = "Pakistan Stock Exchange sheds over 1,000 points"
    candidate.representative_article.headline = "PSX: Stocks shed over 1,000 points in"
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)

    assert (
        _derive_what_to_watch(
            "The CME Group publishes its FedWatch revision on September 16.", candidate
        )
        == ""
    )


def test_a_model_supplied_line_that_only_repeats_the_card_is_dropped():
    """The same date appeared in the headline, the impact line and here."""
    candidate = _build_candidate()
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)

    assert (
        _derive_what_to_watch(
            "PIA increases flights from October 27.",
            candidate,
            already_said=(
                "PIA increases weekly flights to London to seven from October 27. "
                "Travelers gain more scheduling options as PIA increases its flights."
            ),
        )
        == ""
    )


def test_a_model_supplied_line_that_adds_a_real_next_step_survives():
    candidate = _build_candidate()
    candidate.representative_article.publish_date = datetime(2026, 9, 2, tzinfo=timezone.utc)
    line = "The Petroleum Division reviews the fuel subsidy on September 16."

    assert (
        _derive_what_to_watch(
            line, candidate, already_said="Government weighs changes to pump prices"
        )
        == line
    )


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
        "impact_line": "Drivers pay a newly notified toll on the Swat Expressway from today.",
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


def test_a_five_card_pass_gets_deeper_replacement_opportunity():
    candidates = [_build_candidate() for _ in range(30)]
    review_once, windows = _editor_returning([5, 5, 6])

    result = review_with_short_pass_retries(review_once, candidates, max_stories=12)

    assert windows == [18, 26, 30]
    assert len(result) == 6


def test_a_grounding_rejected_cluster_is_not_re_offered_on_retry():
    """Regression: a live run repeatedly re-proposed and re-rejected the same
    ungrounded cluster across retry attempts, spending retry budget on a
    rejection instead of a candidate the editor hadn't judged yet.
    """
    candidates = [_build_candidate() for _ in range(30)]
    bad_id = candidates[0].cluster_id
    seen_candidate_ids = []

    def review_once(prompt_candidates):
        seen_candidate_ids.append([c.cluster_id for c in prompt_candidates])
        stories = []
        if any(c.cluster_id == bad_id for c in prompt_candidates):
            stories.append(
                _story_payload(
                    str(bad_id),
                    priority=99,
                    impact_line="Officials say this may affect prices.",
                )
            )
        deepest = prompt_candidates[-1]
        stories.append(_story_payload(str(deepest.cluster_id), priority=50))
        return EditorialResponse.model_validate({"stories": stories, "omitted_cluster_ids": []})

    result = review_with_short_pass_retries(review_once, candidates, max_stories=12)

    assert len(seen_candidate_ids) == MAX_SHORT_PASS_ATTEMPTS
    assert bad_id in seen_candidate_ids[0]
    assert bad_id not in seen_candidate_ids[1]
    assert bad_id not in seen_candidate_ids[2]
    assert bad_id not in result
    assert set(result.keys()) == {candidates[17].cluster_id}


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


@pytest.mark.parametrize("impact", ["Workers receive the subsidy from May 2026.", "Workers receive the subsidy from 2 may 2026."])
def test_month_may_is_not_rejected_as_hedging(impact):
    candidate = _build_candidate()
    candidate.representative_article.main_text = impact
    story = EditorialStory.model_validate(_story_payload(str(candidate.cluster_id), impact_line=impact))
    accepted, rejected = _stories_by_cluster_id(EditorialResponse(stories=[story]), [candidate])
    assert candidate.cluster_id in accepted
    assert not rejected


class TestTransientProviderFailures:
    """A 503 means "ask again", not "ship what you have".

    On 2026-09-14 the editor's second pass got a bare 503 UNAVAILABLE. Nothing
    retried it - embeddings had had backoff since Phase 1, the editor never did
    - and the short-pass loop treated it as fatal, so the two attempts that
    remained were never made and the brief shipped the four cards the first
    pass had grounded.
    """

    @staticmethod
    def _candidates(n):
        return [_build_candidate() for _ in range(n)]

    @staticmethod
    def _response(candidates, count):
        return EditorialResponse(
            stories=[
                EditorialStory(
                    cluster_id=str(candidates[i].cluster_id),
                    priority=i + 1,
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
                for i in range(count)
            ]
        )

    def test_a_failed_attempt_does_not_abandon_the_rest(self):
        calls = []

        pool = self._candidates(30)

        def review_once(candidates):
            calls.append(len(candidates))
            if len(calls) == 1:
                return self._response(candidates, 4)
            if len(calls) == 2:
                raise EditorialError("Gemini editorial request failed: 503 UNAVAILABLE")
            return self._response(candidates, 7)

        result = review_with_short_pass_retries(review_once, pool, max_stories=12)

        assert len(calls) == 3, "the third window must still be tried after a 503"
        assert len(result) == 7

    def test_the_best_pass_survives_a_later_failure(self):
        pool = self._candidates(30)
        seen = []

        def review_once(candidates):
            if not seen:
                seen.append(True)
                return self._response(candidates, 3)
            raise EditorialError("503 UNAVAILABLE")

        result = review_with_short_pass_retries(review_once, pool, max_stories=12)

        assert len(result) == 3, "a later outage must not discard what was already grounded"

    def test_total_failure_still_raises(self):
        def review_once(candidates):
            raise EditorialError("Gemini editorial request failed: 401 unauthorised")

        with pytest.raises(EditorialError):
            review_with_short_pass_retries(review_once, self._candidates(30), max_stories=12)


class TestRetryableMessages:
    @pytest.mark.parametrize(
        "message",
        [
            "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The service is currently unavailable.'}}",
            "500 Internal error",
            "The model is overloaded. Please try again later.",
            "deadline exceeded",
        ],
    )
    def test_transient_server_errors_are_retryable(self, message):
        assert is_retryable_message(message) is True

    @pytest.mark.parametrize(
        "message",
        ["RESOURCE_EXHAUSTED", "429 rate limit exceeded", "quota exceeded for this project"],
    )
    def test_rate_limits_stay_retryable(self, message):
        assert is_retryable_message(message) is True

    @pytest.mark.parametrize(
        "message",
        ["401 unauthorised", "invalid api key", "response parsing failed"],
    )
    def test_real_failures_are_not_retried(self, message):
        assert is_retryable_message(message) is False


class TestRetryDelay:
    def test_a_busy_server_waits_longer_than_a_quota_refusal(self):
        from src.agents.rate_limit import retry_delay_seconds

        def no_jitter(_lo, _hi):
            return 0.0

        busy = [retry_delay_seconds("503 UNAVAILABLE", n, jitter=no_jitter) for n in range(4)]
        quota = [retry_delay_seconds("429 RESOURCE_EXHAUSTED", n, jitter=no_jitter) for n in range(4)]

        assert busy == [5.0, 15.0, 30.0, 60.0]
        assert quota == [2.0, 4.0, 8.0, 16.0]

    def test_the_servers_own_hint_wins(self):
        from src.agents.rate_limit import retry_delay_seconds

        assert retry_delay_seconds("429 quota. Please retry in 12.5s", 0) == 12.5

    def test_jitter_stays_inside_its_spread(self):
        from src.agents.rate_limit import retry_delay_seconds

        for _ in range(50):
            assert 5.0 <= retry_delay_seconds("503 UNAVAILABLE", 0) <= 8.0
