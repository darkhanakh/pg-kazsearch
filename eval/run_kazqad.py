#!/usr/bin/env python3
"""Stemmer comparison on KazQAD passage retrieval (ISSAI, CC BY-SA 4.0).

KazQAD questions come from the Kazakh national university-entrance exam (UNT)
and are judged against ~815k Kazakh Wikipedia passages by annotators who had
no connection to this project, so unlike gold_v2 nothing here was written
with this stemmer in mind.

Systems share one tokenizer, the repo stopword list and one BM25 index
implementation, and differ only in the token -> stem map:

    no stemming | Snowball kazakh.sbl | Rust, no lexicon | Rust + lexicon

The corpus is indexed once as a raw token-by-passage count matrix. Each system
maps raw tokens to stems (vocabulary stemmed in one batch), and the stemmed
matrix is X_raw @ M with M the one-hot raw-to-stem map. Scoring accumulates
BM25 weight columns per query term.

    just eval-kazqad
    uv run --no-project --with numpy --with scipy python eval/run_kazqad.py --help
"""

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import resource
import subprocess
import sys
import time
from array import array
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "snowball"))
import eval_snowball  # noqa: E402

DATASET_REPO = "https://github.com/IS2AI/KazQAD"
DATASET_COMMIT = "ab8684a667109f2a7345f4f89ab3b123e8d78e1f"
RAW_BASE = f"https://raw.githubusercontent.com/IS2AI/KazQAD/{DATASET_COMMIT}/data/information-retrieval"
CORPUS_FILES = [f"corpus/kazqad-corpus-v1.0-kk-part-{i}.jsonl.gz" for i in (1, 2, 3)]
SPLITS = ("test", "validation")
ALL_SPLITS = ("test", "validation", "train")

SNOWBALL_REPO = "https://github.com/snowballstem/snowball"
SNOWBALL_COMMIT = "6389c79f91cd67ed2de3ebdcf84ec8c2d2d23c11"

CACHE = ROOT / ".cache" / "kazqad"
STOPWORDS = ROOT / "data" / "tsearch_data" / "kaz_stopwords.stop"
SBL = ROOT / "snowball" / "kazakh.sbl"

SYSTEMS = ("no stemming", "snowball", "rust", "rust+lexicon")
PAIRS = (
    ("rust+lexicon", "no stemming"),
    ("rust+lexicon", "rust"),
    ("rust", "snowball"),
    ("rust+lexicon", "snowball"),
    ("snowball", "no stemming"),
    ("rust", "no stemming"),
)
METRICS = ("ndcg@10", "mrr@10", "recall@10", "recall@100")
PARAM_SETS = {"k1=0.9,b=0.4": (0.9, 0.4), "k1=1.2,b=0.75": (1.2, 0.75)}
PRIMARY_PARAMS = "k1=0.9,b=0.4"
TOP_K = 100
MAX_TOKEN_CHARS = 100

PAPER = {"ndcg@10": 0.1446, "mrr": 0.1443, "recall@100": 0.4491}


@dataclass(frozen=True)
class Harness:
    name: str
    tokenizer: str
    stopwords: bool


PRIMARY = Harness("alnum+stopwords", "alnum", True)
GATE_HARNESSES = (
    Harness("alnum, no stopwords", "alnum", False),
    Harness("whitespace, punctuation deleted, no stopwords", "ws", False),
)

_ALNUM = re.compile(r"[^\W_]+")
_PUNCT = re.compile(r"[^\w\s]|_")


def tokenize(text, kind):
    text = text.lower()
    if kind == "alnum":
        return _ALNUM.findall(text)
    if kind == "ws":
        return _PUNCT.sub("", text).split()
    raise ValueError(kind)


class Clock:
    def __init__(self):
        self.t0 = time.perf_counter()
        self.phases = {}

    def lap(self, name):
        now = time.perf_counter()
        self.phases[name] = round(now - self.t0 - sum(self.phases.values()), 1)
        print(f"  [{name}: {self.phases[name]}s, peak RSS {peak_rss_mb():.0f} MB]", flush=True)

    def total(self):
        return round(time.perf_counter() - self.t0, 1)


