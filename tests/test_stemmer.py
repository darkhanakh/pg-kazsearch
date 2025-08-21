# -*- coding: utf-8 -*-
import os
import unittest

from prototype.stemmer_prototype import stem_kazakh_word, LEMMAS, EXCEPTIONS
from prototype.test_cases import ALL_CASES


class TestKazakhStemmer(unittest.TestCase):
    pass


def _make_case_test(word: str, expected: str):
    def test(self):
        result = stem_kazakh_word(word, LEMMAS, EXCEPTIONS)
        ok = result == expected
        emoji = "✅" if ok else "❌"
        print(f"{emoji} {word} -> {result} (expected: {expected})")
        self.assertEqual(result, expected, f"{word} -> {result} (expected: {expected})")
    return test


for i, (word, expected) in enumerate(ALL_CASES):
    name = f"test_{i:04d}_{word}"
    safe_name = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
    setattr(TestKazakhStemmer, safe_name, _make_case_test(word, expected))


if __name__ == "__main__":
    unittest.main()


