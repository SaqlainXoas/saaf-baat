# Saaf Baat Final Ready Plan (Pre-Live)

Status date: **February 15, 2026**

## Objective

Close all remaining backend, frontend, quality, and repository hygiene gaps so Saaf Baat is safe to run in production and clean to publish as open source.

## Current Readiness Snapshot

- Backend pipeline, DB integration, API, and frontend live-data integration are working.
- Embeddings are fixed to `models/gemini-embedding-001` with `768` dimensions (DB-compatible).
- Desktop and mobile UX refinements are in place, and test/build gates currently pass.
- Remaining work is mostly production hardening, data quality tuning, observability, and OSS cleanup.

## Critical Blockers (Must Fix Before Public Release)

- [x] **Secrets hygiene**
  - Remove all real-looking keys/URLs from `backend/.env.example`; replace with placeholders.
  - Rotate any keys that were ever committed historically (manual operator action).
  - Add explicit secret-handling notes to README.
  - **Acceptance:** no real secrets in repo; example env is safe for public use.

- [x] **SDK deprecation migration**
  - Migrate backend embeddings client from deprecated `google.generativeai` to `google.genai`.
  - Keep output dimensionality fixed at `768`.
  - **Acceptance:** pipeline works end-to-end with new SDK, tests updated.

- [x] **Production CORS lock-down**
  - Configure and verify `BACKEND_CORS_ALLOW_ORIGINS` with exact production domains.
  - Add staging/local entries explicitly (no wildcard in production runtime).
  - **Acceptance:** browser requests succeed from allowed origins and fail from others.

## Backend Finalization

- [x] **Pipeline reliability + observability**
  - Add run-level logging summary (inserted, embedded, clustered, feed inserted/skipped).
  - Add clear failure logs for scrape/embed/analyze stages.
  - Add health/staleness signal (last successful pipeline run time).
  - **Acceptance:** one command/check shows if data is fresh and where failures occurred.

- [x] **Rate-limit and cost controls**
  - Re-check `max_articles_per_source`, `embedding_backfill_limit`, and schedule frequency against Gemini quota.
  - Add safe defaults for low-cost mode.
  - **Acceptance:** no quota spikes in normal hourly operation.

- [ ] **Data quality refinement**
  - Review latest live rows for noisy entities and category misclassification.
  - Tune classifier/consensus thresholds minimally (avoid overfitting).
  - **Acceptance:** feed cards show concise, meaningful facts/claims across multiple stories.

- [x] **API contract hardening**
  - Add/confirm response constraints for edge cases (empty feed, missing publish dates, missing source attribution).
  - Add API contract tests for those cases.
  - **Acceptance:** frontend never breaks on null/empty/partial payloads.

## Frontend Finalization

- [x] **Live-data UX hardening**
  - Keep strict live mode enabled for production (`NEXT_PUBLIC_STRICT_LIVE_DATA=1`).
  - Validate stale-data banner behavior with real timestamps.
  - **Acceptance:** clear user messaging for live, stale, and unavailable states.

- [x] **Accessibility polish**
  - Audit keyboard navigation for cards, filters, and expandable lists.
  - Verify focus visibility and semantic landmarks on home/detail pages.
  - **Acceptance:** basic keyboard-only navigation passes manually.

- [ ] **UI refinement pass**
  - Review typography/spacing consistency on desktop and mobile.
  - Ensure source chips/badges are consistent for all configured sources.
  - **Acceptance:** no obvious visual regressions at common breakpoints.

- [x] **Frontend performance sanity**
  - Verify no unnecessary rerenders for large feed lists.
  - Keep bundle growth controlled after refinements.
  - **Acceptance:** build succeeds; no major runtime lag in local manual test.

## Testing and Verification

- [x] **Backend verification pack**
  - Run focused pytest suites for API, analysis, pipeline.
  - Run one constrained live pipeline smoke against Supabase.
  - Progress (February 15, 2026): focused API + analysis + embeddings + pipeline tests passed locally; constrained live smoke run completed against Supabase.
  - **Acceptance:** tests green + smoke run completes with fresh `analyzed_feed` rows.

- [x] **Frontend verification pack**
  - Run Jest + Next build.
  - Manual browser checks for home, detail, strict-live failure mode, stale mode.
  - Progress (February 15, 2026): `npm test` and `npm run build` passed locally.
  - **Acceptance:** no runtime errors, all primary journeys functional.

- [x] **End-to-end journey checks**
  - Verify flow: `pipeline -> Supabase -> API -> frontend`.
  - Confirm newest stories visible in UI after pipeline run and cache window.
  - Progress (February 15, 2026): live smoke inserted fresh rows; `/health` reports connected DB + fresh run timestamp.
  - **Acceptance:** real story inserted by pipeline appears in frontend within expected interval.

## Repository Cleanup for Open Source

- [x] **Remove/organize non-essential files**
  - Move/archive old planning or scratch files if not needed.
  - Ensure only relevant docs remain top-level in `docs/`.
  - **Acceptance:** repo root and docs structure are clean and intentional.

- [x] **Dead code and unused assets cleanup**
  - Remove unused components/helpers/styles/assets discovered by search and test coverage.
  - **Acceptance:** no obvious dead files; imports and exports are purposeful.

- [x] **Open-source readiness docs**
  - Add issue/PR templates.
  - **Acceptance:** community contributors have clear project standards and process.

- [x] **README professionalization (final pass)**
  - Clarify architecture, quick start, env setup, runbook, and troubleshooting.
  - Document production/staging env variable matrix.
  - **Acceptance:** new contributor can run project without guessing steps.

## Deployment-Readiness Checklist (Pre-Go-Live)

- [ ] Production env vars configured and validated (frontend + backend + GitHub Actions secrets).
- [ ] Hourly pipeline schedule confirmed and manual dispatch verified.
- [ ] Health endpoint checked for `database=connected` and fresh feed timestamp.
- [ ] Strict live mode confirmed in production frontend.
- [ ] Rollback plan documented (disable schedule + revert frontend API URL if needed).

Notes:
- Local verification is complete; remaining items are production environment confirmations.

## Suggested Execution Order (Next Session)

1. Secrets hygiene + `.env.example` sanitation + key rotation plan.
2. Migrate Gemini SDK (`google.genai`) and re-run pipeline smoke.
3. Final backend data-quality tuning + API contract tests.
4. Frontend a11y and UI polish pass + strict-live/stale behavior validation.
5. OSS cleanup (dead files/docs/licenses/templates) + final README rewrite.
6. Full verification run and release checklist sign-off.

## Done Definition

This plan is complete when:

- All checkboxes above are marked done.
- Backend and frontend quality gates pass from a clean checkout.
- One full live pipeline run populates good-quality feed data.
- Project documentation is clear, safe (no secrets), and ready for public contributors.
