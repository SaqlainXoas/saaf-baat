# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Saaf Baat** is a minimalist news intelligence platform for Pakistan that synthesizes multi-source news coverage into clear, factual summaries. It's a 100% free, open-source public utility with zero ads, zero tracking, and zero paywalls.

**Core Philosophy:** "Open once in morning. Know what matters. Close app. Get on with life."

**Key Principle:** News as a public utility, not a business. We prioritize clarity over engagement, facts over clicks.

## Repository Structure

```
saaf-baat/
├── .github/
│   └── copilot-instructions.md      # GitHub Copilot guidance
├── backend/                         # Python intelligence engine
│   ├── config/                      # YAML configuration files
│   │   ├── sources.yaml             # News source definitions (Dawn, Tribune, Geo)
│   │   └── classification_rules.yaml # Keyword-based category + impact rules
│   ├── scripts/                     # Database setup utilities
│   │   ├── create_schema.py         # Local schema creation via SQLAlchemy
│   │   └── run_schema.py            # Prints schema SQL for Supabase dashboard
│   ├── src/
│   │   ├── scrapers/                # Web scraping layer
│   │   │   ├── dtos.py              # ScrapedArticle data class
│   │   │   ├── network.py           # StealthFetcher (curl_cffi, anti-bot bypass)
│   │   │   ├── parsers.py           # ContentParser ensemble (trafilatura → newspaper4k → readability)
│   │   │   ├── feed.py              # FeedDiscoverer (RSS/Atom URL discovery)
│   │   │   └── hybrid_orchestrator.py # Three-tier scrape orchestrator
│   │   ├── agents/                  # ML pipeline layer
│   │   │   ├── embeddings.py        # GeminiEmbeddingProvider (text-embedding-004)
│   │   │   ├── clustering.py        # HDBSCAN + DBSCAN with quality checks
│   │   │   └── analysis.py          # Entity extraction, consensus, classification
│   │   ├── db/                      # Database layer
│   │   │   ├── client.py            # SupabaseClient (CRUD, retry, batch ops)
│   │   │   ├── models.py            # Pydantic models (RawArticle, Cluster, AnalyzedFeed)
│   │   │   └── schema.sql           # PostgreSQL schema with pgvector
│   │   └── utils/
│   │       └── validators.py        # Config + article structure validation
│   ├── tests/                       # 21 test files across 4 directories
│   │   ├── conftest.py              # Shared pytest fixtures
│   │   ├── test_agents/             # Embeddings, clustering, analysis tests
│   │   ├── test_db/                 # Client, models, schema, integration tests
│   │   ├── test_scrapers/           # DTOs, network, parsers, feed, orchestrator tests
│   │   └── test_utils/              # Validator tests
│   ├── pyproject.toml               # Black, ruff, mypy configuration
│   ├── pytest.ini                   # Pytest settings (markers, coverage)
│   └── requirements.txt             # Python dependencies
├── frontend/                        # Next.js UI (not yet implemented)
├── plan.md                          # TDD development plan
├── saaf-baat-prd-final.md          # Product requirements document
└── CLAUDE.md                        # This file
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

**Run individual components:**
```bash
# Scraping only
python -m src.scrapers.hybrid_orchestrator

# Clustering only (requires existing articles in DB)
python -m src.agents.clustering

