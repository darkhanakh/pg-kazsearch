"""
Hybrid Kazakh search benchmark inside one PostgreSQL.

Loads the article corpus, builds a GIN (ts_rank baseline), two pg_textsearch
BM25 indexes (kazakh_cfg and simple) and a pgvector HNSW index, embeds the
documents and gold queries, and scores each system on gold_v2:

  ts_rank_cd         strict websearch AND, topped up with OR (README baseline)
  bm25_kazakh        pg_textsearch BM25, text_config='kazakh_cfg'
  bm25_simple        pg_textsearch BM25, text_config='simple' (no stemming)
  dense_<model>      pgvector cosine, HNSW
  rrf_<model>        reciprocal rank fusion of bm25_kazakh and dense, in SQL

Every system is evaluated on its top-DEPTH list. Metrics carry paired
bootstrap 95% CIs of (system - ts_rank_cd baseline).

Usage:
    just hybrid-up
    just hybrid-eval
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import psycopg

from run_eval import mrr, ndcg_at_k, recall_at_k

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:55439/kazsearch"
METRICS = ("R@10", "MRR@10", "nDCG@10", "R@50")
README_BASELINE = {"R@10": 0.595, "MRR@10": 0.753, "R@50": 0.869}
BM25_KAZ_IDX = "idx_articles_bm25_kaz"
BM25_SIMPLE_IDX = "idx_articles_bm25_simple"
BM25_KAZ_T2_IDX = "idx_articles_bm25_kaz_t2"


@dataclass(frozen=True)
class EmbedModel:
    tag: str
    hf_id: str
    query_prefix: str = ""
    doc_prefix: str = ""
    routed: bool = False

    @property
    def column(self) -> str:
        return f"emb_{self.tag}"


MODELS = {
    "bge_m3": EmbedModel("bge_m3", "BAAI/bge-m3"),
    "kaz_embedder": EmbedModel("kaz_embedder", "BekbolatShanakbay/kaz-embedder", routed=True),
}


# ── Data loading ─────────────────────────────────────────────────────────

SCHEMA_SQL = """
DROP TABLE IF EXISTS articles CASCADE;
CREATE TABLE articles (
    id          serial PRIMARY KEY,
    url         text UNIQUE NOT NULL,
    title       text NOT NULL,
    body        text NOT NULL,
    doc         text GENERATED ALWAYS AS (title || E'\\n' || body) STORED,
    doc_simple  text GENERATED ALWAYS AS (title || E'\\n' || body) STORED,
    doc_t2      text GENERATED ALWAYS AS (title || E'\\n' || title || E'\\n' || body) STORED,
    fts_vector  tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('kazakh_cfg', title), 'A') ||
        setweight(to_tsvector('kazakh_cfg', body), 'B')
    ) STORED
);
"""


def load_corpus(conn: psycopg.Connection, path: Path) -> int:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                a = json.loads(line)
                rows.append((a["url"], a["title"], a["body"]))
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
        cur.executemany(
            "INSERT INTO articles (url, title, body) VALUES (%s, %s, %s) ON CONFLICT (url) DO NOTHING",
            rows,
        )
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM articles")
        return cur.fetchone()[0]


def load_gold(conn: psycopg.Connection, path: Path) -> list[dict]:
    queries = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    with conn.cursor() as cur:
        cur.execute("SELECT url, id FROM articles")
        id_of = dict(cur.fetchall())
    out = []
    for q in queries:
        rel = {id_of[u] for u in q.get("relevant_urls", []) if u in id_of}
        if q.get("query") and rel:
            out.append({"query": q["query"], "relevant": rel})
    return out


def build_text_indexes(conn: psycopg.Connection) -> dict[str, float]:
    steps = {
        "gin": "CREATE INDEX idx_articles_fts ON articles USING GIN (fts_vector)",
        "bm25_kazakh": f"CREATE INDEX {BM25_KAZ_IDX} ON articles USING bm25(doc) WITH (text_config='public.kazakh_cfg')",
        "bm25_simple": f"CREATE INDEX {BM25_SIMPLE_IDX} ON articles USING bm25(doc_simple) WITH (text_config='simple')",
        "bm25_kazakh_title2": f"CREATE INDEX {BM25_KAZ_T2_IDX} ON articles USING bm25(doc_t2) WITH (text_config='public.kazakh_cfg')",
    }
    timings = {}
    with conn.cursor() as cur:
        cur.execute("SET max_parallel_maintenance_workers = 0")
        for name, sql in steps.items():
            t0 = time.monotonic()
            cur.execute(sql)
            timings[name] = round(time.monotonic() - t0, 3)
    conn.commit()
    return timings


# ── Embeddings ───────────────────────────────────────────────────────────

def pick_device(requested: str) -> str:
    if requested != "auto":
        return requested
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def encode(model, spec: EmbedModel, texts: list[str], kind: str, batch_size: int) -> np.ndarray:
    prefix = spec.query_prefix if kind == "query" else spec.doc_prefix
    texts = [prefix + t for t in texts]
    if spec.routed:
        fn = model.encode_query if kind == "query" else model.encode_document
        return fn(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=kind == "doc")
    return model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                        show_progress_bar=kind == "doc")


def embed_cached(spec: EmbedModel, texts: list[str], kind: str, max_length: int,
                 cache_dir: Path, device: str, batch_size: int, state: dict) -> tuple[np.ndarray, dict]:
    digest = hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:16]
    stem = f"{spec.tag}_{kind}_L{max_length}_{digest}"
    npy, meta_path = cache_dir / f"{stem}.npy", cache_dir / f"{stem}.json"
    if npy.exists() and meta_path.exists():
        return np.load(npy), {**json.loads(meta_path.read_text()), "cache_hit": True}

    if "model" not in state:
        from sentence_transformers import SentenceTransformer

        state["model"] = SentenceTransformer(spec.hf_id, device=device)
        state["model"].max_seq_length = max_length
    t0 = time.monotonic()
    vecs = encode(state["model"], spec, texts, kind, batch_size).astype(np.float32)
    meta = {"seconds": round(time.monotonic() - t0, 1), "device": device, "n": len(texts),
            "dim": int(vecs.shape[1]), "max_length": max_length, "hf_id": spec.hf_id}
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(npy, vecs)
    meta_path.write_text(json.dumps(meta))
    return vecs, {**meta, "cache_hit": False}


def vec_literal(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def store_embeddings(conn: psycopg.Connection, spec: EmbedModel, ids: list[int], vecs: np.ndarray,
                     hnsw_m: int, hnsw_ef_construction: int) -> float:
    dim = vecs.shape[1]
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE articles ADD COLUMN {spec.column} vector({dim})")
        cur.executemany(
            f"UPDATE articles SET {spec.column} = %s::vector WHERE id = %s",
            [(vec_literal(v), i) for i, v in zip(ids, vecs)],
        )
        t0 = time.monotonic()
        cur.execute(
            f"CREATE INDEX idx_articles_{spec.column}_hnsw ON articles USING hnsw "
            f"({spec.column} vector_cosine_ops) WITH (m = {hnsw_m}, ef_construction = {hnsw_ef_construction})"
        )
        elapsed = time.monotonic() - t0
    conn.commit()
    return round(elapsed, 3)


# ── Systems ──────────────────────────────────────────────────────────────

def sql_ts_rank(depth: int) -> str:
    return f"""
