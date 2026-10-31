"""
Run pg_kazsearch through the public Kaz-RAG-search-benchmark (Tim2190) with
the benchmark's own BM25, tokenizer, metrics and bootstrap. Only the stemmer
changes.

Systems (all via the benchmark's BM25Index, k1=1.5 b=0.75):
  identity     no stemming
  their        the benchmark's stemmer, replayed from its committed stem cache
  pg_kazsearch kazsearch CLI, whole vocabulary stemmed in one batch

Sanity gate: identity and their-stemmer must reproduce the benchmark's
published nDCG@10 (results/bm25_identity.json, results/bm25_kazakh.json).
If they do not, the adapter is wrong and the script exits non-zero.

Usage:
    git clone https://github.com/Tim2190/Kaz-RAG-search-benchmark /tmp/kazrag
    git -C /tmp/kazrag checkout 08bc105c093be16c714b6ba3c363beb54ac0ad16
    python3 eval/run_external_kazrag.py --repo /tmp/kazrag \
        --lexicon data/tsearch_data/kaz_stems.dict \
        --out eval/results/external_kazrag.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent

PINNED_COMMIT = "08bc105c093be16c714b6ba3c363beb54ac0ad16"
SYSTEMS = ("identity", "their", "pg_kazsearch")
METRIC_KEYS = ("recall@1", "recall@5", "recall@10", "mrr@10", "ndcg@10")
REPRO_TOLERANCE = 5e-4
EXAMPLE_LIMIT = 25


def find_cli() -> str:
    for candidate in (
        ROOT / "target" / "release" / "kazsearch",
        ROOT / "target" / "debug" / "kazsearch",
    ):
        if candidate.exists():
            return str(candidate)
    if shutil.which("kazsearch"):
        return "kazsearch"
    sys.exit("kazsearch CLI not found. Build it first: cargo build --release -p kazsearch-cli")


def git_rev(path: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BenchmarkHarness:
    """The benchmark's own modules, imported from a checkout."""

    def __init__(self, repo: Path) -> None:
        sys.path.insert(0, str(repo))
        self.tokenize = importlib.import_module("src.preprocess.tokenize").tokenize
        bm25 = importlib.import_module("src.retrieval.bm25")
        self.bm25_index = bm25.BM25Index
        self.default_analyzer = bm25.default_analyzer
        self.metrics = importlib.import_module("src.eval.metrics")
        self.dataset = importlib.import_module("src.queries.dataset")
        self.akorda = importlib.import_module("src.eval.run_akorda")


class DictStemmer:
    """Stemmer protocol over a precomputed token -> stem table."""

    def __init__(self, table: dict[str, str]) -> None:
        self.table = table
        self.misses: set[str] = set()

    def stem(self, token: str) -> str:
        stem = self.table.get(token)
        if stem is None:
            self.misses.add(token)
            return token
        return stem


class Dataset:
    def __init__(
        self,
        name: str,
        corpus: list[tuple[str, str]],
        queries: dict[str, str],
        qrels: dict[str, set[str]],
        categories: dict[str, str],
    ) -> None:
        self.name = name
        self.corpus = corpus
        self.queries = queries
        self.qrels = qrels
        self.categories = categories

    def vocabulary(self, tokenize: Callable[[str], list[str]]) -> list[str]:
        vocab: set[str] = set()
        for _, text in self.corpus:
            vocab.update(tokenize(text))
        for text in self.queries.values():
            vocab.update(tokenize(text))
        return sorted(vocab)


def load_main(h: BenchmarkHarness, repo: Path) -> Dataset:
    corpus = h.dataset.load_corpus(str(repo / "data/corpus/corpus.jsonl"))
    queries = h.dataset.load_queries(str(repo / "data/queries/queries.jsonl"))
    return Dataset(
        "wiki",
        corpus,
        h.dataset.queries_as_map(queries),
        h.dataset.qrels_from_queries(queries),
        h.dataset.categories_from_queries(queries),
    )


def load_akorda(h: BenchmarkHarness, repo: Path) -> Dataset:
    a = h.akorda
    a.PASSAGES = str(repo / "data/akorda/passages.jsonl")
    a.QUERIES = str(repo / "data/akorda/queries.jsonl")
    a.QRELS_FILE = str(repo / "data/akorda/qrels.jsonl")
    queries = a._load_queries()
    return Dataset(
        "akorda",
        a._load_corpus(),
        {q["query_id"]: q["text"] for q in queries},
        a._load_qrels(),
        {q["query_id"]: q["category"] for q in queries},
    )


