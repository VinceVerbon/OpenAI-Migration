# AIKnowledgeDistill

Turn a raw ChatGPT/OpenAI data export into structured, categorized knowledge files ready for any AI assistant.

**No external dependencies.** Python 3.10+ stdlib only.

---

## What It Does

You exported your ChatGPT history — now what? It's a blob of hundreds (or thousands) of conversations across years, topics, and languages. This pipeline:

1. **Labels** each conversation with a short topic description using AI
2. **Discovers** natural topic clusters from those labels — no predefined categories needed
3. **Categorizes** every conversation using a three-tier system (cluster membership → abstract matching → keyword matching)
4. **Triages** what's worth keeping vs. trivial or outdated
5. **Extracts** valuable content per category into structured JSON (with source traceability)
6. **Distills** extracts into condensed knowledge files via AI
7. **Links** each knowledge file back to its source conversations in the local backup

---

## Pipeline Architecture

```
                       ┌─────────────────────────────────────────────┐
                       │        OpenAI Data Export                    │
                       │    conversations-000.json ... 00N.json       │
                       └──────────────┬──────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       │
   ┌──────────────────┐   ┌───────────────────┐              │
   │  Step 0a          │   │  Step 0b           │              │
   │  00_abstract.py   │   │  00_discover.py    │              │
   │  (Claude Code)    │   │                    │              │
   │                   │   │  Clusters labels   │              │
   │  Generates 3-7    │──▶│  into categories,  │              │
   │  word topic label │   │  outputs config +  │              │
   │  per conversation │   │  membership map    │              │
   └──────────────────┘   └────────┬───────────┘              │
                                   │                          │
                    config.json ───┤                          │
                    cluster_membership.json                   │
                                   │                          │
              ┌────────────────────┼──────────────────────────┤
              ▼                    ▼                          ▼
   ┌───────────────────────────────────────────────────────────┐
   │  Steps 1–5   (automated via run.py)                       │
   │                                                           │
   │  01_scan.py          Initial scan & categorize            │
   │  02_rescan.py        Deeper re-categorization             │
   │  03_build_checklist  Human review checklist                │
   │  04_deep_categorize  Weighted keyword scoring              │
   │  04b_classify.py     TF-IDF statistical classifier         │
   │  05_extract.py       Extract content per category          │
   └────────────────────────────┬──────────────────────────────┘
                                │
                    category_extracts/*.json
                                │
                                ▼
   ┌───────────────────────────────────────────────────────────┐
   │  Step 6   (AI inference + automated)                         │
   │  06_distill.py                                             │
   │                                                           │
   │  AI condenses extracts → knowledge/learning-*.md           │
   │  --add-sources appends local backup file references        │
   └───────────────────────────────────────────────────────────┘
```

### Data Flow

| File | Created by | Used by | Description |
|------|-----------|---------|-------------|
| `excerpts.json` | `00_abstract.py --extract` | Claude Code | Title + first messages per conversation |
| `abstracts.json` | Claude Code session | `00_discover.py`, `01`–`04` | 3-7 word topic label per conversation |
| `cluster_membership.json` | `00_discover.py` | `01_scan`, `02_rescan`, `04_deep` | Direct conv_id → category mapping |
| `config.json` | `00_discover.py` | All pipeline steps | Categories, keywords, triage rules |
| `inventory.json` | `01_scan.py` | Steps `02`–`06` | One entry per conversation with category + triage |
| `CHECKLIST.md` | `03_build_checklist.py` | Human | Markdown review checklist |
| `category_extracts/*.json` | `05_extract.py` | `06_distill.py` / Claude Code | Conversation content grouped by category (with IDs + backup file refs) |
| `knowledge/learning-*.md` | Claude Code (distillation) + `--add-sources` | End user / AI assistants | Final knowledge files with source traceability |

---

## Quick Start

### 1. Get Your Export

1. ChatGPT → Settings → Data Controls → Export Data
2. Wait for the email, download and unzip
3. You'll have a folder with `conversations-000.json`, `conversations-001.json`, etc.

### 2. Create a Seed File

```json
{
  "backup_dir": "/path/to/OpenAI-Export",
  "language_strategy": "unified",
  "min_cluster_size": 3
}
```

