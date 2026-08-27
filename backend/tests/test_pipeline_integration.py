from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import numpy as np
import spacy
import yaml

from src.agents.analysis import AnalysisService, ConsensusDetector, EntityExtractor
from src.agents.editorial import EditorialStory
from src.agents.story_analysis import (
    QuestionBasis,
    StoryAnalysisClaim,
    StoryAnalysisResponse,
)
from src.db.models import RawArticle
from src.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator
from tests.test_pipeline_orchestrator import FakeClusterer, FakeDB, FakeEmbedder, FakeIngestor

# Keyword matching is fine for a test fixture; it was never fine as product
# logic. This stands in for GeminiTriageService so orchestrator tests exercise
# the real triage stage without a network call.
_FIXTURE_CATEGORY_HINTS = (
    ("economy", ("imf", "rupee", "inflation", "oil", "budget", "tax", "economic", "market", "port", "$")),
    ("security", ("attack", "police", "blast", "security", "militant", "killed", "army", "lion", "rescue")),
    ("politics", ("minister", "assembly", "government", "pml", "pti", "election", "senate", "court", "shc", "jit")),
    ("city", ("karachi", "lahore", "traffic", "toll", "expressway", "water", "road")),
    ("health", ("hospital", "dengue", "health", "polio")),
    ("education", ("school", "university", "exam", "student")),
    ("international", ("iran", "china", "india", "us ", "tehran", "sanctions")),
    ("sports", ("cricket", "football", "atp", "premier league")),
    ("entertainment", ("film", "box office", "actor", "prince", "gala")),
)
_FIXTURE_IMPACT_HINTS = (
    ("💳 WALLET", ("rupee", "inflation", "tax", "price", "oil", "budget", "$")),
    ("🛡️ SAFETY", ("attack", "blast", "killed", "police", "security", "lion")),
    ("🚦 COMMUTE", ("traffic", "toll", "expressway", "road", "transport")),
    ("⚡ UTILITIES", ("power", "electricity", "gas", "water", "internet")),
    ("🏛️ GOVERNANCE", ("minister", "assembly", "government", "court", "policy")),
)


class FakeTriageService:
    """Deterministic triage stand-in keyed off the fixture vocabulary."""

    def __init__(self, category: str | None = None, story_type: str = "hard_news"):
        self.category = category
        self.story_type = story_type
        self.calls = 0

    def triage(self, items):
        from src.agents.triage import TriageResult, TriageVerdict

        self.calls += 1
        verdicts = {}
        for item in items:
            text = f"{item.headline} {item.summary}".lower()
            category = self.category or next(
                (name for name, hints in _FIXTURE_CATEGORY_HINTS if any(h in text for h in hints)),
                "other",
            )
            labels = [
                label
                for label, hints in _FIXTURE_IMPACT_HINTS
                if any(hint in text for hint in hints)
            ][:3]
            verdicts[item.key] = TriageVerdict(
                key=item.key,
                category=category,
                impact_labels=labels,
                story_type=self.story_type,
                pk_relevance="national",
                confidence=0.9,
            )
        return TriageResult(verdicts=verdicts, calls=1, failures=0, missing_keys=[])



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


class _GroundedStoryAnalysisService:
    model = "integration-story-analysis"
    last_call_count = 1

    def __init__(self):
        self.calls = 0

    def analyze(self, story_input):
        self.calls += 1
        primary = story_input.primary_articles[0]
        publisher = primary.publisher.replace("_", " ").title()
        return StoryAnalysisResponse(
            analysis=(
                f"{publisher} reports the selected development and its immediate public consequence. "
                "The account remains limited to the facts carried in the current reports."
            ),
            question=None,
            question_basis=QuestionBasis.NONE,
            claims=[
                StoryAnalysisClaim(
                    text="The supplied reporting describes the selected development.",
                    supporting_article_ids=[primary.article_id],
                )
            ],
        )


def test_pipeline_integration_fixture_articles_produce_publishable_cards(tmp_path):
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "pipeline_articles.json"
    fixture_rows = json.loads(fixture_path.read_text(encoding="utf-8"))

    articles = [RawArticle(**row) for row in fixture_rows]

    # The fixture carries fixed timestamps, which age: by now they are ~104
    # days old and the staleness gate rightly rejects them. Shift the whole set
    # forward so it stays the fresh news day it was written to be, preserving
    # the relative spacing between articles.
    latest = max(a.publish_date for a in articles if a.publish_date)
    shift = datetime.now(timezone.utc) - latest
    for article in articles:
        if article.publish_date is not None:
            article.publish_date = article.publish_date + shift
        article.scraped_at = article.scraped_at + shift
    ingestor = FakeIngestor({"dawn": [articles[0], articles[3]], "geo": [articles[1], articles[4]], "tribune": [articles[2], articles[5]]})

    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "dawn": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": True},
                    "geo": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": True},
                    "tribune": {"url": "https://example.com", "tier": "A", "feed_urls": ["https://example.com/rss"], "enabled": True},
                },
                "scraping_config": {"max_articles_per_source": 5},
            }
        ),
        encoding="utf-8",
    )

    analyzer = AnalysisService(
        entity_extractor=EntityExtractor(nlp=spacy.blank("en")),
        consensus_detector=ConsensusDetector(min_agreement_ratio=1.0),
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

    story_analysis_service = _GroundedStoryAnalysisService()
    runner = PipelineOrchestrator(
        config=PipelineConfig(
            sources_yaml=sources_yaml,
            min_cluster_size=2,
            analyze_recent_clusters_limit=20,
            recluster_recent_window=False,
            enable_editorial_llm=True,
            enable_story_analysis_llm=True,
        ),
        db=db,  # type: ignore[arg-type]
        triage_service=FakeTriageService(),
        ingestor=ingestor,  # type: ignore[arg-type]
        embedder=embedder,  # type: ignore[arg-type]
        clusterer=clusterer,  # type: ignore[arg-type]
        analyzer=analyzer,
        editorial_service=_SelectAllEditorialService(),
        story_analysis_service=story_analysis_service,
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
    assert stats.story_analysis_status == "ok"
    assert stats.story_analysis_successes == stats.feeds_inserted
    assert story_analysis_service.calls == stats.feeds_inserted
    assert (first_feed.metadata or {}).get("story_analysis", {}).get("analysis")
