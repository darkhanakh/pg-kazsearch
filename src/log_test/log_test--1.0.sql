-- src/log_test/log_test--1.0.sql
\echo Use "CREATE EXTENSION log_test" to load this file. \quit

CREATE FUNCTION pg_log_message(message text)
RETURNS void
AS '$libdir/log_test', 'pg_log_message'
LANGUAGE C STRICT;