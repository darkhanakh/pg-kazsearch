package io.github.darkhanakh.kazsearch;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class KazakhStemmerNativeTest {
    @Test
    public void stemsKnownWords() {
        assertEquals("алма", KazakhStemmerNative.stem("алмалар"));
        assertEquals("мектеп", KazakhStemmerNative.stem("мектептер"));
        assertEquals("алма", KazakhStemmerNative.stem("алмаларымыздағы"));
        assertEquals("мектеп", KazakhStemmerNative.stem("мектептеріміздегі"));
        assertEquals("бар", KazakhStemmerNative.stem("бармады"));
        assertEquals("алма", KazakhStemmerNative.stem("almalar"));
        assertEquals("мектеп", KazakhStemmerNative.stem("mektepter"));
    }

    @Test
    public void lowercasesInput() {
        assertEquals("алма", KazakhStemmerNative.stem("АЛМАЛАР"));
        assertEquals("мектеп", KazakhStemmerNative.stem("Мектептер"));
    }
}
