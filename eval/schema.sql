CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS articles (
    id          serial PRIMARY KEY,
    url         text UNIQUE NOT NULL,
    title       text NOT NULL,
    body        text NOT NULL,
    category    text,
    published   date,
    fts_vector  tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('kazakh_cfg', title), 'A') ||
        setweight(to_tsvector('kazakh_cfg', body), 'B')
    ) STORED
);

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS fts_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('kazakh_cfg', title), 'A') ||
        setweight(to_tsvector('kazakh_cfg', body), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_articles_fts
    ON articles USING GIN (fts_vector);

CREATE INDEX IF NOT EXISTS idx_articles_trgm_title
    ON articles USING GIN (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_articles_trgm_body
    ON articles USING GIN (body gin_trgm_ops);
