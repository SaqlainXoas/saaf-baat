# Saaf Baat Ship Plan

Status date: **April 8, 2026**

## Phase Status

- Phase 0: complete
- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Phase 4: complete
- Phase 5: complete
- Phase 6: in progress

Current remaining focus inside Phase 6:

- final homepage composition judgment on the fresh live brief
- one more visual-density decision on lead vs supporting story weight
- repeated-run backend monitoring for topline quality
- final signoff only after UI judgment and live output still agree

## Purpose

This document is the execution plan for finishing Saaf Baat to a public-ship standard.

It is intentionally biased toward:

- frontend quality
- visual correctness
- product honesty
- live-data correctness
- durable implementation over hacks

This is not a brainstorming note. It is the phased plan we should execute later.

## Product We Are Shipping

Saaf Baat is a selective Pakistan morning brief.

The shipped product must feel:

- finite, not feed-like
- editorial, not dashboard-like
- calm, not noisy
- trustworthy, not over-claimed
- fast to scan on mobile and desktop

Each story must answer:

- what happened
- why it matters
- what to watch
- which original publishers support it

## Locked Product Constraints Carried Forward

These are already-decided constraints from the current repo state and must remain true while executing this plan:

- morning brief size stays flexible at `5-9`
- importance beats recency
- brief selection is now explicitly **national-topline first**, then strongest direct public-life stories
- one card should represent one real event
- strong single-source civic/public-interest stories may still publish
- LLM use remains bounded to editorial selection and presentation support
- suspicious publish dates are low-confidence, not trusted by default
- frontend must consume the backend API contract, not direct database reads
- source policy remains reliability-first:
  - core sources right now are `dawn`, `tribune`, and `geo`
  - `ary` remains disabled unless its reliability is genuinely fixed
- this plan does not reopen backend clustering architecture
- category presentation should stay small and legible to users

## Current Reviewed State

After reviewing:

- `README.md`
- `AGENTS.md`
- `program.md`
- `docs/final-ready-plan.md`
- recent `codex-thinking/*.md`
- current backend/frontend worktree
- current Stitch design references under `UI-concepts/stitch/`

the current repo state is:

### What is already strong

- backend architecture is no longer the main risk
- backend has already reached a clean constrained live run with `5` coherent stories
- frontend is now wired to backend API routes instead of direct Supabase reads
- homepage is already moving in the right direction:
  - one lead story
  - two supporting stories
  - lower ranked grid
- story detail already has:
  - stronger hero treatment
  - editorial note blocks
  - cleaner source presentation
- trust/consensus UI has already moved away from raw noisy entity chips
- targeted backend API tests pass
- targeted frontend tests pass
- frontend production build passes

### What is still not ship-finished

- frontend still needs a final correctness pass against live data in a real browser
- mobile design is functional, but still not fully resolved against the strongest Stitch references
- some parts of the current UI still use border-heavy separation where the Stitch system wants tonal layering
- some status/freshness semantics are not fully honest yet
- some empty and degraded states are implemented inconsistently
- detail-page source cleanup currently hides upstream clustering noise rather than solving it
- repeated-run backend confidence still needs monitoring, but that is now a support workstream, not the main product workstream
- the current ship plan must still prove:
  - repeated-run `5-9` consistency
  - soft-story suppression when stronger civic stories exist
  - suspicious-date handling on future live rows
  - homepage/detail correctness against real API payloads

## Design North Star

The visual system must follow the local Stitch references and the editorial design notes, especially:

- `UI-concepts/stitch/saaf_baat_desktop_home_refined/code.html`
- `UI-concepts/stitch/saaf_baat_mobile_home_refined/code.html`
- `UI-concepts/stitch/article_detail_view/code.html`
- `UI-concepts/stitch/serene_editorial/DESIGN.md`

### Locked visual principles

- warm paper surfaces, not sterile white
- serif editorial headlines, clean sans body text
- layered surfaces over hard divider lines
- strong hierarchy through spacing and scale, not clutter
- one lead narrative on home, not equal-weight cards
- trust presentation must stay honest and restrained
- desktop and mobile should feel like the same product, not two separate styles

## Non-Negotiable Build Rules

- No hacky one-off CSS patches to “make it look right” on a single screenshot.
- No fake editorial language that overstates certainty.
- No frontend logic that invents trust signals not present in the backend payload.
- No direct frontend database reads.
- No visual regression fixes that break mobile to improve desktop, or vice versa.
- No shipping decision based on green tests alone.
- Any frontend polish change must be verified on real live stories, not just mocks.