WITH q AS (
    SELECT websearch_to_tsquery('kazakh_cfg', %(q)s) AS strict_q,
           (SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | '))
              FROM unnest(to_tsvector('kazakh_cfg', %(q)s))) AS relaxed_q
),
strict AS (
    SELECT a.id, ts_rank_cd(a.fts_vector, q.strict_q) AS r
    FROM articles a, q
    WHERE a.fts_vector @@ q.strict_q
    ORDER BY r DESC, a.id
    LIMIT {depth}
),
relaxed AS (
    SELECT a.id, ts_rank_cd(a.fts_vector, q.relaxed_q) AS r
    FROM articles a, q
    WHERE a.fts_vector @@ q.relaxed_q
      AND a.id NOT IN (SELECT id FROM strict)
    ORDER BY r DESC, a.id
    LIMIT {depth}
)
SELECT id FROM (
    SELECT id, 1 AS tier, r FROM strict
    UNION ALL
    SELECT id, 2 AS tier, r FROM relaxed
) u
ORDER BY tier, r DESC, id
LIMIT {depth}
"""


def sql_bm25(index: str, column: str, depth: int) -> str:
    return f"""
SELECT id FROM articles
ORDER BY {column} <@> to_bm25query(%(q)s, '{index}'), id
LIMIT {depth}
"""


def sql_dense(column: str, depth: int) -> str:
    return f"""
