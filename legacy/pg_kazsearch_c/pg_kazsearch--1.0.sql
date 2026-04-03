\echo Use "CREATE EXTENSION pg_kazsearch" to load this file. \quit

CREATE FUNCTION pg_kazsearch_init(internal)
RETURNS internal
AS '$libdir/pg_kazsearch', 'pg_kazsearch_init'
LANGUAGE C STRICT;

CREATE FUNCTION pg_kazsearch_lexize(internal, internal, internal, internal)
RETURNS internal
AS '$libdir/pg_kazsearch', 'pg_kazsearch_lexize'
LANGUAGE C STRICT;

CREATE TEXT SEARCH TEMPLATE pg_kazsearch_template (
    INIT = pg_kazsearch_init,
    LEXIZE = pg_kazsearch_lexize
);

CREATE TEXT SEARCH DICTIONARY pg_kazsearch_stop (
    TEMPLATE = pg_catalog.simple,
    STOPWORDS = kaz_stopwords,
    ACCEPT = false
);

CREATE TEXT SEARCH DICTIONARY pg_kazsearch_dict (
    TEMPLATE = pg_kazsearch_template,
    derivation = true,
    max_steps = 8,
    lexicon = kaz_stems
);

CREATE TEXT SEARCH CONFIGURATION kazakh_cfg (PARSER = pg_catalog.default);

ALTER TEXT SEARCH CONFIGURATION kazakh_cfg
    ALTER MAPPING FOR asciiword, asciihword, hword_asciipart,
                      word, hword, hword_part
    WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;
