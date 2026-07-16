"""DSPy signatures for Rook learning system.

Signatures define the input/output behavior of AI modules declaratively.
They are automatically optimized by DSPy's compilers (BootstrapFewShot, MIPROv2).

Architecture:
- Strategic Layer: High-level reasoning (orientation, planning, diagnosis)
- Knowledge Consolidation Layer: Pattern management and feedback computation
- Execution Layer: Tool execution with reasoning traces
"""

import dspy
from typing import Literal


# =============================================================================
# Strategic Layer Signatures
# =============================================================================

class OrientSession(dspy.Signature):
    """Analyze knowledge graph state and determine session priorities.

    You are analyzing the current state of a knowledge cultivation system
    for Rhino 3D tools. Determine what should be investigated next based on:
    - Coverage gaps (uncovered tools)
    - Open knowledge gaps (known unknowns)
    - Previous session handoffs
    - Recent failures that might be retryable
    """

    # Inputs
    coverage_percentage: float = dspy.InputField(
        desc="Current tool coverage percentage (0-100)"
    )
    uncovered_tools: list[str] = dspy.InputField(
        desc="List of tools without documented patterns"
    )
    open_gaps: list[str] = dspy.InputField(
        desc="Knowledge gaps that need investigation"
    )
    last_session_priorities: list[str] = dspy.InputField(
        desc="Priorities from the previous session handoff"
    )
    recent_failures: list[str] = dspy.InputField(
        desc="Recent investigation failures to avoid or retry"
    )

    # Outputs
    primary_focus: str = dspy.OutputField(
        desc="Main area to focus on this session"
    )
    investigation_targets: list[str] = dspy.OutputField(
        desc="Ordered list of specific tools or gaps to investigate"
    )
    rationale: str = dspy.OutputField(
        desc="Brief explanation of why these priorities were chosen"
    )


class PlanInvestigation(dspy.Signature):
    """Plan how to investigate an unknown tool or knowledge gap.

    Generate hypotheses about how the tool works and design experiments
    to test them. Consider what geometry might be needed and what
    parameters to try.
    """

    # Inputs
    tool_name: str = dspy.InputField(
        desc="The MCP tool to investigate (e.g., 'rhino_loft')"
    )
    tool_description: str = dspy.InputField(
        desc="Tool's documentation/description"
    )
    known_patterns: list[str] = dspy.InputField(
        desc="Existing patterns for this tool (may be empty)"
    )
    known_antipatterns: list[str] = dspy.InputField(
        desc="Known failure modes for this tool"
    )
    available_geometry: list[str] = dspy.InputField(
        desc="Geometry types available in context (curves, breps, meshes)"
    )

    # Outputs
    hypotheses: list[str] = dspy.OutputField(
        desc="3-5 hypotheses about how the tool works"
    )
    required_geometry: list[str] = dspy.OutputField(
        desc="Geometry that needs to be created for testing"
    )
    test_sequence: list[dict] = dspy.OutputField(
        desc="Ordered list of experiments with parameters to try"
    )
    expected_outcomes: list[str] = dspy.OutputField(
        desc="What success looks like for each hypothesis"
    )


class DiagnoseFailure(dspy.Signature):
    """Diagnose why a tool call failed and suggest fixes.

    Analyze the error message, parameters used, and context to determine
    the root cause and propose specific fixes to try.
    """

    # Inputs
    tool_name: str = dspy.InputField(
        desc="The tool that failed"
    )
    params_used: dict = dspy.InputField(
        desc="Parameters that were passed to the tool"
    )
    error_message: str = dspy.InputField(
        desc="The error message returned"
    )
    available_geometry: list[str] = dspy.InputField(
        desc="Geometry IDs available in context"
    )
    tool_schema: dict = dspy.InputField(
        desc="Tool's parameter schema (required params, types, etc.)"
    )

    # Outputs
    error_category: Literal[
        "missing_param", "invalid_param", "wrong_type",
        "precondition_failed", "geometry_error", "unknown"
    ] = dspy.OutputField(
        desc="Category of error"
    )
    root_cause: str = dspy.OutputField(
        desc="Specific explanation of what went wrong"
    )
    fix_suggestions: list[dict] = dspy.OutputField(
        desc="Concrete parameter changes to try, ordered by likelihood"
    )
    missing_preconditions: list[str] = dspy.OutputField(
        desc="Things that need to be set up before retrying"
    )


class GenerateHypotheses(dspy.Signature):
    """Generate hypotheses about tool behavior given partial information.

    Used when investigating a gap - generate testable hypotheses based on
    the gap description and any existing knowledge.
    """

    # Inputs
    gap_description: str = dspy.InputField(
        desc="What we don't understand about the tool"
    )
    tool_name: str = dspy.InputField(
        desc="The tool this gap relates to"
    )
    related_patterns: list[str] = dspy.InputField(
        desc="Patterns for similar tools that might inform hypotheses"
    )
    failed_attempts: list[str] = dspy.InputField(
        desc="Things already tried that didn't work"
    )

    # Outputs
    hypotheses: list[str] = dspy.OutputField(
        desc="Testable hypotheses about how to resolve the gap"
    )
    test_approach: str = dspy.OutputField(
        desc="Recommended approach for testing these hypotheses"
    )


