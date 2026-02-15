from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

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
    payload = {
        "last_successful_pipeline_run_at": now_utc.isoformat().replace("+00:00", "Z"),
        "stats": stats.as_dict() if hasattr(stats, "as_dict") else str(stats),
    }
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        logging.getLogger("pipeline").info("Wrote pipeline heartbeat: %s", path)
    except Exception as exc:
        logging.getLogger("pipeline").warning("Failed writing pipeline heartbeat: %s", exc)


def main(argv: list[str] | None = None) -> int:
    backend_dir = _setup_import_path()
    load_dotenv(backend_dir / ".env")

    parser = argparse.ArgumentParser(description="Saaf Baat daily pipeline runner")
    parser.add_argument("--sources", default=str(backend_dir / "config" / "sources.yaml"))
    parser.add_argument(
        "--rules", default=str(backend_dir / "config" / "classification_rules.yaml")
    )
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
        help="Disable Playwright fallback in scraping (faster installs for CI).",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)

    if args.disable_playwright:
        os.environ["SAAF_ENABLE_PLAYWRIGHT_FALLBACK"] = "0"
    if args.low_cost_mode:
        os.environ["SAAF_LOW_COST_MODE"] = "1"

    from src.db.client import SupabaseClient
    from src.pipeline.orchestrator import PipelineOrchestrator, default_config

    config = default_config(sources_yaml=Path(args.sources), classification_yaml=Path(args.rules))
    overrides = {}
    if args.max_articles_per_source is not None and args.max_articles_per_source > 0:
        overrides["max_articles_per_source"] = args.max_articles_per_source
    if args.embedding_backfill_limit is not None and args.embedding_backfill_limit > 0:
        overrides["embedding_backfill_limit"] = args.embedding_backfill_limit
    if overrides:
        config = replace(config, **overrides)

    db = SupabaseClient()
    runner = PipelineOrchestrator(config=config, db=db)
    stats = runner.run()

    _write_pipeline_heartbeat(backend_dir, stats)
    logging.getLogger("pipeline").info("Pipeline complete: %s", stats.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
