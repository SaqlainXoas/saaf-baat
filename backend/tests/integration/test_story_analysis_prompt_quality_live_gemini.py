from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.agents.story_analysis import build_story_analysis_input, validate_story_analysis
from src.agents.story_analysis_gemini import GeminiStoryAnalysisService
from src.db.models import RawArticle

pytestmark = pytest.mark.skipif(
    (os.getenv("RUN_LIVE_GEMINI_TESTS") or "").strip().lower() not in {"1", "true", "yes"},
    reason="live Gemini prompt tests are opt-in (set RUN_LIVE_GEMINI_TESTS=1)",
)


def _article(source: str, headline: str, text: str, *, cluster_id=None, status="summary"):
    return RawArticle(
        id=uuid4(),
        source=source,
        url=f"https://example.com/{uuid4()}",
        headline=headline,
        main_text=text,
        cluster_id=cluster_id,
        publish_date=datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 5, 5, tzinfo=timezone.utc),
        embedding=[1.0, 0.0, 0.0],
        metadata={"body_status": status},
    )


def _run(primary, current, *, headline, tags=()):
    service = GeminiStoryAnalysisService(max_attempts=2)
    story_input = build_story_analysis_input(
        cluster_id=str(primary[0].cluster_id or uuid4()),
        selected_headline=headline,
        primary_articles=primary,
        current_articles=current,
        story_tags=tags,
    )
    return validate_story_analysis(service.analyze(story_input), story_input)


def test_live_pims_question_uses_documented_specifics_and_ignores_imran_context():
    cluster_id = uuid4()
    fire = _article(
        "tribune",
        "14 newborns killed in fire at PIMS Hospital in Islamabad",
        "Fourteen newborns were killed when fire broke out in the nursery at PIMS Hospital.",
        cluster_id=cluster_id,
        status="full",
    )
    safety = _article(
        "ary",
        "MCI report exposes fire safety violations at PIMS since 2018",
        "An MCI report recorded fire safety violations at PIMS since 2018. Closed entrances and security obstructions delayed rescue.",
        cluster_id=uuid4(),
    )
    earlier = _article(
        "ary",
        "PIMS saw blaze weeks before Wednesday tragedy",
        "A smaller blaze occurred at PIMS only weeks before the nursery tragedy.",
        cluster_id=uuid4(),
    )
    funding = _article(
        "nation",
        "PIMS receives Rs22bn in federal funding over three years",
        "PIMS received Rs22bn in federal funding over three years.",
        cluster_id=uuid4(),
    )
    imran = _article(
        "geo",
        "Imran Khan taken to PIMS over security concerns",
        "Officials discussed Imran Khan's transfer to PIMS.",
        cluster_id=uuid4(),
    )

    result = _run(
        [fire],
        [fire, safety, earlier, funding, imran],
        headline="PIMS nursery fire kills fourteen newborns",
        tags=["PIMS", "nursery fire"],
    )

    assert result.question is not None
    lowered = result.question.lower()
    cues = ["2018", "rs22bn", "earlier", "weeks", "closed", "obstruction"]
    assert sum(cue in lowered for cue in cues) >= 2
    assert "imran" not in result.analysis.lower()
    assert "imran" not in lowered


def test_live_model_distinguishes_publishers_from_independent_sources():
    cluster_id = uuid4()
    articles = [
        _article(
            source,
            "Security forces report eleven militants killed in operations",
            "Security officials said eleven militants were killed in separate operations. The account came from security sources.",
            cluster_id=cluster_id,
        )
        for source in ("dawn", "tribune", "geo", "ary", "nation", "thenews")
    ]

    result = _run(
        articles,
        articles,
        headline="Security forces report eleven killed in separate operations",
        tags=["security operations"],
    )

    assert result.question is not None
    assert any(term in result.question.lower() for term in ("independent", "verification", "record"))


def test_live_routine_announcement_returns_no_question():
    article = _article(
        "ary",
        "Government launches e-pension portal for retired employees",
        "The government launched an e-pension portal allowing retired federal employees to file claims online.",
        cluster_id=uuid4(),
    )

    result = _run([article], [article], headline=article.headline, tags=["e-pension"])

    assert result.question is None
    assert "ary" in result.analysis.lower()


def test_live_single_source_tariff_stays_attributed():
    article = _article(
        "brecorder",
        "Electricity tariff increase of Rs2.52 per unit proposed",
        "A fuel-adjustment increase of Rs2.52 per unit was proposed. The report does not state whether protected domestic consumers are exempt.",
        cluster_id=uuid4(),
        status="full",
    )

    result = _run([article], [article], headline=article.headline, tags=["electricity tariff"])

    assert "business recorder" in result.analysis.lower()
    assert result.question is not None
    assert "protected" in result.question.lower()
