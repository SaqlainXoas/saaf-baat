# Saaf Baat — Final Draft Product Plan (Frontend → Market-Ready)

Date: **Feb 14, 2026**  
Scope: **Frontend polish + productization** (Next.js App Router UI for the existing backend)

## Execution status (Updated: **Feb 15, 2026**)
- [x] Phase 1 — Brand system
- [x] Phase 2 — Typography + spacing polish
- [x] Phase 3 — Theme control
- [x] Phase 4 — Home experience tuning
- [x] Phase 5 — Focus + lightweight personalization
- [x] Phase 6 — Story detail polish
- [x] Phase 7 — Reliability + backend integration hardening
- [x] Phase 8 — Ship checklist (`npm test` + `npm run build` passed)

## Product promise (what users should feel in 10 seconds)
**“Open once in the morning. See 7 essential stories. Trust what’s agreed. Tap originals. Close. Get on with life.”**

This is not a news feed. It’s a **finite morning brief** for Pakistan: calm, reliable, and skim-first.

---

## Current state (what exists today)
Core UI is implemented and working:
- Home route renders **finite stories** (max 7), mobile **deck**, desktop **brief flow**: `frontend/src/app/page.tsx`
- Story detail route with **Consensus Engine** and **Original sources**: `frontend/src/app/stories/[cluster_id]/page.tsx`
- Focus filters are **functional** and URL-driven (`impact`, `sources`): `frontend/src/components/FocusControl.tsx`, `frontend/src/utils/focusFilters.ts`
- Design tokens exist (paper/surfaces/elevation/focus ring): `frontend/src/app/globals.css`
- Jest tests cover core components and filter logic: `frontend/tests/**`

### Key flaws identified initially (resolved in current build)
1) **Brand isn’t “owned”**: icon rendering is an `<img>` and wordmark typography isn’t a system. It can feel generic.
2) **Typography rhythm isn’t editorial**: sizes/weights/leading don’t yet create the calm hierarchy in the mock.
3) **Light/dark isn’t product-controlled**: relies on `prefers-color-scheme`; no user toggle; dark can feel heavy.
4) **Surface consistency**: hover/pressed/focus states are uneven across buttons/cards/links.
5) **Skim speed**: compact cards need stricter anatomy so users can scan 7 stories faster.

---

## Locked decisions (best-practice defaults)
These choices are the “most user-friendly + most premium + best match to the mock”.

1) **Desktop home layout:** Single-column centered brief flow (Featured + 6 compact cards)
2) **Mobile home layout:** Deck (stacked cards + progress + caught-up closure)
3) **Density:** Featured spacious + rest compact (1-line snippet + inline chips)
4) **Theme:** System default with an explicit toggle (System / Light / Dark)
5) **Dark mode style:** Warm-dark (not pure black) for morning readability
6) **Background:** Warm paper + *very subtle* ambient gradients (no vignette “cinema”)
7) **Brand header:** Inline SVG mark + wordmark (theme-safe), no raster lockups
8) **Trust signals:** Chips are primary; source names/assessed are quiet secondary
9) **Detail page:** Mock order (header card → consensus blocks → originals list → expand coverage)

---

## Design system v1 (decision-complete tokens)
Implement these values as the single source of truth in `frontend/src/app/globals.css`.

### Light
- `--paper`: `#F4EFE3`
- `--surface`: `#FFFFFF`
- `--surface-2`: `#FBFAF6`
- `--ink`: `#0B1220`
- `--ink-muted`: `rgba(11, 18, 32, 0.62)`
- `--hairline`: `rgba(11, 18, 32, 0.10)`
- `--teal`: `#52B7A3`
- `--teal-light`: `#7CD6C8`
- `--mint-bg`: `rgba(82, 183, 163, 0.14)`
- `--amber-bg`: `rgba(240, 195, 122, 0.22)`

### Warm-dark
- `--paper`: `#0C0F10`
- `--surface`: `#121617`
- `--surface-2`: `#0F1314`
- `--ink`: `#F5F7F7`
- `--ink-muted`: `rgba(245, 247, 247, 0.72)`
- `--hairline`: `rgba(245, 247, 247, 0.12)`
- `--teal`: `#49C0AA`
- `--teal-light`: `#66D4C0`
- `--mint-bg`: `rgba(73, 192, 170, 0.16)`
- `--amber-bg`: `rgba(241, 194, 124, 0.18)`

