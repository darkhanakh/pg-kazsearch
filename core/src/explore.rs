use std::collections::{HashSet, VecDeque};

use crate::lexicon::Lexicon;
use crate::rules::*;
use crate::text::*;
use crate::{PenaltyWeights, StemConfig, MAX_STEM_BYTES};

const QUEUE_MAX: usize = 1 << 18;
const PENALTY_NIK_DERIV: u8 = 1;
const PENALTY_FINAL_CONS: u8 = 2;

#[derive(Copy, Clone, Debug)]
pub struct Candidate {
    pub len: i32,
    pub steps: i32,
    pub nominal_inf: i32,
    pub verbal_inf: i32,
    pub deriv: i32,
    pub weak: i32,
    pub single_char: i32,
    pub penalty_flags: u8,
    pub last_suffix: Option<&'static str>,
    pub last_layer: i32,
}

impl Default for Candidate {
    fn default() -> Self {
        Self {
            len: 0,
            steps: 0,
            nominal_inf: 0,
            verbal_inf: 0,
            deriv: 0,
            weak: 0,
            single_char: 0,
            penalty_flags: 0,
            last_suffix: None,
            last_layer: 0,
        }
    }
}

#[derive(Copy, Clone, Debug)]
struct ExploreState {
    len: i32,
    state_idx: i32,
    c: Candidate,
}

#[derive(Clone, Debug)]
pub struct ExploreResult {
    pub best_scored: Candidate,
    pub best_lexhit: Option<Candidate>,
}

/// Match suffix only when it is strictly shorter than the word (mirrors C's
/// `kaz_ends_with_bytes_n` which returns false when `suffix_len >= len`).
#[inline]
fn sfx_shorter(s: &str, suffix: &str) -> bool {
    suffix.len() < s.len() && s.ends_with(suffix)
}

fn penalty_flags_at(word: &str, len: usize) -> u8 {
    let s = &word[..len];
    let mut f: u8 = 0;

    if len < 2 {
        return 0;
    }

    if sfx_shorter(s, "д") || sfx_shorter(s, "г") || sfx_shorter(s, "ғ") || sfx_shorter(s, "б") {
        f |= PENALTY_FINAL_CONS;
    }

    if len < 6 {
        return f;
    }

    if sfx_shorter(s, "дағ") || sfx_shorter(s, "дег")
        || sfx_shorter(s, "тағ") || sfx_shorter(s, "тег")
        || sfx_shorter(s, "нік") || sfx_shorter(s, "дік")
        || sfx_shorter(s, "тік")
    {
        f |= PENALTY_NIK_DERIV;
    }

    f
}

fn visit_key(len: i32, state_idx: i32, steps: i32) -> u64 {
    ((len as u64) << 32) | (((state_idx as u16) as u64) << 16) | ((steps as u16) as u64)
}

fn layer_guard(layer_id: i32, sfx: &str, base: &str, steps_so_far: i32) -> bool {
    match layer_id {
        LAYER_CASE => {
            if sfx == "н" {
                return base.ends_with("сы") || base.ends_with("сі")
                    || base.ends_with("ы") || base.ends_with("і");
            }
            if sfx == "а" || sfx == "е" {
                const POSS_TAILS: &[&str] = &[
                    "ымыз", "іміз", "ыңыз", "іңіз",
                    "мыз", "міз", "ңыз", "ңіз",
                    "ым", "ім", "ың", "ің",
                    "сы", "сі", "ы", "і",
                ];
                if POSS_TAILS.iter().any(|t| base.ends_with(t)) {
                    return true;
                }
                if (base.ends_with("м") || base.ends_with("ң")) && !base.is_empty() {
                    if let Some(prev) = base.chars().rev().nth(1) {
                        return is_vowel(prev);
                    }
                }
                return false;
            }
            match utf8_last_cp(base) {
                Some(cp) => match sfx {
                    "ны" | "ні" => return is_vowel(cp),
                    "ын" | "ін" | "ды" | "ді" | "ты" | "ті" => return !is_vowel(cp),
                    _ => {}
                },
                None => return false,
            }
        }
        LAYER_POSS => {
            if sfx == "м" || sfx == "ң" {
                return utf8_last_cp(base).map_or(false, |cp| is_vowel(cp));
            }
        }
        LAYER_VTENSE => match sfx {
            "у" => return utf8_char_count(base) >= 2 && count_syllables(base) >= 1,
            "й" => return steps_so_far > 0,
            "а" | "е" => return steps_so_far > 0 && count_syllables(base) >= 2,
            _ => {}
        },
        LAYER_VNEG => return utf8_char_count(base) >= 3,
        LAYER_VPERSON => {
            if matches!(sfx, "м" | "ң" | "қ" | "к") {
                return count_syllables(base) >= 2;
            }
        }
        LAYER_DERIV => {
            if matches!(sfx, "лық" | "лік" | "дық" | "дік" | "тық" | "тік") {
                return count_syllables(base) >= 2;
            }
        }
        _ => {}
    }
    true
}

