"""Measurement lever for Russian-keyboard restoration (`--keyboard restore`).

Every stemming call goes through the production CLI, once in Exact mode and
once in Restore mode, so the numbers describe the shipped Rust build.

Measures, all on this repo's data:
  (a) agreement: share of keyboard-folded corpus tokens whose stem equals
      the stem of the proper form (full fold, and a seeded 50% partial fold);
  (b) regressions: proper corpus tokens whose stem changes under Restore,
      split into naturally Kazakh-letter-free tokens and tokens with Kazakh
      letters, plus a fixed probe of frequent inflected Russian words;
  (c) retrieval proxy: gold_queries_v2, proper vs keyboard-folded queries,
      AND semantics (websearch_to_tsquery) with the README's OR fallback,
      ranked by log-tf.idf. The PostgreSQL confirmation is run_eval.py on
      the folded gold file this script writes;
  (d) idempotence stem(stem(w)) == stem(w) over every input and output;
  (e) cost: extra stem_cyrillic calls per token (max and corpus means);
  (f) Exact-mode byte identity against a baseline CLI build on
      core/tests/bench_tokens.txt (pass --baseline-cli).

Usage:
    cargo build --release -p kazsearch-cli
    python3 eval/measure_keyboard_fold.py --corpus data/corpus/articles.jsonl \
        [--baseline-cli /path/to/main/kazsearch] --out eval/results/keyboard_fold.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

KAZ = set("әіңғүұқөһ")
FOLD = str.maketrans({"қ": "к", "ғ": "г", "ң": "н", "ұ": "у", "ү": "у",
                      "і": "и", "ә": "а", "ө": "о", "һ": "х"})
TOKEN_RE = re.compile(r"[^\W\d_]+")
CYR_RE = re.compile(r"[а-яёәіңғүұқөһ]+")

# Constraint-5 probe: frequent inflected Russian words (no Kazakh letters).
# Any change here is a collision with an invented Kazakh stem.
RUSSIAN_PROBE = """который которые которых области района года после также может
время было были будет если когда только между через против более очень
человек people россии президента министра правительства государственный
компании работы вопрос вопросы сказал сказала заявил новости города
республики казахстана жителей детей школы больницы дороги погода около
нужно можно сегодня вчера здесь тогда потому поэтому кроме всего своих
наших который области района годах условиях данных случае""".split()

PROBES = ["мектептеримизде", "шаруашылыгы", "онимдери", "колдарына", "колге",
          "казакстандагы", "республикасынын", "енбек", "тунде", "жана"]


def fold(s: str) -> str:
    return s.translate(FOLD)


def has_k(s: str) -> bool:
    return any(c in KAZ for c in s)


def partial_fold(s: str, p: float = 0.5) -> str:
    out = []
    for i, ch in enumerate(s):
        if ch in KAZ:
            h = hashlib.blake2b(f"{s}:{i}".encode(), digest_size=2).digest()
            if int.from_bytes(h, "big") / 65535 < p:
                ch = fold(ch)
        out.append(ch)
    return "".join(out)


class Stemmer:
    """Batched CLI access. `exact[w]`, `restore[w]`, `cost[w]`."""

    def __init__(self, cli: str, lexicon: str):
        self.cli, self.lexicon = cli, lexicon
        self.exact: dict[str, str] = {}
        self.restore: dict[str, str] = {}
        self.cost: dict[str, int] = {}

    def _run(self, words: list[str], extra: list[str]) -> list[str]:
        cmd = [self.cli, "stem", "--stdin", "--lexicon", self.lexicon, *extra]
        res = subprocess.run(cmd, input="\n".join(words) + "\n", capture_output=True,
                             text=True, check=True)
        return res.stdout.splitlines()

    def stem_all(self, words) -> None:
        todo = sorted({w for w in words if w and w not in self.restore})
        if not todo:
            return
        for line in self._run(todo, []):
            w, s = line.split("\t")
            self.exact[w] = s
        for line in self._run(todo, ["--keyboard", "restore", "--cost"]):
            w, s, c = line.split("\t")
            self.restore[w] = s
            self.cost[w] = int(c)


def retrieval(queries, docs_tokens, stopwords, stem_map, k=10):
    """AND (websearch) with OR fallback; rank = sum of tf-idf over matched stems."""
    df = collections.Counter()
    doc_tf = []
    for toks in docs_tokens:
        tf = collections.Counter(stem_map[t] for t in toks if t not in stopwords)
        doc_tf.append(tf)
        df.update(tf.keys())
    n = len(doc_tf)
    inv = collections.defaultdict(set)
    for i, tf in enumerate(doc_tf):
        for s in tf:
            inv[s].add(i)

    def score(i, qs):
        return sum((1 + math.log(doc_tf[i][s])) * math.log(n / df[s]) for s in qs if doc_tf[i][s])

    recall, mrr, zero_and = [], [], 0
    for q in queries:
        qs = [stem_map[t] for t in q["tokens"] if t not in stopwords]
        if not qs:
            recall.append(0.0)
            mrr.append(0.0)
            zero_and += 1
            continue
        sets = [inv.get(s, set()) for s in qs]
        hits = set.intersection(*sets)
        if not hits:
            zero_and += 1
            hits = set.union(*sets)
        ranked = sorted(hits, key=lambda i: (-score(i, qs), i))[:k]
        rel = q["relevant"]
        found = [r for r, i in enumerate(ranked) if i in rel]
        recall.append(len(found) / len(rel) if rel else 0.0)
        mrr.append(1.0 / (found[0] + 1) if found else 0.0)
    m = len(queries)
    return {"recall@10": round(sum(recall) / m, 4), "mrr@10": round(sum(mrr) / m, 4),
            "and_zero_hit_queries": zero_and}


def strong_syll(s: str) -> int:
    return sum(1 for c in s if c in set("аоұыәеөүіяэ"))


def miss_classes(miss, lex, exact):
    tot = sum(m[-1] for m in miss)
    cls = collections.Counter()
    for _w, f, proper_stem, _got, n in miss:
        if exact[f] in lex:
            cls["false_friend_gate (folded stem is a real entry)"] += n
        elif strong_syll(proper_stem) <= 1:
            cls["short_root (<=1 strong syllable, blocked by policy)"] += n
        elif proper_stem not in lex:
            cls["proper stem not in lexicon (names, OOV)"] += n
        else:
            cls["other (no admissible candidate / wrong parse)"] += n
    return {k: f"{v} ({100 * v / tot:.1f}% of misses)" for k, v in cls.most_common()}


def write_folded_gold(src: Path, dst: Path) -> None:
    with src.open(encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            q["query"] = fold(q["query"].lower())
            q["source"] = "gold_v2_kbfold"
            fout.write(json.dumps(q, ensure_ascii=False) + "\n")


def exact_byte_identity(baseline_cli: str, cli: str, lexicon: str, tokens_file: Path) -> dict:
    words = sorted({l.strip() for l in tokens_file.read_text(encoding="utf-8").splitlines() if l.strip()})
    outs = {}
    for name, binary in (("baseline", baseline_cli), ("exact", cli)):
        res = subprocess.run([binary, "stem", "--stdin", "--lexicon", lexicon],
                             input="\n".join(words) + "\n", capture_output=True, text=True, check=True)
        outs[name] = dict(l.split("\t") for l in res.stdout.splitlines())
    diffs = [(w, outs["baseline"].get(w), outs["exact"].get(w))
             for w in words if outs["baseline"].get(w) != outs["exact"].get(w)]
    return {"tokens": len(words), "mismatches": len(diffs), "examples": diffs[:20]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--cli", default=None, help="kazsearch binary (default: <repo>/target/release/kazsearch)")
    ap.add_argument("--corpus", default=None, help="articles.jsonl (default: <repo>/data/corpus/articles.jsonl)")
    ap.add_argument("--baseline-cli", default=None,
                    help="kazsearch built from origin/main, for the Exact byte-identity check")
    ap.add_argument("--out", default=None, help="JSON report (default: <repo>/eval/results/keyboard_fold.json)")
    args = ap.parse_args()

    repo = Path(args.repo)
    cli = args.cli or str(repo / "target/release/kazsearch")
    corpus = Path(args.corpus or repo / "data/corpus/articles.jsonl")
    out_path = Path(args.out or repo / "eval/results/keyboard_fold.json")
    lexp = str(repo / "data/tsearch_data/kaz_stems.dict")
    lex = {l.strip() for l in open(lexp, encoding="utf-8") if l.strip() and not l.startswith("#")}
    stop = {l.strip() for l in open(repo / "data/tsearch_data/kaz_stopwords.stop", encoding="utf-8") if l.strip()}

    gold_src = repo / "eval/gold_queries_v2.jsonl"
    gold_folded = repo / "eval/gold_queries_v2.kbfold.jsonl"
    write_folded_gold(gold_src, gold_folded)

    freq = collections.Counter()
    docs, urls = [], []
    for line in open(corpus, encoding="utf-8"):
        r = json.loads(line)
        toks = [t for t in TOKEN_RE.findall((r["title"] + " " + r["body"]).lower()) if CYR_RE.fullmatch(t)]
        docs.append(toks)
        urls.append(r["url"])
        freq.update(toks)
    url_idx = {u: i for i, u in enumerate(urls)}
    proper = list(freq)
    full = {w: fold(w) for w in proper}
    part = {w: partial_fold(w) for w in proper}
    docs_folded = [[full[t] for t in toks] for toks in docs]

    queries = []
    for line in open(gold_src, encoding="utf-8"):
        q = json.loads(line)
        rel = {url_idx[u] for u in q["relevant_urls"] if u in url_idx}
        toks = [t for t in TOKEN_RE.findall(q["query"].lower()) if CYR_RE.fullmatch(t)]
        queries.append({"tokens": toks, "relevant": rel})
    qfold = [{"tokens": [fold(t) for t in q["tokens"]], "relevant": q["relevant"]} for q in queries]

    st = Stemmer(cli, lexp)
    inputs = set(proper) | set(full.values()) | set(part.values()) | set(RUSSIAN_PROBE) | set(PROBES)
    inputs |= {t for q in qfold for t in q["tokens"]} | {t for q in queries for t in q["tokens"]}
    st.stem_all(inputs)
    exact, new = st.exact, st.restore

    outs = set(new.values())
    st.stem_all(outs)
    idem_viol = [(w, new[w], new[new[w]]) for w in inputs if new[new[w]] != new[w]]
    exact_idem_viol = [(w, exact[w]) for w in inputs if exact.get(exact[w], exact[w]) != exact[w]]

    with_k = [w for w in proper if has_k(w)]
    no_k = [w for w in proper if not has_k(w)]

    def agree(pairs):
        tok = sum(freq[w] for w, _ in pairs)
        return {"types": len(pairs), "tokens": tok,
                "exact_pct": round(100 * sum(freq[w] for w, f in pairs if exact[f] == exact[w]) / tok, 2),
                "restore_pct": round(100 * sum(freq[w] for w, f in pairs if new[f] == exact[w]) / tok, 2)}

    def regress(ws):
        ch = sorted((w for w in ws if new[w] != exact[w]), key=lambda x: -freq[x])
        tot = sum(freq[w] for w in ws)
        return {"types": len(ws), "tokens": tot,
                "changed_types": len(ch), "changed_tokens": sum(freq[w] for w in ch),
                "changed_tok_pct": round(100 * sum(freq[w] for w in ch) / tot, 3),
                "examples": [(w, exact[w], new[w], freq[w]) for w in ch[:40]]}

    corpus_tok = sum(freq.values())
    miss = sorted(((w, full[w], exact[w], new[full[w]], freq[w]) for w in with_k
                   if new[full[w]] != exact[w]), key=lambda x: -x[-1])

    rep = {
        "cli": cli,
        "a_full_fold": agree([(w, full[w]) for w in with_k]),
        "a_partial_fold": agree([(w, part[w]) for w in with_k if part[w] != w]),
        "a_all_tokens_full_fold": agree([(w, full[w]) for w in proper]),
        "b_natural_k_free": regress(no_k),
        "b_proper_with_k": regress(with_k),
        "b_russian_probe_changed": {w: (exact[w], new[w]) for w in RUSSIAN_PROBE if new[w] != exact[w]},
        "c_retrieval_proxy": {
            "proper_query_exact": retrieval(queries, docs, stop, exact),
            "proper_query_restore": retrieval(queries, docs, stop, new),
            "folded_query_exact": retrieval(qfold, docs, stop, exact),
            "folded_query_restore": retrieval(qfold, docs, stop, new),
            "folded_docs_proper_query_exact": retrieval(queries, docs_folded, stop, exact),
            "folded_docs_proper_query_restore": retrieval(queries, docs_folded, stop, new),
        },
        "d_idempotence_violations": idem_viol[:30],
        "d_idempotence_violation_count": len(idem_viol),
        "d_exact_idempotence_violation_count": len(exact_idem_viol),
        "e_cost": {
            "max_extra_sc_calls": max(st.cost[w] for w in inputs),
            "max_extra_examples": sorted(((st.cost[w], w) for w in inputs), reverse=True)[:5],
            "mean_extra_sc_calls_proper_corpus_token": round(sum(st.cost[w] * freq[w] for w in proper) / corpus_tok, 3),
            "mean_extra_sc_calls_folded_corpus_token": round(sum(st.cost[full[w]] * freq[w] for w in proper) / corpus_tok, 3),
            "mean_extra_sc_calls_partial_corpus_token": round(sum(st.cost[part[w]] * freq[w] for w in proper) / corpus_tok, 3),
        },
        "a_miss_examples": miss[:60],
        "a_miss_classes_tokens": miss_classes(miss, lex, exact),
        "probes": {w: (exact[w], new[w]) for w in PROBES},
        "folded_gold_written": str(gold_folded.relative_to(repo)),
    }
    if args.baseline_cli:
        rep["f_exact_byte_identity_vs_baseline"] = exact_byte_identity(
            args.baseline_cli, cli, lexp, repo / "core/tests/bench_tokens.txt")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    for key in ("a_full_fold", "a_partial_fold", "a_all_tokens_full_fold"):
        print(key, rep[key])
    for key in ("b_natural_k_free", "b_proper_with_k"):
        print(key, {k: v for k, v in rep[key].items() if k != "examples"})
        print("   top:", rep[key]["examples"][:12])
    print("b russian probe changed", rep["b_russian_probe_changed"])
    for k, v in rep["c_retrieval_proxy"].items():
        print("c", k, v)
    print("d idempotence violations (restore)", len(idem_viol), idem_viol[:5])
    print("d idempotence violations (exact)", len(exact_idem_viol))
    print("e", rep["e_cost"])
    print("probes", rep["probes"])
    print("misses", rep["a_miss_classes_tokens"])
    if "f_exact_byte_identity_vs_baseline" in rep:
        print("f exact byte identity", rep["f_exact_byte_identity_vs_baseline"])
    print("report:", out_path)


if __name__ == "__main__":
    main()