def stem_with_cli(cli: str, lexicon: Path | None, words: list[str]) -> dict[str, str]:
    cmd = [cli, "stem", "--stdin"]
    if lexicon is not None:
        cmd += ["-l", str(lexicon)]
    proc = subprocess.run(
        cmd, input="\n".join(words) + "\n", capture_output=True, text=True, timeout=1800
    )
    if proc.returncode != 0:
        sys.exit(f"kazsearch stem failed: {proc.stderr[:500]}")
    lines = proc.stdout.splitlines()
    if len(lines) != len(words):
        sys.exit(f"kazsearch returned {len(lines)} lines for {len(words)} words")
    table: dict[str, str] = {}
    for word, line in zip(words, lines):
        out_word, _, stem = line.partition("\t")
        if out_word != word:
            sys.exit(f"kazsearch output misaligned: sent {word!r}, got {out_word!r}")
        table[word] = stem
    return table


def run_system(h: BenchmarkHarness, ds: Dataset, stemmer) -> dict[str, list[str]]:
    index = h.bm25_index(analyzer=h.default_analyzer(stemmer)).index(ds.corpus)
    return index.run(ds.queries, top_k=10)


def metric_block(h: BenchmarkHarness, run, ds: Dataset) -> dict:
    def block(qrels: dict[str, set[str]]) -> dict:
        full = h.metrics.evaluate_run(run, qrels, metrics=("recall", "mrr", "ndcg"), ks=(1, 5, 10))
        out = {k: full[k] for k in METRIC_KEYS}
        out["n"] = len(qrels)
        return out

    result = {"overall": block(ds.qrels), "by_category": {}}
    for cat in sorted(set(ds.categories.values())):
        sub = {q: r for q, r in ds.qrels.items() if ds.categories.get(q) == cat}
        result["by_category"][cat] = block(sub)
    return result


def bootstrap_ci(diffs: list[float], resamples: int, seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(
        sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)
    )
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def compare(
    h: BenchmarkHarness, run_a, run_b, ds: Dataset, resamples: int, seed: int
) -> dict:
    """Delta is B minus A on ndcg@10, with the benchmark's p-value and a percentile CI."""
    groups = {"overall": set(ds.qrels)}
    for cat in sorted(set(ds.categories.values())):
        groups[cat] = {q for q, c in ds.categories.items() if c == cat}
    out = {}
    for name, qids in groups.items():
        sub = {q: r for q, r in ds.qrels.items() if q in qids}
        delta, p, _ = h.metrics.paired_bootstrap(
            run_a, run_b, sub, metric="ndcg", k=10, n_resamples=resamples, seed=seed
        )
        sa = h.metrics.per_query_scores(run_a, sub, "ndcg", 10)
        sb = h.metrics.per_query_scores(run_b, sub, "ndcg", 10)
        diffs = [sb[q] - sa[q] for q in sa if q in sb]
        lo, hi = bootstrap_ci(diffs, resamples, seed)
        out[name] = {
            "delta_ndcg10": delta,
            "ci95": [lo, hi],
            "p_value": p,
            "wins": sum(1 for d in diffs if d > 0),
            "losses": sum(1 for d in diffs if d < 0),
            "ties": sum(1 for d in diffs if d == 0),
            "n": len(diffs),
        }
    return out


