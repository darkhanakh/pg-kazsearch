# This script uses an LLM to generate stems for a list of words from a priority list to expand the lemma dictionary.
import os
from pathlib import Path

from dotenv import load_dotenv
import openai

# Load environment variables from a .env file in the repository root (if present)
load_dotenv()

# Configure OpenAI client from environment
openai.api_key = os.environ.get("OPENAI_API_KEY", "")
if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Create a .env file based on env.example and set OPENAI_API_KEY=")

# Optional: custom base URL (useful for proxies or self-hosted gateways)
openai.base_url = os.environ.get("OPENAI_BASE_URL", getattr(openai, "base_url", None)) or None

# Model can be overridden via env; defaults to a reasonable model name
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = REPO_ROOT / "data" / "processed" / "priority_list.txt"
OUTPUT_FILE = REPO_ROOT / "data" / "processed" / "word_stems.txt"

BATCH_SIZE = 1000  # adjust depending on token limit and cost

def parse_priority_file(file_path: str, limit=None):
    """Read priority list file and return (count, word) tuples."""
    words = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            count, word = parts[0], parts[1]
            words.append((int(count), word))
            if limit and len(words) >= limit:
                break
    return words

def chunked(iterable, size):
    """Yield successive n-sized chunks."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]

def get_stems_from_llm(words):
    """
    Get stems for a batch of Kazakh words from the LLM.
    Words is a list of strings.
    """
    prompt = f"""
You are an expert Kazakh computational linguist specializing in morphology.
Your task: normalize a batch of Kazakh words to their **dictionary base forms (lemmas)**.

Rules:
- **Nouns**: return singular, nominative form. ("қалаларының" -> "қала").
- **Verbs**: return stem with vowel elision/consonant harmony.
  Examples: "отырып" -> "отыр", "барамын" -> "бар", "ағу" -> "ағу".
- Handle **loanwords**: return base dictionary form without affixes.
- Apply **Kazakh vowel ellision rules** (e.g., "бастап" from "баста-") correctly.
- Apply **all morphological rules**: case endings, possessives, plural, compounds.
- If already lemma, repeat unchanged.
- Return ONLY a valid JSON object where keys = given words, values = stems.

Example Input:
["қалаларының", "отырып", "швингермен"]

Example Output:
{{
  "қалаларының": "қала",
  "отырып": "отыр",
  "швингермен": "швингер"
}}

Now process this batch:

{words}
"""
    response = openai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You return only JSON. No explanations."},
            {"role": "user", "content": prompt},
        ],
    )

    return response.choices[0].message.content.strip()

def main():
    words = parse_priority_file(INPUT_FILE)
    print(f"Total words parsed: {len(words)}")

    # Process in batches
    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
        for batch in chunked(words, BATCH_SIZE):
            batch_words = [w for _, w in batch]
            try:
                stems_json = get_stems_from_llm(batch_words)
                out_f.write(stems_json + "\n")
                print(f"[OK] Processed {len(batch_words)} words")
            except Exception as e:
                print(f"[ERR] {e}")

    print(f"\n✅ Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()