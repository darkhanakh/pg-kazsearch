# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import sys
import unicodedata
import os
from pathlib import Path
import json  # 1. Import the json library

# =======================
# Debug configuration
# =======================
DEBUG = False  # set False to quiet logs
LOG_CODEPOINTS = False  # True -> print hex codepoints of words
EARLY_RETURN_POLICY = "if_looks_uninflected"

logger = logging.getLogger("kaz_stemmer")
handler = logging.StreamHandler(sys.stdout)
fmt = "%(levelname)s %(message)s"
handler.setFormatter(logging.Formatter(fmt))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

# =======================
# Lemmas / data init
# =======================
CLEANED_LEMMAS: set[str] = globals().get("CLEANED_LEMMAS", set())
LEMMAS = CLEANED_LEMMAS
LEMMAS_FILE_ENV = "KAZ_STEMMER_LEMMAS_PATH"
DEFAULT_LEMMAS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "processed" / "lemmas.txt"
)

def _load_lemmas_from_file(path: str | Path) -> set[str]:
    p = Path(path)
    lemmas: set[str] = set()
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                w = unicodedata.normalize("NFC", s).lower()
                lemmas.add(w)
    except FileNotFoundError:
        logger.warning(f"Lemma file not found: '{p}'")
    except Exception as e:
        logger.warning(f"Error reading lemma file '{p}': {e}")
    return lemmas

if not CLEANED_LEMMAS:
    path_str = os.environ.get(LEMMAS_FILE_ENV)
    path = Path(path_str) if path_str else DEFAULT_LEMMAS_PATH
    loaded = _load_lemmas_from_file(path)
    if loaded:
        CLEANED_LEMMAS = loaded
        LEMMAS = CLEANED_LEMMAS
        logger.info(f"Loaded {len(CLEANED_LEMMAS)} lemmas from '{path}'")
    else:
        logger.warning("No lemmas loaded; proceeding with empty lemma set")

EXCEPTIONS = {"абай", "алматы", "туралы", "және"}

# =======================
# Suffixes init
# =======================

# 2. Define a function to load suffixes from the JSON file
def _load_suffixes_from_json(path: str | Path) -> dict[str, list[str]]:
    """Loads suffix groups from a JSON file."""
    p = Path(path)
    suffixes: dict[str, list[str]] = {}
    try:
        with p.open("r", encoding="utf-8") as f:
            suffixes = json.load(f)
            logger.info(f"Loaded {sum(len(v) for v in suffixes.values())} suffixes from '{p}'")
    except FileNotFoundError:
        logger.warning(f"Suffix file not found: '{p}'. Stemming will be impaired.")
    except json.JSONDecodeError:
        logger.warning(f"Error decoding JSON from suffix file: '{p}'")
    except Exception as e:
        logger.warning(f"Error reading suffix file '{p}': {e}")
    return suffixes

# 3. Define the path and load the JSON file
DEFAULT_SUFFIXES_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "processed" / "kazakh_atomic_suffixes.json"
)
all_suffixes = _load_suffixes_from_json(DEFAULT_SUFFIXES_PATH)

# 4. Assign suffix groups from the loaded data, with fallbacks to empty lists
PLURAL_SUFFIXES = all_suffixes.get("PLURAL", [])
POSSESSIVE_SUFFIXES = all_suffixes.get("POSSESSIVE", [])
CASE_SUFFIXES = all_suffixes.get("CASE", [])
PREDICATE_SUFFIXES = all_suffixes.get("PREDICATE", [])


# Better vowel set (Cyrillic)
VOWELS = set("аәеёиіоуыөүұ")

REVERSE_MUTATION = {"б": "п", "г": "к", "ғ": "қ", "д": "т"}


# =======================
# Utilities / normalization
# =======================
def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _is_vowel(ch: str) -> bool:
    return ch in VOWELS


def _log_codepoints(label: str, s: str):
    if not LOG_CODEPOINTS:
        return
    cps = " ".join(hex(ord(c)) for c in s)
    logger.debug(f"{label} codepoints: {cps}")


# =======================
# Elision / mutation checks
# =======================
def _handle_vowel_elision(stem: str, lemmas: set[str]) -> str | None:
    """
    Tries to reverse vowel elision by inserting 'ы' or 'і'.
    Example: 'ауз' -> 'ауыз'
    """
    # ======================================================================
    # OPTIMIZATION: Only run this expensive check on candidates that could
    # plausibly be stems with an elided vowel. These candidates are almost
    # always short and contain exactly one vowel (e.g., 'ауз', 'орн').
    vowel_count = sum(1 for char in stem if _is_vowel(char))
    if vowel_count != 1:
        return None
    # ======================================================================

    if len(stem) < 2:
        return None

    # (The rest of the function is unchanged)
    vowel_back = "аоұы"
    vowel_front = "әеөүі"
    all_vowels = vowel_back + vowel_front

    last_vowel_in_stem = ""
    for char in reversed(stem):
        if char in all_vowels:
            last_vowel_in_stem = char
            break

    vowel_to_insert = ""
    if last_vowel_in_stem in vowel_back:
        vowel_to_insert = "ы"
    elif last_vowel_in_stem in vowel_front:
        vowel_to_insert = "і"
    else:
        return None

    new_stem = stem[:-1] + vowel_to_insert + stem[-1]
    if new_stem in lemmas:
        logger.debug(f"  [ELIDE] '{stem}' -> '{new_stem}' (restored)")
        return new_stem

    logger.debug(
        f"  [ELIDE] '{stem}' -> '{new_stem}', but restored form "
        "not in lemmas"
    )
    return None


