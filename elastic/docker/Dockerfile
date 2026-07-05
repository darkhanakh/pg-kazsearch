ARG PLUGIN_VERSION=2.3.0
FROM docker.elastic.co/elasticsearch/elasticsearch:8.17.0

ARG PLUGIN_VERSION
COPY --chown=elasticsearch:root build/distributions/analysis-kazsearch-${PLUGIN_VERSION}.zip /tmp/plugin.zip
RUN bin/elasticsearch-plugin install --batch file:///tmp/plugin.zip && \
    rm -f /tmp/plugin.zip
