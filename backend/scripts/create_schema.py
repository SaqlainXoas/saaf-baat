"""
Create database schema using SQLAlchemy.
Run: python create_schema.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("=" * 60)
    print("ERROR: DATABASE_URL not found in .env")
    print("=" * 60)
    sys.exit(1)

print("Connecting to database...")
engine = create_engine(DATABASE_URL)

print("Running schema SQL...")
print("=" * 60)

# Execute statements individually to handle errors gracefully
statements = [
    # Enable pgvector
    "CREATE EXTENSION IF NOT EXISTS vector",
    
    # raw_articles table
    """
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
        metadata JSONB DEFAULT '{}'
    )
    """,
    
    # clusters table
    """
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
        metadata JSONB DEFAULT '{}'
    )
    """,
    
    # analyzed_feed table
    """
    CREATE TABLE IF NOT EXISTS analyzed_feed (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        cluster_id UUID REFERENCES clusters(id) ON DELETE CASCADE,
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
        CONSTRAINT valid_category CHECK (category IN (
            'economy', 'politics', 'city', 'education', 'health',
            'sports', 'technology', 'entertainment', 'security',
            'international', 'other'
        )),
        CONSTRAINT valid_headline_length CHECK (LENGTH(headline) > 0),
        CONSTRAINT valid_confidence CHECK (
            classification_confidence IS NULL OR
            (classification_confidence >= 0 AND classification_confidence <= 1)
        )
    )
    """,
    
    # Indexes for raw_articles
    "CREATE INDEX IF NOT EXISTS idx_raw_articles_source ON raw_articles(source)",
    "CREATE INDEX IF NOT EXISTS idx_raw_articles_publish_date ON raw_articles(publish_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_raw_articles_content_hash ON raw_articles(content_hash)",
    "CREATE INDEX IF NOT EXISTS idx_raw_articles_cluster_id ON raw_articles(cluster_id)",
    "CREATE INDEX IF NOT EXISTS idx_raw_articles_scraped_at ON raw_articles(scraped_at DESC)",
    
    # Indexes for clusters
    "CREATE INDEX IF NOT EXISTS idx_clusters_created_at ON clusters(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_clusters_cluster_size ON clusters(cluster_size DESC)",
    
    # Indexes for analyzed_feed
    "CREATE INDEX IF NOT EXISTS idx_analyzed_feed_cluster_id ON analyzed_feed(cluster_id)",
    "CREATE INDEX IF NOT EXISTS idx_analyzed_feed_category ON analyzed_feed(category)",
    "CREATE INDEX IF NOT EXISTS idx_analyzed_feed_created_at ON analyzed_feed(created_at DESC)",
    
    # Foreign key for raw_articles -> clusters
    """
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_raw_articles_cluster'
        ) THEN
            ALTER TABLE raw_articles
            ADD CONSTRAINT fk_raw_articles_cluster
            FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE SET NULL;
        END IF;
    END $$
    """,
]

with engine.connect() as conn:
    for i, statement in enumerate(statements, 1):
        try:
            conn.execute(text(statement))
            conn.commit()
            print(f"✓ Statement {i} executed")
        except Exception as e:
            conn.rollback()
            error_msg = str(e)
            if 'already exists' in error_msg.lower():
                print(f"⚠ Statement {i} skipped (already exists)")
            else:
                print(f"✗ Statement {i} failed: {error_msg[:80]}")

print("=" * 60)
print("✅ Schema creation complete!")
print()
print("Now run integration tests:")
print("  python -m pytest tests/test_db/test_integration.py -v")
