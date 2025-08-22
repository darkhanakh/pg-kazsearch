# kz-psql: Kazakh Stemmer for PostgreSQL (WIP, active development)

A work‑in‑progress PostgreSQL text search dictionary and supporting tools to enable **accurate full‑text search in Kazakh**.
This project combines **rule‑based suffix stripping**, **phonological repair rules**, and a **lemma dictionary** to achieve high accuracy on Kazakh’s rich agglutinative morphology.

---

## ✨ Features

- **Hybrid approach**: rule‑based suffix stripping + lemma dictionary validation
- **Inflectional morphology coverage**:
  - Plural suffixes (`-лар/-лер/-дар/-дер/-тар/-тер`)
  - Possessive suffixes (all persons/numbers, incl. polite forms)
  - Case suffixes (genitive, dative, accusative, locative, ablative, instrumental)
  - Predicate endings (personal endings on verbs)
- **Phonological rules**:
  - Consonant mutation reversal (`кітаб` → `кітап`, `жолдағ` → `жолдақ`)
  - Vowel elision restoration (`аузы` → `ауыз`, `орны` → `орын`, `мұрны` → `мұрын`)
- **Safeguards**:
  - Proper noun protection via an exclusion list (`Абай`, `Алматы`, etc.)
  - Over‑stripping prevention (if both word and base are lemmas, keep the longer form)
  - Contextual constraints (e.g. accusative `-ны/-ні` only after vowel‑final stems)
- **Stopword filtering**: separate curated list of function words
- **PostgreSQL integration**: designed to be compiled as a `ts_dict` extension for `to_tsvector` / `to_tsquery`

---

## 📂 Repository Contents

- `.github/` — CI workflows (GitHub Actions)
- `data/`
  - `raw/` — scraped corpora (Wikipedia, news, etc.)
  - `processed/`
    - `lemmas.txt` — curated lemma list (~tens of thousands of stems)
    - `stopwords.txt` — stopword list
    - `kazakh_atomic_suffixes.json` — cleaned atomic suffix groups (plural, possessive, case, predicate)
- `docs/`
  - Research notes
  - Morphology rules
  - Development journal
- `prototype/`
  - Python stemmer prototype (`stemmer.py`)
  - Test suite (`test_cases.py`) with **347+ test cases** (all passing ✅)
- `src/`
  - `kazakh_stem.c` — C implementation of the stemmer for PostgreSQL
  - `Makefile` — build instructions
- `sql/`
  - Example SQL scripts for dictionary & configuration
- `README.md` — this overview

---

## ✅ Current Status

- **Prototype**: Python stemmer passes **347 test cases** covering:
  - Noun inflections (plural, possessive, case)
  - Verb inflections (tense, negation, participles, predicates)
  - Phonological alternations (mutation, elision)
  - Derivational handling (common participles, causatives, negation)
  - Complex compounds (`қаламсаптарымыздағылардың` → `қаламсап`)
- **Accuracy**: Matches or exceeds KazNU’s reported ~98% accuracy on test sets
- **C extension**: Initial implementation in `src/kazakh_stem.c` (WIP)
- **Integration**: Designed to be used as a PostgreSQL text search dictionary

---

## 🚀 Usage (prototype)

```bash
# Run the Python prototype
cd prototype
python3 stemmer.py "алмаларымыздағы"
# → алма
```

---

## 🚀 Usage (PostgreSQL, planned)

Once compiled and installed:

```sql
-- Create dictionary
CREATE TEXT SEARCH DICTIONARY kazakh_stem (
    TEMPLATE = simple,
    STOPWORDS = kazakh,
    STEMMER = kazakh
);

-- Use in a configuration
CREATE TEXT SEARCH CONFIGURATION kazakh (COPY = simple);
ALTER TEXT SEARCH CONFIGURATION kazakh
    ALTER MAPPING FOR word WITH kazakh_stem;

-- Test
SELECT to_tsvector('kazakh', 'алмаларымыздағы');
-- 'алма':1
```

---

## 📊 Roadmap

- [X] Build Python prototype
- [X] Curate atomic suffix groups from KazNU’s CSE model
- [X] Implement phonological rules (mutation, elision)
- [X] Add 300+ test cases (all passing ✅)
- [ ] Expand lemma dictionary coverage (Wikipedia + news corpora)
- [ ] Optimize recursion depth & performance
- [ ] Finalize C extension (`kazakh_stem.c`)
- [ ] Package as a PostgreSQL extension
- [ ] Benchmark on large corpora (Wikipedia, news)
- [ ] Publish results (coverage, accuracy, F1)

---

## 📚 References

- Tolegen, G., Toleu, A., Mussabayev, R. (2022). *A Finite State Transducer Based Morphological Analyzer for Kazakh Language*. IEEE UBMK.
- Tukeyev, U., Turganbayeva, A., Abduali, B., Rakhimova, D., Amirova, D., Karibayeva, A. (2018). *Lexicon-free stemming for Kazakh language information retrieval*. IEEE AICT.
- Washington, J., Salimzyanov, I., Tyers, F. (2014). *Finite-state morphological transducers for three Kypchak languages*. LREC.
- Makhambetov, O., Makazhanov, A., Sabyrgaliyev, I., Yessenbayev, Z. (2015). *Data-driven morphological analysis and disambiguation for Kazakh*. CICLing.

---

## ⚠️ License

- Code: MIT License
- Data (lemmas, suffixes): CC BY-SA (attribution to KazNU authors for suffix sets)

## 🙌 Acknowledgments
- **KazNU NLP group** (@NLP-KazNU) for sharing their suffix lexicons and morphology models.