from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest

from src.agents.story_analysis import (
    QuestionBasis,
    StoryAnalysisClaim,
    StoryAnalysisResponse,
    StoryAnalysisValidationError,
    _contains_forbidden_conclusion,
    _distinctive_anchors,
    _evidence_tokens,
    _named_publishers,
    _proper_phrases_supported,
    _question_is_specific,
    _question_phrases,
    _tokens_supported,
    build_story_analysis_input,
    build_story_analysis_user_prompt,
    find_related_articles,
    select_primary_articles,
    validate_story_analysis,
)
from src.agents.story_analysis_gemini import GeminiStoryAnalysisService
from src.db.models import RawArticle


def _article(
    source: str,
    headline: str,
    text: str,
    *,
    cluster_id=None,
    body_status: str = "full",
    embedding=None,
) -> RawArticle:
    return RawArticle(
        id=uuid4(),
        source=source,
        url=f"https://example.com/{uuid4()}",
        headline=headline,
        main_text=text,
        cluster_id=cluster_id,
        publish_date=datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 5, 5, tzinfo=timezone.utc),
        embedding=list(embedding if embedding is not None else np.ones(8, dtype=np.float32)),
        metadata={"body_status": body_status},
    )


def _pims_input():
    primary_cluster = uuid4()
    primary = _article(
        "tribune",
        "14 newborns killed in fire at PIMS Hospital",
        "Fourteen newborns were killed when a fire broke out in the PIMS nursery.",
        cluster_id=primary_cluster,
        embedding=[1, 0, 0, 0, 0, 0, 0, 0],
    )
    safety = _article(
        "ary",
        "MCI report exposes fire safety violations at PIMS since 2018",
        "The MCI report recorded fire safety violations at PIMS since 2018 and closed entrances delayed rescue.",
        cluster_id=uuid4(),
        body_status="summary",
        embedding=[0.96, 0.1, 0, 0, 0, 0, 0, 0],
    )
    funding = _article(
        "nation",
        "PIMS receives Rs22bn in federal funding over three years",
        "PIMS received Rs22bn in federal funding over three years.",
        cluster_id=uuid4(),
        body_status="headline_only",
        embedding=[0.94, 0.2, 0, 0, 0, 0, 0, 0],
    )
    imran = _article(
        "geo",
        "Imran Khan taken to PIMS over security concerns",
        "Officials discussed Imran Khan's hospital transfer to PIMS.",
        cluster_id=uuid4(),
        embedding=[0.93, 0.25, 0, 0, 0, 0, 0, 0],
    )
    story_input = build_story_analysis_input(
        cluster_id=str(primary_cluster),
        selected_headline="PIMS nursery fire kills fourteen newborns",
        primary_articles=[primary],
        current_articles=[primary, safety, funding, imran],
    )
    return story_input, primary, safety, funding, imran


def test_primary_selection_prioritises_source_diversity_and_caps_each_publisher():
    articles = [
        _article("ary", f"PIMS report {index}", "PIMS fire report", cluster_id=uuid4())
        for index in range(5)
    ] + [
        _article("dawn", "PIMS Dawn report", "PIMS fire report", cluster_id=uuid4()),
        _article("geo", "PIMS Geo report", "PIMS fire report", cluster_id=uuid4()),
    ]

    selected = select_primary_articles(articles, max_articles=12, max_per_publisher=2)

    assert len([article for article in selected if article.source == "ary"]) == 2
    assert {article.source for article in selected} == {"ary", "dawn", "geo"}


def test_related_selection_requires_distinctive_anchor_and_respects_caps():
    story_input, primary, safety, funding, imran = _pims_input()
    unrelated = _article(
        "dawn",
        "Government reviews hospital policy",
        "A hospital policy was reviewed in Lahore.",
        cluster_id=uuid4(),
    )

    selected = find_related_articles(
        [primary],
        [primary, safety, funding, imran, unrelated],
        selected_headline="PIMS nursery fire kills fourteen newborns",
    )

    assert safety in selected
    assert funding in selected
    assert imran in selected  # A candidate only; the model must not cite it.
    assert unrelated not in selected
    assert len(story_input.related_articles) == 3


