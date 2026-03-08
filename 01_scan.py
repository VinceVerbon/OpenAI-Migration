"""
Step 1: Scan & initial categorization.

Parses all conversations-*.json files from an OpenAI data export and builds
a flat inventory with category assignments and triage decisions.

Usage: python 01_scan.py [--config config.json]
"""
import json
import os
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from shared import keyword_in_text, detect_language

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
    """Extract sorted (timestamp, role, text) tuples from a conversation."""
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


def detect_custom_gpt(conv):
    """Check if conversation used a Custom GPT (long system message)."""
    mapping = conv.get("mapping", {})
    for node in mapping.values():
        msg = node.get("message")
        if msg and msg.get("author", {}).get("role") == "system":
            parts = msg.get("content", {}).get("parts", [])
            for p in parts:
                if isinstance(p, str) and len(p) > 100:
                    return True
    return False


def categorize(search_text, categories, min_score=1):
    """Simple keyword match — returns best category or 'uncategorized'.

    min_score: minimum keyword matches required.
        1 when matching against abstract text (already topically precise).
        2 when matching against raw conversation text (needs stronger evidence).
    """
    best_score = 0
    best_cat = "uncategorized"
    for cat, keywords in categories.items():
        # Support both flat lists and {strong, medium} dicts
        if isinstance(keywords, dict):
            kw_list = keywords.get("strong", []) + keywords.get("medium", [])
        else:
            kw_list = keywords
        score = sum(1 for kw in kw_list if keyword_in_text(kw, search_text))
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat if best_score >= min_score else "uncategorized"


def check_outdated(search_text, triage_config):
    """Check if conversation is outdated how-to content."""
    indicators = triage_config.get("outdated_indicators", {})
    signals = triage_config.get("howto_signals", [])
    for indicator, reason in indicators.items():
        if indicator in search_text and any(s in search_text for s in signals):
            return f"{reason} (current knowledge supersedes)"
    return None


def main():
    parser = argparse.ArgumentParser(description="Scan OpenAI export and build inventory")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    backup_dir = config["backup_dir"]
    categories = config.get("categories", {})
    triage_config = config.get("triage", {})
    already_processed = set(config.get("already_processed", []))

    skip_threshold = triage_config.get("skip_threshold", 2)
    skip_candidate_threshold = triage_config.get("skip_candidate_threshold", 5)

    # Load cluster membership (direct conv_id → category from discovery)
    base_dir = os.path.dirname(args.config) or "."
    membership_path = os.path.join(base_dir, "cluster_membership.json")
    membership = {}
    if os.path.exists(membership_path):
        with open(membership_path, "r", encoding="utf-8") as f:
            membership = json.load(f)
        print(f"Using cluster membership ({len(membership)} direct assignments)")

    # Load abstracts as fallback for non-clustered conversations
    abstracts_path = os.path.join(base_dir, "abstracts.json")
    abstracts = {}
    if os.path.exists(abstracts_path):
        with open(abstracts_path, "r", encoding="utf-8") as f:
            abstracts = json.load(f)
        print(f"Using AI-generated abstracts ({len(abstracts)} labels)")

    print(f"Loading conversations from: {backup_dir}")
    all_convs = load_conversations(backup_dir)
    print(f"Total conversations: {len(all_convs)}")

    inventory = []

    for conv in all_convs:
        title = conv.get("title", "") or "Untitled"
        conv_id = conv.get("id", "")
        create_time = conv.get("create_time", 0) or 0

        messages = extract_messages(conv)
        msg_count = len(messages)

        # First user message preview
        first_user = ""
        for _, role, text in messages:
            if role == "user":
                first_user = text[:500]
                break

        # Date
        dt = datetime.fromtimestamp(create_time) if create_time else None
        date_str = dt.strftime("%Y-%m-%d") if dt else "unknown"

        # Language detection from title + first user messages
        user_text = " ".join(
            text[:500] for _, role, text in messages[:5] if role == "user"
        )
        language = detect_language(title + " " + user_text)

        search_text = ""
        if title.lower().strip() in already_processed:
            category = "already-processed"
            triage = "done"
        elif conv_id in membership:
            # Direct assignment from discovery clustering — most reliable
            category = membership[conv_id]
            if msg_count <= skip_threshold:
                triage = "skip"
            elif msg_count <= skip_candidate_threshold:
                triage = "skip-candidate"
            else:
                triage = "review"
        else:
            # Fallback: keyword matching against abstract or conversation text
            abstract = abstracts.get(conv_id, "")
            if abstract:
                search_text = (title + " " + abstract).lower()
                min_score = 2  # Even abstracts need 2+ keyword matches
            else:
                search_text = (title + " " + first_user).lower()
                min_score = 2
            category = categorize(search_text, categories, min_score=min_score)

            # Triage
            if msg_count <= skip_threshold:
                triage = "skip"
            elif msg_count <= skip_candidate_threshold:
                triage = "skip-candidate"
            else:
                triage = "review"

        # Outdated check
        outdated_reason = None
        if triage in ("review", "skip-candidate"):
            if not search_text:
                search_text = (title + " " + first_user).lower()
            outdated_reason = check_outdated(search_text, triage_config)
            if outdated_reason:
                triage = "outdated"

        inventory.append({
            "id": conv_id,
            "title": title,
            "date": date_str,
            "message_count": msg_count,
            "language": language,
            "category": category,
            "triage": triage,
            "outdated_reason": outdated_reason,
            "first_user_preview": first_user[:200].replace("\n", " "),
            "custom_gpt": detect_custom_gpt(conv),
        })

    # Sort by date
    inventory.sort(key=lambda x: x["date"])

    # Stats
    cat_counts = defaultdict(int)
    triage_counts = defaultdict(int)
    for item in inventory:
        cat_counts[item["category"]] += 1
        triage_counts[item["triage"]] += 1

    print("\n=== Category Distribution ===")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:30s} {count:4d}")

    print("\n=== Triage Distribution ===")
    for tri, count in sorted(triage_counts.items(), key=lambda x: -x[1]):
        print(f"  {tri:20s} {count:4d}")

    # Save
    out_path = os.path.join(os.path.dirname(args.config) or ".", "inventory.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {out_path} with {len(inventory)} entries")


if __name__ == "__main__":
    main()