class SynthesizeInsight(dspy.Signature):
    """Synthesize a higher-level insight from multiple observations.

    Look across patterns and antipatterns to identify meta-knowledge
    about how tools relate or common patterns in their behavior.
    """

    # Inputs
    patterns: list[str] = dspy.InputField(
        desc="Successful patterns observed"
    )
    antipatterns: list[str] = dspy.InputField(
        desc="Failure patterns observed"
    )
    tool_names: list[str] = dspy.InputField(
        desc="Tools involved in these observations"
    )

    # Outputs
    insight: str = dspy.OutputField(
        desc="The higher-level observation"
    )
    category: Literal[
        "tool_relationship", "parameter_pattern", "workflow_pattern",
        "error_pattern", "performance", "edge_case"
    ] = dspy.OutputField(
        desc="Category of insight"
    )
    implications: list[str] = dspy.OutputField(
        desc="What this means for future investigations"
    )


# =============================================================================
# Knowledge Consolidation Signatures
# =============================================================================

class ConsolidatePattern(dspy.Signature):
    """Decide how to integrate a newly discovered pattern into existing knowledge.

    This is critical because we currently just add everything without reasoning
    about relationships to existing patterns. This signature enables:
    - Recognizing variants of existing patterns
    - Merging similar patterns to avoid duplication
    - Detecting workflow relationships between tools
    """

    # Inputs
    new_pattern: dict = dspy.InputField(
        desc="The newly discovered pattern {tool, params, note, confidence}"
    )
    existing_patterns_for_tool: list[dict] = dspy.InputField(
        desc="All existing patterns for this tool"
    )
    related_patterns_other_tools: list[dict] = dspy.InputField(
        desc="Patterns from related tools (e.g., rhino_create patterns when consolidating rhino_transform)"
    )
    triggering_intent: str = dspy.InputField(
        desc="The original intent that led to this discovery"
    )

    # Outputs
    action: Literal["create_new", "merge_with", "update_existing", "discard"] = dspy.OutputField(
        desc="What to do with this pattern"
    )
    target_pattern_id: str = dspy.OutputField(
        desc="If merge/update, which existing pattern to modify (empty string if create_new or discard)"
    )
    merged_params: dict = dspy.OutputField(
        desc="If merging, the combined parameter template (empty dict if not merging)"
    )
    confidence_adjustment: float = dspy.OutputField(
        desc="How much to adjust confidence (-1.0 to 1.0)"
    )
    workflow_link: dict = dspy.OutputField(
        desc="If this pattern connects to others: {predecessor_tool, successor_tool, relationship}"
    )
    rationale: str = dspy.OutputField(
        desc="Explanation of the consolidation decision"
    )


class SemanticFeedback(dspy.Signature):
    """Compute nuanced feedback for MAB updates beyond binary success/failure.

    Current system does: reward = 1 if success else 0
    This enables: reward = contextual_score based on WHY it succeeded/failed

    This feeds into MAB partial_fit() for more informative updates.
    """

    # Inputs
    tool_name: str = dspy.InputField(
        desc="Name of the tool that was executed"
    )
    params_used: dict = dspy.InputField(
        desc="Parameters that were passed to the tool"
    )
    outcome: Literal["success", "failure"] = dspy.InputField(
        desc="Binary outcome of the execution"
    )
    response_data: dict = dspy.InputField(
        desc="The actual response from the tool"
    )
    original_intent: str = dspy.InputField(
        desc="What the user/agent was trying to accomplish"
    )
    hypothesis_tested: str = dspy.InputField(
        desc="What hypothesis this execution was testing"
    )
    execution_context: dict = dspy.InputField(
        desc="Available geometry, session progress, etc."
    )

    # Outputs
    reward_score: float = dspy.OutputField(
        desc="Nuanced reward 0.0-1.0 (not just binary)"
    )
    quality_assessment: Literal[
        "optimal", "suboptimal_but_correct", "correct_but_fragile",
        "partial_success", "near_miss", "fundamental_failure"
    ] = dspy.OutputField(
        desc="Qualitative assessment of the outcome"
    )
    learning_signal: str = dspy.OutputField(
        desc="What should be learned from this outcome"
    )
    pattern_strength: Literal["strong", "moderate", "weak", "negative"] = dspy.OutputField(
        desc="How strongly this should influence the pattern"
    )
    related_patterns_to_update: list[str] = dspy.OutputField(
        desc="Other pattern IDs that should also receive feedback"
    )


class DetectWorkflow(dspy.Signature):
    """Detect when patterns across tools form a workflow sequence.

    Our system stores patterns per-tool, but doesn't capture multi-step
    workflows like: create_curves -> rhino_loft -> rhino_boolean

    This signature identifies when recent successful operations form
    a reusable workflow that should be recorded.
    """

    # Inputs
    recent_operations: list[dict] = dspy.InputField(
        desc="Last N successful operations [{tool, params, intent, timestamp}]"
    )
    triggering_intent: str = dspy.InputField(
        desc="The high-level goal that drove these operations"
    )
    existing_workflows: list[dict] = dspy.InputField(
        desc="Already-known workflow patterns"
    )

    # Outputs
    is_workflow: bool = dspy.OutputField(
        desc="Whether these operations form a coherent workflow"
    )
    workflow_name: str = dspy.OutputField(
        desc="Descriptive name for the workflow (empty if not a workflow)"
    )
    workflow_steps: list[dict] = dspy.OutputField(
        desc="Ordered steps with tool, required_params, optional_params"
    )
    entry_conditions: list[str] = dspy.OutputField(
        desc="What must be true to start this workflow"
    )
    matches_existing: str = dspy.OutputField(
        desc="ID of existing workflow this matches (empty if new)"
    )


# =============================================================================
# Execution Layer Signatures
# =============================================================================

