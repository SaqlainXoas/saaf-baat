# Ingestion research scripts

Re-runnable evidence behind the ingest design described in `CLAUDE.md`.
None of these are part of the pipeline — they exist so source-health and
coverage claims can be re-checked rather than assumed.

Run from `backend/` with the venv active:

```bash
source venv/bin/activate && python scripts/research/probe_feeds.py
```

| Script | What it answers |
|---|---|
| `feeds_catalog.py` | Candidate feed list (data, not a script) |
| `probe_feeds.py` | Which feeds respond, parse, and are fresh. **Run this first when a source looks wrong.** |
| `compare_rss_vs_fetch.py` | Is RSS body text as good as fetching + extracting the page? |
| `test_fetch_reliability.py` | Per-publisher failure rate of direct article fetching |
| `test_coverage.py` | Do feeds miss URLs the site's section pages show? |
| `test_coverage_recency.py` | Are those missed URLs actually today's news? |
| `test_hotnews_recall.py` | Recall vs Google News Pakistan (raw — noisy) |
| `test_hotnews_recall2.py` | Recall vs Pakistani outlets only (the honest benchmark) |
| `test_combined_recall.py` | Does RSS + sitemap close the coverage gap? |
| `discover_feeds.py` | Find working feeds for publishers we don't ingest |
| `test_sitemaps.py` | Which publishers expose Google-News sitemaps |
| `trace_misses.py` | Where do genuinely-missed stories live? |
| `dawn_deep.py` | Dawn's full discovery surface |
| `prototype_ingest.py` | **Reference implementation** of the proposed design, end to end |

Outputs (`*.json`) are snapshots of a single run and are gitignored.

Be considerate: `prototype_ingest.py` issues ~28 requests per run. Avoid tight
loops against publisher sites, and keep a real User-Agent set.