## Main Ship Risks

### Risk 1: visual direction is partly right but not fully systematized

The current UI has the right ingredients, but some pieces still feel assembled rather than designed as one coherent system.

### Risk 2: mobile may lag behind desktop quality

Desktop has received the most obvious editorial-structure work. Mobile still needs intentional refinement against the Stitch mobile stack and flow patterns.

### Risk 3: product honesty can drift

Consensus/trust/source UI must remain useful without implying certainty the data does not support.

This is especially important for the detail-page summary block:

- the current backend does **not** return explicit editorial `agreed` and `debated` bullet lists
- the backend currently returns:
  - `confirmed_facts`
  - `debated_claims`
  - `why_it_matters`
  - `what_to_watch`
  - `sources`
  - supporting `metadata`
- the frontend summary block is therefore a derived presentation layer, not a direct backend-authored consensus object

Because of that, the shipped UI must match current backend truth:

- do not present multi-source stories as stronger agreement than the returned data actually supports
- do not present single-source stories as true consensus
- if the backend only supports “current reporting” and “what to watch,” the UI must use that framing
- exact Stitch-style `What’s Agreed` and `What’s Debated` semantics should only remain where the data is genuinely defensible
- if we want full Stitch semantics later, the backend must add explicit summary fields such as curated `agreed_points` and `debated_points`

### Risk 4: live-state behavior can undercut the premium feel

If stale-state, no-data, API-failure, source-empty, or ranking mismatch states feel rough, the product will feel unfinished even if the happy path looks good.

### Risk 5: backend monitoring is still needed to protect frontend work

If repeated live runs drift back toward soft stories, suspicious timestamps, or cluster contamination, the frontend will be forced to mask upstream problems.

### Risk 6: ship criteria can become implied instead of explicit

If we do not carry the release checklist forward into this plan, we can finish a visually improved frontend while still missing public-ship requirements.

## Execution Strategy

We should execute in phases.

The order matters.

We should not do another broad redesign first. We should first lock correctness, then systemize the visual language, then do ship-grade polish and live verification.

## Phase 0: Lock The Baseline

### Goal

Freeze what is already working, define the reference implementation, and remove ambiguity before more UI work.

### Tasks

- Treat current backend API contracts as the only live data source.
- Treat the current homepage structure as the baseline information architecture:
  - lead story
  - two supporting stories
  - ranked lower grid
- Treat the current story detail layout as the baseline information architecture:
  - hero
  - why it matters
  - what to watch
  - consensus summary
  - original sources
- Define one approved visual reference set from Stitch:
  - desktop home refined
  - mobile home refined
  - article detail view
- Record which existing frontend pieces are keep, revise, or replace:
  - `BrandHeader`
  - `DesktopBrief`
  - `StoryCard`
  - `Deck`
  - `MorningGreeting`
  - `TrustPreview`
  - `ConsensusEngine`
  - `OriginalSourcesList`
  - `globals.css`

### Deliverable

A clear “do not regress” baseline before design execution starts.

### Locked baseline for execution

- Live data contract:
  - homepage and detail pages must keep using the backend API contract in `frontend/src/data/api.ts`
  - no direct Supabase or database reads are allowed back into the frontend
- Homepage information architecture to preserve:
  - `DesktopBrief` keeps the ranked structure of one lead story, two supporting stories, then lower ranked grid
  - `page.tsx` keeps desktop and mobile rendering paths but both must represent the same editorial ranking
- Detail information architecture to preserve:
  - `stories/[cluster_id]/page.tsx` keeps hero, `why_it_matters`, `what_to_watch`, consensus, and original sources as the canonical reading flow
- Approved visual reference set:
  - desktop target: `UI-concepts/stitch/saaf_baat_desktop_home_refined/code.html`
  - mobile target: `UI-concepts/stitch/saaf_baat_mobile_home_refined/code.html`
  - detail target: `UI-concepts/stitch/article_detail_view/code.html`
  - system notes: `UI-concepts/stitch/serene_editorial/DESIGN.md`

### Keep / revise / replace decisions

- `BrandHeader`: revise
  - Keep the editorial positioning and finite-brief framing.
  - Refine hierarchy, spacing, and status treatment later in homepage phases.
- `DesktopBrief`: keep and refine
  - The ranked desktop structure is the correct baseline.
  - Improve pacing and composition later without changing the underlying story order.