class ExecuteWithReasoning(dspy.Signature):
    """Execute a tool with step-by-step reasoning about the approach.

    Think through what the tool should do, verify preconditions,
    then decide on parameters.
    """

    # Inputs
    tool_name: str = dspy.InputField(
        desc="Name of the MCP tool to execute"
    )
    objective: str = dspy.InputField(
        desc="What we're trying to accomplish"
    )
    available_objects: list[str] = dspy.InputField(
        desc="Object IDs available in scene"
    )
    constraints: list[str] = dspy.InputField(
        desc="Known constraints or patterns to follow"
    )

    # Outputs
    reasoning: str = dspy.OutputField(
        desc="Step-by-step reasoning about the approach"
    )
    params: dict = dspy.OutputField(
        desc="Parameters to use for the tool call"
    )
    expected_result: str = dspy.OutputField(
        desc="What we expect to happen"
    )


class VerifyResult(dspy.Signature):
    """Verify that a tool operation succeeded as expected.

    Compare before and after state to confirm the operation worked.
    """

    # Inputs
    tool_name: str = dspy.InputField(
        desc="Name of the tool that was called"
    )
    params_used: dict = dspy.InputField(
        desc="Parameters that were passed"
    )
    expected_result: str = dspy.InputField(
        desc="What we expected to happen"
    )
    api_response: dict = dspy.InputField(
        desc="Response from the tool call"
    )
    before_object_count: int = dspy.InputField(
        desc="Number of objects before the operation"
    )
    after_object_count: int = dspy.InputField(
        desc="Number of objects after the operation"
    )

    # Outputs
    success: bool = dspy.OutputField(
        desc="Whether the operation succeeded as expected"
    )
    confidence: float = dspy.OutputField(
        desc="Confidence in the verification (0.0-1.0)"
    )
    observations: str = dspy.OutputField(
        desc="What was observed about the result"
    )
    discrepancies: list[str] = dspy.OutputField(
        desc="Any differences from expected behavior"
    )


class SelectNextAction(dspy.Signature):
    """Select the next action to take during an investigation.

    Given the current state and available options, decide what to do next.
    This works with MAB to balance exploration vs exploitation.
    """

    # Inputs
    current_objective: str = dspy.InputField(
        desc="What we're trying to accomplish"
    )
    completed_steps: list[str] = dspy.InputField(
        desc="Steps already taken in this investigation"
    )
    available_actions: list[dict] = dspy.InputField(
        desc="Actions that could be taken next [{name, description, mab_score}]"
    )
    time_remaining: int = dspy.InputField(
        desc="Approximate turns remaining in this session"
    )

    # Outputs
    selected_action: str = dspy.OutputField(
        desc="Name of the action to take"
    )
    rationale: str = dspy.OutputField(
        desc="Why this action was selected"
    )
    is_exploration: bool = dspy.OutputField(
        desc="Whether this is exploratory (vs. exploitative)"
    )


# =============================================================================
# Command Learning Signatures (for Rhino command syntax learning)
# =============================================================================

class PlanCommandLearning(dspy.Signature):
    """Plan what input sequences to try for learning a Rhino command's syntax.

    Generate hypotheses about what modes and options exist, and design
    input sequences to systematically explore the command's dialogue.

    Example:
        command_name: "_-Loft"
        command_category: "Surfaces"
        -> hypotheses: ["Has closed option", "Supports multiple curves", ...]
        -> input_sequences: [["_SelID ...", ""], ["_Closed", "_SelID ...", ""], ...]
    """

    # Inputs
    command_name: str = dspy.InputField(
        desc="The Rhino command to learn (e.g., '_-Loft', '_-Box')"
    )
    command_category: str = dspy.InputField(
        desc="Category from roadmap (Primitives, Curves, Surfaces, Transforms, etc.)"
    )
    known_modes: list[str] = dspy.InputField(
        desc="Modes already learned for this command (may be empty)"
    )
    known_options: list[str] = dspy.InputField(
        desc="Option flags already discovered (e.g., '_Center', '_Diameter')"
    )
    related_knowledge: list[str] = dspy.InputField(
        desc="Patterns from similar commands that might inform learning"
    )
    geometry_types_available: list[str] = dspy.InputField(
        desc="Geometry types available for testing (curve, brep, mesh, etc.)"
    )

    # Outputs
    hypotheses: list[str] = dspy.OutputField(
        desc="3-5 hypotheses about undiscovered modes/options"
    )
    input_sequences: list[list[str]] = dspy.OutputField(
        desc="Ordered input sequences to try, e.g., [['0,0,0', '10,10,0', '5'], ['_Center', '5,5,0', '10']]"
    )
    required_geometry: list[str] = dspy.OutputField(
        desc="Geometry types that must be created before testing (e.g., ['curve', 'curve'] for Loft)"
    )
    exploration_rationale: str = dspy.OutputField(
        desc="Why these sequences will help discover new knowledge"
    )


