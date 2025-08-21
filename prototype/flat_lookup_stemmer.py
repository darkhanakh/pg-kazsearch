import re
import os
import json

def splitting_by_words(text):
    result = re.findall(r'\w+', text)
    return result

def sorting_endings_from_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Flatten all endings across categories
    endings = []
    if isinstance(data, dict):
        for values in data.values():
            if isinstance(values, list):
                endings.extend(values)
    elif isinstance(data, list):
        endings.extend(data)
    # Normalize and sort by length (desc) for greedy stripping
    endings = [e.strip() for e in endings if isinstance(e, str) and e.strip()]
    sorted_endings = sorted(set(endings), key=len, reverse=True)
    return sorted_endings

def stem(word, endings, stems_set):
    w = word.lower()
    min_len = 2

    while len(w) > min_len:
        stripped = False
        for ending in endings:
            if w.endswith(ending):
                candidate = w[:-len(ending)]
                # ✅ Stop if candidate is a known lemma
                if candidate in stems_set:
                    return candidate
                # Otherwise, accept strip and continue
                if len(candidate) >= min_len:
                    w = candidate
                    stripped = True
                    break
        if not stripped:
            break
    return w

def load_stems_set(stems_file_path):
    stems_set = set()
    with open(stems_file_path, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if not w:
                continue
            stems_set.add(w.lower())
    return stems_set

def stem_single_word(word, endings, stems_set):
    # Return single word stem for a single input word
    return stem(word, endings, stems_set)
    

def _default_processed_dir():
    # project_root/prototype -> project_root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "data", "processed")

def _load_resources(processed_dir=None):
    if processed_dir is None:
        processed_dir = _default_processed_dir()
    endings_path = os.path.join(processed_dir, "kazakh_endings.json")
    stems_path = os.path.join(processed_dir, "lemmas.txt")
    endings = sorting_endings_from_json(endings_path)
    stems_set = load_stems_set(stems_path)
    return endings, stems_set

def main():
    import sys
    endings, stems_set = _load_resources()
    # Input: single word -> Output: single word (stem)
    if len(sys.argv) > 1:
        input_word = sys.argv[1]
    else:
        # Avoid extra prompts/messages; read a single word
        try:
            input_word = input().strip()
        except EOFError:
            input_word = ""
    if not input_word:
        # Print nothing for empty input
        return
    result = stem_single_word(input_word, endings, stems_set)
    # Print only the stem, no extra text
    print(result)

if __name__ == "__main__":
    main()
