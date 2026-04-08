"""
Pattern Evolution - A-MEM style dynamic evolution for pattern memory.

Implements the three A-MEM operations:
- Ps1 (Note Construction): Metadata extraction via DSPy (handled by PatternMetadataExtractor)
- Ps2 (Link Generation): Decide which patterns to link via DSPy
- Ps3 (Memory Evolution): Update neighbors bidirectionally via DSPy

This module is separate from PatternStore to keep storage/retrieval logic clean.
PatternStore calls into this module when evolution is enabled.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from .dspy_modules import PatternLinker, NeighborEvolver

if TYPE_CHECKING:
    from .pattern_memory import PatternNote, PatternIndex

logger = logging.getLogger("rook.pattern_evolution")


class PatternEvolution:
    """Handles A-MEM style evolution for pattern memory.

    When a new pattern is added:
    1. Find candidate neighbors via structured filters (no embeddings)
    2. Use DSPy (PatternLinker) to decide which candidates to link
    3. Use DSPy (NeighborEvolver) to update linked neighbors bidirectionally

    This creates a dynamic knowledge graph where new knowledge enriches
    existing knowledge, not just the other way around.
    """

    def __init__(self):
        """Initialize evolution with lazy-loaded DSPy modules."""
        self._linker: Optional[PatternLinker] = None
        self._evolver: Optional[NeighborEvolver] = None

    @property
    def linker(self) -> PatternLinker:
        """Lazy-load the PatternLinker DSPy module."""
        if self._linker is None:
            self._linker = PatternLinker()
        return self._linker

    @property
    def evolver(self) -> NeighborEvolver:
        """Lazy-load the NeighborEvolver DSPy module."""
        if self._evolver is None:
            self._evolver = NeighborEvolver()
        return self._evolver

    def find_evolution_candidates(
        self,
        pattern: "PatternNote",
        index: "PatternIndex",
        all_patterns: dict[str, "PatternNote"],
        limit: int = 5,
    ) -> list[str]:
        """Find candidate patterns for linking (A-MEM neighbor search).

        Uses structured filters instead of embeddings for v1:
        - Overlapping tags
        - Same components
        - Similar symptoms

        Args:
            pattern: The new pattern to find neighbors for
            index: The pattern index for fast lookup
            all_patterns: All patterns in the store
            limit: Maximum candidates to return

        Returns:
            List of pattern IDs that are good link candidates
        """
        # Use index to find candidates by multiple criteria
        candidate_ids = index.find_candidates(
            symptoms=pattern.trigger_symptoms,
            tags=pattern.tags,
            components=pattern.components_needed,
            limit=limit + 1,  # +1 in case we include self
        )

        # Filter out the pattern itself
        candidate_ids = [pid for pid in candidate_ids if pid != pattern.pattern_id]

        # Limit results
        return candidate_ids[:limit]

    def decide_links(
        self,
        new_pattern: "PatternNote",
        candidate_patterns: list["PatternNote"],
    ) -> tuple[list[str], list[str], list[str]]:
        """Use DSPy to decide which candidates to link (A-MEM Ps2).

        Args:
            new_pattern: The newly added pattern
            candidate_patterns: Candidate neighbor patterns

        Returns:
            Tuple of (link_ids, rationales, updated_tags)
            - link_ids: Pattern IDs to link to
            - rationales: Explanation for each link
            - updated_tags: Refined tags for the new pattern
        """
        if not candidate_patterns:
            return [], [], new_pattern.tags

        # Prepare candidate data for DSPy
        candidates = [
            {
                "id": p.pattern_id,
                "name": p.name,
                "brief": p.solution_brief,
                "tags": p.tags,
            }
            for p in candidate_patterns
        ]

        try:
            result = self.linker(
                new_pattern_summary=f"{new_pattern.name}: {new_pattern.solution_brief}",
                new_pattern_tags=new_pattern.tags,
                candidate_patterns=candidates,
            )

            links_to_create = result.links_to_create or []
            link_rationales = result.link_rationales or []
            updated_tags = result.updated_tags or new_pattern.tags

            # Validate link IDs - only keep ones that exist in candidates
            valid_candidate_ids = {p.pattern_id for p in candidate_patterns}
            links_to_create = [lid for lid in links_to_create if lid in valid_candidate_ids]

            logger.info(
                f"DSPy decided {len(links_to_create)} links for pattern {new_pattern.pattern_id}"
            )

            return links_to_create, link_rationales, updated_tags

        except Exception as e:
            logger.warning(f"Link decision failed for {new_pattern.pattern_id}: {e}")
            return [], [], new_pattern.tags

    def evolve_neighbors(
        self,
        new_pattern: "PatternNote",
        neighbor_patterns: list["PatternNote"],
    ) -> list[dict]:
        """Use DSPy to evolve neighbor patterns (A-MEM Ps3).

        Bidirectional evolution: new knowledge enriches old knowledge.
        Neighbors may get:
        - Additional tags
        - Extended context
        - New related patterns noted

        Args:
            new_pattern: The newly added pattern
            neighbor_patterns: Linked neighbor patterns to potentially evolve

        Returns:
            List of update dicts: [{id, new_tags, context_addition, rationale}, ...]
        """
        if not neighbor_patterns:
            return []

        # Prepare neighbor data for DSPy
        neighbor_data = [
            {
                "id": p.pattern_id,
                "name": p.name,
                "brief": p.solution_brief,
                "tags": p.tags,
                "context": p.solution_principle,
            }
            for p in neighbor_patterns
        ]

        try:
            result = self.evolver(
                new_pattern={
                    "id": new_pattern.pattern_id,
                    "name": new_pattern.name,
                    "brief": new_pattern.solution_brief,
                    "principle": new_pattern.solution_principle,
                    "tags": new_pattern.tags,
                },
                neighbor_patterns=neighbor_data,
            )

            if not result.should_evolve:
                logger.debug(f"No evolution needed for neighbors of {new_pattern.pattern_id}")
                return []

            updates = result.neighbor_updates or []

            # Validate update IDs
            valid_neighbor_ids = {p.pattern_id for p in neighbor_patterns}
            updates = [u for u in updates if u.get("id") in valid_neighbor_ids]

            logger.info(
                f"DSPy decided to evolve {len(updates)} neighbors for pattern {new_pattern.pattern_id}"
            )

            return updates

        except Exception as e:
            logger.warning(f"Neighbor evolution failed for {new_pattern.pattern_id}: {e}")
            return []

    def apply_neighbor_updates(
        self,
        neighbor_updates: list[dict],
        all_patterns: dict[str, "PatternNote"],
        triggering_pattern_id: str,
    ) -> list[str]:
        """Apply evolution updates to neighbor patterns.

        Args:
            neighbor_updates: Updates from evolve_neighbors()
            all_patterns: All patterns in the store (mutable)
            triggering_pattern_id: ID of the pattern that triggered evolution

        Returns:
            List of pattern IDs that were modified
        """
        modified_ids = []
        now = datetime.now().isoformat()

        for update in neighbor_updates:
            neighbor_id = update.get("id")
            if neighbor_id not in all_patterns:
                continue

            neighbor = all_patterns[neighbor_id]
            modified = False

            # Add new tags (merge, don't replace)
            new_tags = update.get("new_tags", [])
            if new_tags:
                original_tag_count = len(neighbor.tags)
                neighbor.tags = list(set(neighbor.tags + new_tags))
                if len(neighbor.tags) > original_tag_count:
                    modified = True

            # Add context (append to principle)
            context_addition = update.get("context_addition", "")
            if context_addition and context_addition.strip():
                neighbor.solution_principle += f"\n\nRelated insight: {context_addition}"
                modified = True

            if modified:
                # Track evolution metadata
                neighbor.last_evolved = now
                if triggering_pattern_id not in neighbor.evolved_by:
                    neighbor.evolved_by.append(triggering_pattern_id)
                neighbor.evolution_history.append({
                    "date": now,
                    "trigger": f"New pattern: {triggering_pattern_id}",
                    "changes": update.get("rationale", "Tags/context updated"),
                })

                modified_ids.append(neighbor_id)
                logger.debug(f"Evolved neighbor {neighbor_id}: {update.get('rationale', 'updated')}")

        return modified_ids


# Singleton for reuse across calls
_evolution_instance: Optional[PatternEvolution] = None


def get_pattern_evolution() -> PatternEvolution:
    """Get the singleton PatternEvolution instance."""
    global _evolution_instance
    if _evolution_instance is None:
        _evolution_instance = PatternEvolution()
    return _evolution_instance
