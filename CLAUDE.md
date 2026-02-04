# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Saaf Baat** is a minimalist news intelligence platform for Pakistan that synthesizes multi-source news coverage into clear, factual summaries. It's a 100% free, open-source public utility with zero ads, zero tracking, and zero paywalls.

**Core Philosophy:** "Open once in morning. Know what matters. Close app. Get on with life."

**Key Principle:** News as a public utility, not a business. We prioritize clarity over engagement, facts over clicks.

## Repository Structure

```
saaf-baat/
├── .github/workflows/        # GitHub Actions orchestration
│   ├── daily_pipeline.yml   # Main daily scraping/processing pipeline (runs 6am PKT)
│   └── frontend_test.yml    # Frontend CI checks
├── backend/                 # Python intelligence engine
│   ├── config/             # YAML configuration files
│   │   ├── sources.yaml    # News source definitions with scraping methods
│   │   └── classification_rules.yaml  # Keyword-based classification rules
│   ├── src/
│   │   ├── scrapers/       # News scraping modules (newspaper4k + Playwright)
│   │   ├── agents/         # ML pipeline (embeddings, clustering, NLP)
│   │   └── database/       # Supabase client and schema management
│   ├── main.py             # Pipeline entry point (called by GitHub Actions)
│   └── requirements.txt    # Python dependencies
└── frontend/               # Next.js user interface
    ├── app/                # Next.js App Router
    │   ├── feed/          # Main news feed page
    │   └── story/[id]/    # Individual story detail page
    ├── components/         # React components
    │   ├── StoryCard.tsx  # Master card component (core UI)
    │   └── ui/            # Reusable UI primitives
    ├── lib/
    │   └── supabase.ts    # Frontend Supabase client
    └── package.json
```

## Developer Guidelines

### Python Virtual Environment
**CRITICAL:** Always activate the virtual environment before running any Python commands:
```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
```
All Python work (pip installs, running scripts, tests, etc.) must be done inside the activated venv.

### Git Commit Conventions
- **Keep commits minimal and descriptive** - Focus on what changed, not implementation details
- **NEVER mention AI tools in commit messages** - No references to Claude, assistants, or AI
- **Commit at feature completion or checkpoints** - Not after every small change
- **Use imperative mood** - "Add feature" not "Added feature" or "Adding feature"

**Examples of good commit messages:**
```
Add scraping module for Dawn News
Update clustering algorithm parameters
Fix entity extraction bug
Add Supabase schema migrations
Configure GitHub Actions workflow
```

## Development Commands

### Backend (Python)

**Setup environment:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

**Run the full pipeline locally:**
```bash
cd backend
python main.py
```

**Run individual components:**
```bash
# Scraping only
python -m src.scrapers.orchestrator

# Clustering only (requires existing articles in DB)
python -m src.agents.clustering

# Analysis only
python -m src.agents.analysis
```

**Run tests:**
```bash
pytest tests/
pytest tests/test_scrapers.py -v  # Specific test file
pytest -k "test_hdbscan"          # Specific test pattern
```

**Lint and format:**
```bash
black src/
ruff check src/
mypy src/
```

### Frontend (Next.js)

**Setup and run development server:**
```bash
cd frontend
npm install
npm run dev  # Starts on http://localhost:3000
```

**Build and preview production:**
```bash
npm run build
npm start
```

**Run tests:**
```bash
npm test
npm run test:watch
```

**Lint and format:**
```bash
npm run lint
npm run format
```

## High-Level Architecture

### Data Pipeline Flow

1. **Scraping** (GitHub Actions, daily 6am PKT)
   - Multi-tier approach: newspaper4k (primary) → news-please (fallback) → Playwright (dynamic content)
   - Sources defined in `backend/config/sources.yaml`
   - Writes to `raw_articles` table in Supabase

2. **Embedding Generation**
   - Primary: Google Gemini `text-embedding-004` API (task_type='CLUSTERING')
   - Fallback: sentence-transformers/all-MiniLM-L6-v2 (runs locally)
   - Implemented in `EmbeddingService` class with automatic fallback

3. **Story Clustering**
   - Primary: HDBSCAN (handles varying densities, auto-determines cluster count)
   - Fallback: DBSCAN (eps=0.75, metric='cosine')
   - Groups related articles from different sources into unified stories

