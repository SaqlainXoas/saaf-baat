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

## Phase 0: Foundation & Environment Setup

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

## Phase 2: Scraping System (Multi-Tier Architecture)

**Duration:** 5-6 days
**Goal:** Build robust multi-tier scraping system with newspaper4k, news-please, and Playwright fallbacks

### Deliverables

1. **Base Scraper Architecture**
   - Abstract `BaseScraper` class in `src/scrapers/base.py`
   - Common methods: `fetch_page`, `extract_article`, `validate_content`
   - Error handling and retry logic
   - Rate limiting and user-agent rotation

2. **Newspaper4k Integration**
   - `Newspaper4kScraper` class extending `BaseScraper`
   - Configure for Pakistani news sources (Dawn, Tribune, Express Tribune)
   - Extract: headline, body, author, publish_date, images
   - Handle encoding issues (Urdu/English mixed content)

3. **News-Please Fallback**
   - `NewsPleaseScaper` as secondary method
   - Activate when newspaper4k fails or returns incomplete data
   - Same interface as Newspaper4kScraper for interchangeability

4. **Playwright for Dynamic Content**
   - `PlaywrightScraper` for JavaScript-heavy sites (Geo News, forums)
   - Implement scroll behavior for lazy-loaded content
   - Screenshot capability for debugging
   - Headless mode with configurable browser settings

5. **Source Configuration System**
   - Load sources from `config/sources.yaml`
   - Source-specific selectors and scraping strategies
   - Rate limit and retry configurations per source

6. **Orchestrator**
   - `ScraperOrchestrator` in `src/scrapers/orchestrator.py`
   - Parallel scraping with asyncio
   - Automatic method selection (newspaper4k -> news-please -> playwright)
   - Centralized error handling and logging

### Tests to Write BEFORE Implementation

**Test File:** `tests/test_scrapers/test_base_scraper.py`
```python
def test_base_scraper_rate_limiting():
    """Ensure scraper respects rate limits"""
    scraper = BaseScraper(rate_limit=1.0)  # 1 second between requests

    start = time.time()
    scraper.fetch_page("https://example.com/page1")
    scraper.fetch_page("https://example.com/page2")
    duration = time.time() - start

    assert duration >= 1.0  # Should wait at least 1 second

def test_retry_logic_on_timeout():
    """Test automatic retry on network failures"""
    scraper = BaseScraper(max_retries=3)

    with patch('requests.get', side_effect=[Timeout, Timeout, MagicMock()]):
        response = scraper.fetch_page("https://example.com")
        assert response is not None  # Succeeded on 3rd attempt

def test_user_agent_rotation():
    """Verify user agent is rotated to avoid blocking"""
    scraper = BaseScraper()

    ua1 = scraper._get_user_agent()
    ua2 = scraper._get_user_agent()
    ua3 = scraper._get_user_agent()

    # Should cycle through different user agents
    assert len({ua1, ua2, ua3}) > 1
```

**Test File:** `tests/test_scrapers/test_newspaper4k.py`
```python
@pytest.mark.integration
def test_scrape_dawn_article():
    """Test scraping real article from Dawn News"""
    scraper = Newspaper4kScraper(source="dawn")

    # Use a stable, archived article URL for testing
    article_url = "https://www.dawn.com/news/1234567"  # Replace with actual stable URL
    article = scraper.extract_article(article_url)

    # Verify extracted data
    assert article.headline is not None
    assert len(article.headline) > 10
    assert article.main_text is not None
    assert len(article.main_text) > 100
    assert article.url == article_url
    assert article.source == "dawn"
    assert article.publish_date is not None

@pytest.mark.integration
def test_handle_invalid_url():
    """Test graceful handling of invalid URLs"""
    scraper = Newspaper4kScraper(source="dawn")

    with pytest.raises(InvalidURLError):
        scraper.extract_article("https://invalid-url-that-does-not-exist.com")

def test_extract_urdu_content():
    """Verify Urdu text extraction works correctly"""
    scraper = Newspaper4kScraper(source="express_tribune")

    # Mock response with Urdu content
    urdu_html = """
    <article>
        <h1>یہ ایک ٹیسٹ عنوان ہے</h1>
        <p>یہ اردو مضمون ہے۔</p>
    </article>
    """

    with patch_html_response(urdu_html):
        article = scraper.extract_article("https://test.com/urdu-article")
        assert "یہ" in article.headline  # Urdu character present
        assert article.main_text is not None
```

