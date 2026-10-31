use kazsearch_core::lexicon::Lexicon;
use kazsearch_core::{stem, StemConfig};

fn cfg_with(words: &[&str]) -> StemConfig {
    let mut lex = Lexicon::new();
    for w in words {
        lex.insert((*w).to_string());
    }
    StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    }
}

fn cfg_no_lexicon() -> StemConfig {
    StemConfig::default()
}

#[test]
fn lexicon_vowel_restore_never_extends_a_lexicon_entry() {
    // жыл "year" and жылы "warm" are both lexicon entries. Stripping
    // жылдары to жыл is already a lemma, so it must not be re-extended to
    // the unrelated adjective.
    let cfg = cfg_with(&["жыл", "жылы", "ел", "еле", "жол", "жола"]);
    assert_eq!(stem("жылдары", &cfg), "жыл");
    assert_eq!(stem("елімізде", &cfg), "ел");
    assert_eq!(stem("жолында", &cfg), "жол");
    // The input itself is a dictionary word, so the safety valve keeps it.
    assert_eq!(stem("жылы", &cfg), "жылы");
}

#[test]
fn lexicon_vowel_restore_still_recovers_elided_final_vowel() {
    // алмат and отбас are not entries but алматы and отбасы are: the restore
    // must still apply when the stripped lexeme is not a lemma itself.
    let cfg = cfg_with(&["алматы", "отбасы"]);
    assert_eq!(stem("алматыда", &cfg), "алматы");
    assert_eq!(stem("отбасының", &cfg), "отбасы");
}

#[test]
fn negative_and_intentive_suffixes_obey_consonant_assimilation() {
    // -бе/-бек follow voiced obstruents only. After a vowel the same letters
    // are part of a Turkic personal name, not a negated verb.
    for cfg in [cfg_no_lexicon(), cfg_with(&["әлі"])] {
        assert_eq!(stem("жәнібек", &cfg), "жәнібек");
        assert_eq!(stem("жәнібектің", &cfg), "жәнібек");
        assert_eq!(stem("жәнібектер", &cfg), "жәнібек");
        assert_eq!(stem("әлібек", &cfg), "әлібек");
        assert_eq!(stem("әділбек", &cfg), "әділбек");
    }
}

#[test]
fn well_formed_negative_and_intentive_verbs_still_strip() {
    let cfg = cfg_no_lexicon();
    assert_eq!(stem("кетпек", &cfg), "кет");
    assert_eq!(stem("жазбайды", &cfg), "жаз");
    assert_eq!(stem("бармайды", &cfg), "бар");
    assert_eq!(stem("білмеймін", &cfg), "біл");
    assert_eq!(stem("өткізбек", &cfg), "өткіз");
    assert_eq!(stem("сенбейді", &cfg), "сен");
    assert_eq!(stem("жарияланбайды", &cfg), "жариялан");
}

#[test]
fn patronymic_suffix_is_not_a_possessive() {
    let cfg = cfg_no_lexicon();
    assert_eq!(stem("төлегенұлы", &cfg), "төлегенұлы");
    assert_eq!(stem("кемелұлы", &cfg), "кемелұлы");
    assert_eq!(stem("серікқызы", &cfg), "серікқызы");
    assert_eq!(stem("төлегенұлының", &cfg), "төлегенұлы");
    assert_eq!(stem("момышұлына", &cfg), "момышұлы");
    assert_eq!(
        stem(&stem("төлегенұлының", &cfg), &cfg),
        stem("төлегенұлының", &cfg)
    );
}

#[test]
fn bare_possessive_after_ul_or_qyz_words_still_strips() {
    let cfg = cfg_with(&["ұл", "қыз"]);
    assert_eq!(stem("ұлы", &cfg), "ұл");
}

#[test]
fn tay_derivation_requires_voiceless_final_base() {
    // қарақы + тай would put -тай after a vowel (it must be -дай), so
    // қарақытай is a name, not a derived form. It used to be peeled down to
    // қара across the fixed-point passes.
    for cfg in [cfg_no_lexicon(), cfg_with(&["қара", "қытай"])] {
        assert_eq!(stem("қарақытай", &cfg), "қарақытай");
        assert_eq!(stem("қарақытайлар", &cfg), "қарақытай");
    }
}

#[test]
fn tay_dai_derivation_still_strips_well_formed_bases() {
    let cfg = cfg_with(&["зат", "сон", "қор"]);
    assert_eq!(stem("заттай", &cfg), "зат");
    assert_eq!(stem("сондай", &cfg), "сон");
    assert_eq!(stem("қордай", &cfg), "қор");
}
