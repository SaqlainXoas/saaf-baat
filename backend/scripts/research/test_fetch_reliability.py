"""
How reliable is direct article fetching, per publisher?

The current pipeline depends on fetching every article page. This measures the
failure rate that dependency actually carries, and shows exactly what text (if
any) the RSS body omits versus the fetched page.
"""
from __future__ import annotations

import html as html_mod
import re
import time
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests
import trafilatura

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

FEEDS = {
    "dawn":      "https://www.dawn.com/feeds/pakistan",
    "tribune":   "https://tribune.com.pk/feed/pakistan",
    "brecorder": "https://www.brecorder.com/feeds/latest-news",
    "geo":       "https://www.geo.tv/rss/1/1",
    "ary":       "https://arynews.tv/feed/",
    "nation":    "https://www.nation.com.pk/rss/latest",
}
SAMPLE = 15


def clean(raw):
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", raw or ""))).strip()


def body_of(entry):
    best = ""
    for key in ("content", "summary", "description"):
        v = entry.get(key)
        if isinstance(v, list) and v: v = v[0].get("value", "")
        if isinstance(v, dict): v = v.get("value", "")
        if isinstance(v, str) and len(v) > len(best): best = v
    return clean(best)


def fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        return r.status_code, r.text
    except Exception as e:
        return type(e).__name__, ""


print(f"{'publisher':<11} {'tried':<7} {'ok':<5} {'403':<5} {'other':<7} {'fail%':<8} {'median_s':<9}")
print("-" * 60)

tribune_example = None
for pub, feed in FEEDS.items():
    r = requests.get(feed, headers={"User-Agent": UA}, timeout=25)
    entries = feedparser.parse(r.content).entries[:SAMPLE]
    urls = [(e.get("link"), body_of(e)) for e in entries if e.get("link")]

    times, codes = [], []
    def job(item):
        u, rss = item
        t = time.time()
        code, text = fetch(u)
        return code, time.time() - t, u, rss, text

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(job, urls))

    for code, secs, u, rss, text in results:
        codes.append(code); times.append(secs)
        if pub == "tribune" and code == 200 and tribune_example is None and len(rss) > 500:
            extracted = re.sub(r"\s+", " ", trafilatura.extract(text) or "").strip()
            if extracted:
                tribune_example = (u, rss, extracted)

    ok = sum(1 for c in codes if c == 200)
    f403 = sum(1 for c in codes if c == 403)
    other = len(codes) - ok - f403
    med = sorted(times)[len(times)//2] if times else 0
    failpct = 100 * (len(codes)-ok) / max(1, len(codes))
    print(f"{pub:<11} {len(codes):<7} {ok:<5} {f403:<5} {other:<7} {failpct:<8.1f} {med:<9.2f}")

if tribune_example:
    u, rss, page = tribune_example
    print(f"\n--- What Tribune RSS omits vs the fetched page ---\n{u}")
    print(f"rss={len(rss)} chars   page={len(page)} chars")
    # find the longest run of page text absent from the rss body
    rss_low = rss.lower()
    sentences = re.split(r'(?<=[.!?]) ', page)
    missing = [s for s in sentences if len(s) > 40 and s[:60].lower() not in rss_low]
    print(f"sentences in page but not in rss: {len(missing)} of {len(sentences)}")
    for s in missing[:5]:
        print(f"  MISSING: {s[:150]}")
