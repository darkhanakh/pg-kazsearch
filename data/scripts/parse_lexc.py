#!/usr/bin/env python3
# prototype/parse_lexc.py
#
# Extracts lemma stems from specified lexicons in an Apertium .lexc file.
#
# Usage:
#   python prototype/parse_lexc.py \
#     --lexc data/raw/apertium-kaz.kaz.lexc \
#     --lexicons Common \
#     --out-dir data/processed/

import argparse
import os
import sys


def parse_lexc(lexc_path: str, lexicons: set) -> set:
    """
    Parse the .lexc file and extract stems from the given lexicon sections.

    :param lexc_path: Path to apertium-kaz.kaz.lexc
    :param lexicons: Set of lexicon names to extract (e.g. {'Common'})
    :return: Set of lemma stems
    """
    lemmas = set()
    current_lexicon = None

    with open(lexc_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Detect start of a lexicon section
            if line.startswith('LEXICON'):
                parts = line.split()
                current_lexicon = parts[1] if len(parts) >= 2 else None
                continue

            # If inside a desired lexicon, extract the stem before the colon
            if current_lexicon in lexicons and ':' in line:
                stem = line.split(':', 1)[0].strip()
                if stem:
                    lemmas.add(stem)

    return lemmas


def main():
    parser = argparse.ArgumentParser(
        description="Extract lemmas from Apertium .lexc file."
    )
    parser.add_argument(
        '--lexc',
        required=True,
        help="Path to apertium-kaz.kaz.lexc file"
    )
    parser.add_argument(
        '--lexicons',
        nargs='+',
        required=True,
        help="Lexicon names to extract (e.g. Common NounSuffixes)"
    )
    parser.add_argument(
        '--out-dir',
        required=True,
        help="Directory to write lemmas.txt"
    )
    args = parser.parse_args()

    # Validate input file
    if not os.path.isfile(args.lexc):
        print(f"Error: .lexc file not found: {args.lexc}", file=sys.stderr)
        sys.exit(1)

    # Ensure output directory exists
    os.makedirs(args.out_dir, exist_ok=True)

    # Extract and sort lemmas
    lemmas = parse_lexc(args.lexc, set(args.lexicons))
    sorted_lemmas = sorted(lemmas, key=lambda s: s)

    # Write to data/processed/lemmas.txt
    out_path = os.path.join(args.out_dir, 'lemmas.txt')
    with open(out_path, 'w', encoding='utf-8') as out_f:
        for lemma in sorted_lemmas:
            out_f.write(lemma + '\n')

    print(f"Extracted {len(sorted_lemmas)} lemmas to {out_path}")


if __name__ == "__main__":
    main()