class DiagnoseCommandDialogue(dspy.Signature):
    """Diagnose why a Rhino command dialogue failed or produced unexpected results.

    Analyze the sequence of prompts and inputs to understand what went wrong
    and suggest corrections.

    Example:
        command_name: "_-Loft"
        inputs_sent: ["_SelID abc123", ""]
        dialogue_steps: [{"prompt": "Select curves to loft", "input": "_SelID abc123"}, ...]
        final_error: "Unable to loft. Curves must be selected."
        -> root_cause: "Selection did not work - curve ID may be invalid"
        -> corrected_inputs: ["_SelLast", ""]
    """

    # Inputs
    command_name: str = dspy.InputField(
        desc="The command that was being executed"
    )
    inputs_sent: list[str] = dspy.InputField(
        desc="The input sequence that was sent"
    )
    dialogue_steps: list[dict] = dspy.InputField(
        desc="Full dialogue history [{prompt, options, input, result}, ...]"
    )
    final_error: str = dspy.InputField(
        desc="Error message or unexpected result description"
    )
    available_geometry: list[str] = dspy.InputField(
        desc="Geometry IDs that were available"
    )

    # Outputs
    error_category: Literal[
        "invalid_input", "wrong_sequence", "missing_geometry", "missing_option",
        "option_conflict", "geometry_mismatch", "timeout", "unknown"
    ] = dspy.OutputField(
        desc="Category of the dialogue failure"
    )
    root_cause: str = dspy.OutputField(
        desc="Specific explanation of what went wrong in the dialogue"
    )
    failed_at_step: int = dspy.OutputField(
        desc="Which step (0-indexed) in the dialogue caused the failure"
    )
    corrected_inputs: list[str] = dspy.OutputField(
        desc="Fixed input sequence to try"
    )
    new_gotcha: str = dspy.OutputField(
        desc="Pattern to record as a gotcha (empty if not applicable)"
    )


class ConsolidateCommandKnowledge(dspy.Signature):
    """Decide how to integrate new command learning with existing knowledge.

    When we learn something new about a command, decide whether to:
    - Add it as a new mode
    - Update an existing mode
    - Add a new gotcha
    - Discard (if duplicate or unreliable)

    Example:
        command_name: "_-Box"
        new_observation: {dialogue, inputs, result}
        existing_modes: {"default": {...}, "center": {...}}
        -> action: "add_mode"
        -> mode_name: "diagonal"
        -> merged_knowledge: {syntax, dialogue, example, ...}
    """

    # Inputs
    command_name: str = dspy.InputField(
        desc="The command this knowledge is for"
    )
    new_observation: dict = dspy.InputField(
        desc="The new observation {dialogue_steps, inputs_used, objects_created, success}"
    )
    existing_modes: dict = dspy.InputField(
        desc="Already-known modes for this command {mode_name: {syntax, dialogue, ...}}"
    )
    existing_gotchas: list[str] = dspy.InputField(
        desc="Already-known gotchas for this command"
    )

    # Outputs
    action: Literal["add_mode", "update_mode", "add_gotcha", "add_option", "discard"] = dspy.OutputField(
        desc="What to do with this observation"
    )
    mode_name: str = dspy.OutputField(
        desc="Name of the mode to add/update (empty if not applicable)"
    )
    merged_knowledge: dict = dspy.OutputField(
        desc="The consolidated knowledge to store {syntax, dialogue, example, description}"
    )
    new_options_discovered: list[str] = dspy.OutputField(
        desc="Any new option flags discovered during this observation"
    )
    rationale: str = dspy.OutputField(
        desc="Explanation of the consolidation decision"
    )


class ResolveIntentToCommand(dspy.Signature):
    """Select the best Rhino command to accomplish a user's intent.

    Given a natural language intent and available geometry, select the
    most appropriate command and mode from known commands.

    Example:
        user_intent: "create a sphere at origin with radius 5"
        available_geometry: []
        command_candidates: [{command: "-Sphere", modes: {...}}, ...]
        -> selected_command: "_-Sphere"
        -> selected_mode: "default"
        -> parameter_values: {"center": "0,0,0", "radius": "5"}
    """

    # Inputs
    user_intent: str = dspy.InputField(
        desc="Natural language description of what the user wants to do"
    )
    available_geometry: list[dict] = dspy.InputField(
        desc="Geometry available in scene [{id, type, description}, ...]"
    )
    command_candidates: list[dict] = dspy.InputField(
        desc="Commands that might match [{command, modes, description}, ...]"
    )
    recent_commands: list[str] = dspy.InputField(
        desc="Recently used commands (for context)"
    )

    # Outputs
    selected_command: str = dspy.OutputField(
        desc="The command to use (e.g., '_-Sphere')"
    )
    selected_mode: str = dspy.OutputField(
        desc="Which mode of the command to use (e.g., 'default', 'diameter')"
    )
    parameter_values: dict = dspy.OutputField(
        desc="Values to use for parameters {param_name: value}"
    )
    geometry_to_use: list[str] = dspy.OutputField(
        desc="IDs of geometry to select/use (empty if creating new)"
    )
    confidence: float = dspy.OutputField(
        desc="Confidence in this selection (0.0-1.0)"
    )
    rationale: str = dspy.OutputField(
        desc="Why this command/mode was selected"
    )