def test_related_selection_rejects_shared_titles_without_story_anchor():
    story_input, primary, *_ = _pims_input()
    unrelated = _article(
        "app",
        "President and PM express grief over floods in Nepal",
        "The president and prime minister expressed grief over flooding in Nepal.",
        cluster_id=uuid4(),
        embedding=[0.99, 0.01, 0, 0, 0, 0, 0, 0],
    )

    selected = find_related_articles(
        [primary],
        [primary, unrelated],
        selected_headline="PIMS nursery fire kills fourteen newborns",
    )

    assert unrelated not in selected


def test_prompt_labels_body_strength_and_publication_time_as_metadata():
    story_input, *_ = _pims_input()
    payload = json.loads(build_story_analysis_user_prompt(story_input))

    assert {row["role"] for row in payload["articles"]} == {
        "primary_event",
        "related_current_context",
    }
    assert {row["body_status"] for row in payload["articles"]} >= {
        "full",
        "summary",
        "headline_only",
    }
    assert all("article_publish_time_not_event_date" in row for row in payload["articles"])


def test_pims_validation_keeps_specific_supported_question_and_only_cited_context():
    story_input, primary, safety, funding, imran = _pims_input()
    response = StoryAnalysisResponse(
        analysis=(
            "Tribune reports that fourteen newborns died in a fire at PIMS. "
            "ARY reports fire-safety violations at PIMS since 2018 and closed entrances delayed rescue. "
            "Nation reports that PIMS received Rs22bn in federal funding over three years."
        ),
        question=(
            "Safety violations had been recorded since 2018 and PIMS received Rs22bn, yet closed "
            "entrances delayed rescue. Which office was responsible for acting on those findings?"
        ),
        question_basis=QuestionBasis.RESOURCES_VS_OUTCOME,
        claims=[
            StoryAnalysisClaim(
                text="Fourteen newborns died in a fire at PIMS.",
                supporting_article_ids=[str(primary.id)],
            ),
            StoryAnalysisClaim(
                text="Fire-safety violations at PIMS were recorded since 2018 and closed entrances delayed rescue.",
                supporting_article_ids=[str(safety.id)],
            ),
            StoryAnalysisClaim(
                text="PIMS received Rs22bn in federal funding over three years.",
                supporting_article_ids=[str(funding.id)],
            ),
        ],
        question_supporting_article_ids=[str(safety.id), str(funding.id)],
    )

    validated = validate_story_analysis(response, story_input)

    assert validated.status == "ok"
    assert validated.question is not None
    assert set(validated.related_article_ids) == {str(safety.id), str(funding.id)}
    assert str(imran.id) not in validated.related_article_ids


def test_generic_question_is_dropped_without_losing_analysis():
    story_input, primary, *_ = _pims_input()
    response = StoryAnalysisResponse(
        analysis="Tribune reports that fourteen newborns died in a fire at PIMS Hospital.",
        question="A public hospital exists to keep patients safe. Which office was responsible?",
        question_basis=QuestionBasis.RESPONSIBILITY_GAP,
        claims=[
            StoryAnalysisClaim(
                text="Fourteen newborns died in a fire at PIMS Hospital.",
                supporting_article_ids=[str(primary.id)],
            )
        ],
        question_supporting_article_ids=[str(primary.id)],
    )

    validated = validate_story_analysis(response, story_input)

    assert validated.analysis.startswith("Tribune reports")
    assert validated.question is None
    assert validated.status == "question_dropped"
    assert "generic_question" in validated.validation_errors


