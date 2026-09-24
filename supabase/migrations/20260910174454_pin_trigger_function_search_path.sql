CREATE OR REPLACE FUNCTION update_cluster_timestamp()
RETURNS TRIGGER
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_cluster_size()
RETURNS TRIGGER
SET search_path = public
AS $$
BEGIN
    NEW.cluster_size = COALESCE(array_length(NEW.article_ids, 1), 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;;
