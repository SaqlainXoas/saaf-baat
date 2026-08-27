"""
The question that actually matters: would an RSS-first ingest MISS today's big
Pakistan stories?

Method: use Google News (Pakistan edition) as an independent oracle of what is
big today — it aggregates hundreds of outlets and we do not control it. Then
check whether our own publisher feeds contain a matching story.

Matching is done on significant-token overlap between headlines, which is crude
but symmetric and good enough to spot a wholly missing story.

Reported: recall (share of oracle stories our feeds cover) and the actual misses,
so they can be inspected rather than trusted to a number.
"""
from __future__ import annotations

import html as html_mod
import re
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

ORACLES = [
    "https://news.google.com/rss?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-PK&gl=PK&ceid=PK:en",
]

# Candidate ingest sets to compare.
TIER_A = [
    "https://www.dawn.com/feeds/home", "https://www.dawn.com/feeds/latest-news",
    "https://www.dawn.com/feeds/pakistan", "https://www.dawn.com/feeds/business",
    "https://www.dawn.com/feeds/world",
    "https://tribune.com.pk/feed/home", "https://tribune.com.pk/feed/pakistan",
    "https://tribune.com.pk/feed/business",
    "https://www.brecorder.com/feeds/latest-news", "https://www.brecorder.com/feeds/pakistan",
    "https://www.brecorder.com/feeds/markets",
]
TIER_B = [
    "https://www.geo.tv/rss/1/1", "https://www.geo.tv/rss/1/4",
    "https://arynews.tv/feed/", "https://arynews.tv/category/pakistan/feed/",
    "https://www.nation.com.pk/rss/latest",
    "https://www.app.com.pk/feed/", "https://www.app.com.pk/category/national/feed/",
    "https://www.bolnews.com/feed/", "https://dailytimes.com.pk/feed/",
]

STOP = set("""the a an and or of for to in on at by with from as is are was were be been
this that these those it its his her their our your my we they he she you i not no
after before over under about into out up down new says say said will would can could
pakistan pakistani govt government amid vs after""".split())


def sig_tokens(title: str) -> set[str]:
    title = re.sub(r"<[^>]+>", " ", html_mod.unescape(title or ""))
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", title.lower())
    return {w for w in words if w not in STOP}


def pull(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        return [e.get("title", "") for e in feedparser.parse(r.content).entries]
    except Exception:
        return []


def collect(urls):
    with ThreadPoolExecutor(max_workers=10) as pool:
        return [t for batch in pool.map(pull, urls) for t in batch if t]


def strip_source(title: str) -> str:
    # Google News appends " - Publisher"
    return re.sub(r"\s+-\s+[^-]{2,40}$", "", title).strip()


oracle_titles = [strip_source(t) for t in collect(ORACLES)]
# de-duplicate oracle stories that are the same event from different outlets
oracle_unique, oracle_seen = [], []
for t in oracle_titles:
    tk = sig_tokens(t)
    if len(tk) < 3:
        continue
    if any(len(tk & s) / max(1, min(len(tk), len(s))) >= 0.6 for s in oracle_seen):
        continue
    oracle_seen.append(tk)
    oracle_unique.append(t)

print(f"oracle (Google News PK): {len(oracle_titles)} headlines -> {len(oracle_unique)} distinct stories\n")

for label, urls in [("Tier A only (dawn+tribune+brecorder)", TIER_A),
                    ("Tier A + Tier B (7 publishers)", TIER_A + TIER_B)]:
    ours = collect(urls)
    our_tokens = [sig_tokens(t) for t in ours]
    hits, misses = 0, []
    for t in oracle_unique:
        tk = sig_tokens(t)
        best = max((len(tk & s) / max(1, min(len(tk), len(s))) for s in our_tokens), default=0)
        if best >= 0.5:
            hits += 1
        else:
            misses.append((round(best, 2), t))
    recall = 100 * hits / max(1, len(oracle_unique))
    print(f"{label}")
    print(f"  our articles: {len(ours)}   matched: {hits}/{len(oracle_unique)}   recall: {recall:.1f}%")
    if misses:
        print(f"  missed stories ({len(misses)}):")
        for score, t in sorted(misses)[:12]:
            print(f"    [{score}] {t[:95]}")
    print()
