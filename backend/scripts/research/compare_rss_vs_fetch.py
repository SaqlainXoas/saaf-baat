"""
Fidelity test: is the article body inside RSS as good as fetching the page?

This is the decisive question for an RSS-first ingest. If `content:encoded` is
truncated or polluted, we still need per-article fetching and the whole extractor
stack. If it matches a real extraction, the fetch layer can be deleted.

Method: sample N items per feed, take the RSS body, then fetch the same URL and
extract with trafilatura (the current pipeline's primary extractor). Compare
length ratio and token overlap, and time both paths.

Usage:
    python scripts/research/compare_rss_vs_fetch.py --per-feed 8
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import feedparser
import requests
import trafilatura

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

FULL_TEXT_FEEDS = [
    ("dawn",      "https://www.dawn.com/feeds/pakistan"),
    ("dawn",      "https://www.dawn.com/feeds/business"),
    ("tribune",   "https://tribune.com.pk/feed/pakistan"),
    ("brecorder", "https://www.brecorder.com/feeds/latest-news"),
]


def clean(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", html_mod.unescape(text)).strip()


def rss_body(entry) -> str:
    best = ""
    for key in ("content", "summary", "description"):
        value = entry.get(key)
        if isinstance(value, list) and value:
            value = value[0].get("value", "")
        if isinstance(value, dict):
            value = value.get("value", "")
        if isinstance(value, str) and len(value) > len(best):
            best = value
    return clean(best)


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", text.lower()))


def compare(job) -> dict | None:
    publisher, url, rss_text = job
    started = time.time()
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        extracted = trafilatura.extract(resp.text, include_comments=False, include_tables=False) or ""
    except Exception as exc:
        return {"publisher": publisher, "url": url, "error": f"{type(exc).__name__}: {exc}"[:120]}
    fetch_seconds = time.time() - started

    extracted = re.sub(r"\s+", " ", extracted).strip()
    rss_tokens, page_tokens = tokens(rss_text), tokens(extracted)
    if not page_tokens:
        return {"publisher": publisher, "url": url, "error": "extractor returned nothing"}

    # What fraction of the fetched article's vocabulary the RSS body already has.
    recall = len(rss_tokens & page_tokens) / len(page_tokens)
    return {
        "publisher": publisher,
        "url": url,
        "rss_chars": len(rss_text),
        "page_chars": len(extracted),
        "length_ratio": round(len(rss_text) / len(extracted), 3),
        "token_recall": round(recall, 3),
        "fetch_seconds": round(fetch_seconds, 2),
        "error": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-feed", type=int, default=8)
    ap.add_argument("--json", default="scripts/research/fidelity_results.json")
    args = ap.parse_args()

    jobs = []
    rss_started = time.time()
    for publisher, feed_url in FULL_TEXT_FEEDS:
        resp = requests.get(feed_url, headers={"User-Agent": UA}, timeout=25)
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries[: args.per_feed]:
            body = rss_body(entry)
            link = entry.get("link")
            if link and len(body) > 200:
                jobs.append((publisher, link, body))
    rss_seconds = time.time() - rss_started

    print(f"RSS pass: {len(jobs)} articles WITH BODY TEXT in {rss_seconds:.1f}s "
          f"({len(FULL_TEXT_FEEDS)} feed requests)\n")

    fetch_started = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [r for r in pool.map(compare, jobs) if r]
    fetch_seconds = time.time() - fetch_started

    ok = [r for r in rows if not r.get("error")]
    failed = [r for r in rows if r.get("error")]

    hdr = f"{'publisher':<11} {'rss_chars':<10} {'page_chars':<11} {'ratio':<7} {'recall':<7} {'fetch_s':<8}"
    print(hdr)
    print("-" * len(hdr))
    for r in ok:
        print(f"{r['publisher']:<11} {r['rss_chars']:<10} {r['page_chars']:<11} "
              f"{r['length_ratio']:<7} {r['token_recall']:<7} {r['fetch_seconds']:<8}")

    for r in failed:
        print(f"{r['publisher']:<11} FAILED  {r['error']}")

    print()
    by_pub: dict[str, list] = {}
    for r in ok:
        by_pub.setdefault(r["publisher"], []).append(r)

    print(f"{'publisher':<11} {'n':<4} {'median_ratio':<14} {'median_recall':<14} verdict")
    print("-" * 62)
    for pub, rs in sorted(by_pub.items()):
        mr = statistics.median(r["length_ratio"] for r in rs)
        rc = statistics.median(r["token_recall"] for r in rs)
        verdict = ("RSS body is complete" if rc >= 0.9
                   else "RSS body is partial" if rc >= 0.6
                   else "RSS body is a teaser")
        print(f"{pub:<11} {len(rs):<4} {mr:<14.3f} {rc:<14.3f} {verdict}")

    print(f"\nTIMING  rss-only: {rss_seconds:.1f}s for {len(jobs)} articles")
    print(f"        fetch+extract (6 parallel): {fetch_seconds:.1f}s for {len(rows)} articles")
    if rows:
        print(f"        fetch cost per article: {fetch_seconds/len(rows):.2f}s")
    if failed:
        print(f"        fetch failures: {len(failed)}/{len(rows)}")

    Path(args.json).write_text(json.dumps(rows, indent=2))
    print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
