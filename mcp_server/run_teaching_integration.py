"""Integrate teaching sections into the A-MEM knowledge graph.

Reads extracted teaching JSON files from knowledge/gh/teaching/ and creates
KnowledgeNote objects with note_type="teaching" in the unified store.

Prerequisites:
    - Teaching extraction files must exist in knowledge/gh/teaching/unit-*.json

Usage:
    cd mcp_server
    python run_teaching_integration.py [--dry-run] [--force]

Flags:
    --dry-run    Show what would be created without writing files
    --force      Overwrite existing teaching notes
"""
import sys
import os
import json
import hashlib
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from rook.learning.knowledge_note import KnowledgeNote
from rook.learning.unified_store import (
    UnifiedStore,
    DEFAULT_NOTES_DIR,
    DEFAULT_INDEX_PATH,
)

TEACHING_DIR = Path(__file__).parent.parent / "knowledge" / "gh" / "teaching"

# Unit number → difficulty level mapping
UNIT_DIFFICULTY = {
    1: "beginner",
    2: "beginner",
    3: "beginner-intermediate",
    4: "intermediate",
    5: "intermediate",
    6: "intermediate-advanced",
    7: "advanced",
    8: "advanced",
}


def stable_note_id(unit_name: str, section_idx: int) -> str:
    """Generate a deterministic note ID from unit name and section index.

    Using a hash ensures the same section always gets the same ID,
    making re-runs idempotent.
    """
    key = f"{unit_name}:section:{section_idx}"
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return f"teaching_{h}"


