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
    algorithm_used VARCHAR(50) DEFAULT 'event_graph',
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
    cluster_id UUID NOT NULL,
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
ALTER TABLE raw_articles DROP CONSTRAINT IF EXISTS fk_raw_articles_cluster;
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
-- Hosted access is server-only. No anonymous or authenticated table access.
-- Re-running this file upgrades the old schema without deleting content.
ALTER TABLE analyzed_feed DROP CONSTRAINT IF EXISTS analyzed_feed_cluster_id_fkey;
ALTER TABLE raw_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyzed_feed ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON raw_articles, clusters, analyzed_feed FROM anon, authenticated;
GRANT ALL ON raw_articles, clusters, analyzed_feed TO service_role;

CREATE TABLE IF NOT EXISTS pipeline_state (
    id TEXT PRIMARY KEY CHECK (id = 'daily'),
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE pipeline_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON pipeline_state FROM anon, authenticated;
GRANT ALL ON pipeline_state TO service_role;

-- All draft cards become visible in one transaction. Prior editions remain
-- readable; the API selects only the latest published brief_run_at stamp.
CREATE OR REPLACE FUNCTION publish_brief(publication_token TEXT, expected_cards INTEGER, heartbeat JSONB)
RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
    actual_cards INTEGER;
    distinct_clusters INTEGER;
    distinct_runs INTEGER;
BEGIN
    PERFORM pg_advisory_xact_lock(704218);
    IF publication_token IS NULL OR length(publication_token) = 0 OR expected_cards NOT BETWEEN 1 AND 12 THEN
        RAISE EXCEPTION 'Invalid publication request';
    END IF;
    SELECT count(*), count(DISTINCT cluster_id), count(DISTINCT metadata->>'brief_run_at')
    INTO actual_cards, distinct_clusters, distinct_runs FROM analyzed_feed
    WHERE metadata->>'publication_token' = publish_brief.publication_token;
    IF actual_cards <> expected_cards OR distinct_clusters <> actual_cards OR distinct_runs <> 1 THEN
        RAISE EXCEPTION 'Edition is incomplete or contains duplicate stories';
    END IF;
    IF EXISTS (SELECT 1 FROM analyzed_feed
        WHERE metadata->>'publication_token' = publish_brief.publication_token
        AND (length(trim(coalesce(metadata->>'why_it_matters', ''))) = 0
             OR created_at < now() - interval '3 hours'
             OR created_at > now() + interval '5 minutes')) THEN
        RAISE EXCEPTION 'Edition has missing impact copy or invalid dates';
    END IF;
    UPDATE analyzed_feed SET is_published = TRUE
    WHERE metadata->>'publication_token' = publish_brief.publication_token;
    INSERT INTO pipeline_state(id, payload) VALUES ('daily', heartbeat)
    ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW();
    RETURN actual_cards;
END;
$$;
REVOKE ALL ON FUNCTION publish_brief(TEXT, INTEGER, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION publish_brief(TEXT, INTEGER, JSONB) TO service_role;

-- Retention and regrouping must not remove the last readable edition or its
-- source context, including during a multi-day generation outage.
CREATE OR REPLACE FUNCTION preserve_published_context()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    IF TG_TABLE_NAME = 'analyzed_feed' THEN
        IF OLD.is_published AND OLD.metadata->>'brief_run_at' = (
            SELECT metadata->>'brief_run_at' FROM analyzed_feed
            WHERE is_published ORDER BY created_at DESC LIMIT 1
        ) THEN RETURN NULL; END IF;
    ELSIF TG_TABLE_NAME = 'clusters' THEN
        IF EXISTS (SELECT 1 FROM analyzed_feed WHERE cluster_id = OLD.id AND is_published)
        THEN RETURN NULL; END IF;
    ELSIF TG_TABLE_NAME = 'raw_articles' THEN
        IF EXISTS (SELECT 1 FROM clusters c JOIN analyzed_feed f ON f.cluster_id = c.id
                   WHERE f.is_published AND OLD.id = ANY(c.article_ids))
        THEN RETURN NULL; END IF;
    END IF;
    RETURN OLD;
END;
$$;
DROP TRIGGER IF EXISTS preserve_published_feed ON analyzed_feed;
CREATE TRIGGER preserve_published_feed BEFORE DELETE ON analyzed_feed
FOR EACH ROW EXECUTE FUNCTION preserve_published_context();
DROP TRIGGER IF EXISTS preserve_published_cluster ON clusters;
CREATE TRIGGER preserve_published_cluster BEFORE DELETE ON clusters
FOR EACH ROW EXECUTE FUNCTION preserve_published_context();
DROP TRIGGER IF EXISTS preserve_published_article ON raw_articles;
CREATE TRIGGER preserve_published_article BEFORE DELETE ON raw_articles
FOR EACH ROW EXECUTE FUNCTION preserve_published_context();
