//! Russian-keyboard restoration (`KeyboardMode::Restore`).

use std::collections::{BTreeMap, HashSet};
use std::fs;

use kazsearch_core::kbfold::{self, Outcome, MAX_EXTRA_STEM_CALLS};
use kazsearch_core::lexicon::Lexicon;
use kazsearch_core::{stem, KeyboardMode, StemConfig};

const LEXICON: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../data/tsearch_data/kaz_stems.dict");
const BENCH_TOKENS: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/bench_tokens.txt");
const OVERRIDE_GOLDEN: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/kbfold_override_golden.txt");

fn config(keyboard: KeyboardMode) -> StemConfig {
    StemConfig {
        lexicon: Some(Lexicon::load(LEXICON).expect("kaz_stems.dict")),
        keyboard,
        ..StemConfig::default()
    }
}

fn bench_tokens() -> Vec<String> {
    let data = fs::read_to_string(BENCH_TOKENS).expect("bench_tokens.txt");
    let mut seen = HashSet::new();
    data.lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .filter(|l| seen.insert(l.to_string()))
        .map(str::to_string)
        .collect()
}

fn fold(s: &str) -> String {
    kbfold::fold(s)
}

#[test]
fn default_mode_is_exact() {
    assert_eq!(StemConfig::default().keyboard, KeyboardMode::Exact);
    assert_eq!(KeyboardMode::default(), KeyboardMode::Exact);
}

#[test]
fn headline_examples_restore() {
    let cfg = config(KeyboardMode::Restore);
    assert_eq!(stem("мектептеримизде", &cfg), "мектеп");
    assert_eq!(stem("шаруашылыгы", &cfg), "шаруашылық");
    assert_eq!(stem("онимдери", &cfg), "өнім");
    assert_eq!(stem("республикасынын", &cfg), "республика");
    assert_eq!(stem("казакстандагы", &cfg), "қазақстан");
    assert_eq!(stem("енбек", &cfg), "еңбек");
    assert_eq!(stem("Мектептеримизде", &cfg), "мектеп");
}

#[test]
fn restored_forms_meet_proper_forms() {
    let cfg = config(KeyboardMode::Restore);
    for proper in ["мектептерімізде", "шаруашылығы", "өнімдері", "республикасының", "қазақстандағы"] {
        assert_eq!(stem(&fold(proper), &cfg), stem(proper, &cfg), "{proper}");
    }
}

#[test]
fn natural_and_russian_tokens_unchanged() {
    let exact = config(KeyboardMode::Exact);
    let restore = config(KeyboardMode::Restore);
    for w in ["мектеп", "президент", "области", "который", "мектептер", "жана", "мен", "сондай", "бойынша"] {
        assert_eq!(stem(w, &restore), stem(w, &exact), "{w}");
    }
}

#[test]
fn partial_fold_respects_typed_letters() {
    let cfg = config(KeyboardMode::Restore);
    assert_eq!(stem("өнимдери", &cfg), "өнім");
    assert_eq!(stem("мектептерімизде", &cfg), "мектеп");
    // Typed Kazakh letters are user evidence: a lexical-only respelling may
    // not override them (соның is not restored to anything else).
    assert_eq!(stem("соның", &cfg), stem("соның", &config(KeyboardMode::Exact)));
}

#[test]
fn hyphenated_tokens_restore_their_last_run() {
    let cfg = config(KeyboardMode::Restore);
    assert_eq!(stem("ауыл-шаруашылыгы", &cfg), "ауыл-шаруашылық");
}

#[test]
fn restore_without_lexicon_is_exact() {
    let restore = StemConfig { keyboard: KeyboardMode::Restore, ..StemConfig::default() };
    let exact = StemConfig::default();
    for w in ["мектептеримизде", "шаруашылыгы", "онимдери", "мектеп", "алмалар"] {
        assert_eq!(stem(w, &restore), stem(w, &exact), "{w}");
    }
}

#[test]
fn exact_mode_ignores_keyboard_machinery() {
    let exact = config(KeyboardMode::Exact);
    assert_eq!(stem("мектептеримизде", &exact), "мектептеримиз");
    assert_eq!(stem("онимдери", &exact), "онимдери");
}

/// Search-critical: a restored stem must stem to itself in Restore mode,
/// over proper, fully folded and the restored outputs themselves.
#[test]
fn restore_is_idempotent_over_folded_bench_tokens() {
    let cfg = config(KeyboardMode::Restore);
    let mut violations = Vec::new();
    for w in bench_tokens() {
        for input in [w.clone(), fold(&w)] {
            let once = stem(&input, &cfg);
            let twice = stem(&once, &cfg);
            if once != twice {
                violations.push((input, once, twice));
            }
        }
    }
    for (w, a, b) in violations.iter().take(20) {
        eprintln!("{w:<30} stem={a:<20} restem={b}");
    }
    assert!(violations.is_empty(), "{} inputs are not idempotent under Restore", violations.len());
}

