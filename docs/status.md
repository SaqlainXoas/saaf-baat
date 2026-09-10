# Saaf Baat — Status

Status date: **2026-09-10**

The single current state document. Architecture and the reasoning behind each
decision live in `CLAUDE.md`; locked product decisions live in `AGENTS.md`.
Deployment setup lives in `docs/deployment.md`. The old `claude-thinking-notes/`, `codex-thinking/` and
`program.md` were session records of work now finished, and a stale document is
worse than none.

## What the product is

A finite daily Pakistan morning brief: **6–12 cards** that say what happened and
what changed for an ordinary reader — then it ends. Not an infinite feed, not a
rolling wire.

## Public review readiness (10 September)

The polished reading experience is ready for an early-preview demonstration;
unattended public-service reliability is **not yet signed off**. Latest checks:
181 frontend tests pass; lint and production build pass. Backend full suite:
524 passed / 47 skipped in the clean deployment environment, including the
database-initialization privacy and hosted publication regressions. Six distinct live cards and all six
detail endpoints worked in 24 bounded API reads; local maximum latency 11 ms.
A real browser outage check verified a plain failure state, and led to removal
of duplicate mobile errors and the misleading zero-story count. Retry performs
a full request. This is smoke testing, not a production load or penetration test.

Frontend security maintenance now uses Next 15.5.25 with patched PostCSS 8.5.28;
production npm audit reports zero known advisories. Backend requests have an
8-second timeout, database failures do not disclose internal exception strings,
stale pipeline health is degraded, and revalidation secrets are header-only.
Response headers disallow framing and add MIME/referrer restrictions.

The selected hosted setup is now **Vercel + Render + Supabase + GitHub Actions**.
The root Render Blueprint installs only the read API; Next.js has a Vercel config
and Node 22 pin. GitHub generates private drafts, validates the run, then calls
an atomic Supabase publication RPC. Schedule is 06:17 PKT, gated by repository
variable `ENABLE_DAILY_PIPELINE=true`; manual runs are available for setup.
Supabase RLS blocks public table access, shared heartbeat reaches Render, and
retention/regrouping guards preserve the last edition and its source context.
The schema was applied twice in embedded PostgreSQL with pgvector; tests verified
anonymous reads/RPC denial, rejection of an incomplete edition, successful
promotion and protection from retention deletes. This is local SQL evidence,
not verification against a connected Supabase project.

Clean API and pipeline dependency lockfiles replace the old unused ML/tooling
bundle in hosted installs; both audit with zero known vulnerabilities. A fresh
pipeline environment passed **524 backend tests / 47 skipped**. The smaller API
starts without NumPy and served the six existing live details successfully.
The user's existing venv is unchanged and should not be used as the release
artifact. README now uses centered existing branding and two inspected light
screenshots; supporting instructions live under `docs/`, with AGENTS and CLAUDE
retained in the root. Runtime prompts and golden-day fixtures remain in place.

**Still needs the user's accounts:** Supabase project/schema, Render and Vercel
GitHub connections, provider secrets, and first hosted publication/reader test.
Nothing was deployed, pushed or posted. Render Free cold starts can exceed the
frontend timeout; the guide calls this out. Verify consecutive daily editions,
provider quotas, backup/restore and failure notifications before calling this
an unattended reliable service. Today's apology/process story remains a weaker
editorial selection. Marketing Markdown and the 30-second video remain outside
the repository in the session launch-kit directory.

## What ships today

**Ingest** — RSS plus Google-News sitemaps across 8 publishers, ~26 endpoints,
~300 articles in ~6s. Every endpoint is gated on the age of its newest item;
older than 48h and it is quarantined and reported. An endpoint whose newest
item is dated more than an hour in the future — a broken publisher clock, not
fresh news — is quarantined the same way; Nation's feeds report their newest
item around -11h on every run and were being read as simply current until
this guard was added. No HTML scraping, no Playwright. Body text is fetched
lazily, roughly a dozen requests a run.

