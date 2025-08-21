### August 4, 2025: Mining Apertium Resources

**Goal:**
Kick off extraction of lemmas, suffix lists, and phonology rules from Apertium-kaz to serve as the foundation for our Kazakh stemmer.

### August 22, 2025: From Raw Data to a High-Accuracy Stemmer

**Goal:**
To build a functional Kazakh stemmer by integrating the extracted Apertium data and iteratively refining the algorithm to handle complex morphological rules and ambiguities.

**Key Developments:**

1. **Data Engineering & Preparation:** The initial raw data from `qaz_endings.xls` required significant processing. We moved from a simple surface-level extraction to a more precise "atomic" suffix extraction using regular expressions to parse morpheme boundaries (e.g., `*lar<pl>`). All extracted lemma and suffix data was cleaned, normalized, deduplicated, and serialized into clean, machine-readable `JSON` and `.txt` files. This created a solid, maintainable foundation for the stemmer.
2. **Initial Stemmer Implementation:** The hardcoded suffix lists in the Python script were completely replaced. The stemmer now dynamically loads the `kazakh_atomic_suffixes.json` file at runtime. This decouples the linguistic data from the algorithm logic, making future updates to the suffixes much simpler.
3. **Iterative Debugging & Refinement:** An extensive test suite, covering full paradigms for nouns like "алма" and "сөз", was used to evaluate the stemmer. Initial runs revealed several classes of errors, which were systematically addressed through logical enhancements rather than one-off fixes.

**Challenges & Solutions:**

This phase was defined by tackling classic morphological challenges. The process of debugging and fixing them has made the stemmer significantly more robust.

* **Challenge 1: Over-stemming due to Ambiguity (`қысқа` vs. `қыс`)**
  * **Problem:** The stemmer would incorrectly reduce "қысқа" (short) to "қыс" (winter) because "-қа" is a valid dative suffix. This occurred because both the full word and the potential stem were valid lemmas.
  * **Solution:** We implemented a crucial heuristic: if a word is already a lemma, we do not strip a suffix if the resulting base is *also* a lemma. This "prefer the longer valid lemma" rule prevents the stemmer from being overly aggressive and correctly preserves words like "қысқа" and "басқа".
* **Challenge 2: Incorrect Dative Case Logic (`алмама`, `сөзіме`)**
  * **Problem:** The stemmer failed on dative cases attached to 1st and 2nd person possessives. The constraint logic only permitted the dative suffixes `-а`/`-е` after 3rd person endings.
  * **Solution:** The rule in the `_can_use_case_suffix` function was expanded to recognize the full range of possessive endings (`-м`, `-ым`, `-ң`, `-ың`, etc.) that can precede a dative suffix, fixing an entire class of errors.
* **Challenge 3: Suffix Stripping Conflicts (`алмасын`)**
  * **Problem:** The final major bug was `алмасын` being stemmed to `алмас`. The algorithm was greedily stripping the accusative suffix `-ын` before correctly identifying the morphological structure: `алма` + `сы` (possessive) + `н` (accusative).
  * **Solution:** A specific constraint was added to `_can_use_case_suffix` to **block** the stripping of `-ын` if the base word already appears to have a 3rd person possessive marker (`-с-`). This forces the stemmer to find the correct, more granular path of stripping `-н` first.

**Outcome:**
The stemmer now passes the entire test suite with  **100% accuracy** . It correctly handles a wide range of inflectional paradigms, including vowel elision (`ауыз` -> `аузы`), consonant mutation (`кітап` -> `кітабы`), and long, complex suffix chains. The data-driven approach, fortified with precise rule-based constraints, has proven to be highly effective.
