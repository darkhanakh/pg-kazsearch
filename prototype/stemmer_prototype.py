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

# =======================z
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

# 4. Assign suffix groups from the loaded data, pre-sorted once by length (desc)
def _sort_suffixes_desc(seq: list[str]) -> tuple[str, ...]:
    return tuple(sorted(seq, key=len, reverse=True))

PLURAL_SUFFIXES = _sort_suffixes_desc(all_suffixes.get("PLURAL", []))
POSSESSIVE_SUFFIXES = _sort_suffixes_desc(all_suffixes.get("POSSESSIVE", []))
_case_base = list(all_suffixes.get("CASE", []))
# Add common manner/equative endings
_case_base += [
    "дай", "дей",
]
CASE_SUFFIXES = _sort_suffixes_desc(_case_base)

# Augment predicate-like derivational endings that are missing in data
_pred_base = list(all_suffixes.get("PREDICATE", []))
_pred_base += [
    "сыз", "сіз",
    "мын", "мін", "бын", "бін", "пын", "пін",
    "мыз", "міз", "быз", "біз", "пыз", "піз",
    "сың", "сің",
    "сыңдар", "сіңдер",
    "сыздар", "сіздер",
]
# Remove single-letter 'қ' which causes heavy overstemming (e.g., 'қасық' -> 'қас')
_pred_base = [s for s in _pred_base if s != "қ"]
PREDICATE_SUFFIXES = _sort_suffixes_desc(_pred_base)

_verb_base = all_suffixes.get(
    "VERB",
    [
        # Common verb endings / markers
        "йды", "йді", "ады", "еді",
        "ды", "ді", "ты", "ті",
        "саң", "сең", "сақ", "сек", "са", "се",
        "майды", "мейді", "байды", "бейді", "пайды", "пейді",
        "май", "мей",
        "ма", "ме", "ба", "бе", "па", "пе",
        "ған", "ген", "қан", "кен",
        "мақ", "мек", "бақ", "бек", "пақ", "пек",
        # participle/infinitive/conditional/future markers
        "атын", "етін", "йтын", "йтін",
        "тын", "тін",
        "у", "а", "е", "й",
    ],
)
# Add common causative, passive, derivational verb-related and evidential clusters
_verb_base += [
    # evidential past after converb -п
    "пты", "пті",
    # causatives
    "қыз", "ғыз", "кіз", "гіз",
    # passive/causative light suffixes
    "ыл", "іл",
    # adjectival/participle
    "ғы", "гі",
    # nominalizers frequently attached to participles
    "дық", "дік", "тық", "тік", "лық", "лік",
]
VERB_SUFFIXES = _sort_suffixes_desc(_verb_base)

