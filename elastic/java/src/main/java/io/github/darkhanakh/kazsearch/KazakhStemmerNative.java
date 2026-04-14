package io.github.darkhanakh.kazsearch;

import java.security.AccessController;
import java.security.PrivilegedAction;

@SuppressWarnings("removal")
public final class KazakhStemmerNative {
    private static final String LIBRARY_BASENAME = "kazsearch_elastic";

    static {
        AccessController.doPrivileged((PrivilegedAction<Void>) () -> {
            System.loadLibrary(LIBRARY_BASENAME);
            return null;
        });
        int initCode = init0("");
        if (initCode != 0) {
            throw new IllegalStateException("Failed to initialize native kazsearch stemmer: " + initCode);
        }
    }

    private KazakhStemmerNative() {
    }

    public static int init(String lexiconPath) {
        return init0(lexiconPath == null ? "" : lexiconPath);
    }

    public static String stem(String token) {
        if (token == null || token.isEmpty()) {
            return token == null ? "" : token;
        }
        String stemmed = stem0(token);
        return stemmed == null ? token : stemmed;
    }

    private static native int init0(String lexiconPath);

    private static native String stem0(String token);
}