def peak_rss_mb():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1e6 if sys.platform == "darwin" else rss / 1e3


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def fetch_dataset():
    """Download the pinned KazQAD files into the cache; return {relpath: sha256}."""
    wanted = list(CORPUS_FILES)
    wanted += [f"topics/kazqad-topics-v1.0-kk-{s}.tsv" for s in ALL_SPLITS]
    wanted += [f"qrels/kazqad-qrels-v1.0-{s}.tsv" for s in ALL_SPLITS]
    shas = {}
    for rel in wanted:
        path = CACHE / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"  downloading {rel}", flush=True)
            run(["curl", "-sfL", "--retry", "3", "-o", str(path) + ".part", f"{RAW_BASE}/{rel}"])
            os.replace(str(path) + ".part", path)
        shas[rel] = sha256(path)
    return shas


def ensure_snowball_compiler():
    src = eval_snowball.SNOWBALL_DIR
    if not os.path.exists(os.path.join(src, "snowball")):
        if not os.path.isdir(os.path.join(src, ".git")):
            os.makedirs(os.path.dirname(src), exist_ok=True)
            run(["git", "clone", "--quiet", SNOWBALL_REPO, src])
        run(["git", "-C", src, "checkout", "--quiet", SNOWBALL_COMMIT])
        run(["make", "-C", src, "snowball", "-j4"], stdout=subprocess.DEVNULL)
    return SNOWBALL_COMMIT


def read_topics(split):
    topics = {}
    with open(CACHE / f"topics/kazqad-topics-v1.0-kk-{split}.tsv", encoding="utf-8") as f:
        for line in f:
            qid, text = line.rstrip("\n").split("\t", 1)
            topics[qid] = text
    return topics


def read_qrels(split):
    """qid -> set of docids judged relevant (grade 1). Grade 0 rows are judged non-relevant."""
    rel, judged_nonrel = {}, {}
    with open(CACHE / f"qrels/kazqad-qrels-v1.0-{split}.tsv", encoding="utf-8") as f:
        for line in f:
            qid, _, docid, grade = line.split()
            (rel if int(grade) > 0 else judged_nonrel).setdefault(qid, set()).add(docid)
    return rel, judged_nonrel


def iter_passages(limit=0):
    n = 0
    for rel in CORPUS_FILES:
        with gzip.open(CACHE / rel, "rt", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                yield d["docid"], d["title"], d["text"]
                n += 1
                if limit and n >= limit:
                    return


@dataclass
class RawIndex:
    docids: list
    vocab: dict
    counts: sp.csr_matrix
    doc_len: np.ndarray
    n_tokens: int
    dropped_long: int
    keep_text: dict


def build_raw_index(harness, stop, query_texts, keep_ids, limit):
    """Tokenize the corpus into a passage x raw-token count matrix.

    The vocabulary also receives every query token so a query word absent from
    the corpus can still stem onto a corpus stem.
    """
    vocab = {}
    get = vocab.get
    flat = array("i")
    lens = array("i")
    docids = []
    keep_text = {}
    dropped = 0
    kind = harness.tokenizer
    for docid, title, text in iter_passages(limit):
        docids.append(docid)
        if docid in keep_ids:
            keep_text[docid] = (title, text[:300])
        row = []
        for t in tokenize(f"{title} {text}", kind):
            if len(t) > MAX_TOKEN_CHARS:
                dropped += 1
                continue
            if harness.stopwords and t in stop:
                continue
            i = get(t)
            if i is None:
                i = vocab[t] = len(vocab)
            row.append(i)
        lens.append(len(row))
        flat.extend(row)
    for q in query_texts:
        for t in tokenize(q, kind):
            if len(t) <= MAX_TOKEN_CHARS and t not in vocab and not (harness.stopwords and t in stop):
                vocab[t] = len(vocab)

    n = len(docids)
    lens = np.frombuffer(lens, dtype=np.int32).astype(np.int64)
    cols = np.frombuffer(flat, dtype=np.int32).astype(np.int64)
    key = (np.repeat(np.arange(n, dtype=np.int64), lens) << 32) | cols
    del cols
    uniq, cnt = np.unique(key, return_counts=True)
    del key
    rows = uniq >> 32
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(np.bincount(rows, minlength=n), out=indptr[1:])
    counts = sp.csr_matrix(((cnt).astype(np.float64), (uniq & 0xFFFFFFFF).astype(np.int32), indptr),
                           shape=(n, len(vocab)))
    return RawIndex(docids, vocab, counts, lens.astype(np.float64), int(lens.sum()), dropped, keep_text)


def vocab_key(words):
    h = hashlib.sha1()
    for w in words:
        h.update(w.encode())
        h.update(b"\n")
    return h.hexdigest()[:16]


def stem_vocab(system, words, snowball_binary):
    """Return the stem of every word, in order. Cached on vocabulary + tool hashes."""
    if system == "no stemming":
        return list(words)
    tool = {
        "snowball": lambda: sha256(SBL),
        "rust": lambda: sha256(eval_snowball.CLI),
        "rust+lexicon": lambda: sha256(eval_snowball.CLI) + sha256(eval_snowball.LEX)
        + sha256(eval_snowball.LEX + ".verbs"),
    }[system]()
    key = hashlib.sha1((system + tool + vocab_key(words)).encode()).hexdigest()[:20]
    path = CACHE / "stems" / f"{key}.tsv"
    if path.exists():
        stems = path.read_text(encoding="utf-8").split("\n")[:-1]
        if len(stems) == len(words):
            return stems
    if system == "snowball":
        mapping = eval_snowball.snowball_map(snowball_binary, words)
    else:
        mapping = eval_snowball.rust_map(words, lexicon=system == "rust+lexicon")
    stems = [mapping[w] or w for w in words]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(stems) + "\n", encoding="utf-8")
    return stems


