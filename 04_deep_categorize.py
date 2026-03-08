"""
Step 4: Deep categorization of remaining uncategorized conversations.

Uses weighted keyword scoring on actual message content (first 5 user + 3
assistant messages) with a confidence threshold.

Usage: python 04_deep_categorize.py [--config config.json]
"""
import json
import os
import sys
import argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")


def load_conversations(backup_dir):
    all_convs = []
    for i in range(100):
        path = os.path.join(backup_dir, f"conversations-{i:03d}.json")
        if not os.path.exists(path):
            break
        with open(path, "r", encoding="utf-8") as f:
            all_convs.extend(json.load(f))
    return all_convs


def extract_analysis_text(conv, title, max_user=5, max_asst=3):
    """Build search text from title + first N user/assistant messages."""
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

    parts = [title]
    user_count = asst_count = 0
    for _, role, text in messages:
        if role == "user" and user_count < max_user:
            parts.append(text[:500])
            user_count += 1
        elif role == "assistant" and asst_count < max_asst:
            parts.append(text[:300])
            asst_count += 1
        if user_count >= max_user and asst_count >= max_asst:
            break

    return " ".join(parts).lower()


def score_categories(search_text, categories, min_confidence=2):
    """Weighted scoring: strong keywords = 3 points, medium = 1 point."""
    scores = {}
    for cat, keywords in categories.items():
        if isinstance(keywords, dict):
            strong = keywords.get("strong", [])
            medium = keywords.get("medium", [])
        else:
            strong = []
            medium = keywords

        strong_hits = sum(1 for kw in strong if kw in search_text)
        medium_hits = sum(1 for kw in medium if kw in search_text)
        score = strong_hits * 3 + medium_hits
        if score >= min_confidence:
            scores[cat] = score

    if scores:
        return max(scores, key=scores.get)
    return None


def main():
    parser = argparse.ArgumentParser(description="Deep categorize uncategorized conversations")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    backup_dir = config["backup_dir"]
    categories = config.get("categories", {})
    triage_config = config.get("triage", {})

    base_dir = os.path.dirname(args.config) or "."
    inv_path = os.path.join(base_dir, "inventory.json")

    with open(inv_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    print(f"Loading conversations from: {backup_dir}")
    all_convs = load_conversations(backup_dir)
    conv_by_id = {c.get("id", ""): c for c in all_convs}

    outdated_indicators = triage_config.get("outdated_indicators", {})
    howto_signals = triage_config.get("howto_signals", [])
    outdated_before = triage_config.get("outdated_before", "2024-06-01")

    recategorized = 0
    still_uncategorized = 0

    for item in inventory:
        if item["category"] != "uncategorized":
            continue

        conv = conv_by_id.get(item["id"])
        if not conv:
            still_uncategorized += 1
            continue

        search_text = extract_analysis_text(conv, item["title"])
        best_cat = score_categories(search_text, categories)

        if best_cat:
            item["category"] = best_cat
            recategorized += 1
        else:
            still_uncategorized += 1

    # Additional outdated detection on newly categorized items
    tech_categories = {"infrastructure", "development", "networking", "hardware"}
    for item in inventory:
        if item["triage"] in ("done", "outdated"):
            continue
        if item["category"] in tech_categories:
            if item["message_count"] <= 10 and item["date"] < outdated_before:
                conv = conv_by_id.get(item["id"])
                if not conv:
                    continue
                search_text = extract_analysis_text(conv, item["title"])
                howto = howto_signals + ["what is", "explain", "difference between"]
                tech = list(outdated_indicators.keys())
                if any(h in search_text for h in howto) and any(t in search_text for t in tech):
                    item["outdated_reason"] = "Generic tech Q&A (current knowledge supersedes)"
                    item["triage"] = "outdated"

    # Stats
    cat_counts = defaultdict(int)
    triage_counts = defaultdict(int)
    for item in inventory:
        cat_counts[item["category"]] += 1
        triage_counts[item["triage"]] += 1

    print(f"Recategorized: {recategorized}")
    print(f"Still uncategorized: {still_uncategorized}")
    print("\n=== Final Category Distribution ===")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:30s} {count:4d}")
    print("\n=== Final Triage Distribution ===")
    for tri, count in sorted(triage_counts.items(), key=lambda x: -x[1]):
        print(f"  {tri:20s} {count:4d}")

    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)

    print(f"\nSaved updated {inv_path}")


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()
