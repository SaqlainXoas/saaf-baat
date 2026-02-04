# Saaf Baat: Test-Driven Development Plan

**Philosophy:** Build the foundation right. Test rigorously. Ship incrementally.

**Approach:** Backend-first, test-driven development with small, verifiable milestones. Each phase has clear goals, comprehensive tests, and commit checkpoints. We don't move forward until current phase tests pass.

---

## 🎯 MVP Scope Decisions (Important!)

These decisions define what we build NOW vs LATER:

### ✅ MVP (Phase 1) - Ship This First
1. **English-Only Content** - All NLP, entity extraction, and classification targets English news sources only
2. **Headlines + Source Attribution** - Display clustered headlines with correct source attribution (no LLM-generated summaries)
3. **Embeddings & Clustering as Core Feature** - Group related articles into stories using semantic similarity
4. **Advanced Filtering** - Category filters, impact labels, source filtering
5. **Consensus Detection** - Show confirmed facts vs debated claims based on entity agreement across sources

### 🔮 Future Enhancements (Phase 2+)
1. **Urdu Language Support** - NER models, Urdu embeddings, RTL UI support (requires dedicated NLP work)
2. **LLM-Generated Summaries** - Use Gemini Flash to synthesize human-readable story summaries from clustered articles
3. **Real-time Updates** - Multiple pipeline runs per day for breaking news

> **Rationale:** Ship a working English product first. Urdu NLP is complex (weak spaCy support, different entity patterns). LLM summaries are enhancement, not core value. The core value is **multi-source clustering with consensus detection**.

---

## Development Principles

1. **Test-Driven Development (TDD):** Write tests BEFORE implementation
2. **Backend First:** Build solid agents layer before UI
3. **Incremental Commits:** Commit after each small achievable milestone
4. **Quality Gates:** All tests must pass before moving to next phase
5. **Real Testing:** No mock-only tests—use actual data, real APIs (with fallbacks)
6. **Iterative Bug Fixing:** If tests fail, fix immediately before proceeding

---

## Current Implementation Status (As Of February 4, 2026)

This section maps the **actual repo state** to this plan (so you can see what’s done vs next).

### ✅ Completed / Implemented

- **Phase 0 (Foundation):** Implemented (`backend/pyproject.toml`, `backend/tests/*`, configs in `backend/config/*`)
- **Phase 1 (Database):** Implemented (schema + client + models)
  - Schema: `backend/src/db/schema.sql`, `backend/scripts/create_schema.py`
  - Client: `backend/src/db/client.py`
  - Models: `backend/src/db/models.py`
- **Phase 2 (Scraping):** Implemented (Hybrid stack)
  - Orchestrator: `backend/src/scrapers/hybrid_orchestrator.py`
  - Fetch: `backend/src/scrapers/network.py`
  - Parse: `backend/src/scrapers/parsers.py`
  - RSS discovery: `backend/src/scrapers/feed.py`
- **Phase 3 (Embeddings):** Implemented (Gemini only)
  - Provider: `backend/src/agents/embeddings.py`
- **Phase 4 (Clustering):** Implemented
  - Clusterers + service: `backend/src/agents/clustering.py`
- **Phase 5 (Analysis, MVP subset):** Implemented (spaCy + rules, no SetFit wiring)
  - Analysis module: `backend/src/agents/analysis.py`
  - Exported in: `backend/src/agents/__init__.py`
  - spaCy deps installed in venv: `spacy`, `en_core_web_sm`

### ⏳ Not Yet Implemented (Next Work)

- **Phase 6 (Pipeline Orchestration):** Not implemented
  - Missing glue code: scrape → embed → cluster → analyze → write `analyzed_feed`
  - Missing GitHub Actions workflow for daily run
- **Phase 7 (Frontend):** Not implemented
- **Deferred (Optional): SetFit classification**
  - SetFit training/inference is not wired in MVP implementation yet (rules-based classification is implemented).

---

## Test Status + Known Failing Areas (As Of February 4, 2026)

This is important for TDD: you should be able to run a “fast local suite” (unit tests) reliably, and run “integration/live tests” intentionally.

### ✅ Passing (Offline / Unit)

- Phase 5 unit tests (analysis layer):
  - `backend/tests/test_agents/test_analysis_entities.py`
  - `backend/tests/test_agents/test_analysis_consensus.py`
  - `backend/tests/test_agents/test_analysis_classification.py`
  - `backend/tests/test_agents/test_analysis_pipeline.py`

Recommended local command:
```bash
source backend/venv/bin/activate && pytest backend/tests -m "not integration"
```

### ⚠️ Failing When You Run The Full Suite (Mostly Integration/Live)

These failures are not “logic bugs” in the codebase — they happen when tests try to hit real external systems but DNS/network/credentials aren’t available.

Observed locally on **February 4, 2026** when running:
```bash
source backend/venv/bin/activate && pytest backend/tests
```
Result: **43 failed, 233 passed, 9 skipped** (failures dominated by network-dependent integration tests).

1. **Gemini live embedding integration tests** (network/DNS required)
   - File: `backend/tests/test_agents/test_embeddings.py`
   - Failing tests include:
     - `TestGeminiIntegration::test_real_embedding_generation`
     - `TestGeminiIntegration::test_similar_texts_high_similarity`
     - `TestGeminiIntegration::test_real_batch_embedding`
     - `TestEmbeddingPayloadValidation::*`
   - Typical error: DNS resolution / API unreachable

2. **Supabase integration tests** (Supabase reachable + valid creds required)
   - File: `backend/tests/test_db/test_integration.py`
   - If `SUPABASE_URL` / `SUPABASE_KEY` are set but Supabase isn’t reachable, tests fail.
   - If creds are **unset**, this module will skip.

3. **Live scraping tests** (real websites reachable required)
   - File: `backend/tests/test_scrapers/test_live_scraping.py`
   - These fail if the network is blocked or sites are unreachable/rate-limited.

4. **Network integration fetch tests** (httpbin/example.com reachable required)
   - File: `backend/tests/test_scrapers/test_network.py`
   - These fail if outbound HTTP is blocked.

If you want to intentionally run integration tests, run:
```bash
source backend/venv/bin/activate && pytest backend/tests -m integration
```

---

## Storage & Vector Search Guidance (MVP)

- **Pinecone?** Not required for MVP. Supabase + pgvector is enough for embedding storage and clustering.
- **Local dev option:** Use Supabase local or a lightweight local Postgres with pgvector. If you want a purely local stack, ChromaDB is fine for prototyping.
- **When to add a vector DB:** Only after scale demands it (e.g., >100k articles, cross-time semantic search, or interactive similarity search).

---

## Phase 0: Foundation & Environment Setup

**Status:** ✅ DONE (implemented in repo)

**Duration:** 1-2 days
**Goal:** Establish development environment, project structure, and testing infrastructure

