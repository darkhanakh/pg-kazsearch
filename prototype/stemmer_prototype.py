LEMMAS = {
    "бала", "кітап", "тас", "мектеп", "оқушы", "ұстаз", "қасқыр",
    "толқын", "тау", "дос", "жаз", "кел", "оқы", "керемет", "жақсы"
}

EXCEPTIONS = {"абай", "алматы", "туралы", "және"}

# N4: Personal endings (Жіктік жалғау)
N4_SUFFIXES = ["мын", "мін", "пын", "пін", "сың", "сің", "сыз", "сіз"]

# N3: Case endings (Септік жалғау)
N3_SUFFIXES = [
    "ға", "ге", "қа", "ке", "на", "не", "да", "де", "та", "те",
    "дан", "ден", "тан", "тен", "нан", "нен", "ның", "нің",
    "дың", "дің", "тың", "тің", "мен", "бен", "пен", "ны", "ні",
    "ды", "ді", "ты", "ті"
]

# N2: Possessive endings (Тәуелдік жалғау)
N2_SUFFIXES = [
    "ым", "ім", "ың", "ің", "сы", "сі", "ымыз", "іміз", "іңіз", "іңіз"
]

# N1: Plural endings (Көптік жалғау)
N1_SUFFIXES = ["лар", "лер", "дар", "дер", "тар", "тер"]

# A map to reverse the consonant mutation (e.g., кітабы -> кітап)
REVERSE_MUTATION = {
    'б': 'п',
    'г': 'к',
    'ғ': 'қ',
    'д': 'т'
}

def _strip_suffix(word: str, suffixes: list) -> (str, str or None):
    """
    Helper function to find and strip the longest matching suffix from a list.
    """
    # Sort suffixes by length (longest first) to ensure correct matching
    # e.g., match "ымыз" before "ыз"
    for suffix in sorted(suffixes, key=len, reverse=True):
        if word.endswith(suffix):
            return word[:-len(suffix)], suffix
    return word, None

def stem_kazakh_word(word: str) -> str:
    """
    Stems a Kazakh word based on the paper's flowchart for nouns.

    Args:
        word (str): The Kazakh word to be stemmed.

    Returns:
        str: The stemmed root of the word, or the original word if no stem is found.
    """
    word_lower = word.lower()

    # 1. Check for exceptions and if the word is already a root
    if word_lower in EXCEPTIONS:
        return word_lower
    if word_lower in LEMMAS:
        return word_lower

    # 2. Implement the flowchart logic (N4 -> N3 -> N2 -> N1)
    # This is the core of the paper's algorithm.
    current_word = word_lower
    current_word, _ = _strip_suffix(current_word, N4_SUFFIXES)
    current_word, _ = _strip_suffix(current_word, N3_SUFFIXES)
    current_word, _ = _strip_suffix(current_word, N2_SUFFIXES)
    current_word, _ = _strip_suffix(current_word, N1_SUFFIXES)

    # 3. Validate the result against the dictionary
    # If the stripped word is a valid lemma, we are done.
    if current_word in LEMMAS:
        return current_word

    # 4. Handle consonant mutation (A critical improvement over the paper)
    # Example: "кітабы" -> "кітаб". We need to check for "кітап".
    if current_word and current_word[-1] in REVERSE_MUTATION:
        mutated_word = current_word[:-1] + REVERSE_MUTATION[current_word[-1]]
        if mutated_word in LEMMAS:
            return mutated_word

    # 5. If no valid stem was found after all stripping, return the original word.
    return word_lower

words_to_test = [
    "тастардың",
    "кітабым",
    "балаларымыз",
    "мектепке",
    "достық",
    "Абай",
    "керемет"
]

print("--- Stemming Results ---")
for w in words_to_test:
    stemmed = stem_kazakh_word(w)
    print(f"'{w}' -> '{stemmed}'")