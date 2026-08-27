"""
Decisive test: does RSS + news-sitemap discovery close the coverage gap?

RSS gives us clean full text but under-covers (measured ~62% recall against
Pakistani outlets). News sitemaps are a second, independent, structured channel
listing everything a publisher pushed in ~48h. This measures the union.

Also reports how many extra articles the sitemap contributes that RSS lacks —
i.e. how many page fetches an RSS+sitemap design would actually need.
"""
from __future__ import annotations

import html as html_mod
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

RSS = [
    "https://www.dawn.com/feeds/home", "https://www.dawn.com/feeds/latest-news",
    "https://www.dawn.com/feeds/pakistan", "https://www.dawn.com/feeds/business",
    "https://www.dawn.com/feeds/world",
    "https://tribune.com.pk/feed/home", "https://tribune.com.pk/feed/pakistan",
    "https://tribune.com.pk/feed/business",
    "https://www.brecorder.com/feeds/latest-news", "https://www.brecorder.com/feeds/pakistan",
    "https://www.brecorder.com/feeds/markets",
    "https://www.geo.tv/rss/1/1", "https://www.geo.tv/rss/1/4",
    "https://arynews.tv/feed/", "https://arynews.tv/category/pakistan/feed/",
    "https://www.nation.com.pk/rss/latest",
    "https://www.app.com.pk/feed/", "https://www.app.com.pk/category/national/feed/",
]

SITEMAPS = [
    "https://www.dawn.com/feeds/sitemap",
    "https://tribune.com.pk/sitemap/sitemap_main.xml",
    "https://www.brecorder.com/feeds/sitemap",
    "https://www.geo.tv/assets/uploads/google_news_latest.xml",
    "https://arynews.tv/sitemap/news_sitemap.xml",
    "https://www.nation.com.pk/sitemap_news_google.xml",
    "https://www.thenews.com.pk/assets/uploads/google_news_latest.xml",
]

ORACLES = [
    "https://news.google.com/rss?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/search?q=Pakistan+when:1d&hl=en-PK&gl=PK&ceid=PK:en",
]

PK_OUTLETS = {"dawn", "the express tribune", "express tribune", "geo", "geo.tv", "geo news",
              "ary news", "business recorder", "brecorder", "the news international",
              "the nation", "the nation (pakistan )", "app.com.pk", "samaa", "bol news",
              "dunya news", "daily times", "pakistan today", "the news pakistan"}

STOP = set("""the a an and or of for to in on at by with from as is are was were be been this
that these those it its his her their our your my we they he she you i not no after before
over under about into out up down new says say said will would can could amid vs has have
had who what when where why how than then them pakistan""".split())


def sig(t):
    t = re.sub(r"<[^>]+>", " ", html_mod.unescape(t or ""))
    return {w for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", t.lower()) if w not in STOP}


def slug_tokens(url: str) -> set[str]:
    """Headlines are embedded in these publishers' URL slugs — usable for matching."""
    path = urlparse(url).path
    words = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", path.replace("-", " ").replace("/", " "))
    return {w.lower() for w in words if w.lower() not in STOP and not w.isdigit()}


def get(url, timeout=25):
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    except Exception:
        return None


def rss_items(url):
    r = get(url)
    if not r:
        return []
    return [(e.get("title", ""), e.get("link", "")) for e in feedparser.parse(r.content).entries]


def sitemap_items(url):
    r = get(url)
    if not r or r.status_code != 200:
        return []
    body = r.text
    out = []
    now = datetime.now(timezone.utc)
    blocks = re.findall(r"<url>(.*?)</url>", body, re.S) or [body]
    for b in blocks:
        loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", b)
        if not loc:
            continue
        title = re.search(r"<news:title>\s*(.*?)\s*</news:title>", b, re.S)
        date = re.search(r"<news:publication_date>\s*([^<]+?)\s*</news:publication_date>", b)
        fresh = True
        if date:
            try:
                dt = datetime.fromisoformat(date.group(1).strip().replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                fresh = (now - dt).total_seconds() <= 36 * 3600
            except Exception:
                pass
        if fresh:
            out.append((html_mod.unescape(title.group(1)) if title else "", loc.group(1)))
    return out


def canon(u):
    p = urlparse(u)
    return f"{p.netloc.replace('www.','')}{p.path.rstrip('/')}"


with ThreadPoolExecutor(max_workers=12) as pool:
    rss_all = [x for b in pool.map(rss_items, RSS) for x in b]
    sm_all = [x for b in pool.map(sitemap_items, SITEMAPS) for x in b]

rss_urls = {canon(u) for _, u in rss_all if u}
sm_urls = {canon(u) for _, u in sm_all if u}

print(f"RSS       : {len(rss_all)} items -> {len(rss_urls)} unique URLs")
print(f"SITEMAPS  : {len(sm_all)} fresh items -> {len(sm_urls)} unique URLs")
print(f"UNION     : {len(rss_urls | sm_urls)} unique URLs")
print(f"sitemap-only (would need a fetch): {len(sm_urls - rss_urls)}")
print(f"rss-only   (free full text)      : {len(rss_urls - sm_urls)}\n")

# oracle
def oracle_items(url):
    r = get(url)
    if not r:
        return []
    out = []
    for e in feedparser.parse(r.content).entries:
        src = (e.get("source", {}) or {}).get("title", "") or ""
        out.append((re.sub(r"\s+-\s+[^-]{2,40}$", "", e.get("title", "")).strip(), src))
    return out


with ThreadPoolExecutor(max_workers=6) as pool:
    oracle_raw = [x for b in pool.map(oracle_items, ORACLES) for x in b]

pk = [t for t, s in oracle_raw if s and s.lower() in PK_OUTLETS]
unique, seen = [], []
for t in pk:
    tk = sig(t)
    if len(tk) < 3:
        continue
    if any(len(tk & s) / max(1, min(len(tk), len(s))) >= 0.6 for s in seen):
        continue
    seen.append(tk); unique.append(t)

print(f"oracle (Pakistani outlets): {len(unique)} distinct stories\n")

def recall(label, titles, urls):
    pools = [sig(t) for t in titles if t] + [slug_tokens(u) for u in urls]
    hits, misses = 0, []
    for t in unique:
        tk = sig(t)
        best = max((len(tk & s) / max(1, min(len(tk), len(s))) for s in pools if s), default=0)
        if best >= 0.5:
            hits += 1
        else:
            misses.append((round(best, 2), t))
    print(f"{label:<34} recall {100*hits/max(1,len(unique)):5.1f}%   ({hits}/{len(unique)})")
    return misses

recall("RSS only", [t for t, _ in rss_all], list(rss_urls))
recall("SITEMAP only", [t for t, _ in sm_all], list(sm_urls))
misses = recall("RSS + SITEMAP (union)", [t for t, _ in rss_all] + [t for t, _ in sm_all],
                list(rss_urls | sm_urls))

print(f"\nstill missed ({len(misses)}):")
for score, t in sorted(misses)[:18]:
    print(f"  [{score}] {t[:96]}")
