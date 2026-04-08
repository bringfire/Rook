"""Strip Ps3 (NeighborEvolver) damage from all A-MEM notes.

Removes:
- "Related insight: ..." text appended to solution_principle
- evolution_history entries (confabulated rationales)
- evolved_by lists (tracking which note triggered Ps3)
- last_evolved timestamps

Preserves:
- All original note content (type_data, components, etc.)
- links (from Ps2 — useful for retrieval)
- tags (hard to separate Ps3 noise, low impact)

Usage:
    cd mcp_server
    python run_ps3_cleanup.py [--dry-run]
"""

import argparse
import json
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NOTES_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge", "gh", "notes")


def strip_related_insights(text: str) -> str:
    """Remove all 'Related insight: ...' content from text.

    Handles both '\n\nRelated insight: ...' (appended to existing text)
    and cases where the entire text starts with 'Related insight: ...'
    (solution_principle was empty, so Ps3 set it directly).
    """
    # Split on the pattern (with or without leading newlines)
    parts = re.split(r"(?:\n\n)?Related insight:", text)
    result = parts[0].strip()
    return result


def clean_note(data: dict) -> tuple[dict, list[str]]:
    """Clean Ps3 damage from a note dict. Returns (cleaned_data, list_of_changes)."""
    changes = []

    # Strip "Related insight:" from solution_principle
    sp = data.get("solution_principle", "")
    if "Related insight:" in sp:
        data["solution_principle"] = strip_related_insights(sp)
        changes.append("stripped Related insight from solution_principle")

    # Strip "Related insight:" from context too (just in case)
    ctx = data.get("context", "")
    if "Related insight:" in ctx:
        data["context"] = strip_related_insights(ctx)
        changes.append("stripped Related insight from context")

    # Clear evolution_history (confabulated rationales)
    if data.get("evolution_history"):
        count = len(data["evolution_history"])
        data["evolution_history"] = []
        changes.append(f"cleared {count} evolution_history entries")

    # Clear evolved_by
    if data.get("evolved_by"):
        count = len(data["evolved_by"])
        data["evolved_by"] = []
        changes.append(f"cleared {count} evolved_by entries")

    # Clear last_evolved
    if data.get("last_evolved"):
        data["last_evolved"] = None
        changes.append("cleared last_evolved")

    return data, changes


def main():
    parser = argparse.ArgumentParser(description="Strip Ps3 damage from A-MEM notes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    args = parser.parse_args()

    notes_files = sorted(glob.glob(os.path.join(NOTES_DIR, "*.json")))
    print(f"Found {len(notes_files)} note files")

    total_cleaned = 0
    total_unchanged = 0
    all_changes = {}

    for filepath in notes_files:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        note_id = data.get("note_id", os.path.basename(filepath))
        cleaned, changes = clean_note(data)

        if changes:
            total_cleaned += 1
            all_changes[note_id] = changes

            if args.dry_run:
                print(f"  WOULD CLEAN {note_id}: {'; '.join(changes)}")
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(cleaned, f, indent=2, ensure_ascii=False)
                print(f"  CLEANED {note_id}: {'; '.join(changes)}")
        else:
            total_unchanged += 1

    print(f"\n=== Summary ===")
    print(f"Cleaned: {total_cleaned}")
    print(f"Unchanged: {total_unchanged}")
    print(f"Total: {len(notes_files)}")

    if args.dry_run:
        print("\nDry run — no files modified.")


if __name__ == "__main__":
    main()
