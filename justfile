set dotenv-load := false

container   := "pg-kazsearch"
pg_user     := "postgres"
pg_db       := "kazsearch"

corpus      := "data/corpus/articles.jsonl"
auto_q      := "eval/auto_queries.jsonl"
gold_q      := "eval/gold_queries.jsonl"
scrape_lim  := "3000"
eval_max_q  := "0"
opt_report  := "eval/results/optimized_weights.json"
opt_evals   := "2000"
opt_obj     := "combined"

# ── Helpers ──────────────────────────────────────────────────────────────

[private]
dc-exec +cmd:
    docker exec -w /app {{ container }} {{ cmd }}

[private]
psql-exec sql:
    docker exec {{ container }} psql -U {{ pg_user }} -d {{ pg_db }} -c "{{ sql }}"

# ── Database ─────────────────────────────────────────────────────────────

# Start PostgreSQL container
up:
    docker compose up -d --build
    @echo "Waiting for database…"
    @until docker exec {{ container }} pg_isready -U {{ pg_user }} -d {{ pg_db }} -q 2>/dev/null; do sleep 1; done
    @echo "Database ready."

# Stop container
down:
    docker compose down

# Restart container
restart:
    docker compose restart
    @until docker exec {{ container }} pg_isready -U {{ pg_user }} -d {{ pg_db }} -q 2>/dev/null; do sleep 1; done

# Tail container logs
logs:
    docker compose logs -f --tail=50

# Show DB and extension status
status:
    @docker exec {{ container }} pg_isready -U {{ pg_user }} -d {{ pg_db }} && \
        echo "Extensions:" && \
        docker exec {{ container }} psql -U {{ pg_user }} -d {{ pg_db }} -c "SELECT extname, extversion FROM pg_extension ORDER BY extname;"

# Open interactive psql session
psql:
    docker exec -it {{ container }} psql -U {{ pg_user }} -d {{ pg_db }}

# ── Extension build ─────────────────────────────────────────────────────

# Build lexicon, compile, and install extension
build:
    python3 scripts/build_lexicon.py
    just dc-exec make -C src/pg_kazsearch
    just dc-exec make -C src/pg_kazsearch install

# Build + reload extension and FTS configuration
reload: build
    just psql-exec "DROP EXTENSION IF EXISTS pg_kazsearch CASCADE; CREATE EXTENSION pg_kazsearch;"
    just psql-exec "DROP TEXT SEARCH CONFIGURATION IF EXISTS kazakh_cfg CASCADE; CREATE TEXT SEARCH CONFIGURATION kazakh_cfg (PARSER = pg_catalog.default);"
    just psql-exec "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR asciiword WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
    just psql-exec "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR asciihword WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
    just psql-exec "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR hword_asciipart WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
    just psql-exec "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR word WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
    just psql-exec "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR hword WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
    just psql-exec "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR hword_part WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
    @echo "Extension reloaded."

# ── Test ─────────────────────────────────────────────────────────────────

# Smoke test stemmer and tsvector
test-ext:
    @echo "── Testing pg_kazsearch extension ──"
    just psql-exec "SELECT ts_lexize('pg_kazsearch_dict', 'алмаларымыздағы');"
    just psql-exec "SELECT to_tsvector('kazakh_cfg', 'алмаларымыздағы мектептеріміздегі');"

# ── Eval pipeline ────────────────────────────────────────────────────────

# Scrape articles from Tengrinews
scrape:
    python3 eval/scraper.py --output "{{ corpus }}" --limit {{ scrape_lim }} --resume

# Load article corpus into PostgreSQL
load-corpus:
    python3 eval/load_corpus.py --input "{{ corpus }}"

# Generate evaluation queries from corpus
gen-queries:
    python3 eval/generate_queries.py --input "{{ corpus }}" --output "{{ auto_q }}" --use-db-ids

# Run FTS vs trigram comparison
eval-search:
    python3 eval/run_eval.py --auto "{{ auto_q }}" --gold "{{ gold_q }}" --max-queries {{ eval_max_q }}

# Run CMA-ES weight optimizer
optimize:
    python3 eval/optimize_weights.py --auto "{{ auto_q }}" --gold "{{ gold_q }}" \
        --max-evals {{ opt_evals }} --objective {{ opt_obj }} --report "{{ opt_report }}"

# Apply optimized weights from JSON report
apply-weights:
    @python3 -c "\
    import json; \
    r = json.load(open('{{ opt_report }}')); \
    w = r['weights']; \
    opts = ', '.join(f'{k} = {v}' for k, v in w.items()); \
    print(f'ALTER TEXT SEARCH DICTIONARY pg_kazsearch_dict ({opts});')" | \
    docker exec -i {{ container }} psql -U {{ pg_user }} -d {{ pg_db }}

# Full eval pipeline: scrape, load, generate queries, evaluate
pipeline: scrape load-corpus gen-queries eval-search

# ── Release ──────────────────────────────────────────────────────────────

# Create distribution zip
dist:
    #!/usr/bin/env bash
    version=$(grep -m 1 '"version":' META.json | sed -e 's/[[:space:]]*"version":[[:space:]]*"\([^"]*\)".*/\1/')
    git archive --format zip --prefix="pg_kazsearch-${version}/" -o "pg_kazsearch-${version}.zip" HEAD

# ── Cleanup ──────────────────────────────────────────────────────────────

# Remove build artifacts
clean:
    -just dc-exec make -C src/pg_kazsearch clean
    rm -rf eval/results/

# Stop container and remove volumes
nuke: down
    docker compose down -v
    @echo "Volumes removed."
