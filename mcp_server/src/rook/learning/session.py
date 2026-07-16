"""
Session Management for Autonomous Learning.

Manages learning sessions - each session:
1. Reads from knowledge graph
2. Picks investigation targets
3. Conducts investigations
4. Writes back to knowledge graph
5. Hands off to next session

This module coordinates the overall learning flow and ensures
graceful handoffs between Claude instances.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from datetime import datetime

from .schema import (
    Gap,
    GapPriority,
    GapStatus,
    SessionHandoff,
    now_iso,
    generate_id,
)
from .graph import KnowledgeGraphV2
from .investigator import Investigator, InvestigationResult
from .hybrid_investigator import HybridInvestigator, HybridInvestigationResult
from .verifier import VisualVerifier
from .monitor import ProgressReporter, setup_logging
from ..explorer.context import ExplorationContext
from ..tool_lifecycle import DispatchOrigin
from ..tool_lifecycle_runtime import deny_if_contained

logger = logging.getLogger("rook.learning.session")


# Type alias for tool executor
ToolExecutor = Callable[[str, dict], Awaitable[dict]]


@dataclass
class SessionPlan:
    """Plan for what this session will work on."""
    session_id: str

    # What to focus on
    primary_targets: list[str] = field(default_factory=list)  # Gap IDs or tool names
    secondary_targets: list[str] = field(default_factory=list)

    # From last session
    continued_from: str | None = None  # Previous session ID
    inherited_priorities: list[str] = field(default_factory=list)

    # Coverage info
    current_coverage: float = 0.0
    uncovered_tools: list[str] = field(default_factory=list)

    # Session limits
    max_investigations: int = 20
    context_limit_percentage: float = 0.8  # Start handoff at 80%


@dataclass
class SessionProgress:
    """Track progress within a session."""
    investigations_completed: int = 0
    patterns_discovered: int = 0
    antipatterns_discovered: int = 0
    gaps_resolved: int = 0
    verifications_performed: int = 0

    # Current state
    current_investigation: str | None = None
    context_usage_estimate: float = 0.0

    # Accomplishments log
    accomplishments: list[str] = field(default_factory=list)


class LearningSession:
    """
    Manages a single learning session.

    Each session:
    1. Reads from knowledge graph (orient)
    2. Picks investigation targets (prioritize)
    3. Conducts investigations
    4. Writes back to knowledge graph
    5. Hands off to next session (graceful handoff)
    """

    def __init__(
        self,
        executor: ToolExecutor,
        all_tools: list[str] | None = None,
        session_id: str | None = None,
        reporter: ProgressReporter | None = None,
        use_hybrid: bool = True,
        use_dspy: bool = True,
        visual_verification: bool = True,
    ):
        """
        Initialize a learning session.

        Args:
            executor: Async function to execute MCP tools
            all_tools: List of all available MCP tool names
            session_id: Optional session ID (generates if not provided)
            reporter: Optional progress reporter (creates one if not provided)
            use_hybrid: Use HybridInvestigator (DSPy+MAB) instead of basic Investigator
            use_dspy: Enable DSPy reasoning (requires ANTHROPIC_API_KEY)
            visual_verification: Verify results visually via viewport capture
        """
        self.session_id = session_id or generate_id()
        self.executor = executor
        self.all_tools = all_tools or []

        # Initialize components
        self.kg = KnowledgeGraphV2(session_id=self.session_id)
        self.context = ExplorationContext()

        # Choose investigator type
        self.use_hybrid = use_hybrid
        if use_hybrid:
            self.hybrid_investigator = HybridInvestigator(
                self.kg, executor,
                use_dspy=use_dspy,
                visual_verification=visual_verification
            )
            # Keep basic investigator for fallback
            self.investigator = Investigator(self.kg, executor, self.context)
            logger.info(f"Using HybridInvestigator (DSPy={use_dspy}, visual={visual_verification})")
        else:
            self.hybrid_investigator = None
            self.investigator = Investigator(self.kg, executor, self.context)
            logger.info("Using basic Investigator")

        self.verifier = VisualVerifier(self.kg, executor)

        # Progress reporter for monitoring
        self.reporter = reporter or ProgressReporter(self.session_id, logger)

        # Session state
        self.plan: SessionPlan | None = None
        self.progress = SessionProgress()
        self.start_time = datetime.now()
        self._is_active = False

    async def orient(self) -> SessionPlan:
        """
        First step: understand current state.

        - How much of the knowledge graph is filled?
        - What are the highest-priority gaps?
        - What was the last session working on?
        - What should this session focus on?

        Returns:
            SessionPlan for this session
        """
        self.reporter.set_state("orienting")
        logger.info(f"Session {self.session_id[:8]} orienting...")

        plan = SessionPlan(session_id=self.session_id)

        # Check last handoff
        last_handoff = self.kg.get_last_handoff()
        if last_handoff:
            plan.continued_from = last_handoff.session_id
            plan.inherited_priorities = last_handoff.next_priorities
            logger.info(f"Continuing from session {last_handoff.session_id[:8]}")
            logger.info(f"Inherited priorities: {plan.inherited_priorities}")

        # Get coverage statistics
        if self.all_tools:
            coverage = self.kg.get_tool_coverage(self.all_tools)
            plan.current_coverage = coverage["coverage_percentage"]
            plan.uncovered_tools = coverage["uncovered"][:10]  # Top 10 uncovered
            logger.info(f"Tool coverage: {plan.current_coverage:.1f}%")

        # Get high-priority gaps
        priority_gaps = self.kg.get_high_priority_gaps()
        uninvestigated_gaps = self.kg.get_uninvestigated_gaps()

        # Get set of covered tools to avoid re-investigating
        covered_tools = set(coverage.get("covered", []))

        # Build target list
        # 1. Inherited priorities from last session (filter out already-covered tools)
        for priority in plan.inherited_priorities[:5]:
            # Skip if this is a tool that's already covered
            if priority.startswith("tool:"):
                tool_name = priority[5:]
                if tool_name in covered_tools:
                    continue
            if priority not in plan.primary_targets:
                plan.primary_targets.append(priority)

        # 2. High-priority gaps
        for gap in priority_gaps[:3]:
            if f"gap:{gap.id}" not in plan.primary_targets:
                plan.primary_targets.append(f"gap:{gap.id}")

        # 3. Uninvestigated gaps
        for gap in uninvestigated_gaps[:5]:
            if f"gap:{gap.id}" not in plan.primary_targets:
                plan.secondary_targets.append(f"gap:{gap.id}")

        # 4. Uncovered tools (these are already filtered)
        for tool in plan.uncovered_tools[:5]:
            target = f"tool:{tool}"
            if target not in plan.primary_targets and target not in plan.secondary_targets:
                plan.secondary_targets.append(target)

        # 5. FALLBACK: If no targets yet, add tools for verification/exploration
        # This ensures we always have something to investigate even at 100% coverage
        if not plan.primary_targets and not plan.secondary_targets:
            logger.info("No gaps/uncovered tools - adding verification targets")

            # Get pattern counts to prioritize tools with fewer patterns
            pattern_counts = coverage.get("pattern_counts", {})

            # Independent tools first - these can work without existing geometry
            # They should be investigated first to BUILD context for dependent tools
            independent_tools = [
                "rhino_create", "rhino_layer_create", "rhino_execute",
                "rhino_ping", "rhino_document", "rhino_layers", "rhino_command",
            ]

            # Dependent tools - these need existing geometry
            dependent_tools = [
                "rhino_transform", "rhino_boolean", "rhino_extrude",
                "rhino_loft", "rhino_sweep", "rhino_block_create",
            ]

            # Add independent tools first (regardless of pattern count - they bootstrap context)
            independent_with_counts = [(t, pattern_counts.get(t, 0)) for t in independent_tools if t in self.all_tools]
            independent_with_counts.sort(key=lambda x: x[1])  # Still sort by count within category

            for tool, count in independent_with_counts[:3]:
                target = f"tool:{tool}"
                plan.secondary_targets.append(target)
                logger.info(f"  Added independent target: {tool} (patterns: {count})")

            # Then add dependent tools (sorted by pattern count)
            dependent_with_counts = [(t, pattern_counts.get(t, 0)) for t in dependent_tools if t in self.all_tools]
            dependent_with_counts.sort(key=lambda x: x[1])

            for tool, count in dependent_with_counts[:2]:
                target = f"tool:{tool}"
                plan.secondary_targets.append(target)
                logger.info(f"  Added dependent target: {tool} (patterns: {count})")

            # If still not enough targets, add random tools
            if len(plan.secondary_targets) < 3:
                import random
                remaining_tools = [t for t in self.all_tools if f"tool:{t}" not in plan.secondary_targets]
                random.shuffle(remaining_tools)
                for tool in remaining_tools[:5]:
                    target = f"tool:{tool}"
                    if target not in plan.secondary_targets:
                        plan.secondary_targets.append(target)

        logger.info(f"Primary targets: {len(plan.primary_targets)}")
        logger.info(f"Secondary targets: {len(plan.secondary_targets)}")

        self.plan = plan
        self.reporter.log_action(
            f"Oriented with {len(plan.primary_targets)} primary, {len(plan.secondary_targets)} secondary targets",
            f"Coverage: {plan.current_coverage:.1f}%"
        )
        return plan

    async def run_investigation_cycle(self, target: str) -> InvestigationResult | HybridInvestigationResult | None:
        """
        Run one investigation cycle.

        Args:
            target: Target identifier (gap:ID, tool:NAME, or description)

        Returns:
            InvestigationResult/HybridInvestigationResult or None if target not found
        """
        if type(target) is str and target.startswith("tool:"):
            denial = deny_if_contained(
                target[5:],
                DispatchOrigin.INTERNAL_HANDLER,
            )
            if denial is not None:
                canonical_name = denial["data"]["tool"]
                if self.use_hybrid:
                    return HybridInvestigationResult(
                        tool=canonical_name,
                        success=False,
                        containment_denial=denial,
                    )
                return InvestigationResult(
                    tool=canonical_name,
                    containment_denial=denial,
                )

        self.progress.current_investigation = target
        self.progress.investigations_completed += 1

        self.reporter.set_state("investigating", target=target)
        logger.info(f"Investigating: {target}")

        result = None

        if target.startswith("gap:"):
            # Investigate a specific gap
            gap_id = target[4:]
            gaps = self.kg.get_gaps()
            gap = next((g for g in gaps if g.id == gap_id), None)

            if gap:
                if self.use_hybrid and self.hybrid_investigator:
                    result = await self.hybrid_investigator.investigate_gap(gap)
                else:
                    result = await self.investigator.investigate_gap(gap)
            else:
                logger.warning(f"Gap not found: {gap_id}")

        elif target.startswith("tool:"):
            # Investigate a tool
            tool_name = target[5:]
            if self.use_hybrid and self.hybrid_investigator:
                result = await self.hybrid_investigator.investigate_tool(tool_name)
            else:
                result = await self.investigator.investigate_tool(tool_name)

        else:
            # Treat as a description - create a gap and investigate
            gap = self.kg.add_gap(
                tool="unknown",
                unknown_aspect=target,
                priority=GapPriority.MEDIUM.value,
            )
            if self.use_hybrid and self.hybrid_investigator:
                result = await self.hybrid_investigator.investigate_gap(gap)
            else:
                result = await self.investigator.investigate_gap(gap)

        # Update progress - handle both result types
        if result:
            patterns = result.patterns_discovered
            antipatterns = result.antipatterns_discovered

            self.progress.patterns_discovered += len(patterns)
            self.progress.antipatterns_discovered += len(antipatterns)

            # Check for gap resolution
            gap_resolved = getattr(result, 'gap_resolved', False)
            if gap_resolved:
                self.progress.gaps_resolved += 1

            # Check for visual verification (hybrid only)
            if hasattr(result, 'visually_verified') and result.visually_verified:
                self.progress.verifications_performed += 1
                self.reporter.log_discovery("verification", result.visual_description or "Verified")

            # Log discoveries to reporter
            for pattern in patterns:
                if isinstance(pattern, dict):
                    note = pattern.get('note', str(pattern))
                else:
                    note = getattr(pattern, 'note', None) or str(pattern)
                self.reporter.log_discovery("pattern", note)

            for antipattern in antipatterns:
                if isinstance(antipattern, dict):
                    note = antipattern.get('diagnosis', antipattern.get('error', str(antipattern)))
                else:
                    note = getattr(antipattern, 'note', None) or str(antipattern)
                self.reporter.log_discovery("antipattern", note)

            if gap_resolved:
                self.reporter.log_discovery("gap_resolved", target)

            # Log accomplishment
            if patterns:
                verified = ""
                if hasattr(result, 'visually_verified') and result.visually_verified:
                    verified = " (verified)"
                self.progress.accomplishments.append(
                    f"Discovered {len(patterns)} pattern(s) for {target}{verified}"
                )
            if gap_resolved:
                self.progress.accomplishments.append(
                    f"Resolved gap: {target}"
                )

            # Log reasoning trace if available (hybrid only)
            if hasattr(result, 'reasoning_trace') and result.reasoning_trace:
                for trace in result.reasoning_trace[-3:]:  # Last 3 items
                    logger.debug(f"  Trace: {trace}")

            # Log investigation complete
            self.reporter.log_investigation_complete(
                target,
                len(patterns),
                len(antipatterns)
            )

        self.progress.current_investigation = None
        return result

    def estimate_context_usage(self) -> float:
        """
        Estimate how much context has been used.

        This is a rough heuristic based on:
        - Number of investigations run
        - Patterns and antipatterns discovered
        - Time elapsed

        Returns:
            Estimated context usage as percentage (0.0 to 1.0)
        """
        # Simple heuristic: each investigation uses ~3-5% of context
        base_usage = self.progress.investigations_completed * 0.04

        # Patterns and antipatterns add to context
        pattern_usage = (
            self.progress.patterns_discovered +
            self.progress.antipatterns_discovered
        ) * 0.01

        # Cap at 1.0
        estimated = min(1.0, base_usage + pattern_usage)
        self.progress.context_usage_estimate = estimated

        return estimated

    def should_handoff(self) -> bool:
        """
        Check if it's time to hand off to next session.

        Returns:
            True if handoff should begin
        """
        if not self.plan:
            return False

        # Check context usage
        usage = self.estimate_context_usage()
        self.reporter.update_context_usage(usage)
        if usage >= self.plan.context_limit_percentage:
            logger.info(f"Context limit reached: {usage:.1%}")
            return True

        # Check investigation limit
        if self.progress.investigations_completed >= self.plan.max_investigations:
            logger.info("Investigation limit reached")
            return True

        return False

    async def graceful_handoff(self, reason: str = "context_limit") -> SessionHandoff:
        """
        Prepare for next session.

        - Commit all findings to knowledge graph
        - Write session summary
        - Identify next priorities
        - Clean up any resources

        Args:
            reason: Why handoff is happening

        Returns:
            SessionHandoff record for next instance
        """
        self.reporter.set_state("handoff", phase=reason)
        logger.info(f"Beginning graceful handoff: {reason}")

        # Determine next priorities
        next_priorities = []

        # Build set of investigated targets from accomplishments
        investigated = set()
        for acc in self.progress.accomplishments:
            # Accomplishments look like "Discovered 1 pattern(s) for tool:rhino_ping"
            if " for " in acc:
                target = acc.split(" for ")[-1]
                investigated.add(target)

        # 1. Any targets we didn't get to
        if self.plan:
            remaining_primary = [
                t for t in self.plan.primary_targets
                if t not in investigated
            ]
            next_priorities.extend(remaining_primary[:3])

            remaining_secondary = [
                t for t in self.plan.secondary_targets
                if t not in investigated
            ]
            next_priorities.extend(remaining_secondary[:3])

        # 2. Any new gaps discovered during this session
        new_gaps = self.kg.get_uninvestigated_gaps()
        for gap in new_gaps[:3]:
            if f"gap:{gap.id}" not in next_priorities:
                next_priorities.append(f"gap:{gap.id} - {gap.unknown_aspect[:50]}")

        # Build notes
        notes = []
        notes.append(f"Session ran for {self.progress.investigations_completed} investigations")
        if self.progress.patterns_discovered > 0:
            notes.append(f"Discovered {self.progress.patterns_discovered} patterns")
        if self.progress.gaps_resolved > 0:
            notes.append(f"Resolved {self.progress.gaps_resolved} gaps")

        # Record handoff
        handoff = self.kg.record_handoff(
            accomplishments=self.progress.accomplishments,
            next_priorities=next_priorities,
            notes="\n".join(notes),
            context_percentage_used=self.progress.context_usage_estimate,
            reason=reason,
        )

        logger.info(f"Handoff recorded: {len(self.progress.accomplishments)} accomplishments")
        logger.info(f"Next priorities: {next_priorities}")

        # Log handoff to reporter
        self.reporter.log_handoff(self.progress.accomplishments, next_priorities)

        self._is_active = False
        return handoff

    async def run(self, max_cycles: int | None = None) -> SessionHandoff:
        """
        Run the complete learning session.

        1. Orient
        2. Run investigation cycles until limit
        3. Graceful handoff

        Args:
            max_cycles: Optional override for max investigation cycles

        Returns:
            SessionHandoff for next instance
        """
        self._is_active = True

        # Orient
        plan = await self.orient()

        if max_cycles is not None:
            plan.max_investigations = max_cycles

        # Run investigations
        all_targets = plan.primary_targets + plan.secondary_targets

        for target in all_targets:
            if not self._is_active:
                break

            if self.should_handoff():
                break

            try:
                await self.run_investigation_cycle(target)
            except Exception as e:
                logger.error(f"Investigation failed for {target}: {e}")
                self.progress.accomplishments.append(f"Failed: {target} - {str(e)[:50]}")

        # Graceful handoff
        reason = "completed" if self.progress.investigations_completed >= len(all_targets) else "context_limit"
        return await self.graceful_handoff(reason=reason)

    def stop(self):
        """Stop the session (will trigger handoff on next cycle)."""
        self._is_active = False

    def get_status(self) -> dict[str, Any]:
        """
        Get current session status.

        Returns:
            Status summary
        """
        elapsed = datetime.now() - self.start_time

        return {
            "session_id": self.session_id,
            "is_active": self._is_active,
            "elapsed_seconds": elapsed.total_seconds(),
            "progress": {
                "investigations_completed": self.progress.investigations_completed,
                "patterns_discovered": self.progress.patterns_discovered,
                "antipatterns_discovered": self.progress.antipatterns_discovered,
                "gaps_resolved": self.progress.gaps_resolved,
                "verifications_performed": self.progress.verifications_performed,
                "current_investigation": self.progress.current_investigation,
                "context_usage_estimate": self.estimate_context_usage(),
            },
            "plan": {
                "primary_targets": self.plan.primary_targets if self.plan else [],
                "secondary_targets": self.plan.secondary_targets if self.plan else [],
                "coverage": self.plan.current_coverage if self.plan else 0.0,
            } if self.plan else None,
            "accomplishments": self.progress.accomplishments,
        }