### 3. Run the Full Pipeline

From a Claude Code session, just say: *"Run the full pipeline on myrun/ with seed.json"*

Or run step by step:

```bash
# Step 0a: Extract excerpts + topic-label them (AI inference)
python 00_abstract.py --extract --config seed.json --dir myrun/

# Step 0b: Discover categories from abstracts
python 00_discover.py --seed myrun/seed.json

# Steps 1–5: Automated pipeline
python run.py --config myrun/config.json

# Step 6: Distill extracts into knowledge files (AI inference)
python 06_distill.py --status --dir myrun/

# Step 6b: Add source traceability links (automated)
python 06_distill.py --add-sources --dir myrun/
```

---

## Three-Tier Categorization

The pipeline assigns categories using three methods in order of reliability:

```
Tier 1: Cluster Membership   (authoritative, ~99.5% accurate)
    ↓ not found
Tier 2: Abstract Matching     (precise, keywords against topic label)
    ↓ no match
Tier 3: Raw Text Matching     (broad, keywords against conversation text)
    ↓ no match
    → uncategorized
```

### Tier 1 — Cluster Membership

During discovery (step 0b), conversations are grouped into clusters based on shared words in their AI-generated topic labels. Every conversation in a cluster is directly mapped to that cluster's category via `cluster_membership.json`. This mapping is **authoritative** — steps 01, 02, and 04 never re-categorize these items.

**Typical accuracy:** ~99.5%. A 1,308-conversation export yielded 608 cluster-assigned items with ~3 errors.

### Tier 2 — Abstract Matching

For conversations not in any cluster, the pipeline matches the conversation's topic label (from `abstracts.json`) against category keywords from `config.json`. Since topic labels are short and topically precise, a single strong keyword hit (3+ points) is sufficient.

**Used in:** steps 01 and 04.

### Tier 3 — Raw Text Matching

For conversations without a usable topic label, the pipeline matches keywords against actual conversation content (title + user/assistant messages). Since raw text is noisy and may contain incidental keyword hits, stricter thresholds apply: **4+ distinct keyword hits** required.

**Typical accuracy:** ~70%. This tier adds coverage at the cost of some false positives. In a 1,308-conversation test, it correctly categorized ~82 items but miscategorized ~35.

**Used in:** steps 01, 02, and 04.

### Coverage vs. Accuracy Tradeoff

Tested on a 1,308-conversation export (639 qualifying with 6+ messages):

| Configuration | Coverage | Accuracy | Notes |
|--------------|----------|----------|-------|
| Cluster-only (tier 1) | 66.8% | ~99.5% | Highest quality, lowest coverage |
| Cluster + abstract + text (all tiers) | 76.5% | ~95% | Production default |
| Looser text matching (min_hits=2) | 81.7% | ~93% | Higher coverage, more noise |

---

## Step Reference

### Step 0a: `00_abstract.py` — Topic Labeling

**Purpose:** Generate a 3-7 word topic label per conversation using AI.

**Why this exists:** ChatGPT auto-generates titles from the first message and never updates them when the conversation topic shifts. Parsing actual content produces dramatically better topic labels.

**Modes:**
- `--extract` — Extract excerpts from conversations → `excerpts.json`
- `--show-prompt` — Print the topic labeling prompt for Claude Code

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--config` | `seed.json` | Config with `backup_dir` |
| `--dir` | `.` | Output directory for excerpts.json |

**Logic:**
1. Reads each conversation, extracts `id`, `title`, and first 3 user messages (300 chars each)
2. Writes `excerpts.json` with all conversations
3. User feeds this to Claude Code with the built-in prompt
4. Claude Code produces `abstracts.json`: `{ "conv_id": "3-7 word topic label", ... }`

**Prompt rules for topic labels:**
- 3-7 words, lowercase, English
- Describe the **topic**, not the format (bad: "SSL connection error"; good: "SSL TLS certificate renewal")
- Never end with generic action words (error, issue, setup, configuration, guide, overview)
- Use `general-chat` for conversations with no clear single topic

**Batch processing:** ~50 conversations per batch. Total cost ~200K tokens for ~900 conversations.

---

### Step 0b: `00_discover.py` — Topic Discovery

**Purpose:** Cluster conversations by topic label similarity, generate `config.json` with categories and keywords, and output `cluster_membership.json` with direct conversation-to-category mappings.

**Modes:**
- Interactive: `--backup /path` — asks questions, reviews clusters
- Non-interactive: `--seed seed.json` — reads answers from seed file

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--backup` | — | Path to OpenAI export (interactive mode) |
| `--seed` | — | Path to seed config (non-interactive mode) |
| `--output` | `./config.json` | Where to write the generated config |
| `min_cluster_size` | `5` (in seed) | Minimum conversations to form a cluster |