def stem_matrix(stems):
    """One-hot raw-token -> stem map as a (raw vocab x stem vocab) CSR matrix."""
    ids = {}
    cols = np.fromiter((ids.setdefault(s, len(ids)) for s in stems), dtype=np.int32, count=len(stems))
    m = sp.csr_matrix((np.ones(len(stems)), cols, np.arange(len(stems) + 1)), shape=(len(stems), len(ids)))
    return m, cols, len(ids)


class Bm25:
    """BM25 over one system's stemmed matrix, weights laid out per term column."""

    def __init__(self, counts_csr, doc_len):
        self.n_docs = counts_csr.shape[0]
        self.avgdl = float(doc_len.mean())
        self.csc = counts_csr.tocsc()
        self.csc.sort_indices()
        self.dl = doc_len[self.csc.indices]
        self.df = np.diff(self.csc.indptr).astype(np.float64)

    def weights(self, k1, b):
        idf = np.log1p((self.n_docs - self.df + 0.5) / (self.df + 0.5))
        col_of_entry = np.repeat(np.arange(len(self.df)), np.diff(self.csc.indptr))
        tf = self.csc.data
        norm = k1 * (1.0 - b + b * self.dl / self.avgdl)
        return tf * (k1 + 1.0) / (tf + norm) * idf[col_of_entry]

    def search(self, weights, term_ids, top_k=TOP_K):
        """Top-k passage indices by score; ties break to the lower passage index."""
        scores = np.zeros(self.n_docs)
        indptr, indices = self.csc.indptr, self.csc.indices
        for t in term_ids:
            lo, hi = indptr[t], indptr[t + 1]
            scores[indices[lo:hi]] += weights[lo:hi]
        hit = np.flatnonzero(scores)
        if len(hit) == 0:
            return np.empty(0, dtype=np.int64), np.empty(0)
        if len(hit) > top_k:
            thr = np.partition(scores[hit], -top_k)[-top_k]
            hit = hit[scores[hit] >= thr]
        order = np.lexsort((hit, -scores[hit]))[:top_k]
        return hit[order], scores[hit[order]]


