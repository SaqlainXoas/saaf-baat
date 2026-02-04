"""
TDD tests for ConsensusDetector.
"""
from __future__ import annotations

def test_consensus_detector_strict_intersection_and_counts():
    from src.agents.analysis import ConsensusDetector
    from src.db.models import ExtractedEntity

    detector = ConsensusDetector(min_agreement_ratio=1.0)

    extracted = [
        [
            ExtractedEntity(text="Pakistan", type="GPE"),
            ExtractedEntity(text="IMF", type="ORG"),
            ExtractedEntity(text="Rs 10", type="MONEY"),
        ],
        [
            ExtractedEntity(text="Pakistan", type="GPE"),
            ExtractedEntity(text="IMF", type="ORG"),
            ExtractedEntity(text="Rs 20", type="MONEY"),
        ],
        [
            ExtractedEntity(text="Pakistan", type="GPE"),
            ExtractedEntity(text="IMF", type="ORG"),
            ExtractedEntity(text="Rs 30", type="MONEY"),
        ],
    ]

    result = detector.analyze(extracted)

    confirmed = {(e.text, e.type, e.sources) for e in result.confirmed_facts}
    debated = {(e.text, e.type, e.sources) for e in result.debated_claims}

    # Pakistan + IMF appear in all 3
    assert ("Pakistan", "GPE", 3) in confirmed
    assert ("IMF", "ORG", 3) in confirmed

    # Money values appear in only one source each
    assert ("Rs 10", "MONEY", 1) in debated
    assert ("Rs 20", "MONEY", 1) in debated
    assert ("Rs 30", "MONEY", 1) in debated


def test_consensus_detector_case_insensitive_normalization():
    from src.agents.analysis import ConsensusDetector
    from src.db.models import ExtractedEntity

    detector = ConsensusDetector(min_agreement_ratio=1.0)

    # Same entity with different casing should be treated as the same.
    per_article = [
        [ExtractedEntity(text="Pakistan", type="GPE")],
        [ExtractedEntity(text="pakistan", type="GPE")],
    ]

    result = detector.analyze(per_article)
    assert any(e.text == "Pakistan" and e.sources == 2 for e in result.confirmed_facts)
