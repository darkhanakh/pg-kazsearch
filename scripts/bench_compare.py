#!/usr/bin/env python3
"""
Head-to-head benchmark: C extension vs Rust extension, both via
ts_lexize inside PostgreSQL, plus Rust kazsearch-core natively.

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


def bench_pg_extension(
    tokens: list[str],
    iterations: int,
    batch_size: int,
    dict_name: str,
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
            f"SELECT sum(COALESCE(array_length("
            f"ts_lexize('{dict_name}', token), 1), 0)) FROM input;"
        )
        batches.append(sql)

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


def rust_ext_available(container: str, db: str, user: str) -> bool:
    r = subprocess.run(
        ["docker", "exec", container, "psql", "-U", user, "-d", db, "-At", "-c",
         "SELECT 1 FROM pg_ts_dict WHERE dictname = 'pg_kazsearch_rs_dict';"],
        capture_output=True, text=True,
    )
    return "1" in r.stdout


def bench_rust_core() -> dict[str, float] | None:
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
        print("  WARNING: Failed to parse Rust bench output", file=sys.stderr)
        return None

    return {
        "tokens": n_tokens,
        "single_ms": single_ms or 0,
        "avg_ms": avg_ms or 0,
        "single_us_per_word": single_us or 0,
        "avg_us_per_word": avg_us or 0,
        "single_throughput": single_tp or 0,
        "avg_throughput": avg_tp or 0,
    }


def print_comparison(results: list[tuple[str, float, float]]):
    print("\n" + "=" * 62)
    print("COMPARISON (avg per word)")
    print("=" * 62)
    print(f"  {'':24}  {'us/word':>10}  {'words/sec':>12}")
    print(f"  {'-'*24}  {'-'*10}  {'-'*12}")
    for label, us, tp in results:
        print(f"  {label:24}  {us:>10.3f}  {tp:>12,.0f}")

    fastest = min(results, key=lambda r: r[1])
    print()
    for label, us, tp in results:
        if label == fastest[0]:
            continue
        if fastest[1] > 0:
            ratio = us / fastest[1]
            print(f"  {fastest[0]} is {ratio:.1f}x faster than {label}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark C vs Rust stemmer")
    parser.add_argument("--iterations", type=int, default=5, help="PostgreSQL benchmark iterations")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--skip-native", action="store_true", help="Skip native Rust benchmark")
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

    results: list[tuple[str, float, float]] = []

    # ── Rust native benchmark ────────────────────────────────────────────
    if not args.skip_native:
        print("\n=== Rust (kazsearch-core, native, --release) ===")
        print("Running cargo test --release ...", flush=True)
        rust = bench_rust_core()
        if rust:
            print(f"  Tokens:          {rust['tokens']}")
            print(f"  Single pass:     {rust['single_ms']:.2f} ms  ({rust['single_us_per_word']:.3f} us/word, {rust['single_throughput']:.0f} words/sec)")
            print(f"  Avg (5 passes):  {rust['avg_ms']:.2f} ms  ({rust['avg_us_per_word']:.3f} us/word, {rust['avg_throughput']:.0f} words/sec)")
            results.append(("Rust (native)", rust["avg_us_per_word"], rust["avg_throughput"]))

    # ── C extension in PostgreSQL ────────────────────────────────────────
    print(f"\n=== C (pg_kazsearch_dict, PostgreSQL, {args.iterations} iters) ===")
    print(f"Running {args.iterations} iterations via docker exec ...", flush=True)
    c = bench_pg_extension(tokens, args.iterations, args.batch_size,
                           "pg_kazsearch_dict", args.container, args.db, args.user)
    print(f"  Tokens:          {c['tokens']}")
    print(f"  Best iteration:  {c['best_ms']:.2f} ms  ({c['best_us_per_word']:.3f} us/word, {c['best_throughput']:.0f} words/sec)")
    print(f"  Avg iteration:   {c['avg_ms']:.2f} ms  ({c['avg_us_per_word']:.3f} us/word, {c['avg_throughput']:.0f} words/sec)")
    results.append(("C (PostgreSQL)", c["avg_us_per_word"], c["avg_throughput"]))

    # ── Rust extension in PostgreSQL ─────────────────────────────────────
    has_rs = rust_ext_available(args.container, args.db, args.user)
    if has_rs:
        print(f"\n=== Rust (pg_kazsearch_rs_dict, PostgreSQL, {args.iterations} iters) ===")
        print(f"Running {args.iterations} iterations via docker exec ...", flush=True)
        rs = bench_pg_extension(tokens, args.iterations, args.batch_size,
                                "pg_kazsearch_rs_dict", args.container, args.db, args.user)
        print(f"  Tokens:          {rs['tokens']}")
        print(f"  Best iteration:  {rs['best_ms']:.2f} ms  ({rs['best_us_per_word']:.3f} us/word, {rs['best_throughput']:.0f} words/sec)")
        print(f"  Avg iteration:   {rs['avg_ms']:.2f} ms  ({rs['avg_us_per_word']:.3f} us/word, {rs['avg_throughput']:.0f} words/sec)")
        results.append(("Rust (PostgreSQL)", rs["avg_us_per_word"], rs["avg_throughput"]))
    else:
        print("\n  Rust extension (pg_kazsearch_rs) not installed in PostgreSQL.")
        print("  Run `just reload-rs` to install it for apples-to-apples comparison.")

    # ── Comparison table ─────────────────────────────────────────────────
    if len(results) >= 2:
        print_comparison(results)


if __name__ == "__main__":
    main()
