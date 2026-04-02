use std::collections::HashSet;
use std::fs::File;
use std::io::{self, BufRead, BufReader};
use std::path::Path;

use crate::MAX_STEM_BYTES;

#[derive(Clone, Debug, Default)]
pub struct Lexicon {
    entries: HashSet<String>,
}

impl Lexicon {
    pub fn new() -> Self {
        Self { entries: HashSet::new() }
    }

    pub fn load<P: AsRef<Path>>(path: P) -> io::Result<Self> {
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

        Ok(Self { entries })
    }

    pub fn contains(&self, word: &str) -> bool {
        self.entries.contains(word)
    }

    pub fn insert(&mut self, word: String) {
        self.entries.insert(word);
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}