def test_single_source_analysis_requires_attribution_and_allows_null_question():
    article = _article("ary", "Government launches e-pension portal", "The government launched an e-pension portal.")
    story_input = build_story_analysis_input(
        cluster_id=str(uuid4()),
        selected_headline=article.headline,
        primary_articles=[article],
        current_articles=[article],
    )
    response = StoryAnalysisResponse(
        analysis="The government launched an e-pension portal for retired employees.",
        question=None,
        question_basis=QuestionBasis.NONE,
        claims=[
            StoryAnalysisClaim(
                text="The government launched an e-pension portal.",
                supporting_article_ids=[str(article.id)],
            )
        ],
    )

    with pytest.raises(StoryAnalysisValidationError, match="missing_single_source_attribution"):
        validate_story_analysis(response, story_input)

    attributed = response.model_copy(
        update={"analysis": "ARY reports that the government launched an e-pension portal for retired employees."}
    )
    assert validate_story_analysis(attributed, story_input).question is None


def test_publication_timestamp_cannot_supply_an_event_date():
    article = _article("dawn", "Cabinet approves relief package", "The cabinet approved a relief package.")
    story_input = build_story_analysis_input(
        cluster_id=str(uuid4()),
        selected_headline=article.headline,
        primary_articles=[article],
        current_articles=[article],
    )
    response = StoryAnalysisResponse(
        analysis="Dawn reports that the cabinet approved the package on August 27, 2026.",
        question=None,
        question_basis=QuestionBasis.NONE,
        claims=[
            StoryAnalysisClaim(
                text="The cabinet approved the package on August 27, 2026.",
                supporting_article_ids=[str(article.id)],
            )
        ],
    )

    with pytest.raises(StoryAnalysisValidationError, match="unsupported_number_or_date"):
        validate_story_analysis(response, story_input)


def test_equivalent_number_abbreviations_are_supported():
    article = _article(
        "ary",
        "SC upholds Rs30m penalty",
        "The court reduced the penalty from Rs50 million to Rs30 million.",
    )
    story_input = build_story_analysis_input(
        cluster_id=str(uuid4()),
        selected_headline=article.headline,
        primary_articles=[article],
        current_articles=[article],
    )
    response = StoryAnalysisResponse(
        analysis="ARY reports that the court upheld an Rs30m penalty.",
        question=None,
        question_basis=QuestionBasis.NONE,
        claims=[
            StoryAnalysisClaim(
                text="The court upheld an Rs30m penalty.",
                supporting_article_ids=[str(article.id)],
            )
        ],
    )

    assert validate_story_analysis(response, story_input).status == "ok"


def test_sentence_openers_are_not_treated_as_unsupported_names():
    story_input, _primary, safety, funding, _imran = _pims_input()
    response = StoryAnalysisResponse(
        analysis=(
            "ARY reports that closed entrances delayed rescue. "
            "Nation reports that PIMS received Rs22bn in funding."
        ),
        question=(
            "The reports describe closed entrances and Rs22bn in funding. "
            "Given these facts, which office was responsible for the safety audit?"
        ),
        question_basis=QuestionBasis.RESOURCES_VS_OUTCOME,
        claims=[
            StoryAnalysisClaim(
                text="Closed entrances delayed rescue.",
                supporting_article_ids=[str(safety.id)],
            ),
            StoryAnalysisClaim(
                text="PIMS received Rs22bn in funding.",
                supporting_article_ids=[str(funding.id)],
            ),
        ],
        question_supporting_article_ids=[str(safety.id), str(funding.id)],
    )

    assert validate_story_analysis(response, story_input).question is not None


def test_unsupported_accusation_is_rejected():
    story_input, primary, *_ = _pims_input()
    response = StoryAnalysisResponse(
        analysis="Tribune reports that fourteen newborns died in a fire at PIMS Hospital.",
        question="Why did corrupt officials ignore the warning?",
        question_basis=QuestionBasis.DOCUMENTED_WARNING,
        claims=[
            StoryAnalysisClaim(
                text="Fourteen newborns died in a fire at PIMS Hospital.",
                supporting_article_ids=[str(primary.id)],
            )
        ],
        question_supporting_article_ids=[str(primary.id)],
    )

    validated = validate_story_analysis(response, story_input)
    assert validated.question is None
    assert "unsupported_conclusion_in_question" in validated.validation_errors


