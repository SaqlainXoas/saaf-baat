"""
Score the brief the pipeline produces for a recorded news day.

    python scripts/eval_golden_day.py                 # every captured day
    python scripts/eval_golden_day.py --day 2026-08-24
    python scripts/eval_golden_day.py --json report.json

    python scripts/eval_golden_day.py --live-editorial

Offline and deterministic by default: no network, no API keys. Turns "does the
brief feel right?" — currently a manual QA pass done days later — into something
runnable in seconds, which is what makes later selection changes measurable.

`--live-editorial` replays the same recorded day but calls the real editor, so
the run scores the path production actually ships, including the card copy.
That needs API keys and costs two or three LLM calls. Because the editor is
nondeterministic, that mode reports its numbers and never fails the build: the
`baseline_recall` ratchet belongs to the offline run alone.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from src.eval.golden_day import GoldenDay, available_days, run_golden_day  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the golden-day evaluation")
    parser.add_argument("--day", default=None, help="Fixture name (default: all captured days)")
    parser.add_argument("--json", default=None, help="Write the full report as JSON")
    parser.add_argument(
        "--live-editorial",
        action="store_true",
        help="Call the real editor over the recorded day (needs API keys; reports, never gates)",
    )
    args = parser.parse_args()

    if args.live_editorial:
        from dotenv import load_dotenv

        load_dotenv(_BACKEND_DIR / ".env")

    days = available_days()
    if args.day:
        days = [path for path in days if path.name == args.day]
    if not days:
        print("No golden days captured. Run scripts/capture_golden_day.py first.")
        return 1

    reports = []
    failures = 0
    unreviewed: list[str] = []
    for path in days:
        day = GoldenDay.load(path)
        with tempfile.TemporaryDirectory() as tmp:
            report, stats = run_golden_day(
                day,
                db_path=Path(tmp) / "golden.db",
                live_editorial=args.live_editorial,
            )

        print(report.format())
        print()
        print(
            f"pipeline: discovered={stats.scraped} inserted={stats.inserted} "
            f"clusters={stats.clusters_created} feeds={stats.feeds_inserted}"
            + (
                f" editorial={stats.editorial_status}"
                f" story_analysis={stats.story_analysis_status}"
                f" (calls={stats.story_analysis_calls}"
                f" ok={stats.story_analysis_successes}"
                f" q_rejected={stats.story_analysis_question_rejections}"
                f" fallback={stats.story_analysis_fallbacks}"
                f" failed={stats.story_analysis_failures})"
                if args.live_editorial
                else ""
            )
        )
        if not args.live_editorial:
            # Say it on every run. A future session must not read this pass as
            # covering story analysis; only --live-editorial exercises it.
            print("  NOTE: story analysis is not exercised offline - run with --live-editorial.")
        # A fixture with no adjudication.json replays with adjudication fully
        # disabled: RecordedAdjudicator answers nothing and every ambiguous pair
        # falls through to the deterministic split. That is a grouping path
        # production does not use, so the grouping numbers above are measured
        # against a weaker grouper than the live one - say so rather than let a
        # silently-degraded harness look healthy.
        if getattr(stats, "adjudication_failures", 0):
            print(
                f"  NOTE: {stats.adjudication_failures} ambiguous pairs went unadjudicated "
                "- this fixture has no adjudication.json, so grouping above is measured "
                "with adjudication OFF (live runs merge some of these)."
            )
        print()
        reports.append(report.as_dict())

        if args.live_editorial:
            # A nondeterministic editor cannot gate a build, and under the
            # no-padding rule a short brief is a correct outcome, not a
            # failure. Read the numbers; do not ratchet on them.
            continue

        if not report.has_expectations:
            # Not a failure - the fixture is captured and replaying. But it
            # cannot measure anything until a human writes down what that day
            # should have contained, and a vacuous 100% must not read as a pass.
            unreviewed.append(day.name)

        if report.violations or report.duplicates or not report.size_in_range:
            failures += 1
        if report.baseline_recall is not None and report.recall < report.baseline_recall:
            failures += 1

    if unreviewed:
        print(
            "NEEDS A HUMAN READ: "
            + ", ".join(f"tests/fixtures/golden_days/{name}/expected.yaml" for name in unreviewed)
        )
        print("  Until must_have is written, these days replay but score nothing.")
        print()

    if args.json:
        Path(args.json).write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
        print(f"written: {args.json}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
