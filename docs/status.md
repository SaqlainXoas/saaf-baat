# Saaf Baat — Status

Status date: **2026-08-28**

The single current state document. Architecture and the reasoning behind each
decision live in `CLAUDE.md`; locked product decisions live in `AGENTS.md`.
Nothing else is kept — the old `claude-thinking-notes/`, `codex-thinking/` and
`program.md` were session records of work now finished, and a stale document is
worse than none.

## What the product is

A finite daily Pakistan morning brief: **6–12 cards** that say what happened and
what changed for an ordinary reader — then it ends. Not an infinite feed, not a
rolling wire.

## What ships today

**Ingest** — RSS plus Google-News sitemaps across 8 publishers, ~26 endpoints,
~300 articles in ~6s. Every endpoint is gated on the age of its newest item;
older than 48h and it is quarantined and reported. No HTML scraping, no
Playwright. Body text is fetched lazily, roughly a dozen requests a run.

**Triage and grouping** — Gemini triage over batched headlines assigns category,
impact labels, story type and Pakistan relevance; verdicts persist so a re-run
does not re-pay. Event grouping is deterministic at a 0.92 pair-similarity
threshold, with LLM adjudication only for genuinely ambiguous split/merge pairs.

**Selection** — facts, not a score. `CandidateEvidence` carries source count,
prominence, freshness and the triage verdict, and is shown to the editor.
Gemini is the only editorial provider. An editorial outage publishes nothing and
leaves the previous brief standing, honestly labelled stale.

**Story analysis** — per-card multi-source analysis plus an optional
accountability question, both validated against the supplied reporting before
anything ships. A failed analysis costs the card its analysis, never the card.

**Delivery** — FastAPI over local SQLite, Next.js frontend. `/api/feed` serves
one run's brief; `/health` reports every LLM stage.

Budget is about 16–24 LLM calls a day, inside the free tier.

## Verification state

- backend: 470 passed, 47 skipped; `ruff` clean
- frontend: 185 tests / 28 suites; typecheck, lint and production build clean
- golden day: exit 0, recall at baseline on all three recorded days
- live: `story_analysis_status=ok` on a clean run; brief renders at 375, 768
  and 1440 with no overflow and no console output

## What is open

**Impact-line style.** The big rules stick — every line names real people and
hedging went from 6/8 to 0/8. Fine style rules do not: about half the lines are
still shaped `<people> face <thing>`, and one or two address "observers" rather
than readers. Three prompt iterations moved this very little. It wants a
deterministic post-check or a stronger editorial model, not a fourth rewrite.

**`what_to_watch` is always null.** Correct behaviour most days — it is written
only when the reporting names a real next event — but it stays null even when a
hearing date is in the copy. The model folds that into the impact line instead.

**Grouping splits.** 33 split-across-groups on the hardest fixture: one story
reaching the editor as two weaker candidates. Merges are healthy; splits are
not. Fixing this makes existing stories stronger, and may recover a card.

**Brief size on an ordinary day is 6–8, not 12.** Measured against the pool, not
guessed: one live day gave 320 clusters, 49 national hard-news, of which five
were strong and about three marginal. The rest were reaffirmed commitments,
denials, a flat market and agency PR. This is the honest number; see `AGENTS.md`.

**A narrow ruling can still take a slot.** A competition-commission penalty over
ghee pricing reached the brief on judgement the editor is entitled to make. The
prompt now argues against it and `_log_thin_admissions` records it every time,
but it is not prevented. Closing it needs a deterministic gate that has so far
been judged worse than the problem.

## Next

1. Impact-line style: deterministic post-check, or a stronger editorial model.
2. Grouping splits.
3. Decide whether the ghee class needs a hard gate.