def test_gemini_service_retries_once_and_parses_structured_response():
    story_input, primary, *_ = _pims_input()
    parsed = StoryAnalysisResponse(
        analysis="Tribune reports that fourteen newborns died in a fire at PIMS Hospital.",
        question=None,
        question_basis=QuestionBasis.NONE,
        claims=[
            StoryAnalysisClaim(
                text="Fourteen newborns died in a fire at PIMS Hospital.",
                supporting_article_ids=[str(primary.id)],
            )
        ],
    )

    class _Models:
        calls = 0

        def generate_content(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary provider failure")
            return SimpleNamespace(parsed=parsed, text=None)

    models = _Models()
    service = GeminiStoryAnalysisService(
        api_key="test",
        client=SimpleNamespace(models=models),
        sleep=lambda _seconds: None,
    )

    assert service.analyze(story_input) == parsed
    assert service.last_call_count == 2
    assert models.calls == 2


# ---------------------------------------------------------------------------
# Guard-layer regressions (2026-08-27 defect report, SA-1..SA-14).
# Every case below was reproduced against the shipped code before the fix.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spellings",
    [
        # A glued currency prefix produced no token at all, and a comma-grouped
        # figure tokenised from its last group only (Rs483,036 -> "036").
        ("Rs22 billion", "Rs22bn", "Rs 22 billion", "22 billion rupees"),
        ("Rs30m", "Rs 30 million", "30 million rupees", "0.03 billion"),
        # Publishers mix scales: reserves in millions and in billions, same day.
        ("$22,506 million", "$22.506 billion"),
        ("Rs2.1 million", "Rs21 lakh"),
        ("Rs483,036", "Rs 483,036"),
    ],
)
def test_every_spelling_of_a_figure_produces_one_token(spellings):
    tokens = {tuple(_evidence_tokens(text)) for text in spellings}
    assert len(tokens) == 1, f"{spellings} produced {tokens}"
    assert tokens != {()}, f"{spellings} produced no tokens at all"


def test_figures_of_different_magnitude_stay_different():
    assert not _tokens_supported("22 billion", "22 million")
    assert not _tokens_supported("Rs30m", "Rs30bn")
    assert not _tokens_supported("483,036", "912,036")


def test_a_comma_separated_list_is_not_read_as_one_number():
    # `\d[\d,]*` swallowed the whole run, so "1,2,3" became 123 and would
    # have validated an output claiming 123.
    assert _evidence_tokens("items 1,2,3") == ["1", "2", "3"]
    assert not _tokens_supported("a figure of 123", "items 1,2,3")


def test_fabricated_money_is_not_supported_by_a_source_without_it():
    assert not _tokens_supported(
        "PIMS received Rs22 billion in funding", "The hospital was inspected."
    )


def test_a_different_figure_sharing_a_trailing_group_is_not_support():
    assert not _tokens_supported("reached Rs483,036", "reached Rs912,036")


def test_the_same_figure_written_two_ways_is_supported_both_directions():
    assert _tokens_supported("a 30 million rupee penalty", "Orders Rs30m Penalty Deposit")
    assert _tokens_supported("Orders Rs30m penalty", "a 30 million rupee penalty")


def test_source_year_range_supports_both_expanded_endpoints():
    # Sources write a period as `2007-09`; the model correctly expands it.
    assert _tokens_supported("between 2007 and 2009", "the 2007-09 period")
    assert _tokens_supported("from 2019 to 2020", "over 2019-20")


def test_year_range_expansion_does_not_admit_an_endpoint_outside_it():
    assert not _tokens_supported("between 2007 and 2011", "the 2007-09 period")