def check_reproduction(repo: Path, datasets: dict) -> dict:
    """Wiki identity and their-stemmer must match the published files.

    Akorda identity is checked too. The akorda their-stemmer run in the repo
    used a complete stem cache, but the committed cache covers only part of the
    akorda vocabulary, so that number is reported as a reference, not asserted.
    """
    wiki = datasets["wiki"]["metrics"]
    published = {
        "identity": json.loads((repo / "results/bm25_identity.json").read_text()),
        "their": json.loads((repo / "results/bm25_kazakh.json").read_text()),
    }
    report = {}
    for system, pub in published.items():
        ours = wiki[system]
        gaps = {"overall": abs(ours["overall"]["ndcg@10"] - pub["overall"]["ndcg@10"])}
        for cat, m in pub["by_category"].items():
            gaps[cat] = abs(ours["by_category"][cat]["ndcg@10"] - m["ndcg@10"])
        report[system] = {
            "published_ndcg10": {
                "overall": pub["overall"]["ndcg@10"],
                **{c: m["ndcg@10"] for c, m in pub["by_category"].items()},
            },
            "max_abs_gap": max(gaps.values()),
            "reproduced": max(gaps.values()) <= REPRO_TOLERANCE,
        }
    if "akorda" in datasets:
        pub = json.loads((repo / "results/akorda/bm25_identity.json").read_text())
        ours = datasets["akorda"]["metrics"]["identity"]
        gaps = [abs(ours["overall"]["ndcg@10"] - pub["overall"]["ndcg@10"])]
        gaps += [abs(ours["by_category"][c]["ndcg@10"] - m["ndcg@10"])
                 for c, m in pub["by_category"].items()]
        report["akorda_identity"] = {
            "published_ndcg10": pub["overall"]["ndcg@10"],
            "max_abs_gap": max(gaps),
            "reproduced": max(gaps) <= REPRO_TOLERANCE,
        }
        full = json.loads((repo / "results/akorda/bm25_kazakh_full.json").read_text())
        report["akorda_their_reference"] = {
            "published_full_cache_ndcg10": full["overall"]["ndcg@10"],
            "ours_partial_cache_ndcg10": datasets["akorda"]["metrics"]["their"]["overall"]["ndcg@10"],
            "note": "committed stem cache covers "
                    f"{datasets['akorda']['their_cache_vocab_coverage_pct']}% of the akorda "
                    "vocabulary; uncached tokens fall back to identity, as in the benchmark's "
                    "own cache-only mode, so this run is not the published full-cache run",
        }
    return report


def disagreement(
    ds: Dataset, tokenize, their: dict[str, str], pg: dict[str, str], vocab: list[str]
) -> dict:
    differ = [w for w in vocab if their.get(w, w) != pg[w]]
    q_tokens: dict[str, int] = {}
    for text in ds.queries.values():
        for t in set(tokenize(text)):
            q_tokens[t] = q_tokens.get(t, 0) + 1
    examples = sorted(
        (w for w in differ if w in q_tokens), key=lambda w: (-q_tokens[w], w)
    )[:EXAMPLE_LIMIT]
    return {
        "vocab_size": len(vocab),
        "stems_differ": len(differ),
        "stems_differ_pct": round(100.0 * len(differ) / len(vocab), 2),
        "query_token_examples": [
            {"token": w, "their": their.get(w, w), "pg_kazsearch": pg[w], "queries": q_tokens[w]}
            for w in examples
        ],
    }


def evaluate_dataset(
    h: BenchmarkHarness,
    ds: Dataset,
    their_cache: dict[str, str],
    cli: str,
    lexicon: Path | None,
    resamples: int,
    seed: int,
) -> tuple[dict, dict[str, dict[str, str]]]:
    vocab = ds.vocabulary(h.tokenize)
    pg_table = stem_with_cli(cli, lexicon, vocab)
    their = DictStemmer(their_cache)
    stemmers = {
        "identity": DictStemmer({w: w for w in vocab}),
        "their": their,
        "pg_kazsearch": DictStemmer(pg_table),
    }
    runs = {name: run_system(h, ds, st) for name, st in stemmers.items()}
    metrics = {name: metric_block(h, runs[name], ds) for name in SYSTEMS}
    covered = sum(1 for w in vocab if w in their_cache)
    result = {
        "n_passages": len(ds.corpus),
        "n_queries": len(ds.queries),
        "vocab_size": len(vocab),
        "their_cache_vocab_coverage_pct": round(100.0 * covered / len(vocab), 2),
        "metrics": metrics,
        "bootstrap": {
            "pg_kazsearch_vs_identity": compare(
                h, runs["identity"], runs["pg_kazsearch"], ds, resamples, seed
            ),
            "pg_kazsearch_vs_their": compare(
                h, runs["their"], runs["pg_kazsearch"], ds, resamples, seed
            ),
            "their_vs_identity": compare(
                h, runs["identity"], runs["their"], ds, resamples, seed
            ),
        },
        "stemmer_disagreement": disagreement(ds, h.tokenize, their_cache, pg_table, vocab),
    }
    return result, {"pg": pg_table, "runs": runs}


