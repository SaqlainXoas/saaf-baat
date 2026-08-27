"""
Feed discovery: find working RSS endpoints for publishers we are missing.

Driven by the recall test, which showed Arab News PK, Radio Pakistan, and The
News carrying stories our current feed set never sees — plus Dawn print-edition
stories absent from the main sections.

Strategy: try each site's declared <link rel="alternate" type="...rss..."> tags
first (authoritative), then fall back to probing common feed paths.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

HOMEPAGES = [
    "https://www.arabnews.pk/",
    "https://radio.gov.pk/",
    "https://www.thenews.com.pk/",
    "https://www.dawn.com/",
]

GUESS_PATHS = [
    "/feed", "/feed/", "/rss", "/rss.xml", "/feeds", "/index.xml",
    "/rss/feed", "/feeds/all", "/category/pakistan/feed/",
]

# Dawn + The News section probes, driven by their URL conventions.
EXPLICIT = (
    [f"https://www.dawn.com/feeds/{s}" for s in
     ("newspaper", "national", "prism", "technology", "life-style", "magazines", "herald")]
    + [f"https://www.thenews.com.pk/rss/1/{i}" for i in range(1, 12)]
    + [f"https://www.thenews.com.pk/rss/2/{i}" for i in range(1, 6)]
    + ["https://www.arabnews.pk/rss.xml", "https://www.arabnews.pk/taxonomy/term/1/feed"]
)


def declared_feeds(home):
    try:
        r = requests.get(home, headers={"User-Agent": UA}, timeout=25)
        found = set()
        for m in re.finditer(r'<link[^>]+>', r.text, re.I):
            tag = m.group(0)
            if "alternate" in tag.lower() and re.search(r'(rss|atom)\+xml', tag, re.I):
                href = re.search(r'href=["\']([^"\']+)["\']', tag)
                if href:
                    found.add(urljoin(home, href.group(1)))
        return found
    except Exception:
        return set()


def check(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200:
            return (url, r.status_code, 0, None, "")
        parsed = feedparser.parse(r.content)
        entries = parsed.entries or []
        if not entries:
            return (url, 200, 0, None, "no entries")
        now = datetime.now(timezone.utc)
        ages = []
        for e in entries:
            for key in ("published_parsed", "updated_parsed"):
                if e.get(key):
                    try:
                        ages.append((now - datetime(*e[key][:6], tzinfo=timezone.utc)).total_seconds()/3600)
                        break
                    except Exception:
                        pass
        newest = round(min(ages), 1) if ages else None
        title = (entries[0].get("title") or "")[:55]
        return (url, 200, len(entries), newest, title)
    except Exception as e:
        return (url, type(e).__name__, 0, None, "")


candidates = set(EXPLICIT)
print("declared feeds found on homepages:")
for home in HOMEPAGES:
    found = declared_feeds(home)
    for f in sorted(found):
        print(f"  {home:<30} -> {f}")
    candidates |= found
    for p in GUESS_PATHS:
        candidates.add(urljoin(home, p))

print(f"\nprobing {len(candidates)} candidate endpoints...\n")
with ThreadPoolExecutor(max_workers=12) as pool:
    results = list(pool.map(check, sorted(candidates)))

live = [r for r in results if r[1] == 200 and r[2] > 0]
live.sort(key=lambda r: (r[3] if r[3] is not None else 1e9))

print(f"{'newest_h':<10} {'items':<7} url")
print("-" * 100)
for url, status, items, newest, title in live:
    age = "-" if newest is None else f"{newest:.1f}"
    flag = "" if (newest is not None and newest < 48) else "   <-- STALE"
    print(f"{age:<10} {items:<7} {url}{flag}")
    if newest is not None and newest < 48:
        print(f"{'':<18} e.g. {title}")

print(f"\nlive feeds: {len(live)} / {len(candidates)} probed")