def query_metrics(ranked, relevant, n_rel):
    """ndcg@10, mrr@10, recall@10, recall@100 plus the first relevant rank (0 = not in top-100).

    n_rel counts every judged-relevant passage, including any missing from the corpus.
    """
    hits = np.fromiter((d in relevant for d in ranked), dtype=bool, count=len(ranked))
    gains = hits[:10] / np.log2(np.arange(2, min(10, len(hits)) + 2))
    ideal = (1.0 / np.log2(np.arange(2, min(n_rel, 10) + 2))).sum()
    first = int(np.argmax(hits)) + 1 if hits.any() else 0
    return (
        gains.sum() / ideal,
        1.0 / first if 0 < first <= 10 else 0.0,
        hits[:10].sum() / n_rel,
        hits[:100].sum() / n_rel,
        first,
    )


def paired_bootstrap(diffs, idx):
    """Mean difference with a 95% percentile CI over the shared resample index matrix."""
    means = np.concatenate([diffs[idx[i:i + 1000]].mean(axis=1) for i in range(0, len(idx), 1000)])
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(diffs.mean()), float(lo), float(hi)


def summarize_pairs(per_query, idx):
    out = {}
    for a, b in PAIRS:
        entry = {}
        for m, mi in zip(METRICS, range(4)):
            d = per_query[a][:, mi] - per_query[b][:, mi]
            delta, lo, hi = paired_bootstrap(d, idx)
            entry[m] = {
                "delta": delta,
                "ci95": [lo, hi],
                "significant": bool(lo > 0 or hi < 0),
                "wins": int((d > 1e-12).sum()),
                "losses": int((d < -1e-12).sum()),
                "ties": int((np.abs(d) <= 1e-12).sum()),
            }
        out[f"{a} - {b}"] = entry
    return out


@dataclass
class Split:
    name: str
    qids: list
    texts: list
    relevant: list
    judged: list
    n_topics: int
    n_without_relevant: int
    n_relevant_not_in_corpus: int


def load_split(name, docid_index):
    topics = read_topics(name)
    rel, nonrel = read_qrels(name)
    qids = [q for q in topics if q in rel]
    missing = sum(1 for q in qids for d in rel[q] if d not in docid_index)
    return Split(name, qids, [topics[q] for q in qids], [rel[q] for q in qids],
                 [rel[q] | nonrel.get(q, set()) for q in qids],
                 len(topics), len(topics) - len(qids), missing)


def evaluate_system(system, raw, stop, harness, splits, docid_index, params, snowball_binary, want_overlap):
    stems = stem_vocab(system, list(raw.vocab), snowball_binary)
    m, raw_to_stem, n_stems = stem_matrix(stems)
    stemmed = (raw.counts @ m).tocsr()
    stemmed.sort_indices()

    def query_terms(text):
        toks = [t for t in tokenize(text, harness.tokenizer)
                if len(t) <= MAX_TOKEN_CHARS and not (harness.stopwords and t in stop)]
        return sorted({int(raw_to_stem[raw.vocab[t]]) for t in toks})

    overlap = {}
    if want_overlap:
        for s in splits:
            reach = []
            for text, rel in zip(s.texts, s.relevant):
                terms = np.array(query_terms(text), dtype=np.int32)
                for d in rel:
                    i = docid_index.get(d)
                    if i is None:
                        continue
                    row = stemmed.indices[stemmed.indptr[i]:stemmed.indptr[i + 1]]
                    reach.append(bool(np.isin(terms, row).any()) if len(terms) else False)
            overlap[s.name] = float(np.mean(reach))

    bm25 = Bm25(stemmed, raw.doc_len)
    del stemmed
    result = {"index_terms": n_stems, "overlap": overlap, "per_query": {}, "ranks": {}, "judged_at_10": {}}
    for label, (k1, b) in params.items():
        w = bm25.weights(k1, b)
        for s in splits:
            rows, judged_frac = [], []
            for text, rel, judged in zip(s.texts, s.relevant, s.judged):
                terms = [t for t in query_terms(text) if bm25.df[t] > 0]
                ranked, _ = bm25.search(w, terms)
                rel_idx = {docid_index[d] for d in rel if d in docid_index}
                rows.append(query_metrics(ranked, rel_idx, len(rel)))
                judged_idx = {docid_index[d] for d in judged if d in docid_index}
                if len(ranked):
                    judged_frac.append(np.mean([d in judged_idx for d in ranked[:10]]))
            result["judged_at_10"][(s.name, label)] = float(np.mean(judged_frac))
            arr = np.array(rows)
            result["per_query"][(s.name, label)] = arr[:, :4]
            result["ranks"][(s.name, label)] = arr[:, 4].astype(int)
    return result, stems