**Triage and grouping** — Gemini triage over batched headlines assigns category,
impact labels, story type and Pakistan relevance; verdicts persist so a re-run
does not re-pay. Event grouping is deterministic at a 0.92 pair-similarity
threshold, with LLM adjudication only for genuinely ambiguous split/merge pairs.
Causal context is removed before event matching, so a fire, the inquiry into it
and later hospital audits do not become one falsely corroborated event. A
presentation-layer story-family check keeps related follow-ups from becoming
duplicate cards while preserving their separate provenance underneath.

**Selection** — facts, not a score. `CandidateEvidence` carries source count,
prominence, freshness and the triage verdict, and is shown to the editor.
Unsupported numbers, consequences, active-policy claims and mood/hedge impact
lines are rejected after generation. A pass below six retries against deeper
candidates up to three times, but separate passes are not combined and no
template cards pad the result. A cluster that fails grounding is excluded from
every later retry attempt, so a retry spends its budget on candidates the
editor hasn't judged yet rather than re-proposing and re-rejecting the same
story. `what_to_watch` requires the source sentence name a specific subject
connected to the story itself, not just any nearby date and event keyword — a
live card once surfaced "The meeting is scheduled for September 16." lifted
from unrelated U.S. Federal Reserve market commentary cited in passing inside
a Pakistani PSX article. An editorial outage publishes nothing and leaves the
previous brief standing, honestly labelled stale.

**Story analysis** — per-card multi-source analysis plus an optional
accountability question, both validated against the supplied reporting before
anything ships. Invalid output is retried once with the same evidence packet. A
second failure costs the card its analysis, never the card, and the detail page
discloses the excerpt fallback.

**Delivery** — FastAPI over local SQLite, Next.js frontend. `/api/feed` serves
one run's brief; `/health` reports every LLM stage. “Today's brief” requires an
edition generated on the current Pakistan date at or after 07:00 PKT; older or
pre-morning output is explicitly the latest available brief. Editions below six
cards are visibly marked partial.

Budget remains inside the intended daily free-tier envelope on a normal run;
editorial and analysis retries increase calls only when output fails validation.

## Product finish and verification

The reader experience has completed a presentation polish pass. The masthead
identifies a Pakistan-wide brief; cards have clearer typography and an explicit
“Why it matters” label; full publisher names replace internal slugs. Desktop has
a working story index and reading progress. A single sun/moon icon switches themes on every screen, follows the system
appearance initially and remembers an explicit choice. Detail pages put impact before analysis in a narrower reading column,
and source headlines wrap so readers can identify the reports.

Stale editions take precedence over partial-edition copy. Short editions no
longer claim review is actively happening. Focus has been removed at the user’s request: every reader gets the full
curated edition, including visitors with old filter query strings. The filter
parser, dialog, unused Button/Sheet primitives and their feature-specific
tests are removed. Repeated header, sidebar and end-of-brief copy is shorter. Old editions no longer say the reader is caught up. A short expandable
explanation discloses AI assistance and directs readers to original reporting.
Exact repeated headlines and explicit image captions are omitted from card
excerpts without removing the story or its impact line.

A real desktop test exposed a progress bug: percentage IntersectionObserver
margins resolve against viewport width and erased the reading band on a wide
screen. Progress now uses height-based pixel margins and retains the visible
set across observer updates. Browser jumping to story five confirms 5 / 6.

- Frontend: **180 tests / 25 suites passed**, ESLint and production build passed.
- Backend: **517 passed, 47 skipped**, Ruff clean; two failures repaired:
  an unpinned September watch-date fixture and an unused lower-case `may`
  hedge check. Month-name regression cases preserve valid May dates.
- Golden-day replay: exit 0 across all three fixtures, baseline gates passed.
  Offline replay still does not validate live editorial quality.
- Fresh live run on **2026-09-10**: **314 articles, all 8 sources healthy,
  269 clusters, 6 published cards**. Embedding rate limits recovered through
  the existing retry path. All LLM stages ended `ok`.
