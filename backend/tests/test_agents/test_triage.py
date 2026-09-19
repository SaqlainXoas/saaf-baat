"""Triage: batching, key translation, aggregation, and honest failure."""
from __future__ import annotations

from datetime import datetime, timezone

from src.agents.analysis import aggregate_triage, article_triage
from src.agents.triage import (
    GeminiTriageService,
    TriageItem,
    build_triage_user_prompt,
    wire_keys,
)
from src.db.models import RawArticle


class FakeResponse:
    def __init__(self, payload):
        self.parsed = payload
        self.text = None


class FakeGenaiClient:
    """Answers every item with a fixed verdict, recording the prompts it saw."""

    def __init__(self, answer=None, fail_times=0, error="boom"):
        self.answer = answer or {
            "category": "economy",
            "impact_labels": ["💳 WALLET"],
            "story_type": "hard_news",
            "pk_relevance": "national",
            "confidence": 0.8,
        }
        self.fail_times = fail_times
        self.error = error
        self.prompts = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.prompts.append(contents)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError(self.error)
        import json

        items = json.loads(contents)["items"]
        return FakeResponse(
            {"verdicts": [dict(self.answer, key=row["key"]) for row in items]}
        )


def _no_sleep(_seconds):
    return None


def _items(count):
    return [
        TriageItem(key=f"uuid-{i}", source="dawn", headline=f"Headline {i}", url=f"https://x/{i}")
        for i in range(count)
    ]


def _article(**kwargs):
    now = datetime.now(timezone.utc)
    defaults = {
        "source": "dawn",
        "url": "https://example.com/a",
        "headline": "Headline",
        "main_text": "Body text " * 30,
        "publish_date": now,
        "scraped_at": now,
    }
    defaults.update(kwargs)
    return RawArticle(**defaults)


def _triaged(article, **verdict):
    payload = {
        "category": "economy",
        "impact_labels": ["💳 WALLET"],
        "story_type": "hard_news",
        "pk_relevance": "national",
        "confidence": 0.9,
    }
    payload.update(verdict)
    article.metadata = dict(article.metadata or {}) | {"triage": payload}
    return article


class TestBatching:
    def test_batches_are_capped_and_every_item_is_covered(self):
        client = FakeGenaiClient()
        service = GeminiTriageService(client=client, batch_size=50, sleep=_no_sleep)
        result = service.triage(_items(120))

        assert result.calls == 3, "120 items at 50 per call is three requests"
        assert len(result.verdicts) == 120
        assert result.failures == 0

    def test_wire_keys_keep_caller_identity_off_the_prompt(self):
        # A 70-character URL echoed back per item burns tokens and invites
        # near-miss mismatches; the caller key is restored on the way out.
        client = FakeGenaiClient()
        service = GeminiTriageService(client=client, batch_size=50, sleep=_no_sleep)
        items = _items(3)
        result = service.triage(items)

        assert wire_keys(items) == ["i0", "i1", "i2"]
        assert "uuid-0" not in client.prompts[0]
        assert "https://x/0" not in client.prompts[0]
        assert set(result.verdicts) == {"uuid-0", "uuid-1", "uuid-2"}

    def test_one_failed_batch_costs_only_its_own_articles(self):
        client = FakeGenaiClient(fail_times=1)
        service = GeminiTriageService(client=client, batch_size=2, max_retries=1, sleep=lambda _s: None)
        result = service.triage(_items(4))

        assert result.failures == 2
        assert len(result.verdicts) == 2
        assert sorted(result.missing_keys) == ["uuid-0", "uuid-1"]

    def test_rate_limits_are_retried_rather_than_dropped(self):
        client = FakeGenaiClient(fail_times=2, error="RESOURCE_EXHAUSTED: quota")
        slept = []
        service = GeminiTriageService(
            client=client, batch_size=50, max_retries=4, sleep=slept.append
        )
        result = service.triage(_items(2))

        assert len(result.verdicts) == 2
        assert len(slept) == 2, "each 429 waits before retrying"


