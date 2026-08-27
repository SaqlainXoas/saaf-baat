"""
Do publishers expose Google News sitemaps?

A news sitemap is a structured XML index of everything a publisher put out in
roughly the last 48 hours, maintained for search engines. If one exists it is a
complete, machine-readable answer to "what did this outlet publish today" —
strictly better than scraping section pages for links, and a natural supplement
to RSS where RSS under-covers (e.g. Dawn print-edition stories).

Method: read robots.txt for declared sitemaps, follow sitemap indexes, and
report how many URLs each yields and how fresh they are.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

SITES = {
    "dawn":      "https://www.dawn.com",
    "tribune":   "https://tribune.com.pk",
    "brecorder": "https://www.brecorder.com",
    "geo":       "https://www.geo.tv",
    "ary":       "https://arynews.tv",
    "nation":    "https://www.nation.com.pk",
    "thenews":   "https://www.thenews.com.pk",
    "app":       "https://www.app.com.pk",
}

COMMON = ["/sitemap-news.xml", "/news-sitemap.xml", "/sitemap_news.xml",
          "/sitemap-google-news.xml", "/sitemap.xml", "/sitemap_index.xml"]


def get(url, timeout=25):
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    except Exception:
        return None


def robots_sitemaps(base):
    r = get(f"{base}/robots.txt", timeout=15)
    if not r or r.status_code != 200:
        return []
    return re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text)


def analyse(url):
    r = get(url)
    if not r or r.status_code != 200:
        return None
    body = r.text
    if "<sitemapindex" in body:
        children = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", body)
        news_children = [c for c in children if "news" in c.lower()] or children[:2]
        return {"kind": "index", "children": news_children[:4], "count": len(children)}

    locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", body)
    dates = re.findall(r"<news:publication_date>\s*([^<]+?)\s*</news:publication_date>", body)
    if not dates:
        dates = re.findall(r"<lastmod>\s*([^<]+?)\s*</lastmod>", body)

    now = datetime.now(timezone.utc)
    ages = []
    for d in dates:
        try:
            dt = datetime.fromisoformat(d.strip().replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ages.append((now - dt).total_seconds() / 3600)
        except Exception:
            continue
    return {
        "kind": "news" if "<news:" in body else "urlset",
        "urls": len(locs),
        "dated": len(ages),
        "newest_h": round(min(ages), 1) if ages else None,
        "within_24h": sum(1 for a in ages if 0 <= a <= 24),
        "sample": locs[0][:88] if locs else "",
    }


print(f"{'site':<11} {'sitemap':<58} {'kind':<7} {'urls':<6} {'24h':<6} {'new_h'}")
print("-" * 100)

for name, base in SITES.items():
    declared = robots_sitemaps(base)
    tried, shown = set(), 0
    candidates = [u for u in declared if "news" in u.lower()] + declared[:2] + [base + p for p in COMMON]

    for url in candidates:
        if url in tried or shown >= 2:
            continue
        tried.add(url)
        info = analyse(url)
        if not info:
            continue
        if info["kind"] == "index":
            for child in info["children"]:
                if shown >= 2:
                    break
                sub = analyse(child)
                if sub and sub.get("urls"):
                    print(f"{name:<11} {child[:58]:<58} {sub['kind']:<7} {sub['urls']:<6} "
                          f"{sub['within_24h']:<6} {sub['newest_h']}")
                    shown += 1
            continue
        if info.get("urls"):
            print(f"{name:<11} {url[:58]:<58} {info['kind']:<7} {info['urls']:<6} "
                  f"{info['within_24h']:<6} {info['newest_h']}")
            shown += 1
    if shown == 0:
        print(f"{name:<11} {'(no usable sitemap found)':<58}")
