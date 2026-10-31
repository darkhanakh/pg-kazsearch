#!/usr/bin/env python3
"""Render the README charts in docs/img from the result files in eval/results.

Every number comes from a committed JSON report, so a chart cannot drift from
the measurement behind it. Rerun after any eval:

    python3 scripts/gen_readme_charts.py
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
OUT = ROOT / "docs" / "img"

INK = "#8b949e"
KAZ = "#2f81f7"
BASE = "#a0a6ad"
ALT = "#f0883e"
ALT2 = "#3fb950"

plt.rcParams.update({
    "figure.facecolor": "none",
    "axes.facecolor": "none",
    "savefig.facecolor": "none",
    "savefig.transparent": True,
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.titlepad": 12,
    "font.size": 10,
    "legend.frameon": False,
    "legend.labelcolor": INK,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": INK,
    "grid.alpha": 0.25,
    "axes.axisbelow": True,
})


def load(name: str) -> dict:
    path = RESULTS / name
    if not path.exists():
        sys.exit(f"{path} not found; run the eval that produces it first")
    return json.loads(path.read_text(encoding="utf-8"))


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> docs/img/{name}")


def grouped_bars(ax, groups: list[str], series: list[tuple[str, list[float], str]],
                 errors: list[list[tuple[float, float]] | None] | None = None,
                 fmt: str = "%.3f", width: float = 0.8) -> None:
    n = len(series)
    x = np.arange(len(groups))
    w = width / n
    for i, (label, values, color) in enumerate(series):
        pos = x - width / 2 + w * (i + 0.5)
        ax.bar(pos, values, w * 0.92, label=label, color=color)
        err = errors[i] if errors else None
        tops = values
        if err:
            lo = [v - e[0] for v, e in zip(values, err)]
            hi = [e[1] - v for v, e in zip(values, err)]
            ax.errorbar(pos, values, yerr=[lo, hi], fmt="none", ecolor=INK, elinewidth=1, capsize=3)
            tops = [e[1] for e in err]
        for p, v, t in zip(pos, values, tops):
            ax.annotate(fmt % v, (p, t), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.tick_params(axis="x", length=0)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)


def chart_stemming_effect(report: dict) -> None:
    sources = ["gold_v2", "gold", "morpho_variant", "title_keywords"]
    labels = {
        "gold_v2": "gold_v2\nhuman",
        "gold": "gold\nhuman",
        "morpho_variant": "morpho_variant\nsynthetic",
        "title_keywords": "title_keywords\nverbatim",
    }
    by_src = report["fts_by_source"]
    groups = [f"{labels[s]}\nn={by_src[s]['num_queries']}" for s in sources]
    stem = [by_src[s]["metrics"]["10"]["recall"] for s in sources]
    plain = [by_src[s]["nostem_metrics"]["10"]["recall"] for s in sources]
    ci = [tuple(by_src[s]["ci95"]["recall@10"]) for s in sources]

    fig, ax = plt.subplots(figsize=(9, 4.4))
    grouped_bars(ax, groups, [("kazakh_cfg (pg_kazsearch)", stem, KAZ), ("simple (no stemming)", plain, BASE)],
                 errors=[ci, None])
    ax.set_ylabel("Recall@10")
    ax.set_ylim(0, 1.12)
    ax.set_title("Recall@10 with and without stemming, same index and ranking (95% CI on stemmed bars)")
    ax.legend(loc="upper left", ncol=2)
    save(fig, "stemming_effect.png")


def chart_trgm(report: dict) -> None:
    fts = report["fts_on_sample"]["10"]
    trgm = report["trgm"]["10"]
    n = report["num_trgm_queries"]
    metrics = ["Recall@10", "MRR@10", "nDCG@10"]
    keys = ["recall", "mrr", "ndcg"]
    fig, ax = plt.subplots(figsize=(7, 4))
    grouped_bars(ax, metrics,
                 [("pg_kazsearch", [fts[k] for k in keys], KAZ),
                  (f"pg_trgm (threshold {report['trgm_threshold']})", [trgm[k] for k in keys], BASE)],
                 width=0.6)
    ax.set_ylim(0, 1.08)
    ax.set_title(f"pg_kazsearch vs pg_trgm on the same {n}-query sample")
    ax.legend(loc="upper right")
    save(fig, "pg_trgm_head_to_head.png")


def chart_hybrid(report: dict) -> None:
    systems = report["systems"]
    rows = [
        ("ts_rank_cd (AND+OR)", "ts_rank_cd, AND then OR fallback", BASE),
        ("bm25_simple", "BM25, simple (no stemming)", BASE),
        ("bm25_kazakh", "BM25, kazakh_cfg", KAZ),
        ("dense_bge_m3", "dense only, bge-m3", ALT),
        ("dense_kaz_embedder", "dense only, kaz-embedder", ALT),
        ("rrf_bge_m3", "RRF: BM25 kazakh_cfg + bge-m3", ALT2),
        ("rrf_kaz_embedder", "RRF: BM25 kazakh_cfg + kaz-embedder", ALT2),
    ]
    rows = [r for r in rows if r[0] in systems]
    names = [r[1] for r in rows]
    vals = [systems[r[0]]["metrics"]["R@10"] for r in rows]
    ci = [systems[r[0]]["ci95"]["R@10"] for r in rows]
    colors = [r[2] for r in rows]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(rows))[::-1]
    ax.barh(y, vals, color=colors, height=0.62)
    ax.errorbar(vals, y, xerr=[[v - c[0] for v, c in zip(vals, ci)], [c[1] - v for v, c in zip(vals, ci)]],
                fmt="none", ecolor=INK, elinewidth=1, capsize=3)
    for yy, v, c in zip(y, vals, ci):
        ax.annotate(f"{v:.3f}", (c[1], yy), xytext=(5, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=INK, alpha=0.25)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 0.9)
    ax.set_xlabel("Recall@10 on gold_v2 (95% bootstrap CI)")
    meta = report["meta"]
    ax.set_title(f"Ranking methods on {meta['n_docs']} articles, {meta['n_queries']} human queries")
    save(fig, "hybrid_search.png")


def chart_external(report: dict) -> None:
    wiki = report["datasets"]["wiki"]["metrics"]
    cats = ["overall", "inflected", "natural", "vocabulary-gap"]

    def ndcg(system: str) -> list[float]:
        m = wiki[system]
        return [m["overall"]["ndcg@10"]] + [m["by_category"][c]["ndcg@10"] for c in cats[1:]]

    n = report["datasets"]["wiki"]["n_queries"]
    groups = [f"{c}\n(n={n if c == 'overall' else wiki['identity']['by_category'][c]['n']})" for c in cats]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    grouped_bars(ax, groups, [
        ("BM25, no stemming", ndcg("identity"), BASE),
        ("BM25 + benchmark's stemmer", ndcg("their"), ALT),
        ("BM25 + pg_kazsearch", ndcg("pg_kazsearch"), KAZ),
    ])
    ax.set_ylabel("nDCG@10")
    ax.set_ylim(0, 1.0)
    ax.set_title("Kaz-RAG-search-benchmark, 8,370 Wikipedia passages, benchmark's own BM25 and tokenizer")
    ax.legend(loc="upper left", ncol=3)
    save(fig, "external_kazrag.png")


def chart_kazqad(report: dict) -> None:
    params = report["parameters"]
    harness = params["primary_harness"]["name"]
    split = report["results"][harness]["splits"]["test"]
    metrics = split["params"][params["primary_params"]]["metrics"]
    keys = ["ndcg@10", "mrr@10", "recall@10", "recall@100"]
    groups = ["nDCG@10", "MRR@10", "Recall@10", "Recall@100"]
    systems = [
        ("no stemming", "BM25, no stemming", BASE),
        ("snowball", "BM25 + Snowball kazakh.sbl", ALT),
        ("rust", "BM25 + Rust, no lexicon", ALT2),
        ("rust+lexicon", "BM25 + Rust + lexicon (pg_kazsearch)", KAZ),
    ]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    grouped_bars(ax, groups, [(label, [metrics[s][k] for k in keys], color) for s, label, color in systems])
    ax.set_ylim(0, 0.85)
    n = split["queries"]
    passages = report["corpus"]["passages"]
    ax.set_title(f"KazQAD test split, {n:,} exam questions over {passages:,} Wikipedia passages, "
                 f"BM25 {params['primary_params']}")
    ax.legend(loc="upper left", ncol=2)
    save(fig, "kazqad.png")


def chart_keyboard(folded_exact: dict, folded_restore: dict, proper_exact: dict, proper_restore: dict) -> None:
    def pair(report: dict) -> tuple[float, float]:
        m = report["fts"]["10"]
        return m["recall"], m["mrr"]

    fe, fr, pe, pr = pair(folded_exact), pair(folded_restore), pair(proper_exact), pair(proper_restore)
    groups = ["Recall@10\nkeyboard-typed queries", "MRR@10\nkeyboard-typed queries",
              "Recall@10\nproperly typed queries", "MRR@10\nproperly typed queries"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    grouped_bars(ax, groups, [
        ("keyboard = exact (default)", [fe[0], fe[1], pe[0], pe[1]], BASE),
        ("keyboard = restore", [fr[0], fr[1], pr[0], pr[1]], KAZ),
    ])
    n = folded_exact["num_queries"]
    ax.set_ylim(0, 1.0)
    ax.set_title(f"PostgreSQL search on gold_v2 (n={n}) when the query is typed on a Russian keyboard")
    ax.legend(loc="upper left", ncol=2)
    save(fig, "keyboard_restore.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = load("report.json")
    chart_stemming_effect(report)
    chart_trgm(report)
    chart_hybrid(load("report_hybrid.json"))
    chart_external(load("external_kazrag.json"))
    chart_kazqad(load("kazqad.json"))
    chart_keyboard(load("kb_exact_folded.json"), load("kb_restore_folded.json"),
                   load("kb_exact_proper.json"), load("kb_restore_proper.json"))


if __name__ == "__main__":
    main()
