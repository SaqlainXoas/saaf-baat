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
- Replace global density clustering with deterministic event-level grouping as the main story-formation step.
- Use LLM only for ambiguous split or merge adjudication after deterministic grouping.
- Make event links strict and multi-signal: strong embedding similarity plus headline/entity overlap plus time closeness.
- Do not keep the legacy whole-batch clustering path as a live fallback after the new grouping path lands.
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

The earlier main architectural failure has been addressed:

- whole-batch density clustering is no longer the production story-formation path
- deterministic event grouping now forms the recent-window stories

The current issues are narrower:

- category and impact rules still need live tuning for civic and public-service stories
- publish selection now reaches the `5-9` range, but still needs consistency toward the best `5-9`
- `dawn` discovery quality is inconsistent and can surface `images.dawn.com` lifestyle links instead of hard-news pages
- Groq editorial fallback is still too easy to trigger under schema failure or `429` rate limits
- core-source scraping is still slower than it should be for a bounded morning run

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

## Story Grouping Principles

- Group by event identity, not by broad semantic similarity alone.
- Prefer strict pairwise event links over whole-batch unsupervised clustering.
- Use multiple signals together: embedding similarity, headline overlap, entity overlap, and time closeness.
- Prevent chaining where article A links to B and B links to C even though A and C are different events.
- Split or reject oversized mixed groups before editorial selection.
- Keep the grouping system singular and legible. Do not leave two competing clustering systems active in production.

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

## Current Next Targets

The next improvements should stay within the current architecture:

1. Verify the latest classifier and publish-gate tuning against one more clean live run.
2. Fix `dawn` hard-news discovery quality before broadening sources again.
3. Harden Groq editorial behavior so deterministic fallback is exceptional.
4. Tighten category consistency and deterministic importance ranking so the surviving `5-9` cards are the right `5-9`, not just coherent clusters.
5. Reduce scraper runtime without broadening source risk or adding opaque complexity.

## Current Main Blockers

- `dawn` discovery quality is still inconsistent and sometimes surfaces `images.dawn.com` lifestyle links instead of hard-news URLs.
- Groq editorial reliability is still below target because strict schema mode can fail and the fallback path can hit `429` rate limits.
- The system can now produce `5-9` cards, but deterministic ranking still needs work so softer feature stories do not take slots from stronger civic/public-interest stories.

## Hard Rules

- Do not trade correctness for novelty.
- Do not tolerate ugly complexity for marginal gains.
- Do not assume live quality from green tests alone.
- Do not duplicate the same story under slightly different headlines.
- Do not leave old documents pretending to be current truth.
- Do not stop at code changes; verify the outcome.
