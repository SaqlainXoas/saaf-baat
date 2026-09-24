"""Promote this workflow's validated drafts and share heartbeat with Render."""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_run_health import heartbeat_path  # noqa: E402

from src.db.factory import create_db_client  # noqa: E402


def _execute(db, build):
    retry = getattr(db, "_execute_retryable", None)
    return retry(build) if callable(retry) else build().execute()


def publish(db, token: str, heartbeat: dict) -> int:
    stats = heartbeat.get("stats", {})
    if not token or os.getenv("SAAF_STAGE_PUBLICATION") != "1":
        raise ValueError("Hosted publication requires staged mode and a run token")
    if any(stats.get(key) != "ok" for key in ("embedding_status", "triage_status", "editorial_status")):
        raise ValueError("Required pipeline stages did not succeed")
    if stats.get("analyze_failures", 0) or stats.get("cluster_failures", 0):
        raise ValueError("An edition with failed cluster or card writes cannot be published")
    count = int(stats.get("feeds_inserted", 0))
    if not 1 <= count <= 12:
        raise ValueError("Edition must contain 1–12 grounded cards")
    published_at = datetime.now(timezone.utc).isoformat()
    heartbeat = {
        **heartbeat,
        "last_successful_run_at": published_at,
        "stats": {**stats, "publication_status": "ok"},
    }
    return _execute(db, lambda: db.client.rpc("publish_brief", {
        "publication_token": token, "expected_cards": count, "heartbeat": heartbeat,
    })).data


def publication_drafts(db, token: str) -> list[dict]:
    """Only drafts belonging to this exact attempt may be resumed."""
    rows = _execute(db, lambda: db.client.table("analyzed_feed")
            .select("id,cluster_id,created_at,metadata,is_published")
            .eq("metadata->>publication_token", token)
            ).data
    return list(rows or [])


def record_failed_run(db, heartbeat: dict) -> None:
    previous = _execute(db, lambda: db.client.table("pipeline_state")
                        .select("payload").eq("id", "daily").limit(1)).data
    standing = previous[0]["payload"] if previous else {}
    # A warm/cache failure after the RPC must never mark a published edition failed.
    if (standing.get("publication_token") == heartbeat.get("publication_token")
            and (standing.get("stats") or {}).get("publication_status") == "ok"):
        return
    heartbeat["last_successful_run_at"] = standing.get("last_successful_run_at")
    heartbeat.setdefault("stats", {})["publication_status"] = "failed"
    _execute(db, lambda: db.client.table("pipeline_state")
             .upsert({"id": "daily", "payload": heartbeat}))


def wake_backend() -> None:
    """Get Render answering before Vercel is told to re-render.

    Render Free spins down after ~15 minutes idle, and nothing else sends it
    traffic: this pipeline writes straight to Supabase and never calls the API.
    So the revalidation below reliably woke a *sleeping* instance, and the
    frontend abandons a backend fetch after 25 seconds - less than a cold boot.
    Vercel then cached "Unable to load brief", Render finished waking with
    nobody asking, and idled back to sleep. The site was in that state on
    2026-09-13 and again on 2026-09-14 while Supabase, the pipeline and the API
    itself were all healthy; holding Render awake by hand was enough to make the
    very next revalidation render the brief correctly.

    Best effort, like the ping it precedes: the edition is already committed, so
    a backend that will not wake costs freshness, never the run.
    """
    url = os.getenv("SAAF_BACKEND_HEALTH_URL", "").strip()
    if not url:
        print("Backend health URL not configured; revalidating without waking Render")
        return
    deadline = time.monotonic() + 120
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                if response.status == 200:
                    print(f"Backend awake after {attempt} attempt(s)")
                    return
                print(f"Backend answered HTTP {response.status}; retrying")
        except (urllib.error.URLError, OSError) as exc:
            print(f"Backend not awake yet (attempt {attempt}): {exc}")
        time.sleep(5)
    print("Warning: backend did not wake in time; revalidating anyway")


