# Root Makefile — delegates C extension build to PGXS.
# All other commands live in the justfile (run with `just <recipe>`).

.DEFAULT_GOAL := help

.PHONY: help extension clean

help:
	@echo "C extension build (delegates to src/pg_kazsearch via PGXS):"
	@echo "  make extension   Compile the pg_kazsearch shared library"
	@echo "  make clean       Remove build artifacts"
	@echo ""
	@echo "For all other commands use just:"
	@echo "  just --list"

extension:
	$(MAKE) -C src/pg_kazsearch

clean:
	$(MAKE) -C src/pg_kazsearch clean
