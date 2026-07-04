#!/usr/bin/env python3
"""
Build kaz_stems.dict from Apertium-kaz POS-tagged lemmas.

Only extracts entries with known continuation classes (N1, V-TV, A1..A6,
NP-*, etc.) to guarantee a clean dictionary of root/citation forms with no
inflected words.

The Apertium source is pinned to a commit SHA for reproducible builds, and a
kaz_stems.dict.meta.json sidecar records the source and per-POS lemma counts.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

# Pinned commit of apertium/apertium-kaz (last change to the .lexc file).
APERTIUM_LEXC_SHA = "0d82c015ddee75a743e4184b8c7ce9c388576b13"
DEFAULT_APERTIUM_URL = (
    "https://raw.githubusercontent.com/apertium/apertium-kaz/"
    f"{APERTIUM_LEXC_SHA}/apertium-kaz.kaz.lexc"
)
DEFAULT_LEXC_CACHE = Path("data/raw/apertium-kaz.kaz.lexc")
DEFAULT_OUTPUT_PATH = Path("data/tsearch_data/kaz_stems.dict")

# A3/A4 are deliberately excluded: in apertium-kaz they hold *derived*
# adjectives (авиациялық, автокөлікті, айналы) whose presence in the lemma
# dictionary triggers the overstemming safety valve and blocks the stemmer
# from conflating them with their bases — measured as a net loss on search
# recall. A6 is a small closed class of genuine adjectives and stays.
POS_PATTERN = re.compile(
    r"(N[0-9]|N-COMPOUND|N-INFL"
    r"|V-TV|V-IV|V-TD|V-DER"
    r"|A[126]"
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

# All V-TD (transitive denominal verb) entries are commented out in the
# Apertium lexc — the paradigm is unfinished in their transducer — but the
# lemmas themselves are valid citation forms, which is all the stemmer's
# lexicon needs.
COMMENTED_VTD_RE = re.compile(
    r"^\s*!\s*([^\s!:;%][^\s:;%]*?)"
    r"(?:\s*:\s*[^\s;]+)?"
    r"\s+V-TD\s*;",
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


def load_apertium_pos_lemmas(source: str) -> dict[str, set[str]]:
    """Return lemma -> set of coarse POS classes."""
    if source.startswith("http"):
        with urlopen(source) as resp:  # nosec B310
            content = resp.read().decode("utf-8", errors="ignore")
    else:
        with open(source, encoding="utf-8", errors="ignore") as f:
            content = f.read()

    lemmas: dict[str, set[str]] = {}
    for m in ENTRY_RE.finditer(content):
        lemma = normalize_word(m.group(1))
        if not is_clean_lemma(lemma):
            continue
        coarse = POS_PATTERN.match(m.group(2)).group(1)
        lemmas.setdefault(lemma, set()).add(coarse)

    for m in COMMENTED_VTD_RE.finditer(content):
        lemma = normalize_word(m.group(1))
        if is_clean_lemma(lemma):
            lemmas.setdefault(lemma, set()).add("V-TD")

    return lemmas


def validate_lexicon(lemmas: dict[str, set[str]]) -> tuple[dict[str, set[str]], int]:
    clean: dict[str, set[str]] = {}
    rejected = 0
    for w, pos in lemmas.items():
        if any(w.endswith(sfx) and len(w) > len(sfx) + 3 for sfx in INFLECTED_SUFFIXES):
            rejected += 1
            continue
        clean[w] = pos
    return clean, rejected


def pos_counts(lemmas: dict[str, set[str]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for pos in lemmas.values():
        counter.update(pos)
    return dict(sorted(counter.items(), key=lambda kv: -kv[1]))


# Coarse verb classes. Used to emit the .verbs sibling file: the stemmer's
# verb-root reductions (-у/-ю verbal nouns, -ған participles, -п converbs)
# must only land on verb roots, so noun homographs don't get swallowed.
VERB_CLASSES = {"V-TV", "V-IV", "V-TD", "V-DER"}


def write_dict(lemmas: dict[str, set[str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for w in sorted(lemmas):
            f.write(w)
            f.write("\n")


def write_verbs(lemmas: dict[str, set[str]], output: Path) -> tuple[Path, int]:
    """Sibling file `<dict>.verbs` with verb lemmas only.

    kazsearch-core auto-loads it next to the main dict (no config changes in
    pg_ext / ES / CLI) and uses it to gate verb-root reductions.
    """
    verbs_path = output.with_name(output.name + ".verbs")
    verbs = sorted(w for w, pos in lemmas.items() if pos & VERB_CLASSES)
    with verbs_path.open("w", encoding="utf-8") as f:
        for w in verbs:
            f.write(w)
            f.write("\n")
    return verbs_path, len(verbs)


def write_meta(
    lemmas: dict[str, set[str]], rejected: int, source: str, output: Path, verb_count: int
) -> Path:
    meta_path = output.with_name(output.name + ".meta.json")
    meta = {
        "generated": _dt.date.today().isoformat(),
        "source": source,
        "apertium_lexc_sha": APERTIUM_LEXC_SHA,
        "total_lemmas": len(lemmas),
        "verb_lemmas": verb_count,
        "rejected_inflected": rejected,
        "pos_counts": pos_counts(lemmas),
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return meta_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build kaz_stems.dict from Apertium POS-tagged lemmas."
    )
    parser.add_argument(
        "--apertium-url",
        default=DEFAULT_APERTIUM_URL,
        help="Apertium lexc raw URL, pinned to a commit SHA (used if --lexc-cache missing)",
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
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print per-POS lemma counts",
    )
    args = parser.parse_args()

    if args.lexc_cache.is_file():
        source = str(args.lexc_cache)
        print(f"source:          {args.lexc_cache} (cached, pinned SHA {APERTIUM_LEXC_SHA[:12]})")
    else:
        source = args.apertium_url
        print(f"source:          {args.apertium_url} (remote)")

    raw_lemmas = load_apertium_pos_lemmas(source)
    print(f"POS-tagged lemmas: {len(raw_lemmas)}")

    clean, rejected = validate_lexicon(raw_lemmas)
    if rejected:
        print(f"rejected inflected: {rejected}")

    write_dict(clean, args.output)
    verbs_path, verb_count = write_verbs(clean, args.output)
    meta_path = write_meta(clean, rejected, source, args.output, verb_count)
    print(f"final lemmas:    {len(clean)}")
    print(f"verb lemmas:     {verb_count}")
    print(f"wrote:           {args.output}")
    print(f"verbs:           {verbs_path}")
    print(f"meta:            {meta_path}")

    if args.stats:
        print("\nper-POS lemma counts:")
        for pos, n in pos_counts(clean).items():
            print(f"  {pos:12} {n}")


if __name__ == "__main__":
    main()