def mean_row(arr):
    return {m: float(arr[:, i].mean()) for i, m in enumerate(METRICS)}


def run_harness(harness, systems, splits, params, rng_idx, stop, docid_index, raw, snowball_binary,
                clock, want_overlap):
    out = {"systems": {}, "splits": {}}
    per_system = {}
    for system in systems:
        res, stems = evaluate_system(system, raw, stop, harness, splits, docid_index, params,
                                     snowball_binary, want_overlap)
        per_system[system] = (res, stems)
        clock.lap(f"{harness.name} / {system}")
    for s in splits:
        sp_out = {"queries": len(s.qids), "topics": s.n_topics, "topics_without_relevant": s.n_without_relevant,
                  "relevant_not_in_corpus": s.n_relevant_not_in_corpus, "params": {}}
        for label in params:
            pq = {sys_: per_system[sys_][0]["per_query"][(s.name, label)] for sys_ in systems}
            entry = {"metrics": {sys_: mean_row(pq[sys_]) for sys_ in systems}}
            for sys_ in systems:
                ranks = per_system[sys_][0]["ranks"][(s.name, label)]
                entry["metrics"][sys_]["mrr@100"] = float(np.where(ranks > 0, 1.0 / np.maximum(ranks, 1), 0).mean())
                entry["metrics"][sys_]["judged_fraction_of_top10"] = per_system[sys_][0]["judged_at_10"][(s.name, label)]
            all_topics_scale = len(s.qids) / s.n_topics
            entry["metrics_all_topics_denominator"] = {
                sys_: {m: v * all_topics_scale for m, v in mean_row(pq[sys_]).items()} for sys_ in systems}
            entry["pairs"] = summarize_pairs(pq, rng_idx[s.name]) if len(systems) > 1 else {}
            sp_out["params"][label] = entry
        out["splits"][s.name] = sp_out
    for system in systems:
        res = per_system[system][0]
        out["systems"][system] = {"index_terms": res["index_terms"], "relevant_pair_reachable": res["overlap"]}
    return out, per_system


def print_table(title, metrics):
    print(f"\n{title}")
    print(f"  {'system':14s} " + " ".join(f"{m:>10s}" for m in METRICS))
    for sys_, row in metrics.items():
        print(f"  {sys_:14s} " + " ".join(f"{row[m]:10.4f}" for m in METRICS))


def print_pairs(pairs):
    for name, entry in pairs.items():
        cells = []
        for m in METRICS:
            e = entry[m]
            cells.append(f"{m} {e['delta']:+.4f} [{e['ci95'][0]:+.4f},{e['ci95'][1]:+.4f}]{'*' if e['significant'] else ' '}")
        e = entry["ndcg@10"]
        print(f"  {name:32s} " + "  ".join(cells) + f"  W/L/T(ndcg) {e['wins']}/{e['losses']}/{e['ties']}")