# Analysis only
python -m src.agents.analysis
```

**Run tests:**
```bash
pytest tests/
pytest tests/test_scrapers/test_parsers.py -v  # Specific test file
pytest -k "test_hdbscan"                       # Specific test pattern
pytest -m unit                                 # Run only unit-marked tests
```

**Lint and format:**
```bash
black src/
ruff check src/
mypy src/
```

### Frontend (Next.js)

> **Status:** Not yet implemented. The `frontend/` directory is a placeholder.

Frontend development commands will be added once the Next.js scaffold is in place.

## High-Level Architecture

### Data Pipeline Flow

1. **Scraping** (`HybridOrchestrator` in `src/scrapers/hybrid_orchestrator.py`)
   - **URL discovery:** FeedDiscoverer (RSS/Atom) → HTML scrape + regex fallback
   - **Content fetch:** StealthFetcher (curl_cffi, Chrome-fingerprint bypass) → Playwright (session-reused fallback)
   - **Content parse:** ContentParser ensemble — trafilatura (primary) → newspaper4k (metadata fill) → readability-lxml (safety net)
   - Sources defined in `backend/config/sources.yaml` (Dawn, Tribune, Geo)
   - Writes `RawArticle` objects to `raw_articles` table in Supabase

2. **Embedding Generation** (`GeminiEmbeddingProvider` in `src/agents/embeddings.py`)
   - Primary: Google Gemini `text-embedding-004` API (task_type='CLUSTERING', 768-dim)
   - Embeddings are L2-normalized for cosine similarity
   - Batch processing with configurable rate-limit delays
   - Raises `RateLimitError` on resource-exhausted responses (caller can retry or fall back to local model)

3. **Story Clustering** (`ClusteringService` in `src/agents/clustering.py`)
   - Primary: HDBSCAN (handles varying densities, auto-determines cluster count)
   - Fallback: DBSCAN (eps=0.3 cosine distance, i.e. similarity > 0.7)
   - Quality checks: min 3 clusters, noise ratio < 30%, avg intra-cluster similarity > 0.7
   - Auto-fallback to DBSCAN when quality checks fail
   - Helpers: `calculate_centroid`, `find_representative_article`, `calculate_intra_cluster_similarity`

4. **NLP Analysis & Classification** (`AnalysisService` in `src/agents/analysis.py`)
   - **Entity extraction:** spaCy `en_core_web_sm` — extracts PERSON, ORG, GPE, DATE, MONEY, EVENT; deduplicates case-insensitively
   - **Consensus detection:** Entities in ALL sources → confirmed facts; entities in SOME → debated claims
   - **Category classification:** `RuleBasedClassifier` — keyword matching driven by `classification_rules.yaml` (5 categories, 6 impact labels)
   - **Impact labeling:** 💳 WALLET, 🚦 COMMUTE, 🛡️ SAFETY, 🏢 WORK, ⚡ UTILITIES, 🏛️ GOVERNANCE
   - Config limits: max 2 categories and max 3 impact labels per article; min confidence 0.6

5. **Frontend Display** (not yet implemented)
   - Designed to fetch from Supabase `analyzed_feed` table via Next.js
   - Story cards will show: headline, summary, confirmed facts, debated claims, source attribution, impact badges

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
- Rich entity types available; `EntityExtractor` currently uses PERSON, ORG, GPE, DATE, MONEY, EVENT (configurable via `allowed_labels`)
- Context-aware dependency parsing
- Industry standard for NLP pipelines

**Why SetFit for classification (Phase 2)?**
- Few-shot learning (8 examples per class vs thousands)
- 67x faster than BART-large-mnli
- Phase 1 uses `RuleBasedClassifier` (keyword matching); SetFit will supplement it in Phase 2 for higher accuracy

**Why GitHub Actions?**
- Zero cost (2,000 min/month free for private, unlimited for public)
- 2-core CPU, 7GB RAM sufficient for ML workload
- Built-in cron scheduling
- Code and pipeline versioned together

## Database Schema (Supabase PostgreSQL)

Schema lives in `backend/src/db/schema.sql`. Requires the `pgvector` extension. Apply via Supabase SQL editor (see `scripts/run_schema.py`).

### `raw_articles`
Stores scraped articles before processing.
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
source          VARCHAR(100) NOT NULL           -- e.g., "dawn", "tribune", "geo"
url             TEXT NOT NULL UNIQUE
headline        TEXT NOT NULL
main_text       TEXT NOT NULL                   -- CHECK length > 50
author          VARCHAR(255)
publish_date    TIMESTAMPTZ
scraped_at      TIMESTAMPTZ DEFAULT NOW()
content_hash    VARCHAR(64) NOT NULL UNIQUE     -- SHA-256 for deduplication (exactly 64 chars)
cluster_id      UUID                            -- FK → clusters (SET NULL on delete)
embedding       VECTOR(768)                     -- pgvector; set after embedding generation
metadata        JSONB DEFAULT '{}'
```