def print_report(name: str, result: dict) -> None:
    print(f"\n=== {name}: {result['n_passages']} passages, {result['n_queries']} queries, "
          f"their-cache vocab coverage {result['their_cache_vocab_coverage_pct']}% ===")
    cats = ["overall", *result["metrics"]["identity"]["by_category"]]
    for metric in ("ndcg@10", "recall@10"):
        print(f"\n{metric:<14}" + "".join(f"{c[:14]:>16}" for c in cats))
        for system in SYSTEMS:
            m = result["metrics"][system]
            row = [m["overall"][metric], *(m["by_category"][c][metric] for c in cats[1:])]
            print(f"{system:<14}" + "".join(f"{v:>16.4f}" for v in row))
    for pair, groups in result["bootstrap"].items():
        print(f"\n{pair} (delta ndcg@10, 95% CI, p)")
        for g, s in groups.items():
            print(f"  {g:<16} {s['delta_ndcg10']:+.4f}  [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}]  "
                  f"p={s['p_value']:.4f}  W/L/T={s['wins']}/{s['losses']}/{s['ties']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate pg_kazsearch on the Kaz-RAG-search-benchmark with its own harness"
    )
    parser.add_argument("--repo", required=True, help="Checkout of Tim2190/Kaz-RAG-search-benchmark")
    parser.add_argument("--lexicon", default="data/tsearch_data/kaz_stems.dict",
                        help="Lexicon dict file passed to the kazsearch CLI ('' for none)")
    parser.add_argument("--out", default="eval/results/external_kazrag.json")
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=13, help="Bootstrap seed (benchmark default)")
    parser.add_argument("--skip-akorda", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / "src/retrieval/bm25.py").exists():
        sys.exit(f"{repo} does not look like the benchmark checkout")
    rev = git_rev(repo)
    if rev != PINNED_COMMIT:
        print(f"WARN benchmark at {rev}, results were pinned to {PINNED_COMMIT}", file=sys.stderr)

    lexicon = Path(args.lexicon) if args.lexicon else None
    if lexicon is not None and not lexicon.is_absolute():
        lexicon = ROOT / lexicon
    if lexicon is not None and not lexicon.exists():
        sys.exit(f"Lexicon not found: {lexicon}")
    cli = find_cli()

    h = BenchmarkHarness(repo)
    their_cache = json.loads((repo / "data/resources/stem_cache.json").read_text(encoding="utf-8"))

    datasets = {"wiki": load_main(h, repo)}
    if not args.skip_akorda:
        datasets["akorda"] = load_akorda(h, repo)

    results = {}
    for name, ds in datasets.items():
        results[name], _ = evaluate_dataset(
            h, ds, their_cache, cli, lexicon, args.resamples, args.seed
        )
        print_report(name, results[name])

    reproduction = check_reproduction(repo, results)
    print("\nReproduction of published nDCG@10")
    for system, r in reproduction.items():
        if "reproduced" not in r:
            print(f"  {system}: {r['note']}")
            continue
        pub = r["published_ndcg10"]
        pub = pub["overall"] if isinstance(pub, dict) else pub
        print(f"  {system:<16} published overall {pub:.4f}, "
              f"max abs gap {r['max_abs_gap']:.6f}, reproduced={r['reproduced']}")

    report = {
        "benchmark": {
            "repo": "https://github.com/Tim2190/Kaz-RAG-search-benchmark",
            "commit": rev,
            "retrieval": "BM25 k1=1.5 b=0.75 (benchmark src/retrieval/bm25.py), top_k=10",
            "tokenizer": "benchmark src/preprocess/tokenize.py",
        },
        "pg_kazsearch": {
            "commit": git_rev(ROOT),
            "lexicon": str(lexicon.relative_to(ROOT)) if lexicon and lexicon.is_relative_to(ROOT) else str(lexicon),
            "lexicon_sha256": sha256_file(lexicon) if lexicon else None,
        },
        "bootstrap": {"resamples": args.resamples, "seed": args.seed, "metric": "ndcg@10",
                      "ci": "percentile 95% of paired per-query deltas",
                      "p_value": "benchmark's paired_bootstrap (one-sided sign-flip share)"},
        "reproduction": reproduction,
        "datasets": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nReport saved to {out}")

    if not all(r["reproduced"] for r in reproduction.values() if "reproduced" in r):
        sys.exit("Published numbers did not reproduce; the adapter is wrong")


if __name__ == "__main__":
    main()
