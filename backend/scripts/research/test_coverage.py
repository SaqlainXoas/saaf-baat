"""
Coverage test: does the RSS feed miss stories the site itself is showing?

This is the one real risk of an RSS-first ingest. Method: scrape the publisher's
own section pages for article links (what the current pipeline does), then check
how many of those URLs the feeds already contain — and inspect what is missing.
"""
from __future__ import annotations

import html as html_mod
import re
from urllib.parse import urljoin, urlparse

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

SOURCES = {
    "dawn": {
        "feeds": ["https://www.dawn.com/feeds/home",
                  "https://www.dawn.com/feeds/latest-news",
                  "https://www.dawn.com/feeds/pakistan",
                  "https://www.dawn.com/feeds/business"],
        "pages": ["https://www.dawn.com/", "https://www.dawn.com/pakistan",
                  "https://www.dawn.com/business"],
        "article_re": r"/news/\d+",
    },
    "tribune": {
        "feeds": ["https://tribune.com.pk/feed/home",
                  "https://tribune.com.pk/feed/pakistan",
                  "https://tribune.com.pk/feed/business"],
        "pages": ["https://tribune.com.pk/", "https://tribune.com.pk/pakistan",
                  "https://tribune.com.pk/business"],
        "article_re": r"/story/\d+",
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
        "pages": ["https://www.geo.tv/category/pakistan",
                  "https://www.geo.tv/category/business"],
        "article_re": r"/latest/\d+",
    },
}


def norm(u: str) -> str:
    p = urlparse(u)
    return f"{p.netloc.replace('www.','')}{p.path.rstrip('/')}"


def links_from_page(url, pattern):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return set(), r.status_code
    except Exception as e:
        return set(), type(e).__name__
    found = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', r.text):
        absolute = urljoin(url, html_mod.unescape(href))
        if re.search(pattern, urlparse(absolute).path):
            found.add(norm(absolute))
    return found, 200


print(f"{'source':<11} {'feed_urls':<11} {'page_urls':<11} {'page_only':<11} {'covered%':<10} note")
print("-" * 72)

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

    page_urls, notes = set(), []
    for p in cfg["pages"]:
        got, status = links_from_page(p, cfg["article_re"])
        if status != 200:
            notes.append(f"{urlparse(p).path or '/'}={status}")
        page_urls |= got

    page_only = page_urls - feed_urls
    covered = 100 * (len(page_urls & feed_urls) / len(page_urls)) if page_urls else 0.0
    print(f"{name:<11} {len(feed_urls):<11} {len(page_urls):<11} {len(page_only):<11} "
          f"{covered:<10.1f} {' '.join(notes)}")

    if page_only and name in ("dawn", "tribune"):
        print("    examples only on site, not in feeds:")
        for u in sorted(page_only)[:6]:
            print(f"      {u}")
