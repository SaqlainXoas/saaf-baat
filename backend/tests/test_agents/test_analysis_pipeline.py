"""
TDD integration-style unit test for cluster analysis -> AnalyzedFeed.

We use an injected spaCy pipeline (blank + EntityRuler) + rule-based classifier
so the test is deterministic and offline.
"""
from __future__ import annotations

from uuid import uuid4

import spacy

from src.db.models import ExtractedEntity, RawArticle


def _with_triage(article, category="economy", impact_labels=("💳 WALLET",), story_type="hard_news"):
    """Stamp the triage verdict the pipeline would have persisted before analysis."""
    metadata = dict(article.metadata or {})
    metadata["triage"] = {
        "category": category,
        "impact_labels": list(impact_labels),
        "story_type": story_type,
        "pk_relevance": "national",
        "confidence": 0.9,
    }
    article.metadata = metadata
    return article



def test_analysis_service_produces_analyzed_feed():
    from src.agents.analysis import AnalysisService, ConsensusDetector, EntityExtractor


    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns(
        [
            {"label": "GPE", "pattern": "Pakistan"},
            {"label": "ORG", "pattern": "IMF"},
            {"label": "MONEY", "pattern": "rupee"},
        ]
    )
    extractor = EntityExtractor(nlp=nlp)
    consensus = ConsensusDetector(min_agreement_ratio=1.0)
    service = AnalysisService(entity_extractor=extractor, consensus_detector=consensus)

    cluster_id = uuid4()
    articles = [
        RawArticle(
            source="dawn",
            url="https://dawn.com/a",
            headline="Pakistan talks to IMF as rupee falls",
            main_text=("Pakistan IMF rupee " * 30),
        ),
        RawArticle(
            source="tribune",
            url="https://tribune.com.pk/b",
            headline="IMF meeting in Pakistan amid inflation fears",
            main_text=("Pakistan IMF inflation " * 30),
        ),
        RawArticle(
            source="geo",
            url="https://geo.tv/c",
            headline="Pakistan seeks IMF relief package",
            main_text=("Pakistan IMF package " * 30),
        ),
    ]

    articles = [_with_triage(a) for a in articles]
    feed = service.analyze_cluster(cluster_id=cluster_id, articles=articles)

    assert str(feed.cluster_id) == str(cluster_id)
    assert feed.headline  # chosen deterministically
    assert isinstance(feed.summary, str)
    assert feed.summary
    assert len(feed.summary) <= 241  # 240 chars + possible ellipsis
    assert feed.category == "economy"
    assert feed.source_attribution.get("dawn") == 1
    assert feed.source_attribution.get("tribune") == 1
    assert feed.source_attribution.get("geo") == 1
    assert any(e.text == "Pakistan" and e.sources == 3 for e in feed.confirmed_facts)
    assert any(e.text == "IMF" and e.sources == 3 for e in feed.confirmed_facts)


def test_analysis_service_caps_confirmed_and_debated_entities():
    from src.agents.analysis import AnalysisService, ConsensusDetector

    class FakeExtractor:
        def extract(self, text: str):
            suffix = text[-1]
            shared = [ExtractedEntity(text=f"Shared {i}", type="ORG", sources=1) for i in range(10)]
            unique = [ExtractedEntity(text=f"Unique {suffix}-{i}", type="GPE", sources=1) for i in range(10)]
            return shared + unique

    service = AnalysisService(
        entity_extractor=FakeExtractor(),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        max_confirmed_facts=5,
        max_debated_claims=6,
    )

    cluster_id = uuid4()
    articles = [
        RawArticle(source="dawn", url="https://dawn.com/c1", headline="H1", main_text=("Pakistan IMF a" * 30)),
        RawArticle(source="tribune", url="https://tribune.com.pk/c2", headline="H2", main_text=("Pakistan IMF b" * 30)),
        RawArticle(source="geo", url="https://geo.tv/c3", headline="H3", main_text=("Pakistan IMF c" * 30)),
    ]

    articles = [_with_triage(a) for a in articles]
    feed = service.analyze_cluster(cluster_id=cluster_id, articles=articles)

    assert len(feed.confirmed_facts) == 5
    assert len(feed.debated_claims) == 6
    assert len(feed.entity_counts) == 11


def test_analysis_service_prefers_centroid_representative_for_story_text():
    from src.agents.analysis import AnalysisService, ConsensusDetector

    class FakeExtractor:
        def extract(self, text: str):
            return []

    service = AnalysisService(
        entity_extractor=FakeExtractor(),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
    )

    cluster_id = uuid4()
    representative = RawArticle(
        source="tribune",
        url="https://tribune.com.pk/rep",
        headline="Budget measures target inflation",
        main_text=("budget inflation tax " * 30),
        embedding=[1.0, 0.0, 0.0],
    )
    outlier = RawArticle(
        source="dawn",
        url="https://dawn.com/outlier",
        headline="Sports outlier headline with much longer wording than representative",
        main_text=("cricket tournament semifinal championship highlights " * 30),
        embedding=[0.0, 1.0, 0.0],
    )
    near_representative = RawArticle(
        source="geo",
        url="https://geo.tv/near-rep",
        headline="Inflation remains central to budget talks",
        main_text=("budget inflation fiscal " * 30),
        embedding=[0.98, 0.02, 0.0],
    )

    feed = service.analyze_cluster(
        cluster_id=cluster_id,
        articles=[
            _with_triage(representative),
            # The outlier is triaged as sport, and is outvoted rather than ignored.
            _with_triage(outlier, category="sports", impact_labels=(), story_type="sport"),
            _with_triage(near_representative),
        ],
    )

    assert feed.headline != "Sports outlier headline with much longer wording than representative"
    assert feed.headline in {
        "Budget measures target inflation",
        "Inflation remains central to budget talks",
    }
    assert feed.summary is not None and "budget inflation" in feed.summary.lower()
    assert feed.category == "economy"
