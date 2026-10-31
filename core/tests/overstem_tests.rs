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

fn cfg_with_verbs(words: &[&str], verbs: &[&str]) -> StemConfig {
    let mut lex = Lexicon::new();
    for w in words {
        lex.insert((*w).to_string());
    }
    for v in verbs {
        lex.insert_verb((*v).to_string());
    }
    StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    }
}

#[test]
fn verb_track_undoes_stem_final_voicing_before_a_vowel_suffix() {
    // соқ + ады → соғады: a stem-final қ/к/п voices before a vowel-initial
    // verbal suffix. The verb parse must land on the lexicon root instead of
    // stopping at соға and leaving a dative-looking -ға to the noun track.
    let cfg = cfg_with_verbs(&["бақа", "жаға", "бала", "тау"], &["соқ", "шық", "бақ", "жақ", "тап", "қақ", "жап"]);
    assert_eq!(stem("соғады", &cfg), "соқ");
    assert_eq!(stem("шығады", &cfg), "шық");
    assert_eq!(stem("шығып", &cfg), "шық");
    assert_eq!(stem("соғатын", &cfg), "соқ");
    assert_eq!(stem("қағып", &cfg), "қақ");
    assert_eq!(stem("жабу", &cfg), "жап");
    assert_eq!(stem("табу", &cfg), "тап");
    assert_eq!(stem("табады", &cfg), "тап");
    // Dictionary nouns that look like converbs of a verb root stay whole,
    // and a real dative is still a dative.
    assert_eq!(stem("бақа", &cfg), "бақа");
    assert_eq!(stem("жаға", &cfg), "жаға");
    assert_eq!(stem("балаға", &cfg), "бала");
    assert_eq!(stem("тауға", &cfg), "тау");
    // Devoicing applies to tense and converb suffixes only. Through a voice
    // suffix it would carry соқтығысқан past the nominal соқтығыс
    // "collision" that соқтығысты still stems to.
    let cfg_voice = cfg_with_verbs(&["соқтығыс"], &["соқтық", "соқтығыс"]);
    assert_eq!(stem("соқтығысқан", &cfg_voice), "соқтығыс");
    assert_eq!(stem("соқтығысты", &cfg_voice), "соқтығыс");
    for w in ["соғады", "шығып", "жабу"] {
        assert_eq!(stem(&stem(w, &cfg), &cfg), stem(w, &cfg), "{w} must stem idempotently");
    }
}

#[test]
fn first_person_suffix_obeys_consonant_assimilation() {
    // талабын is талап+ы+н. -бын after a vowel is impossible (it would be
    // -мын), so the verb parse тала+бын must not be on offer.
    let cfg = cfg_with_verbs(
        &["себеп", "талап", "торап", "студент", "қазақ", "есеп", "кәсіп", "адам"],
        &["сеп", "тала", "тор", "есе", "кәс"],
    );
    assert_eq!(stem("себебін", &cfg), "себеп");
    assert_eq!(stem("талабын", &cfg), "талап");
    assert_eq!(stem("торабын", &cfg), "торап");
    assert_eq!(stem("есебін", &cfg), "есеп");
    assert_eq!(stem("кәсібін", &cfg), "кәсіп");
    // Well-formed first-person forms still strip.
    assert_eq!(stem("студентпін", &cfg), "студент");
    assert_eq!(stem("қазақпын", &cfg), "қазақ");
    assert_eq!(stem("адаммын", &cfg), "адам");
}

