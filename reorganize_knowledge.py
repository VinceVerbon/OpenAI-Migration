"""
Post-distillation knowledge file reorganizer.

Reads all learning-*.md files, identifies misplaced sections by heading,
moves them to correct destination files or a catch-all 'various' file.

Usage: python reorganize_knowledge.py --dir testrun5/knowledge --dry-run
       python reorganize_knowledge.py --dir testrun5/knowledge
"""
import os
import re
import sys
import argparse
from collections import defaultdict

# Each move: (source_category, section_heading_substring, destination_category)
# destination_category = "various" means catch-all
# section_heading_substring matches against ## heading text (case-insensitive)
MOVES = [
    # === Batch 1 (files 1-25) ===
    ("aalsmeer-restaurant", "Motorolie viscositeit", "various"),
    ("account-tax", "Insta360 Studio login", "creation-camera"),
    ("account-tax", "360-video bekijken", "creation-camera"),
    ("account-tax", "Datanormalisatie", "various"),
    ("account-tax", "KPI formulier", "various"),
    ("advice-teenage", "Videokaart upgrade", "purchase-rtx"),
    ("advice-teenage", "3D Scanner", "purchase-rtx"),
    ("architecture-business", "RUTX11", "camper-installation"),
    ("blood-potassium", "Vochtmeter", "various"),
    ("board-azure", "Confluence", "various"),
    ("business-servicenow", "ArchiMate", "archimate-bpmn"),
    ("business-servicenow", "Anonieme SMS", "various"),
    # ("business-servicenow", "Lettertypen jaarverslag", "various"),  # ###-level, fits parent section
    ("capability-mapping", "Authenticatie vs autorisatie", "security-casb"),
    ("charging-expense", "ITIL/ITSM begrippen", "itil-change"),
    ("chatgpt-canvas", "IAM API-integratie", "identity-iga"),
    ("child-appropriate", "Power Query", "excel-pivot"),
    ("child-appropriate", "Gedichten en visuals", "children-story"),
    ("code-claude", "LoRaWAN GPS", "arduino-nano"),
    ("code-claude", "Emoji met onzichtbare", "various"),
    ("code-claude", "TOTP mismatch", "teltonika-trb140"),
    ("code-claude", "Git-gebaseerde notitie", "various"),
    ("code-claude", "Windows Terminal foutmelding", "windows-stability"),
    ("configuration-openai", "Linux sudo NOPASSWD", "usage-linux"),
    ("contact-lens", "ESTA voor CES", "ces-quantum"),
    ("contact-lens", "Barrel jack connector", "electronics-resistor"),

    # === Batch 2 (files 26-50) ===
    ("control-pest", "Andorra", "various"),
    ("control-pest", "Controls modelleren in ArchiMate", "archimate-bpmn"),
    ("conversion-olm", "Bakken: baksoda", "recipe-calorie"),
    ("cost-program", "Teltonika RMS", "teltonika-trb140"),
    # ("creation-camera", "ESP32 sensor latency", "esp32-board"),  # ###-level under color sensor, related
    ("design-laser", "PowerPoint diamodel", "various"),
    ("design-laser", "AutoCAD 3D solids", "usage-autodesk"),
    ("device-wearable", "TASCAM", "various"),
    ("directory-entra", "Application Delivery Controller", "network-gbit"),
    ("edge-https", "Meta Quest", "various"),
    ("error-ios", "Arduino Nano upload error", "arduino-nano"),
    ("error-ios", "MKR1500NB MQTT", "iot-sim"),
    ("error-ios", "OpenGL-initialisatiefout", "fix-nvidia"),
    ("error-ios", "Homey Hue rate limit", "smart-home"),
    ("excel-formula", "PowerPoint grafiek-as", "various"),
    ("excel-formula", "RSA encryptie", "quantum-computing"),
    ("excel-formula", "Boekhoudkundige basisregels", "account-tax"),
    ("excel-pivot", "Motorolie viscositeit", "various"),
    ("excel-pivot", "Economische begrippen", "various"),
    ("explained-soc2", "UV curing", "design-laser"),
    ("explained-soc2", "Aanbestedingsformule", "documentation-leyon"),
    ("fix-ios", "MindManager naar MS Project", "planning-folder"),
    ("fix-ios", "Claude Code PATH", "installation-claude"),
    ("fix-ios", "Notitieapps met Git", "various"),
    ("fix-ios", "Roblox op ultrawide", "language-roblox"),
    ("fix-ios", "Roblox keyboard", "language-roblox"),
    ("fix-ios", "Vioolpennen slippen", "various"),
    ("fix-nvidia", "WebView2", "windows-stability"),
    ("fix-nvidia", "5 Gbit/s glasvezel", "network-gbit"),

    # === Batch 3 (files 51-76) ===
    ("history-kashmir", "Landal Warsberg", "camping-france"),
    ("history-kashmir", "Autohistorie-rapporten", "various"),
    ("identity-iga", "DDI", "network-gbit"),
    ("installation-claude", "Ubuntu Server Management", "usage-linux"),
    ("installation-claude", "Snap packages", "usage-linux"),
    ("installation-claude", "Automatische updates", "ubuntu-automatic"),
    ("installation-claude", "LVM-volume", "usage-linux"),
    ("instructions-ios", "MPU-9250", "esp32-board"),
    ("instructions-ios", "Spruiten invriezen", "recipe-calorie"),
    ("integration-tuya", "IAM API-integratie", "identity-iga"),
    ("integration-tuya", "Waterhardheid", "various"),
    # ("integration-tuya", "Waarom geen centrale ontharding", "various"),  # moves with parent Waterhardheid
    ("integration-tuya", "Activepieces", "lookup-n8n"),
    ("issue-google", "MS Project Kalenderinstellingen", "planning-folder"),
    ("issue-google", "VPS Emergency Mode", "performance-vps"),
    ("issue-google", "AutoSave / OneDrive", "various"),
    ("issue-google", "Insta360 Studio Login", "creation-camera"),
    ("issue-google", "MindManager Export", "planning-folder"),
    ("itsm-incident", "AI Context Framework", "various"),
    ("language-roblox", "Google Nest Hub Taalprobleem", "smart-home"),
    ("language-roblox", "TASCAM DR-05X Taal", "various"),
    ("language-roblox", "AMBI-modules", "various"),
    ("lookup-n8n", "Pinterest Account", "various"),
    ("meaning-life", "Use Case Diagram", "archimate-bpmn"),
    ("meaning-life", "Jira Issue Types", "board-azure"),
    ("meaning-life", "Over-The-Top", "various"),
    ("meaning-life", "Excel: Dubbele Stijlen", "excel-formula"),
    ("meaning-life", "Woordpuzzel", "various"),
    ("measurement-apple", "DORA Metrics", "itil-change"),
    ("measurement-apple", "Excel Draaitabellen", "excel-pivot"),
    ("microsoft-install", "Microsoft Sentinel", "microsoft-sentinel"),
    ("microsoft-install", "SOC 2 Type II", "explained-soc2"),

    # === Batch 4 (files 77-101) ===
    ("model-generated", "OSI Use Cases", "capability-mapping"),
    ("model-generated", "ArchiMate: Access", "archimate-bpmn"),
    ("name-suggestions", "Websiteplatform", "various"),
    ("name-suggestions", "Company Website", "various"),
    ("name-suggestions", "Open Source Planning", "planning-folder"),
    ("performance-vps", "Audio Interfaces", "music-classical"),
    ("performance-vps", "Apple Pencil", "various"),
    ("planning-folder", "ITIL Change Management", "itil-change"),
    ("planning-folder", "Las Vegas Reistips", "ces-quantum"),
    ("planning-folder", "Website Setup", "various"),
    ("power-voltage", "Power BI Formules", "excel-pivot"),
    ("power-voltage", "Phishing Detectie", "security-casb"),
    ("principle-versus", "SIEM Bronnen", "microsoft-sentinel"),
    ("product-montel", "ServiceNow CSDM", "business-servicenow"),
    ("product-montel", "Huidverzorging", "various"),
    ("profile-program", "Instagram Profielinstellingen", "various"),
    ("quality-masters", "Watertester Waarden", "pool-chlorine"),
    ("quality-masters", "Oude Meesters en Dieren", "various"),
    ("quality-masters", "Contactlenzen", "contact-lens"),
    ("requirements-building", "UK ETA", "camping-france"),
    ("scheduling-sports", "Due Date Wijzigingsproces", "table-governance"),
    ("school-american", "AI Tools voor Tekst", "generation-art"),
    ("scooter-diagnosis", "Arduino Nano Clone", "arduino-nano"),

    # === Batch 5 (files 102-126) ===
    ("security-casb", "Camerasysteem Vergelijking", "smart-home"),
    ("series-crime", "Teltonika Routers voor Camper", "teltonika-trb140"),
    ("software-garden", "Remote Browser Isolation", "security-casb"),
    ("software-garden", "ZTNA versus VPN", "security-casb"),
    ("strategy-transformation", "Arduino MKR1500", "arduino-nano"),
    ("strategy-transformation", "OpenClaw Multi-Model", "various"),
    ("system-american", "Zwembadonderhoud", "pool-chlorine"),
    ("system-american", "RAM-fouten", "windows-stability"),
    ("system-american", "n8n workflows", "docker-compose"),
    ("system-american", "Confluence permissies", "various"),
    ("terminology-planning", "Sluitplaten en sloten", "various"),
    ("test-findings", "Multimeter gebruik", "voltage-electrical"),
    ("test-findings", "Vochtmeting in caissons", "various"),
    ("ubuntu-automatic", "UNC-paden via VPN", "windows-stability"),
    ("usage-autodesk", "VoltTime laadpaal", "charging-expense"),
    ("usage-autodesk", "Leyon Smart Glasses", "device-wearable"),
    ("usage-linux", "Rozemarijn in de keuken", "recipe-calorie"),
    ("usage-linux", "Fusion 360", "usage-autodesk"),
    ("windows-stability", "MQTT testen", "smart-home"),
    ("windows-stability", "Windows Store vs Steam", "various"),
    ("windows-stability", "Xbox Play Anywhere", "various"),
    ("windows-update", "GoDaddy DNS", "various"),
    ("windows-update", "Insta360 X4 als drive", "creation-camera"),
]


