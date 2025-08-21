# -*- coding: utf-8 -*-
import os
import unittest

from prototype.stemmer_prototype import stem_kazakh_word, LEMMAS, EXCEPTIONS
from prototype.test_cases import ALL_CASES


class TestKazakhStemmer(unittest.TestCase):
    def test_all_cases(self):
        failures = []
        for word, expected in ALL_CASES:
            result = stem_kazakh_word(word, LEMMAS, EXCEPTIONS)
            # Show each tested word and its stemming result
            print(f"{word} -> {result} (expected: {expected})")
            if result != expected:
                failures.append((word, result, expected))
        if failures:
            lines = [f"{w} -> {r} (expected: {e})" for w, r, e in failures]
            self.fail("\n" + "\n".join(lines))


if __name__ == "__main__":
    unittest.main()


