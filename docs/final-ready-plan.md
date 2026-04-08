# Saaf Baat Final Ready Plan

Status date: **April 8, 2026**

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
- the latest verified April 8 live run published `7` cards and `/health` reported `pipeline_is_stale: false`
- frontend now consumes the backend `/api/feed` and `/api/stories/{cluster_id}` contracts instead of direct Supabase table reads
- frontend detail pages can now show real original-source article links from backend story detail data
- frontend ship-pass implementation is in place with a calmer editorial presentation system, and local `npm test` plus `npm run build` both pass
- frontend feed presentation now sorts live stories by editorial priority instead of insertion timestamp semantics
- frontend/detail trust presentation no longer relies on raw entity chips as literal consensus bullets; it now derives cleaner editorial summary copy from sources, tags, `why_it_matters`, and `what_to_watch`
- story detail source lists now filter obviously unrelated cluster members before they are shown as supporting reports
- frontend live fetches now bypass stale brief caching so a fresh publish is visible immediately
- desktop homepage and story detail layouts have been reshaped around the local Stitch concept references under `UI-concepts/stitch/`
- the homepage hierarchy now follows a premium editorial structure:
  - one clear lead story
  - two supporting sidebar stories
  - the remaining brief in a lower ranked grid
- detail pages now use a richer editorial hero, cleaner source presentation, and a more honest “consensus summary” block
- story detail pages have been compressed into a quick-brief layout with top reporting links above the fold
- deterministic ranking now carries publisher-prominence signals from ordered discovery and scores the brief as a national-topline product, not only as a coherent civic-impact product

Not finished:

- repeated-run consistency still needs monitoring across additional live runs
- source coverage is not broad enough beyond the reliable core set
- editorial LLM layer is now **Gemini-first** with Groq fallback and is working in live conditions; repeated-run reliability still needs confirmation
- deterministic ranking/publish gating was tightened in this iteration, and soft-feature score tuning was added; continue live confirmation that softer or second-tier stories do not occupy slots when stronger civic/public-interest stories exist
- freshness and publish-date trust have been tightened in both scoring and editorial prompt inputs, but still need live DB confirmation against suspicious rows
- frontend now has the intended live-data contract, corrected ranking semantics, and a stronger visual system, but still needs final live visual confirmation against the improved brief
- the product is now good enough for serious UI review, but homepage composition still may over-weight the lead story visually
- payload cleanup is not fully complete: backend `confirmed_facts` and `debated_claims` still contain some noisy entity/date fragments even though the frontend suppresses the worst presentation issues
- final frontend polish still depends on one more real-browser pass to confirm:
  - homepage ranking feels right
  - the visual hierarchy feels premium rather than heavy
  - story detail still feels fast and finite, not article-like
  - source lists stay clean across multiple live stories

## Current Main Blockers

- Repeated-run confidence: the backend now has a clean constrained acceptance run, but should still be watched across additional live runs.
- Deterministic ranking/publish gating tightening is implemented; continue live confirmation so softer or second-tier stories do not occupy slots that should go to stronger civic and public-interest stories.
- Freshness and publish-date trust handling is hardened more consistently in code and prompt inputs, but still needs live confirmation against the suspicious rows already present in Supabase.
- Frontend composition review remains the main product-facing workstream.
- Cluster cleanliness should continue to be monitored in live output even though obviously unrelated source links are now filtered before display.
- Publisher-prominence scoring still needs watching because several published stories can still carry weak or zero prominence scores.

## Frontend UI Hardening

Issues fixed in this pass:

- homepage was effectively featuring stories by insertion order instead of editorial rank
- the old `What&apos;s agreed` / `What&apos;s debated` UI was misleading because it surfaced raw extracted entity fragments
- detail pages could show obviously unrelated supporting articles from slightly noisy clusters
- the desktop homepage felt too sticky, too tall, and too much like stacked cards rather than a clean morning brief

Redesign completed in this pass:

