# Saaf Baat Final Ready Plan

Status date: **April 2, 2026**

## Objective

Ship a trustworthy Pakistan morning brief that reliably produces a finite set of must-know stories from fresh live data.

This is no longer a generic pre-live checklist. It is the current release checklist for the product we actually have today.

## Current Snapshot

Working:

- backend pipeline is wired end-to-end
- Supabase integration is working
- Gemini embeddings are working with `768` dimensions
- clustering and deterministic analysis are active
- Groq editorial review is integrated for bounded story selection and card framing
- API and frontend are connected to live data
- Geo source coverage bug is fixed

Not finished:

- live story yield is too low for the intended morning brief
- source coverage is not broad enough beyond the reliable core set
- freshness and publish-date trust need more validation
- full live acceptance from scrape to frontend still needs a clean pass

## Release Definition

The project is ready to ship only when all of the following are true:

- a fresh live run produces `5-9` distinct meaningful story cards
- cards are on-mission for Pakistan morning relevance
- duplicate event variants are merged well
- source attribution is credible and inspectable
- stale or suspicious dates do not drive the brief blindly
- the frontend presents the feed clearly on desktop and mobile

## Product Decisions Locked For This Phase

- Use a tiered source policy: core sources only if they are reliable
- Morning brief size is flexible `5-9`
- Strong single-source civic/public-interest stories may publish
- LLM use stays bounded to editorial selection and presentation support
- Suspicious dates are low-confidence, not trusted by default
- Card shape should emphasize `why_it_matters` and `what_to_watch`

## Source Status

Core sources:

- `dawn`
- `tribune`
- `geo`

Disabled for now:

- `ary`

Reason:

- `geo` had a real URL-pattern bug and is now fixed
- `ary` remains unreliable for discovery and extraction, so it should not remain a core source

## Work Completed Recently

- tightened source scoping to reduce off-mission raw input
- added Groq structured-output editorial review
- added editorial metadata into published feed rows
- added stage-level pipeline logging
- fixed Geo article URL recognition
- added tests for editorial parsing/gating and Geo scraping
- verified provider-level Gemini and Groq behavior
- verified DB-backed improvement on at least one coherent published row

## Must Fix Before Ship

- [ ] Run a fresh constrained live pipeline and verify the DB reflects it
- [ ] Confirm core sources appear in recent raw rows as expected
- [ ] Raise publishable story yield to a consistent `5-9` strong cards
- [ ] Inspect suspicious `publish_date` rows and tighten trust handling
- [ ] Re-check duplicate suppression and clustering on the newest live batch
- [ ] Confirm the frontend shows the improved live brief cleanly

## Should Fix Soon After Ship

- [ ] Add one more reliable core source if it improves coverage without hurting trust
- [ ] Tighten category consistency into a smaller user-facing set
- [ ] Refine card presentation for faster scanning and stronger visual hierarchy
- [ ] Improve scraper observability where long-running fetches are still opaque

## Can Wait

- [ ] richer point-form explanation styles on cards
- [ ] broader source expansion beyond the reliable core
- [ ] deeper historical analytics or editorial tooling

## Immediate Next Execution Order

1. Run a constrained live pipeline pass.
2. Inspect Supabase recent rows, clusters, and analyzed feed output.
3. Identify why the candidate-to-published yield is still low.
4. Fix the highest-leverage cause with the smallest clean change.
5. Re-run verification.
6. Only then do final frontend polish.

## Verification Commands

Backend tests:

```bash
cd backend
source venv/bin/activate
pytest
```

Constrained live pipeline:

```bash
cd backend
source venv/bin/activate
python run_pipeline.py --disable-playwright --log-level INFO --max-articles-per-source 12
```

Quality report:

```bash
cd backend
source venv/bin/activate
python scripts/quality_report.py --limit 20
```

Frontend sanity:

```bash
cd frontend
npm test
npm run build
```

## Current Confidence Estimate

- technical foundation: `75-80%`
- actual product readiness for the intended morning brief: `55-65%`

Reason:

- the architecture is largely in place
- the live outcome is still not consistently at the quality bar
