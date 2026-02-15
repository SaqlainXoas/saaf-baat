# Saaf Baat

<p align="left">
  <img src="design/brand/icon/saaf-baat-icon.svg" alt="Saaf Baat logo" width="64" />
</p>

Calm, finite morning brief for Pakistan.

Saaf Baat turns multi-source coverage into a clear daily digest:
- what is agreed,
- what is debated,
- where to verify each claim from original reporting.

## Product Promise

Open once in the morning. Read 7 essential stories. Verify quickly. Move on with your day.

## Current Product Status

- Backend ingestion, clustering, analysis, API routes, and daily orchestration are implemented.
- Frontend home/detail experience, theme controls, focus filters, and reliability states are implemented.
- Frontend quality gates pass:
  - `cd frontend && npm test`
  - `cd frontend && npm run build`

## Repository Structure

- `backend/` FastAPI API, scraping + NLP pipeline, database layer, pytest suite
- `frontend/` Next.js App Router UI + Jest tests
- `docs/` core product documents and plans
  - `docs/plan.md` primary engineering execution plan
  - `docs/saaf-baat-prd-final.md` primary PRD
  - `docs/final-draft-product.md` frontend productization draft
  - `docs/final-draft-plan.md` completed frontend phase checklist
- `design/` brand and design assets

## Quick Start

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Environment Variables

### Frontend

- `NEXT_PUBLIC_API_URL` backend base URL (example: `http://localhost:8000`)
- `NEXT_PUBLIC_CITY_NAME` local greeting city (default: `Islamabad`)
- `NEXT_PUBLIC_DEFAULT_THEME` `system|light|dark` (default: `system`)

### Backend

Use `.env` (gitignored) for API keys and database credentials. See `CLAUDE.md` and `backend/config/` for operational details.

## Quality Commands

### Backend

```bash
cd backend
pytest
black src
ruff check src
mypy src
```

### Frontend

```bash
cd frontend
npm test
npm run build
```

## Documentation

- Developer and workflow notes: `CLAUDE.md`
- Primary product docs: `docs/`

## License

Open source (license file to be finalized).
