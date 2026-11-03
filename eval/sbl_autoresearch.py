#!/usr/bin/env python3
"""Score a candidate kazakh.sbl against a baseline for an autoresearch loop.

The loop optimises on KazQAD train (3,487 questions) and gates on KazQAD
validation (548) and the news set (132). KazQAD test (1,929) is read only by
`holdout`, the one check run after the loop has stopped.

    build-index   tokenize the KazQAD corpus once and save the raw count matrix
    score CAND BASE [--gate-out FILE]
                  compile both, stem the vocabulary with each, report
                  METRIC lines and write the gate verdict as JSON
    holdout CAND BASE --out FILE
                  nDCG@10 of both on KazQAD test with paired-bootstrap intervals

A candidate passes the gate when it compiles without compiler output, its
train nDCG@10 gain over the baseline has a 99% paired-bootstrap lower bound
above zero, its validation gain is positive, and it is not significantly
worse on the news set.

    uv run --no-project --with numpy --with scipy python eval/sbl_autoresearch.py build-index
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "snowball"))
import eval_snowball  # noqa: E402
import run_kazqad as rk  # noqa: E402

LOOP_SPLITS = ("train", "validation")
INDEX = rk.CACHE / "loop_index"
SCORES = rk.CACHE / "loop_scores"
BOOT = 10000
SEED = 20261102
TRAIN_ALPHA = 0.01
NEWS_MAX_DROP = 0.015


def sha256_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def build_index():
    rk.fetch_dataset()
    stop = load_stop()
    queries = [t for s in LOOP_SPLITS for t in rk.read_topics(s).values()]
    t0 = time.perf_counter()
    raw = rk.build_raw_index(rk.PRIMARY, stop, queries, set(), 0)
    INDEX.mkdir(parents=True, exist_ok=True)
    c = raw.counts
    np.savez(INDEX / "counts.npz", data=c.data.astype(np.float32), indices=c.indices,
             indptr=c.indptr, shape=np.array(c.shape), doc_len=raw.doc_len)
    (INDEX / "vocab.txt").write_text("\n".join(raw.vocab) + "\n", encoding="utf-8")
    (INDEX / "docids.txt").write_text("\n".join(raw.docids) + "\n", encoding="utf-8")
    print(f"indexed {len(raw.docids)} passages, {len(raw.vocab)} types, {c.nnz} nonzeros "
          f"in {time.perf_counter() - t0:.0f}s")


def load_stop():
    return {w.strip() for w in rk.STOPWORDS.read_text(encoding="utf-8").split("\n") if w.strip()}


def load_index():
    z = np.load(INDEX / "counts.npz")
    counts = sp.csr_matrix((z["data"].astype(np.float64), z["indices"], z["indptr"]), shape=tuple(z["shape"]))
    vocab = (INDEX / "vocab.txt").read_text(encoding="utf-8").split("\n")[:-1]
    docids = (INDEX / "docids.txt").read_text(encoding="utf-8").split("\n")[:-1]
    return counts, z["doc_len"], {w: i for i, w in enumerate(vocab)}, vocab, docids


def compile_sbl(sbl_text, workdir):
    """Compile with the pinned compiler; any compiler output counts as a failure."""
    src = Path(workdir) / "kazakh.sbl"
    src.write_text(sbl_text, encoding="utf-8")
    out = Path(workdir) / "kazakh"
    p = subprocess.run([os.path.join(eval_snowball.SNOWBALL_DIR, "snowball"), str(src), "-o", str(out),
                        "-u", "-ep", "kazakh_UTF_8_"], capture_output=True, text=True)
    if p.returncode or p.stdout.strip() or p.stderr.strip():
        return None, (p.stdout + p.stderr).strip() or f"exit {p.returncode}"
    runtime = os.path.join(eval_snowball.SNOWBALL_DIR, "runtime")
    sources = [os.path.join(runtime, f) for f in ("api.c", "utilities.c", "snowball_runtime.c")
               if os.path.exists(os.path.join(runtime, f))]
    binary = Path(workdir) / "stemwords"
    p = subprocess.run(["cc", "-O2", "-I", runtime, "-I", workdir, "-o", str(binary),
                        os.path.join(eval_snowball.HERE, "stemwords.c"), f"{out}.c", *sources],
                       capture_output=True, text=True)
    if p.returncode:
        return None, p.stderr.strip()
    return str(binary), ""


def kazqad_per_query(binary, index, splits):
    counts, doc_len, vocab_ids, vocab, _ = index
    mapping = eval_snowball.snowball_map(binary, vocab)
    m, raw_to_stem, _ = rk.stem_matrix([mapping[w] or w for w in vocab])
    bm25 = rk.Bm25((counts @ m).tocsr(), doc_len)
    w = bm25.weights(*rk.PARAM_SETS[rk.PRIMARY_PARAMS])
    stop = load_stop()
    out = {}
    for s in splits:
        rows = []
        for text, rel_idx, n_rel in zip(s["texts"], s["rel_idx"], s["n_rel"]):
            toks = [t for t in rk.tokenize(text, rk.PRIMARY.tokenizer)
                    if len(t) <= rk.MAX_TOKEN_CHARS and t not in stop]
            terms = sorted({int(raw_to_stem[vocab_ids[t]]) for t in toks})
            terms = [t for t in terms if bm25.df[t] > 0]
            ranked, _ = bm25.search(w, terms)
            rows.append(rk.query_metrics(ranked, rel_idx, n_rel)[0])
        out[s["name"]] = np.array(rows)
    return out


def news_per_query(binary, gold):
    docs, queries, doc_toks, q_toks, vocab = gold
    m = eval_snowball.snowball_map(binary, vocab)
    r10, _, _ = eval_snowball.bm25_per_query(m, docs, queries, doc_toks, q_toks)
    return np.array(r10)


def load_gold():
    docs, queries, doc_toks, q_toks = eval_snowball.load_gold()
    vocab = sorted({t for ts in doc_toks + q_toks for t in ts})
    return docs, queries, doc_toks, q_toks, vocab


def per_query_cached(sbl_text, binary, index, splits, gold):
    """Per-query scores for one algorithm, cached on its text so the baseline is scored once."""
    SCORES.mkdir(parents=True, exist_ok=True)
    path = SCORES / f"{sha256_text(sbl_text)[:20]}.npz"
    if path.exists():
        z = np.load(path)
        return {k: z[k] for k in z.files}
    res = {**kazqad_per_query(binary, index, splits), "news": news_per_query(binary, gold)}
    np.savez(path, **res)
    return res


def boot_ci(diff, alpha, rng_idx):
    means = np.concatenate([diff[rng_idx[i:i + 1000]].mean(axis=1) for i in range(0, len(rng_idx), 1000)])
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(diff.mean()), float(lo), float(hi)


def score(cand_path, base_path, gate_out):
    cand_text = Path(cand_path).read_text(encoding="utf-8")
    base_text = Path(base_path).read_text(encoding="utf-8")
    verdict = {"pass": False, "reasons": []}

    with tempfile.TemporaryDirectory() as tc, tempfile.TemporaryDirectory() as tb:
        cand_bin, err = compile_sbl(cand_text, tc)
        if cand_bin is None:
            print(f"compile failed:\n{err}")
            verdict["reasons"].append("compile: " + err[:500])
            write(gate_out, verdict)
            sys.exit(1)
        base_bin, err = compile_sbl(base_text, tb)
        if base_bin is None:
            sys.exit(f"baseline does not compile:\n{err}")

        t0 = time.perf_counter()
        index = load_index()
        docid_index = {d: i for i, d in enumerate(index[4])}
        splits = []
        for name in LOOP_SPLITS:
            s = rk.load_split(name, docid_index)
            splits.append({"name": name, "texts": s.texts, "n_rel": [len(r) for r in s.relevant],
                           "rel_idx": [{docid_index[d] for d in r if d in docid_index} for r in s.relevant]})
        gold = load_gold()
        base = per_query_cached(base_text, base_bin, index, splits, gold)
        cand = per_query_cached(cand_text, cand_bin, index, splits, gold)
        elapsed = time.perf_counter() - t0

    rng = np.random.default_rng(SEED)
    res = {}
    for key, alpha in (("train", TRAIN_ALPHA), ("validation", 0.05), ("news", 0.05)):
        idx = rng.integers(0, len(base[key]), size=(BOOT, len(base[key])), dtype=np.int32)
        d, lo, hi = boot_ci(cand[key] - base[key], alpha, idx)
        res[key] = {"cand": float(cand[key].mean()), "base": float(base[key].mean()),
                    "delta": d, "lo": lo, "hi": hi, "alpha": alpha,
                    "wins": int((cand[key] - base[key] > 1e-12).sum()),
                    "losses": int((cand[key] - base[key] < -1e-12).sum())}

    identical = cand_text == base_text
    t, v, n = res["train"], res["validation"], res["news"]
    if identical:
        verdict["pass"] = True
        verdict["reasons"].append("candidate identical to baseline")
    else:
        if not t["lo"] > 0:
            verdict["reasons"].append(f"train gain {t['delta']:+.4f} has 99% lower bound {t['lo']:+.4f} <= 0")
        if not v["delta"] > 0:
            verdict["reasons"].append(f"validation gain {v['delta']:+.4f} <= 0")
        if n["hi"] < 0 or n["delta"] < -NEWS_MAX_DROP:
            verdict["reasons"].append(f"news recall@10 {n['delta']:+.4f} [{n['lo']:+.4f}, {n['hi']:+.4f}] is a drop")
        verdict["pass"] = not verdict["reasons"]
    verdict["results"] = res
    write(gate_out, verdict)

    print(f"METRIC ndcg_train={t['cand']:.5f}")
    print(f"METRIC d_train={t['delta']:.5f}")
    print(f"METRIC lo99_train={t['lo']:.5f}")
    print(f"METRIC d_val={v['delta']:.5f}")
    print(f"METRIC d_news_r10={n['delta']:.5f}")
    print(f"METRIC train_wins={t['wins']}")
    print(f"METRIC train_losses={t['losses']}")
    print(f"METRIC gate_pass={int(verdict['pass'])}")
    print(f"METRIC eval_seconds={elapsed:.1f}")
    for r in verdict["reasons"]:
        print(f"gate: {r}")


def holdout(cand_path, base_path, out):
    rk.fetch_dataset()
    stop = load_stop()
    raw = rk.build_raw_index(rk.PRIMARY, stop, list(rk.read_topics("test").values()), set(), 0)
    docid_index = {d: i for i, d in enumerate(raw.docids)}
    s = rk.load_split("test", docid_index)
    split = {"name": "test", "texts": s.texts, "n_rel": [len(r) for r in s.relevant],
             "rel_idx": [{docid_index[d] for d in r if d in docid_index} for r in s.relevant]}
    index = (raw.counts, raw.doc_len, raw.vocab, list(raw.vocab), raw.docids)
    scores = {}
    for name, path in (("baseline", base_path), ("candidate", cand_path)):
        with tempfile.TemporaryDirectory() as d:
            binary, err = compile_sbl(Path(path).read_text(encoding="utf-8"), d)
            if binary is None:
                sys.exit(f"{path} does not compile:\n{err}")
            scores[name] = kazqad_per_query(binary, index, [split])["test"]
    diff = scores["candidate"] - scores["baseline"]
    idx = np.random.default_rng(SEED).integers(0, len(diff), size=(BOOT, len(diff)), dtype=np.int32)
    result = {"split": "test", "queries": len(diff), "metric": "ndcg@10", "params": rk.PRIMARY_PARAMS,
              "baseline": float(scores["baseline"].mean()), "candidate": float(scores["candidate"].mean()),
              "wins": int((diff > 1e-12).sum()), "losses": int((diff < -1e-12).sum()),
              "bootstrap": {"resamples": BOOT, "seed": SEED}}
    for alpha in (0.05, 0.01):
        d, lo, hi = boot_ci(diff, alpha, idx)
        result["delta"] = d
        result[f"ci{int(100 * (1 - alpha))}"] = [lo, hi]
    Path(out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"test nDCG@10 {result['baseline']:.4f} -> {result['candidate']:.4f}, delta {result['delta']:+.4f} "
          f"95% [{result['ci95'][0]:+.4f}, {result['ci95'][1]:+.4f}], {result['wins']} wins / {result['losses']} losses")


def write(path, verdict):
    if path:
        Path(path).write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-index")
    s = sub.add_parser("score")
    s.add_argument("candidate")
    s.add_argument("baseline")
    s.add_argument("--gate-out")
    h = sub.add_parser("holdout")
    h.add_argument("candidate")
    h.add_argument("baseline")
    h.add_argument("--out", required=True)
    args = ap.parse_args()
    rk.ensure_snowball_compiler()
    if args.cmd == "build-index":
        build_index()
    elif args.cmd == "score":
        score(args.candidate, args.baseline, args.gate_out)
    else:
        holdout(args.candidate, args.baseline, args.out)


if __name__ == "__main__":
    main()
