CONTAINER   := pg-kazsearch
PG_USER     := postgres
PG_DB       := kazsearch
DOCKER      := docker
COMPOSE     := docker compose

EXTDIR      := src/pg_kazsearch

# ── Helpers ──────────────────────────────────────────────────────────────

define dc_exec
	$(DOCKER) exec -w /app $(CONTAINER) $(1)
endef

define psql_exec
	$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c $(1)
endef

# ── Database ─────────────────────────────────────────────────────────────

.PHONY: up down restart logs status psql

up:
	$(COMPOSE) up -d --build
	@echo "Waiting for database…"
	@until $(DOCKER) exec $(CONTAINER) pg_isready -U $(PG_USER) -d $(PG_DB) -q 2>/dev/null; do sleep 1; done
	@echo "Database ready."

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart
	@until $(DOCKER) exec $(CONTAINER) pg_isready -U $(PG_USER) -d $(PG_DB) -q 2>/dev/null; do sleep 1; done

logs:
	$(COMPOSE) logs -f --tail=50

status:
	@$(DOCKER) exec $(CONTAINER) pg_isready -U $(PG_USER) -d $(PG_DB) && \
		echo "Extensions:" && \
		$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "SELECT extname, extversion FROM pg_extension ORDER BY extname;"

psql:
	$(DOCKER) exec -it $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB)

# ── Extension build ─────────────────────────────────────────────────────

.PHONY: build reload

build:
	python3 scripts/build_lexicon.py
	$(call dc_exec, make -C src/pg_kazsearch)
	$(call dc_exec, make -C src/pg_kazsearch install)

reload: build
	$(call psql_exec, "DROP EXTENSION IF EXISTS pg_kazsearch CASCADE; CREATE EXTENSION pg_kazsearch;")
	$(call psql_exec, "DROP TEXT SEARCH CONFIGURATION IF EXISTS kazakh_cfg CASCADE; CREATE TEXT SEARCH CONFIGURATION kazakh_cfg (PARSER = pg_catalog.default);")
	$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR asciiword WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
	$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR asciihword WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
	$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR hword_asciipart WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
	$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR word WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
	$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR hword WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
	$(DOCKER) exec $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "ALTER TEXT SEARCH CONFIGURATION kazakh_cfg ALTER MAPPING FOR hword_part WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;"
	@echo "Extension reloaded."

# ── Test ─────────────────────────────────────────────────────────────────

.PHONY: test-ext

test-ext:
	@echo "── Testing pg_kazsearch extension ──"
	$(call psql_exec, "SELECT ts_lexize('pg_kazsearch_dict', 'алмаларымыздағы');")
	$(call psql_exec, "SELECT to_tsvector('kazakh_cfg', 'алмаларымыздағы мектептеріміздегі');")

# ── Eval pipeline ────────────────────────────────────────────────────────

CORPUS     ?= data/corpus/articles.jsonl
AUTO_Q     ?= eval/auto_queries.jsonl
GOLD_Q     ?= eval/gold_queries.jsonl
SCRAPE_LIM ?= 3000
EVAL_MAX_Q ?= 0

OPT_REPORT ?= eval/results/optimized_weights.json
OPT_EVALS  ?= 2000
OPT_OBJ    ?= combined

.PHONY: scrape load-corpus gen-queries eval-search pipeline optimize apply-weights

scrape:
	python3 eval/scraper.py --output "$(CORPUS)" --limit $(SCRAPE_LIM) --resume

load-corpus:
	python3 eval/load_corpus.py --input "$(CORPUS)"

gen-queries:
	python3 eval/generate_queries.py --input "$(CORPUS)" --output "$(AUTO_Q)" --use-db-ids

eval-search:
	python3 eval/run_eval.py --auto "$(AUTO_Q)" --gold "$(GOLD_Q)" --max-queries $(EVAL_MAX_Q)

optimize:
	python3 eval/optimize_weights.py --auto "$(AUTO_Q)" --gold "$(GOLD_Q)" \
		--max-evals $(OPT_EVALS) --objective $(OPT_OBJ) --report "$(OPT_REPORT)"

apply-weights:
	@python3 -c "\
	import json, sys; \
	r = json.load(open('$(OPT_REPORT)')); \
	w = r['weights']; \
	opts = ', '.join(f'{k} = {v}' for k, v in w.items()); \
	print(f'ALTER TEXT SEARCH DICTIONARY pg_kazsearch_dict ({opts});')" | \
	$(DOCKER) exec -i $(CONTAINER) psql -U $(PG_USER) -d $(PG_DB)

pipeline: scrape load-corpus gen-queries eval-search

# ── Release ──────────────────────────────────────────────────────────────

DISTVERSION = $(shell grep -m 1 '"version":' META.json | sed -e 's/[[:space:]]*"version":[[:space:]]*"\([^"]*\)".*/\1/')

.PHONY: dist

dist:
	git archive --format zip --prefix=pg_kazsearch-$(DISTVERSION)/ -o pg_kazsearch-$(DISTVERSION).zip HEAD

# ── Cleanup ──────────────────────────────────────────────────────────────

.PHONY: clean nuke

clean:
	-$(call dc_exec, make -C src/pg_kazsearch clean)
	rm -rf eval/results/

nuke: down
	$(COMPOSE) down -v
	@echo "Volumes removed."

# ── Help ─────────────────────────────────────────────────────────────────

.PHONY: help
.DEFAULT_GOAL := help

help:
	@printf "\n  pg_kazsearch — Kazakh full-text search for PostgreSQL\n\n"
	@printf "  \033[1mDatabase\033[0m\n"
	@printf "    make up            Start PostgreSQL container\n"
	@printf "    make down          Stop container\n"
	@printf "    make psql          Open interactive psql session\n"
	@printf "    make status        Show DB and extension status\n"
	@printf "\n"
	@printf "  \033[1mExtension\033[0m\n"
	@printf "    make build         Compile + install extension\n"
	@printf "    make reload        Build + reload extension + config\n"
	@printf "    make test-ext      Smoke test stemmer + tsvector\n"
	@printf "\n"
	@printf "  \033[1mEval\033[0m\n"
	@printf "    make pipeline      Full eval (scrape+load+gen+eval)\n"
	@printf "    make eval-search   Run FTS vs trigram comparison\n"
	@printf "    make load-corpus   Load articles into PostgreSQL\n"
	@printf "    make optimize      Run CMA-ES weight optimizer\n"
	@printf "    make apply-weights Apply optimized weights from JSON\n"
	@printf "\n"
	@printf "  \033[1mCleanup\033[0m\n"
	@printf "    make clean         Remove build artifacts\n"
	@printf "    make nuke          Stop + remove volumes\n"
	@printf "\n"
