pub fn is_back_vowel(cp: char) -> bool {
    matches!(cp, 'а' | 'о' | 'ұ' | 'ы' | 'у')
}

pub fn is_front_vowel(cp: char) -> bool {
    matches!(cp, 'ә' | 'е' | 'ө' | 'ү' | 'і' | 'и' | 'ё')
}

pub fn is_vowel(cp: char) -> bool {
    is_back_vowel(cp) || is_front_vowel(cp)
}

/// Vowel including loan vowels (я/э), for guards that care about whether a
/// stem ends vocalically rather than about native harmony class.
pub fn is_vocalic(cp: char) -> bool {
    is_vowel(cp) || is_loan_vowel(cp)
}

pub fn is_glide(cp: char) -> bool {
    matches!(cp, 'у' | 'и' | 'ю')
}

pub fn is_loan_vowel(cp: char) -> bool {
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

/// Table size: stem() never explores words of `MAX_STEM_BYTES` (128) bytes
/// or longer, so fixed stack arrays avoid four heap allocations per word.
const TABLE_LEN: usize = crate::MAX_STEM_BYTES + 1;

/// Prefix sums indexed by UTF-8 byte offset `b`: `chars[b]` / `syll[b]` count
/// Unicode scalars and vowel-based syllables in `s[0..b)`. `harm_back[b]` and
/// `tail_back[b]` precompute [`word_is_back`] / `tail_is_back` for `s[0..b)`
/// so harmony checks during BFS are O(1) instead of prefix rescans.
#[derive(Clone, Debug)]
pub struct PrefixTables {
    pub chars: [i32; TABLE_LEN],
    pub syll: [i32; TABLE_LEN],
    harm_back: [bool; TABLE_LEN],
    tail_back: [bool; TABLE_LEN],
    /// Whether the prefix contains any harmony-bearing (non-glide) vowel.
    /// Glides (у/и/ю) are transparent, so loanwords like `туризм` carry no
    /// harmony class at all and must accept suffixes of either class.
    has_strong: [bool; TABLE_LEN],
}

/// Build prefix tables for [`PrefixTables`]. `s` must be shorter than
/// [`crate::MAX_STEM_BYTES`] (the caller guards this).
pub fn fill_prefix_tables(s: &str) -> PrefixTables {
    let len = s.len();
    assert!(len < TABLE_LEN, "fill_prefix_tables: input too long");
    let mut chars = [0i32; TABLE_LEN];
    let mut syll = [0i32; TABLE_LEN];
    let mut harm_back = [true; TABLE_LEN];
    let mut tail_back = [true; TABLE_LEN];
    let mut has_strong = [false; TABLE_LEN];

    let mut nchars: i32 = 0;
    let mut nsyll: i32 = 0;

    // Incremental state mirroring word_is_back / tail_is_back.
    let mut wb_back = true; // word_is_back: class of last harmony-bearing vowel
    let mut strong_seen = false; // any non-glide harmony-bearing vowel so far
    let mut last_two = ['\0', '\0']; // tail_is_back: last two non-glide vowels

    for (i, cp) in s.char_indices() {
        let char_len = cp.len_utf8();
        nchars += 1;
        if is_vowel(cp) || is_loan_vowel(cp) {
            nsyll += 1;
        }

        if !is_glide(cp) {
            if is_back_vowel(cp) || cp == 'я' {
                wb_back = true;
                strong_seen = true;
            } else if is_front_vowel(cp) || cp == 'э' {
                wb_back = false;
                strong_seen = true;
            }
            if is_back_vowel(cp) || is_front_vowel(cp) || is_loan_vowel(cp) {
                last_two[0] = last_two[1];
                last_two[1] = cp;
            }
        }

        let tb = if last_two[1] == '\0' {
            true
        } else if is_loan_vowel(last_two[1]) {
            if last_two[0] != '\0' { is_back_vowel(last_two[0]) } else { true }
        } else {
            is_back_vowel(last_two[1])
        };

        let end = i + char_len;
        for b in (i + 1)..=end.min(len) {
            chars[b] = nchars;
            syll[b] = nsyll;
            harm_back[b] = wb_back;
            tail_back[b] = tb;
            has_strong[b] = strong_seen;
        }
    }

    PrefixTables { chars, syll, harm_back, tail_back, has_strong }
}

impl PrefixTables {
    /// O(1) equivalent of `harmony_ok(&s[..b], harmony)`.
    pub fn harmony_ok_at(&self, b: usize, harmony: u8) -> bool {
        if harmony == HARM_ANY_CLASS {
            return true;
        }
        if b == 0 {
            return false;
        }
        // Harmony-neutral prefix (glide-only vowels, e.g. туризм): accept
        // suffixes of either class, otherwise no FRONT/BACK-classed case
        // ending can ever attach and the word is unstemmable.
        if !self.has_strong[b] {
            return true;
        }
        let full_back = self.harm_back[b];
        if harmony == 1 && full_back {
            return true;
        }
        if harmony == 2 && !full_back {
            return true;
        }
        if self.syll[b] >= 4 {
            let tb = self.tail_back[b];
            return if harmony == 1 { tb } else { !tb };
        }
        false
    }
}

const HARM_ANY_CLASS: u8 = 0;

/// Harmony class of the last harmony-bearing vowel: `Some(true)` = back,
/// `Some(false)` = front, `None` = no strong vowel at all (glide-only
/// loanwords like `туризм` are harmony-neutral).
pub fn strong_vowel_class(s: &str) -> Option<bool> {
    let mut class: Option<bool> = None;
    for cp in s.chars() {
        if is_glide(cp) {
            continue;
        }
        // Loan vowels take a harmony class instead of being invisible:
        // я = /ja/ patterns back (идеяға), э patterns front. Without this,
        // я/э-final loanwords fail every harmony check until the 4-syllable
        // tail fallback kicks in.
        if is_back_vowel(cp) || cp == 'я' {
            class = Some(true);
        } else if is_front_vowel(cp) || cp == 'э' {
            class = Some(false);
        }
    }
    class
}

pub fn word_is_back(s: &str) -> bool {
    strong_vowel_class(s).unwrap_or(true)
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

    // Harmony-neutral word (glide-only vowels): either class attaches.
    let full_back = match strong_vowel_class(s) {
        Some(back) => back,
        None => return true,
    };
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
