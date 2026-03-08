"""
Step 6 (optional): Suggest keywords to improve categorization.

Analyzes uncategorized conversations to find frequently occurring words and
bigrams that could be added to config categories. Helps users tune their
keyword config for better coverage.

Usage: python 06_suggest_keywords.py --config path/to/config.json
"""
import json
import os
import sys
import argparse
import re
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")


STOP_WORDS = {
    # English
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "for", "of", "and",
    "or", "but", "not", "with", "from", "by", "as", "this", "that", "was",
    "are", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "if", "then",
    "so", "no", "yes", "up", "out", "all", "just", "also", "about", "its",
    "my", "your", "their", "our", "his", "her", "me", "you", "we", "they",
    "i", "he", "she", "what", "which", "who", "how", "when", "where", "why",
    "one", "two", "three", "some", "any", "each", "more", "most", "other",
    "new", "old", "first", "last", "get", "got", "like", "want", "need",
    "make", "use", "know", "see", "way", "thing", "here", "there", "very",
    "still", "now", "than", "too", "even", "much", "many", "well", "back",
    "only", "over", "such", "after", "before", "between", "same", "own",
    "while", "because", "through", "both", "few", "those", "these", "into",
    "them", "him", "us", "something", "nothing", "everything", "anything",
    "don", "doesn", "didn", "won", "wouldn", "couldn", "shouldn", "isn",
    "aren", "wasn", "weren", "hasn", "haven", "hadn", "let", "say", "said",
    "think", "look", "come", "go", "take", "give", "tell", "ask", "try",
    "call", "find", "put", "keep", "help", "show", "work", "part", "place",
    "case", "point", "hand", "turn", "start", "end", "line", "move", "long",
    "right", "left", "high", "big", "small", "great", "good", "bad", "sure",
    "able", "already", "really", "actually", "please", "thanks", "thank",
    "okay", "ok", "hi", "hello", "hey",
    # Dutch
    "een", "het", "van", "dat", "die", "niet", "ook", "als", "zijn", "maar",
    "dan", "bij", "heb", "moet", "naar", "geen", "wil", "wel", "dit", "maak",
    "dus", "deze", "aan", "geef", "welke", "maken", "tot", "nog", "hebben",
    "mijn", "waar", "waarom", "uit", "worden", "alleen", "hoeveel", "per",
    "meer", "goed", "nee", "heeft", "andere", "jaar", "iets", "kan", "wat",
    "hoe", "met", "voor", "toch", "weer", "omdat", "heel", "over", "zou",
    "daar", "hier", "echt", "mag", "ben", "wordt", "alles", "graag", "weet",
    "misschien", "kun", "zelf", "waren", "werd", "hadden", "zou", "zonder",
    "onder", "door", "haar", "hem", "ons", "zij", "wij", "hij", "ik", "jij",
    "jullie", "hun", "uw", "erg", "veel", "weinig", "gaan", "doen", "zien",
    "komen", "staan", "geven", "vragen", "laten", "nemen", "zetten", "houden",
    "liggen", "lopen", "zitten", "brengen", "denken", "willen", "kunnen",
    "moeten", "zullen", "mogen", "eerst", "tweede", "derde", "bijvoorbeeld",
    "echter", "eigenlijk", "natuurlijk", "daarom", "ongeveer", "daarna",
    "verder", "altijd", "nooit", "soms", "vaak", "elke", "elk", "ander",
    "zelfde", "nieuwe", "grote", "kleine", "goede", "hele", "volgende",
    "vorige", "laatste", "eerste",
    # French (common in multilingual chats)
    "les", "des", "une", "est", "pas", "que", "qui", "dans", "sur", "pour",
    "avec", "plus", "sont", "nous", "vous", "ils", "elle", "mais", "aussi",
    "cette", "tout", "bien", "fait", "peut",
    # Generic filler
    "etc", "e.g", "i.e", "just", "thing", "stuff", "way", "lot", "bit",
}


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_conversations(backup_dir):
    all_convs = []
    for i in range(100):
        path = os.path.join(backup_dir, f"conversations-{i:03d}.json")
        if not os.path.exists(path):
            break
        with open(path, "r", encoding="utf-8") as f:
            all_convs.extend(json.load(f))
    return all_convs


def get_existing_keywords(categories):
    """Collect all keywords already used in config."""
    existing = set()
    for cat, keywords in categories.items():
        if isinstance(keywords, dict):
            for kw in keywords.get("strong", []):
                existing.add(kw.lower().strip())
            for kw in keywords.get("medium", []):
                existing.add(kw.lower().strip())
        else:
            for kw in keywords:
                existing.add(kw.lower().strip())
    return existing


def extract_words(conv, max_messages=5):
    """Extract words from first N user messages."""
    mapping = conv.get("mapping", {})
    messages = []
    for node in mapping.values():
        msg = node.get("message")
        if not msg:
            continue
        role = msg.get("author", {}).get("role", "")
        ct = msg.get("create_time", 0) or 0
        parts = msg.get("content", {}).get("parts", [])
        text = "\n".join(p for p in parts if isinstance(p, str) and p.strip())
        if text.strip() and role == "user":
            messages.append((ct, text))

    messages.sort(key=lambda x: x[0])
    all_text = " ".join(text[:500] for _, text in messages[:max_messages])
    return all_text.lower()


def tokenize(text):
    """Split text into words, filtering short/stop words."""
    words = re.findall(r"[a-z][a-z0-9_.-]+", text)
    return [w for w in words if len(w) > 2 and w not in STOP_WORDS]


