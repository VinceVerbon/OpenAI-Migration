"""
Step 6: Distill category extracts into structured knowledge files.

This is a MANUAL step that requires a Claude Code session. It reads
category extract files and produces one learning file per category
containing condensed, deduplicated knowledge.

Pipeline position:
  05_extract.py      →  category_extracts/*.json   (automated)
  06_distill.py      →  (runs in Claude Code)      (manual)
                     →  knowledge/learning-*.md     (output)

Usage:
  # Step 1: See what needs distilling
  python 06_distill.py --status --dir myrun/

  # Step 2: Run in Claude Code:
  #   "Distill myrun/category_extracts into knowledge files in myrun/knowledge/"
  #   Claude Code reads each extract, applies the PROMPT below, and writes
  #   one learning-[topic]-[date].md per category.

  # Step 3: Verify completeness
  python 06_distill.py --status --dir myrun/

Output format:
  knowledge/learning-[category]-[yyyymmdd].md

  Each file contains condensed knowledge from all conversations in that
  category, written in the language specified by the extract's _meta header.
"""
import json
import os
import sys
import argparse
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")


# ─── The Prompt ──────────────────────────────────────────────────────────────
# This is the exact prompt Claude Code uses to distill category extracts.
# Single source of truth — versioned alongside the pipeline.

PROMPT = """You are a knowledge distiller. You are given a JSON file containing
conversation extracts from a ChatGPT export, all belonging to one topic category.

Your task: condense ALL conversations into a single structured knowledge file.

## Language

{language_instruction}

## Rules

1. Extract the KNOWLEDGE, not the conversation. Strip away greetings, corrections,
   back-and-forth, and conversational noise. Keep only the insights, facts,
   decisions, how-tos, and lessons learned.

2. Deduplicate. If multiple conversations cover the same ground, merge them into
   one section. Don't repeat information.

3. Organize by sub-topic. Use clear markdown headers (##, ###) to group related
   knowledge. The structure should make sense for someone scanning the document.

4. Preserve specifics. Keep concrete details: exact commands, configuration values,
   model numbers, URLs, formulas, thresholds, version numbers. Generic advice
   without specifics is worthless.

5. Attribute when relevant. If knowledge came from a specific context (e.g., a
   particular project, device, or tool version), note it briefly.

6. Flag contradictions. If conversations contain conflicting information, note both
   positions and flag the contradiction.

7. Skip trivial conversations. If a conversation has triage "skip-candidate" and
   contains no real knowledge, omit it entirely.

8. Keep it concise. The goal is a reference document, not a textbook. Aim for
   information density — every sentence should carry weight.

## Output format

```markdown
# [Category Topic Name]

> Distilled from [N] conversations ([date range]).
> Source: ChatGPT export, category: [category-name]

## [Sub-topic 1]

[Knowledge content]

## [Sub-topic 2]

[Knowledge content]

...
```

NOTE: Do NOT add a sources/references section. Source links are added automatically
by the pipeline after distillation (via `06_distill.py --add-sources`).
"""


def get_language_instruction(meta):
    """Build language instruction string from extract _meta header."""
    if not meta:
        return "Write in English."

    strategy = meta.get("language_strategy", "unified")
    target = meta.get("target_language", "en")
    instruction = meta.get("instruction", "")

    if instruction:
        return instruction

    if strategy == "translate":
        return f"Write the entire document in {target}."
    elif strategy == "unified":
        return f"Write the entire document in {target}."
    elif strategy == "preserve":
        lang = meta.get("language", "unknown")
        return f"Write in {lang}. Preserve the original language of the source material."
    elif strategy == "multilingual":
        return f"Include both the original language content and a {target} translation."
    else:
        return "Write in English."


