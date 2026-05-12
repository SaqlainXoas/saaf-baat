# Saaf Baat Final Ready Plan

Status date: **May 12, 2026**

## Objective

Ship a trustworthy Pakistan morning brief that reliably publishes a finite set of `5-9` must-know stories from fresh live data.

## Current Snapshot

Completed in the current ship pass:

- backend `/api/feed` now returns `generated_at`, `is_fresh`, and `stories`
- frontend now shows explicit stale, empty, partial, and failure states instead of silently rendering an old or blank brief
- masthead now carries brief identity directly:
  - `Today's Brief · [Day, Month Date]` for a fresh same-day brief
  - `Morning Brief · [Month Date]` for an older brief
- detail pages now anchor back to the product with `← Today's Brief`
- editorial path is now single-provider: Gemini only
- canonical editorial prompt now lives in `backend/config/editorial_prompt.md`
- published API payload no longer exposes noisy `confirmed_facts` and `debated_claims`
- pipeline now records per-source article counts and degraded zero-yield sources in heartbeat state
- `/api/health` now exposes:
  - `last_run_at`
  - `last_successful_run_at`
  - `degraded_sources`
  - `source_article_counts`
  - `pipeline_is_stale`
- scheduled daily pipeline workflow is wired for `0 0 * * *` UTC = `05:00` PKT
- publish-date trust rules are now enforced in code:
  - reject null `published_at`
  - penalize dates more than `1` hour in the future
  - penalize dates more than `36` hours old
- publish ranking now enforces tag diversity:
  - max `3` cards per tag bucket
  - include at least `1` Economy card when a publishable one exists
- homepage cards now surface `what_to_watch`
- source trust treatment is visible on every card
- editorial pass is capped to `8` articles per cluster
- backend integration coverage now exercises fixture ingest -> cluster -> editorial -> publish
- frontend failure-state tests now cover stale, empty, and load-failure behavior

Working:

- Supabase integration is working
- deterministic event grouping and deterministic analysis are active
- frontend reads backend DTOs instead of direct Supabase feed reads
- the brief UI is now honest about freshness and partial availability
- the editorial layer is simpler and more consistent after removing multi-model variance

## Current Main Blocker

- Fresh live verification is still needed on the newest contract:
  - run the daily pipeline on fresh source data
  - confirm `/api/health` reflects the new heartbeat fields correctly
  - confirm the homepage shows the right stale/fresh state against real live timestamps

## Next

1. Run a fresh live pipeline and verify the new heartbeat, freshness, and degraded-source signals end to end.
2. Qualify additional sources in this order:
   - `thenews`
   - `reuters_pk`
   - `business_recorder`
3. Keep monitoring repeated-run consistency so the brief remains a strong `5-9` cards without weak filler.

## Release Definition

The project is ready to ship only when all of the following are true:

- a fresh live run produces `5-9` distinct meaningful story cards
- cards answer `what happened`, `why it matters`, and `what to watch`
- stale or missing briefs are shown honestly in the UI
- duplicate event variants are merged well
- source attribution is visible and trustworthy
- source failures are observable without manual DB inspection
- the frontend presents the brief clearly on desktop and mobile

## Source Status

Core sources:

- `dawn`
- `tribune`
- `geo`

Pending qualification:

- `thenews`
- `reuters_pk`
- `business_recorder`

Disabled for now:

- `ary`

## Work Completed Recently

- removed Groq from the editorial runtime path and env contract
- externalized the canonical editorial prompt to `backend/config/editorial_prompt.md`
- switched feed delivery to a freshness-aware envelope DTO
- removed noisy extracted-fact fields from the published story schema
- added source-health logging and degraded-source reporting to heartbeat and `/api/health`
- wired daily scheduled execution at `05:00` PKT via GitHub Actions
- enforced publish-date penalties and null-date rejection in code
- added tag-diversity selection and Economy minimum handling in publish ranking
- made homepage cards show `what_to_watch` and visible source trust signals
- added integration and failure-state regression coverage around the new brief contract
- audited zero `publisher_topline_score` rows and added fallback prominence scoring when legacy source metadata is missing

## Must Fix Before Ship

- [ ] Run one fresh live pipeline on the new contract and verify the live brief, `/api/feed`, and `/api/health`
- [ ] Confirm `degraded_sources` is empty for intended healthy sources on a fresh successful run
- [ ] Confirm a stale brief shows the fallback banner in the real app against real timestamps
- [ ] Qualify `thenews` before enabling it as a core source
- [ ] Qualify `reuters_pk` before enabling it as a core source

## Should Fix Soon After Ship

- [ ] Add `business_recorder` after `thenews` and `reuters_pk` are stable
- [ ] Keep tightening category consistency into a smaller user-facing set
- [ ] Add operator-visible admin surfacing for source-health signals beyond raw `/api/health`

## Immediate Next Execution Order

1. Run the live pipeline and inspect the resulting heartbeat state.
2. Check the frontend against real live data for fresh, stale, and partial states.
3. Start source qualification for `thenews`.

## Verification Commands

Backend tests:

```bash
cd backend
source venv/bin/activate
pytest
```

Constrained pipeline:

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
