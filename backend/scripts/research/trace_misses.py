"""
Where do the genuinely-missed stories live?

Takes headlines the union of RSS + sitemaps failed to match, finds their real
URL via the oracle, and reports which URL space they occupy — which tells us
whether one more discovery channel would close the gap.
"""
from __future__ import annotations

from urllib.parse import urlparse

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

TARGETS = [
    "Tarbela cost jumps", "Iesco", "HIV data concealment", "divide Sindh",
    "dengue cases rise in Kohat", "TikToker", "Syria says FM",
]

ORACLES = [
    "https://news.google.com/rss?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/search?q=Pakistan+when:1d&hl=en-PK&gl=PK&ceid=PK:en",
]

entries = []
for u in ORACLES:
    try:
        r = requests.get(u, headers={"User-Agent": UA}, timeout=25)
        entries.extend(feedparser.parse(r.content).entries)
    except Exception:
        pass

print(f"scanning {len(entries)} oracle entries\n")
for target in TARGETS:
    for e in entries:
        title = e.get("title", "")
        if target.lower() in title.lower():
            src = (e.get("source", {}) or {}).get("title", "?")
            link = e.get("link", "")
            # Google News wraps links; try to recover the publisher URL
            real = link
            if "news.google.com" in link:
                try:
                    resp = requests.head(link, headers={"User-Agent": UA},
                                         timeout=15, allow_redirects=True)
                    real = resp.url
                except Exception:
                    real = "(google redirect, not resolved)"
            path = urlparse(real).path if real.startswith("http") else real
            print(f"{target}")
            print(f"   title : {title[:88]}")
            print(f"   source: {src}")
            print(f"   path  : {urlparse(real).netloc}{path[:80]}")
            print()
            break
