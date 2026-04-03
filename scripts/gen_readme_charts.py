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

BG = "#0d1117"
FG = "#c9d1d9"
GRID = "#21262d"
ACCENT = "#58a6ff"
ACCENT2 = "#6e7681"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "axes.edgecolor": GRID,
    "axes.labelcolor": FG,
    "text.color": FG,
    "xtick.color": FG,
    "ytick.color": FG,
    "grid.color": GRID,
    "font.family": "sans-serif",
    "font.size": 13,
})


def chart_retrieval_quality():
    metrics = ["Recall@10", "MRR@10", "nDCG@10"]
    kazsearch = [0.784, 0.712, 0.729]
    trgm = [0.635, 0.566, 0.582]

    x = np.arange(len(metrics))
    w = 0.32

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars1 = ax.bar(x - w/2, kazsearch, w, label="pg_kazsearch", color=ACCENT, zorder=3)
    bars2 = ax.bar(x + w/2, trgm, w, label="pg_trgm", color=ACCENT2, zorder=3)

    for bar, val in zip(bars1, kazsearch):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.012,
                f"{val:.3f}", ha="center", va="bottom", fontsize=11, fontweight="bold", color=ACCENT)
    for bar, val in zip(bars2, trgm):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.012,
                f"{val:.3f}", ha="center", va="bottom", fontsize=11, color=ACCENT2)

    ax.set_ylabel("Score")
    ax.set_title("Retrieval Quality — 9,048 Queries over 2,999 Articles", fontsize=14, fontweight="bold", pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 0.92)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="y", alpha=0.4, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(OUT / "retrieval_quality.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT / 'retrieval_quality.png'}")


def chart_latency():
    methods = ["pg_kazsearch", "pg_trgm"]
    latency = [0.5, 1.4]
    colors = [ACCENT, ACCENT2]

    fig, ax = plt.subplots(figsize=(6, 3.5))
    bars = ax.barh(methods, latency, color=colors, height=0.45, zorder=3)

    for bar, val in zip(bars, latency):
        ax.text(bar.get_width() + 0.04, bar.get_y() + bar.get_height()/2,
                f"{val} ms", ha="left", va="center", fontsize=12, fontweight="bold")

    ax.set_xlabel("Query Latency (ms)")
    ax.set_title("Average Query Latency", fontsize=14, fontweight="bold", pad=14)
    ax.set_xlim(0, 2.0)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.4, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(OUT / "query_latency.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT / 'query_latency.png'}")


def chart_suffix_layers():
    layers = [
        "Derivational", "Plural", "Possessive", "Case",
        "Predicate", "Voice", "Negation", "Tense", "Person"
    ]
    track = ["Noun", "Noun", "Noun", "Noun", "Noun",
             "Verb", "Verb", "Verb", "Verb"]
    examples = [
        "-лық/-тік", "-лар/-лер", "-ым/-ің/-ы", "-да/-де/-ға/-ге",
        "-мын/-мін", "-ыл/-іл", "-ма/-ме", "-ды/-ді/-ған", "-м/-ң/-ңыз"
    ]

    noun_color = ACCENT
    verb_color = "#f78166"

    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = [noun_color if t == "Noun" else verb_color for t in track]
    y = np.arange(len(layers))

    bars = ax.barh(y, [1]*len(layers), color=colors, height=0.6, alpha=0.85, zorder=3)

    for i, (layer, ex) in enumerate(zip(layers, examples)):
        ax.text(0.03, i, f"{layer}", ha="left", va="center",
                fontsize=12, fontweight="bold", color=BG)
        ax.text(0.97, i, ex, ha="right", va="center",
                fontsize=11, color=BG, style="italic")

    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.set_title("BFS Suffix Stripping Layers", fontsize=14, fontweight="bold", pad=14)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)

    ax.text(0.5, -0.08, "■ Noun track     ■ Verb track",
            ha="center", va="top", transform=ax.transAxes, fontsize=11,
            color=FG)

    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(OUT / "suffix_layers.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT / 'suffix_layers.png'}")


def chart_improvement():
    metrics = ["Recall@10", "MRR@10", "nDCG@10", "Latency"]
    improvement = [
        ((0.784 - 0.635) / 0.635) * 100,
        ((0.712 - 0.566) / 0.566) * 100,
        ((0.729 - 0.582) / 0.582) * 100,
        ((1.4 - 0.5) / 1.4) * 100,
    ]
    colors = [ACCENT, ACCENT, ACCENT, "#3fb950"]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(metrics, improvement, color=colors, width=0.55, zorder=3)

    for bar, val in zip(bars, improvement):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f"+{val:.0f}%", ha="center", va="bottom", fontsize=13, fontweight="bold")

    ax.set_ylabel("Improvement over pg_trgm (%)")
    ax.set_title("pg_kazsearch vs pg_trgm — Relative Improvement", fontsize=14, fontweight="bold", pad=14)
    ax.set_ylim(0, 80)
    ax.grid(axis="y", alpha=0.4, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(OUT / "improvement.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {OUT / 'improvement.png'}")


if __name__ == "__main__":
    print("Generating charts...")
    chart_retrieval_quality()
    chart_latency()
    chart_suffix_layers()
    chart_improvement()
    print("Done.")
