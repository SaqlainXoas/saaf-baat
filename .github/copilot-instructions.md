# Saaf Baat - Copilot Instructions

## Project Overview
Saaf Baat is a **free, open-source news intelligence platform for Pakistan** that synthesizes multi-source news into factual summaries. Core philosophy: "Open once in morning. Know what matters. Close app."

**Key constraint:** Zero-cost infrastructure only (GitHub Actions, Supabase free tier, Vercel Hobby). No ads, tracking, or paywalls—news as a public utility.

## Architecture

### Data Pipeline (runs daily 6am PKT via GitHub Actions)
```
Scraping → Embeddings → Clustering → NLP Analysis → Frontend
```

1. **Scraping** (`backend/src/scrapers/`): Multi-tier - newspaper4k (primary) → news-please (fallback) → Playwright (JS-heavy sites)
2. **Embeddings** (`backend/src/agents/embeddings.py`): Gemini API (primary) → sentence-transformers (local fallback)
3. **Clustering** (`backend/src/agents/clustering.py`): HDBSCAN (primary) → DBSCAN (fallback)
4. **Analysis** (`backend/src/agents/analysis.py`): spaCy NER + SetFit classification + rule-based keywords

### Database (Supabase PostgreSQL)
- `raw_articles`: Scraped content before processing
- `clusters`: Grouped articles by story (has `centroid_embedding VECTOR(768)`)
- `analyzed_feed`: Final stories with confirmed facts, debated claims, impact labels

## Critical Development Rules

### Python Environment
```bash
cd backend && source venv/bin/activate  # ALWAYS activate before any Python work
```

### Git Commits
- **NEVER mention AI tools** in commit messages (no "Claude", "Copilot", etc.)
- Use imperative mood: "Add feature" not "Added feature"
- Commit at feature completion, not after every small change

### Adding New News Sources
1. Add config to `backend/config/sources.yaml` (method: newspaper4k/playwright, rate_limit, sections)
2. Test locally: `python -m src.scrapers.test_source --source=new_source`
3. Update orchestrator if needed

### Modifying Classification
- **Keyword changes:** Edit `backend/config/classification_rules.yaml` only (no code changes)
- **SetFit updates:** Retrain in `src/agents/classifier.py`
- Always maintain hybrid approach (SetFit + rules)

## Code Patterns

### Embedding Service (Always use abstraction, never call APIs directly)
```python
# Correct - uses automatic Gemini→local fallback
embeddings = await embedding_service.embed_batch(texts)

# Wrong - no fallback handling
embeddings = gemini_client.embed(texts)
```

### Consensus Detection (core differentiator)
```python
# Entities in ALL articles = confirmed facts
confirmed = set.intersection(*[article.entities for article in cluster])

# Entities in SOME but not ALL = debated claims  
debated = set.symmetric_difference(*[article.entities for article in cluster])
```

### Impact Labels (user relevance)
- 💳 WALLET, 🚦 COMMUTE, 🛡️ SAFETY, 🏢 WORK, ⚡ UTILITIES, 🏛️ GOVERNANCE
- Defined via keywords in `classification_rules.yaml`

## Quality Gates

### Clustering Validation (auto-fallback to DBSCAN if fails)
- Minimum 3 distinct clusters
- Noise ratio < 30%
- Avg intra-cluster similarity > 0.7

### Pipeline Targets
- Scraping success: >95%
- Pipeline execution: <30 minutes
- Classification accuracy: >80%

## Commands

```bash
# Backend
cd backend && source venv/bin/activate
python main.py                            # Full pipeline
python -m src.scrapers.orchestrator       # Scraping only
python -m src.agents.clustering           # Clustering only
pytest tests/                             # Run tests
black src/ && ruff check src/             # Lint

# Frontend
cd frontend && npm install
npm run dev                               # Dev server (localhost:3000)
npm run build && npm start                # Production build
```

## Non-Goals (Never Implement)
- Ads, tracking, paywalls, user data collection
- Engagement optimization (infinite scroll, clickbait)
- Hard-coded source selectors (use `sources.yaml`)
- Skipping fallback mechanisms

## Phase 1 Focus
Build complete ML pipeline without LLM dependency. Phase 2 (Gemini Flash summaries) is optional enhancement—Phase 1 must work independently.