**Logic — Abstract-based clustering (when `abstracts.json` present):**

1. **Tokenize labels:** Extract words from each conversation's topic label, filtering stop words, generic words, and `ABSTRACT_GENERIC` words
2. **Build inverted index:** Map each label word → set of conversation indices
3. **Greedy clustering:** Starting from the most frequent word:
   - Collect all conversations containing that word
   - If cluster size ≥ `min_cluster_size`, accept it
   - Find co-occurring words (in ≥20% of cluster members)
   - Mark these conversations as used
4. **Merge clusters:** Clusters sharing 2+ keywords get combined
5. **Enforce 2-word minimum:** Each cluster must produce at least 2 non-generic keywords for its name. If only 1, try extracting a second from member labels. If still only 1, the cluster is dropped.
6. **Name categories:** First two non-generic keywords joined with hyphen (e.g., `docker-compose`, `excel-pivot`)
7. **Generate keywords:** Strong keywords (first 5 from cluster) + medium keywords (next 5 from cluster + title-derived words appearing in 20%+ of cluster members)
8. **Write `cluster_membership.json`:** Maps every clustered conversation ID directly to its category

**ABSTRACT_GENERIC filter (~80 words):**

Words that cannot anchor clusters or appear in category names. Prevents garbage clusters from ambiguous terms. Includes:
- Format words: comparison, overview, guide, tutorial, troubleshooting
- Language names: dutch, english, german, french, spanish
- Generic nouns: system, update, code, control, service, process, management, tool, device
- Common verbs/modifiers: design, power, smart, home, create, build, work, install, change

**Fallback clustering (no abstracts):**
- Tokenizes title + first 10 messages per conversation
- Computes IDF per word: `log(N / (1 + doc_freq))`
- Scores anchor candidates: `doc_freq × IDF²`
- Co-occurrence threshold: 40% of cluster, lift ≥ 3.0x
- Requires ≥2 domain words (length ≥6)

**Key thresholds:**

| Threshold | Value | Purpose |
|-----------|-------|---------|
| Co-occurrence (abstracts) | 20% of cluster | Capture sub-topics in diverse clusters |
| Co-occurrence (fallback) | 40% of cluster | Tighter for noisier input |
| Merge threshold | 2+ shared keywords | Combine overlapping clusters |
| Min keywords for naming | 2 non-generic | Prevent ambiguous single-word categories |
| Title keyword frequency | 20% of cluster members | Extract medium keywords from conversation titles |

---

### Step 01: `01_scan.py` — Initial Scan & Categorization

**Purpose:** Parse all conversations, build `inventory.json` with initial category and triage assignments.

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--config` | `config.json` | Path to config file |

**Inputs:** `config.json`, `cluster_membership.json`, `abstracts.json`, raw conversations
**Output:** `inventory.json`

**Logic:**

For each conversation:
1. Extract metadata: title, date, message count, language, first user message, custom GPT flag
2. **Categorize** using the three-tier system:
   - If title in `already_processed` → category `already-processed`, triage `done`
   - If conversation ID in `cluster_membership.json` → use that category (tier 1)
   - Else: keyword match against abstract text or raw text (tiers 2/3), `min_score=2`
3. **Triage:**
   - `msg_count ≤ skip_threshold` → `skip`
   - `msg_count ≤ skip_candidate_threshold` → `skip-candidate`
   - Otherwise → `review`
4. **Outdated check:** If triage is `review` or `skip-candidate`, check against `outdated_indicators` + `howto_signals`

**What it reads per conversation:** Title + first user message (500 chars)

**Categorization function (`categorize`):**
- Supports both `{strong, medium}` keyword dicts and flat lists
- At this stage, all keywords score 1 point each (no weighting)
- `min_score` parameter controls minimum hits required (default: 2)

**Inventory entry structure:**
```json
{
  "id": "conversation-uuid",
  "title": "ESP32 LED Setup",
  "date": "2024-03-15",
  "message_count": 12,
  "language": "en",
  "category": "esp32-board",
  "triage": "review",
  "outdated_reason": null,
  "first_user_preview": "How do I connect...",
  "custom_gpt": false
}
```

---

### Step 02: `02_rescan.py` — Deeper Re-categorization

**Purpose:** Improve categorization by reading actual conversation content, not just titles.

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--config` | `config.json` | Path to config file |

