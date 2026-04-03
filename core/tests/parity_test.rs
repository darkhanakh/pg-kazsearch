use kazsearch_core::lexicon::Lexicon;
use kazsearch_core::{stem, StemConfig};
use std::fs;

fn load_test_config() -> StemConfig {
    let lexicon_path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../data/tsearch_data/kaz_stems.dict"
    );
    let lexicon = Lexicon::load(lexicon_path).expect("failed to load kaz_stems.dict");
    StemConfig {
        derivation: true,
        max_steps: 8,
        lexicon: Some(lexicon),
        ..Default::default()
    }
}

#[test]
fn test_parity_with_c_extension() {
    let cfg = load_test_config();
    let data = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/c_stem_output.txt"
    ))
    .expect("c_stem_output.txt not found");

    let mut total = 0;
    let mut matches = 0;
    let mut mismatches: Vec<(String, String, String)> = Vec::new();

    for line in data.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.splitn(2, '|').collect();
        if parts.len() != 2 {
            continue;
        }
        let word = parts[0];
        let c_stem_raw = parts[1].trim_start_matches('{').trim_end_matches('}');

        let rust_stem = stem(word, &cfg);
        total += 1;

        if rust_stem == c_stem_raw {
            matches += 1;
        } else {
            mismatches.push((word.to_string(), c_stem_raw.to_string(), rust_stem));
        }
    }

    let parity_pct = if total > 0 {
        (matches as f64 / total as f64) * 100.0
    } else {
        0.0
    };

    eprintln!("\n=== Parity Report (with lexicon) ===");
    eprintln!("Lexicon entries: {}", cfg.lexicon.as_ref().unwrap().len());
    eprintln!("Total words:     {}", total);
    eprintln!("Matches:         {}", matches);
    eprintln!("Mismatches:      {}", mismatches.len());
    eprintln!("Parity:          {:.2}%", parity_pct);

    if !mismatches.is_empty() {
        eprintln!("\nFirst 40 mismatches:");
        eprintln!(
            "{:<30} {:<25} {:<25}",
            "WORD", "C_STEM", "RUST_STEM"
        );
        eprintln!("{}", "-".repeat(80));
        for (word, c_s, r_s) in mismatches.iter().take(40) {
            eprintln!("{:<30} {:<25} {:<25}", word, c_s, r_s);
        }
    }

    assert!(
        parity_pct >= 70.0,
        "Parity too low: {:.2}% ({}/{} words match)",
        parity_pct,
        matches,
        total
    );
}

#[test]
fn test_parity_5k_words_with_lexicon() {
    let cfg = load_test_config();
    let data = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/c_stem_output_5k.txt"
    ))
    .expect("c_stem_output_5k.txt not found");

    let mut total = 0;
    let mut matches = 0;
    let mut mismatches: Vec<(String, String, String)> = Vec::new();

    for line in data.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.splitn(2, '|').collect();
        if parts.len() != 2 {
            continue;
        }
        let word = parts[0];
        let c_stem_raw = parts[1].trim_start_matches('{').trim_end_matches('}');

        let rust_stem = stem(word, &cfg);
        total += 1;
        if rust_stem == c_stem_raw {
            matches += 1;
        } else {
            mismatches.push((word.to_string(), c_stem_raw.to_string(), rust_stem));
        }
    }

    let parity_pct = (matches as f64 / total as f64) * 100.0;
    eprintln!("\n=== 5K Parity Report (with lexicon) ===");
    eprintln!("Total words:     {}", total);
    eprintln!("Matches:         {}", matches);
    eprintln!("Mismatches:      {}", mismatches.len());
    eprintln!("Parity:          {:.2}%", parity_pct);

    if !mismatches.is_empty() {
        eprintln!("\nFirst 30 mismatches:");
        eprintln!("{:<35} {:<25} {:<25}", "WORD", "C_STEM", "RUST_STEM");
        eprintln!("{}", "-".repeat(85));
        for (word, c_s, r_s) in mismatches.iter().take(30) {
            eprintln!("{:<35} {:<25} {:<25}", word, c_s, r_s);
        }
    }

    assert!(
        parity_pct >= 95.0,
        "5K parity too low: {:.2}% ({}/{} words match)",
        parity_pct,
        matches,
        total
    );
}

#[test]
fn test_parity_without_lexicon() {
    let cfg = StemConfig::default();
    let data = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/c_stem_output.txt"
    ))
    .expect("c_stem_output.txt not found");

    let mut total = 0;
    let mut matches = 0;

    for line in data.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.splitn(2, '|').collect();
        if parts.len() != 2 {
            continue;
        }
        let word = parts[0];
        let c_stem_raw = parts[1].trim_start_matches('{').trim_end_matches('}');

        let rust_stem = stem(word, &cfg);
        total += 1;
        if rust_stem == c_stem_raw {
            matches += 1;
        }
    }

    let parity_pct = (matches as f64 / total as f64) * 100.0;
    eprintln!("\n=== No-lexicon baseline: {:.2}% ({}/{}) ===", parity_pct, matches, total);
}
