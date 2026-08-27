"""
Refine the coverage test: are the URLs found only on section pages actually
TODAY'S news, or are they archive/sidebar/'related' links?

HTML link scraping harvests every anchor on a page, including "most read",
"related stories", and evergreen promos. If the page-only URLs are old, then RSS
is not missing current news — the HTML path is just adding noise that downstream
filtering then has to remove.

Method: sample the page-only URLs, fetch each, and read its real publish date.
"""
from __future__ import annotations

import html as html_mod
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

SOURCES = {
    "dawn": {
        "feeds": ["https://www.dawn.com/feeds/home", "https://www.dawn.com/feeds/latest-news",
                  "https://www.dawn.com/feeds/pakistan", "https://www.dawn.com/feeds/business"],
        "pages": ["https://www.dawn.com/", "https://www.dawn.com/pakistan",
                  "https://www.dawn.com/business"],
        "article_re": r"/news/\d+",
    },
    "brecorder": {
        "feeds": ["https://www.brecorder.com/feeds/latest-news",
                  "https://www.brecorder.com/feeds/pakistan",
                  "https://www.brecorder.com/feeds/markets"],
        "pages": ["https://www.brecorder.com/", "https://www.brecorder.com/pakistan"],
        "article_re": r"/news/\d+",
    },
    "geo": {
        "feeds": ["https://www.geo.tv/rss/1/1", "https://www.geo.tv/rss/1/4"],
        "pages": ["https://www.geo.tv/category/pakistan", "https://www.geo.tv/category/business"],
        "article_re": r"/latest/\d+",
    },
}

DATE_PATTERNS = [
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'property="article:published_time"\s+content="([^"]+)"',
    r'name="pubdate"\s+content="([^"]+)"',
    r'<meta[^>]+content="([^"]+)"[^>]*property="article:published_time"',
]


def norm(u):
    p = urlparse(u)
    return f"{p.netloc.replace('www.','')}{p.path.rstrip('/')}"


def publish_date(url):
    try:
        r = requests.get(url if url.startswith("http") else f"https://{url}",
                         headers={"User-Agent": UA}, timeout=25)
        if r.status_code != 200:
            return None, r.status_code
    except Exception as e:
        return None, type(e).__name__
    for pat in DATE_PATTERNS:
        m = re.search(pat, r.text)
        if m:
            raw = m.group(1).strip()
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")), 200
            except ValueError:
                continue
    return None, 200


now = datetime.now(timezone.utc)
print(f"{'source':<11} {'sampled':<9} {'dated':<7} {'<24h':<6} {'<7d':<6} {'older':<7} {'oldest'}")
print("-" * 70)

for name, cfg in SOURCES.items():
    feed_urls = set()
    for f in cfg["feeds"]:
        try:
            r = requests.get(f, headers={"User-Agent": UA}, timeout=25)
            for e in feedparser.parse(r.content).entries:
                if e.get("link"):
                    feed_urls.add(norm(e["link"]))
        except Exception:
            pass

    page_urls = set()
    for p in cfg["pages"]:
        try:
            r = requests.get(p, headers={"User-Agent": UA}, timeout=30)
            for href in re.findall(r'href=["\']([^"\']+)["\']', r.text):
                absolute = urljoin(p, html_mod.unescape(href))
                if re.search(cfg["article_re"], urlparse(absolute).path):
                    page_urls.add(norm(absolute))
        except Exception:
            pass

    page_only = sorted(page_urls - feed_urls)
    random.seed(7)
    sample = random.sample(page_only, min(25, len(page_only)))

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(publish_date, sample))

    dated = [d for d, _ in results if d]
    fresh24 = sum(1 for d in dated if (now - d).total_seconds() <= 86400)
    fresh7d = sum(1 for d in dated if (now - d).total_seconds() <= 7 * 86400)
    older = len(dated) - fresh7d
    oldest = min(dated).date().isoformat() if dated else "-"
    print(f"{name:<11} {len(sample):<9} {len(dated):<7} {fresh24:<6} {fresh7d:<6} {older:<7} {oldest}")
