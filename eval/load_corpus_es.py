"""
Load the article corpus into Elasticsearch with the kazsearch_stem analyzer.

Creates an index 'articles' with two analyzers:
  - kazakh_kazsearch: standard tokenizer + lowercase + kazsearch_stem
  - kazakh_standard: standard tokenizer + lowercase (no stemming, baseline)

Usage:
    python3 eval/load_corpus_es.py [--input data/corpus/articles.jsonl]
                                   [--es-url http://localhost:9200]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

INDEX = "articles"
BATCH_SIZE = 100


def es_request(url: str, method: str = "GET", body: dict | list | None = None,
               expected: set[int] | None = None) -> dict | None:
    if expected is None:
        expected = {200}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in expected:
            return json.loads(e.read())
        raise


def wait_for_es(base_url: str, timeout: int = 120):
    print(f"Waiting for Elasticsearch at {base_url}...", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = es_request(f"{base_url}/_cluster/health")
            if resp and resp.get("status") in ("yellow", "green"):
                print(" ready.")
                return
        except Exception:
            pass
        time.sleep(2)
        print(".", end="", flush=True)
    sys.exit("\nElasticsearch did not become ready in time.")


def create_index(base_url: str):
    es_request(f"{base_url}/{INDEX}", method="DELETE", expected={200, 404})

    settings = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "filter": {
                    "kaz_stem": {"type": "kazsearch_stem"}
                },
                "analyzer": {
                    "kazakh_kazsearch": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "kaz_stem"]
                    },
                    "kazakh_standard": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "url": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "analyzer": "kazakh_kazsearch",
                    "fields": {
                        "standard": {
                            "type": "text",
                            "analyzer": "kazakh_standard"
                        }
                    }
                },
                "body": {
                    "type": "text",
                    "analyzer": "kazakh_kazsearch",
                    "fields": {
                        "standard": {
                            "type": "text",
                            "analyzer": "kazakh_standard"
                        }
                    }
                },
                "category": {"type": "keyword"},
                "published": {"type": "date", "format": "yyyy-MM-dd||epoch_millis", "ignore_malformed": True}
            }
        }
    }
    es_request(f"{base_url}/{INDEX}", method="PUT", body=settings)
    print(f"Created index '{INDEX}' with kazakh_kazsearch analyzer.")


def bulk_index(base_url: str, articles: list[dict]):
    lines = []
    for art in articles:
        meta = {"index": {"_index": INDEX, "_id": art["_id"]}}
        doc = {k: v for k, v in art.items() if k != "_id"}
        lines.append(json.dumps(meta, ensure_ascii=False))
        lines.append(json.dumps(doc, ensure_ascii=False))
    payload = "\n".join(lines) + "\n"
    data = payload.encode("utf-8")
    req = urllib.request.Request(f"{base_url}/_bulk", data=data, method="POST")
    req.add_header("Content-Type", "application/x-ndjson")
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    if result.get("errors"):
        errs = [item for item in result["items"] if "error" in item.get("index", {})]
        print(f"  WARNING: {len(errs)} bulk errors")


def main():
    parser = argparse.ArgumentParser(description="Load articles into Elasticsearch")
    parser.add_argument("--input", default="data/corpus/articles.jsonl")
    parser.add_argument("--es-url", default="http://localhost:9200")
    args = parser.parse_args()

    corpus_path = Path(args.input)
    if not corpus_path.exists():
        sys.exit(f"Corpus not found: {corpus_path}")

    wait_for_es(args.es_url)
    create_index(args.es_url)

    articles = []
    with corpus_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            art = json.loads(line)
            doc = {
                "_id": i,
                "url": art.get("url", ""),
                "title": art.get("title", ""),
                "body": art.get("body", ""),
                "category": art.get("category", ""),
            }
            date_val = art.get("date", "")
            if date_val:
                doc["published"] = date_val
            articles.append(doc)

    print(f"Indexing {len(articles)} articles...")
    t0 = time.monotonic()
    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_start:batch_start + BATCH_SIZE]
        bulk_index(args.es_url, batch)
        done = min(batch_start + BATCH_SIZE, len(articles))
        print(f"  {done}/{len(articles)}", flush=True)

    es_request(f"{args.es_url}/{INDEX}/_refresh", method="POST")
    elapsed = time.monotonic() - t0
    print(f"Indexed {len(articles)} articles in {elapsed:.1f}s")

    count_resp = es_request(f"{args.es_url}/{INDEX}/_count")
    print(f"Index document count: {count_resp.get('count', '?')}")


if __name__ == "__main__":
    main()