BUSY = (
    "Triage request failed: 503 UNAVAILABLE. {'error': {'code': 503, 'message': "
    "'This model is currently experiencing high demand. Spikes in demand are usually "
    "temporary. Please try again later.', 'status': 'UNAVAILABLE'}}"
)


class ScriptedClient(FakeGenaiClient):
    """Fails the calls whose 1-based numbers are listed, answers the rest."""

    def __init__(self, fail_calls, error=BUSY):
        super().__init__()
        self.fail_calls = set(fail_calls)
        self.error = error
        self.call_number = 0

    def generate_content(self, *, model, contents, config):
        self.call_number += 1
        if self.call_number in self.fail_calls:
            self.prompts.append(contents)
            raise RuntimeError(self.error)
        return super().generate_content(model=model, contents=contents, config=config)


class TestProviderBusy:
    """The 2026-09-17 and 2026-09-19 runs: a 503 dropped whole batches unretried."""

    def test_a_503_is_retried_instead_of_dropping_the_batch(self):
        client = FakeGenaiClient(fail_times=1, error=BUSY)
        slept = []
        service = GeminiTriageService(client=client, batch_size=50, sleep=slept.append)
        result = service.triage(_items(50))

        assert result.failures == 0
        assert len(result.verdicts) == 50
        assert len(client.prompts) == 2
        assert len(slept) == 1 and slept[0] >= 5.0, "a busy server gets a real wait"

    def test_the_busy_backoff_grows_to_cover_a_minute_long_spike(self):
        client = FakeGenaiClient(fail_times=3, error=BUSY)
        slept = []
        service = GeminiTriageService(
            client=client, batch_size=50, max_retries=4, sleep=slept.append
        )
        result = service.triage(_items(3))

        assert result.failures == 0
        assert slept == sorted(slept)
        assert sum(slept) >= 50.0

    def test_batches_are_paced_rather_than_fired_back_to_back(self):
        slept = []
        service = GeminiTriageService(
            client=FakeGenaiClient(), batch_size=10, sleep=slept.append
        )
        result = service.triage(_items(30))

        assert result.failures == 0
        assert len(slept) == 2, "a gap before every batch but the first"
        assert all(3.0 <= s <= 5.0 for s in slept)

    def test_a_final_pass_recovers_a_batch_that_outlasted_its_retries(self):
        # Batch 2 (calls 2-5) exhausts all four attempts; the spike then clears.
        client = ScriptedClient(fail_calls={2, 3, 4, 5})
        slept = []
        service = GeminiTriageService(
            client=client, batch_size=2, max_retries=4, sleep=slept.append
        )
        result = service.triage(_items(6))

        assert result.failures == 0
        assert result.missing_keys == []
        assert len(result.verdicts) == 6
        assert 60.0 in slept, "the final pass waits for the spike to clear"

    def test_a_real_outage_still_fails_honestly(self):
        client = FakeGenaiClient(fail_times=10_000, error=BUSY)
        service = GeminiTriageService(client=client, batch_size=2, sleep=_no_sleep)
        result = service.triage(_items(4))

        assert result.failures == 4
        assert sorted(result.missing_keys) == ["uuid-0", "uuid-1", "uuid-2", "uuid-3"]
        assert len(client.prompts) == 2 * 4 + 2 * 2, "four tries each, then two in the final pass"

    def test_a_non_retryable_error_gets_no_final_pass(self):
        client = FakeGenaiClient(fail_times=1, error="401 invalid api key")
        slept = []
        service = GeminiTriageService(client=client, batch_size=2, sleep=slept.append)
        result = service.triage(_items(4))

        assert result.failures == 2
        assert len(client.prompts) == 2
        assert 60.0 not in slept

    def test_verdicts_for_unknown_keys_are_ignored(self):
        class Liar(FakeGenaiClient):
            def generate_content(self, *, model, contents, config):
                return FakeResponse({"verdicts": [dict(self.answer, key="not-a-real-key")]})

        service = GeminiTriageService(client=Liar(), batch_size=50, sleep=_no_sleep)
        result = service.triage(_items(2))

        assert result.verdicts == {}
        assert result.failures == 2

    def test_prompt_states_the_allowed_vocabulary(self):
        import json

        payload = json.loads(build_triage_user_prompt(_items(1)))
        assert "economy" in payload["allowed_categories"]
        assert "hard_news" in payload["allowed_story_types"]
        assert "foreign_with_pk_effect" in payload["allowed_pk_relevance"]