### Typography (system font, editorial scale)
- Featured card headline: **28px**, weight 700, leading 1.15
- Compact card headline: **14px**, weight 700, leading 1.2
- Featured snippet: **14px**, leading 1.55
- Compact snippet: **12px**, leading 1.55 (clamp 1)
- Detail headline: **30px**, weight 700, leading 1.15
- Detail snippet: **14px**, leading 1.55
- Metadata (sources/date): **12px**, muted

### Layout + surfaces
- Desktop container width: **860–920px** max (default 900px)
- Card radius: **26px** (`--radius-2xl`)
- Card border: `1px solid var(--hairline)`
- Card elevation:
  - default: `--elev-1` (soft)
  - hover: `--elev-2` + translateY(-1px) (desktop only)
- Ambient glow: keep, but it must be **subtle** (no vignette; no heavy top gradient)

---

## Component specs v1 (decision-complete anatomy)

### Home — Featured card
- `Pill` (primary impact only)
- Headline clamp **2 lines**
- Snippet clamp **2 lines**
- Trust: “Agreed across sources” (max 2 chips) + “Debated / emerging” (max 1 chip)
- Sources: “Sources assessed: Dawn • Geo • Tribune” (quiet)
- CTA: “Open →” (quiet teal)

### Home — Compact cards (6 items)
- `Pill` (same size as featured)
- Headline clamp **2 lines**
- Snippet clamp **1 line**
- Trust chips inline (no labels; max 3 total)
- Sources: “Sources assessed: {N}” (quiet)
- Whole card is clickable

### Mobile — Deck
- Show 4 layers (top + 3 behind)
- Keep progress dots + `2 / 7`
- Caught-up text shown after last card (same copy as desktop)
- Reduced motion: disable transitions if `prefers-reduced-motion`

### Detail page
- Header inside a flat card (`surface`, hairline border)
- Consensus Engine:
  - two blocks: mint (“What’s agreed”), amber (“What’s debated”)
  - caps: agreed 2, debated 1
  - show “Sources assessed: {N}” (quiet)
- Original sources:
  - rows: source badge, “Source: Headline”, quiet “Read” link right
  - “View full coverage →” expands in place (toggle to “Show less”)

---

## Design principles (non-negotiable)
- **Finite beats infinite:** no infinite scroll cues; show closure (“caught up”)
- **Skim-first hierarchy:** strict caps (headline/snippet/chips)
- **Calm surfaces:** warm paper, soft elevation, no loud colors, no urgency red
- **Trust is visible:** “Agreed” vs “Debated” is always present, never hidden behind taps
- **Verifiable by default:** original sources always reachable in one tap
- **Accessibility:** keyboard nav, focus rings, reduced motion support

---

## Phase plan (incremental, verifiable, test-backed)

### ✅ Phase 1 — Brand system (logo, wordmark, header) — Completed
**Goal:** instantly recognizable brand that looks intentional in light/dark.

**Work**
- Add `frontend/src/components/Logo.tsx` (inline SVG; accepts `size`, `variant`)
- Update `frontend/src/components/BrandHeader.tsx` to use `<Logo />` + refined wordmark
- Add a small “brand spacing spec” to `design/brand/README.md` (usage + sizes)

**Acceptance**
- Logo is crisp at 18–28px and consistent in light/dark
- Header reads as “product”, not “template”

**Tests**
- Update `frontend/tests/components/BrandHeader.test.tsx` to assert Logo renders and wordmark exists

---

### ✅ Phase 2 — Typography + spacing polish (editorial hierarchy) — Completed
**Goal:** the mock’s premium readability: big headline, calm snippet, quiet metadata.

**Work**
- Finalize a type scale + leading system in `frontend/src/app/globals.css`
- Replace “inline style typography tweaks” with consistent class patterns where possible
- Enforce line-length and clamp rules:
  - Home featured: headline clamp 2, snippet clamp 2
  - Home compact: headline clamp 2, snippet clamp 1
  - Detail: headline large, snippet relaxed, metadata quiet

**Acceptance**
- Users can skim 7 stories in under 20 seconds without visual fatigue
- No layout jumpiness when headlines are long

**Tests**
- Update/add tests for clamping behavior (DOM presence + no overflow assumptions)

---

### ✅ Phase 3 — Theme control (System/Light/Dark toggle) — Completed
**Goal:** reliable theme experience; dark mode feels warm and premium.

**Work**
- Add `frontend/src/components/ThemeProvider.tsx` (client):
  - stores `theme` in `localStorage`
  - applies `data-theme="light|dark|system"` on `<html>`
- Update `frontend/src/app/globals.css` to read from `[data-theme]` instead of only `prefers-color-scheme`
- Add `frontend/src/components/ThemeToggle.tsx` (header control)
- Add `NEXT_PUBLIC_DEFAULT_THEME` optional (defaults to `system`)

