package io.github.darkhanakh.kazsearch;

import org.apache.lucene.analysis.TokenStream;
import org.elasticsearch.common.settings.Settings;
import org.elasticsearch.index.IndexSettings;
import org.elasticsearch.index.analysis.AbstractTokenFilterFactory;

public class KazakhStemTokenFilterFactory extends AbstractTokenFilterFactory {
    KazakhStemTokenFilterFactory(IndexSettings indexSettings, String name, Settings settings) {
        super(name, settings);
    }

    @Override
    public TokenStream create(TokenStream tokenStream) {
        return new KazakhStemTokenFilter(tokenStream);
    }
}
