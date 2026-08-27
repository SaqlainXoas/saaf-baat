#!/usr/bin/env python3
"""
Dump the current brief as JSON, exactly as `/api/feed` would serve it.

Used by the scheduled workflow, which runs on an ephemeral runner and would
otherwise leave no trace of what it produced. Also the quickest way to read a
brief locally without starting uvicorn.

It deliberately reuses `src.api.routes.feed`'s own helpers rather than
re-querying: a second copy of "which rows are today's brief" would drift from
the one the API uses, and that drift is exactly the bug `brief_run_at` fixed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.api.routes.feed import (  # noqa: E402
    _latest_brief_only,
    _story_sort_key,
    _to_story_card,
)
from src.db.factory import create_db_client  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="-", help="Output path, or '-' for stdout.")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)

    db = create_db_client()
    feeds = _latest_brief_only(db.get_analyzed_feed(limit=args.limit))
    feeds = sorted(feeds, key=_story_sort_key)

    payload = {
        "card_count": len(feeds),
        "stories": [
            json.loads(_to_story_card(feed).model_dump_json()) for feed in feeds
        ],
    }
    text = json.dumps(payload, indent=2, default=str) + "\n"

    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {len(feeds)} cards to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