fn next_state_idx(noun_track: bool, cur_idx: i32, layer_id: i32, suffix: &str) -> i32 {
    if !noun_track {
        if layer_id == LAYER_VVOICE {
            return 3;
        }
        return cur_idx + 1;
    }

    if layer_id == LAYER_DERIV
        && (suffix == "ндағы" || suffix == "ндегі"
            || suffix == "дағы" || suffix == "дегі"
            || suffix == "тағы" || suffix == "тегі")
    {
        return 2;
    }
    if layer_id == LAYER_DERIV {
        return 4;
    }
    cur_idx + 1
}

pub fn candidate_penalty(
    c: &Candidate,
    _word: &str,
    original_chars: i32,
    verb_track: bool,
    prefix: &PrefixTables,
    w: &PenaltyWeights,
) -> f64 {
    let chars = prefix.chars[c.len as usize];
    let syll = prefix.syll[c.len as usize];
    let removed = (original_chars - chars).max(0);
    let mut p: f64 = 0.0;

    if c.steps == 0 { p += w.w_no_strip; }
    if chars < 2 { p += w.w_short_char; }
    if syll < 1 { p += w.w_no_syll; }
    if chars == 2 { p += w.w_two_char; }
    if chars == 3 && syll == 1 { p += w.w_three_one; }

    p += c.deriv as f64 * w.w_deriv
        + c.weak as f64 * w.w_weak
        + c.single_char as f64 * w.w_single_char;

    if verb_track && c.verbal_inf > 0 && c.verbal_inf == c.weak {
        p += w.w_verb_all_weak;
    }

    if c.penalty_flags & PENALTY_NIK_DERIV != 0 { p += w.w_nik_deriv; }
    if c.penalty_flags & PENALTY_FINAL_CONS != 0 { p += w.w_final_cons; }

    p -= c.nominal_inf as f64 * w.w_nominal_inf
        + c.verbal_inf as f64 * w.w_verbal_inf
        + removed.min(10) as f64 * w.w_removed;

    if verb_track { p += w.w_verb_track; }

    p
}

pub fn candidate_beats(
    challenger: &Candidate,
    current: &Candidate,
    p_challenger: f64,
    p_current: f64,
    prefix: &PrefixTables,
) -> bool {
    #![allow(clippy::float_cmp)]
    if p_challenger != p_current {
        return p_challenger < p_current;
    }
    if challenger.deriv != current.deriv {
        return challenger.deriv < current.deriv;
    }
    if challenger.weak != current.weak {
        return challenger.weak < current.weak;
    }

    let inf_ch = challenger.nominal_inf + challenger.verbal_inf;
    let inf_cu = current.nominal_inf + current.verbal_inf;
    if inf_ch != inf_cu {
        return inf_ch > inf_cu;
    }

    let ch_ch = prefix.chars[challenger.len as usize];
    let ch_cu = prefix.chars[current.len as usize];
    ch_ch > ch_cu
}