def _check_stem(stem: str, lemmas: set[str]) -> tuple[str | None, str]:
    """
    Returns (valid_stem, reason) where reason ∈ {'direct','mutated','elided',''}
    """
    if stem in lemmas:
        logger.debug(f"  [CHECK] '{stem}' is a direct lemma")
        return stem, "direct"

    if stem and stem[-1] in REVERSE_MUTATION:
        mutated = stem[:-1] + REVERSE_MUTATION[stem[-1]]
        if mutated in lemmas:
            logger.debug(f"  [CHECK] '{stem}' -> '{mutated}' via mutation")
            return mutated, "mutated"

    elided = _handle_vowel_elision(stem, lemmas)
    if elided:
        return elided, "elided"

    logger.debug(f"  [CHECK] '{stem}' not a lemma (no mutation/elision)")
    return None, ""


# =======================
# Constraints / suffix iteration
# =======================
def _can_use_case_suffix(word: str, suffix: str) -> bool:
    """
    Avoid incorrect splits:
    - Accusative -ны/-ні only after a vowel-final base.
    - Dative -а/-е only after possessive (heuristic).
    """
    if suffix in {"ны", "ні"}:
        if len(word) < len(suffix) + 1:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (too short for check)"
            )
            return False
        base = word[: -len(suffix)]
        # Block accusative -ны/-ні after 3sg possessive tails
        if base.endswith(("ы", "і", "сы", "сі")):
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (after 3sg possessive; use 'н')"
            )
        ok = _is_vowel(word[-len(suffix) - 1]) and not base.endswith(("ы", "і", "сы", "сі"))
        if not ok:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (preceding "
                f"'{word[-len(suffix) - 1]}' not a vowel)"
            )
        return ok

    # Accusative variants -ын/-ін typically after a consonant-final base
    if suffix in {"ын", "ін"}:
        if len(word) < len(suffix) + 1:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (too short for check)"
            )
            return False
        base = word[: -len(suffix)]
        # Do not allow -ын/-ін right after 3sg possessive stem ending with 'с' (as in '-сы/-сі')
        if base.endswith("с"):
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (base ends with 'с' -> prefer enclitic 'н')"
            )
            return False
        ok = not _is_vowel(word[-len(suffix) - 1])
        if not ok:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (preceding "
                f"'{word[-len(suffix) - 1]}' is a vowel)"
            )
        return ok

    if suffix in {"а", "е"}:
        base = word[: -len(suffix)]
        # Allow dative -а/-е after 1st/2nd/3rd possessives with guard rails
        long_possessive = (
            "ым", "ім", "ың", "ің", "сы", "сі", "ы", "і",
            "ымыз", "іміз", "ыңыз", "іңіз", "мыз", "міз", "ңыз", "ңіз"
        )
        ok = False
        if base.endswith(long_possessive):
            ok = True
        elif base.endswith("м") and len(base) >= 2 and _is_vowel(base[-2]):
            # 1sg possessive -м attaches to vowel-final base: e.g., 'алмам' (алма+м)
            ok = True
        elif base.endswith("ң") and len(base) >= 2 and _is_vowel(base[-2]):
            # 2sg possessive -ң attaches to vowel-final base
            ok = True
        if not ok:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (no possessive tail)"
            )
        return ok

    # Enclitic accusative -н generally after 3sg possessive -ы/-і
    if suffix == "н":
        base = word[: -1]
        ok = base.endswith(("ы", "і"))
        if not ok:
            logger.debug(
                f"  [BLOCK] 'н' on '{word}' (base '{base}' lacks 3sg possessive)"
            )
        return ok

    return True


