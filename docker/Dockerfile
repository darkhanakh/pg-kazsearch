# docker/Dockerfile

# Use the official PostgreSQL latest image as a base
FROM postgres:17

# Install build tools, PostgreSQL development package, and Python
# Also add git and procps for better dev experience inside the container
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-server-dev-17 \
    python3 \
    python3-pip \
    git \
    procps \
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

# Enable Git LFS system-wide inside the container
RUN git lfs install --system