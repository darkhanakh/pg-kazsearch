use std::collections::HashSet;
use std::fs::File;
use std::io::{self, BufRead, BufReader};
use std::path::Path;
use std::sync::OnceLock;

use crate::kbfold::FoldIndex;
use crate::MAX_STEM_BYTES;

#[derive(Clone, Debug, Default)]
pub struct Lexicon {
    entries: HashSet<String>,
    /// Verb lemmas from the optional `<dict>.verbs` sibling file. Used to
    /// gate verb-root reductions (-у/-ю, -ған participles, -п converbs) so
    /// they never land on noun homographs. Empty when the sibling is absent.
    verbs: HashSet<String>,
    /// Keyboard-fold index, derived from `entries` on first use and dropped
    /// by `insert`/`insert_verb`, so it can never disagree with the entry
    /// set. `OnceLock` keeps `Lexicon: Sync` for the Elasticsearch
    /// `Arc<StemConfig>` shared across analysis threads.
    fold: OnceLock<FoldIndex>,
}

/// Proof that a string is a lexicon entry. Only [`Lexicon::verify`] builds
/// one, so keyboard restoration cannot return a stem that was not checked
/// against the dictionary, which is the invariant its idempotence argument
/// rests on.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LexStem(String);

impl LexStem {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn into_string(self) -> String {
        self.0
    }
}

fn read_entries<P: AsRef<Path>>(path: P) -> io::Result<HashSet<String>> {
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mut entries = HashSet::new();

    for line in reader.lines() {
        let line = line?;
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if trimmed.len() >= MAX_STEM_BYTES {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("lexicon entry too long: \"{}\"", trimmed),
            ));
        }
        entries.insert(trimmed.to_string());
    }

    Ok(entries)
}

impl Lexicon {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn load<P: AsRef<Path>>(path: P) -> io::Result<Self> {
        let path = path.as_ref();
        let entries = read_entries(path)?;

        // Sibling-file convention: `kaz_stems.dict.verbs` next to the main
        // dict, produced by scripts/build_lexicon.py. Loaded automatically so
        // no consumer (pg_ext, ES plugin, CLI) needs a new config option.
        let mut verbs_name = path.file_name().unwrap_or_default().to_os_string();
        verbs_name.push(".verbs");
        let verbs_path = path.with_file_name(verbs_name);
        let verbs = if verbs_path.is_file() {
            read_entries(&verbs_path)?
        } else {
            HashSet::new()
        };

        Ok(Self { entries, verbs, fold: OnceLock::new() })
    }

    pub fn contains(&self, word: &str) -> bool {
        self.entries.contains(word)
    }

    pub fn verify(&self, word: &str) -> Option<LexStem> {
        self.contains(word).then(|| LexStem(word.to_owned()))
    }

    pub fn fold_index(&self) -> &FoldIndex {
        self.fold.get_or_init(|| FoldIndex::build(self.entries.iter()))
    }

    /// True when `word` is a known verb root. Falls back to plain dictionary
    /// membership when no verb set was loaded, preserving the pre-sibling
    /// behavior of verb-root reductions.
    pub fn is_verb_root(&self, word: &str) -> bool {
        if self.verbs.is_empty() {
            self.entries.contains(word)
        } else {
            self.verbs.contains(word)
        }
    }

    pub fn has_verb_set(&self) -> bool {
        !self.verbs.is_empty()
    }

    pub fn insert(&mut self, word: String) {
        self.entries.insert(word);
        self.fold = OnceLock::new();
    }

    /// Insert a verb lemma (also added to the general entry set, mirroring
    /// the builder, which writes verbs into both files).
    pub fn insert_verb(&mut self, word: String) {
        self.verbs.insert(word.clone());
        self.entries.insert(word);
        self.fold = OnceLock::new();
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}