- `StoryCard`: keep and refine
  - Card variants stay, but visual hierarchy and source treatment will be tightened later.
- `Deck`: revise decisively in Phase 3
  - Keep only if it feels intentional and preserves ranked comprehension on mobile.
  - Replace with a simpler ranked mobile flow if the deck remains gimmicky under live data.
- `MorningGreeting`: revise
  - Keep the purpose, but align it more closely with the approved mobile editorial reference.
- `TrustPreview`: keep and refine
  - The current move away from noisy chips is correct.
  - Final wording and visual restraint still need verification against live stories.
- `ConsensusEngine`: keep and refine
  - Preserve bounded editorial synthesis, not pseudo-analysis theater.
- `OriginalSourcesList`: keep and refine
  - The component stays, but sparse and empty states must remain reachable and credible.
- `globals.css`: revise heavily
  - It remains the correct place for tokens and system rules, but it needs a more coherent editorial design system in Phase 2.

### Exit criteria

- no uncertainty about which references define the ship target
- no uncertainty about which live contract powers the UI
- no new design work begins before this baseline is locked mentally and in docs

## Phase 1: Correctness Before Cosmetics

### Goal

Fix product-honesty and live-state correctness issues that would otherwise pollute the design pass.

### Tasks

- Fix freshness/status semantics so “last updated” reflects actual newest live update, not the first ranked story.
- Fix empty original-source behavior so the user sees a graceful empty state when no source links exist.
- Audit all degraded states:
  - missing API base
  - strict-live failure
  - no published brief yet
  - no stories matching filters
  - story detail 404
- Ensure copy in these states stays premium and calm, not technical unless necessary.
- Audit any frontend-derived editorial copy to ensure it never overclaims what the backend payload actually supports.
- Review source-list filtering behavior and define when the frontend should suppress obvious contamination versus surface the backend truth.
- Define how single-source but legitimate civic/public-interest stories should look so they do not feel visually “invalid” just because source count is lower.

### Deliverable

A correctness-stable frontend that can be trusted before design polish.

### Exit criteria

- freshness messaging is honest
- all empty/error/degraded states are intentionally designed
- no hidden empty states remain
- trust/consensus wording remains clearly bounded and defensible

## Phase 2: Establish The Real Design System

### Goal

Turn the current partial styling into a deliberate editorial design system aligned to Stitch.

### Tasks

- Refactor global design tokens in `frontend/src/app/globals.css` so they match the editorial sanctuary system:
  - paper/surface tiers
  - text hierarchy
  - tonal blocks
  - depth/shadow rules
  - radius rules
  - spacing cadence
- Replace border-heavy separation with tonal layering where appropriate.
- Standardize serif display usage across:
  - hero headlines
  - lead cards
  - story detail headlines
- Standardize metadata, kicker, and label styling.
- Define rules for:
  - lead card
  - compact card
  - detail editorial note
  - consensus summary blocks
  - source list rows
  - status chips
- Ensure light and dark themes both preserve the editorial feel.
- Avoid introducing visual patterns not supported by the product:
  - fake authors
  - fake read times unless grounded
  - fake sections like Saved/Explore if not actually part of current ship scope
- Keep category presentation constrained and user-legible instead of expanding into a noisy taxonomy.

### Deliverable

A coherent frontend visual system, not just component-local styling.

### Exit criteria

- desktop home, mobile home, and detail page clearly feel like one system
- hierarchy is driven by type, spacing, and surface tiers
- visual debt in `globals.css` is reduced rather than increased
- no obvious mismatch remains between current app and chosen Stitch references

## Phase 3: Homepage Ship Pass

### Goal

Make the homepage feel premium, ranked, and calm on both desktop and mobile.

### Desktop tasks

- Refine the header so it feels editorial, not app-shell-like.
- Tighten the lead-story composition:
  - visual hero
  - headline scale
  - snippet restraint
  - source support
  - why-it-matters and watch framing
- Improve support-card rhythm so the sidebar feels subordinate but still useful.
- Tune lower-grid card density for scan speed.
- Remove any remaining elements that feel sticky, stacked, or generic.
- Make sure ranking is visually obvious without explicit “rank number” noise.

### Mobile tasks

- Rework the mobile greeting and deck flow to align more closely with the Stitch mobile-home references.
- Decide whether the stacked-deck interaction is ship-worthy or whether a simpler ranked mobile flow is more trustworthy and usable.
- If the deck remains:
  - make it feel intentional, not gimmicky
  - preserve fast access to story detail
  - ensure story order remains legible