/// (b1) structural guarantee: a token the baseline already grounds (the
/// token or its Exact stem is a lexicon entry) stems identically in Restore
/// mode, except through the whole-token override path, whose every corpus
/// instance is frozen in `kbfold_override_golden.txt`.
#[test]
fn grounded_tokens_only_change_through_the_listed_overrides() {
    let exact = config(KeyboardMode::Exact);
    let restore = config(KeyboardMode::Restore);
    let lex = restore.lexicon.as_ref().unwrap();

    let golden: BTreeMap<String, String> = fs::read_to_string(OVERRIDE_GOLDEN)
        .expect("kbfold_override_golden.txt")
        .lines()
        .filter(|l| !l.trim().is_empty() && !l.starts_with('#'))
        .map(|l| {
            let (w, s) = l.split_once('\t').expect("word<TAB>stem");
            (w.to_string(), s.to_string())
        })
        .collect();

    let mut unexpected = Vec::new();
    let mut overrides = BTreeMap::new();
    let mut grounded_count = 0usize;
    for w in bench_tokens() {
        let e = stem(&w, &exact);
        let grounded = lex.contains(&w) || lex.contains(&e);
        if !grounded {
            continue;
        }
        grounded_count += 1;
        let r = stem(&w, &restore);
        if r == e {
            continue;
        }
        let trace = kbfold::explain(&w, &restore, lex);
        match trace.outcome {
            Outcome::Overridden(_) => {
                overrides.insert(w.clone(), r.clone());
            }
            _ => unexpected.push((w.clone(), e.clone(), r.clone())),
        }
    }
    eprintln!("grounded tokens checked: {grounded_count}, overrides: {}", overrides.len());
    assert!(grounded_count > 20_000, "bench_tokens.txt no longer exercises the gate");
    for (w, e, r) in unexpected.iter().take(20) {
        eprintln!("not an override: {w:<25} exact={e:<20} restore={r}");
    }
    assert!(unexpected.is_empty(), "{} grounded tokens changed outside the override path", unexpected.len());

    let missing: Vec<_> = overrides.iter().filter(|(w, s)| golden.get(*w) != Some(s)).collect();
    let stale: Vec<_> = golden.iter().filter(|(w, s)| overrides.get(*w) != Some(s)).collect();
    for (w, s) in &missing {
        eprintln!("override not in golden: {w}\t{s}");
    }
    for (w, s) in &stale {
        eprintln!("golden entry no longer produced: {w}\t{s}");
    }
    assert!(missing.is_empty() && stale.is_empty(), "override golden file out of date");
}

/// Worst case documented in `kbfold::MAX_EXTRA_STEM_CALLS`: the override
/// path and the two-source restore path are exclusive, each capped.
#[test]
fn extra_stem_calls_are_bounded() {
    let cfg = config(KeyboardMode::Restore);
    let lex = cfg.lexicon.as_ref().unwrap();
    let mut max = 0;
    let mut total = 0usize;
    let mut n = 0usize;
    for w in bench_tokens() {
        for input in [w.clone(), fold(&w)] {
            let calls = kbfold::explain(&input, &cfg, lex).extra_calls();
            assert!(calls <= MAX_EXTRA_STEM_CALLS, "{input}: {calls} extra calls");
            max = max.max(calls);
            total += calls;
            n += 1;
        }
    }
    eprintln!("extra stem_cyrillic calls: max {max}, mean {:.3} over {n} inputs", total as f64 / n as f64);
    assert_eq!(MAX_EXTRA_STEM_CALLS, 8);
}

#[test]
fn explain_reports_why() {
    let cfg = config(KeyboardMode::Restore);
    let lex = cfg.lexicon.as_ref().unwrap();

    let gated = kbfold::explain("мектептер", &cfg, lex);
    assert_eq!(gated.outcome, Outcome::Gated);
    assert_eq!(gated.extra_calls(), 0);

    let restored = kbfold::explain("республикасынын", &cfg, lex);
    assert!(matches!(restored.outcome, Outcome::Restored { .. }));
    assert_eq!(restored.output(), "республика");
    let hit = restored.attempts.iter().find(|a| a.accepted).unwrap();
    assert_eq!(hit.candidate, "республикасының");
    assert!(hit.evidence.ng_suffix && !hit.evidence.lexical);

    let overridden = kbfold::explain("енбек", &cfg, lex);
    assert!(matches!(overridden.outcome, Outcome::Overridden(_)));
    assert_eq!(overridden.output(), "еңбек");

    let fallback = kbfold::explain("который", &cfg, lex);
    assert_eq!(fallback.outcome, Outcome::Fallback);
    assert_eq!(fallback.output(), "который");
}