**Inputs:** `inventory.json`, `config.json`, `cluster_membership.json`, `abstracts.json`, raw conversations
**Output:** Updated `inventory.json`

**Logic:**

For each conversation (except `triage=done` and cluster-assigned items):
1. Build search text: prefer abstract over raw content
   - If abstract exists: `title + abstract` (more precise)
   - Else: `title + first 3 user messages` (noisier)
2. Re-categorize with `min_score=2`
3. **Outdated detection (two rules):**
   - Matches `outdated_indicators` + `howto_signals` → outdated
   - Date < cutoff AND ≤10 messages AND matches generic Q&A patterns ("what is", "explain", "how to", "difference between") + tech keywords → outdated

**Key difference from step 01:** Reads 3 user messages instead of just the first. Can change an existing category if a better match is found (except cluster-assigned items, which are never touched).

---

### Step 03: `03_build_checklist.py` — Review Checklist

**Purpose:** Generate a human-readable Markdown checklist for manual review.

**Input:** `inventory.json`
**Output:** `CHECKLIST.md`

**Format:** Grouped by category, then triage status:
- `[x]` — done/outdated (no action needed)
- `[ ]` — review/skip-candidate (needs human review)
- `[-]` — skip (trivial)

Includes summary tables with category and triage distribution counts.

---

### Step 04: `04_deep_categorize.py` — Weighted Keyword Scoring

