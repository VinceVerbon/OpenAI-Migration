"""
Step 0a: Generate topic abstracts for conversations using Claude Code.

This is a MANUAL step that requires a Claude Code session. It prepares
conversation excerpts and provides the prompt for Claude to generate
topic labels. The output (abstracts.json) is used by 00_discover.py
for high-quality topic clustering.

Pipeline position:
  00_abstract.py --extract  →  excerpts.json  (automated)
  Claude Code session       →  abstracts.json (manual, uses PROMPT below)
  00_discover.py            →  config.json    (automated, reads abstracts.json)

Usage:
  # Step 1: Extract conversation excerpts
  python 00_abstract.py --extract --config seed.json --dir myrun/

  # Step 2: Run in Claude Code (see PROMPT constant below, or just say:)
  #   "Process myrun/excerpts.json and generate myrun/abstracts.json"
  #   Claude Code will read the excerpts, batch-process them, and write labels.

  # Step 3: Discovery uses the abstracts automatically
  python 00_discover.py --seed myrun/seed.json --output myrun/config.json
"""
import json
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import check_mapped_drive, normalize_path

sys.stdout.reconfigure(encoding="utf-8")


# ─── The Prompt ──────────────────────────────────────────────────────────────
# This is the exact prompt Claude Code uses to generate topic labels.
# It is kept here as the single source of truth so it can be versioned,
# reviewed, and improved alongside the rest of the pipeline.

PROMPT = """You are a topic classifier for ChatGPT conversation exports.

For each conversation excerpt below, determine the MAIN TOPIC — what the
conversation is actually about, not how it's written.

Rules:
- Output a short topic label: 3-7 words, descriptive of the subject matter
- Use English for the label regardless of conversation language
- Focus on the DOMAIN, not the format (e.g., "Arduino ESP32 wiring" not "Technical question")
- If the conversation covers multiple topics, pick the dominant one
- If the conversation is too vague or trivial to label, use "general-chat"
- Be specific: "Docker container networking" not just "Docker"
- Be consistent: similar conversations should get similar labels
- NEVER end labels with generic action/status words like: error, issue, problem,
  troubleshooting, question, help, fix, setup, configuration, design, overview,
  requirements, guide. These describe the FORMAT of the conversation, not the topic.
  Bad: "SSL connection error" → Good: "SSL TLS certificate renewal"
  Bad: "ESP32 display configuration" → Good: "ESP32 TFT display driver"
  Bad: "Power BI issue" → Good: "Power BI date column transformation"

Output format: A JSON object mapping conversation ID to topic label.
Example: {"abc-123": "Excel pivot table formulas", "def-456": "Docker compose networking"}

Conversation excerpts:
"""

# ─── Excerpt Extraction ─────────────────────────────────────────────────────

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


def extract_excerpts(backup_dir, min_messages=3):
    """Extract compact conversation excerpts for topic labeling.

    Returns list of dicts with id, title, and first user messages.
    Only includes conversations with min_messages or more.
    """
    all_convs = load_conversations(backup_dir)
    excerpts = []

    for conv in all_convs:
        messages = extract_messages(conv)
        if len(messages) < min_messages:
            continue

        title = conv.get("title", "") or "Untitled"
        conv_id = conv.get("id", "")

        # First 3 user messages, truncated to keep batches compact
        user_msgs = [
            text[:300] for _, role, text in messages[:8] if role == "user"
        ][:3]

        excerpts.append({
            "id": conv_id,
            "title": title,
            "user_messages": user_msgs,
        })

    return excerpts


def build_batches(excerpts, batch_size=50):
    """Split excerpts into batches for efficient Claude Code processing."""
    batches = []
    for i in range(0, len(excerpts), batch_size):
        batches.append(excerpts[i:i + batch_size])
    return batches


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract conversation excerpts for Claude Code topic labeling"
    )
    parser.add_argument("--extract", action="store_true",
                       help="Extract excerpts from conversations")
    parser.add_argument("--config", default="seed.json",
                       help="Path to seed/config file (for backup_dir)")
    parser.add_argument("--dir", default=".",
                       help="Output directory for excerpts.json")
    parser.add_argument("--batch-size", type=int, default=50,
                       help="Conversations per batch (default: 50)")
    parser.add_argument("--show-prompt", action="store_true",
                       help="Print the Claude Code prompt and exit")
    args = parser.parse_args()

    if args.show_prompt:
        print(PROMPT)
        print("\n[Paste conversation excerpts here]")
        return

    if not args.extract:
        print("Usage: python 00_abstract.py --extract --config seed.json --dir myrun/")
        print("       python 00_abstract.py --show-prompt")
        print()
        print("This script extracts conversation excerpts for Claude Code to label.")
        print("See the docstring or docs/README.md for the full workflow.")
        return

    # Load config for backup_dir
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    backup_dir = normalize_path(config.get("backup_dir", ""))
    if not backup_dir:
        print("ERROR: config must contain backup_dir")
        sys.exit(1)

    check_mapped_drive(backup_dir)

    if not os.path.exists(backup_dir):
        print(f"ERROR: Directory not found: {backup_dir}")
        sys.exit(1)

    # Extract
    print(f"Extracting excerpts from: {backup_dir}")
    excerpts = extract_excerpts(backup_dir)
    print(f"Extracted {len(excerpts)} conversations (3+ messages)")

    # Save excerpts
    os.makedirs(args.dir, exist_ok=True)
    excerpts_path = os.path.join(args.dir, "excerpts.json")
    with open(excerpts_path, "w", encoding="utf-8") as f:
        json.dump(excerpts, f, indent=1, ensure_ascii=False)

    file_size = os.path.getsize(excerpts_path) / 1024
    batches = build_batches(excerpts, args.batch_size)

    print(f"Saved to: {excerpts_path} ({file_size:.0f} KB)")
    print(f"Will process in {len(batches)} batches of ~{args.batch_size}")

    # Check if abstracts already exist
    abstracts_path = os.path.join(args.dir, "abstracts.json")
    if os.path.exists(abstracts_path):
        with open(abstracts_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"\nNote: abstracts.json already exists with {len(existing)} entries")
        missing = len(excerpts) - len(existing)
        if missing > 0:
            print(f"  {missing} conversations still need labeling")
        else:
            print(f"  All conversations labeled — run 00_discover.py next")
            return

    print(f"\n{'─' * 60}")
    print(f"NEXT STEP: Run in Claude Code")
    print(f"{'─' * 60}")
    print(f"\nOpen a Claude Code session and say:")
    print(f'  "Process {excerpts_path} to generate topic abstracts."')
    print(f'  "Write results to {abstracts_path}"')
    print(f"\nClaude Code will read the excerpts in batches, generate")
    print(f"topic labels using the prompt in this script, and save them.")
    print(f"\nAfter that, run:")
    print(f"  python 00_discover.py --seed {args.config} --output {args.dir}/config.json")


if __name__ == "__main__":
    main()
