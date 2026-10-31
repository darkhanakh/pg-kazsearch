package io.github.darkhanakh.kazsearch;

/**
 * Thin JNI bridge to the Rust kazsearch stemmer.
 *
 * The native stemmer keeps one process-global configuration (lexicon +
 * script mode), so {@link #configure} applies "first explicit config wins"
 * semantics: the bundled default never overrides an explicit per-index
 * setting, and re-applying an identical config is a no-op.
 */
public final class KazakhStemmerNative {

    /** Native status codes (mirrors elastic/src/lib.rs). */
    public static final int OK = 0;
    public static final int ERR_LEXICON = -3;
    public static final int ERR_CONFIG = -6;

    private static final Object CONFIG_LOCK = new Object();
    private static String appliedConfigKey;

    static {
        NativeLibraryLoader.load();
    }

    private KazakhStemmerNative() {
    }

    /**
     * Applies the lexicon path, script mode and keyboard mode to the native
     * stemmer config.
     *
     * @param lexiconPath absolute path to a lexicon dict, or empty for none
     * @param scriptMode  "auto" or "cyrillic_only"
     * @param keyboard    "exact" (today's stems, byte for byte) or "restore"
     *                    (restore Kazakh letters typed on a Russian layout
     *                    when the lexicon confirms the reading)
     * @param explicit    true when the values come from user-provided index
     *                    settings; explicit configs may replace previous ones,
     *                    the bundled default only applies when nothing has
     *                    been configured yet
     * @return native status code ({@link #OK} on success)
     */
    static int configure(String lexiconPath, String scriptMode, String keyboard, boolean explicit) {
        String lex = lexiconPath == null ? "" : lexiconPath;
        String mode = scriptMode == null || scriptMode.isEmpty() ? "auto" : scriptMode;
        String kb = keyboard == null || keyboard.isEmpty() ? "exact" : keyboard;
        synchronized (CONFIG_LOCK) {
            String key = lex + "\u0000" + mode + "\u0000" + kb;
            if (key.equals(appliedConfigKey)) {
                return OK;
            }
            if (!explicit && appliedConfigKey != null) {
                return OK;
            }
            int code = init0(lex, mode, kb);
            if (code == OK) {
                appliedConfigKey = key;
            }
            return code;
        }
    }

    public static String stem(String token) {
        if (token == null || token.isEmpty()) {
            return token == null ? "" : token;
        }
        String stemmed = stem0(token);
        return stemmed == null ? token : stemmed;
    }

    private static native int init0(String lexiconPath, String scriptMode, String keyboard);

    private static native String stem0(String token);
}