### Deliverables

1. **Python Environment Setup**
   - Create and activate virtual environment in `backend/`
   - Install core dependencies: pytest, black, ruff, mypy
   - Create `requirements.txt` with pinned versions
   - Configure linting and formatting tools

2. **Project Structure**
   - Create directory tree:
     ```
     backend/
     ├── config/                  # YAML configuration files
     ├── src/
     │   ├── __init__.py
     │   ├── scrapers/
     │   │   ├── __init__.py
     │   │   ├── base.py          # Base scraper class
     │   │   └── orchestrator.py
     │   ├── agents/
     │   │   ├── __init__.py
     │   │   ├── embeddings.py
     │   │   ├── clustering.py
     │   │   └── analysis.py
     │   ├── database/
     │   │   ├── __init__.py
     │   │   ├── client.py
     │   │   └── schema.py
     │   └── utils/
     │       ├── __init__.py
     │       └── validators.py
     ├── tests/
     │   ├── __init__.py
     │   ├── conftest.py          # Pytest fixtures
     │   ├── test_scrapers/
     │   ├── test_agents/
     │   └── test_database/
     ├── main.py
     └── pytest.ini
     ```

3. **Configuration Files**
   - Create `backend/config/sources.yaml` (initially 2-3 test sources)
   - Create `backend/config/classification_rules.yaml` (basic categories)
   - Add `.env.example` for environment variables (API keys, DB URLs)

4. **Testing Infrastructure**
   - Configure pytest with coverage reporting
   - Set up fixtures for test data
   - Create helper functions for test assertions
   - Add `conftest.py` with shared fixtures

### Tests to Write BEFORE Implementation

**Test File:** `tests/test_project_structure.py`
```python
def test_directory_structure_exists():
    """Verify all required directories are created"""
    assert Path("backend/src/scrapers").exists()
    assert Path("backend/src/agents").exists()
    assert Path("backend/config").exists()

def test_config_files_exist():
    """Verify configuration files are present"""
    assert Path("backend/config/sources.yaml").exists()
    assert Path("backend/config/classification_rules.yaml").exists()

def test_python_environment():
    """Verify Python version and virtual environment"""
    import sys
    assert sys.version_info >= (3, 10)
```

**Test File:** `tests/test_utils/test_validators.py`
```python
def test_validate_article_structure():
    """Ensure article validation catches missing required fields"""
    valid_article = {
        "headline": "Test headline",
        "main_text": "Test content",
        "url": "https://example.com",
        "publish_date": "2026-02-03T10:00:00Z"
    }
    assert validate_article(valid_article) == True

    invalid_article = {"headline": "Test"}  # Missing required fields
    assert validate_article(invalid_article) == False
```

### Acceptance Criteria

- ✅ Virtual environment activated and dependencies installed
- ✅ All project directories created
- ✅ Config files present with at least 2 news sources defined
- ✅ `pytest` runs successfully (even with placeholder tests)
- ✅ Code passes `black`, `ruff`, and `mypy` checks

### Commit Checkpoints

1. `Initialize Python environment and project structure`
2. `Add configuration files and test infrastructure`

**Output:** Runnable test suite (even if tests are basic), clean project structure, linting passing

---

## Phase 1: Database Layer & Supabase Integration

**Status:** ✅ DONE (schema + client + models + tests implemented)

**Duration:** 3-4 days
**Goal:** Establish database schema, connection handling, and CRUD operations with comprehensive testing

### Deliverables

1. **Supabase Project Setup**
   - Create Supabase project (free tier)
   - Configure database URL and API keys in `.env`
   - Enable pgvector extension for embeddings

2. **Database Schema Implementation**
   - Create `backend/src/database/schema.sql` with:
     - `raw_articles` table
     - `clusters` table
     - `analyzed_feed` table
   - Add indexes for performance (url, content_hash, publish_date)
   - Add foreign key constraints

3. **Database Client**
   - Implement `SupabaseClient` class in `backend/src/database/client.py`
   - Connection pooling and retry logic
   - CRUD methods: insert_article, get_articles, update_cluster, etc.
   - Batch operations for efficiency

4. **Data Models**
   - Create Pydantic models in `backend/src/database/models.py`
   - `RawArticle`, `Cluster`, `AnalyzedFeed` classes
   - Validation and serialization logic

### Tests to Write BEFORE Implementation

**Test File:** `tests/test_database/test_schema.py`
```python
@pytest.fixture
def test_db_client():
    """Create test database client with cleanup"""
    client = SupabaseClient(test_mode=True)
    yield client
    client.cleanup_test_data()

def test_raw_articles_table_exists(test_db_client):
    """Verify raw_articles table schema"""
    schema = test_db_client.get_table_schema("raw_articles")
    required_columns = ["id", "source", "url", "headline", "main_text",
                       "publish_date", "content_hash"]
    assert all(col in schema for col in required_columns)

def test_unique_constraint_on_url(test_db_client):
    """Ensure duplicate URLs are rejected"""
    article1 = create_test_article(url="https://test.com/story1")
    article2 = create_test_article(url="https://test.com/story1")  # Same URL

    test_db_client.insert_article(article1)
    with pytest.raises(DuplicateArticleError):
        test_db_client.insert_article(article2)
```

**Test File:** `tests/test_database/test_client.py`
```python
def test_insert_and_retrieve_article(test_db_client):
    """Test basic CRUD operations"""
    article = RawArticle(
        source="dawn",
        url="https://dawn.com/test-article",
        headline="Test Headline",
        main_text="Article content here...",
        publish_date="2026-02-03T10:00:00Z"
    )

    # Insert
    article_id = test_db_client.insert_article(article)
    assert article_id is not None

    # Retrieve
    retrieved = test_db_client.get_article_by_id(article_id)
    assert retrieved.headline == "Test Headline"
    assert retrieved.source == "dawn"

def test_batch_insert_articles(test_db_client):
    """Test inserting multiple articles efficiently"""
    articles = [create_test_article(i) for i in range(50)]

    start_time = time.time()
    result = test_db_client.batch_insert_articles(articles)
    duration = time.time() - start_time

    assert len(result.inserted_ids) == 50
    assert duration < 5.0  # Should complete in under 5 seconds

def test_connection_retry_logic(test_db_client):
    """Verify client retries on connection failure"""
    with patch('supabase.create_client', side_effect=[ConnectionError, MagicMock()]):
        client = SupabaseClient()  # Should retry and succeed on 2nd attempt
        assert client.is_connected()
```

