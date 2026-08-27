-- Saaf Baat local SQLite schema.
--
-- Mirrors src/db/schema.sql (Postgres/Supabase) closely enough that the same
-- client API works against either backend. Differences that matter:
--   * UUIDs are stored as TEXT
--   * TIMESTAMPTZ becomes TEXT holding normalized ISO-8601 UTC (sortable)
--   * VECTOR(768)/JSONB/arrays become TEXT holding JSON
-- Similarity math already happens in numpy inside the pipeline, so no
-- in-database vector support is required.

PRAGMA foreign_keys = ON;

-- ============================================
-- Table: clusters
-- Created before raw_articles so the FK target exists.
-- ============================================
CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    article_ids TEXT NOT NULL DEFAULT '[]',
    centroid_embedding TEXT,
    representative_article_id TEXT,
    cluster_size INTEGER NOT NULL DEFAULT 0,
    avg_similarity REAL,
    algorithm_used TEXT NOT NULL DEFAULT 'hdbscan',
    metadata TEXT NOT NULL DEFAULT '{}',

    CONSTRAINT valid_cluster_size CHECK (cluster_size >= 0),
    CONSTRAINT valid_similarity CHECK (
        avg_similarity IS NULL OR (avg_similarity >= 0 AND avg_similarity <= 1)
    )
);

CREATE INDEX IF NOT EXISTS idx_clusters_created_at ON clusters(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clusters_cluster_size ON clusters(cluster_size DESC);

-- ============================================
-- Table: raw_articles
-- ============================================
CREATE TABLE IF NOT EXISTS raw_articles (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    headline TEXT NOT NULL,
    main_text TEXT NOT NULL,
    author TEXT,
    publish_date TEXT,
    scraped_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    cluster_id TEXT REFERENCES clusters(id) ON DELETE SET NULL,
    embedding TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',

    CONSTRAINT valid_source CHECK (LENGTH(source) > 0),
    CONSTRAINT valid_headline CHECK (LENGTH(headline) > 0),
    -- Tier B corroboration rows carry only a headline until the body is
    -- fetched lazily; metadata->>'body_status' records which state a row is in.
    CONSTRAINT valid_main_text CHECK (LENGTH(main_text) > 0),
    CONSTRAINT valid_content_hash CHECK (LENGTH(content_hash) = 64)
);

CREATE INDEX IF NOT EXISTS idx_raw_articles_source ON raw_articles(source);
CREATE INDEX IF NOT EXISTS idx_raw_articles_publish_date ON raw_articles(publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_articles_content_hash ON raw_articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_articles_cluster_id ON raw_articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_raw_articles_scraped_at ON raw_articles(scraped_at DESC);

-- ============================================
-- Table: analyzed_feed
-- ============================================
CREATE TABLE IF NOT EXISTS analyzed_feed (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    category TEXT NOT NULL,
    confirmed_facts TEXT NOT NULL DEFAULT '[]',
    debated_claims TEXT NOT NULL DEFAULT '[]',
    impact_labels TEXT NOT NULL DEFAULT '[]',
    source_attribution TEXT NOT NULL DEFAULT '{}',
    entity_counts TEXT NOT NULL DEFAULT '{}',
    classification_confidence REAL,
    is_published INTEGER NOT NULL DEFAULT 1,
    metadata TEXT NOT NULL DEFAULT '{}',

    CONSTRAINT valid_category CHECK (category IN (
        'economy', 'politics', 'city', 'education', 'health', 'sports',
        'technology', 'entertainment', 'security', 'international', 'other'
    )),
    CONSTRAINT valid_headline_length CHECK (LENGTH(headline) > 0),
    CONSTRAINT valid_confidence CHECK (
        classification_confidence IS NULL
        OR (classification_confidence >= 0 AND classification_confidence <= 1)
    )
);

CREATE INDEX IF NOT EXISTS idx_analyzed_feed_cluster_id ON analyzed_feed(cluster_id);
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_category ON analyzed_feed(category);
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_created_at ON analyzed_feed(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_is_published ON analyzed_feed(is_published);
