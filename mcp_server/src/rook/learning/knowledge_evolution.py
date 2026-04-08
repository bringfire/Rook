"""
Knowledge Evolution - Deterministic linking for unified knowledge notes.

Links notes based on structured overlap (tags, components, keywords, symptoms).
No LLM involved — store facts, reason at query time.

History:
    Previously used DSPy (Ps2 for link decisions, Ps3 for neighbor content
    rewriting). Ps3 was found to inject confabulated domain reasoning into
    note content ("Related insight: ..."). Ps2 added marginal value over the
    deterministic candidate finder it was filtering. Both removed.
"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .unified_store import UnifiedStore
    from .knowledge_note import KnowledgeNote

logger = logging.getLogger("rook.knowledge_evolution")


class KnowledgeEvolution:
    """Deterministic linking for unified knowledge notes.

    When a new note is added:
    1. Find candidate neighbors via structured index (tag/component/keyword overlap)
    2. Link all candidates (bidirectional)

    No LLM calls. No content rewriting. Notes stay exactly as extracted.
    Query-time Claude reasons about relationships — that reasoning is
    ephemeral and doesn't corrupt the store.
    """

    def find_link_candidates(
        self,
        note: "KnowledgeNote",
        store: "UnifiedStore",
        limit: int = 5,
    ) -> list[str]:
        """Find notes to link based on structured overlap.

        Uses the UnifiedIndex to score candidates by:
        - Overlapping tags (+1 each)
        - Shared components (+1 each)
        - Matching symptoms (+2 each, more specific)
        - Matching keywords (+1 each)

        Returns top candidates by overlap score, excluding self.
        """
        candidate_ids = store._index.find_candidates(
            symptoms=note.trigger_symptoms or None,
            tags=note.tags or None,
            components=note.components or None,
            keywords=note.keywords or None,
            limit=limit + 1,  # buffer for self-filtering
        )

        # Filter out self
        candidate_ids = [nid for nid in candidate_ids if nid != note.note_id]
        return candidate_ids[:limit]

    def link(
        self,
        note: "KnowledgeNote",
        store: "UnifiedStore",
        limit: int = 5,
    ) -> list[str]:
        """Link a note to its best candidates. Bidirectional.

        This is the main entry point called by UnifiedStore._evolve()
        and by batch linking scripts.

        Args:
            note: The note to link
            store: The unified store (for index access and note retrieval)
            limit: Max number of links to create

        Returns:
            List of note IDs that were linked
        """
        candidate_ids = self.find_link_candidates(
            note=note,
            store=store,
            limit=limit,
        )

        if not candidate_ids:
            logger.debug(f"No link candidates found for {note.note_id}")
            return []

        # Apply forward links (note -> candidates)
        if note.links is None:
            note.links = []

        new_links = []
        for cid in candidate_ids:
            if cid not in note.links:
                note.links.append(cid)
                new_links.append(cid)

        # Apply back-links (candidates -> note) so graph is bidirectional
        for cid in new_links:
            neighbor = store.get(cid, track_access=False)
            if neighbor is not None:
                if neighbor.links is None:
                    neighbor.links = []
                if note.note_id not in neighbor.links:
                    neighbor.links.append(note.note_id)
                # Update index for the back-link
                store._index.add_note(neighbor)
                if store.auto_save:
                    store._save_note(neighbor)

        # Update index for forward links
        if new_links:
            store._index.add_note(note)

        if new_links:
            logger.info(
                f"Linked {note.note_id} to {len(new_links)} candidates: "
                f"{', '.join(new_links)}"
            )

        return new_links

    # Keep old method name as alias for backward compatibility with
    # any code that calls evolve() (e.g., UnifiedStore._evolve)
    def evolve(
        self,
        note: "KnowledgeNote",
        store: "UnifiedStore",
    ) -> list[str]:
        """Alias for link(). Maintains backward compatibility."""
        return self.link(note=note, store=store)


# Singleton for reuse across calls
_evolution_instance: Optional[KnowledgeEvolution] = None


def get_knowledge_evolution() -> KnowledgeEvolution:
    """Get the singleton KnowledgeEvolution instance."""
    global _evolution_instance
    if _evolution_instance is None:
        _evolution_instance = KnowledgeEvolution()
    return _evolution_instance


def reset_knowledge_evolution() -> None:
    """Reset the singleton (for testing)."""
    global _evolution_instance
    _evolution_instance = None
