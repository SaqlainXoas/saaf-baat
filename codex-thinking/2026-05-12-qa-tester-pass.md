# 2026-05-12 QA Tester Pass

## Hypothesis

The app may be technically green while still failing the product standard for a trustworthy Pakistan morning brief.

## Commands Run

```bash
cd /Users/saqlain/projects/personal/saaf-baat/backend
venv/bin/pytest -q
venv/bin/python scripts/quality_report.py --limit 20

cd /Users/saqlain/projects/personal/saaf-baat/frontend
npm test -- --runInBand
npm run build

curl -sS -m 15 http://127.0.0.1:8000/health
curl -sS -m 20 'http://127.0.0.1:8000/api/feed?limit=9'
curl -sS -m 20 'http://127.0.0.1:8000/api/stories/8a720596-295f-4fbc-882b-d1638ba72043'
```

Live QA also covered:

- desktop homepage in browser
- mobile homepage in browser
- desktop detail page in browser
- mobile detail page in browser

## Findings

- `P0` Live product is stale, not ship-ready.
  - `/health` returns `pipeline_is_stale: true`
  - `last_run_at` is `null`
  - homepage is serving a brief from `2026-04-08`

- `P1` Homepage identity is contradictory on a stale brief.
  - UI shows current date and `Today's edition`
  - main headline shows `Morning Brief · April 8`
  - result feels mixed rather than calm and trustworthy

- `P1` Mobile lead-card regression: top story does not show `What to watch`.
  - lower homepage cards show it
  - lead mobile card drops it, which breaks the promised card shape

- `P1` Source publish times look collapsed and untrustworthy.
  - detail payload and UI show multiple different reports with the same `8 Apr, 12:00 am PKT` timestamp
  - this weakens freshness and source-confidence signals

- `P1` Operator health data is still incomplete for real QA use.
  - `degraded_sources` is empty
  - `source_article_counts` is empty
  - after a stale 33-day gap, operators still cannot see which source path failed or stopped

- `P2` Mobile/header chrome overlap issue.
  - skip link visually crowds or obscures the brand/header area
  - detail-page back link is clipped near the top edge on mobile

- `P2` Editorial trust is not yet strong enough for a finished product feel.
  - the lead story is a very large geopolitical claim
  - with the brief 33 days stale, the app does not provide enough confidence framing for that level of claim

- `P2` Taxonomy still feels off in places.
  - `Sindh announces fuel subsidy for motorcyclists` is published as `politics`
  - the story reads more like economy/cost-of-living than politics in the user-facing product

## Keep / Discard

- Keep:
  - stale-brief warning behavior
  - finite brief structure
  - visible source support treatment
  - detail-page back-to-brief identity anchor

- Discard:
  - treating green tests as evidence that the live product is ready
  - current mixed stale-state identity copy as “good enough”

## Next Step

- run a fresh live pipeline before any ship decision
- fix the stale-state identity mismatch on the homepage
- restore `What to watch` on the mobile lead card
- audit source publish-date normalization before calling the trust layer finished