def make_filename(cat, date_str):
    return f"learning-{cat}-{date_str}.md"


def split_sections(text):
    """Split markdown into sections by ## headings.
    Returns list of (heading, content) tuples.
    The first element may have heading=None (preamble before first ##).
    """
    sections = []
    current_heading = None
    current_lines = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_heading is not None or current_lines:
                sections.append((current_heading, "\n".join(current_lines)))
            current_heading = line
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading is not None or current_lines:
        sections.append((current_heading, "\n".join(current_lines)))

    return sections


def reassemble(sections):
    """Reassemble sections into markdown text."""
    parts = []
    for heading, content in sections:
        if heading:
            parts.append(heading)
        if content.strip():
            parts.append(content)
    result = "\n".join(parts)
    # Ensure file ends with single newline
    return result.rstrip("\n") + "\n"


def main():
    parser = argparse.ArgumentParser(description="Reorganize knowledge files")
    parser.add_argument("--dir", required=True, help="Knowledge directory")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    args = parser.parse_args()

    knowledge_dir = args.dir
    date_str = "20260308"

    # Read all files into memory
    files = {}
    for fname in os.listdir(knowledge_dir):
        if fname.startswith("learning-") and fname.endswith(".md"):
            path = os.path.join(knowledge_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                files[fname] = f.read()

    print(f"Loaded {len(files)} knowledge files")

    # Track moves
    moved = []
    not_found = []
    modified_files = set()

    # Process each move
    for source_cat, heading_match, dest_cat in MOVES:
        source_file = make_filename(source_cat, date_str)
        dest_file = make_filename(dest_cat, date_str)

        if source_file not in files:
            not_found.append((source_cat, heading_match, "source file missing"))
            continue

        sections = split_sections(files[source_file])
        found = False

        for i, (heading, content) in enumerate(sections):
            if heading and heading_match.lower() in heading.lower():
                found = True
                section_text = heading + "\n" + content

                if args.dry_run:
                    print(f"  MOVE: {source_cat} -> {dest_cat}: {heading.strip()}")
                else:
                    # Remove from source
                    sections.pop(i)
                    files[source_file] = reassemble(sections)
                    modified_files.add(source_file)

                    # Add to destination
                    if dest_file not in files:
                        # Create new file with header
                        if dest_cat == "various":
                            files[dest_file] = "# Diverse Onderwerpen\n\n> Verzameling van losstaande kennisfragmenten zonder duidelijke thuiscategorie.\n\n"
                        else:
                            files[dest_file] = ""
                    files[dest_file] = files[dest_file].rstrip("\n") + "\n\n" + section_text.strip() + "\n"
                    modified_files.add(dest_file)

                moved.append((source_cat, heading_match, dest_cat))
                break

        if not found:
            not_found.append((source_cat, heading_match, "heading not found"))

    # Report
    print(f"\nMoves executed: {len(moved)}")
    if not_found:
        print(f"Not found: {len(not_found)}")
        for src, heading, reason in not_found:
            print(f"  ! {src}: '{heading}' ({reason})")

    # Check for emptied files (only preamble/title remaining)
    emptied = []
    for fname, content in files.items():
        sections = split_sections(content)
        # Count non-preamble sections
        real_sections = [s for s in sections if s[0] is not None]
        if not real_sections:
            lines = content.strip().split("\n")
            # If only title + maybe a quote line remain
            substantive = [l for l in lines if l.strip() and not l.startswith("#") and not l.startswith(">") and not l.startswith("*")]
            if len(substantive) <= 1:
                emptied.append(fname)

    if emptied:
        print(f"\nEmptied files (can be deleted): {len(emptied)}")
        for fname in emptied:
            print(f"  - {fname}")

    if args.dry_run:
        print(f"\n=== DRY RUN — no files modified ===")
        return

    # Write modified files
    for fname in modified_files:
        path = os.path.join(knowledge_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(files[fname])

    # Delete emptied files
    for fname in emptied:
        path = os.path.join(knowledge_dir, fname)
        os.remove(path)
        print(f"  Deleted: {fname}")

    print(f"\nModified: {len(modified_files)} files")
    print(f"Deleted: {len(emptied)} files")
    remaining = len([f for f in os.listdir(knowledge_dir) if f.startswith("learning-") and f.endswith(".md")])
    print(f"Remaining: {remaining} files")


if __name__ == "__main__":
    main()
