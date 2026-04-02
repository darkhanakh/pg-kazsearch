pub mod text;
pub mod rules;
pub mod lexicon;
pub mod explore;

use explore::ExploreResult;
use rules::{NOUN_LAYERS, VERB_LAYERS, POSS_VOWEL_SUFFIXES};
use text::{fill_prefix_tables, word_is_back, utf8_last_cp, is_vowel};
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
}

impl Default for StemConfig {
    fn default() -> Self {
        Self {
            derivation: true,
            max_steps: 8,
            lexicon: None,
            weights: PenaltyWeights::default(),
        }
    }
}

fn restore_lexicon_vowel(lexeme: &str, lexicon: &Lexicon, steps: i32) -> String {
    if steps < 2 {
        return lexeme.to_string();
    }
    let len = lexeme.len();
    if len == 0 || len >= MAX_STEM_BYTES {
        return lexeme.to_string();
    }
    if let Some(cp) = utf8_last_cp(lexeme) {
        if is_vowel(cp) {
            return lexeme.to_string();
        }
    } else {
        return lexeme.to_string();
    }

    let is_back = word_is_back(lexeme);

    let v1 = if is_back { "ы" } else { "і" };
    let trial = format!("{}{}", lexeme, v1);
    if trial.len() < MAX_STEM_BYTES && lexicon.contains(&trial) {
        return trial;
    }

    let v2 = if is_back { "а" } else { "е" };
    let trial = format!("{}{}", lexeme, v2);
    if trial.len() < MAX_STEM_BYTES && lexicon.contains(&trial) {
        return trial;
    }

    lexeme.to_string()
}

pub fn stem(word: &str, cfg: &StemConfig) -> String {
    if word.is_empty() {
        return String::new();
    }

    let txt: String = word.to_lowercase();
    if txt.is_empty() {
        return String::new();
    }

    let len = txt.len();
    let (chars_prefix, syll_prefix) = fill_prefix_tables(&txt);

    if syll_prefix[len] < 2 {
        return txt;
    }

    let original_chars = chars_prefix[len] as i32;

    let noun = explore::explore_track_best(
        &txt, len, &NOUN_LAYERS, cfg, true, &chars_prefix, &syll_prefix,
    );
    let verb = explore::explore_track_best(
        &txt, len, &VERB_LAYERS, cfg, false, &chars_prefix, &syll_prefix,
    );

    let best;

    if let Some(ref lex) = cfg.lexicon {
        if noun.has_lexhit || verb.has_lexhit {
            let best_lex = pick_best_lexhit(&noun, &verb, &txt, original_chars, &chars_prefix, &syll_prefix, &cfg.weights);

            if let Some(bl) = best_lex {
                let lex_input_is_known = lex.contains(&txt);
                let shallow_ambiguous = bl.steps == 1 && syll_prefix[len] <= 2;

                if lex_input_is_known
                    && (shallow_ambiguous
                        || (syll_prefix[len] >= 3
                            && (syll_prefix[bl.len as usize] < syll_prefix[len])))
                {
                    return txt;
                }
                best = bl;
            } else {
                best = pick_best_scored(&noun, &verb, &txt, original_chars, &chars_prefix, &syll_prefix, &cfg.weights, cfg.lexicon.as_ref());
            }
        } else {
            best = pick_best_scored(&noun, &verb, &txt, original_chars, &chars_prefix, &syll_prefix, &cfg.weights, cfg.lexicon.as_ref());
        }
    } else {
        best = pick_best_scored(&noun, &verb, &txt, original_chars, &chars_prefix, &syll_prefix, &cfg.weights, None);
    }

    let mut lexeme = txt[..best.len as usize].to_string();

    if best.steps > 0 && best.nominal_inf > 0 {
        if let Some(ref last_sfx) = best.last_suffix {
            if POSS_VOWEL_SUFFIXES.contains(&last_sfx.as_str()) {
                explore::apply_mutation(&mut lexeme);
                lexeme = explore::apply_elision_restore(&lexeme);
            }
        }
    }

    if let Some(ref lex) = cfg.lexicon {
        lexeme = restore_lexicon_vowel(&lexeme, lex, best.steps);
    }

    lexeme
}

fn pick_best_lexhit(
    noun: &ExploreResult,
    verb: &ExploreResult,
    txt: &str,
    original_chars: i32,
    chars_prefix: &[i32],
    syll_prefix: &[i32],
    weights: &PenaltyWeights,
) -> Option<explore::Candidate> {
    match (noun.has_lexhit, verb.has_lexhit) {
        (true, true) => {
            let nc = noun.best_lexhit.as_ref().unwrap();
            let vc = verb.best_lexhit.as_ref().unwrap();
            let np = explore::candidate_penalty(nc, txt, original_chars, false, chars_prefix, syll_prefix, weights);
            let vp = explore::candidate_penalty(vc, txt, original_chars, true, chars_prefix, syll_prefix, weights);
            if explore::candidate_beats(vc, nc, vp, np, chars_prefix) {
                Some(vc.clone())
            } else {
                Some(nc.clone())
            }
        }
        (true, false) => noun.best_lexhit.clone(),
        (false, true) => verb.best_lexhit.clone(),
        (false, false) => None,
    }
}

fn pick_best_scored(
    noun: &ExploreResult,
    verb: &ExploreResult,
    txt: &str,
    original_chars: i32,
    chars_prefix: &[i32],
    syll_prefix: &[i32],
    weights: &PenaltyWeights,
    lexicon: Option<&Lexicon>,
) -> explore::Candidate {
    let np = explore::candidate_penalty(&noun.best_scored, txt, original_chars, false, chars_prefix, syll_prefix, weights);
    let vp = explore::candidate_penalty(&verb.best_scored, txt, original_chars, true, chars_prefix, syll_prefix, weights);

    let input_is_known = lexicon.map_or(false, |l| l.contains(txt));

    let best = if explore::candidate_beats(&verb.best_scored, &noun.best_scored, vp, np, chars_prefix) {
        &verb.best_scored
    } else {
        &noun.best_scored
    };

    if input_is_known {
        let hits = lexicon.map_or(false, |l| explore::candidate_hits_lexicon(best, txt, l));
        if !hits
            || (best.steps > 0 && best.single_char == best.steps)
            || syll_prefix[best.len as usize] < syll_prefix[txt.len()]
        {
            return explore::Candidate {
                len: txt.len() as i32,
                steps: 0,
                nominal_inf: 0,
                verbal_inf: 0,
                deriv: 0,
                weak: 0,
                single_char: 0,
                penalty_flags: 0,
                last_suffix: None,
                last_layer: 0,
            };
        }
    }

    best.clone()
}
