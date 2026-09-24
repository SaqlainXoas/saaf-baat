-- Reliability functions for resumable daily publication.
-- Apply after the four historical migrations fetched from the live project.

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
    -- A retry after a lost HTTP response must not re-promote or overwrite a
    -- newer edition's heartbeat with this older attempt.
    IF NOT EXISTS (SELECT 1 FROM analyzed_feed
        WHERE metadata->>'publication_token' = publish_brief.publication_token
          AND is_published = FALSE) THEN
        RETURN actual_cards;
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

-- Build the new graph before this call. Any invalid member or failed insert
-- rolls the entire regrouping back, leaving the old graph intact.
CREATE OR REPLACE FUNCTION replace_recent_clusters(since_at TIMESTAMPTZ, new_groups JSONB)
RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
    old_ids UUID[];
    seen_ids UUID[] := '{}';
    member_ids UUID[];
    item JSONB;
    group_id UUID;
    cleared_count INTEGER := 0;
    removed_count INTEGER := 0;
    assigned_count INTEGER;
BEGIN
    PERFORM pg_advisory_xact_lock(704219);
    IF since_at IS NULL OR since_at < now() - interval '7 days'
       OR since_at > now() + interval '5 minutes'
       OR jsonb_typeof(new_groups) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Invalid cluster replacement request';
    END IF;
    SELECT coalesce(array_agg(DISTINCT cluster_id), '{}') INTO old_ids
    FROM raw_articles WHERE scraped_at >= since_at AND cluster_id IS NOT NULL;
    UPDATE raw_articles SET cluster_id = NULL
    WHERE cluster_id = ANY(old_ids);
    GET DIAGNOSTICS cleared_count = ROW_COUNT;
    DELETE FROM clusters WHERE id = ANY(old_ids);
    GET DIAGNOSTICS removed_count = ROW_COUNT;

    FOR item IN SELECT value FROM jsonb_array_elements(new_groups) LOOP
        group_id := (item->>'id')::UUID;
        SELECT array_agg(value::UUID) INTO member_ids
        FROM jsonb_array_elements_text(item->'article_ids');
        IF group_id IS NULL OR member_ids IS NULL OR cardinality(member_ids) = 0
           OR member_ids && seen_ids
           OR (SELECT count(DISTINCT id) FROM unnest(member_ids) AS id) <> cardinality(member_ids)
           OR (SELECT count(*) FROM raw_articles
               WHERE id = ANY(member_ids) AND scraped_at >= since_at AND embedding IS NOT NULL)
              <> cardinality(member_ids) THEN
            RAISE EXCEPTION 'Invalid or duplicate cluster membership';
        END IF;
        seen_ids := seen_ids || member_ids;
        INSERT INTO clusters(id, article_ids, centroid_embedding, algorithm_used)
        VALUES (group_id, member_ids,
                (item->'centroid_embedding')::TEXT::VECTOR(768),
                item->>'algorithm_used');
        UPDATE raw_articles SET cluster_id = group_id WHERE id = ANY(member_ids);
        GET DIAGNOSTICS assigned_count = ROW_COUNT;
        IF assigned_count <> cardinality(member_ids) THEN
            RAISE EXCEPTION 'Incomplete cluster assignment';
        END IF;
    END LOOP;
    RETURN jsonb_build_object('removed', removed_count, 'cleared', cleared_count);
END;
$$;
REVOKE ALL ON FUNCTION replace_recent_clusters(TIMESTAMPTZ, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION replace_recent_clusters(TIMESTAMPTZ, JSONB) TO service_role;

CREATE OR REPLACE FUNCTION persist_embeddings(updates JSONB)
RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE item JSONB; changed INTEGER; total INTEGER := 0;
BEGIN
    IF jsonb_typeof(updates) IS DISTINCT FROM 'array' OR jsonb_array_length(updates) > 100 THEN
        RAISE EXCEPTION 'Invalid embedding batch';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(updates) LOOP
        UPDATE raw_articles SET embedding = (item->'embedding')::TEXT::VECTOR(768)
        WHERE id = (item->>'id')::UUID;
        GET DIAGNOSTICS changed = ROW_COUNT;
        IF changed <> 1 THEN RAISE EXCEPTION 'Missing embedding article'; END IF;
        total := total + changed;
    END LOOP;
    RETURN total;
END;
$$;
REVOKE ALL ON FUNCTION persist_embeddings(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION persist_embeddings(JSONB) TO service_role;

CREATE OR REPLACE FUNCTION persist_triage_metadata(updates JSONB)
RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE item JSONB; changed INTEGER; total INTEGER := 0;
BEGIN
    IF jsonb_typeof(updates) IS DISTINCT FROM 'array' OR jsonb_array_length(updates) > 100 THEN
        RAISE EXCEPTION 'Invalid triage batch';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(updates) LOOP
        IF jsonb_typeof(item->'metadata'->'triage') IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'Missing triage verdict';
        END IF;
        UPDATE raw_articles SET metadata = item->'metadata'
        WHERE id = (item->>'id')::UUID;
        GET DIAGNOSTICS changed = ROW_COUNT;
        IF changed <> 1 THEN RAISE EXCEPTION 'Missing triage article'; END IF;
        total := total + changed;
    END LOOP;
    RETURN total;
END;
$$;
REVOKE ALL ON FUNCTION persist_triage_metadata(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION persist_triage_metadata(JSONB) TO service_role;
