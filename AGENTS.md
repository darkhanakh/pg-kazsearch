# Repository Guidelines

## What This Is

Kazakh stemmer for PostgreSQL full-text search. BFS suffix-stripping over ordered morphological layers (noun: DERIV→PLUR→POSS→CASE→PRED, verb: VVOICE→VNEG→VTENSE→VPERSON) with vowel harmony enforcement, penalty-based candidate scoring, optional lexicon verification, morphophonological stem repair, and an idempotent fixed-point pass (with lexicon) that conflates verbal nouns, denominal verbs, lexicalized participles (-ған/-ген/-қан/-кен), and converbs (-п, gated on the verb-tagged lexicon sibling `kaz_stems.dict.verbs`) onto their lexicon root. Glide-only words (туризм) are harmony-neutral. Token coverage (measured by `eval/measure_stem_coverage.py` over 45.7k corpus tokens): 76.5% analyzed, 87.5% recognized (stemmed or dictionary lemma).

No prior Kazakh stemmer exists for PostgreSQL or Elasticsearch. This is the first.

## Architecture

Cargo workspace with a shared core library and multiple consumers:

- `core/` — `kazsearch-core`: pure Rust stemmer (BFS engine, suffix rules, vowel harmony, penalty scoring, lexicon, stem repair). No Postgres dependencies.
- `pg_ext/` — `pg_kazsearch`: pgrx-based PostgreSQL extension. Thin wrapper that calls `kazsearch_core::stem()`.
- `cli/` — `kazsearch-cli`: CLI tool (`kazsearch stem`, `analyze`, `bench`, `lexicon validate`).
- `elastic/` — `kazsearch-elastic`: Elasticsearch plugin (placeholder).
- `legacy/pg_kazsearch_c/` — archived original C implementation (reference only, not built).

Key core modules:

- `core/src/explore.rs` — BFS engine, visit set, penalty scorer, stem repair. The heart.
- `core/src/text.rs` — UTF-8 iteration, vowel classification, harmony checks.
- `core/src/rules.rs` — Suffix tables for noun and verb layers.
- `core/src/lexicon.rs` — Lexicon loader.
- `core/src/lib.rs` — `stem()` entry point, winner selection, sound change undo.

Supporting: `scripts/` (lexicon builder), `eval/` (scraper, corpus loader, evaluator, CMA-ES optimizer), `docker/` (dev container).

## Commands

All via `just`.

| Command | What it does |
|---|---|
| `just up` / `just down` | Start/stop Postgres container |
| `just build` | Build lexicon + compile Rust extension + install |
| `just reload` | Build + DROP/CREATE EXTENSION |
| `just cli` | Build CLI tool |
| `just test-core` | Run core library unit tests |
| `just test-ext` | Smoke-test stemmer output via SQL |
| `just psql` | Interactive psql |
| `just pipeline` | Full eval: scrape → load → gen queries → evaluate |
| `just optimize` | CMA-ES penalty weight optimization |
| `just apply-weights` | Push optimized weights to running DB |

## Style

**Rust:** Standard `rustfmt`. Public API in `core/src/lib.rs`. Modules mirror the C design: `explore`, `text`, `rules`, `lexicon`.

**Python:** `snake_case`, standalone `argparse` CLIs.

**Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`). One logical change per commit. `just build && just test-ext` must pass.

## Critical Context

- Kazakh is agglutinative — words stack 5-6 suffixes. Greedy stripping fails; BFS is necessary.
- Vowel harmony (back/front) is mandatory for suffix validation. Glides (у, и, ю) are transparent.
- Penalty constants in `candidate_penalty` (`core/src/explore.rs`) are empirically tuned via CMA-ES against a real corpus. Changing one can break others.
- Stem repair reverses morphophonological changes: consonant mutation (б→п, ғ→қ, г→к), vowel elision, and lexicon-based vowel restore.
- The lexicon safety valve prevents overstemming: if the input word is already in the dictionary and the candidate looks suspicious, return input unchanged.
- Layer guards in `core/src/explore.rs` encode real morphotactic constraints — they are not optional and each one prevents a class of mis-stems.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **Note remaining work** - Summarize anything that needs follow-up in the handoff
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
4. **Clean up** - Clear stashes, prune remote branches
5. **Verify** - All changes committed AND pushed
6. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
