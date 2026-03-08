"""
Step 4b: Statistical classifier for remaining uncategorized conversations.

Uses the already-categorized conversations as training data to build
word-frequency profiles per category. Then scores each uncategorized
conversation against those profiles using TF-IDF-like weighting.

Reads messages progressively (more messages for longer conversations)
until confident category match is found.

Usage: python 04b_classify.py --config path/to/config.json
"""
import json
import os
import sys
import argparse
import re
import math
from collections import Counter, defaultdict
from shared import keyword_in_text, tokenize, STOP_WORDS, GENERIC_WORDS

sys.stdout.reconfigure(encoding="utf-8")


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


def extract_messages_sorted(conv):
    """Extract all user+assistant messages, sorted by time."""
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
        if text.strip() and role in ("user", "assistant"):
            messages.append((ct, role, text))
    messages.sort(key=lambda x: x[0])
    return messages




def build_category_profiles(inventory, conv_by_id):
    """Build word frequency profiles from categorized conversations.

    Returns:
        profiles: {category: {word: tf-idf score}}
        idf: {word: idf score}
    """
    skip_categories = {"uncategorized", "already-processed"}

    # Collect documents per category
    cat_docs = defaultdict(list)  # {cat: [set_of_words, ...]}

    for item in inventory:
        if item["category"] in skip_categories:
            continue
        conv = conv_by_id.get(item["id"])
        if not conv:
            continue
        messages = extract_messages_sorted(conv)
        # Use all messages for profile building
        all_text = item["title"].lower() + " "
        all_text += " ".join(text[:1000] for _, _, text in messages)
        words = set(tokenize(all_text))
        cat_docs[item["category"]].append(words)

    # Compute IDF across all categorized documents
    total_docs = sum(len(docs) for docs in cat_docs.values())
    doc_freq = Counter()
    for docs in cat_docs.values():
        for word_set in docs:
            doc_freq.update(word_set)

    idf = {}
    for word, df in doc_freq.items():
        idf[word] = math.log(total_docs / (1 + df))

    # Build TF-IDF profile per category with distinctiveness filter
    # A word only contributes to a category profile if it appears
    # proportionally more in that category than in others
    # Skip categories with too few training examples (profiles are noisy)
    MIN_TRAINING_DOCS = 20
    profiles = {}
    for cat, docs in cat_docs.items():
        if len(docs) < MIN_TRAINING_DOCS:
            continue  # Not enough data for reliable statistical profile

        word_counts = Counter()
        for word_set in docs:
            word_counts.update(word_set)

        n_docs = len(docs)
        other_docs_total = total_docs - n_docs

        profile = {}
        for word, count in word_counts.items():
            tf = count / n_docs  # fraction of this category's docs containing word

            # Count how often this word appears in OTHER categories
            other_count = doc_freq[word] - count
            other_tf = other_count / other_docs_total if other_docs_total > 0 else 0

            # Distinctiveness: word must appear at least 2x more often
            # in this category than in others (relative to category size)
            if other_tf > 0 and tf / other_tf < 2.0:
                continue  # Word is not distinctive to this category

            profile[word] = tf * idf.get(word, 0)

        # Keep only top N most distinctive words per category
        top_words = sorted(profile.items(), key=lambda x: -x[1])[:500]
        profiles[cat] = dict(top_words)

    return profiles, idf


