from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def _setup_import_path() -> Path:
    backend_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(backend_dir / "src"))
    return backend_dir


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _resolve_heartbeat_path(backend_dir: Path) -> Path:
    configured = (os.getenv("SAAF_PIPELINE_HEARTBEAT_FILE") or "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = backend_dir.parent / path
    else:
        path = backend_dir / ".pipeline_heartbeat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_pipeline_heartbeat(backend_dir: Path, stats: object) -> None:
    path = _resolve_heartbeat_path(backend_dir)
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    existing_payload = {}
    if path.exists():
        try:
            existing_payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing_payload = {}

    last_successful = existing_payload.get("last_successful_run_at")
    if getattr(stats, "feeds_inserted", 0) > 0 and os.getenv("SAAF_STAGE_PUBLICATION") != "1":
        last_successful = now_utc.isoformat().replace("+00:00", "Z")

    payload = {
        "publication_token": (os.getenv("SAAF_PUBLICATION_TOKEN") or "").strip(),
        "edition_date": now_utc.astimezone(ZoneInfo("Asia/Karachi")).date().isoformat(),
        "run_started_at": getattr(stats, "run_started_at", now_utc).isoformat(),
        "last_run_at": now_utc.isoformat().replace("+00:00", "Z"),
        "last_successful_run_at": last_successful,
        "source_article_counts": dict(getattr(stats, "source_article_counts", {}) or {}),
        "source_discovered_counts": dict(getattr(stats, "source_discovered_counts", {}) or {}),
        "degraded_sources": list(getattr(stats, "degraded_sources", []) or []),
        "endpoint_health": [dict(row) for row in getattr(stats, "endpoint_health", []) or []],
        "stats": stats.as_dict() if hasattr(stats, "as_dict") else str(stats),
    }
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        logging.getLogger("pipeline").info("Wrote pipeline heartbeat: %s", path)
    except Exception as exc:
        logging.getLogger("pipeline").warning("Failed writing pipeline heartbeat: %s", exc)


def _trigger_frontend_revalidate(stats: object) -> None:
    """
    Optionally tell the Next.js app to invalidate cached feed/health responses.

    This enables near-real-time UI updates even when server fetch uses long
    revalidate windows.
    """
    url = (os.getenv("SAAF_FRONTEND_REVALIDATE_URL") or "").strip()
    secret = (os.getenv("SAAF_FRONTEND_REVALIDATE_SECRET") or "").strip()
    if not url or not secret:
        return

    payload = json.dumps({"tags": ["feed", "health"]}).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-revalidate-secret": secret,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            logging.getLogger("pipeline").info("Frontend revalidate response: %s", body[:200])
    except urllib.error.HTTPError as exc:
        logging.getLogger("pipeline").warning("Frontend revalidate failed (HTTP %s)", exc.code)
    except Exception as exc:
        logging.getLogger("pipeline").warning("Frontend revalidate failed: %s", exc)


def main(argv: list[str] | None = None) -> int:
    backend_dir = _setup_import_path()
    load_dotenv(backend_dir / ".env")

    parser = argparse.ArgumentParser(description="Saaf Baat daily pipeline runner")
    parser.add_argument("--sources", default=str(backend_dir / "config" / "sources.yaml"))
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--max-articles-per-source",
        type=int,
        default=None,
        help="Override max articles scraped per source for this run.",
    )
    parser.add_argument(
        "--embedding-backfill-limit",
        type=int,
        default=None,
        help="Override pending-embedding backfill limit for this run.",
    )
    parser.add_argument(
        "--low-cost-mode",
        action="store_true",
        help="Force low-cost defaults (caps scraping + backfill).",
    )
    parser.add_argument(
        "--disable-playwright",
        action="store_true",
        help="Deprecated no-op. Playwright was retired with the HTML scraper.",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)

    if args.disable_playwright:
        logging.getLogger("pipeline").warning(
            "--disable-playwright is a no-op: ingest is RSS + sitemap only and "
            "no browser fallback exists. The flag is accepted so existing cron "
            "entries keep working; drop it when convenient."
        )
    if args.low_cost_mode:
        os.environ["SAAF_LOW_COST_MODE"] = "1"

    from src.db.factory import create_db_client
    from src.pipeline.orchestrator import PipelineOrchestrator, default_config

    config = default_config(sources_yaml=Path(args.sources))
    overrides = {}
    if args.max_articles_per_source is not None and args.max_articles_per_source > 0:
        overrides["max_articles_per_source"] = args.max_articles_per_source
    if args.embedding_backfill_limit is not None and args.embedding_backfill_limit > 0:
        overrides["embedding_backfill_limit"] = args.embedding_backfill_limit
    if overrides:
        config = replace(config, **overrides)

    db = create_db_client()
    runner = PipelineOrchestrator(config=config, db=db)
    stats = runner.run()

    _write_pipeline_heartbeat(backend_dir, stats)
    _trigger_frontend_revalidate(stats)
    logging.getLogger("pipeline").info("Pipeline complete: %s", stats.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
