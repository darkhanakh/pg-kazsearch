CREATE EXTENSION IF NOT EXISTS pg_kazsearch;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_ts_config
        WHERE cfgname = 'kazakh_cfg'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION kazakh_cfg (PARSER = pg_catalog.default);
    END IF;
END $$;

ALTER TEXT SEARCH CONFIGURATION kazakh_cfg
    ALTER MAPPING FOR asciiword, asciihword, hword_asciipart, word, hword, hword_part
    WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'articles'
    ) THEN
        EXECUTE $SQL$
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS fts_vector tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('kazakh_cfg', title), 'A') ||
                setweight(to_tsvector('kazakh_cfg', body), 'B')
            ) STORED
        $SQL$;

        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING GIN (fts_vector)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_articles_trgm_title ON articles USING GIN (title gin_trgm_ops)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_articles_trgm_body ON articles USING GIN (body gin_trgm_ops)';
    END IF;
END $$;