**Test File:** `tests/test_scrapers/test_playwright.py`
```python
@pytest.mark.slow
@pytest.mark.integration
def test_scrape_javascript_heavy_site():
    """Test Playwright scraping of JS-rendered content"""
    scraper = PlaywrightScraper(source="geo_news")

    article_url = "https://www.geo.tv/latest/123456"  # Stable test URL
    article = scraper.extract_article(article_url)

    assert article.headline is not None
    assert article.main_text is not None
    # Playwright should wait for JS to load
    assert len(article.main_text) > 200

def test_lazy_loading_scroll_behavior():
    """Verify scraper scrolls to trigger lazy-loaded content"""
    scraper = PlaywrightScraper(scroll_depth=3)

    with patch_playwright_page() as mock_page:
        scraper.extract_article("https://test.com")

        # Verify scroll actions were performed
        assert mock_page.evaluate.call_count >= 3  # Scrolled 3 times
```

**Test File:** `tests/test_scrapers/test_orchestrator.py`
```python
@pytest.mark.integration
def test_orchestrator_parallel_scraping():
    """Test scraping multiple sources in parallel"""
    sources = ["dawn", "tribune", "express_tribune"]
    orchestrator = ScraperOrchestrator(sources=sources)

    start = time.time()
    results = orchestrator.scrape_all_sources()
    duration = time.time() - start

    # Parallel execution should be faster than sequential
    assert duration < (len(sources) * 5)  # Should not take 5s per source
    assert len(results) > 0  # Got at least some articles

def test_automatic_fallback_mechanism():
    """Verify orchestrator falls back to alternative scrapers"""
    orchestrator = ScraperOrchestrator()

    # Mock newspaper4k to fail, news-please to succeed
    with patch('Newspaper4kScraper.extract_article', side_effect=ScrapingError):
        with patch('NewsPleaseScaper.extract_article', return_value=mock_article()):
            article = orchestrator.scrape_url("https://test.com/article")

            assert article is not None  # Fallback worked

@pytest.mark.integration
def test_deduplicate_across_sources():
    """Ensure orchestrator detects duplicate articles from different sources"""
    orchestrator = ScraperOrchestrator()

    # Same story from Dawn and Tribune
    results = orchestrator.scrape_all_sources()

    # Check for duplicates using content_hash
    hashes = [article.content_hash for article in results]
    assert len(hashes) == len(set(hashes))  # No duplicate hashes
```

**Test File:** `tests/test_scrapers/test_config.py`
```python
def test_load_sources_from_yaml():
    """Verify source configuration loading"""
    config = load_scraper_config("config/sources.yaml")

    assert "dawn" in config["sources"]
    assert config["sources"]["dawn"]["method"] == "newspaper4k"
    assert "url" in config["sources"]["dawn"]

def test_validate_source_config():
    """Test config validation catches missing required fields"""
    invalid_config = {
        "sources": {
            "test_source": {
                # Missing 'method' and 'url'
                "sections": ["news"]
            }
        }
    }

    with pytest.raises(ConfigValidationError):
        validate_scraper_config(invalid_config)
```

### Real-World Scraping Tests

**Test File:** `tests/test_scrapers/test_real_sources.py`
```python
@pytest.mark.integration
@pytest.mark.slow
def test_scrape_all_configured_sources():
    """Integration test: scrape all sources defined in config"""
    orchestrator = ScraperOrchestrator()
    results = orchestrator.scrape_all_sources()

    # Should get articles from at least 80% of sources
    success_rate = len(results) / orchestrator.total_sources
    assert success_rate > 0.8

    # Validate article structure
    for article in results:
        assert validate_article(article) == True

@pytest.mark.integration
def test_scraping_with_database_insertion():
    """End-to-end test: scrape and insert into database"""
    orchestrator = ScraperOrchestrator()
    db_client = SupabaseClient(test_mode=True)

    articles = orchestrator.scrape_all_sources()
    inserted_ids = db_client.batch_insert_articles(articles)

    assert len(inserted_ids) > 0
    assert len(inserted_ids) == len(articles)
```

### Acceptance Criteria

- ✅ Scraper can extract articles from at least 3 real news sources
- ✅ newspaper4k, news-please, and Playwright all working independently
- ✅ Automatic fallback works (newspaper4k fails → news-please activates)
- ✅ Rate limiting prevents overwhelming news sites
- ✅ Duplicate detection via content_hash works
- ✅ Parallel scraping completes faster than sequential
- ✅ Urdu content extraction works correctly
- ✅ All scraped articles pass validation
- ✅ Integration test: scrape → insert into database succeeds

