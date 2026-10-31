#!/usr/bin/env python3
"""Measure snowball/kazakh.sbl against the Rust stemmer on the same data.

Rows: no stemming, Snowball (one row per --sbl), Rust without lexicon, Rust
with lexicon.  For gold_v2 the harness is the one behind the README numbers:
BM25 k1=1.2 b=0.75, title counted twice, kaz_stopwords.stop removed, letters-
only tokens.  Differences come with a paired bootstrap CI over queries.

Also reports agreement with the Rust lexicon stemmer over
core/tests/bench_tokens.txt and, with --kazrag DIR, the Wikipedia benchmark
of that repository (its own BM25 and tokenizer, k1=1.5).

    python3 snowball/eval_snowball.py
    python3 snowball/eval_snowball.py --sbl snowball/kazakh.sbl --sbl /tmp/variant.sbl
    python3 snowball/eval_snowball.py --kazrag /tmp/kazrag --dump .cache/disagreements.tsv
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNOWBALL_DIR = os.path.join(ROOT, ".cache", "snowball")
BUILD_ROOT = os.path.join(ROOT, ".cache", "kazakh_build")
CLI = os.path.join(ROOT, "target", "release", "kazsearch")
LEX = os.path.join(ROOT, "data", "tsearch_data", "kaz_stems.dict")
STOP = os.path.join(ROOT, "data", "tsearch_data", "kaz_stopwords.stop")
CORPUS = os.path.join(ROOT, "data", "corpus", "articles.jsonl")
QUERIES = os.path.join(ROOT, "eval", "gold_queries_v2.jsonl")
BENCH_TOKENS = os.path.join(ROOT, "core", "tests", "bench_tokens.txt")

TOK = re.compile(r"[^\W\d_]+", re.UNICODE)


def build(sbl):
    """Compile an .sbl to C, link the stemwords driver, return the binary."""
    tag = hashlib.sha1(os.path.abspath(sbl).encode()).hexdigest()[:8]
    out = os.path.join(BUILD_ROOT, tag)
    os.makedirs(out, exist_ok=True)
    binary = os.path.join(out, "stemwords")
    subprocess.run([os.path.join(SNOWBALL_DIR, "snowball"), sbl, "-o",
                    os.path.join(out, "kazakh"), "-u", "-ep", "kazakh_UTF_8_"], check=True)
    runtime = os.path.join(SNOWBALL_DIR, "runtime")
    subprocess.run(["cc", "-O2", "-I", runtime, "-I", out, "-o", binary,
                    os.path.join(HERE, "stemwords.c"), os.path.join(out, "kazakh.c"),
                    os.path.join(runtime, "api.c"), os.path.join(runtime, "utilities.c")],
                   check=True)
    return binary


def snowball_map(binary, words):
    out = subprocess.run([binary], input="\n".join(words) + "\n",
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert len(out) == len(words), (len(out), len(words))
    return {w: line.split("\t")[1] for w, line in zip(words, out)}


def rust_map(words, lexicon):
    args = [CLI, "stem", "--stdin"] + (["--lexicon", LEX] if lexicon else [])
    out = subprocess.run(args, input="\n".join(words) + "\n",
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert len(out) == len(words), (len(out), len(words))
    return {w: line.split("\t")[-1].split("→")[-1].strip() for w, line in zip(words, out)}


def load_gold():
    docs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    queries = [json.loads(l) for l in open(QUERIES, encoding="utf-8")]
    stop = {w.strip() for w in open(STOP, encoding="utf-8") if w.strip()}

    def toks(s):
        return [t for t in TOK.findall(s.lower()) if t not in stop]

    doc_toks = [toks(d["title"] + " " + d["title"] + " " + d["body"]) for d in docs]
    q_toks = [toks(q["query"]) for q in queries]
    return docs, queries, doc_toks, q_toks


def bm25_per_query(m, docs, queries, doc_toks, q_toks, k1=1.2, b=0.75):
    """Return (recall@10 list, reciprocal-rank list, index term count)."""
    D = [[m[t] for t in ts] for ts in doc_toks]
    N = len(D)
    avgdl = sum(map(len, D)) / N
    df = Counter(t for d in D for t in set(d))
    tfs = [Counter(d) for d in D]
    r10, rr = [], []
    for q, qt in zip(queries, q_toks):
        qs = {m[t] for t in qt}
        scores = []
        for i, tf in enumerate(tfs):
            s = 0.0
            for t in qs:
                f = tf.get(t)
                if f:
                    idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(D[i]) / avgdl))
            if s:
                scores.append((s, i))
        top = [docs[i]["url"] for _, i in sorted(scores, reverse=True)[:10]]
        rel = set(q["relevant_urls"])
        r10.append(len(rel & set(top)) / len(rel))
        rr.append(next((1 / (k + 1) for k, u in enumerate(top) if u in rel), 0.0))
    return r10, rr, len(set(m.values()))


def bootstrap_ci(a, b, n=5000, seed=13):
    """95% CI of mean(a - b) over paired resamples of queries."""
    diffs = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    n_q = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n_q)] for _ in range(n_q)) / n_q for _ in range(n))
    return sum(diffs) / n_q, means[int(0.025 * n)], means[int(0.975 * n)]


def mean(xs):
    return sum(xs) / len(xs)


def agreement(sb_binary, dump):
    words = [l.split("\t")[0].strip() for l in open(BENCH_TOKENS, encoding="utf-8")]
    words = [w for w in words if w]
    sb = snowball_map(sb_binary, words)
    lex = rust_map(words, lexicon=True)
    nolex = rust_map(words, lexicon=False)
    same_lex = sum(sb[w] == lex[w] for w in words)
    same_nolex = sum(sb[w] == nolex[w] for w in words)
    sb_changed = sum(sb[w] != w for w in words)
    lex_changed = sum(lex[w] != w for w in words)
    if dump:
        with open(dump, "w", encoding="utf-8") as f:
            f.write("word\tsnowball\trust_lexicon\trust_nolexicon\n")
            for w in words:
                if sb[w] != lex[w]:
                    f.write(f"{w}\t{sb[w]}\t{lex[w]}\t{nolex[w]}\n")
    return {
        "tokens": len(words),
        "agree_with_rust_lexicon": same_lex / len(words),
        "agree_with_rust_nolexicon": same_nolex / len(words),
        "snowball_changed": sb_changed / len(words),
        "rust_lexicon_changed": lex_changed / len(words),
    }


class DictStemmer:
    def __init__(self, m):
        self.m = m

    def stem(self, token):
        return self.m.get(token, token)


def kazrag(kazrag_dir, stem_fns):
    """Wikipedia benchmark: recall@10 / mrr@10 per stemmer with bootstrap CIs."""
    # The harness is an optional external checkout, so it is imported here,
    # after its path is known, rather than at module level.
    sys.path.insert(0, kazrag_dir)
    from src.preprocess.tokenize import tokenize
    from src.queries import dataset
    from src.retrieval.bm25 import BM25Index, default_analyzer
    from src.eval import metrics

    corpus = dataset.load_corpus(os.path.join(kazrag_dir, "data/corpus/corpus.jsonl"))
    queries = dataset.load_queries(os.path.join(kazrag_dir, "data/queries/queries.jsonl"))
    qmap = dataset.queries_as_map(queries)
    qrels = dataset.qrels_from_queries(queries)
    vocab = set()
    for _, text in corpus:
        vocab.update(tokenize(text))
    for text in qmap.values():
        vocab.update(tokenize(text))
    vocab = sorted(vocab)

    per_query = {}
    summary = {}
    for name, fn in stem_fns.items():
        m = {t: t for t in vocab} if fn is None else fn(vocab)
        index = BM25Index(analyzer=default_analyzer(DictStemmer(m))).index(corpus)
        run = index.run(qmap, top_k=10)
        r = metrics.per_query_scores(run, qrels, "recall", 10)
        rr = metrics.per_query_scores(run, qrels, "mrr", 10)
        qids = sorted(r)
        per_query[name] = [r[q] for q in qids]
        summary[name] = {"recall@10": mean(per_query[name]), "mrr@10": mean([rr[q] for q in qids])}
    return summary, per_query


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sbl", action="append", help="algorithm file(s); default snowball/kazakh.sbl")
    ap.add_argument("--boot", type=int, default=5000, help="bootstrap resamples")
    ap.add_argument("--kazrag", help="path to the kazrag checkout for the Wikipedia benchmark")
    ap.add_argument("--dump", help="write Snowball/Rust-lexicon disagreements (TSV) here")
    ap.add_argument("--no-agreement", action="store_true")
    ap.add_argument("--json", help="write all numbers to this JSON file")
    args = ap.parse_args()
    sbls = args.sbl or [os.path.join(HERE, "kazakh.sbl")]

    binaries = {os.path.basename(s) if len(sbls) == 1 else s: build(s) for s in sbls}

    docs, queries, doc_toks, q_toks = load_gold()
    vocab = sorted({t for ts in doc_toks + q_toks for t in ts})
    maps = {"no stemming": {t: t for t in vocab}}
    for name, binary in binaries.items():
        maps[f"snowball {name}"] = snowball_map(binary, vocab)
    maps["rust, no lexicon"] = rust_map(vocab, lexicon=False)
    maps["rust + lexicon"] = rust_map(vocab, lexicon=True)

    result = {"gold_v2": {}, "gold_v2_ci": {}}
    per_query = {}
    print(f"gold_v2: {len(queries)} queries, {len(docs)} docs, {len(vocab)} vocab types\n")
    print(f"{'system':34s} {'R@10':>6s} {'MRR@10':>7s} {'terms':>7s}")
    for name, m in maps.items():
        r10, rr, terms = bm25_per_query(m, docs, queries, doc_toks, q_toks)
        per_query[name] = r10
        result["gold_v2"][name] = {"R@10": mean(r10), "MRR@10": mean(rr), "index_terms": terms}
        print(f"{name:34s} {mean(r10):6.3f} {mean(rr):7.3f} {terms:7d}")

    print("\npaired bootstrap on R@10 (mean difference, 95% CI):")
    pairs = []
    for name in maps:
        if name.startswith("snowball"):
            pairs += [(name, "no stemming"), (name, "rust, no lexicon"), (name, "rust + lexicon")]
    pairs.append(("rust, no lexicon", "no stemming"))
    for a, b in pairs:
        d, lo, hi = bootstrap_ci(per_query[a], per_query[b], n=args.boot)
        result["gold_v2_ci"][f"{a} - {b}"] = {"delta": d, "ci95": [lo, hi]}
        flag = "" if lo <= 0 <= hi else "  *"
        print(f"  {a} - {b}: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]{flag}")

    if not args.no_agreement:
        print(f"\nagreement over {os.path.relpath(BENCH_TOKENS, ROOT)}:")
        result["agreement"] = {}
        for name, binary in binaries.items():
            a = agreement(binary, args.dump if len(binaries) == 1 else None)
            result["agreement"][name] = a
            print(f"  {name}: {a['agree_with_rust_lexicon']:.3f} same stem as rust+lexicon, "
                  f"{a['agree_with_rust_nolexicon']:.3f} as rust no-lexicon "
                  f"(snowball changes {a['snowball_changed']:.3f} of tokens, "
                  f"rust+lexicon {a['rust_lexicon_changed']:.3f})")

    if args.kazrag:
        fns = {"no stemming": None}
        for name, binary in binaries.items():
            fns[f"snowball {name}"] = (lambda b: lambda v: snowball_map(b, v))(binary)
        fns["rust, no lexicon"] = lambda v: rust_map(v, lexicon=False)
        fns["rust + lexicon"] = lambda v: rust_map(v, lexicon=True)
        summary, pq = kazrag(args.kazrag, fns)
        result["kazrag"] = summary
        result["kazrag_ci"] = {}
        print(f"\nkazrag Wikipedia benchmark ({len(next(iter(pq.values())))} queries):")
        print(f"{'system':34s} {'R@10':>6s} {'MRR@10':>7s}")
        for name, s in summary.items():
            print(f"{name:34s} {s['recall@10']:6.3f} {s['mrr@10']:7.3f}")
        for name in summary:
            if name.startswith("snowball"):
                for other in ("no stemming", "rust, no lexicon"):
                    d, lo, hi = bootstrap_ci(pq[name], pq[other], n=args.boot)
                    result["kazrag_ci"][f"{name} - {other}"] = {"delta": d, "ci95": [lo, hi]}
                    flag = "" if lo <= 0 <= hi else "  *"
                    print(f"  {name} - {other}: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]{flag}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
