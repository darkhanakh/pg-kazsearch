"""
Evaluate pg_kazsearch FTS vs pg_trgm on the article corpus.

Runs all queries in batched SQL calls (not one subprocess per query),
computes Precision@k, Recall@k, MRR, and nDCG@k, then prints a
comparison table and writes a JSON report.

Usage:
    python3 eval/run_eval.py --auto eval/auto_queries.jsonl \
                             --gold eval/gold_queries.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

CONTAINER = "pg-kazsearch"
DB = "kazsearch"
USER = "postgres"
BATCH = 200
TRGM_BATCH = 25


def qlit(s: str) -> str:
    return s.replace("'", "''").replace("\\", "\\\\")


def psql_stdin(sql: str, container: str, db: str, user: str) -> str:
    cmd = ["docker", "exec", "-i", container, "psql", "-U", user, "-d", db, "-At", "-F", "\t"]
    result = subprocess.run(cmd, input=sql, text=True, capture_output=True, timeout=300)
    if result.returncode != 0:
        print(f"  WARN psql: {result.stderr[:200]}", file=sys.stderr)
    return result.stdout


def batch_search_fts(queries: list[tuple[int, str]], k: int,
                     container: str, db: str, user: str) -> dict[int, list[int]]:
    if not queries:
        return {}

    values = ",\n".join(f"({qid}, '{qlit(qt)}')" for qid, qt in queries)
    sql = f"""
WITH qs(qid, query) AS (VALUES {values})
SELECT qid, id
FROM qs,
LATERAL (
    SELECT id
    FROM articles
    WHERE fts_vector @@ websearch_to_tsquery('kazakh_cfg', qs.query)
    ORDER BY ts_rank_cd(fts_vector, websearch_to_tsquery('kazakh_cfg', qs.query)) DESC
    LIMIT {k}
) sub;
"""
    out = psql_stdin(sql, container, db, user)
    results: dict[int, list[int]] = {qid: [] for qid, _ in queries}
    for line in out.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            try:
                results.setdefault(int(parts[0]), []).append(int(parts[1]))
            except ValueError:
                pass
    return results


def batch_search_trgm(queries: list[tuple[int, str]], k: int, threshold: float,
                      container: str, db: str, user: str) -> dict[int, list[int]]:
    if not queries:
        return {}

    values = ",\n".join(f"({qid}, '{qlit(qt)}')" for qid, qt in queries)
    sql = f"""
