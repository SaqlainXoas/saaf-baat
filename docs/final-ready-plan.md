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
- deterministic event grouping and deterministic analysis are active
- Groq editorial review is integrated for bounded story selection and card framing
- API and frontend are connected to live data
- Geo source coverage bug is fixed
- runtime scrape caps and source-level logging are fixed
- constrained live runs now publish between `5` and `9` feed rows instead of the earlier `1`

Not finished:

- live story yield has reached the floor of the intended `5-9` morning brief, but consistency still needs confirmation
- source coverage is not broad enough beyond the reliable core set
- `dawn` discovery still needs cleanup because some runs pull `images.dawn.com` lifestyle links instead of hard-news links
- Groq editorial still needs hardening because schema failures and `429` rate limits can force deterministic fallback
- deterministic ranking still lets some softer feature stories survive when the brief should stay more hard-news selective
- freshness and publish-date trust need more validation
- one more clean live acceptance pass is still needed after the latest classifier and publish-gate tuning

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
- Story formation should move to deterministic event-level grouping instead of whole-batch HDBSCAN/DBSCAN as the main source of truth
- LLM may be used only for bounded split or merge adjudication after deterministic grouping
- Event links should be strict and multi-signal: embedding similarity, headline/entity overlap, and time proximity
- Do not keep the current whole-batch clustering path as an operational fallback after the new grouping path is implemented
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
- replaced production whole-batch clustering with deterministic event grouping
- tightened event-group support so broad buckets need stronger evidence
- added deterministic publish gating ahead of editorial selection
- reduced default scraper pacing for the bounded morning run
- added headline-aware classification to improve civic, education, and public-service categorization
- added early known-URL skipping so repeated runs avoid re-scraping already-known article URLs
- verified a live run with `9` published stories, strong cluster coherence, and correct survival of a previously dropped civic disruption story

## Must Fix Before Ship

- [ ] Run one more fresh constrained live pipeline after the latest tuning pass and verify the DB reflects it
- [ ] Confirm core sources appear in recent raw rows as expected
- [ ] Keep publishable story yield in a consistent `5-9` strong cards over repeated runs
- [ ] Fix `dawn` discovery quality so hard-news links dominate over `images.dawn.com` lifestyle links
- [ ] Harden Groq editorial reliability around schema validation and rate limits
- [ ] Tighten deterministic ranking so softer feature stories lose to stronger civic and public-interest stories
- [ ] Inspect suspicious `publish_date` rows and tighten trust handling
- [ ] Re-check duplicate suppression, event grouping, and publish gating on the newest live batch
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

1. Run a constrained live pipeline pass after the latest classification/publish/runtime tuning.
2. Inspect Supabase recent rows, clusters, and analyzed feed output.
3. Check whether civic/public-service stories classify correctly and whether Dawn contributes the intended hard-news rows.
4. Identify what still lets softer feature stories survive or causes Groq editorial fallback.
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

- technical foundation: `88-90%`
- actual product readiness for the intended morning brief: `78-82%`

Reason:

- the main architecture change has landed and the live brief now reaches the floor of the target range
- the remaining work is narrower: source quality, Groq reliability, story-quality consistency, and date trust
