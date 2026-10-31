-- Hybrid Kazakh search in one PostgreSQL:
--   pg_kazsearch (stemming) + pg_textsearch (BM25) + pgvector (dense), fused with RRF.
--
-- Requires PostgreSQL 17/18 with shared_preload_libraries = 'pg_textsearch'.
-- Run with:  psql -v q='мал шаруашылығын дамыту' -v qvec='[0.01,-0.02,...]' -f examples/hybrid-search.sql
-- `qvec` is the query embedding (1024 floats for BAAI/bge-m3, L2-normalized).

CREATE EXTENSION IF NOT EXISTS pg_kazsearch;
CREATE EXTENSION IF NOT EXISTS pg_textsearch;
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Schema. `doc` is the single text column BM25 scores (title + body).
CREATE TABLE IF NOT EXISTS docs (
    id        bigserial PRIMARY KEY,
    title     text NOT NULL,
    body      text NOT NULL,
    doc       text GENERATED ALWAYS AS (title || E'\n' || body) STORED,
    embedding vector(1024)   -- bge-m3 of title + body, truncated to 512 tokens
);

-- 2. Indexes. Create them after bulk loading.
-- The text search config must be schema-qualified: pg_textsearch does not
-- resolve 'kazakh_cfg' through search_path.
CREATE INDEX IF NOT EXISTS docs_bm25_idx ON docs
    USING bm25 (doc) WITH (text_config = 'public.kazakh_cfg');
CREATE INDEX IF NOT EXISTS docs_hnsw_idx ON docs
    USING hnsw (embedding vector_cosine_ops);

-- HNSW returns at most hnsw.ef_search rows; keep it >= the candidate depth below.
SET hnsw.ef_search = 200;

-- 3. Hybrid query: top-100 BM25 + top-100 dense, fused by reciprocal rank (k = 60).
-- Do not select the BM25 score next to ORDER BY: that forces per-row scoring
-- (~250x slower in our benchmark). Rank by position instead.
WITH bm AS (
    SELECT id, row_number() OVER () AS rnk
    FROM (SELECT id FROM docs
          ORDER BY doc <@> to_bm25query(:'q', 'docs_bm25_idx')
          LIMIT 100) t
),
dn AS (
    SELECT id, row_number() OVER () AS rnk
    FROM (SELECT id FROM docs
          ORDER BY embedding <=> :'qvec'::vector
          LIMIT 100) t
)
SELECT d.id, d.title,
       COALESCE(1.0 / (60 + bm.rnk), 0) + COALESCE(1.0 / (60 + dn.rnk), 0) AS rrf
FROM bm
FULL OUTER JOIN dn USING (id)
JOIN docs d USING (id)
ORDER BY rrf DESC
LIMIT 10;
