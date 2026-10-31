//! Russian-keyboard restoration: `KeyboardMode::Restore`.
//!
//! People typing Kazakh on a Russian layout fold nine letters onto their
//! Russian neighbours (қ→к ғ→г ң→н ұ/ү→у і→и ә→а ө→о һ→х). Restoration is a
//! wrapper around the unchanged `stem_cyrillic`: when today's stem is not a
//! lexicon entry, propose a few proper-orthography respellings anchored on a
//! lexicon entry, stem each with the real engine, and return the first result
//! the lexicon verifies. Otherwise return today's answer.
//!
//! Generation ([`candidates`]) and policy ([`admissible`]) never mix: every
//! "is this restoration safe?" question lives in `admissible`, and the eval
//! script `eval/measure_keyboard_fold.py` measures its consequences.

use std::collections::HashMap;

use crate::lexicon::{LexStem, Lexicon};
use crate::text::{is_glide, is_loan_vowel, is_vowel, strong_vowel_class};
use crate::{stem_cyrillic, StemConfig, MAX_STEM_BYTES};

/// Restoration hypotheses stemmed per source string. Agreement saturates
/// at 4 (cap 2: 73.3%, cap 4/8/16: 73.5% in candidate 4's frontier).
pub const MAX_RESTORE_CANDIDATES: usize = 4;

/// Worst-case extra `stem_cyrillic` calls per token: the whole-token override
/// path and the two-source restore path are exclusive, so the bound is the
/// restore path alone (`word` then `stem`, each capped).
pub const MAX_EXTRA_STEM_CALLS: usize = 2 * MAX_RESTORE_CANDIDATES;

/// A lexical-only restoration (the dictionary spelling is the only evidence)
/// needs an anchor with this many harmony-bearing syllables. One-syllable
/// roots collide with real Kazakh-letter-free words (мен/мең, сон/соң).
const MIN_LEXICAL_ANCHOR_SYLLABLES: u8 = 2;

/// Anchors shorter than this many chars are never looked up.
const MIN_ANCHOR_CHARS: usize = 3;

/// The nine Kazakh-specific letters and the Russian-layout letter typed for
/// each. Every pair is 2-byte UTF-8 on both sides, so folding preserves byte
/// offsets: `fold(w)[..k]` is the fold of `w[..k]` at every char boundary.
pub const KEYBOARD_FOLD: [(char, char); 9] = [
    ('қ', 'к'),
    ('ғ', 'г'),
    ('ң', 'н'),
    ('ұ', 'у'),
    ('ү', 'у'),
    ('і', 'и'),
    ('ә', 'а'),
    ('ө', 'о'),
    ('һ', 'х'),
];

pub fn fold_char(c: char) -> char {
    match c {
        'қ' => 'к',
        'ғ' => 'г',
        'ң' => 'н',
        'ұ' | 'ү' => 'у',
        'і' => 'и',
        'ә' => 'а',
        'ө' => 'о',
        'һ' => 'х',
        _ => c,
    }
}

pub fn is_kazakh_specific(c: char) -> bool {
    fold_char(c) != c
}

fn is_fold_target(c: char) -> bool {
    matches!(c, 'к' | 'г' | 'н' | 'у' | 'и' | 'а' | 'о' | 'х')
}

pub fn fold(s: &str) -> String {
    s.chars().map(fold_char).collect()
}

/// Text in keyboard-folded space. Only `fold_into` builds one, so
/// `FoldIndex::lookup` cannot be handed unfolded text.
#[derive(Copy, Clone, Debug)]
struct Folded<'a>(&'a str);

impl<'a> Folded<'a> {
    /// Prefix at byte offset `k` of the original word (folding is
    /// byte-length preserving, so `k` is a char boundary here too).
    fn prefix(self, k: usize) -> Folded<'a> {
        Folded(&self.0[..k])
    }
}

fn fold_into<'b>(s: &str, buf: &'b mut [u8; MAX_STEM_BYTES]) -> Option<Folded<'b>> {
    if s.len() >= MAX_STEM_BYTES {
        return None;
    }
    let mut n = 0;
    for c in s.chars() {
        n += fold_char(c).encode_utf8(&mut buf[n..]).len();
    }
    debug_assert_eq!(n, s.len(), "fold must preserve byte length");
    Some(Folded(std::str::from_utf8(&buf[..n]).ok()?))
}

