<p align="center">
  <img src="frontend/public/icon.svg" alt="Saaf Baat Logo" width="110" />
</p>

<h1 align="center">Saaf Baat</h1>
<p align="center"><strong>A finite Pakistan morning brief. What happened, what changed for you, and then it ends.</strong></p>

## What this is

Saaf Baat is not a news reader. It is a **6–12 card morning brief** that a
person in Pakistan can read once, before getting on with the day.

Every card answers two things:

- **what happened**, drawn from several publishers rather than one
- **what is different for you today** — a price, a deadline, a closure, a queue

Then it stops. There is no infinite scroll, and the brief is short on a quiet
day rather than padded to a number.

## How it works

```
RSS + Google-News sitemaps   8 publishers, ~26 endpoints, ~300 articles in ~6s
        ↓                    every endpoint gated on the age of its newest item
Gemini embeddings            one request per text, paced for the free tier
        ↓
Gemini triage                category, impact, story type, Pakistan relevance
        ↓
Deterministic event grouping 0.92 pair similarity; LLM adjudicates only the
        ↓                    genuinely ambiguous split/merge pairs
Gemini editorial selection   picks the brief and writes each card
        ↓
Gemini story analysis        multi-source analysis + optional accountability
        ↓                    question, both validated against the reporting
FastAPI  →  Next.js
```

About 16–24 LLM calls a day, inside the free tier. Storage is local SQLite by
default; Postgres/Supabase is opt-in.

## Principles

- Prefer importance over recency, and one clean card per real event.
- **Never pad the brief.** Six strong cards beat twelve with six weak ones.
- Source count tells you a story is true, not that it is important — a ministry
  press release every publisher reprinted is still a card with no reader in it.
- Deterministic where determinism helps; the LLM only for triage, ambiguous
  adjudication, editorial selection and the analysis layer.
- A provider failure must be visible, not fatal. An editorial outage publishes
  nothing and leaves yesterday's brief standing, honestly labelled stale.
- The UI must never assert more than the backend knows, or quietly show less.

## Running it

Backend, from `backend/`:

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

```bash
python -m spacy download en_core_web_sm
```

```bash
python scripts/init_db.py
```

```bash
python run_pipeline.py --log-level INFO
```

```bash
uvicorn main:app --reload
```

Frontend, from `frontend/`:

```bash
npm ci && npm run dev
```

Copy `backend/.env.example` to `backend/.env` and set `GEMINI_API_KEY`.

## Tests and evaluation

```bash
cd backend && source venv/bin/activate && python -m pytest -q && ruff check .
```

```bash
cd frontend && npm test && npm run typecheck && npm run lint && npm run build
```

The golden day replays a recorded news day through the real pipeline, offline,
in about six seconds, and scores the brief against what that day should have
contained:

```bash
cd backend && source venv/bin/activate && python scripts/eval_golden_day.py
```

`--live-editorial` replays the same day through the real editor and story
analysis — the only way to A/B a prompt change without waiting for tomorrow's
news. It reports and never gates.

**A green suite says the code does what it was written to do. It says nothing
about whether the brief is good.** Check `/api/feed`, the database and the
rendered page.

## Layout

```
backend/
  src/agents/      embeddings, triage, clustering, editorial, story analysis
  src/pipeline/    orchestration
  src/scrapers/    RSS + sitemap ingest, lazy body fetch
  src/db/          storage clients (SQLite default) and models
  src/api/         FastAPI app and routes
  src/eval/        golden-day evaluation
  config/          sources.yaml and the LLM prompts
  tests/           pytest suites

frontend/
  src/app/         Next.js routes
  src/components/  UI
  src/data/        API client and adapters
  tests/           Jest + Testing Library
```

## Documentation

Four files, deliberately:

| File | What it holds |
|---|---|
| `README.md` | this — what the product is and how to run it |
| `AGENTS.md` | locked product decisions |
| `CLAUDE.md` | the working guide and architecture reference |
| `docs/status.md` | current state, verification numbers, open work |

Anything else is scratch and belongs outside the repo. A stale document is
worse than no document — it is the file the next session reads and believes.
