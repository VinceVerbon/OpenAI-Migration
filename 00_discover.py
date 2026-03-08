"""
Step 0: Discover what's in your ChatGPT export.

Scans all conversations with ZERO configuration needed. Detects languages,
finds natural topic clusters, and generates a config.json ready for the
rest of the pipeline.

Can run interactively (asks questions) or config-driven (reads answers
from a minimal seed config).

Usage:
  Interactive:    python 00_discover.py --backup /path/to/export
  Config-driven:  python 00_discover.py --seed seed.json

Seed config format (all fields optional except backup_dir):
{
  "backup_dir": "/path/to/OpenAI-Export",

  // Language strategy for output knowledge files (required):
  //   "unified"      - translate to dominant language (auto-detected, no target needed)
  //   "preserve"     - split files by language (e.g. infra-en.json, infra-nl.json)
  //   "translate"    - translate everything to target_language (requires target_language)
  //   "multilingual" - include both original + translated (requires target_language)
  "language_strategy": "translate",

  // Target language when strategy is "translate" or "multilingual"
  // Use ISO 639-1 code: "en", "nl", "de", "fr", "es", etc.
  // Not needed for "unified" (auto-detected) or "preserve"
  "target_language": "en",

  // Minimum cluster size to propose as category (default: 5)
  "min_cluster_size": 5,

  // Triage settings
  "triage": {
    "skip_threshold": 2,
    "skip_candidate_threshold": 5,
    "outdated_before": "2024-06-01"
  }
}
"""
import json
import os
import sys
import re
import argparse
import math
from collections import Counter, defaultdict
from datetime import datetime
from shared import tokenize, STOP_WORDS, GENERIC_WORDS, detect_language, LANG_MARKERS, LANG_NAMES

sys.stdout.reconfigure(encoding="utf-8")

# ─── Conversation Parsing ────────────────────────────────────────────────────

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
    """Extract sorted (timestamp, role, text) from conversation."""
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


def detect_custom_gpt(conv):
    """Check if conversation used a Custom GPT."""
    mapping = conv.get("mapping", {})
    for node in mapping.values():
        msg = node.get("message")
        if msg and msg.get("author", {}).get("role") == "system":
            parts = msg.get("content", {}).get("parts", [])
            for p in parts:
                if isinstance(p, str) and len(p) > 100:
                    return True
    return False


# ─── Topic Clustering ────────────────────────────────────────────────────────

