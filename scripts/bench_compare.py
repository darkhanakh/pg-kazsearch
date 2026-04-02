#!/usr/bin/env python3
"""
Head-to-head benchmark: C extension (via ts_lexize in PostgreSQL)
vs Rust kazsearch-core (via cargo test --release).

Uses the same 45k token set from core/tests/bench_tokens.txt.

Usage:
    python3 scripts/bench_compare.py
    just bench
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time


def qlit(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def load_tokens(path: str) -> list[str]:
    tokens: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if t:
                tokens.append(t)
    return tokens


def bench_c_extension(
    tokens: list[str],
    iterations: int,
    batch_size: int,
    container: str,
    db: str,
    user: str,
) -> dict[str, float]:
    batches: list[str] = []
    for i in range(0, len(tokens), batch_size):
        chunk = tokens[i : i + batch_size]
        values = ",".join(f"('{qlit(t)}')" for t in chunk)
        sql = (
            f"WITH input(token) AS (VALUES {values}) "
            "SELECT sum(COALESCE(array_length("
            "ts_lexize('pg_kazsearch_dict', token), 1), 0)) FROM input;"
        )
        batches.append(sql)

    # Warmup
    for sql in batches[:2]:
        subprocess.run(
            ["docker", "exec", container, "psql", "-U", user, "-d", db, "-At", "-c", sql],
            capture_output=True, text=True,
        )

    elapsed_iters: list[float] = []
    for _ in range(iterations):
        t0 = time.monotonic()
        for sql in batches:
            subprocess.run(
                ["docker", "exec", container, "psql", "-U", user, "-d", db, "-At", "-c", sql],
                capture_output=True, text=True,
            )
        elapsed_iters.append(time.monotonic() - t0)

    n = len(tokens)
    avg = sum(elapsed_iters) / len(elapsed_iters)
    best = min(elapsed_iters)
    return {
        "tokens": n,
        "iterations": iterations,
        "avg_ms": avg * 1000,
        "best_ms": best * 1000,
        "avg_us_per_word": avg * 1e6 / n,
        "best_us_per_word": best * 1e6 / n,
        "avg_throughput": n / avg,
        "best_throughput": n / best,
    }


def bench_rust_core() -> dict[str, float]:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = subprocess.run(
        ["cargo", "test", "--release", "-p", "kazsearch-core",
         "bench_stem_unique_tokens", "--", "--nocapture"],
        capture_output=True, text=True, cwd=root, timeout=120,
    )

    output = result.stderr + result.stdout

    single_ms = None
    single_us = None
    single_tp = None
    avg_ms = None
    avg_us = None
    avg_tp = None
    n_tokens = None

    for line in output.splitlines():
        if "Unique tokens:" in line:
            m = re.search(r"(\d+)", line)
            if m:
                n_tokens = int(m.group(1))
        if "Single pass:" in line:
            m = re.search(r"([\d.]+)\s*ms", line)
            if m:
                single_ms = float(m.group(1))
        if "per word:" in line and single_us is None:
            m = re.search(r"([\d.]+)\s*us", line)
            if m:
                single_us = float(m.group(1))
        if "throughput:" in line and single_tp is None:
            m = re.search(r"([\d.]+)\s*words/sec", line)
            if m:
                single_tp = float(m.group(1))
        if "Avg of" in line:
            m = re.search(r"([\d.]+)\s*ms", line)
            if m:
                avg_ms = float(m.group(1))
        if "per word:" in line and avg_us is None and single_us is not None:
            m = re.search(r"([\d.]+)\s*us", line)
            if m:
                avg_us = float(m.group(1))
        if "throughput:" in line and avg_tp is None and single_tp is not None:
            m = re.search(r"([\d.]+)\s*words/sec", line)
            if m:
                avg_tp = float(m.group(1))

    if avg_ms is None or n_tokens is None:
        print("Failed to parse Rust bench output:", file=sys.stderr)
        print(output, file=sys.stderr)
        sys.exit(1)

    return {
        "tokens": n_tokens,
        "single_ms": single_ms or 0,
        "avg_ms": avg_ms or 0,
        "single_us_per_word": single_us or 0,
        "avg_us_per_word": avg_us or 0,
        "single_throughput": single_tp or 0,
        "avg_throughput": avg_tp or 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark C vs Rust stemmer")
    parser.add_argument("--iterations", type=int, default=5, help="C benchmark iterations")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--container", default="pg-kazsearch")
    parser.add_argument("--db", default="kazsearch")
    parser.add_argument("--user", default="postgres")
    args = parser.parse_args()

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    tokens_path = os.path.join(root, "core", "tests", "bench_tokens.txt")
    if not os.path.isfile(tokens_path):
        sys.exit(f"Token file not found: {tokens_path}")

    tokens = load_tokens(tokens_path)
    print(f"Loaded {len(tokens)} tokens from {tokens_path}")

    # ── Rust benchmark ───────────────────────────────────────────────────
    print("\n=== Rust (kazsearch-core, native, --release) ===")
    print("Running cargo test --release ...", flush=True)
    rust = bench_rust_core()
    print(f"  Tokens:          {rust['tokens']}")
    print(f"  Single pass:     {rust['single_ms']:.2f} ms  ({rust['single_us_per_word']:.3f} us/word, {rust['single_throughput']:.0f} words/sec)")
    print(f"  Avg (5 passes):  {rust['avg_ms']:.2f} ms  ({rust['avg_us_per_word']:.3f} us/word, {rust['avg_throughput']:.0f} words/sec)")

    # ── C benchmark ──────────────────────────────────────────────────────
    print(f"\n=== C (pg_kazsearch, PostgreSQL ts_lexize, {args.iterations} iters) ===")
    print(f"Running {args.iterations} iterations via docker exec ...", flush=True)
    c = bench_c_extension(tokens, args.iterations, args.batch_size,
                          args.container, args.db, args.user)
    print(f"  Tokens:          {c['tokens']}")
    print(f"  Best iteration:  {c['best_ms']:.2f} ms  ({c['best_us_per_word']:.3f} us/word, {c['best_throughput']:.0f} words/sec)")
    print(f"  Avg iteration:   {c['avg_ms']:.2f} ms  ({c['avg_us_per_word']:.3f} us/word, {c['avg_throughput']:.0f} words/sec)")

    # ── Comparison ───────────────────────────────────────────────────────
    rust_us = rust['avg_us_per_word']
    c_us = c['avg_us_per_word']

    print("\n" + "=" * 60)
    print("COMPARISON (avg per word)")
    print("=" * 60)
    print(f"  {'':20}  {'us/word':>10}  {'words/sec':>12}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*12}")
    print(f"  {'Rust (native)':20}  {rust_us:>10.3f}  {rust['avg_throughput']:>12,.0f}")
    print(f"  {'C (PostgreSQL)':20}  {c_us:>10.3f}  {c['avg_throughput']:>12,.0f}")
    print()

    if c_us > 0 and rust_us > 0:
        if rust_us < c_us:
            ratio = c_us / rust_us
            print(f"  Rust is {ratio:.1f}x faster per word (pure stemmer vs PG overhead)")
        else:
            ratio = rust_us / c_us
            print(f"  C is {ratio:.1f}x faster per word")

    print()
    print("NOTE: C timings include PostgreSQL overhead (parsing, palloc,")
    print("      docker exec, network). Rust timings are pure in-process.")
    print("      For apples-to-apples, compare both inside PostgreSQL")
    print("      by installing the Rust extension with pgrx.")


if __name__ == "__main__":
    main()