**Test File:** `tests/test_database/test_models.py`
```python
def test_raw_article_model_validation():
    """Test Pydantic model validation"""
    # Valid article
    article = RawArticle(
        source="dawn",
        url="https://dawn.com/article",
        headline="Test",
        main_text="Content",
        publish_date="2026-02-03T10:00:00Z"
    )
    assert article.source == "dawn"

    # Invalid article (missing required field)
    with pytest.raises(ValidationError):
        RawArticle(source="dawn", url="https://dawn.com")  # Missing headline

def test_content_hash_generation():
    """Ensure content hash is generated for deduplication"""
    article = RawArticle(
        source="dawn",
        url="https://dawn.com/article",
        headline="Test Headline",
        main_text="Article content",
        publish_date="2026-02-03T10:00:00Z"
    )

    assert article.content_hash is not None
    assert len(article.content_hash) == 64  # SHA-256 hash
```

### Real-World Integration Tests

**Test File:** `tests/test_database/test_integration.py`
```python
@pytest.mark.integration
def test_full_article_lifecycle(test_db_client):
    """Test complete article flow: insert -> retrieve -> update -> delete"""
    # Insert
    article = create_test_article()
    article_id = test_db_client.insert_article(article)

    # Retrieve
    retrieved = test_db_client.get_article_by_id(article_id)
    assert retrieved is not None

    # Update (e.g., add to cluster)
    test_db_client.assign_to_cluster(article_id, cluster_id="test-cluster")
    updated = test_db_client.get_article_by_id(article_id)
    assert updated.cluster_id == "test-cluster"

    # Cleanup handled by fixture

@pytest.mark.integration
def test_query_articles_by_date_range(test_db_client):
    """Test date-based filtering"""
    # Insert articles with different publish dates
    articles = [
        create_test_article(publish_date="2026-02-01T10:00:00Z"),
        create_test_article(publish_date="2026-02-03T10:00:00Z"),
        create_test_article(publish_date="2026-02-05T10:00:00Z"),
    ]
    test_db_client.batch_insert_articles(articles)

    # Query for Feb 1-3
    results = test_db_client.get_articles_in_date_range(
        start="2026-02-01", end="2026-02-03"
    )
    assert len(results) == 2
```

### Acceptance Criteria

- ✅ Supabase project created and accessible
- ✅ Database schema deployed (all 3 tables with proper constraints)
- ✅ `SupabaseClient` can insert, retrieve, update, delete articles
- ✅ Batch operations work efficiently (50 articles in <5s)
- ✅ Duplicate detection works (content_hash and URL uniqueness)
- ✅ All integration tests pass against real Supabase instance
- ✅ Connection retry logic tested and verified

### Commit Checkpoints

1. `Add database schema and migration files`
2. `Implement Supabase client with CRUD operations`
3. `Add Pydantic models with validation`
4. `Add database integration tests`

**Output:** Fully functional database layer with passing tests. Can insert/retrieve articles reliably.

---

## Phase 2: Scraping System (Hybrid Orchestrator)

**Status:** ✅ DONE (hybrid orchestrator + stealth fetch + parser ensemble + Playwright fallback)

**Duration:** 5-6 days  
**Goal:** Build a robust hybrid scraper with RSS discovery, stealth fetching, parser ensemble, and Playwright fallback.

### Deliverables

1. **Hybrid Orchestrator**
   - `HybridOrchestrator` in `src/scrapers/hybrid_orchestrator.py`
   - URL discovery: RSS first, HTML section scrape fallback
   - Centralized error handling and stats

2. **Stealth Network Layer**
   - `StealthFetcher` (curl_cffi) with retries, backoff, rate limiting
   - Realistic headers + referer

3. **Parser Ensemble**
   - `ContentParser` (trafilatura → newspaper4k → readability)
   - Merge metadata (date/author) across parsers
   - Quality checks (min text length)

4. **Playwright Fallback**
   - Headless Chromium with stealth plugin
   - Scroll to trigger lazy loading
   - Session reuse for performance

5. **Source Configuration**
   - `config/sources.yaml` with RSS feed + sections
   - Per-source enable/disable

### Tests to Write BEFORE Implementation

**Test Files (already in repo):**
- `tests/test_scrapers/test_hybrid_orchestrator.py`
- `tests/test_scrapers/test_network.py`
- `tests/test_scrapers/test_parsers.py`
- `tests/test_scrapers/test_feed.py`
- `tests/test_scrapers/test_live_scraping.py`

### Acceptance Criteria

- ✅ Scraper can extract articles from at least 3 real news sources
- ✅ RSS discovery works; HTML fallback works
- ✅ StealthFetcher bypasses common bot protection
- ✅ Playwright fallback works for JS-heavy pages
- ✅ Duplicate detection via content_hash works
- ✅ Integration test: scrape → insert into database succeeds

### Commit Checkpoints

1. `Add stealth fetcher with retry + rate limiting`
2. `Add parser ensemble with metadata merge`
3. `Add hybrid orchestrator + RSS discovery`
4. `Add Playwright fallback + stealth`
5. `Add scraping integration tests`

**Output:** Hybrid scraping system that can extract articles reliably and store them in database.

---

## Phase 3: Embedding Service (Gemini Only)

**Status:** ✅ DONE (Gemini provider + unit tests; integration tests require network)

**Duration:** 3-4 days
**Goal:** Build embedding generation service with Gemini API (no local fallback)

### Deliverables

1. **Gemini Embedding Integration**
   - `GeminiEmbeddingProvider` in `src/agents/embeddings.py`
   - Configure `task_type='CLUSTERING'` for optimal results
   - Batch processing to respect 100 RPM quota
   - API key management and error handling

2. **Embedding Service Wrapper**
   - Optional `EmbeddingService` abstraction for batch + rate limiting
   - Caching to avoid re-embedding identical text
   - Provider fixed to Gemini

4. **Embedding Pipeline**
   - Process: headline + first 500 chars of main_text
   - Normalize embeddings for cosine similarity
   - Store embeddings with metadata (provider used, timestamp)

### Tests to Write BEFORE Implementation

**Test File:** `tests/test_agents/test_gemini_embedding.py`
```python
@pytest.mark.integration
@pytest.mark.requires_api_key
def test_gemini_embedding_generation():
    """Test embedding generation with Gemini API"""
    provider = GeminiEmbeddingProvider(api_key=os.getenv("GEMINI_API_KEY"))

    texts = [
        "Rupee falls to record low against dollar",
        "Stock market crashes amid economic uncertainty"
    ]

    embeddings = provider.embed(texts, task_type="CLUSTERING")

    # Verify output shape
    assert embeddings.shape == (2, 768)  # 2 texts, 768-dim embeddings
    assert embeddings.dtype == np.float32

    # Verify embeddings are normalized
    norms = np.linalg.norm(embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=0.01)

@pytest.mark.integration
def test_gemini_batch_processing():
    """Test batching respects rate limits"""
    provider = GeminiEmbeddingProvider(api_key=os.getenv("GEMINI_API_KEY"))

    # Generate 150 embeddings (exceeds 100 RPM limit)
    texts = [f"Article {i} text content" for i in range(150)]

    start = time.time()
    embeddings = provider.embed_batch(texts, batch_size=50)
    duration = time.time() - start

    assert embeddings.shape == (150, 768)
    # Should take at least 1 minute due to rate limiting
    assert duration >= 60

def test_gemini_api_error_handling():
    """Test handling of API errors"""
    provider = GeminiEmbeddingProvider(api_key="invalid_key")

    with pytest.raises(APIKeyError):
        provider.embed(["test text"])
```

