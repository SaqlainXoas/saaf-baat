"""
TDD integration-style unit test for cluster analysis -> AnalyzedFeed.

We use an injected spaCy pipeline (blank + EntityRuler) + rule-based classifier
so the test is deterministic and offline.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import spacy

from src.db.models import ExtractedEntity
from src.db.models import RawArticle


def test_analysis_service_produces_analyzed_feed():
    from src.agents.analysis import EntityExtractor, ConsensusDetector, RuleBasedClassifier, AnalysisService

    rules_path = Path(__file__).resolve().parent.parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)

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
    service = AnalysisService(entity_extractor=extractor, consensus_detector=consensus, classifier=clf)

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
    from src.agents.analysis import AnalysisService, ConsensusDetector, RuleBasedClassifier

    class FakeExtractor:
        def extract(self, text: str):
            suffix = text[-1]
            shared = [ExtractedEntity(text=f"Shared {i}", type="ORG", sources=1) for i in range(10)]
            unique = [ExtractedEntity(text=f"Unique {suffix}-{i}", type="GPE", sources=1) for i in range(10)]
            return shared + unique

    rules_path = Path(__file__).resolve().parent.parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)
    service = AnalysisService(
        entity_extractor=FakeExtractor(),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=clf,
        max_confirmed_facts=5,
        max_debated_claims=6,
    )

    cluster_id = uuid4()
    articles = [
        RawArticle(source="dawn", url="https://dawn.com/c1", headline="H1", main_text=("Pakistan IMF a" * 30)),
        RawArticle(source="tribune", url="https://tribune.com.pk/c2", headline="H2", main_text=("Pakistan IMF b" * 30)),
        RawArticle(source="geo", url="https://geo.tv/c3", headline="H3", main_text=("Pakistan IMF c" * 30)),
    ]

    feed = service.analyze_cluster(cluster_id=cluster_id, articles=articles)

    assert len(feed.confirmed_facts) == 5
    assert len(feed.debated_claims) == 6
    assert len(feed.entity_counts) == 11


def test_analysis_service_prefers_centroid_representative_for_story_text():
    from src.agents.analysis import AnalysisService, ConsensusDetector, RuleBasedClassifier

    class FakeExtractor:
        def extract(self, text: str):
            return []

    rules_path = Path(__file__).resolve().parent.parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)
    service = AnalysisService(
        entity_extractor=FakeExtractor(),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=clf,
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

    feed = service.analyze_cluster(cluster_id=cluster_id, articles=[representative, outlier, near_representative])

    assert feed.headline != "Sports outlier headline with much longer wording than representative"
    assert feed.headline in {
        "Budget measures target inflation",
        "Inflation remains central to budget talks",
    }
    assert feed.summary is not None and "budget inflation" in feed.summary.lower()
    assert feed.category == "economy"