def extract_unit_number(unit_name: str) -> int:
    """Extract unit number from name like 'Unit-01-Class'."""
    m = re.search(r"Unit-(\d+)", unit_name, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def build_trigger_intents(section: dict, unit_num: int) -> list[str]:
    """Build trigger intents from section content.

    These are the queries that should surface this teaching note.
    """
    intents = []
    title = section.get("section_title", "").strip()

    if title:
        # Clean title — remove trailing punctuation and numbering prefix
        clean_title = re.sub(r"^\d+[-.:]\s*", "", title).strip()
        clean_title = clean_title.rstrip(".")

        # Add the title itself as an intent
        intents.append(clean_title.lower())

        # Add "how to" variants for actionable titles
        if not clean_title.lower().startswith(("what ", "why ", "how ")):
            intents.append(f"how to use {clean_title.lower()}")

    # Add component-based intents
    components = section.get("components_demonstrated", {})
    for comp_name in components:
        if comp_name not in ("NumberSlider", "Panel"):
            intents.append(f"how to use {comp_name.lower()}")

    # Add concept-based intents
    for concept in section.get("concepts_taught", []):
        cleaned = concept.strip().rstrip(".").lower()
        if len(cleaned) > 5 and len(cleaned) < 80:
            intents.append(cleaned)

    return list(dict.fromkeys(intents))  # deduplicate preserving order


def build_keywords(section: dict, unit_name: str) -> list[str]:
    """Build keywords from section content."""
    keywords = []
    title = section.get("section_title", "")

    # Title words
    for word in re.findall(r"[A-Za-z]{3,}", title):
        keywords.append(word.lower())

    # Component names
    for comp_name in section.get("components_demonstrated", {}):
        keywords.append(comp_name.lower())

    # Unit name
    keywords.append(unit_name.lower().replace("-", " "))

    # Named groups
    for group in section.get("groups", []):
        gname = group.get("name", "")
        if gname:
            for word in re.findall(r"[A-Za-z]{3,}", gname):
                keywords.append(word.lower())

    return list(dict.fromkeys(keywords))  # deduplicate


def build_tags(section: dict, unit_num: int) -> list[str]:
    """Build tags for the teaching note."""
    tags = [f"unit-{unit_num:02d}"]

    difficulty = UNIT_DIFFICULTY.get(unit_num, "intermediate")
    tags.append(difficulty)
    tags.append("teaching")
    tags.append("tutorial")

    # Add component-type tags
    components = section.get("components_demonstrated", {})
    comp_names = set(components.keys()) - {"NumberSlider", "Panel"}
    if comp_names:
        tags.append("hands-on")

    # Stats-based tags
    stats = section.get("stats", {})
    if stats.get("flows", 0) > 20:
        tags.append("complex-wiring")
    if stats.get("groups", 0) > 3:
        tags.append("multi-group")
    if stats.get("sub_annotations", 0) > 0:
        tags.append("annotated")

    # Named group topics
    for group in section.get("groups", []):
        gname = group.get("name", "")
        if gname and len(gname) < 40:
            tags.append(gname.lower())

    return tags


def section_to_note(
    section: dict, unit_name: str, unit_num: int, section_idx: int
) -> KnowledgeNote:
    """Convert a teaching section to a KnowledgeNote."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    note_id = stable_note_id(unit_name, section_idx)
    title = section.get("section_title", "").strip()
    sec_num = section.get("section_number")
    teaching_text = section.get("teaching_text", "")

    # Build name
    if title:
        clean_title = re.sub(r"^\d+[-.:]\s*", "", title).strip().rstrip(".")
        name = f"U{unit_num:02d} - {clean_title}"
    else:
        name = f"U{unit_num:02d} - Section {section_idx}"

    # Build brief
    if title:
        brief = f"Teaching: {title[:120]}"
    elif teaching_text:
        brief = f"Teaching: {teaching_text[:100].strip()}..."
    else:
        brief = f"Teaching section from {unit_name}"

    # Components list
    components = list(section.get("components_demonstrated", {}).keys())

    # Sub-annotations as preconditions/tips
    sub_annotations = []
    for sa in section.get("sub_annotations", []):
        text = sa.get("text", "")
        if text:
            sub_annotations.append(text[:200])

    # Build solution_principle from teaching text
    if teaching_text:
        # Truncate very long teaching text for the principle field
        principle = teaching_text[:1500]
        if len(teaching_text) > 1500:
            principle += "\n\n[... see type_data.full_teaching_text for complete text]"
    else:
        principle = f"Section from {unit_name} demonstrating {', '.join(components[:5]) or 'concepts'}"

    # Type-specific data
    type_data = {
        "unit_name": unit_name,
        "unit_number": unit_num,
        "section_number": sec_num,
        "section_index": section_idx,
        "x_range": section.get("x_range"),
        "full_teaching_text": teaching_text,
        "sub_annotations": section.get("sub_annotations", []),
        "working_component_ids": section.get("working_component_ids", []),
        "intra_section_flows": section.get("intra_section_flows", []),
        "groups": section.get("groups", []),
        "components_demonstrated": section.get("components_demonstrated", {}),
        "stats": section.get("stats", {}),
    }

    return KnowledgeNote(
        note_id=note_id,
        note_type="teaching",
        name=name,
        brief=brief,
        created=now,
        version="1.0",
        context=teaching_text[:500] if teaching_text else "",
        keywords=build_keywords(section, unit_name),
        category=f"Unit {unit_num:02d}",
        tags=build_tags(section, unit_num),
        trigger_intents=build_trigger_intents(section, unit_num),
        trigger_symptoms=[],
        components=components,
        solution_principle=principle,
        anti_patterns=[],
        preconditions=sub_annotations,
        postconditions=[],
        links=[],
        times_used=0,
        times_succeeded=0,
        retrieval_count=0,
        last_accessed=None,
        last_verified=now,
        citations=[],
        created_from="teaching_extract",
        last_evolved=None,
        evolved_by=[],
        evolution_history=[],
        type_data=type_data,
    )


def is_meaningful_section(section: dict) -> bool:
    """Check if a section has enough content to be worth a note.

    Skip sections that are just empty columns with no teaching content.
    """
    has_text = bool(section.get("teaching_text", "").strip())
    has_components = bool(section.get("components_demonstrated"))
    has_sub_annotations = len(section.get("sub_annotations", [])) > 0
    has_additional_panels = len(section.get("additional_teaching_panels", [])) > 0

    return has_text or (has_components and has_sub_annotations) or has_additional_panels


def main():
    parser = argparse.ArgumentParser(
        description="Integrate teaching sections into A-MEM knowledge graph"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing teaching notes",
    )
    args = parser.parse_args()

    # Find teaching files
    teaching_files = sorted(TEACHING_DIR.glob("unit-*.json"))
    if not teaching_files:
        print(f"No teaching files found in {TEACHING_DIR}")
        sys.exit(1)

    print(f"Found {len(teaching_files)} teaching files")

    # Load existing store to check for duplicates
    if not args.dry_run:
        store = UnifiedStore(
            notes_dir=DEFAULT_NOTES_DIR,
            index_path=DEFAULT_INDEX_PATH,
            auto_save=False,
            enable_evolution=False,
        )
        existing_ids = {n.note_id for n in store.all()}
        print(f"Existing store: {len(existing_ids)} notes")
    else:
        existing_ids = set()

    # Process each teaching file
    total_created = 0
    total_skipped = 0
    total_overwritten = 0
    all_notes = []

    for tf in teaching_files:
        data = json.loads(tf.read_text(encoding="utf-8"))
        unit_name = data["document"]["name"]
        unit_num = extract_unit_number(unit_name)
        sections = data.get("sections", [])

        print(f"\n--- {unit_name} ({len(sections)} sections) ---")

        for i, section in enumerate(sections):
            if not is_meaningful_section(section):
                title = section.get("section_title", "(untitled)")[:40]
                print(f"  [{i}] SKIP empty: {title}")
                total_skipped += 1
                continue

            note = section_to_note(section, unit_name, unit_num, i)

            # Check for existing
            if note.note_id in existing_ids and not args.force:
                print(f"  [{i}] EXISTS: {note.name} -> {note.note_id}")
                total_skipped += 1
                continue

            if note.note_id in existing_ids and args.force:
                total_overwritten += 1

            all_notes.append(note)

            comp_count = len(note.components)
            intent_count = len(note.trigger_intents)
            tag_count = len(note.tags)

            if args.dry_run:
                print(
                    f"  [{i}] WOULD CREATE: {note.name} -> {note.note_id} "
                    f"({comp_count}C, {intent_count}I, {tag_count}T)"
                )
            else:
                print(
                    f"  [{i}] CREATE: {note.name} -> {note.note_id} "
                    f"({comp_count}C, {intent_count}I, {tag_count}T)"
                )

            total_created += 1

    if args.dry_run:
        print(f"\n=== Dry Run Summary ===")
        print(f"Would create: {total_created} teaching notes")
        print(f"Would skip:   {total_skipped} (empty or existing)")
        return

    # Write notes to disk
    print(f"\nWriting {len(all_notes)} notes to {DEFAULT_NOTES_DIR}...")

    for note in all_notes:
        note_path = DEFAULT_NOTES_DIR / f"{note.note_id}.json"
        note_path.write_text(
            json.dumps(note.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # Add to store index
    print("Rebuilding unified index...")
    store_fresh = UnifiedStore(
        notes_dir=DEFAULT_NOTES_DIR,
        index_path=DEFAULT_INDEX_PATH,
        auto_save=True,
        enable_evolution=False,
    )
    all_store_notes = store_fresh.all()
    teaching_notes = [n for n in all_store_notes if n.note_type == "teaching"]
    recipe_notes = [n for n in all_store_notes if n.note_type == "recipe"]
    comp_notes = [n for n in all_store_notes if n.note_type == "component"]

    print(f"\n=== Integration Complete ===")
    print(f"Teaching notes created: {total_created}")
    if total_overwritten:
        print(f"Teaching notes overwritten: {total_overwritten}")
    print(f"Sections skipped:       {total_skipped}")
    print(f"\nStore totals:")
    print(f"  Components: {len(comp_notes)}")
    print(f"  Recipes:    {len(recipe_notes)}")
    print(f"  Teaching:   {len(teaching_notes)}")
    print(f"  Total:      {len(all_store_notes)}")

    print(f"\n=== Next Steps ===")
    print(f"Run batch evolution to create A-MEM links:")
    print(f"  cd mcp_server && python run_batch_evolution.py --type teaching")
    print(f"Or dry-run first:")
    print(f"  cd mcp_server && python run_batch_evolution.py --type teaching --dry-run")


if __name__ == "__main__":
    main()
