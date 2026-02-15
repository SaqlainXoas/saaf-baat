"""
Tests for EntityExtractor and ConsensusDetector using the real en_core_web_sm
model (no injected pipelines).  Assertions are pinned to outputs that were
empirically verified against this model.

Known spaCy quirks accounted for:
- "Karachi" sometimes tags as ORG — assertions avoid depending on its label.
- "IMF" (3 letters, standalone) is inconsistently tagged; tests use the full
  phrase "The International Monetary Fund" where a reliable hit is needed.
- "IMF" and "The International Monetary Fund" are distinct keys in
  ConsensusDetector (no synonym resolution).
"""
from __future__ import annotations

import pytest

from src.agents.analysis import ConsensusDetector, EntityExtractor


# ---------------------------------------------------------------------------
# Shared fixture: load the real model once per session so the 300 MB download
# only happens once and the ~1 s load cost is paid once.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def extractor():
    return EntityExtractor()  # defaults to en_core_web_sm, no injected nlp


# ---------------------------------------------------------------------------
# 1. IMF full-phrase + Pakistan + Washington
# ---------------------------------------------------------------------------


def test_extracts_imf_and_pakistan(extractor):
    text = (
        "The International Monetary Fund has approved a bailout package for "
        "Pakistan after talks held in Washington last week."
    )
    entities = extractor.extract(text)

    texts_by_label = {(e.text, e.type) for e in entities}

    assert ("The International Monetary Fund", "ORG") in texts_by_label
    assert ("Pakistan", "GPE") in texts_by_label
    assert ("Washington", "GPE") in texts_by_label


# ---------------------------------------------------------------------------
# 2. Person entity + ORG + GPE in a single sentence
# ---------------------------------------------------------------------------


def test_extracts_person_entities(extractor):
    text = (
        "Prime Minister Shehbaz Sharif met with representatives of the "
        "World Bank in Islamabad to discuss development aid for rural areas."
    )
    entities = extractor.extract(text)

    texts_by_label = {(e.text, e.type) for e in entities}

    assert ("Shehbaz Sharif", "PERSON") in texts_by_label
    # en_core_web_sm includes the leading article in the span
    assert ("the World Bank", "ORG") in texts_by_label
    assert ("Islamabad", "GPE") in texts_by_label


# ---------------------------------------------------------------------------
# 3. PTI + Imran Khan + Rawalpindi
# ---------------------------------------------------------------------------


def test_extracts_pti_imran_khan(extractor):
    text = (
        "PTI leader Imran Khan addressed thousands of supporters at a rally "
        "held in Rawalpindi on Saturday evening."
    )
    entities = extractor.extract(text)

    texts_by_label = {(e.text, e.type) for e in entities}

    assert ("Imran Khan", "PERSON") in texts_by_label
    assert ("PTI", "ORG") in texts_by_label
    assert ("Rawalpindi", "GPE") in texts_by_label


# ---------------------------------------------------------------------------
# 4. CARDINAL entities must be filtered out; ORG must survive
# ---------------------------------------------------------------------------


def test_filters_cardinal_labels(extractor):
    text = (
        "The Pakistan Stock Exchange saw 500 million shares traded as the "
        "State Bank of Pakistan announced new monetary policy guidelines."
    )
    entities = extractor.extract(text)

    # No CARDINAL entities should appear (not in DEFAULT_ALLOWED_ENTITY_LABELS)
    assert all(e.type != "CARDINAL" for e in entities)

    # en_core_web_sm includes the leading article in the span
    assert any(e.text == "the State Bank of Pakistan" and e.type == "ORG" for e in entities)


# ---------------------------------------------------------------------------
# 5. Case-insensitive deduplication inside ConsensusDetector
# ---------------------------------------------------------------------------


def test_case_dedup_with_consensus(extractor):
    # Two articles with different casing of "Pakistan"
    art1_text = "Pakistan's economy grew by three percent this quarter."
    art2_text = "pakistan reported strong GDP numbers in the latest quarter."

    ent1 = extractor.extract(art1_text)
    ent2 = extractor.extract(art2_text)

    detector = ConsensusDetector(min_agreement_ratio=1.0)
    result = detector.analyze([ent1, ent2])

    # "Pakistan" / "pakistan" should collapse to a single entity.
    pakistan_entities = [e for e in result.confirmed_facts if e.text.lower() == "pakistan"]
    assert len(pakistan_entities) == 1
    assert pakistan_entities[0].sources == 2
    # The canonical form should be the one with more upper-case letters
    assert pakistan_entities[0].text == "Pakistan"


# ---------------------------------------------------------------------------
# 6. Full consensus across three simulated sources (dawn / tribune / geo)
# ---------------------------------------------------------------------------


def test_consensus_on_three_imf_articles(extractor):
    articles = [
        # dawn
        (
            "The International Monetary Fund has extended its support to "
            "Pakistan following productive discussions in Washington. The "
            "bailout is expected to stabilise the economy in the coming months."
        ),
        # tribune
        (
            "Pakistan received a positive signal from The International "
            "Monetary Fund during high-level talks in Washington, paving the "
            "way for continued financial assistance."
        ),
        # geo
        (
            "The International Monetary Fund confirmed its commitment to "
            "Pakistan after a successful review round held in Washington last "
            "week, sources said."
        ),
    ]

    entities_by_article = [extractor.extract(t) for t in articles]

    detector = ConsensusDetector(min_agreement_ratio=1.0)
    result = detector.analyze(entities_by_article)

    # Build a lookup: (text, type) -> sources count  — confirmed only
    confirmed_lookup = {(e.text, e.type): e.sources for e in result.confirmed_facts}

    # All three articles mention Pakistan, Washington, and The International Monetary Fund
    assert ("Pakistan", "GPE") in confirmed_lookup
    assert confirmed_lookup[("Pakistan", "GPE")] == 3

    assert ("Washington", "GPE") in confirmed_lookup
    assert confirmed_lookup[("Washington", "GPE")] == 3

    assert ("The International Monetary Fund", "ORG") in confirmed_lookup
    assert confirmed_lookup[("The International Monetary Fund", "ORG")] == 3