def test_generic_category_words_are_not_story_anchors():
    # `story_tags` are editorial category labels and used to feed the anchor
    # set, so `Economy` matched an unrelated SCO report onto a subsidy card.
    assert not (_distinctive_anchors("Economy Politics Safety") & {"economy", "politics", "safety"})
    assert "supreme" not in _distinctive_anchors("Supreme Court upholds penalty")
    assert "pvma" in _distinctive_anchors("SC upholds Rs30m penalty on PVMA")


def test_related_context_requires_an_anchor_carried_by_most_primary_reports():
    primary = [
        _article(
            "dawn",
            "Punjab CM Maryam orders fresh safety audit of hospitals after PIMS fire",
            "Hospitals were told to audit fire safety after the PIMS fire.",
            cluster_id=uuid4(),
            embedding=[1, 0, 0, 0, 0, 0, 0, 0],
        ),
        _article(
            "geo",
            "Punjab orders review of fire-safety arrangements at PIMS-style facilities",
            "A review of fire-safety arrangements was ordered.",
            cluster_id=uuid4(),
            embedding=[0.99, 0.05, 0, 0, 0, 0, 0, 0],
        ),
    ]
    # Shares `maryam` with one primary headline only, and is a different story.
    junk = _article(
        "dawn",
        "CM Maryam orders Punjab IG to purge police force of corrupt officials",
        "The chief minister ordered a purge of the police force.",
        cluster_id=uuid4(),
        embedding=[0.91, 0.41, 0, 0, 0, 0, 0, 0],
    )
    on_topic = _article(
        "nation",
        "PIMS receives Rs22bn in federal funding over three years",
        "PIMS received Rs22bn in federal funding.",
        cluster_id=uuid4(),
        embedding=[0.99, 0.1, 0, 0, 0, 0, 0, 0],
    )

    selected = find_related_articles(
        primary,
        [*primary, junk, on_topic],
        selected_headline="Punjab orders urgent fire safety audits after PIMS fire",
    )

    assert on_topic in selected
    assert junk not in selected


def test_related_context_below_the_similarity_floor_is_dropped():
    primary = _article(
        "dawn",
        "PIMS nursery fire kills fourteen newborns",
        "A fire killed fourteen newborns at PIMS.",
        cluster_id=uuid4(),
        embedding=[1, 0, 0, 0, 0, 0, 0, 0],
    )
    # Shares the `pims` anchor but sits far below the floor.
    distant = _article(
        "geo",
        "PIMS canteen contract awarded after tender",
        "A canteen contract was awarded at PIMS.",
        cluster_id=uuid4(),
        embedding=[0.5, 0.87, 0, 0, 0, 0, 0, 0],
    )
    near = _article(
        "nation",
        "PIMS receives Rs22bn in federal funding",
        "PIMS received Rs22bn.",
        cluster_id=uuid4(),
        embedding=[0.99, 0.14, 0, 0, 0, 0, 0, 0],
    )

    selected = find_related_articles(
        [primary],
        [primary, distant, near],
        selected_headline="PIMS nursery fire kills fourteen newborns",
    )

    assert near in selected
    assert distant not in selected


def test_a_candidate_without_an_embedding_cannot_clear_the_floor():
    primary = _article(
        "dawn",
        "PIMS nursery fire kills fourteen newborns",
        "A fire killed fourteen newborns at PIMS.",
        cluster_id=uuid4(),
        embedding=[1, 0, 0, 0, 0, 0, 0, 0],
    )
    unembedded = _article(
        "geo", "PIMS statement issued", "PIMS issued a statement.", cluster_id=uuid4()
    )
    unembedded.embedding = None

    assert unembedded not in find_related_articles(
        [primary],
        [primary, unembedded],
        selected_headline="PIMS nursery fire kills fourteen newborns",
    )


