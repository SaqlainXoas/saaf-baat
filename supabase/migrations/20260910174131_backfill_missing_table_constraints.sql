ALTER TABLE raw_articles ADD CONSTRAINT raw_articles_content_hash_key UNIQUE (content_hash);
ALTER TABLE raw_articles ADD CONSTRAINT valid_source CHECK (LENGTH(source) > 0);
ALTER TABLE raw_articles ADD CONSTRAINT valid_headline CHECK (LENGTH(headline) > 0);
ALTER TABLE raw_articles ADD CONSTRAINT valid_main_text CHECK (LENGTH(main_text) > 0);
ALTER TABLE raw_articles ADD CONSTRAINT valid_content_hash CHECK (LENGTH(content_hash) = 64);

ALTER TABLE clusters ADD CONSTRAINT valid_cluster_size CHECK (cluster_size >= 0);
ALTER TABLE clusters ADD CONSTRAINT valid_similarity CHECK (avg_similarity IS NULL OR (avg_similarity >= 0 AND avg_similarity <= 1));

ALTER TABLE analyzed_feed ADD CONSTRAINT valid_category CHECK (category IN ('economy','politics','city','education','health','sports','technology','entertainment','security','international','other'));
ALTER TABLE analyzed_feed ADD CONSTRAINT valid_headline_length CHECK (LENGTH(headline) > 0);
ALTER TABLE analyzed_feed ADD CONSTRAINT valid_confidence CHECK (classification_confidence IS NULL OR (classification_confidence >= 0 AND classification_confidence <= 1));;
