"""
Step 3: Generate human-reviewable checklist.

Creates a Markdown file with all conversations grouped by category and triage
status. This is the manual review step — skim it, fix miscategorizations,
mark anything important.

Usage: python 03_build_checklist.py [--config config.json]
"""
import json
import os
import sys
import argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Generate review checklist")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    base_dir = os.path.dirname(args.config) or "."
    inv_path = os.path.join(base_dir, "inventory.json")

    with open(inv_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    # Stats
    cat_counts = defaultdict(int)
    triage_counts = defaultdict(int)
    for item in inventory:
        cat_counts[item["category"]] += 1
        triage_counts[item["triage"]] += 1

    lines = []
    lines.append("# Conversation Checklist")
    lines.append("")
    lines.append(f"**Total conversations:** {len(inventory)}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append("### By Triage Status")
    lines.append("| Status | Count | Description |")
    lines.append("|--------|-------|-------------|")
    triage_desc = {
        "done": "Already processed",
        "review": "Needs review — likely contains useful knowledge",
        "skip-candidate": "Short (3-5 messages) — probably not worth processing",
        "skip": "Trivial (1-2 messages)",
        "outdated": "Outdated how-to content (current AI knowledge supersedes)",
    }
    for tri in ["done", "review", "skip-candidate", "skip", "outdated"]:
        count = triage_counts.get(tri, 0)
        desc = triage_desc.get(tri, "")
        lines.append(f"| {tri} | {count} | {desc} |")

    lines.append("")
    lines.append("### By Category")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {count} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Group by category
    by_category = defaultdict(list)
    for item in inventory:
        by_category[item["category"]].append(item)

    cat_order = sorted(cat_counts.keys(), key=lambda c: -cat_counts[c])

    for cat in cat_order:
        items = by_category.get(cat, [])
        if not items:
            continue

        lines.append(f"## {cat.replace('-', ' ').title()} ({len(items)})")
        lines.append("")

        items.sort(key=lambda x: x["date"])

        by_triage = defaultdict(list)
        for item in items:
            by_triage[item["triage"]].append(item)

        for triage_status in ["done", "review", "outdated", "skip-candidate", "skip"]:
            t_items = by_triage.get(triage_status, [])
            if not t_items:
                continue

            if triage_status not in ("review",):
                lines.append(f"### {triage_status.title()}")
                lines.append("")

            for item in t_items:
                msgs = item["message_count"]
                date = item["date"]
                title = item["title"]
                preview = item.get("first_user_preview", "")[:80].replace("|", "/")

                suffix = ""
                if item.get("outdated_reason"):
                    suffix = f" -- {item['outdated_reason']}"
                elif item.get("custom_gpt"):
                    suffix = " [Custom GPT]"

                if triage_status == "done":
                    lines.append(f"- [x] `{date}` **{title}** ({msgs} msgs)")
                elif triage_status == "skip":
                    lines.append(f"- [-] `{date}` {title} ({msgs} msgs)")
                elif triage_status == "outdated":
                    lines.append(f"- [x] `{date}` ~~{title}~~ ({msgs} msgs){suffix}")
                else:
                    lines.append(f"- [ ] `{date}` **{title}** ({msgs} msgs) `{triage_status}`{suffix}")
                    if preview:
                        lines.append(f"  > {preview}")

            lines.append("")

    out_path = os.path.join(base_dir, "CHECKLIST.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generated {out_path} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
