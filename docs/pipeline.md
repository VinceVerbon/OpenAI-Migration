# Knowledge Distillation Pipeline

## Overview

The pipeline converts a raw ChatGPT export (hundreds or thousands of conversations) into a small set of structured knowledge files organized by topic. The output is designed to be loaded as persistent context for any AI assistant.

```
Raw Export (N conversations, ~100MB+ JSON)
    ↓ Step 1: Scan & initial categorize
    ↓ Step 2: Deeper re-categorization
    ↓ Step 3: Human review checklist
    ↓ Step 4: Final categorization pass
    ↓ Step 5: Extract valuable content
Structured extracts per category (JSON)
    ↓ Step 6: AI-assisted distillation
Topic knowledge files (Markdown)
    ↓ Step 7: Synthesize profile
User profile document (Markdown)
```

## Before You Start

1. **Get your export** — see `export-structure.md`
2. **Copy `config.example.json` to `config.json`** and edit:
   - Set `backup_dir` to where you unzipped the export
   - Set `output_dir` to where you want knowledge files written
   - Customize `categories` to match your life/work domains
3. **Review the default categories** — they cover common domains but you should add/remove to match your actual usage

## Step 1: Scan (`01_scan.py`)

Parses all `conversations-*.json` files and builds a flat inventory of every conversation.

**What it does:**
- Extracts title, date, message count, first user message
- Detects Custom GPT usage (system messages >100 chars)
- Assigns each conversation to a category using keyword matching on title + first user message
- Assigns a triage status based on message count:
  - `skip` — 1-2 messages (too short to contain useful knowledge)
  - `skip-candidate` — 3-5 messages (probably not worth processing)
  - `review` — 6+ messages (worth reviewing)
- Flags outdated content (generic how-to questions about tech where current AI knowledge supersedes the old answers)

**Output:** `inventory.json` — one entry per conversation with category, triage status, and preview.

**Why keyword matching?** It's fast, requires no API calls, and handles 70-80% of conversations correctly. The remaining ~20% are caught by later passes.

## Step 2: Rescan (`02_rescan.py`)

Second categorization pass with expanded analysis.

**What it does:**
- Reads first 3 user messages (not just the first one) for better topic detection
- Uses expanded keyword lists including both English and native-language terms
- Fixes common miscategorizations (e.g. "pool chemistry" matched as infrastructure due to "setup" keyword)
- Marks additional outdated content

**Why a second pass?** Titles are often vague ("Help me with this", "Quick question"). Reading actual message content dramatically improves accuracy.

## Step 3: Build Checklist (`03_build_checklist.py`)

Generates a human-readable Markdown checklist for manual review and correction.

**Output:** `CHECKLIST.md` — all conversations grouped by category with checkboxes:
- `[x]` — already processed
- `[ ]` — needs review
- `[-]` — auto-skipped (trivial)
- `[~]` — outdated

**What you do here:**
- Skim the checklist
- Fix any obvious miscategorizations
- Mark conversations you know are valuable with specific notes
- This is the only manual step — spend 15-30 minutes here

## Step 4: Deep Categorize (`04_deep_categorize.py`)

Final categorization pass for remaining uncategorized conversations.

**What it does:**
- Reads first 5 user messages + first 3 assistant responses for each uncategorized chat
- Uses weighted scoring: strong keyword matches (3 points) vs. weak matches (1 point)
- Requires a minimum confidence threshold to assign a category
- Catches conversations that used unusual phrasing or mixed topics

**After this step:** Typically <5% of conversations remain uncategorized. These are usually one-off questions that don't fit any domain.

## Step 5: Extract (`05_extract.py`)

Extracts the valuable content from each category into structured JSON files.

**What it does:**
- For each category, takes all conversations with triage `review` or `skip-candidate` (excludes `skip` and `outdated`)
- Extracts: title, date, first 3 user messages (up to 1000 chars each), first 2 assistant responses (up to 1000 chars each), and the last user message for longer conversations
- Outputs one JSON file per category in `category_extracts/`

**Why extract instead of using full conversations?** Full conversations contain greetings, corrections, tangents, and repetition. The first few exchanges usually establish the topic and reveal the user's actual knowledge, preferences, and decisions.

## Step 6: AI-Assisted Distillation

Feed each category extract to an AI with a distillation prompt. This is where raw conversation data becomes structured knowledge.

**This step is not scripted** — it requires an AI capable of synthesizing patterns across many conversations. Use whatever AI you prefer.

### Distillation Prompt Template

```
I'm giving you extracted summaries from [N] ChatGPT conversations in the
category "[CATEGORY]", spanning [DATE RANGE].

These are my actual conversations — they reveal my knowledge level,
preferences, decisions, tools I use, and problems I've solved.

Please analyze all conversations and produce a structured Markdown document
that captures:

1. **Key knowledge and expertise demonstrated** — what do I clearly know well?
2. **Tools, services, and products used** — with specific versions/preferences
3. **Decisions made and rationale** — choices I made and why
4. **Recurring patterns** — problems I keep solving, workflows I repeat
5. **Preferences and opinions** — strong preferences revealed across conversations
6. **Open questions or gaps** — things I struggled with or didn't resolve

Format as a clean Markdown document with headers and bullet points.
Be specific — include actual product names, version numbers, configuration
choices. Skip generic knowledge that any AI already knows.

Do NOT include:
- Generic explanations of technologies
- Information I was clearly just exploring without committing to
- One-off questions that don't reveal lasting patterns
```

### Tips for Step 6

- Process one category at a time — don't overload the context
- Use a capable model (Claude Opus, GPT-4) for synthesis quality
- Review each output and correct factual errors before saving
- Name outputs consistently: `learning-input-[category].md`

## Step 7: Synthesize Profile

Feed all category knowledge files to an AI to produce a single user profile document.

### Profile Synthesis Prompt Template

```
I'm giving you [N] topic-specific knowledge files distilled from my ChatGPT
history. Together they paint a complete picture of who I am, how I work,
and what I know.

Please synthesize these into a single structured profile document covering:

1. Identity & professional profile
2. Domain expertise (demonstrated, not claimed)
3. Technical environment and infrastructure
4. Tools and workflow preferences
5. Communication style and AI interaction preferences
6. Key decisions and rationale

This document will be loaded as persistent context at the start of every AI
session. Keep it concise but complete — aim for under 250 lines.
```

## Output Structure

After completing the pipeline, you'll have:

```
output/
├── profile.md                          # Master profile (~200 lines)
└── topics/
    ├── learning-input-business.md      # Per-topic knowledge
    ├── learning-input-development.md
    ├── learning-input-infrastructure.md
    └── ...                             # One per category
```

## Using the Output

### As AI context files
Most AI coding tools support loading files as context:
- **Claude Code:** Reference in `CLAUDE.md` instructions
- **Claude Desktop:** Add as project knowledge
- **ChatGPT:** Upload as project files
- **Cursor/Windsurf:** Add to context rules

### Selective loading
Don't load all topic files in every session — load `profile.md` always, and only load the relevant topic file(s) for the current task. This keeps context focused and token-efficient.

## Customizing Categories

The default categories cover common domains. Edit `config.json` to:

- **Add categories** for your specific domains (e.g. `photography`, `legal`, `cooking`)
- **Add keywords** in your native language — the scripts support any language
- **Adjust triage rules** — change message count thresholds or age cutoffs for "outdated"
- **Add "already done" filters** — conversations you've already processed elsewhere
