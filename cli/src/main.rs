use std::io::{self, BufRead, Write as _};
use std::path::PathBuf;
use std::time::Instant;

use clap::{Parser, Subcommand};
use kazsearch_core::lexicon::Lexicon;
use kazsearch_core::{ScriptMode, StemConfig, stem};

#[derive(Parser)]
#[command(name = "kazsearch", about = "Kazakh stemmer CLI")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Stem one or more Kazakh words
    Stem {
        /// Words to stem (omit to read from stdin)
        words: Vec<String>,

        /// Read words from stdin, one per line
        #[arg(long)]
        stdin: bool,

        /// Path to lexicon dictionary file
        #[arg(short, long)]
        lexicon: Option<PathBuf>,

        /// Disable Latin auto-detection and stem Cyrillic only
        #[arg(long)]
        cyrillic_only: bool,
    },

    /// Show morphological analysis of a word
    Analyze {
        /// Word to analyze
        word: String,

        /// Path to lexicon dictionary file
        #[arg(short, long)]
        lexicon: Option<PathBuf>,

        /// Disable Latin auto-detection and stem Cyrillic only
        #[arg(long)]
        cyrillic_only: bool,
    },

    /// Benchmark stemming throughput
    Bench {
        /// File with words to stem (one per line); defaults to stdin
        file: Option<PathBuf>,

        /// Path to lexicon dictionary file
        #[arg(short, long)]
        lexicon: Option<PathBuf>,

        /// Disable Latin auto-detection and stem Cyrillic only
        #[arg(long)]
        cyrillic_only: bool,
    },

    /// Lexicon utilities
    Lexicon {
        #[command(subcommand)]
        action: LexiconAction,
    },
}

#[derive(Subcommand)]
enum LexiconAction {
    /// Validate a lexicon dictionary file and print stats
    Validate {
        /// Path to the dictionary file
        file: PathBuf,
    },
}

fn build_config(lexicon_path: Option<&PathBuf>, cyrillic_only: bool) -> StemConfig {
    let mut cfg = StemConfig::default();
    if cyrillic_only {
        cfg.script_mode = ScriptMode::CyrillicOnly;
    }
    if let Some(path) = lexicon_path {
        match Lexicon::load(path) {
            Ok(lex) => cfg.lexicon = Some(lex),
            Err(e) => {
                eprintln!("warning: could not load lexicon {:?}: {}", path, e);
            }
        }
    }
    cfg
}

fn stem_word(word: &str, cfg: &StemConfig) {
    let result = stem(word, cfg);
    println!("{}\t{}", word, result);
}

fn cmd_stem(words: Vec<String>, use_stdin: bool, lexicon: Option<PathBuf>, cyrillic_only: bool) {
    let cfg = build_config(lexicon.as_ref(), cyrillic_only);

    if use_stdin || words.is_empty() {
        let stdin = io::stdin();
        let stdout = io::stdout();
        let mut out = io::BufWriter::new(stdout.lock());
        for line in stdin.lock().lines() {
            let line = match line {
                Ok(l) => l,
                Err(_) => break,
            };
            let word = line.trim();
            if word.is_empty() {
                continue;
            }
            let result = stem(word, &cfg);
            let _ = writeln!(out, "{}\t{}", word, result);
        }
    } else {
        for word in &words {
            stem_word(word, &cfg);
        }
    }
}

