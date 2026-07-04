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
    let prefix = fill_prefix_tables("алма");
    let len = "алма".len();
    assert_eq!(prefix.chars[len], 4);
    assert_eq!(prefix.syll[len], 2);
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

#[test]
fn test_overlong_input_returned_unchanged() {
    // >= MAX_STEM_BYTES: exploration is skipped, input returned (lowercased)
    let long_word = "алма".repeat(40);
    assert!(long_word.len() >= kazsearch_core::MAX_STEM_BYTES);
    assert_eq!(stem_default(&long_word), long_word);
}

#[test]
fn test_max_steps_out_of_range_is_clamped() {
    let mut cfg = StemConfig::default();
    cfg.max_steps = 1_000_000; // would collide in the u16-packed visit key
    assert_eq!(stem("мектептеріміздегі", &cfg), "мектеп");

    cfg.max_steps = -5;
    // clamped to 1: still allowed a single strip
    assert_eq!(stem("алмалар", &cfg), "алма");
}

#[test]
fn test_two_syllable_lexicon_word_not_overstemmed() {
    use kazsearch_core::lexicon::Lexicon;

    // Both the derived lemma and a shorter word are in the dictionary.
    // The lex-hit path used to allow syllable loss for inputs with < 3
    // syllables, mis-stemming dictionary lemmas like балтық -> бала.
    let mut lex = Lexicon::new();
    for w in ["дос", "достық", "бала", "балтық", "екі", "егін"] {
        lex.insert(w.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    assert_eq!(stem("достық", &cfg), "достық");
    assert_eq!(stem("балтық", &cfg), "балтық");
    assert_eq!(stem("егін", &cfg), "егін");
    // Inflected forms of dictionary words must still stem normally.
    assert_eq!(stem("балалар", &cfg), "бала");
}

#[test]
fn test_adjectival_ly_li_derivation() {
    use kazsearch_core::lexicon::Lexicon;

    let mut lex = Lexicon::new();
    // "сулы" is itself a dictionary word (as in the real dict): the -лы
    // guard blocks derivation from the monosyllabic base and the lexicon
    // safety valve keeps the input.
    for w in ["бала", "ашу", "су", "сулы"] {
        lex.insert(w.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    // -лы/-лі "having X" strips only from bases of >= 2 syllables.
    assert_eq!(stem("балалы", &cfg), "бала");
    assert_eq!(stem("ашулы", &cfg), "ашу");
    // Monosyllabic base: guard blocks the strip.
    assert_eq!(stem("сулы", &cfg), "сулы");
}

#[test]
fn test_loan_vowel_harmony() {
    // я/э carry a harmony class; loanword inflections stem directly.
    assert_eq!(stem_default("идеяға"), "идея");
    assert_eq!(stem_default("акцияларды"), "акция");
    assert_eq!(stem_default("станцияда"), "станция");
    // ...and elision restore must not fire after a loan vowel.
    assert_eq!(stem_default("академияны"), "академия");
}

#[test]
fn test_verbal_noun_conflation() {
    use kazsearch_core::lexicon::Lexicon;

    // gold_v2 zero-recall class: query-side verbal nouns (-у/-ю, often +poss)
    // and document-side finite verbs must meet at the same root.
    let mut lex = Lexicon::new();
    for w in [
        "өзгер", "өзгеру", "көбей", "көбею", "ұстал", "ұсталу",
        "тарат", "арзан", "арзанда", "қымбат", "қымбатта",
        // single-syllable roots that must NOT swallow homographs
        "ат", "ату", "аю", "ай", "оқ", "оқу",
    ] {
        lex.insert(w.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    // -у/-ю nominalized infinitives collapse onto the lexicon verb root...
    assert_eq!(stem("өзгеру", &cfg), "өзгер");
    assert_eq!(stem("өзгеруі", &cfg), "өзгер");
    assert_eq!(stem("өзгерді", &cfg), "өзгер");
    assert_eq!(stem("көбею", &cfg), "көбей");
    assert_eq!(stem("көбеюі", &cfg), "көбей");
    assert_eq!(stem("көбейді", &cfg), "көбей");
    assert_eq!(stem("ұсталуы", &cfg), "ұстал");
    assert_eq!(stem("ұсталды", &cfg), "ұстал");
    // ...denominal -да/-та verbs collapse onto the nominal root...
    assert_eq!(stem("арзандады", &cfg), "арзан");
    assert_eq!(stem("арзандауы", &cfg), "арзан");
    assert_eq!(stem("қымбаттады", &cfg), "қымбат");
    assert_eq!(stem("қымбаттауы", &cfg), "қымбат");
    // ...but single-syllable bases stay put: ату is not the horse ат,
    // аю (bear) is not ай (moon), оқу (study) is not оқ (bullet).
    assert_eq!(stem("ату", &cfg), "ату");
    assert_eq!(stem("аю", &cfg), "аю");
    assert_eq!(stem("оқу", &cfg), "оқу");
}

#[test]
fn test_lexicalized_participle_bridge() {
    use kazsearch_core::lexicon::Lexicon;

    // News text uses lexicalized participles (тағайындалған is an Apertium
    // dict entry) while queries use finite past (тағайындалды). The dict
    // entry must not act as a conflation barrier: both reduce to the
    // passive root тағайындал.
    let mut lex = Lexicon::new();
    for w in [
        "тағайында", "тағайындал", "тағайындалған",
        "анықта", "анықтал", "анықталған",
        // participle-shaped nominal homographs that must NOT reduce
        "қор", "қорған", "ту", "туған",
    ] {
        lex.insert(w.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    assert_eq!(stem("тағайындалған", &cfg), "тағайындал");
    assert_eq!(stem("тағайындалды", &cfg), "тағайындал");
    assert_eq!(stem("анықталған", &cfg), "анықтал");
    assert_eq!(stem("анықталды", &cfg), "анықтал");
    // Substantivized participle plural rides the fixed-point loop.
    assert_eq!(stem("тағайындалғандар", &cfg), "тағайындал");
    // Single-strong-syllable bases stay put: қорған is a fortress, not
    // "қор + participle"; туған is native, not "ту + participle".
    assert_eq!(stem("қорған", &cfg), "қорған");
    assert_eq!(stem("туған", &cfg), "туған");
}

#[test]
fn test_participle_plural_idempotent() {
    use kazsearch_core::lexicon::Lexicon;

    let mut lex = Lexicon::new();
    for w in ["тарат", "тарату"] {
        lex.insert(w.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    // stem() used to be non-idempotent: таратқандар stopped at таратқан
    // while таратқан itself went to тарат. The fixed-point pass makes the
    // substantivized participle meet the bare participle and the root.
    assert_eq!(stem("таратқан", &cfg), "тарат");
    assert_eq!(stem("таратқандар", &cfg), "тарат");
    assert_eq!(stem("тарату", &cfg), "тарат");

    let once = stem("таратқандар", &cfg);
    assert_eq!(stem(&once, &cfg), once, "stem must be idempotent");
}

#[test]
fn test_converb_reduction_requires_verb_set() {
    use kazsearch_core::lexicon::Lexicon;

    let mut lex = Lexicon::new();
    lex.insert_verb("асыра".to_string());
    lex.insert_verb("жоспарла".to_string());
    lex.insert_verb("тала".to_string());
    // Dict nouns ending in -п: converbs never lexicalize, so dict membership
    // blocks the reduction even when the residue is a verb (талап / тала).
    lex.insert("талап".to_string());
    lex.insert("кітап".to_string());
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    // Bare -п after a vowel has no BFS rule; the reduction fixes it.
    // (The -ып/-іп converbs are already stripped inside the BFS itself.)
    assert_eq!(stem("асырап", &cfg), "асыра");
    assert_eq!(stem("жоспарлап", &cfg), "жоспарла");
    // Nouns stay put.
    assert_eq!(stem("талап", &cfg), "талап");
    assert_eq!(stem("кітап", &cfg), "кітап");
}

#[test]
fn test_agent_noun_deriv_and_lexicon_aware_ly_guard() {
    use kazsearch_core::lexicon::Lexicon;

    let mut lex = Lexicon::new();
    for w in ["сөндір", "қар", "су", "сулы", "оқушы", "жүргізуші"] {
        lex.insert(w.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    // Agent noun -уші strips down to the verb stem (dict hit beats the
    // previous non-word residue сөндіруш).
    assert_eq!(stem("сөндіруші", &cfg), "сөндір");
    assert_eq!(stem("сөндірушілер", &cfg), "сөндір");
    // Lexicalized professions stay whole: dict entry + 1-strong-syllable
    // base (оқ, жүргіз has 2 but the valve keeps the dict entry).
    assert_eq!(stem("оқушы", &cfg), "оқушы");
    // -лы strips off a monosyllabic dictionary base (қарлы → қар "snow",
    // previously stuck at the non-word қарл)...
    assert_eq!(stem("қарлы", &cfg), "қар");
    // ...but сулы is itself a dict entry and the valve keeps it.
    assert_eq!(stem("сулы", &cfg), "сулы");
}

#[test]
fn test_glide_only_words_are_harmony_neutral() {
    use kazsearch_core::lexicon::Lexicon;

    // туризм has no strong vowel (у and и are transparent glides), so it
    // used to fail every FRONT/BACK-classed suffix check and pass through
    // case-inflected forms unstemmed.
    let mut lex = Lexicon::new();
    lex.insert("туризм".to_string());
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    assert_eq!(stem("туризм", &cfg), "туризм");
    assert_eq!(stem("туризмді", &cfg), "туризм");
    assert_eq!(stem("туризмге", &cfg), "туризм");
    assert_eq!(stem("туризмнің", &cfg), "туризм");
}

#[test]
fn test_verbal_noun_reduction_gated_on_verb_set() {
    use kazsearch_core::lexicon::Lexicon;

    // With a verb set loaded, -у only reduces onto verb roots: қалау must
    // not collapse onto a noun-tagged қала.
    let mut lex = Lexicon::new();
    lex.insert_verb("өзгер".to_string());
    lex.insert("қала".to_string());
    lex.insert("қалау".to_string());
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    assert_eq!(stem("өзгеру", &cfg), "өзгер");
    assert_eq!(stem("қалау", &cfg), "қалау");
}

#[test]
fn test_hyphenated_tokens_stem_last_run() {
    use kazsearch_core::lexicon::Lexicon;

    let mut lex = Lexicon::new();
    for w in ["жек", "қон"] {
        lex.insert(w.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };

    assert_eq!(stem("жекпе-жекте", &cfg), "жекпе-жек");
    assert_eq!(stem("көші-қонның", &cfg), "көші-қон");
    // Trailing separator: nothing after the run to lose.
    assert_eq!(stem("сөз-", &cfg), "сөз-");
    // Mixed-script or non-separator punctuation still passes through.
    assert_eq!(stem("kaspi-банкті", &cfg), "kaspi-банкті");
}
