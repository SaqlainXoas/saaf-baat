"""
TDD integration-style unit test for cluster analysis -> AnalyzedFeed.

We use an injected spaCy pipeline (blank + EntityRuler) + rule-based classifier
so the test is deterministic and offline.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import spacy

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
    assert feed.category == "economy"
    assert feed.source_attribution.get("dawn") == 1
    assert feed.source_attribution.get("tribune") == 1
    assert feed.source_attribution.get("geo") == 1
    assert any(e.text == "Pakistan" and e.sources == 3 for e in feed.confirmed_facts)
    assert any(e.text == "IMF" and e.sources == 3 for e in feed.confirmed_facts)
