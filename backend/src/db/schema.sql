-- Saaf Baat Database Schema
-- Requires pgvector extension for embedding storage

-- Enable pgvector extension (run this in Supabase SQL editor first)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- Table: raw_articles
-- Stores scraped articles before processing
-- ============================================
CREATE TABLE IF NOT EXISTS raw_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(100) NOT NULL,
    url TEXT NOT NULL UNIQUE,
    headline TEXT NOT NULL,
    main_text TEXT NOT NULL,
    author VARCHAR(255),
    publish_date TIMESTAMPTZ,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    cluster_id UUID,
    embedding VECTOR(768),
    metadata JSONB DEFAULT '{}',
    
    -- Constraints
    CONSTRAINT valid_source CHECK (LENGTH(source) > 0),
    CONSTRAINT valid_headline CHECK (LENGTH(headline) > 0),
    -- Tier B corroboration rows carry only a headline until the body is
    -- fetched lazily; metadata->>'body_status' records which state a row is in.
    CONSTRAINT valid_main_text CHECK (LENGTH(main_text) > 0),
    CONSTRAINT valid_content_hash CHECK (LENGTH(content_hash) = 64)
);

-- Indexes for raw_articles
CREATE INDEX IF NOT EXISTS idx_raw_articles_source ON raw_articles(source);
CREATE INDEX IF NOT EXISTS idx_raw_articles_publish_date ON raw_articles(publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_articles_content_hash ON raw_articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_articles_cluster_id ON raw_articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_raw_articles_scraped_at ON raw_articles(scraped_at DESC);

-- ============================================
-- Table: clusters
-- Groups related articles by story
-- ============================================
CREATE TABLE IF NOT EXISTS clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    article_ids UUID[] NOT NULL DEFAULT '{}',
    centroid_embedding VECTOR(768),
    representative_article_id UUID,
    cluster_size INTEGER DEFAULT 0,
    avg_similarity FLOAT,
    algorithm_used VARCHAR(50) DEFAULT 'hdbscan',
    metadata JSONB DEFAULT '{}',
    
    -- Constraints
    CONSTRAINT valid_cluster_size CHECK (cluster_size >= 0),
    CONSTRAINT valid_similarity CHECK (avg_similarity IS NULL OR (avg_similarity >= 0 AND avg_similarity <= 1))
);

-- Indexes for clusters
CREATE INDEX IF NOT EXISTS idx_clusters_created_at ON clusters(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clusters_cluster_size ON clusters(cluster_size DESC);

-- ============================================
-- Table: analyzed_feed
-- Final processed stories for frontend display
-- ============================================
CREATE TABLE IF NOT EXISTS analyzed_feed (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    headline TEXT NOT NULL,
    summary TEXT,
    category VARCHAR(50) NOT NULL,
    confirmed_facts JSONB DEFAULT '[]',
    debated_claims JSONB DEFAULT '[]',
    impact_labels TEXT[] DEFAULT '{}',
    source_attribution JSONB DEFAULT '{}',
    entity_counts JSONB DEFAULT '{}',
    classification_confidence FLOAT,
    is_published BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    
    -- Constraints
    CONSTRAINT valid_category CHECK (category IN ('economy', 'politics', 'city', 'education', 'health', 'sports', 'technology', 'entertainment', 'security', 'international', 'other')),
    CONSTRAINT valid_headline_length CHECK (LENGTH(headline) > 0),
    CONSTRAINT valid_confidence CHECK (classification_confidence IS NULL OR (classification_confidence >= 0 AND classification_confidence <= 1))
);

-- Indexes for analyzed_feed
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_cluster_id ON analyzed_feed(cluster_id);
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_category ON analyzed_feed(category);
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_created_at ON analyzed_feed(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_is_published ON analyzed_feed(is_published) WHERE is_published = TRUE;
CREATE INDEX IF NOT EXISTS idx_analyzed_feed_impact_labels ON analyzed_feed USING GIN(impact_labels);

-- ============================================
-- Foreign Key: Link raw_articles to clusters
-- ============================================
ALTER TABLE raw_articles
ADD CONSTRAINT fk_raw_articles_cluster
FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE SET NULL;

-- ============================================
-- Function: Update cluster timestamp on modification
-- ============================================
CREATE OR REPLACE FUNCTION update_cluster_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating cluster timestamp
DROP TRIGGER IF EXISTS trigger_update_cluster_timestamp ON clusters;
CREATE TRIGGER trigger_update_cluster_timestamp
    BEFORE UPDATE ON clusters
    FOR EACH ROW
    EXECUTE FUNCTION update_cluster_timestamp();

-- ============================================
-- Function: Update cluster size when articles change
-- ============================================
CREATE OR REPLACE FUNCTION update_cluster_size()
RETURNS TRIGGER AS $$
BEGIN
    NEW.cluster_size = COALESCE(array_length(NEW.article_ids, 1), 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating cluster size
DROP TRIGGER IF EXISTS trigger_update_cluster_size ON clusters;
CREATE TRIGGER trigger_update_cluster_size
    BEFORE INSERT OR UPDATE ON clusters
    FOR EACH ROW
    EXECUTE FUNCTION update_cluster_size();

-- ============================================
-- Row Level Security (RLS) Policies
-- For Supabase - enable if using anon key from frontend
-- ============================================
-- ALTER TABLE raw_articles ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE clusters ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE analyzed_feed ENABLE ROW LEVEL SECURITY;

-- Read-only access for analyzed_feed (frontend)
-- CREATE POLICY "Public read access" ON analyzed_feed
--     FOR SELECT USING (is_published = TRUE);
