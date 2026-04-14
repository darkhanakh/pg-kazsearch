package io.github.darkhanakh.kazsearch;

import java.io.IOException;

import org.apache.lucene.analysis.TokenFilter;
import org.apache.lucene.analysis.TokenStream;
import org.apache.lucene.analysis.tokenattributes.CharTermAttribute;
import org.apache.lucene.analysis.tokenattributes.KeywordAttribute;

public final class KazakhStemTokenFilter extends TokenFilter {
    private final CharTermAttribute termAttribute = addAttribute(CharTermAttribute.class);
    private final KeywordAttribute keywordAttribute = addAttribute(KeywordAttribute.class);

    public KazakhStemTokenFilter(TokenStream input) {
        super(input);
    }

    @Override
    public boolean incrementToken() throws IOException {
        if (!input.incrementToken()) {
            return false;
        }

        if (keywordAttribute.isKeyword()) {
            return true;
        }

        String stemmed = KazakhStemmerNative.stem(termAttribute.toString());
        termAttribute.setEmpty().append(stemmed);
        return true;
    }
}
