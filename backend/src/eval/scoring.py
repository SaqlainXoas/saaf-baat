"""
Scoring a produced brief against a hand-written expectation of the day.

The question this answers is not "did the pipeline run" but "does this set of
cards look like today's real Pakistan toplines". That judgement is human, so it
is written down once per golden day in `expected.yaml`; this module only
measures a brief against it.

Matching is deliberately crude — keyword hits against headline and summary.
A cleverer matcher would be a second thing to debug when the brief regresses,
and would tempt the harness into scoring wording instead of coverage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_MIN_KEYWORD_HITS = 2
# Two cards are the same event when the shorter one's content words are almost
# entirely contained in the longer one.
DUPLICATE_CONTAINMENT_THRESHOLD = 0.75
# Half the impact line already said in the headline is a restatement.
RESTATEMENT_THRESHOLD = 0.5

# Enough to stop "the", "a", "of" dominating a seven-word headline.
_STOPWORDS = frozenset(
    """a an and as at be by for from has have in is it its of on or that the
    to was were will with after amid over into up down out new says said""".split()
)

# A diagnostic, never a gate. Two failure modes were visible in live output:
# an impact line that paraphrases the headline, and one that names nothing a
# reader can act on - "Violent crime incidents highlight ongoing security
# challenges in local districts." The second is measured as the absence of a
# concrete anchor: a number, a price, a unit, a named day, or a specific
# consequence. Deliberately one short list rather than a hedge-word list too:
# a compound heuristic here would be a scoring tower, which is what Phase 4
# deleted, and this only exists to point a human at cards worth reading.
_CONCRETE_WORDS = frozenset(
    """tomorrow tonight monday tuesday wednesday thursday friday saturday
    sunday rupees rupee paisa litre litres kilo kilos kg percent deadline
    closed closure shut shuts reopen reopens suspended cancelled queue queues
    blocked diverted strike outage blackout delay delays detour detours
    shortage rationing refund fine fines penalty permit"""
    .split()
)


# Reported, never gated. A proposal honestly described as a proposal is a
# legitimate hedge; eight of them in one brief is a candidate-pool problem.
_HEDGE_RE = re.compile(
    r"\b(?:may|might|could|potential|potentially|possible|possibly|expected to|"
    r"set to|likely|would)\b",
    re.IGNORECASE,
)
_STOCK_TEMPLATE_RE = re.compile(r"^[^.]{0,60}?\bfaces?\b", re.IGNORECASE)


def _has_concrete_anchor(text: str) -> bool:
    normalized = normalize(text)
    if any(char.isdigit() for char in normalized):
        return True
    if "%" in text or "rs" in normalized.split():
        return True
    return bool(set(normalized.split()) & _CONCRETE_WORDS)


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())


@dataclass(frozen=True)
class Expectation:
    """One story the brief should — or should not — contain."""

    id: str
    keywords: Sequence[str]
    description: str = ""
    min_keyword_hits: int = DEFAULT_MIN_KEYWORD_HITS

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Expectation":
        keywords = [str(k) for k in (raw.get("keywords") or [])]
        return cls(
            id=str(raw.get("id") or (keywords[0] if keywords else "unnamed")),
            keywords=keywords,
            description=str(raw.get("description") or ""),
            min_keyword_hits=int(raw.get("min_keyword_hits") or DEFAULT_MIN_KEYWORD_HITS),
        )

    def hits(self, text: str) -> List[str]:
        haystack = normalize(text)
        return [kw for kw in self.keywords if normalize(kw).strip() in haystack]

    def matches(self, text: str) -> bool:
        required = min(self.min_keyword_hits, len(self.keywords)) or 1
        return len(self.hits(text)) >= required


@dataclass(frozen=True)
class BriefCard:
    """The part of a published story this harness looks at."""

    cluster_id: str
    headline: str
    summary: str = ""
    impact_line: str = ""

    @property
    def text(self) -> str:
        return f"{self.headline} {self.summary}".strip()

    @property
    def impact_restates_headline(self) -> float:
        """How much of the impact line is already in the headline, 0 to 1."""
        impact = content_tokens(self.impact_line)
        if not impact:
            return 0.0
        return len(impact & content_tokens(self.headline)) / len(impact)

    @property
    def impact_is_hedged(self) -> bool:
        """Says something might happen rather than that something has."""
        return bool(_HEDGE_RE.search(self.impact_line))

    @property
    def impact_follows_the_stock_template(self) -> bool:
        """`<people> face <thing>` - accurate, and identical on every card.

        Eight cards built from one sentence shape read as a machine however
        true each line is. Counted so a prompt change can be measured against
        it instead of eyeballed.
        """
        return bool(_STOCK_TEMPLATE_RE.search(self.impact_line))

    @property
    def impact_lacks_anchor(self) -> bool:
        """Names nothing a reader can act on: no number, price, day or effect."""
        if not self.impact_line.strip():
            return False
        return not _has_concrete_anchor(self.impact_line)

    @classmethod
    def from_feed(cls, feed: Any) -> "BriefCard":
        metadata = getattr(feed, "metadata", None) or {}
        impact = ""
        if isinstance(metadata, dict):
            impact = str(metadata.get("why_it_matters") or metadata.get("impact_line") or "")
        return cls(
            cluster_id=str(getattr(feed, "cluster_id", "")),
            headline=str(getattr(feed, "headline", "") or ""),
            summary=str(getattr(feed, "summary", "") or ""),
            impact_line=impact,
        )


@dataclass(frozen=True)
class DuplicatePair:
    left: str
    right: str
    overlap: float


@dataclass
class GoldenDayReport:
    day: str
    cards: List[BriefCard] = field(default_factory=list)
    matched: List[str] = field(default_factory=list)
    missed: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    duplicates: List[DuplicatePair] = field(default_factory=list)
    size_min: int = 0
    size_max: int = 0
    baseline_recall: Optional[float] = None
    # Set by `run_golden_day`; None when the day has too few embedded articles
    # to measure. Reported, never gated - see `measure_cluster_quality`.
    cluster_quality: Optional[Any] = None

    @property
    def brief_size(self) -> int:
        return len(self.cards)

    @property
    def has_expectations(self) -> bool:
        """Has a human written down what this day should have contained?

        A day with no must-haves scores 100% by arithmetic, which reads as a
        pass and is worth nothing. Saying so is the whole point of the file.
        """
        return bool(self.matched or self.missed)

    @property
    def recall(self) -> float:
        total = len(self.matched) + len(self.missed)
        if total == 0:
            return 1.0
        return len(self.matched) / total

    @property
    def size_in_range(self) -> bool:
        return self.size_min <= self.brief_size <= self.size_max

    @property
    def cards_with_impact_lines(self) -> List[BriefCard]:
        return [card for card in self.cards if card.impact_line.strip()]

    @property
    def restating_impact_lines(self) -> List[BriefCard]:
        return [
            card
            for card in self.cards_with_impact_lines
            if card.impact_restates_headline >= RESTATEMENT_THRESHOLD
        ]

    @property
    def unquantified_impact_lines(self) -> List[BriefCard]:
        return [card for card in self.cards_with_impact_lines if card.impact_lacks_anchor]

    @property
    def hedged_impact_lines(self) -> List[BriefCard]:
        return [card for card in self.cards_with_impact_lines if card.impact_is_hedged]

    @property
    def templated_impact_lines(self) -> List[BriefCard]:
        return [
            card
            for card in self.cards_with_impact_lines
            if card.impact_follows_the_stock_template
        ]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "brief_size": self.brief_size,
            "size_range": [self.size_min, self.size_max],
            "size_in_range": self.size_in_range,
            "has_expectations": self.has_expectations,
            "recall": round(self.recall, 3) if self.has_expectations else None,
            "baseline_recall": self.baseline_recall,
            "matched": list(self.matched),
            "missed": list(self.missed),
            "violations": list(self.violations),
            "duplicates": [
                {"left": pair.left, "right": pair.right, "overlap": round(pair.overlap, 3)}
                for pair in self.duplicates
            ],
            "impact_lines": len(self.cards_with_impact_lines),
            "impact_lines_restating_headline": len(self.restating_impact_lines),
            "impact_lines_without_a_number": len(self.unquantified_impact_lines),
            "impact_lines_hedged": len(self.hedged_impact_lines),
            "impact_lines_templated": len(self.templated_impact_lines),
        }

    def format(self) -> str:
        lines = [
            f"GOLDEN DAY: {self.day}",
            "=" * 72,
            f"brief size      : {self.brief_size} (expected {self.size_min}-{self.size_max})"
            f"{'' if self.size_in_range else '   <-- OUT OF RANGE'}",
            (
                f"topline recall  : {self.recall:.0%} "
                f"({len(self.matched)}/{len(self.matched) + len(self.missed)})"
                + (f"   baseline {self.baseline_recall:.0%}" if self.baseline_recall is not None else "")
            )
            if self.has_expectations
            else "topline recall  : NOT MEASURED - expected.yaml has no must_have "
                 "entries, so this day scores nothing",
            "",
            "matched must-haves:",
        ]
        lines += [f"  + {name}" for name in self.matched] or ["  (none)"]
        lines += ["", "MISSED must-haves:"]
        lines += [f"  - {name}" for name in self.missed] or ["  (none)"]
        lines += ["", "must-not-have VIOLATIONS:"]
        lines += [f"  ! {name}" for name in self.violations] or ["  (none)"]
        lines += ["", "duplicate events:"]
        lines += [
            f"  = {pair.left[:40]} ~ {pair.right[:40]} ({pair.overlap:.2f})"
            for pair in self.duplicates
        ] or ["  (none)"]
        if self.cards_with_impact_lines:
            total = len(self.cards_with_impact_lines)
            lines += [
                "",
                "impact lines (a tuning signal, not a verdict - a good line can "
                "still carry no number):",
                f"  restating the headline      : {len(self.restating_impact_lines)}/{total}",
                f"  no number, price or named day: {len(self.unquantified_impact_lines)}/{total}",
                f"  hedged (may/could/potential) : {len(self.hedged_impact_lines)}/{total}",
                f"  stock '<people> face <thing>': {len(self.templated_impact_lines)}/{total}",
            ]
        if self.cluster_quality is not None:
            quality = self.cluster_quality
            lines += [
                "",
                "grouping (articles put in the wrong group - reported, not gated):",
                f"  merged into a blob : {quality.merged_in}"
                "   <- a story the editor never sees as a candidate",
                f"  split across groups: {quality.split_apart}"
                "   <- one story arriving as two candidates",
                f"  clusters           : {quality.clusters}",
            ]
        lines += ["", "cards:"]
        for index, card in enumerate(self.cards):
            lines.append(f"  {index + 1:>2}. {card.headline[:66]}")
            if card.impact_line:
                lines.append(f"      {card.impact_line[:70]}")
        return "\n".join(lines)


def content_tokens(text: str) -> set:
    return {word for word in normalize(text).split() if word and word not in _STOPWORDS}


def containment(left: set, right: set) -> float:
    """
    How much of the smaller set the larger one already covers.

    Containment rather than Jaccard because card text is a headline plus a
    sentence: the pipeline's body-level shingle threshold is tuned for a
    thousand characters, and on short text a single inserted word moves it far
    more than it should. "Rupee gains against dollar" and "Rupee gains against
    the dollar" are the same event, and containment says so.
    """
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def find_duplicate_events(
    cards: Sequence[BriefCard],
    threshold: float = DUPLICATE_CONTAINMENT_THRESHOLD,
) -> List[DuplicatePair]:
    """Report card pairs that describe the same event."""
    tokens = [content_tokens(card.text) for card in cards]
    pairs: List[DuplicatePair] = []
    for left in range(len(cards)):
        for right in range(left + 1, len(cards)):
            overlap = containment(tokens[left], tokens[right])
            if overlap >= threshold:
                pairs.append(
                    DuplicatePair(
                        left=cards[left].headline,
                        right=cards[right].headline,
                        overlap=overlap,
                    )
                )
    return pairs


def score_brief(
    cards: Sequence[BriefCard],
    expectations: Dict[str, Any],
    *,
    day: str = "",
) -> GoldenDayReport:
    """Measure a produced brief against one day's written expectations."""
    must_have = [Expectation.from_dict(row) for row in (expectations.get("must_have") or [])]
    must_not_have = [
        Expectation.from_dict(row) for row in (expectations.get("must_not_have") or [])
    ]
    size = expectations.get("brief_size") or {}

    corpus = [card.text for card in cards]

    matched, missed = [], []
    for expectation in must_have:
        if any(expectation.matches(text) for text in corpus):
            matched.append(expectation.id)
        else:
            missed.append(expectation.id)

    violations = [
        expectation.id
        for expectation in must_not_have
        if any(expectation.matches(text) for text in corpus)
    ]

    return GoldenDayReport(
        day=day or str(expectations.get("day") or ""),
        cards=list(cards),
        matched=matched,
        missed=missed,
        violations=violations,
        duplicates=find_duplicate_events(cards),
        size_min=int(size.get("min", 0)),
        size_max=int(size.get("max", 0)),
        baseline_recall=(
            float(expectations["baseline_recall"])
            if expectations.get("baseline_recall") is not None
            else None
        ),
    )
