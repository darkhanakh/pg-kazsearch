#!/usr/bin/env python3
"""Generate README charts for pg_kazsearch benchmarks."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)


def chart_retrieval_quality():
    metrics = ["Recall@10", "MRR@10", "nDCG@10"]
    kazsearch = [0.784, 0.712, 0.729]
    trgm = [0.635, 0.566, 0.582]

    x = np.arange(len(metrics))
    w = 0.32

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars1 = ax.bar(x - w/2, kazsearch, w, label="pg_kazsearch")
    bars2 = ax.bar(x + w/2, trgm, w, label="pg_trgm")

    ax.bar_label(bars1, fmt="%.3f", padding=3, fontweight="bold")
    ax.bar_label(bars2, fmt="%.3f", padding=3)

    ax.set_ylabel("Score")
    ax.set_title("Retrieval Quality — 9,048 Queries over 2,999 Articles", fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 0.92)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(OUT / "retrieval_quality.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT / 'retrieval_quality.png'}")


def chart_latency():
    methods = ["pg_kazsearch", "pg_trgm"]
    latency = [0.5, 1.4]

    fig, ax = plt.subplots(figsize=(6, 3))
    bars = ax.barh(methods, latency, height=0.45)

    ax.bar_label(bars, labels=["0.5 ms", "1.4 ms"], padding=5, fontweight="bold")

    ax.set_xlabel("Query Latency (ms)")
    ax.set_title("Average Query Latency", fontweight="bold", pad=12)
    ax.set_xlim(0, 2.0)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(OUT / "query_latency.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT / 'query_latency.png'}")


def chart_improvement():
    metrics = ["Recall@10", "MRR@10", "nDCG@10", "Latency"]
    improvement = [
        ((0.784 - 0.635) / 0.635) * 100,
        ((0.712 - 0.566) / 0.566) * 100,
        ((0.729 - 0.582) / 0.582) * 100,
        ((1.4 - 0.5) / 1.4) * 100,
    ]
    colors = ["#1f77b4", "#1f77b4", "#1f77b4", "#2ca02c"]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(metrics, improvement, color=colors, width=0.55)

    ax.bar_label(bars, labels=[f"+{v:.0f}%" for v in improvement], padding=3, fontweight="bold")

    ax.set_ylabel("Improvement over pg_trgm (%)")
    ax.set_title("pg_kazsearch vs pg_trgm — Relative Improvement", fontweight="bold", pad=12)
    ax.set_ylim(0, 80)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(OUT / "improvement.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT / 'improvement.png'}")


if __name__ == "__main__":
    print("Generating charts...")
    chart_retrieval_quality()
    chart_latency()
    chart_improvement()
    print("Done.")