SELECT id FROM articles
ORDER BY {column} <=> %(qvec)s::vector, id
LIMIT {depth}
"""


def sql_rrf(column: str, depth: int, rrf_k: int) -> str:
    return f"""
WITH bm AS (
    SELECT id, row_number() OVER () AS rnk
    FROM (SELECT id FROM articles
          ORDER BY doc <@> to_bm25query(%(q)s, '{BM25_KAZ_IDX}') LIMIT {depth}) t
),
dn AS (
    SELECT id, row_number() OVER () AS rnk
    FROM (SELECT id FROM articles
          ORDER BY {column} <=> %(qvec)s::vector LIMIT {depth}) t
)
SELECT COALESCE(bm.id, dn.id) AS id
FROM bm FULL OUTER JOIN dn ON bm.id = dn.id
ORDER BY COALESCE(1.0 / ({rrf_k} + bm.rnk), 0) + COALESCE(1.0 / ({rrf_k} + dn.rnk), 0) DESC,
         COALESCE(bm.id, dn.id)
LIMIT {depth}
"""


def sql_rrf_ts_dense(column: str, depth: int, rrf_k: int) -> str:
    base = sql_ts_rank(depth)
    return f"""
WITH ts AS (
    SELECT id, row_number() OVER () AS rnk FROM ({base}) t0
),
dn AS (
    SELECT id, row_number() OVER () AS rnk
    FROM (SELECT id FROM articles
          ORDER BY {column} <=> %(qvec)s::vector LIMIT {depth}) t
)
SELECT COALESCE(ts.id, dn.id) AS id
FROM ts FULL OUTER JOIN dn ON ts.id = dn.id
ORDER BY COALESCE(1.0 / ({rrf_k} + ts.rnk), 0) + COALESCE(1.0 / ({rrf_k} + dn.rnk), 0) DESC,
         COALESCE(ts.id, dn.id)
