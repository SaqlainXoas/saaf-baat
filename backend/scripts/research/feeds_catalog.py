"""
Candidate feed catalog for Saaf Baat ingestion research.

Deliberately much wider than the shipping source list: the point of the probe
is to find out empirically which endpoints are real, fresh, and rich, rather
than to assume. Entries here are candidates, not commitments.
"""
from __future__ import annotations

# (publisher, label, url)
CANDIDATES: list[tuple[str, str, str]] = [
    # ---- Dawn ----
    ("dawn", "home",        "https://www.dawn.com/feeds/home"),
    ("dawn", "latest",      "https://www.dawn.com/feeds/latest-news"),
    ("dawn", "pakistan",    "https://www.dawn.com/feeds/pakistan"),
    ("dawn", "business",    "https://www.dawn.com/feeds/business"),
    ("dawn", "world",       "https://www.dawn.com/feeds/world"),
    ("dawn", "sport",       "https://www.dawn.com/feeds/sport"),
    ("dawn", "opinion",     "https://www.dawn.com/feeds/opinion"),

    # ---- Express Tribune ----
    ("tribune", "home",     "https://tribune.com.pk/feed/home"),
    ("tribune", "pakistan", "https://tribune.com.pk/feed/pakistan"),
    ("tribune", "business", "https://tribune.com.pk/feed/business"),
    ("tribune", "world",    "https://tribune.com.pk/feed/world"),
    ("tribune", "sports",   "https://tribune.com.pk/feed/sports"),

    # ---- Business Recorder ----
    ("brecorder", "latest",     "https://www.brecorder.com/feeds/latest-news"),
    ("brecorder", "pakistan",   "https://www.brecorder.com/feeds/pakistan"),
    ("brecorder", "markets",    "https://www.brecorder.com/feeds/markets"),
    ("brecorder", "business",   "https://www.brecorder.com/feeds/business-finance"),
    ("brecorder", "world",      "https://www.brecorder.com/feeds/world"),

    # ---- Geo ----
    ("geo", "pakistan",  "https://www.geo.tv/rss/1/1"),
    ("geo", "business",  "https://www.geo.tv/rss/1/53"),
    ("geo", "latest",    "https://www.geo.tv/rss/1/53"),
    ("geo", "world",     "https://www.geo.tv/rss/1/4"),

    # ---- The News ----
    ("thenews", "rss11",  "https://www.thenews.com.pk/rss/1/1"),
    ("thenews", "rss13",  "https://www.thenews.com.pk/rss/1/3"),
    ("thenews", "latest", "https://www.thenews.com.pk/rss/2/2"),

    # ---- ARY ----
    ("ary", "main",      "https://arynews.tv/feed/"),
    ("ary", "pakistan",  "https://arynews.tv/category/pakistan/feed/"),
    ("ary", "business",  "https://arynews.tv/category/business/feed/"),

    # ---- The Nation ----
    ("nation", "latest",   "https://www.nation.com.pk/rss/latest"),
    ("nation", "national", "https://www.nation.com.pk/rss/national"),
    ("nation", "business", "https://www.nation.com.pk/rss/business"),

    # ---- APP (state wire) ----
    ("app", "main",      "https://www.app.com.pk/feed/"),
    ("app", "national",  "https://www.app.com.pk/category/national/feed/"),
    ("app", "business",  "https://www.app.com.pk/category/business/feed/"),

    # ---- Samaa ----
    ("samaa", "main",  "https://www.samaa.tv/feed/"),
    ("samaa", "rss1",  "https://www.samaa.tv/rss/1"),

    # ---- Pakistan Today / Profit ----
    ("pakistantoday", "main",   "https://www.pakistantoday.com.pk/feed/"),
    ("profit",        "main",   "https://profit.pakistantoday.com.pk/feed"),

    # ---- Dunya ----
    ("dunya", "main",  "https://dunyanews.tv/rss/rss.xml"),
    ("dunya", "pak",   "https://dunyanews.tv/en/rss/Pakistan"),

    # ---- Bol ----
    ("bol", "main",  "https://www.bolnews.com/feed/"),

    # ---- 92 News ----
    ("92news", "main",  "https://www.92newshd.tv/feed"),

    # ---- Urdu Point / Minute Mirror / Daily Times ----
    ("dailytimes",  "main", "https://dailytimes.com.pk/feed/"),
    ("minutemirror", "main", "https://minutemirror.com.pk/feed/"),

    # ---- Aggregator safety net (evaluate separately, licensing caveats) ----
    ("googlenews", "pk-en",
     "https://news.google.com/rss?hl=en-PK&gl=PK&ceid=PK:en"),
    ("googlenews", "pk-topic-nation",
     "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-PK&gl=PK&ceid=PK:en"),
]