### Commit Checkpoints

1. `Add base scraper class with retry and rate limiting`
2. `Implement newspaper4k scraper for static sites`
3. `Add news-please fallback scraper`
4. `Implement Playwright scraper for dynamic content`
5. `Add scraper orchestrator with parallel execution`
6. `Add source configuration loading and validation`
7. `Add comprehensive scraping tests`

**Output:** Robust scraping system that can extract articles from 5+ Pakistani news sources, handle failures gracefully, and store results in database.

---

## Phase 3: Embedding Service (Gemini + Local Fallback)

**Duration:** 3-4 days
**Goal:** Build embedding generation service with primary Gemini API and automatic local fallback

### Deliverables

1. **Gemini Embedding Integration**
   - `GeminiEmbeddingProvider` in `src/agents/embeddings.py`
   - Configure `task_type='CLUSTERING'` for optimal results
   - Batch processing to respect 100 RPM quota
   - API key management and error handling

2. **Local Fallback (sentence-transformers)**
   - `LocalEmbeddingProvider` using `all-MiniLM-L6-v2`
   - Runs entirely offline, no external dependencies
   - Same interface as GeminiEmbeddingProvider

3. **Unified EmbeddingService**
   - `EmbeddingService` class that abstracts provider selection
   - Automatic fallback: Gemini → Local on API failure
   - Caching layer to avoid re-embedding identical text
   - Batch optimization for efficiency

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

**Test File:** `tests/test_agents/test_local_embedding.py`
```python
def test_local_embedding_generation():
    """Test local sentence-transformers embedding"""
    provider = LocalEmbeddingProvider(model="all-MiniLM-L6-v2")

    texts = [
        "Prime minister announces new economic policy",
        "Cricket team wins against rivals"
    ]

    embeddings = provider.embed(texts)

    assert embeddings.shape == (2, 384)  # MiniLM outputs 384-dim
    assert embeddings.dtype == np.float32

def test_local_embedding_similarity():
    """Verify similar texts have higher cosine similarity"""
    provider = LocalEmbeddingProvider()

    text1 = "Inflation rises to 30 percent in Pakistan"
    text2 = "Pakistan's inflation rate reaches 30 percent"
    text3 = "Cricket match postponed due to rain"

    embeddings = provider.embed([text1, text2, text3])

    # Calculate cosine similarity
    sim_1_2 = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    sim_1_3 = cosine_similarity([embeddings[0]], [embeddings[2]])[0][0]

    # Text1 and Text2 are about same topic, should be more similar
    assert sim_1_2 > sim_1_3
    assert sim_1_2 > 0.7  # High similarity threshold

def test_local_embedding_runs_offline():
    """Ensure local embedding works without internet"""
    provider = LocalEmbeddingProvider()

    # Disable network access
    with patch('socket.socket', side_effect=OSError("Network disabled")):
        embeddings = provider.embed(["test text"])
        assert embeddings is not None  # Should still work offline
```

**Test File:** `tests/test_agents/test_embedding_service.py`
```python
@pytest.mark.integration
def test_embedding_service_primary_gemini():
    """Test EmbeddingService uses Gemini when available"""
    service = EmbeddingService()

    texts = ["Test article 1", "Test article 2"]
    result = service.embed_batch(texts)

    assert result.embeddings.shape[0] == 2
    assert result.provider_used == "gemini"

def test_embedding_service_fallback_to_local():
    """Test automatic fallback to local when Gemini fails"""
    service = EmbeddingService()

    # Mock Gemini to fail
    with patch('GeminiEmbeddingProvider.embed', side_effect=APIError):
        texts = ["Test article"]
        result = service.embed_batch(texts)

        assert result.embeddings is not None
        assert result.provider_used == "local"

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

@pytest.mark.integration
def test_embedding_real_articles():
    """Integration test: embed real scraped articles"""
    db_client = SupabaseClient(test_mode=True)
    embedding_service = EmbeddingService()

    # Get articles from database
    articles = db_client.get_articles_without_embeddings(limit=10)

    # Generate text for embedding
    texts = [f"{a.headline} {a.main_text[:500]}" for a in articles]

    # Embed
    result = embedding_service.embed_batch(texts)

    assert result.embeddings.shape[0] == len(articles)
    assert result.embeddings.shape[1] in [384, 768]  # Valid dimension
```

### Acceptance Criteria