class BuildCommandSyntax(dspy.Signature):
    """Build the exact input sequence for executing a Rhino command.

    Given a command, mode, and parameter values, construct the precise
    input sequence to send through the command dialogue.

    IMPORTANT: Always check the gotchas parameter for command-specific rules
    that affect how parameters should be formatted. Gotchas contain critical
    information about parameter ordering, coordinate handling, and common mistakes.

    Example:
        command_name: "_-Sphere"
        mode: "diameter"
        mode_syntax: "_-Sphere _Diameter <point1> <point2>"
        parameter_values: {"point1": "0,0,0", "point2": "10,0,0"}
        gotchas: ["Points must be different positions"]
        -> input_sequence: ["_Diameter", "0,0,0", "10,0,0"]
        -> full_command: "_-Sphere _Diameter 0,0,0 10,0,0"
    """

    # Inputs
    command_name: str = dspy.InputField(
        desc="The command to execute (e.g., '_-Sphere')"
    )
    mode: str = dspy.InputField(
        desc="The mode to use (e.g., 'default', 'diameter')"
    )
    mode_syntax: str = dspy.InputField(
        desc="Syntax template for this mode (e.g., '_-Sphere _Diameter <point1> <point2>')"
    )
    parameter_values: dict = dspy.InputField(
        desc="Values to substitute {param_name: value}"
    )
    geometry_ids: dict = dspy.InputField(
        desc="Available geometry IDs for selection {type: id}"
    )
    gotchas: list[str] = dspy.InputField(
        desc="CRITICAL rules that MUST be followed when building syntax. These contain command-specific parameter formatting rules, coordinate requirements, and constraints. Read carefully and apply to output."
    )

    # Outputs
    input_sequence: list[str] = dspy.OutputField(
        desc="Ordered inputs to send to the command dialogue, following gotcha rules"
    )
    full_command: str = dspy.OutputField(
        desc="Complete command string built by applying gotcha rules to mode_syntax template"
    )
    pre_selection_commands: list[str] = dspy.OutputField(
        desc="Commands to run before main command (e.g., selection)"
    )
    warnings: list[str] = dspy.OutputField(
        desc="Any gotcha rules that were applied or potential issues"
    )


# =============================================================================
# Training Data Generation Signatures
# =============================================================================

class ExtractDemonstration(dspy.Signature):
    """Extract a clean demonstration from a successful investigation trace.

    Convert a raw investigation trace into a reusable training example
    for DSPy optimization.
    """

    # Inputs
    investigation_trace: list[dict] = dspy.InputField(
        desc="Full trace of the investigation [{step, tool, params, result}]"
    )
    initial_objective: str = dspy.InputField(
        desc="What the investigation set out to accomplish"
    )
    final_outcome: str = dspy.InputField(
        desc="What was ultimately achieved"
    )

    # Outputs
    clean_example: dict = dspy.OutputField(
        desc="Cleaned demonstration with clear inputs and outputs"
    )
    key_insights: list[str] = dspy.OutputField(
        desc="Most important learnings from this investigation"
    )
    reusability_score: float = dspy.OutputField(
        desc="How likely this example is to generalize (0.0-1.0)"
    )


# =============================================================================
# Grasshopper Intent Resolution Signatures
# =============================================================================

class GHSelectComponents(dspy.Signature):
    """Select which Grasshopper components should be created for an intent.

    Given a natural language intent and component candidates from the sparse index,
    select which components to create. Do NOT solve wiring yet.

    IMPORTANT: Pay attention to quantity words in the intent!
    - "two sliders" = create TWO slider components in components_to_create
    - "three spheres" = create THREE sphere components
    - "multiple panels" = create multiple panel components as appropriate

    When multiple variants of a component exist (e.g., Circle, Circle CNR,
    Circle 3Pt), prefer the simplest/most-generic one (shortest name) unless
    the intent specifies otherwise.

    Include ALL components needed to fulfill the intent — do not omit
    components mentioned by the user. Do not drop a component just because
    wiring may be difficult.

    Example 1 (single slider):
        user_intent: "create a parametric sphere controlled by a slider"
        -> components_to_create: [{guid: slider_guid, ...}, {guid: sphere_guid, ...}]

    Example 2 (two sliders):
        user_intent: "create sphere with two sliders for radius and segments"
        -> components_to_create: [
            {guid: slider_guid, nickname: "Radius", ...},
            {guid: slider_guid, nickname: "Segments", ...},  # TWO sliders!
            {guid: sphere_guid, ...}
        ]
    """

    # Inputs
    user_intent: str = dspy.InputField(
        desc="Natural language description of what the user wants to create. Pay attention to quantity words like 'two', 'three', 'multiple'."
    )
    candidate_guids: list[str] = dspy.InputField(
        desc="Component GUIDs from sparse index lookup"
    )
    tiered_knowledge: list[dict] = dspy.InputField(
        desc="Knowledge for each candidate [{guid, name, quick, contexts, params, errors}]"
    )
    canvas_state: list[dict] = dspy.InputField(
        desc="Existing objects on canvas [{guid, name, type, x, y}]"
    )

    # Outputs
    components_to_create: list[dict] = dspy.OutputField(
        desc="Components to create [{guid, x, y, nickname, values}]. x and y are RELATIVE OFFSETS (not absolute positions) from a base point. Use small values: x in range 0-400 (left-to-right flow), y in range -200 to 200. IMPORTANT: Include multiple entries for quantity words (e.g., 'two sliders' = two slider dicts with same guid but different nicknames)"
    )
    confidence: float = dspy.OutputField(
        desc="Confidence in the selected component list (0.0-1.0)"
    )
    rationale: str = dspy.OutputField(
        desc="Why these components were selected"
    )


