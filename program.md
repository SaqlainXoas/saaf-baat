# Saaf Baat Program

## Mission

Build a small, modern Pakistan morning brief that answers one question quickly:

What does an ordinary person in Pakistan need to know this morning before moving on with the day?

The product should feel selective, calm, finite, and trustworthy.

## Product Shape

The target experience is:

- open once in the morning
- skim `5-9` must-know stories
- understand why each story matters
- see what to watch next
- inspect the original reporting if needed

Saaf Baat is not meant to be a generic all-day timeline or a content-maximizing news reader.

## Current Agreed Decisions

These are active product decisions:

- Prefer a flexible `5-9` story brief over a forced fixed count.
- Prefer importance over recency when choosing what reaches the brief.
- Prefer one card per real event over multiple headline variants.
- Keep deterministic evidence extraction where it helps trust and explainability.
- Use the LLM layer only for bounded editorial selection and presentation support.
- Allow a single-source story only when civic or public-impact value is clearly high.
- Treat suspicious publish dates as low-confidence.
- Keep the source list small and reliable rather than broad and flaky.

## Core Product Standard

- Prefer important stories over merely recent stories.
- Prefer transparent evidence over opaque cleverness.
- Prefer fewer moving parts over layered heuristics.
- Prefer disabling bad inputs over compensating for them downstream.
- Prefer discarding weak stories over filling the brief with noise.

## Non-Goals

- Do not optimize for infinite scroll.
- Do not chase maximum article volume.
- Do not let entertainment, sports, gossip, or low-value filler dominate the brief.
- Do not turn the product into an LLM-first summarizer when deterministic structure already helps.
- Do not keep complexity that cannot be justified by live feed quality.

## What Counts As Success

The live feed should consistently produce:

- `5-9` meaningful Pakistan stories
- clean deduplication of the same event across sources
- credible source attribution
- useful public-impact framing
- coherent cards with `why_it_matters` and `what_to_watch`
- stable operation from scrape to DB to API to frontend

## Current Known Reality

The system already has:

- source scraping
- Supabase storage
- Gemini embeddings
- clustering
- deterministic analysis
- Groq editorial review
- API and frontend delivery

The remaining challenge is not architecture creation. The remaining challenge is live reliability:

- enough strong candidate stories
- trustworthy freshness/date handling
- stable source coverage from reliable publishers
- consistent final morning-brief quality

## Source Principles

- Favor stable Pakistani publishers over source-count vanity.
- Keep source rules explicit in `backend/config/sources.yaml`.
- If a source is flaky, either fix it properly or disable it.
- Do not let half-working sources create downstream noise.
- Judge scraper changes by feed quality, not scrape totals.

## Analysis Principles

- Keep analysis explainable from raw articles and metadata.
- Tune thresholds only after observing a concrete failure mode.
- Rank by public consequence, source credibility, source breadth, and cluster coherence.
- Merge story variants aggressively when the underlying event is the same.
- If a step keeps producing confusing output, simplify it instead of adding another heuristic layer.

## Editorial LLM Principles

- Groq is allowed as a bounded editorial gate.
- It may decide which candidate clusters deserve publication and shape structured fields for the card.
- It should not replace evidence, source attribution, or basic determinism.
- It should not be called on every refresh; it is for scheduled morning-brief preparation.
- If the LLM layer becomes hard to reason about, reduce its scope.

## Evaluation Rubric

Judge each change against these questions:

1. Does it improve trust, correctness, or importance?
2. Does it reduce duplicate, weak, or off-mission cards?
3. Does it simplify the system or at least justify any added complexity?
4. Can the improvement be verified with tests, DB inspection, quality reports, or live runs?
5. Would users miss it more than engineers would miss the implementation?

If the answer is mostly no, discard the idea.

## Autonomous Improvement Loop

1. Read the latest `codex-thinking/*.md` notes.
2. State the current hypothesis in a new note.
3. Run the smallest useful verification:
   - targeted tests
   - API checks
   - DB inspection
   - `backend/scripts/quality_report.py`
   - constrained live pipeline run
4. Identify the highest-leverage problem.
5. Implement the simplest fix that materially improves the product.
6. Re-run verification.
7. Record `keep`, `discard`, or `needs follow-up`.
8. Move to the next highest-value issue.

## Verification Priority

When in doubt, verify in this order:

1. Targeted unit or integration tests
2. API contract and health checks
3. Supabase inspection
4. `backend/scripts/quality_report.py`
5. Constrained live pipeline run
6. Frontend manual sanity after payload or ranking changes

## Hard Rules

- Do not trade correctness for novelty.
- Do not tolerate ugly complexity for marginal gains.
- Do not assume live quality from green tests alone.
- Do not duplicate the same story under slightly different headlines.
- Do not leave old documents pretending to be current truth.
- Do not stop at code changes; verify the outcome.