fn cmd_analyze(word: &str, lexicon: Option<PathBuf>, cyrillic_only: bool) {
    use kazsearch_core::explore::{explore_track_best, candidate_penalty};
    use kazsearch_core::rules::{NOUN_LAYERS, VERB_LAYERS};
    use kazsearch_core::script::lower_kazakh;
    use kazsearch_core::text::{fill_prefix_tables, count_syllables, utf8_char_count};

    let cfg = build_config(lexicon.as_ref(), cyrillic_only);
    let txt = lower_kazakh(word);
    let len = txt.len();
    let prefix = fill_prefix_tables(&txt);
    let chars = prefix.chars[len];

    println!("Input:      {}", word);
    println!("Lowered:    {}", txt);
    println!("Bytes:      {}", len);
    println!("Chars:      {}", utf8_char_count(&txt));
    println!("Syllables:  {}", count_syllables(&txt));
    println!();

    let noun = explore_track_best(&txt, len, &NOUN_LAYERS, &cfg, true, &prefix);
    let verb = explore_track_best(&txt, len, &VERB_LAYERS, &cfg, false, &prefix);

    let np = candidate_penalty(&noun.best_scored, &txt, chars, false, &prefix, &cfg.weights);
    let vp = candidate_penalty(&verb.best_scored, &txt, chars, true, &prefix, &cfg.weights);

    println!("--- Noun track ---");
    println!("  Stem:     {}", &txt[..noun.best_scored.len as usize]);
    println!("  Steps:    {}", noun.best_scored.steps);
    println!("  Penalty:  {:.4}", np);
    if let Some(lh) = noun.best_lexhit {
        println!("  Lex hit:  {} (steps={})", &txt[..lh.len as usize], lh.steps);
    }

    println!();
    println!("--- Verb track ---");
    println!("  Stem:     {}", &txt[..verb.best_scored.len as usize]);
    println!("  Steps:    {}", verb.best_scored.steps);
    println!("  Penalty:  {:.4}", vp);
    if let Some(lh) = verb.best_lexhit {
        println!("  Lex hit:  {} (steps={})", &txt[..lh.len as usize], lh.steps);
    }

    println!();
    let final_stem = stem(word, &cfg);
    println!("Final stem: {}", final_stem);
}

fn cmd_bench(file: Option<PathBuf>, lexicon: Option<PathBuf>, cyrillic_only: bool) {
    let cfg = build_config(lexicon.as_ref(), cyrillic_only);

    let words: Vec<String> = if let Some(path) = file {
        match std::fs::read_to_string(&path) {
            Ok(contents) => contents
                .lines()
                .map(|l| l.trim().to_string())
                .filter(|l| !l.is_empty())
                .collect(),
            Err(e) => {
                eprintln!("error: could not read {:?}: {}", path, e);
                std::process::exit(1);
            }
        }
    } else {
        let stdin = io::stdin();
        stdin
            .lock()
            .lines()
            .filter_map(|l| l.ok())
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect()
    };

    if words.is_empty() {
        eprintln!("No words to benchmark.");
        std::process::exit(1);
    }

    println!("Benchmarking {} words...", words.len());

    let iterations = 10;
    let start = Instant::now();
    for _ in 0..iterations {
        for word in &words {
            let _ = stem(word, &cfg);
        }
    }
    let elapsed = start.elapsed();

    let total_ops = words.len() * iterations;
    let ops_per_sec = total_ops as f64 / elapsed.as_secs_f64();
    let us_per_op = elapsed.as_micros() as f64 / total_ops as f64;

    println!("Total:      {} stems in {:.2?}", total_ops, elapsed);
    println!("Throughput: {:.0} stems/sec", ops_per_sec);
    println!("Latency:    {:.2} us/stem", us_per_op);
}

fn cmd_lexicon_validate(file: PathBuf) {
    match Lexicon::load(&file) {
        Ok(lex) => {
            println!("Lexicon:  {:?}", file);
            println!("Entries:  {}", lex.len());
            println!("Status:   OK");
        }
        Err(e) => {
            eprintln!("Lexicon:  {:?}", file);
            eprintln!("Status:   INVALID");
            eprintln!("Error:    {}", e);
            std::process::exit(1);
        }
    }
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Stem {
            words,
            stdin,
            lexicon,
            cyrillic_only,
        } => cmd_stem(words, stdin, lexicon, cyrillic_only),
        Commands::Analyze {
            word,
            lexicon,
            cyrillic_only,
        } => cmd_analyze(&word, lexicon, cyrillic_only),
        Commands::Bench {
            file,
            lexicon,
            cyrillic_only,
        } => cmd_bench(file, lexicon, cyrillic_only),
        Commands::Lexicon { action } => match action {
            LexiconAction::Validate { file } => cmd_lexicon_validate(file),
        },
    }
}