class GHSelectComponentsFast(dspy.Signature):
    """Select which Grasshopper components should be created for an intent.

    Same contract as GHSelectComponents but without rationale output,
    for use with dspy.Predict (faster, no chain-of-thought reasoning).

    IMPORTANT: Pay attention to quantity words in the intent!
    - "two sliders" = create TWO slider components in components_to_create
    - "three spheres" = create THREE sphere components
    - "multiple panels" = create multiple panel components as appropriate

    When multiple variants of a component exist (e.g., Circle, Circle CNR,
    Circle 3Pt), prefer the simplest/most-generic one (shortest name) unless
    the intent specifies otherwise.

    Include ALL components needed to fulfill the intent — do not omit
    components mentioned by the user. Do not drop a component just because
    wiring may be difficult.

    Example 1 (single slider):
        user_intent: "create a parametric sphere controlled by a slider"
        -> components_to_create: [{guid: slider_guid, ...}, {guid: sphere_guid, ...}]

    Example 2 (two sliders):
        user_intent: "create sphere with two sliders for radius and segments"
        -> components_to_create: [
            {guid: slider_guid, nickname: "Radius", ...},
            {guid: slider_guid, nickname: "Segments", ...},  # TWO sliders!
            {guid: sphere_guid, ...}
        ]
    """

    # Inputs (identical to GHSelectComponents)
    user_intent: str = dspy.InputField(
        desc="Natural language description of what the user wants to create. Pay attention to quantity words like 'two', 'three', 'multiple'."
    )
    candidate_guids: list[str] = dspy.InputField(
        desc="Component GUIDs from sparse index lookup"
    )
    tiered_knowledge: list[dict] = dspy.InputField(
        desc="Knowledge for each candidate [{guid, name, quick, contexts, params, errors}]"
    )
    canvas_state: list[dict] = dspy.InputField(
        desc="Existing objects on canvas [{guid, name, type, x, y}]"
    )

    # Outputs (no rationale — confidence is kept for the 0.3 quality gate)
    components_to_create: list[dict] = dspy.OutputField(
        desc="Components to create [{guid, x, y, nickname, values}]. x and y are RELATIVE OFFSETS (not absolute positions) from a base point. Use small values: x in range 0-400 (left-to-right flow), y in range -200 to 200. IMPORTANT: Include multiple entries for quantity words (e.g., 'two sliders' = two slider dicts with same guid but different nicknames)"
    )
    confidence: float = dspy.OutputField(
        desc="Confidence in the selected component list (0.0-1.0)"
    )


class GHPlanComponentWiring(dspy.Signature):
    """Plan wiring and initial values for a fixed component list.

    The component list is already selected and frozen. Do NOT add or remove
    components. Only emit wiring_plan and values_to_set that reference indices
    in selected_components.

    Example:
        user_intent: "create a parametric sphere controlled by a slider"
        selected_components: [
            {guid: slider_guid, name: "Number Slider", ...},
            {guid: sphere_guid, name: "Sphere", params: {...}}
        ]
        -> wiring_plan: [{source_index: 0, target_index: 1, target_param: "R"}]
        -> values_to_set: [{component_index: 0, value: 10}]
    """

    user_intent: str = dspy.InputField(
        desc="Natural language description of what the user wants to create."
    )
    selected_components: list[dict] = dspy.InputField(
        desc="Frozen ordered component list [{guid, name, family, quick, params, x, y, nickname}] that will be created. Do not add/remove/reorder components."
    )
    canvas_state: list[dict] = dspy.InputField(
        desc="Existing objects on canvas [{guid, name, type, x, y}]"
    )

    wiring_plan: list[dict] = dspy.OutputField(
        desc="Connections to make [{source_index, target_index, target_param}] - indices into selected_components"
    )
    values_to_set: list[dict] = dspy.OutputField(
        desc="Initial values to set [{component_index, value}] for sliders/panels"
    )
    confidence: float = dspy.OutputField(
        desc="Confidence in the wiring/value plan (0.0-1.0)"
    )
    rationale: str = dspy.OutputField(
        desc="Why these connections and values were selected"
    )


class GHPlanComponentWiringFast(dspy.Signature):
    """Plan wiring and initial values for a fixed component list.

    Same contract as GHPlanComponentWiring but without rationale output,
    for use with dspy.Predict.
    """

    user_intent: str = dspy.InputField(
        desc="Natural language description of what the user wants to create."
    )
    selected_components: list[dict] = dspy.InputField(
        desc="Frozen ordered component list [{guid, name, family, quick, params, x, y, nickname}] that will be created. Do not add/remove/reorder components."
    )
    canvas_state: list[dict] = dspy.InputField(
        desc="Existing objects on canvas [{guid, name, type, x, y}]"
    )

    wiring_plan: list[dict] = dspy.OutputField(
        desc="Connections to make [{source_index, target_index, target_param}] - indices into selected_components"
    )
    values_to_set: list[dict] = dspy.OutputField(
        desc="Initial values to set [{component_index, value}] for sliders/panels"
    )
    confidence: float = dspy.OutputField(
        desc="Confidence in the wiring/value plan (0.0-1.0)"
    )


class GHWiringBuilder(dspy.Signature):
    """Build the exact tool call sequence to execute a GH wiring plan.

    Given created components and a wiring plan, generate the precise
    sequence of MCP tool calls to execute.

    Example:
        created_components: [{guid: "abc", instance_guid: "123", ...}]
        wiring_plan: [{source_index: 0, target_index: 1, target_param: "R"}]
        -> tool_calls: [{tool: "gh_edit", args: {connect: [...]}}]
    """

    # Inputs
    created_components: list[dict] = dspy.InputField(
        desc="Components that were created [{guid, instance_guid, name, x, y}]"
    )
    wiring_plan: list[dict] = dspy.InputField(
        desc="Connections to make [{source_index, target_index, target_param}]"
    )
    values_to_set: list[dict] = dspy.InputField(
        desc="Values to set [{component_index, value}]"
    )
    gotchas: list[str] = dspy.InputField(
        desc="Warnings and gotchas to consider when building connections"
    )

    # Outputs
    tool_calls: list[dict] = dspy.OutputField(
        desc="Ordered tool calls [{tool, args}] to execute"
    )
    execution_notes: list[str] = dspy.OutputField(
        desc="Notes about the execution sequence"
    )


