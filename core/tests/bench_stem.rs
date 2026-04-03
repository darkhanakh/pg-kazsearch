use kazsearch_core::lexicon::Lexicon;
use kazsearch_core::{stem, StemConfig};
use std::fs;
use std::process::Command;
use std::time::Instant;

fn tokenize_kazakh(text: &str) -> Vec<&str> {
    let mut tokens = Vec::new();
    let mut start = None;
    for (i, ch) in text.char_indices() {
        let is_kaz = ch.is_alphabetic()
            && (('\u{0400}'..='\u{04FF}').contains(&ch)
                || ('\u{0500}'..='\u{052F}').contains(&ch));
        if is_kaz {
            if start.is_none() {
                start = Some(i);
            }
        } else if let Some(s) = start {
            let tok = &text[s..i];
            if !tok.is_empty() {
                tokens.push(tok);
            }
            start = None;
        }
    }
    if let Some(s) = start {
        tokens.push(&text[s..]);
    }
    tokens
}

#[test]
fn bench_stem_unique_tokens() {
    let tokens_path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/bench_tokens.txt");
    let tokens: Vec<String> = fs::read_to_string(tokens_path)
        .expect("bench_tokens.txt not found")
        .lines()
        .filter(|l| !l.is_empty())
        .map(String::from)
        .collect();

    let lexicon = Lexicon::load(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../data/tsearch_data/kaz_stems.dict"
    ))
    .unwrap();

    let cfg = StemConfig {
        lexicon: Some(lexicon),
        ..Default::default()
    };

    let n = tokens.len();
    eprintln!("Loaded {} unique tokens", n);

    // Warmup
    for t in tokens.iter().take(1000) {
        let _ = stem(t, &cfg);
    }

    // Single pass (mirrors C benchmark)
    let start = Instant::now();
    let mut results: Vec<String> = Vec::with_capacity(n);
    for t in &tokens {
        results.push(stem(t, &cfg));
    }
    let elapsed_single = start.elapsed();

    // Multi-pass for stable timing (5 iterations)
    let iterations = 5;
    let start_multi = Instant::now();
    for _ in 0..iterations {
        for t in &tokens {
            let _ = stem(t, &cfg);
        }
    }
    let elapsed_multi = start_multi.elapsed();
    let avg_per_iter = elapsed_multi / iterations;

    let us_per_word_single = elapsed_single.as_micros() as f64 / n as f64;
    let us_per_word_avg = avg_per_iter.as_micros() as f64 / n as f64;
    let throughput_single = n as f64 / elapsed_single.as_secs_f64();
    let throughput_avg = n as f64 / avg_per_iter.as_secs_f64();

    eprintln!();
    eprintln!("=== Rust kazsearch-core Benchmark ===");
    eprintln!("Unique tokens:     {}", n);
    eprintln!();
    eprintln!("Single pass:       {:.2} ms", elapsed_single.as_secs_f64() * 1000.0);
    eprintln!("  per word:        {:.3} us", us_per_word_single);
    eprintln!("  throughput:      {:.0} words/sec", throughput_single);
    eprintln!();
    eprintln!("Avg of {} passes:   {:.2} ms", iterations, avg_per_iter.as_secs_f64() * 1000.0);
    eprintln!("  per word:        {:.3} us", us_per_word_avg);
    eprintln!("  throughput:      {:.0} words/sec", throughput_avg);

    eprintln!();
    eprintln!("Lexicon entries:   {}", cfg.lexicon.as_ref().unwrap().len());
}

#[test]
fn bench_stem_full_articles() {
    let articles_path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/bench_articles.txt");
    let raw = fs::read_to_string(articles_path).expect("bench_articles.txt not found");
    let articles: Vec<&str> = raw.lines().collect();

    let lexicon = Lexicon::load(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../data/tsearch_data/kaz_stems.dict"
    ))
    .unwrap();

    let cfg = StemConfig {
        lexicon: Some(lexicon),
        ..Default::default()
    };

    let n_articles = articles.len();
    let mut total_tokens: usize = 0;

    // Single pass: tokenize + stem every article
    let start = Instant::now();
    for article in &articles {
        let lower = article.to_lowercase();
        let tokens = tokenize_kazakh(&lower);
        for t in &tokens {
            let _ = stem(t, &cfg);
        }
        total_tokens += tokens.len();
    }
    let elapsed = start.elapsed();

    let ms = elapsed.as_secs_f64() * 1000.0;
    let per_article_ms = ms / n_articles as f64;
    let articles_per_sec = n_articles as f64 / elapsed.as_secs_f64();
    let tokens_per_sec = total_tokens as f64 / elapsed.as_secs_f64();

    eprintln!();
    eprintln!("=== Rust: Full Article Stemming ===");
    eprintln!("Articles:          {}", n_articles);
    eprintln!("Total tokens:      {}", total_tokens);
    eprintln!("Total time:        {:.2} ms", ms);
    eprintln!("Per article:       {:.3} ms", per_article_ms);
    eprintln!("Articles/sec:      {:.0}", articles_per_sec);
    eprintln!("Tokens/sec:        {:.0}", tokens_per_sec);
}

fn get_rss_kb() -> u64 {
    let output = Command::new("ps")
        .args(["-o", "rss=", "-p", &std::process::id().to_string()])
        .output()
        .unwrap();
    String::from_utf8_lossy(&output.stdout).trim().parse::<u64>().unwrap_or(0)
}

#[test]
fn bench_memory_usage() {
    let rss_base = get_rss_kb();
    eprintln!();
    eprintln!("=== Rust Memory Usage ===");
    eprintln!("RSS baseline (test harness): {} kB", rss_base);

    let lexicon = Lexicon::load(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../data/tsearch_data/kaz_stems.dict"
    ))
    .unwrap();
    let rss_after_lex = get_rss_kb();
    eprintln!("RSS after lexicon load:      {} kB  (+{} kB)", rss_after_lex, rss_after_lex.saturating_sub(rss_base));
    eprintln!("Lexicon entries:             {}", lexicon.len());

    let cfg = StemConfig {
        lexicon: Some(lexicon),
        ..Default::default()
    };

    let tokens: Vec<String> = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/bench_tokens.txt"
    ))
    .unwrap()
    .lines()
    .filter(|l| !l.is_empty())
    .map(String::from)
    .collect();

    for t in &tokens {
        let _ = stem(t, &cfg);
    }
    let rss_after_stem = get_rss_kb();
    eprintln!("RSS after stemming {} words: {} kB  (+{} kB from lexicon)", tokens.len(), rss_after_stem, rss_after_stem.saturating_sub(rss_after_lex));
    eprintln!();
    eprintln!("Total RSS delta (lex+stem):  {} kB", rss_after_stem.saturating_sub(rss_base));
}