**Test File:** `tests/test_agents/test_embedding_service.py`
```python
@pytest.mark.integration
def test_embedding_service_primary_gemini():
    """Test EmbeddingService uses Gemini"""
    service = EmbeddingService()

    texts = ["Test article 1", "Test article 2"]
    result = service.embed_batch(texts)

    assert result.embeddings.shape[0] == 2
    assert result.provider_used == "gemini"

def test_embedding_caching():
    """Verify identical texts use cached embeddings"""
    service = EmbeddingService(enable_cache=True)

    text = "This is a test article about economy"

    # First call - fresh embedding
    result1 = service.embed([text])

    # Second call - should use cache
    start = time.time()
    result2 = service.embed([text])
    duration = time.time() - start

    assert np.array_equal(result1.embeddings, result2.embeddings)
    assert duration < 0.1  # Cache retrieval is very fast
```

### Acceptance Criteria

- ✅ Gemini API integration works (verified with real API call)
- ✅ Batch processing respects rate limits
- ✅ Embeddings are normalized for cosine similarity
- ✅ Caching prevents redundant API calls
- ✅ Similar texts have high cosine similarity (>0.7)
- ✅ Integration test: embed real articles from database

### Commit Checkpoints

1. `Add Gemini embedding provider with rate limiting`
2. `Implement EmbeddingService wrapper with caching`
3. `Add embedding tests and integration checks`

**Output:** Reliable Gemini embedding service that generates high-quality vectors for clustering.

---

## Phase 4: Clustering Pipeline (HDBSCAN + DBSCAN)

**Status:** ✅ DONE (clusterers + clustering service + tests implemented)

**Duration:** 4-5 days
**Goal:** Implement story clustering with quality validation and automatic fallback

### Deliverables

1. **HDBSCAN Clustering Implementation**
   - `HDBSCANClusterer` in `src/agents/clustering.py`
   - Parameter tuning: `min_cluster_size`, `min_samples`, `metric='cosine'`
   - Cluster quality metrics (cohesion, noise ratio)

2. **DBSCAN Fallback**
   - `DBSCANClusterer` as backup algorithm
   - Parameter: `eps=0.75`, `min_samples=2`
   - Same interface as HDBSCAN for seamless switching

3. **Clustering Service**
   - `ClusteringService` class that manages algorithm selection
   - Quality validation before accepting results
   - Automatic fallback: HDBSCAN → DBSCAN if quality low

4. **Cluster Analysis**
   - Calculate cluster centroids
   - Identify representative articles per cluster
   - Compute intra-cluster similarity scores
   - Detect outlier/noise articles

5. **Database Integration**
   - Store clusters in `clusters` table
   - Update `raw_articles` with cluster assignments
   - Link articles to clusters via `article_ids` array

### Tests to Write BEFORE Implementation

**Test File:** `tests/test_agents/test_hdbscan.py`
```python
def test_hdbscan_basic_clustering():
    """Test HDBSCAN clusters similar articles together"""
    # Create synthetic embeddings for 3 distinct stories
    # Story 1: 5 articles about economy
    # Story 2: 3 articles about sports
    # Story 3: 4 articles about politics

    embeddings = create_synthetic_embeddings(
        num_clusters=3,
        articles_per_cluster=[5, 3, 4]
    )

    clusterer = HDBSCANClusterer(min_cluster_size=3)
    labels = clusterer.fit_predict(embeddings)

    # Should identify 3 clusters
    unique_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    assert unique_clusters == 3

def test_hdbscan_noise_detection():
    """Verify HDBSCAN identifies outlier articles"""
    # Create embeddings: 3 clusters + 2 outliers
    embeddings = create_embeddings_with_outliers()

    clusterer = HDBSCANClusterer(min_cluster_size=3)
    labels = clusterer.fit_predict(embeddings)

    # Check noise ratio
    noise_count = np.sum(labels == -1)
    assert noise_count >= 2  # At least 2 outliers detected

def test_hdbscan_varying_densities():
    """Test clustering with varying cluster sizes"""
    # Story 1: 20 articles (major story)
    # Story 2: 3 articles (minor story)
    embeddings = create_synthetic_embeddings(
        num_clusters=2,
        articles_per_cluster=[20, 3]
    )

    clusterer = HDBSCANClusterer(min_cluster_size=3)
    labels = clusterer.fit_predict(embeddings)

    # Should handle both large and small clusters
    unique_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    assert unique_clusters == 2
```

**Test File:** `tests/test_agents/test_clustering_service.py`
```python
def test_clustering_quality_validation():
    """Test quality checks accept good clustering"""
    service = ClusteringService()

    # Good clustering: 5 clusters, low noise
    good_labels = np.array([0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4])
    assert service._is_quality_clustering(good_labels) == True

    # Bad clustering: only 1 cluster, high noise
    bad_labels = np.array([-1, -1, -1, -1, -1, 0, 0])
    assert service._is_quality_clustering(bad_labels) == False

def test_automatic_fallback_to_dbscan():
    """Verify fallback when HDBSCAN quality is low"""
    service = ClusteringService()

    # Create embeddings that HDBSCAN struggles with
    poor_embeddings = create_uniform_random_embeddings(50)

    # Mock HDBSCAN to produce poor clustering
    with patch('HDBSCANClusterer.fit_predict', return_value=np.full(50, -1)):
        labels = service.cluster(poor_embeddings)

        # Should have fallen back to DBSCAN
        assert service.algorithm_used == "dbscan"

@pytest.mark.integration
def test_cluster_real_articles():
    """Integration test: cluster real article embeddings"""
    db_client = SupabaseClient(test_mode=True)
    embedding_service = EmbeddingService()
    clustering_service = ClusteringService()

    # Get articles
    articles = db_client.get_recent_articles(limit=50)

    # Embed
    texts = [f"{a.headline} {a.main_text[:500]}" for a in articles]
    embeddings = embedding_service.embed_batch(texts).embeddings

    # Cluster
    labels = clustering_service.cluster(embeddings)

    # Validate results
    num_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    assert num_clusters >= 3  # At least 3 distinct stories
    assert num_clusters <= 15  # Not too fragmented

    noise_ratio = np.sum(labels == -1) / len(labels)
    assert noise_ratio < 0.3  # Less than 30% noise
```

