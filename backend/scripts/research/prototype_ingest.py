"""
Reference implementation of the proposed RSS-first ingest.

Proves the whole design end to end before it is built into the pipeline:

  1. Two independent discovery channels: RSS feeds and Google-News sitemaps.
  2. Automatic source health gating — a feed whose newest item is older than a
     threshold is quarantined, not ingested. This is what catches the traps
     found in research (geo/rss/1/53 was 295 days stale, thenews/rss/1/1 was
     276 days stale, both returning HTTP 200 with 50 items).
  3. Body text taken from RSS where the publisher supplies it; page fetch only
     for URLs discovered by sitemap alone.
  4. Canonical-URL de-duplication across channels.

Run:
    python scripts/research/prototype_ingest.py
    python scripts/research/prototype_ingest.py --fetch-missing
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

STALE_FEED_HOURS = 48        # quarantine a feed whose newest item is older
ARTICLE_MAX_AGE_HOURS = 36   # ignore individual items older than this
FULL_TEXT_MIN_CHARS = 600

# tier: "A" = publisher ships full text in RSS, "B" = summary only
SOURCES = {
    "dawn": {"tier": "A", "rss": [
        "https://www.dawn.com/feeds/home", "https://www.dawn.com/feeds/latest-news",
        "https://www.dawn.com/feeds/pakistan", "https://www.dawn.com/feeds/business",
        "https://www.dawn.com/feeds/newspaper", "https://www.dawn.com/feeds/world"],
        "sitemap": ["https://www.dawn.com/feeds/sitemap"]},
    "tribune": {"tier": "A", "rss": [
        "https://tribune.com.pk/feed/home", "https://tribune.com.pk/feed/pakistan",
        "https://tribune.com.pk/feed/business"],
        "sitemap": ["https://tribune.com.pk/sitemap/sitemap_main.xml"]},
    "brecorder": {"tier": "A", "rss": [
        "https://www.brecorder.com/feeds/latest-news", "https://www.brecorder.com/feeds/pakistan",
        "https://www.brecorder.com/feeds/markets"],
        "sitemap": ["https://www.brecorder.com/feeds/sitemap"]},
    "geo": {"tier": "B", "rss": [
        "https://www.geo.tv/rss/1/1", "https://www.geo.tv/rss/1/4",
        "https://www.geo.tv/rss/1/53"],   # deliberately included: known stale, must be caught
        "sitemap": ["https://www.geo.tv/assets/uploads/google_news_latest.xml"]},
    "ary": {"tier": "B", "rss": [
        "https://arynews.tv/feed/", "https://arynews.tv/category/pakistan/feed/"],
        "sitemap": ["https://arynews.tv/sitemap/news_sitemap.xml"]},
    "nation": {"tier": "B", "rss": ["https://www.nation.com.pk/rss/latest"],
        "sitemap": ["https://www.nation.com.pk/sitemap_news_google.xml"]},
    "app": {"tier": "B", "rss": [
        "https://www.app.com.pk/feed/", "https://www.app.com.pk/category/national/feed/"],
        "sitemap": []},
    "thenews": {"tier": "B", "rss": [
        "https://www.thenews.com.pk/rss/1/1"],   # known dead, must be quarantined
        "sitemap": ["https://www.thenews.com.pk/assets/uploads/google_news_latest.xml"]},
}


def clean(raw: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", raw or ""))).strip()


def canon(url: str) -> str:
    p = urlparse(url)
    path = re.sub(r"/(amp|amp/)$", "", p.path.rstrip("/"))
    return f"{p.netloc.replace('www.', '')}{path}"


def entry_body(entry) -> str:
    best = ""
    for key in ("content", "summary", "description"):
        v = entry.get(key)
        if isinstance(v, list) and v:
            v = v[0].get("value", "")
        if isinstance(v, dict):
            v = v.get("value", "")
        if isinstance(v, str) and len(v) > len(best):
            best = v
    return clean(best)


def entry_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        if entry.get(key):
            try:
                return datetime(*entry[key][:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def get(url, timeout=25):
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    except Exception:
        return None


def read_rss(job):
    source, tier, url = job
    now = datetime.now(timezone.utc)
    resp = get(url)
    if not resp or resp.status_code != 200:
        return {"source": source, "url": url, "channel": "rss",
                "status": "unreachable", "items": []}

    entries = feedparser.parse(resp.content).entries or []
    if not entries:
        return {"source": source, "url": url, "channel": "rss",
                "status": "empty", "items": []}

    dates = [d for d in (entry_date(e) for e in entries) if d]
    newest_age = min((now - d).total_seconds() / 3600 for d in dates) if dates else None

    # HEALTH GATE — this is what stops 9-month-old news being published as today's.
    if newest_age is None:
        return {"source": source, "url": url, "channel": "rss",
                "status": "no-dates", "items": []}
    if newest_age > STALE_FEED_HOURS:
        return {"source": source, "url": url, "channel": "rss", "status": "STALE",
                "newest_age_hours": round(newest_age, 1), "items": []}

    items = []
    for e in entries:
        d = entry_date(e)
        if not d or (now - d) > timedelta(hours=ARTICLE_MAX_AGE_HOURS):
            continue
        link = e.get("link")
        if not link:
            continue
        items.append({
            "source": source, "tier": tier, "channel": "rss",
            "url": link, "canon": canon(link),
            "headline": clean(e.get("title", "")),
            "body": entry_body(e),
            "published": d.isoformat(),
            "categories": [t.get("term", "") for t in (e.get("tags") or [])][:4],
        })
    return {"source": source, "url": url, "channel": "rss", "status": "ok",
            "newest_age_hours": round(newest_age, 1), "items": items}


def read_sitemap(job):
    source, tier, url = job
    now = datetime.now(timezone.utc)
    resp = get(url)
    if not resp or resp.status_code != 200:
        return {"source": source, "url": url, "channel": "sitemap",
                "status": "unreachable", "items": []}

    body = resp.text
    blocks = re.findall(r"<url>(.*?)</url>", body, re.S)
    items, ages = [], []
    for b in blocks:
        loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", b)
        if not loc:
            continue
        dm = re.search(r"<news:publication_date>\s*([^<]+?)\s*</news:publication_date>", b)
        published = None
        if dm:
            try:
                published = datetime.fromisoformat(dm.group(1).strip().replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except Exception:
                published = None
        if published is None:
            continue
        age = (now - published).total_seconds() / 3600
        ages.append(age)
        if age > ARTICLE_MAX_AGE_HOURS:
            continue
        tm = re.search(r"<news:title>\s*(.*?)\s*</news:title>", b, re.S)
        link = loc.group(1)
        items.append({
            "source": source, "tier": tier, "channel": "sitemap",
            "url": link, "canon": canon(link),
            "headline": clean(tm.group(1)) if tm else "",
            "body": "", "published": published.isoformat(), "categories": [],
        })

    if not ages:
        return {"source": source, "url": url, "channel": "sitemap",
                "status": "no-dates", "items": []}
    newest = min(ages)
    if newest > STALE_FEED_HOURS:
        return {"source": source, "url": url, "channel": "sitemap", "status": "STALE",
                "newest_age_hours": round(newest, 1), "items": []}
    return {"source": source, "url": url, "channel": "sitemap", "status": "ok",
            "newest_age_hours": round(newest, 1), "items": items}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-missing", action="store_true",
                    help="fetch bodies for sitemap-only URLs (measures the real fetch cost)")
    ap.add_argument("--json", default="scripts/research/prototype_output.json")
    args = ap.parse_args()

    rss_jobs, sm_jobs = [], []
    for source, cfg in SOURCES.items():
        for u in cfg["rss"]:
            rss_jobs.append((source, cfg["tier"], u))
        for u in cfg["sitemap"]:
            sm_jobs.append((source, cfg["tier"], u))

    started = time.time()
    with ThreadPoolExecutor(max_workers=16) as pool:
        rss_reports = list(pool.map(read_rss, rss_jobs))
        sm_reports = list(pool.map(read_sitemap, sm_jobs))
    discovery_seconds = time.time() - started

    print("=" * 78)
    print("SOURCE HEALTH")
    print("=" * 78)
    print(f"{'source':<11} {'ch':<9} {'status':<13} {'newest_h':<10} {'items':<7} endpoint")
    print("-" * 78)
    quarantined = []
    for r in sorted(rss_reports + sm_reports, key=lambda x: (x["source"], x["channel"])):
        age = r.get("newest_age_hours")
        flag = "  <-- QUARANTINED" if r["status"] != "ok" else ""
        if r["status"] != "ok":
            quarantined.append(r)
        print(f"{r['source']:<11} {r['channel']:<9} {r['status']:<13} "
              f"{str(age if age is not None else '-'):<10} {len(r['items']):<7} "
              f"{r['url'][:34]}{flag}")

    # merge, preferring the record that already carries body text
    merged: dict[str, dict] = {}
    for r in rss_reports + sm_reports:
        for item in r["items"]:
            key = item["canon"]
            existing = merged.get(key)
            if existing is None or (len(item["body"]) > len(existing["body"])):
                if existing:
                    item["categories"] = item["categories"] or existing["categories"]
                merged[key] = item

    articles = list(merged.values())
    with_text = [a for a in articles if len(a["body"]) >= FULL_TEXT_MIN_CHARS]
    needs_fetch = [a for a in articles if len(a["body"]) < FULL_TEXT_MIN_CHARS]

    print()
    print("=" * 78)
    print("INGEST RESULT")
    print("=" * 78)
    print(f"discovery wall clock      : {discovery_seconds:.1f}s "
          f"({len(rss_jobs)} feeds + {len(sm_jobs)} sitemaps, parallel)")
    print(f"quarantined endpoints     : {len(quarantined)}")
    print(f"unique articles (<= {ARTICLE_MAX_AGE_HOURS}h) : {len(articles)}")
    print(f"  with full body from feed: {len(with_text)}")
    print(f"  body would need a fetch : {len(needs_fetch)}")

    by_source = Counter(a["source"] for a in articles)
    by_channel = Counter(a["channel"] for a in articles)
    print(f"\nper source : {dict(sorted(by_source.items()))}")
    print(f"per channel: {dict(by_channel)}")

    tier_a_text = [a for a in with_text if a["tier"] == "A"]
    if tier_a_text:
        print(f"\nTier A full-text median body: "
              f"{int(statistics.median(len(a['body']) for a in tier_a_text))} chars "
              f"({len(tier_a_text)} articles)")

    cats = Counter(c for a in articles for c in a["categories"] if c)
    print(f"publisher categories seen  : {len(cats)} distinct, "
          f"top = {[c for c, _ in cats.most_common(6)]}")

    if args.fetch_missing and needs_fetch:
        print(f"\nfetching {len(needs_fetch)} sitemap-only bodies...")
        import trafilatura
        t0 = time.time()

        def fetch_body(a):
            r = get(a["url"], timeout=20)
            if not r or r.status_code != 200:
                return a, None, (r.status_code if r else "ERR")
            text = trafilatura.extract(r.text, include_comments=False) or ""
            return a, re.sub(r"\s+", " ", text).strip(), 200

        ok = fail = 0
        codes = Counter()
        with ThreadPoolExecutor(max_workers=8) as pool:
            for a, text, code in pool.map(fetch_body, needs_fetch):
                codes[code] += 1
                if text and len(text) >= FULL_TEXT_MIN_CHARS:
                    a["body"] = text
                    ok += 1
                else:
                    fail += 1
        print(f"  fetched ok: {ok}   failed/thin: {fail}   in {time.time()-t0:.1f}s")
        print(f"  status codes: {dict(codes)}")
        final_text = [a for a in articles if len(a["body"]) >= FULL_TEXT_MIN_CHARS]
        print(f"  articles with usable body after fetch: {len(final_text)}/{len(articles)}")

    Path(args.json).write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "discovery_seconds": round(discovery_seconds, 2),
        "quarantined": [{k: v for k, v in q.items() if k != "items"} for q in quarantined],
        "counts": {"articles": len(articles), "with_text": len(with_text),
                   "needs_fetch": len(needs_fetch), "by_source": dict(by_source)},
        "articles": [{k: (v[:400] if k == "body" else v) for k, v in a.items()} for a in articles],
    }, indent=2))
    print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
