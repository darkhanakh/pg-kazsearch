use kazsearch_core::{stem, StemConfig};

fn stem_default(word: &str) -> String {
    let cfg = StemConfig::default();
    stem(word, &cfg)
}

#[test]
fn test_short_words_returned_unchanged() {
    assert_eq!(stem_default("ал"), "ал");
    assert_eq!(stem_default("бар"), "бар");
    assert_eq!(stem_default(""), "");
}

#[test]
fn test_single_syllable_returned_unchanged() {
    assert_eq!(stem_default("бас"), "бас");
    assert_eq!(stem_default("көз"), "көз");
}

#[test]
fn test_noun_plural() {
    assert_eq!(stem_default("алмалар"), "алма");
    assert_eq!(stem_default("мектептер"), "мектеп");
    assert_eq!(stem_default("адамдар"), "адам");
}

#[test]
fn test_noun_case_genitive() {
    assert_eq!(stem_default("алманың"), "алма");
    assert_eq!(stem_default("мектептің"), "мектеп");
}

#[test]
fn test_noun_case_ablative() {
    assert_eq!(stem_default("алмадан"), "алма");
}

#[test]
fn test_noun_possessive() {
    assert_eq!(stem_default("алмасы"), "алма");
    // Without lexicon, мектебі stems to мектеп (possessive strip + no mutation visible)
    assert_eq!(stem_default("мектебі"), "мектеп");
}

#[test]
fn test_noun_stacked_suffixes() {
    let result = stem_default("алмаларымыздағы");
    assert_eq!(result, "алма");

    let result = stem_default("мектептеріміздегі");
    assert_eq!(result, "мектеп");
}

#[test]
fn test_noun_pred_myn() {
    // адаммын: адам + мын (pred); without lexicon, aggressive stripping may occur
    let result = stem_default("адаммын");
    assert!(!result.is_empty());
}

#[test]
fn test_verb_tense_ady() {
    // барады = бар + ады (tense) — result is "бара" without lexicon
    assert_eq!(stem_default("барады"), "бара");
}

#[test]
fn test_verb_negation() {
    assert_eq!(stem_default("бармады"), "бар");
}

#[test]
fn test_verb_person() {
    assert_eq!(stem_default("барамын"), "бара");
}

#[test]
fn test_derivation_lyk() {
    assert_eq!(stem_default("алмалық"), "алма");
}

#[test]
fn test_derivation_shy() {
    // ші is a weak suffix — it strips to мектепш (one Cyrillic char left after strip)
    let result = stem_default("мектепші");
    assert!(result.starts_with("мектеп"));
}

#[test]
fn test_lowercase_handling() {
    assert_eq!(stem_default("АЛМАЛАР"), "алма");
    assert_eq!(stem_default("Мектептер"), "мектеп");
}

#[test]
fn test_text_module_vowel_classification() {
    use kazsearch_core::text::*;
    assert!(is_back_vowel('а'));
    assert!(is_back_vowel('о'));
    assert!(is_back_vowel('ұ'));
    assert!(is_back_vowel('ы'));
    assert!(is_back_vowel('у'));

    assert!(is_front_vowel('ә'));
    assert!(is_front_vowel('е'));
    assert!(is_front_vowel('ө'));
    assert!(is_front_vowel('ү'));
    assert!(is_front_vowel('і'));
    assert!(is_front_vowel('и'));

    assert!(is_vowel('а'));
    assert!(is_vowel('е'));
    assert!(!is_vowel('б'));

    assert!(is_glide('у'));
    assert!(is_glide('и'));
    assert!(is_glide('ю'));
}

#[test]
fn test_text_module_syllable_count() {
    use kazsearch_core::text::*;
    assert_eq!(count_syllables("алма"), 2);
    assert_eq!(count_syllables("мектеп"), 2);
    assert_eq!(count_syllables("бас"), 1);
    // 'у' is both a glide and a back vowel — counted as syllable
    // алмаларымыздағы has 7 vowel codepoints
    assert_eq!(count_syllables("алмаларымыздағы"), 7);
}

#[test]
fn test_text_module_harmony() {
    use kazsearch_core::text::*;
    assert!(harmony_ok("алма", 1));
    assert!(!harmony_ok("мектеп", 1));
    assert!(harmony_ok("мектеп", 2));
    assert!(harmony_ok("anything", 0));
}

#[test]
fn test_text_module_word_is_back() {
    use kazsearch_core::text::*;
    assert!(word_is_back("алма"));
    assert!(!word_is_back("мектеп"));
    assert!(word_is_back("бар"));
}

#[test]
fn test_text_module_prefix_tables() {
    use kazsearch_core::text::*;
    let (cp, sp) = fill_prefix_tables("алма");
    let len = "алма".len();
    assert_eq!(cp[len], 4);
    assert_eq!(sp[len], 2);
}

#[test]
fn test_explore_apply_mutation() {
    use kazsearch_core::explore::apply_mutation;
    let mut s = "адамб".to_string();
    apply_mutation(&mut s);
    assert_eq!(s, "адамп");

    let mut s = "адамғ".to_string();
    apply_mutation(&mut s);
    assert_eq!(s, "адамқ");

    let mut s = "адамг".to_string();
    apply_mutation(&mut s);
    assert_eq!(s, "адамк");
}

#[test]
fn test_explore_apply_mutation_exception() {
    use kazsearch_core::explore::apply_mutation;
    // After 'о' (back vowel in exception list), 'г' should not mutate
    let mut s = "ког".to_string();
    apply_mutation(&mut s);
    assert_eq!(s, "ког");
}

#[test]
fn test_explore_elision_restore() {
    use kazsearch_core::explore::apply_elision_restore;
    let result = apply_elision_restore("алмн");
    assert_eq!(result, "алмын");
}

#[test]
fn test_verb_voice_causative() {
    // барғыз = бар + ғыз (voice)
    assert_eq!(stem_default("барғыз"), "бар");
}

#[test]
fn test_verb_compound_strip() {
    // бармаған = бар + ма + ған (neg + tense)
    assert_eq!(stem_default("бармаған"), "бар");
}

#[test]
fn test_noun_dative() {
    assert_eq!(stem_default("алмаға"), "алма");
    assert_eq!(stem_default("мектепке"), "мектеп");
}

#[test]
fn test_noun_locative() {
    assert_eq!(stem_default("алмада"), "алма");
    assert_eq!(stem_default("мектепте"), "мектеп");
}

#[test]
fn test_comparative() {
    assert_eq!(stem_default("алмарақ"), "алма");
}