pub fn apply_mutation(lexeme: &mut String) {
    if lexeme.len() < 2 {
        return;
    }
    if lexeme.ends_with("б") {
        let byte_len = "б".len();
        let new_len = lexeme.len() - byte_len;
        lexeme.truncate(new_len);
        lexeme.push_str("п");
    } else if lexeme.ends_with("ғ") {
        let byte_len = "ғ".len();
        let new_len = lexeme.len() - byte_len;
        lexeme.truncate(new_len);
        lexeme.push_str("қ");
    } else if lexeme.ends_with("г") {
        let base = &lexeme[..lexeme.len() - "г".len()];
        if let Some(cp) = utf8_last_cp(base) {
            if cp == 'о' || cp == 'ө' || cp == 'ұ' || cp == 'ү' || cp == 'у' {
                return;
            }
        }
        let byte_len = "г".len();
        let new_len = lexeme.len() - byte_len;
        lexeme.truncate(new_len);
        lexeme.push_str("к");
    }
}

fn try_elision_restore(s: &str) -> Option<String> {
    let mut it = s.chars().rev();
    let last_cp = it.next()?;
    if last_cp != 'н' && last_cp != 'з' {
        return None;
    }
    let prev_cp = it.next()?;

    if is_vowel(prev_cp) && !(s.ends_with("уз") || s.ends_with("із")) {
        return None;
    }

    let lv = s.chars().filter(|&c| is_vowel(c)).last()?;
    let ins = if is_back_vowel(lv) { "ы" } else { "і" };

    let last_char_start = s.len() - last_cp.len_utf8();
    let mut result = String::with_capacity(s.len() + ins.len());
    result.push_str(&s[..last_char_start]);
    result.push_str(ins);
    result.push_str(&s[last_char_start..]);
    if result.len() >= MAX_STEM_BYTES {
        return None;
    }
    Some(result)
}

