# Repository Guidelines

## What This Is

Kazakh stemmer for PostgreSQL full-text search. BFS suffix-stripping over ordered morphological layers (noun: DERIV→PLUR→POSS→CASE→PRED, verb: VVOICE→VNEG→VTENSE→VPERSON) with vowel harmony enforcement, penalty-based candidate scoring, optional lexicon verification, and morphophonological stem repair. ~80.88% token coverage.

No prior Kazakh stemmer exists for PostgreSQL or Elasticsearch. This is the first.

## Architecture

The algorithm lives in C, tightly coupled to Postgres (`palloc`/`pfree`, `HTAB`, `PG_FUNCTION_INFO_V1`). Key files:

- `kaz_explore.c` — BFS engine, visit set, penalty scorer, stem repair. The heart.
- `kaz_text.c` — UTF-8 iteration, vowel classification, harmony checks.
- `kaz_rules.c` — Suffix tables for noun and verb layers.
- `pg_kazsearch.c` — Postgres INIT/LEXIZE entry points, dual-track exploration, winner selection.
- `kaz_internal.h` — All shared types (`KazCandidate`, `KazLayerDef`, `KazExploreState`, etc).
- `kaz_lexicon.c` — Lexicon hash-table loader.

Supporting: `scripts/` (lexicon builder), `eval/` (scraper, corpus loader, evaluator, CMA-ES optimizer), `docker/` (dev container).

## Commands

All via `just`. Root `Makefile` only delegates to PGXS.

| Command | What it does |
|---|---|
| `just up` / `just down` | Start/stop Postgres container |
| `just build` | Build lexicon + compile + install extension |
| `just reload` | Build + DROP/CREATE EXTENSION |
| `just test-ext` | Smoke-test stemmer output |
| `just psql` | Interactive psql |
| `just pipeline` | Full eval: scrape → load → gen queries → evaluate |
| `just optimize` | CMA-ES penalty weight optimization |
| `just apply-weights` | Push optimized weights to running DB |

## Style

**C:** Tabs, `kaz_` prefix on symbols, `KAZ_` on constants, `KazPascalCase` on types. Follow Postgres conventions. All internal API in `kaz_internal.h`.

**Python:** `snake_case`, standalone `argparse` CLIs.

**Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`). One logical change per commit. `just build && just test-ext` must pass.

## Critical Context

- Kazakh is agglutinative — words stack 5-6 suffixes. Greedy stripping fails; BFS is necessary.
- Vowel harmony (back/front) is mandatory for suffix validation. Glides (у, и, ю) are transparent.
- Penalty constants in `kaz_candidate_penalty` are empirically tuned via CMA-ES against a real corpus. Changing one can break others.
- Stem repair reverses morphophonological changes: consonant mutation (б→п, ғ→қ, г→к), vowel elision, and lexicon-based vowel restore.
- The lexicon safety valve prevents overstemming: if the input word is already in the dictionary and the candidate looks suspicious, return input unchanged.
- Layer guards in `kaz_explore.c` encode real morphotactic constraints — they are not optional and each one prevents a class of mis-stems.

<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json

# Use stdin for descriptions with special characters (backticks, !, nested quotes)
echo 'Description with `backticks` and "quotes"' | bd create "Title" --description=- --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push` / `bd dolt pull` for remote sync
- No manual export/import needed!

### Important Rules

- Use bd for ALL task tracking
- Always use `--json` flag for programmatic use
- Link discovered work with `discovered-from` dependencies
- Check `bd ready` before asking "what should I work on?"
- Do NOT create markdown TODO lists
- Do NOT use external issue trackers
- Do NOT duplicate tracking systems

<!-- END BEADS INTEGRATION -->

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