**Test File:** `tests/test_agents/test_cluster_analysis.py`
```python
def test_calculate_cluster_centroid():
    """Test centroid calculation for cluster"""
    embeddings = np.array([
        [1.0, 0.0, 0.0],
        [0.9, 0.1, 0.0],
        [0.8, 0.2, 0.0]
    ])

    centroid = calculate_centroid(embeddings)

    # Should be normalized mean
    expected = np.mean(embeddings, axis=0)
    expected = expected / np.linalg.norm(expected)

    assert np.allclose(centroid, expected)

def test_find_representative_article():
    """Find article closest to cluster centroid"""
    cluster_embeddings = create_synthetic_cluster_embeddings(5)
    centroid = calculate_centroid(cluster_embeddings)

    rep_index = find_representative_article(cluster_embeddings, centroid)

    # Representative should be closest to centroid
    distances = [cosine_distance(emb, centroid) for emb in cluster_embeddings]
    assert rep_index == np.argmin(distances)

def test_intra_cluster_similarity():
    """Calculate average similarity within cluster"""
    tight_cluster = create_tight_cluster_embeddings(5)
    loose_cluster = create_loose_cluster_embeddings(5)

    tight_sim = calculate_intra_cluster_similarity(tight_cluster)
    loose_sim = calculate_intra_cluster_similarity(loose_cluster)

    assert tight_sim > loose_sim
    assert tight_sim > 0.8  # Tight cluster should have high similarity
```

**Test File:** `tests/test_agents/test_cluster_database.py`
```python
@pytest.mark.integration
def test_store_clusters_in_database():
    """Test storing clustering results in database"""
    db_client = SupabaseClient(test_mode=True)

    # Create test articles
    articles = [create_test_article(i) for i in range(10)]
    article_ids = db_client.batch_insert_articles(articles)

    # Create clusters
    cluster_assignments = {
        "cluster-1": article_ids[:4],
        "cluster-2": article_ids[4:7],
        "cluster-3": article_ids[7:]
    }

    # Store clusters
    for cluster_id, article_id_list in cluster_assignments.items():
        db_client.create_cluster(
            cluster_id=cluster_id,
            article_ids=article_id_list,
            centroid_embedding=np.random.rand(768)
        )

    # Verify storage
    retrieved_cluster = db_client.get_cluster("cluster-1")
    assert len(retrieved_cluster.article_ids) == 4

@pytest.mark.integration
def test_end_to_end_clustering_pipeline():
    """Full pipeline: scrape → embed → cluster → store"""
    db_client = SupabaseClient(test_mode=True)
    embedding_service = EmbeddingService()
    clustering_service = ClusteringService()

    # Step 1: Get articles from database
    articles = db_client.get_articles_without_clusters(limit=30)
    assert len(articles) > 0

    # Step 2: Generate embeddings
    texts = [f"{a.headline} {a.main_text[:500]}" for a in articles]
    embeddings = embedding_service.embed_batch(texts).embeddings

    # Step 3: Cluster
    labels = clustering_service.cluster(embeddings)

    # Step 4: Store results
    cluster_map = create_cluster_mapping(articles, labels, embeddings)
    for cluster_id, data in cluster_map.items():
        db_client.create_cluster(
            cluster_id=cluster_id,
            article_ids=data['article_ids'],
            centroid_embedding=data['centroid']
        )

    # Verify
    stored_clusters = db_client.get_all_clusters()
    assert len(stored_clusters) > 0
```

### Acceptance Criteria

- ✅ HDBSCAN successfully clusters synthetic test data
- ✅ DBSCAN fallback activates when quality checks fail
- ✅ Outlier/noise detection works (identifies standalone articles)
- ✅ Cluster centroids calculated correctly
- ✅ Representative articles identified per cluster
- ✅ Integration test: cluster real article embeddings
- ✅ Clustering results stored in database with proper schema
- ✅ End-to-end test: articles → embeddings → clusters → database

### Commit Checkpoints

1. `Add HDBSCAN clustering implementation`
2. `Add DBSCAN fallback algorithm`
3. `Implement ClusteringService with quality validation`
4. `Add cluster analysis functions (centroid, similarity)`
5. `Integrate clustering with database storage`
6. `Add comprehensive clustering tests`

**Output:** Working clustering pipeline that groups related articles into stories with quality validation. Can process 50+ articles and produce 5-10 meaningful clusters.

---

## Phase 5: NLP Analysis Engine (spaCy + Rules)

**Status:** ✅ DONE (analysis module + unit tests; pipeline wiring is Phase 6)

**Duration:** 5-6 days  
**Goal:** Extract entities, detect agreement across sources, and assign transparent category/impact labels (no LLM summaries).

> ⚠️ **MVP Scope: English Only** - This phase focuses on English content using the `en_core_web_sm` spaCy model.

### Deliverables (What We Build)

1. **Entity Extraction with spaCy**
   - `EntityExtractor` in `backend/src/agents/analysis.py`
   - Keep entity types: PERSON, ORG, GPE, DATE, MONEY, EVENT
   - Normalize whitespace **before** NLP so extraction is stable across sources
   - Deduplicate entities within an article (case-insensitive key, best display casing)

2. **Consensus Detection (Agreement Signal)**
   - `ConsensusDetector` in `backend/src/agents/analysis.py`
   - For a cluster of N articles:
     - entities mentioned by **all** sources → `confirmed_facts`
     - entities mentioned by **some** sources → `debated_claims`
   - Track how many sources mention each entity (`sources` count)

3. **Rule-Based Classification (MVP Classifier)**
   - `RuleBasedClassifier` in `backend/src/agents/analysis.py`
   - Loads `backend/config/classification_rules.yaml`
   - Outputs:
     - `category` (string)
     - `impact_labels` (list of strings)
     - `confidence` (simple bounded function of matched keyword counts)

4. **Analysis Service (Cluster → AnalyzedFeed Payload)**
   - `AnalysisService` in `backend/src/agents/analysis.py`
   - Input: `cluster_id` + list of `RawArticle`
   - Output: `AnalyzedFeed` instance (ready for DB insert)
   - Deterministic headline choice with a source-priority list (configurable later)

5. **Optional Later: SetFit**
   - Add SetFit only after rules-based MVP is stable, and keep rules as the baseline for transparency.

> 📝 **Note:** In MVP we do not generate any LLM summaries. Story cards display: representative headline, confirmed facts list, debated claims list, source attribution, category, and impact labels.

### Tests (TDD)

**Implemented test suite (offline + deterministic):**
- `backend/tests/test_agents/test_analysis_entities.py`
- `backend/tests/test_agents/test_analysis_consensus.py`
- `backend/tests/test_agents/test_analysis_classification.py`
- `backend/tests/test_agents/test_analysis_pipeline.py`

### Acceptance Criteria

