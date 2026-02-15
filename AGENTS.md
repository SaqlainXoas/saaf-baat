# Repository Guidelines

## Project Structure

- `backend/`: Python FastAPI API + news pipeline
  - `backend/src/`: application code (`scrapers/`, `agents/`, `db/`, `api/`, `pipeline/`, `utils/`)
  - `backend/config/`: YAML config (`sources.yaml`, `classification_rules.yaml`)
  - `backend/tests/`: pytest suite (unit/integration/slow markers)
  - Entrypoints: `backend/main.py` (API app), `backend/run_pipeline.py` (daily pipeline)
- `frontend/`: Next.js (App Router) UI
  - `frontend/src/app/`: routes (e.g. `stories/[cluster_id]`)
  - `frontend/src/components/`: UI components
  - `frontend/tests/`: Jest + Testing Library tests
- Root docs/plans: `README.md`, `CLAUDE.md`, `plan*.md`, `saaf-baat-prd-final.md`

## Build, Test, and Development Commands

Backend (run from `backend/`):
- Install: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Models: `python -m spacy download en_core_web_sm`
- API: `uvicorn main:app --reload` (docs at `/docs`)
- Pipeline: `python run_pipeline.py` (use `--disable-playwright` for faster CI installs)
- Quality: `black src`, `ruff check src`, `mypy src`
- Tests: `pytest` (coverage configured via `pytest.ini`)

Frontend (run from `frontend/`):
- Install: `npm ci`
- Dev: `npm run dev`
- Lint: `npm run lint`
- Tests: `npm test`
- Build/serve: `npm run build && npm run start`

## Coding Style & Naming Conventions

- Python: Black + Ruff, 100-char lines (`backend/pyproject.toml`); `snake_case` for functions/files, `PascalCase` for classes.
- TypeScript/React: `PascalCase` components, `.tsx` for React; prefer `@/…` imports (Jest maps `@/` → `frontend/src/`).
- Keep generated artifacts out of commits (e.g. `frontend/.next/`, `backend/htmlcov/`, local `backend/venv/`).

## Testing Guidelines

- Backend: name tests `test_*.py`; use markers (`@pytest.mark.unit|integration|slow`) and run subsets, e.g. `pytest -m unit`.
- Frontend: name tests `*.test.tsx` under `frontend/tests/`; use Testing Library patterns.

## Commit & Pull Request Guidelines

- Commits: concise, imperative summaries (examples in history: “Add …”, “Fix …”, “Refactor …”, “Restructure: …”); avoid mentioning AI tools.
- PRs: include a clear description, linked issue/plan if applicable, and screenshots for UI changes; call out any config/env var changes.

## Security & Configuration

- Secrets live in `.env`/`.env.local` (gitignored). If adding new required variables, document them in `README.md` and/or provide a safe `.env.example`.