#[test]
fn locative_ta_te_requires_a_t_allomorph_base() {
    // -та/-те is the т allomorph of -да/-де. After a vowel, liquid or nasal
    // the letters belong to the word: грамота and плита are loanwords the
    // lexicon lacks, and the parse грамо+та+лар+ын used to cut them.
    let cfg = cfg_with(&["ай", "мектеп", "клуб", "қала", "үй", "ес", "жаз"]);
    assert_eq!(stem("грамоталарын", &cfg), "грамота");
    assert_eq!(stem("плитаның", &cfg), "плита");
    assert_eq!(stem("банкнотаға", &cfg), "банкнота");
    assert_eq!(stem("айта", &cfg), "айта");
    // Well-formed locatives still strip.
    assert_eq!(stem("есте", &cfg), "ес");
    assert_eq!(stem("мектепте", &cfg), "мектеп");
    assert_eq!(stem("клубта", &cfg), "клуб");
    assert_eq!(stem("қалада", &cfg), "қала");
    assert_eq!(stem("үйде", &cfg), "үй");
    // ж, з, ғ take -да/-де, so жазта is not a locative of жаз.
    assert_eq!(stem("жазта", &cfg), "жазта");
    assert_eq!(stem("жазда", &cfg), "жаз");
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
fn past_tense_ty_ti_requires_voiceless_final() {
    // үкіметі is үкімет + possessive. The verb parse -ме (negation) + -ті
    // (past) needs -ті after a vowel, which Kazakh never allows.
    let cfg = cfg_with(&["үкімет", "үкі"]);
    assert_eq!(stem("үкіметі", &cfg), "үкімет");
    assert_eq!(stem("үкіметінің", &cfg), "үкімет");
}

#[test]
fn well_formed_past_tense_after_voiceless_still_strips() {
    let cfg = cfg_no_lexicon();
    assert_eq!(stem("кетті", &cfg), "кет");
    assert_eq!(stem("қашты", &cfg), "қаш");
    assert_eq!(stem("тоқтатты", &cfg), "тоқтат");
    assert_eq!(stem("көрсетті", &cfg), "көрсет");
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

#[test]
fn sound_change_repair_leaves_a_stripped_lemma_alone() {
    // негіз, теңіз, клуб and рейтинг are lemmas as stripped. Vowel
    // re-insertion (негізі → негііз) and final-consonant devoicing
    // (клубы → клуп) only repair stems that are not lemmas.
    let cfg = cfg_with(&["негіз", "теңіз", "тізім", "клуб", "штаб", "рейтинг"]);
    assert_eq!(stem("негізінде", &cfg), "негіз");
    assert_eq!(stem("теңізі", &cfg), "теңіз");
    assert_eq!(stem("клубы", &cfg), "клуб");
    assert_eq!(stem("штабының", &cfg), "штаб");
    assert_eq!(stem("рейтингінде", &cfg), "рейтинг");
}

#[test]
fn sound_change_repair_still_restores_non_lemma_stems() {
    let cfg = cfg_with(&["кітап", "ауыз", "мұрын"]);
    assert_eq!(stem("кітабы", &cfg), "кітап");
    assert_eq!(stem("ауызы", &cfg), "ауыз");
    assert_eq!(stem("мұрны", &cfg), "мұрын");
}

#[test]
fn t_initial_suffixes_attach_after_voiced_stop_finals() {
    // б, в, г, д take the т-initial allomorphs like voiceless consonants
    // (клуб-тық, сауд-тың), so these are well-formed derivations.
    let cfg = cfg_with(&["клуб", "штаб", "форвард", "сауд", "көпмиллиард"]);
    assert_eq!(stem("клубтық", &cfg), "клуб");
    assert_eq!(stem("штабтық", &cfg), "штаб");
    assert_eq!(stem("форвардтық", &cfg), "форвард");
    assert_eq!(stem("көпмиллиардтық", &cfg), "көпмиллиард");
    assert_eq!(stem("саудтың", &cfg), "сауд");
    assert_eq!(stem("штабтың", &cfg), "штаб");
}

#[test]
fn name_overstem_fixes_still_hold_with_voiced_stop_guard() {
    let cfg = cfg_with(&["үкімет", "үкі", "апат", "қара", "қытай"]);
    assert_eq!(stem("үкіметі", &cfg), "үкімет");
    assert_eq!(stem("апаты", &cfg), "апат");
    assert_eq!(stem("қарақытайлар", &cfg), "қарақытай");
}

#[test]
fn tay_derivation_attaches_after_voiced_stop_finals() {
    let cfg = cfg_with(&["клуб", "сауд"]);
    assert_eq!(stem("клубтай", &cfg), "клуб");
    assert_eq!(stem("саудтай", &cfg), "сауд");
}

#[test]
fn lexicon_vowel_restore_resegments_reflexive_to_the_vowel_final_stem() {
    // A vowel-final stem takes plain -н, so the BFS parse жыл + -ын- of
    // жылынады is really жылы + -н-. Handing the one vowel back lands on the
    // intended lemma even though жыл "year" is a lexicon entry too.
    let cfg = cfg_with(&["жыл", "жылы"]);
    assert_eq!(stem("жылынады", &cfg), "жылы");
    assert_eq!(stem("жылынып", &cfg), "жылы");
    assert_eq!(stem("жылыну", &cfg), "жылы");
}

#[test]
fn lexicon_vowel_restore_ignores_vowels_the_suffix_did_not_start_with() {
    let cfg = cfg_with(&["жыл", "жылы", "ел", "еле", "жол", "жола"]);
    assert_eq!(stem("жылдары", &cfg), "жыл");
    assert_eq!(stem("еліміздің", &cfg), "ел");
    assert_eq!(stem("елімізде", &cfg), "ел");
    assert_eq!(stem("жолында", &cfg), "жол");
}

#[test]
fn lexicon_vowel_restore_keeps_a_verb_root_cut_by_a_verbal_suffix() {
    // берілді is бер + passive -іл + past -ді and ұрынып is ұр + reflexive
    // -ын + converb -ып. бері "hither" and ұры "thief" are entries, but the
    // verb roots are already complete.
    let mut lex = Lexicon::new();
    for verb in ["бер", "ұр"] {
        lex.insert_verb(verb.to_string());
    }
    for word in ["бері", "ұры", "жыл", "жылы"] {
        lex.insert(word.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };
    assert_eq!(stem("берілді", &cfg), "бер");
    assert_eq!(stem("ұрынып", &cfg), "ұр");
    assert_eq!(stem("жылынады", &cfg), "жылы");
}
#[test]
fn lexicon_vowel_restore_follows_a_verb_root_when_the_rest_is_a_noun_chain() {
    // желісін is желі + poss. -сі + acc. -н. The BFS reads жел + -іс + -ін
    // instead. жел is a verb root, but the tail сін is a noun inflection
    // chain, while the tail лді of бер-іл-ді is not.
    let mut lex = Lexicon::new();
    for verb in ["жел", "бер"] {
        lex.insert_verb(verb.to_string());
    }
    for word in ["желі", "бері"] {
        lex.insert(word.to_string());
    }
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };
    assert_eq!(stem("желісін", &cfg), "желі");
    assert_eq!(stem("берілді", &cfg), "бер");
}

#[test]
fn possessive_after_lexicon_noun_ending_in_ul_still_strips() {
    // Only a base that is not a word itself reads as a patronymic stub.
    let cfg = cfg_with(&["құл", "бұлбұл", "ұл"]);
    assert_eq!(stem("құлы", &cfg), "құл");
    assert_eq!(stem("бұлбұлы", &cfg), "бұлбұл");
    assert_eq!(stem("бұлбұлының", &cfg), "бұлбұл");
    assert_eq!(stem("төлегенұлы", &cfg), "төлегенұлы");
    assert_eq!(stem("төлегенұлының", &cfg), "төлегенұлы");
    assert_eq!(stem("серікқызы", &cfg), "серікқызы");
}

#[test]
fn possessive_after_lexicon_noun_ending_in_qyz_still_strips() {
    let cfg = cfg_with(&["бейқыз", "қыз"]);
    assert_eq!(stem("бейқызы", &cfg), "бейқыз");
    assert_eq!(stem("серікқызы", &cfg), "серікқызы");
}

#[test]
fn consonant_suffix_after_a_cut_verb_stem_still_restores_its_vowel() {
    // міндеттіге is cut at міндетт and қорғалмаған at қорғал, neither an entry.
    // The verb roots міндетте- and қорғала- are, so the stem is rebuilt from
    // them and the fixed-point pass reduces them to міндет and қорға.
    let mut lex = Lexicon::new();
    for verb in ["міндетте", "қорғала", "қорға"] {
        lex.insert_verb(verb.to_string());
    }
    lex.insert("міндет".to_string());
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };
    assert_eq!(stem("міндеттіге", &cfg), "міндет");
    assert_eq!(stem("қорғалмаған", &cfg), "қорға");
}

#[test]
fn consonant_suffix_does_not_restore_a_noun_vowel() {
    // дәрмек is cut at дәр. дәрі is a noun, not a verb root, so it must not
    // be handed back.
    let mut lex = Lexicon::new();
    lex.insert_verb("бер".to_string());
    lex.insert("дәрі".to_string());
    let cfg = StemConfig {
        lexicon: Some(lex),
        ..Default::default()
    };
    assert_eq!(stem("дәрмектер", &cfg), "дәр");
}