SET pg_trgm.similarity_threshold = {threshold};
WITH qs(qid, query) AS (VALUES {values})
SELECT qid, id
FROM qs,
LATERAL (
    SELECT id
    FROM articles
    WHERE title % qs.query
    ORDER BY similarity(title, qs.query) DESC
    LIMIT {k}
) sub;
"""
    out = psql_stdin(sql, container, db, user)
    results: dict[int, list[int]] = {qid: [] for qid, _ in queries}
    for line in out.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            try:
                results.setdefault(int(parts[0]), []).append(int(parts[1]))
            except ValueError:
                pass
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


def evaluate(queries: list[dict], ks: list[int], trgm_thresholds: list[float],
             container: str, db: str, user: str,
             trgm_sample: int = 0) -> dict:
    max_k = max(ks)
    t0 = time.monotonic()

    indexed: list[tuple[int, str, set[int]]] = []
    for i, q in enumerate(queries):
        qt = q.get("query", "")
        rel = set(q.get("relevant_ids", []))
        if qt and rel:
            indexed.append((i, qt, rel))

    print(f"  Running FTS searches ({len(indexed)} queries)...", end="", flush=True)
    fts_all: dict[int, list[int]] = {}
    for batch_start in range(0, len(indexed), BATCH):
        batch = [(idx, qt) for idx, qt, _ in indexed[batch_start:batch_start + BATCH]]
        fts_all.update(batch_search_fts(batch, max_k, container, db, user))
    fts_elapsed = time.monotonic() - t0
    print(f" {fts_elapsed:.1f}s")

    trgm_indexed = indexed
    if trgm_sample > 0 and trgm_sample < len(indexed):
        trgm_indexed = random.sample(indexed, trgm_sample)
        print(f"  Trigram: sampling {trgm_sample}/{len(indexed)} queries")
    trgm_idx_set = {idx for idx, _, _ in trgm_indexed}

    trgm_all: dict[float, dict[int, list[int]]] = {}
    for t in trgm_thresholds:
        t1 = time.monotonic()
        print(f"  Running trigram searches (threshold={t:.2f})...", flush=True)
        trgm_all[t] = {}
        n_batches = (len(trgm_indexed) + TRGM_BATCH - 1) // TRGM_BATCH
        for bi, batch_start in enumerate(range(0, len(trgm_indexed), TRGM_BATCH)):
            batch = [(idx, qt) for idx, qt, _ in trgm_indexed[batch_start:batch_start + TRGM_BATCH]]
            trgm_all[t].update(batch_search_trgm(batch, max_k, t, container, db, user))
            if (bi + 1) % 10 == 0 or bi + 1 == n_batches:
                print(f"    batch {bi+1}/{n_batches}  ({time.monotonic()-t1:.0f}s)", flush=True)
        print(f"  trigram t={t:.2f} done in {time.monotonic() - t1:.1f}s")

    fts_metrics: dict[int, dict[str, list[float]]] = {}
    fts_on_trgm_sample: dict[int, dict[str, list[float]]] = {}
    for k_val in ks:
        fts_metrics[k_val] = {"precision": [], "recall": [], "mrr": [], "ndcg": []}
        fts_on_trgm_sample[k_val] = {"precision": [], "recall": [], "mrr": [], "ndcg": []}

    trgm_by_threshold: dict[float, dict[int, dict[str, list[float]]]] = {}
    for t in trgm_thresholds:
        trgm_by_threshold[t] = {}
        for k_val in ks:
            trgm_by_threshold[t][k_val] = {"precision": [], "recall": [], "mrr": [], "ndcg": []}

    for idx, qt, relevant in indexed:
        fts_results = fts_all.get(idx, [])
        for k_val in ks:
            fts_metrics[k_val]["precision"].append(precision_at_k(fts_results, relevant, k_val))
            fts_metrics[k_val]["recall"].append(recall_at_k(fts_results, relevant, k_val))
            fts_metrics[k_val]["mrr"].append(mrr(fts_results[:k_val], relevant))
            fts_metrics[k_val]["ndcg"].append(ndcg_at_k(fts_results, relevant, k_val))

        if idx not in trgm_idx_set:
            continue

        for k_val in ks:
            fts_on_trgm_sample[k_val]["precision"].append(precision_at_k(fts_results, relevant, k_val))
            fts_on_trgm_sample[k_val]["recall"].append(recall_at_k(fts_results, relevant, k_val))
            fts_on_trgm_sample[k_val]["mrr"].append(mrr(fts_results[:k_val], relevant))
            fts_on_trgm_sample[k_val]["ndcg"].append(ndcg_at_k(fts_results, relevant, k_val))

        for t in trgm_thresholds:
            trgm_results = trgm_all[t].get(idx, [])
            for k_val in ks:
                trgm_by_threshold[t][k_val]["precision"].append(
                    precision_at_k(trgm_results, relevant, k_val))
                trgm_by_threshold[t][k_val]["recall"].append(
                    recall_at_k(trgm_results, relevant, k_val))
                trgm_by_threshold[t][k_val]["mrr"].append(
                    mrr(trgm_results[:k_val], relevant))
                trgm_by_threshold[t][k_val]["ndcg"].append(
                    ndcg_at_k(trgm_results, relevant, k_val))

    def _avg(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    def _summarize(m: dict[int, dict[str, list[float]]]) -> dict:
        out = {}
        for k_val in ks:
            out[k_val] = {name: round(_avg(vals), 4) for name, vals in m[k_val].items()}
        return out

    fts_summary = _summarize(fts_metrics)
    fts_sample_summary = _summarize(fts_on_trgm_sample)

    best_f1 = -1.0
    best_trgm_threshold = trgm_thresholds[0]
    best_trgm_metrics: dict[int, dict[str, list[float]]] = trgm_by_threshold[trgm_thresholds[0]]
    for t in trgm_thresholds:
        p = _avg(trgm_by_threshold[t][ks[0]]["precision"])
        r = _avg(trgm_by_threshold[t][ks[0]]["recall"])
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_trgm_threshold = t
            best_trgm_metrics = trgm_by_threshold[t]

    trgm_summary = _summarize(best_trgm_metrics)

    elapsed = time.monotonic() - t0
    print(f"  Total eval time: {elapsed:.1f}s")

    return {
        "fts": fts_summary,
        "fts_on_sample": fts_sample_summary,
        "trgm": trgm_summary,
        "trgm_threshold": best_trgm_threshold,
        "num_queries": len(indexed),
        "num_trgm_queries": len(trgm_indexed),
        "ks": ks,
    }


def print_report(result: dict):
    ks = result["ks"]
    n_fts = result["num_queries"]
    n_trgm = result.get("num_trgm_queries", n_fts)

    print(f"\nFTS queries evaluated: {n_fts}")
    print(f"Trigram queries evaluated: {n_trgm}")
    print(f"Best trigram threshold: {result['trgm_threshold']:.2f}")

    header = f"{'':28}"
    for k_val in ks:
        header += f"  {'P@' + str(k_val):>8}  {'R@' + str(k_val):>8}  {'MRR@' + str(k_val):>8}  {'nDCG@' + str(k_val):>8}"
    print()
    print(f"=== All {n_fts} queries (FTS only) ===")
    print(header)
    print("-" * len(header))
    row = f"{'pg_kazsearch (FTS)':28}"
    for k_val in ks:
        m = result["fts"][k_val]
        row += f"  {m['precision']:>8.4f}  {m['recall']:>8.4f}  {m['mrr']:>8.4f}  {m['ndcg']:>8.4f}"
    print(row)

    print()
    print(f"=== Head-to-head on {n_trgm}-query sample ===")
    print(header)
    print("-" * len(header))
    for label, key in [("pg_kazsearch (FTS)", "fts_on_sample"), ("pg_trgm", "trgm")]:
        row = f"{label:28}"
        for k_val in ks:
            m = result[key][k_val]
            row += f"  {m['precision']:>8.4f}  {m['recall']:>8.4f}  {m['mrr']:>8.4f}  {m['ndcg']:>8.4f}"
        print(row)

    print()
    k0 = ks[0]
    fts_r = result["fts_on_sample"][k0]["recall"]
    trgm_r = result["trgm"][k0]["recall"]
    if fts_r > trgm_r:
        print(f"pg_kazsearch wins on Recall@{k0} by +{fts_r - trgm_r:.4f}")
    elif trgm_r > fts_r:
        print(f"pg_trgm wins on Recall@{k0} by +{trgm_r - fts_r:.4f}")
    else:
        print(f"Tie on Recall@{k0}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate FTS vs trigram search quality")
    parser.add_argument("--auto", default="eval/auto_queries.jsonl", help="Auto-generated queries")
    parser.add_argument("--gold", default="eval/gold_queries.jsonl", help="Manual gold queries")
    parser.add_argument("--k", type=int, nargs="+", default=[10, 50], help="k values for metrics")
    parser.add_argument("--trgm-thresholds", type=float, nargs="+",
                        default=[0.2, 0.3, 0.4],
                        help="Trigram similarity thresholds to sweep")
    parser.add_argument("--max-queries", type=int, default=0, help="Limit queries (0=all)")
    parser.add_argument("--trgm-sample", type=int, default=500,
                        help="Run trigram on a random sample of N queries (0=all)")
    parser.add_argument("--container", default=CONTAINER)
    parser.add_argument("--db", default=DB)
    parser.add_argument("--user", default=USER)
    parser.add_argument("--report", default="eval/results/report.json")
    args = parser.parse_args()

    queries = load_queries(Path(args.auto)) + load_queries(Path(args.gold))
    if not queries:
        sys.exit("No queries found. Run generate_queries.py first.")

    if args.max_queries > 0:
        queries = queries[: args.max_queries]

    print(f"Loaded {len(queries)} queries")
    print(f"k values: {args.k}")
    print(f"Trigram thresholds: {args.trgm_thresholds}")

    result = evaluate(queries, args.k, args.trgm_thresholds,
                      args.container, args.db, args.user,
                      trgm_sample=args.trgm_sample)
    print_report(result)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        "fts": {str(k): v for k, v in result["fts"].items()},
        "fts_on_sample": {str(k): v for k, v in result["fts_on_sample"].items()},
        "trgm": {str(k): v for k, v in result["trgm"].items()},
        "trgm_threshold": result["trgm_threshold"],
        "num_queries": result["num_queries"],
        "num_trgm_queries": result.get("num_trgm_queries", result["num_queries"]),
        "ks": result["ks"],
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