- Improve vertical rhythm, card height behavior, and story progression cues.
- Ensure first-screen mobile experience communicates:
  - what the product is
  - how many stories there are
  - what action the user should take next
- Confirm mobile still respects the same editorial ranking semantics as desktop.

### Deliverable

A homepage that feels public-ready on desktop and mobile.

### Exit criteria

- lead story always visually reads as the main story
- mobile experience feels designed, not merely responsive
- all homepage states remain clear with live data, mock fallback, and empty data

## Phase 4: Story Detail Ship Pass

### Goal

Make the detail page feel like a premium editorial brief, not a data dump.

### Tasks

- Tighten the hero block:
  - headline width
  - snippet scale
  - metadata treatment
  - hero visual balance
- Keep `why_it_matters` and `what_to_watch` prominent but not repetitive.
- Refine the consensus summary so it reads as editorial synthesis, not pseudo-analysis theater.
- Ensure the summary block labels and bullets match the backend contract that exists today:
  - current backend truth is signal-level data, not explicit editorial agreement/debate lists
  - use `Consensus Summary` only where multi-source support and returned signals justify it
  - use `Reporting Summary` or similarly bounded wording where the backend only supports current-reporting framing
  - do not let Stitch wording overrule data semantics
- Improve source-list design for scanability and trust:
  - clearer source identity
  - calmer spacing
  - more credible timestamp presentation
- Decide whether article timestamps should be relative, absolute, or mixed based on trust and clarity.
- Ensure source-empty and source-sparse cases still feel complete.
- Audit the detail page for long-headline, low-source-count, and single-source edge cases.
- Confirm the detail page never implies broader consensus than the source support actually provides.

### Deliverable

A story page that can be shown publicly without apology.

### Exit criteria

- detail page supports the story rather than re-explaining the homepage
- source evidence is inspectable and clear
- the page still feels premium on weak or sparse story payloads
- summary semantics are aligned with what the backend actually returns, not with a stronger editorial model that does not exist yet

## Phase 5: Live Data Reality Pass

### Goal

Prove that the design holds up against real production-like payloads instead of ideal mocks.

### Tasks

- Run the frontend against live backend API data.
- Review multiple real briefs across desktop and mobile.
- Check at least:
  - strong multi-source hard-news story
  - single-source civic/public-interest story
  - story with weak or sparse tags
  - story with limited original-source links
  - story with noisy upstream cluster members
- Verify homepage/detail alignment:
  - lead story on home matches backend priority
  - detail page preserves the same editorial framing
- Confirm summary blocks feel honest across several real stories, not just the best-looking example.
- Confirm summary blocks do not surface raw noisy entity extraction as editorial bullets:
  - no date-fragment “debate” bullets
  - no weak entity artifacts presented as consensus
- Confirm source lists stay clean across several live stories, not just one cluster.
- Inspect all major breakpoints in browser:
  - small mobile
  - standard mobile
  - tablet
  - laptop
  - wide desktop

### Deliverable

A live-data validation pass with concrete keep/fix decisions.

### Exit criteria

- no major layout breaks on real stories
- no misleading trust or source language on real stories
- no noisy extracted-entity artifacts leaking into user-facing summary copy
- no obvious ranking mismatch between backend priority and frontend presentation

## Phase 6: Ship Hardening

### Goal

Finish the final public-ship layer: polish, accessibility, regression coverage, and operational confidence.

### Tasks

- Add or update targeted tests for any UI behavior changed in earlier phases.
- Verify accessibility basics:
  - heading structure
  - focus states
  - keyboard navigation
  - contrast on tonal blocks
  - link clarity
- Remove dead CSS and dead component branches introduced during earlier iterations.
- Review performance costs of large shadows, blur, and layered mobile interactions.
- Tighten copy throughout the product for consistency.
- Update release docs if the design system or ship criteria changed materially.
- Run one final live browser pass after all fixes.
- Run the final command-level verification loop before calling the product shippable.

### Current progress

- Story-selection hardening has moved forward:
  - raw discovery order from core sources now carries publisher-prominence metadata into scraped articles
  - deterministic publish scoring now includes publisher topline strength, not just coherence and category/impact
  - editorial prompts now explicitly target a national-topline Pakistan morning brief
  - a deterministic post-editorial guardrail now prevents an isolated low-prominence incident from surviving as the lead when a stronger topline story exists