**Acceptance**
- Theme choice persists across refresh
- Dark mode retains “paper/ink” warmth (not pure black)

**Tests**
- Unit test theme storage logic (mock `localStorage`)
- Component test: toggle updates attribute on `document.documentElement`

---

### ✅ Phase 4 — Home experience tuning (brief flow + “finite ritual”) — Completed
**Goal:** desktop feels like a morning brief, not a dashboard; mobile deck feels premium.

**Work**
- Desktop:
  - Keep single-column flow but tune container width (820–920px), vertical rhythm, card spacing
  - Add “7 essential stories” context near header (desktop too, subtle)
- Mobile:
  - Keep deck; tune stack offsets/shadows; ensure reduced motion is respected
  - Ensure progress + caught-up is visually identical to mock intent
- Ensure end-state copy is consistent on both: “You’re all caught up. Enjoy your day.”

**Acceptance**
- Desktop: one flow, no “side rail” perception, no excessive empty canvas
- Mobile: deck feels layered, not like repeated identical rectangles

**Tests**
- Snapshot-like component tests (structure-only) for Home (optional)
- Keep `frontend/tests/components/Deck` logic covered (add tests if missing)

---

### ✅ Phase 5 — Focus + lightweight personalization (without accounts) — Completed
**Goal:** users feel this is “their” brief while staying simple.

**Work**
- Keep URL query as source of truth (`impact`, `sources`)
- Add *optional* persistence:
  - If user applies Focus, store it in `localStorage` and re-apply on next visit (unless URL overrides)
- Greeting/local tone:
  - Keep “Subah Bakhair, {City}.” and make `NEXT_PUBLIC_CITY_NAME` first-class
- Add “Clear focus” quick action when filters active (desktop + mobile)

**Acceptance**
- Returning users see their preferred focus without needing login
- Sharing links still works (URL remains canonical)

**Tests**
- Unit tests for “URL overrides localStorage”
- Component test for “Clear all” resets filters

---

### ✅ Phase 6 — Story detail polish (trust + originals) — Completed
**Goal:** detail view becomes the “aha” moment (what makes Saaf Baat different).

**Work**
- Consensus Engine:
  - maintain caps (Agreed 2, Debated 1)
  - refine spacing, icons, and “Sources assessed” label hierarchy
- Original sources:
  - list rows feel like the mock (quiet “Read”, aligned metadata)
  - “View full coverage →” expands in place (already implemented; polish styling + transitions)

**Acceptance**
- Detail is calm, scannable, and obviously trust-oriented

**Tests**
- Extend `frontend/tests/components/ConsensusEngine.test.tsx` for layout invariants
- Extend `frontend/tests/components/OriginalSourcesList.test.tsx` to verify expand/collapse

---

### ✅ Phase 7 — Reliability + backend integration hardening — Completed
**Goal:** “reliable product” feel: graceful errors, no confusing fallback behavior.

**Work**
- `frontend/src/data/api.ts`:
  - Add visible “offline/mock” banner in dev when API is missing (optional)
  - Improve error states: don’t silently swap to mock in prod without signal
- Add loading states (skeletons) for slow API responses (minimal, calm)
- Validate external link handling for originals (noopener/noreferrer, target=_blank)

**Acceptance**
- Users never wonder “is this real data?”
- Error states are calm and actionable

**Tests**
- Unit tests for API fallback behavior based on env

---

### ✅ Phase 8 — Ship checklist (quality gates) — Completed
**Goal:** ready to demo/sell as a coherent product.

**Quality gates**
- `cd frontend && npm test`
- `cd frontend && npm run build`
- Manual QA widths: 390 / 768 / 1024 / 1280
- Keyboard nav: Focus sheet, toggles, close, escape
- Contrast check on light/dark tokens
- Reduced motion check (deck + sheet)

**Optional (recommended)**
- Add Playwright smoke tests (Home loads, Focus filters apply, Story detail opens)

---

## Metrics for “this is good enough to ship”
- **Skim time:** can read headlines of 7 stories in < 20s
- **Trust clarity:** users can answer “what’s agreed vs debated?” without scrolling much
- **Completion feeling:** end-state is visible and satisfying (caught up)
- **Retention lever:** Focus + theme persist; greeting feels local and warm

---

## Implementation notes (env + config)
Frontend env vars (document in `frontend/README` or root README when shipping):
- `NEXT_PUBLIC_API_URL` (prod backend)
- `NEXT_PUBLIC_CITY_NAME` (default: Islamabad)
- `NEXT_PUBLIC_DEFAULT_THEME` (`system|light|dark`, default: system)
