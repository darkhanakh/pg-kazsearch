pub fn is_back_vowel(cp: char) -> bool {
    matches!(cp, 'а' | 'о' | 'ұ' | 'ы' | 'у')
}

pub fn is_front_vowel(cp: char) -> bool {
    matches!(cp, 'ә' | 'е' | 'ө' | 'ү' | 'і' | 'и' | 'ё')
}

pub fn is_vowel(cp: char) -> bool {
    is_back_vowel(cp) || is_front_vowel(cp)
}

pub fn is_glide(cp: char) -> bool {
    matches!(cp, 'у' | 'и' | 'ю')
}

fn is_loan_vowel(cp: char) -> bool {
    matches!(cp, 'я' | 'э')
}

pub fn utf8_last_cp(s: &str) -> Option<char> {
    s.chars().last()
}

pub fn utf8_char_count(s: &str) -> i32 {
    s.chars().count() as i32
}

pub fn count_syllables(s: &str) -> i32 {
    s.chars()
        .filter(|&c| is_vowel(c) || is_loan_vowel(c))
        .count() as i32
}

/// Build prefix tables: chars_prefix[b] and syll_prefix[b] give counts in s[0..b).
/// Valid for every byte offset b that is a UTF-8 boundary.
pub fn fill_prefix_tables(s: &str) -> (Vec<i32>, Vec<i32>) {
    let len = s.len();
    let mut chars_prefix = vec![0i32; len + 1];
    let mut syll_prefix = vec![0i32; len + 1];

    let mut nchars: i32 = 0;
    let mut nsyll: i32 = 0;

    for (i, cp) in s.char_indices() {
        let char_len = cp.len_utf8();
        nchars += 1;
        if is_vowel(cp) || is_loan_vowel(cp) {
            nsyll += 1;
        }
        let end = i + char_len;
        for b in (i + 1)..=end.min(len) {
            chars_prefix[b] = nchars;
            syll_prefix[b] = nsyll;
        }
    }
    // Fill any trailing bytes beyond the last character
    for b in (s.len().saturating_sub(0) + 1)..=len {
        chars_prefix[b] = nchars;
        syll_prefix[b] = nsyll;
    }

    (chars_prefix, syll_prefix)
}

pub fn word_is_back(s: &str) -> bool {
    let mut found = false;
    let mut back = true;
    for cp in s.chars() {
        if is_glide(cp) {
            continue;
        }
        if is_back_vowel(cp) {
            found = true;
            back = true;
        } else if is_front_vowel(cp) {
            found = true;
            back = false;
        }
    }
    if found { back } else { true }
}

fn tail_is_back(s: &str) -> bool {
    let mut last_two = ['\0', '\0'];
    let mut n = 0;

    for cp in s.chars() {
        if is_glide(cp) {
            continue;
        }
        if is_back_vowel(cp) || is_front_vowel(cp) || is_loan_vowel(cp) {
            last_two[0] = last_two[1];
            last_two[1] = cp;
            n += 1;
        }
    }
    if n == 0 {
        return true;
    }
    if is_loan_vowel(last_two[1]) {
        return if last_two[0] != '\0' {
            is_back_vowel(last_two[0])
        } else {
            true
        };
    }
    is_back_vowel(last_two[1])
}

pub fn harmony_ok(s: &str, harmony: u8) -> bool {
    if harmony == 0 {
        // KAZ_HARM_ANY
        return true;
    }
    if s.is_empty() {
        return false;
    }

    let full_back = word_is_back(s);
    if harmony == 1 && full_back {
        // KAZ_HARM_BACK
        return true;
    }
    if harmony == 2 && !full_back {
        // KAZ_HARM_FRONT
        return true;
    }

    if count_syllables(s) >= 4 {
        let tb = tail_is_back(s);
        if harmony == 1 {
            return tb;
        }
        return !tb;
    }

    false
}

pub fn ends_with_suffix<'a>(s: &'a str, suffix: &str) -> Option<&'a str> {
    if suffix.is_empty() || suffix.len() >= s.len() {
        return None;
    }
    if s.as_bytes().ends_with(suffix.as_bytes()) {
        Some(&s[..s.len() - suffix.len()])
    } else {
        None
    }
}

pub fn ends_with_any(s: &str, suffixes: &[&str]) -> bool {
    suffixes.iter().any(|sfx| ends_with_suffix(s, sfx).is_some())
}

pub fn suffix_in(sfx: &str, arr: &[&str]) -> bool {
    arr.contains(&sfx)
}
