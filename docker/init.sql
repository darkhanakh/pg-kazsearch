CREATE EXTENSION IF NOT EXISTS pg_kazsearch;

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