def parse_selection_file(selection_path):
    """Parse custom-user-selection.md and return set of selected category names.

    Returns None if file doesn't exist (meaning: select all).
    Returns a set of category names that are checked [x].
    """
    if not os.path.exists(selection_path):
        return None

    selected = set()
    with open(selection_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("- [x] "):
                rest = line[6:]  # after "- [x] "
                cat = rest.split(" (")[0].strip()
                if cat:
                    selected.add(cat)
    return selected


def scan_extracts(extracts_dir):
    """Scan category extract files and return their metadata."""
    results = []
    if not os.path.exists(extracts_dir):
        return results

    for filename in sorted(os.listdir(extracts_dir)):
        if not filename.endswith(".json"):
            continue
        category = filename.replace(".json", "")
        if category == "uncategorized":
            continue

        filepath = os.path.join(extracts_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "conversations" in data:
            meta = data.get("_meta", {})
            convs = data["conversations"]
        else:
            meta = {}
            convs = data if isinstance(data, list) else []

        # Date range
        dates = [c.get("date", "") for c in convs if c.get("date")]
        date_range = f"{min(dates)} — {max(dates)}" if dates else "unknown"

        results.append({
            "category": category,
            "filename": filename,
            "filepath": filepath,
            "conv_count": len(convs),
            "date_range": date_range,
            "meta": meta,
            "total_messages": sum(c.get("message_count", 0) for c in convs),
        })

    return results


def scan_knowledge(knowledge_dir):
    """Scan existing knowledge files."""
    existing = set()
    if not os.path.exists(knowledge_dir):
        return existing
    for filename in os.listdir(knowledge_dir):
        if filename.startswith("learning-") and filename.endswith(".md"):
            # Extract category from learning-[category]-[date].md
            parts = filename.removeprefix("learning-").removesuffix(".md")
            # Remove the date suffix (last 8 chars + dash)
            if len(parts) > 9 and parts[-9] == "-" and parts[-8:].isdigit():
                cat = parts[:-9]
            else:
                cat = parts
            existing.add(cat)
    return existing


def add_sources(extracts_dir, knowledge_dir, backup_dir=None):
    """Append ## Bronnen section with local backup file references to knowledge files."""
    extracts = scan_extracts(extracts_dir)
    existing = scan_knowledge(knowledge_dir)

    updated = 0
    skipped_no_ids = 0

    for ext in extracts:
        cat = ext["category"]
        if cat not in existing:
            continue

        # Find the knowledge file
        knowledge_file = None
        for fname in os.listdir(knowledge_dir):
            if fname.startswith(f"learning-{cat}-") and fname.endswith(".md"):
                knowledge_file = os.path.join(knowledge_dir, fname)
                break
        if not knowledge_file:
            continue

        # Read extract to get conversation IDs
        with open(ext["filepath"], "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "conversations" in data:
            convs = data["conversations"]
        else:
            convs = data if isinstance(data, list) else []

        # Check if any conversations have IDs
        convs_with_ids = [c for c in convs if c.get("id")]
        if not convs_with_ids:
            skipped_no_ids += 1
            continue

        # Read existing knowledge file
        with open(knowledge_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Remove existing Bronnen section if present (for re-runs)
        bronnen_marker = "\n## Bronnen\n"
        if bronnen_marker in content:
            content = content[:content.index(bronnen_marker)]

        # Build sources section
        lines = ["\n## Bronnen\n"]
        lines.append("| Gesprek | Datum | Berichten | Bronbestand | Gesprek-ID |")
        lines.append("|---------|-------|-----------|-------------|------------|")
        for c in sorted(convs_with_ids, key=lambda x: x.get("date", "")):
            title = c.get("title", "Untitled")
            conv_id = c["id"]
            conv_date = c.get("date", "?")
            msg_count = c.get("message_count", "?")
            backup_file = c.get("backup_file", "")

            if backup_file and backup_dir:
                file_ref = f"`{backup_dir}/{backup_file}`"
            elif backup_file:
                file_ref = f"`{backup_file}`"
            else:
                file_ref = ""

            lines.append(f"| {title} | {conv_date} | {msg_count} | {file_ref} | `{conv_id}` |")

        content = content.rstrip("\n") + "\n" + "\n".join(lines) + "\n"

        with open(knowledge_file, "w", encoding="utf-8") as f:
            f.write(content)
        updated += 1

    print(f"Added source links to {updated} knowledge files")
    if skipped_no_ids:
        print(f"Skipped {skipped_no_ids} files (extracts missing conversation IDs)")
        print("Re-run 05_extract.py to add IDs, then re-run --add-sources")


def main():
    parser = argparse.ArgumentParser(
        description="Distill category extracts into knowledge files"
    )
    parser.add_argument("--status", action="store_true",
                       help="Show distillation status")
    parser.add_argument("--dir", default=".",
                       help="Run directory containing category_extracts/")
    parser.add_argument("--show-prompt", action="store_true",
                       help="Print the distillation prompt and exit")
    parser.add_argument("--add-sources", action="store_true",
                       help="Append source links to existing knowledge files")
    args = parser.parse_args()

    if args.show_prompt:
        print(PROMPT.format(language_instruction="[from extract _meta header]"))
        return

    extracts_dir = os.path.join(args.dir, "category_extracts")
    knowledge_dir = os.path.join(args.dir, "knowledge")

    if args.add_sources:
        # Read backup_dir from config for full file paths in source references
        config_path = os.path.join(args.dir, "config.json")
        backup_dir = None
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            backup_dir = config.get("backup_dir")
        add_sources(extracts_dir, knowledge_dir, backup_dir=backup_dir)
        return

    if not args.status:
        print("Usage:")
        print(f"  python 06_distill.py --status --dir {args.dir}")
        print(f"  python 06_distill.py --show-prompt")
        print()
        print("This script shows distillation status and provides the prompt.")
        print("Actual distillation runs in a Claude Code session.")
        return

    # Status report
    extracts = scan_extracts(extracts_dir)
    existing = scan_knowledge(knowledge_dir)

    if not extracts:
        print(f"No extract files found in {extracts_dir}/")
        print("Run the pipeline first: python run.py --config config.json")
        return

    # Check for user selection file
    selection_path = os.path.join(args.dir, "custom-user-selection.md")
    selected = parse_selection_file(selection_path)
    has_selection = selected is not None

    print(f"{'=' * 60}")
    print(f"DISTILLATION STATUS")
    print(f"{'=' * 60}")

    if has_selection:
        total_cats = len([e for e in extracts if e["category"] != "uncategorized"])
        excluded = total_cats - len([e for e in extracts if e["category"] in selected])
        print(f"\nSelection: {selection_path}")
        print(f"  {len(selected)} selected, {excluded} excluded")
    else:
        print(f"\nSelection: all categories (no custom-user-selection.md found)")

    # Language info
    if extracts:
        meta = extracts[0].get("meta", {})
        strategy = meta.get("language_strategy", "unknown")
        target = meta.get("target_language", "")
        print(f"Language: {strategy}", end="")
        if target:
            print(f" → {target}")
        else:
            print()

    today = date.today().strftime("%Y%m%d")

    print(f"\n{'Category':<30s} {'Convs':>5s} {'Msgs':>5s}  {'Status':<12s}  Output")
    print(f"{'─' * 90}")

    pending = 0
    done = 0
    excluded_count = 0
    for ext in extracts:
        cat = ext["category"]
        output_name = f"learning-{cat}-{today}.md"

        if has_selection and cat not in selected:
            status = "✗ excluded"
            excluded_count += 1
        elif cat in existing:
            status = "✓ done"
            done += 1
        else:
            status = "⧖ pending"
            pending += 1

        print(f"{cat:<30s} {ext['conv_count']:>5d} {ext['total_messages']:>5d}  {status:<12s}  {output_name}")

    print(f"\n{'─' * 60}")
    parts = [f"{len(extracts)} categories", f"{done} done", f"{pending} pending"]
    if excluded_count:
        parts.append(f"{excluded_count} excluded")
    print(f"Total: {', '.join(parts)}")
    print(f"Output directory: {knowledge_dir}/")

    if pending > 0:
        print(f"\n{'─' * 60}")
        print(f"NEXT STEP: Run in Claude Code")
        print(f"{'─' * 60}")
        print(f"\nOpen a Claude Code session and say:")
        print(f'  "Distill {extracts_dir}/ into knowledge files in {knowledge_dir}/"')
        print(f"\nClaude Code will process each pending category extract,")
        print(f"condense the conversations, and write structured markdown files.")
        if has_selection:
            print(f"\nNote: {excluded_count} categories excluded by custom-user-selection.md")
        print(f"\nOutput: {knowledge_dir}/learning-[category]-{today}.md")
    else:
        print(f"\nAll categories distilled! Knowledge files in {knowledge_dir}/")


if __name__ == "__main__":
    main()
