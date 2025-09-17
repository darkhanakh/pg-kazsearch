# Use the official PostgreSQL latest image as a base
FROM postgres:17

# Install build tools and the PostgreSQL development package
# The -dev package contains the necessary header files for C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-server-dev-17 \
    && rm -rf /var/lib/apt/lists/*