- replaced the sticky featured-preview layout with a more editorial homepage structure inspired by the local Stitch concepts
- introduced a richer lead-story treatment with a visual hero and cleaner supporting hierarchy
- restyled compact cards so the brief reads like ranked editorial coverage rather than duplicate oversized cards
- rebuilt the trust presentation into a sentence-level summary block that is closer to the intended product meaning
- refreshed story-detail layout so it feels closer to a premium article brief with stronger hierarchy and cleaner original-source presentation
- later tightened that story-detail layout into a faster quick-brief surface with top reporting links inside the main brief card

What still remains after this pass:

- one more live browser verification pass across multiple stories on desktop and mobile
- confirm the lead story now consistently matches backend editorial priority in live output
- confirm the homepage lead/supporting/grid balance feels premium rather than oversized
- confirm the new summary blocks feel honest and useful across several real stories, not just one or two
- continue watching for cluster contamination upstream even though the UI now suppresses the most obvious bad source links

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
- switched the frontend live-data adapter from direct Supabase reads to the backend API DTOs
- fixed the frontend live detail route so it can render original source articles from `/api/stories/{cluster_id}`
- implemented a calm editorial UI pass across the homepage, cards, and story detail view
- added frontend regression coverage for the backend API adapter and richer featured-card metadata rendering
- verified local frontend test and production build success after the live-data and UI pass
- re-ranked frontend feed presentation by editorial priority so the homepage lead story aligns with the backend editorial decision
- replaced raw “agreed/debated” entity chips with derived editorial summary blocks that better match the intended product meaning
- aligned homepage and story-detail visual hierarchy with the local Stitch concept exports while preserving Saaf Baat branding and `Subah Bakhair` framing
- added display-side filtering of obviously unrelated source links in story detail output and backend tests to lock it in
- added a new frontend presentation helper layer to derive cleaner summary language from live backend story data
- added freshness-safe frontend API fetch behavior so the live brief updates immediately after publish
- added publisher-topline discovery metadata and national-topline-aware ranking guardrails
- reshaped story detail pages into quick-brief reading surfaces instead of article-like pages
- verified a fresh April 8 live run with `7` published cards, `pipeline_is_stale: false`, and quality-report success

## Must Fix Before Ship

- [x] Run one more fresh constrained live pipeline after the latest tuning pass and verify the DB reflects it
- [x] Confirm core sources appear in recent raw rows as expected
- [ ] Keep publishable story yield in a consistent `5-9` strong cards over repeated runs
- [x] Harden Dawn discovery so strict same-site links dominate over `images.dawn.com` lifestyle links (implemented in both RSS and HTML paths; re-check in the next live run)
- [x] Harden strict structured-output reliability (schema-shape hardening + salvage) to reduce editorial-call failures
- [x] Implement Gemini-first editorial with structured JSON output (`application/json`) and configurable model selection
- [ ] Confirm editorial operational reliability across repeated runs: Gemini-first should keep succeeding and Groq fallback should remain rare
- [x] Confirm in a fresh live run that deterministic fallback never inserts more than the configured `5-9` brief size
- [ ] Confirm via repeated live runs that deterministic ranking/publish-gate tightening plus editorial floor supplementation removes softer or second-tier survivors when stronger civic/public-interest stories exist
- [ ] Confirm in a fresh live run that suspicious `publish_date` rows lose ranking strength and do not dominate the brief or the editorial prompt
- [x] Re-check duplicate suppression, event grouping, and publish gating on the newest live batch
- [ ] Confirm the frontend shows the improved live brief cleanly with real backend API data on desktop and mobile after the latest ranking and UI-hardening pass
- [ ] Make a final call on homepage composition density and lead-card weight after reviewing the fresh live brief in a real browser

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

1. Review the fresh live brief in a real browser and decide whether homepage lead/supporting/grid composition needs one more density pass.
2. Confirm the homepage lead card matches editorial priority rather than insertion order.
3. Keep monitoring repeated constrained live runs for `5-9` consistency and soft-story suppression.
4. Re-check suspicious-date behavior, prominence scoring, and cluster cleanliness on future live rows.

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
- actual product readiness for the intended morning brief: `93-95%`

Reason:

- the backend now has a fresh live run that matches the intended brief shape more closely, including true topline stories
- remaining work is final composition judgment, repeated-run confidence, and semantic cleanup rather than major backend architecture or pipeline rework