class GHAnalyzeCanvas(dspy.Signature):
    """Analyze the current Grasshopper canvas state.

    Given a query about the canvas and the current objects,
    provide analysis and suggestions.

    Example:
        query: "what does this definition do?"
        canvas_objects: [{guid, name, type, connections}]
        -> analysis: "This creates a parametric tower..."
        -> suggestions: ["Add a panel to see the output", ...]
    """

    # Inputs
    query: str = dspy.InputField(
        desc="Question about the canvas"
    )
    canvas_objects: list[dict] = dspy.InputField(
        desc="Objects on canvas with their connections"
    )
    selected_objects: list[str] = dspy.InputField(
        desc="GUIDs of currently selected objects (if any)"
    )

    # Outputs
    analysis: str = dspy.OutputField(
        desc="Analysis of the canvas/selection"
    )
    data_flow: list[str] = dspy.OutputField(
        desc="Description of data flow through the definition"
    )
    suggestions: list[str] = dspy.OutputField(
        desc="Suggestions for improvements or next steps"
    )


# =============================================================================
# Pattern Memory Signatures (Phase 2 Meta-Learning)
# =============================================================================

class ExtractPatternMetadata(dspy.Signature):
    """Extract structured metadata from a pattern description.

    Given a solution description (from reflection or manual input),
    extract the key elements needed for pattern storage and retrieval.
    This is the A-MEM Ps1 (Note Construction) equivalent for our domain.

    Example:
        solution_description: "When extracting arcs from concentric circles,
            you must scale the domain by each circle's radius because GH circles
            use arc-length parameterization (0 to 2πR), not angular (0 to 2π)."
        session_context: "Discovered while debugging spiral staircase tread depth"
        components_involved: ["Circle", "SubCurve", "Construct Domain"]
        -> solution_brief: "Scale domain by radius: domain_end = angle × radius"
        -> trigger_symptoms: ["microscopic slider changes", "same domain different angles"]
        -> tags: ["domain-math", "curves", "parameterization", "concentric"]
    """

    # Inputs
    solution_description: str = dspy.InputField(
        desc="Free-form description of what was learned and what to do"
    )
    session_context: str = dspy.InputField(
        desc="Context from the session where this was discovered (optional)"
    )
    components_involved: list[str] = dspy.InputField(
        desc="GH components that were used in this solution"
    )

    # Outputs
    solution_brief: str = dspy.OutputField(
        desc="One-sentence summary of the solution (max 30 words)"
    )
    solution_principle: str = dspy.OutputField(
        desc="The underlying principle or 'why' behind the solution"
    )
    trigger_intents: list[str] = dspy.OutputField(
        desc="3-5 phrases a user might say when they need this pattern"
    )
    trigger_symptoms: list[str] = dspy.OutputField(
        desc="2-4 observable symptoms that indicate this pattern applies"
    )
    tags: list[str] = dspy.OutputField(
        desc="3-6 classification tags for retrieval (e.g., 'domain-math', 'curves', 'parameterization')"
    )
    preconditions: list[str] = dspy.OutputField(
        desc="Conditions that must be true before applying this pattern"
    )


class DecidePatternLinks(dspy.Signature):
    """Decide which existing patterns should be linked to a new pattern.

    Analyze the new pattern against candidate neighbors and determine
    meaningful connections. This is the A-MEM Ps2 (Link Generation) equivalent.

    Links should represent:
    - Complementary knowledge (A extends B)
    - Alternative approaches (A vs B for same problem)
    - Prerequisite relationships (need A before B)
    - Shared concepts (A and B both involve X)

    Example:
        new_pattern_summary: "Scale domain by radius for concentric circles"
        new_pattern_tags: ["domain-math", "curves", "parameterization"]
        candidate_patterns: [
            {id: "domain_gotcha", name: "Domain Scaling Gotcha", brief: "...", tags: [...]},
            {id: "loft_direction", name: "Loft Curve Direction", brief: "...", tags: [...]}
        ]
        -> links_to_create: ["domain_gotcha"]
        -> link_rationales: ["Both patterns deal with domain parameterization issues"]
        -> updated_tags: ["domain-math", "curves", "parameterization", "concentric"]
    """

    # Inputs
    new_pattern_summary: str = dspy.InputField(
        desc="Summary of the new pattern being added (name + brief)"
    )
    new_pattern_tags: list[str] = dspy.InputField(
        desc="Tags of the new pattern"
    )
    candidate_patterns: list[dict] = dspy.InputField(
        desc="List of candidate patterns: [{id, name, brief, tags}, ...]"
    )

    # Outputs
    links_to_create: list[str] = dspy.OutputField(
        desc="Pattern IDs that should be linked to the new pattern"
    )
    link_rationales: list[str] = dspy.OutputField(
        desc="One rationale per link explaining why the connection is valuable"
    )
    updated_tags: list[str] = dspy.OutputField(
        desc="Updated tags for the new pattern based on neighbor analysis"
    )