- ✅ Gemini API integration works (verified with real API call)
- ✅ Local sentence-transformers embedding works offline
- ✅ Automatic fallback activates when Gemini fails
- ✅ Batch processing respects rate limits
- ✅ Embeddings are normalized for cosine similarity
- ✅ Caching prevents redundant API calls
- ✅ Similar texts have high cosine similarity (>0.7)
- ✅ Integration test: embed real articles from database

### Commit Checkpoints

1. `Add Gemini embedding provider with rate limiting`
2. `Add local sentence-transformers fallback`
3. `Implement unified EmbeddingService with caching`
4. `Add embedding tests and integration checks`

**Output:** Reliable embedding service that generates high-quality vectors with automatic fallback. Can embed 100+ articles efficiently.

---

## Phase 4: Clustering Pipeline (HDBSCAN + DBSCAN)

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

## Phase 5: NLP Analysis Engine (spaCy + SetFit + Rules)

**Duration:** 5-6 days
**Goal:** Extract entities, detect consensus, classify categories, and assign impact labels

> ⚠️ **MVP Scope: English Only** - This phase focuses on English content using `en_core_web_sm` spaCy model. Urdu NLP support will be added in a future phase after MVP ships.

### Deliverables

1. **Entity Extraction with spaCy**
   - `EntityExtractor` in `src/agents/analysis.py`
   - Extract: PERSON, ORG, GPE, DATE, MONEY, EVENT entities
   - **English only for MVP** (use `en_core_web_sm` model)
   - Filter and normalize entities

2. **Consensus Detection**
   - `ConsensusDetector` class
   - Set intersection: entities in ALL articles → "Confirmed Facts"
   - Symmetric difference: entities in SOME articles → "Debated Claims"
   - Count sources reporting each entity

3. **SetFit Zero-Shot Classification**
   - `SetFitClassifier` for categories and impact labels
   - Train with synthetic examples (8 per class)
   - Categories: economy, politics, city, education, health, sports, etc.
   - Impact labels: 💳 WALLET, 🚦 COMMUTE, 🛡️ SAFETY, 🏢 WORK, ⚡ UTILITIES, 🏛️ GOVERNANCE

4. **Rule-Based Classification (Backup)**
   - `RuleBasedClassifier` using keyword matching
   - Load rules from `config/classification_rules.yaml`
   - Hybrid approach: SetFit primary, rules as fallback

5. **Analysis Pipeline**
   - Process each cluster through full analysis
   - Generate analyzed story cards with all metadata
   - Store in `analyzed_feed` table

> 📝 **Note:** No LLM-generated summaries in MVP. Story cards display: representative headline, confirmed facts list, debated claims list, source attribution, and impact labels. Human-readable summaries via Gemini Flash will be added post-MVP.

### Tests to Write BEFORE Implementation

**Test File:** `tests/test_agents/test_entity_extraction.py`
```python
def test_extract_persons():
    """Test person name extraction"""
    extractor = EntityExtractor()

    text = "Prime Minister Imran Khan met with President Arif Alvi yesterday."
    entities = extractor.extract(text)

    persons = [e for e in entities if e['type'] == 'PERSON']
    assert len(persons) == 2
    assert any('Imran Khan' in p['text'] for p in persons)

def test_extract_organizations():
    """Test organization name extraction"""
    extractor = EntityExtractor()

    text = "The State Bank of Pakistan and IMF reached an agreement."
    entities = extractor.extract(text)

    orgs = [e for e in entities if e['type'] == 'ORG']
    assert len(orgs) >= 2  # SBP and IMF

def test_extract_money_amounts():
    """Test money/currency extraction"""
    extractor = EntityExtractor()

    text = "The budget increased by Rs 500 billion."
    entities = extractor.extract(text)

    money = [e for e in entities if e['type'] == 'MONEY']
    assert len(money) >= 1
    assert any('500 billion' in m['text'] or 'Rs' in m['text'] for m in money)

def test_handle_urdu_entities():
    """Test extraction from Urdu text"""
    extractor = EntityExtractor()

    text = "وزیر اعظم نے اعلان کیا"  # Prime Minister announced
    entities = extractor.extract(text)

    # Should handle Urdu text without crashing
    assert entities is not None
```

