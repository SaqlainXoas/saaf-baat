"""Promote this workflow's validated drafts and share heartbeat with Render."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_run_health import heartbeat_path  # noqa: E402

from src.db.factory import create_db_client  # noqa: E402


def publish(db, token: str, heartbeat: dict) -> int:
    stats = heartbeat.get("stats", {})
    if not token or os.getenv("SAAF_STAGE_PUBLICATION") != "1":
        raise ValueError("Hosted publication requires staged mode and a run token")
    if any(stats.get(key) != "ok" for key in ("embedding_status", "triage_status", "editorial_status")):
        raise ValueError("Required pipeline stages did not succeed")
    if stats.get("analyze_failures", 0):
        raise ValueError("An edition with failed card writes cannot be published")
    count = int(stats.get("feeds_inserted", 0))
    if not 1 <= count <= 12:
        raise ValueError("Edition must contain 1–12 grounded cards")
    heartbeat = {**heartbeat, "stats": {**stats, "publication_status": "ok"}}
    return db.client.rpc("publish_brief", {
        "publication_token": token, "expected_cards": count, "heartbeat": heartbeat,
    }).execute().data


def notify_frontend() -> None:
    """Swap the cached edition on Vercel for the one just published.

    The page is served from Vercel's cache so a reader never waits on a sleeping
    Render instance; without this ping a new edition would sit behind the
    revalidate window. Best effort on purpose: the brief is already committed by
    the time this runs, so a failed ping must not fail the workflow — it only
    costs freshness until the window lapses.
    """
    url = os.getenv("SAAF_REVALIDATE_URL", "").strip()
    secret = os.getenv("SAAF_REVALIDATE_SECRET", "").strip()
    if not url or not secret:
        print("Revalidation not configured; cached edition refreshes on its own")
        return
    request = urllib.request.Request(
        url,
        data=json.dumps({"tags": ["feed", "story"]}).encode(),
        headers={"Content-Type": "application/json", "x-revalidate-secret": secret},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"Revalidated the published edition (HTTP {response.status})")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"Warning: could not revalidate the frontend cache: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure", action="store_true")
    args = parser.parse_args()
    if os.getenv("SAAF_DB_BACKEND") != "supabase":
        raise ValueError("Hosted publishing requires Supabase")
    db = create_db_client()
    heartbeat = json.loads(heartbeat_path().read_text())
    if args.failure:
        # A failed job must not advance the last successful publication time.
        previous = db.client.table("pipeline_state").select("payload").eq("id", "daily").limit(1).execute().data
        heartbeat["last_successful_run_at"] = previous[0]["payload"].get("last_successful_run_at") if previous else None
        heartbeat.setdefault("stats", {})["publication_status"] = "failed"
        db.client.table("pipeline_state").upsert({"id": "daily", "payload": heartbeat}).execute()
        print("Recorded failed run; previous edition retained")
    else:
        count = publish(db, os.environ["SAAF_PUBLICATION_TOKEN"], heartbeat)
        print(f"Published {count} cards atomically")
        notify_frontend()


if __name__ == "__main__":
    main()
