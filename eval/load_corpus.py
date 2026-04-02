"""
Load articles.jsonl into the PostgreSQL articles table.

Applies eval/schema.sql first (idempotent), then batch-inserts
articles with ON CONFLICT (url) DO NOTHING.

Usage:
    python3 eval/load_corpus.py --input data/corpus/articles.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CONTAINER = "pg-kazsearch"
DB = "kazsearch"
USER = "postgres"
SCHEMA_FILE = Path(__file__).parent / "schema.sql"
BATCH_SIZE = 20


def psql(sql: str, container: str = CONTAINER, db: str = DB, user: str = USER) -> str:
    cmd = ["docker", "exec", "-i", container, "psql", "-U", user, "-d", db, "-At"]
    result = subprocess.run(cmd, input=sql, text=True, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout + result.stderr)
    return result.stdout


def psql_file(path: Path, container: str = CONTAINER, db: str = DB, user: str = USER) -> str:
    with open(path, "r") as f:
        sql = f.read()
    return psql(sql, container, db, user)


def qlit(s: str) -> str:
    return s.replace("'", "''").replace("\\", "\\\\")


def ensure_fts_schema(container: str, db: str, user: str):
    sql = """
ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS fts_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('kazakh_cfg', title), 'A') ||
        setweight(to_tsvector('kazakh_cfg', body), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_articles_fts
    ON articles USING GIN (fts_vector);
"""
    psql(sql, container, db, user)


def load_articles(path: Path, container: str, db: str, user: str) -> int:
    articles = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                articles.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not articles:
        print("No articles found in input file")
        return 0

    loaded = 0
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i : i + BATCH_SIZE]
        values = []
        for a in batch:
            url = qlit(a.get("url", ""))
            title = qlit(a.get("title", ""))
            body = qlit(a.get("body", ""))
            category = qlit(a.get("category", ""))
            date = a.get("date", "")

            date_expr = f"'{date}'" if date else "NULL"
            values.append(
                f"('{url}', '{title}', '{body}', '{category}', {date_expr})"
            )

        sql = (
            "INSERT INTO articles (url, title, body, category, published) VALUES\n"
            + ",\n".join(values)
            + "\nON CONFLICT (url) DO NOTHING;"
        )

        try:
            psql(sql, container, db, user)
            loaded += len(batch)
        except subprocess.CalledProcessError as e:
            print(f"  WARN batch {i}-{i + len(batch)}: {e.output[:200]}", file=sys.stderr)

    return loaded


def print_stats(container: str, db: str, user: str):
    count = psql("SELECT count(*) FROM articles;", container, db, user).strip()
    avg_len = psql(
        "SELECT round(avg(length(body))) FROM articles;", container, db, user
    ).strip()
    idx_size = psql(
        "SELECT pg_size_pretty(pg_total_relation_size('articles'));",
        container, db, user,
    ).strip()
    print(f"  Total articles: {count}")
    print(f"  Avg body length: {avg_len} chars")
    print(f"  Table + indexes: {idx_size}")


def main():
    parser = argparse.ArgumentParser(description="Load article corpus into PostgreSQL")
    parser.add_argument("--input", default="data/corpus/articles.jsonl")
    parser.add_argument("--container", default=CONTAINER)
    parser.add_argument("--db", default=DB)
    parser.add_argument("--user", default=USER)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"Input file not found: {input_path}")

    print("Applying schema...")
    try:
        psql_file(SCHEMA_FILE, args.container, args.db, args.user)
    except subprocess.CalledProcessError as e:
        sys.exit(f"Schema failed: {e.output[:500]}")

    print("Ensuring FTS column/index migration...")
    try:
        ensure_fts_schema(args.container, args.db, args.user)
    except subprocess.CalledProcessError as e:
        sys.exit(f"FTS migration failed: {e.output[:500]}")

    print(f"Loading articles from {input_path}...")
    loaded = load_articles(input_path, args.container, args.db, args.user)
    print(f"Inserted {loaded} articles (duplicates skipped)")

    print("Stats:")
    print_stats(args.container, args.db, args.user)


if __name__ == "__main__":
    main()
