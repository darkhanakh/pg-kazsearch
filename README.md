# pg_kazsearch

[![PGXN version](https://badge.fury.io/pg/pg_kazsearch.svg)](https://pgxn.org/dist/pg_kazsearch/)

The first PostgreSQL full-text search extension for the Kazakh language.

Kazakh is heavily agglutinative: a single word like `мектептерімізде` carries plural, possessive, and locative suffixes that must all be stripped to reach the root `мектеп`. No existing PostgreSQL or Elasticsearch analyzer handles this. pg_kazsearch fills that gap with a C extension that plugs directly into PostgreSQL's text search pipeline.

---

## What it does

```sql
-- Install and configure
CREATE EXTENSION pg_kazsearch;
CREATE TEXT SEARCH CONFIGURATION kazakh_cfg (PARSER = pg_catalog.default);
ALTER TEXT SEARCH CONFIGURATION kazakh_cfg
    ALTER MAPPING FOR word, hword, hword_part
    WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;

-- Index your table
ALTER TABLE articles ADD COLUMN fts_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('kazakh_cfg', title), 'A') ||
        setweight(to_tsvector('kazakh_cfg', body), 'B')
    ) STORED;
CREATE INDEX idx_fts ON articles USING GIN (fts_vector);

-- Search in Kazakh
SELECT title FROM articles
WHERE fts_vector @@ websearch_to_tsquery('kazakh_cfg', 'президенттің жарлығы')
ORDER BY ts_rank_cd(fts_vector, websearch_to_tsquery('kazakh_cfg', 'президенттің жарлығы')) DESC
LIMIT 10;
```

The stemmer normalizes both query and document terms so `президенттің` (president's) matches `президент`, `мектептерімізде` matches `мектеп`, and `өзгеруі` matches `өзгеру`.

---

## Stemmer quality

Tested on 2,999 Kazakh news articles (tengrinews.kz) with 9,048 evaluation queries:

| Metric | pg_kazsearch | pg_trgm (trigram) |
|--------|-------------|-------------------|
| Recall@10 | **0.784** | 0.635 |
| MRR@10 | **0.712** | 0.566 |
| nDCG@10 | **0.729** | 0.582 |
| Query latency | **0.5 ms** | 1.4 ms |

pg_kazsearch beats trigram by **+16 percentage points** on Recall@10.

### Stemmer examples

| Input | Output | Morphology stripped |
|-------|--------|-------------------|
| мектептерімізде | мектеп | plural + possessive + locative |
| президенттерінің | президент | plural + possessive + genitive |
| өзгеруі | өзгеру | verbal noun possessive |
| берді | бер | past tense |
| экономикалық | экономика | derivational adjective |
| алматыға | алматы | dative case (proper noun) |
| көмек | көмек | protected (lexicon-known root) |

---

## Architecture

The extension consists of:

- **BFS suffix stripper** (`kaz_explore.c`) — breadth-first search over layered suffix rules (predicate, case, possessive, plural, derivational for nouns; person, tense, negation, voice for verbs), with vowel harmony validation and phonological guards
- **Penalty scoring** (`kaz_explore.c`) — candidates scored by syllable count, suffix weakness, derivational depth, and lexicon hits to pick the best stem
- **Lexicon** (`kaz_stems.dict`) — 21,863 POS-tagged stems extracted from Apertium-kaz's morphological transducer, filtered to root forms only (nouns, verbs, adjectives, place names)
- **Stopwords** (`kaz_stopwords.stop`) — 53 Kazakh function words filtered before stemming
- **Vowel harmony** (`kaz_text.c`) — back/front vowel classification with glide exclusion (у/и/ю treated as consonants for harmony) and tail-based fallback for loanwords
- **Stem repair** (`kaz_explore.c`, `pg_kazsearch.c`) — consonant mutation reversal (б→п, г→к, ғ→қ), vowel elision restoration, and lexicon-based vowel append for proper nouns

---

## Quick start

```bash
# Prerequisites: Docker
git clone https://github.com/darkhanakh/pg-kazsearch.git
cd pg-kazsearch

make up          # start PostgreSQL with the extension
make reload      # build, install, and configure kazakh_cfg
make test-ext    # smoke test stemmer + tsvector

# Load the evaluation corpus (optional)
python3 eval/load_corpus.py --input data/corpus/articles.jsonl

# Run the evaluation
python3 eval/run_eval.py --trgm-sample 500
```

---

## Project structure

| Directory | Contents |
|-----------|----------|
| `src/pg_kazsearch/` | C extension: stemmer dictionary, suffix rules, BFS explorer, text utilities, lexicon loader |
| `data/tsearch_data/` | Stem dictionary (`kaz_stems.dict`) and stopword list (`kaz_stopwords.stop`) |
| `scripts/` | `build_lexicon.py` — extracts POS-tagged lemmas from Apertium-kaz |
| `eval/` | Evaluation pipeline: scraper, corpus loader, query generator, FTS vs trigram eval |
| `docker/` | Dockerfile and init SQL for local development |
| `prototype/` | Python stemmer prototypes (v1-v3) used during research phase |
| `benchmark/` | Performance and parity benchmarks |

---

## Lexicon

The stem dictionary is built from [Apertium-kaz](https://github.com/apertium/apertium-kaz), a linguistically vetted morphological transducer for Kazakh. Only entries with explicit POS continuation classes are included:

- **N1/N5/N6** — common nouns (13,900+)
- **V-TV/V-IV** — transitive/intransitive verbs (3,500+)
- **A1/A2** — base adjectives (3,200+)
- **NP-TOP/NP-ORG** — place names and organizations (1,800+)
- **ADV/NUM** — adverbs and numerals (900+)

Derived adjectives (A3/A4), personal names (NP-ANT/NP-COG), and inflected forms are excluded to keep the dictionary clean for stemmer disambiguation.

Rebuild with:

```bash
python3 scripts/build_lexicon.py
```

---

## References

- Krippes, K.A. (1993). *Kazakh (Qazaq-) Grammatical Sketch with Affix List*. ERIC.
- Washington, J., Salimzyanov, I., Tyers, F. (2014). *Finite-state morphological transducers for three Kypchak languages*. LREC.
- Makhambetov, O. et al. (2015). *Data-driven morphological analysis and disambiguation for Kazakh*. CICLing.
- Tolegen, G., Toleu, A., Mussabayev, R. (2022). *A Finite State Transducer Based Morphological Analyzer for Kazakh Language*. IEEE UBMK.

---

## License

- **Code:** [LGPL-3.0](LICENSE)
- **Lexicon data** derived from [Apertium-kaz](https://github.com/apertium/apertium-kaz) (GPL-3.0) and KazNU morphology resources (CC BY-SA).