**Purpose:** Categorize remaining uncategorized items using weighted scoring on deeper content analysis.

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--config` | `config.json` | Path to config file |

**Inputs:** `inventory.json`, `config.json`, `cluster_membership.json`, `abstracts.json`, raw conversations
**Output:** Updated `inventory.json`

**Logic:**

For each uncategorized conversation (skipping cluster-assigned items):
1. **Try abstract matching first** (tier 2):
   - Search text: `title + abstract`
   - Scoring: strong keywords = 3 points, medium = 1 point
   - Threshold: `min_confidence=3`, `min_hits=1`
   - Rationale: abstracts are precise enough that 1 strong keyword hit is reliable

2. **Fall back to raw text matching** (tier 3):
   - Search text: title + first 5 user messages (500 chars each) + first 3 assistant messages (300 chars each)
   - Scoring: strong keywords = 3 points, medium = 1 point
   - Threshold: `min_confidence=4`, `min_hits=4`
   - Rationale: raw text is noisy; requiring 4+ distinct keyword hits reduces false positives

3. **Additional outdated detection** on newly categorized tech items

**Scoring function (`score_categories`):**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `min_confidence` | 3 (abstract) / 4 (text) | Minimum weighted score to assign |
| `min_hits` | 1 (abstract) / 4 (text) | Minimum distinct keyword matches |
| Strong weight | 3 points | Domain-specific keywords |
| Medium weight | 1 point | Supporting keywords |

**Why two thresholds:** A single strong keyword like "docker" in raw text would score 3 points — enough to categorize with just `min_confidence=3`. But "docker" might appear incidentally in any conversation about software. Requiring `min_hits=4` ensures the conversation actually discusses the category topic in depth.

---

### Step 04b: `04b_classify.py` — Statistical Classifier

**Purpose:** Classify remaining uncategorized conversations using TF-IDF statistical profiles built from already-categorized items.

**Inputs:** `inventory.json`, `config.json`, raw conversations
**Output:** Updated `inventory.json`

**Logic:**

1. Build TF-IDF vocabulary from all categorized conversations
2. Build per-category statistical profiles (top 500 distinctive features per category)
3. For each uncategorized item, read messages progressively (3 → 6 → 12 → 25 → all)
4. Score against all category profiles using cosine-like similarity
5. Assign if three gates pass:

| Gate | Threshold | Purpose |
|------|-----------|---------|
| Relative margin | Top score > #2 by 10-15% | Prevents ambiguous assignments |
| Absolute score | ≥40% of category average | Prevents weak matches |
| Keyword anchor | ≥1 config keyword OR ≥3 of top 20 profile features | Prevents noise-driven misclassification |

**Key thresholds:**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `MIN_TRAINING_DOCS` | 20 | Categories need enough data for reliable profiles |
| Distinctiveness | 2.0x | Profile words must appear 2x more in category than elsewhere |
| Progressive batches | 3, 6, 12, 25, all | Read more messages until confident |
| Message truncation | 1000 chars | Per-message limit |

---

### Step 05: `05_extract.py` — Content Extraction

**Purpose:** Extract valuable content from each category into structured JSON files for AI distillation, with full source traceability back to the local backup files.

**Input:** `inventory.json`, raw conversations
**Output:** `category_extracts/<category>.json`

**Logic:**

For each conversation with `triage ∉ {skip, outdated, done}`:
- Extract first 3 user messages (1000 chars each)
- Extract first 2 assistant responses (1000 chars each)
- For longer chats (6+ messages): include last user message (500 chars) for context
- Include metadata: `id`, `title`, `date`, `message_count`, `triage`, `custom_gpt`, `backup_file`

Each extract file contains a `_meta` header with language strategy and target language (from config), so the distillation step knows what language to write in.

**Source traceability fields:**
- `id` — conversation UUID (matches the key in the backup JSON)
- `backup_file` — which `conversations-NNN.json` file contains this conversation

**ID backfilling:** When re-running on a project where some conversations are already marked `done` (and therefore not re-extracted), the script automatically backfills `id` and `backup_file` into existing extract files by matching on `title + date` against `inventory.json`.

---

### Step 06: `06_distill.py` — Knowledge Distillation & Source Linking

**Purpose:** Condense category extracts into structured knowledge files, then link each file back to its source conversations in the local backup.

**Distillation requires AI inference (Claude Code performs this automatically). Source linking is fully automated.**

**Modes:**
- `--status` — Show distillation progress (pending/done per category)
- `--show-prompt` — Print the distillation prompt
- `--add-sources` — Append `## Bronnen` section with local backup references to all knowledge files

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--dir` | `.` | Run directory containing `category_extracts/` and `knowledge/` |

**Workflow:**
1. `python 06_distill.py --status --dir myrun/` — see what needs distilling
2. In Claude Code: "Distill myrun/category_extracts/ into knowledge files in myrun/knowledge/"
3. Claude reads each extract, condenses conversations, writes one `learning-[category]-[date].md`
4. `python 06_distill.py --status --dir myrun/` — verify completeness
5. `python 06_distill.py --add-sources --dir myrun/` — append source references

**Output format:** `knowledge/learning-[category]-yyyymmdd.md`

**Distillation rules (from the built-in PROMPT):**
- Extract **knowledge**, not conversation — strip greetings, back-and-forth, noise
- **Deduplicate** across conversations covering the same ground
- Organize by **sub-topic** with clear markdown headers
- Preserve **specifics**: exact commands, config values, URLs, model numbers, version numbers
- **Flag contradictions** when conversations contain conflicting information
- Skip trivial `skip-candidate` conversations with no real knowledge
- Write in the language specified by the extract's `_meta` header
- Do NOT add a sources section — the pipeline adds it automatically

**Language handling:** Translation happens at distillation time, not extraction. The `_meta` header tells Claude Code which language to produce.

**Source linking (`--add-sources`):**

Appends a `## Bronnen` table to each knowledge file with columns:

| Column | Content |
|--------|---------|
| Gesprek | Conversation title |
| Datum | Date of conversation |
| Berichten | Message count (indicates depth of the original conversation) |
| Bronbestand | Full path to the local backup JSON file (e.g., `//FS/Backups/AI/.../conversations-003.json`) |
| Gesprek-ID | UUID to search for within that backup file |