@pytest.mark.parametrize(
    "sentence",
    [
        "The government launched an e-pension app for retirees.",
        "Protests spread across the nation this week.",
        "Police raided the compound at dawn on Thursday.",
    ],
)
def test_ordinary_words_are_not_publisher_attributions(sentence):
    assert _named_publishers(sentence) == set()


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("Brecorder reports that the figure rose.", {"brecorder"}),
        ("The Nation reports that PIMS received Rs22bn.", {"nation"}),
        ("According to Dawn, the ward was closed.", {"dawn"}),
    ],
)
def test_real_publisher_attributions_still_resolve(sentence, expected):
    assert _named_publishers(sentence) == expected


def test_an_unrecognised_publisher_name_never_discards_the_analysis():
    story_input, primary, *_ = _pims_input()
    response = StoryAnalysisResponse(
        analysis=(
            "Tribune reports that fourteen newborns died in a fire at PIMS. "
            "The News reports that the nursery was evacuated late."
        ),
        question=None,
        question_basis=QuestionBasis.NONE,
        claims=[
            StoryAnalysisClaim(
                text="Fourteen newborns died in a fire at PIMS.",
                supporting_article_ids=[str(primary.id)],
            )
        ],
    )

    validated = validate_story_analysis(response, story_input)

    assert validated.analysis
    assert "unknown_publisher_in_analysis" in validated.validation_errors


def test_the_canonical_bad_generic_question_is_rejected():
    assert not _question_is_specific(
        "A public hospital exists to keep patients safe. Which office was "
        "responsible for fire safety, and what failed?",
        QuestionBasis.RESPONSIBILITY_GAP,
        "PIMS fire. Safety violations were recorded since 2018.",
        core_anchors={"pims"},
    )


def test_naming_only_the_storys_own_subject_is_not_specific():
    assert not _question_is_specific(
        "Why do such tragedies keep happening in PIMS?",
        QuestionBasis.RESPONSIBILITY_GAP,
        "PIMS fire. Safety violations were recorded since 2018 at PIMS.",
        core_anchors={"pims"},
    )


def test_a_question_reusing_a_supported_figure_is_specific():
    assert _question_is_specific(
        "Given that PIMS received Rs22bn over three years, which office was "
        "responsible for acting on the 2018 findings?",
        QuestionBasis.RESOURCES_VS_OUTCOME,
        "PIMS received Rs22bn in federal funding. Violations recorded since 2018.",
        core_anchors={"pims"},
    )


def test_the_source_independence_question_survives_the_specificity_guard():
    assert _question_is_specific(
        "Six publisher names do not become six independent sources when every "
        "report traces back to the institution that conducted the operation. "
        "What independent record will establish who was killed?",
        QuestionBasis.SOURCE_INDEPENDENCE,
        "Security officials said eleven militants were killed in the operations.",
        core_anchors=set(),
    )


def test_question_proper_nouns_are_checked_against_the_whole_supplied_input():
    story_input, primary, safety, funding, _imran = _pims_input()
    # The question names a subject that appears in a supplied article the model
    # did not cite. Scoping this to the cited subset rejected 40% of live
    # questions, including the contract's own canonical case.
    response = StoryAnalysisResponse(
        analysis="Tribune reports that fourteen newborns died in a fire at PIMS Hospital.",
        question=(
            "The MCI report recorded violations since 2018 while PIMS received "
            "Rs22bn. Which office acted on those findings?"
        ),
        question_basis=QuestionBasis.RESOURCES_VS_OUTCOME,
        claims=[
            StoryAnalysisClaim(
                text="Fourteen newborns died in a fire at PIMS Hospital.",
                supporting_article_ids=[str(primary.id)],
            )
        ],
        question_supporting_article_ids=[str(safety.id), str(funding.id)],
    )

    validated = validate_story_analysis(response, story_input)

    assert validated.question is not None
    assert validated.status == "ok"