- Story UX hardening has moved forward:
  - detail pages now open as `Quick brief` views rather than mini-article pages
  - top reporting links now appear directly inside the briefing card above the fold
  - the homepage featured card is lighter and less article-like while preserving the approved visual system
- Accessibility hardening has moved forward:
  - desktop and mobile edition dates now both use Pakistan time
  - the homepage filtered empty state now uses the product's `focus` language consistently
  - original-source `Read` links now expose descriptive accessible names
  - the original-source expander now exposes `aria-controls`
  - live status banners now announce politely
  - sheet/dialog focus now returns to the opener after close
  - button primitives and local action buttons now default safely to non-submit behavior
- Dead-edge cleanup has moved forward:
  - the old unused `StoryListItem` branch is already gone from earlier Phase 6 work
- Regression coverage has moved forward:
  - targeted backend ranking/discovery suite passed: `47 passed`, `3 skipped`
  - targeted homepage/detail/accessibility regression suite passed: `74 passed`
  - frontend production build passed on the same hardening pass
- Phase 6 is still open because the final ship gate still needs:
  - one last live browser pass on fresh data
  - one fresh live feed check that the published set feels like true Pakistan toplines rather than merely coherent clusters
  - a final contrast and heading-structure sweep
  - final public-ship signoff against live primary flows

### Deliverable

A ship candidate that is stable, deliberate, and supportable.

### Exit criteria

- tests and build pass
- live browser pass passes
- no known correctness issue remains in primary flows
- no remaining visual compromise feels like a temporary patch

## Backend Monitoring Track

This plan is frontend-first, but the following backend monitoring must continue in parallel because it directly affects frontend ship quality:

- repeated constrained live runs stay in the `5-9` range
- Gemini-first editorial keeps succeeding
- narrow incidents and soft features do not displace stronger national toplines or core public-life stories
- suspicious publish dates do not dominate ranking or prompt pressure
- cluster contamination stays rare enough that the frontend is not acting as the primary cleanup layer
- recent raw rows still reflect the intended reliable core sources

If any of these regress, frontend work should pause long enough to decide whether the issue is visual, contract-level, or upstream editorial quality.

## Sequence We Should Follow

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6

Do not skip from the current state straight into polish.

The correct order is:

- correctness
- system
- homepage
- detail
- live validation
- ship hardening

## Verification Loop We Must Use

This should be the standard verification sequence during execution:

1. targeted frontend tests for touched components
2. frontend production build
3. targeted backend API route or contract tests if payload behavior changed
4. real-browser validation against live backend data
5. constrained backend live pipeline monitoring
6. quality report review

### Core commands

Frontend:

```bash
cd frontend
npm test
npm run build
```

Backend targeted tests:

```bash
cd backend
source venv/bin/activate
venv/bin/pytest -q tests/test_api_feed_route.py tests/test_api_story_detail_route.py
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

## What We Are Explicitly Not Doing In This Plan

- expanding the product into Explore/Saved/features not needed for ship
- broad backend architecture changes
- adding new flaky sources just to increase volume
- building a fake editorial CMS layer
- inventing extra UI complexity to compensate for weak story payloads
- polishing mock-only scenarios while ignoring live-data behavior
- broadening source coverage before the reliable core and frontend presentation are clearly ship-ready

## Definition Of Done

Saaf Baat is ready to ship publicly when all of the following are true:

- the frontend reflects the Stitch editorial direction clearly and consistently
- desktop and mobile both feel intentional and premium
- the homepage lead story reliably matches backend editorial priority
- the detail page feels trustworthy and evidence-backed
- empty, stale, sparse, and failure states still feel finished
- original-source presentation is clean and honest
- no major UI decision depends on a hack or temporary patch
- live runs continue to produce a finite, on-mission morning brief
- repeated live runs continue to stay within `5-9` strong stories
- soft feature stories do not survive when stronger civic/public-interest stories exist
- suspicious publish-date behavior remains under control in live output
- source attribution remains credible and inspectable on the shipped UI

## Immediate Next Step When Execution Starts

Begin with **Phase 1: Correctness Before Cosmetics**.

The first concrete fixes to make when we execute should be:

1. fix freshness/status semantics
2. fix hidden original-sources empty state
3. audit all degraded states and tighten copy
4. then move into the design-system pass

That keeps the later visual work anchored to truth instead of presentation-only cleanup.