/// Harmony-bearing syllables: vowels minus glides (у/и/ю are transparent to
/// harmony, so `туризм` has none and `кино` has one).
fn harmony_syllables(s: &str) -> u8 {
    s.chars()
        .filter(|&c| (is_vowel(c) || is_loan_vowel(c)) && !is_glide(c))
        .count()
        .min(u8::MAX as usize) as u8
}

/// How a lexicon entry surfaces before a suffix. Only alternations the
/// engine already undoes are indexed, so a candidate built on a surface is
/// reachable by `stem_cyrillic` (`кітап`→`кітаб-ы`, `мұрын`→`мұрн-ы`).
#[derive(Copy, Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum SurfaceKind {
    Citation,
    /// Final п/қ/к voiced to б/ғ/г before a vowel-initial suffix.
    Mutated,
    /// ы/і dropped before a final н/з.
    Elided,
}

fn surfaces(entry: &str) -> Vec<(SurfaceKind, String)> {
    let chars: Vec<char> = entry.chars().collect();
    let mut out = vec![(SurfaceKind::Citation, entry.to_string())];
    if let [.., prev, last] = chars[..] {
        let voiced = match last {
            'п' => Some('б'),
            'қ' => Some('ғ'),
            // apply_mutation refuses г→к after rounded vowels, so that
            // surface would never stem back to the entry.
            'к' if !matches!(prev, 'о' | 'ө' | 'ұ' | 'ү' | 'у') => Some('г'),
            _ => None,
        };
        if let Some(v) = voiced {
            let mut s: String = chars[..chars.len() - 1].iter().collect();
            s.push(v);
            out.push((SurfaceKind::Mutated, s));
        }
    }
    if let [.., _, vowel, last] = chars[..] {
        if matches!(last, 'н' | 'з') && matches!(vowel, 'ы' | 'і') {
            let mut s: String = chars[..chars.len() - 2].iter().collect();
            s.push(last);
            out.push((SurfaceKind::Elided, s));
        }
    }
    out
}

/// A lexicon entry as it may appear at the front of a typed token.
#[derive(Clone, Debug)]
pub(crate) struct Anchor {
    /// Citation form: what a restoration ultimately claims.
    entry: Box<str>,
    /// Proper spelling of the prefix as it appears in the word.
    surface: Box<str>,
    kind: SurfaceKind,
    /// Harmony class the suffix tail must follow. `None` = glide-only
    /// surface, try both.
    back: Option<bool>,
    strong_syllables: u8,
}

impl Anchor {
    /// The candidate-3 `align` rule: a Kazakh letter the user did type is
    /// never overridden, it must equal the anchor's letter at that position.
    fn agrees_with(&self, typed: &str) -> bool {
        typed
            .chars()
            .zip(self.surface.chars())
            .all(|(t, s)| !is_kazakh_specific(t) || t == s)
    }
}

/// fold(surface) → anchors. Derived from the lexicon's entry set, owned by
/// [`Lexicon`], never constructed by callers.
#[derive(Clone, Debug, Default)]
pub struct FoldIndex {
    by_fold: HashMap<Box<str>, Box<[Anchor]>>,
}

impl FoldIndex {
    pub(crate) fn build<'a>(entries: impl Iterator<Item = &'a String>) -> Self {
        let mut buckets: HashMap<Box<str>, Vec<Anchor>> = HashMap::new();
        for entry in entries {
            for (kind, surface) in surfaces(entry) {
                let anchor = Anchor {
                    entry: entry.as_str().into(),
                    back: strong_vowel_class(&surface),
                    strong_syllables: harmony_syllables(entry),
                    kind,
                    surface: surface.as_str().into(),
                };
                buckets.entry(fold(&surface).into()).or_default().push(anchor);
            }
        }
        let by_fold = buckets
            .into_iter()
            .map(|(key, mut anchors)| {
                anchors.sort_by(|a, b| (&a.entry, a.kind).cmp(&(&b.entry, b.kind)));
                (key, anchors.into_boxed_slice())
            })
            .collect();
        Self { by_fold }
    }

    fn lookup(&self, key: Folded<'_>) -> &[Anchor] {
        self.by_fold.get(key.0).map_or(&[], |a| a)
    }

    /// Citation entries whose fold equals the whole token and that agree
    /// with every Kazakh letter the user did type.
    fn whole_token<'s>(
        &'s self,
        word: &'s str,
        folded: Folded<'s>,
    ) -> impl Iterator<Item = &'s Anchor> + 's {
        self.lookup(folded)
            .iter()
            .filter(move |a| a.kind == SurfaceKind::Citation && &*a.entry != word && a.agrees_with(word))
    }
}

