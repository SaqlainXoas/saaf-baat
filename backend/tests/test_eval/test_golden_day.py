"""
The golden-day harness: does the brief look like that day's real toplines?

363 mechanical tests said nothing about whether a brief is *good*. These do —
against a hand-written statement of what one real Pakistani news day should
have produced.

Two tiers, deliberately:

* Hard assertions — must-not-haves absent, no duplicate events, size in range.
  These are statements about correctness that should never regress.
* A recall ratchet — the brief must not cover fewer of the day's toplines than
  the recorded baseline. Recall on day one is what it is; the harness exists to
  stop it going backwards, not to fail until selection is rebuilt.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.eval.golden_day import (
    GoldenDay,
    available_days,
    measure_cluster_quality,
    run_golden_day,
)
from src.eval.scoring import (
    BriefCard,
    Expectation,
    find_duplicate_events,
    score_brief,
)

pytestmark = pytest.mark.eval


class TestExpectationMatching:
    def test_a_story_is_covered_when_enough_keywords_appear(self):
        expectation = Expectation(
            id="ajk-reserved-seats",
            keywords=["ajk", "reserved seats", "pml-n"],
            min_keyword_hits=2,
        )
        assert expectation.matches("PML-N secures 5 of 7 reserved seats in AJK assembly")

    def test_one_incidental_keyword_is_not_coverage(self):
        expectation = Expectation(
            id="ajk-reserved-seats",
            keywords=["ajk", "reserved seats", "pml-n"],
            min_keyword_hits=2,
        )
        assert not expectation.matches("PML-N leader comments on the economy")

    def test_matching_ignores_case_and_punctuation(self):
        expectation = Expectation(id="imf", keywords=["IMF", "bailout"], min_keyword_hits=2)
        assert expectation.matches("The I.M.F. — bailout talks resume" .replace(".", ""))
        assert expectation.matches("imf, bailout tranche approved")


class TestDuplicateDetection:
    def test_two_cards_about_one_event_are_flagged(self):
        cards = [
            BriefCard("1", "Rupee gains against dollar in interbank trading today"),
            BriefCard("2", "Rupee gains against the dollar in interbank trading today"),
        ]
        duplicates = find_duplicate_events(cards)
        assert len(duplicates) == 1
        assert duplicates[0].overlap >= 0.5

    def test_distinct_stories_are_not_flagged(self):
        cards = [
            BriefCard("1", "Rupee gains against dollar in interbank trading"),
            BriefCard("2", "Karachi water supply restored after main burst"),
        ]
        assert find_duplicate_events(cards) == []


class TestScoring:
    EXPECTATIONS = {
        "must_have": [
            {"id": "imf-tranche", "keywords": ["imf", "tranche"], "min_keyword_hits": 2},
            {"id": "karachi-water", "keywords": ["karachi", "water"], "min_keyword_hits": 2},
        ],
        "must_not_have": [
            {"id": "celebrity-filler", "keywords": ["kazaam", "shaquille"], "min_keyword_hits": 1}
        ],
        "brief_size": {"min": 2, "max": 3},
        "baseline_recall": 0.5,
    }

    def test_full_coverage_scores_one(self):
        cards = [
            BriefCard("1", "IMF approves next tranche for Pakistan"),
            BriefCard("2", "Karachi water supply restored"),
        ]
        report = score_brief(cards, self.EXPECTATIONS)

        assert report.recall == 1.0
        assert report.missed == []
        assert report.violations == []
        assert report.size_in_range is True

    def test_missing_topline_is_reported_by_name(self):
        report = score_brief([BriefCard("1", "IMF approves next tranche")], self.EXPECTATIONS)

        assert report.missed == ["karachi-water"]
        assert report.recall == 0.5

    def test_must_not_have_is_a_violation(self):
        cards = [
            BriefCard("1", "IMF approves next tranche"),
            BriefCard("2", "Karachi water supply restored"),
            BriefCard("3", "Shaquille O'Neal defends Kazaam"),
        ]
        report = score_brief(cards, self.EXPECTATIONS)

        assert report.violations == ["celebrity-filler"]

    def test_a_brief_outside_the_size_range_is_flagged(self):
        report = score_brief([BriefCard("1", "IMF approves next tranche")], self.EXPECTATIONS)
        assert report.size_in_range is False

    def test_report_renders_without_a_brief(self):
        report = score_brief([], self.EXPECTATIONS)
        assert "MISSED must-haves" in report.format()
        assert report.recall == 0.0


_CAPTURED_DAYS = available_days()


@pytest.fixture(
    scope="module",
    params=_CAPTURED_DAYS or [None],
    ids=lambda path: path.name if path is not None else "no-golden-day",
)
def outcome(request):
    """Replay one captured day; each day is run once and shared by the tests."""
    if request.param is None:
        pytest.skip("no golden day captured yet — run scripts/capture_golden_day.py")
    day = GoldenDay.load(request.param)
    with tempfile.TemporaryDirectory() as tmp:
        return run_golden_day(day, db_path=Path(tmp) / "golden.db"), day


class TestRecordedDay:
    """Replays a real captured day through the real pipeline."""

    def test_the_recorded_payloads_still_produce_a_pool(self, outcome):
        (report, stats), day = outcome
        assert stats.scraped > 50, "the fixture stopped yielding articles"
        assert stats.inserted > 0

    def test_the_health_gate_still_fires_on_the_recorded_day(self, outcome):
        (report, stats), day = outcome
        expected = set(day.expectations.get("expected_quarantine") or [])
        if not expected:
            pytest.skip("this day records no expected quarantine")
        assert expected.issubset(set(stats.degraded_sources))

    def test_no_must_not_have_reaches_the_brief(self, outcome):
        (report, _stats), _day = outcome
        assert report.violations == [], report.format()

    def test_no_duplicate_events_across_cards(self, outcome):
        (report, _stats), _day = outcome
        assert report.duplicates == [], report.format()

    def test_brief_size_is_in_range(self, outcome):
        (report, _stats), _day = outcome
        if report.size_max <= 0:
            pytest.skip("this day records no size range")
        assert report.size_in_range, report.format()

    def test_topline_recall_does_not_regress(self, outcome):
        (report, _stats), _day = outcome
        if report.baseline_recall is None:
            pytest.skip("no baseline recorded yet for this day")
        assert report.recall >= report.baseline_recall, report.format()

    def test_grouping_does_not_bury_stories_in_blobs(self, outcome):
        """A merged article is a story the editor never sees as a candidate.

        Recall cannot catch this: keyword matching finds its must-have inside a
        blob as happily as inside a clean cluster, which is why both days
        scored 100% while a live cluster held four unrelated events under the
        headline of the smallest of them.
        """
        (report, _stats), day = outcome
        ceiling = day.expectations.get("max_merged_articles")
        if ceiling is None:
            pytest.skip("this day records no grouping ceiling")
        assert report.cluster_quality is not None, "grouping was not measured"
        assert report.cluster_quality.merged_in <= int(ceiling), report.format()


class TestDuplicateMeasure:
    """Containment, not Jaccard: card text is short enough that one stopword matters."""

    def test_a_restated_headline_is_a_duplicate(self):
        cards = [
            BriefCard("1", "Rupee gains against dollar in interbank trading today"),
            BriefCard("2", "Rupee gains against the dollar in interbank trading today"),
        ]
        assert len(find_duplicate_events(cards)) == 1

    def test_two_angles_on_one_topic_are_not_duplicates(self):
        cards = [
            BriefCard("1", "PML-N wins six reserved seats, set to form AJK govt"),
            BriefCard("2", "PPP secures two reserved seats in AJK assembly"),
        ]
        assert find_duplicate_events(cards) == []

    def test_containment_is_symmetric_for_the_shorter_card(self):
        long_card = BriefCard("1", "CDF Munir and Naqvi arrive in Tehran for peace talks with Iran")
        short_card = BriefCard("2", "Munir Naqvi Tehran Iran")
        assert len(find_duplicate_events([long_card, short_card])) == 1
        assert len(find_duplicate_events([short_card, long_card])) == 1


class TestClusterQualityMeasure:
    """The measure itself, on cases whose right answer is known by construction."""

    @staticmethod
    def _article(vector, cluster_id):
        return SimpleNamespace(embedding=list(vector), cluster_id=cluster_id)

    @staticmethod
    def _pair():
        """Two unit vectors 0.60 apart - far below the 0.93 event linkage."""
        angle = np.arccos(0.60)
        return np.array([1.0, 0.0]), np.array([np.cos(angle), np.sin(angle)])

    def test_two_events_in_one_cluster_are_counted_as_merged(self):
        near, far = self._pair()
        quality = measure_cluster_quality(
            [
                self._article(near, "c1"),
                self._article(near, "c1"),
                self._article(far, "c1"),
            ]
        )
        assert quality.merged_in == 3
        assert quality.split_apart == 0

    def test_one_event_across_two_clusters_is_counted_as_split(self):
        vector = np.array([1.0, 0.0])
        quality = measure_cluster_quality(
            [self._article(vector, "c1"), self._article(vector, "c2")]
        )
        assert quality.split_apart == 2
        assert quality.merged_in == 0

    def test_a_clean_grouping_scores_zero_on_both(self):
        near, far = self._pair()
        quality = measure_cluster_quality(
            [
                self._article(near, "c1"),
                self._article(near, "c1"),
                self._article(far, "c2"),
                self._article(far, "c2"),
            ]
        )
        assert quality.misplaced == 0
        assert quality.clusters == 2

    def test_too_few_embedded_articles_reports_nothing_rather_than_zero(self):
        assert measure_cluster_quality([]) is None
        assert measure_cluster_quality([SimpleNamespace(embedding=None, cluster_id="c1")]) is None
