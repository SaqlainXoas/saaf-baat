# Saaf Baat Final Ready Plan

Status date: **April 3, 2026**

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
- Dawn discovery has been hardened across RSS-first and HTML discovery with stricter same-site filtering
- Groq strict schema mode has local salvage and json-object fallback hardening, but fallback still needs operational confirmation in live runs
- Gemini-first editorial now runs successfully in live conditions after SDK-compatible schema sanitization
- deterministic fallback now enforces the configured finite brief size in live conditions
- editorial prompt now explicitly targets a `5-9` brief and the orchestrator can supplement editorial under-selection up to the floor of `5` when enough publishable candidates exist
- editorial candidate prompts now use trusted timestamps and surface suspicious publish-date counts instead of blindly passing raw publish dates
- latest constrained live acceptance run produced `5` coherent cards with live Gemini-first editorial success and all three core sources contributing fresh rows

Not finished:

- repeated-run consistency still needs monitoring across additional live runs
- source coverage is not broad enough beyond the reliable core set
- editorial LLM layer is now **Gemini-first** with Groq fallback and is working in live conditions; repeated-run reliability still needs confirmation
- deterministic ranking/publish gating was tightened in this iteration, and soft-feature score tuning was added; continue live confirmation that softer feature stories do not occupy slots when stronger civic/public-interest stories exist
- freshness and publish-date trust have been tightened in both scoring and editorial prompt inputs, but still need live DB confirmation against suspicious rows
- frontend presentation still needs final polish and confirmation against the improved live brief

## Current Main Blockers

- Repeated-run confidence: the backend now has a clean constrained acceptance run, but should still be watched across additional live runs.
- Deterministic ranking/publish gating tightening is implemented; continue live confirmation so softer feature stories do not occupy slots that should go to stronger civic and public-interest stories.
- Freshness and publish-date trust handling is hardened more consistently in code and prompt inputs, but still needs live confirmation against the suspicious rows already present in Supabase.
- Frontend handoff and presentation validation are now the next major workstream.

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
- corrected Gemini structured-output config for the installed `google-genai==1.0.0` client
- sanitized Gemini response schema to remove SDK-incompatible fields such as `additionalProperties`
- added deterministic fallback ranking/capping so provider failure should still keep the brief finite
- fixed editorial insertion ordering so higher editorial priority stories are inserted first
- verified a live run where Gemini-first editorial selected the final brief without falling back to Groq
- tightened the shared editorial prompt so it explicitly aims for `5-9` stories when the candidate pool supports it
- added ranked deterministic supplementation so editorial under-selection can still reach the floor of `5` when enough publishable candidates exist
- switched editorial prompt timestamps to trusted timestamps and surfaced suspicious publish-date counts
- added regression coverage for editorial prompt shape, trusted timestamp signalling, and story-floor supplementation
- verified a constrained live run with `5` final cards, live Gemini-first editorial success, good core-source coverage, and clean cluster coherence

## Must Fix Before Ship

- [x] Run one more fresh constrained live pipeline after the latest tuning pass and verify the DB reflects it
- [x] Confirm core sources appear in recent raw rows as expected
- [ ] Keep publishable story yield in a consistent `5-9` strong cards over repeated runs
- [x] Harden Dawn discovery so strict same-site links dominate over `images.dawn.com` lifestyle links (implemented in both RSS and HTML paths; re-check in the next live run)
- [x] Harden strict structured-output reliability (schema-shape hardening + salvage) to reduce editorial-call failures
- [x] Implement Gemini-first editorial with structured JSON output (`application/json`) and configurable model selection
- [ ] Confirm editorial operational reliability across repeated runs: Gemini-first should keep succeeding and Groq fallback should remain rare
- [x] Confirm in a fresh live run that deterministic fallback never inserts more than the configured `5-9` brief size
- [ ] Confirm via repeated live runs that deterministic ranking/publish-gate tightening plus editorial floor supplementation removes softer feature survivors when stronger civic/public-interest stories exist
- [ ] Confirm in a fresh live run that suspicious `publish_date` rows lose ranking strength and do not dominate the brief or the editorial prompt
- [x] Re-check duplicate suppression, event grouping, and publish gating on the newest live batch
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

1. Freeze the current backend path and move to frontend polish/integration.
2. Keep monitoring repeated constrained live runs for `5-9` consistency and soft-story suppression.
3. Re-check suspicious-date behavior on future live rows.
4. Validate the frontend presentation against the improved live brief.

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

- technical foundation: `95%`
- actual product readiness for the intended morning brief: `92-94%`

Reason:

- the backend now has a clean live acceptance run that matches the intended brief shape
- remaining work is mostly repeated-run confidence and frontend presentation, not major backend architecture or pipeline rework
