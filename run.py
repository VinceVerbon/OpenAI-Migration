"""
Run the full pipeline (steps 1-5) in sequence.

Captures output from each step. If a step fails, prints the error and stops.
All paths are derived from the config file location — nothing is hardcoded.

Usage: python run.py --config path/to/config.json
"""
import subprocess
import sys
import os
import time
import json
import glob

# Add script directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import check_mapped_drive

STEPS = [
    ("01_scan.py", "Scan & initial categorization"),
    ("02_rescan.py", "Deeper re-categorization"),
    ("03_build_checklist.py", "Generate review checklist"),
    ("04_deep_categorize.py", "Keyword categorization pass"),
    ("04b_classify.py", "Statistical classifier for remaining uncategorized"),
    ("05_extract.py", "Extract content per category"),
]


SELECTION_FILENAME = "custom-user-selection.md"


def generate_selection_file(extracts_dir, output_path):
    """Generate custom-user-selection.md with all categories pre-checked.

    Lists every category from category_extracts/ with conversation and message
    counts. All categories start checked — the user unchecks ones to exclude
    from distillation.
    """
    if not os.path.exists(extracts_dir):
        return

    categories = []
    for filepath in sorted(glob.glob(os.path.join(extracts_dir, "*.json"))):
        filename = os.path.basename(filepath)
        category = filename.replace(".json", "")
        if category == "uncategorized":
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "conversations" in data:
            convs = data["conversations"]
        elif isinstance(data, list):
            convs = data
        else:
            continue

        conv_count = len(convs)
        msg_count = sum(c.get("message_count", 0) for c in convs)
        categories.append((category, conv_count, msg_count))

    if not categories:
        return

    lines = [
        "# Category Selection",
        "",
        "Uncheck categories you want to exclude from distillation.",
        "The pipeline will only distill checked `[x]` categories.",
        "If this file is deleted, all categories will be distilled.",
        "",
    ]
    for cat, conv_count, msg_count in categories:
        lines.append(f"- [x] {cat} ({conv_count} conversations, {msg_count} messages)")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n--- Category selection file ---")
    print(f"  Generated: {output_path}")
    print(f"  {len(categories)} categories, all selected by default")


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
                # Extract category name (everything before the first parenthesis)
                rest = line[6:]  # after "- [x] "
                cat = rest.split(" (")[0].strip()
                if cat:
                    selected.add(cat)
    return selected


def validate_config(config_path):
    """Check config exists and has required fields before running."""
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        print(f"Copy config.example.json to your run directory and edit it.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    backup_dir = config.get("backup_dir", "")
    if not backup_dir or backup_dir.startswith("/path/to"):
        print(f"ERROR: backup_dir in config is not set.")
        print(f"Edit {config_path} and set backup_dir to your OpenAI export location.")
        sys.exit(1)

    check_mapped_drive(backup_dir)

    if not os.path.exists(backup_dir):
        print(f"ERROR: backup_dir does not exist: {backup_dir}")
        sys.exit(1)

    # Check that at least one conversations file exists
    found = False
    for i in range(100):
        if os.path.exists(os.path.join(backup_dir, f"conversations-{i:03d}.json")):
            found = True
            break
    if not found:
        print(f"ERROR: No conversations-*.json files found in: {backup_dir}")
        print(f"Make sure this is an unzipped OpenAI data export.")
        sys.exit(1)

    if not config.get("categories"):
        print(f"WARNING: No categories defined in config. Everything will be uncategorized.")

    return config


def main():
    # Parse args
    config_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            config_path = sys.argv[i + 1]

    if not config_path:
        print("Usage: python run.py --config path/to/config.json")
        sys.exit(1)

    config_path = os.path.abspath(config_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("AIKnowledgeDistill Pipeline")
    print("=" * 60)
    print(f"Config:  {config_path}")
    print(f"Scripts: {script_dir}")
    print()

    # Validate before running
    config = validate_config(config_path)
    print(f"Backup:  {config['backup_dir']}")
    print(f"Output:  {os.path.dirname(config_path)}")
    print()

    start = time.time()
    step_times = []

    for script, description in STEPS:
        script_path = os.path.join(script_dir, script)

        if not os.path.exists(script_path):
            print(f"ERROR: Script not found: {script_path}")
            sys.exit(1)

        print(f"--- {description} ({script}) ---")
        step_start = time.time()

        result = subprocess.run(
            [sys.executable, script_path, "--config", config_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        step_elapsed = time.time() - step_start
        step_times.append((script, step_elapsed))

        # Print stdout
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")

        # Print stderr as warnings/errors
        if result.stderr.strip():
            for line in result.stderr.strip().split("\n"):
                print(f"  [STDERR] {line}")

        if result.returncode != 0:
            print(f"\n  FAILED (exit code {result.returncode})")
            print(f"\nPipeline aborted at {script}.")
            sys.exit(1)

        print(f"  ({step_elapsed:.1f}s)")
        print()

    elapsed = time.time() - start

    print("=" * 60)
    print(f"Pipeline complete in {elapsed:.1f}s")
    print()
    for script, t in step_times:
        print(f"  {script:30s} {t:.1f}s")
    print("=" * 60)

    # Generate custom-user-selection.md from category extracts
    base_dir = os.path.dirname(config_path)
    selection_path = os.path.join(base_dir, "custom-user-selection.md")
    extracts_dir = os.path.join(base_dir, "category_extracts")
    generate_selection_file(extracts_dir, selection_path)

    print()
    print(f"Next steps:")
    print(f"  1. (Optional) Review: {selection_path}")
    print(f"     Uncheck categories you want to exclude from distillation.")
    print(f"  2. Feed category_extracts/*.json to an AI with the distillation prompt")
    print(f"     (see docs/README.md for the full pipeline documentation)")


if __name__ == "__main__":
    main()
