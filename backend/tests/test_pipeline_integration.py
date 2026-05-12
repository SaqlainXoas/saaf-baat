from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import numpy as np
import spacy
import yaml

from src.agents.analysis import AnalysisService, ConsensusDetector, EntityExtractor, RuleBasedClassifier
from src.agents.editorial import EditorialStory
from src.db.models import RawArticle
from src.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator
from tests.test_pipeline_orchestrator import FakeClusterer, FakeDB, FakeEmbedder, FakeScraper


class _SelectAllEditorialService:
    model = "integration-editorial"

    def review_clusters(self, candidates, *, max_stories: int = 9):
        selected = {}
        for priority, candidate in enumerate(candidates, start=1):
            selected[candidate.cluster_id] = EditorialStory(
                cluster_id=str(candidate.cluster_id),
                priority=100 - priority,
                headline=f"Edited: {candidate.base_feed.headline}",
                impact_line="This story has immediate public relevance in Pakistan.",
                category=str(candidate.base_feed.category),
                impact_labels=list(candidate.base_feed.impact_labels or ["🏛️ GOVERNANCE"]),
                what_to_watch="Watch for the next official update or policy response.",
                public_impact="high",
                story_tags=["pakistan", "brief"],
                confidence=0.9,
                selection_reason="Selected in the integration test editorial pass.",
            )
            if len(selected) >= max_stories:
                break
        return selected


def test_pipeline_integration_fixture_articles_produce_publishable_cards(tmp_path):
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "pipeline_articles.json"
    fixture_rows = json.loads(fixture_path.read_text(encoding="utf-8"))

    articles = [RawArticle(**row) for row in fixture_rows]
    scraper = FakeScraper({"dawn": [articles[0], articles[3]], "geo": [articles[1], articles[4]], "tribune": [articles[2], articles[5]]})

    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {"url": "https://example.com", "sections": ["pakistan"], "enabled": True},
                    "geo": {"url": "https://example.com", "sections": ["pakistan"], "enabled": True},
                    "tribune": {"url": "https://example.com", "sections": ["business"], "enabled": True},
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )
    rules_path = Path(__file__).resolve().parent.parent / "config" / "classification_rules.yaml"

    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
        classifier=RuleBasedClassifier.from_yaml(rules_path),
    )
    embedder = FakeEmbedder(
        embeddings=np.array(
            [
                [1.0, 0.0, 0.0],
                [0.99, 0.01, 0.0],
                [0.98, 0.02, 0.0],
                [0.0, 1.0, 0.0],
                [0.01, 0.99, 0.0],
                [0.02, 0.98, 0.0],
            ],
            dtype=np.float32,
        )
    )
    clusterer = FakeClusterer(labels=[0, 0, 0, 1, 1, 1])
    db = FakeDB()

    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            classification_yaml=rules_path,
            min_cluster_size=2,
            analyze_recent_clusters_limit=20,
            recluster_recent_window=False,
            enable_editorial_llm=True,
        ),
        db=db,  # type: ignore[arg-type]
        scraper=scraper,  # type: ignore[arg-type]
        embedder=embedder,  # type: ignore[arg-type]
        clusterer=clusterer,  # type: ignore[arg-type]
        analyzer=analyzer,
        editorial_service=_SelectAllEditorialService(),
    )

    stats = runner.run()

    assert stats.feeds_inserted >= 1
    assert db._feed_by_cluster

    first_feed = next(iter(db._feed_by_cluster.values()))
    assert first_feed.headline
    assert (first_feed.metadata or {}).get("why_it_matters")
    assert (first_feed.metadata or {}).get("what_to_watch")
    assert first_feed.source_attribution
    assert isinstance(first_feed.cluster_id, UUID)
