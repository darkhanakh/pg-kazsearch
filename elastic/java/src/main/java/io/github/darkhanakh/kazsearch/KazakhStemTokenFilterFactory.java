package io.github.darkhanakh.kazsearch;

import java.nio.file.Path;

import org.apache.lucene.analysis.TokenStream;
import org.elasticsearch.common.settings.Settings;
import org.elasticsearch.env.Environment;
import org.elasticsearch.index.IndexSettings;
import org.elasticsearch.index.analysis.AbstractTokenFilterFactory;

/**
 * Factory for the {@code kazsearch_stem} token filter.
 *
 * Index-level settings:
 * <ul>
 *   <li>{@code lexicon_path} — absolute path to a lexicon dict file,
 *       overriding the {@code data/kaz_stems.dict} bundled with the plugin</li>
 *   <li>{@code script_mode} — {@code auto} (default; Latin input is
 *       transliterated and stemmed) or {@code cyrillic_only}</li>
 * </ul>
 *
 * Note: the native stemmer configuration is process-global; if multiple
 * indices declare conflicting settings, the first explicit configuration wins.
 */
public class KazakhStemTokenFilterFactory extends AbstractTokenFilterFactory {

    private static final String PLUGIN_NAME = "analysis-kazsearch";
    private static final String BUNDLED_LEXICON = "kaz_stems.dict";

    KazakhStemTokenFilterFactory(IndexSettings indexSettings, Environment environment,
                                 String name, Settings settings) {
        super(name, settings);

        Path pluginsPath = pluginsPath(environment);
        if (pluginsPath != null) {
            NativeLibraryLoader.hintPluginDirectory(pluginsPath.resolve(PLUGIN_NAME));
        }

        String lexiconSetting = settings.get("lexicon_path");
        String scriptMode = settings.get("script_mode", "auto");
        if (!"auto".equals(scriptMode) && !"cyrillic_only".equals(scriptMode)) {
            throw new IllegalArgumentException(
                    "[script_mode] must be 'auto' or 'cyrillic_only', got [" + scriptMode + "]");
        }
        boolean explicit = lexiconSetting != null || settings.get("script_mode") != null;
        String lexiconPath = lexiconSetting != null ? lexiconSetting : bundledLexiconPath();

        int code = KazakhStemmerNative.configure(lexiconPath, scriptMode, explicit);
        if (code == KazakhStemmerNative.ERR_LEXICON && lexiconSetting == null) {
            // The bundled dict is missing or unreadable; degrade gracefully to
            // stemming without a lexicon rather than failing index creation.
            code = KazakhStemmerNative.configure("", scriptMode, explicit);
        }
        if (code != KazakhStemmerNative.OK) {
            throw new IllegalArgumentException(
                    "kazsearch_stem: native stemmer init failed (code " + code
                            + ") for lexicon_path=[" + lexiconPath + "], script_mode=["
                            + scriptMode + "]");
        }
    }

    /**
     * ES renamed {@code Environment.pluginsFile()} to {@code pluginsDir()}
     * after 8.17. Resolve whichever exists so one source tree compiles and
     * runs across all supported ES versions.
     */
    private static Path pluginsPath(Environment environment) {
        if (environment == null) {
            return null;
        }
        for (String method : new String[] {"pluginsDir", "pluginsFile"}) {
            try {
                return (Path) Environment.class.getMethod(method).invoke(environment);
            } catch (ReflectiveOperationException | ClassCastException ignored) {
                // try the next name
            }
        }
        return null;
    }

    private static String bundledLexiconPath() {
        Path pluginDir = NativeLibraryLoader.pluginDirectory();
        if (pluginDir == null) {
            return "";
        }
        return pluginDir.resolve("data").resolve(BUNDLED_LEXICON).toAbsolutePath().toString();
    }

    @Override
    public TokenStream create(TokenStream tokenStream) {
        return new KazakhStemTokenFilter(tokenStream);
    }
}
