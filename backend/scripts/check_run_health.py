#!/usr/bin/env python3
"""
Read the pipeline heartbeat and exit non-zero if the run degraded.

A pipeline run that finishes without crashing is not the same as a run that
published a brief. Since 2026-08-25 the orchestrator records whether each LLM
stage actually ran (`embedding_status`, `triage_status`, `editorial_status`),
precisely so a silently empty run cannot look like a success. Nothing acted on
those fields outside `/health`, so a scheduled run that triaged nothing still
finished green.

This is the "degrade loudly" rule applied to CI: a red job is the signal.
Run it after `run_pipeline.py`, in the same working directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

# The three stages that can be unavailable without the process failing.
STATUS_FIELDS = ("embedding_status", "triage_status", "editorial_status")


def heartbeat_path() -> Path:
    env_path = (os.getenv("SAAF_PIPELINE_HEARTBEAT_FILE") or "").strip()
    if not env_path:
        return BACKEND_DIR / ".pipeline_heartbeat.json"
    path = Path(env_path)
    return path if path.is_absolute() else BACKEND_DIR.parent / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-cards",
        type=int,
        default=1,
        help="Fail when fewer than this many cards were published (default: 1).",
    )
    parser.add_argument(
        "--allow-degraded-sources",
        action="store_true",
        help="Report quarantined endpoints without failing on them.",
    )
    args = parser.parse_args(argv)

    path = heartbeat_path()
    try:
        heartbeat = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL  no readable heartbeat at {path}: {exc}")
        return 1

    stats = dict(heartbeat.get("stats") or {})
    failures: list[str] = []

    for field in STATUS_FIELDS:
        value = str(stats.get(field) or "unknown")
        marker = "ok  " if value == "ok" else "FAIL"
        print(f"{marker}  {field} = {value}")
        if value != "ok":
            failures.append(f"{field} is {value!r}, not 'ok'")

    cards = int(stats.get("feeds_inserted") or 0)
    print(f"{'ok  ' if cards >= args.min_cards else 'FAIL'}  cards published = {cards}")
    if cards < args.min_cards:
        failures.append(f"published {cards} cards, expected at least {args.min_cards}")
    if cards and cards < 6:
        print(f"note  short brief reason = {stats.get('short_brief_reason') or 'not recorded'}")
    cluster_failures = int(stats.get("cluster_failures") or 0)
    if cluster_failures:
        failures.append(f"{cluster_failures} cluster write or assignment failures")
    print(
        "note  processing unresolved: embeddings=%d triage=%d; "
        "candidates=%d eligible=%d selected=%d" % (
            int(stats.get("embedding_unresolved") or 0),
            int(stats.get("triage_unresolved") or 0),
            int(stats.get("candidates_analyzed") or 0),
            int(stats.get("candidates_publishable") or 0),
            int(stats.get("editorial_selected") or 0),
        )
    )

    # Reported either way: a quarantined endpoint is normal on some days and a
    # real outage on others, and the difference is not mechanical.
    degraded = [str(s) for s in list(heartbeat.get("degraded_sources") or [])]
    if degraded:
        print(f"note  degraded sources: {', '.join(degraded)}")
        if not args.allow_degraded_sources and len(degraded) >= 4:
            failures.append(f"{len(degraded)} sources quarantined: {', '.join(degraded)}")

    if failures:
        print("\nRun degraded:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nRun healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
