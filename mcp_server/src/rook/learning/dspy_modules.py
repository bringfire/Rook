"""DSPy modules for Rook learning system.

Modules wrap signatures with specific invocation strategies:
- dspy.Predict: Direct prediction, fastest
- dspy.ChainOfThought: Step-by-step reasoning before output
- dspy.Module: Custom multi-step modules

These modules are optimized via DSPy's compilers (BootstrapFewShot, MIPROv2)
which automatically find good few-shot examples and prompt formulations.
"""

import logging
import re
from typing import Any, Optional

import dspy

# Learning boundary: configure DSPy once, on first import of any module that runs an LM.
from .dspy_config import ensure_configured as _ensure_dspy_configured
_ensure_dspy_configured()

from .dspy_signatures import (
    # Strategic Layer (MCP tools)
    OrientSession,
    PlanInvestigation,
    DiagnoseFailure,
    GenerateHypotheses,
    SynthesizeInsight,
    # Knowledge Consolidation (MCP tools)
    ConsolidatePattern,
    SemanticFeedback,
    DetectWorkflow,
    # Execution Layer (MCP tools)
    ExecuteWithReasoning,
    VerifyResult,
    SelectNextAction,
    ExtractDemonstration,
    # Command Learning (Rhino commands)
    PlanCommandLearning,
    DiagnoseCommandDialogue,
    ConsolidateCommandKnowledge,
    ResolveIntentToCommand,
    BuildCommandSyntax,
    # Grasshopper (GH canvas)
    GHSelectComponents,
    GHSelectComponentsFast,
    GHPlanComponentWiring,
    GHPlanComponentWiringFast,
    GHWiringBuilder,
    GHAnalyzeCanvas,
    # Pattern Memory (Phase 2 Meta-Learning)
    ExtractPatternMetadata,
    DecidePatternLinks,
    EvolveNeighborPatterns,
    # Reflection (Phase 5 Meta-Learning)
    AnalyzeStruggleSequence,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Strategic Layer Modules
# =============================================================================

class SessionOrienter(dspy.Module):
    """Orients the session by analyzing knowledge graph state.

    Uses ChainOfThought to reason through priorities before deciding.
    This is important because orientation sets the direction for the
    entire investigation session.
    """

    def __init__(self):
        super().__init__()
        self.orient = dspy.ChainOfThought(OrientSession)

    def forward(
        self,
        coverage_percentage: float,
        uncovered_tools: list[str],
        open_gaps: list[str],
        last_session_priorities: list[str],
        recent_failures: list[str],
    ) -> dspy.Prediction:
        """
        Analyze knowledge state and determine session priorities.

        Args:
            coverage_percentage: Current tool coverage (0-100)
            uncovered_tools: Tools without documented patterns
            open_gaps: Known unknowns that need investigation
            last_session_priorities: Handoff from previous session
            recent_failures: Recent failures to avoid or retry

        Returns:
            Prediction with primary_focus, investigation_targets, rationale
        """
        return self.orient(
            coverage_percentage=coverage_percentage,
            uncovered_tools=uncovered_tools,
            open_gaps=open_gaps,
            last_session_priorities=last_session_priorities,
            recent_failures=recent_failures,
        )


class InvestigationPlanner(dspy.Module):
    """Plans how to investigate an unknown tool or gap.

    Uses ChainOfThought for careful hypothesis generation.
    The quality of the plan directly affects investigation success.
    """

    def __init__(self):
        super().__init__()
        self.plan = dspy.ChainOfThought(PlanInvestigation)

    def forward(
        self,
        tool_name: str,
        tool_description: str,
        known_patterns: list[str],
        known_antipatterns: list[str],
        available_geometry: list[str],
    ) -> dspy.Prediction:
        """
        Generate investigation plan with hypotheses and test sequence.

        Args:
            tool_name: MCP tool to investigate
            tool_description: Tool's documentation
            known_patterns: Existing patterns (may be empty)
            known_antipatterns: Known failure modes
            available_geometry: Geometry types in context

        Returns:
            Prediction with hypotheses, required_geometry, test_sequence, expected_outcomes
        """
        return self.plan(
            tool_name=tool_name,
            tool_description=tool_description,
            known_patterns=known_patterns,
            known_antipatterns=known_antipatterns,
            available_geometry=available_geometry,
        )


class FailureDiagnoser(dspy.Module):
    """Diagnoses tool failures and suggests fixes.

    Critical for learning from mistakes. Uses ChainOfThought to
    carefully analyze the error before suggesting fixes.
    """

    def __init__(self):
        super().__init__()
        self.diagnose = dspy.ChainOfThought(DiagnoseFailure)

    def forward(
        self,
        tool_name: str,
        params_used: dict,
        error_message: str,
        available_geometry: list[str],
        tool_schema: dict,
    ) -> dspy.Prediction:
        """
        Diagnose failure and suggest fixes.

        Args:
            tool_name: Tool that failed
            params_used: Parameters that caused failure
            error_message: Error message from tool
            available_geometry: Available geometry IDs
            tool_schema: Tool's parameter schema

        Returns:
            Prediction with error_category, root_cause, fix_suggestions, missing_preconditions
        """
        return self.diagnose(
            tool_name=tool_name,
            params_used=params_used,
            error_message=error_message,
            available_geometry=available_geometry,
            tool_schema=tool_schema,
        )


class HypothesisGenerator(dspy.Module):
    """Generates hypotheses about tool behavior from partial information.

    Used when investigating gaps. Simpler than full planning,
    focused just on generating testable hypotheses.
    """

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(GenerateHypotheses)

    def forward(
        self,
        gap_description: str,
        tool_name: str,
        related_patterns: list[str],
        failed_attempts: list[str],
    ) -> dspy.Prediction:
        """
        Generate hypotheses to test a knowledge gap.

        Args:
            gap_description: What we don't understand
            tool_name: Tool the gap relates to
            related_patterns: Patterns from similar tools
            failed_attempts: Things already tried

        Returns:
            Prediction with hypotheses, test_approach
        """
        return self.generate(
            gap_description=gap_description,
            tool_name=tool_name,
            related_patterns=related_patterns,
            failed_attempts=failed_attempts,
        )


class InsightSynthesizer(dspy.Module):
    """Synthesizes higher-level insights from observations.

    Looks across patterns and antipatterns to identify meta-knowledge.
    Uses ChainOfThought for deep reasoning about relationships.
    """

    def __init__(self):
        super().__init__()
        self.synthesize = dspy.ChainOfThought(SynthesizeInsight)

    def forward(
        self,
        patterns: list[str],
        antipatterns: list[str],
        tool_names: list[str],
    ) -> dspy.Prediction:
        """
        Synthesize insight from multiple observations.

        Args:
            patterns: Successful patterns observed
            antipatterns: Failure patterns observed
            tool_names: Tools involved in observations

        Returns:
            Prediction with insight, category, implications
        """
        return self.synthesize(
            patterns=patterns,
            antipatterns=antipatterns,
            tool_names=tool_names,
        )


# =============================================================================
# Knowledge Consolidation Modules
# =============================================================================

class PatternConsolidator(dspy.Module):
    """Decides how to integrate new patterns into existing knowledge.

    This is critical for avoiding knowledge bloat and maintaining
    coherent, non-duplicated patterns. Uses ChainOfThought for
    careful analysis of pattern relationships.

    Relationship to other Consolidators:
        - PatternConsolidator: (THIS) DSPy module for merging individual patterns.
          Used for real-time pattern deduplication during learning.
        - IntelligentConsolidator: DSPy module for tiered knowledge generation.
          Used for creating token-aware knowledge tiers (quick/context/errors/raw).
        - CommandConsolidator: Orchestrator class for structural analysis.
          Used for batch processing command families and relationships.
    """

    def __init__(self):
        super().__init__()
        self.consolidate = dspy.ChainOfThought(ConsolidatePattern)

    def forward(
        self,
        new_pattern: dict,
        existing_patterns_for_tool: list[dict],
        related_patterns_other_tools: list[dict],
        triggering_intent: str,
    ) -> dspy.Prediction:
        """
        Decide how to integrate a new pattern.

        Args:
            new_pattern: Newly discovered pattern
            existing_patterns_for_tool: Current patterns for this tool
            related_patterns_other_tools: Patterns from related tools
            triggering_intent: Intent that led to discovery

        Returns:
            Prediction with action, target_pattern_id, merged_params,
            confidence_adjustment, workflow_link, rationale
        """
        return self.consolidate(
            new_pattern=new_pattern,
            existing_patterns_for_tool=existing_patterns_for_tool,
            related_patterns_other_tools=related_patterns_other_tools,
            triggering_intent=triggering_intent,
        )


class FeedbackComputer(dspy.Module):
    """Computes nuanced feedback for MAB updates.

    Transforms binary success/failure into semantic feedback with
    quality assessments and learning signals. This improves MAB
    learning by providing richer reward signals.
    """

    def __init__(self):
        super().__init__()
        # Use Predict here for speed - feedback computation happens frequently
        self.compute = dspy.Predict(SemanticFeedback)

    def forward(
        self,
        tool_name: str,
        params_used: dict,
        outcome: str,
        response_data: dict,
        original_intent: str,
        hypothesis_tested: str,
        execution_context: dict,
    ) -> dspy.Prediction:
        """
        Compute nuanced feedback for a tool execution.

        Args:
            tool_name: Tool that was executed
            params_used: Parameters used
            outcome: "success" or "failure"
            response_data: Tool response data
            original_intent: What we were trying to do
            hypothesis_tested: Hypothesis being tested
            execution_context: Context (geometry, session state)

        Returns:
            Prediction with reward_score, quality_assessment, learning_signal,
            pattern_strength, related_patterns_to_update
        """
        return self.compute(
            tool_name=tool_name,
            params_used=params_used,
            outcome=outcome,
            response_data=response_data,
            original_intent=original_intent,
            hypothesis_tested=hypothesis_tested,
            execution_context=execution_context,
        )


class WorkflowDetector(dspy.Module):
    """Detects multi-tool workflow sequences.

    Identifies when recent operations form a reusable workflow pattern
    that should be recorded for future use.
    """

    def __init__(self):
        super().__init__()
        self.detect = dspy.ChainOfThought(DetectWorkflow)

    def forward(
        self,
        recent_operations: list[dict],
        triggering_intent: str,
        existing_workflows: list[dict],
    ) -> dspy.Prediction:
        """
        Detect if recent operations form a workflow.

        Args:
            recent_operations: Recent successful operations
            triggering_intent: High-level goal
            existing_workflows: Known workflow patterns

        Returns:
            Prediction with is_workflow, workflow_name, workflow_steps,
            entry_conditions, matches_existing
        """
        return self.detect(
            recent_operations=recent_operations,
            triggering_intent=triggering_intent,
            existing_workflows=existing_workflows,
        )


# =============================================================================
# Execution Layer Modules
# =============================================================================

class ReasoningExecutor(dspy.Module):
    """Executes tools with explicit reasoning traces.

    Uses ChainOfThought to reason through the execution before
    generating parameters. This creates traceable reasoning that
    can be used for debugging and learning.
    """

    def __init__(self):
        super().__init__()
        self.execute = dspy.ChainOfThought(ExecuteWithReasoning)

    def forward(
        self,
        tool_name: str,
        objective: str,
        available_objects: list[str],
        constraints: list[str],
    ) -> dspy.Prediction:
        """
        Generate execution parameters with reasoning.

        Args:
            tool_name: MCP tool to execute
            objective: What we're trying to accomplish
            available_objects: Object IDs in scene
            constraints: Patterns/constraints to follow

        Returns:
            Prediction with reasoning, params, expected_result
        """
        return self.execute(
            tool_name=tool_name,
            objective=objective,
            available_objects=available_objects,
            constraints=constraints,
        )


class ResultVerifier(dspy.Module):
    """Verifies that operations succeeded as expected.

    Compares expected vs actual results to confirm success.
    Uses Predict for speed since this is called frequently.
    """

    def __init__(self):
        super().__init__()
        self.verify = dspy.Predict(VerifyResult)

    def forward(
        self,
        tool_name: str,
        params_used: dict,
        expected_result: str,
        api_response: dict,
        before_object_count: int,
        after_object_count: int,
    ) -> dspy.Prediction:
        """
        Verify an operation succeeded as expected.

        Args:
            tool_name: Tool that was called
            params_used: Parameters used
            expected_result: What we expected
            api_response: Actual response
            before_object_count: Objects before operation
            after_object_count: Objects after operation

        Returns:
            Prediction with success, confidence, observations, discrepancies
        """
        return self.verify(
            tool_name=tool_name,
            params_used=params_used,
            expected_result=expected_result,
            api_response=api_response,
            before_object_count=before_object_count,
            after_object_count=after_object_count,
        )


class ActionSelector(dspy.Module):
    """Selects next action during investigation.

    Works with MAB to balance exploration vs exploitation.
    Uses ChainOfThought to reason about action selection.
    """

    def __init__(self):
        super().__init__()
        self.select = dspy.ChainOfThought(SelectNextAction)

    def forward(
        self,
        current_objective: str,
        completed_steps: list[str],
        available_actions: list[dict],
        time_remaining: int,
    ) -> dspy.Prediction:
        """
        Select next action to take.

        Args:
            current_objective: Current goal
            completed_steps: Steps already taken
            available_actions: Possible actions with MAB scores
            time_remaining: Turns remaining

        Returns:
            Prediction with selected_action, rationale, is_exploration
        """
        return self.select(
            current_objective=current_objective,
            completed_steps=completed_steps,
            available_actions=available_actions,
            time_remaining=time_remaining,
        )


class DemonstrationExtractor(dspy.Module):
    """Extracts clean demonstrations from investigation traces.

    Used to create training data for DSPy optimization.
    """

    def __init__(self):
        super().__init__()
        self.extract = dspy.Predict(ExtractDemonstration)

    def forward(
        self,
        investigation_trace: list[dict],
        initial_objective: str,
        final_outcome: str,
    ) -> dspy.Prediction:
        """
        Extract demonstration from investigation trace.

        Args:
            investigation_trace: Full trace of investigation
            initial_objective: Original goal
            final_outcome: What was achieved

        Returns:
            Prediction with clean_example, key_insights, reusability_score
        """
        return self.extract(
            investigation_trace=investigation_trace,
            initial_objective=initial_objective,
            final_outcome=final_outcome,
        )


# =============================================================================
# Composite Modules
# =============================================================================

class InvestigationOrchestrator(dspy.Module):
    """Orchestrates a complete investigation from planning to verification.

    This is a higher-level module that composes multiple submodules
    for a complete investigation workflow.
    """

    def __init__(self):
        super().__init__()
        self.planner = InvestigationPlanner()
        self.diagnoser = FailureDiagnoser()
        self.executor = ReasoningExecutor()
        self.verifier = ResultVerifier()

    def forward(
        self,
        tool_name: str,
        tool_description: str,
        tool_schema: dict,
        known_patterns: list[str],
        known_antipatterns: list[str],
        available_geometry: list[str],
        available_objects: list[str],
    ) -> dict[str, Any]:
        """
        Orchestrate a complete tool investigation.

        This method:
        1. Plans the investigation
        2. Executes with reasoning
        3. Verifies results
        4. Diagnoses any failures

        Returns a dict with plan, execution, verification, and diagnosis results.
        """
        results = {}

        # Step 1: Plan the investigation
        plan = self.planner(
            tool_name=tool_name,
            tool_description=tool_description,
            known_patterns=known_patterns,
            known_antipatterns=known_antipatterns,
            available_geometry=available_geometry,
        )
        results["plan"] = plan

        # Step 2: For each hypothesis, try to execute
        for i, hypothesis in enumerate(plan.hypotheses[:3]):  # Limit to top 3
            test_seq = plan.test_sequence[i] if i < len(plan.test_sequence) else {}

            # Generate execution with reasoning
            execution = self.executor(
                tool_name=tool_name,
                objective=hypothesis,
                available_objects=available_objects,
                constraints=known_patterns + known_antipatterns,
            )
            results[f"execution_{i}"] = execution

        return results


# =============================================================================
# Command Learning Modules (for Rhino command syntax learning)
# =============================================================================

class CommandLearningPlanner(dspy.Module):
    """Plans input sequences to learn a Rhino command's syntax.

    Uses ChainOfThought to reason about what modes and options might exist
    and generate input sequences to systematically explore the command.

    This is the entry point for learning mode - it takes a command name
    and generates hypotheses + input sequences to try.
    """

    def __init__(self):
        super().__init__()
        self.plan = dspy.ChainOfThought(PlanCommandLearning)

    def forward(
        self,
        command_name: str,
        command_category: str,
        known_modes: list[str],
        known_options: list[str],
        related_knowledge: list[str],
        geometry_types_available: list[str],
    ) -> dspy.Prediction:
        """
        Generate a learning plan for a Rhino command.

        Args:
            command_name: The command to learn (e.g., '_-Loft')
            command_category: Category (Primitives, Curves, Surfaces, etc.)
            known_modes: Already-learned modes for this command
            known_options: Already-discovered option flags
            related_knowledge: Patterns from similar commands
            geometry_types_available: Geometry types available for testing

        Returns:
            Prediction with hypotheses, input_sequences, required_geometry,
            exploration_rationale
        """
        return self.plan(
            command_name=command_name,
            command_category=command_category,
            known_modes=known_modes,
            known_options=known_options,
            related_knowledge=related_knowledge,
            geometry_types_available=geometry_types_available,
        )


class CommandDialogueDiagnoser(dspy.Module):
    """Diagnoses failures in Rhino command dialogues.

    Uses ChainOfThought to analyze the sequence of prompts and inputs
    to understand what went wrong and suggest corrections.

    Critical for learning from mistakes during command exploration.
    """

    def __init__(self):
        super().__init__()
        self.diagnose = dspy.ChainOfThought(DiagnoseCommandDialogue)

    def forward(
        self,
        command_name: str,
        inputs_sent: list[str],
        dialogue_steps: list[dict],
        final_error: str,
        available_geometry: list[str],
    ) -> dspy.Prediction:
        """
        Diagnose a command dialogue failure.

        Args:
            command_name: The command that was being executed
            inputs_sent: The input sequence that was sent
            dialogue_steps: Full dialogue history
            final_error: Error message or unexpected result
            available_geometry: Geometry IDs that were available

        Returns:
            Prediction with error_category, root_cause, failed_at_step,
            corrected_inputs, new_gotcha
        """
        return self.diagnose(
            command_name=command_name,
            inputs_sent=inputs_sent,
            dialogue_steps=dialogue_steps,
            final_error=final_error,
            available_geometry=available_geometry,
        )


class CommandKnowledgeConsolidator(dspy.Module):
    """Consolidates new command learning with existing knowledge.

    Uses ChainOfThought to decide whether new observations should
    create a new mode, update an existing mode, add a gotcha, or be discarded.

    This prevents knowledge bloat and maintains coherent command documentation.
    """

    def __init__(self):
        super().__init__()
        self.consolidate = dspy.ChainOfThought(ConsolidateCommandKnowledge)

    def forward(
        self,
        command_name: str,
        new_observation: dict,
        existing_modes: dict,
        existing_gotchas: list[str],
    ) -> dspy.Prediction:
        """
        Decide how to integrate new command learning.

        Args:
            command_name: The command this knowledge is for
            new_observation: New observation {dialogue_steps, inputs_used, etc.}
            existing_modes: Already-known modes {mode_name: {syntax, ...}}
            existing_gotchas: Already-known gotchas

        Returns:
            Prediction with action, mode_name, merged_knowledge,
            new_options_discovered, rationale
        """
        return self.consolidate(
            command_name=command_name,
            new_observation=new_observation,
            existing_modes=existing_modes,
            existing_gotchas=existing_gotchas,
        )


class IntentResolver(dspy.Module):
    """Resolves user intent to the best Rhino command.

    Uses ChainOfThought to reason about which command and mode best
    accomplishes the user's goal, given available geometry and known commands.

    This is the entry point for execution mode - it takes a natural language
    intent and returns a command + mode + parameters.
    """

    def __init__(self):
        super().__init__()
        self.resolve = dspy.ChainOfThought(ResolveIntentToCommand)

    def forward(
        self,
        user_intent: str,
        available_geometry: list[dict],
        command_candidates: list[dict],
        recent_commands: list[str],
    ) -> dspy.Prediction:
        """
        Resolve a user intent to a specific command.

        Args:
            user_intent: Natural language intent (e.g., "create a sphere at origin")
            available_geometry: Geometry in scene [{id, type, description}, ...]
            command_candidates: Commands that might match
            recent_commands: Recently used commands for context

        Returns:
            Prediction with selected_command, selected_mode, parameter_values,
            geometry_to_use, confidence, rationale
        """
        return self.resolve(
            user_intent=user_intent,
            available_geometry=available_geometry,
            command_candidates=command_candidates,
            recent_commands=recent_commands,
        )


class SyntaxBuilder(dspy.Module):
    """Builds exact input sequences for Rhino command execution.

    Uses Predict (faster than ChainOfThought) to construct the precise
    input sequence from a mode template and parameter values.

    Called after IntentResolver to prepare the actual execution.
    """

    def __init__(self):
        super().__init__()
        # Use Predict for speed - this is a more mechanical transformation
        self.build = dspy.Predict(BuildCommandSyntax)

    def forward(
        self,
        command_name: str,
        mode: str,
        mode_syntax: str,
        parameter_values: dict,
        geometry_ids: dict,
        gotchas: list[str],
    ) -> dspy.Prediction:
        """
        Build the input sequence for command execution.

        Args:
            command_name: The command to execute
            mode: The mode to use
            mode_syntax: Syntax template for this mode
            parameter_values: Values to substitute
            geometry_ids: Available geometry IDs for selection
            gotchas: Known gotchas to avoid

        Returns:
            Prediction with input_sequence, full_command,
            pre_selection_commands, warnings
        """
        return self.build(
            command_name=command_name,
            mode=mode,
            mode_syntax=mode_syntax,
            parameter_values=parameter_values,
            geometry_ids=geometry_ids,
            gotchas=gotchas,
        )


# =============================================================================
# Grasshopper Modules
# =============================================================================

class GHIntentResolver(dspy.Module):
    """Resolves GH intents to component plans.

    Uses two passes:
    1. Select which components to create
    2. Plan wiring/values for that frozen component list

    Debug mode (ROOK_DSPY_COT=1): dspy.ChainOfThought with the full
    signatures including rationale. Use for debugging resolution quality
    or collecting training data for DSPy compilation.
    """

    def __init__(self):
        super().__init__()
        import os
        self._debug_cot = os.environ.get("ROOK_DSPY_COT", "").strip() in ("1", "true", "yes")
        if self._debug_cot:
            self.select_components = dspy.ChainOfThought(GHSelectComponents)
            self.plan_wiring = dspy.ChainOfThought(GHPlanComponentWiring)
        else:
            self.select_components = dspy.Predict(GHSelectComponentsFast)
            self.plan_wiring = dspy.Predict(GHPlanComponentWiringFast)

    def forward(
        self,
        user_intent: str,
        candidate_guids: list[str],
        tiered_knowledge: list[dict],
        canvas_state: list[dict],
    ) -> dspy.Prediction:
        """
        Resolve intent to component creation and wiring plan.

        Args:
            user_intent: What the user wants to create
            candidate_guids: GUIDs from sparse index lookup
            tiered_knowledge: Knowledge for each candidate
            canvas_state: Existing objects on canvas

        Returns:
            Prediction with components_to_create, wiring_plan, values_to_set, confidence.
            Also includes rationale when ROOK_DSPY_COT=1.
        """
        candidate_guids, tiered_knowledge = self._prepare_selector_inputs(
            user_intent=user_intent,
            candidate_guids=candidate_guids,
            tiered_knowledge=tiered_knowledge,
        )

        selection = self.select_components(
            user_intent=user_intent,
            candidate_guids=candidate_guids,
            tiered_knowledge=tiered_knowledge,
            canvas_state=canvas_state,
        )
        selection_rationale = self._get_rationale(selection)
        raw_selection = list(getattr(selection, "components_to_create", []) or [])
        components_to_create = self._apply_exact_mention_guardrail(
            user_intent=user_intent,
            components_to_create=raw_selection,
            candidate_guids=candidate_guids,
            tiered_knowledge=tiered_knowledge,
        )

        if not components_to_create:
            return dspy.Prediction(
                components_to_create=[],
                wiring_plan=[],
                values_to_set=[],
                confidence=self._coerce_confidence(getattr(selection, "confidence", None)),
                selection_confidence=self._coerce_confidence(getattr(selection, "confidence", None)),
                wiring_confidence=None,
                rationale=selection_rationale,
            )

        frozen_components = self._freeze_selected_components(components_to_create, tiered_knowledge)
        wiring = self.plan_wiring(
            user_intent=user_intent,
            selected_components=frozen_components,
            canvas_state=canvas_state,
        )
        wiring_rationale = self._get_rationale(wiring)

        # The quality gate should track component-selection confidence. Wiring can
        # fall back downstream, but omitted components cannot be recovered later.
        selection_confidence = self._coerce_confidence(getattr(selection, "confidence", None))

        return dspy.Prediction(
            components_to_create=components_to_create,
            wiring_plan=list(getattr(wiring, "wiring_plan", []) or []),
            values_to_set=list(getattr(wiring, "values_to_set", []) or []),
            confidence=selection_confidence,
            selection_confidence=selection_confidence,
            wiring_confidence=self._coerce_confidence(getattr(wiring, "confidence", None)),
            rationale=self._join_rationales(selection_rationale, wiring_rationale),
        )

    @staticmethod
    def _get_rationale(result: Any) -> str:
        rationale = getattr(result, "rationale", "")
        return rationale or ""

    @staticmethod
    def _coerce_confidence(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _join_rationales(selection_rationale: str, wiring_rationale: str) -> str:
        parts = []
        if selection_rationale:
            parts.append(f"Selection: {selection_rationale}")
        if wiring_rationale:
            parts.append(f"Wiring: {wiring_rationale}")
        return "\n".join(parts)

    @staticmethod
    def _freeze_selected_components(
        components_to_create: list[dict],
        tiered_knowledge: list[dict],
    ) -> list[dict]:
        """Enrich the selected list with candidate metadata without changing order."""
        knowledge_by_guid = {
            item.get("guid"): item
            for item in tiered_knowledge
            if isinstance(item, dict) and item.get("guid")
        }

        frozen_components = []
        for comp_plan in components_to_create:
            if not isinstance(comp_plan, dict):
                continue

            guid = comp_plan.get("guid")
            base = dict(knowledge_by_guid.get(guid, {}))
            frozen = {
                "guid": guid,
                "name": base.get("name", comp_plan.get("name", "")),
                "family": base.get("family", comp_plan.get("family", "")),
                "quick": base.get("quick", comp_plan.get("quick", "")),
                "params": base.get("params", comp_plan.get("params", {})),
                "deprecated": base.get("deprecated", comp_plan.get("deprecated", False)),
                "x": comp_plan.get("x", 0),
                "y": comp_plan.get("y", 0),
            }

            if "nickname" in comp_plan:
                frozen["nickname"] = comp_plan.get("nickname")
            if "values" in comp_plan:
                frozen["values"] = comp_plan.get("values")

            frozen_components.append(frozen)

        return frozen_components

    @classmethod
    def _prepare_selector_inputs(
        cls,
        user_intent: str,
        candidate_guids: list[str],
        tiered_knowledge: list[dict],
    ) -> tuple[list[str], list[dict]]:
        """Reduce noisy near-duplicate candidates before selection."""
        knowledge_by_guid = {
            item.get("guid"): item
            for item in tiered_knowledge
            if isinstance(item, dict) and item.get("guid")
        }

        concept_order: list[str] = []
        concept_candidates: dict[str, list[dict]] = {}
        deduped_guids: list[str] = []
        for guid in candidate_guids:
            candidate = knowledge_by_guid.get(guid)
            concept = cls._component_concept_key(candidate)
            if not concept:
                deduped_guids.append(guid)
                continue
            if concept not in concept_candidates:
                concept_candidates[concept] = []
                concept_order.append(concept)
            concept_candidates[concept].append(candidate)

        for concept in concept_order:
            preferred = cls._select_preferred_candidate_for_concept(
                concept=concept,
                candidates=concept_candidates[concept],
                user_intent=user_intent,
            )
            if preferred and preferred.get("guid"):
                deduped_guids.append(preferred.get("guid"))

        deduped_knowledge = [
            knowledge_by_guid[guid]
            for guid in deduped_guids
            if guid in knowledge_by_guid
        ]

        return deduped_guids, deduped_knowledge

    @classmethod
    def _apply_exact_mention_guardrail(
        cls,
        user_intent: str,
        components_to_create: list[dict],
        candidate_guids: list[str],
        tiered_knowledge: list[dict],
    ) -> list[dict]:
        """Ensure explicitly-mentioned component concepts are represented at least once."""
        if not components_to_create:
            components_to_create = []

        knowledge_by_guid = {
            item.get("guid"): item
            for item in tiered_knowledge
            if isinstance(item, dict) and item.get("guid")
        }
        ranked_candidates = [
            knowledge_by_guid[guid]
            for guid in candidate_guids
            if guid in knowledge_by_guid
        ]

        required_by_concept: dict[str, str] = {}
        intent_text = cls._normalize_component_text(user_intent)
        concept_candidates: dict[str, list[dict]] = {}
        ordered_concepts: list[str] = []
        for candidate in ranked_candidates:
            concept = cls._component_concept_key(candidate)
            if not concept:
                continue
            if concept not in concept_candidates:
                concept_candidates[concept] = []
                ordered_concepts.append(concept)
            concept_candidates[concept].append(candidate)

        for concept in ordered_concepts:
            explicit_matches = [
                candidate for candidate in concept_candidates[concept]
                if cls._candidate_full_name_in_text(candidate, intent_text)
            ]
            if explicit_matches:
                preferred = cls._select_preferred_candidate_for_concept(
                    concept=concept,
                    candidates=explicit_matches,
                    user_intent=user_intent,
                )
                if preferred and preferred.get("guid"):
                    required_by_concept[concept] = preferred.get("guid")

        intent_terms = cls._intent_component_terms(user_intent)
        for term in intent_terms:
            match = next(
                (
                    candidate for candidate in ranked_candidates
                    if cls._candidate_matches_term(candidate, term)
                ),
                None,
            )
            if match:
                concept = cls._component_concept_key(match)
                if concept and concept not in required_by_concept:
                    required_by_concept[concept] = match.get("guid")

        plan_buckets: dict[str, list[dict]] = {}
        leftovers: list[dict] = []
        for plan in components_to_create:
            if not isinstance(plan, dict):
                continue
            guid = plan.get("guid")
            if not guid:
                leftovers.append(plan)
                continue
            concept = cls._component_concept_key(knowledge_by_guid.get(guid) or plan)
            if not concept:
                # Drop hallucinated or dedup-elided GUIDs that no longer map to
                # the current candidate set. The guardrail will reinsert the
                # correct representative for explicitly required concepts.
                continue
            plan_buckets.setdefault(concept, []).append(plan)

        for concept, guid in required_by_concept.items():
            if concept not in plan_buckets:
                plan_buckets[concept] = [{"guid": guid}]
                continue
            normalized_plans = []
            for plan in plan_buckets[concept]:
                updated = dict(plan)
                updated["guid"] = guid
                normalized_plans.append(updated)
            plan_buckets[concept] = normalized_plans

        merged: list[dict] = []
        for concept in ordered_concepts:
            merged.extend(plan_buckets.pop(concept, []))

        for plans in plan_buckets.values():
            merged.extend(plans)
        merged.extend(leftovers)
        return merged

    @staticmethod
    def _intent_component_terms(user_intent: str) -> list[str]:
        terms = re.findall(r"[a-z0-9]+", user_intent.lower())
        stop_words = {
            "a", "an", "the", "with", "and", "or", "to", "it", "of", "from",
            "create", "make", "add", "use", "using", "height", "width", "length",
            "radius", "controlled", "control", "driven", "driving", "parametric",
        }
        ordered_terms: list[str] = []
        for term in terms:
            if term in stop_words or len(term) < 3:
                continue
            singular = term[:-1] if term.endswith("s") and not term.endswith("ss") and len(term) > 3 else term
            if singular not in ordered_terms:
                ordered_terms.append(singular)
        return ordered_terms

    @classmethod
    def _candidate_matches_term(cls, candidate: dict, term: str) -> bool:
        name_tokens = cls._candidate_name_tokens(candidate)
        if not name_tokens:
            return False
        if term == cls._component_concept_key(candidate):
            return True
        if term == "slider" and "slider" in name_tokens:
            return True
        return term in name_tokens

    @staticmethod
    def _normalize_component_text(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    @classmethod
    def _candidate_full_name_in_text(cls, candidate: dict, normalized_text: str) -> bool:
        candidate_name = cls._candidate_normalized_name(candidate)
        if not candidate_name:
            return False
        return re.search(rf"\b{re.escape(candidate_name)}\b", normalized_text) is not None

    @classmethod
    def _candidate_normalized_name(cls, candidate: dict | None) -> str:
        return " ".join(cls._candidate_name_tokens(candidate))

    @classmethod
    def _select_preferred_candidate_for_concept(
        cls,
        concept: str,
        candidates: list[dict],
        user_intent: str,
    ) -> dict | None:
        if not candidates:
            return None

        normalized_intent = cls._normalize_component_text(user_intent)
        explicit_matches = [
            candidate for candidate in candidates
            if cls._candidate_full_name_in_text(candidate, normalized_intent)
        ]
        pool = explicit_matches or candidates

        # C# modern-over-legacy preference. When the concept is
        # csharp_script and the intent does NOT explicitly cue legacy,
        # prefer the modern RhinoCode C# Script; on legacy cues, prefer
        # legacy. Runs before the generic sort_key so name-token
        # heuristics don't flip the signal. Scoped to csharp_script
        # only per the 2026-04-21 parked follow-up — Python preference
        # is not in scope for this PR.
        if concept == "csharp_script":
            # Cue against the normalized intent — _normalize_component_text
            # strips punctuation including ".", so ".NET" becomes "net"
            # (verified via probe 2026-04-21). Match against both "dotnet"
            # (preserved) and " net " (word-bounded, to avoid matching
            # substrings like "internet"/"network").
            legacy_cues_substring = ("legacy", "dotnet", "gh1")
            legacy_cues_word = (" net ",)
            padded = f" {normalized_intent} "
            wants_legacy = (
                any(cue in normalized_intent for cue in legacy_cues_substring)
                or any(cue in padded for cue in legacy_cues_word)
            )

            def _is_legacy(candidate: dict) -> bool:
                c_tokens = cls._candidate_name_tokens(candidate)
                return "legacy" in c_tokens or "dotnet" in c_tokens

            modern = [c for c in pool if not _is_legacy(c)]
            legacy = [c for c in pool if _is_legacy(c)]
            if wants_legacy and legacy:
                pool = legacy
            elif modern:
                pool = modern
            # else: fall through on empty-modern with no legacy cue —
            # existing sort_key handles the remaining pool as-is.

        # Python modern-over-legacy preference. Symmetric to the C#
        # branch above but scoped to python_script. Default to modern
        # Python 3; route to IronPython 2 only on explicit legacy cues.
        # Substring cues include "python2" (no-space spelling) and
        # "ipy"; word-bounded cues cover " python 2 " / " py2 " /
        # " iron python " to avoid collision with substrings like
        # "I have 2 python scripts" or similar. GhPython is not in
        # scope — see _component_concept_key docstring.
        if concept == "python_script":
            py_legacy_cues_substring = ("ironpython", "python2", "ipy", "legacy", "gh1")
            py_legacy_cues_word = (" python 2 ", " py2 ", " iron python ")
            padded = f" {normalized_intent} "
            py_wants_legacy = (
                any(cue in normalized_intent for cue in py_legacy_cues_substring)
                or any(cue in padded for cue in py_legacy_cues_word)
            )

            def _is_legacy_python(candidate: dict) -> bool:
                c_tokens = cls._candidate_name_tokens(candidate)
                return "ironpython" in c_tokens or "legacy" in c_tokens

            modern_py = [c for c in pool if not _is_legacy_python(c)]
            legacy_py = [c for c in pool if _is_legacy_python(c)]
            if py_wants_legacy and legacy_py:
                pool = legacy_py
            elif modern_py:
                pool = modern_py

        def sort_key(candidate: dict) -> tuple[int, int, int, int]:
            normalized_name = cls._candidate_normalized_name(candidate)
            tokens = cls._candidate_name_tokens(candidate)
            preferred_name = cls._preferred_generic_name_for_concept(concept)
            generic_penalty = 0 if normalized_name == preferred_name else 1
            specialized_tokens = {
                "3pt", "cnr", "tantan", "mesh", "along", "linear", "md",
            }
            modifier_penalty = sum(1 for token in tokens if token in specialized_tokens)
            return (generic_penalty, modifier_penalty, len(tokens), len(normalized_name))

        return min(pool, key=sort_key)

    @staticmethod
    def _preferred_generic_name_for_concept(concept: str) -> str:
        if concept == "slider":
            return "number slider"
        return concept

    @staticmethod
    def _candidate_name_tokens(candidate: dict | None) -> list[str]:
        if not isinstance(candidate, dict):
            return []
        return re.findall(r"[a-z0-9]+", (candidate.get("name") or "").lower())

    @classmethod
    def _component_concept_key(cls, candidate: dict | None) -> str:
        tokens = cls._candidate_name_tokens(candidate)
        if not tokens:
            return ""
        # Script-family unification: modern and legacy variants of the
        # same script language must share a concept bucket so
        # _select_preferred_candidate_for_concept can compare them as
        # alternatives. The default first-token logic below keys by
        # first regex token and never compares cross-variant names.
        #
        # C# (PR-86): RhinoCode "C# Script" vs GH1-legacy "DotNET C#
        #   Script (LEGACY)" unified under "csharp_script".
        # Python (Python-follow-up): RhinoCode "Python 3 Script" vs
        #   GH1-legacy "IronPython 2 Script" unified under
        #   "python_script". GhPython is intentionally NOT included —
        #   no component note exists for it today, so it never enters
        #   the candidate pool. Revisit only if a GhPython component
        #   note is added and its creation identity is settled.
        if "script" in tokens:
            looks_csharp = ("csharp" in tokens) or (
                "c" in tokens
                and "python" not in tokens
                and "vb" not in tokens
                and "ironpython" not in tokens
                and "ghpython" not in tokens
            )
            if looks_csharp:
                return "csharp_script"
            looks_python = ("python" in tokens) or ("ironpython" in tokens)
            if looks_python and "vb" not in tokens:
                return "python_script"
        if "slider" in tokens:
            return "slider"
        if "toggle" in tokens:
            return "toggle"
        return tokens[0]


class GHWiringExecutor(dspy.Module):
    """Builds tool call sequences for GH wiring.

    Uses Predict for speed since wiring is relatively deterministic
    once the plan is established.
    """

    def __init__(self):
        super().__init__()
        self.build = dspy.Predict(GHWiringBuilder)

    def forward(
        self,
        created_components: list[dict],
        wiring_plan: list[dict],
        values_to_set: list[dict],
        gotchas: list[str],
    ) -> dspy.Prediction:
        """
        Build tool call sequence for wiring.

        Args:
            created_components: Components that were created
            wiring_plan: Connections to make
            values_to_set: Initial values
            gotchas: Warnings to consider

        Returns:
            Prediction with tool_calls, execution_notes
        """
        return self.build(
            created_components=created_components,
            wiring_plan=wiring_plan,
            values_to_set=values_to_set,
            gotchas=gotchas,
        )


class GHCanvasAnalyzer(dspy.Module):
    """Analyzes GH canvas state.

    Uses ChainOfThought for thoughtful analysis of complex definitions.
    """

    def __init__(self):
        super().__init__()
        self.analyze = dspy.ChainOfThought(GHAnalyzeCanvas)

    def forward(
        self,
        query: str,
        canvas_objects: list[dict],
        selected_objects: list[str],
    ) -> dspy.Prediction:
        """
        Analyze canvas and answer query.

        Args:
            query: Question about the canvas
            canvas_objects: Objects with connections
            selected_objects: Currently selected GUIDs

        Returns:
            Prediction with analysis, data_flow, suggestions
        """
        return self.analyze(
            query=query,
            canvas_objects=canvas_objects,
            selected_objects=selected_objects,
        )


# =============================================================================
# Pattern Memory Modules (Phase 2 Meta-Learning)
# =============================================================================

class PatternMetadataExtractor(dspy.Module):
    """Extract metadata from pattern descriptions for storage.

    Uses ChainOfThought to reason through the solution and extract
    structured metadata including triggers, symptoms, and tags.

    This is the A-MEM Ps1 (Note Construction) equivalent.
    Called when adding a new pattern to the store.
    """

    def __init__(self):
        super().__init__()
        self.extract = dspy.ChainOfThought(ExtractPatternMetadata)

    def forward(
        self,
        solution_description: str,
        session_context: str = "",
        components_involved: list[str] = None,
    ) -> dspy.Prediction:
        """
        Extract structured metadata from a solution description.

        Args:
            solution_description: Free-form description of what was learned
            session_context: Context from the discovery session (optional)
            components_involved: GH components used in the solution

        Returns:
            Prediction with solution_brief, solution_principle, trigger_intents,
            trigger_symptoms, tags, preconditions
        """
        return self.extract(
            solution_description=solution_description,
            session_context=session_context,
            components_involved=components_involved or [],
        )


class PatternLinker(dspy.Module):
    """Decide pattern links using ChainOfThought reasoning.

    Analyzes a new pattern against candidate neighbors to determine
    which patterns should be linked together.

    This is the A-MEM Ps2 (Link Generation) equivalent.
    Called after metadata extraction to build the knowledge graph.
    """

    def __init__(self):
        super().__init__()
        self.decide = dspy.ChainOfThought(DecidePatternLinks)

    def forward(
        self,
        new_pattern_summary: str,
        new_pattern_tags: list[str],
        candidate_patterns: list[dict],
    ) -> dspy.Prediction:
        """
        Decide which patterns to link to the new pattern.

        Args:
            new_pattern_summary: Summary of the new pattern (name + brief)
            new_pattern_tags: Tags of the new pattern
            candidate_patterns: Potential neighbors [{id, name, brief, tags}, ...]

        Returns:
            Prediction with links_to_create, link_rationales, updated_tags
        """
        return self.decide(
            new_pattern_summary=new_pattern_summary,
            new_pattern_tags=new_pattern_tags,
            candidate_patterns=candidate_patterns,
        )


class NeighborEvolver(dspy.Module):
    """Evolve neighbor patterns when new knowledge arrives.

    Updates existing patterns based on newly added related knowledge.
    This enables bidirectional evolution - new patterns enrich old ones.

    This is the A-MEM Ps3 (Memory Evolution) equivalent.
    Called after linking to propagate knowledge to neighbors.
    """

    def __init__(self):
        super().__init__()
        self.evolve = dspy.ChainOfThought(EvolveNeighborPatterns)

    def forward(
        self,
        new_pattern: dict,
        neighbor_patterns: list[dict],
    ) -> dspy.Prediction:
        """
        Determine how to evolve neighbor patterns.

        Args:
            new_pattern: The newly added pattern {id, name, brief, principle, tags}
            neighbor_patterns: Neighbors to consider [{id, name, brief, tags, context}, ...]

        Returns:
            Prediction with should_evolve, neighbor_updates, evolution_summary
        """
        return self.evolve(
            new_pattern=new_pattern,
            neighbor_patterns=neighbor_patterns,
        )


# =============================================================================
# Module Factory
# =============================================================================

# =============================================================================
# Phase 5: Reflection Modules
# =============================================================================

class ReflectionAnalyzer(dspy.Module):
    """Analyze struggle sequences to extract learnable patterns.

    Uses ChainOfThought to reason through the 5 reflection questions:
    1. Was this hard-won?
    2. What was the breakthrough?
    3. Is this generalizable?
    4. How would future Claude recognize this?
    5. What constraints apply?

    Outputs a complete ReflectionResult ready for pattern building.
    """

    def __init__(self):
        super().__init__()
        self.analyze = dspy.ChainOfThought(AnalyzeStruggleSequence)

    def forward(
        self,
        failures_summary: str,
        success_summary: str,
        action_type: str,
        intent: str,
        error_messages: list[str],
        failure_params: list[dict],
        success_params: dict,
    ) -> dspy.Prediction:
        """Analyze a struggle sequence.

        Args:
            failures_summary: Summary of failed attempts
            success_summary: Summary of successful attempt
            action_type: The GH action being used
            intent: The intent (for execute_intent)
            error_messages: Unique errors from failures
            failure_params: Params from failed attempts
            success_params: Params from success

        Returns:
            Prediction with all ReflectionResult fields
        """
        result = self.analyze(
            failures_summary=failures_summary,
            success_summary=success_summary,
            action_type=action_type,
            intent=intent or "",
            error_messages=error_messages,
            failure_params=failure_params,
            success_params=success_params,
        )

        logger.debug(
            f"Reflection analysis: recommendation={result.recommendation}, "
            f"generalizable={result.is_generalizable}"
        )

        return result


# =============================================================================
# Module Factory
# =============================================================================

def create_all_modules() -> dict[str, dspy.Module]:
    """Create instances of all DSPy modules.

    Returns a dictionary of module name -> module instance.
    Useful for optimization and testing.
    """
    return {
        # Strategic Layer (MCP tools)
        "session_orienter": SessionOrienter(),
        "investigation_planner": InvestigationPlanner(),
        "failure_diagnoser": FailureDiagnoser(),
        "hypothesis_generator": HypothesisGenerator(),
        "insight_synthesizer": InsightSynthesizer(),
        # Knowledge Consolidation (MCP tools)
        "pattern_consolidator": PatternConsolidator(),
        "feedback_computer": FeedbackComputer(),
        "workflow_detector": WorkflowDetector(),
        # Execution Layer (MCP tools)
        "reasoning_executor": ReasoningExecutor(),
        "result_verifier": ResultVerifier(),
        "action_selector": ActionSelector(),
        "demonstration_extractor": DemonstrationExtractor(),
        # Composite (MCP tools)
        "investigation_orchestrator": InvestigationOrchestrator(),
        # Command Learning (Rhino commands)
        "command_learning_planner": CommandLearningPlanner(),
        "command_dialogue_diagnoser": CommandDialogueDiagnoser(),
        "command_knowledge_consolidator": CommandKnowledgeConsolidator(),
        "intent_resolver": IntentResolver(),
        "syntax_builder": SyntaxBuilder(),
        # Grasshopper (GH canvas)
        "gh_intent_resolver": GHIntentResolver(),
        "gh_wiring_executor": GHWiringExecutor(),
        "gh_canvas_analyzer": GHCanvasAnalyzer(),
        # Pattern Memory (Phase 2 Meta-Learning)
        "pattern_metadata_extractor": PatternMetadataExtractor(),
        "pattern_linker": PatternLinker(),
        "neighbor_evolver": NeighborEvolver(),
        # Reflection (Phase 5 Meta-Learning)
        "reflection_analyzer": ReflectionAnalyzer(),
    }