- ✅ `en_core_web_sm` is installed and loadable via `spacy.load('en_core_web_sm')`
- ✅ Entities extracted and normalized reliably
- ✅ Consensus detector produces stable confirmed/debated lists with correct counts
- ✅ Rule-based classifier reads YAML and assigns category/impact labels
- ✅ AnalysisService builds `AnalyzedFeed` payloads deterministically
- ✅ All Phase 5 unit tests pass without network access

### Commit Checkpoints

1. `Add spaCy entity extraction (EntityExtractor)`
2. `Implement consensus detection (ConsensusDetector)`
3. `Implement rule-based classifier (RuleBasedClassifier)`
4. `Add analysis service (cluster -> AnalyzedFeed)`
5. `Add Phase 5 tests`

**Output:** A working, transparent analysis layer that turns clusters into story-card metadata.

---

## Phase 6: Full Pipeline Orchestration & GitHub Actions

**Status:** ⏳ NOT STARTED

**Duration:** 3-4 days
**Goal:** Integrate all components into automated daily pipeline with error handling and monitoring

### Deliverables

1. **Main Pipeline Script**
   - `backend/main.py` as entry point
   - Orchestrates: scraping → embedding → clustering → analysis → storage
   - Error handling at each stage
   - Logging and monitoring
   - Graceful degradation on component failures

2. **GitHub Actions Workflow**
   - `.github/workflows/daily_pipeline.yml`
   - Scheduled cron: 6:00 AM PKT daily
   - Environment setup (Python, dependencies, spaCy models)
   - Secret management (API keys, DB credentials)
   - Artifact storage for logs

3. **Error Handling & Retries**
   - Retry logic for transient failures
   - Fallback mechanisms at every layer
   - Detailed error reporting
   - Continue pipeline even if one source fails

4. **Monitoring & Alerting**
   - Pipeline success/failure notifications
   - Metrics collection (articles scraped, clusters formed, etc.)
   - Quality checks (clustering quality, classification confidence)

### Tests to Write BEFORE Implementation

**Test File:** `tests/test_pipeline/test_orchestrator.py`
```python
@pytest.mark.integration
@pytest.mark.slow
def test_full_pipeline_execution():
    """Integration test: run entire pipeline end-to-end"""
    from main import run_daily_pipeline

    result = run_daily_pipeline()

    # Verify pipeline completed
    assert result.status == "success"
    assert result.articles_scraped > 0
    assert result.clusters_formed > 0
    assert result.stories_analyzed > 0

def test_pipeline_handles_scraping_failure():
    """Test pipeline continues if one scraper fails"""
    with patch('Newspaper4kScraper.extract_article', side_effect=ScrapingError):
        result = run_daily_pipeline()

        # Should still complete using other sources
        assert result.status == "partial_success"
        assert result.errors['scraping'] > 0

def test_pipeline_logs_metrics():
    """Verify pipeline logs key metrics"""
    result = run_daily_pipeline()

    metrics = result.metrics
    assert 'articles_scraped' in metrics
    assert 'clusters_formed' in metrics
    assert 'avg_cluster_size' in metrics
    assert 'classification_confidence' in metrics
```

**Test File:** `tests/test_pipeline/test_error_handling.py`
```python
def test_retry_on_network_error():
    """Test automatic retry on network failures"""
    call_count = 0

    def mock_scrape():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise requests.exceptions.Timeout()
        return mock_article()

    with patch('scraper.fetch', side_effect=mock_scrape):
        result = scrape_with_retry(max_retries=3)

    assert result is not None
    assert call_count == 3  # Succeeded on 3rd attempt

def test_graceful_degradation():
    """Test pipeline continues with reduced functionality"""
    # Mock SetFit to fail
    with patch('SetFitClassifier.predict_category', side_effect=Exception):
        result = run_daily_pipeline()

        # Should fall back to rule-based classification
        assert result.status == "success"
        assert result.classification_method == "rule_based"
```

**Test File:** `tests/test_pipeline/test_github_actions.py`
```python
def test_github_actions_workflow_syntax():
    """Verify GitHub Actions YAML is valid"""
    import yaml

    with open('.github/workflows/daily_pipeline.yml') as f:
        workflow = yaml.safe_load(f)

    # Verify required fields
    assert 'name' in workflow
    assert 'on' in workflow
    assert 'schedule' in workflow['on']  # Cron trigger
    assert 'jobs' in workflow

def test_environment_variables_configured():
    """Ensure required env vars are defined"""
    required_vars = [
        'SUPABASE_URL',
        'SUPABASE_KEY',
        'GEMINI_API_KEY'
    ]

    # In CI environment, these should be set
    for var in required_vars:
        assert os.getenv(var) is not None, f"{var} not configured"
```

**Test File:** `tests/test_pipeline/test_monitoring.py`
```python
def test_collect_pipeline_metrics():
    """Test metrics collection during pipeline run"""
    metrics_collector = MetricsCollector()

    # Simulate pipeline stages
    metrics_collector.record('articles_scraped', 45)
    metrics_collector.record('clusters_formed', 8)
    metrics_collector.record('avg_cluster_size', 5.6)

    summary = metrics_collector.get_summary()

    assert summary['articles_scraped'] == 45
    assert summary['clusters_formed'] == 8

def test_quality_checks():
    """Test quality validation during pipeline"""
    quality_checker = QualityChecker()

    # Good quality metrics
    metrics = {
        'clustering_noise_ratio': 0.15,
        'avg_intra_cluster_similarity': 0.82,
        'classification_confidence': 0.88
    }

    assert quality_checker.validate(metrics) == True

    # Poor quality metrics
    poor_metrics = {
        'clustering_noise_ratio': 0.50,  # Too much noise
        'avg_intra_cluster_similarity': 0.40,  # Low similarity
    }

    assert quality_checker.validate(poor_metrics) == False
```

### Acceptance Criteria

- ✅ Full pipeline runs successfully from start to finish
- ✅ GitHub Actions workflow executes on schedule (test with manual trigger)
- ✅ Pipeline handles failures gracefully (tested with mocked errors)
- ✅ Fallback mechanisms activate automatically
- ✅ Metrics logged for each pipeline stage
- ✅ Quality checks validate output before storage
- ✅ Error notifications sent on critical failures
- ✅ Pipeline completes in <30 minutes

### Commit Checkpoints

1. `Add main pipeline orchestrator script`
2. `Configure GitHub Actions workflow with cron`
3. `Add error handling and retry logic`
4. `Implement metrics collection and monitoring`
5. `Add pipeline integration tests`

**Output:** Fully automated pipeline that runs daily, scrapes news, processes articles, and populates database with analyzed stories. Robust error handling ensures pipeline completes even with partial failures.

---

## Phase 7: Frontend (Next.js UI)

**Status:** ⏳ NOT STARTED

**Duration:** 6-7 days
**Goal:** Build user-facing interface with story cards, filters, and responsive design

### Deliverables

