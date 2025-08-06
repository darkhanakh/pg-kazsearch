# Add the new root to the dictionary for testing
LEMMAS = {
    "бала", "кітап", "тас", "мектеп", "оқушы", "ұстаз", "қасқыр",
    "толқын", "тау", "дос", "жаз", "кел", "оқы", "керемет", "жақсы",
    "ауыз", "орын", "ерін" # Added for vowel elision testing
}

EXCEPTIONS = {"абай", "алматы", "туралы", "және"}

# Suffix lists remain the same
N4_SUFFIXES = ["мын", "мін", "пын", "пін", "сың", "сің", "сыз", "сіз"]
N3_SUFFIXES = [
    "ға", "ге", "қа", "ке", "на", "не", "да", "де", "та", "те",
    "дан", "ден", "тан", "тен", "нан", "нен", "ның", "нің",
    "дың", "дің", "тың", "тің", "мен", "бен", "пен", "ны", "ні",
    "ды", "ді", "ты", "ті"
]
N2_SUFFIXES = [
    "ым", "ім", "ың", "ің", "сы", "сі", "ымыз", "іміз", "іңіз", "іңіз",
    "ы", "і" # Added simple possessive suffixes
]
N1_SUFFIXES = ["лар", "лер", "дар", "дер", "тар", "тер"]

REVERSE_MUTATION = {
    'б': 'п',
    'г': 'к',
    'ғ': 'қ',
    'д': 'т'
}

# --- NEW HELPER FUNCTION FOR VOWEL ELISION ---
def _handle_vowel_elision(stem: str, lemmas: set) -> str or None:
    """
    Tries to reverse vowel elision by inserting 'ы' or 'і'.
    Example: 'ауз' -> 'ауыз'
    """
    if len(stem) < 2:
        return None

    # Define vowel groups for harmony check
    vowel_back = 'аоұы'
    vowel_front = 'әеөүі'
    all_vowels = vowel_back + vowel_front

    # Find the last vowel in the stem to determine harmony
    last_vowel_in_stem = ''
    for char in reversed(stem):
        if char in all_vowels:
            last_vowel_in_stem = char
            break

    # Determine which vowel to insert based on harmony
    vowel_to_insert = ''
    if last_vowel_in_stem in vowel_back:
        vowel_to_insert = 'ы'
    elif last_vowel_in_stem in vowel_front:
        vowel_to_insert = 'і'
    else:
        return None # Cannot determine harmony

    # Create a new potential stem by inserting the vowel before the last char
    new_stem = stem[:-1] + vowel_to_insert + stem[-1]

    # Check if this new stem is a valid lemma
    if new_stem in lemmas:
        return new_stem

    return None

def _strip_suffix(word: str, suffixes: list) -> (str, str or None):
    """
    Helper function to find and strip the longest matching suffix from a list.
    """
    for suffix in sorted(suffixes, key=len, reverse=True):
        if word.endswith(suffix):
            return word[:-len(suffix)], suffix
    return word, None

def _stem_with_order(word: str, order: list, lemmas: set) -> str or None:
    """
    Internal stemming helper that processes suffixes in a specific order.
    """
    current_word = word
    for suffixes in order:
        current_word, _ = _strip_suffix(current_word, suffixes)

    if current_word in lemmas:
        return current_word

    if current_word and current_word[-1] in REVERSE_MUTATION:
        mutated_word = current_word[:-1] + REVERSE_MUTATION[current_word[-1]]
        if mutated_word in lemmas:
            return mutated_word

    elided_stem = _handle_vowel_elision(current_word, lemmas)
    if elided_stem:
        return elided_stem

    return None

def stem_kazakh_word(word: str) -> str:
    """
    Stems a Kazakh word by trying different suffix stripping strategies
    to handle ambiguities.
    """
    word_lower = word.lower()

    if word_lower in EXCEPTIONS or word_lower in LEMMAS:
        return word_lower

    suffix_map = {
        'N1': N1_SUFFIXES, 'N2': N2_SUFFIXES,
        'N3': N3_SUFFIXES, 'N4': N4_SUFFIXES
    }

    # Strategy 1: Standard morphological order (N4 -> N3 -> N2 -> N1)
    order1 = [suffix_map[s] for s in ['N4', 'N3', 'N2', 'N1']]
    stem = _stem_with_order(word_lower, order1, LEMMAS)
    if stem:
        return stem

    # Strategy 2: Swap N2 and N3 to handle possessive ambiguity (N4 -> N2 -> N3 -> N1)
    order2 = [suffix_map[s] for s in ['N4', 'N2', 'N3', 'N1']]
    stem = _stem_with_order(word_lower, order2, LEMMAS)
    if stem:
        return stem

    return word_lower


# --- Updated Test Cases ---
words_to_test = [
    "тастардың",   # Standard
    "кітабым",     # Consonant Mutation
    "балаларымыз", # Suffix chain
    "мектепке",    # Standard
    "аузы",        # Vowel Elision (NEW)
    "орны",        # Vowel Elision (NEW)
    "баланы",      # Accusative case to test strategy
    "Абай",        # Exception
    "керемет"      # Already a root
]

print("--- Stemming Results ---")
for w in words_to_test:
    stemmed = stem_kazakh_word(w)
    print(f"'{w}' -> '{stemmed}'")
