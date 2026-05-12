# 2026-05-12 Topline Score Audit

## Hypothesis

Recent published stories with `publisher_topline_score = 0` are not all genuinely low-prominence stories.

At least some of those zeroes are likely caused by missing source-prominence metadata rather than by correct ranking logic.

## Commands Run

```bash
cd /Users/saqlain/projects/personal/saaf-baat/backend
venv/bin/python -c "<Supabase audit query for recent stories and raw-article prominence metadata>"
venv/bin/python scripts/quality_report.py --limit 20
```

## Findings

- The recent published set contained `7` rows.
- `4` of those published rows had `publisher_topline_score = 0`.
- The affected stories were:
  - `Heavy rains disrupt civic services`
  - `IHC schedules meeting between Imran Khan and counsel`
  - `Sindh announces fuel subsidy for motorcyclists`
  - `Security forces neutralize 13 terrorists in KP operations`
- Raw-article inspection showed the underlying prominence metadata was missing on those clusters:
  - `source_prominence_score = null`
  - `topline_bucket = null`
  - `discovery_rank = null`
  - `discovery_origin = null`
- This means the zeroes were a scoring-input bug, not a trustworthy signal that those stories lacked topline value.
- After adding source-name fallback prominence scoring, the same stories recomputed to:
  - `0 -> 10`
  - `0 -> 10`
  - `0 -> 20`
  - `0 -> 30`
- `venv/bin/python scripts/quality_report.py --limit 20` then reported `OK: all checked clusters meet thresholds`.

## Keep / Discard

- Keep:
  - fallback prominence scoring when older raw rows are missing legacy discovery metadata
  - explicit DB inspection as part of ranking audits
- Discard:
  - the assumption that `publisher_topline_score = 0` always means “correctly weak story”

## Next Step

- verify the next fresh live run writes non-zero prominence for strong publishable stories without relying on the fallback path
- keep watching `/api/feed` ordering and quality-report output after the next live publish
