EXTENSION = log
MODULE_big = log
DATA = log--0.0.1.sql
OBJS = log.o 
PG_CONFIG = pg_config
PG_INCDIR_SERVER := $(shell $(PG_CONFIG) --includedir-server)
PG_INCDIR := $(shell $(PG_CONFIG) --includedir)
PG_CPPFLAGS += -I$(PG_INCDIR_SERVER) -I$(PG_INCDIR)
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)