**Test File:** `tests/test_agents/test_consensus_detection.py`
```python
def test_consensus_with_matching_entities():
    """Test consensus when all articles agree"""
    detector = ConsensusDetector()

    articles = [
        "Imran Khan announced new policy on Monday in Islamabad.",
        "On Monday, Imran Khan revealed policy in Islamabad.",
        "Imran Khan's Monday policy announcement in Islamabad."
    ]

    result = detector.analyze_cluster(articles)

    # "Imran Khan", "Monday", "Islamabad" should be confirmed (in all 3)
    confirmed_texts = [e['text'] for e in result['confirmed_facts']]
    assert any('Imran Khan' in text for text in confirmed_texts)
    assert any('Monday' in text for text in confirmed_texts)

def test_debated_claims_detection():
    """Test detection of inconsistent information"""
    detector = ConsensusDetector()

    articles = [
        "The meeting will cost Rs 100 million.",
        "The meeting will cost Rs 200 million.",
        "The meeting expense is Rs 150 million."
    ]

    result = detector.analyze_cluster(articles)

    # Money amounts differ across articles → debated
    debated = result['debated_claims']
    money_claims = [e for e in debated if e['type'] == 'MONEY']
    assert len(money_claims) > 0

def test_source_counting():
    """Verify source count for each entity"""
    detector = ConsensusDetector()

    articles = [
        "Article 1 mentions Imran Khan and Islamabad.",
        "Article 2 mentions Imran Khan only.",
        "Article 3 mentions Imran Khan only."
    ]

    result = detector.analyze_cluster(articles)

    # Find "Imran Khan" entity
    imran_entity = next(e for e in result['confirmed_facts'] if 'Imran Khan' in e['text'])
    assert imran_entity['sources'] == 3  # Mentioned in all 3

    # Find "Islamabad" entity
    islamabad_entity = next(e for e in result['debated_claims'] if 'Islamabad' in e['text'])
    assert islamabad_entity['sources'] == 1  # Only in article 1
```

**Test File:** `tests/test_agents/test_setfit_classifier.py`
```python
@pytest.mark.slow
def test_train_category_classifier():
    """Test SetFit training with synthetic examples"""
    classifier = SetFitClassifier()

    # Synthetic training data
    examples = {
        "economy": ["rupee falls", "inflation rises", "stock market crashes"],
        "politics": ["election announced", "minister resigns", "assembly session"],
        "sports": ["cricket match", "football victory", "team wins"]
    }

    classifier.train_category_model(examples)

    # Test predictions
    assert classifier.predict_category("Dollar rate increases") == "economy"
    assert classifier.predict_category("Parliament dissolved") == "politics"
    assert classifier.predict_category("Hockey championship") == "sports"

def test_impact_label_classification():
    """Test impact label assignment"""
    classifier = SetFitClassifier()

    # Train with impact examples
    impact_examples = {
        "💳 WALLET": ["price increase", "tax hike", "petrol expensive"],
        "🚦 COMMUTE": ["road closed", "traffic jam", "metro delays"],
        "🛡️ SAFETY": ["blast reported", "crime surge", "fire incident"]
    }

    classifier.train_impact_model(impact_examples)

    # Test predictions
    labels = classifier.predict_impact("Petrol price increased by Rs 10")
    assert "💳 WALLET" in labels

def test_multi_label_impact():
    """Test assigning multiple impact labels to one story"""
    classifier = SetFitClassifier()
    classifier.train_impact_model(get_impact_examples())

    text = "Road closure due to gas pipeline explosion causes commute delays"
    labels = classifier.predict_impact(text)

    # Should detect both COMMUTE and UTILITIES impact
    assert "🚦 COMMUTE" in labels
    assert "⚡ UTILITIES" in labels
```

**Test File:** `tests/test_agents/test_rule_based_classifier.py`
```python
def test_keyword_based_category():
    """Test rule-based category classification"""
    classifier = RuleBasedClassifier("config/classification_rules.yaml")

    text = "Rupee falls against dollar amid inflation concerns"
    result = classifier.classify_text(text)

    # Should match "economy" keywords: rupee, dollar, inflation
    assert result['category'] == "economy"
    assert result['category_confidence'] >= 3  # Matched 3 keywords

def test_impact_label_from_rules():
    """Test rule-based impact detection"""
    classifier = RuleBasedClassifier("config/classification_rules.yaml")

    text = "Electricity loadshedding increases to 12 hours daily"
    result = classifier.classify_text(text)

    assert "⚡ UTILITIES" in result['impact_labels']

def test_hybrid_classification():
    """Test SetFit + rule-based hybrid approach"""
    setfit = SetFitClassifier()
    rules = RuleBasedClassifier("config/classification_rules.yaml")

    text = "Budget deficit widens as tax collection falls short"

    # SetFit prediction
    setfit_category = setfit.predict_category(text)

    # Rule-based prediction
    rule_category = rules.classify_text(text)['category']

    # Both should agree on "economy"
    assert setfit_category == "economy"
    assert rule_category == "economy"
```

