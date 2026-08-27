"""Adjudication: which pairs get asked, and what a verdict is allowed to do."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from src.agents.adjudication import AdjudicationPair, AdjudicationResult, GeminiAdjudicationService
from src.agents.clustering import EventGroupingService
from src.db.models import RawArticle


class FakeResponse:
    def __init__(self, payload):
        self.parsed = payload
        self.text = None


class FakeGenaiClient:
    def __init__(self, same_event=True):
        self.same_event = same_event
        self.prompts = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        import json

        self.prompts.append(contents)
        pairs = json.loads(contents)["pairs"]
        return FakeResponse(
            {"verdicts": [{"id": p["id"], "same_event": self.same_event, "confidence": 0.9} for p in pairs]}
        )


class RecordingAdjudicator:
    """Captures what the grouping service decided to ask about."""

    def __init__(self, same_event=False):
        self.seen = []
        self.same_event = same_event

    def adjudicate(self, pairs):
        self.seen = list(pairs)
        return AdjudicationResult(verdicts={p.key: self.same_event for p in pairs}, calls=1)


class ExplodingAdjudicator:
    def adjudicate(self, pairs):
        raise RuntimeError("adjudication is down")


def _article(headline, vector, source="dawn", url=None):
    now = datetime.now(timezone.utc)
    return RawArticle(
        source=source,
        url=url or f"https://example.com/{abs(hash(headline)) % 10**8}",
        headline=headline,
        main_text=f"{headline}. " * 40,
        publish_date=now,
        scraped_at=now,
        embedding=list(vector),
    )


def _unit(angle_degrees):
    """A 768-dim unit vector at a chosen angle, so similarity is exact."""
    radians = np.deg2rad(angle_degrees)
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = np.cos(radians)
    vector[1] = np.sin(radians)
    return vector


class TestBandSelection:
    def test_pairs_both_signals_agree_on_are_never_asked_about(self):
        # Near-identical headlines and near-identical vectors: the gates agree,
        # so no call should be spent.
        articles = [
            _article("Rupee gains against dollar in interbank trade", _unit(0)),
            _article("Rupee gains against dollar in interbank market", _unit(1), source="tribune"),
        ]
        adjudicator = RecordingAdjudicator()
        EventGroupingService(min_cluster_size=1, adjudicator=adjudicator).group_articles(articles)

        assert adjudicator.seen == []

    def test_a_pair_with_one_generic_shared_token_is_not_ambiguous(self):
        # Sharing only "pakistan" is not evidence. Measured on the golden day,
        # a one-token floor surfaced 51 pairs; a two-token floor surfaced 2.
        articles = [
            _article("Pakistan cricket captains appeal over health care", _unit(0)),
            _article("Pakistan governance crisis starts with local government", _unit(36), source="geo"),
        ]
        adjudicator = RecordingAdjudicator()
        EventGroupingService(min_cluster_size=1, adjudicator=adjudicator).group_articles(articles)

        shared = list(adjudicator.seen)
        assert shared == [], "one generic shared token must not buy a call"

    def test_the_budget_is_capped(self):
        articles = [
            _article(f"Iran sanctions statement number {i} issued today", _unit(35 + i * 0.01), source=f"s{i}")
            for i in range(12)
        ]
        adjudicator = RecordingAdjudicator()
        EventGroupingService(
            min_cluster_size=1, adjudicator=adjudicator, max_adjudication_pairs=3
        ).group_articles(articles)

        assert len(adjudicator.seen) <= 3


class TestVerdictAuthority:
    def test_the_coherence_gates_still_veto_a_same_event_verdict(self):
        """The adjudicator proposes; it never disposes."""
        # Two articles far apart in embedding space. Even told they are the same
        # event, the group quality gates must refuse to put them in one cluster.
        articles = [
            _article("Iran sanctions loom over oil markets", _unit(0)),
            _article("Iran sanctions prompt rand rally", _unit(75), source="geo"),
        ]
        result = EventGroupingService(
            min_cluster_size=1,
            adjudicator=RecordingAdjudicator(same_event=True),
            # Widen the band so the pair is definitely put to the adjudicator.
            adjudication_band_below=0.9,
            adjudication_band_above=0.9,
        ).group_articles(articles)

        assert result.num_clusters == 2, "a wrong verdict must not create an incoherent cluster"

    def test_an_adjudication_outage_leaves_deterministic_grouping_standing(self):
        articles = [
            _article("Rupee gains against dollar in interbank trade", _unit(0)),
            _article("Rupee gains against dollar in interbank market", _unit(1), source="tribune"),
        ]
        without = EventGroupingService(min_cluster_size=1).group_articles(articles)
        with_outage = EventGroupingService(
            min_cluster_size=1, adjudicator=ExplodingAdjudicator()
        ).group_articles(articles)

        assert with_outage.num_clusters == without.num_clusters


class TestService:
    def test_pairs_are_batched_and_keys_translate_back(self):
        client = FakeGenaiClient(same_event=True)
        service = GeminiAdjudicationService(client=client, batch_size=8)
        pairs = [
            AdjudicationPair(
                left_index=i,
                right_index=i + 100,
                left_source="dawn",
                left_headline=f"A{i}",
                right_source="geo",
                right_headline=f"B{i}",
                similarity=0.79,
                headline_overlap=0.2,
                entity_overlap=0.1,
            )
            for i in range(20)
        ]
        result = service.adjudicate(pairs)

        assert result.calls == 3
        assert len(result.verdicts) == 20
        assert result.merged == 20
        assert result.verdicts[(0, 100)] is True

    def test_urls_are_a_replay_key_not_a_prompt_field(self):
        client = FakeGenaiClient()
        service = GeminiAdjudicationService(client=client, batch_size=8)
        service.adjudicate(
            [
                AdjudicationPair(
                    left_index=0,
                    right_index=1,
                    left_source="dawn",
                    left_headline="A",
                    right_source="geo",
                    right_headline="B",
                    similarity=0.79,
                    headline_overlap=0.2,
                    entity_overlap=0.1,
                    left_url="https://example.com/left-story",
                    right_url="https://example.com/right-story",
                )
            ]
        )
        assert "left-story" not in client.prompts[0]
