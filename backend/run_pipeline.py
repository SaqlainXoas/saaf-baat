from __future__ import annotations

import argparse
import logging
import os
import sys
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


def main(argv: list[str] | None = None) -> int:
    backend_dir = _setup_import_path()
    load_dotenv(backend_dir / ".env")

    parser = argparse.ArgumentParser(description="Saaf Baat daily pipeline runner")
    parser.add_argument("--sources", default=str(backend_dir / "config" / "sources.yaml"))
    parser.add_argument("--rules", default=str(backend_dir / "config" / "classification_rules.yaml"))
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--disable-playwright",
        action="store_true",
        help="Disable Playwright fallback in scraping (faster installs for CI).",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)

    if args.disable_playwright:
        os.environ["SAAF_ENABLE_PLAYWRIGHT_FALLBACK"] = "0"

    from src.db.client import SupabaseClient
    from src.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator

    config = PipelineConfig(
        sources_yaml=Path(args.sources),
        classification_yaml=Path(args.rules),
    )

    db = SupabaseClient()
    runner = PipelineOrchestrator(config=config, db=db)
    stats = runner.run()

    logging.getLogger("pipeline").info("Pipeline complete: %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

