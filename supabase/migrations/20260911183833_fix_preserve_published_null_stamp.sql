CREATE OR REPLACE FUNCTION preserve_published_context()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    IF TG_TABLE_NAME = 'analyzed_feed' THEN
        IF OLD.is_published AND OLD.metadata->>'brief_run_at' IS NOT DISTINCT FROM (
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
$$;;
