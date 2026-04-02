# Repository Guidelines

## Current Phase

- Working directory: `/Users/saqlain/projects/personal/saaf-baat`
- Active phase: `live-quality hardening` before ship
- Core product target: a trustworthy Pakistan morning brief with `5-9` must-know stories
- Source-of-truth docs:
  - `README.md`
  - `AGENTS.md`
  - `program.md`
  - `docs/final-ready-plan.md`

## Product Reality Check

The project is past the basic build stage. It already has scraping, embeddings, clustering, DB integration, API delivery, frontend rendering, and a bounded Groq editorial layer.

The project is not done yet because the live morning brief still does not reliably produce the intended `5-9` strong cards from fresh data.

Current state:

- `dawn`, `tribune`, and `geo` are the active core sources
- `ary` is disabled because live discovery and extraction were unreliable
- deterministic extraction still matters for explainability
- Groq is now allowed for editorial selection and card framing only
- the main remaining work is source quality, editorial reliability, freshness, and feed trust
- latest constrained live runs now reach the `5-9` target range, but some surviving stories are still softer than the product goal wants

## End Vision

Saaf Baat should feel like a quick, modern, trustworthy morning briefing for Pakistan.

When a user opens it, they should immediately understand:

- what happened
- why it matters to ordinary life or public affairs
- what to watch next
- which original publishers support the story

The product should feel finite, calm, and selective. It should not become an infinite noisy feed.

## Locked Product Decisions

These decisions are currently approved and should be treated as active constraints unless explicitly changed by the user:

- Use a tiered source model:
  - core sources must work reliably every day
  - flaky or partial sources should be disabled, not tolerated
- Morning brief size should be flexible `5-9`, not forced to `9`
- A single-source story may still publish if it has strong civic/public-impact value
- LLM use should stay bounded to editorial selection and presentation support
- Story grouping should use a deterministic event-graph approach, not global HDBSCAN/DBSCAN as the primary source of truth
- LLM may assist only on ambiguous split/merge decisions after deterministic grouping
- Event links should be strict and multi-signal, not loose semantic similarity alone
- Do not preserve the current global clustering path as an operational fallback once the new event-grouping path is implemented
- Suspicious publish dates should lower confidence, not be trusted blindly
- Cards should emphasize `why_it_matters` and `what_to_watch`
- Category surface should stay small and user-legible

## Working Principles

- Read `program.md` before making architecture, scraper, ranking, or product-direction changes.
- Prefer reliability, clarity, and fewer moving parts over feature accumulation.
- Verify every meaningful claim with tests, DB inspection, API checks, or live pipeline output.
- If a source is flaky, fix it properly or disable it.
- If a heuristic chain becomes hard to reason about, simplify it.
- Do not optimize for article volume. Optimize for morning-brief quality.
- Do not revert unrelated user changes in a dirty worktree.

## Current Priorities

The order of work should be:

1. Fix `dawn` discovery quality so hard-news links dominate and off-mission `images.dawn.com` links do not drive a run.
2. Harden the Groq editorial path so schema validation or rate limits do not routinely force deterministic fallback.
3. Tighten deterministic importance ranking so softer feature stories do not consume morning-brief slots.
4. Tighten freshness and publish-date trust.
5. Polish the frontend only after backend output is stable.

## Documentation Hygiene

- Keep tracked docs minimal.
- Put scratch, experiments, abandoned plans, and temporary notes under `docs/extra/` or delete them if they are no longer useful.
- Keep iterative evaluator notes in `codex-thinking/` as short dated `.md` files.
- After each meaningful run, add a note with:
  - hypothesis
  - commands run
  - findings
  - keep/discard decision
  - next step

## Project Structure

- `backend/`: FastAPI API and news pipeline
  - `backend/src/agents/`: embeddings, clustering, analysis, editorial
  - `backend/src/pipeline/`: orchestration
  - `backend/src/scrapers/`: source discovery and extraction
  - `backend/src/db/`: Supabase integration
  - `backend/src/api/`: API routes and app setup
  - `backend/config/`: YAML config for sources and rules
  - `backend/tests/`: pytest suite
- `frontend/`: Next.js app
  - `frontend/src/app/`: routes
  - `frontend/src/components/`: UI
  - `frontend/src/data/`: API client and adapters
  - `frontend/tests/`: frontend tests

## Build, Test, and Run Commands

Backend:

- Install: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Models: `python -m spacy download en_core_web_sm`
- API: `uvicorn main:app --reload`
- Pipeline: `python run_pipeline.py --disable-playwright --log-level INFO --max-articles-per-source 12`
- Quality report: `python scripts/quality_report.py --limit 20`
- Tests: `pytest`

Frontend:

- Install: `npm ci`
- Dev: `npm run dev`
- Tests: `npm test`
- Build: `npm run build`

## Coding and Review Standards

- Python: Black + Ruff, `snake_case`, focused functions, minimal comments
- React/TypeScript: preserve existing patterns unless there is a clear reason to change them
- Keep new logic explainable from data and tests
- Remove dead or bloated code when it does not improve product quality
- KISS, DRY, and YAGNI apply by default

## Ship Criteria

Do not consider the project ready just because tests pass.

Pre-ship confidence means:

- fresh live rows come from the intended reliable sources
- the feed consistently produces `5-9` distinct meaningful cards
- duplicate events are merged well without collapsing different events into one blob
- source attribution is trustworthy
- dates are believable
- the Groq editorial layer works reliably enough that deterministic fallback is exceptional
- frontend presentation is clear and stable

If those conditions are not true in live output, the product is not ready.
