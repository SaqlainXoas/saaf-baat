<p align="center">
  <img src="frontend/public/icon.svg" alt="Saaf Baat Logo" width="110" />
</p>

<h1 align="center">Saaf Baat</h1>
<p align="center"><strong>A selective Pakistan morning brief built to answer one question fast: what do I need to know today, and why does it matter?</strong></p>

## What This Product Is

Saaf Baat is not an infinite news reader.

The goal is a calm, finite morning brief with roughly `5-9` strong story cards. Each card should help an ordinary person in Pakistan understand:

- what happened
- why it matters
- what to watch next
- where the reporting came from

The product should feel trustworthy, modern, and quick to scan before getting on with the day.

## Current Product Direction

These decisions are currently intentional and active:

- Keep the feed finite: target `5-9` cards, not endless scrolling.
- Prefer importance over recency.
- Treat the brief as **national-topline first**, then strongest direct public-life stories.
- Prefer one clean card per real story over multiple headline variants.
- Keep deterministic extraction for evidence, attribution, and clustering support.
- Use the LLM layer only for bounded editorial selection and card framing, not for free-form rewriting of the whole product.
- Story grouping should move toward a deterministic event graph, not whole-batch HDBSCAN/DBSCAN as the main truth source.
- Use LLM only for bounded split or merge adjudication when deterministic grouping is genuinely ambiguous.
- Event links should be strict, not loose: use strong embedding similarity plus headline/entity overlap plus time closeness.
- The new event-grouping path should replace legacy whole-batch clustering directly; do not keep the old clustering logic as an active fallback path.
- Allow a strong single-source story only when the civic or public-impact signal is clearly high.
- Treat suspicious publish dates as low-confidence data, not as automatically trustworthy.
- Prefer a small set of reliable Pakistani sources over a large unreliable source list.
- Keep story pages as quick briefs, not long article clones.

## Current Status

As of `2026-05-12`, the backend and frontend are on the intended morning-brief contract, the product now handles stale and missing briefs honestly, and the remaining work is live operational verification rather than product-definition churn.

Working:

- scraper pipeline runs and inserts fresh rows from the core sources
- Gemini embeddings are working with DB-compatible `768` dimensions
- deterministic event grouping replaced whole-batch density clustering in production
- deterministic analysis and publish gating are wired end-to-end
- Gemini-only structured editorial review is the active editorial path
- deterministic fallback now keeps the brief finite if editorial fails
- Dawn same-site filtering is hardened across RSS-first and HTML discovery
- recent constrained live runs now produce a finite `5-9` morning brief instead of collapsing into one blob or overflowing the feed
- the latest fresh live run produced `7` published cards with all three core sources contributing
- the brief now ranks toward Pakistan morning toplines first by carrying ordered discovery prominence into publish scoring
- frontend now reads the backend `/api/feed` and `/api/stories/{cluster_id}` DTOs instead of direct Supabase table reads
- `/api/feed` now exposes freshness explicitly through `generated_at` and `is_fresh`
- detail pages can now render real original-source article links from the backend story route
- frontend fetches now use live API data directly instead of serving stale cached brief data after a publish
- homepage and detail routes now show explicit stale, empty, partial, and error states instead of failing silently
- homepage and story detail UI now follow the Stitch-inspired editorial system more closely
- story detail pages now behave like quick briefs instead of mini article pages
- frontend test suites and production build are green on the current worktree
- pipeline heartbeat state now records:
  - `last_run_at`
  - `last_successful_run_at`
  - `source_article_counts`
  - `degraded_sources`
- `/health` now exposes `pipeline_is_stale` using a hard `28` hour threshold

Still being monitored:

- repeated-run consistency: keep the brief in `5-9` across additional live runs
- final story quality: keep softer or second-tier stories out when stronger national/public-interest stories exist
- fresh live verification: confirm the new freshness and health signals against the next real pipeline run
- source qualification: add `thenews`, `reuters_pk`, and `business_recorder` only after they pass the reliability bar

## Current Source Status

Core sources right now:

- `dawn`
- `tribune`
- `geo`

Disabled for now:

- `ary`

`ary` was not removed arbitrarily. It was investigated live and found unreliable for both discovery and extraction. The current policy is to disable flaky sources rather than let them pollute downstream clustering and editorial selection.

## How The Pipeline Works

```text
scrape sources
-> normalize + deduplicate
-> reject null or suspicious publish dates aggressively
-> embed articles with Gemini
-> cluster related coverage
-> score source prominence and national-topline strength
-> run deterministic analysis
-> run bounded Gemini editorial review on candidates
-> publish the best morning-brief cards
-> serve via FastAPI to the Next.js frontend
```

### Deterministic Layers

- URL/domain filtering and source scoping
- raw article storage in Supabase
- embeddings for similarity grouping
- clustering and representative-article selection
- entity extraction, source attribution, and classification support

### LLM Layer

Gemini is the single editorial layer. It decides whether a candidate cluster deserves publication and shapes structured card fields such as:

- `why_it_matters`
- `what_to_watch`
- `impact_line`
- priority
- grade
- tags

The canonical prompt lives in `backend/config/editorial_prompt.md`.

This is intentionally bounded. The system is not meant to become an opaque LLM-only summarizer.

## Main Problem We Are Solving Now

The core challenge is no longer basic plumbing or story formation.

The remaining challenge is final product judgment:

- keep the selected `5-9` stories aligned with what a Pakistan reader would actually expect as the day’s toplines
- keep homepage composition feeling premium and finite rather than oversized or article-heavy
- keep the product honest about what the backend truly knows

The main architecture issue is already fixed:

- global density clustering is no longer the production grouping method
- deterministic event grouping now produces distinct story clusters instead of one news blob

The remaining live issues are narrower:

- keep the surviving `5-9` stories on-mission for a must-know Pakistan morning brief
- continue suppressing weaker or second-tier survivors when stronger national/public-life stories are available
- keep repeated editorial runs reliable enough that fallback remains exceptional
- keep freshness and publish-date handling trustworthy on future live rows
- finish the final homepage/detail visual signoff in a real browser

## Next Phase

The current phase is `freshness-safe brief ship hardening with backend monitoring`.

The next work items are:

1. Run a fresh live pipeline and verify `/api/feed` and `/api/health` on the new contract.
2. Keep monitoring constrained live runs for repeated `5-9` consistency and better topline selection.
3. Qualify `thenews`, then `reuters_pk`, before expanding the core source set.
4. Do only targeted backend ranking/prominence tuning unless a new live regression appears.

## Main Remaining Risks

These are the current areas still worth watching:

- repeated-run confidence, not one-run confidence
- occasional second-tier survivors if ranking/editorial pressure drifts
- operational verification of the new heartbeat and freshness signals on live runs
- source qualification discipline as coverage expands beyond the current core set

## Repository Layout

```text
backend/
  config/                   # sources and classification rules
  scripts/                  # quality inspection helpers
  src/
    agents/                 # embeddings, clustering, analysis, editorial
    api/                    # FastAPI app and routes
    db/                     # Supabase client and models
    pipeline/               # orchestration
    scrapers/               # source discovery and extraction
  tests/                    # pytest suites
  main.py                   # API entrypoint
  run_pipeline.py           # pipeline entrypoint

frontend/
  src/app/                  # Next.js routes
  src/components/           # UI components
  src/data/                 # API client and adapters
  tests/                    # Jest + Testing Library

docs/
  final-ready-plan.md       # active release checklist

program.md                  # operating rules and product principles
AGENTS.md                   # stable repo blueprint for autonomous evaluators
```

## Setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Environment

Backend env lives in `backend/.env`.

Required:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `GEMINI_API_KEY`

Important optional controls:

- `SAAF_ENABLE_EDITORIAL_LLM`
- `SAAF_EDITORIAL_GEMINI_MODEL` (default `gemini-3.1-flash-lite-preview`)
- `SAAF_EDITORIAL_CANDIDATE_LIMIT`
- `SAAF_EDITORIAL_MAX_STORIES`
- `SAAF_LOW_COST_MODE`
- `SAAF_MAX_ARTICLES_PER_SOURCE`
- `SAAF_EMBEDDING_BACKFILL_LIMIT`
- `SAAF_ENABLE_PLAYWRIGHT_FALLBACK`
- `SAAF_PIPELINE_HEARTBEAT_FILE`

## API Notes

Current feed contract:

- `/api/feed` returns:
  - `generated_at`
  - `is_fresh`
  - `stories`
- `is_fresh` is `true` when the published brief was generated within the last `20` hours
- if no brief exists or too few stories are available, the frontend surfaces explicit preparation or partial-brief messaging instead of rendering a silent empty state

Other useful env values:

- `BACKEND_CORS_ALLOW_ORIGINS`
- `SAAF_FRONTEND_REVALIDATE_URL`
- `SAAF_FRONTEND_REVALIDATE_SECRET`

Frontend env usually needs:

- `BACKEND_API_BASE_URL` or `NEXT_PUBLIC_BACKEND_API_BASE_URL`
- `NEXT_PUBLIC_STRICT_LIVE_DATA=1`
- `NEXT_PUBLIC_CITY_NAME`
- `NEXT_PUBLIC_DEFAULT_THEME`
- `REVALIDATE_SECRET`

See `backend/.env.example` for the backend template and `frontend/.env.example` for the frontend live-data template.

## Useful Commands

Backend tests:

```bash
cd backend
source venv/bin/activate
pytest
```

Constrained pipeline run:

```bash
cd backend
source venv/bin/activate
python run_pipeline.py --disable-playwright --log-level INFO --max-articles-per-source 4
```

Quality report:

```bash
cd backend
source venv/bin/activate
python scripts/quality_report.py --limit 12 --min-avg-sim 0.65 --min-centroid-sim 0.70 --fail-on-missing-embeddings
```

Frontend tests:

```bash
cd frontend
npm test
npm run build
```

## How To Evaluate Progress

The project should be judged by live output, not by passing unit tests alone.

Good signs:

- recent rows are on-mission Pakistan stories
- the feed contains `5-9` distinct cards
- duplicate events are merged cleanly
- cards have useful `why it matters` and `what to watch` fields
- source attribution is credible and easy to inspect

Bad signs:

- only `1-3` cards appear after a fresh run
- celebrity/sports/global filler enters the brief
- stale or suspicious dates leak into top cards
- one event appears as multiple cards
- source extraction is flaky but still left enabled

## Documentation Policy

Tracked docs should stay minimal and current:

- `README.md`
- `AGENTS.md`
- `program.md`
- `docs/final-ready-plan.md`

Everything else belongs in local scratch or `codex-thinking/` notes, not in permanent tracked docs.