This provides full traceability from any distilled knowledge item back to the complete original conversation in the local backup — no dependency on ChatGPT being online or the account existing.

**Idempotent:** Re-running `--add-sources` replaces existing Bronnen sections. Safe to re-run after re-extraction or reorganization.

---

### Post-Distillation: `reorganize_knowledge.py` — Topical Cleanup (Optional)

**Purpose:** Move misplaced sections between knowledge files after distillation.

**⚠ Cost warning:** This step requires AI agents to read ALL knowledge files in depth to identify misplaced content. For a 120-file run, expect ~250K tokens across 5 parallel review agents. The MOVES list must be curated from the review results before the script can run. Only proceed if topical consistency matters for your use case.

The categorization pipeline achieves ~95% accuracy, but ~5% of conversations end up in the wrong category. After distillation, this surfaces as sections that don't belong in their file's topic. This script automates the cleanup.

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--dir` | — | Knowledge directory path |
| `--dry-run` | — | Show planned moves without executing |

**Usage:**
```bash
# Preview what will be moved
python reorganize_knowledge.py --dir myrun/knowledge --dry-run

# Execute moves
python reorganize_knowledge.py --dir myrun/knowledge
```

**How it works:**
1. Reads all `learning-*.md` files
2. Splits each file by `##` headings
3. Matches section headings against a curated `MOVES` list (source → destination)
4. Removes matched sections from source files, appends them to destination files
5. Sections with no matching category go to `learning-various-[date].md`
6. Deletes files that become empty after all their sections are moved

**The MOVES list** is curated by reviewing all knowledge files for topical consistency (typically via AI agents reading each file). It lives in the script as a Python list of `(source_category, heading_substring, destination_category)` tuples.

**Workflow for populating the MOVES list:**
1. Have AI agents read all knowledge files in batches (25-30 files per agent)
2. For each file, flag sections that don't belong topically
3. Suggest destination categories from the existing 126-category list
4. Add entries to the MOVES list
5. Run with `--dry-run` to verify, then execute

---

### `06_suggest_keywords.py` — Keyword Suggestions (Optional)

**Purpose:** Analyze uncategorized conversations and suggest keywords to improve coverage.

**Parameters:**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `--config` | `config.json` | Path to config file |
| `--top` | `30` | Number of suggestions per type |

**Three suggestion types:**
1. **Frequent words** in uncategorized items (≥3 occurrences) not already in config
2. **Frequent bigrams** (word pairs, ≥2 occurrences) not already in config
3. **Category-specific candidates** — words distinctive to an existing category that also appear frequently in uncategorized items

---

## Shared Utilities (`shared.py`)

### `keyword_in_text(keyword, text)`

Word-boundary-aware keyword matching.

- **Single-word keywords** (any length): use regex `(?<![a-z])keyword(?![a-z])` — prevents "compose" matching "composers", "design" matching "designated", "sso" matching "espresso"
- **Multi-word phrases**: use substring matching — phrases like "raspberry pi" or "power bi" are inherently specific

### `detect_language(text)`

Language detection via function word frequency. Counts matches against `LANG_MARKERS` (en/nl/fr/de/es, ~30-50 markers each). Returns ISO code if ≥3 hits, else `"unknown"`. Requires ≥10 words in input.

### `tokenize(text)`

Splits text into lowercase tokens ≥3 characters, filtering stop words. Regex: `[a-z\u00e0-\u024f][a-z\u00e0-\u024f0-9]{2,}`.

### Word lists

| List | Size | Purpose |
|------|------|---------|
| `STOP_WORDS` | ~400 | Function words in en/nl/fr filtered during tokenization |
| `GENERIC_WORDS` | ~500 | Too generic to define a topic (adjectives, verbs, ChatGPT artifacts) |

---

## Configuration Reference

### Full Config (`config.json`)