def get_bigrams(words):
    """Generate bigrams from word list."""
    return [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]


def main():
    parser = argparse.ArgumentParser(description="Suggest keywords for uncategorized conversations")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--top", type=int, default=30, help="Number of suggestions per type")
    args = parser.parse_args()

    config = load_config(args.config)
    backup_dir = config["backup_dir"]
    categories = config.get("categories", {})

    base_dir = os.path.dirname(args.config) or "."
    inv_path = os.path.join(base_dir, "inventory.json")

    with open(inv_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    # Get uncategorized items worth analyzing
    uncat = [
        i for i in inventory
        if i["category"] == "uncategorized" and i["triage"] != "skip"
    ]

    if not uncat:
        print("No uncategorized conversations to analyze.")
        return

    print(f"Analyzing {len(uncat)} uncategorized conversations...")
    print(f"Loading conversations from: {backup_dir}")

    all_convs = load_conversations(backup_dir)
    conv_by_id = {c.get("id", ""): c for c in all_convs}

    existing_keywords = get_existing_keywords(categories)

    word_counter = Counter()
    bigram_counter = Counter()

    for item in uncat:
        conv = conv_by_id.get(item["id"])
        if not conv:
            continue

        text = extract_words(conv)
        # Also include title
        text = item["title"].lower() + " " + text

        words = tokenize(text)
        word_counter.update(words)

        bigrams = get_bigrams(words)
        bigram_counter.update(bigrams)

    # Filter out words already in config
    new_words = {
        w: c for w, c in word_counter.items()
        if w not in existing_keywords and c >= 3
    }
    new_bigrams = {
        b: c for b, c in bigram_counter.items()
        if b not in existing_keywords and c >= 2
    }

    print(f"\n{'=' * 60}")
    print(f"KEYWORD SUGGESTIONS")
    print(f"{'=' * 60}")
    print(f"\nThese words appear frequently in uncategorized conversations")
    print(f"but are NOT in your current config keywords.\n")
    print(f"Review and add relevant ones to your config categories.\n")

    print(f"--- Top {args.top} single words (frequency >= 3) ---")
    for word, count in sorted(new_words.items(), key=lambda x: -x[1])[:args.top]:
        print(f"  {count:4d}x  {word}")

    print(f"\n--- Top {args.top} word pairs (frequency >= 2) ---")
    for bigram, count in sorted(new_bigrams.items(), key=lambda x: -x[1])[:args.top]:
        print(f"  {count:4d}x  {bigram}")

    # Category-aware suggestions using distinctiveness scoring
    # A word is a good keyword candidate if it appears much more in one
    # category than others (distinctive) and also appears in uncategorized items
    print(f"\n--- Category-specific keyword candidates ---")
    print(f"(Words distinctive to one category that also appear uncategorized)\n")

    # Build per-category document counts (how many conversations contain word)
    cat_doc_counts = {}
    cat_totals = Counter()
    for item in inventory:
        if item["category"] == "uncategorized":
            continue
        conv = conv_by_id.get(item["id"])
        if not conv:
            continue
        text = extract_words(conv)
        words = set(tokenize(text))
        cat = item["category"]
        cat_totals[cat] += 1
        if cat not in cat_doc_counts:
            cat_doc_counts[cat] = Counter()
        cat_doc_counts[cat].update(words)

    # Count how many uncategorized docs contain each word
    uncat_doc_counts = Counter()
    for item in uncat:
        conv = conv_by_id.get(item["id"])
        if not conv:
            continue
        text = extract_words(conv)
        text = item["title"].lower() + " " + text
        words = set(tokenize(text))
        uncat_doc_counts.update(words)

    # Find words that are distinctive to a category and frequent in uncategorized
    suggestions_by_cat = {}
    for cat, doc_counts in cat_doc_counts.items():
        total_in_cat = cat_totals[cat]
        for word, count_in_cat in doc_counts.items():
            if word in existing_keywords:
                continue
            uncat_count = uncat_doc_counts.get(word, 0)
            if uncat_count < 3:
                continue
            # Distinctiveness: fraction of category docs containing word
            cat_fraction = count_in_cat / total_in_cat
            # vs fraction across all other categories
            other_count = sum(
                cat_doc_counts.get(c, {}).get(word, 0)
                for c in cat_doc_counts if c != cat
            )
            other_total = sum(cat_totals[c] for c in cat_totals if c != cat)
            other_fraction = other_count / other_total if other_total > 0 else 0
            # Word must be at least 2x more common in this category
            if cat_fraction > 0.1 and cat_fraction > other_fraction * 2:
                score = uncat_count * cat_fraction
                if cat not in suggestions_by_cat:
                    suggestions_by_cat[cat] = []
                suggestions_by_cat[cat].append((word, uncat_count, cat_fraction))

    if suggestions_by_cat:
        for cat in sorted(suggestions_by_cat.keys()):
            items = sorted(suggestions_by_cat[cat], key=lambda x: -x[1])[:5]
            print(f"  {cat}:")
            for word, uncat_count, cat_frac in items:
                print(f"    {word:25s} {uncat_count:3d}x uncategorized ({cat_frac:.0%} in {cat})")
    else:
        print("  (No distinctive category matches found — may need new categories)")

    # Summary
    total = len(inventory)
    categorized = sum(1 for i in inventory if i["category"] != "uncategorized")
    print(f"\n{'=' * 60}")
    print(f"Current coverage: {categorized}/{total} ({100*categorized/total:.0f}%)")
    print(f"Uncategorized (reviewable): {len(uncat)}")
    print(f"Adding top suggested keywords could improve coverage significantly.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
