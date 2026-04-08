"""
Knowledge Graph V2 API - Wrapper around existing knowledge system.

This class provides a higher-level API for the autonomous learning agent.
It delegates to the existing knowledge.py for core operations (query/record with MAB)
and adds metadata tracking for gaps, insights, verifications, and session handoffs.

The existing MAB-based knowledge system remains the source of truth for patterns.
This layer adds investigation coordination on top.
"""

import json
import logging
from typing import Any
from ..runtime_paths import resolve_writable_knowledge_path

from .schema import (
    Pattern,
    Antipattern,
    Gap,
    GapStatus,
    GapPriority,
    Insight,
    ToolRelationship,
    Verification,
    SessionHandoff,
    CultivationStats,
    KnowledgeGraphV2Data,
    now_iso,
    generate_id,
)

# Import existing knowledge system
from ..knowledge import (
    query_knowledge,
    record_knowledge,
    load_graph,
    save_graph,
    merge_graphs,
    CANONICAL_PATH,
    LOCAL_PATH,
    get_learning_summary,
)

logger = logging.getLogger("rook.learning.graph")

# V2 metadata file path (separate from core knowledge)
V2_METADATA_PATH = resolve_writable_knowledge_path("v2_metadata.json")


class KnowledgeGraphV2:
    """
    Enhanced knowledge graph API for autonomous learning.

    This wraps the existing knowledge.py system and adds:
    - Gap tracking for investigation targets
    - Insight recording for meta-knowledge
    - Verification tracking for visual confirmation
    - Session handoff for multi-instance continuity

    Core pattern/antipattern operations still go through the existing
    knowledge_query and knowledge_record functions with MAB integration.
    """

    def __init__(self, session_id: str | None = None):
        """
        Initialize the V2 knowledge graph.

        Args:
            session_id: Optional session identifier for provenance tracking
        """
        self.session_id = session_id or generate_id()
        self._metadata: KnowledgeGraphV2Data | None = None
        self._load_metadata()

    # =========================================================================
    # Core Knowledge Operations (delegate to existing system)
    # =========================================================================

    def query(
        self,
        intent: str | None = None,
        tool: str | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """
        Query knowledge graph for patterns and antipatterns.

        Delegates to existing knowledge_query with MAB integration.

        Args:
            intent: Natural language description of what you want to do
            tool: Optional specific MCP tool name
            params: Optional parameters for context encoding

        Returns:
            Dict with 'patterns', 'avoid', and 'confidence' keys
        """
        return query_knowledge(intent=intent, tool=tool, params=params)

    def record(
        self,
        intent: str,
        action: dict[str, Any],
        outcome: str,
        correction_of: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Record a learning outcome to the knowledge graph.

        Delegates to existing knowledge_record with MAB update.

        Args:
            intent: What the user wanted to accomplish
            action: The action taken (tool name and params)
            outcome: "success" or "failure"
            correction_of: If this corrected a failure, what failed

        Returns:
            Status of the recording operation
        """
        result = record_knowledge(
            intent=intent,
            action=action,
            outcome=outcome,
            correction_of=correction_of,
        )

        # Update cultivation stats
        if result.get("success"):
            if outcome == "success":
                self._metadata.cultivation_stats.patterns_discovered += 1
            else:
                self._metadata.cultivation_stats.antipatterns_discovered += 1
            self._metadata.cultivation_stats.total_investigations += 1
            self._save_metadata()

        return result

    def get_summary(self) -> dict[str, Any]:
        """
        Get learning summary including MAB state.

        Returns:
            Summary of knowledge graph, MAB, and context history
        """
        return get_learning_summary()

    # =========================================================================
    # Gap Management (investigation targets)
    # =========================================================================

    def get_gaps(
        self,
        status: str | None = None,
        priority: str | None = None,
        tool: str | None = None,
    ) -> list[Gap]:
        """
        Get knowledge gaps that need investigation.

        Args:
            status: Filter by status (uninvestigated, investigating, resolved)
            priority: Filter by priority (critical, high, medium, low)
            tool: Filter by tool name

        Returns:
            List of Gap objects matching filters
        """
        gaps = self._metadata.gaps

        if status:
            gaps = [g for g in gaps if g.status == status]
        if priority:
            gaps = [g for g in gaps if g.priority == priority]
        if tool:
            gaps = [g for g in gaps if g.tool == tool]

        return gaps

    def get_uninvestigated_gaps(self) -> list[Gap]:
        """Get gaps that haven't been investigated yet."""
        return self.get_gaps(status=GapStatus.UNINVESTIGATED.value)

    def get_high_priority_gaps(self) -> list[Gap]:
        """Get critical and high priority gaps."""
        return [
            g for g in self._metadata.gaps
            if g.priority in (GapPriority.CRITICAL.value, GapPriority.HIGH.value)
            and g.status != GapStatus.RESOLVED.value
        ]

    def add_gap(
        self,
        tool: str,
        unknown_aspect: str,
        priority: str = GapPriority.MEDIUM.value,
        hypotheses: list[str] | None = None,
    ) -> Gap:
        """
        Add a new knowledge gap to investigate.

        Args:
            tool: Which tool this gap relates to
            unknown_aspect: What we don't understand
            priority: Investigation priority
            hypotheses: Initial hypotheses to test

        Returns:
            The created Gap object
        """
        gap = Gap(
            tool=tool,
            unknown_aspect=unknown_aspect,
            priority=priority,
            hypotheses=hypotheses or [],
            discovered_by_session=self.session_id,
        )
        self._metadata.gaps.append(gap)
        self._metadata.cultivation_stats.gaps_created += 1
        self._save_metadata()
        logger.info(f"Added gap: {unknown_aspect[:50]}...")
        return gap

    def mark_gap_investigating(self, gap_id: str) -> bool:
        """
        Mark a gap as being investigated by this session.

        Args:
            gap_id: The gap ID to mark

        Returns:
            True if found and marked, False otherwise
        """
        for gap in self._metadata.gaps:
            if gap.id == gap_id:
                gap.status = GapStatus.INVESTIGATING.value
                gap.investigating_session = self.session_id
                gap.investigation_attempts += 1
                gap.last_attempt = now_iso()
                self._save_metadata()
                return True
        return False

    def add_hypothesis_result(
        self,
        gap_id: str,
        hypothesis: str,
        result: str,
    ) -> bool:
        """
        Record the result of testing a hypothesis.

        Args:
            gap_id: The gap ID
            hypothesis: The hypothesis that was tested
            result: What happened (success, failure, partial, etc.)

        Returns:
            True if found and updated, False otherwise
        """
        for gap in self._metadata.gaps:
            if gap.id == gap_id:
                gap.tested_hypotheses.append({
                    "hypothesis": hypothesis,
                    "result": result,
                    "timestamp": now_iso(),
                    "session": self.session_id,
                })
                self._save_metadata()
                return True
        return False

    def resolve_gap(
        self,
        gap_id: str,
        resolution: str,
        pattern_id: str | None = None,
    ) -> bool:
        """
        Mark a gap as resolved.

        Args:
            gap_id: The gap ID to resolve
            resolution: What we learned
            pattern_id: Optional link to pattern documenting the solution

        Returns:
            True if found and resolved, False otherwise
        """
        for gap in self._metadata.gaps:
            if gap.id == gap_id:
                gap.status = GapStatus.RESOLVED.value
                gap.resolution = resolution
                gap.resolved_by_pattern_id = pattern_id
                self._metadata.cultivation_stats.gaps_resolved += 1
                self._save_metadata()
                logger.info(f"Resolved gap: {gap.unknown_aspect[:50]}...")
                return True
        return False

    def abandon_gap(self, gap_id: str, reason: str) -> bool:
        """
        Mark a gap as abandoned (too difficult, not worth pursuing).

        Args:
            gap_id: The gap ID to abandon
            reason: Why we're abandoning it

        Returns:
            True if found and abandoned, False otherwise
        """
        for gap in self._metadata.gaps:
            if gap.id == gap_id:
                gap.status = GapStatus.ABANDONED.value
                gap.resolution = f"Abandoned: {reason}"
                self._save_metadata()
                return True
        return False

    # =========================================================================
    # Tool Discovery (find uninvestigated tools)
    # =========================================================================

    def get_uninvestigated_tools(self, all_tools: list[str]) -> list[str]:
        """
        Find tools that have no patterns in the knowledge graph.

        Args:
            all_tools: List of all available MCP tool names

        Returns:
            List of tool names with no recorded patterns
        """
        # Load current knowledge graph
        canonical = load_graph(CANONICAL_PATH)
        local = load_graph(LOCAL_PATH)
        graph = merge_graphs(canonical, local)

        # Find tools that have patterns
        tools_with_patterns = set()
        for node in graph.get("nodes", []):
            if node.get("type") == "action":
                tool = node.get("tool")
                if tool:
                    tools_with_patterns.add(tool)

        # Return tools without patterns
        return [t for t in all_tools if t not in tools_with_patterns]

    def get_tool_coverage(self, all_tools: list[str]) -> dict[str, Any]:
        """
        Get coverage statistics for all tools.

        Args:
            all_tools: List of all available MCP tool names

        Returns:
            Coverage statistics including covered, uncovered, and percentage
        """
        canonical = load_graph(CANONICAL_PATH)
        local = load_graph(LOCAL_PATH)
        graph = merge_graphs(canonical, local)

        # Count patterns per tool - check action nodes, intent labels, and pattern notes
        tool_pattern_counts = {}
        for node in graph.get("nodes", []):
            node_type = node.get("type")

            # Action nodes have tool directly
            if node_type == "action":
                tool = node.get("tool")
                if tool:
                    tool_pattern_counts[tool] = tool_pattern_counts.get(tool, 0) + 1

            # Intent nodes may have "use <tool_name>" in labels
            if node_type == "intent":
                labels = node.get("labels", [])
                for label in labels:
                    if isinstance(label, str):
                        # Check for "use rhino_xxx" pattern
                        for tool in all_tools:
                            if f"use {tool}" in label.lower() or tool in label:
                                if tool not in tool_pattern_counts:
                                    tool_pattern_counts[tool] = 0
                                tool_pattern_counts[tool] += 1
                                break

        # Also check V2 patterns for tool coverage
        if self._metadata:
            for pattern in self._metadata.patterns:
                if pattern.tool and pattern.tool not in tool_pattern_counts:
                    tool_pattern_counts[pattern.tool] = 1

        covered = [t for t in all_tools if t in tool_pattern_counts]
        uncovered = [t for t in all_tools if t not in tool_pattern_counts]

        return {
            "total_tools": len(all_tools),
            "covered_tools": len(covered),
            "uncovered_tools": len(uncovered),
            "coverage_percentage": len(covered) / len(all_tools) * 100 if all_tools else 0,
            "covered": covered,
            "uncovered": uncovered,
            "pattern_counts": tool_pattern_counts,
        }

    # =========================================================================
    # Insight Management (meta-knowledge)
    # =========================================================================

    def get_insights(self, category: str | None = None) -> list[Insight]:
        """
        Get recorded insights.

        Args:
            category: Optional category filter

        Returns:
            List of Insight objects
        """
        insights = self._metadata.insights
        if category:
            insights = [i for i in insights if i.category == category]
        return insights

    def record_insight(
        self,
        category: str,
        observation: str,
        implications: list[str] | None = None,
        pattern_ids: list[str] | None = None,
        antipattern_ids: list[str] | None = None,
    ) -> Insight:
        """
        Record a new insight about how tools work.

        Args:
            category: Category of insight
            observation: The insight itself
            implications: What this means for future work
            pattern_ids: Patterns that support this insight
            antipattern_ids: Antipatterns that support this insight

        Returns:
            The created Insight object
        """
        insight = Insight(
            category=category,
            observation=observation,
            implications=implications or [],
            derived_from_pattern_ids=pattern_ids or [],
            derived_from_antipattern_ids=antipattern_ids or [],
            discovered_by_session=self.session_id,
        )
        self._metadata.insights.append(insight)
        self._metadata.cultivation_stats.insights_discovered += 1
        self._save_metadata()
        logger.info(f"Recorded insight: {observation[:50]}...")
        return insight

    # =========================================================================
    # Tool Relationships
    # =========================================================================

    def get_tool_relationships(self, tool: str | None = None) -> list[ToolRelationship]:
        """
        Get tool relationships.

        Args:
            tool: Optional filter for tool_a or tool_b

        Returns:
            List of ToolRelationship objects
        """
        relationships = self._metadata.tool_relationships
        if tool:
            relationships = [
                r for r in relationships
                if r.tool_a == tool or r.tool_b == tool
            ]
        return relationships

    def record_relationship(
        self,
        tool_a: str,
        tool_b: str,
        relationship_type: str,
        description: str,
        example_chain: list[str] | None = None,
    ) -> ToolRelationship:
        """
        Record a relationship between two tools.

        Args:
            tool_a: First tool
            tool_b: Second tool
            relationship_type: Type of relationship
            description: Description of the relationship
            example_chain: Example of tools working together

        Returns:
            The created ToolRelationship object
        """
        rel = ToolRelationship(
            tool_a=tool_a,
            tool_b=tool_b,
            relationship_type=relationship_type,
            description=description,
            example_chain=example_chain or [],
            discovered_by_session=self.session_id,
        )
        self._metadata.tool_relationships.append(rel)
        self._save_metadata()
        logger.info(f"Recorded relationship: {tool_a} -> {tool_b}")
        return rel

    # =========================================================================
    # Verification Management
    # =========================================================================

    def get_verifications(self, pattern_id: str | None = None) -> list[Verification]:
        """
        Get verification records.

        Args:
            pattern_id: Optional filter for specific pattern

        Returns:
            List of Verification objects
        """
        verifications = self._metadata.verifications
        if pattern_id:
            verifications = [v for v in verifications if v.pattern_id == pattern_id]
        return verifications

    def get_unverified_patterns(self) -> list[str]:
        """
        Get pattern IDs that have no visual verification.

        Returns:
            List of pattern IDs without verification
        """
        # Get all pattern IDs from knowledge graph
        canonical = load_graph(CANONICAL_PATH)
        local = load_graph(LOCAL_PATH)
        graph = merge_graphs(canonical, local)

        pattern_ids = {
            node["id"] for node in graph.get("nodes", [])
            if node.get("type") == "pattern"
        }

        # Get verified pattern IDs
        verified_ids = {v.pattern_id for v in self._metadata.verifications}

        # Return unverified
        return list(pattern_ids - verified_ids)

    def record_verification(
        self,
        pattern_id: str,
        geometry_created: bool = False,
        geometry_at_expected_location: bool = False,
        measurements_correct: bool = False,
        visual_description: str = "",
        viewport_hash: str | None = None,
    ) -> Verification:
        """
        Record visual verification of a pattern.

        Args:
            pattern_id: Which pattern was verified
            geometry_created: Whether geometry was created
            geometry_at_expected_location: Whether it's in the right place
            measurements_correct: Whether measurements match
            visual_description: Description of what was seen
            viewport_hash: Optional hash of viewport image

        Returns:
            The created Verification object
        """
        verification = Verification(
            pattern_id=pattern_id,
            session_id=self.session_id,
            geometry_created=geometry_created,
            geometry_at_expected_location=geometry_at_expected_location,
            measurements_correct=measurements_correct,
            visual_description=visual_description,
            viewport_hash=viewport_hash,
        )
        self._metadata.verifications.append(verification)
        self._metadata.cultivation_stats.verifications_performed += 1
        self._save_metadata()
        logger.info(f"Recorded verification for pattern: {pattern_id}")
        return verification

    # =========================================================================
    # Session Management
    # =========================================================================

    def get_last_handoff(self) -> SessionHandoff | None:
        """Get the most recent session handoff."""
        if self._metadata.session_handoffs:
            return self._metadata.session_handoffs[-1]
        return None

    def get_handoffs(self, limit: int = 10) -> list[SessionHandoff]:
        """
        Get recent session handoffs.

        Args:
            limit: Maximum number to return

        Returns:
            List of recent SessionHandoff objects
        """
        return self._metadata.session_handoffs[-limit:]

    def record_handoff(
        self,
        accomplishments: list[str],
        next_priorities: list[str],
        notes: str = "",
        context_percentage_used: float = 0.0,
        reason: str = "context_limit",
    ) -> SessionHandoff:
        """
        Record a session handoff for the next instance.

        Args:
            accomplishments: What was accomplished this session
            next_priorities: What the next session should focus on
            notes: Free-form notes for next instance
            context_percentage_used: How much context was used
            reason: Why handoff is happening

        Returns:
            The created SessionHandoff object
        """
        # Calculate stats for this session
        patterns_this_session = sum(
            1 for v in self._metadata.verifications
            if v.session_id == self.session_id
        )

        handoff = SessionHandoff(
            session_id=self.session_id,
            accomplishments=accomplishments,
            next_priorities=next_priorities,
            notes=notes,
            context_percentage_used=context_percentage_used,
            reason_for_handoff=reason,
            patterns_discovered=patterns_this_session,
            open_gaps=[
                g.id for g in self._metadata.gaps
                if g.status == GapStatus.INVESTIGATING.value
            ],
        )
        self._metadata.session_handoffs.append(handoff)
        self._metadata.cultivation_stats.total_sessions += 1
        self._metadata.cultivation_stats.update_rates()
        self._save_metadata()
        logger.info(f"Recorded handoff: {len(accomplishments)} accomplishments, {len(next_priorities)} priorities")
        return handoff

    # =========================================================================
    # Statistics and Reports
    # =========================================================================

    def get_cultivation_stats(self) -> CultivationStats:
        """Get overall cultivation statistics."""
        return self._metadata.cultivation_stats

    def get_investigation_priorities(self) -> list[tuple[str, float]]:
        """
        Get prioritized list of what to investigate next.

        Returns:
            List of (description, priority_score) tuples, highest first
        """
        priorities = []

        # Add gaps with priority scores
        for gap in self.get_uninvestigated_gaps():
            score = {
                GapPriority.CRITICAL.value: 1.0,
                GapPriority.HIGH.value: 0.8,
                GapPriority.MEDIUM.value: 0.5,
                GapPriority.LOW.value: 0.2,
            }.get(gap.priority, 0.5)
            priorities.append((f"Gap: {gap.unknown_aspect}", score))

        # Add unverified patterns (lower priority than gaps)
        for pattern_id in self.get_unverified_patterns()[:10]:
            priorities.append((f"Verify: {pattern_id}", 0.3))

        # Sort by score descending
        priorities.sort(key=lambda x: x[1], reverse=True)
        return priorities

    # =========================================================================
    # Persistence
    # =========================================================================

    def _load_metadata(self):
        """Load V2 metadata from disk."""
        if V2_METADATA_PATH.exists():
            try:
                data = json.loads(V2_METADATA_PATH.read_text(encoding="utf-8"))
                self._metadata = KnowledgeGraphV2Data.from_dict(data)
                logger.debug(f"Loaded V2 metadata: {len(self._metadata.gaps)} gaps, {len(self._metadata.insights)} insights")
            except Exception as e:
                logger.error(f"Failed to load V2 metadata: {e}")
                self._metadata = KnowledgeGraphV2Data()
        else:
            self._metadata = KnowledgeGraphV2Data()
            logger.info("Created new V2 metadata")

    def _save_metadata(self):
        """Save V2 metadata to disk."""
        self._metadata.last_updated = now_iso()
        try:
            V2_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            V2_METADATA_PATH.write_text(
                json.dumps(self._metadata.to_dict(), indent=2),
                encoding="utf-8"
            )
            logger.debug("Saved V2 metadata")
        except Exception as e:
            logger.error(f"Failed to save V2 metadata: {e}")

    def export_full_state(self) -> dict[str, Any]:
        """
        Export complete state for debugging or backup.

        Returns:
            Dict with both core knowledge and V2 metadata
        """
        return {
            "core_knowledge": get_learning_summary(),
            "v2_metadata": self._metadata.to_dict(),
            "session_id": self.session_id,
        }
