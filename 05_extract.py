"""
Step 5: Extract valuable conversation content per category.

For each category, reads conversations with triage=review or skip-candidate
and extracts the key content into structured JSON files. These files are
then fed to an AI for distillation (Step 6).

Usage: python 05_extract.py [--config config.json]
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


def build_extract_entry(item, conv_by_id, include_language=False):
    """Build a single extract entry from an inventory item.

    Args:
        item: Inventory entry dict.
        conv_by_id: Dict mapping conversation id to raw conversation data.
        include_language: If True, include the "language" field in the entry.

    Returns:
        Extract entry dict, or None if conversation not found.
    """
    conv = conv_by_id.get(item["id"])
    if not conv:
        return None

    messages = extract_messages(conv)

    # First 3 user messages, first 2 assistant responses
    user_msgs = []
    asst_msgs = []
    for _, role, text in messages:
        if role == "user" and len(user_msgs) < 3:
            user_msgs.append(text[:1000])
        elif role == "assistant" and len(asst_msgs) < 2:
            asst_msgs.append(text[:1000])

    # Last user message for context in longer chats
    last_user = ""
    if item["message_count"] > 6:
        for _, role, text in reversed(messages):
            if role == "user":
                last_user = text[:500]
                break

    entry = {
        "title": item["title"],
        "date": item["date"],
        "message_count": item["message_count"],
        "triage": item["triage"],
        "custom_gpt": item.get("custom_gpt", False),
        "user_messages": user_msgs,
        "assistant_responses": asst_msgs,
        "last_user_message": last_user,
    }
    if include_language:
        entry["language"] = item.get("language", "unknown")
    return entry


def write_extract(path, data, meta=None):
    """Write extract data to a JSON file, optionally with a _meta header.

    Args:
        path: Output file path.
        data: List of extract entries.
        meta: Optional dict to include as "_meta" top-level key.
    """
    if meta:
        output = {"_meta": meta, "conversations": data}
    else:
        output = data
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Extract conversation content per category")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    backup_dir = config["backup_dir"]
    language_strategy = config.get("language_strategy", "unified")
    target_language = config.get("target_language", "en")

    base_dir = os.path.dirname(args.config) or "."
    inv_path = os.path.join(base_dir, "inventory.json")
    extracts_dir = os.path.join(base_dir, "category_extracts")

    with open(inv_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    print(f"Loading conversations from: {backup_dir}")
    print(f"Language strategy: {language_strategy}", end="")
    if language_strategy in ("unified", "translate", "multilingual"):
        print(f" (target: {target_language})")
    else:
        print()

    all_convs = load_conversations(backup_dir)
    conv_by_id = {c.get("id", ""): c for c in all_convs}

    os.makedirs(extracts_dir, exist_ok=True)

    # Get all categories except meta ones
    skip_categories = {"already-processed", "uncategorized"}
    categories_to_process = sorted(set(
        i["category"] for i in inventory
        if i["category"] not in skip_categories
    ))

    for cat in categories_to_process:
        items = [
            i for i in inventory
            if i["category"] == cat and i["triage"] not in ("skip", "outdated", "done")
        ]
        if not items:
            continue

        items.sort(key=lambda x: x["date"])

        # Build extract entries for this category
        cat_data = []
        for item in items:
            entry = build_extract_entry(item, conv_by_id, include_language=True)
            if entry:
                cat_data.append(entry)

        if not cat_data:
            continue

        if language_strategy == "preserve":
            # Split output by detected language
            by_lang = defaultdict(list)
            for entry in cat_data:
                by_lang[entry.get("language", "unknown")].append(entry)

            for lang, lang_data in by_lang.items():
                if lang == "unknown":
                    output_path = os.path.join(extracts_dir, f"{cat}.json")
                else:
                    output_path = os.path.join(extracts_dir, f"{cat}-{lang}.json")

                meta = {
                    "language_strategy": "preserve",
                    "language": lang,
                    "instruction": f"Content is in {lang}. Preserve the original language.",
                }
                write_extract(output_path, lang_data, meta=meta)
                total_msgs = sum(c["message_count"] for c in lang_data)
                suffix = f" ({lang})" if lang != "unknown" else " (unknown lang)"
                print(f"  {cat}{suffix}: {len(lang_data)} chats, {total_msgs} total messages")

        elif language_strategy == "translate":
            # Single file, instruct AI to translate everything to target language
            meta = {
                "language_strategy": "translate",
                "target_language": target_language,
                "instruction": (
                    f"Translate all content to {target_language} during distillation. "
                    f"Output knowledge files must be entirely in {target_language}."
                ),
            }
            output_path = os.path.join(extracts_dir, f"{cat}.json")
            write_extract(output_path, cat_data, meta=meta)
            total_msgs = sum(c["message_count"] for c in cat_data)
            print(f"  {cat}: {len(cat_data)} chats, {total_msgs} total messages")

        elif language_strategy == "multilingual":
            # Single file, instruct AI to include both original + translation
            meta = {
                "language_strategy": "multilingual",
                "target_language": target_language,
                "instruction": (
                    f"For each knowledge item, include both the original language "
                    f"content and a {target_language} translation."
                ),
            }
            output_path = os.path.join(extracts_dir, f"{cat}.json")
            write_extract(output_path, cat_data, meta=meta)
            total_msgs = sum(c["message_count"] for c in cat_data)
            print(f"  {cat}: {len(cat_data)} chats, {total_msgs} total messages")

        else:
            # "unified" — translate everything to auto-detected dominant language
            meta = {
                "language_strategy": "unified",
                "target_language": target_language,
                "instruction": (
                    f"Translate all content to {target_language} during distillation. "
                    f"This language was auto-detected as the dominant language in the export."
                ),
            }
            output_path = os.path.join(extracts_dir, f"{cat}.json")
            write_extract(output_path, cat_data, meta=meta)
            total_msgs = sum(c["message_count"] for c in cat_data)
            print(f"  {cat}: {len(cat_data)} chats, {total_msgs} total messages")

    # Also extract uncategorized for reference
    uncat_items = [
        i for i in inventory
        if i["category"] == "uncategorized" and i["triage"] != "skip"
    ]
    if uncat_items:
        uncat_data = []
        for item in sorted(uncat_items, key=lambda x: x["date"]):
            conv = conv_by_id.get(item["id"])
            if not conv:
                continue
            messages = extract_messages(conv)
            user_msgs = [text[:800] for _, role, text in messages if role == "user"][:2]
            uncat_data.append({
                "title": item["title"],
                "date": item["date"],
                "message_count": item["message_count"],
                "triage": item["triage"],
                "language": item.get("language", "unknown"),
                "user_messages": user_msgs,
            })

        output_path = os.path.join(extracts_dir, "uncategorized.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(uncat_data, f, indent=2, ensure_ascii=False)
        print(f"  uncategorized: {len(uncat_data)} chats")

    print(f"\nExtracts saved to {extracts_dir}/")
    print("Feed these to an AI with the distillation prompt from docs/pipeline.md")


if __name__ == "__main__":
    main()
