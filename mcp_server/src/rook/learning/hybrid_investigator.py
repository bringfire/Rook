"""Hybrid Investigator combining DSPy reasoning with MAB selection.

This is the core of the integrated system - it uses DSPy for intelligent
reasoning and hypothesis generation, MABWiser for principled selection,
and the existing knowledge graph for persistence.

Architecture:
    ┌─────────────────────────────────────────┐
    │         DSPy Strategic Layer            │
    │  (Planner, Diagnoser, HypothesisGen)    │
    └────────────────┬────────────────────────┘
                     │ Generate candidates
                     ▼
    ┌─────────────────────────────────────────┐
    │         MABWiser Tactical Layer         │
    │  (HypothesisSelector, FixSelector)      │
    └────────────────┬────────────────────────┘
                     │ Select action
                     ▼
    ┌─────────────────────────────────────────┐
    │         Execution Layer                  │
    │  (Tool execution with reasoning trace)  │
    └────────────────┬────────────────────────┘
                     │ Outcome + data
                     ▼
    ┌─────────────────────────────────────────┐
    │     Knowledge Consolidation Layer       │
    │  (FeedbackComputer, PatternConsolidator)│
    └─────────────────────────────────────────┘
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

from .dspy_config import is_configured, configure_dspy
from .dspy_modules import (
    InvestigationPlanner,
    FailureDiagnoser,
    HypothesisGenerator,
    InsightSynthesizer,
    PatternConsolidator,
    FeedbackComputer,
    WorkflowDetector,
    # New command learning modules
    CommandLearningPlanner,
    CommandDialogueDiagnoser,
    CommandKnowledgeConsolidator,
    IntentResolver,
    SyntaxBuilder,
)
from .mab_selectors import (
    HypothesisSelector,
    FixSelector,
    PrioritySelector,
    SelectionContext,
    # New command learning selectors
    CommandSelector,
    ModeSelector,
    InputSequenceSelector,
    IntentContext,
    ModeContext,
    LearningContext,
    # Dormant mode flag
    MAB_DORMANT,
)
from .command_knowledge_store import CommandKnowledgeStore
from .command_consolidator import PlaceNewCommand, PropagateGotcha, ReconsolidationManager
from .roadmap_manager import RoadmapManager
from .graph import KnowledgeGraphV2
from .schema import Pattern, Antipattern, Gap, Insight
from .tool_schemas import get_tool_schema, generate_params_for_tool
from .verifier import VisualVerifier, ViewportState

logger = logging.getLogger("rook.learning.hybrid_investigator")

# Type alias for tool executor function
ToolExecutor = Callable[[str, dict], Awaitable[dict]]

class SimpleGeometryContext:
    """Adapter that wraps geometry ID dict to provide ExplorationContext-like interface."""

    def __init__(self, geometry_ids: dict[str, str]):
        self._ids = geometry_ids or {}

    def get_any_id(self):
        return next(iter(self._ids.values())) if self._ids else None

    def get_any_ids(self, limit=2):
        return list(self._ids.values())[:limit]

    def get_curve_id(self):
        return self._ids.get('curve')

    def get_curve_ids(self, limit=2, count=None):
        curve_id = self._ids.get('curve')
        return [curve_id] if curve_id else []

    def get_brep_id(self):
        return self._ids.get('brep')

    def get_brep_ids(self, limit=2, count=None):
        brep_id = self._ids.get('brep')
        return [brep_id] if brep_id else []

    def get_mesh_id(self):
        return self._ids.get('mesh')

    def get_mesh_ids(self, limit=2, count=None):
        mesh_id = self._ids.get('mesh')
        return [mesh_id] if mesh_id else []

    def get_subd_id(self):
        return self._ids.get('subd')

    def get_subd_ids(self, limit=2):
        subd_id = self._ids.get('subd')
        return [subd_id] if subd_id else []

    def get_surface_id(self):
        return self._ids.get('surface') or self._ids.get('brep')

    def get_point_id(self):
        return self._ids.get('point')

    def get_layer(self):
        return self._ids.get('layer')

    def get_material(self):
        return self._ids.get('material')

    def get_block(self):
        return self._ids.get('block')




@dataclass
class HybridInvestigationResult:
    """Result from hybrid investigation."""
    tool: str
    success: bool

    # DSPy outputs
    hypotheses_generated: list[str] = field(default_factory=list)
    diagnosis: Optional[str] = None
    reasoning_trace: list[str] = field(default_factory=list)

    # MAB selections
    hypothesis_selected: Optional[str] = None
    fix_selected: Optional[dict] = None

    # Knowledge captured
    patterns_discovered: list[dict] = field(default_factory=list)
    antipatterns_discovered: list[dict] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)

    # Consolidation results
    consolidation_action: Optional[str] = None  # create_new, merge_with, etc.
    workflow_detected: Optional[dict] = None
    nuanced_reward: Optional[float] = None

    # Visual verification
    visually_verified: bool = False
    visual_description: Optional[str] = None
    viewport_hash_before: Optional[str] = None
    viewport_hash_after: Optional[str] = None

    # Gap tracking (for compatibility with InvestigationResult)
    gap_id: Optional[str] = None
    gap_resolved: bool = False
    resolution: Optional[str] = None
    new_gaps: list = field(default_factory=list)

    # Metrics
    attempts: int = 0
    time_ms: float = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "tool": self.tool,
            "success": self.success,
            "hypotheses_generated": self.hypotheses_generated,
            "diagnosis": self.diagnosis,
            "reasoning_trace": self.reasoning_trace,
            "hypothesis_selected": self.hypothesis_selected,
            "fix_selected": self.fix_selected,
            "patterns_discovered": self.patterns_discovered,
            "antipatterns_discovered": self.antipatterns_discovered,
            "insights": self.insights,
            "consolidation_action": self.consolidation_action,
            "workflow_detected": self.workflow_detected,
            "nuanced_reward": self.nuanced_reward,
            "visually_verified": self.visually_verified,
            "visual_description": self.visual_description,
            "gap_id": self.gap_id,
            "gap_resolved": self.gap_resolved,
            "resolution": self.resolution,
            "attempts": self.attempts,
            "time_ms": self.time_ms,
        }


@dataclass
class CommandLearningResult:
    """Result from learning a Rhino command."""
    command: str
    success: bool
    modes_learned: list[str] = field(default_factory=list)
    modes_failed: list[str] = field(default_factory=list)
    gotchas_discovered: list[str] = field(default_factory=list)
    dialogue_steps: int = 0
    attempts: int = 0
    time_ms: float = 0
    reasoning_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "success": self.success,
            "modes_learned": self.modes_learned,
            "modes_failed": self.modes_failed,
            "gotchas_discovered": self.gotchas_discovered,
            "dialogue_steps": self.dialogue_steps,
            "attempts": self.attempts,
            "time_ms": self.time_ms,
            "reasoning_trace": self.reasoning_trace,
        }


@dataclass
class CommandExecutionResult:
    """Result from executing a Rhino command via intent."""
    intent: str
    command: str
    mode: str
    success: bool
    objects_created: int = 0
    error: Optional[str] = None
    reasoning_trace: list[str] = field(default_factory=list)
    time_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "command": self.command,
            "mode": self.mode,
            "success": self.success,
            "objects_created": self.objects_created,
            "error": self.error,
            "reasoning_trace": self.reasoning_trace,
            "time_ms": self.time_ms,
        }


class HybridInvestigator:
    """
    Investigator that combines DSPy reasoning with MAB selection,
    plus knowledge consolidation for intelligent integration.

    Flow:
    1. DSPy generates hypotheses/plans
    2. MAB selects which to try (exploration/exploitation)
    3. Execute and capture outcome
    4. Knowledge Consolidation Layer:
       a. FeedbackComputer: compute nuanced reward
       b. PatternConsolidator: decide how to integrate
       c. WorkflowDetector: detect multi-tool sequences
    5. Update MAB with nuanced feedback
    6. If failure, DSPy diagnoses, MAB selects fix
    7. Record consolidated knowledge to graph
    """

    def __init__(
        self,
        kg: Optional[KnowledgeGraphV2] = None,
        executor: Optional[ToolExecutor] = None,
        use_dspy: bool = True,
        visual_verification: bool = True,
        knowledge_store: Optional[CommandKnowledgeStore] = None,
        roadmap: Optional[RoadmapManager] = None,
    ):
        """
        Initialize the hybrid investigator.

        Args:
            kg: Knowledge graph for storing learnings (optional for command-only mode)
            executor: Async function to execute tool calls (optional for testing)
            use_dspy: Whether to use DSPy (requires ANTHROPIC_API_KEY)
            visual_verification: Whether to verify results visually
            knowledge_store: CommandKnowledgeStore for command syntax knowledge
            roadmap: RoadmapManager for learning roadmap
        """
        self.kg = kg
        self.executor = executor
        self.use_dspy = use_dspy
        self.use_visual_verification = visual_verification

        # Command learning components
        self.knowledge_store = knowledge_store or CommandKnowledgeStore()
        self.roadmap = roadmap or RoadmapManager()

        # Reconsolidation manager for periodic structure refinement (Phase 7)
        self._reconsolidation_manager: Optional[ReconsolidationManager] = None

        # Track available geometry
        self._geometry_ids: dict[str, str] = {}  # type -> ID

        # Visual verifier for viewport-based verification
        self.verifier = VisualVerifier(kg, executor) if visual_verification and kg and executor else None

        # DSPy modules for MCP tool investigation (lazy init)
        self._planner: Optional[InvestigationPlanner] = None
        self._diagnoser: Optional[FailureDiagnoser] = None
        self._hypothesis_gen: Optional[HypothesisGenerator] = None
        self._insight_synth: Optional[InsightSynthesizer] = None
        self._consolidator: Optional[PatternConsolidator] = None
        self._feedback_computer: Optional[FeedbackComputer] = None
        self._workflow_detector: Optional[WorkflowDetector] = None

        # DSPy modules for command learning (lazy init)
        self._cmd_planner: Optional[CommandLearningPlanner] = None
        self._cmd_diagnoser: Optional[CommandDialogueDiagnoser] = None
        self._cmd_consolidator: Optional[CommandKnowledgeConsolidator] = None
        self._intent_resolver: Optional[IntentResolver] = None
        self._syntax_builder: Optional[SyntaxBuilder] = None

        # DSPy modules for structural integration (Phase 5 - lazy init)
        self._place_new_command: Optional[Any] = None  # dspy.ChainOfThought(PlaceNewCommand)
        self._propagate_gotcha: Optional[Any] = None   # dspy.ChainOfThought(PropagateGotcha)

        # MAB selectors for MCP tools (no API key required)
        self.hypothesis_selector = HypothesisSelector()
        self.fix_selector = FixSelector()
        self.priority_selector = PrioritySelector()

        # MAB selectors for command learning/execution
        self.command_selector = CommandSelector()
        self.mode_selector = ModeSelector()
        self.input_selector = InputSequenceSelector()

        # Training buffer for DSPy optimization
        self.training_buffer: list[dict] = []

        # Recent operations for workflow detection
        self._recent_operations: list[dict] = []
        self._max_recent_ops = 10

        # Session metrics
        self._success_count = 0
        self._attempt_count = 0
        self._verification_count = 0

    def _init_dspy_modules(self) -> bool:
        """Initialize DSPy modules lazily. Returns True if successful."""
        if not self.use_dspy:
            return False

        if self._planner is not None:
            return True  # Already initialized

        try:
            if not is_configured():
                configure_dspy()

            self._planner = InvestigationPlanner()
            self._diagnoser = FailureDiagnoser()
            self._hypothesis_gen = HypothesisGenerator()
            self._insight_synth = InsightSynthesizer()
            self._consolidator = PatternConsolidator()
            self._feedback_computer = FeedbackComputer()
            self._workflow_detector = WorkflowDetector()

            logger.info("DSPy modules initialized successfully")
            return True

        except Exception as e:
            logger.warning(f"Failed to initialize DSPy modules: {e}")
            self.use_dspy = False
            return False

    def _init_cmd_dspy_modules(self) -> bool:
        """Initialize command learning DSPy modules lazily."""
        if not self.use_dspy:
            return False

        if self._cmd_planner is not None:
            return True  # Already initialized

        try:
            if not is_configured():
                configure_dspy()

            self._cmd_planner = CommandLearningPlanner()
            self._cmd_diagnoser = CommandDialogueDiagnoser()
            self._cmd_consolidator = CommandKnowledgeConsolidator()
            self._intent_resolver = IntentResolver()
            self._syntax_builder = SyntaxBuilder()

            # Initialize structural integration modules (Phase 5)
            if DSPY_AVAILABLE:
                self._place_new_command = dspy.ChainOfThought(PlaceNewCommand)
                self._propagate_gotcha = dspy.ChainOfThought(PropagateGotcha)
                logger.info("Structural integration DSPy modules initialized")

            logger.info("Command learning DSPy modules initialized successfully")
            return True

        except Exception as e:
            logger.warning(f"Failed to initialize command DSPy modules: {e}")
            return False

    @property
    def reconsolidation_manager(self) -> Optional[ReconsolidationManager]:
        """Lazy initialization of reconsolidation manager."""
        if self._reconsolidation_manager is None:
            # Get paths from knowledge store
            try:
                from pathlib import Path
                knowledge_dir = Path(self.knowledge_store._path).parent if hasattr(self.knowledge_store, '_path') else Path("knowledge/commands")
                structure_path = knowledge_dir / "command_structure.json"
                knowledge_path = knowledge_dir / "command_knowledge.json"

                if structure_path.exists() and knowledge_path.exists():
                    self._reconsolidation_manager = ReconsolidationManager(
                        structure_path=structure_path,
                        knowledge_path=knowledge_path,
                    )
                    logger.info("Reconsolidation manager initialized")
                else:
                    logger.debug(f"Reconsolidation manager not initialized - missing files")
            except Exception as e:
                logger.warning(f"Failed to initialize reconsolidation manager: {e}")
        return self._reconsolidation_manager

    async def investigate_tool(self, tool_name: str) -> HybridInvestigationResult:
        """
        Investigate a tool using hybrid DSPy + MAB approach.

        Args:
            tool_name: MCP tool name to investigate

        Returns:
            HybridInvestigationResult with all learnings
        """
        start = time.time()
        result = HybridInvestigationResult(tool=tool_name, success=False)

        # Build MAB context
        mab_context = self._build_mab_context(tool_name)

        # Get tool info
        tool_schema = get_tool_schema(tool_name)
        tool_description = tool_schema.description if tool_schema else f"MCP tool: {tool_name}"

        # Query existing knowledge
        existing = self.kg.query(tool=tool_name)
        known_patterns = [p.get("note", str(p)) for p in existing.get("patterns", [])]
        known_antipatterns = [a.get("reason", str(a)) for a in existing.get("avoid", [])]
        available_geometry = list(self._geometry_ids.keys())

        # === DSPy STRATEGIC LAYER ===
        plan = None
        if self._init_dspy_modules() and self._planner:
            try:
                plan = self._planner(
                    tool_name=tool_name,
                    tool_description=tool_description,
                    known_patterns=known_patterns,
                    known_antipatterns=known_antipatterns,
                    available_geometry=available_geometry,
                )
                result.hypotheses_generated = list(plan.hypotheses) if plan.hypotheses else []
                result.reasoning_trace.append(f"Generated {len(result.hypotheses_generated)} hypotheses")
            except Exception as e:
                logger.warning(f"DSPy planning failed: {e}")
                result.reasoning_trace.append(f"DSPy planning failed: {e}")

        # Fallback if no hypotheses
        if not result.hypotheses_generated:
            result.hypotheses_generated = ["Use default parameters from schema"]

        # === MAB TACTICAL LAYER ===
        # Select which hypothesis to test
        selected_hypothesis, idx = self.hypothesis_selector.select(
            result.hypotheses_generated,
            mab_context,
        )
        result.hypothesis_selected = selected_hypothesis
        result.reasoning_trace.append(f"MAB selected hypothesis: {selected_hypothesis}")

        # Get params for selected hypothesis
        # ALWAYS start with schema-based params as foundation (ensures required params)
        params = generate_params_for_tool(tool_name, SimpleGeometryContext(self._geometry_ids))

        # Merge any DSPy-suggested params on top (but keep schema defaults for missing)
        if plan and hasattr(plan, 'test_sequence') and plan.test_sequence and idx < len(plan.test_sequence):
            dspy_params = plan.test_sequence[idx]
            if isinstance(dspy_params, dict):
                # Merge DSPy params, but don't overwrite with None values
                for key, value in dspy_params.items():
                    if value is not None:
                        params[key] = value
            else:
                # DSPy gave a string description, add as note
                params["_hypothesis_note"] = str(dspy_params)

        result.reasoning_trace.append(f"Using params: {list(params.keys())}")

        # === EXECUTION LAYER ===
        result.attempts += 1
        self._attempt_count += 1

        # Capture viewport BEFORE execution for visual verification
        viewport_before: Optional[ViewportState] = None
        if self.verifier and self.use_visual_verification:
            try:
                viewport_before = await self.verifier.capture_state()
                result.viewport_hash_before = viewport_before.image_hash
                result.reasoning_trace.append(f"Captured viewport before (hash: {viewport_before.image_hash})")
            except Exception as e:
                logger.warning(f"Failed to capture viewport before: {e}")

        try:
            response = await self.executor(tool_name, params)
        except Exception as e:
            response = {"success": False, "error": str(e)}

        success = response.get("success", False)

        # Capture viewport AFTER execution
        viewport_after: Optional[ViewportState] = None
        if self.verifier and self.use_visual_verification:
            try:
                viewport_after = await self.verifier.capture_state()
                result.viewport_hash_after = viewport_after.image_hash
            except Exception as e:
                logger.warning(f"Failed to capture viewport after: {e}")

        if success:
            result.success = True
            self._success_count += 1

            # Track any created geometry
            if "data" in response:
                self._track_created_geometry(tool_name, response["data"])

            # Create candidate pattern
            candidate_pattern = {
                "tool": tool_name,
                "params": params,
                "note": result.hypothesis_selected or f"Basic usage of {tool_name}",
                "confidence": 0.7,
            }

            # === KNOWLEDGE CONSOLIDATION LAYER ===
            nuanced_reward = 1.0  # Default

            # Compute nuanced feedback
            if self._feedback_computer:
                try:
                    feedback = self._feedback_computer(
                        tool_name=tool_name,
                        params_used=params,
                        outcome="success",
                        response_data=response.get("data", {}),
                        original_intent=f"use {tool_name}",
                        hypothesis_tested=result.hypothesis_selected or "",
                        execution_context={
                            "geometry": available_geometry,
                            "session_progress": self._attempt_count / 20,
                        },
                    )
                    nuanced_reward = float(feedback.reward_score) if hasattr(feedback, 'reward_score') else 1.0
                    result.nuanced_reward = nuanced_reward

                    quality = getattr(feedback, 'quality_assessment', 'unknown')
                    result.reasoning_trace.append(f"Feedback: {quality} (reward={nuanced_reward:.2f})")
                except Exception as e:
                    logger.warning(f"Feedback computation failed: {e}")
                    result.nuanced_reward = 1.0

            # Decide how to consolidate pattern
            consolidation_action = "create_new"  # Default
            if self._consolidator:
                try:
                    existing_patterns = existing.get("patterns", [])
                    related_patterns = self._get_related_patterns(tool_name)

                    consolidation = self._consolidator(
                        new_pattern=candidate_pattern,
                        existing_patterns_for_tool=existing_patterns,
                        related_patterns_other_tools=related_patterns,
                        triggering_intent=f"use {tool_name}",
                    )
                    consolidation_action = str(consolidation.action) if hasattr(consolidation, 'action') else "create_new"
                    result.consolidation_action = consolidation_action

                    rationale = getattr(consolidation, 'rationale', '')
                    result.reasoning_trace.append(f"Consolidation: {consolidation_action} - {rationale}")
                except Exception as e:
                    logger.warning(f"Consolidation failed: {e}")
                    result.consolidation_action = "create_new"

            # Apply consolidation decision
            if consolidation_action == "create_new":
                result.patterns_discovered.append(candidate_pattern)

            # Track operation for workflow detection
            self._recent_operations.append({
                "tool": tool_name,
                "params": params,
                "intent": f"use {tool_name}",
                "timestamp": time.time(),
            })
            if len(self._recent_operations) > self._max_recent_ops:
                self._recent_operations.pop(0)

            # Check for workflow patterns
            if len(self._recent_operations) >= 3 and self._workflow_detector:
                try:
                    workflow_check = self._workflow_detector(
                        recent_operations=self._recent_operations,
                        triggering_intent=f"use {tool_name}",
                        existing_workflows=[],
                    )
                    if hasattr(workflow_check, 'is_workflow') and workflow_check.is_workflow:
                        result.workflow_detected = {
                            "name": getattr(workflow_check, 'workflow_name', ''),
                            "steps": getattr(workflow_check, 'workflow_steps', []),
                        }
                        result.reasoning_trace.append(
                            f"Workflow detected: {result.workflow_detected['name']}"
                        )
                except Exception as e:
                    logger.warning(f"Workflow detection failed: {e}")

            # === VISUAL VERIFICATION ===
            if self.verifier and viewport_before and viewport_after:
                try:
                    diff = self.verifier.compare_states(viewport_before, viewport_after)
                    if diff.has_changes():
                        result.visually_verified = True
                        self._verification_count += 1

                        # Build description of visual changes
                        changes = []
                        if diff.objects_added > 0:
                            changes.append(f"+{diff.objects_added} objects")
                        if diff.objects_removed > 0:
                            changes.append(f"-{diff.objects_removed} objects")
                        if diff.type_changes:
                            for t, delta in diff.type_changes.items():
                                changes.append(f"{t}: {'+' if delta > 0 else ''}{delta}")

                        result.visual_description = f"Viewport changed: {', '.join(changes)}"
                        result.reasoning_trace.append(f"Visual verification PASSED: {result.visual_description}")

                        # Boost confidence for visually verified patterns
                        if result.patterns_discovered:
                            result.patterns_discovered[-1]["confidence"] = 0.9
                            result.patterns_discovered[-1]["visually_verified"] = True
                    else:
                        result.visual_description = "No visible changes in viewport"
                        result.reasoning_trace.append("Visual verification: No changes detected (may be expected)")
                except Exception as e:
                    logger.warning(f"Visual verification failed: {e}")
                    result.reasoning_trace.append(f"Visual verification error: {e}")

            # Update MAB with nuanced reward
            self.hypothesis_selector.update(
                result.hypothesis_selected,
                success=True,
                context=mab_context,
                nuanced_reward=nuanced_reward,
            )

            # Record to knowledge graph
            if consolidation_action != "discard":
                self.kg.record(
                    intent=f"use {tool_name}",
                    action={"tool": tool_name, "params": params},
                    outcome="success",
                )

        else:
            # === FAILURE HANDLING ===
            error_msg = str(response.get("data", response.get("error", "Unknown error")))
            result.reasoning_trace.append(f"Execution failed: {error_msg}")

            # DSPy diagnoses failure
            if self._diagnoser:
                try:
                    diagnosis = self._diagnoser(
                        tool_name=tool_name,
                        params_used=params,
                        error_message=error_msg,
                        available_geometry=available_geometry,
                        tool_schema=tool_schema.to_dict() if tool_schema and hasattr(tool_schema, 'to_dict') else {},
                    )
                    result.diagnosis = str(diagnosis.root_cause) if hasattr(diagnosis, 'root_cause') else None
                    result.reasoning_trace.append(f"Diagnosis: {result.diagnosis}")

                    # MAB selects fix to try
                    fix_suggestions = list(diagnosis.fix_suggestions) if hasattr(diagnosis, 'fix_suggestions') and diagnosis.fix_suggestions else []
                    if fix_suggestions:
                        error_category = str(diagnosis.error_category) if hasattr(diagnosis, 'error_category') else "unknown"
                        selected_fix, fix_idx = self.fix_selector.select(
                            fix_suggestions,
                            error_category=error_category,
                            tool_name=tool_name,
                        )
                        result.fix_selected = selected_fix
                        result.reasoning_trace.append(f"Trying fix: {selected_fix}")

                        # Apply fix and retry
                        fixed_params = self._apply_fix(params, selected_fix)
                        result.attempts += 1
                        self._attempt_count += 1

                        try:
                            retry_response = await self.executor(tool_name, fixed_params)
                        except Exception as e:
                            retry_response = {"success": False, "error": str(e)}

                        if retry_response.get("success", False):
                            result.success = True
                            self._success_count += 1
                            result.reasoning_trace.append("Fix succeeded!")

                            # Record corrected pattern
                            result.patterns_discovered.append({
                                "tool": tool_name,
                                "params": fixed_params,
                                "note": f"Fixed: {result.diagnosis}",
                                "confidence": 0.6,
                            })

                            # Update fix selector
                            self.fix_selector.update(
                                selected_fix,
                                success=True,
                                error_category=error_category,
                                tool_name=tool_name,
                            )

                            # Record with correction
                            self.kg.record(
                                intent=f"use {tool_name}",
                                action={"tool": tool_name, "params": fixed_params},
                                outcome="success",
                                correction_of={"params": params, "error": error_msg},
                            )
                        else:
                            self.fix_selector.update(
                                selected_fix,
                                success=False,
                                error_category=error_category,
                                tool_name=tool_name,
                            )
                            result.reasoning_trace.append("Fix did not work")

                except Exception as e:
                    logger.warning(f"DSPy diagnosis failed: {e}")
                    result.reasoning_trace.append(f"Diagnosis failed: {e}")

            # Update hypothesis MAB with failure
            self.hypothesis_selector.update(
                result.hypothesis_selected,
                success=False,
                context=mab_context,
            )

            # Record antipattern if still failed
            if not result.success:
                result.antipatterns_discovered.append({
                    "tool": tool_name,
                    "params": params,
                    "error": error_msg,
                    "diagnosis": result.diagnosis or "Unknown",
                })

                self.kg.record(
                    intent=f"use {tool_name}",
                    action={"tool": tool_name, "params": params},
                    outcome="failure",
                )

        # Buffer for DSPy training
        self._buffer_training_example(tool_name, plan, result, success=result.success)

        result.time_ms = (time.time() - start) * 1000
        return result

    async def investigate_gap(self, gap: Gap) -> HybridInvestigationResult:
        """
        Investigate a knowledge gap using hybrid approach.

        Args:
            gap: The gap to investigate

        Returns:
            HybridInvestigationResult
        """
        result = HybridInvestigationResult(tool=gap.tool, success=False)

        # Use DSPy to generate hypotheses for the gap
        if self._init_dspy_modules() and self._hypothesis_gen:
            try:
                hyp_result = self._hypothesis_gen(
                    gap_description=gap.unknown_aspect,
                    tool_name=gap.tool,
                    related_patterns=[],
                    failed_attempts=[h.get("hypothesis", "") for h in gap.tested_hypotheses],
                )
                result.hypotheses_generated = list(hyp_result.hypotheses) if hyp_result.hypotheses else []
            except Exception as e:
                logger.warning(f"DSPy hypothesis generation failed: {e}")

        # Fallback to gap's own hypotheses
        if not result.hypotheses_generated:
            result.hypotheses_generated = gap.hypotheses or ["Try default parameters"]

        # Test top hypotheses
        for hypothesis in result.hypotheses_generated[:3]:
            result.reasoning_trace.append(f"Testing hypothesis: {hypothesis}")
            # Generate params based on hypothesis
            params = generate_params_for_tool(gap.tool, SimpleGeometryContext(self._geometry_ids))

            try:
                response = await self.executor(gap.tool, params)
                result.attempts += 1

                if response.get("success"):
                    result.success = True
                    result.hypothesis_selected = hypothesis
                    result.patterns_discovered.append({
                        "tool": gap.tool,
                        "params": params,
                        "note": hypothesis,
                        "confidence": 0.7,
                    })
                    break
            except Exception as e:
                result.reasoning_trace.append(f"Hypothesis failed: {e}")

        return result

    def synthesize_insights(self) -> list[Insight]:
        """
        Synthesize insights from accumulated patterns and antipatterns.

        Returns:
            List of generated insights
        """
        insights = []

        if not self._init_dspy_modules() or not self._insight_synth:
            return insights

        # Get recent patterns and antipatterns
        summary = self.kg.get_summary()
        patterns = [p.get("note", str(p)) for p in summary.get("patterns", [])[:10]]
        antipatterns = [a.get("reason", str(a)) for a in summary.get("antipatterns", [])[:10]]
        tools = list(set(
            [p.get("tool", "") for p in summary.get("patterns", [])] +
            [a.get("tool", "") for a in summary.get("antipatterns", [])]
        ))[:10]

        if patterns or antipatterns:
            try:
                result = self._insight_synth(
                    patterns=patterns,
                    antipatterns=antipatterns,
                    tool_names=tools,
                )
                if hasattr(result, 'insight') and result.insight:
                    insight = Insight(
                        observation=str(result.insight),
                        category=str(result.category) if hasattr(result, 'category') else "tool_relationship",
                        implications=list(result.implications) if hasattr(result, 'implications') else [],
                        discovered_by_session=self.kg.session_id,
                    )
                    insights.append(insight)
            except Exception as e:
                logger.warning(f"Insight synthesis failed: {e}")

        return insights

    def get_training_buffer(self) -> list[dict]:
        """Get accumulated training examples for DSPy optimization."""
        return self.training_buffer.copy()

    def clear_training_buffer(self):
        """Clear the training buffer (after optimization)."""
        self.training_buffer = []

    def set_geometry(self, geometry_type: str, obj_id: str):
        """Set an available geometry ID for testing."""
        self._geometry_ids[geometry_type] = obj_id

    def clear_geometry(self):
        """Clear tracked geometry."""
        self._geometry_ids.clear()

    def get_stats(self) -> dict:
        """Get investigator statistics."""
        return {
            "attempts": self._attempt_count,
            "successes": self._success_count,
            "success_rate": self._success_count / max(1, self._attempt_count),
            "verifications": self._verification_count,
            "verification_rate": self._verification_count / max(1, self._success_count),
            "dspy_enabled": self.use_dspy and self._planner is not None,
            "visual_verification_enabled": self.use_visual_verification,
            "training_buffer_size": len(self.training_buffer),
            "hypothesis_selector": self.hypothesis_selector.get_stats(),
            "priority_selector": self.priority_selector.get_stats(),
        }

    def _build_mab_context(self, tool_name: str) -> SelectionContext:
        """Build MAB selection context."""
        existing = self.kg.query(tool=tool_name)

        success_rate = (
            self._success_count / self._attempt_count
            if self._attempt_count > 0 else 0.5
        )

        return SelectionContext(
            tool_name=tool_name,
            existing_pattern_count=len(existing.get("patterns", [])),
            existing_antipattern_count=len(existing.get("avoid", [])),
            session_progress=min(1.0, self._attempt_count / 20),
            recent_success_rate=success_rate,
            geometry_available=list(self._geometry_ids.keys()),
        )

    def _get_related_patterns(self, tool_name: str) -> list[dict]:
        """Get patterns from related tools."""
        related = []
        related_tools = self._get_related_tools(tool_name)

        for rt in related_tools[:3]:
            rt_existing = self.kg.query(tool=rt)
            related.extend(rt_existing.get("patterns", [])[:2])

        return related

    def _get_related_tools(self, tool_name: str) -> list[str]:
        """Get tools related to the given tool."""
        parts = tool_name.split("_")
        if len(parts) < 2:
            return []

        category = parts[1] if len(parts) > 1 else ""

        # Known tool relationships
        relationships = {
            "create": ["transform", "boolean", "extrude"],
            "transform": ["create", "copy", "boolean"],
            "boolean": ["create", "transform", "brep"],
            "loft": ["create", "curve", "sweep"],
            "sweep": ["loft", "curve", "extrude"],
            "curve": ["loft", "sweep", "create"],
            "brep": ["boolean", "transform", "split"],
            "mesh": ["boolean", "create", "quad"],
            "subd": ["mesh", "create", "brep"],
        }

        related_categories = relationships.get(category, [])
        return [f"rhino_{cat}" for cat in related_categories]

    def _track_created_geometry(self, tool_name: str, data: Any):
        """Track geometry created by tool execution."""
        if not isinstance(data, dict):
            return

        # Check for created IDs
        if "id" in data:
            obj_id = data["id"]
            # Infer type from tool name
            if "curve" in tool_name.lower() or "circle" in tool_name.lower():
                self._geometry_ids["curve"] = obj_id
            elif "mesh" in tool_name.lower():
                self._geometry_ids["mesh"] = obj_id
            elif "subd" in tool_name.lower():
                self._geometry_ids["subd"] = obj_id
            elif "brep" in tool_name.lower() or "boolean" in tool_name.lower():
                self._geometry_ids["brep"] = obj_id
            else:
                self._geometry_ids["object"] = obj_id

    def _apply_fix(self, params: dict, fix: dict) -> dict:
        """Apply a fix suggestion to parameters."""
        new_params = params.copy()
        if isinstance(fix, dict):
            for key, value in fix.items():
                if key not in ["description", "reason", "explanation"]:
                    new_params[key] = value
        return new_params

    def _buffer_training_example(
        self,
        tool_name: str,
        plan,
        result: HybridInvestigationResult,
        success: bool,
    ):
        """Buffer a training example for DSPy optimization."""
        example = {
            "tool_name": tool_name,
            "hypotheses_generated": result.hypotheses_generated,
            "hypothesis_selected": result.hypothesis_selected,
            "diagnosis": result.diagnosis,
            "fix_selected": result.fix_selected,
            "success": success,
            "patterns_discovered": len(result.patterns_discovered),
            "consolidation_action": result.consolidation_action,
            "workflow_detected": result.workflow_detected,
            "nuanced_reward": result.nuanced_reward,
            "reasoning_trace": result.reasoning_trace,
        }
        self.training_buffer.append(example)

        # Keep buffer reasonable
        if len(self.training_buffer) > 100:
            self.training_buffer = self.training_buffer[-100:]

    # =========================================================================
    # COMMAND LEARNING METHODS
    # =========================================================================

    async def learn_command(
        self,
        command: str,
        dialogue_executor: Optional[Callable[[str, list[str]], Awaitable[dict]]] = None,
    ) -> CommandLearningResult:
        """
        Learn a Rhino command by exploring its dialogue and modes.

        This is the core learning method that:
        1. Uses DSPy to plan what input sequences to try
        2. Uses MAB to select which sequences to test
        3. Executes the dialogue and captures results
        4. Consolidates learned knowledge into the knowledge store

        Args:
            command: Rhino command to learn (e.g., "-Box", "Sphere")
            dialogue_executor: Optional async function to execute command dialogue.
                              Signature: (command, inputs) -> {success, dialogue_steps, ...}

        Returns:
            CommandLearningResult with learning outcomes
        """
        start = time.time()
        result = CommandLearningResult(command=command, success=False)

        # Normalize command name
        normalized = command.lstrip("_")
        if not normalized.startswith("-"):
            normalized = "-" + normalized

        result.command = normalized

        # Get existing knowledge
        existing = self.knowledge_store.get_command(normalized)
        known_modes = self.knowledge_store.get_modes(normalized) if existing else []
        known_options = list(existing.options.keys()) if existing else []

        # Get command from roadmap for category info
        roadmap_cmd = self.roadmap.get_command(normalized)
        category = roadmap_cmd.category if roadmap_cmd else "Unknown"

        result.reasoning_trace.append(f"Learning command: {normalized} ({category})")
        result.reasoning_trace.append(f"Known modes: {known_modes}")

        # === DSPy PLANNING ===
        input_sequences: list[list[str]] = []
        hypotheses: list[str] = []

        if self._init_cmd_dspy_modules() and self._cmd_planner:
            try:
                # Get related knowledge for context (includes dialogue structure)
                related = self._get_related_command_knowledge(normalized)

                # Get dialogue info for THIS command (if we have prior observations)
                dialogue_info = self._get_command_dialogue_info(normalized)
                if dialogue_info:
                    # Prepend dialogue info so DSPy knows what prompts to expect
                    related = [f"[THIS COMMAND] {d}" for d in dialogue_info] + related

                plan = self._cmd_planner(
                    command_name=normalized,
                    command_category=category,
                    known_modes=known_modes,
                    known_options=known_options,
                    related_knowledge=related,
                    geometry_types_available=list(self._geometry_ids.keys()),
                )

                hypotheses = list(plan.hypotheses) if hasattr(plan, 'hypotheses') and plan.hypotheses else []
                input_sequences = list(plan.input_sequences) if hasattr(plan, 'input_sequences') and plan.input_sequences else []

                result.reasoning_trace.append(f"DSPy planned {len(input_sequences)} input sequences")
            except Exception as e:
                logger.warning(f"DSPy planning failed: {e}")
                result.reasoning_trace.append(f"DSPy planning failed: {e}")

        # Fallback input sequences if DSPy fails
        if not input_sequences:
            input_sequences = self._generate_fallback_sequences(normalized, category)
            result.reasoning_trace.append(f"Using {len(input_sequences)} fallback sequences")

        # === MAB SELECTION & EXECUTION ===
        # Build learning context
        learning_ctx = LearningContext(
            command=normalized,
            mode="default",
            attempts_so_far=0,
            successes_so_far=0,
            unexplored_options=known_options,
        )

        for seq_idx, inputs in enumerate(input_sequences[:5]):  # Limit to 5 attempts
            result.attempts += 1

            # Use MAB to possibly reorder/select sequence
            selected_seq, _ = self.input_selector.select(
                [inputs],
                learning_ctx,
            )

            result.reasoning_trace.append(f"Attempt {result.attempts}: {selected_seq}")

            # Execute if we have a dialogue executor
            if dialogue_executor:
                try:
                    response = await dialogue_executor(normalized, selected_seq)

                    success = response.get("success", False)
                    dialogue_steps = response.get("dialogue_steps", 0)
                    result.dialogue_steps += dialogue_steps

                    if success:
                        # Extract mode name from inputs or response
                        mode_name = self._extract_mode_name(selected_seq, response)

                        # Add to knowledge store
                        syntax = self._build_syntax_from_dialogue(normalized, selected_seq, response)
                        self.knowledge_store.add_mode(
                            command=normalized,
                            mode_name=mode_name,
                            syntax=syntax,
                            dialogue=str(response.get("dialogue", "")),
                            example=f"_-{normalized.lstrip('-')} {' '.join(selected_seq)}",
                        )

                        result.modes_learned.append(mode_name)
                        result.reasoning_trace.append(f"Learned mode: {mode_name}")

                        # Phase 5: Place command in structure after learning first mode
                        if len(result.modes_learned) == 1:
                            placement = self._place_command_in_structure(normalized)
                            if placement:
                                result.reasoning_trace.append(
                                    f"Placed in family '{placement.get('family')}', "
                                    f"inherited {len(placement.get('inherited_gotchas', []))} gotchas"
                                )

                        # Update MAB with success (knowledge_gained=True since we learned a mode)
                        self.input_selector.update(selected_seq, True, True, learning_ctx)
                        learning_ctx.successes_so_far += 1
                    else:
                        error = response.get("error") or "Unknown failure"
                        result.modes_failed.append(f"{selected_seq[0] if selected_seq else 'default'}: {error}")
                        result.reasoning_trace.append(f"Failed: {error}")

                        # Update MAB with failure (knowledge_gained=False)
                        self.input_selector.update(selected_seq, False, False, learning_ctx)

                        # Check if this reveals a gotcha (only if we have an error message)
                        gotcha = self._extract_gotcha(error, selected_seq) if error else None
                        if gotcha:
                            self.knowledge_store.add_gotcha(normalized, gotcha)
                            result.gotchas_discovered.append(gotcha)

                            # Phase 5: Propagate gotcha to similar commands
                            propagated_to = self._propagate_gotcha_to_similar(gotcha, normalized)
                            if propagated_to:
                                result.reasoning_trace.append(
                                    f"Propagated gotcha to {len(propagated_to)} similar commands: {propagated_to}"
                                )

                    learning_ctx.attempts_so_far += 1

                except Exception as e:
                    logger.warning(f"Dialogue execution failed: {e}")
                    result.reasoning_trace.append(f"Execution error: {e}")
            else:
                # No executor - just record that we would try this
                result.reasoning_trace.append(f"Would try sequence: {selected_seq}")

        # Mark success if we learned at least one mode
        result.success = len(result.modes_learned) > 0

        # Save knowledge if we learned anything
        if result.success:
            self.knowledge_store.save()

            # Update roadmap
            if roadmap_cmd and not roadmap_cmd.learned:
                self.roadmap.record_attempt(normalized, success=True)
                self.roadmap.save()

            # Phase 7: Record new command for reconsolidation tracking
            if self.reconsolidation_manager:
                command_data = self.knowledge_store.get_command(normalized)
                if command_data:
                    self.reconsolidation_manager.record_new_command(
                        normalized,
                        command_data.__dict__ if hasattr(command_data, '__dict__') else {}
                    )
                    # Check if reconsolidation should be triggered
                    if self.reconsolidation_manager.should_reconsolidate():
                        result.reasoning_trace.append("Reconsolidation threshold reached")
                        # Note: Reconsolidation itself is run separately, not blocking here

        result.time_ms = (time.time() - start) * 1000
        return result

    async def learn_next_from_roadmap(
        self,
        dialogue_executor: Optional[Callable[[str, list[str]], Awaitable[dict]]] = None,
        phase: Optional[int] = None,
        category: Optional[str] = None,
    ) -> Optional[CommandLearningResult]:
        """
        Get the next unlearned command from the roadmap and learn it.

        Args:
            dialogue_executor: Function to execute command dialogue
            phase: Optional phase filter (1-7)
            category: Optional category filter

        Returns:
            CommandLearningResult or None if all commands learned
        """
        # Get next unlearned command
        next_cmd = self.roadmap.get_next_unlearned(phase=phase, category=category)

        if next_cmd is None:
            logger.info("All commands in roadmap have been learned!")
            return None

        logger.info(f"Learning next command: {next_cmd.name} ({next_cmd.category})")

        # Learn the command
        result = await self.learn_command(next_cmd.command_name, dialogue_executor)

        return result

    # =========================================================================
    # COMMAND EXECUTION METHODS
    # =========================================================================

    async def execute_intent(
        self,
        intent: str,
        command_executor: Optional[Callable[[str], Awaitable[dict]]] = None,
    ) -> CommandExecutionResult:
        """
        Execute a user intent by selecting the best command and mode.

        This uses learned knowledge to:
        1. Resolve the intent to a command+mode using DSPy
        2. Use MAB to select among candidates based on history
        3. Build the exact syntax and execute
        4. Update MAB with result for future selections

        Args:
            intent: Natural language intent (e.g., "create a sphere at origin")
            command_executor: Function to execute command string

        Returns:
            CommandExecutionResult with execution outcome
        """
        start = time.time()
        result = CommandExecutionResult(intent=intent, command="", mode="", success=False)

        result.reasoning_trace.append(f"Executing intent: {intent}")

        # === INTENT RESOLUTION ===
        selected_command = ""
        selected_mode = "default"
        param_values: dict = {}
        selection_source = ""  # Track what selected the command

        # First, search knowledge store for candidates
        candidates = self.knowledge_store.search_by_intent(intent)

        if not candidates:
            result.error = "No matching commands found for intent"
            result.reasoning_trace.append(result.error)
            result.time_ms = (time.time() - start) * 1000
            return result

        result.reasoning_trace.append(f"Found {len(candidates)} candidate commands")

        # Build intent context for MAB (used by both MAB and mode selection)
        intent_ctx = IntentContext(
            intent_keywords=intent.lower().split()[:10],
            geometry_types_available=list(self._geometry_ids.keys()),
            recent_commands_used=[],
            session_success_rate=self._success_count / max(1, self._attempt_count),
        )

        # === PHASE 6: MAB-FIRST SELECTION ===
        # Try MAB first - it learns from actual execution outcomes
        candidate_commands = [c.command for c in candidates[:5]]
        mab_command, mab_idx = self.command_selector.select(candidate_commands, intent_ctx)
        mab_confidence = self.command_selector.get_confidence(mab_command)

        # Use MAB selection if it has sufficient confidence (learned from experience)
        # When MAB_DORMANT=True, threshold is infinity so DSPy always handles selection
        MAB_CONFIDENCE_THRESHOLD = float('inf') if MAB_DORMANT else 0.65
        if mab_confidence > MAB_CONFIDENCE_THRESHOLD:
            selected_command = mab_command
            selected_mode = candidates[mab_idx].mode if mab_idx < len(candidates) else "default"
            selection_source = "mab"
            result.reasoning_trace.append(
                f"MAB selected: {selected_command} (confidence={mab_confidence:.2f})"
            )

            # CRITICAL: Even when MAB selects the command, we still need DSPy to extract parameters
            # from the intent. Without parameters, the syntax builder can't fill in the template.
            if self._init_cmd_dspy_modules() and self._intent_resolver:
                try:
                    # Build command candidates with just the MAB-selected command
                    cmd = self.knowledge_store.get_command(selected_command)
                    if cmd:
                        command_candidates = [{
                            "command": selected_command,
                            "modes": list(cmd.modes.keys()),
                            "description": cmd.description,
                        }]

                        available_geometry = [
                            {"id": gid, "type": gtype, "description": f"{gtype} object"}
                            for gtype, gid in self._geometry_ids.items()
                        ]

                        resolution = self._intent_resolver(
                            user_intent=intent,
                            available_geometry=available_geometry,
                            command_candidates=command_candidates,
                            recent_commands=[],
                        )

                        # Extract parameters from DSPy resolution
                        if hasattr(resolution, 'parameter_values') and resolution.parameter_values:
                            param_values = dict(resolution.parameter_values)
                            result.reasoning_trace.append(f"DSPy extracted params: {list(param_values.keys())}")

                        # Optionally use DSPy's mode if it differs
                        if hasattr(resolution, 'selected_mode') and resolution.selected_mode:
                            selected_mode = resolution.selected_mode
                except Exception as e:
                    logger.warning(f"DSPy parameter extraction failed: {e}")
                    result.reasoning_trace.append(f"DSPy param extraction failed: {e}")
        else:
            # MAB lacks confidence or is dormant - use DSPy for intelligent selection
            if MAB_DORMANT:
                result.reasoning_trace.append("MAB dormant, using DSPy")
            else:
                result.reasoning_trace.append(
                    f"MAB confidence low ({mab_confidence:.2f}), using DSPy"
                )

            if self._init_cmd_dspy_modules() and self._intent_resolver:
                try:
                    # Build command candidates with proper structure
                    command_candidates = []
                    for c in candidates[:5]:
                        cmd = self.knowledge_store.get_command(c.command)
                        if cmd:
                            command_candidates.append({
                                "command": c.command,
                                "modes": list(cmd.modes.keys()),
                                "description": cmd.description,
                            })

                    # Build available geometry list
                    available_geometry = [
                        {"id": gid, "type": gtype, "description": f"{gtype} object"}
                        for gtype, gid in self._geometry_ids.items()
                    ]

                    resolution = self._intent_resolver(
                        user_intent=intent,
                        available_geometry=available_geometry,
                        command_candidates=command_candidates,
                        recent_commands=[],
                    )

                    if hasattr(resolution, 'selected_command') and resolution.selected_command:
                        selected_command = resolution.selected_command
                        selected_mode = resolution.selected_mode if hasattr(resolution, 'selected_mode') else "default"
                        param_values = dict(resolution.parameter_values) if hasattr(resolution, 'parameter_values') and resolution.parameter_values else {}
                        selection_source = "dspy"

                        result.reasoning_trace.append(
                            f"DSPy selected: {selected_command} mode={selected_mode}"
                        )

                except Exception as e:
                    logger.warning(f"DSPy intent resolution failed: {e}")
                    result.reasoning_trace.append(f"DSPy failed: {e}")

            # Final fallback to top candidate if both MAB and DSPy fail
            if not selected_command and candidates:
                selected_command = candidates[0].command
                selected_mode = candidates[0].mode
                selection_source = "fallback"
                result.reasoning_trace.append(f"Fallback to top candidate: {selected_command}")

        result.command = selected_command
        result.mode = selected_mode

        # === BUILD SYNTAX ===
        syntax = self.knowledge_store.get_syntax(selected_command, selected_mode)

        if not syntax:
            # Try default mode
            syntax = self.knowledge_store.get_syntax(selected_command, "default")

        if not syntax:
            result.error = f"No syntax found for {selected_command} mode {selected_mode}"
            result.reasoning_trace.append(result.error)
            result.time_ms = (time.time() - start) * 1000
            return result

        # Build full command string
        full_command = syntax
        if self._syntax_builder:
            try:
                # Get gotchas from command knowledge store
                gotchas = self.knowledge_store.get_gotchas(selected_command)

                # === INTEGRATE MAIN KNOWLEDGE GRAPH ===
                # Query the main knowledge graph for avoid patterns (corrections/antipatterns)
                # This is critical for the meta-learning loop: corrections recorded via
                # knowledge_record() must be used by execute_intent() to avoid mistakes
                if self.kg:
                    # Query by INTENT (not tool) since the graph indexes by intent
                    # Use the command name as part of the intent query
                    cmd_name = selected_command.lstrip('-').lower()
                    kg_data = self.kg.query(intent=f"create {cmd_name}")

                    # Also try with the original intent for broader matching
                    kg_data_intent = self.kg.query(intent=intent)

                    # Merge avoid patterns from both queries
                    all_avoid = kg_data.get("avoid", []) + kg_data_intent.get("avoid", [])

                    # Extract avoid patterns and add to gotchas
                    avoid_count = 0
                    for avoid in all_avoid:
                        # Extract the reason/pattern from the antipattern
                        if isinstance(avoid, dict):
                            reason = avoid.get("reason") or avoid.get("error") or str(avoid)
                            # Only include relevant avoid patterns (mentioning the command)
                            if reason and cmd_name in reason.lower() or "DirectionConstraint" in reason:
                                if reason not in gotchas and f"AVOID: {reason}" not in gotchas:
                                    gotchas.append(f"AVOID: {reason}")
                                    avoid_count += 1
                        elif isinstance(avoid, str) and avoid not in gotchas:
                            if cmd_name in avoid.lower():
                                gotchas.append(f"AVOID: {avoid}")
                                avoid_count += 1

                    # Also check patterns for correction notes
                    for pattern in kg_data.get("patterns", []) + kg_data_intent.get("patterns", []):
                        if isinstance(pattern, dict) and pattern.get("note"):
                            note = pattern.get("note", "")
                            # If it's a correction note, extract what to avoid
                            if ("Fixed:" in note or "corrected" in note.lower()) and cmd_name in note.lower():
                                if note not in gotchas:
                                    gotchas.append(f"Pattern: {note}")

                    if avoid_count > 0:
                        result.reasoning_trace.append(
                            f"Knowledge graph provided {avoid_count} relevant avoid patterns"
                        )

                built = self._syntax_builder(
                    command_name=selected_command,
                    mode=selected_mode,
                    mode_syntax=syntax,
                    parameter_values=param_values,
                    geometry_ids=self._geometry_ids,
                    gotchas=gotchas,
                )
                if hasattr(built, 'full_command') and built.full_command:
                    full_command = built.full_command
            except Exception as e:
                logger.warning(f"Syntax builder failed: {e}")

        result.reasoning_trace.append(f"Command: {full_command}")

        # === EXECUTE ===
        if command_executor:
            try:
                response = await command_executor(full_command)
                result.success = response.get("success", False)
                result.objects_created = response.get("objects_created", 0)

                if not result.success:
                    result.error = response.get("error", "Unknown error")
                    result.reasoning_trace.append(f"Failed: {result.error}")

                    # Phase 7: Record failure for reconsolidation pattern detection
                    if self.reconsolidation_manager:
                        self.reconsolidation_manager.record_failure(
                            command=selected_command,
                            reason=result.error,
                            context={
                                "intent": intent,
                                "mode": selected_mode,
                                "full_command": full_command,
                                "params": param_values,
                            }
                        )
                else:
                    result.reasoning_trace.append(f"Success! Created {result.objects_created} objects")

                # === PHASE 6: FEEDBACK LOOP ===
                # Update command selector MAB with execution outcome
                # This trains MAB to prefer commands that actually succeed
                self.command_selector.update(selected_command, result.success, intent_ctx)

                # Update mode selector (correct API: command, mode, success, context)
                mode_ctx = ModeContext(
                    command=selected_command,
                    available_params=list(param_values.keys()),
                    geometry_available=bool(self._geometry_ids),
                    previous_mode_used=None,
                )
                self.mode_selector.update(selected_command, selected_mode, result.success, mode_ctx)

                # Log selection source effectiveness for analysis
                logger.debug(
                    f"Intent execution: source={selection_source}, "
                    f"command={selected_command}, success={result.success}"
                )

            except Exception as e:
                result.error = str(e)
                result.reasoning_trace.append(f"Execution error: {e}")
        else:
            result.reasoning_trace.append("No executor - command would be: " + full_command)

        result.time_ms = (time.time() - start) * 1000
        return result

    async def execute_command(
        self,
        command: str,
        mode: str = "default",
        params: Optional[dict] = None,
        command_executor: Optional[Callable[[str], Awaitable[dict]]] = None,
    ) -> CommandExecutionResult:
        """
        Execute a specific Rhino command with known syntax.

        Args:
            command: Command name (e.g., "-Sphere")
            mode: Mode to use (e.g., "diameter", "3point")
            params: Parameter values to substitute
            command_executor: Function to execute command string

        Returns:
            CommandExecutionResult
        """
        start = time.time()
        result = CommandExecutionResult(
            intent=f"execute {command} {mode}",
            command=command,
            mode=mode,
            success=False,
        )

        # Get syntax from knowledge
        syntax = self.knowledge_store.get_syntax(command, mode)

        if not syntax:
            result.error = f"No syntax found for {command} mode {mode}"
            result.reasoning_trace.append(result.error)
            result.time_ms = (time.time() - start) * 1000
            return result

        # Build command with params
        full_command = syntax
        if params and self._syntax_builder:
            try:
                # Get gotchas from both knowledge systems
                gotchas = self.knowledge_store.get_gotchas(command)

                # Integrate main knowledge graph avoid patterns (query by intent, not tool)
                if self.kg:
                    cmd_name = command.lstrip('-').lower()
                    kg_data = self.kg.query(intent=f"create {cmd_name}")
                    for avoid in kg_data.get("avoid", []):
                        if isinstance(avoid, dict):
                            reason = avoid.get("reason") or avoid.get("error") or str(avoid)
                            if reason and (cmd_name in reason.lower() or "DirectionConstraint" in reason):
                                if reason not in gotchas and f"AVOID: {reason}" not in gotchas:
                                    gotchas.append(f"AVOID: {reason}")
                        elif isinstance(avoid, str) and avoid not in gotchas:
                            if cmd_name in avoid.lower():
                                gotchas.append(f"AVOID: {avoid}")

                built = self._syntax_builder(
                    command_name=command,
                    mode=mode,
                    mode_syntax=syntax,
                    parameter_values=params,
                    geometry_ids=self._geometry_ids,
                    gotchas=gotchas,
                )
                if hasattr(built, 'full_command') and built.full_command:
                    full_command = built.full_command
            except Exception as e:
                logger.warning(f"Syntax builder failed: {e}")

        result.reasoning_trace.append(f"Executing: {full_command}")

        # Execute
        if command_executor:
            try:
                response = await command_executor(full_command)
                result.success = response.get("success", False)
                result.objects_created = response.get("objects_created", 0)

                if not result.success:
                    result.error = response.get("error")
                    result.reasoning_trace.append(f"Failed: {result.error}")
                else:
                    result.reasoning_trace.append(f"Success! Created {result.objects_created} objects")

            except Exception as e:
                result.error = str(e)
                result.reasoning_trace.append(f"Execution error: {e}")
        else:
            result.reasoning_trace.append("No executor provided")

        result.time_ms = (time.time() - start) * 1000
        return result

    # =========================================================================
    # HELPER METHODS FOR COMMAND LEARNING
    # =========================================================================

    def _get_related_command_knowledge(self, command: str) -> list[str]:
        """Get knowledge from related commands with dialogue structure.

        Returns syntax AND dialogue info so DSPy knows what inputs to expect.
        """
        related = self.knowledge_store.get_related_commands(command)
        knowledge = []

        for rel_cmd in related[:3]:
            rel = self.knowledge_store.get_command(rel_cmd)
            if rel:
                for mode_name, mode in rel.modes.items():
                    if mode.syntax:
                        # Include dialogue structure so DSPy knows what prompts to expect
                        entry = f"{rel_cmd} {mode_name}: {mode.syntax}"
                        if mode.dialogue:
                            entry += f" (prompts: {mode.dialogue})"
                        if mode.example:
                            entry += f" [example: {mode.example}]"
                        knowledge.append(entry)

        return knowledge

    def _get_command_dialogue_info(self, command: str) -> list[str]:
        """Get dialogue structure for the command being learned.

        This tells DSPy what prompts to expect based on existing observations.
        If we've already learned this command, use that knowledge.
        """
        existing = self.knowledge_store.get_command(command)
        if not existing:
            return []

        dialogue_info = []
        for mode_name, mode in existing.modes.items():
            if mode.dialogue:
                # Format: "mode_name: <prompt1>: <prompt2>: ... [example inputs: x,y,z 10]"
                entry = f"{mode_name}: {mode.dialogue}"
                if mode.example:
                    # Extract just the inputs from example (after command name)
                    example_parts = mode.example.split()
                    if len(example_parts) > 1:
                        inputs = " ".join(example_parts[1:])
                        entry += f" [inputs: {inputs}]"
                dialogue_info.append(entry)

        return dialogue_info

    def _generate_fallback_sequences(self, command: str, category: str) -> list[list[str]]:
        """Generate fallback input sequences based on existing knowledge or category.

        If we have existing examples for this command, use them.
        Otherwise, fall back to category-based patterns.
        """
        # First try: Use existing examples from knowledge store
        existing = self.knowledge_store.get_command(command)
        if existing and existing.modes:
            sequences = []
            for mode_name, mode in existing.modes.items():
                if mode.example:
                    # Extract inputs from example (after command name)
                    # Example: "_-Sphere 0,0,0 5" -> ["0,0,0", "5"]
                    parts = mode.example.split()
                    if len(parts) > 1:
                        inputs = parts[1:]  # Skip command name
                        sequences.append(inputs)
            if sequences:
                return sequences

        # Second try: Category-based patterns
        category_patterns = {
            "Primitives": [
                ["0,0,0", "10"],  # center + size
                ["0,0,0", "10,10,10"],  # two corners
                ["_Enter"],  # accept defaults
            ],
            "Curves": [
                ["0,0,0", "10,0,0"],  # two points
                ["0,0,0", "5,5,0", "10,0,0"],  # three points
                ["_Enter"],
            ],
            "Transforms": [
                ["0,0,0", "10,0,0"],  # from/to
                ["_Enter"],
            ],
            "Booleans": [
                ["_Enter"],  # typically needs pre-selected geometry
            ],
        }

        return category_patterns.get(category, [["_Enter"]])

    def _extract_mode_name(self, inputs: list[str], response: dict) -> str:
        """Extract mode name from inputs or response."""
        # Check for mode flags in inputs
        for inp in inputs:
            if inp.startswith("_") and not inp.startswith("_-"):
                return inp.lstrip("_").lower()

        # Check response for mode
        if "mode" in response:
            return response["mode"]

        return "default"

    def _build_syntax_from_dialogue(self, command: str, inputs: list[str], response: dict) -> str:
        """Build syntax template from dialogue."""
        # Simple template: command + placeholders for inputs
        placeholders = []
        for i, inp in enumerate(inputs):
            if inp.startswith("_"):
                placeholders.append(inp)
            elif "," in inp:
                placeholders.append(f"<point{i+1}>")
            else:
                placeholders.append(f"<param{i+1}>")

        return f"_-{command.lstrip('-')} {' '.join(placeholders)}"

    def _extract_gotcha(self, error: str, inputs: list[str]) -> Optional[str]:
        """Extract a gotcha from an error message."""
        error_lower = error.lower()

        # Common gotcha patterns
        if "select" in error_lower and "first" in error_lower:
            return "Requires pre-selected geometry"
        if "collinear" in error_lower:
            return "Points must not be collinear"
        if "coplanar" in error_lower:
            return "Points must not be coplanar"
        if "closed" in error_lower:
            return "Curve must be closed"
        if "invalid" in error_lower:
            return f"Invalid input: {error}"

        return None

    def get_learning_progress(self) -> dict:
        """Get learning progress from roadmap."""
        progress = self.roadmap.get_overall_progress()
        return {
            "total_commands": progress.total_commands,
            "learned_commands": progress.learned_commands,
            "percentage": progress.percentage,
            "current_phase": progress.current_phase,
            "knowledge_stats": self.knowledge_store.get_stats(),
        }

    # =========================================================================
    # PHASE 5: STRUCTURAL INTEGRATION METHODS
    # =========================================================================

    def _place_command_in_structure(self, command: str) -> Optional[dict]:
        """
        Place a newly learned command into the existing structure.

        Uses DSPy PlaceNewCommand signature to determine:
        - Which family the command belongs to
        - What similar commands exist
        - What gotchas it should inherit

        Args:
            command: Normalized command name (e.g., "-Box")

        Returns:
            Dict with placement info or None if placement fails
        """
        if not self._place_new_command or not DSPY_AVAILABLE:
            logger.debug("PlaceNewCommand not available, skipping structure placement")
            return None

        try:
            # Get command knowledge
            cmd_pattern = self.knowledge_store.get_command(command)
            if not cmd_pattern:
                return None

            # Build command JSON
            new_command_json = json.dumps({
                "command": command,
                "description": cmd_pattern.description,
                "modes": list(cmd_pattern.modes.keys()),
                "options": list(cmd_pattern.options.keys()),
                "gotchas": cmd_pattern.gotchas,
            })

            # Get existing families from knowledge store structure
            families = self.knowledge_store.get_all_families()
            families_info = []
            for family in families:
                info = self.knowledge_store.get_family_info_by_name(family)
                if info:
                    families_info.append({
                        "name": family,
                        "description": info.get("description", ""),
                        "commands": info.get("commands", [])[:5],  # Limit for token efficiency
                    })
            existing_families_json = json.dumps(families_info)

            # Get similar pairs from structure cache
            similar_pairs = []
            if hasattr(self.knowledge_store, '_structure_cache') and self.knowledge_store._structure_cache:
                raw_pairs = self.knowledge_store._structure_cache.get("similar_pairs", [])
                # Simplify for DSPy - just include command names and similarity
                for pair in raw_pairs[:10]:  # Limit for token efficiency
                    similar_pairs.append({
                        "cmd1": pair.get("cmd1", ""),
                        "cmd2": pair.get("cmd2", ""),
                        "similarity_score": pair.get("similarity_score", 0),
                        "reason": pair.get("reason", ""),
                    })
            existing_similar_pairs_json = json.dumps(similar_pairs)

            # Run DSPy placement
            result = self._place_new_command(
                new_command_json=new_command_json,
                existing_families_json=existing_families_json,
                existing_similar_pairs_json=existing_similar_pairs_json,
            )

            placement = {
                "command": command,
                "family": result.family if hasattr(result, 'family') else None,
                "similar_to": result.similar_to if hasattr(result, 'similar_to') else None,
                "inherited_gotchas": [],
                "new_shared_gotchas": [],
            }

            # Parse inherited gotchas
            if hasattr(result, 'inherited_gotchas_json') and result.inherited_gotchas_json:
                try:
                    placement["inherited_gotchas"] = json.loads(result.inherited_gotchas_json)
                except json.JSONDecodeError:
                    pass

            # Parse new shared gotchas
            if hasattr(result, 'new_shared_gotchas_json') and result.new_shared_gotchas_json:
                try:
                    placement["new_shared_gotchas"] = json.loads(result.new_shared_gotchas_json)
                except json.JSONDecodeError:
                    pass

            logger.info(f"Placed {command} in family '{placement['family']}', similar to '{placement['similar_to']}'")

            # Apply inherited gotchas to command
            for gotcha in placement["inherited_gotchas"]:
                if gotcha not in cmd_pattern.gotchas:
                    self.knowledge_store.add_gotcha(command, gotcha)
                    logger.debug(f"Inherited gotcha '{gotcha}' for {command}")

            return placement

        except Exception as e:
            logger.warning(f"Failed to place command in structure: {e}")
            return None

    def _propagate_gotcha_to_similar(self, gotcha: str, source_command: str) -> list[str]:
        """
        Check if a discovered gotcha applies to similar/related commands.

        Uses DSPy PropagateGotcha signature to identify which other commands
        might have the same gotcha based on family membership and similarity.

        Args:
            gotcha: The gotcha text discovered
            source_command: Command where gotcha was discovered

        Returns:
            List of commands the gotcha was propagated to
        """
        if not self._propagate_gotcha or not DSPY_AVAILABLE:
            logger.debug("PropagateGotcha not available, skipping propagation")
            return []

        try:
            # Get candidate commands (family members + similar commands)
            candidates = set()

            # Add commands from same family
            family = self.knowledge_store.get_family(source_command)
            if family:
                family_cmds = self.knowledge_store.get_commands_in_family(family)
                candidates.update(family_cmds)

            # Add similar commands
            similar = self.knowledge_store.get_similar_commands(source_command)
            for sim in similar:
                if isinstance(sim, dict) and 'command' in sim:
                    candidates.add(sim['command'])
                elif isinstance(sim, str):
                    candidates.add(sim)

            # Remove source command
            candidates.discard(source_command)

            if not candidates:
                return []

            # Build candidate objects with full info as expected by PropagateGotcha
            candidate_objects = []
            for cmd in candidates:
                cmd_info = self.knowledge_store.get_command(cmd)
                if cmd_info:
                    candidate_objects.append({
                        "command": cmd,
                        "description": cmd_info.description or "",
                        "modes": list(cmd_info.modes.keys()) if cmd_info.modes else [],
                    })
                else:
                    # Include even if no detailed info
                    candidate_objects.append({
                        "command": cmd,
                        "description": "",
                        "modes": [],
                    })

            candidate_commands_json = json.dumps(candidate_objects)

            # Run DSPy propagation
            result = self._propagate_gotcha(
                gotcha_text=gotcha,
                source_command=source_command,
                candidate_commands_json=candidate_commands_json,
            )

            # Parse result - returns dict of {command: confidence}
            applies_to_dict = {}
            if hasattr(result, 'applies_to_json') and result.applies_to_json:
                try:
                    applies_to_dict = json.loads(result.applies_to_json)
                except json.JSONDecodeError:
                    pass

            # Apply gotcha to identified commands (those with confidence > 0.5)
            propagated_to = []
            for cmd, confidence in applies_to_dict.items():
                # Validate it's a real candidate and has sufficient confidence
                if cmd in candidates and (isinstance(confidence, (int, float)) and confidence > 0.5):
                    existing = self.knowledge_store.get_command(cmd)
                    if existing and gotcha not in existing.gotchas:
                        self.knowledge_store.add_gotcha(cmd, f"[propagated from {source_command}] {gotcha}")
                        propagated_to.append(cmd)
                        logger.info(f"Propagated gotcha to {cmd} (confidence={confidence}): {gotcha}")

            if propagated_to:
                self.knowledge_store.save()

            reasoning = result.reasoning if hasattr(result, 'reasoning') else ""
            if reasoning:
                logger.debug(f"Propagation reasoning: {reasoning}")

            return propagated_to

        except Exception as e:
            logger.warning(f"Failed to propagate gotcha: {e}")
            return []
