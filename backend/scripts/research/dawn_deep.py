"""Does Dawn expose a fuller discovery surface than the one sitemap we found?"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def get(u, t=25):
    try: return requests.get(u, headers={"User-Agent": UA}, timeout=t)
    except Exception: return None

print("--- robots.txt sitemaps ---")
r = get("https://www.dawn.com/robots.txt", 15)
declared = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text) if r else []
for d in declared: print("  ", d)

print("\n--- probing Dawn discovery endpoints ---")
CANDS = declared + [
    "https://www.dawn.com/feeds/sitemap",
    "https://www.dawn.com/sitemap.xml",
    "https://www.dawn.com/feeds/newspaper",
    "https://www.dawn.com/feeds/national",
    "https://www.dawn.com/feeds/karachi",
    "https://www.dawn.com/feeds/lahore",
    "https://www.dawn.com/feeds/islamabad",
    "https://www.dawn.com/feeds/peshawar",
    "https://www.dawn.com/feeds/cities",
]

def check(u):
    resp = get(u)
    if not resp or resp.status_code != 200:
        return (u, resp.status_code if resp else "ERR", 0, 0, "")
    body = resp.text
    now = datetime.now(timezone.utc)
    locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", body)
    if locs:
        dates = re.findall(r"<news:publication_date>\s*([^<]+?)\s*</news:publication_date>", body)
        fresh = 0
        for d in dates:
            try:
                dt = datetime.fromisoformat(d.strip().replace("Z","+00:00"))
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                if (now-dt).total_seconds() <= 86400: fresh += 1
            except Exception: pass
        news_paths = sum(1 for l in locs if "/newspaper/" in l)
        return (u, 200, len(locs), fresh, f"newspaper_urls={news_paths}")
    entries = feedparser.parse(resp.content).entries
    return (u, 200, len(entries), 0, "rss" if entries else "empty")

with ThreadPoolExecutor(max_workers=8) as pool:
    for u, st, n, fresh, note in pool.map(check, CANDS):
        print(f"  {str(st):<5} items={n:<6} fresh24={fresh:<5} {note:<22} {u}")

# Are the specific missed stories reachable from the sitemap at all?
print("\n--- searching Dawn sitemap for the missed headlines ---")
sm = get("https://www.dawn.com/feeds/sitemap")
body = sm.text if sm else ""
for needle in ["iesco", "hiv", "sindh", "dengue", "kohat", "tiktoker"]:
    hits = re.findall(rf"<loc>([^<]*{needle}[^<]*)</loc>", body, re.I)
    print(f"  {needle:<10} -> {len(hits)} match(es) {hits[0][:70] if hits else ''}")

print("\n--- how many /newspaper/ URLs are in the sitemap ---")
locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", body)
print(f"  total locs={len(locs)}  /newspaper/={sum(1 for l in locs if '/newspaper/' in l)}"
      f"  /news/={sum(1 for l in locs if '/news/' in l)}")
