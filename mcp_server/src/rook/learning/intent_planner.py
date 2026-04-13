"""Intent Planner: natural language intent -> typed ExecutionPlan.

The planner is the first stage of the intent runtime. It takes a natural
language intent string and produces an ExecutionPlan that the SmartExecutor
can execute without re-parsing.

Two resolution paths:

  1. FAST PATH (CapabilityRouter)
     - A lightweight DSPy Predict call extracts operation + params from intent
     - CapabilityRouter checks if the operation has a direct HTTP route
     - If yes: plan is complete, no command resolution needed
     - Typical latency: 1 LLM call (param extraction only)

  2. SLOW PATH (command resolution)
     - CapabilityRouter has no route for this operation
     - Falls back to existing CommandKnowledgeStore + DSPy IntentResolver
     - Resolves command name, mode, and syntax via 2 LLM calls
     - Augments with gotchas from KnowledgeGraphV2
     - Typical latency: 2-3 LLM calls

The planner never executes anything. It only produces plans.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger("rook.learning.intent_planner")

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

from .intent_runtime import (
    CapabilityRouter,
    ExecutionPlan,
    RouteSpec,
)


# ---------------------------------------------------------------------------
# DSPy signature for operation extraction (fast path)
# ---------------------------------------------------------------------------

if DSPY_AVAILABLE:
    class ExtractOperation(dspy.Signature):
        """Extract a structured operation from a natural language Rhino intent.

        Given a user's intent and the list of available operations, determine:
        1. Which operation best matches (must be from the provided list, or 'unknown')
        2. The typed parameters for that operation

        If the intent doesn't match any known operation, set operation to 'unknown'.

        Examples:
            "create a sphere at 0,0,0 with radius 5"
            -> operation: "create_sphere", params: {"center": [0,0,0], "radius": 5}

            "move objects guid-1 guid-2 by 10 in x"
            -> operation: "move", params: {"ids": ["guid-1", "guid-2"], "vector": [10,0,0]}

            "loft through these curves"
            -> operation: "unknown", params: {"description": "loft through curves"}
        """
        user_intent: str = dspy.InputField(
            desc="Natural language description of what to do in Rhino"
        )
        available_operations: list[str] = dspy.InputField(
            desc="List of operation names that have direct API routes"
        )
        operation: str = dspy.OutputField(
            desc="The operation name from available_operations, or 'unknown'"
        )
        params: dict = dspy.OutputField(
            desc="Typed parameters for the operation (JSON dict)"
        )
        confidence: float = dspy.OutputField(
            desc="Confidence in this extraction (0.0-1.0)"
        )


# ---------------------------------------------------------------------------
# Intent Planner
# ---------------------------------------------------------------------------

class IntentPlanner:
    """Converts natural language intent into a typed ExecutionPlan.

    Usage:
        planner = IntentPlanner()
        plan = await planner.plan("create a sphere at origin with radius 5")

        if plan.execution_route == "direct_api":
            # Fast path: route_spec is set, no command resolution needed
            ...
        elif plan.execution_route == "known_command":
            # Slow path: command/mode/syntax are set
            ...
        else:
            # Unknown: no route found
            ...
    """

    def __init__(
        self,
        router: CapabilityRouter | None = None,
        knowledge_store: Any | None = None,
        knowledge_graph: Any | None = None,
    ) -> None:
        self._router = router or CapabilityRouter.get()
        self._knowledge_store = knowledge_store
        self._knowledge_graph = knowledge_graph

        # Lazy-init DSPy modules
        self._extractor: Any | None = None
        self._intent_resolver: Any | None = None
        self._syntax_builder: Any | None = None
        self._dspy_configured = False
        self._dspy_init_failed = False

        # Cache the operation list for the extractor prompt
        self._operation_list = self._router.list_operations()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def plan(
        self, intent: str, context: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """Plan an execution for the given intent.

        Args:
            intent: Natural language description of the desired operation.
            context: Optional geometry context from the current Rhino session.
                Supported keys:
                  - ``selected_ids``: list[str] — GUIDs of currently selected objects
                  - ``geometry_types``: dict[str, str] — {guid: type_name} for selected objects

                When the intent references "selected objects" or "these edges"
                without explicit GUIDs, selected_ids are injected into the plan
                params so the executor can operate on the correct objects.

        Tries the fast path (CapabilityRouter) first.
        Falls back to command resolution if no direct route found.
        """
        start = time.time()
        ctx = context or {}
        trace: list[str] = [f"Planning: {intent}"]

        if ctx.get("selected_ids"):
            trace.append(f"Context: {len(ctx['selected_ids'])} selected objects")

        # --- Fast path: try CapabilityRouter ---
        plan = await self._try_fast_path(intent, trace, ctx)
        if plan is not None:
            plan.time_ms = (time.time() - start) * 1000
            return plan

        # --- Slow path: command resolution ---
        plan = await self._try_command_path(intent, trace, ctx)
        if plan is not None:
            plan.time_ms = (time.time() - start) * 1000
            return plan

        # --- No route found ---
        trace.append("No execution path found")
        return ExecutionPlan(
            intent=intent,
            operation="unknown",
            execution_route="unknown",
            confidence=0.0,
            reasoning_trace=trace,
        )

    def plan_direct(self, operation: str, params: dict[str, Any]) -> ExecutionPlan:
        """Create a plan for a known operation without LLM calls.

        Use when the caller already knows the operation and params
        (e.g. from a previous planning step or explicit user specification).
        """
        spec = self._router.route(operation)
        if spec is not None:
            valid, missing = self._router.validate_params(operation, params)
            return ExecutionPlan(
                intent=f"direct:{operation}",
                operation=operation,
                params=params,
                execution_route="direct_api",
                route_spec=spec,
                confidence=1.0 if valid else 0.5,
                reasoning_trace=[
                    f"Direct plan for {operation}",
                    f"Route: {spec.endpoint}",
                    *([] if valid else [f"Missing params: {missing}"]),
                ],
            )

        return ExecutionPlan(
            intent=f"direct:{operation}",
            operation=operation,
            params=params,
            execution_route="unknown",
            confidence=0.0,
            reasoning_trace=[f"No direct route for {operation}"],
        )

    # ------------------------------------------------------------------
    # Fast path: CapabilityRouter + lightweight extraction
    # ------------------------------------------------------------------

    async def _try_fast_path(
        self, intent: str, trace: list[str], ctx: dict[str, Any],
    ) -> ExecutionPlan | None:
        """Try to resolve intent via CapabilityRouter.

        1. Use DSPy Predict to extract operation + params from intent
        2. Check if operation has a direct route
        3. Validate params against route requirements
        4. Inject selected_ids from context when operation needs IDs
        """
        # Step 1: Try regex-based extraction first (zero LLM calls)
        regex_result = self._regex_extract(intent)
        if regex_result is not None:
            operation, params, conf = regex_result
            # M1: Inject selected_ids when the operation needs IDs but
            # none were found in the intent text.
            params = self._inject_context_ids(operation, params, ctx, trace)
            spec = self._router.route(operation)
            if spec is not None:
                valid, missing = self._router.validate_params(operation, params)
                trace.append(f"Fast path (regex): {operation}")
                return ExecutionPlan(
                    intent=intent,
                    operation=operation,
                    params=params,
                    execution_route="direct_api",
                    route_spec=spec,
                    confidence=conf if valid else conf * 0.5,
                    reasoning_trace=trace + (
                        [f"Missing params: {missing}"] if not valid else []
                    ),
                )

        # Step 2: DSPy extraction
        if not self._ensure_dspy():
            trace.append("DSPy not available, skipping fast path")
            return None

        try:
            extraction = self._extractor(
                user_intent=intent,
                available_operations=self._operation_list,
            )

            operation = str(extraction.operation).strip()
            confidence = _parse_confidence(extraction.confidence)

            if operation == "unknown" or not self._router.has_direct_route(operation):
                trace.append(f"Extractor returned '{operation}' — no direct route")
                return None

            params = _parse_params(extraction.params)
            # M1: Inject context IDs for DSPy path too
            params = self._inject_context_ids(operation, params, ctx, trace)
            spec = self._router.route(operation)
            valid, missing = self._router.validate_params(operation, params)

            if not valid:
                trace.append(
                    f"Fast path: {operation} matched but missing params: {missing}"
                )
                # Still return the plan — the executor can attempt with partial params
                # and the C++ handler will give a clear error

            trace.append(f"Fast path (DSPy): {operation} conf={confidence:.2f}")
            return ExecutionPlan(
                intent=intent,
                operation=operation,
                params=params,
                execution_route="direct_api",
                route_spec=spec,
                confidence=confidence if valid else confidence * 0.5,
                reasoning_trace=trace,
            )

        except Exception as e:
            trace.append(f"Fast path extraction failed: {e}")
            logger.warning(f"Fast path extraction failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Slow path: command resolution via knowledge store + DSPy
    # ------------------------------------------------------------------

    async def _try_command_path(
        self, intent: str, trace: list[str], ctx: dict[str, Any],
    ) -> ExecutionPlan | None:
        """Fall back to command-string resolution.

        This replicates the core logic from HybridInvestigator.execute_intent
        but produces an ExecutionPlan instead of executing directly.
        """
        if self._knowledge_store is None:
            trace.append("No knowledge store — command path unavailable")
            return None

        # Phase A: candidate retrieval
        candidates = self._knowledge_store.search_by_intent(intent)
        if not candidates:
            trace.append("No command candidates found")
            return None

        trace.append(f"Found {len(candidates)} command candidates")

        # Phase B: command selection via DSPy
        selected_command = ""
        selected_mode = "default"
        param_values: dict[str, Any] = {}

        if self._ensure_dspy() and self._intent_resolver:
            try:
                command_candidates = []
                for c in candidates[:5]:
                    cmd = self._knowledge_store.get_command(c.command)
                    if cmd:
                        command_candidates.append({
                            "command": c.command,
                            "modes": list(cmd.modes.keys()),
                            "description": cmd.description,
                        })

                # M1: Feed available geometry from context so DSPy can
                # reference selected objects in its resolution.
                avail_geo = _build_available_geometry(ctx)
                resolution = self._intent_resolver(
                    user_intent=intent,
                    available_geometry=avail_geo,
                    command_candidates=command_candidates,
                    recent_commands=[],
                )

                if hasattr(resolution, "selected_command") and resolution.selected_command:
                    selected_command = resolution.selected_command
                    selected_mode = (
                        resolution.selected_mode
                        if hasattr(resolution, "selected_mode")
                        else "default"
                    )
                    if hasattr(resolution, "parameter_values") and resolution.parameter_values:
                        param_values = dict(resolution.parameter_values)

                    confidence = _parse_confidence(
                        getattr(resolution, "confidence", 0.7)
                    )
                    trace.append(f"DSPy selected: {selected_command} mode={selected_mode}")

            except Exception as e:
                trace.append(f"DSPy command resolution failed: {e}")
                logger.warning(f"DSPy command resolution failed: {e}")

        # Fallback to top candidate
        if not selected_command and candidates:
            selected_command = candidates[0].command
            selected_mode = candidates[0].mode
            confidence = candidates[0].confidence
            trace.append(f"Fallback to top candidate: {selected_command}")

        if not selected_command:
            trace.append("No command selected")
            return None

        # Phase C: syntax resolution
        syntax = self._knowledge_store.get_syntax(selected_command, selected_mode)
        if not syntax:
            syntax = self._knowledge_store.get_syntax(selected_command, "default")
        if not syntax:
            trace.append(f"No syntax for {selected_command} mode={selected_mode}")
            return ExecutionPlan(
                intent=intent,
                operation=f"command:{selected_command}",
                params=param_values,
                execution_route="known_command",
                command=selected_command,
                mode=selected_mode,
                confidence=confidence * 0.5,
                reasoning_trace=trace,
            )

        # Phase D: build full command string
        full_command = syntax
        gotchas = self._knowledge_store.get_gotchas(selected_command)

        # Augment gotchas from knowledge graph
        if self._knowledge_graph:
            gotchas = self._augment_gotchas(
                gotchas, selected_command, intent, trace,
            )

        if self._syntax_builder:
            try:
                # M1: Pass geometry IDs from context so the syntax builder
                # can substitute object references into command strings.
                geo_ids = _build_geometry_ids(ctx)
                built = self._syntax_builder(
                    command_name=selected_command,
                    mode=selected_mode,
                    mode_syntax=syntax,
                    parameter_values=param_values,
                    geometry_ids=geo_ids,
                    gotchas=gotchas,
                )
                if hasattr(built, "full_command") and built.full_command:
                    full_command = built.full_command
            except Exception as e:
                trace.append(f"Syntax builder failed: {e}")
                logger.warning(f"Syntax builder failed: {e}")

        trace.append(f"Command syntax: {full_command}")

        return ExecutionPlan(
            intent=intent,
            operation=f"command:{selected_command}",
            params=param_values,
            execution_route="known_command",
            command=selected_command,
            mode=selected_mode,
            syntax=full_command,
            fallbacks=["interactive"],
            confidence=confidence,
            knowledge_context=gotchas,
            reasoning_trace=trace,
        )

    # ------------------------------------------------------------------
    # DSPy initialization
    # ------------------------------------------------------------------

    def _ensure_dspy(self) -> bool:
        """Lazily initialize DSPy modules. Returns True if available."""
        if not DSPY_AVAILABLE:
            return False

        if self._dspy_configured:
            return True

        if self._dspy_init_failed:
            return False

        try:
            from .dspy_config import is_configured, configure_dspy
            if not is_configured():
                configure_dspy()

            self._extractor = dspy.Predict(ExtractOperation)

            from .dspy_modules import IntentResolver, SyntaxBuilder
            self._intent_resolver = IntentResolver()
            self._syntax_builder = SyntaxBuilder()

            self._dspy_configured = True
            return True
        except Exception as e:
            logger.warning(f"DSPy initialization failed: {e}")
            self._dspy_init_failed = True
            return False

    # ------------------------------------------------------------------
    # Regex extraction (zero LLM calls)
    # ------------------------------------------------------------------

    def _regex_extract(
        self, intent: str,
    ) -> tuple[str, dict[str, Any], float] | None:
        """Try to extract operation + params from common intent patterns.

        This handles the most frequent patterns without any LLM call:
        - "create a {type} at {point} with {dimension} {value}"
        - "move {ids} by {vector}"
        - "delete {ids}"
        - "select all"

        Returns (operation, params, confidence) or None.
        """
        lower = intent.lower().strip()

        # --- Creation patterns (sorted longest-first, word-boundary match) ---
        for type_name, op_name in _CREATE_PATTERNS:
            if re.search(rf"\b{type_name}\b", lower):
                params = _extract_creation_params(lower, type_name)
                if params is not None:
                    return op_name, params, 0.9
                # Type keyword matched but no params extracted.
                # Only return if near a creation verb; otherwise let DSPy handle it.
                if re.search(r"\b(?:create|make|add|draw|build)\b", lower):
                    return op_name, {}, 0.6
                # No creation verb — might be incidental mention, skip
                return None

        # --- Delete / Remove ---
        if re.search(r"\b(?:delete|remove|erase)\b", lower):
            ids = _extract_ids(lower)
            if ids:
                return "delete", {"ids": ids}, 0.95
            # No explicit GUIDs — context may provide selected_ids
            return "delete", {}, 0.7

        # --- Select all ---
        if "select all" in lower:
            return "select_objects", {"all": True}, 0.95

        # --- Move ---
        move_m = re.search(
            r"move\b.*?(?:by\s+)?\[?\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]?",
            lower,
        )
        if move_m:
            vector = [float(move_m.group(i)) for i in (1, 2, 3)]
            ids = _extract_ids(lower)
            params: dict[str, Any] = {"vector": vector}
            if ids:
                params["ids"] = ids
            return "move", params, 0.85

        return None

    # ------------------------------------------------------------------
    # Knowledge graph gotcha augmentation
    # ------------------------------------------------------------------

    def _augment_gotchas(
        self,
        gotchas: list[str],
        command: str,
        intent: str,
        trace: list[str],
    ) -> list[str]:
        """Merge antipatterns from KnowledgeGraphV2 into gotchas list."""
        if not self._knowledge_graph:
            return gotchas

        # Work on a copy to avoid mutating the knowledge store's cached list
        gotchas = list(gotchas)

        try:
            cmd_name = command.lstrip("-_").lower()
            kg_data = self._knowledge_graph.query(intent=f"create {cmd_name}")
            kg_data_intent = self._knowledge_graph.query(intent=intent)

            all_avoid = kg_data.get("avoid", []) + kg_data_intent.get("avoid", [])
            added = 0

            for avoid in all_avoid:
                if isinstance(avoid, dict):
                    reason = avoid.get("reason") or avoid.get("error") or str(avoid)
                else:
                    reason = str(avoid)

                if reason and cmd_name in reason.lower():
                    entry = f"AVOID: {reason}"
                    if entry not in gotchas and reason not in gotchas:
                        gotchas.append(entry)
                        added += 1

            if added > 0:
                trace.append(f"Knowledge graph: {added} avoid patterns")

        except Exception as e:
            logger.debug(f"KG augmentation failed: {e}")

        return gotchas

    # ------------------------------------------------------------------
    # Geometry context injection (M1)
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_context_ids(
        operation: str,
        params: dict[str, Any],
        ctx: dict[str, Any],
        trace: list[str],
    ) -> dict[str, Any]:
        """Inject selected_ids from context when the operation needs IDs.

        Only injects when:
          1. The operation is in _ID_INJECTABLE_OPS
          2. The params don't already have ``ids`` (or ``id`` for single-object ops)
          3. The context has ``selected_ids``

        Returns a (possibly new) params dict — never mutates the input.
        """
        if operation not in _ID_INJECTABLE_OPS:
            return params

        selected = ctx.get("selected_ids", [])
        if not selected:
            return params

        # Single-object ops use "id"; multi-object ops use "ids"
        single_ops = {"fillet_edge", "chamfer_edge"}
        if operation in single_ops:
            if "id" not in params and len(selected) >= 1:
                params = {**params, "id": selected[0]}
                trace.append(f"Injected selected object for {operation}")
        else:
            if "ids" not in params:
                params = {**params, "ids": selected}
                trace.append(f"Injected {len(selected)} selected IDs for {operation}")

        return params


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Sorted longest-first so "polyline" matches before "line", "rectangle" before "arc", etc.
_CREATE_PATTERNS: list[tuple[str, str]] = sorted(
    [
        ("sphere", "create_sphere"),
        ("box", "create_box"),
        ("cylinder", "create_cylinder"),
        ("cone", "create_cone"),
        ("circle", "create_circle"),
        ("arc", "create_arc"),
        ("line", "create_line"),
        ("point", "create_point"),
        ("rectangle", "create_rectangle"),
        ("polyline", "create_polyline"),
    ],
    key=lambda t: len(t[0]),
    reverse=True,
)

_COORD_RE = re.compile(
    r"\[?\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]?"
)
_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")
_GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _extract_creation_params(
    lower: str, type_name: str,
) -> dict[str, Any] | None:
    """Extract typed creation params from intent text.

    Handles patterns like:
        "at 0,0,0 with radius 5"
        "center 0,0,0 radius 5"
        "from 0,0,0 to 10,10,10"
        "width 10 height 5 depth 8"
    """
    params: dict[str, Any] = {}

    # Extract coordinates
    coords = _COORD_RE.findall(lower)
    if coords:
        first_coord = [float(x) for x in coords[0]]
        second_coord = [float(x) for x in coords[1]] if len(coords) >= 2 else None

        if type_name in ("line",):
            if second_coord is not None:
                params["start"] = first_coord
                params["end"] = second_coord
                return params
            return None

        # Support corner-to-corner box/rectangle specs like:
        # "box from 0,0,0 to 10,10,5"
        if second_coord is not None and type_name in ("box", "rectangle"):
            mins = [
                min(first_coord[0], second_coord[0]),
                min(first_coord[1], second_coord[1]),
                min(first_coord[2], second_coord[2]),
            ]
            deltas = [
                abs(second_coord[0] - first_coord[0]),
                abs(second_coord[1] - first_coord[1]),
                abs(second_coord[2] - first_coord[2]),
            ]
            params["origin"] = mins
            if type_name == "box":
                params.setdefault("width", deltas[0])
                params.setdefault("depth", deltas[1])
                params.setdefault("height", deltas[2])
            else:
                params.setdefault("width", deltas[0])
                params.setdefault("height", deltas[1])
            return params

        # First coordinate is center/origin
        center_key = "origin" if type_name in ("box", "rectangle") else "center"
        if type_name == "point":
            center_key = "location"
        params[center_key] = first_coord

    # Extract named dimensions
    for dim_name in ("radius", "width", "height", "depth", "distance",
                     "startAngle", "endAngle", "factor"):
        m = re.search(rf"{dim_name}\s*[:=]?\s*([-+]?\d*\.?\d+)", lower)
        if m:
            params[dim_name] = float(m.group(1))

    # Type-specific defaults
    if type_name == "sphere" and "radius" not in params:
        # Look for bare number after "sphere" that isn't part of a named dimension
        after = lower.split("sphere", 1)[1]
        # Remove coordinate triples and named dimension values
        cleaned = _COORD_RE.sub("", after)
        for dim in ("radius", "width", "height", "depth", "distance",
                     "startAngle", "endAngle", "factor"):
            cleaned = re.sub(rf"{dim}\s*[:=]?\s*[-+]?\d*\.?\d+", "", cleaned)
        bare_nums = _NUMBER_RE.findall(cleaned)
        if bare_nums:
            val = float(bare_nums[-1])
            if val > 0:
                params["radius"] = val

    if type_name in ("box", "rectangle", "cylinder", "cone"):
        # Try "10 by 8 by 6" pattern
        by_match = re.search(
            r"(\d+\.?\d*)\s*(?:by|x)\s*(\d+\.?\d*)(?:\s*(?:by|x)\s*(\d+\.?\d*))?",
            lower,
        )
        if by_match:
            if "width" not in params:
                params["width"] = float(by_match.group(1))
            if "depth" not in params and by_match.group(2):
                if type_name in ("box",):
                    params["depth"] = float(by_match.group(2))
                elif type_name in ("rectangle",):
                    params["height"] = float(by_match.group(2))
            if "height" not in params and by_match.group(3):
                params["height"] = float(by_match.group(3))

    if not params:
        return None
    return params


def _extract_ids(text: str) -> list[str]:
    """Extract GUID-like IDs from text."""
    return _GUID_RE.findall(text)


def _parse_confidence(value: Any) -> float:
    """Safely parse a confidence value from DSPy output."""
    try:
        f = float(value)
        return max(0.0, min(1.0, f))
    except (TypeError, ValueError):
        return 0.5


def _parse_params(value: Any) -> dict[str, Any]:
    """Safely parse params dict from DSPy output."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            import json
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


