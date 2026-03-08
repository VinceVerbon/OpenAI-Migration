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

STEPS = [
    ("01_scan.py", "Scan & initial categorization"),
    ("02_rescan.py", "Deeper re-categorization"),
    ("03_build_checklist.py", "Generate review checklist"),
    ("04_deep_categorize.py", "Keyword categorization pass"),
    ("04b_classify.py", "Statistical classifier for remaining uncategorized"),
    ("05_extract.py", "Extract content per category"),
]


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
    print()
    print(f"Next steps:")
    print(f"  1. Review: {os.path.join(os.path.dirname(config_path), 'CHECKLIST.md')}")
    print(f"  2. Fix miscategorizations in inventory.json if needed")
    print(f"  3. (Optional) Run 06_suggest_keywords.py to improve keyword coverage")
    print(f"  4. Feed category_extracts/*.json to an AI with the distillation prompt")
    print(f"     (see docs/pipeline.md for the prompt template)")


if __name__ == "__main__":
    main()
