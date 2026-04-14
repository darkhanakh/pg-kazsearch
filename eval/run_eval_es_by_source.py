"""Quick per-source breakdown of ES eval metrics."""
from __future__ import annotations
import json, math, time, urllib.request, sys
from pathlib import Path
from collections import defaultdict

ES_URL = "http://localhost:9200"
INDEX = "articles"
BATCH = 50
KS = [10]

def es_msearch(queries, k, fields):
    lines = []
    for qid, qt in queries:
        lines.append(json.dumps({"index": INDEX}))
        lines.append(json.dumps({"size": k, "query": {"multi_match": {"query": qt, "fields": fields, "type": "best_fields"}}, "_source": False}))
    data = ("\n".join(lines) + "\n").encode("utf-8")
    req = urllib.request.Request(f"{ES_URL}/_msearch", data=data, method="POST")
    req.add_header("Content-Type", "application/x-ndjson")
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    out = {}
    for i, (qid, _) in enumerate(queries):
        out[qid] = [int(h["_id"]) for h in result["responses"][i].get("hits", {}).get("hits", [])]
    return out

def recall_at_k(retrieved, relevant, k):
    if not relevant: return 0.0
    return sum(1 for x in retrieved[:k] if x in relevant) / len(relevant)

def mrr(retrieved, relevant):
    for i, d in enumerate(retrieved):
        if d in relevant: return 1.0 / (i + 1)
    return 0.0

all_queries = []
for path in ["eval/auto_queries.jsonl", "eval/gold_queries.jsonl"]:
    for line in open(path):
        all_queries.append(json.loads(line))

indexed = []
for i, q in enumerate(all_queries):
    qt, rel, src = q.get("query",""), set(q.get("relevant_ids",[])), q.get("source","unknown")
    if qt and rel:
        indexed.append((i, qt, rel, src))

methods = {"kazsearch_stem": ["title^2","body"], "standard": ["title.standard^2","body.standard"]}
k = KS[0]

for label, fields in methods.items():
    print(f"\n=== {label} ===")
    all_results = {}
    for bs in range(0, len(indexed), BATCH):
        batch = [(idx, qt) for idx, qt, _, _ in indexed[bs:bs+BATCH]]
        all_results.update(es_msearch(batch, k, fields))

    by_source = defaultdict(lambda: {"recall": [], "mrr": []})
    for idx, qt, rel, src in indexed:
        res = all_results.get(idx, [])
        by_source[src]["recall"].append(recall_at_k(res, rel, k))
        by_source[src]["mrr"].append(mrr(res[:k], rel))

    print(f"{'source':20} {'count':>6} {'R@10':>8} {'MRR@10':>8}")
    print("-" * 46)
    for src in ["title_keywords", "body_sentence", "morpho_variant", "gold"]:
        if src not in by_source: continue
        m = by_source[src]
        n = len(m["recall"])
        r = sum(m["recall"])/n
        mrr_val = sum(m["mrr"])/n
        print(f"{src:20} {n:>6} {r:>8.4f} {mrr_val:>8.4f}")
