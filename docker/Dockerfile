# syntax=docker/dockerfile:1
FROM postgres:18 AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    postgresql-server-dev-18 \
    curl \
    pkg-config \
    libclang-dev \
    && rm -rf /var/lib/apt/lists/*

ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH="/usr/local/cargo/bin:${PATH}"

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --profile minimal

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    cargo install --locked cargo-pgrx --version "=0.17.0" \
    && cargo pgrx init --pg18 $(which pg_config) \
    && chmod -R a+rw $CARGO_HOME $RUSTUP_HOME

# ── Pre-build extension into the image ──────────────────────────────────
FROM base AS builder

WORKDIR /build

# 1) Copy only manifests + lockfile to cache dependency compilation
COPY Cargo.toml Cargo.lock ./
COPY .cargo .cargo
COPY core/Cargo.toml core/Cargo.toml
COPY pg_ext/Cargo.toml pg_ext/Cargo.toml
COPY cli/Cargo.toml cli/Cargo.toml
COPY elastic/Cargo.toml elastic/Cargo.toml

# 2) Stub sources so cargo can resolve the workspace and fetch deps
RUN mkdir -p core/src pg_ext/src/bin cli/src elastic/src \
    && echo 'pub fn _stub() {}' > core/src/lib.rs \
    && echo '' > pg_ext/src/lib.rs \
    && echo 'fn main() {}' > cli/src/main.rs \
    && echo '' > elastic/src/lib.rs \
    && echo '::pgrx::pgrx_embed!();' > pg_ext/src/bin/pgrx_embed.rs

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/build/target \
    cargo fetch && cargo build --release -p kazsearch-core 2>/dev/null; true

# 3) Copy real sources and build extension
COPY core core
COPY pg_ext pg_ext
COPY cli cli
COPY elastic elastic
COPY data data

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/build/target \
    find core pg_ext -name '*.rs' -exec touch {} + \
    && cargo pgrx install --release -c /usr/bin/pg_config -p pg_kazsearch

RUN cp data/tsearch_data/kaz_stems.dict "$(pg_config --sharedir)/tsearch_data/" \
    && cp data/tsearch_data/kaz_stopwords.stop "$(pg_config --sharedir)/tsearch_data/"

# ── Dev image (toolchain included for `just build` iteration) ───────────
FROM base AS dev

COPY --from=builder /usr/share/postgresql/18/extension/pg_kazsearch* /usr/share/postgresql/18/extension/
COPY --from=builder /usr/lib/postgresql/18/lib/pg_kazsearch* /usr/lib/postgresql/18/lib/
COPY --from=builder /usr/share/postgresql/18/tsearch_data/kaz_stems.dict /usr/share/postgresql/18/tsearch_data/
COPY --from=builder /usr/share/postgresql/18/tsearch_data/kaz_stopwords.stop /usr/share/postgresql/18/tsearch_data/

# ── Production image (slim, no toolchain) ───────────────────────────────
FROM postgres:18 AS prod

COPY --from=builder /usr/share/postgresql/18/extension/pg_kazsearch* /usr/share/postgresql/18/extension/
COPY --from=builder /usr/lib/postgresql/18/lib/pg_kazsearch* /usr/lib/postgresql/18/lib/
COPY --from=builder /usr/share/postgresql/18/tsearch_data/kaz_stems.dict /usr/share/postgresql/18/tsearch_data/
COPY --from=builder /usr/share/postgresql/18/tsearch_data/kaz_stopwords.stop /usr/share/postgresql/18/tsearch_data/