def discover_clusters(conversations, min_cluster_size=5):
    """Find natural topic clusters using IDF-weighted distinctiveness.

    Instead of raw word frequency, scores words by how distinctive they are
    (appear in a small fraction of conversations). Then clusters conversations
    around these distinctive anchor words.

    Returns list of clusters, each with keywords, count, and sample titles.
    """
    # Build word sets per conversation
    item_words = {}
    word_items = defaultdict(set)

    for idx, (conv, title) in enumerate(conversations):
        messages = extract_messages(conv)
        all_text = title.lower() + " "
        all_text += " ".join(text[:800] for _, _, text in messages[:10])
        words = set(
            w for w in tokenize(all_text)
            if len(w) >= 4 and w not in GENERIC_WORDS
        )
        item_words[idx] = words
        for w in words:
            word_items[w].add(idx)

    n_items = len(item_words)
    if n_items < min_cluster_size * 2:
        return []

    # Compute IDF for each word
    word_idf = {}
    for w, items in word_items.items():
        df = len(items)
        # Only consider words in enough items but not too many
        # Strict ceiling: words in >5% of conversations are too generic
        if df < min_cluster_size or df > n_items * 0.05:
            continue
        word_idf[w] = math.log(n_items / (1 + df))

    if not word_idf:
        return []

    # Sort candidate anchor words by IDF (most distinctive first is wrong —
    # we want words that are distinctive BUT appear in enough conversations).
    # Score = df * idf² — balances frequency with distinctiveness.
    anchor_scores = {}
    for w, idf_val in word_idf.items():
        df = len(word_items[w])
        anchor_scores[w] = df * idf_val * idf_val

    # Greedy clustering
    used_items = set()
    clusters = []

    for word, _ in sorted(anchor_scores.items(), key=lambda x: -x[1]):
        available = word_items[word] - used_items
        if len(available) < min_cluster_size:
            continue

        # Find co-occurring distinctive words in these items
        shared_words = Counter()
        for idx in available:
            for w in item_words.get(idx, set()):
                if w in word_idf:
                    shared_words[w] += 1

        # Keep words in at least 40% of cluster
        min_shared = len(available) * 0.4
        co_occurring = {
            w: c for w, c in shared_words.items()
            if c >= min_shared
        }

        if len(co_occurring) < 3:
            continue

        # Rank keywords by distinctiveness within this cluster
        # (fraction in cluster vs fraction in corpus)
        keyword_scores = []
        for w, cluster_count in co_occurring.items():
            cluster_frac = cluster_count / len(available)
            corpus_frac = len(word_items[w]) / n_items
            # Distinctiveness: how much more this word appears in the cluster
            # than in the overall corpus
            if corpus_frac > 0:
                lift = cluster_frac / corpus_frac
            else:
                lift = 0
            # Only keep words with meaningful lift (>3x more likely in cluster)
            if lift >= 3.0:
                keyword_scores.append((w, lift))

        keyword_scores.sort(key=lambda x: -x[1])
        topic_words = [w for w, _ in keyword_scores[:10]]

        # Need at least 3 distinctive keywords, with 2+ being domain-specific
        # (length >= 6 chars — short words tend to be function words)
        domain_words = [w for w in topic_words if len(w) >= 6]
        if len(topic_words) < 3 or len(domain_words) < 2:
            continue

        # Get sample titles
        titles = []
        for idx in sorted(available):
            titles.append(conversations[idx][1])
            if len(titles) >= 5:
                break

        clusters.append({
            "keywords": topic_words,
            "count": len(available),
            "sample_titles": titles,
            "item_indices": available,
        })
        used_items.update(available)

    # Post-filter: drop clusters where keywords lack domain specificity.
    GENERIC_SUFFIXES = {
        "ally", "tion", "ment", "ness", "lijk", "isch", "atie", "baar",
        "elen", "igen", "eren",
    }
    filtered = []
    for cluster in clusters:
        domain_count = 0
        for w in cluster["keywords"][:5]:
            if len(w) >= 6 and not any(w.endswith(s) for s in GENERIC_SUFFIXES):
                domain_count += 1
        if domain_count >= 2:
            filtered.append(cluster)

    # Merge clusters that share keywords (e.g., both about Docker/electronics)
    merged = []
    skip = set()
    for i, c1 in enumerate(filtered):
        if i in skip:
            continue
        kw1 = set(c1["keywords"])
        for j, c2 in enumerate(filtered):
            if j <= i or j in skip:
                continue
            kw2 = set(c2["keywords"])
            overlap = len(kw1 & kw2)
            # Merge if they share 2+ keywords or 50%+ of the smaller cluster's keywords
            if overlap >= 2 or (overlap >= 1 and overlap / min(len(kw1), len(kw2)) >= 0.5):
                # Merge c2 into c1
                c1["count"] += c2["count"]
                c1["item_indices"] = c1["item_indices"] | c2["item_indices"]
                # Combine keywords (deduplicate, keep order)
                for w in c2["keywords"]:
                    if w not in kw1:
                        c1["keywords"].append(w)
                        kw1.add(w)
                c1["sample_titles"] = c1["sample_titles"][:5]
                skip.add(j)
        merged.append(c1)

    return sorted(merged, key=lambda x: -x["count"])


# ─── Interactive Prompts ─────────────────────────────────────────────────────

def ask_choice(prompt, options, default=None):
    """Ask user to pick from options. Returns the chosen value."""
    print(f"\n{prompt}")
    for i, (key, label) in enumerate(options, 1):
        marker = " (default)" if key == default else ""
        print(f"  {i}. {label}{marker}")

    while True:
        raw = input(f"\nChoice [1-{len(options)}]: ").strip()
        if not raw and default:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f"  Please enter a number 1-{len(options)}")


