#!/usr/bin/env python3
"""Build the snowball-data sample vocabulary (voc.txt / output.txt).

Takes a JSONL file with a "text" field per line (Kazakh Wikipedia passages,
CC BY-SA), keeps the Cyrillic words seen at least --min-freq times, writes
them sorted to voc.txt and their stems to output.txt using the compiled
stemmer from eval_snowball.build().

    python3 snowball/make_voc.py /tmp/kazrag/data/corpus/corpus.jsonl --min-freq 3
"""

import argparse
import json
import os
import re
from collections import Counter

import eval_snowball

HERE = os.path.dirname(os.path.abspath(__file__))
WORD = re.compile(r"[а-яёәғқңөұүһі]+")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus", help="JSONL with a text field per line")
    ap.add_argument("--min-freq", type=int, default=3)
    ap.add_argument("--sbl", default=os.path.join(HERE, "kazakh.sbl"))
    ap.add_argument("--out", default=HERE, help="directory for voc.txt and output.txt")
    args = ap.parse_args()

    counts = Counter()
    for line in open(args.corpus, encoding="utf-8"):
        counts.update(WORD.findall(json.loads(line)["text"].lower()))
    words = sorted(w for w, n in counts.items() if n >= args.min_freq)
    stems = eval_snowball.snowball_map(eval_snowball.build(args.sbl), words)
    with open(os.path.join(args.out, "voc.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(words) + "\n")
    with open(os.path.join(args.out, "output.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(stems[w] for w in words) + "\n")
    changed = sum(stems[w] != w for w in words)
    print(f"{len(words)} words (freq >= {args.min_freq}), {changed} changed by the stemmer, "
          f"{len(set(stems.values()))} distinct stems")


if __name__ == "__main__":
    main()
