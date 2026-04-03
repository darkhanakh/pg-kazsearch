MODULE_big = pg_kazsearch
OBJS = pg_kazsearch.o kaz_text.o kaz_rules.o kaz_lexicon.o kaz_explore.o
EXTENSION  = pg_kazsearch
DATA       = pg_kazsearch--1.0.sql

PG_CONFIG ?= pg_config
PGXS      := $(shell $(PG_CONFIG) --pgxs)

ifdef KAZ_PROFILE
PG_CPPFLAGS += -fno-omit-frame-pointer -g
endif

include $(PGXS)

install: install-kaz-data

install-kaz-data:
	$(MKDIR_P) '$(DESTDIR)$(datadir)/tsearch_data'
	$(INSTALL_DATA) '$(srcdir)/../../data/tsearch_data/kaz_stems.dict' '$(DESTDIR)$(datadir)/tsearch_data/kaz_stems.dict'
	$(INSTALL_DATA) '$(srcdir)/../../data/tsearch_data/kaz_stopwords.stop' '$(DESTDIR)$(datadir)/tsearch_data/kaz_stopwords.stop'
