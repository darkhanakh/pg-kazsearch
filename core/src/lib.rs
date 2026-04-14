pub mod text;
pub mod rules;
pub mod lexicon;
pub mod explore;
pub mod script;

use explore::ExploreResult;
use rules::{NOUN_LAYERS, VERB_LAYERS, POSS_VOWEL_SUFFIXES};
use script::{LatinAnalysis, ScriptClass};
use text::{count_syllables, fill_prefix_tables, utf8_char_count, word_is_back, utf8_last_cp, is_vowel, PrefixTables};
use lexicon::Lexicon;

pub const MAX_STEM_BYTES: usize = 128;

#[derive(Clone, Debug)]
pub struct PenaltyWeights {
    pub w_no_strip: f64,
    pub w_short_char: f64,
    pub w_no_syll: f64,
    pub w_two_char: f64,
    pub w_three_one: f64,
    pub w_deriv: f64,
    pub w_weak: f64,
    pub w_single_char: f64,
    pub w_verb_all_weak: f64,
    pub w_nik_deriv: f64,
    pub w_final_cons: f64,
    pub w_nominal_inf: f64,
    pub w_verbal_inf: f64,
    pub w_removed: f64,
    pub w_verb_track: f64,
}

impl Default for PenaltyWeights {
    fn default() -> Self {
        Self {
            w_no_strip: 6.0,
            w_short_char: 120.0,
            w_no_syll: 90.0,
            w_two_char: 8.0,
            w_three_one: 2.5,
            w_deriv: 3.2,
            w_weak: 2.5,
            w_single_char: 1.2,
            w_verb_all_weak: 10.0,
            w_nik_deriv: 20.0,
            w_final_cons: 4.0,
            w_nominal_inf: 3.9,
            w_verbal_inf: 4.2,
            w_removed: 0.32,
            w_verb_track: 1.2,
        }
    }
}

#[derive(Clone, Debug)]
pub struct StemConfig {
    pub derivation: bool,
    pub max_steps: i32,
    pub lexicon: Option<Lexicon>,
    pub weights: PenaltyWeights,
    pub script_mode: ScriptMode,
}

impl Default for StemConfig {
    fn default() -> Self {
        Self {
            derivation: true,
            max_steps: 8,
            lexicon: None,
            weights: PenaltyWeights::default(),
            script_mode: ScriptMode::Auto,
        }
    }
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum ScriptMode {
    Auto,
    CyrillicOnly,
}

#[derive(Clone, Debug)]
struct StemOutcome {
    stem: String,
    best: explore::Candidate,
}

fn concat_on_stack<'a>(a: &str, b: &str, buf: &'a mut [u8; MAX_STEM_BYTES]) -> Option<&'a str> {
    let total = a.len() + b.len();
    if total >= MAX_STEM_BYTES {
        return None;
    }
    buf[..a.len()].copy_from_slice(a.as_bytes());
    buf[a.len()..total].copy_from_slice(b.as_bytes());
    Some(std::str::from_utf8(&buf[..total]).unwrap())
}

fn restore_lexicon_vowel(lexeme: &str, lexicon: &Lexicon, steps: i32) -> String {
    if steps < 2 || lexeme.is_empty() || lexeme.len() >= MAX_STEM_BYTES {
        return lexeme.to_string();
    }

    let ends_with_vowel = utf8_last_cp(lexeme).map_or(true, |cp| is_vowel(cp));
    if ends_with_vowel {
        return lexeme.to_string();
    }

    let is_back = word_is_back(lexeme);
    let mut buf = [0u8; MAX_STEM_BYTES];
    let candidates = if is_back { ["ы", "а"] } else { ["і", "е"] };

    for sfx in &candidates {
        if let Some(trial) = concat_on_stack(lexeme, sfx, &mut buf) {
            if lexicon.contains(trial) {
                return trial.to_string();
            }
        }
    }

    lexeme.to_string()
}