4. **NLP Analysis & Classification**
   - **Entity extraction:** spaCy en_core_web_sm (18 entity types)
   - **Consensus detection:** Set intersection/difference across articles in cluster
   - **Category classification:** SetFit zero-shot learning + rule-based keywords
   - **Impact labeling:** 💳 WALLET, 🚦 COMMUTE, 🛡️ SAFETY, 🏢 WORK, ⚡ UTILITIES, 🏛️ GOVERNANCE

5. **Frontend Display**
   - Next.js fetches from Supabase `analyzed_feed` table
   - Story cards show: headline, confirmed facts, debated claims, source attribution
   - Category filters and impact badges for personalization

### Key Architectural Decisions

**Why HDBSCAN over K-Means?**
- News story count varies daily (can't pre-define K)
- Handles varying cluster densities (some stories have 20+ sources, others 2-3)
- Automatic noise detection for one-off stories
- Backed by Amazon FSI news clustering research

**Why Gemini embeddings with local fallback?**
- High quality comparable to OpenAI
- Generous free tier (100 RPM, 30K tokens/min, 1K req/day)
- `task_type='CLUSTERING'` parameter optimizes for our use case
- Local sentence-transformers ensures zero downtime

**Why spaCy over NLTK?**
- Production-grade performance (5x faster)
- 18 entity types vs NLTK's 3
- Context-aware dependency parsing
- Industry standard for NLP pipelines

**Why SetFit for classification?**
- Few-shot learning (8 examples per class vs thousands)
- 67x faster than BART-large-mnli
- Outperforms GPT-3 on RAFT benchmark despite being 30x smaller
- Easy to add new categories without full retraining

**Why GitHub Actions?**
- Zero cost (2,000 min/month free for private, unlimited for public)
- 2-core CPU, 7GB RAM sufficient for ML workload
- Built-in cron scheduling
- Code and pipeline versioned together

## Database Schema (Supabase PostgreSQL)

### `raw_articles`
Stores scraped articles before processing.
```sql
id UUID PRIMARY KEY
source VARCHAR(100)          -- e.g., "dawn", "geo_news"
url TEXT UNIQUE
headline TEXT
main_text TEXT
author VARCHAR(200)
publish_date TIMESTAMPTZ
scrape_timestamp TIMESTAMPTZ
raw_html_backup TEXT
content_hash VARCHAR(64)     -- For deduplication
```

### `clusters`
Groups related articles into unified stories.
```sql
cluster_id UUID PRIMARY KEY
article_ids UUID[]           -- Array of raw_articles.id
centroid_embedding VECTOR(768)
num_sources INTEGER
created_at TIMESTAMPTZ
```

### `analyzed_feed`
Final processed stories for frontend display.
```sql
id UUID PRIMARY KEY
cluster_id UUID REFERENCES clusters
headline TEXT
category VARCHAR(50)         -- economy, politics, city, etc.
confirmed_facts JSONB        -- Entities in ALL sources
debated_claims JSONB         -- Entities in SOME sources
impact_labels TEXT[]         -- [💳 WALLET, 🚦 COMMUTE, etc.]
source_attribution JSONB     -- Which outlets reported what
relevance_score FLOAT
publish_date TIMESTAMPTZ
llm_enhanced_summary TEXT    -- (Phase 2: optional Gemini Flash summaries)
```

## Configuration Files

### `backend/config/sources.yaml`
Defines news sources and scraping methods:
```yaml
sources:
  dawn:
    url: "https://www.dawn.com"
    method: "newspaper4k"
    sections: ["latest-news", "pakistan", "business"]
    rate_limit: 1  # seconds between requests

  pakwheels_forum:
    url: "https://www.pakwheels.com/forums"
    method: "playwright"
    scroll_depth: 3
```

### `backend/config/classification_rules.yaml`
Keyword-based classification rules (supplements SetFit):
```yaml
categories:
  economy: ["rupee", "dollar", "inflation", "budget", "psx", "imf"]
  politics: ["election", "assembly", "minister", "pti", "pmln", "ppp"]

impact_labels:
  "💳 WALLET": ["price", "increase", "tax", "salary", "petrol", "bill"]
  "🚦 COMMUTE": ["road", "closed", "accident", "metro", "traffic"]
```

## Important Implementation Notes

### Multi-Tier Scraping Strategy
When adding new sources, follow this decision tree:
1. **Static HTML sites:** Use newspaper4k (Dawn, Tribune, Express Tribune)
2. **JavaScript-heavy sites:** Use Playwright (Geo News with lazy loading)
3. **Specialized content:** Add custom parser extending base scraper

### Embedding Service Pattern
The `EmbeddingService` class abstracts embedding generation:
```python
# Automatically tries Gemini first, falls back to local model
embeddings = await embedding_service.embed_batch(texts)
```
Never call embedding APIs directly - always use this service to ensure fallback.

### Clustering Quality Checks
After clustering, validate results:
- Minimum 3 distinct clusters
- Noise ratio < 30% (articles labeled as outliers)
- Average intra-cluster similarity > 0.7
If quality checks fail, HDBSCAN automatically falls back to DBSCAN.

### Consensus Detection Logic
For each cluster, extract entities from all articles:
- **Confirmed facts:** Entities present in ALL articles (set intersection)
- **Debated claims:** Entities in SOME but not ALL (symmetric difference)
This creates "What's Certain" vs "What's Debated" sections in story cards.

### Zero-Cost Infrastructure Requirements
- Supabase free tier: 500MB database + 2GB storage (monitor usage)
- GitHub Actions: 2,000 min/month for private repos, unlimited for public
- Vercel Hobby tier: Next.js hosting with unlimited bandwidth
- Gemini API: 1,000 requests/day free (batch requests to stay under limit)

## Development Workflow

### Adding a New News Source
1. Add source config to `backend/config/sources.yaml`
2. If using Playwright, add selector mappings to scraper
3. Test scraping locally: `python -m src.scrapers.test_source --source=new_source`
4. Update `sources` array in orchestrator
5. Monitor first run via GitHub Actions logs

### Modifying Classification Logic
1. For keyword changes: Edit `classification_rules.yaml` (no code changes needed)
2. For SetFit model updates: Retrain with new examples in `src/agents/classifier.py`
3. Always maintain hybrid approach (SetFit + rules) for robustness

### Debugging Pipeline Failures
1. Check GitHub Actions logs for error stage
2. Run problematic component locally with `--debug` flag
3. For scraping failures: Check if source HTML structure changed
4. For clustering issues: Inspect embedding quality and cluster metrics
5. Use Supabase dashboard to query intermediate tables

## Phase 1 vs Phase 2

**Current focus: Phase 1 (8-10 weeks)**
- Complete ML-powered pipeline without LLM dependency
- Rule-based + SetFit classification
- spaCy entity extraction and consensus detection
- Production-ready, fully automated

**Future: Phase 2 (4-6 weeks)**
- Add optional Gemini Flash for enhanced summaries
- LLM-powered bias detection and context generation
- Graceful degradation: Phase 1 output always available as fallback
- Store LLM results in `analyzed_feed.llm_enhanced_summary`

When working on code, always ensure Phase 1 functionality works independently of Phase 2 LLM features.

## Quality Metrics & Monitoring

### Technical Metrics to Track
- Scraping success rate: Target >95%
- Clustering quality: Avg intra-cluster similarity >0.7
- Entity extraction accuracy: >85% (spot-check manually)
- Pipeline execution time: <30 minutes for full daily run
- Classification accuracy: >80% categories, >75% impact labels

### User Experience Metrics
- Time to insight: <5 seconds to understand day's major stories
- Reading completion: >60% of expanded cards read to end
- Retention: >40% day-7, >20% day-30

## Non-Goals & Constraints

**Never implement:**
- Ads or tracking (violates core "news as public utility" principle)
- Paywalls or premium features
- User data collection beyond basic analytics
- Engagement optimization (infinite scroll, clickbait, etc.)

**Always maintain:**
- Open source codebase (public GitHub for transparency)
- Zero-cost infrastructure (use free tiers, avoid paid services)
- Manual override capability (humans can flag errors in automated analysis)
- Source transparency (always show which outlets reported what)

## Common Pitfalls

1. **Don't hard-code source selectors in scraper code** - use `sources.yaml` configuration
2. **Don't skip fallback mechanisms** - embedding service, clustering, scraping all need fallbacks
3. **Don't assume clustering always succeeds** - validate quality and handle edge cases
4. **Don't forget deduplication** - use content hashing to avoid duplicate articles
5. **Don't make changes without testing scraping** - source HTML changes frequently
6. **Don't optimize for engagement** - optimize for clarity and user time-saving

## Testing Strategy

**Unit tests:** Individual components (scrapers, embeddings, clustering)
**Integration tests:** Full pipeline with mock data
**End-to-end tests:** GitHub Actions workflow with test sources
**Manual QA:** Review story cards for factual accuracy and UX

Run full test suite before committing changes to scraping or intelligence modules.
