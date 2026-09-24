"""Run or recover one hosted edition without repeating completed Gemini work."""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from check_run_health import heartbeat_path  # noqa: E402
from check_run_health import main as check_health  # noqa: E402
from publish_hosted import (  # noqa: E402
    notify_frontend,
    publication_drafts,
    publish,
    published_stories,
    record_failed_run,
    wake_backend,
    warm_frontend_cache,
)

import run_pipeline  # noqa: E402
from src.db.factory import create_db_client  # noqa: E402
from src.pipeline.orchestrator import (  # noqa: E402
    PipelineOrchestrator,
    PipelineStats,
    default_config,
)

PKT = ZoneInfo("Asia/Karachi")
LOG = logging.getLogger(__name__)


def edition_date() -> str:
    return datetime.now(timezone.utc).astimezone(PKT).date().isoformat()


def before_noon() -> bool:
    return datetime.now(PKT).hour < 12


def _read(db, query):
    retry = getattr(db, "_execute_retryable", None)
    return retry(query) if callable(retry) else query().execute()


def saved_state(db) -> dict:
    rows = _read(db, lambda: db.client.table("pipeline_state")
                 .select("payload").eq("id", "daily").limit(1)).data
    return dict(rows[0]["payload"]) if rows else {}


def published_today(db) -> bool:
    rows = _read(db, lambda: db.client.table("analyzed_feed")
            .select("metadata")
            .eq("is_published", True)
            .order("created_at", desc=True)
            .limit(1)).data
    if not rows:
        return False
    stamp = (rows[0].get("metadata") or {}).get("brief_run_at")
    if not stamp:
        return False
    when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return when.astimezone(PKT).date().isoformat() == edition_date()


def valid_drafts(db, token: str) -> list[dict]:
    rows = publication_drafts(db, token)
    if not 1 <= len(rows) <= 12 or len({row["cluster_id"] for row in rows}) != len(rows):
        return []
    now = datetime.now(timezone.utc)
    for row in rows:
        created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
        if (row.get("is_published") or created < now - timedelta(hours=3)
                or created > now + timedelta(minutes=5)
                or not (row.get("metadata") or {}).get("why_it_matters")):
            return []
    return rows


def write_heartbeat(payload: dict) -> None:
    path = heartbeat_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def recover_processing(db, heartbeat: dict, token: str) -> dict | None:
    """Use persisted drafts, embeddings and triage; never call the editor again."""
    drafts = valid_drafts(db, token)
    if not drafts or heartbeat.get("edition_date") != edition_date():
        return None
    old = dict(heartbeat.get("stats") or {})
    if (old.get("editorial_status") != "ok" or old.get("analyze_failures")
            or old.get("cluster_failures")):
        return None
    stats = PipelineStats()
    for field in fields(PipelineStats):
        if field.name in old and field.name != "run_started_at":
            setattr(stats, field.name, old[field.name])
    if old.get("run_started_at"):
        stats.run_started_at = datetime.fromisoformat(old["run_started_at"])
    stats.feeds_inserted = len(drafts)
    runner = PipelineOrchestrator(
        config=default_config(sources_yaml=BACKEND / "config" / "sources.yaml"), db=db
    )
    # At most five bounded backfill passes. Each pass reads persisted state; a
    # failed write is not mistaken for a recovered article.
    previous_missing: tuple[int, int] | None = None
    for _ in range(5):
        runner.embed_backfill(stats)
        runner.triage_backfill(stats)
        if stats.embedding_status == stats.triage_status == "ok":
            break
        missing = (stats.embedding_unresolved, stats.triage_unresolved)
        if missing == previous_missing:
            break
        previous_missing = missing
    updated = {
        **heartbeat,
        "publication_token": token,
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "stats": {**old, **stats.as_dict()},
    }
    write_heartbeat(updated)
    return updated


def run_daily(mode: str, token: str) -> int:
    db = create_db_client()
    fresh_token = token
    standing = saved_state(db)
    today = edition_date()
    standing_stats = standing.get("stats") or {}
    if (mode != "manual"
            and ((standing.get("edition_date") == today
                  and standing_stats.get("publication_status") == "ok")
                 or published_today(db))):
        LOG.info("Today's edition is already published; skipping")
        return 0
    if mode != "manual" and not before_noon():
        LOG.error("Scheduled edition started after the noon PKT freshness cutoff")
        return 1

    heartbeat: dict = {}
    if mode == "backup" and standing.get("edition_date") == today:
        old_token = str(standing.get("publication_token") or "")
        if old_token and valid_drafts(db, old_token):
            token = old_token
            heartbeat = standing
    os.environ["SAAF_PUBLICATION_TOKEN"] = token
    def deadline_exceeded(_signal, _frame):
        raise TimeoutError("Generation exhausted its reserved workflow time")

    previous_handler = signal.signal(signal.SIGALRM, deadline_exceeded)
    signal.alarm(32 * 60)  # Reserve time for install, publication and cache warm.
    try:
        if heartbeat:
            recovered = recover_processing(db, heartbeat, token)
            if recovered is not None:
                heartbeat = recovered
            else:
                heartbeat = {}
                token = fresh_token
                os.environ["SAAF_PUBLICATION_TOKEN"] = token
        if not heartbeat:
            run_pipeline.main(["--low-cost-mode", "--log-level", "INFO"])
            heartbeat = json.loads(heartbeat_path().read_text(encoding="utf-8"))
            if check_health(["--min-cards", "1"]) != 0:
                recovered = recover_processing(db, heartbeat, token)
                if recovered is not None:
                    heartbeat = recovered

        if check_health(["--min-cards", "1"]) != 0:
            raise RuntimeError("Edition remains unhealthy after recovery")
        count = publish(db, token, heartbeat)
        LOG.info("Published %d cards", count)
    except Exception:
        signal.alarm(0)
        LOG.exception("Daily edition failed; prior edition remains live")
        if not heartbeat:
            heartbeat = {
                "edition_date": today, "publication_token": token,
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "stats": {"publication_status": "failed"},
            }
        record_failed_run(db, heartbeat)
        write_heartbeat(heartbeat)
        return 1
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)

    # These operations occur after atomic publication and cannot undo it.
    try:
        stories = published_stories(db, token)
        wake_backend()
        notify_frontend()
        warm_frontend_cache(stories)
    except Exception:
        LOG.exception("Edition published, but cache warm did not complete")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("primary", "backup", "manual"), required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    token = (os.getenv("SAAF_PUBLICATION_TOKEN") or "").strip()
    if not token:
        parser.error("SAAF_PUBLICATION_TOKEN is required")
    os.environ["SAAF_STAGE_PUBLICATION"] = "1"
    return run_daily(args.mode, token)


if __name__ == "__main__":
    raise SystemExit(main())
