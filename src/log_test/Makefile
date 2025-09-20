# src/log_test/Makefile
MODULES = log_test
EXTENSION = log_test
DATA = log_test--1.0.sql # <-- Add this line

# PG_CONFIG tells the build system where to find PostgreSQL's configuration
PG_CONFIG = pg_config
PG_INCDIR_SERVER := $(shell $(PG_CONFIG) --includedir-server)
PG_INCDIR := $(shell $(PG_CONFIG) --includedir)
PG_CPPFLAGS += -I$(PG_INCDIR_SERVER) -I$(PG_INCDIR)
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)