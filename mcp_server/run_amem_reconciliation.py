"""Reconcile A-MEM unified store with pattern store after v2 migration.

Handles three cases:
1. RENAME: Orphan notes that match unmatched v2 patterns by name → rename note_id
2. DELETE: Orphan notes that are stale duplicates → remove
3. CREATE: V2 patterns with no A-MEM note at all → create new note

Usage:
    python run_amem_reconciliation.py [--dry-run]
"""
import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from rook.learning.pattern_store import get_pattern_store
from rook.learning.unified_store import get_unified_store
from rook.learning.knowledge_note import KnowledgeNote


def normalize_name(s: str) -> str:
    return s.lower().strip().replace(".gh", "").replace("-", " ").replace("_", " ").replace("  ", " ")


def convert_pattern_to_note(pattern) -> KnowledgeNote:
    """Convert a PatternNote to a KnowledgeNote (same as migrate_patterns_to_unified.py)."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    type_data = {
        "wiring": [],  # v2 patterns have wiring cleared
        "input_structure": pattern.input_structure or {},
        "output_type": pattern.output_type or "",
        "source_definition": pattern.source_definition or "",
        "pattern_type": pattern.pattern_type or "recipe",
        "component_count": len(pattern.components_needed) if pattern.components_needed else 0,
    }
    return KnowledgeNote(
        note_id=f"recipe_{pattern.pattern_id[:8]}",
        note_type="recipe",
        name=pattern.name,
        brief=pattern.solution_brief or f"Recipe from {pattern.source_definition or 'unknown'}",
        created=pattern.created or now,
        version="1.0",
        context=pattern.solution_brief or "",
        keywords=[pattern.name] + (pattern.tags or []),
        category=pattern.tags[0] if pattern.tags else "Uncategorized",
        tags=pattern.tags or [],
        trigger_intents=pattern.trigger_intents or [],
        trigger_symptoms=pattern.trigger_symptoms or [],
        components=pattern.components_needed or [],
        solution_principle=pattern.solution_brief or "",
        anti_patterns=pattern.anti_patterns or [],
        preconditions=pattern.preconditions or [],
        postconditions=[],
        links=[],
        times_used=pattern.times_used or 0,
        times_succeeded=pattern.times_succeeded or 0,
        retrieval_count=0,
        last_accessed=None,
        last_verified=pattern.last_verified,
        citations=pattern.citations or [],
        created_from="v2_migration_reconciliation",
        last_evolved=None,
        evolved_by=[],
        evolution_history=[],
        type_data=type_data,
    )


def main():
    dry_run = "--dry-run" in sys.argv

    print("Loading stores...")
    ps = get_pattern_store()
    us = get_unified_store()
    notes_dir = us.notes_dir

    all_notes = us.all()
    recipes = [n for n in all_notes if n.note_type == "recipe"]

    # Build lookups
    note_by_pid = {}
    for n in recipes:
        pid = n.note_id.replace("recipe_", "")
        note_by_pid[pid] = n

    all_pids = {p.pattern_id for p in ps.patterns.values()}
    v2 = {p.pattern_id: p for p in ps.patterns.values()
          if p.schema_version == "2.0" and p.pattern_type == "recipe"}

    # Find orphan notes (reference non-existent pattern IDs)
    orphan_notes = [(pid, n) for pid, n in note_by_pid.items() if pid not in all_pids]
    # Find v2 patterns without notes
    patterns_no_note = [(pid, p) for pid, p in v2.items() if pid not in note_by_pid]

    # Build lookup: source_def → noted patterns (for duplicate detection)
    src_to_noted = {}
    for pid, p in v2.items():
        if pid in note_by_pid and p.source_definition:
            key = normalize_name(p.source_definition)
            if key not in src_to_noted:
                src_to_noted[key] = []
            src_to_noted[key].append(pid)

    # Build lookup: source_def → unmatched patterns (for rename matching)
    src_to_unmatched = {}
    for pid, p in patterns_no_note:
        if p.source_definition:
            key = normalize_name(p.source_definition)
            if key not in src_to_unmatched:
                src_to_unmatched[key] = []
            src_to_unmatched[key].append((pid, p))

    print(f"\nOrphan notes: {len(orphan_notes)}")
    print(f"V2 patterns without notes: {len(patterns_no_note)}")

    # Phase 1: Match orphans to unmatched patterns by name → source_definition
    renames = []
    deletes = []
    used_pids = set()

    for old_pid, note in orphan_notes:
        name_key = normalize_name(note.name)

        # Try to find an unmatched pattern whose source matches this note's name
        candidates = [(pid, p) for pid, p in src_to_unmatched.get(name_key, [])
                      if pid not in used_pids]
        if candidates:
            new_pid = candidates[0][0]
            used_pids.add(new_pid)
            renames.append((old_pid, new_pid, note, candidates[0][1]))
            continue

        # No match found — check if this is a stale duplicate
        if name_key in src_to_noted:
            deletes.append((old_pid, note, "stale duplicate"))
        else:
            # Truly orphan with no pattern at all — delete
            deletes.append((old_pid, note, "no matching pattern"))

    # Phase 2: Remaining patterns that need brand new notes
    creates = [(pid, p) for pid, p in patterns_no_note if pid not in used_pids]

    print(f"\n=== Reconciliation Plan ===")
    print(f"RENAME: {len(renames)} notes (transfer links to correct pattern ID)")
    for old_pid, new_pid, note, pattern in renames:
        print(f"  recipe_{old_pid} -> recipe_{new_pid} ({note.name}, {len(note.links)} links)")

    print(f"\nDELETE: {len(deletes)} stale notes")
    for old_pid, note, reason in deletes:
        print(f"  recipe_{old_pid}: {note.name} ({reason}, {len(note.links)} links)")

    print(f"\nCREATE: {len(creates)} new notes")
    for pid, p in creates:
        print(f"  recipe_{pid}: {p.name} ({p.source_definition})")

    if dry_run:
        print("\nDRY RUN — no changes made")
        return

    # Execute renames
    renamed = 0
    for old_pid, new_pid, note, pattern in renames:
        old_file = notes_dir / f"recipe_{old_pid}.json"
        new_file = notes_dir / f"recipe_{new_pid}.json"

        if old_file.exists():
            # Read, update ID and source, write to new path
            data = json.loads(old_file.read_text(encoding="utf-8"))
            data["note_id"] = f"recipe_{new_pid}"
            data["type_data"]["source_definition"] = pattern.source_definition or ""
            new_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            old_file.unlink()
            renamed += 1
            print(f"  RENAMED: recipe_{old_pid} -> recipe_{new_pid}")
        else:
            print(f"  SKIP rename: {old_file} not found")

    # Execute deletes
    deleted = 0
    for old_pid, note, reason in deletes:
        old_file = notes_dir / f"recipe_{old_pid}.json"
        if old_file.exists():
            old_file.unlink()
            deleted += 1
            print(f"  DELETED: recipe_{old_pid} ({note.name})")
        else:
            print(f"  SKIP delete: {old_file} not found")

    # Execute creates
    created = 0
    for pid, pattern in creates:
        new_file = notes_dir / f"recipe_{pid[:8]}.json"
        if new_file.exists():
            print(f"  SKIP create: {new_file} already exists")
            continue
        note = convert_pattern_to_note(pattern)
        data = note.to_dict()
        new_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        created += 1
        print(f"  CREATED: recipe_{pid[:8]} ({pattern.name})")

    # Clean up dangling links in remaining notes
    deleted_ids = {f"recipe_{old_pid}" for old_pid, _, _ in deletes}
    if deleted_ids:
        cleaned = 0
        for note_file in notes_dir.glob("*.json"):
            data = json.loads(note_file.read_text(encoding="utf-8"))
            links = data.get("links", [])
            filtered = [lnk for lnk in links if lnk not in deleted_ids]
            if len(filtered) < len(links):
                data["links"] = filtered
                note_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                cleaned += 1
        if cleaned:
            print(f"  CLEANED: {cleaned} notes had dangling links removed")

    # Summary
    print(f"\n=== Done ===")
    print(f"Renamed: {renamed}")
    print(f"Deleted: {deleted}")
    print(f"Created: {created}")

    # Verification: reload and check
    print(f"\n=== Verification ===")
    us2 = get_unified_store()
    all2 = us2.all()
    recipes2 = [n for n in all2 if n.note_type == "recipe"]
    note_pids2 = {n.note_id.replace("recipe_", "") for n in recipes2}

    v2_pids = set(v2.keys())
    covered = v2_pids & note_pids2
    missing = v2_pids - note_pids2
    orphan = note_pids2 - all_pids

    print(f"Recipe notes: {len(recipes2)}")
    print(f"V2 patterns with notes: {len(covered)}/{len(v2_pids)}")
    print(f"V2 patterns still missing notes: {len(missing)}")
    if missing:
        for pid in sorted(missing):
            print(f"  {pid}")
    print(f"Orphan notes remaining: {len(orphan)}")
    if orphan:
        for pid in sorted(orphan):
            print(f"  {pid}")


if __name__ == "__main__":
    main()
