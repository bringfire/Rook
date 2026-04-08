"""Migrate PatternStore patterns to UnifiedStore with A-MEM evolution."""
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

from datetime import datetime, timezone
from rook.learning.pattern_store import get_pattern_store
from rook.learning.unified_store import get_unified_store
from rook.learning.knowledge_note import KnowledgeNote

# Suppress noisy loggers
logging.getLogger("rook.learning.dspy_config").setLevel(logging.WARNING)
logging.getLogger("rook.learning.command_learner").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

def convert_pattern_to_note(pattern) -> KnowledgeNote:
    """Convert a PatternNote to a KnowledgeNote."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Build type_data from pattern fields
    type_data = {
        "wiring": pattern.wiring or [],
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
        created_from="pattern_migration",
        last_evolved=None,
        evolved_by=[],
        evolution_history=[],
        type_data=type_data,
    )

def main():
    print("Loading stores...")
    pattern_store = get_pattern_store()
    unified_store = get_unified_store()

    # Get existing recipe IDs in unified store
    existing_ids = {n.note_id for n in unified_store.all() if n.note_type == 'recipe'}
    existing_sources = {
        n.type_data.get('source_definition', '')
        for n in unified_store.all()
        if n.note_type == 'recipe' and n.type_data
    }

    print(f"Pattern Store: {len(pattern_store.patterns)} patterns")
    print(f"Unified Store: {len(unified_store)} notes ({len(existing_ids)} recipes)")

    # Find patterns to migrate (not already in unified store)
    to_migrate = []
    for pattern in pattern_store.patterns.values():
        note_id = f"recipe_{pattern.pattern_id[:8]}"
        source = pattern.source_definition or ""

        # Skip if already exists by ID or source file
        if note_id in existing_ids:
            continue
        if source and source in existing_sources:
            continue

        to_migrate.append(pattern)

    print(f"\nPatterns to migrate: {len(to_migrate)}")

    if not to_migrate:
        print("Nothing to migrate!")
        return

    print(f"\n{'='*60}")
    print("Starting migration with A-MEM evolution...")
    print(f"{'='*60}\n")

    migrated = 0
    evolved_count = 0

    for i, pattern in enumerate(to_migrate, 1):
        print(f"[{i}/{len(to_migrate)}] {pattern.name[:50]}...")

        try:
            # Convert to KnowledgeNote
            note = convert_pattern_to_note(pattern)

            # Check if this ID already exists (edge case)
            if note.note_id in {n.note_id for n in unified_store.all()}:
                print(f"    - Skipped (ID exists)")
                continue

            # Add to unified store WITH evolution
            unified_store.add(note, skip_evolution=False)
            migrated += 1

            # Check if evolution happened
            if note.links:
                evolved_count += 1
                print(f"    + Migrated, evolved with {len(note.links)} links")
            else:
                print(f"    + Migrated (no evolution candidates)")

        except Exception as e:
            print(f"    X Error: {e}")

    # Save everything
    print(f"\n{'='*60}")
    print("Saving changes...")
    unified_store.save_all()

    print(f"\n{'='*60}")
    print("MIGRATION COMPLETE")
    print(f"{'='*60}")
    print(f"Patterns migrated: {migrated}")
    print(f"With evolution links: {evolved_count}")
    print(f"Total unified notes: {len(unified_store)}")

if __name__ == "__main__":
    main()