**Test File:** `tests/test_agents/test_analysis_pipeline.py`
```python
@pytest.mark.integration
def test_full_analysis_pipeline():
    """Integration test: cluster → entities → consensus → classification"""
    db_client = SupabaseClient(test_mode=True)

    # Get a cluster from database
    cluster = db_client.get_cluster_by_id("test-cluster-id")
    articles = db_client.get_articles_by_ids(cluster.article_ids)

    # Extract entities
    extractor = EntityExtractor()
    all_entities = [extractor.extract(a.main_text) for a in articles]

    # Detect consensus
    detector = ConsensusDetector()
    consensus = detector.analyze_cluster([a.main_text for a in articles])

    # Classify
    classifier = SetFitClassifier()
    combined_text = " ".join([a.headline for a in articles])
    category = classifier.predict_category(combined_text)
    impact_labels = classifier.predict_impact(combined_text)

    # Verify results
    assert consensus['confirmed_facts'] is not None
    assert category in ["economy", "politics", "city", "education", "health", "sports"]
    assert len(impact_labels) > 0

@pytest.mark.integration
def test_store_analyzed_feed():
    """Test storing analysis results in analyzed_feed table"""
    db_client = SupabaseClient(test_mode=True)

    analyzed_story = {
        "cluster_id": "test-cluster-123",
        "headline": "Rupee falls to record low",
        "category": "economy",
        "confirmed_facts": [
            {"text": "Rupee", "type": "MONEY", "sources": 5},
            {"text": "State Bank", "type": "ORG", "sources": 4}
        ],
        "debated_claims": [
            {"text": "100 rupees", "type": "MONEY", "sources": 2},
            {"text": "105 rupees", "type": "MONEY", "sources": 3}
        ],
        "impact_labels": ["💳 WALLET", "🏛️ GOVERNANCE"],
        "source_attribution": {
            "dawn": 2,
            "tribune": 3
        }
    }

    feed_id = db_client.insert_analyzed_feed(analyzed_story)

    # Verify storage
    retrieved = db_client.get_analyzed_feed_by_id(feed_id)
    assert retrieved.category == "economy"
    assert len(retrieved.impact_labels) == 2
```

### Acceptance Criteria

- ✅ spaCy extracts entities from English and Urdu text
- ✅ Consensus detection correctly identifies confirmed vs debated facts
- ✅ SetFit classifier achieves >80% accuracy on test categories
- ✅ Impact labels assigned correctly (manual spot-check on 10 samples)
- ✅ Rule-based classifier works as fallback
- ✅ Hybrid approach (SetFit + rules) provides robust classification
- ✅ Full pipeline: cluster → analysis → database storage works
- ✅ Analyzed feed contains all required fields

### Commit Checkpoints

1. `Add spaCy entity extraction module`
2. `Implement consensus detection algorithm`
3. `Add SetFit zero-shot classification`
4. `Implement rule-based classifier with YAML config`
5. `Create analysis pipeline orchestrator`
6. `Add comprehensive NLP analysis tests`

**Output:** Complete NLP analysis engine that processes clusters and generates rich metadata for story cards. Can identify facts, detect debates, classify categories, and assign impact labels.

---

## Phase 6: Full Pipeline Orchestration & GitHub Actions

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

def test_pipeline_uses_embedding_fallback():
    """Test pipeline switches to local embeddings on API failure"""
    with patch('GeminiEmbeddingProvider.embed', side_effect=APIError):
        result = run_daily_pipeline()

        # Should complete using local embeddings
        assert result.embedding_provider == "local"
        assert result.status == "success"

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
pytest tests/test_scrapers/test_newspaper4k.py
git add src/scrapers/newspaper4k.py tests/test_scrapers/test_newspaper4k.py
git commit -m "Add newspaper4k scraper for static sites"

# Work on Playwright scraper
# ... write code, write tests ...
pytest tests/test_scrapers/test_playwright.py
git add src/scrapers/playwright_scraper.py tests/test_scrapers/test_playwright.py
git commit -m "Implement Playwright scraper for dynamic content"

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
- [ ] Local fallback activates on API failure
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