// main function to stem a word, entrypoint for the library
pub fn stem(word: &str, cfg: &StemConfig) -> String {
    if word.is_empty() {
        return String::new();
    }

    let analyzed = script::analyze_input(word);

    if cfg.script_mode == ScriptMode::CyrillicOnly {
        return match analyzed.class {
            ScriptClass::Cyrillic => stem_canonical(&analyzed.lowered, cfg).stem,
            _ => analyzed.lowered,
        };
    }

    match analyzed.class {
        ScriptClass::Cyrillic => stem_canonical(&analyzed.lowered, cfg).stem,
        ScriptClass::Latin => {
            let latin = match analyzed.latin.as_ref() {
                Some(v) => v,
                None => return analyzed.lowered,
            };
            stem_latin(latin, cfg).unwrap_or(analyzed.lowered)
        }
        ScriptClass::Mixed | ScriptClass::Unsupported => analyzed.lowered,
    }
}

fn no_strip_candidate(len: usize) -> explore::Candidate {
    explore::Candidate {
        len: len as i32,
        ..Default::default()
    }
}

fn stem_canonical(txt: &str, cfg: &StemConfig) -> StemOutcome {
    let len = txt.len();
    let prefix = fill_prefix_tables(&txt);

    if prefix.syll[len] < 2 {
        return StemOutcome {
            stem: txt.to_string(),
            best: no_strip_candidate(len),
        };
    }

    let original_chars = prefix.chars[len];
    let noun = explore::explore_track_best(&txt, len, &NOUN_LAYERS, cfg, true, &prefix);
    let verb = explore::explore_track_best(&txt, len, &VERB_LAYERS, cfg, false, &prefix);

    let best = select_best(&noun, &verb, &txt, original_chars, &prefix, cfg);
    if best.steps == 0 {
        return StemOutcome {
            stem: txt.to_string(),
            best: no_strip_candidate(len),
        };
    }

    let mut lexeme = txt[..best.len as usize].to_string();
    undo_sound_changes(&mut lexeme, &best);

    if let Some(ref lex) = cfg.lexicon {
        lexeme = restore_lexicon_vowel(&lexeme, lex, best.steps);
    }

    StemOutcome { stem: lexeme, best }
}

fn is_inflectional_strip(best: &explore::Candidate) -> bool {
    best.steps > 0 && (best.nominal_inf > 0 || best.verbal_inf > 0)
}

fn latin_candidate_confident(
    latin: &LatinAnalysis,
    best: &explore::Candidate,
    stem_chars: i32,
    stem_syll: i32,
    lex_word_hit: bool,
    lex_stem_hit: bool,
) -> bool {
    if lex_word_hit || lex_stem_hit {
        return true;
    }
    if !is_inflectional_strip(best) || stem_chars < 3 {
        return false;
    }

    if latin.has_diacritic {
        return stem_syll >= 1;
    }
    if latin.has_q_or_w {
        return stem_syll >= 2;
    }
    stem_syll >= 2
}

fn latin_candidate_score(
    latin: &LatinAnalysis,
    best: &explore::Candidate,
    stem_chars: i32,
    stem_syll: i32,
    lex_word_hit: bool,
    lex_stem_hit: bool,
) -> i32 {
    let mut score: i32 = 0;
    if lex_stem_hit {
        score += 120;
    }
    if lex_word_hit {
        score += 80;
    }
    if is_inflectional_strip(best) {
        score += 35 + best.steps * 6;
    }
    if latin.has_diacritic {
        score += 12;
    } else if latin.has_q_or_w {
        score += 8;
    }

    score += stem_syll * 2;
    score + stem_chars.min(8)
}

fn stem_latin(latin: &LatinAnalysis, cfg: &StemConfig) -> Option<String> {
    let mut best_choice: Option<((i32, i32, i32, i32, i32, i32), String)> = None;

    for candidate in &latin.candidates {
        let outcome = stem_canonical(candidate, cfg);
        let stem_chars = utf8_char_count(&outcome.stem);
        let stem_syll = count_syllables(&outcome.stem);

        let (lex_word_hit, lex_stem_hit) = if let Some(ref lex) = cfg.lexicon {
            (lex.contains(candidate), lex.contains(&outcome.stem))
        } else {
            (false, false)
        };

        if !latin_candidate_confident(
            latin,
            &outcome.best,
            stem_chars,
            stem_syll,
            lex_word_hit,
            lex_stem_hit,
        ) {
            continue;
        }

        let key = (
            latin_candidate_score(
                latin,
                &outcome.best,
                stem_chars,
                stem_syll,
                lex_word_hit,
                lex_stem_hit,
            ),
            i32::from(lex_stem_hit),
            i32::from(lex_word_hit),
            outcome.best.steps,
            outcome.best.nominal_inf + outcome.best.verbal_inf,
            stem_chars,
        );

        let should_replace = best_choice
            .as_ref()
            .map_or(true, |(best_key, _)| key > *best_key);

        if should_replace {
            best_choice = Some((key, outcome.stem));
        }
    }

    best_choice.map(|(_, stem)| stem)
}