```jsonc
{
  // Path to unzipped OpenAI data export
  "backup_dir": "/path/to/OpenAI-Export",

  // Language handling for output files
  "language_strategy": "unified",   // unified|preserve|translate|multilingual

  // Target language (required for translate/multilingual; auto-detected for unified)
  "target_language": "nl",

  // Categories with keywords — auto-generated by 00_discover.py
  "categories": {
    "docker-compose": {
      "strong": ["docker", "compose"],          // 3 points each in weighted scoring
      "medium": ["vps", "container", "traefik"]  // 1 point each
    },
    "recipe-calorie": {
      "strong": ["recipe", "calorie", "muffin"],
      "medium": ["baking", "ingredients"]
    }
  },

  // Triage rules
  "triage": {
    "skip_threshold": 2,
    "skip_candidate_threshold": 5,
    "outdated_before": "2024-06-01",
    "outdated_indicators": { "docker": "Docker setup" },
    "howto_signals": ["how to", "setup", "install"]
  },

  // Titles already distilled in a previous run
  "already_processed": ["Some Chat Title"]
}
```

### Seed Config (`seed.json`)

Minimal file for non-interactive discovery:

```jsonc
{
  "backup_dir": "/path/to/OpenAI-Export",     // required
  "language_strategy": "unified",             // required
  "target_language": "en",                    // required for translate/multilingual
  "min_cluster_size": 3                       // optional, default: 5
}
```

### Language Strategies

| Strategy | Behavior | Requires `target_language` |
|----------|----------|---------------------------|
| `unified` | Auto-detect dominant language, translate everything to it | No (auto-detected) |
| `preserve` | Split output files by language (e.g., `infra-en.json`, `infra-nl.json`) | No |
| `translate` | Translate everything to specified target language | **Yes** |
| `multilingual` | Include both original + translated content | **Yes** |

### All Parameters

| Parameter | Location | Default | Effect |
|-----------|----------|---------|--------|
| `backup_dir` | config/seed | — | Path to OpenAI export |
| `language_strategy` | config/seed | **required** | Language handling mode |
| `target_language` | config/seed | auto-detected | ISO 639-1 target language |
| `min_cluster_size` | seed | `5` | Minimum conversations per cluster |
| `skip_threshold` | triage | `2` | Messages ≤ this → triage `skip` |
| `skip_candidate_threshold` | triage | `5` | Messages ≤ this → `skip-candidate` |
| `outdated_before` | triage | `2024-06-01` | Date cutoff for outdated detection |
| `already_processed` | config | `[]` | Titles to mark as `done` |

---

## Triage System

| Status | Meaning | Rule |
|--------|---------|------|
| `skip` | Too short to contain knowledge | ≤ `skip_threshold` messages (default: 2) |
| `skip-candidate` | Short, probably not worth processing | ≤ `skip_candidate_threshold` messages (default: 5) |
| `review` | Likely contains knowledge | 6+ messages |
| `outdated` | Generic how-to that current AI supersedes | Matches outdated indicators + how-to signals |
| `done` | Already processed in a previous run | Title in `already_processed` |

---

## Directory Structure

```
AIKnowledgeDistill/
├── 00_abstract.py          # Step 0a: Topic labeling (Claude Code)
├── 00_discover.py          # Step 0b: Topic discovery & config generation
├── 01_scan.py              # Step 1: Initial scan & categorize
├── 02_rescan.py            # Step 2: Deeper re-categorization
├── 03_build_checklist.py   # Step 3: Human review checklist
├── 04_deep_categorize.py   # Step 4: Weighted keyword scoring
├── 04b_classify.py         # Step 4b: TF-IDF statistical classifier
├── 05_extract.py           # Step 5: Content extraction
├── 06_distill.py           # Step 6: Knowledge distillation + source linking
├── 06_suggest_keywords.py  # Optional: keyword suggestions
├── reorganize_knowledge.py # Optional: post-distillation topical cleanup
├── run.py                  # Pipeline orchestrator (steps 1–5)
├── shared.py               # Shared utilities
├── docs/
│   └── README.md           # This file
└── testrun5/               # Example run
    ├── seed.json
    ├── abstracts.json       # 919 topic labels
    ├── cluster_membership.json  # 608 direct assignments
    ├── config.json          # 92 categories
    ├── inventory.json       # 1308 conversations
    ├── CHECKLIST.md
    ├── category_extracts/   # 126 extract files (with conv IDs + backup refs)
    └── knowledge/           # Distilled knowledge files
        ├── learning-docker-compose-20260308.md  # includes ## Bronnen section
        ├── learning-various-20260308.md         # catch-all for orphan sections
        └── ...
```

