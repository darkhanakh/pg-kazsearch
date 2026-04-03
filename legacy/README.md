# Legacy C Extension

This directory contains the original C implementation of the Kazakh stemmer PostgreSQL extension.

It has been archived and replaced by the Rust implementation:

- **Core stemmer logic**: `core/` (`kazsearch-core`)
- **PostgreSQL extension**: `pg_ext/` (`pg_kazsearch`, via pgrx)

The C code is kept here for reference only and is no longer built or maintained.