def notify_frontend() -> None:
    """Swap the cached edition on Vercel for the one just published.

    Call `wake_backend` first. Re-rendering the page makes Vercel fetch the API,
    and if that fetch times out the *error* state is what gets cached - which is
    strictly worse than the stale edition this ping was meant to replace.

    Best effort on purpose: the brief is already committed by the time this
    runs, so a failed ping must not fail the workflow — it only costs freshness
    until the window lapses.
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


def published_stories(db, token: str) -> list[dict]:
    """The cards this run just promoted, for the warm step to check against.

    Best effort: without them the warm still rebuilds the home page, it just
    cannot prove the new edition is what Vercel serves.
    """
    try:
        rows = (
            db.client.table("analyzed_feed")
            .select("cluster_id, headline")
            .eq("metadata->>publication_token", token)
            .eq("is_published", True)
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001 - the edition is already committed
        print(f"::warning::Could not list the published stories to warm: {exc}")
        return []
    return [
        {"id": str(row["cluster_id"]), "headline": str(row.get("headline") or "")}
        for row in rows or []
        if row.get("cluster_id")
    ]


# Revalidating serves the old page once more while Vercel rebuilds it in the
# background, so the first request after the ping is expected to be stale.
# Six tries fifteen seconds apart outlast a rebuild that has to wake Render.
WARM_ATTEMPTS = 6
WARM_RETRY_SECONDS = 15
WARM_REQUEST_TIMEOUT = 90
# The whole warm - home page and every story page - must end inside this.
# Unbounded, 13 pages x 6 attempts x (90s + 15s) is over two hours; the daily
# workflow is killed at 45 minutes and its slowest recent run took 22. A job
# killed here would also run "Record failed run" and mark an edition that is
# already published as failed. So the warm stops and warns instead.
WARM_BUDGET_SECONDS = 480


def _get_page(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "saaf-baat-pipeline/cache-warm"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, html.unescape(response.read().decode("utf-8", "replace"))


def _warm_until(url: str, label: str, is_current, deadline: float) -> bool:
    reason = "no attempt made"
    for attempt in range(1, WARM_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            print(f"::warning::could not warm {label}: warm budget of {WARM_BUDGET_SECONDS}s spent ({reason})")
            return False
        started = time.monotonic()
        try:
            status, body = _get_page(url, min(WARM_REQUEST_TIMEOUT, remaining))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            reason = str(exc)
        else:
            if status == 200 and is_current(body):
                elapsed = time.monotonic() - started
                print(f"Warmed {label} (attempt {attempt}, {elapsed:.1f}s)")
                return True
            reason = f"HTTP {status} but still the previous content"
        if attempt < WARM_ATTEMPTS:
            print(f"{label} not current yet (attempt {attempt}): {reason}; retrying")
            time.sleep(max(0.0, min(WARM_RETRY_SECONDS, deadline - time.monotonic())))
    print(f"::warning::could not warm {label} after {WARM_ATTEMPTS} attempts: {reason}")
    return False


def warm_frontend_cache(stories: list[dict] | None = None) -> bool:
    """Rebuild the cached pages now, and check they serve the new edition.

    Revalidating empties Vercel's cache; it does not refill it. Overnight that
    leaves nothing to serve: the run finishes around 06:20, Render idles back to
    sleep fifteen minutes later, and the first reader of the morning arrives to
    an empty cache and a sleeping API. Vercel has to build the page on the spot,
    which means waking Render while the reader waits - half a minute or more,
    staring at a loading page, for a brief that was ready hours earlier.

    So the run pays that cost itself, here, one request after `wake_backend`
    while everything is still up. The page is rebuilt and cached, and the
    morning's first reader gets it in a fraction of a second like everyone else.

    One request was not enough. Right after a revalidation Vercel serves the
    old home page once more while it rebuilds, so a single 200 proved nothing;
    and story pages were never warmed at all, so the lead story - the one every
    reader opens first - was built by a reader. On 2026-09-15 that build hit a
    transient 503 and the lead story sat on an error page. So the home page is
    retried until it links every published story, and each story page until it
    carries its own headline - all inside `WARM_BUDGET_SECONDS`.

    Best effort, like the ping before it: the edition is already published, so
    a failed warm is a visible warning in the run, never a failed run.
    """
    revalidate_url = os.getenv("SAAF_REVALIDATE_URL", "").strip()
    if not revalidate_url:
        print("No site URL to warm; the first reader will rebuild the page")
        return False
    parsed = urllib.parse.urlsplit(revalidate_url)
    if not parsed.scheme or not parsed.netloc:
        print("Could not read a site origin from SAAF_REVALIDATE_URL; skipping warm")
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}/"
    stories = stories or []
    deadline = time.monotonic() + WARM_BUDGET_SECONDS

    ok = _warm_until(
        origin,
        "the home page",
        lambda body: all(f"/stories/{story['id']}" in body for story in stories),
        deadline,
    )
    for index, story in enumerate(stories):
        if deadline - time.monotonic() <= 1:
            skipped = len(stories) - index
            print(
                f"::warning::warm budget of {WARM_BUDGET_SECONDS}s spent; "
                f"{skipped} story page(s) left for readers to build"
            )
            return False
        headline = story["headline"]
        ok = _warm_until(
            f"{origin}stories/{story['id']}",
            f"story {story['id']}",
            lambda body, headline=headline: headline in body,
            deadline,
        ) and ok
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure", action="store_true")
    args = parser.parse_args()
    if os.getenv("SAAF_DB_BACKEND") != "supabase":
        raise ValueError("Hosted publishing requires Supabase")
    db = create_db_client()
    heartbeat = json.loads(heartbeat_path().read_text())
    if args.failure:
        record_failed_run(db, heartbeat)
        print("Recorded failed run; previous edition retained")
    else:
        token = os.environ["SAAF_PUBLICATION_TOKEN"]
        count = publish(db, token, heartbeat)
        print(f"Published {count} cards atomically")
        stories = published_stories(db, token)
        wake_backend()
        notify_frontend()
        warm_frontend_cache(stories)


if __name__ == "__main__":
    main()
