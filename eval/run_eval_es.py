"""
Evaluate Elasticsearch search quality with kazsearch_stem vs standard analyzer.

Mirrors eval/run_eval.py metrics (Precision@k, Recall@k, MRR, nDCG@k) but
runs against Elasticsearch instead of PostgreSQL.

Usage:
    python3 eval/run_eval_es.py --auto eval/auto_queries.jsonl \
                                --gold eval/gold_queries.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ES_URL = "http://localhost:9200"
INDEX = "articles"
BATCH = 50


def es_request(url: str, method: str = "GET", body: dict | None = None) -> dict | None:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def search_es(query: str, k: int, base_url: str, fields: list[str]) -> list[int]:
    body = {
        "size": k,
        "query": {
            "multi_match": {
                "query": query,
                "fields": fields,
                "type": "best_fields"
            }
        },
        "_source": False
    }
    resp = es_request(f"{base_url}/{INDEX}/_search", method="POST", body=body)
    return [int(hit["_id"]) for hit in resp.get("hits", {}).get("hits", [])]


def msearch_es(queries: list[tuple[int, str]], k: int, base_url: str,
               fields: list[str]) -> dict[int, list[int]]:
    if not queries:
        return {}

    lines = []
    for qid, qt in queries:
        lines.append(json.dumps({"index": INDEX}))
        lines.append(json.dumps({
            "size": k,
            "query": {
                "multi_match": {
                    "query": qt,
                    "fields": fields,
                    "type": "best_fields"
                }
            },
            "_source": False
        }))
    payload = "\n".join(lines) + "\n"
    data = payload.encode("utf-8")
    req = urllib.request.Request(f"{base_url}/_msearch", data=data, method="POST")
    req.add_header("Content-Type", "application/x-ndjson")
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())

    results: dict[int, list[int]] = {}
    for i, (qid, _) in enumerate(queries):
        response = result["responses"][i]
        hits = response.get("hits", {}).get("hits", [])
        results[qid] = [int(h["_id"]) for h in hits]
    return results


def precision_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for x in top if x in relevant) / len(top)


def recall_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    return sum(1 for x in top if x in relevant) / len(relevant)


def mrr(retrieved: list[int], relevant: set[int]) -> float:
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant:
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    score = 0.0
    for i, doc_id in enumerate(retrieved[:k]):
        rel = 1.0 if doc_id in relevant else 0.0
        score += rel / math.log2(i + 2)
    return score


def ndcg_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    dcg = dcg_at_k(retrieved, relevant, k)
    ideal = sorted([1.0] * min(len(relevant), k) + [0.0] * max(0, k - len(relevant)), reverse=True)
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def load_queries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    queries = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                queries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return queries


def evaluate_method(name: str, indexed: list[tuple[int, str, set[int]]],
                    ks: list[int], base_url: str, fields: list[str]) -> dict:
    max_k = max(ks)
    t0 = time.monotonic()
    print(f"  Running {name} ({len(indexed)} queries)...", end="", flush=True)

    all_results: dict[int, list[int]] = {}
    for batch_start in range(0, len(indexed), BATCH):
        batch = [(idx, qt) for idx, qt, _ in indexed[batch_start:batch_start + BATCH]]
        all_results.update(msearch_es(batch, max_k, base_url, fields))
    elapsed = time.monotonic() - t0
    print(f" {elapsed:.1f}s")

    metrics: dict[int, dict[str, list[float]]] = {}
    for k_val in ks:
        metrics[k_val] = {"precision": [], "recall": [], "mrr": [], "ndcg": []}

    for idx, qt, relevant in indexed:
        results = all_results.get(idx, [])
        for k_val in ks:
            metrics[k_val]["precision"].append(precision_at_k(results, relevant, k_val))
            metrics[k_val]["recall"].append(recall_at_k(results, relevant, k_val))
            metrics[k_val]["mrr"].append(mrr(results[:k_val], relevant))
            metrics[k_val]["ndcg"].append(ndcg_at_k(results, relevant, k_val))

    def _avg(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    summary = {}
    for k_val in ks:
        summary[k_val] = {m: round(_avg(vals), 4) for m, vals in metrics[k_val].items()}

    return {"summary": summary, "elapsed": elapsed}


def print_report(results: dict, ks: list[int], n_queries: int):
    header = f"{'':36}"
    for k_val in ks:
        header += f"  {'P@' + str(k_val):>8}  {'R@' + str(k_val):>8}  {'MRR@' + str(k_val):>8}  {'nDCG@' + str(k_val):>8}"
    print(f"\n=== Elasticsearch eval ({n_queries} queries) ===")
    print(header)
    print("-" * len(header))
    for label, data in results.items():
        row = f"{label:36}"
        for k_val in ks:
            m = data["summary"][k_val]
            row += f"  {m['precision']:>8.4f}  {m['recall']:>8.4f}  {m['mrr']:>8.4f}  {m['ndcg']:>8.4f}"
        row += f"  ({data['elapsed']:.1f}s)"
        print(row)


def main():
    parser = argparse.ArgumentParser(description="Evaluate ES search quality")
    parser.add_argument("--auto", default="eval/auto_queries.jsonl")
    parser.add_argument("--gold", default="eval/gold_queries.jsonl")
    parser.add_argument("--k", type=int, nargs="+", default=[10, 50])
    parser.add_argument("--max-queries", type=int, default=0)
    parser.add_argument("--es-url", default=ES_URL)
    parser.add_argument("--report", default="eval/results/report_es.json")
    args = parser.parse_args()

    queries = load_queries(Path(args.auto)) + load_queries(Path(args.gold))
    if not queries:
        sys.exit("No queries found.")
    if args.max_queries > 0:
        queries = queries[:args.max_queries]

    print(f"Loaded {len(queries)} queries, k={args.k}")

    indexed: list[tuple[int, str, set[int]]] = []
    for i, q in enumerate(queries):
        qt = q.get("query", "")
        rel = set(q.get("relevant_ids", []))
        if qt and rel:
            indexed.append((i, qt, rel))
    print(f"Valid queries: {len(indexed)}")

    methods = {
        "ES kazsearch_stem": ["title^2", "body"],
        "ES standard (no stemming)": ["title.standard^2", "body.standard"],
    }

    results = {}
    for label, fields in methods.items():
        results[label] = evaluate_method(label, indexed, args.k, args.es_url, fields)

    print_report(results, args.k, len(indexed))

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {}
    for label, data in results.items():
        serializable[label] = {
            "summary": {str(k): v for k, v in data["summary"].items()},
            "elapsed_s": round(data["elapsed"], 2),
        }
    serializable["num_queries"] = len(indexed)
    serializable["ks"] = args.k
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
