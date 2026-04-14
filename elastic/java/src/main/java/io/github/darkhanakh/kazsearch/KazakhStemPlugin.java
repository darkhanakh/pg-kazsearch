package io.github.darkhanakh.kazsearch;

import java.util.Map;

import org.elasticsearch.index.analysis.TokenFilterFactory;
import org.elasticsearch.indices.analysis.AnalysisModule;
import org.elasticsearch.plugins.AnalysisPlugin;
import org.elasticsearch.plugins.Plugin;

public class KazakhStemPlugin extends Plugin implements AnalysisPlugin {
    @Override
    public Map<String, AnalysisModule.AnalysisProvider<TokenFilterFactory>> getTokenFilters() {
        return Map.of("kazsearch_stem", (indexSettings, environment, name, settings) ->
                new KazakhStemTokenFilterFactory(indexSettings, name, settings));
    }
}
