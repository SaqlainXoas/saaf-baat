"""
Refined hot-news recall.

The first pass measured recall against raw Google News Pakistan, which mixes in
foreign business, entertainment, sport, and even academic papers — content the
brief deliberately excludes, so those "misses" were meaningless.

This version restricts the oracle to stories published by PAKISTANI outlets,
which is the honest question: are we covering what Pakistan's press is covering
today? It also reports which outlets Google surfaces, to reveal any publisher we
should be ingesting but are not.
"""
from __future__ import annotations

import html as html_mod
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

ORACLES = [
    "https://news.google.com/rss?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-PK&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/search?q=Pakistan+when:1d&hl=en-PK&gl=PK&ceid=PK:en",
]

PK_OUTLETS = {
    "dawn", "the express tribune", "express tribune", "geo", "geo.tv", "geo news",
    "ary news", "arynews", "business recorder", "brecorder", "the news international",
    "the nation", "app.com.pk", "associated press of pakistan", "samaa", "samaa tv",
    "bol news", "dunya news", "daily times", "pakistan today", "profit by pakistan today",
    "minute mirror", "the friday times", "24 news hd", "92 news", "aaj news",
    "the current", "nayadaur", "pakistan observer", "the express", "urdupoint",
}

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
amid vs has have had who what when where why how than then them""".split())


def sig(title):
    title = re.sub(r"<[^>]+>", " ", html_mod.unescape(title or ""))
    return {w for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", title.lower()) if w not in STOP}


def pull_titles(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        return [e.get("title", "") for e in feedparser.parse(r.content).entries]
    except Exception:
        return []


def pull_oracle(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        out = []
        for e in feedparser.parse(r.content).entries:
            src = ""
            if e.get("source"):
                src = (e["source"].get("title") or "").strip()
            out.append((e.get("title", ""), src))
        return out
    except Exception:
        return []


with ThreadPoolExecutor(max_workers=6) as pool:
    oracle_raw = [x for b in pool.map(pull_oracle, ORACLES) for x in b]

sources = Counter(s for _, s in oracle_raw if s)
print("Pakistani outlets Google News is surfacing today (top 20):")
for name, n in sources.most_common(20):
    mark = "  <-- we ingest" if name.lower() in {
        "dawn", "the express tribune", "business recorder", "geo.tv", "ary news",
        "the nation", "app.com.pk", "bol news", "daily times"} else ""
    flag = "PK" if name.lower() in PK_OUTLETS else "  "
    print(f"  [{flag}] {name:<38} {n:>3}{mark}")

def strip_src(t):
    return re.sub(r"\s+-\s+[^-]{2,40}$", "", t).strip()

pk_titles = [strip_src(t) for t, s in oracle_raw if s and s.lower() in PK_OUTLETS]

unique, seen = [], []
for t in pk_titles:
    tk = sig(t)
    if len(tk) < 3:
        continue
    if any(len(tk & s) / max(1, min(len(tk), len(s))) >= 0.6 for s in seen):
        continue
    seen.append(tk); unique.append(t)

print(f"\noracle restricted to Pakistani outlets: {len(pk_titles)} headlines -> {len(unique)} distinct stories\n")

for label, urls in [("Tier A only (dawn+tribune+brecorder)", TIER_A),
                    ("Tier A + Tier B (7 publishers)", TIER_A + TIER_B)]:
    with ThreadPoolExecutor(max_workers=10) as pool:
        ours = [t for b in pool.map(pull_titles, urls) for t in b if t]
    our_tokens = [sig(t) for t in ours]
    hits, misses = 0, []
    for t in unique:
        tk = sig(t)
        best = max((len(tk & s) / max(1, min(len(tk), len(s))) for s in our_tokens), default=0)
        if best >= 0.5:
            hits += 1
        else:
            misses.append((round(best, 2), t))
    print(f"{label}")
    print(f"  our articles: {len(ours)}   matched: {hits}/{len(unique)}   RECALL: {100*hits/max(1,len(unique)):.1f}%")
    if misses:
        print(f"  missed ({len(misses)}):")
        for score, t in sorted(misses)[:15]:
            print(f"    [{score}] {t[:95]}")
    print()
