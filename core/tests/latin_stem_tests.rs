use kazsearch_core::script::lower_kazakh;
use kazsearch_core::{stem, ScriptMode, StemConfig};

fn stem_default(word: &str) -> String {
    stem(word, &StemConfig::default())
}

#[test]
fn test_latin_cross_script_equivalence() {
    assert_eq!(stem_default("almalar"), "алма");
    assert_eq!(stem_default("mektepter"), "мектеп");
    assert_eq!(stem_default("qazaqtar"), "қазақ");
}

#[test]
fn test_latin_uppercase_support() {
    assert_eq!(stem_default("ALMALAR"), "алма");
    assert_eq!(stem_default("QAZAQTAR"), "қазақ");
}

#[test]
fn test_latin_turkic_i_casefold() {
    assert_eq!(lower_kazakh("Iİ"), "ıi");
}

#[test]
fn test_latin_mixed_script_passthrough() {
    assert_eq!(stem_default("алmaлар"), "алmaлар");
}

#[test]
fn test_latin_ascii_safety_passthrough() {
    assert_eq!(stem_default("docker"), "docker");
    assert_eq!(stem_default("solar"), "solar");
}

#[test]
fn test_cyrillic_only_mode_disables_latin() {
    let cfg = StemConfig {
        script_mode: ScriptMode::CyrillicOnly,
        ..Default::default()
    };
    assert_eq!(stem("almalar", &cfg), "almalar");
    assert_eq!(stem("алмалар", &cfg), "алма");
}