def classify_conversation(conv, title, profiles, idf, cat_avg_scores,
                          cat_keywords, min_confidence=0.15, min_score_ratio=0.4):
    """Classify a conversation by reading messages progressively.

    Reads messages in batches, scoring after each batch. Stops when
    confident or all messages are consumed.

    Requires:
    - Relative margin: top score must be sufficiently ahead of #2
    - Absolute score: top score must be at least min_score_ratio of what
      a typical conversation in that category scores
    - Keyword anchor: at least one of the category's config keywords must
      appear in the conversation (prevents noise-driven misclassification)

    Returns (category, confidence, top_score) or (None, 0, 0).
    """
    messages = extract_messages_sorted(conv)
    if not messages:
        return None, 0, 0

    # Progressive reading: start with title + first 3 messages,
    # then add more until confident or done
    batches = [3, 6, 12, 25, len(messages)]
    seen_text = title.lower() + " "
    best_cat = None
    best_confidence = 0
    best_score = 0

    for batch_size in batches:
        # Add messages up to batch_size
        for _, _, text in messages[:batch_size]:
            seen_text += " " + text[:1000]

        words = set(tokenize(seen_text))
        if len(words) < 5:
            continue

        # Score against each category profile
        scores = {}
        for cat, profile in profiles.items():
            # Cosine-like similarity: sum of matching TF-IDF weights
            score = sum(profile.get(w, 0) for w in words)
            # Normalize by sqrt of profile magnitude to avoid bias toward large categories
            magnitude = math.sqrt(sum(v ** 2 for v in profile.values()))
            if magnitude > 0:
                scores[cat] = score / magnitude

        if not scores:
            continue

        # Get top two scores for confidence calculation
        sorted_scores = sorted(scores.values(), reverse=True)
        top_score = sorted_scores[0]
        second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0

        # Confidence: how much better is #1 vs #2 (relative margin)
        if top_score > 0:
            margin = (top_score - second_score) / top_score
            best_cat_candidate = max(scores, key=scores.get)

            # Check absolute score: must be at least min_score_ratio of
            # what a typical known-good conversation scores in this category
            avg = cat_avg_scores.get(best_cat_candidate, 1.0)
            if top_score < avg * min_score_ratio:
                continue  # Too weak a match, keep reading

            # Keyword anchor: the conversation must show topical relevance
            # Check config keywords first (strong signal), then top profile
            # features (weaker but still meaningful)
            anchored = False
            for kw in cat_keywords.get(best_cat_candidate, []):
                if keyword_in_text(kw, seen_text):
                    anchored = True
                    break
            if not anchored:
                # Fallback: check if at least 3 of the top 20 profile features
                # appear — this allows topically related content through
                # while still blocking noise
                profile = profiles.get(best_cat_candidate, {})
                top_features = sorted(profile.items(), key=lambda x: -x[1])[:20]
                feature_hits = sum(1 for w, _ in top_features if w in words)
                if feature_hits < 3:
                    continue

            if margin > best_confidence:
                best_confidence = margin
                best_cat = best_cat_candidate
                best_score = top_score

            # Stop early if confident enough
            if margin >= min_confidence:
                return best_cat, margin, top_score

    return best_cat, best_confidence, best_score


def main():
    parser = argparse.ArgumentParser(
        description="Statistical classifier for uncategorized conversations"
    )
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument(
        "--threshold", type=float, default=0.10,
        help="Minimum confidence margin to assign category (default: 0.10)"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    backup_dir = config["backup_dir"]

    base_dir = os.path.dirname(args.config) or "."
    inv_path = os.path.join(base_dir, "inventory.json")

    with open(inv_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    print(f"Loading conversations from: {backup_dir}")
    all_convs = load_conversations(backup_dir)
    conv_by_id = {c.get("id", ""): c for c in all_convs}

    # Count initial state
    initial_uncat = sum(1 for i in inventory if i["category"] == "uncategorized")
    initial_review = sum(
        1 for i in inventory
        if i["category"] == "uncategorized" and i["triage"] == "review"
    )

    print(f"Uncategorized: {initial_uncat} ({initial_review} with 6+ messages)")
    print(f"Building category profiles from {sum(1 for i in inventory if i['category'] != 'uncategorized')} categorized conversations...")

    profiles, idf = build_category_profiles(inventory, conv_by_id)

    for cat, profile in sorted(profiles.items()):
        top5 = sorted(profile.items(), key=lambda x: -x[1])[:5]
        words_str = ", ".join(w for w, _ in top5)
        print(f"  {cat:20s} ({len(profile)} features) top: {words_str}")

    # Build flat keyword lists per category from config (for anchor check)
    categories = config.get("categories", {})
    cat_keywords = {}
    for cat, keywords in categories.items():
        flat = []
        if isinstance(keywords, dict):
            flat.extend(kw.lower() for kw in keywords.get("strong", []))
            flat.extend(kw.lower() for kw in keywords.get("medium", []))
        else:
            flat.extend(kw.lower() for kw in keywords)
        cat_keywords[cat] = flat

    # Compute average scores for known-good items per category
    # This tells us "what does a real security conversation score like?"
    cat_avg_scores = {}
    cat_score_lists = defaultdict(list)
    for item in inventory:
        if item["category"] == "uncategorized":
            continue
        conv = conv_by_id.get(item["id"])
        if not conv:
            continue
        messages = extract_messages_sorted(conv)
        all_text = item["title"].lower() + " "
        all_text += " ".join(text[:1000] for _, _, text in messages)
        words = set(tokenize(all_text))
        cat = item["category"]
        profile = profiles.get(cat, {})
        if not profile:
            continue
        score = sum(profile.get(w, 0) for w in words)
        magnitude = math.sqrt(sum(v ** 2 for v in profile.values()))
        if magnitude > 0:
            cat_score_lists[cat].append(score / magnitude)

    for cat, scores in cat_score_lists.items():
        cat_avg_scores[cat] = sum(scores) / len(scores) if scores else 1.0
        print(f"  {cat:20s} avg score: {cat_avg_scores[cat]:.3f}")

    # Classify uncategorized conversations
    classified = 0
    low_confidence = 0
    no_match = 0

    for item in inventory:
        if item["category"] != "uncategorized":
            continue

        conv = conv_by_id.get(item["id"])
        if not conv:
            continue

        cat, confidence, top_score = classify_conversation(
            conv, item["title"], profiles, idf, cat_avg_scores,
            cat_keywords, min_confidence=args.threshold
        )

        if cat and confidence >= args.threshold:
            item["category"] = cat
            item["classified_by"] = "statistical"
            item["classify_confidence"] = round(confidence, 3)
            classified += 1
        elif cat:
            low_confidence += 1
        else:
            no_match += 1

    # Stats
    final_uncat = sum(1 for i in inventory if i["category"] == "uncategorized")
    final_review = sum(
        1 for i in inventory
        if i["category"] == "uncategorized" and i["triage"] == "review"
    )
    total_review = sum(1 for i in inventory if i["triage"] == "review")

    cat_counts = defaultdict(int)
    for item in inventory:
        cat_counts[item["category"]] += 1

    print(f"\nClassified: {classified}")
    print(f"Low confidence (kept uncategorized): {low_confidence}")
    print(f"No match: {no_match}")

    print(f"\n=== Final Category Distribution ===")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:30s} {count:4d}")

    pct = (final_review / total_review * 100) if total_review > 0 else 0
    print(f"\nUncategorized with 6+ msgs: {final_review}/{total_review} ({pct:.1f}%)")
    target = "ACHIEVED" if pct < 5 else f"target <5%"
    print(f"Target: <5% uncategorized among reviewable conversations — {target}")

    # Discover potential new categories from remaining uncategorized
    remaining = [
        i for i in inventory
        if i["category"] == "uncategorized" and i["triage"] != "skip"
    ]
    if remaining:
        discover_categories(remaining, conv_by_id)

    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)

    print(f"\nSaved updated {inv_path}")


