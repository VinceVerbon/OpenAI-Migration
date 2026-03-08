"""
Step 2: Deeper re-categorization.

Reads actual conversation content (first 3 user messages) instead of just
titles, improving category accuracy from ~70% to ~90%.

Usage: python 02_rescan.py [--config config.json]
"""
import json
import os
import sys
import argparse
from collections import defaultdict

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


def extract_messages(conv):
    messages = []
    mapping = conv.get("mapping", {})
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


def categorize_deep(search_text, categories):
    """Keyword match with flat or {strong, medium} keyword dicts."""
    best_score = 0
    best_cat = "uncategorized"
    for cat, keywords in categories.items():
        if isinstance(keywords, dict):
            kw_list = keywords.get("strong", []) + keywords.get("medium", [])
        else:
            kw_list = keywords
        score = sum(1 for kw in kw_list if kw in search_text)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat if best_score > 0 else None


def main():
    parser = argparse.ArgumentParser(description="Re-categorize using deeper content analysis")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    backup_dir = config["backup_dir"]
    categories = config.get("categories", {})
    triage_config = config.get("triage", {})

    inv_path = os.path.join(os.path.dirname(args.config) or ".", "inventory.json")
    with open(inv_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    print(f"Loading conversations from: {backup_dir}")
    all_convs = load_conversations(backup_dir)
    conv_by_id = {c.get("id", ""): c for c in all_convs}

    outdated_indicators = triage_config.get("outdated_indicators", {})
    howto_signals = triage_config.get("howto_signals", [])
    outdated_before = triage_config.get("outdated_before", "2024-06-01")

    improved = 0

    for item in inventory:
        if item["triage"] == "done":
            continue

        conv = conv_by_id.get(item["id"])
        if not conv:
            continue

        messages = extract_messages(conv)

        # Build search text from title + first 3 user messages
        user_texts = [text for _, role, text in messages if role == "user"][:3]
        search_text = (item["title"] + " " + " ".join(user_texts)).lower()

        # Re-categorize
        new_cat = categorize_deep(search_text, categories)
        if new_cat and (item["category"] == "uncategorized" or new_cat != item["category"]):
            old_cat = item["category"]
            item["category"] = new_cat
            if old_cat == "uncategorized":
                improved += 1

        # Outdated detection — generic how-to in tech categories before cutoff date
        if item["triage"] in ("review", "skip-candidate") and item["message_count"] <= 20:
            for indicator, reason in outdated_indicators.items():
                if indicator in search_text and any(s in search_text for s in howto_signals):
                    item["outdated_reason"] = f"{reason} (current knowledge supersedes)"
                    item["triage"] = "outdated"
                    break

        # Old generic tech Q&A
        if (item["triage"] in ("review", "skip-candidate")
                and item["date"] < outdated_before
                and item["message_count"] <= 10):
            generic = ["what is", "explain", "how to", "difference between"]
            tech = list(outdated_indicators.keys())
            if any(g in search_text for g in generic) and any(t in search_text for t in tech):
                item["outdated_reason"] = "Generic tech Q&A (current knowledge supersedes)"
                item["triage"] = "outdated"

    # Stats
    cat_counts = defaultdict(int)
    triage_counts = defaultdict(int)
    for item in inventory:
        cat_counts[item["category"]] += 1
        triage_counts[item["triage"]] += 1

    print(f"Improved categorization for {improved} previously uncategorized chats")
    print("\n=== Category Distribution ===")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:30s} {count:4d}")

    print("\n=== Triage Distribution ===")
    for tri, count in sorted(triage_counts.items(), key=lambda x: -x[1]):
        print(f"  {tri:20s} {count:4d}")

    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)

    print(f"\nUpdated {inv_path}")


if __name__ == "__main__":
    main()