def test_a_dropped_question_is_kept_for_diagnosis_but_not_rendered():
    story_input, primary, *_ = _pims_input()
    response = StoryAnalysisResponse(
        analysis="Tribune reports that fourteen newborns died in a fire at PIMS Hospital.",
        question="Why do such tragedies keep happening in PIMS?",
        question_basis=QuestionBasis.RESPONSIBILITY_GAP,
        claims=[
            StoryAnalysisClaim(
                text="Fourteen newborns died in a fire at PIMS Hospital.",
                supporting_article_ids=[str(primary.id)],
            )
        ],
        question_supporting_article_ids=[str(primary.id)],
    )

    validated = validate_story_analysis(response, story_input)

    assert validated.question is None
    assert validated.status == "question_dropped"
    assert validated.rejected_question == "Why do such tragedies keep happening in PIMS?"
    metadata = validated.to_metadata(model="test")
    assert metadata["question"] is None
    assert metadata["rejected"]["question"].startswith("Why do such tragedies")


def test_analysis_figures_are_not_validated_against_uncited_context():
    # Pooling every supplied article let a number from an unrelated context
    # report validate a figure in the analysis.
    primary = _article(
        "dawn",
        "PIMS nursery fire kills fourteen newborns",
        "A fire killed fourteen newborns at PIMS.",
        cluster_id=uuid4(),
        embedding=[1, 0, 0, 0, 0, 0, 0, 0],
    )
    context = _article(
        "ary",
        "PIMS funding reported at Rs2,640 crore in earlier years",
        "PIMS funding was reported at Rs2,640 crore.",
        cluster_id=uuid4(),
        embedding=[0.99, 0.1, 0, 0, 0, 0, 0, 0],
    )
    story_input = build_story_analysis_input(
        cluster_id=str(uuid4()),
        selected_headline="PIMS nursery fire kills fourteen newborns",
        primary_articles=[primary],
        current_articles=[primary, context],
    )
    assert context.id in {UUID(a.article_id) for a in story_input.related_articles}

    response = StoryAnalysisResponse(
        analysis=(
            "Dawn reports that a fire killed fourteen newborns at PIMS, a facility "
            "funded at Rs2,640 crore."
        ),
        question=None,
        question_basis=QuestionBasis.NONE,
        claims=[
            StoryAnalysisClaim(
                text="A fire killed fourteen newborns at PIMS.",
                supporting_article_ids=[str(primary.id)],
            )
        ],
    )

    with pytest.raises(StoryAnalysisValidationError) as excinfo:
        validate_story_analysis(response, story_input)
    assert "unsupported_number_or_date_in_analysis" in str(excinfo.value)


def test_primary_selection_gives_every_publisher_a_slot_before_any_gets_two():
    articles = [
        _article(source, f"{source} report {index}", "PIMS fire report", cluster_id=uuid4())
        for source in ("dawn", "tribune", "geo", "ary", "nation", "app")
        for index in range(3)
    ]
    # The seventh publisher's only report, and the oldest in the pool.
    lone = _article("brecorder", "brecorder report", "PIMS fire report", cluster_id=uuid4())
    lone.publish_date = datetime(2026, 8, 26, 1, 0, tzinfo=timezone.utc)

    selected = select_primary_articles([*articles, lone], max_articles=12, max_per_publisher=2)

    assert len(selected) == 12
    assert lone in selected
    assert len({article.source for article in selected}) == 7


def test_an_exhausted_content_budget_emits_nothing_rather_than_everything():
    long_body = "word " * 3_000
    articles = [
        _article("dawn", "PIMS fire report one", long_body, cluster_id=uuid4()),
        _article("geo", "PIMS fire report two", long_body, cluster_id=uuid4()),
    ]

    story_input = build_story_analysis_input(
        cluster_id=str(uuid4()),
        selected_headline="PIMS nursery fire",
        primary_articles=articles,
        current_articles=[],
        total_content_limit=200,
    )

    assert sum(len(article.content) for article in story_input.articles) <= 200
    # The budget runs out on the second row; it must not be emitted in full.
    assert all(len(article.content) <= 200 for article in story_input.articles)