---

## Typical Workflows

### Full Pipeline from Claude Code (Recommended)

When run from a Claude Code session, the entire pipeline is **end-to-end automated** — Claude Code both executes the Python scripts and performs the AI inference steps (topic labeling and distillation). No manual intervention required.

```
"Run the full AIKnowledgeDistill pipeline on myrun/ with seed.json"
```

Claude Code will execute all steps in sequence:

```bash
mkdir myrun

# Step 0a: Extract excerpts, then topic-label them (AI inference)
python 00_abstract.py --extract --config seed.json --dir myrun/
# Claude Code reads excerpts.json and generates abstracts.json

# Step 0b: Discover categories from abstracts
python 00_discover.py --seed myrun/seed.json

# Steps 1–5: Automated Python pipeline
python run.py --config myrun/config.json

# Step 6: Distill extracts into knowledge files (AI inference)
# Claude Code reads each category_extract and writes learning-*.md files

# Step 6b: Add source traceability (automated)
python 06_distill.py --add-sources --dir myrun/
```

At this point, the pipeline is complete. Claude Code should **ask the user** whether to run the optional post-distillation reorganization:

> *"Knowledge files are ready. ~5% of sections may be topically misplaced due to categorization noise. I can review all files and reorganize misplaced content, but this costs ~250K tokens (5 parallel agents reading every file). Want me to proceed?"*

If the user agrees:

```bash
# Review all knowledge files for misplaced content (AI inference, ~250K tokens)
# → Produces a MOVES list for reorganize_knowledge.py

# Execute the reorganization
python reorganize_knowledge.py --dir myrun/knowledge

# Re-add source links after reorganization (idempotent)
python 06_distill.py --add-sources --dir myrun/
```

### Without Claude Code (Standalone)

Steps 0a and 6 require AI inference. Without Claude Code, you need to provide
topic labels and distillation via another LLM (API calls, ChatGPT, etc.).

```bash
# Step 0a: Extract excerpts
python 00_abstract.py --extract --config seed.json --dir myrun/
# → Feed myrun/excerpts.json to an LLM → save as myrun/abstracts.json

# Step 0b + Steps 1–5: Fully automated
python 00_discover.py --seed myrun/seed.json
python run.py --config myrun/config.json

# Step 6: Feed each category_extract to an LLM with the distillation prompt
python 06_distill.py --show-prompt  # get the prompt
# → LLM writes knowledge/learning-*.md files

# Step 6b: Add source traceability (automated)
python 06_distill.py --add-sources --dir myrun/
```

### Iterative Improvement

```bash
# Check what's still uncategorized
python 06_suggest_keywords.py --config myrun/config.json

# Add keywords to config, re-run
python run.py --config myrun/config.json
```

---

## Tested Results

Validated against a 1,308-conversation ChatGPT export (April 2023 — March 2026, mixed English/Dutch):

| Metric | Value |
|--------|-------|
| Total conversations | 1,308 |
| Qualifying (6+ messages) | 639 |
| Cluster-assigned | 608 (92 categories) |
| Coverage (qualifying) | 76.5% |
| Overall accuracy | ~95% |
| Categories produced | 92 |
| Distillable categories (3+ qualifying) | 77 |
| Knowledge files produced (after distillation) | 126 |
| Knowledge files after reorganization | 121 (6 emptied, 1 catch-all added) |
| Misplaced sections identified | 130 |
| Sections moved to correct file | 130 |
| Source-linked knowledge files | 120 |

### Quality by Tier

| Tier | Items | Accuracy | Notes |
|------|-------|----------|-------|
| Cluster membership | 608 | ~99.5% | 3 errors (topic label ambiguity) |
| Keyword matching | 117 | ~70% | 35 errors (incidental keyword hits) |
| **Overall** | **725** | **~95%** | Cluster quality drives the aggregate |

### Remaining Uncategorized

The ~120 uncategorized qualifying conversations are genuinely unique one-off topics (biometrics, fridge repair, perfume shopping, etc.) that don't cluster with anything. ~20 of these have `general-chat` as their topic label, meaning even AI couldn't identify a clear topic.
