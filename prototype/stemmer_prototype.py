from __future__ import annotations

import logging
import sys
import unicodedata

# =======================
# Debug configuration
# =======================
DEBUG = True  # set False to quiet logs
LOG_CODEPOINTS = False  # True -> print hex codepoints of words

# Early-return policy when a word is in LEMMAS:
# - "always": return immediately (original behavior).
# - "if_looks_uninflected": return only if no plausible suffix is detected.
# - "never": never early-return; always try to stem and fall back on failure.
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
try:
    CLEANED_LEMMAS
except NameError:
    CLEANED_LEMMAS = set()

# Your line (kept)
CLEANED_LEMMAS.add("мектеп")

# For demo/tests; remove if your environment supplies these already
CLEANED_LEMMAS.update({"ауыз", "орын"})

LEMMAS = CLEANED_LEMMAS

# Exceptions: words that should not be stemmed.
EXCEPTIONS = {"абай", "алматы", "туралы", "және"}

# Suffix groups
PLURAL_SUFFIXES = ["лар", "лер", "дар", "дер", "тар", "тер"]

POSSESSIVE_SUFFIXES = [
    "ымыз",
    "іміз",
    "ыңыз",
    "іңіз",
    "лары",
    "лері",
    "дары",
    "дері",
    "тары",
    "тері",  # 3rd person plural possessive
    "сы",
    "сі",
    "ым",
    "ім",
    "ың",
    "ің",
    "м",
    "ң",
    "ы",
    "і",
]

# NOTE: bare "н" removed
CASE_SUFFIXES = [
    "дағы",
    "дегі",
    "тағы",
    "тегі",
    "дан",
    "ден",
    "тан",
    "тен",
    "нан",
    "нен",
    "ның",
    "нің",
    "дың",
    "дің",
    "тың",
    "тің",
    "нда",  # Locative after possessive
    "нде",
    "мен",
    "бен",
    "пен",
    "ға",
    "ге",
    "қа",
    "ке",
    "на",
    "не",
    "да",
    "де",
    "та",
    "те",
    "ны",  # guarded by constraints
    "ні",  # guarded by constraints
    "ды",
    "ді",
    "ты",
    "ті",
    "а",  # Dative after possessive (guarded)
    "е",  # Dative after possessive (guarded)
]

PREDICATE_SUFFIXES = [
    "сыңдар",
    "сіңдер",
    "сыздар",
    "сіздер",
    "мын",
    "мін",
    "пын",
    "пін",
    "сың",
    "сің",
    "сыз",
    "сіз",
    "мыз",
    "міз",
    "пыз",
    "піз",
]

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
    if len(stem) < 2:
        return None

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
        ok = _is_vowel(word[-len(suffix) - 1])
        if not ok:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (preceding "
                f"'{word[-len(suffix) - 1]}' not a vowel)"
            )
        return ok

    if suffix in {"а", "е"}:
        base = word[: -len(suffix)]
        ok = base.endswith(("ы", "і", "сы", "сі"))
        if not ok:
            logger.debug(
                f"  [BLOCK] '{suffix}' on '{word}' (no possessive tail)"
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
    word: str, lemmas: set[str], depth: int, seen: set[str]
) -> str | None:
    logger.debug(f"[DEPTH {depth}] Enter: '{word}'")
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

        found = _search(base, lemmas, depth - 1, seen)
        if found:
            logger.debug(
                f"[DEPTH {depth}] Backtrack success via '{sfx}': '{found}'"
            )
            return found

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

    found = _search(w, lemmas, depth=4, seen=set())
    if found:
        logger.debug(f"RESULT: '{orig}' -> '{found}'")
        return found

    logger.debug(f"RESULT: '{orig}' unchanged (no lemma found)")
    return w


# =======================
# Test / sanity
# =======================
if __name__ == "__main__":
    # Your quick membership probe
    for probe in ["мектепке", "аузы", "орны"]:
        print(
            f"Membership in CLEANED_LEMMAS: {probe!r} -> "
            f"{probe in CLEANED_LEMMAS}"
        )

    print("--- Refined Stemming Results ---")
    words_to_test = [
        "мектептің",  # -> 'мектеп'
        "аузы",  # -> 'ауыз'
        "орны",  # -> 'орын'
        "мектепке",  # -> 'мектеп'
    ]
    for w in words_to_test:
        stemmed = stem_kazakh_word(w, LEMMAS, EXCEPTIONS)
        print(f"'{w}' -> '{stemmed}'")