def test_a_sentence_opening_word_is_not_treated_as_a_name():
    # The live source-independence question opened with "Multiple", which was
    # not on the hand-written ignore list, so the whole question was dropped.
    question = (
        "Multiple publishers report these operations, but all accounts trace back "
        "to security sources without independent confirmation from the sites. What "
        "independent verification exists to confirm the identities of those killed?"
    )

    assert _question_phrases(question) == set()
    assert _proper_phrases_supported(
        question, "Security officials said eleven militants were killed in the operations."
    )


def test_a_name_used_mid_sentence_is_still_checked():
    assert "sharif" in _question_phrases("Why was Nawaz Sharif briefed before the audit?")
    assert not _proper_phrases_supported(
        "Why was Nawaz Sharif briefed before the audit?",
        "The chief minister ordered an audit of the hospitals.",
    )


def test_an_abbreviated_month_in_the_source_supports_the_written_form():
    # Dawn writes "Sept 16"; the model wrote "September 16", and the claim was
    # discarded as a fabricated date.
    assert _tokens_supported(
        "scheduled for September 16", "the SC had fixed the contempt plea for Sept 16"
    )
    assert _tokens_supported("an August 18 order", "in violation of the court's Aug 18 order")


def test_a_different_month_is_still_unsupported():
    assert not _tokens_supported(
        "scheduled for October 16", "the SC had fixed the contempt plea for Sept 16"
    )


def test_ordinary_words_are_not_read_as_abbreviated_weekdays():
    assert _evidence_tokens("he sat down and wed the following year") == []


@pytest.mark.parametrize(
    "sentence",
    [
        "Opposition members raised allegations of corruption within the Land Department.",
        "Dawn reports that lawmakers accused officials of a cover-up.",
        "The minister denied that warnings had been ignored.",
    ],
)
def test_an_attributed_accusation_is_not_the_models_own_conclusion(sentence):
    # The prompt requires accusatory claims to be *attributed*, so an
    # attributed sentence cannot be the model inferring guilt. A bare word
    # search discarded a whole live analysis over "allegations of corruption".
    assert not _contains_forbidden_conclusion(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "The hospital administration is corrupt.",
        "Officials ignored the warnings for seven years.",
        "This was a cover-up.",
    ],
)
def test_an_unattributed_accusation_is_still_rejected(sentence):
    assert _contains_forbidden_conclusion(sentence)


def test_an_own_voice_assertion_beside_an_attributed_one_is_still_rejected():
    assert _contains_forbidden_conclusion(
        "Opposition members alleged corruption. The department is corrupt."
    )


def test_a_question_naming_concrete_policy_mechanisms_is_specific():
    # Live rejection: no figure, and no name outside the story's own subject,
    # but plainly not a generic moral question.
    assert _question_is_specific(
        "The government intends to replace slab-based pricing with a uniform rate. "
        "What specific metrics or income thresholds will define vulnerable segments?",
        QuestionBasis.MISSING_PUBLIC_INFORMATION,
        "The petroleum minister said slab pricing would be replaced with a uniform rate.",
        core_anchors=set(),
    )


def test_the_modal_verb_may_is_not_read_as_the_month():
    # "may" is the one month name that is also an everyday English word, and
    # treating it as a date discarded a live analysis over "the party may
    # expand its protest to include a wheel-jam strike".
    assert _evidence_tokens("the party may expand its protest") == []
    assert _tokens_supported(
        "the party may expand its protest", "JI announced a nationwide strike."
    )


def test_may_still_counts_when_it_is_a_date():
    assert "may" in _evidence_tokens("a strike on May 3")
    assert "may" in _evidence_tokens("a strike on 3 May")
    assert not _tokens_supported("a strike on May 3", "a strike was announced")