pub fn apply_elision_restore(lexeme: &str) -> String {
    try_elision_restore(lexeme).unwrap_or_else(|| lexeme.to_string())
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

fn try_append_vowel_check(stem: &str, suffix: &str, lexicon: &Lexicon) -> bool {
    if stem.is_empty() {
        return false;
    }
    let mut buf = [0u8; MAX_STEM_BYTES];
    match concat_on_stack(stem, suffix, &mut buf) {
        Some(trial) => lexicon.contains(trial),
        None => false,
    }
}

pub fn candidate_hits_lexicon(c: &Candidate, word: &str, lexicon: &Lexicon) -> bool {
    if c.len <= 0 || (c.len as usize) >= MAX_STEM_BYTES {
        return false;
    }

    let stem = &word[..c.len as usize];
    if lexicon.contains(stem) {
        return true;
    }

    if c.steps > 0 && c.nominal_inf > 0 {
        if let Some(last_sfx) = c.last_suffix {
            if POSS_VOWEL_SUFFIXES.contains(&last_sfx) {
                let mut alt = stem.to_string();
                apply_mutation(&mut alt);
                if lexicon.contains(&alt) {
                    return true;
                }
                if let Some(restored) = try_elision_restore(&alt) {
                    if lexicon.contains(&restored) {
                        return true;
                    }
                }

                let alt2 = stem.to_string();
                if let Some(restored) = try_elision_restore(&alt2) {
                    if lexicon.contains(&restored) {
                        return true;
                    }
                    let mut restored_mut = restored;
                    apply_mutation(&mut restored_mut);
                    if lexicon.contains(&restored_mut) {
                        return true;
                    }
                }
            }
        }
    }

    if c.steps < 2 {
        return false;
    }
    let last_cp = match utf8_last_cp(stem) {
        Some(cp) => cp,
        None => return false,
    };
    if is_vowel(last_cp) {
        return false;
    }

    let stem_back = word_is_back(stem);
    let v1 = if stem_back { "ы" } else { "і" };
    let v2 = if stem_back { "а" } else { "е" };

    if try_append_vowel_check(stem, v1, lexicon) {
        return true;
    }
    if try_append_vowel_check(stem, v2, lexicon) {
        return true;
    }

    let mut alt = stem.to_string();
    apply_mutation(&mut alt);
    if try_append_vowel_check(&alt, v1, lexicon) {
        return true;
    }
    if try_append_vowel_check(&alt, v2, lexicon) {
        return true;
    }

    false
}

pub fn explore_track_best(
    word: &str,
    len: usize,
    layers: &[LayerDef],
    cfg: &StemConfig,
    noun_track: bool,
    prefix: &PrefixTables,
) -> ExploreResult {
    let nlayer = layers.len() as i32;
    let verb_track = !noun_track;
    let original_chars = prefix.chars[len];

    let mut queue: VecDeque<ExploreState> = VecDeque::with_capacity(1024);
    let mut visit: HashSet<u64> = HashSet::with_capacity(4096);

    let mut best_scored = Candidate {
        len: len as i32,
        penalty_flags: penalty_flags_at(word, len),
        ..Default::default()
    };
    let mut best_pen = candidate_penalty(
        &best_scored, word, original_chars, verb_track,
        prefix, &cfg.weights,
    );

    let mut best_lexhit: Option<Candidate> = None;
    let mut best_lex_pen: f64 = 0.0;

    visit.insert(visit_key(len as i32, 0, 0));
    queue.push_back(ExploreState {
        len: len as i32,
        state_idx: 0,
        c: Candidate {
            len: len as i32,
            penalty_flags: penalty_flags_at(word, len),
            ..Default::default()
        },
    });

    while let Some(st) = queue.pop_front() {
        if queue.len() > QUEUE_MAX {
            break;
        }

        let cur_pen = candidate_penalty(
            &st.c, word, original_chars, verb_track,
            prefix, &cfg.weights,
        );

        if candidate_beats(&st.c, &best_scored, cur_pen, best_pen, prefix) {
            best_scored = st.c;
            best_pen = cur_pen;
        }

        if st.c.steps > 0 {
            if let Some(ref lex) = cfg.lexicon {
                if candidate_hits_lexicon(&st.c, word, lex) {
                    let dominated = best_lexhit
                        .as_ref()
                        .map_or(true, |prev| candidate_beats(&st.c, prev, cur_pen, best_lex_pen, prefix));
                    if dominated {
                        best_lexhit = Some(st.c);
                        best_lex_pen = cur_pen;
                    }
                }
            }
        }

        if st.state_idx >= nlayer || st.c.steps >= cfg.max_steps {
            continue;
        }

        // Option 1: skip current layer
        {
            let next_idx = st.state_idx + 1;
            let key = visit_key(st.len, next_idx, st.c.steps);
            if visit.insert(key) {
                queue.push_back(ExploreState {
                    len: st.len,
                    state_idx: next_idx,
                    c: st.c,
                });
            }
        }

        let layer = &layers[st.state_idx as usize];
        if !cfg.derivation && layer.layer_id == LAYER_DERIV {
            continue;
        }

        // Option 2: strip a matching suffix
        for rule in layer.rules.iter() {
            let sfx_bytes = rule.suffix.len();
            let st_len = st.len as usize;
            if sfx_bytes == 0 || sfx_bytes >= st_len {
                continue;
            }
            if !word[..st_len].ends_with(rule.suffix) {
                continue;
            }
            let base_len = st_len - sfx_bytes;
            if prefix.chars[base_len] < 2 {
                continue;
            }
            if prefix.syll[base_len] < 1 {
                continue;
            }
            if !harmony_ok(&word[..base_len], rule.harmony) {
                continue;
            }
            if !layer_guard(layer.layer_id, rule.suffix, &word[..base_len], st.c.steps) {
                continue;
            }

            let new_state_idx = next_state_idx(noun_track, st.state_idx, layer.layer_id, rule.suffix);

            let mut new_c = st.c;
            new_c.len = base_len as i32;
            new_c.steps += 1;
            new_c.last_suffix = Some(rule.suffix);
            new_c.last_layer = layer.layer_id;
            if rule.weak { new_c.weak += 1; }
            new_c.penalty_flags = penalty_flags_at(word, base_len);
            if rule.sfx_chars == 1 { new_c.single_char += 1; }
            match layer.kind {
                1 => new_c.nominal_inf += 1,
                2 => new_c.verbal_inf += 1,
                _ => new_c.deriv += 1,
            }

            let key = visit_key(base_len as i32, new_state_idx, new_c.steps);
            if visit.insert(key) {
                queue.push_back(ExploreState {
                    len: base_len as i32,
                    state_idx: new_state_idx,
                    c: new_c,
                });
            }
        }
    }

    ExploreResult { best_scored, best_lexhit }
}