def examples(per_system, splits, keep_text, harness, stop, raw_vocab, limit=6):
    """Test queries where Rust+lexicon and Snowball disagree most on nDCG@10."""
    s = splits[0]
    a, b = "rust+lexicon", "snowball"
    pa = per_system[a][0]["per_query"][(s.name, PRIMARY_PARAMS)]
    pb = per_system[b][0]["per_query"][(s.name, PRIMARY_PARAMS)]
    diff = pa[:, 0] - pb[:, 0]
    order = np.argsort(diff)
    picks = {"lexicon_better": order[::-1][:limit], "snowball_better": order[:limit]}
    stems = {sys_: per_system[sys_][1] for sys_ in SYSTEMS if sys_ in per_system}
    out = {}
    for kind, idxs in picks.items():
        out[kind] = []
        for qi in idxs:
            toks = [t for t in tokenize(s.texts[qi], harness.tokenizer) if not (harness.stopwords and t in stop)]
            rel_docs = sorted(s.relevant[qi])
            out[kind].append({
                "qid": s.qids[qi],
                "query": s.texts[qi],
                "ndcg@10": {sys_: float(per_system[sys_][0]["per_query"][(s.name, PRIMARY_PARAMS)][qi, 0])
                            for sys_ in per_system},
                "first_relevant_rank": {sys_: int(per_system[sys_][0]["ranks"][(s.name, PRIMARY_PARAMS)][qi])
                                        for sys_ in per_system},
                "query_stems": {sys_: [stems[sys_][raw_vocab[t]] for t in toks] for sys_ in stems},
                "relevant": [{"docid": d, "title": keep_text.get(d, ("", ""))[0],
                              "text": keep_text.get(d, ("", ""))[1][:200]} for d in rel_docs[:2]],
            })
    return out


