use std::collections::HashSet;

use unicode_normalization::UnicodeNormalization;

const MAX_LATIN_CANDIDATES: usize = 32;

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum ScriptClass {
    Cyrillic,
    Latin,
    Mixed,
    Unsupported,
}

#[derive(Clone, Debug)]
pub struct LatinAnalysis {
    pub candidates: Vec<String>,
    pub has_diacritic: bool,
    pub has_q_or_w: bool,
}

#[derive(Clone, Debug)]
pub struct InputAnalysis {
    pub lowered: String,
    pub class: ScriptClass,
    pub latin: Option<LatinAnalysis>,
}

pub fn lower_kazakh(word: &str) -> String {
    let mut lowered = String::with_capacity(word.len());
    for ch in word.chars() {
        match ch {
            'I' => lowered.push('ı'),
            'İ' => lowered.push('i'),
            _ => lowered.extend(ch.to_lowercase()),
        }
    }
    lowered.nfc().collect()
}

pub fn analyze_input(word: &str) -> InputAnalysis {
    let lowered = lower_kazakh(word);
    let class = classify_script(&lowered);
    let latin = if class == ScriptClass::Latin {
        transliterate_latin(&lowered)
    } else {
        None
    };
    InputAnalysis { lowered, class, latin }
}

fn classify_script(s: &str) -> ScriptClass {
    let mut has_cyr = false;
    let mut has_lat = false;

    for ch in s.chars() {
        if ch.is_alphabetic() {
            if is_cyrillic_letter(ch) {
                has_cyr = true;
            } else if is_latin_letter(ch) {
                has_lat = true;
            } else {
                return ScriptClass::Unsupported;
            }
        } else {
            return ScriptClass::Unsupported;
        }
    }

    match (has_cyr, has_lat) {
        (true, true) => ScriptClass::Mixed,
        (true, false) => ScriptClass::Cyrillic,
        (false, true) => ScriptClass::Latin,
        (false, false) => ScriptClass::Unsupported,
    }
}

fn transliterate_latin(s: &str) -> Option<LatinAnalysis> {
    let mut candidates: Vec<String> = vec![String::new()];
    let mut has_diacritic = false;
    let mut has_q_or_w = false;

    for ch in s.chars() {
        if is_diacritic_marker(ch) {
            has_diacritic = true;
        }
        if ch == 'q' || ch == 'w' {
            has_q_or_w = true;
        }

        let options = latin_char_options(ch)?;
        let mut next: Vec<String> = Vec::with_capacity(candidates.len() * options.len());
        for base in &candidates {
            for mapped in options {
                if next.len() >= MAX_LATIN_CANDIDATES {
                    return None;
                }
                let mut value = String::with_capacity(base.len() + mapped.len());
                value.push_str(base);
                value.push_str(mapped);
                next.push(value);
            }
        }
        candidates = next;
    }

    if candidates.is_empty() {
        return None;
    }

    let mut seen: HashSet<String> = HashSet::with_capacity(candidates.len());
    candidates.retain(|item| seen.insert(item.clone()));

    Some(LatinAnalysis {
        candidates,
        has_diacritic,
        has_q_or_w,
    })
}

fn latin_char_options(ch: char) -> Option<&'static [&'static str]> {
    match ch {
        'a' => Some(&["а"]),
        'ä' => Some(&["ә"]),
        'b' => Some(&["б"]),
        'd' => Some(&["д"]),
        'e' => Some(&["е"]),
        'f' => Some(&["ф"]),
        'g' => Some(&["г"]),
        'ğ' => Some(&["ғ"]),
        'h' => Some(&["х", "һ"]),
        'ı' => Some(&["і"]),
        'i' => Some(&["и", "й"]),
        'j' => Some(&["ж"]),
        'k' => Some(&["к"]),
        'l' => Some(&["л"]),
        'm' => Some(&["м"]),
        'n' => Some(&["н"]),
        'ñ' => Some(&["ң"]),
        'o' => Some(&["о"]),
        'ö' => Some(&["ө"]),
        'p' => Some(&["п"]),
        'q' => Some(&["қ"]),
        'r' => Some(&["р"]),
        's' => Some(&["с"]),
        'ş' => Some(&["ш"]),
        't' => Some(&["т"]),
        'u' => Some(&["у"]),
        'ū' => Some(&["ұ"]),
        'ü' => Some(&["ү"]),
        'v' => Some(&["в"]),
        'w' => Some(&["у"]),
        'y' => Some(&["ы"]),
        'z' => Some(&["з"]),
        _ => None,
    }
}

fn is_cyrillic_letter(ch: char) -> bool {
    ('\u{0400}'..='\u{04FF}').contains(&ch) || ('\u{0500}'..='\u{052F}').contains(&ch)
}

fn is_latin_letter(ch: char) -> bool {
    ch.is_ascii_alphabetic()
        || matches!(ch, 'ä' | 'ö' | 'ü' | 'ū' | 'ğ' | 'ş' | 'ñ' | 'ı')
}

fn is_diacritic_marker(ch: char) -> bool {
    matches!(ch, 'ä' | 'ö' | 'ü' | 'ū' | 'ğ' | 'ş' | 'ñ' | 'ı')
}
