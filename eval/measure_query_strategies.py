"""
Measure how query construction changes PostgreSQL FTS quality on gold_v2.

Three strategies run against the same index, the same tsvector column and the
same ranking function (ts_rank_cd). Only the tsquery differs:

  and     websearch_to_tsquery: every term must match
  or      the stemmed terms joined with |
  and_or  the strict query first, then OR-ranked results top up a short list

Usage:
    python3 eval/measure_query_strategies.py --container pg-kazsearch \
        --gold eval/gold_queries_v2.jsonl --report eval/results/query_strategies.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_eval import (
    BATCH,
    bootstrap_ci,
    load_queries,
    mrr,
    ndcg_at_k,
    precision_at_k,
    psql_stdin,
    qlit,
    recall_at_k,
    resolve_relevant_urls,
)

QUERY_SQL = {
    "and": """
    SELECT id FROM articles
    WHERE fts_vector @@ websearch_to_tsquery('kazakh_cfg', qs.query)
    ORDER BY ts_rank_cd(fts_vector, websearch_to_tsquery('kazakh_cfg', qs.query)) DESC, id
    LIMIT {k}
""",
    "or": """
    SELECT a.id FROM articles a,
         (SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | ')) AS tsq
          FROM unnest(to_tsvector('kazakh_cfg', qs.query))) q
    WHERE a.fts_vector @@ q.tsq
    ORDER BY ts_rank_cd(a.fts_vector, q.tsq) DESC, a.id
    LIMIT {k}
""",
    "and_or": """
    WITH q AS (
        SELECT websearch_to_tsquery('kazakh_cfg', qs.query) AS strict_q,
               (SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | '))
                  FROM unnest(to_tsvector('kazakh_cfg', qs.query))) AS relaxed_q
    ),
    strict AS (
        SELECT a.id, ts_rank_cd(a.fts_vector, q.strict_q) AS r
        FROM articles a, q
        WHERE a.fts_vector @@ q.strict_q
        ORDER BY r DESC, a.id
        LIMIT {k}
    ),
    relaxed AS (
        SELECT a.id, ts_rank_cd(a.fts_vector, q.relaxed_q) AS r
        FROM articles a, q
        WHERE a.fts_vector @@ q.relaxed_q
          AND a.id NOT IN (SELECT id FROM strict)
        ORDER BY r DESC, a.id
        LIMIT {k}
    )
    SELECT id FROM (
        SELECT id, 1 AS tier, r FROM strict
        UNION ALL
        SELECT id, 2 AS tier, r FROM relaxed
    ) u
    ORDER BY tier, r DESC, id
    LIMIT {k}
""",
}


def batch_search(strategy: str, queries: list[tuple[int, str]], k: int,
                 container: str, db: str, user: str) -> dict[int, list[int]]:
    values = ",\n".join(f"({qid}, '{qlit(qt)}')" for qid, qt in queries)
    inner = QUERY_SQL[strategy].format(k=k)
    sql = f"WITH qs(qid, query) AS (VALUES {values})\nSELECT qid, id FROM qs, LATERAL ({inner}) sub;"
    results: dict[int, list[int]] = {qid: [] for qid, _ in queries}
    for line in psql_stdin(sql, container, db, user).strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            results[int(parts[0])].append(int(parts[1]))
    return results


def evaluate(strategy: str, indexed: list[tuple[int, str, set[int]]], ks: list[int],
             container: str, db: str, user: str) -> dict:
    max_k = max(ks)
    hits: dict[int, list[int]] = {}
    for start in range(0, len(indexed), BATCH):
        batch = [(idx, qt) for idx, qt, _ in indexed[start:start + BATCH]]
        hits.update(batch_search(strategy, batch, max_k, container, db, user))

    per_k = {k: {"precision": [], "recall": [], "mrr": [], "ndcg": []} for k in ks}
    empty = 0
    for idx, _, relevant in indexed:
        got = hits.get(idx, [])
        if not got:
            empty += 1
        for k in ks:
            per_k[k]["precision"].append(precision_at_k(got, relevant, k))
            per_k[k]["recall"].append(recall_at_k(got, relevant, k))
            per_k[k]["mrr"].append(mrr(got[:k], relevant))
            per_k[k]["ndcg"].append(ndcg_at_k(got, relevant, k))

    k0 = ks[0]
    return {
        "metrics": {
            str(k): {name: round(sum(v) / len(v), 4) for name, v in m.items()}
            for k, m in per_k.items()
        },
        "ci95": {
            f"recall@{k0}": bootstrap_ci(per_k[k0]["recall"]),
            f"mrr@{k0}": bootstrap_ci(per_k[k0]["mrr"]),
        },
        "no_result_queries": empty,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", default="eval/gold_queries_v2.jsonl")
    ap.add_argument("--k", type=int, nargs="+", default=[10, 50])
    ap.add_argument("--container", default="pg-kazsearch")
    ap.add_argument("--db", default="kazsearch")
    ap.add_argument("--user", default="postgres")
    ap.add_argument("--report", default="eval/results/query_strategies.json")
    args = ap.parse_args()

    queries = load_queries(Path(args.gold))
    resolve_relevant_urls(queries, args.container, args.db, args.user)
    indexed = [
        (i, q["query"], set(q["relevant_ids"]))
        for i, q in enumerate(queries)
        if q.get("query") and q.get("relevant_ids")
    ]
    print(f"gold_v2 queries with relevant documents: {len(indexed)}")

    report = {
        "gold": args.gold,
        "num_queries": len(indexed),
        "ks": args.k,
        "strategies": {},
    }
    for strategy in QUERY_SQL:
        r = evaluate(strategy, indexed, args.k, args.container, args.db, args.user)
        report["strategies"][strategy] = r
        m10 = r["metrics"][str(args.k[0])]
        print(f"{strategy:7} P@10 {m10['precision']:.3f}  R@10 {m10['recall']:.3f}  "
              f"MRR@10 {m10['mrr']:.3f}  R@{args.k[-1]} {r['metrics'][str(args.k[-1])]['recall']:.3f}  "
              f"no results {r['no_result_queries']}/{len(indexed)}")

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Report saved to {out}")


if __name__ == "__main__":
    main()
