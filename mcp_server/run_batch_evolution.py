"""
Batch Deterministic Linker
==========================

Links all unlinked notes in the UnifiedStore using deterministic
tag/component/keyword overlap. No LLM calls. Fast and reproducible.

Usage:
    cd mcp_server
    python run_batch_evolution.py [--dry-run] [--type component] [--limit 10] [--relink]

Flags:
    --dry-run     Show what would be linked without writing files
    --type        Filter by note type: "component", "recipe", "teaching", or "all" (default: "all")
    --limit N     Only link first N notes (useful for testing)
    --relink      Clear existing links and re-link all notes from scratch
"""

import argparse
import logging
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rook.learning.unified_store import UnifiedStore, DEFAULT_NOTES_DIR, DEFAULT_INDEX_PATH
from rook.learning.knowledge_evolution import KnowledgeEvolution

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_linker")


def find_unlinked_notes(store: UnifiedStore, note_type: str = "all", relink: bool = False):
    """Find notes that need linking."""
    targets = []
    for note in store.all():
        if note_type != "all" and note.note_type != note_type:
            continue
        if relink or not note.links:
            targets.append(note)
    return targets


def run_batch_linking(
    dry_run: bool = False,
    note_type: str = "all",
    limit: int = None,
    relink: bool = False,
):
    """Run deterministic linking on unlinked notes."""

    logger.info("Loading UnifiedStore...")
    store = UnifiedStore(
        notes_dir=DEFAULT_NOTES_DIR,
        index_path=DEFAULT_INDEX_PATH,
        auto_save=not dry_run,
        enable_evolution=False,
    )
    logger.info(f"Loaded {len(store)} notes")

    targets = find_unlinked_notes(store, note_type=note_type, relink=relink)

    if limit:
        targets = targets[:limit]

    logger.info(f"")
    logger.info(f"=== Linking Summary ===")
    logger.info(f"Notes to link: {len(targets)}")
    if relink:
        logger.info(f"Mode: RELINK (clearing existing links first)")
    logger.info(f"")

    if dry_run:
        logger.info("DRY RUN — listing notes that would be linked:")
        evolution = KnowledgeEvolution()
        for note in targets:
            candidates = evolution.find_link_candidates(note=note, store=store, limit=5)
            tags_str = ", ".join(note.tags[:3]) if note.tags else "(no tags)"
            logger.info(
                f"  {note.note_id} — {note.name} [{tags_str}] "
                f"-> {len(candidates)} candidates"
            )
        return

    # Clear existing links if relinking
    if relink:
        logger.info("Clearing existing links...")
        for note in targets:
            note.links = []

    evolution = KnowledgeEvolution()
    total_links = 0
    linked_count = 0

    for i, note in enumerate(targets, 1):
        new_links = evolution.link(note=note, store=store, limit=5)

        if new_links:
            linked_count += 1
            total_links += len(new_links)

        if i % 50 == 0:
            logger.info(f"  Progress: {i}/{len(targets)}")

    # Save all notes and rebuild index
    logger.info("Saving notes and index...")
    for note in targets:
        store._save_note(note)
    store._save_index()

    logger.info(f"")
    logger.info(f"=== Linking Complete ===")
    logger.info(f"Notes processed:  {len(targets)}")
    logger.info(f"Notes linked:     {linked_count}")
    logger.info(f"Total new links:  {total_links}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch deterministic linker")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be linked")
    parser.add_argument("--type", default="all", choices=["all", "component", "recipe", "teaching"], help="Filter by note type")
    parser.add_argument("--limit", type=int, default=None, help="Max notes to link")
    parser.add_argument("--relink", action="store_true", help="Clear existing links and re-link from scratch")

    args = parser.parse_args()
    run_batch_linking(
        dry_run=args.dry_run,
        note_type=args.type,
        limit=args.limit,
        relink=args.relink,
    )
