FROM postgres:18

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-server-dev-18 \
    && rm -rf /var/lib/apt/lists/*
