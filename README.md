# kz-psql: Kazakh Stemmer for PostgreSQL (WIP, active development)

A work-in-progress C extension and supporting tools to enable accurate full-text search in Kazakh by combining rule-based suffix stripping with dictionary validation.

## Features

- Hybrid rule-based + lemma-dictionary approach for high-accuracy stemming
- Handles plural, possessive, and case suffixes with Kazakh vowel harmony
- Consonant mutation support (к→г, қ→ғ, п→б) and vowel elision (e.g. `аузы`→`ауыз`)
- Proper noun protection via an exclusion list of names
- Separate stopword list for filtering out function words

## Repository Contents

- `.github/`  
  CI workflows (GitHub Actions)
- `data/`
    - `raw/`  
      Scraped corpora
    - `processed/`  
      `lemmas.txt`, `names.txt`, `stopwords.txt`
- `docs/`  
  Research notes, morphology rules, development journal
- `prototype/`  
  Python stemmer prototype + test corpus
- `src/`  
  `kazakh_stem.c`, `Makefile` for building the extension
- `sql/`  
  Example SQL scripts for dictionary & configuration
- `README.md`  
  This overview

> **WIP:** Core algorithms are prototyped, data lists are being curated, and the C extension is under active refinement.