/// Why a restored spelling is believed. Computed by [`candidates`], judged
/// by [`admissible`].
#[derive(Copy, Clone, Debug, Default, Eq, PartialEq)]
pub struct Evidence {
    /// The dictionary spells the anchor with Kazakh letters the input lacks
    /// (`оним` vs `өнім`).
    pub lexical: bool,
    /// Harmony forced a suffix letter: back stem + к/г must be қ/ғ, front
    /// stem + non-final и must be і.
    pub forced_tail: bool,
    /// A tail-final н read as ң where only ң-suffixes occur (genitive
    /// -ның/-нің/-дың/-дің/-тың/-тің, possessive -ың/-ің, polite -ңыз/-ңіз).
    pub ng_suffix: bool,
    pub anchor_strong_syllables: u8,
    /// The typed token already contained a Kazakh-specific letter.
    pub input_has_kazakh: bool,
}

/// The whole restoration policy. Each rule is tied to a measured failure
/// class (see `eval/measure_keyboard_fold.py`):
/// * some evidence is required, and ң guesses outside the suffix inventory
///   are never generated (unrestricted ң turned жарияланды into жария);
/// * lexical-only evidence needs a ≥2-syllable anchor (мен→мең, сондай→соң);
/// * a token that already has a Kazakh letter was typed by someone who can
///   type them, so only grammatical tail evidence justifies touching it
///   (өнимдери yes, соның no).
pub fn admissible(ev: &Evidence) -> bool {
    let tail = ev.forced_tail || ev.ng_suffix;
    (ev.lexical || tail)
        && (ev.forced_tail || ev.anchor_strong_syllables >= MIN_LEXICAL_ANCHOR_SYLLABLES)
        && (!ev.input_has_kazakh || tail)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Tail {
    text: String,
    forced: bool,
    ng: bool,
}

/// ң inventory rule (candidate 1): the restored tail may read н as ң only
/// where it ends in `[ыі]ң` or `[ыі]ң(ыз|із)`. Never a bare or internal ң.
fn ng_suffix_variant(tail: &str) -> Option<String> {
    let (core, polite) = match tail.strip_suffix("ыз").or_else(|| tail.strip_suffix("із")) {
        Some(core) => (core, &tail[core.len()..]),
        None => (tail, ""),
    };
    let base = core.strip_suffix("ын").or_else(|| core.strip_suffix("ін"))?;
    let vowel = &core[base.len()..base.len() + 'ы'.len_utf8()];
    Some(format!("{base}{vowel}ң{polite}"))
}

/// Restore the suffix tail under the anchor's harmony class. A tail that
/// contradicts the class yields nothing: the engine would reject it anyway,
/// this only saves `stem_cyrillic` calls. Fewest guesses first.
fn restore_tail(tail: &str, back: bool, out: &mut Vec<Tail>) {
    out.clear();
    // A bare word-final -и is the Arabic/Persian adjectival suffix (әскери,
    // діни, ресми), typed correctly, not a folded -і.
    let bare_final_i = tail == "и";
    let text: String = tail
        .chars()
        .map(|c| match c {
            'к' if back => 'қ',
            'г' if back => 'ғ',
            'и' if !back && !bare_final_i => 'і',
            _ => c,
        })
        .collect();
    let contradicts = if back {
        text.chars().any(|c| matches!(c, 'і' | 'ә' | 'ө' | 'ү'))
    } else {
        text.chars().any(|c| matches!(c, 'а' | 'ы'))
    };
    if contradicts {
        return;
    }
    let forced = text != tail;
    let ng = ng_suffix_variant(&text);
    out.push(Tail { text, forced, ng: false });
    if let Some(text) = ng {
        out.push(Tail { text, forced, ng: true });
    }
}

#[derive(Clone, Debug)]
pub(crate) struct Candidate {
    /// Proper-orthography spelling of the whole token.
    text: String,
    evidence: Evidence,
}

/// Bounded, deterministic restoration hypotheses for `word`, longest anchor
/// first. Never yields `word` itself. A pure function of (word, index).
pub(crate) fn candidates(word: &str, index: &FoldIndex, out: &mut Vec<Candidate>) {
    out.clear();
    if !word.chars().any(is_fold_target) {
        return;
    }
    let mut buf = [0u8; MAX_STEM_BYTES];
    let folded = match fold_into(word, &mut buf) {
        Some(f) => f,
        None => return,
    };
    let input_has_kazakh = word.chars().any(is_kazakh_specific);
    let boundaries: Vec<usize> = word
        .char_indices()
        .map(|(i, _)| i)
        .skip(MIN_ANCHOR_CHARS)
        .chain(std::iter::once(word.len()))
        .collect();
    let mut tails = Vec::with_capacity(2);
    for &k in boundaries.iter().rev() {
        let typed = &word[..k];
        for anchor in index.lookup(folded.prefix(k)) {
            if !anchor.agrees_with(typed) {
                continue;
            }
            let lexical = &*anchor.surface != typed;
            let classes: &[bool] = match anchor.back {
                Some(true) => &[true],
                Some(false) => &[false],
                None => &[true, false],
            };
            for &back in classes {
                restore_tail(&word[k..], back, &mut tails);
                for tail in &tails {
                    let evidence = Evidence {
                        lexical,
                        forced_tail: tail.forced,
                        ng_suffix: tail.ng,
                        anchor_strong_syllables: anchor.strong_syllables,
                        input_has_kazakh,
                    };
                    if !admissible(&evidence) {
                        continue;
                    }
                    let text = format!("{}{}", anchor.surface, tail.text);
                    if text == word || out.iter().any(|c| c.text == text) {
                        continue;
                    }
                    out.push(Candidate { text, evidence });
                    if out.len() >= MAX_RESTORE_CANDIDATES {
                        return;
                    }
                }
            }
        }
    }
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Source {
    /// Respelling of the typed token.
    Word,
    /// Respelling of today's stem of the token.
    Stem,
    /// A dictionary word whose fold is the whole token.
    WholeToken,
}

/// One `stem_cyrillic` call spent on a restoration hypothesis.
#[derive(Clone, Debug)]
pub struct Attempt {
    pub source: Source,
    pub candidate: String,
    pub evidence: Evidence,
    pub stem: String,
    pub accepted: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Outcome {
    /// Today's stem is a lexicon entry; restoration never ran.
    Gated,
    /// A dictionary word beat a dictionary stem reached by stripping a
    /// folded string (енбек→ен became еңбек).
    Overridden(LexStem),
    Restored { source: Source, stem: LexStem },
    /// No hypothesis verified; today's stem stands.
    Fallback,
}

/// Why a token was or was not restored. `extra_calls()` is the number of
/// `stem_cyrillic` calls beyond the one Exact mode makes.
#[derive(Clone, Debug)]
pub struct Trace {
    /// Today's stem, `stem_cyrillic(word)`.
    pub exact: String,
    pub outcome: Outcome,
    pub attempts: Vec<Attempt>,
}

impl Trace {
    pub fn output(&self) -> &str {
        match &self.outcome {
            Outcome::Gated | Outcome::Fallback => &self.exact,
            Outcome::Overridden(s) | Outcome::Restored { stem: s, .. } => s.as_str(),
        }
    }

    pub fn extra_calls(&self) -> usize {
        self.attempts.len()
    }
}

fn try_whole_token(
    word: &str,
    cfg: &StemConfig,
    lex: &Lexicon,
    index: &FoldIndex,
    attempts: &mut Vec<Attempt>,
) -> Option<LexStem> {
    let mut buf = [0u8; MAX_STEM_BYTES];
    let folded = fold_into(word, &mut buf)?;
    let input_has_kazakh = word.chars().any(is_kazakh_specific);
    let admitted = index.whole_token(word, folded).filter(|a| {
        admissible(&Evidence {
            lexical: true,
            anchor_strong_syllables: a.strong_syllables,
            input_has_kazakh,
            ..Evidence::default()
        })
    });
    for anchor in admitted.take(MAX_RESTORE_CANDIDATES) {
        let stem = stem_cyrillic(&anchor.entry, cfg).stem;
        let verified = lex.verify(&stem);
        attempts.push(Attempt {
            source: Source::WholeToken,
            candidate: anchor.entry.to_string(),
            evidence: Evidence {
                lexical: true,
                anchor_strong_syllables: anchor.strong_syllables,
                input_has_kazakh,
                ..Evidence::default()
            },
            stem,
            accepted: verified.is_some(),
        });
        if verified.is_some() {
            return verified;
        }
    }
    None
}

/// Restoration-aware stemming, with the reasoning kept for `analyze`.
///
/// Let SC = `stem_cyrillic` (idempotent), `t = SC(word)`.
/// 1. Override: `word ∉ lex`, `t ≠ word`, `t ∈ lex`, and some admissible
///    whole-token anchor `e` has `SC(e) ∈ lex` → SC(e).
/// 2. Gate: `t ∈ lex` → t. Most proper tokens stop here at zero extra cost.
/// 3. Restore: for src in [word, t] (t only if t ≠ word), for each candidate
///    c of src: `SC(c) ∈ lex` → SC(c). `word` first keeps the tail's harmony
///    evidence; `t` second is what idempotence needs.
/// 4. Fallback → t.
///
/// Idempotence: an output from 1 or 3 is a `LexStem` s = SC(x), so SC(s) = s
/// and step 2 returns s on re-entry. An output from 2 is in the lexicon,
/// same argument. An output t from 4 re-enters with SC(t) = t, fails the
/// gate, tries only `candidates(t)` (the same pure call that already failed)
/// and falls back to t again.
pub fn explain(word: &str, cfg: &StemConfig, lex: &Lexicon) -> Trace {
    let exact = stem_cyrillic(word, cfg).stem;
    let mut attempts = Vec::new();
    let index = lex.fold_index();

    if exact != word && !lex.contains(word) && lex.contains(&exact) {
        if let Some(stem) = try_whole_token(word, cfg, lex, index, &mut attempts) {
            return Trace { exact, outcome: Outcome::Overridden(stem), attempts };
        }
    }
    if lex.contains(&exact) {
        return Trace { exact, outcome: Outcome::Gated, attempts };
    }

    let mut restored = None;
    let mut cands = Vec::with_capacity(MAX_RESTORE_CANDIDATES);
    let sources = [(Source::Word, word), (Source::Stem, exact.as_str())];
    'sources: for (source, src) in sources {
        if source == Source::Stem && src == word {
            break;
        }
        candidates(src, index, &mut cands);
        for c in cands.drain(..) {
            let stem = stem_cyrillic(&c.text, cfg).stem;
            let verified = lex.verify(&stem);
            attempts.push(Attempt {
                source,
                candidate: c.text,
                evidence: c.evidence,
                stem,
                accepted: verified.is_some(),
            });
            if let Some(stem) = verified {
                restored = Some(Outcome::Restored { source, stem });
                break 'sources;
            }
        }
    }
    Trace { exact, outcome: restored.unwrap_or(Outcome::Fallback), attempts }
}

pub(crate) fn resolve(word: &str, cfg: &StemConfig, lex: &Lexicon) -> String {
    let trace = explain(word, cfg, lex);
    match trace.outcome {
        Outcome::Gated | Outcome::Fallback => trace.exact,
        Outcome::Overridden(s) | Outcome::Restored { stem: s, .. } => s.into_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fold_pairs_preserve_byte_length() {
        for (kazakh, russian) in KEYBOARD_FOLD {
            assert_eq!(kazakh.len_utf8(), russian.len_utf8());
            assert_eq!(fold_char(kazakh), russian);
            assert!(is_kazakh_specific(kazakh));
            assert!(!is_kazakh_specific(russian));
        }
    }

    #[test]
    fn fold_into_matches_fold() {
        let mut buf = [0u8; MAX_STEM_BYTES];
        let word = "шаруашылығы";
        let folded = fold_into(word, &mut buf).unwrap();
        assert_eq!(folded.0, fold(word));
        let k = word.char_indices().nth(4).unwrap().0;
        assert_eq!(folded.prefix(k).0, fold(&word[..k]));
    }

    #[test]
    fn ng_only_in_suffix_inventory() {
        assert_eq!(ng_suffix_variant("сынын").as_deref(), Some("сының"));
        assert_eq!(ng_suffix_variant("нин").as_deref(), None);
        assert_eq!(ng_suffix_variant("нін").as_deref(), Some("нің"));
        assert_eq!(ng_suffix_variant("ыныз").as_deref(), Some("ыңыз"));
        assert_eq!(ng_suffix_variant("ініз").as_deref(), Some("іңіз"));
        assert_eq!(ng_suffix_variant("дай").as_deref(), None);
        assert_eq!(ng_suffix_variant("ланды").as_deref(), None);
        assert_eq!(ng_suffix_variant("н").as_deref(), None);
        assert_eq!(ng_suffix_variant("").as_deref(), None);
    }

    #[test]
    fn tail_is_forced_by_harmony() {
        let mut out = Vec::new();
        restore_tail("ка", true, &mut out);
        assert_eq!(out[0], Tail { text: "қа".into(), forced: true, ng: false });
        restore_tail("дери", false, &mut out);
        assert_eq!(out[0], Tail { text: "дері".into(), forced: true, ng: false });
        restore_tail("и", false, &mut out);
        assert_eq!(out[0], Tail { text: "и".into(), forced: false, ng: false });
        restore_tail("дірі", true, &mut out);
        assert!(out.is_empty(), "front tail under a back anchor is dropped");
        restore_tail("дары", false, &mut out);
        assert!(out.is_empty(), "back tail under a front anchor is dropped");
        restore_tail("сынын", true, &mut out);
        assert_eq!(out.len(), 2);
        assert_eq!(out[1], Tail { text: "сының".into(), forced: false, ng: true });
    }

    #[test]
    fn policy_table() {
        let lexical_two = Evidence { lexical: true, anchor_strong_syllables: 2, ..Default::default() };
        assert!(admissible(&lexical_two));
        assert!(!admissible(&Evidence { anchor_strong_syllables: 1, ..lexical_two }));
        assert!(!admissible(&Evidence { input_has_kazakh: true, ..lexical_two }));
        assert!(admissible(&Evidence { forced_tail: true, anchor_strong_syllables: 1, ..Default::default() }));
        assert!(!admissible(&Evidence { ng_suffix: true, anchor_strong_syllables: 1, ..Default::default() }));
        assert!(admissible(&Evidence { ng_suffix: true, anchor_strong_syllables: 2, ..Default::default() }));
        assert!(!admissible(&Evidence::default()));
    }

    #[test]
    fn surfaces_follow_engine_alternations() {
        let kinds = |e: &str| surfaces(e).into_iter().map(|(_, s)| s).collect::<Vec<_>>();
        assert_eq!(kinds("шаруашылық"), vec!["шаруашылық", "шаруашылығ"]);
        assert_eq!(kinds("мұрын"), vec!["мұрын", "мұрн"]);
        assert_eq!(kinds("кітап"), vec!["кітап", "кітаб"]);
        assert_eq!(kinds("көк"), vec!["көк"]);
    }

    fn candidate_texts(word: &str, entries: &[&str]) -> Vec<String> {
        let entries: Vec<String> = entries.iter().map(|e| e.to_string()).collect();
        let index = FoldIndex::build(entries.iter());
        let mut out = Vec::new();
        candidates(word, &index, &mut out);
        out.into_iter().map(|c| c.text).collect()
    }

    #[test]
    fn no_candidate_joins_a_vowel_final_anchor_to_a_vowel_initial_tail() {
        assert!(candidate_texts("более", &["бөле"]).is_empty());
        assert_eq!(candidate_texts("болен", &["бөле"]), vec!["бөлен"]);
    }

    #[test]
    fn glides_are_not_vowels_for_the_hiatus_rule() {
        assert_eq!(candidate_texts("коргауы", &["қорға"]), vec!["қорғауы"]);
        assert_eq!(candidate_texts("карауы", &["қарау"]), vec!["қарауы"]);
    }
}
