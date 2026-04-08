"""
Pattern Store - Storage and retrieval for A-MEM style patterns.

Provides:
- PatternStore: CRUD operations, search, and persistence for patterns
- File-based storage with JSON serialization
- In-memory index for fast lookup
- A-MEM style evolution (Task 4): DSPy-based linking and neighbor updates

Part of Phase 2 of the meta-learning system.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from ..runtime_paths import get_bundled_knowledge_root, resolve_writable_knowledge_path

from .pattern_memory import PatternNote, PatternIndex
from .pattern_evolution import PatternEvolution, get_pattern_evolution
from .pattern_verifier import PatternVerifier, get_pattern_verifier, VerificationResult

logger = logging.getLogger("rook.pattern_store")


def _bundled_patterns_dir() -> Path:
    return get_bundled_knowledge_root() / "gh" / "patterns"


DEFAULT_PATTERNS_DIR = resolve_writable_knowledge_path("gh", "patterns")
DEFAULT_INDEX_PATH = resolve_writable_knowledge_path("gh", "pattern_index.json")


class PatternStore:
    """Manages pattern storage, retrieval, and persistence.

    Core responsibilities (Task 3):
    - CRUD operations for patterns
    - Index maintenance for fast lookup
    - File-based persistence
    - Search by symptoms, intents, tags, components

    Evolution responsibilities (Task 4):
    - DSPy-based link decisions (A-MEM Ps2)
    - Neighbor pattern updates (A-MEM Ps3)
    - Bidirectional knowledge propagation

    Usage:
        store = PatternStore()

        # Add a pattern (automatically links and evolves neighbors)
        pattern = PatternNote(name="My Pattern", ...)
        store.add(pattern)

        # Add without evolution (for bulk imports)
        store.add(pattern, skip_evolution=True)

        # Search
        results = store.search(symptoms=["microscopic changes"])

        # Get by ID
        pattern = store.get("abc123")

        # Update
        pattern.tags.append("new-tag")
        store.update(pattern)

        # Delete
        store.delete("abc123")
    """

    def __init__(
        self,
        auto_save: bool = True,
        enable_evolution: bool = True,
        verify_on_search: bool = True,
    ):
        """Initialize the pattern store.

        Args:
            auto_save: If True, persist changes to disk after each operation.
                      Set False for batch operations, then call save() manually.
            enable_evolution: If True, new patterns trigger A-MEM style evolution:
                             - Find and link related patterns
                             - Update neighbor patterns bidirectionally
                             Set False for testing or bulk imports.
            verify_on_search: If True, verify pattern citations when searching.
                             Implements Phase 3 JIT verification.
                             Set False for testing or when performance critical.
        """
        self.auto_save = auto_save
        self.enable_evolution = enable_evolution
        self.verify_on_search = verify_on_search
        self.patterns_dir = DEFAULT_PATTERNS_DIR
        self.index_path = DEFAULT_INDEX_PATH
        self.patterns: dict[str, PatternNote] = {}
        self.index = PatternIndex()

        # Evolution handler (lazy-loaded via singleton)
        self._evolution: Optional[PatternEvolution] = None

        # Verification handler (lazy-loaded)
        self._verifier: Optional[PatternVerifier] = None

        # Ensure directories exist
        self.patterns_dir.mkdir(parents=True, exist_ok=True)

        # Load existing patterns
        self._load_all()

    @property
    def evolution(self) -> PatternEvolution:
        """Get the evolution handler (lazy-loaded singleton)."""
        if self._evolution is None:
            self._evolution = get_pattern_evolution()
        return self._evolution

    @property
    def verifier(self) -> PatternVerifier:
        """Get the verification handler (lazy-loaded).

        Uses the global sessions directory for citation verification.
        """
        if self._verifier is None:
            self._verifier = get_pattern_verifier()
        return self._verifier

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def get(self, pattern_id: str) -> Optional[PatternNote]:
        """Get a pattern by ID.

        Args:
            pattern_id: The pattern's unique identifier

        Returns:
            PatternNote if found, None otherwise
        """
        return self.patterns.get(pattern_id)

    def add(self, pattern: PatternNote, skip_evolution: bool = False) -> PatternNote:
        """Add a new pattern to the store.

        If evolution is enabled and not skipped:
        1. Find candidate neighbors via structured filters
        2. Use DSPy to decide which links to create (A-MEM Ps2)
        3. Update neighbor patterns bidirectionally (A-MEM Ps3)

        Args:
            pattern: The pattern to add
            skip_evolution: If True, skip A-MEM evolution even if enabled.
                           Use for bulk imports or testing.

        Returns:
            The added pattern (possibly modified by evolution with links/tags)

        Raises:
            ValueError: If pattern with same ID already exists
        """
        if pattern.pattern_id in self.patterns:
            raise ValueError(f"Pattern {pattern.pattern_id} already exists. Use update() instead.")

        # Store in memory
        self.patterns[pattern.pattern_id] = pattern
        self.index.add_pattern(pattern)

        # A-MEM style evolution (if enabled and not first pattern)
        evolved_neighbor_ids = []
        if self.enable_evolution and not skip_evolution and len(self.patterns) > 1:
            pattern, evolved_neighbor_ids = self._evolve_on_add(pattern)

        # Persist pattern (may have been modified by evolution)
        if self.auto_save:
            self._save_pattern(pattern)
            # Also save evolved neighbors
            for neighbor_id in evolved_neighbor_ids:
                if neighbor_id in self.patterns:
                    self._save_pattern(self.patterns[neighbor_id])
            self._save_index()

        logger.info(
            f"Added pattern: {pattern.pattern_id} ({pattern.name}) "
            f"[links={len(pattern.links)}, evolved_neighbors={len(evolved_neighbor_ids)}]"
        )
        return pattern

    def update(self, pattern: PatternNote) -> PatternNote:
        """Update an existing pattern.

        Args:
            pattern: The pattern with updated fields

        Returns:
            The updated pattern

        Raises:
            ValueError: If pattern doesn't exist
        """
        if pattern.pattern_id not in self.patterns:
            raise ValueError(f"Pattern {pattern.pattern_id} not found. Use add() for new patterns.")

        # Update index (remove old, add new with updated data)
        self.index.remove_pattern(pattern.pattern_id)
        self.index.add_pattern(pattern)

        # Store in memory
        self.patterns[pattern.pattern_id] = pattern

        # Persist
        if self.auto_save:
            self._save_pattern(pattern)
            self._save_index()

        logger.info(f"Updated pattern: {pattern.pattern_id} ({pattern.name})")
        return pattern

    def delete(self, pattern_id: str) -> bool:
        """Delete a pattern from the store.

        Also cleans up links from other patterns pointing to this one.

        Args:
            pattern_id: ID of the pattern to delete

        Returns:
            True if deleted, False if not found
        """
        if pattern_id not in self.patterns:
            return False

        # Clean up links from other patterns pointing to this one
        patterns_updated = []
        for other_id, other_pattern in self.patterns.items():
            if other_id != pattern_id and pattern_id in other_pattern.links:
                other_pattern.links.remove(pattern_id)
                patterns_updated.append(other_id)

        # Remove from memory
        self.index.remove_pattern(pattern_id)
        del self.patterns[pattern_id]

        # Remove file
        pattern_path = self.patterns_dir / f"{pattern_id}.json"
        if pattern_path.exists():
            pattern_path.unlink()

        # Persist updated patterns and index
        if self.auto_save:
            for updated_id in patterns_updated:
                if updated_id in self.patterns:
                    self._save_pattern(self.patterns[updated_id])
            self._save_index()

        logger.info(f"Deleted pattern: {pattern_id} (cleaned {len(patterns_updated)} stale links)")
        return True

    def exists(self, pattern_id: str) -> bool:
        """Check if a pattern exists.

        Args:
            pattern_id: ID to check

        Returns:
            True if pattern exists
        """
        return pattern_id in self.patterns

    # =========================================================================
    # Search Operations
    # =========================================================================

    def search(
        self,
        intent: Optional[str] = None,
        symptoms: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        components: Optional[list[str]] = None,
        pattern_type: str = "all",
        limit: int = 5,
        verify: bool = True,
        confidence_min: float = 0.0,
    ) -> list[PatternNote]:
        """Search for patterns matching criteria with JIT verification.

        Results are ranked by:
        1. Verification status (verified > stale > unverifiable)
        2. Success rate (patterns that work more often rank higher)

        JIT Verification (Phase 3):
        When verify=True and verify_on_search is enabled:
        - Each pattern's citations are checked against session history
        - Pattern._verification_status is set with the result
        - Verified patterns rank higher than stale/unverifiable

        Confidence Filtering (Phase 7):
        Use confidence_min to filter out low-confidence patterns:
        - 0.8 = high confidence only (trusted patterns)
        - 0.5 = medium+ confidence (exclude unreliable)
        - 0.0 = all patterns (default)

        Args:
            intent: Intent phrase to match (e.g., "create wedge shape")
            symptoms: Observable symptoms to match
            tags: Classification tags to match
            components: Component names to match
            pattern_type: Filter by pattern type - "struggle", "recipe", or "all" (default).
            limit: Maximum number of results
            verify: If True (default), run JIT verification on candidates.
                   Set False to skip verification (faster, but status unknown).
            confidence_min: Minimum success rate (0.0-1.0) to include.
                           Patterns with times_used=0 are included if confidence_min < 0.5.

        Returns:
            List of matching PatternNote objects, best matches first.
            Each pattern has _verification_status set if verified.
        """
        # If no search criteria provided, return all patterns (list all mode)
        if not any([intent, symptoms, tags, components]):
            candidates = list(self.patterns.values())
        else:
            # Get candidates from index
            candidate_ids = self.index.find_candidates(
                symptoms=symptoms,
                intents=[intent] if intent else None,
                tags=tags,
                components=components,
                limit=limit * 2,  # Get more candidates, then rank
            )

            # Load patterns
            candidates = [
                self.patterns[pid]
                for pid in candidate_ids
                if pid in self.patterns
            ]

        # Confidence Filtering (Phase 7)
        if confidence_min > 0:
            candidates = [
                p for p in candidates
                if (p.times_used == 0 and confidence_min < 0.5)  # Include untested if not requiring high confidence
                or (p.times_used > 0 and p.success_rate() >= confidence_min)
            ]

        # JIT Verification (Phase 3)
        if verify and self.verify_on_search:
            for pattern in candidates:
                result = self.verifier.verify(pattern, level="existence")
                pattern.set_verification(
                    status=result.status,
                    warnings=result.warnings,
                    days_since=result.days_since_verified,
                )

        # Sort by verification status, then success rate
        # Verified (0) > Stale (1) > Unverifiable (2) > No citations (3) > Unchecked (4)
        def sort_key(p: PatternNote) -> tuple:
            status_order = {
                "verified": 0,
                "stale": 1,
                "unverifiable": 2,
                "no_citations": 3,
                "unchecked": 4,
            }
            return (status_order.get(p.verification_status, 4), -p.success_rate())

        candidates.sort(key=sort_key)

        # Filter by pattern_type if specified
        if pattern_type != "all":
            candidates = [p for p in candidates if p.pattern_type == pattern_type]

        return candidates[:limit]

    def get_by_tag(self, tag: str) -> list[PatternNote]:
        """Get all patterns with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of patterns with this tag
        """
        pattern_ids = self.index.by_tag.get(tag.lower(), [])
        return [self.patterns[pid] for pid in pattern_ids if pid in self.patterns]

    def get_by_component(self, component: str) -> list[PatternNote]:
        """Get all patterns that use a specific component.

        Args:
            component: Component name to filter by

        Returns:
            List of patterns using this component
        """
        pattern_ids = self.index.by_component.get(component.lower(), [])
        return [self.patterns[pid] for pid in pattern_ids if pid in self.patterns]

    def get_all(self) -> list[PatternNote]:
        """Get all patterns in the store.

        Returns:
            List of all patterns
        """
        return list(self.patterns.values())

    # =========================================================================
    # Link Operations (for Task 4 evolution)
    # =========================================================================

    def get_neighbors(self, pattern_id: str) -> list[PatternNote]:
        """Get linked patterns (neighbors in the knowledge graph).

        Args:
            pattern_id: Pattern to get neighbors for

        Returns:
            List of linked patterns
        """
        pattern = self.patterns.get(pattern_id)
        if not pattern:
            return []

        return [
            self.patterns[link_id]
            for link_id in pattern.links
            if link_id in self.patterns
        ]

    def add_link(self, pattern_id: str, link_to_id: str, bidirectional: bool = True) -> bool:
        """Add a link between two patterns.

        Args:
            pattern_id: Source pattern
            link_to_id: Target pattern to link to
            bidirectional: If True, also add reverse link

        Returns:
            True if link added, False if patterns not found
        """
        pattern = self.patterns.get(pattern_id)
        link_to = self.patterns.get(link_to_id)

        if not pattern or not link_to:
            return False

        # Add forward link
        if link_to_id not in pattern.links:
            pattern.links.append(link_to_id)
            if self.auto_save:
                self._save_pattern(pattern)

        # Add reverse link if bidirectional
        if bidirectional and pattern_id not in link_to.links:
            link_to.links.append(pattern_id)
            if self.auto_save:
                self._save_pattern(link_to)

        return True

    def remove_link(self, pattern_id: str, link_to_id: str, bidirectional: bool = True) -> bool:
        """Remove a link between two patterns.

        Args:
            pattern_id: Source pattern
            link_to_id: Target pattern to unlink
            bidirectional: If True, also remove reverse link

        Returns:
            True if link removed, False if patterns not found
        """
        pattern = self.patterns.get(pattern_id)
        link_to = self.patterns.get(link_to_id)

        if not pattern or not link_to:
            return False

        # Remove forward link
        if link_to_id in pattern.links:
            pattern.links.remove(link_to_id)
            if self.auto_save:
                self._save_pattern(pattern)

        # Remove reverse link if bidirectional
        if bidirectional and pattern_id in link_to.links:
            link_to.links.remove(pattern_id)
            if self.auto_save:
                self._save_pattern(link_to)

        return True

    # =========================================================================
    # A-MEM Evolution (Task 4)
    # =========================================================================

    def _evolve_on_add(self, pattern: PatternNote) -> tuple[PatternNote, list[str]]:
        """Perform A-MEM style evolution when adding a pattern.

        Steps:
        1. Find candidates via structured filters (no embeddings for v1)
        2. DSPy decides which to link (Ps2)
        3. Bidirectional update: neighbors may evolve (Ps3)

        Args:
            pattern: The newly added pattern

        Returns:
            Tuple of (modified_pattern, list_of_evolved_neighbor_ids)
        """
        evolved_neighbor_ids = []

        # Step 1: Find candidates
        candidate_ids = self.evolution.find_evolution_candidates(
            pattern=pattern,
            index=self.index,
            all_patterns=self.patterns,
            limit=5,
        )

        if not candidate_ids:
            logger.debug(f"No evolution candidates for {pattern.pattern_id}")
            return pattern, evolved_neighbor_ids

        # Get actual pattern objects for candidates
        candidate_patterns = [
            self.patterns[pid] for pid in candidate_ids if pid in self.patterns
        ]

        if not candidate_patterns:
            return pattern, evolved_neighbor_ids

        # Step 2: DSPy decides links (A-MEM Ps2)
        links_to_create, rationales, updated_tags = self.evolution.decide_links(
            new_pattern=pattern,
            candidate_patterns=candidate_patterns,
        )

        # Apply link decisions
        if links_to_create:
            # Update pattern's links (dedup)
            pattern.links = list(set(pattern.links + links_to_create))

            # Add bidirectional links
            for link_id in links_to_create:
                if link_id in self.patterns:
                    neighbor = self.patterns[link_id]
                    if pattern.pattern_id not in neighbor.links:
                        neighbor.links.append(pattern.pattern_id)

        # Apply updated tags
        if updated_tags and updated_tags != pattern.tags:
            pattern.tags = updated_tags
            # Re-index with new tags
            self.index.remove_pattern(pattern.pattern_id)
            self.index.add_pattern(pattern)

        # Step 3: Evolve neighbors (A-MEM Ps3)
        if pattern.links:
            neighbor_patterns = [
                self.patterns[lid] for lid in pattern.links if lid in self.patterns
            ]

            if neighbor_patterns:
                neighbor_updates = self.evolution.evolve_neighbors(
                    new_pattern=pattern,
                    neighbor_patterns=neighbor_patterns,
                )

                # Apply updates to neighbors
                evolved_neighbor_ids = self.evolution.apply_neighbor_updates(
                    neighbor_updates=neighbor_updates,
                    all_patterns=self.patterns,
                    triggering_pattern_id=pattern.pattern_id,
                )

                # Re-index evolved neighbors (tags may have changed)
                for neighbor_id in evolved_neighbor_ids:
                    if neighbor_id in self.patterns:
                        neighbor = self.patterns[neighbor_id]
                        self.index.remove_pattern(neighbor_id)
                        self.index.add_pattern(neighbor)

        return pattern, evolved_neighbor_ids

    def evolve_pattern(self, pattern_id: str) -> tuple[PatternNote, list[str]]:
        """Manually trigger evolution for an existing pattern.

        Useful for re-evaluating links after updates or for testing.

        Args:
            pattern_id: ID of the pattern to evolve

        Returns:
            Tuple of (updated_pattern, list_of_evolved_neighbor_ids)

        Raises:
            ValueError: If pattern not found
        """
        pattern = self.patterns.get(pattern_id)
        if not pattern:
            raise ValueError(f"Pattern {pattern_id} not found")

        # Temporarily store, then call evolution
        pattern, evolved_neighbor_ids = self._evolve_on_add(pattern)

        # Persist changes
        if self.auto_save:
            self._save_pattern(pattern)
            for neighbor_id in evolved_neighbor_ids:
                if neighbor_id in self.patterns:
                    self._save_pattern(self.patterns[neighbor_id])
            self._save_index()

        return pattern, evolved_neighbor_ids

    # =========================================================================
    # Confidence Tracking
    # =========================================================================

    def record_use(
        self,
        pattern_id: str,
        success: bool,
        session_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[PatternNote]:
        """Record that a pattern was used and update confidence.

        Args:
            pattern_id: Pattern that was used
            success: Whether the pattern helped solve the problem
            session_id: Session where it was used (for citation)
            notes: Optional observations

        Returns:
            Updated pattern, or None if not found
        """
        pattern = self.patterns.get(pattern_id)
        if not pattern:
            return None

        # Update confidence
        pattern.times_used += 1
        if success:
            pattern.times_succeeded += 1

        now = datetime.utcnow().isoformat() + "Z"
        pattern.last_used = now

        if success:
            pattern.last_verified = now

        # Add citation if session provided
        if session_id:
            pattern.citations.append({
                "session_id": session_id,
                "outcome": "success" if success else "failure",
                "timestamp": now,
                "notes": notes,
            })

        # Persist
        if self.auto_save:
            self._save_pattern(pattern)

        return pattern

    def detect_regressions(
        self,
        min_uses: int = 8,
        recent_window: int = 5,
        historical_threshold: float = 0.7,
        recent_threshold: float = 0.5,
    ) -> list[dict]:
        """Find patterns that have degraded in performance.

        Uses a sliding window approach to compare historical vs recent success rates.
        This correctly detects regressions even after they've dragged down the overall rate.

        A pattern is considered regressed when:
        - It has enough citation history (min_uses with outcome data)
        - Its HISTORICAL success rate (older citations, excluding recent) was >= historical_threshold
        - Its RECENT success rate (last recent_window uses) is < recent_threshold

        Args:
            min_uses: Minimum uses with outcome data to consider (default 8, needs enough for both windows)
            recent_window: Number of recent uses to check (default 5)
            historical_threshold: Min success rate for historical period to be "was good" (default 0.7)
            recent_threshold: Max success rate for recent period to be "now bad" (default 0.5)

        Returns:
            List of regression info dicts:
            - pattern_id, name, historical_success_rate, recent_success_rate
            - recent_failures: count of failures in recent window
            - recommendation: suggested action
        """
        regressions = []

        for pattern in self.patterns.values():
            # Get all citations with outcome data, sorted by timestamp (most recent first)
            citations_with_outcome = sorted(
                [c for c in pattern.citations if "outcome" in c],
                key=lambda c: c.get("timestamp", ""),
                reverse=True
            )

            # Need enough citations for both windows
            min_citations_needed = max(min_uses, recent_window + 3)
            if len(citations_with_outcome) < min_citations_needed:
                continue

            # Split into recent and historical windows
            recent_citations = citations_with_outcome[:recent_window]
            historical_citations = citations_with_outcome[recent_window:]

            # Calculate recent success rate
            recent_successes = sum(1 for c in recent_citations if c.get("outcome") == "success")
            recent_rate = recent_successes / len(recent_citations)

            # Calculate historical success rate (BEFORE the recent window)
            historical_successes = sum(1 for c in historical_citations if c.get("outcome") == "success")
            historical_rate = historical_successes / len(historical_citations)

            # Check for regression: was good historically, now bad recently
            if historical_rate >= historical_threshold and recent_rate < recent_threshold:
                regressions.append({
                    "pattern_id": pattern.pattern_id,
                    "name": pattern.name,
                    "historical_success_rate": round(historical_rate, 3),
                    "recent_success_rate": round(recent_rate, 3),
                    "recent_failures": len(recent_citations) - recent_successes,
                    "total_uses": pattern.times_used,
                    "historical_uses": len(historical_citations),
                    "recommendation": self._regression_recommendation(recent_rate),
                })

        return regressions

    def _regression_recommendation(self, recent: float) -> str:
        """Generate recommendation for a regressed pattern."""
        if recent == 0:
            return "Critical: Pattern completely failing. Review citations for what changed."
        elif recent < 0.3:
            return "Severe: Major degradation. Pattern may no longer apply to current workflows."
        else:
            return "Warning: Performance dropping. Verify pattern still matches current environment."

    def get_confidence_stats(self) -> dict:
        """Get statistics about pattern confidence levels.

        Returns:
            Dict with counts by confidence level and overall stats.
        """
        high_confidence = []  # >= 80%
        medium_confidence = []  # 50-79%
        low_confidence = []  # < 50%
        untested = []  # times_used == 0

        for pattern in self.patterns.values():
            if pattern.times_used == 0:
                untested.append(pattern.pattern_id)
            elif pattern.success_rate() >= 0.8:
                high_confidence.append(pattern.pattern_id)
            elif pattern.success_rate() >= 0.5:
                medium_confidence.append(pattern.pattern_id)
            else:
                low_confidence.append(pattern.pattern_id)

        return {
            "total": len(self.patterns),
            "high_confidence": len(high_confidence),
            "medium_confidence": len(medium_confidence),
            "low_confidence": len(low_confidence),
            "untested": len(untested),
            "high_confidence_ids": high_confidence,
            "low_confidence_ids": low_confidence,
        }

    # =========================================================================
    # Persistence
    # =========================================================================

    def _load_all(self) -> None:
        """Load all patterns from disk."""
        loaded_files = 0
        error_count = 0

        pattern_dirs: list[Path] = []
        bundled_dir = _bundled_patterns_dir()
        if bundled_dir.exists() and bundled_dir != self.patterns_dir:
            pattern_dirs.append(bundled_dir)
        pattern_dirs.append(self.patterns_dir)

        for pattern_dir in pattern_dirs:
            for pattern_path in pattern_dir.glob("*.json"):
                try:
                    with open(pattern_path, encoding="utf-8") as f:
                        data = json.load(f)
                    pattern = PatternNote.from_dict(data)
                    self.patterns[pattern.pattern_id] = pattern
                    loaded_files += 1
                except Exception as e:
                    logger.error(f"Failed to load pattern {pattern_path}: {e}")
                    error_count += 1

        self.index = PatternIndex()
        for pattern in self.patterns.values():
            self.index.add_pattern(pattern)

        unique_count = len(self.patterns)
        if loaded_files > 0 or error_count > 0:
            logger.info(f"Loaded {unique_count} unique patterns from {loaded_files} files ({error_count} errors)")

    def _save_pattern(self, pattern: PatternNote) -> None:
        """Save a single pattern to disk."""
        pattern_path = self.patterns_dir / f"{pattern.pattern_id}.json"
        pattern_path.parent.mkdir(parents=True, exist_ok=True)

        with open(pattern_path, "w", encoding="utf-8") as f:
            json.dump(pattern.to_dict(), f, indent=2, ensure_ascii=False)

    def _save_index(self) -> None:
        """Save the index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index.to_dict(), f, indent=2, ensure_ascii=False)

    def save(self) -> None:
        """Manually save all patterns and index to disk.

        Call this after batch operations when auto_save=False.
        """
        for pattern in self.patterns.values():
            self._save_pattern(pattern)
        self._save_index()
        logger.info(f"Saved {len(self.patterns)} patterns")

    def rebuild_index(self) -> None:
        """Rebuild index from pattern files.

        Use this to recover from a corrupted index.
        """
        self.index = PatternIndex()
        for pattern in self.patterns.values():
            self.index.add_pattern(pattern)
        self._save_index()
        logger.info(f"Rebuilt index with {len(self.patterns)} patterns")

    # =========================================================================
    # Statistics
    # =========================================================================

    def stats(self) -> dict:
        """Get statistics about the pattern store.

        Returns:
            Dictionary with counts and metrics
        """
        patterns = list(self.patterns.values())

        total_uses = sum(p.times_used for p in patterns)
        total_successes = sum(p.times_succeeded for p in patterns)

        verified = [p for p in patterns if p.is_verified]
        linked = [p for p in patterns if p.links]
        evolved = [p for p in patterns if p.evolved_by]

        # Count total links (each bidirectional link counted once)
        total_links = sum(len(p.links) for p in patterns) // 2

        # Count stale patterns (is_stale property checks staleness threshold)
        stale = [p for p in patterns if p.is_stale]

        # Count patterns with citations
        with_citations = [p for p in patterns if p.citations]

        # Count v2 (replayable) recipes vs v1
        v2_recipes = [p for p in patterns if p.pattern_type == "recipe" and p.schema_version == "2.0"]
        v1_recipes = [p for p in patterns if p.pattern_type == "recipe" and p.schema_version != "2.0"]

        return {
            "total_patterns": len(patterns),
            "total_symptoms": len(self.index.by_symptom),
            "total_tags": len(self.index.by_tag),
            "total_components": len(self.index.by_component),
            "verified_patterns": len(verified),
            "stale_patterns": len(stale),
            "patterns_with_citations": len(with_citations),
            "linked_patterns": len(linked),
            "evolved_patterns": len(evolved),
            "total_links": total_links,
            "total_uses": total_uses,
            "total_successes": total_successes,
            "overall_success_rate": total_successes / total_uses if total_uses > 0 else 0.0,
            "v2_recipes": len(v2_recipes),
            "v1_recipes": len(v1_recipes),
            "evolution_enabled": self.enable_evolution,
            "verification_enabled": self.verify_on_search,
        }

    def __len__(self) -> int:
        return len(self.patterns)

    def __contains__(self, pattern_id: str) -> bool:
        return pattern_id in self.patterns

    def __repr__(self) -> str:
        return (
            f"PatternStore(patterns={len(self.patterns)}, "
            f"evolution={'on' if self.enable_evolution else 'off'}, "
            f"index={self.index})"
        )


# =============================================================================
# Singleton Accessor
# =============================================================================

_store_instance: Optional[PatternStore] = None


def get_pattern_store() -> PatternStore:
    """Get the singleton PatternStore instance.

    The store is initialized on first access and reused thereafter.
    """
    global _store_instance
    if _store_instance is None:
        _store_instance = PatternStore()
    return _store_instance