### `clusters`
Groups related articles into unified stories.
```sql
id                       UUID PRIMARY KEY DEFAULT gen_random_uuid()
created_at               TIMESTAMPTZ DEFAULT NOW()
updated_at               TIMESTAMPTZ DEFAULT NOW()     -- auto-updated by trigger
article_ids              UUID[] NOT NULL DEFAULT '{}'
centroid_embedding       VECTOR(768)
representative_article_id UUID                          -- most central article in cluster
cluster_size             INTEGER DEFAULT 0             -- auto-set by trigger from article_ids length
avg_similarity           FLOAT                         -- CHECK 0–1 or NULL
algorithm_used           VARCHAR(50) DEFAULT 'hdbscan'
metadata                 JSONB DEFAULT '{}'
```

### `analyzed_feed`
Final processed stories for frontend display.
```sql
id                        UUID PRIMARY KEY DEFAULT gen_random_uuid()
cluster_id                UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE
created_at                TIMESTAMPTZ DEFAULT NOW()
headline                  TEXT NOT NULL
summary                   TEXT
category                  VARCHAR(50) NOT NULL          -- CHECK: economy | politics | city | education | health | sports | technology | entertainment | security | international | other
confirmed_facts           JSONB DEFAULT '[]'            -- Entities present in ALL sources
debated_claims            JSONB DEFAULT '[]'            -- Entities present in SOME sources
impact_labels             TEXT[] DEFAULT '{}'           -- [💳 WALLET, 🚦 COMMUTE, …]
source_attribution        JSONB DEFAULT '{}'            -- Which outlets reported what
entity_counts             JSONB DEFAULT '{}'
classification_confidence FLOAT                         -- CHECK 0–1 or NULL
is_published              BOOLEAN DEFAULT TRUE
metadata                  JSONB DEFAULT '{}'
```

**RLS policies** (commented out in schema, enable when frontend uses the anon key): read-only SELECT on `analyzed_feed` WHERE `is_published = TRUE`.

## Configuration Files

### `backend/config/sources.yaml`
Defines active news sources. Each entry specifies a base URL, an optional RSS `feed_url` for discovery, and which sections to scrape. `HybridOrchestrator` reads this at runtime.
```yaml
sources:
  dawn:
    url: "https://www.dawn.com"
    feed_url: "https://www.dawn.com/feeds/latest-news"
    sections: ["latest-news", "pakistan", "business"]
    enabled: true

  tribune:
    url: "https://tribune.com.pk"
    feed_url: "https://tribune.com.pk/rss.xml"
    sections: ["latest", "pakistan", "business"]
    enabled: true

  geo:
    url: "https://www.geo.tv"
    feed_url: "https://www.geo.tv/rss"
    sections: ["latest-news", "pakistan"]
    enabled: true

scraping_config:
  max_articles_per_source: 50
```

### `backend/config/classification_rules.yaml`
Keyword-based classification consumed by `RuleBasedClassifier`. Each category and impact label has a keyword list and a weight. Tuning keywords here requires no code changes.

**Categories:** economy, politics, city, security, international
**Impact labels:** 💳 WALLET, 🚦 COMMUTE, 🛡️ SAFETY, 🏢 WORK, ⚡ UTILITIES, 🏛️ GOVERNANCE

**Classification config thresholds:**
- `min_confidence: 0.6`
- `max_categories_per_article: 2`
- `max_impact_labels_per_article: 3`

## Important Implementation Notes

### Multi-Tier Scraping Strategy
`HybridOrchestrator` runs three tiers automatically for every source:

1. **URL Discovery:** `FeedDiscoverer` pulls article URLs from RSS/Atom feeds; falls back to scraping the section pages and extracting URLs via regex patterns (date-based `/2024/01/01/`, numeric `/news/123`, etc.)
2. **Content Fetch:** `StealthFetcher` (curl_cffi with Chrome-110 fingerprint) is tried first; on failure, Playwright with session reuse is the fallback.
3. **Content Parse:** `ContentParser` runs a "smart waterfall" — trafilatura extracts text, newspaper4k fills in missing author/date metadata, readability-lxml is the last resort for badly structured HTML.

When adding a new source, just add an entry to `sources.yaml`. The orchestrator handles everything else. No per-source code changes needed for standard sites.

### Embedding Pattern
`GeminiEmbeddingProvider` is the embedding entry point:
```python
provider = GeminiEmbeddingProvider()          # reads GEMINI_API_KEY from env
result   = provider.embed_batch(texts)        # returns EmbeddingResult (L2-normalized)
print(result.dimension)                       # 768
```
If Gemini returns a rate-limit error, it raises `RateLimitError` — the caller should catch this and fall back to a local sentence-transformers model. Never call the Gemini API directly.

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
1. Add an entry to `backend/config/sources.yaml` with `url`, `feed_url` (if available), `sections`, and `enabled: true`
2. `HybridOrchestrator` will automatically attempt RSS discovery → HTML scrape → Playwright fallback — no code changes needed for standard sites
3. Test locally by importing and calling `HybridOrchestrator.scrape_source(...)` in a script
4. If the site requires non-standard parsing, extend `ContentParser` logic in `src/scrapers/parsers.py`

### Modifying Classification Logic
1. **Keyword tuning:** Edit `classification_rules.yaml` directly — no code changes needed. `RuleBasedClassifier` reloads the file.
2. **Adding a new category:** Add an entry under `categories:` with a `keywords` list and `weight: 1.0`; add the category string to the `valid_category` CHECK constraint in `schema.sql`
3. **SetFit** is planned for Phase 2 as a higher-accuracy supplement; Phase 1 uses rules only

### Debugging Pipeline Failures
1. Check GitHub Actions logs for error stage
2. Run problematic component locally with `--debug` flag
3. For scraping failures: Check if source HTML structure changed
4. For clustering issues: Inspect embedding quality and cluster metrics
5. Use Supabase dashboard to query intermediate tables

## Phase 1 vs Phase 2

**Current: Phase 1 — Core ML pipeline (in progress)**
- Scraping layer: complete (`HybridOrchestrator`, `StealthFetcher`, `ContentParser`, `FeedDiscoverer`)
- Database layer: complete (`SupabaseClient`, Pydantic models, schema with pgvector)
- Embedding layer: complete (`GeminiEmbeddingProvider` with `RateLimitError` for caller-side fallback)
- Clustering layer: complete (`HDBSCANClusterer` + `DBSCANClusterer` + `ClusteringService` with quality checks)
- Analysis layer: complete (`EntityExtractor`, `ConsensusDetector`, `RuleBasedClassifier`, `AnalysisService`)
- Pipeline orchestration (`main.py`) and GitHub Actions workflows: **not yet wired**
- Frontend: **not yet implemented**

**Future: Phase 2**
- Add optional Gemini Flash for `analyzed_feed.summary` generation
- LLM-powered bias detection and context enrichment
- Graceful degradation: Phase 1 output always available as fallback

Always ensure Phase 1 functionality works independently of any Phase 2 LLM features.

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

Tests live in `backend/tests/` (21 files). Use the markers defined in `pytest.ini`:

| Marker | Scope | Example |
|--------|-------|---------|
| `unit` | Single class/function, fully mocked | `test_agents/test_analysis_entities.py` |
| `integration` | Real Supabase connection | `test_db/test_integration.py` |
| `slow` | Network or heavy-compute tests | `test_scrapers/test_live_scraping.py` |

```bash
pytest tests/              # All tests
pytest -m unit             # Unit tests only (fast, no network)
pytest -m "not slow"       # Skip slow/live tests
pytest --cov=src           # With coverage report
```

Run the full test suite before committing changes to scraping or intelligence modules.
