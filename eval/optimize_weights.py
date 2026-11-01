"""
CMA-ES weight optimizer for pg_kazsearch stemmer penalty weights.

Iterates ALTER TEXT SEARCH DICTIONARY with candidate weight vectors,
evaluates FTS recall/precision on the query corpus, and uses CMA-ES
to converge on optimal weights.

Usage:
    python3 eval/optimize_weights.py \
        --auto eval/auto_queries.jsonl \
        --gold eval/gold_queries.jsonl \
        --report eval/results/optimized_weights.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import cma

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_eval import (
    BATCH,
    batch_search_fts,
    load_queries,
    ndcg_at_k,
    precision_at_k,
    psql_stdin,
    recall_at_k,
)

WEIGHT_NAMES = [
    "w_no_strip",
    "w_two_char",
    "w_three_one",
    "w_deriv",
    "w_weak",
    "w_single_char",
    "w_verb_all_weak",
    "w_nik_deriv",
    "w_final_cons",
    "w_nominal_inf",
    "w_verbal_inf",
    "w_removed",
    "w_verb_track",
]

DEFAULTS = {
    "w_no_strip": 6.0,
    "w_two_char": 8.0,
    "w_three_one": 2.5,
    "w_deriv": 3.2,
    "w_weak": 2.5,
    "w_single_char": 1.2,
    "w_verb_all_weak": 10.0,
    "w_nik_deriv": 20.0,
    "w_final_cons": 4.0,
    "w_nominal_inf": 3.9,
    "w_verbal_inf": 4.2,
    "w_removed": 0.32,
    "w_verb_track": 1.2,
}

LOWER_BOUNDS = [0.0] * len(WEIGHT_NAMES)
UPPER_BOUNDS = [200.0] * len(WEIGHT_NAMES)


def weights_dict(vec: list[float]) -> dict[str, float]:
    return dict(zip(WEIGHT_NAMES, vec))


def defaults_vec() -> list[float]:
    return [DEFAULTS[n] for n in WEIGHT_NAMES]


def alter_dictionary(weights: dict[str, float], container: str, db: str, user: str) -> None:
    opts = ", ".join(f"{k} = {v:.6f}" for k, v in weights.items())
    sql = f"ALTER TEXT SEARCH DICTIONARY pg_kazsearch_dict ({opts});"
    psql_stdin(sql, container, db, user)


def evaluate_fts(
    indexed: list[tuple[int, str, set[int]]],
    k: int,
    container: str,
    db: str,
    user: str,
) -> dict[str, float]:
    fts_all: dict[int, list[int]] = {}
    for start in range(0, len(indexed), BATCH):
        batch = [(idx, qt) for idx, qt, _ in indexed[start : start + BATCH]]
        fts_all.update(batch_search_fts(batch, k, container, db, user))

    prec_vals: list[float] = []
    rec_vals: list[float] = []
    ndcg_vals: list[float] = []

    for idx, _qt, relevant in indexed:
        retrieved = fts_all.get(idx, [])
        prec_vals.append(precision_at_k(retrieved, relevant, k))
        rec_vals.append(recall_at_k(retrieved, relevant, k))
        ndcg_vals.append(ndcg_at_k(retrieved, relevant, k))

    n = len(indexed)
    return {
        "precision": sum(prec_vals) / n if n else 0.0,
        "recall": sum(rec_vals) / n if n else 0.0,
        "ndcg": sum(ndcg_vals) / n if n else 0.0,
    }


def compute_objective(metrics: dict[str, float], objective: str) -> float:
    r = metrics["recall"]
    p = metrics["precision"]
    n = metrics["ndcg"]

    if objective == "recall":
        return r
    elif objective == "precision":
        return p
    elif objective == "ndcg":
        return n
    elif objective == "f1":
        return (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    else:
        return 0.7 * r + 0.3 * p


def index_queries(queries: list[dict], offset: int = 0) -> list[tuple[int, str, set[int]]]:
    indexed = []
    for i, q in enumerate(queries):
        qt = q.get("query", "")
        rel = set(q.get("relevant_ids", []))
        if qt and rel:
            indexed.append((offset + i, qt, rel))
    return indexed


def split_train_holdout(
    auto_indexed: list[tuple[int, str, set[int]]],
    holdout_frac: float,
    seed: int,
) -> tuple[list[tuple[int, str, set[int]]], list[tuple[int, str, set[int]]]]:
    """Document-disjoint split: auto queries generated from the same article
    always land on the same side, so training never sees holdout documents."""
    by_doc: dict[int, list[tuple[int, str, set[int]]]] = {}
    for item in auto_indexed:
        doc = min(item[2])
        by_doc.setdefault(doc, []).append(item)

    docs = sorted(by_doc)
    rng = random.Random(seed)
    rng.shuffle(docs)
    n_hold = int(len(docs) * holdout_frac)
    hold_docs = docs[:n_hold]
    train_docs = docs[n_hold:]

    train = [it for d in train_docs for it in by_doc[d]]
    hold = [it for d in hold_docs for it in by_doc[d]]
    return train, hold


def main():
    parser = argparse.ArgumentParser(description="CMA-ES weight optimizer for pg_kazsearch")
    parser.add_argument("--auto", default="eval/auto_queries.jsonl")
    parser.add_argument("--gold", default="eval/gold_queries.jsonl")
    parser.add_argument("--k", type=int, default=10, help="k for P@k / R@k")
    parser.add_argument("--max-evals", type=int, default=2000)
    parser.add_argument("--population-size", type=int, default=0, help="CMA-ES popsize (0=auto)")
    parser.add_argument("--sigma0", type=float, default=2.0, help="Initial step size")
    parser.add_argument("--sample-size", type=int, default=500,
                        help="Subsample of TRAIN queries per iteration (0=all)")
    parser.add_argument("--objective", default="combined",
                        choices=["recall", "precision", "f1", "ndcg", "combined"])
    parser.add_argument("--holdout-frac", type=float, default=0.2,
                        help="Fraction of auto-query source articles held out for final verification")
    parser.add_argument("--seed", type=int, default=42, help="Seed for split and subsampling")
    parser.add_argument("--container", default="pg-kazsearch")
    parser.add_argument("--db", default="kazsearch")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--report", default="eval/results/optimized_weights.json")
    args = parser.parse_args()

    auto_queries = load_queries(Path(args.auto))
    gold_queries = load_queries(Path(args.gold))
    if not auto_queries and not gold_queries:
        sys.exit("No queries found. Run generate_queries.py first.")

    auto_indexed = index_queries(auto_queries)
    gold_indexed = index_queries(gold_queries, offset=len(auto_queries))

    # Gold queries are the reporting set and are NEVER used for optimization.
    # Auto queries are split document-disjoint into train and holdout so the
    # optimizer cannot overfit the numbers we report.
    train, auto_holdout = split_train_holdout(auto_indexed, args.holdout_frac, args.seed)
    print(f"Loaded {len(auto_indexed)} auto + {len(gold_indexed)} gold queries")
    print(f"Split: {len(train)} train / {len(auto_holdout)} auto-holdout "
          f"(doc-disjoint, seed={args.seed}) / {len(gold_indexed)} gold (report-only)")

    sample_size = args.sample_size if args.sample_size > 0 else len(train)
    sample_size = min(sample_size, len(train))

    if sample_size < len(train):
        rng = random.Random(args.seed)
        sample = rng.sample(train, sample_size)
        print(f"Using fixed subsample of {sample_size} train queries (seed={args.seed})")
    else:
        sample = train

    x0 = defaults_vec()
    eval_count = 0
    best_obj = -1e9
    best_weights: dict[str, float] = dict(DEFAULTS)
    t_start = time.monotonic()

    def eval_named(indexed, label):
        m = evaluate_fts(indexed, args.k, args.container, args.db, args.user)
        print(f"  {label}: R@{args.k}={m['recall']:.4f}  "
              f"P@{args.k}={m['precision']:.4f}  "
              f"nDCG@{args.k}={m['ndcg']:.4f}", flush=True)
        return m

    print("Evaluating baseline (default weights)...", flush=True)
    alter_dictionary(DEFAULTS, args.container, args.db, args.user)
    baseline_hold = eval_named(auto_holdout, "Baseline auto-holdout")
    baseline_gold = eval_named(gold_indexed, "Baseline gold") if gold_indexed else {}

    opts = {
        "maxfevals": args.max_evals,
        "bounds": [LOWER_BOUNDS, UPPER_BOUNDS],
        "verb_disp": 0,
        "verb_log": 0,
        "verb_filenameprefix": "outcmaes/",
    }
    if args.population_size > 0:
        opts["popsize"] = args.population_size

    es = cma.CMAEvolutionStrategy(x0, args.sigma0, opts)

    try:
        while not es.stop():
            solutions = es.ask()
            fitnesses = []

            for sol in solutions:
                w = weights_dict(sol)
                alter_dictionary(w, args.container, args.db, args.user)
                metrics = evaluate_fts(sample, args.k, args.container, args.db, args.user)
                obj = compute_objective(metrics, args.objective)
                fitnesses.append(-obj)
                eval_count += 1

                if obj > best_obj:
                    best_obj = obj
                    best_weights = w
                    print(f"  [{eval_count:>5}] NEW BEST (train) obj={obj:.4f}  "
                          f"R={metrics['recall']:.4f}  P={metrics['precision']:.4f}  "
                          f"nDCG={metrics['ndcg']:.4f}", flush=True)

            es.tell(solutions, fitnesses)

            if eval_count % 50 == 0:
                elapsed = time.monotonic() - t_start
                print(f"  [{eval_count:>5}] {elapsed:.0f}s elapsed", flush=True)

        elapsed = time.monotonic() - t_start

        print("\nVerifying best weights on held-out sets (never used in training)...", flush=True)
        alter_dictionary(best_weights, args.container, args.db, args.user)
        final_hold = eval_named(auto_holdout, "Optimized auto-holdout")
        final_gold = eval_named(gold_indexed, "Optimized gold") if gold_indexed else {}
    finally:
        # Always leave the live dictionary in its default state, even on
        # interrupt: this script mutates the shared DB thousands of times.
        print("\nRestoring default weights...", flush=True)
        alter_dictionary(DEFAULTS, args.container, args.db, args.user)

    report = {
        "baseline_holdout": {k: round(v, 6) for k, v in baseline_hold.items()},
        "baseline_gold": {k: round(v, 6) for k, v in baseline_gold.items()},
        "optimized_holdout": {k: round(v, 6) for k, v in final_hold.items()},
        "optimized_gold": {k: round(v, 6) for k, v in final_gold.items()},
        "k": args.k,
        "objective": args.objective,
        "holdout_frac": args.holdout_frac,
        "seed": args.seed,
        "num_train": len(train),
        "num_auto_holdout": len(auto_holdout),
        "num_gold": len(gold_indexed),
        "evals": eval_count,
        "elapsed_s": round(elapsed, 1),
        "weights": {k: round(v, 6) for k, v in best_weights.items()},
        "defaults": DEFAULTS,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to {report_path}")

    print("\nTo apply optimized weights:")
    opts_sql = ", ".join(f"{k} = {v:.6f}" for k, v in best_weights.items())
    print(f"  ALTER TEXT SEARCH DICTIONARY pg_kazsearch_dict ({opts_sql});")


if __name__ == "__main__":
    main()