def discover_categories(uncategorized_items, conv_by_id):
    """Find natural topic clusters in uncategorized conversations.

    Groups conversations by shared distinctive vocabulary and suggests
    potential new categories the user could add to their config.
    Only considers topic-specific words (min 4 chars, not in stop words).
    """
    # Build word sets per conversation (topic words only)
    item_words = {}
    word_items = defaultdict(set)

    for idx, item in enumerate(uncategorized_items):
        conv = conv_by_id.get(item["id"])
        if not conv:
            continue
        messages = extract_messages_sorted(conv)
        all_text = item["title"].lower() + " "
        all_text += " ".join(text[:800] for _, _, text in messages[:10])
        words = set(tokenize(all_text))
        # Only keep words that are specific enough to define a topic
        words = {w for w in words if len(w) >= 4 and w not in GENERIC_WORDS}
        item_words[idx] = words
        for w in words:
            word_items[w].add(idx)

    n_items = len(item_words)
    if n_items < 10:
        return

    # Find words that appear in 4+ items but less than 20% of items
    cluster_words = {
        w: items for w, items in word_items.items()
        if 4 <= len(items) <= n_items * 0.20
    }

    if not cluster_words:
        return

    # Greedy clustering: find groups of items sharing specific vocabulary
    used_items = set()
    clusters = []

    for word, items in sorted(cluster_words.items(), key=lambda x: -len(x[1])):
        available = items - used_items
        if len(available) < 5:
            continue

        # Find co-occurring topic words in these items
        shared_words = Counter()
        for idx in available:
            for w in item_words.get(idx, set()):
                if w in cluster_words:
                    shared_words[w] += 1

        # Topic words must appear in at least 60% of the cluster
        min_shared = len(available) * 0.6
        topic_words = [w for w, c in shared_words.most_common(15) if c >= min_shared]

        # Need at least 3 meaningful topic words to form a cluster
        if len(topic_words) < 3:
            continue

        cluster_titles = [uncategorized_items[idx]["title"] for idx in available]
        clusters.append({
            "keywords": topic_words[:8],
            "count": len(available),
            "sample_titles": cluster_titles[:5],
        })
        used_items.update(available)

    if clusters:
        # Only show clusters with meaningful keywords
        meaningful = [c for c in clusters if any(len(kw) >= 5 for kw in c["keywords"])]
        if meaningful:
            print(f"\n--- Potential new categories discovered ---")
            print(f"(Clusters of uncategorized conversations sharing vocabulary)\n")
            for i, cluster in enumerate(sorted(meaningful, key=lambda x: -x["count"]), 1):
                kw_str = ", ".join(cluster["keywords"][:6])
                print(f"  Cluster {i} ({cluster['count']} conversations):")
                print(f"    Keywords: {kw_str}")
                for title in cluster["sample_titles"][:3]:
                    print(f"    - {title[:70]}")
                print()
            print(f"  To use: add these as new categories in your config.json")
            print(f"  with the suggested keywords as 'strong' entries.")


if __name__ == "__main__":
    main()