class TestAggregation:
    def test_confidence_weighted_majority_decides_the_category(self):
        articles = [
            _triaged(_article(url="https://x/1"), category="economy", confidence=0.9),
            _triaged(_article(url="https://x/2"), category="economy", confidence=0.8),
            _triaged(_article(url="https://x/3"), category="politics", confidence=0.95),
        ]
        assert aggregate_triage(articles).category == "economy"

    def test_representative_breaks_a_tie(self):
        left = _triaged(_article(url="https://x/1"), category="economy", confidence=0.9)
        right = _triaged(_article(url="https://x/2"), category="politics", confidence=0.9)
        assert aggregate_triage([left, right], right).category == "politics"

    def test_hard_news_anywhere_wins(self):
        # One outlet running colour alongside does not make the development a feature.
        articles = [
            _triaged(_article(url="https://x/1"), story_type="feature"),
            _triaged(_article(url="https://x/2"), story_type="hard_news"),
        ]
        assert aggregate_triage(articles).story_type == "hard_news"

    def test_most_relevant_reading_wins(self):
        articles = [
            _triaged(_article(url="https://x/1"), pk_relevance="local"),
            _triaged(_article(url="https://x/2"), pk_relevance="national"),
        ]
        assert aggregate_triage(articles).pk_relevance == "national"

    def test_impact_labels_are_ranked_and_capped_at_three(self):
        articles = [
            _triaged(_article(url="https://x/1"), impact_labels=["💳 WALLET", "🛡️ SAFETY"]),
            _triaged(_article(url="https://x/2"), impact_labels=["💳 WALLET", "🚦 COMMUTE"]),
            _triaged(_article(url="https://x/3"), impact_labels=["💳 WALLET", "⚡ UTILITIES"]),
        ]
        labels = aggregate_triage(articles).impact_labels
        assert labels[0] == "💳 WALLET", "the label three sources agree on ranks first"
        assert len(labels) <= 3

    def test_a_cluster_with_no_verdicts_is_a_state_not_a_guess(self):
        result = aggregate_triage([_article(url="https://x/1")])
        assert result.category == "other"
        assert result.confidence == 0.0
        assert result.story_type is None
        assert not result.has_verdicts

    def test_article_triage_ignores_a_malformed_blob(self):
        article = _article()
        article.metadata = {"triage": "not-a-dict"}
        assert article_triage(article) is None


def test_triage_schema_constrains_every_enumerated_field():
    """A live run answered `category: "opinion"` - a story_type, not a category.

    The schema said "type": "string", so nothing stopped it and the verdict was
    discarded; triage_status went to "degraded" for the run.
    """
    from src.agents.editorial import VALID_CATEGORIES, VALID_IMPACT_LABELS
    from src.agents.triage import (
        VALID_PK_RELEVANCE,
        VALID_STORY_TYPES,
        _gemini_response_schema,
    )

    props = _gemini_response_schema()["$defs"]["TriageVerdict"]["properties"]

    assert props["category"]["enum"] == list(VALID_CATEGORIES)
    assert props["story_type"]["enum"] == list(VALID_STORY_TYPES)
    assert props["pk_relevance"]["enum"] == list(VALID_PK_RELEVANCE)
    assert props["impact_labels"]["items"]["enum"] == list(VALID_IMPACT_LABELS)
    assert "opinion" not in props["category"]["enum"]


def test_routine_is_a_triage_story_type():
    """Routine departmental bulletins were indistinguishable from real news."""
    from src.agents.triage import TRIAGE_SYSTEM_PROMPT, VALID_STORY_TYPES

    assert "routine" in VALID_STORY_TYPES
    assert "routine" in TRIAGE_SYSTEM_PROMPT
    # It is about the absence of a consequence, not about who spoke.
    assert "inspection" in TRIAGE_SYSTEM_PROMPT
