# Repository Guidelines

## Current Phase

- Working directory: `/Users/saqlain/projects/personal/saaf-baat`
- Active phase: `freshness-safe brief ship hardening with backend monitoring`
- Core product target: a trustworthy Pakistan morning brief with `6-12` must-know stories
- Source-of-truth docs, with deployment instructions kept under `docs/`:
  - `README.md` — what the product is, and how to run it
  - `AGENTS.md` — this file: locked product decisions
  - `CLAUDE.md` — the working guide and architecture reference
  - `docs/status.md` — current state, verification numbers, open work
  - `docs/deployment.md` — provider setup, secrets and hosted verification

For current progress, blockers and next actions, read `docs/status.md`.
For architecture and the reasoning behind each threshold, read `CLAUDE.md`.
Treat `docs/status.md` as the changing state; keep this file stable and blueprint-like.

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

- Use a tiered source model, RSS-first (`2026-08-24`):
  - Tier A ships full article text in RSS and needs no page fetch:
    `dawn`, `tribune`, `brecorder`
  - Tier B ships headline + summary, used for corroboration signal only:
    `geo`, `ary`, `nation`, `app`, `thenews`
  - `thenews` runs sitemap-only: its RSS is frozen at November 2025, while its
    Google-News sitemap is current (implemented `2026-08-24`)
  - disable a source for a verified reason, and re-check that reason against RSS
    before trusting it — `ary` was disabled over HTML scraping failures while its
    feed works fine
- Morning brief size is `6-12` cards (changed by the user on `2026-08-28` from
  `10-12`, which was itself changed from `5-9` on `2026-08-24`). The number was
  measured, not chosen: one live day produced 320 clusters, of which 49 were
  national hard news, and reading those by hand gave five strong stories where
  something changed for an ordinary reader plus about three marginal ones. The
  rest were reaffirmed commitments, denials, a flat market, agency PR and
  corporate results. A `10-12` target could only be met by admitting those, and
  that is exactly how a bilateral defence protocol and a foreign-reserves total
  reached the brief. Six on a quiet day is the honest answer, not a failure.
  Only the floor moved: lowering the cap to `10` was tried on the same day and
  reverted, because it cost the `2026-08-24` golden day a must-have topline
  outright. A heavy day really can hold twelve.
- If the editorial pass returns short, retry `2-3` times with the next tier of
  candidates; do not pad the brief with template-generated fallback cards
- Brief selection is national-topline first, then strongest direct public-life stories
- A single-source story may still publish if it has strong civic/public-impact value
- LLM use covers triage, ambiguous split/merge adjudication, and editorial
  selection/presentation (widened by the user on `2026-08-24`; previously
  bounded to editorial only). Triage replaces keyword-file classification.
  Budget target is roughly `30` calls/day, well inside the free tier.
- Story grouping should use a deterministic event-graph approach, not global HDBSCAN/DBSCAN as the primary source of truth
- Deterministic event grouping runs first; the LLM adjudicates only the pairs it
  leaves genuinely ambiguous
- Event links should be strict and multi-signal, not loose semantic similarity alone
- Do not preserve the current global clustering path as an operational fallback once the new event-grouping path is implemented
- Suspicious publish dates should lower confidence, not be trusted blindly
- Cards should emphasize `why_it_matters` and `what_to_watch`
- Story pages should read as quick briefs, not long article pages
- Category surface should stay small and user-legible

## Working Principles

- Read `CLAUDE.md` and `docs/status.md` before making architecture, scraper, ranking, or product-direction changes.
- Prefer reliability, clarity, and fewer moving parts over feature accumulation.
- Verify every meaningful claim with tests, DB inspection, API checks, or live pipeline output.
- If a source is flaky, fix it properly or disable it.
- If a heuristic chain becomes hard to reason about, simplify it.
- Do not optimize for article volume. Optimize for morning-brief quality.
- Do not let the UI overstate what the backend actually knows.
- Do not revert unrelated user changes in a dirty worktree.

## Documentation Hygiene

- Keep `README.md`, `AGENTS.md`, and `CLAUDE.md` in the root. Supporting user documentation and screenshots belong in `docs/`. Runtime prompts and golden-day fixtures remain with their code; do not move them as documentation cleanup.
- After meaningful work, **update `docs/status.md`** — what ships, what the
  numbers are, what is still open. Do not add a new dated note.
- Scratch, experiments and abandoned plans belong outside the repo.
- A stale document is worse than no document: it is the file the next session
  reads and believes.

## Project Structure

- `backend/`: FastAPI API and news pipeline
  - `backend/src/agents/`: embeddings, clustering, analysis, editorial
  - `backend/src/pipeline/`: orchestration
  - `backend/src/scrapers/`: source discovery and extraction
  - `backend/src/db/`: storage — local SQLite by default, Supabase opt-in
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
- Pipeline: `python run_pipeline.py --log-level INFO`
- Daily cron: `0 2 * * * cd /Users/saqlain/projects/personal/saaf-baat/backend && /bin/zsh -lc 'source venv/bin/activate && python run_pipeline.py --log-level INFO'` (07:00 PKT)
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
- the feed produces `6-12` distinct meaningful cards, and is short on a quiet day rather than padded
- the selected set feels like the day’s true Pakistan toplines, not merely coherent clusters
- duplicate events are merged well without collapsing different events into one blob
- source attribution is trustworthy
- dates are believable
- the editorial layer works reliably enough that deterministic fallback is exceptional
- frontend presentation is clear, finite, and quick to scan
- story detail pages feel like fast briefs rather than mini articles

If those conditions are not true in live output, the product is not ready.