1. **Next.js Project Setup**
   - Initialize Next.js with TypeScript and App Router
   - Configure Tailwind CSS
   - Set up Supabase client for frontend
   - Create basic layout and routing

2. **Story Card Component**
   - `StoryCard.tsx` as master component
   - Display: headline, confirmed facts, debated claims, sources
   - Show impact labels with icons
   - Expandable/collapsible states
   - Responsive design (mobile-first)

3. **Feed Page**
   - Main feed view at `/feed`
   - Fetch analyzed stories from Supabase
   - Infinite scroll or pagination
   - Loading states and skeletons

4. **Filtering & Search**
   - Category filters (Economy, Politics, City, etc.)
   - Impact label filters (💳 WALLET, 🚦 COMMUTE, etc.)
   - Search by keyword
   - Sort by date/relevance

5. **Individual Story Page**
   - Detailed story view at `/story/[id]`
   - Show all source articles
   - Entity highlighting
   - Source attribution visualization

### Tests to Write BEFORE Implementation

**Test File:** `frontend/tests/components/StoryCard.test.tsx`
```typescript
import { render, screen } from '@testing-library/react';
import StoryCard from '@/components/StoryCard';

test('renders story headline', () => {
  const story = {
    headline: "Rupee falls to record low",
    category: "economy",
    confirmed_facts: [],
    debated_claims: [],
    impact_labels: []
  };

  render(<StoryCard story={story} />);

  expect(screen.getByText(/Rupee falls to record low/i)).toBeInTheDocument();
});

test('displays confirmed facts section', () => {
  const story = {
    headline: "Test Story",
    confirmed_facts: [
      { text: "Imran Khan", type: "PERSON", sources: 5 },
      { text: "Islamabad", type: "GPE", sources: 5 }
    ],
    debated_claims: []
  };

  render(<StoryCard story={story} />);

  expect(screen.getByText(/What's Certain/i)).toBeInTheDocument();
  expect(screen.getByText(/Imran Khan/i)).toBeInTheDocument();
});

test('shows impact labels with icons', () => {
  const story = {
    headline: "Test",
    impact_labels: ["💳 WALLET", "🚦 COMMUTE"]
  };

  render(<StoryCard story={story} />);

  expect(screen.getByText(/💳 WALLET/i)).toBeInTheDocument();
  expect(screen.getByText(/🚦 COMMUTE/i)).toBeInTheDocument();
});
```

**Test File:** `frontend/tests/pages/feed.test.tsx`
```typescript
test('fetches and displays stories from Supabase', async () => {
  const mockStories = [
    { id: '1', headline: 'Story 1', category: 'economy' },
    { id: '2', headline: 'Story 2', category: 'politics' }
  ];

  // Mock Supabase client
  jest.mock('@/lib/supabase', () => ({
    getAnalyzedFeed: jest.fn().mockResolvedValue(mockStories)
  }));

  render(<FeedPage />);

  // Wait for stories to load
  await waitFor(() => {
    expect(screen.getByText(/Story 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Story 2/i)).toBeInTheDocument();
  });
});

test('filters stories by category', async () => {
  render(<FeedPage />);

  // Click "Economy" filter
  fireEvent.click(screen.getByText(/Economy/i));

  // Should show only economy stories
  await waitFor(() => {
    expect(screen.queryByText(/Politics story/i)).not.toBeInTheDocument();
  });
});
```

**Test File:** `frontend/tests/integration/e2e.test.ts`
```typescript
// Playwright or Cypress test
test('user can browse and filter news', async ({ page }) => {
  await page.goto('http://localhost:3000/feed');

  // Wait for stories to load
  await page.waitForSelector('[data-testid="story-card"]');

  // Click category filter
  await page.click('text=Economy');

  // Verify filtered results
  const stories = await page.$$('[data-testid="story-card"]');
  for (const story of stories) {
    const category = await story.getAttribute('data-category');
    expect(category).toBe('economy');
  }

  // Click on a story
  await page.click('[data-testid="story-card"]:first-child');

  // Should navigate to detail page
  expect(page.url()).toMatch(/\/story\/[a-z0-9-]+/);
});
```

### Acceptance Criteria

- ✅ Frontend fetches data from Supabase successfully
- ✅ Story cards display all required information (headline, facts, sources, labels)
- ✅ Category and impact filters work correctly
- ✅ Responsive design works on mobile, tablet, desktop
- ✅ Loading states and error handling implemented
- ✅ Individual story page shows detailed view
- ✅ End-to-end test: user can browse, filter, and view stories

### Commit Checkpoints

1. `Initialize Next.js project with Tailwind and TypeScript`
2. `Add Supabase client and data fetching`
3. `Implement StoryCard component`
4. `Build feed page with filtering`
5. `Add individual story detail page`
6. `Add frontend tests and E2E tests`

**Output:** Functional, responsive web app where users can read analyzed news stories with fact/debate separation, category filters, and impact labels.

---

## Testing Strategy Summary

### Test Types Across All Phases

1. **Unit Tests**
   - Test individual functions and classes in isolation
   - Mock external dependencies
   - Fast execution (<1s per test)
   - Run on every commit

2. **Integration Tests**
   - Test component interactions
   - Use real external services (Supabase, Gemini API) in test mode
   - Slower execution (5-30s per test)
   - Run before major commits

3. **End-to-End Tests**
   - Test complete user workflows
   - Backend pipeline + frontend interaction
   - Slowest execution (1-5 minutes)
   - Run before phase completion

4. **Real-World Tests**
   - Test with actual news sources (not mocks)
   - Validate quality with manual spot-checks
   - Run weekly or on-demand

### Test Coverage Goals

- **Unit tests:** >80% code coverage
- **Integration tests:** All critical paths covered
- **E2E tests:** At least 3 major user flows

### Running Tests

```bash
# Backend tests
cd backend
pytest tests/                          # All tests
pytest tests/test_scrapers/            # Specific module
pytest -m "not slow"                   # Skip slow tests
pytest -m integration                  # Only integration tests

# Frontend tests
cd frontend
npm test                               # All tests
npm test -- StoryCard.test.tsx         # Specific test
npm run test:e2e                       # End-to-end tests
```

---

## Git Workflow & Commit Strategy

### Commit Frequency

- **After each deliverable:** Commit when a specific component is complete and tested
- **Small, atomic commits:** Each commit should represent one logical change
- **Test before commit:** All tests for that component must pass

### Commit Message Format

```
<verb> <component>: <brief description>

Examples:
- Add base scraper class with retry logic
- Implement Gemini embedding provider
- Fix entity extraction for Urdu text
- Update clustering quality thresholds
```

### Branch Strategy

- **main:** Stable, tested code only
- **develop:** Integration branch for ongoing work
- **feature/<phase-name>:** Individual phase branches

### Example Workflow

