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