def ask_yes_no(prompt, default=True):
    """Ask a yes/no question."""
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix}: ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def ask_text(prompt, default=""):
    """Ask for text input with optional default."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw if raw else default


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Discover what's in your ChatGPT export and generate config"
    )
    parser.add_argument("--backup", help="Path to unzipped OpenAI export directory")
    parser.add_argument("--seed", help="Path to seed config (skips interactive prompts)")
    parser.add_argument("--output", help="Where to write generated config (default: ./config.json)")
    args = parser.parse_args()

    # Load seed config if provided
    seed = {}
    if args.seed:
        with open(args.seed, "r", encoding="utf-8") as f:
            seed = json.load(f)

    backup_dir = args.backup or seed.get("backup_dir")
    if not backup_dir:
        print("ERROR: Provide --backup /path/to/export or a seed config with backup_dir")
        sys.exit(1)

    if not os.path.exists(backup_dir):
        print(f"ERROR: Directory not found: {backup_dir}")
        sys.exit(1)

    output_path = args.output or os.path.join(".", "config.json")
    interactive = not args.seed

    # ── Phase 1: Scan ────────────────────────────────────────────────────

    print("=" * 60)
    print("AIKnowledgeDistill — Discovery")
    print("=" * 60)
    print(f"\nScanning: {backup_dir}")

    all_convs = load_conversations(backup_dir)
    if not all_convs:
        print("ERROR: No conversations-*.json files found.")
        sys.exit(1)

    print(f"Found {len(all_convs)} conversations\n")

    # ── Phase 2: Analyze ─────────────────────────────────────────────────

    print("Analyzing conversations...")

    conv_data = []  # (conv, title, msg_count, date, language, custom_gpt)
    lang_counts = Counter()
    date_range = [None, None]
    msg_count_dist = Counter()  # bucketed
    custom_gpt_count = 0

    for conv in all_convs:
        title = conv.get("title", "") or "Untitled"
        messages = extract_messages(conv)
        msg_count = len(messages)
        create_time = conv.get("create_time", 0) or 0
        dt = datetime.fromtimestamp(create_time) if create_time else None
        date_str = dt.strftime("%Y-%m-%d") if dt else "unknown"
        is_custom_gpt = detect_custom_gpt(conv)

        # Language detection from first 3 user messages
        user_text = " ".join(
            text[:500] for _, role, text in messages[:5] if role == "user"
        )
        lang = detect_language(title + " " + user_text)

        lang_counts[lang] += 1
        if is_custom_gpt:
            custom_gpt_count += 1

        if dt:
            if date_range[0] is None or dt < date_range[0]:
                date_range[0] = dt
            if date_range[1] is None or dt > date_range[1]:
                date_range[1] = dt

        # Message count buckets
        if msg_count <= 2:
            msg_count_dist["1-2 (throwaway)"] += 1
        elif msg_count <= 5:
            msg_count_dist["3-5 (short)"] += 1
        elif msg_count <= 20:
            msg_count_dist["6-20 (medium)"] += 1
        elif msg_count <= 50:
            msg_count_dist["21-50 (long)"] += 1
        else:
            msg_count_dist["50+ (extended)"] += 1

        conv_data.append({
            "conv": conv,
            "title": title,
            "msg_count": msg_count,
            "date": date_str,
            "language": lang,
            "custom_gpt": is_custom_gpt,
        })

    # ── Phase 3: Report ──────────────────────────────────────────────────

    print(f"\n{'─' * 60}")
    print(f"YOUR EXPORT AT A GLANCE")
    print(f"{'─' * 60}")

    if date_range[0] and date_range[1]:
        print(f"\nDate range:    {date_range[0].strftime('%B %Y')} — {date_range[1].strftime('%B %Y')}")
    print(f"Conversations: {len(all_convs)}")
    print(f"Custom GPTs:   {custom_gpt_count}")

    print(f"\nConversation lengths:")
    for bucket in ["1-2 (throwaway)", "3-5 (short)", "6-20 (medium)",
                    "21-50 (long)", "50+ (extended)"]:
        count = msg_count_dist.get(bucket, 0)
        pct = 100 * count / len(all_convs)
        bar = "█" * int(pct / 2)
        print(f"  {bucket:25s} {count:5d} ({pct:4.1f}%) {bar}")

    print(f"\nLanguages detected:")
    for lang, count in lang_counts.most_common():
        pct = 100 * count / len(all_convs)
        name = LANG_NAMES.get(lang, lang)
        print(f"  {name:20s} {count:5d} ({pct:4.1f}%)")

    # ── Phase 4: Topic Discovery ─────────────────────────────────────────

    print(f"\n{'─' * 60}")
    print(f"DISCOVERING TOPICS...")
    print(f"{'─' * 60}")

    # Only cluster conversations with 3+ messages (skip throwaways)
    clusterable = [
        (cd["conv"], cd["title"])
        for cd in conv_data
        if cd["msg_count"] >= 3
    ]

    min_cluster = seed.get("min_cluster_size", 5)
    clusters = discover_clusters(clusterable, min_cluster_size=min_cluster)

    if clusters:
        print(f"\nFound {len(clusters)} topic clusters:\n")
        for i, cluster in enumerate(clusters, 1):
            kw_str = ", ".join(cluster["keywords"][:6])
            print(f"  {i:2d}. [{cluster['count']:3d} conversations] {kw_str}")
            for title in cluster["sample_titles"][:3]:
                print(f"      → {title[:65]}")
            print()
    else:
        print("\nNo clear topic clusters found. Categories will need manual definition.")

    unclustered = len(clusterable) - sum(c["count"] for c in clusters)
    print(f"  Clustered: {sum(c['count'] for c in clusters)}")
    print(f"  Unclustered: {unclustered}")

    # ── Phase 5: User Choices ────────────────────────────────────────────

    print(f"\n{'─' * 60}")
    print(f"CONFIGURATION")
    print(f"{'─' * 60}")

    # Language strategy (mandatory choice)
    if "language_strategy" in seed:
        lang_strategy = seed["language_strategy"]
        valid = ("unified", "preserve", "translate", "multilingual")
        if lang_strategy not in valid:
            print(f"ERROR: language_strategy must be one of: {', '.join(valid)}")
            sys.exit(1)
        print(f"\nLanguage strategy: {lang_strategy} (from seed config)")
    elif interactive:
        lang_strategy = ask_choice(
            "How should output knowledge files handle languages?",
            [
                ("unified", "Unified — all conversations in one file per category, as-is"),
                ("preserve", "Preserve — split files by language (e.g. infra-en.json, infra-nl.json)"),
                ("translate", "Translate — output everything in one target language"),
                ("multilingual", "Multilingual — include both original + translated version"),
            ],
            default="unified",
        )
    else:
        print("ERROR: language_strategy is required. Set it in seed config or run interactively.")
        sys.exit(1)

    # Target language
    # - unified: auto-detected from most dominant language in the export
    # - translate/multilingual: user must specify
    # - preserve: not needed
    target_lang = None

    # Auto-detect dominant language for reference
    most_common_lang = lang_counts.most_common(1)[0][0]
    if most_common_lang == "unknown":
        # Fall back to second most common, or "en"
        for lang, _ in lang_counts.most_common():
            if lang != "unknown":
                most_common_lang = lang
                break
        else:
            most_common_lang = "en"

    if lang_strategy == "unified":
        # Auto-detect: unify to the most dominant language
        target_lang = most_common_lang
        print(f"Target language: {LANG_NAMES.get(target_lang, target_lang)} (auto-detected dominant)")

    elif lang_strategy in ("translate", "multilingual"):
        if "target_language" in seed:
            target_lang = seed["target_language"]
            print(f"Target language: {LANG_NAMES.get(target_lang, target_lang)} (from seed config)")
        elif interactive:
            lang_options = []
            for lang, count in lang_counts.most_common():
                if lang == "unknown":
                    continue
                name = LANG_NAMES.get(lang, lang)
                lang_options.append((lang, f"{name} ({count} conversations)"))
            # Add English if not present
            if not any(l[0] == "en" for l in lang_options):
                lang_options.append(("en", "English"))

            target_lang = ask_choice(
                f"Target language for {lang_strategy} output:",
                lang_options,
                default=most_common_lang,
            )
        else:
            print(f"ERROR: target_language is required when language_strategy is '{lang_strategy}'.")
            sys.exit(1)

    # Category selection
    categories = {}
    if interactive and clusters:
        print("\n" + "─" * 60)
        print("CATEGORY SELECTION")
        print("─" * 60)
        print("\nReview discovered topics. For each, you can:")
        print("  - Accept as a category (press Enter or type a name)")
        print("  - Skip it (type 'skip')")
        print("  - Merge with another (type the number of the cluster to merge with)")
        print()

        accepted = {}  # cluster_index -> category_name
        for i, cluster in enumerate(clusters, 1):
            kw_str = ", ".join(cluster["keywords"][:5])
            print(f"\n  Cluster {i}: {kw_str}")
            print(f"  ({cluster['count']} conversations)")
            for title in cluster["sample_titles"][:3]:
                print(f"    → {title[:65]}")

            # Suggest a category name from the top keyword
            suggested = cluster["keywords"][0].replace(" ", "-")
            raw = ask_text(f"  Category name", default=suggested)

            if raw.lower() == "skip":
                continue

            # Check if it's a merge (number)
            try:
                merge_target = int(raw)
                if merge_target in accepted:
                    # Merge keywords
                    target_name = accepted[merge_target]
                    existing_kw = categories[target_name]["strong"]
                    new_kw = [w for w in cluster["keywords"] if w not in existing_kw]
                    categories[target_name]["strong"].extend(new_kw[:5])
                    print(f"    → Merged into '{target_name}'")
                    continue
            except ValueError:
                pass

            # Accept as new category
            cat_name = raw.lower().replace(" ", "-")
            categories[cat_name] = {
                "strong": cluster["keywords"][:5],
                "medium": cluster["keywords"][5:10],
            }
            accepted[i] = cat_name
            print(f"    → Category '{cat_name}' created")

    elif clusters:
        # Non-interactive: auto-accept all clusters
        for cluster in clusters:
            cat_name = cluster["keywords"][0].replace(" ", "-")
            # Avoid duplicate names
            base = cat_name
            suffix = 1
            while cat_name in categories:
                cat_name = f"{base}-{suffix}"
                suffix += 1
            categories[cat_name] = {
                "strong": cluster["keywords"][:5],
                "medium": cluster["keywords"][5:10],
            }

    # Ask about additional manual categories
    if interactive:
        print()
        while ask_yes_no("Add a manual category?", default=False):
            name = ask_text("  Category name")
            if not name:
                continue
            kw = ask_text("  Keywords (comma-separated)")
            keywords = [k.strip() for k in kw.split(",") if k.strip()]
            cat_name = name.lower().replace(" ", "-")
            categories[cat_name] = {
                "strong": keywords[:5],
                "medium": keywords[5:],
            }
            print(f"    → Category '{cat_name}' created with {len(keywords)} keywords")

    # Triage settings
    triage = seed.get("triage", {})
    if not triage:
        triage = {
            "skip_threshold": 2,
            "skip_candidate_threshold": 5,
            "outdated_before": "2024-06-01",
            "outdated_indicators": {},
            "howto_signals": [
                "how to", "how do i", "setup", "install", "configure",
                "set up", "getting started"
            ],
        }

    # ── Phase 6: Generate Config ─────────────────────────────────────────

    config = {
        "_comment": "Generated by 00_discover.py — edit freely",
        "backup_dir": backup_dir,
        "language_strategy": lang_strategy,
    }
    if target_lang:
        config["target_language"] = target_lang

    config["categories"] = categories
    config["triage"] = triage
    config["already_processed"] = []

    # Write config
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # ── Summary ──────────────────────────────────────────────────────────

    print(f"\n{'=' * 60}")
    print(f"DISCOVERY COMPLETE")
    print(f"{'=' * 60}")
    print(f"\nConfig written to: {output_path}")
    print(f"Categories: {len(categories)}")
    print(f"Language: {lang_strategy}", end="")
    if target_lang:
        print(f" → {LANG_NAMES.get(target_lang, target_lang)}")
    else:
        print()

    if categories:
        print(f"\nCategories:")
        for name, kw in categories.items():
            all_kw = kw.get("strong", []) + kw.get("medium", [])
            print(f"  {name:30s} [{', '.join(all_kw[:5])}]")

    print(f"\nNext steps:")
    print(f"  1. Review and edit {output_path}")
    print(f"     - Rename categories to meaningful names")
    print(f"     - Add/remove keywords")
    print(f"     - Adjust triage settings")
    print(f"  2. Run the pipeline:")
    print(f"     python run.py --config {output_path}")


if __name__ == "__main__":
    main()
