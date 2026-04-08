"""
Investigation Engine for Autonomous Learning.

This module conducts investigations to fill knowledge gaps.
It's not just testing - it's problem-solving. When something fails,
it diagnoses WHY and finds alternatives.

The investigator uses the existing exploration context to track
created objects and the existing knowledge system to record findings.

Enhanced with tool schema awareness for intelligent parameter generation.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum

from .schema import (
    Gap,
    GapStatus,
    Pattern,
    Antipattern,
    ErrorCategory,
    InsightCategory,
    now_iso,
)
from .graph import KnowledgeGraphV2
from .tool_schemas import (
    get_tool_schema,
    generate_params_for_tool,
    parse_missing_param_from_error,
    parse_invalid_param_from_error,
    generate_default_value,
    get_geometry_requirements,
    get_geometry_count,
    ToolSchema,
)
from ..explorer.context import ExplorationContext, GeometryType, parse_create_result

logger = logging.getLogger("rook.learning.investigator")


class InvestigationPhase(Enum):
    """Phases of an investigation."""
    SETUP = "setup"           # Creating prerequisite geometry
    HYPOTHESIS = "hypothesis" # Testing a hypothesis
    DIAGNOSIS = "diagnosis"   # Analyzing a failure
    ALTERNATIVE = "alternative" # Trying an alternative approach
    VERIFICATION = "verification" # Visual verification


@dataclass
class ExperimentResult:
    """Result of a single experiment."""
    tool: str
    params: dict
    success: bool
    response: Any = None
    error: str | None = None
    error_category: str = ErrorCategory.UNKNOWN.value
    execution_time_ms: float = 0


@dataclass
class Diagnosis:
    """Analysis of why something failed."""
    error_message: str
    error_category: str
    likely_cause: str
    suggested_fixes: list[str] = field(default_factory=list)
    missing_preconditions: list[str] = field(default_factory=list)


@dataclass
class InvestigationResult:
    """Complete result of an investigation."""
    gap_id: str | None = None
    tool: str = ""

    # What was learned
    patterns_discovered: list[Pattern] = field(default_factory=list)
    antipatterns_discovered: list[Antipattern] = field(default_factory=list)

    # Experiments run
    experiments: list[ExperimentResult] = field(default_factory=list)

    # Was the gap resolved?
    gap_resolved: bool = False
    resolution: str | None = None

    # Any new gaps discovered
    new_gaps: list[Gap] = field(default_factory=list)

    # Insights gained
    insights: list[str] = field(default_factory=list)


# Type alias for tool executor function
ToolExecutor = Callable[[str, dict], Awaitable[dict]]


class Investigator:
    """
    Conducts investigations to fill knowledge gaps.

    Not testing - problem-solving. When something fails,
    diagnose WHY and find alternatives.
    """

    def __init__(
        self,
        kg: KnowledgeGraphV2,
        executor: ToolExecutor,
        context: ExplorationContext | None = None,
    ):
        """
        Initialize the investigator.

        Args:
            kg: Knowledge graph V2 API
            executor: Async function to execute MCP tools
            context: Optional exploration context (creates new if not provided)
        """
        self.kg = kg
        self.executor = executor
        self.context = context or ExplorationContext()
        self._current_phase = InvestigationPhase.SETUP

    async def investigate_gap(self, gap: Gap) -> InvestigationResult:
        """
        Investigate a knowledge gap with problem-solving.

        1. Form hypotheses based on gap description
        2. Design experiments to test hypotheses
        3. Run experiments, capture results
        4. Diagnose failures, try alternatives
        5. Record everything learned

        Args:
            gap: The gap to investigate

        Returns:
            InvestigationResult with findings
        """
        result = InvestigationResult(gap_id=gap.id, tool=gap.tool)

        # Mark gap as being investigated
        self.kg.mark_gap_investigating(gap.id)

        logger.info(f"Investigating gap: {gap.unknown_aspect}")

        # Setup: Create test geometry if needed for this tool
        self._current_phase = InvestigationPhase.SETUP
        await self._setup_test_geometry(gap.tool)

        # Test each hypothesis
        for hypothesis in gap.hypotheses:
            logger.info(f"Testing hypothesis: {hypothesis}")

            self._current_phase = InvestigationPhase.HYPOTHESIS
            experiment = await self._test_hypothesis(gap.tool, hypothesis)
            result.experiments.append(experiment)

            # Record result
            self.kg.add_hypothesis_result(
                gap_id=gap.id,
                hypothesis=hypothesis,
                result="success" if experiment.success else f"failed: {experiment.error}"
            )

            if experiment.success:
                # Found something that works!
                pattern = await self._create_pattern_from_experiment(
                    experiment, hypothesis
                )
                result.patterns_discovered.append(pattern)

                # Record to knowledge graph
                self.kg.record(
                    intent=gap.unknown_aspect,
                    action={"tool": experiment.tool, "params": experiment.params},
                    outcome="success"
                )
            else:
                # Diagnose and try alternatives
                self._current_phase = InvestigationPhase.DIAGNOSIS
                diagnosis = self._diagnose_failure(experiment)

                # Try alternatives based on diagnosis
                self._current_phase = InvestigationPhase.ALTERNATIVE
                for fix in diagnosis.suggested_fixes[:3]:  # Try up to 3 alternatives
                    alt_experiment = await self._try_alternative(
                        experiment, fix, diagnosis
                    )
                    result.experiments.append(alt_experiment)

                    if alt_experiment.success:
                        # Record as pattern with correction
                        pattern = await self._create_pattern_from_experiment(
                            alt_experiment, f"{hypothesis} (fixed: {fix})"
                        )
                        result.patterns_discovered.append(pattern)

                        # Record with correction
                        self.kg.record(
                            intent=gap.unknown_aspect,
                            action={"tool": alt_experiment.tool, "params": alt_experiment.params},
                            outcome="success",
                            correction_of={
                                "params": experiment.params,
                                "error": experiment.error
                            }
                        )
                        break

                # Record antipattern
                antipattern = Antipattern(
                    tool=experiment.tool,
                    params=experiment.params,
                    error=experiment.error or "Unknown error",
                    error_category=diagnosis.error_category,
                    diagnosis=diagnosis.likely_cause,
                )
                result.antipatterns_discovered.append(antipattern)

        # Check if we resolved the gap
        if result.patterns_discovered:
            result.gap_resolved = True
            result.resolution = f"Found {len(result.patterns_discovered)} working pattern(s)"
            self.kg.resolve_gap(
                gap_id=gap.id,
                resolution=result.resolution,
            )

        return result

    async def investigate_tool(self, tool_name: str) -> InvestigationResult:
        """
        Thorough investigation of a tool's behavior.

        1. What parameters does it accept?
        2. What are valid value ranges?
        3. What preconditions must be met?
        4. What does it produce?
        5. How does it fail?
        6. What are common mistakes?

        Args:
            tool_name: The MCP tool to investigate

        Returns:
            InvestigationResult with findings
        """
        result = InvestigationResult(tool=tool_name)

        logger.info(f"Investigating tool: {tool_name}")

        # Query existing knowledge first
        existing = self.kg.query(tool=tool_name)

        # Setup: Create test geometry if needed
        self._current_phase = InvestigationPhase.SETUP
        await self._setup_test_geometry(tool_name)

        # Test basic usage
        self._current_phase = InvestigationPhase.HYPOTHESIS
        basic_params = self._generate_basic_params(tool_name)

        experiment = await self._run_experiment(tool_name, basic_params)
        result.experiments.append(experiment)

        if experiment.success:
            pattern = await self._create_pattern_from_experiment(
                experiment, f"Basic usage of {tool_name}"
            )
            result.patterns_discovered.append(pattern)

            self.kg.record(
                intent=f"use {tool_name}",
                action={"tool": tool_name, "params": basic_params},
                outcome="success"
            )
        else:
            # Diagnose and record
            diagnosis = self._diagnose_failure(experiment)

            antipattern = Antipattern(
                tool=tool_name,
                params=basic_params,
                error=experiment.error or "Unknown error",
                error_category=diagnosis.error_category,
                diagnosis=diagnosis.likely_cause,
            )
            result.antipatterns_discovered.append(antipattern)

            self.kg.record(
                intent=f"use {tool_name}",
                action={"tool": tool_name, "params": basic_params},
                outcome="failure"
            )

            # Create a gap for further investigation
            gap = self.kg.add_gap(
                tool=tool_name,
                unknown_aspect=f"How to successfully use {tool_name}? Initial attempt failed: {diagnosis.likely_cause}",
                hypotheses=diagnosis.suggested_fixes,
            )
            result.new_gaps.append(gap)

        return result

    async def investigate_workflow(
        self,
        workflow: list[tuple[str, dict]],
        description: str,
    ) -> InvestigationResult:
        """
        Investigate how tools work together.

        1. Execute workflow step by step
        2. Track data flow between tools
        3. Identify failure points
        4. Record successful chains

        Args:
            workflow: List of (tool_name, params) tuples
            description: Description of what this workflow does

        Returns:
            InvestigationResult with findings
        """
        result = InvestigationResult(tool=workflow[0][0] if workflow else "")

        logger.info(f"Investigating workflow: {description}")

        success_so_far = True
        last_result = None

        for i, (tool_name, params) in enumerate(workflow):
            # Substitute IDs from context if needed
            resolved_params = self._resolve_params(params)

            experiment = await self._run_experiment(tool_name, resolved_params)
            result.experiments.append(experiment)

            if experiment.success:
                # Track any created objects
                self._track_created_objects(tool_name, resolved_params, experiment.response)
                last_result = experiment.response
            else:
                success_so_far = False
                diagnosis = self._diagnose_failure(experiment)

                # Record where the workflow failed
                result.insights.append(
                    f"Workflow failed at step {i+1}/{len(workflow)}: {tool_name} - {diagnosis.likely_cause}"
                )

                antipattern = Antipattern(
                    tool=tool_name,
                    params=resolved_params,
                    error=experiment.error or "Unknown error",
                    error_category=diagnosis.error_category,
                    diagnosis=f"Failed in workflow context: {diagnosis.likely_cause}",
                )
                result.antipatterns_discovered.append(antipattern)
                break

        if success_so_far:
            # Record successful workflow
            result.insights.append(f"Workflow completed successfully: {description}")

            # Record tool relationships
            for i in range(len(workflow) - 1):
                tool_a = workflow[i][0]
                tool_b = workflow[i + 1][0]
                self.kg.record_relationship(
                    tool_a=tool_a,
                    tool_b=tool_b,
                    relationship_type="produces_input_for",
                    description=f"{tool_a} output feeds into {tool_b}",
                    example_chain=[f"{tool_a} → {tool_b}"],
                )

        return result

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _run_experiment(self, tool: str, params: dict) -> ExperimentResult:
        """Run a single experiment."""
        import time
        start = time.time()

        try:
            response = await self.executor(tool, params)
            elapsed = (time.time() - start) * 1000

            success = response.get("success", False)
            error = None if success else str(response.get("data", response.get("error", "Unknown error")))

            return ExperimentResult(
                tool=tool,
                params=params,
                success=success,
                response=response.get("data") if success else None,
                error=error,
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ExperimentResult(
                tool=tool,
                params=params,
                success=False,
                error=str(e),
                error_category=ErrorCategory.NETWORK_ERROR.value,
                execution_time_ms=elapsed,
            )

    async def _test_hypothesis(self, tool: str, hypothesis: str) -> ExperimentResult:
        """Test a specific hypothesis about a tool."""
        # Generate params based on hypothesis
        params = self._params_from_hypothesis(tool, hypothesis)
        return await self._run_experiment(tool, params)

    async def _try_alternative(
        self,
        failed: ExperimentResult,
        fix: str,
        diagnosis: Diagnosis,
    ) -> ExperimentResult:
        """Try an alternative approach based on diagnosis."""
        # Modify params based on the suggested fix
        new_params = self._apply_fix(failed.params, fix, diagnosis, tool=failed.tool)
        logger.debug(f"Trying alternative with params: {new_params}")
        return await self._run_experiment(failed.tool, new_params)

    def _diagnose_failure(self, experiment: ExperimentResult) -> Diagnosis:
        """Analyze why an experiment failed.

        Parses the error message to extract specific information about
        what went wrong and what parameter might be missing or invalid.
        """
        error = experiment.error or "Unknown error"
        error_lower = error.lower()

        # Try to extract specific parameter name from error
        missing_param = parse_missing_param_from_error(error)
        invalid_param, expected_type = parse_invalid_param_from_error(error)

        missing_preconditions = []

        # Categorize the error with specific diagnosis
        if missing_param:
            category = ErrorCategory.MISSING_PARAM.value
            likely_cause = f"Missing required parameter: '{missing_param}'"
            fixes = self._suggest_fixes_for_missing_param(experiment.tool, missing_param)
            missing_preconditions = [f"Parameter '{missing_param}' must be provided"]
            logger.info(f"Diagnosed missing param: {missing_param}")

        elif invalid_param:
            category = ErrorCategory.INVALID_PARAM.value
            likely_cause = f"Invalid value for parameter '{invalid_param}'"
            if expected_type:
                likely_cause += f" (expected {expected_type})"
            fixes = self._suggest_fixes_for_invalid_param(experiment.tool, invalid_param, expected_type)
            logger.info(f"Diagnosed invalid param: {invalid_param} -> {expected_type}")

        elif "missing" in error_lower or "required" in error_lower:
            category = ErrorCategory.MISSING_PARAM.value
            likely_cause = "A required parameter was not provided"
            fixes = self._suggest_missing_param_fixes(experiment)

        elif "invalid" in error_lower or "type" in error_lower:
            category = ErrorCategory.INVALID_PARAM.value
            likely_cause = "A parameter has an invalid value or type"
            fixes = self._suggest_invalid_param_fixes(experiment)

        elif "not found" in error_lower or "does not exist" in error_lower:
            category = ErrorCategory.PRECONDITION_FAILED.value
            likely_cause = "A referenced object does not exist"
            fixes = ["Create the required geometry first", "Use a valid object ID from the scene"]
            missing_preconditions = ["Referenced object must exist in the scene"]

        elif "geometry" in error_lower or "brep" in error_lower or "curve" in error_lower:
            category = ErrorCategory.GEOMETRY_ERROR.value
            likely_cause = "The geometry operation failed"
            fixes = ["Check input geometry is valid", "Try with simpler geometry", "Ensure geometry types are compatible"]

        else:
            category = ErrorCategory.UNKNOWN.value
            likely_cause = f"Unknown error: {error[:100]}"
            # Try to get schema and suggest required params
            schema = get_tool_schema(experiment.tool)
            if schema:
                missing = [p.name for p in schema.get_required_params() if p.name not in experiment.params]
                if missing:
                    fixes = [f"Add required parameter '{p}'" for p in missing[:3]]
                else:
                    fixes = ["Check tool documentation", "Try with different parameter values"]
            else:
                fixes = ["Check tool documentation", "Try with different parameters"]

        return Diagnosis(
            error_message=error,
            error_category=category,
            likely_cause=likely_cause,
            suggested_fixes=fixes,
            missing_preconditions=missing_preconditions,
        )

    def _suggest_fixes_for_missing_param(
        self, tool: str, param_name: str,
    ) -> list[str]:
        """Suggest specific fixes for a known missing parameter."""
        fixes = []

        schema = get_tool_schema(tool)
        if schema:
            param_schema = schema.get_param(param_name)
            if param_schema:
                # Generate a specific value suggestion
                value = generate_default_value(param_schema, self.context)
                if value is not None:
                    if isinstance(value, str):
                        fixes.append(f"Add '{param_name}': \"{value}\"")
                    else:
                        fixes.append(f"Add '{param_name}': {value}")
                else:
                    fixes.append(f"Add required parameter '{param_name}' ({param_schema.param_type})")

                # Add description-based hint
                if param_schema.description:
                    fixes.append(f"{param_name}: {param_schema.description}")
            else:
                fixes.append(f"Add parameter '{param_name}'")
        else:
            fixes.append(f"Add parameter '{param_name}'")

        return fixes

    def _suggest_fixes_for_invalid_param(
        self, tool: str, param_name: str, expected_type: str | None,
    ) -> list[str]:
        """Suggest specific fixes for an invalid parameter value."""
        fixes = []

        schema = get_tool_schema(tool)
        if schema:
            param_schema = schema.get_param(param_name)
            if param_schema:
                # If there are enum values, suggest them
                if param_schema.enum:
                    fixes.append(f"Use one of: {', '.join(param_schema.enum)}")

                # Suggest the correct type
                fixes.append(f"'{param_name}' should be {param_schema.param_type}")

                # Generate example value
                value = generate_default_value(param_schema, self.context)
                if value is not None:
                    fixes.append(f"Example value: {value}")

        if expected_type:
            fixes.append(f"Expected type: {expected_type}")

        if not fixes:
            fixes = ["Check the parameter type and value"]

        return fixes

    def _suggest_missing_param_fixes(self, experiment: ExperimentResult) -> list[str]:
        """Suggest fixes for missing parameter errors."""
        fixes = []

        # Common missing parameters by tool type
        if "ids" not in experiment.params:
            fixes.append("Add 'ids' parameter with object GUIDs")
        if "id" not in experiment.params and "Id" in experiment.tool:
            fixes.append("Add 'id' parameter with object GUID")

        return fixes or ["Check required parameters in tool documentation"]

    def _suggest_invalid_param_fixes(self, experiment: ExperimentResult) -> list[str]:
        """Suggest fixes for invalid parameter errors."""
        return [
            "Check parameter types (string vs number vs array)",
            "Ensure coordinate arrays have 3 elements [x, y, z]",
            "Use valid enum values for operation types",
        ]

    def _apply_fix(self, params: dict, fix: str, diagnosis: Diagnosis, tool: str = None) -> dict:
        """Apply a suggested fix to parameters.

        Parses the fix string to extract parameter names and values,
        then adds them to the parameters dict.
        """
        import re
        new_params = params.copy()

        # Extract parameter name from fix string
        # Pattern: "Add 'param_name': value" or "Add 'param_name'"
        match = re.search(r"[Aa]dd\s+['\"](\w+)['\"](?::\s*(.+))?", fix)
        if match:
            param_name = match.group(1)
            value_str = match.group(2)

            if param_name not in new_params:
                if value_str:
                    # Try to parse the value
                    try:
                        # Remove quotes from string values
                        if value_str.startswith('"') and value_str.endswith('"'):
                            new_params[param_name] = value_str[1:-1]
                        elif value_str.startswith('[') or value_str.startswith('{'):
                            import json
                            new_params[param_name] = json.loads(value_str)
                        elif value_str.lower() in ('true', 'false'):
                            new_params[param_name] = value_str.lower() == 'true'
                        elif '.' in value_str:
                            new_params[param_name] = float(value_str)
                        else:
                            new_params[param_name] = int(value_str)
                    except (ValueError, json.JSONDecodeError):
                        new_params[param_name] = value_str
                else:
                    # Generate value from schema
                    if tool:
                        schema = get_tool_schema(tool)
                        if schema:
                            param_schema = schema.get_param(param_name)
                            if param_schema:
                                value = generate_default_value(param_schema, self.context)
                                if value is not None:
                                    new_params[param_name] = value
            logger.debug(f"Applied fix: added {param_name} = {new_params.get(param_name)}")
            return new_params

        # Extract from "parameter 'X' must be provided" or similar
        match = re.search(r"[Pp]arameter\s+['\"](\w+)['\"]", fix)
        if match:
            param_name = match.group(1)
            if param_name not in new_params and tool:
                schema = get_tool_schema(tool)
                if schema:
                    param_schema = schema.get_param(param_name)
                    if param_schema:
                        value = generate_default_value(param_schema, self.context)
                        if value is not None:
                            new_params[param_name] = value
                            logger.debug(f"Applied fix: added {param_name} = {value}")
            return new_params

        # Fall back to simple heuristics for common fixes
        if "ids" in fix.lower() and "ids" not in new_params:
            obj_ids = self.context.get_any_ids(limit=2)
            if obj_ids:
                new_params["ids"] = obj_ids

        if "id'" in fix.lower() and "id" not in new_params:
            obj_id = self.context.get_any_id()
            if obj_id:
                new_params["id"] = obj_id

        if "curveId" in fix and "curveId" not in new_params:
            curve_id = self.context.get_curve_id()
            if curve_id:
                new_params["curveId"] = curve_id

        if "brepId" in fix and "brepId" not in new_params:
            brep_id = self.context.get_brep_id()
            if brep_id:
                new_params["brepId"] = brep_id

        if "meshId" in fix and "meshId" not in new_params:
            mesh_id = self.context.get_mesh_id()
            if mesh_id:
                new_params["meshId"] = mesh_id

        if "code" in fix.lower() and "code" not in new_params:
            new_params["code"] = "import rhinoscriptsyntax as rs\nprint('Hello from Rook')"

        if "command" in fix.lower() and "command" not in new_params:
            new_params["command"] = "_Line 0,0,0 10,0,0"

        if "name" in fix.lower() and "name" not in new_params:
            new_params["name"] = "TestObject"

        return new_params

    async def _setup_test_geometry(self, tool_name: str):
        """Create test geometry needed for investigating a tool.

        Uses the tool schema to determine exactly what geometry is needed.
        """
        # Get schema-based requirements first
        requirements = get_geometry_requirements(tool_name)
        geometry_count = get_geometry_count(tool_name)

        if not requirements:
            # Fall back to name-based heuristics for tools without schemas
            if any(x in tool_name for x in ["transform", "copy", "delete", "measure", "select"]):
                requirements = ["any"]
            elif any(x in tool_name for x in ["curve", "offset", "extend", "fillet", "loft", "sweep", "extrude"]):
                requirements = ["curve"]
            elif any(x in tool_name for x in ["brep", "boolean", "split", "trim", "surface"]):
                requirements = ["brep"]
            elif any(x in tool_name for x in ["mesh"]):
                requirements = ["mesh"]
            elif any(x in tool_name for x in ["subd"]):
                requirements = ["subd"]

        logger.debug(f"Setting up geometry for {tool_name}: needs {requirements}, count={geometry_count}")

        # Create geometry based on requirements
        for req in requirements:
            await self._ensure_geometry_type(req, geometry_count)

    async def _ensure_geometry_type(self, geom_type: str, count: int = 1):
        """Ensure we have the required geometry type available."""

        if geom_type == "curve":
            existing_count = len(self.context.get_curve_ids(limit=10))
            needed = max(0, count - existing_count)
            for i in range(needed):
                # Create different curves at different positions
                result = await self.executor("rhino_create", {
                    "type": "LINE",
                    "start": [i * 15, 0, 0],
                    "end": [i * 15 + 10, 0, 0],
                })
                if result.get("success"):
                    self._track_created_objects("rhino_create", {"type": "LINE"}, result.get("data"))
                    logger.info(f"Created LINE for test geometry, ID: {result.get('data', {}).get('id', 'unknown')}")
                else:
                    logger.warning(f"Failed to create LINE: {result.get('data', result.get('error', 'unknown error'))}")
                # Also create a circle for more variety
                if needed > 1 and i == 0:
                    result = await self.executor("rhino_create", {
                        "type": "CIRCLE",
                        "center": [0, 15, 0],
                        "radius": 5,
                    })
                    if result.get("success"):
                        self._track_created_objects("rhino_create", {"type": "CIRCLE"}, result.get("data"))
                        logger.info(f"Created CIRCLE for test geometry")
                    else:
                        logger.warning(f"Failed to create CIRCLE: {result.get('data', result.get('error', 'unknown error'))}")

        elif geom_type == "brep":
            existing_count = len(self.context.get_brep_ids(limit=10))
            needed = max(0, count - existing_count)
            for i in range(needed):
                # Create different breps at different positions
                geom_name = "SPHERE" if i == 0 else "BOX"
                if i == 0:
                    result = await self.executor("rhino_create", {
                        "type": "SPHERE",
                        "center": [0, 0, 0],
                        "radius": 5,
                    })
                else:
                    result = await self.executor("rhino_create", {
                        "type": "BOX",
                        "origin": [i * 15, 0, 0],
                        "width": 8,
                        "depth": 8,
                        "height": 8,
                    })
                if result.get("success"):
                    self._track_created_objects("rhino_create", {"type": geom_name}, result.get("data"))
                    logger.info(f"Created {geom_name} for test geometry, ID: {result.get('data', {}).get('id', 'unknown')}")
                else:
                    logger.warning(f"Failed to create {geom_name}: {result.get('data', result.get('error', 'unknown error'))}")

        elif geom_type == "mesh":
            existing_count = len(self.context.get_mesh_ids(limit=10))
            needed = max(0, count - existing_count)
            for i in range(needed):
                mesh_type = "mesh_sphere" if i == 0 else "mesh_box"
                if i == 0:
                    result = await self.executor("rhino_mesh_sphere", {
                        "radius": 5,
                    })
                else:
                    result = await self.executor("rhino_mesh_box", {
                        "width": 10,
                        "depth": 10,
                        "height": 10,
                        "origin": [i * 15, 0, 0],
                    })
                if result.get("success"):
                    self._track_created_objects("rhino_mesh_sphere" if i == 0 else "rhino_mesh_box", {}, result.get("data"))
                    logger.info(f"Created {mesh_type} for test geometry")
                else:
                    logger.warning(f"Failed to create {mesh_type}: {result.get('data', result.get('error', 'unknown error'))}")

        elif geom_type == "subd":
            existing_count = len(self.context.get_subd_ids(limit=10))
            needed = max(0, count - existing_count)
            for i in range(needed):
                result = await self.executor("rhino_subd_sphere", {
                    "radius": 5,
                    "center": [i * 15, 0, 0],
                })
                if result.get("success"):
                    self._track_created_objects("rhino_subd_sphere", {}, result.get("data"))
                    logger.info(f"Created subd_sphere for test geometry")
                else:
                    logger.warning(f"Failed to create subd_sphere: {result.get('data', result.get('error', 'unknown error'))}")

        elif geom_type == "any":
            # Just need some geometry - prefer brep
            if not self.context.has_objects():
                result = await self.executor("rhino_create", {
                    "type": "BOX",
                    "origin": [0, 0, 0],
                    "width": 10,
                    "depth": 10,
                    "height": 10,
                })
                if result.get("success"):
                    self._track_created_objects("rhino_create", {"type": "BOX"}, result.get("data"))
                    logger.info(f"Created BOX for test geometry (any), ID: {result.get('data', {}).get('id', 'unknown')}")
                else:
                    logger.warning(f"Failed to create BOX for 'any' geometry: {result.get('data', result.get('error', 'unknown error'))}")

        # Log context state after geometry setup
        logger.debug(f"Context after setup for '{geom_type}': {self.context.get_stats()}")

    def _generate_basic_params(self, tool_name: str) -> dict:
        """Generate basic parameters for a tool using its schema.

        Uses the tool schema to generate all required parameters with
        appropriate default values, including geometry IDs from context.
        """
        # First, try schema-based generation
        schema = get_tool_schema(tool_name)
        if schema:
            params = generate_params_for_tool(tool_name, self.context)
            logger.debug(f"Generated params from schema for {tool_name}: {list(params.keys())}")
            return params

        # Fall back to heuristic-based generation for unknown tools
        params = {}
        logger.debug(f"No schema for {tool_name}, using heuristics")

        # Common patterns based on tool name
        if "ids" in tool_name or any(x in tool_name for x in ["transform", "copy", "delete"]):
            obj_id = self.context.get_any_id()
            if obj_id:
                params["ids"] = [obj_id]

        if "brep" in tool_name.lower():
            brep_id = self.context.get_brep_id()
            if brep_id:
                params["brepId"] = brep_id

        if "curve" in tool_name.lower():
            curve_id = self.context.get_curve_id()
            if curve_id:
                params["curveId"] = curve_id

        if "mesh" in tool_name.lower():
            mesh_id = self.context.get_mesh_id()
            if mesh_id:
                params["meshId"] = mesh_id

        if "subd" in tool_name.lower():
            subd_id = self.context.get_subd_id()
            if subd_id:
                params["subdId"] = subd_id

        return params

    def _params_from_hypothesis(self, tool: str, hypothesis: str) -> dict:
        """Generate parameters based on a hypothesis."""
        # Start with basic params
        params = self._generate_basic_params(tool)

        # Add based on hypothesis keywords (simple heuristics)
        hypothesis_lower = hypothesis.lower()

        if "vector" in hypothesis_lower:
            params["vector"] = [10, 0, 0]
        if "angle" in hypothesis_lower:
            params["angle"] = 45
        if "scale" in hypothesis_lower:
            params["factor"] = 2.0
        if "center" in hypothesis_lower:
            params["center"] = [0, 0, 0]

        return params

    def _resolve_params(self, params: dict) -> dict:
        """Resolve placeholder parameters with real IDs from context."""
        resolved = {}

        for key, value in params.items():
            if value == "<any_id>":
                resolved[key] = self.context.get_any_id()
            elif value == "<brep_id>":
                resolved[key] = self.context.get_brep_id()
            elif value == "<curve_id>":
                resolved[key] = self.context.get_curve_id()
            elif value == "<mesh_id>":
                resolved[key] = self.context.get_mesh_id()
            elif value == "<any_ids>":
                resolved[key] = self.context.get_any_ids()
            else:
                resolved[key] = value

        return resolved

    def _track_created_objects(self, tool: str, params: dict, response: Any):
        """Track objects created by a tool."""
        if response is None:
            return

        obj_id, geom_type = parse_create_result(
            {"success": True, "data": response},
            tool,
            params
        )

        if obj_id and geom_type:
            self.context.add_object(
                obj_id=obj_id,
                geometry_type=geom_type,
                tool_used=tool,
                params_used=params,
            )

    async def _create_pattern_from_experiment(
        self,
        experiment: ExperimentResult,
        note: str,
    ) -> Pattern:
        """Create a Pattern from a successful experiment."""
        return Pattern(
            tool=experiment.tool,
            params=experiment.params,
            note=note,
            confidence=0.7,  # Initial confidence, will be updated by MAB
            discovered_by_session=self.kg.session_id,
        )