```bash
# Start Phase 2: Scraping
git checkout -b feature/scraping-system

# Work on newspaper4k scraper
    # ... write code, write tests ...
    pytest tests/test_scrapers/test_hybrid_orchestrator.py
    git add src/scrapers/hybrid_orchestrator.py tests/test_scrapers/test_hybrid_orchestrator.py
    git commit -m "Add hybrid scraper orchestrator"

# Work on Playwright scraper
    # ... write code, write tests ...
    pytest tests/test_scrapers/test_live_scraping.py
    git add src/scrapers/parsers.py tests/test_scrapers/test_live_scraping.py
    git commit -m "Add parser ensemble + live scraping tests"

# Phase complete, merge to develop
git checkout develop
git merge feature/scraping-system
git push origin develop
```

---

## Success Criteria & Phase Exit Gates

Each phase has clear exit criteria that MUST be met before moving to next phase:

### Phase 0: Foundation
- [ ] Virtual environment activated, all dependencies installed
- [ ] Project structure created and validated
- [ ] pytest runs successfully
- [ ] Linting passes (black, ruff, mypy)

### Phase 1: Database
- [ ] Supabase project accessible
- [ ] All 3 tables created with proper schema
- [ ] CRUD operations work (insert, retrieve, update, delete)
- [ ] Integration tests pass against real Supabase

### Phase 2: Scraping
- [ ] Can scrape from at least 3 real news sources
- [ ] Fallback mechanisms work (newspaper4k → news-please → Playwright)
- [ ] Duplicate detection via content_hash works
- [ ] Scraped articles stored in database
- [ ] Integration test: scrape → database succeeds

### Phase 3: Embeddings
- [ ] Gemini API integration works
- [ ] Embeddings generated for 100+ articles successfully
- [ ] Caching prevents redundant API calls

### Phase 4: Clustering
- [ ] HDBSCAN clusters synthetic test data correctly
- [ ] DBSCAN fallback works when quality is low
- [ ] Clustering results stored in database
- [ ] End-to-end test: articles → embeddings → clusters → database

### Phase 5: NLP Analysis
- [ ] Entity extraction works on English and Urdu text
- [ ] Consensus detection identifies confirmed vs debated facts
- [ ] SetFit classification achieves >80% accuracy
- [ ] Analyzed stories stored in analyzed_feed table

### Phase 6: Pipeline
- [ ] Full pipeline runs end-to-end successfully
- [ ] GitHub Actions workflow executes (manual trigger test)
- [ ] Error handling prevents pipeline crashes
- [ ] Metrics logged for monitoring

### Phase 7: Frontend
- [ ] Next.js app fetches data from Supabase
- [ ] Story cards display correctly
- [ ] Filters work (category, impact labels)
- [ ] E2E test: user can browse and view stories

---

## Risk Mitigation

### Technical Risks

| Risk | Mitigation |
|------|-----------|
| Scraping failures due to site changes | Multi-tier approach with 3 fallback methods; automated alerts |
| Gemini API quota exceeded | Automatic fallback to local embeddings; batch processing |
| Poor clustering quality | Quality validation with DBSCAN fallback; manual review dashboard |
| Database limits (Supabase free tier) | Monitor usage; optimize queries; plan migration if needed |

### Process Risks

| Risk | Mitigation |
|------|-----------|
| Tests become stale or ignored | Run tests on every commit; CI/CD integration |
| Scope creep | Strict phase boundaries; defer non-essential features |
| Losing work due to bugs | Small, frequent commits; test before moving forward |

---

## Timeline & Milestones

| Phase | Duration | Cumulative | Milestone |
|-------|----------|------------|-----------|
| Phase 0 | 1-2 days | Week 1 | Development environment ready |
| Phase 1 | 3-4 days | Week 1 | Database operational |
| Phase 2 | 5-6 days | Week 2 | Scraping system working |
| Phase 3 | 3-4 days | Week 3 | Embeddings generated |
| Phase 4 | 4-5 days | Week 3-4 | Clustering pipeline complete |
| Phase 5 | 5-6 days | Week 4-5 | NLP analysis engine ready |
| Phase 6 | 3-4 days | Week 5-6 | Automated pipeline deployed |
| Phase 7 | 6-7 days | Week 6-7 | Frontend launched |

**Total Estimated Duration:** 6-7 weeks (matching PRD Phase 1 timeline of 8-10 weeks with buffer)

---

## Phase Transition Checklist

Before moving to next phase, verify:

- [ ] All tests for current phase pass
- [ ] Code reviewed and linted (black, ruff)
- [ ] Integration tests completed
- [ ] Changes committed to git
- [ ] Documentation updated (if needed)
- [ ] Exit criteria met (see Success Criteria section)

---

## Final Output: What We're Building

### MVP (This Plan)

After completing all phases, we will have:

1. **Robust Backend:**
   - Scrapes 5+ Pakistani **English** news sources daily
   - Generates embeddings with Gemini + local fallback
   - **Clusters articles into stories** (core feature)
   - Extracts entities and detects consensus
   - Classifies categories and assigns impact labels
   - Stores analyzed data in Supabase

2. **Automated Pipeline:**
   - Runs daily at 6am PKT via GitHub Actions
   - Handles failures gracefully with fallbacks
   - Logs metrics and monitors quality
   - Completes in <30 minutes

3. **User-Facing Frontend:**
   - Clean, responsive Next.js interface
   - **Story cards with headlines + source attribution**
   - Confirmed facts vs debated claims display
   - Category and impact filters
   - Mobile-first design
   - Fast loading (<5s to first content)

4. **Quality Assurance:**
   - Comprehensive test suite (80%+ coverage)
   - Integration tests for all critical paths
   - E2E tests for user workflows
   - CI/CD with automated testing

### Future Enhancements (Post-MVP)

| Feature | Description | Why Later? |
|---------|-------------|------------|
| **Urdu Support** | Urdu NER, embeddings, RTL UI | Requires dedicated NLP models and testing |
| **LLM Summaries** | Gemini Flash to generate readable story summaries | Enhancement, not core value |
| **Real-time Updates** | Multiple pipeline runs per day | Adds complexity; daily is sufficient for MVP |
| **Personalization** | User preferences, saved stories | Requires user accounts |

---

## Getting Started

**First Steps:**
1. Review this plan thoroughly
2. Set up development environment (Phase 0)
3. Create Supabase project and get credentials
4. Obtain Gemini API key (free tier)
5. Begin Phase 0 implementation

**Daily Workflow:**
1. Review current phase goals and deliverables
2. Write tests FIRST (TDD approach)
3. Implement functionality to pass tests
4. Run tests to verify
5. Commit when tests pass
6. Move to next deliverable

**Remember:**
- Test-driven development is non-negotiable
- Small, frequent commits preserve progress
- Fix bugs immediately before moving forward
- Quality over speed - build it right the first time

---

**This plan is our roadmap. Let's build Saaf Baat the right way.**