# ---------------------------------------------------------------------------
# Geometry context helpers (M1)
# ---------------------------------------------------------------------------

# Operations that require object IDs and can use the current selection
# when no IDs are specified in the intent text.
_ID_INJECTABLE_OPS: frozenset[str] = frozenset({
    "move", "rotate", "scale", "mirror", "copy", "delete",
    "boolean_union", "boolean_difference", "boolean_intersection", "boolean_split",
    "fillet_edge", "chamfer_edge",
    "join_curves", "create_group",
    "assign_material",
    "uv_box_mapping", "uv_planar_mapping", "uv_cylinder_mapping", "uv_sphere_mapping",
    "tag_semantic", "validate_export", "game_export",
    "export_file",
})


def _build_available_geometry(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the ``available_geometry`` list for the DSPy IntentResolver.

    The IntentResolver signature expects a list of dicts describing objects
    available in the scene.  We build lightweight descriptors from context.
    """
    selected = ctx.get("selected_ids", [])
    types = ctx.get("geometry_types", {})
    if not selected:
        return []
    return [
        {"id": gid, "type": types.get(gid, "object")}
        for gid in selected
    ]


def _build_geometry_ids(ctx: dict[str, Any]) -> dict[str, str]:
    """Build the ``geometry_ids`` dict for the DSPy SyntaxBuilder.

    Maps placeholder names to GUIDs.  When the context has selected objects,
    we expose them as ``selected_0``, ``selected_1``, etc.
    """
    selected = ctx.get("selected_ids", [])
    if not selected:
        return {}
    return {f"selected_{i}": gid for i, gid in enumerate(selected)}
