package io.github.darkhanakh.kazsearch;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.io.IOException;

import org.apache.lucene.analysis.TokenStream;
import org.apache.lucene.analysis.Tokenizer;
import org.apache.lucene.analysis.tokenattributes.CharTermAttribute;
import org.junit.Test;

public class KazakhStemTokenFilterTest {
    @Test
    public void stemsSingleToken() throws IOException {
        try (TokenStream stream = new KazakhStemTokenFilter(new SingleTokenTokenizer("алмаларымыздағы"))) {
            CharTermAttribute term = stream.addAttribute(CharTermAttribute.class);
            stream.reset();
            assertTrue(stream.incrementToken());
            assertEquals("алма", term.toString());
            assertFalse(stream.incrementToken());
            stream.end();
        }
    }

    @Test
    public void stemsLatinTokenToCanonicalCyrillic() throws IOException {
        try (TokenStream stream = new KazakhStemTokenFilter(new SingleTokenTokenizer("almalar"))) {
            CharTermAttribute term = stream.addAttribute(CharTermAttribute.class);
            stream.reset();
            assertTrue(stream.incrementToken());
            assertEquals("алма", term.toString());
            assertFalse(stream.incrementToken());
            stream.end();
        }
    }

    private static final class SingleTokenTokenizer extends Tokenizer {
        private final String token;
        private final CharTermAttribute term = addAttribute(CharTermAttribute.class);
        private boolean emitted;

        private SingleTokenTokenizer(String token) {
            this.token = token;
        }

        @Override
        public boolean incrementToken() {
            if (emitted) {
                return false;
            }
            clearAttributes();
            term.append(token);
            emitted = true;
            return true;
        }

        @Override
        public void reset() throws IOException {
            super.reset();
            emitted = false;
        }
    }
}
