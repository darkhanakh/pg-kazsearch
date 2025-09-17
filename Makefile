.PHONY: help build test benchmark bench benchmarl clean

# Defaults (override like: make benchmark FILE=path/to/file.txt PROCESSES=8)
FILE ?= benchmark/kaz_tokens.txt
OUTDIR ?= results
PROCESSES ?= 0

help:
	@echo "Available targets:"
	@echo "  build       Build PostgreSQL extension(s) in src/"
	@echo "  test        Run extension tests (if configured)"
	@echo "  benchmark   Run benchmark (FILE=$(FILE) PROCESSES=$(PROCESSES) OUTDIR=$(OUTDIR))"
	@echo "  bench       Alias for 'benchmark'"
	@echo "  benchmarl   Alias for 'benchmark' (typo-friendly)"
	@echo "  clean       Clean build artifacts and results"

build:
	$(MAKE) -C src

test:
	-$(MAKE) -C src/log_test installcheck

benchmark:
	python3 benchmark/benchmark.py --file "$(FILE)" --output-dir "$(OUTDIR)" --processes $(PROCESSES)

bench: benchmark

# typo-friendly alias requested in chat
benchmarl: benchmark

clean:
	-$(MAKE) -C src clean
	-$(MAKE) -C src/log_test clean
	rm -rf "$(OUTDIR)"


