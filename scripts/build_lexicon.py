#!/usr/bin/env python3
"""
Build kaz_stems.dict from Apertium-kaz POS-tagged lemmas.

Only extracts entries with known continuation classes (N1, V-TV, A1, NP-*, etc.)
to guarantee a clean dictionary of root/citation forms with no inflected words.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from urllib.request import urlopen

DEFAULT_APERTIUM_URL = "https://raw.githubusercontent.com/apertium/apertium-kaz/master/apertium-kaz.kaz.lexc"
DEFAULT_LEXC_CACHE = Path("data/raw/apertium-kaz.kaz.lexc")
DEFAULT_OUTPUT_PATH = Path("data/tsearch_data/kaz_stems.dict")

POS_PATTERN = re.compile(
    r"(N[0-9]|N-COMPOUND|N-INFL"
    r"|V-TV|V-IV|V-DER"
    r"|A[12]"
    r"|ADV|ADV-LANG|ADV-WITH-KI"
    r"|NUM|POSTADV"
    r"|NP-TOP|NP-ORG"
    r"|COP|PRON)"
)

ENTRY_RE = re.compile(
    r"^\s*([^\s!:;%][^\s:;%]*?)"
    r"(?:\s*:\s*[^\s;]+)?"
    r"\s+(" + POS_PATTERN.pattern + r"[A-Za-z0-9\-_]*)"
    r"\s*;",
    re.MULTILINE,
)

INFLECTED_SUFFIXES = [
    "ылған", "ілген", "ланған", "ленген",
    "ылды", "ілді", "ланды", "ленді",
]


def normalize_word(word: str) -> str:
    return unicodedata.normalize("NFC", word.strip()).lower()


def is_clean_lemma(word: str) -> bool:
    if not word or len(word) < 2:
        return False
    if word[0] in "%<+":
        return False
    if not all(ch.isalpha() or ch in "-''ʼ" for ch in word):
        return False
    if all(ch.isascii() for ch in word):
        return False
    if any(ch.isascii() and ch.isalpha() for ch in word):
        return False
    return True


def load_apertium_pos_lemmas(source: str) -> set[str]:
    if source.startswith("http"):
        with urlopen(source) as resp:  # nosec B310
            content = resp.read().decode("utf-8", errors="ignore")
    else:
        with open(source, encoding="utf-8", errors="ignore") as f:
            content = f.read()

    words: set[str] = set()
    for m in ENTRY_RE.finditer(content):
        lemma = normalize_word(m.group(1))
        if is_clean_lemma(lemma):
            words.add(lemma)
    return words


def validate_lexicon(words: set[str]) -> tuple[set[str], int]:
    clean: set[str] = set()
    rejected = 0
    for w in words:
        if any(w.endswith(sfx) and len(w) > len(sfx) + 3 for sfx in INFLECTED_SUFFIXES):
            rejected += 1
            continue
        clean.add(w)
    return clean, rejected


def write_dict(words: set[str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for w in sorted(words):
            f.write(w)
            f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build kaz_stems.dict from Apertium POS-tagged lemmas."
    )
    parser.add_argument(
        "--apertium-url",
        default=DEFAULT_APERTIUM_URL,
        help="Apertium lexc raw URL (used if --lexc-cache missing)",
    )
    parser.add_argument(
        "--lexc-cache",
        type=Path,
        default=DEFAULT_LEXC_CACHE,
        help="Local cached copy of apertium-kaz.kaz.lexc",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output dictionary file path",
    )
    args = parser.parse_args()

    if args.lexc_cache.is_file():
        source = str(args.lexc_cache)
        print(f"source:          {args.lexc_cache} (cached)")
    else:
        source = args.apertium_url
        print(f"source:          {args.apertium_url} (remote)")

    raw_lemmas = load_apertium_pos_lemmas(source)
    print(f"POS-tagged lemmas: {len(raw_lemmas)}")

    clean, rejected = validate_lexicon(raw_lemmas)
    if rejected:
        print(f"rejected inflected: {rejected}")

    write_dict(clean, args.output)
    print(f"final lemmas:    {len(clean)}")
    print(f"wrote:           {args.output}")


if __name__ == "__main__":
    main()
