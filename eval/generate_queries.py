"""
Auto-generate evaluation queries from a scraped article corpus.

Three strategies:
  1. title_keywords  — 2-3 salient words from the title
  2. body_sentence   — first substantive sentence from the body
  3. morpho_variant  — inflected version of a title keyword

Each query maps to the source article as the single relevant document.

Usage:
    python3 eval/generate_queries.py --input data/corpus/articles.jsonl \
                                     --output eval/auto_queries.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

STOPWORDS_PATH = Path(__file__).parent.parent / "data" / "processed" / "stopwords.txt"

KAZAKH_SUFFIXES = [
    "дар", "дер", "лар", "лер", "тар", "тер",
    "да", "де", "та", "те",
    "дан", "ден", "тан", "тен",
    "дың", "дің", "тың", "тің", "ның", "нің",
    "ға", "ге", "қа", "ке",
    "мен", "бен", "пен",
    "ды", "ді", "ты", "ті",
    "ын", "ін",
    "ның", "нің",
    "дағы", "дегі", "тағы", "тегі",
    "лық", "лік", "дық", "дік",
    "шы", "ші",
]

BACK_VOWELS = set("аоұыу")
FRONT_VOWELS = set("әеөүіиё")
ALL_VOWELS = BACK_VOWELS | FRONT_VOWELS


def _load_stopwords() -> set[str]:
    out: set[str] = set()
    if not STOPWORDS_PATH.exists():
        return out
    with STOPWORDS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            w = line.strip().lower()
            if w and not w.startswith("#"):
                out.add(w)
    return out


STOPWORDS = _load_stopwords()


def _is_content_word(w: str) -> bool:
    if len(w) < 3:
        return False
    if w in STOPWORDS:
        return False
    if not any(c.isalpha() for c in w):
        return False
    if re.match(r"^\d+$", w):
        return False
    return True


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text.lower())
    text = re.sub(r"[^\w\s]", " ", text)
    return [w for w in text.split() if w]


def _is_back(word: str) -> bool:
    for c in reversed(word):
        if c in BACK_VOWELS:
            return True
        if c in FRONT_VOWELS:
            return False
    return True


def _pick_suffix(word: str) -> str:
    back = _is_back(word)
    compatible = []
    for sfx in KAZAKH_SUFFIXES:
        sfx_has_back = any(c in BACK_VOWELS for c in sfx)
        sfx_has_front = any(c in FRONT_VOWELS for c in sfx)
        if sfx_has_back and not back:
            continue
        if sfx_has_front and back:
            continue
        compatible.append(sfx)
    if not compatible:
        return random.choice(KAZAKH_SUFFIXES[:6])
    return random.choice(compatible)


def generate_title_keywords(article: dict, article_id: int) -> dict | None:
    tokens = _tokenize(article["title"])
    content = [w for w in tokens if _is_content_word(w)]
    if len(content) < 2:
        return None
    selected = content[:3]
    return {
        "query": " ".join(selected),
        "relevant_ids": [article_id],
        "source": "title_keywords",
    }


def generate_body_sentence(article: dict, article_id: int) -> dict | None:
    body = article.get("body", "")
    sentences = re.split(r"[.!?।]\s+", body)
    for s in sentences[:3]:
        s = s.strip()
        words = _tokenize(s)
        content = [w for w in words if _is_content_word(w)]
        if len(content) >= 3 and len(s) >= 20:
            trimmed = " ".join(content[:5])
            return {
                "query": trimmed,
                "relevant_ids": [article_id],
                "source": "body_sentence",
            }
    return None


def generate_morpho_variant(article: dict, article_id: int) -> dict | None:
    tokens = _tokenize(article["title"])
    content = [w for w in tokens if _is_content_word(w) and len(w) >= 4]
    if not content:
        return None
    word = random.choice(content)
    suffix = _pick_suffix(word)
    inflected = word + suffix
    other = [w for w in content if w != word][:2]
    query_parts = [inflected] + other
    return {
        "query": " ".join(query_parts),
        "relevant_ids": [article_id],
        "source": "morpho_variant",
    }


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation queries from article corpus")
    parser.add_argument("--input", default="data/corpus/articles.jsonl")
    parser.add_argument("--output", default="eval/auto_queries.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--use-db-ids", action="store_true",
                        help="Query DB for actual article IDs by URL")
    parser.add_argument("--container", default="pg-kazsearch")
    parser.add_argument("--db", default="kazsearch")
    parser.add_argument("--user", default="postgres")
    args = parser.parse_args()

    random.seed(args.seed)

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"Input file not found: {input_path}")

    articles = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                articles.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not articles:
        sys.exit("No articles in input file")

    url_to_id: dict[str, int] = {}
    if args.use_db_ids:
        urls_csv = ",".join(f"'{a['url'].replace(chr(39), chr(39)*2)}'" for a in articles)
        sql = f"SELECT url, id FROM articles WHERE url IN ({urls_csv});"
        try:
            out = subprocess.check_output(
                ["docker", "exec", args.container, "psql",
                 "-U", args.user, "-d", args.db, "-At", "-F", "\t", "-c", sql],
                text=True,
            )
            for line in out.strip().splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    url_to_id[parts[0]] = int(parts[1])
        except (subprocess.CalledProcessError, ValueError):
            print("WARN: Could not fetch DB IDs, using file-order IDs", file=sys.stderr)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    queries: list[dict] = []
    for i, article in enumerate(articles):
        article_id = url_to_id.get(article.get("url", ""), i + 1)

        q = generate_title_keywords(article, article_id)
        if q:
            queries.append(q)

        q = generate_body_sentence(article, article_id)
        if q:
            queries.append(q)

        q = generate_morpho_variant(article, article_id)
        if q:
            queries.append(q)

    with out_path.open("w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    by_source = {}
    for q in queries:
        by_source[q["source"]] = by_source.get(q["source"], 0) + 1

    print(f"Generated {len(queries)} queries from {len(articles)} articles")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