class EvolveNeighborPatterns(dspy.Signature):
    """Update existing patterns based on newly added related knowledge.

    When a new pattern is added, its neighbors may need updates. This is
    the A-MEM Ps3 (Memory Evolution) equivalent - bidirectional evolution.

    Neighbors may gain:
    - Expanded context (new use cases discovered)
    - Additional tags (better classification)
    - New anti-patterns (mistakes to avoid)
    - Refined preconditions

    Example:
        new_pattern: {
            id: "concentric_arcs",
            name: "Concentric Circle Arc Extraction",
            brief: "Scale domain by radius",
            principle: "Circles use arc-length parameterization",
            tags: ["domain-math", "curves"]
        }
        neighbor_patterns: [
            {id: "domain_gotcha", name: "Domain Scaling Gotcha",
             brief: "Domain values are not always 0-1", tags: ["domain"],
             context: "Parameterization varies by curve type"}
        ]
        -> should_evolve: true
        -> neighbor_updates: [
            {id: "domain_gotcha", new_tags: ["domain", "parameterization", "circles"],
             context_addition: "Circles use arc-length (0 to 2πR), not angular.",
             rationale: "New pattern provides specific circle case"}
        ]
    """

    # Inputs
    new_pattern: dict = dspy.InputField(
        desc="The newly added pattern: {id, name, brief, principle, tags}"
    )
    neighbor_patterns: list[dict] = dspy.InputField(
        desc="Neighbors to potentially update: [{id, name, brief, tags, context}, ...]"
    )

    # Outputs
    should_evolve: bool = dspy.OutputField(
        desc="Whether any neighbor updates are warranted"
    )
    neighbor_updates: list[dict] = dspy.OutputField(
        desc="Updates per neighbor: [{id, new_tags, context_addition, rationale}, ...]"
    )
    evolution_summary: str = dspy.OutputField(
        desc="Brief summary of what evolved and why"
    )


# =============================================================================
# Phase 5: Reflection & Pattern Extraction
# =============================================================================

class AnalyzeStruggleSequence(dspy.Signature):
    """Analyze a struggle→success sequence to extract learnable patterns.

    Given a sequence of failed attempts followed by a success, analyze:
    1. What made this hard (multiple failures)?
    2. What was the breakthrough (what changed)?
    3. Is this generalizable (worth storing)?
    4. How would future Claude recognize this situation?
    5. What constraints apply?

    The goal is to extract actionable insights that help future Claude
    instances avoid the same struggle.

    Example:
        failures_summary: "3 attempts to connect slider to SubCurve.D failed with
                          'microscopic geometry changes' symptom"
        success_summary: "Connected slider after scaling domain by radius"
        action_type: "gh_edit"
        intent: "create wedge shape from concentric circles"
        error_messages: ["microscopic slider changes", "geometry doesn't match"]

        -> is_hard_won: true
        -> breakthrough: "Scale domain values by circle radius"
        -> is_generalizable: true
        -> trigger_intents: ["wedge shape", "pie slice", "arc from circles"]
        -> trigger_symptoms: ["microscopic slider changes"]
        -> solution_brief: "Scale domain by radius for concentric circles"
        -> recommendation: "approve"
    """

    # Inputs
    failures_summary: str = dspy.InputField(
        desc="Summary of failed attempts (what was tried, how many times, what errors)"
    )
    success_summary: str = dspy.InputField(
        desc="Summary of the successful attempt (what worked)"
    )
    action_type: str = dspy.InputField(
        desc="The explicit GH action/tool being used (e.g., 'gh_edit', 'gh_connect')"
    )
    intent: str = dspy.InputField(
        desc="The user goal associated with the explicit action (empty string if unavailable)"
    )
    error_messages: list[str] = dspy.InputField(
        desc="Unique error messages from the failures"
    )
    failure_params: list[dict] = dspy.InputField(
        desc="Parameters used in failed attempts"
    )
    success_params: dict = dspy.InputField(
        desc="Parameters used in successful attempt"
    )

    # Outputs - Answers to reflection questions
    is_hard_won: bool = dspy.OutputField(
        desc="True if this required significant effort (2+ failures)"
    )
    hard_won_reason: str = dspy.OutputField(
        desc="Why this was (or wasn't) hard-won"
    )
    breakthrough: str = dspy.OutputField(
        desc="What changed between last failure and success"
    )
    breakthrough_insight: str = dspy.OutputField(
        desc="The underlying principle discovered (the 'why')"
    )
    is_generalizable: bool = dspy.OutputField(
        desc="True if this pattern would help with similar problems"
    )
    generalization_scope: str = dspy.OutputField(
        desc="Description of when this pattern applies"
    )

    # Outputs - Pattern components
    trigger_intents: list[str] = dspy.OutputField(
        desc="Intent phrases that should trigger this pattern"
    )
    trigger_symptoms: list[str] = dspy.OutputField(
        desc="Observable symptoms that indicate this pattern applies"
    )
    solution_brief: str = dspy.OutputField(
        desc="One-line summary of the solution"
    )
    solution_principle: str = dspy.OutputField(
        desc="Underlying principle (why this works)"
    )
    preconditions: list[str] = dspy.OutputField(
        desc="What must be true before applying this pattern"
    )
    postconditions: list[str] = dspy.OutputField(
        desc="What should be true after successful application"
    )
    anti_patterns: list[dict] = dspy.OutputField(
        desc="What NOT to do: [{mistake, symptom, why_wrong}, ...]"
    )

    # Outputs - Recommendation
    recommendation: str = dspy.OutputField(
        desc="'approve' (clear insight), 'review' (needs human judgment), or 'skip' (not worth storing)"
    )
    recommendation_reason: str = dspy.OutputField(
        desc="Why this recommendation was made"
    )