- **6/6 validated story analyses, zero fallbacks or failures** in this run.
- API: fresh six-card edition, all six detail routes HTTP 200, `/health` `ok`.
- Browser: real API data in development and production builds; desktop, 820px
  tablet, 375px phone and 320px narrow-phone checks; light/dark themes,
  filters/apply/clear, zero matches, browser back, detail/source links,
  edition index, reading progress and disclosure. No console errors observed
  on the final production page. The simplification pass additionally verified
  the single icon toggle, saved appearance after reload, 320px phone rendering,
  old filter URLs returning all six cards, and story navigation. Test count fell
  because the retired filtering/dialog/button tests were removed.

The fresh edition covers goods transport fares, the stock-market decline, the
PIMS fire investigation, the Mir Raza judicial commission, polio-worker pay,
and Punjab electric buses. A September 14 hearing reaches `what_to_watch`,
providing a live acceptance-path example. The judicial-commission apology remains
a weaker ordinary-reader slot than the transport and pay stories; one successful
six-card day is not proof of dependable selection across repeated days.

Local presentation preview: `http://127.0.0.1:3003` (production build; no deployment).

## What is open

**Repeated-day editorial reliability remains unproven.** September 10 reached
six grounded cards; the earlier live runs on 2026-09-02
still returned only 4-5 grounded stories against the six-card floor. An
experiment that unioned separate passes produced nine cards, but also promoted
a story another pass called routine and duplicated the PIMS storyline; it was
rejected and reverted. `COLLAPSE_RETRY_FLOOR` now equals `TARGET_STORY_FLOOR`
(6, was 4) so every short pass retries against deeper candidates, and a
cluster that fails grounding is never re-offered on a later attempt — but
neither change has been observed to close the gap on its own; the pool a live
run draws from may simply not contain six stories that pass the grounding
gate on a given day. The product still needs a more stable editor or a
deterministic, evidence-based selection policy that can reach six without
admitting process stories merely to hit the count.

**Some selected cards still fail the ordinary-reader test.** The FBR audit and
Fesco prequalification cards are real and corroborated, but their current
impact lines describe administrative process rather than a concrete change a
reader can feel today. The final brief contains no direct wallet or daily-life
change. Grounding prevents invention; it does not yet guarantee importance.

**Story-analysis reliability needs repeated-day evidence.** September 10
produced six validated analyses with no fallback. On September 2, four of five cards had
validated multi-source analysis. The Fesco analysis invented unsupported
numbers/dates twice and fell back. The disclosure is correct, but a dependable
brief should make fallback exceptional across repeated live days, not merely
honest when it happens.

**Stable publisher-identity dedup is still open.** A changed slug can leave two
URLs for the same publisher article ID looking like two reports. URL
canonicalisation needs source-specific stable IDs, particularly for Business
Recorder.

**Impact-line style.** The big rules stick — every line names real people and
hedging went from 6/8 to 0/8. Fine style rules do not: about half the lines are
still shaped `<people> face <thing>`, and one or two address "observers" rather
than readers. Three prompt iterations moved this very little. It wants a
deterministic post-check or a stronger editorial model, not a fourth rewrite.

**`what_to_watch` needs more live coverage.** A deterministic fallback extracts
concrete dated strikes, hearings, votes, elections, deadlines, rallies and
meetings; rejects dates already past relative to the story; requires the
source sentence name a subject connected to the story itself, not an
incidental mention elsewhere in the article; and splits sentences with the
same abbreviation-aware splitter used for card snippets, after a naive
`.`-based split once cut a sentence apart at "U.S." and both halves fed a
false positive. All four guards are confirmed against a live failure. The September 10 edition now includes a September 14 hearing; the
acceptance path has been observed, though more live coverage is still useful.

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

1. Stabilise selection so one coherent pass returns at least six strong cards
   when the day supports them, and strengthen the hard gate against institutional
   process stories with no direct reader consequence.
2. Measure story-analysis fallback rate across several live days and fix the
   recurring unsupported-number/date failure shape.
3. Source-specific stable-ID deduplication (future-clock quarantine shipped
   2026-09-02).
4. Continue monitoring impact-line style, remaining grouping splits and the
   narrow regulatory-story gate. The filtered partial-brief copy is fixed.