def stem_change_rates(per_system, splits, harness, stop, raw_vocab):
    s = splits[0]
    toks = sorted({t for text in s.texts for t in tokenize(text, harness.tokenizer)
                   if not (harness.stopwords and t in stop)})
    out = {"test_query_token_types": len(toks)}
    for sys_, (_, stems) in per_system.items():
        out[sys_] = {"changed_fraction": float(np.mean([stems[raw_vocab[t]] != t for t in toks]))}
    for a, b in PAIRS:
        if a in per_system and b in per_system:
            out[f"same_stem {a} / {b}"] = float(np.mean(
                [per_system[a][1][raw_vocab[t]] == per_system[b][1][raw_vocab[t]] for t in toks]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "eval" / "results" / "kazqad.json"))
    ap.add_argument("--boot", type=int, default=10000, help="paired bootstrap resamples")
    ap.add_argument("--seed", type=int, default=20260501)
    ap.add_argument("--limit-docs", type=int, default=0, help="index only the first N passages (smoke test)")
    ap.add_argument("--skip-gate", action="store_true", help="skip the paper-baseline reproduction harnesses")
    args = ap.parse_args()

    if not os.path.exists(eval_snowball.CLI):
        sys.exit("kazsearch CLI not found. Build it first: cargo build --release -p kazsearch-cli")

    clock = Clock()
    print("fetching data and tools", flush=True)
    dataset_shas = fetch_dataset()
    snowball_commit = ensure_snowball_compiler()
    snowball_binary = eval_snowball.build(str(SBL))
    clock.lap("fetch+build")

    stop = {w.strip() for w in STOPWORDS.read_text(encoding="utf-8").split("\n") if w.strip()}
    topics = {s: read_topics(s) for s in ALL_SPLITS}
    keep_ids = set()
    for s in SPLITS:
        for rel in read_qrels(s)[0].values():
            keep_ids |= rel
    eval_queries = [t for s in SPLITS for t in topics[s].values()]

    result = {
        "dataset": {"name": "KazQAD information-retrieval", "repo": DATASET_REPO, "commit": DATASET_COMMIT,
                    "license": "CC BY-SA 4.0", "files_sha256": dataset_shas},
        "parameters": {"param_sets": PARAM_SETS, "primary_params": PRIMARY_PARAMS, "top_k": TOP_K,
                       "bootstrap_resamples": args.boot, "bootstrap_seed": args.seed,
                       "primary_harness": PRIMARY.__dict__, "stopword_file": "data/tsearch_data/kaz_stopwords.stop",
                       "document_text": "title + passage text", "max_token_chars": MAX_TOKEN_CHARS,
                       "relevance": "grade 1 = relevant; grade 0 judged non-relevant, ignored by the metrics",
                       "query_population": "topics with at least one relevant judgment",
                       "limit_docs": args.limit_docs or None},
        "tools": {"kazsearch_cli_sha256": sha256(eval_snowball.CLI),
                  "lexicon_sha256": sha256(eval_snowball.LEX),
                  "lexicon_verbs_sha256": sha256(eval_snowball.LEX + ".verbs"),
                  "snowball_sbl_sha256": sha256(SBL), "snowball_compiler_commit": snowball_commit},
        "results": {},
    }

    harnesses = [PRIMARY] + ([] if args.skip_gate else list(GATE_HARNESSES))
    rng = np.random.default_rng(args.seed)
    rng_idx = {}
    split_cache = {}

    for hi, harness in enumerate(harnesses):
        print(f"\n=== harness: {harness.name} ===", flush=True)
        primary = hi == 0
        raw = build_raw_index(harness, stop, eval_queries, keep_ids, args.limit_docs)
        clock.lap(f"{harness.name} / tokenize+count")
        docid_index = {d: i for i, d in enumerate(raw.docids)}
        if primary:
            splits = [load_split(s, docid_index) for s in SPLITS]
            for s in splits:
                rng_idx[s.name] = rng.integers(0, len(s.qids), size=(args.boot, len(s.qids)), dtype=np.int32)
            split_cache["splits"] = splits
            result["corpus"] = {"passages": len(raw.docids), "tokens": raw.n_tokens,
                                "raw_vocab_types": len(raw.vocab), "tokens_dropped_over_max_len": raw.dropped_long,
                                "mean_passage_tokens": raw.n_tokens / len(raw.docids)}
        splits = split_cache["splits"]
        systems = SYSTEMS if primary else ("no stemming",)
        params = PARAM_SETS
        out, per_system = run_harness(harness, systems, splits, params, rng_idx, stop, docid_index, raw,
                                      snowball_binary, clock, want_overlap=primary)
        out["harness"] = harness.__dict__
        result["results"][harness.name] = out
        if primary:
            keep_text = raw.keep_text
            raw_vocab = raw.vocab
            result["query_token_stems"] = stem_change_rates(per_system, splits, harness, stop, raw_vocab)
            result["examples_test_lexicon_vs_snowball"] = examples(
                per_system, splits, keep_text, harness, stop, raw_vocab)
            ceiling = {}
            for s in splits:
                ranks = np.stack([per_system[sys_][0]["ranks"][(s.name, PRIMARY_PARAMS)] for sys_ in systems])
                ceiling[s.name] = {
                    "queries_with_relevant_in_top100_any_system": float((ranks > 0).any(axis=0).mean()),
                    "queries_with_relevant_in_top100_all_systems": float((ranks > 0).all(axis=0).mean()),
                    **{f"queries_with_relevant_in_top100_{sys_}": float((r > 0).mean())
                       for sys_, r in zip(systems, ranks)},
                }
            result["recall_ceiling"] = ceiling
        del raw, per_system

        for s in splits:
            for label in params:
                print_table(f"[{harness.name}] {s.name} ({len(s.qids)} queries) {label}",
                            out["splits"][s.name]["params"][label]["metrics"])
                if primary:
                    print_pairs(out["splits"][s.name]["params"][label]["pairs"])

    gate = {}
    for hname in (h.name for h in harnesses):
        node = result["results"][hname]["splits"]["test"]["params"]
        gate[hname] = {label: {
            "no stemming": node[label]["metrics"]["no stemming"],
            "no stemming, all topics as denominator": node[label]["metrics_all_topics_denominator"]["no stemming"],
        } for label in PARAM_SETS}
    result["paper_baseline"] = {
        "source": "KazQAD paper (LREC-COLING 2024), Table 4, 'BM25 (title+text)' candidate generator, FlexNeuART, "
                  "whitespace tokenisation with lowercase and punctuation removal",
        "reported": PAPER,
        "note": "The abstract's NDCG@10 0.389 / MRR 0.382 is the fine-tuned XLM-R re-ranker, not BM25.",
        "reproduction": gate,
    }

    result["environment"] = {
        "wall_seconds": clock.total(), "phases_seconds": clock.phases, "peak_rss_mb": round(peak_rss_mb()),
        "machine": f"{platform.platform()}, {os.cpu_count()} cores",
        "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nwall {clock.total()}s, peak RSS {peak_rss_mb():.0f} MB, wrote {args.out}")


if __name__ == "__main__":
    main()
