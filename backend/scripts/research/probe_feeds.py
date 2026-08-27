"""
Probe every candidate feed and record hard health metrics.

Answers, per feed, the questions that decide whether it can be trusted as a
daily ingestion source:
  - does it respond, and how fast
  - does it parse, and how many items
  - how OLD is the newest item (the single best staleness signal)
  - does it carry full article text, or only a summary
  - does it carry publisher categories and authors
  - do its links point at the publisher's own domain

Usage:
    python probe_feeds.py                 # probe all, write JSON + table
    python probe_feeds.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feeds_catalog import CANDIDATES  # noqa: E402

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
FULL_TEXT_MIN_CHARS = 600


def _text_of(entry, *keys) -> str:
    """Longest plain-text value among the given entry keys."""
    best = ""
    for key in keys:
        value = entry.get(key)
        if isinstance(value, list) and value:
            value = value[0].get("value", "")
        if isinstance(value, dict):
            value = value.get("value", "")
        if isinstance(value, str) and len(value) > len(best):
            best = value
    if not best:
        return ""
    import html as html_mod
    import re

    cleaned = re.sub(r"<[^>]+>", " ", best)
    return re.sub(r"\s+", " ", html_mod.unescape(cleaned)).strip()


def _published(entry):
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def probe(candidate) -> dict:
    publisher, label, url = candidate
    row = {
        "publisher": publisher,
        "label": label,
        "url": url,
        "ok": False,
        "error": None,
        "http": None,
        "seconds": None,
        "bytes": 0,
        "items": 0,
        "newest_age_hours": None,
        "items_last_24h": 0,
        "dated_items": 0,
        "median_body": 0,
        "full_text_items": 0,
        "with_category": 0,
        "with_author": 0,
        "own_domain_links": 0,
        "sample_title": None,
    }

    started = time.time()
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=25, allow_redirects=True)
        row["http"] = resp.status_code
        row["bytes"] = len(resp.content)
        row["seconds"] = round(time.time() - started, 2)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:
        row["seconds"] = round(time.time() - started, 2)
        row["error"] = f"{type(exc).__name__}: {exc}"[:160]
        return row

    entries = parsed.entries or []
    row["items"] = len(entries)
    if not entries:
        row["error"] = "parsed but zero entries"
        return row

    now = datetime.now(timezone.utc)
    bodies, ages = [], []
    feed_host = urlparse(url).netloc.replace("www.", "")

    for entry in entries:
        body = _text_of(entry, "content", "summary", "description")
        bodies.append(len(body))
        if len(body) >= FULL_TEXT_MIN_CHARS:
            row["full_text_items"] += 1
        if entry.get("tags") or entry.get("category"):
            row["with_category"] += 1
        if entry.get("author"):
            row["with_author"] += 1
        link = entry.get("link") or ""
        if feed_host and feed_host.split(".")[-2:] == urlparse(link).netloc.replace("www.", "").split(".")[-2:]:
            row["own_domain_links"] += 1

        published = _published(entry)
        if published:
            row["dated_items"] += 1
            age = (now - published).total_seconds() / 3600.0
            ages.append(age)
            if 0 <= age <= 24:
                row["items_last_24h"] += 1

    row["median_body"] = int(statistics.median(bodies)) if bodies else 0
    if ages:
        row["newest_age_hours"] = round(min(ages), 1)
    row["sample_title"] = (entries[0].get("title") or "")[:70]
    row["ok"] = True
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="probe_results.json")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(probe, CANDIDATES))
    elapsed = time.time() - started

    rows.sort(key=lambda r: (r["publisher"], r["label"]))

    hdr = f"{'publisher/label':<24} {'http':<5} {'items':<6} {'new_h':<7} {'24h':<5} {'body':<7} {'full':<6} {'cat':<5} {'s':<5} note"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        note = r["error"] or (r["sample_title"] or "")[:38]
        age = r["newest_age_hours"]
        age_s = "-" if age is None else f"{age:.1f}"
        print(
            f"{r['publisher'] + '/' + r['label']:<24} {str(r['http'] or '-'):<5} {r['items']:<6} "
            f"{age_s:<7} {r['items_last_24h']:<5} {r['median_body']:<7} {r['full_text_items']:<6} "
            f"{r['with_category']:<5} {str(r['seconds']):<5} {note}"
        )

    out = Path(args.json)
    out.write_text(json.dumps({"probed_at": datetime.now(timezone.utc).isoformat(),
                               "wall_clock_seconds": round(elapsed, 2),
                               "results": rows}, indent=2))
    healthy = [r for r in rows if r["ok"] and (r["newest_age_hours"] or 999) < 24]
    print(f"\nprobed {len(rows)} feeds in {elapsed:.1f}s  |  fresh-and-parsing: {len(healthy)}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
