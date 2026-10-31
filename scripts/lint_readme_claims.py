#!/usr/bin/env python3
"""List every README line that compares two systems, for review.

A comparative or causal claim in the README must point at a committed paired
bootstrap interval that excludes zero, or report the measured values with no
verdict. This script does not judge. It lists every line outside a code fence
that carries a comparative term, a ratio or percent after a number, a signed
delta, or a bold table cell, so a reviewer can check each one against the
rule. A line is tagged `cited` when it carries a 95% interval, and `review`
otherwise.

Usage: python3 scripts/lint_readme_claims.py [README.md] [--review-only]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORDS = [
    r"rais(?:e|es|ed|ing)",
    r"add(?:s|ed|ing)?",
    r"above",
    r"below",
    r"ahead",
    r"behind",
    r"beat(?:s|en)?",
    r"outperform(?:s|ed|ing)?",
    r"improv(?:e|es|ed|ing|ement|ements)",
    r"wors(?:e|en|ens|ened)",
    r"better",
    r"cost(?:s)?",
    r"halv(?:e|es|ed|ing)",
    r"doubl(?:e|es|ed|ing)",
    r"best",
    r"winner(?:s)?",
    r"win(?:s)?",
    r"los(?:e|es|t)",
    r"level with",
    r"tie(?:s|d)?",
    r"same",
    r"match(?:es|ed|ing)?",
    r"equal(?:s|ly)?",
    r"equivalen(?:t|ce)",
    r"more than",
    r"less than",
    r"higher",
    r"lower",
    r"gain(?:s)?",
    r"advantage",
    r"faster",
    r"slower",
]

PATTERNS = [
    ("term", re.compile(r"\b(?:" + "|".join(WORDS) + r")\b", re.IGNORECASE)),
    ("ratio", re.compile(r"\b\d+(?:\.\d+)?x\b")),
    ("percent", re.compile(r"\d+(?:\.\d+)?%(?! (?:CI|paired|intervals?)\b)")),
    ("delta", re.compile(r"(?<![\w.\[])[+\u2212]\d+(?:\.\d+)?")),
]
BOLD_CELL = re.compile(r"\*\*[^*]+\*\*")
INTERVAL = re.compile(r"95% CI|\[[+\u2212-]?\d[^\]]*,[^\]]*\]")
FENCE = re.compile(r"^\s*```")


def scan(lines: list[str]) -> list[tuple[int, bool, dict[str, list[str]], str]]:
    """Return (line number, cited, {kind: matches}, line) for each flagged line."""
    flagged = []
    in_fence = False
    for i, raw in enumerate(lines, start=1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = raw.rstrip("\n")
        hits: dict[str, list[str]] = {}
        if line.lstrip().startswith("|"):
            cells = [m.group(0) for m in BOLD_CELL.finditer(line)]
            if cells:
                hits["bold"] = cells
        for kind, pattern in PATTERNS:
            found = [m.group(0) for m in pattern.finditer(line)]
            if found:
                hits[kind] = found
        if hits:
            flagged.append((i, bool(INTERVAL.search(line)), hits, line))
    return flagged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("readme", nargs="?", default="README.md")
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="print only the lines that carry no confidence interval",
    )
    args = parser.parse_args()
    lines = Path(args.readme).read_text(encoding="utf-8").splitlines(keepends=True)
    flagged = scan(lines)

    for line_no, cited, hits, line in flagged:
        if args.review_only and cited:
            continue
        tag = "cited " if cited else "review"
        what = "; ".join(f"{kind}: {', '.join(found)}" for kind, found in hits.items())
        excerpt = line.strip()
        if len(excerpt) > 100:
            excerpt = excerpt[:97] + "..."
        print(f"L{line_no:<4} {tag} {what}")
        print(f"      {excerpt}")

    total_hits = sum(len(found) for _, _, hits, _ in flagged for found in hits.values())
    by_kind: dict[str, int] = {}
    for _, _, hits, _ in flagged:
        for kind, found in hits.items():
            by_kind[kind] = by_kind.get(kind, 0) + len(found)
    review = [f for f in flagged if not f[1]]
    kinds = ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items()))
    print(
        f"\n{len(flagged)} flagged lines, {total_hits} hits ({kinds}); "
        f"{len(flagged) - len(review)} lines cited, {len(review)} lines for review",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