def _iter_suffixes_with_group(
    word: str,
    apply_single_vowel_safeguard: bool = True,
    probe: bool = False,
):
    """
    Yield matching suffixes grouped by morphological layer.
    - apply_single_vowel_safeguard: skip single vowels if the whole word
      is a lemma AND removing the vowel doesn't lead to a valid lemma.
    - probe: looser logging-only mode for 'looks inflected' checks.
    """
    # Morphological order: Case before Possessive helps nested genitive chains
    # like 'алмасының' (алма+сы+ның) to peel case first.
    groups = [
        ("PRED", PREDICATE_SUFFIXES),
        ("CASE", CASE_SUFFIXES),
        ("POSS", POSSESSIVE_SUFFIXES),
        ("PLUR", PLURAL_SUFFIXES),
    ]
    for tag, group in groups:
        for sfx in sorted(group, key=len, reverse=True):
            if not word.endswith(sfx):
                continue

            if tag == "CASE" and not _can_use_case_suffix(word, sfx):
                # already logged by _can_use_case_suffix
                continue

            if (
                apply_single_vowel_safeguard
                and len(sfx) == 1
                and sfx in VOWELS
                and word in LEMMAS
            ):
                base = word[: -len(sfx)]
                hit, _ = _check_stem(base, LEMMAS)
                if hit is None:
                    logger.debug(
                        f"  [SAFE] Skip single-vowel '{sfx}' on '{word}': "
                        "word is lemma AND stripping would not reach a lemma"
                    )
                    continue  # keep the lemma intact

            # If the whole word and the base are both lemmas, avoid stripping
            # case suffixes to preserve uninflected lemmas like 'қысқа'.
            base = word[: -len(sfx)]
            if tag == "CASE" and word in LEMMAS:
                if base in LEMMAS:
                    logger.debug(
                        f"  [SAFE] Skip CASE '{sfx}' on lemma '{word}': base '{base}' is also lemma"
                    )
                    continue

            if probe:
                logger.debug(
                    f"  [LOOKS-INFLECTED] {tag} suffix '{sfx}' matches '{word}'"
                )
            else:
                logger.debug(f"  [MATCH] {tag} suffix '{sfx}' matches '{word}'")
            yield tag, sfx


def _looks_inflected(word: str) -> bool:
    # Probe without the single-vowel safeguard so we don't miss cases like 'аузы'
    for _ in _iter_suffixes_with_group(
        word, apply_single_vowel_safeguard=False, probe=True
    ):
        return True
    return False


# =======================
# Search / main stemmer
# =======================
def _search(
    word: str, lemmas: set[str], depth: int, seen: set[str], prefer_strip_first: bool = False
) -> str | None:
    logger.debug(f"[DEPTH {depth}] Enter: '{word}'")

    # Optionally try stripping suffixes before accepting the word as a direct lemma.
    if not prefer_strip_first:
        hit, reason = _check_stem(word, lemmas)
        if hit:
            logger.debug(f"[DEPTH {depth}] HIT '{hit}' ({reason})")
            return hit

    if depth == 0 or word in seen:
        logger.debug(f"[DEPTH {depth}] Stop on '{word}' (depth/seen)")
        return None
    seen.add(word)

    for tag, sfx in _iter_suffixes_with_group(word):
        base = word[: -len(sfx)]
        logger.debug(
            f"[DEPTH {depth}] Try {tag} suffix '{sfx}': "
            f"'{word}' -> base '{base}'"
        )

        hit, reason = _check_stem(base, lemmas)
        if hit:
            logger.debug(
                f"[DEPTH {depth}] HIT after strip '{sfx}': "
                f"'{hit}' ({reason})"
            )
            return hit

        found = _search(base, lemmas, depth - 1, seen, prefer_strip_first)
        if found:
            logger.debug(
                f"[DEPTH {depth}] Backtrack success via '{sfx}': '{found}'"
            )
            return found

    # If we preferred stripping first, check the word as-is last.
    if prefer_strip_first:
        hit, reason = _check_stem(word, lemmas)
        if hit:
            logger.debug(f"[DEPTH {depth}] HIT '{hit}' ({reason})")
            return hit

    logger.debug(f"[DEPTH {depth}] No suffix led to lemma for '{word}'")
    return None


def stem_kazakh_word(word: str, lemmas: set[str], exceptions: set[str]) -> str:
    orig = word
    w = nfc(word.lower())
    logger.debug("=" * 60)
    logger.debug(f"WORD '{orig}' -> normalized '{w}'")
    _log_codepoints("word", w)

    if w in exceptions:
        logger.debug(f"Early return: '{w}' is in EXCEPTIONS")
        return w

    if w in lemmas:
        if EARLY_RETURN_POLICY == "always":
            logger.debug("Early return: word is in LEMMAS (policy=always)")
            return w
        elif EARLY_RETURN_POLICY == "if_looks_uninflected":
            if not _looks_inflected(w):
                logger.debug(
                    "Early return: word is in LEMMAS and does not look "
                    "inflected (policy=if_looks_uninflected)"
                )
                return w
            logger.debug(
                "Bypass early return: word is in LEMMAS but looks inflected; "
                "attempting stemming"
            )
        else:
            logger.debug(
                "Bypass early return: policy=never; attempting stemming"
            )

    prefer_strip_first = False
    if w in lemmas and _looks_inflected(w):
        # Looks inflected, but also present as a lemma: prioritize stripping
        prefer_strip_first = True

    found = _search(w, lemmas, depth=7, seen=set(), prefer_strip_first=prefer_strip_first)
    if found:
        logger.debug(f"RESULT: '{orig}' -> '{found}'")
        return found

    logger.debug(f"RESULT: '{orig}' unchanged (no lemma found)")
    return w


# =======================
# Test / sanity
# =======================
if __name__ == "__main__":
    from prototype.test_cases import ALL_CASES
    print("--- Refined Stemming Results ---")

    for word, expected in ALL_CASES:
        result = stem_kazakh_word(word, LEMMAS, EXCEPTIONS)
        print(f"{word:20} -> {result:10} (expected: {expected})")