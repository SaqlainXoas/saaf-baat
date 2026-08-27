#!/usr/bin/env python3
"""
Derive a golden day's `must_have` list from cross-publisher corroboration.

The problem this solves: `expected.yaml` states what a brief *should* have
contained, and the 2026-08-24 file was drafted by Claude from the headline
list. Recall measured against it therefore means "found everything Claude
guessed mattered" - a number that reads like a quality bar and is actually a
self-assessment.

This script replaces the guess with a fact already present in the fixture:
**how many distinct publishers ran the story**. When dawn, geo, ary, tribune
and brecorder all lead with the same event on the same morning, that is the
Pakistani press corps saying it was one of the day's toplines, and it is
independent of anything the selector does. A brief that misses it has missed
something real.

What it is not: it is not editorial judgement, and it will not catch the
important story only one outlet had. It is a floor, deliberately - the stories
no defensible brief could omit - not a ceiling.

Method
------
1. Replay the day's captured endpoints through the real ingest path, so the
   pool is exactly what the pipeline sees (same parse, same freshness gate,
   same per-source cap). Deriving from the raw payloads instead would demand
   stories the capture truncated away, which is an ingest finding, not a
   selection one - and the harness would be unfalsifiable.
2. Group headlines by content-token containment, using `src.eval.scoring`'s
   own tokeniser so the oracle and the scorer agree on what a token is.
3. Keep groups carried by at least `--min-publishers` distinct sources.
4. Emit keywords from the tokens those publishers *share*, which is the part
   of the story every outlet found worth putting in the headline.

Usage:
    python scripts/derive_expectations.py 2026-08-25 --write
    python scripts/derive_expectations.py 2026-08-24            # diff only
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import yaml  # noqa: E402

from src.eval.golden_day import GOLDEN_DAYS_DIR, GoldenDay, ReplayIngestor  # noqa: E402
from src.eval.scoring import containment, content_tokens  # noqa: E402
from src.utils.urls import canonicalize_url_for_dedup  # noqa: E402

# The pipeline's own locked exclusions, copied from
# `PipelineOrchestrator._passes_hard_gates`. A corroborated story that trips one
# of these belongs in must_not_have, not must_have: every outlet reprinting the
# same wire copy about a cricket result or a bitcoin price is corroboration that
# it was published widely, not that a Pakistani reader needed it. Keeping the
# two lists in step matters - if the product's exclusions change, this must too.
EXCLUDED_CATEGORIES = {"sports", "entertainment"}
EXCLUDED_STORY_TYPES = {"opinion", "advertorial", "sport", "entertainment"}

# Two headlines are the same event when this much of the shorter one's content
# tokens appear in the longer. Same measure the duplicate-event check uses,
# at a lower bar: different outlets word the same story differently, where the
# duplicate check is looking at two cards in one brief.
GROUP_CONTAINMENT = 0.45

# Tokens that carry no event identity. Distinct from the scorer's stopword
# list, which is about sentence glue; these are newsroom furniture that would
# otherwise group unrelated stories together.
_NON_IDENTIFYING = frozenset(
    """pakistan pakistani news update latest report reports says said told
    according government official officials minister ministry president prime
    chief court case man men woman people year years day days today
    yesterday first two three new call calls meeting held during more than
    against also may could would police
    """.split()
)


class Group:
    """One event, and every publisher that ran it."""

    def __init__(self, tokens: set, headline: str, source: str, verdict: Optional[dict]):
        self.tokens = set(tokens)
        self.headlines: List[str] = [headline]
        self.sources: Counter = Counter([source])
        self.token_counts: Counter = Counter(tokens)
        self.verdicts: List[dict] = [verdict] if verdict else []

    def add(self, tokens: set, headline: str, source: str, verdict: Optional[dict]) -> None:
        self.headlines.append(headline)
        self.sources[source] += 1
        self.token_counts.update(tokens)
        if verdict:
            self.verdicts.append(verdict)
        # Union, not intersection: a Tier B outlet's five-word headline would
        # otherwise erode the group's identity down to nothing.
        self.tokens |= tokens

    @property
    def publisher_count(self) -> int:
        return len(self.sources)

    def verdict_bucket(self) -> tuple[str, str]:
        """
        Which list this group belongs in, and why.

        Three answers, not two, and the third one matters:

        * `must_not_have` - it trips one of the pipeline's own hard gates. The
          brief carrying it would be a bug, not a judgement call.
        * `must_have` - it is corroborated *and* triage called it nationally
          relevant. No defensible brief skips a story most of the Pakistani
          press led with and that matters across the country.
        * `editor_call` - corroborated, eligible, but `foreign_with_pk_effect`
          or `local`. Widely reprinted wire copy about a bitcoin price or an
          Indian bond market is exactly this shape: the pipeline is right to
          let it through to the editor, and the editor is right to be allowed
          to drop it. Asserting it either way would be this script inventing
          editorial policy. Reported, never asserted.

        Decided by majority of the group's recorded triage verdicts, so one
        outlet filing a sports story under `national` cannot flip the group.
        """
        if not self.verdicts:
            return "editor_call", "no triage verdict recorded"
        categories = Counter(str(v.get("category") or "") for v in self.verdicts)
        story_types = Counter(str(v.get("story_type") or "") for v in self.verdicts)
        relevance = Counter(str(v.get("pk_relevance") or "") for v in self.verdicts)
        half = len(self.verdicts) / 2

        for tally, excluded, label in (
            (categories, EXCLUDED_CATEGORIES, "category"),
            (story_types, EXCLUDED_STORY_TYPES, "story type"),
        ):
            for value, count in tally.most_common():
                if value in excluded and count > half:
                    return "must_not_have", f"excluded {label} {value}"
        if relevance.get("foreign", 0) > half:
            return "must_not_have", "no Pakistan relevance"
        if relevance.get("national", 0) > half:
            return "must_have", "nationally relevant"
        top = relevance.most_common(1)[0][0] if relevance else "unknown"
        return "editor_call", f"pk_relevance {top} - the editor may take it or leave it"

    def shared_keywords(self, corpus: Counter, corpus_size: int, limit: int = 4) -> List[str]:
        """
        The tokens the group's publishers agreed on, most-agreed first.

        Two failure modes had to be designed around, both seen on real days:

        * Ranking by raw frequency yielded "business", "end", "progress" -
          words half the corpus contains, so `min_keyword_hits: 2` would match
          cards about something else entirely.
        * Filtering everything the corpus is full of threw away "iran", which
          appears in dozens of the day's headlines *because* it is the big
          story. The identifying name of a topline is corpus-common by
          definition.

        So: a token every publisher in the group used is identity and is kept
        whatever the corpus does with it; the corpus cutoff applies only to
        tokens a minority used.
        """
        core_threshold = max(2, (self.publisher_count + 1) // 2)
        common_cutoff = max(6, int(corpus_size * 0.06))

        core, supporting = [], []
        for token, count in self.token_counts.most_common():
            if token in _NON_IDENTIFYING or len(token) <= 2 or token.isdigit():
                continue
            if count >= self.publisher_count:
                core.append(token)
            elif count >= core_threshold:
                (supporting if corpus.get(token, 0) <= common_cutoff else []).append(token)

        return (core + supporting)[:limit]

    def representative(self) -> str:
        """The longest headline: most likely to name every party involved."""
        return max(self.headlines, key=len)


def group_articles(articles: Sequence, verdicts: Dict[str, dict]) -> List[Group]:
    groups: List[Group] = []
    # Longest headline first, so a group forms around a fully-specified
    # headline rather than a wire-stub that happens to be read first.
    for article in sorted(articles, key=lambda a: -len(a.headline or "")):
        tokens = {t for t in content_tokens(article.headline or "") if t not in _NON_IDENTIFYING}
        if len(tokens) < 3:
            continue
        verdict = verdicts.get(canonicalize_url_for_dedup(str(article.url)))
        for group in groups:
            if containment(tokens, group.tokens) >= GROUP_CONTAINMENT:
                group.add(tokens, article.headline, article.source, verdict)
                break
        else:
            groups.append(Group(tokens, article.headline, article.source, verdict))
    return groups


def build_expectations(day: GoldenDay, min_publishers: int) -> Dict[str, List[Dict[str, object]]]:
    """Split corroborated stories into what the brief must carry and must not."""
    result = ReplayIngestor(day).run()
    groups = [
        g
        for g in group_articles(result.articles, day.triage_verdicts)
        if g.publisher_count >= min_publishers
    ]
    groups.sort(key=lambda g: (-g.publisher_count, -len(g.headlines)))

    # How many headlines in the whole day contain each token. Used to prefer
    # distinctive keywords over words the corpus is full of.
    corpus: Counter = Counter()
    for article in result.articles:
        corpus.update(content_tokens(article.headline or ""))

    buckets: Dict[str, List[Dict[str, object]]] = {
        "must_have": [],
        "must_not_have": [],
        "editor_call": [],
    }
    seen_ids: set = set()
    for group in groups:
        keywords = group.shared_keywords(corpus, len(result.articles))
        if len(keywords) < 2:
            # Nothing the publishers agreed on is a group held together by
            # coincidence. Better to drop it than to assert it.
            continue
        entry_id = "-".join(keywords[:3])
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        publishers = ", ".join(sorted(group.sources))
        bucket, reason = group.verdict_bucket()
        buckets[bucket].append(
            {
                "id": entry_id,
                "description": (
                    f"{group.representative()} "
                    f"Carried by {group.publisher_count} publishers: {publishers}. "
                    f"Triage: {reason}."
                ),
                "keywords": keywords,
                # Two hits keeps a single common word from matching a card
                # about something else entirely.
                "min_keyword_hits": 2,
                "publisher_count": group.publisher_count,
            }
        )
    return buckets


HEADER = """\
# What the brief for {day} should have contained.
#
# DERIVED, NOT JUDGED. Every entry below is a story that at least
# {min_publishers} distinct publishers in the captured pool ran on this
# morning - a fact recorded in the fixture, measured by
# `scripts/derive_expectations.py`, and independent of anything the selector
# does. It is not an editor's opinion about what mattered.
#
# Read that honestly in both directions:
#   * A missed must-have is real. Most of the Pakistani press led with it and
#     the brief did not carry it.
#   * A perfect score is a floor, not a ceiling. This method cannot see the
#     important story only one outlet had, and it will include a wire story
#     everyone reprinted without anyone thinking it was important.
#
# Regenerate with:
#     python scripts/derive_expectations.py {day} --write
#
# It must not be edited to make a failing run pass. If a run misses an entry
# here, that is a selection bug to fix, not a line to delete.
"""


def _clean(entries: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return [
        {
            "id": entry["id"],
            "description": entry["description"],
            "keywords": list(entry["keywords"]),
            "min_keyword_hits": entry["min_keyword_hits"],
        }
        for entry in entries
    ]


def render_yaml(day_name: str, derived: Dict[str, List[Dict[str, object]]], existing: Dict, min_publishers: int) -> str:
    body = {
        "day": day_name,
        "must_have": _clean(derived["must_have"]),
        "must_not_have": _clean(derived["must_not_have"]),
        "brief_size": existing.get("brief_size") or {"min": 10, "max": 12},
        "baseline_recall": existing.get("baseline_recall"),
    }
    if existing.get("expected_quarantine"):
        body["expected_quarantine"] = existing["expected_quarantine"]

    header = HEADER.format(day=day_name, min_publishers=min_publishers)
    return header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=88)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("day", help="Golden day directory name, e.g. 2026-08-25")
    parser.add_argument("--min-publishers", type=int, default=3)
    parser.add_argument("--write", action="store_true", help="Overwrite expected.yaml.")
    args = parser.parse_args(argv)

    path = GOLDEN_DAYS_DIR / args.day
    if not path.exists():
        print(f"No such golden day: {path}")
        return 1

    day = GoldenDay.load(path)
    derived = build_expectations(day, args.min_publishers)

    total = sum(len(v) for v in derived.values())
    print(f"GOLDEN DAY {args.day}: {total} stories carried by >= {args.min_publishers} publishers\n")
    for label, key in (
        ("MUST HAVE", "must_have"),
        ("MUST NOT HAVE", "must_not_have"),
        ("EDITOR'S CALL (reported, not asserted)", "editor_call"),
    ):
        print(f"{label} ({len(derived[key])}):")
        for entry in derived[key]:
            print(f"  [{entry['publisher_count']} pubs] {entry['id']}")
            print(f"      {entry['description'][:130]}")
            print(f"      keywords: {entry['keywords']}")
        print()

    existing = day.expectations or {}
    prior_ids = {str(item.get("id")) for item in (existing.get("must_have") or [])}
    new_ids = {str(entry["id"]) for entry in derived["must_have"]}
    if prior_ids:
        print("\nDiff against the existing file:")
        print(f"  kept by both  : {len(prior_ids & new_ids)}")
        for lost in sorted(prior_ids - new_ids):
            print(f"  only in file  : {lost}")
        for gained in sorted(new_ids - prior_ids):
            print(f"  only in oracle: {gained}")

    if args.write:
        target = path / "expected.yaml"
        target.write_text(render_yaml(args.day, derived, existing, args.min_publishers), encoding="utf-8")
        print(f"\nWrote {target}")
    else:
        print("\n(dry run - pass --write to update expected.yaml)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