# Predicate endings that often clash with possessives; try them before others when present
PRED_PRIORITY_SUFFIXES: tuple[str, ...] = _sort_suffixes_desc([
    "сыңдар", "сіңдер", "сыздар", "сіздер",
    "сыз", "сіз", "сың", "сің",
    "мын", "мін", "мыз", "міз",
])


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
    # Prefer reverse-mutation restoration over accepting the raw base
    if stem and stem[-1] in REVERSE_MUTATION:
        mutated = stem[:-1] + REVERSE_MUTATION[stem[-1]]
        if mutated in lemmas:
            logger.debug(f"  [CHECK] '{stem}' -> '{mutated}' via mutation")
            return mutated, "mutated"

    if stem in lemmas:
        logger.debug(f"  [CHECK] '{stem}' is a direct lemma")
        return stem, "direct"

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
        # If both the full word and the base are lemmas, prefer the longer lemma
        # to avoid overstemming lexicalized forms like 'қарын'/'ерін'.
        if word in LEMMAS and base in LEMMAS:
            logger.debug(
                f"  [SAFE] Skip accusative '{suffix}' on lemma '{word}': base '{base}' is also lemma"
            )
            return False
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
        # If both the full word and the base are lemmas, prefer the longer lemma
        # to avoid overstemming lexicalized forms like 'қарын'/'ерін'.
        if word in LEMMAS and base in LEMMAS:
            logger.debug(
                f"  [SAFE] Skip accusative '{suffix}' on lemma '{word}': base '{base}' is also lemma"
            )
            return False
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

    # Stricter handling for accusative -ды/-ді/-ты/-ті
    if suffix in {"ды", "ді", "ты", "ті"}:
        if len(word) < len(suffix) + 1:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (too short for check)"
            )
            return False
        base = word[: -len(suffix)]
        # Preceding character must be a consonant (true accusative context)
        pre_char = word[-len(suffix) - 1]
        if _is_vowel(pre_char):
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (preceding '{pre_char}' is a vowel)"
            )
            return False
        # Avoid splitting evidential past '-пты/-пті' as CASE 'ты/ті'
        if base.endswith("п"):
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (base ends with 'п' -> likely evidential past)"
            )
            return False
        # Avoid treating possessive + 'і' as case 'ті' (e.g., 'жігіті')
        if base.endswith((
            "ымыз", "іміз", "ыңыз", "іңіз", "мыз", "міз", "ңыз", "ңіз",
            "ым", "ім", "ың", "ің", "сы", "сі", "ы", "і", "м", "ң"
        )):
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (base has possessive tail)"
            )
            return False
        return True

    if suffix in {"а", "е"}:
        base = word[: -len(suffix)]
        # Consolidate most possessive tails into one tuple for a single endswith check,
        # but keep guard rails for single-letter 'м'/'ң' which require a preceding vowel.
        valid_possessive_tails = (
            "ымыз", "іміз", "ыңыз", "іңіз", "мыз", "міз", "ңыз", "ңіз",
            "ым", "ім", "ың", "ің", "сы", "сі", "ы", "і"
        )
        ok = (
            base.endswith(valid_possessive_tails)
            or (base.endswith("м") and len(base) >= 2 and _is_vowel(base[-2]))
            or (base.endswith("ң") and len(base) >= 2 and _is_vowel(base[-2]))
        )
        if not ok:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (no possessive tail)"
            )
        return ok

    # Enclitic accusative -н generally after 3sg possessive -ы/-і or -сы/-сі
    if suffix == "н":
        base = word[: -1]
        # If the full word is a lemma, avoid stripping a bare -н to
        # preserve lexicalized forms like 'қарын', 'ерін'.
        if word in LEMMAS:
            logger.debug(
                f"  [SAFE] Skip enclitic 'н' on lemma '{word}'"
            )
            return False
        ok = base.endswith(("ы", "і", "сы", "сі"))
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
        # Peel inflectional layers first, then derivational/verb-like
        ("CASE", CASE_SUFFIXES),
        ("POSS", POSSESSIVE_SUFFIXES),
        ("PLUR", PLURAL_SUFFIXES),
        ("VERB", VERB_SUFFIXES),
        ("PRED", PREDICATE_SUFFIXES),
    ]
    # Prioritize predicate personal endings to avoid mis-parsing as possessives
    for sfx in PRED_PRIORITY_SUFFIXES:
        if word.endswith(sfx):
            if probe:
                logger.debug(
                    f"  [LOOKS-INFLECTED] PRED (priority) suffix '{sfx}' matches '{word}'"
                )
            else:
                logger.debug(f"  [MATCH] PRED (priority) suffix '{sfx}' matches '{word}'")
            yield "PRED", sfx

    for tag, group in groups:
        for sfx in group:
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

            # Ambiguity safeguard: If the whole word and the base are both lemmas,
            # avoid stripping for non-derivational layers (CASE/POSS/PLUR).
            # Allow stripping for VERB/PRED (derivational/copular) so forms like
            # 'бару' -> 'бар' and 'сөзсіз' -> 'сөз' still work.
            base = word[: -len(sfx)]
            if word in LEMMAS and base in LEMMAS and tag in {"CASE", "POSS", "PLUR"}:
                logger.debug(
                    f"  [SAFE] Skip {tag} '{sfx}' on lemma '{word}': base '{base}' is also lemma"
                )
                continue

            # Additional guards for VERB layer to avoid over-stripping
            if tag == "VERB":
                short_vowels = {"а", "е"}
                # Only treat single-letter markers as ambiguous; allow stripping negation -ма/-ме
                ambiguous_verb_markers = {"а", "е", "й"}
                # Negation markers frequently coincide with noun endings (e.g., 'алма').
                # If both the word and the base are lemmas and the base is very short,
                # prefer keeping the noun intact to avoid overstemming.
                negation_markers = {"ма", "ме", "ба", "бе", "па", "пе"}
                if sfx in negation_markers and word in LEMMAS and base in LEMMAS and len(base) <= 2:
                    logger.debug(
                        f"  [SAFE] Skip VERB '{sfx}' on lemma '{word}': base '{base}' too short"
                    )
                    continue
                # Only allow single vowel verb markers if the base is a known lemma
                if sfx in short_vowels and base not in LEMMAS:
                    logger.debug(
                        f"  [SAFE] Skip VERB '{sfx}' on '{word}': base '{base}' not a lemma"
                    )
                    continue
                # If both word and base are lemmas and suffix is ambiguous, keep the lemma intact
                if word in LEMMAS and base in LEMMAS and sfx in ambiguous_verb_markers:
                    logger.debug(
                        f"  [SAFE] Skip VERB '{sfx}' on lemma '{word}': base '{base}' is also lemma"
                    )
                    continue

            # Guard comparative adjective stripping on very short bases to avoid e.g. 'жапырақ' -> 'жап'
            if tag == "PRED":
                comparative_set = {"ырақ", "ірек", "рақ", "рек"}
                if sfx in comparative_set:
                    # Avoid stripping if the base is too short or not a known lemma
                    if len(base) < 4 or base not in LEMMAS:
                        logger.debug(
                            f"  [SAFE] Skip PRED comparative '{sfx}' on '{word}': base '{base}' not reliable"
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
            # If the form still looks inflected, keep stripping; otherwise accept the hit
            if not _looks_inflected(word):
                logger.debug(f"[DEPTH {depth}] HIT '{hit}' ({reason})")
                return hit
            else:
                logger.debug(
                    f"[DEPTH {depth}] Bypass direct hit for '{word}': looks inflected, continue"
                )

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

        # Immediately and fully check the base for lemma match, including mutation/elision
        hit, reason = _check_stem(base, lemmas)
        if hit:
            logger.debug(
                f"[DEPTH {depth}] HIT after strip '{sfx}': "
                f"'{hit}' ({reason})"
            )
            return hit

        # If not a direct or repaired lemma, continue recursion from the base
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

    found = _search(w, lemmas, depth=8, seen=set(), prefer_strip_first=prefer_strip_first)
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