LIMIT {depth}
"""


def run_system(cur: psycopg.Cursor, sql: str, queries: list[dict], qvecs: np.ndarray | None,
               warmup: int = 3) -> tuple[list[list[int]], float]:
    def params(i: int) -> dict:
        p = {"q": queries[i]["query"]}
        if qvecs is not None:
            p["qvec"] = vec_literal(qvecs[i])
        return p

    for i in range(min(warmup, len(queries))):
        cur.execute(sql, params(i))
        cur.fetchall()
    results, times = [], []
    for i in range(len(queries)):
        t0 = time.perf_counter()
        cur.execute(sql, params(i))
        results.append([r[0] for r in cur.fetchall()])
        times.append((time.perf_counter() - t0) * 1000)
    return results, round(statistics.median(times), 2)


def per_query_metrics(results: list[list[int]], queries: list[dict]) -> dict[str, np.ndarray]:
    out = {m: [] for m in METRICS}
    for res, q in zip(results, queries):
        rel = q["relevant"]
        out["R@10"].append(recall_at_k(res, rel, 10))
        out["MRR@10"].append(mrr(res[:10], rel))
        out["nDCG@10"].append(ndcg_at_k(res, rel, 10))
        out["R@50"].append(recall_at_k(res, rel, 50))
    return {m: np.array(v) for m, v in out.items()}


def bootstrap(per_q: dict[str, dict[str, np.ndarray]], baseline: str, n_boot: int, seed: int) -> dict:
    n = len(next(iter(next(iter(per_q.values())).values())))
    idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
    summary = {}
    for name, metrics in per_q.items():
        entry = {"metrics": {}, "ci95": {}, "delta_vs_baseline": {}, "delta_ci95": {}, "delta_p_le_0": {}}
        for m, vals in metrics.items():
            boot_mean = vals[idx].mean(axis=1)
            entry["metrics"][m] = round(float(vals.mean()), 4)
            entry["ci95"][m] = [round(float(x), 4) for x in np.percentile(boot_mean, [2.5, 97.5])]
            if name != baseline:
                diff = (vals - per_q[baseline][m])
                boot_diff = diff[idx].mean(axis=1)
                entry["delta_vs_baseline"][m] = round(float(diff.mean()), 4)
                entry["delta_ci95"][m] = [round(float(x), 4) for x in np.percentile(boot_diff, [2.5, 97.5])]
                entry["delta_p_le_0"][m] = round(float((boot_diff <= 0).mean()), 4)
        summary[name] = entry
    return summary


def overlap_with_exact(conn: psycopg.Connection, column: str, queries: list[dict],
                       qvecs: np.ndarray, depth: int) -> float:
    """Mean top-`depth` overlap between the HNSW scan and an exact scan."""
    sql = sql_dense(column, depth)
    scores = []
    with conn.cursor() as cur:
        for i, q in enumerate(queries):
            p = {"q": q["query"], "qvec": vec_literal(qvecs[i])}
            cur.execute("SET enable_indexscan = off")
            cur.execute(sql, p)
            exact = [r[0] for r in cur.fetchall()]
            cur.execute("SET enable_indexscan = on")
            cur.execute(sql, p)
            approx = [r[0] for r in cur.fetchall()]
            scores.append(len(set(exact) & set(approx)) / max(len(exact), 1))
    return round(float(np.mean(scores)), 4)


def explain_node(cur: psycopg.Cursor, sql: str, params: dict) -> str:
    cur.execute("EXPLAIN " + sql, params)
    plan = "\n".join(r[0] for r in cur.fetchall())
    return re.sub(r"\[-?[0-9][0-9.,e-]*\]", "[...]", plan)


# ── Reporting ────────────────────────────────────────────────────────────

def print_table(summary: dict, baseline: str, latencies: dict) -> None:
    print(f"\n{'system':<28}" + "".join(f"{m:>26}" for m in METRICS) + f"{'ms/q':>8}")
    for name, e in summary.items():
        cells = "".join(
            f"{e['metrics'][m]:>8.3f} [{e['ci95'][m][0]:.3f},{e['ci95'][m][1]:.3f}]".rjust(26) for m in METRICS
        )
        print(f"{name:<28}{cells}{latencies[name]:>8}")
    print(f"\npaired bootstrap delta vs {baseline} (95% CI)")
    for name, e in summary.items():
        if name == baseline:
            continue
        cells = "".join(
            f"{e['delta_vs_baseline'][m]:>+8.3f} [{e['delta_ci95'][m][0]:+.3f},{e['delta_ci95'][m][1]:+.3f}]".rjust(26)
            for m in METRICS
        )
        print(f"{name:<28}{cells}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Hybrid (BM25 + dense + RRF) Kazakh search eval inside PostgreSQL")
    ap.add_argument("--dsn", default=DEFAULT_DSN)
    ap.add_argument("--corpus", type=Path, default=Path("data/corpus/articles.jsonl"))
    ap.add_argument("--gold", type=Path, default=Path("eval/gold_queries_v2.jsonl"))
    ap.add_argument("--models", nargs="+", default=["bge_m3"], choices=sorted(MODELS))
    ap.add_argument("--max-length", type=int, default=512, help="document token truncation")
    ap.add_argument("--query-max-length", type=int, default=64)
    ap.add_argument("--device", default="auto", help="auto | mps | cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--cache-dir", type=Path, default=Path("data/embeddings"))
    ap.add_argument("--depth", type=int, default=100, help="list depth fed to metrics and RRF")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--hnsw-m", type=int, default=16)
    ap.add_argument("--hnsw-ef-construction", type=int, default=64)
    ap.add_argument("--hnsw-ef-search", type=int, default=200)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--report", type=Path, default=Path("eval/results/report_hybrid.json"))
    args = ap.parse_args()

    device = pick_device(args.device)
    conn = psycopg.connect(args.dsn)
    with conn.cursor() as cur:
        cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname IN "
                    "('pg_kazsearch','pg_textsearch','vector')")
        ext_versions = dict(cur.fetchall())
        cur.execute("SHOW server_version")
        pg_version = cur.fetchone()[0]
    if len(ext_versions) != 3:
        sys.exit(f"Missing extensions, found {ext_versions}. Run `just hybrid-up`.")

    print(f"Loading corpus from {args.corpus}")
    n_docs = load_corpus(conn, args.corpus)
    queries = load_gold(conn, args.gold)
    print(f"  {n_docs} articles, {len(queries)} gold queries")

    t_idx = build_text_indexes(conn)
    print(f"  text index build seconds: {t_idx}")

    with conn.cursor() as cur:
        cur.execute("SELECT id, title, body FROM articles ORDER BY id")
        rows = cur.fetchall()
    ids = [r[0] for r in rows]
    doc_texts = [f"{t}\n{b}" for _, t, b in rows]
    query_texts = [q["query"] for q in queries]

    model_meta: dict[str, dict] = {}
    qvecs_by_model: dict[str, np.ndarray] = {}
    for tag in args.models:
        spec = MODELS[tag]
        state: dict = {}
        print(f"Embedding with {spec.hf_id} on {device} (doc max_length={args.max_length})")
        dvecs, dmeta = embed_cached(spec, doc_texts, "doc", args.max_length, args.cache_dir,
                                    device, args.batch_size, state)
        if "model" in state:
            state["model"].max_seq_length = args.query_max_length
        qvecs, qmeta = embed_cached(spec, query_texts, "query", args.query_max_length, args.cache_dir,
                                    device, args.batch_size, state)
        hnsw_s = store_embeddings(conn, spec, ids, dvecs, args.hnsw_m, args.hnsw_ef_construction)
        model_meta[tag] = {"hf_id": spec.hf_id, "dim": dmeta["dim"], "doc_max_length": args.max_length,
                           "query_max_length": args.query_max_length, "doc_embedding": dmeta,
                           "query_embedding": qmeta, "hnsw_build_seconds": hnsw_s}
        qvecs_by_model[tag] = qvecs
        print(f"  docs: {dmeta['seconds']}s ({'cached' if dmeta['cache_hit'] else 'computed'}), "
              f"queries: {qmeta['seconds']}s, HNSW build {hnsw_s}s")

    systems: dict[str, tuple[str, str, np.ndarray | None]] = {
        "ts_rank_cd (AND+OR)": ("strict websearch AND, OR top-up, ts_rank_cd", sql_ts_rank(args.depth), None),
        "bm25_kazakh": ("pg_textsearch BM25, kazakh_cfg", sql_bm25(BM25_KAZ_IDX, "doc", args.depth), None),
        "bm25_simple": ("pg_textsearch BM25, simple", sql_bm25(BM25_SIMPLE_IDX, "doc_simple", args.depth), None),
        "bm25_kazakh_title2": ("BM25 kazakh_cfg, title counted twice",
                               sql_bm25(BM25_KAZ_T2_IDX, "doc_t2", args.depth), None),
    }
    for tag in args.models:
        col = MODELS[tag].column
        qv = qvecs_by_model[tag]
        systems[f"dense_{tag}"] = (f"pgvector cosine HNSW, {MODELS[tag].hf_id}", sql_dense(col, args.depth), qv)
        systems[f"rrf_{tag}"] = (f"RRF(k={args.rrf_k}) of bm25_kazakh + dense_{tag}",
                                 sql_rrf(col, args.depth, args.rrf_k), qv)
        systems[f"rrf_ts_{tag}"] = (f"RRF(k={args.rrf_k}) of ts_rank_cd (AND+OR) + dense_{tag}",
                                    sql_rrf_ts_dense(col, args.depth, args.rrf_k), qv)

    per_q: dict[str, dict[str, np.ndarray]] = {}
    latencies: dict[str, float] = {}
    no_results: dict[str, int] = {}
    plans: dict[str, str] = {}
    with conn.cursor() as cur:
        cur.execute("SET enable_seqscan = off")
        cur.execute(f"SET hnsw.ef_search = {args.hnsw_ef_search}")
        cur.execute(f"SET hnsw.iterative_scan = off")
        for name, (_, sql, qv) in systems.items():
            results, lat = run_system(cur, sql, queries, qv)
            per_q[name] = per_query_metrics(results, queries)
            latencies[name] = lat
            no_results[name] = sum(1 for r in results if not r)
            p = {"q": queries[0]["query"]}
            if qv is not None:
                p["qvec"] = vec_literal(qv[0])
            plans[name] = explain_node(cur, sql, p)
            print(f"  {name}: median {lat} ms/query")

    summary = bootstrap(per_q, "ts_rank_cd (AND+OR)", args.n_boot, args.seed)
    vs_bm25 = bootstrap(per_q, "bm25_kazakh", args.n_boot, args.seed)
    for name, entry in summary.items():
        entry["delta_vs_bm25_kazakh"] = vs_bm25[name]["delta_vs_baseline"]
        entry["delta_vs_bm25_kazakh_ci95"] = vs_bm25[name]["delta_ci95"]
    print_table(summary, "ts_rank_cd (AND+OR)", latencies)

    base = summary["ts_rank_cd (AND+OR)"]["metrics"]
    baseline_check = {m: {"readme": v, "measured": base[m], "match": abs(base[m] - v) <= 0.005}
                      for m, v in README_BASELINE.items()}
    print(f"\nREADME baseline reproduction: {baseline_check}")

    hnsw_overlap = {}
    with conn.cursor() as cur:
        cur.execute(f"SET hnsw.ef_search = {args.hnsw_ef_search}")
    for tag in args.models:
        hnsw_overlap[tag] = overlap_with_exact(conn, MODELS[tag].column, queries,
                                               qvecs_by_model[tag], args.depth)
    print(f"HNSW vs exact top-{args.depth} overlap: {hnsw_overlap}")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.relname, pg_relation_size(c.oid) FROM pg_class c "
            "JOIN pg_index i ON i.indexrelid = c.oid WHERE i.indrelid = 'articles'::regclass"
        )
        index_bytes = dict(cur.fetchall())

    report = {
        "meta": {
            "corpus": str(args.corpus), "n_docs": n_docs, "gold": str(args.gold), "n_queries": len(queries),
            "postgres": pg_version, "extensions": ext_versions, "device": device,
            "rrf_k": args.rrf_k, "depth": args.depth, "n_boot": args.n_boot, "seed": args.seed,
            "bootstrap": "paired percentile, queries resampled with replacement, shared across systems",
            "hnsw": {"m": args.hnsw_m, "ef_construction": args.hnsw_ef_construction,
                     "ef_search": args.hnsw_ef_search, "opclass": "vector_cosine_ops",
                     "top_overlap_with_exact": hnsw_overlap},
            "bm25_params": {"k1": 1.2, "b": 0.75, "note": "pg_textsearch defaults"},
            "text_index_build_seconds": t_idx,
            "index_bytes": index_bytes,
            "models": model_meta,
            "notes": [
                "pg_textsearch resolves text_config without search_path: use 'public.kazakh_cfg', not 'kazakh_cfg'.",
                "Two BM25 indexes on one column make the planner pick either one; use one column per config.",
                "Selecting the BM25 score next to ORDER BY forces per-row scoring (~250x slower); rank by position.",
            ],
            "baseline_reproduction": baseline_check,
        },
        "systems": {
            name: {
                "description": systems[name][0],
                **summary[name],
                "median_latency_ms": latencies[name],
                "queries_without_results": no_results[name],
                "plan": plans[name],
            }
            for name in systems
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"\nReport saved to {args.report}")


if __name__ == "__main__":
    main()