fn should_keep_input(
    candidate: &explore::Candidate,
    txt: &str,
    prefix: &PrefixTables,
    lex: &Lexicon,
) -> bool {
    if !lex.contains(txt) {
        return false;
    }
    let len = txt.len();
    let shallow_ambiguous = candidate.steps == 1 && prefix.syll[len] <= 2;
    let lost_syllables = prefix.syll[len] >= 3
        && prefix.syll[candidate.len as usize] < prefix.syll[len];
    shallow_ambiguous || lost_syllables
}

fn select_best(
    noun: &ExploreResult,
    verb: &ExploreResult,
    txt: &str,
    original_chars: i32,
    prefix: &PrefixTables,
    cfg: &StemConfig,
) -> explore::Candidate {
    let scored = || pick_best_scored(noun, verb, txt, original_chars, prefix, &cfg.weights, cfg.lexicon.as_ref());

    let lex = match cfg.lexicon {
        Some(ref l) => l,
        None => return pick_best_scored(noun, verb, txt, original_chars, prefix, &cfg.weights, None),
    };

    if noun.best_lexhit.is_none() && verb.best_lexhit.is_none() {
        return scored();
    }

    match pick_best_lexhit(noun, verb, txt, original_chars, prefix, &cfg.weights) {
        Some(bl) if should_keep_input(&bl, txt, prefix, lex) => {
            explore::Candidate { len: txt.len() as i32, ..Default::default() }
        }
        Some(bl) => bl,
        None => scored(),
    }
}

fn undo_sound_changes(lexeme: &mut String, best: &explore::Candidate) {
    let needs_restore = best.nominal_inf > 0
        && best.last_suffix.map_or(false, |s| POSS_VOWEL_SUFFIXES.contains(&s));

    if needs_restore {
        explore::apply_mutation(lexeme);
        *lexeme = explore::apply_elision_restore(lexeme);
    }
}

fn pick_best_lexhit(
    noun: &ExploreResult,
    verb: &ExploreResult,
    txt: &str,
    original_chars: i32,
    prefix: &PrefixTables,
    weights: &PenaltyWeights,
) -> Option<explore::Candidate> {
    match (noun.best_lexhit, verb.best_lexhit) {
        (Some(nc), Some(vc)) => {
            let np = explore::candidate_penalty(&nc, txt, original_chars, false, prefix, weights);
            let vp = explore::candidate_penalty(&vc, txt, original_chars, true, prefix, weights);
            Some(if explore::candidate_beats(&vc, &nc, vp, np, prefix) { vc } else { nc })
        }
        (Some(c), None) | (None, Some(c)) => Some(c),
        (None, None) => None,
    }
}

fn pick_best_scored(
    noun: &ExploreResult,
    verb: &ExploreResult,
    txt: &str,
    original_chars: i32,
    prefix: &PrefixTables,
    weights: &PenaltyWeights,
    lexicon: Option<&Lexicon>,
) -> explore::Candidate {
    let np = explore::candidate_penalty(&noun.best_scored, txt, original_chars, false, prefix, weights);
    let vp = explore::candidate_penalty(&verb.best_scored, txt, original_chars, true, prefix, weights);

    let best = if explore::candidate_beats(&verb.best_scored, &noun.best_scored, vp, np, prefix) {
        &verb.best_scored
    } else {
        &noun.best_scored
    };

    let no_strip = explore::Candidate { len: txt.len() as i32, ..Default::default() };

    if let Some(lex) = lexicon {
        if lex.contains(txt) {
            let only_single_char = best.steps > 0 && best.single_char == best.steps;
            let lost_syllables = prefix.syll[best.len as usize] < prefix.syll[txt.len()];
            let hits_lex = explore::candidate_hits_lexicon(best, txt, lex);
            if !hits_lex || only_single_char || lost_syllables {
                return no_strip;
            }
        }
    }

    *best
}
