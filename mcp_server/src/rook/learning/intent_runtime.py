"""Intent Runtime: typed execution plans, capability routing, and structured failures.

Replaces the monolithic execute_intent pattern with a layered intent runtime
that routes operations through the most reliable execution substrate available.

Architecture:

    IntentPlanner (P1)           <- natural language -> typed plan
           |
    CapabilityRouter (P0)        <- operation -> direct API route
           |
    SmartExecutor (P2)           <- plan -> direct/command/interactive cascade
           |
    TypedReflection (P3)         <- failure -> typed, layer-tagged correction

P0 (this module) provides:
  - ExecutionPlan: typed intermediate representation between planning and execution
  - ExecutionResult: structured success/failure response with trace
  - ExecutionFailure: layer-tagged failure for precise correction recording
  - CapabilityRouter: maps ~95 semantic operations to direct HTTP endpoints
  - RouteSpec: specification for a single direct API route

The CapabilityRouter is the highest-leverage change: operations that have typed
HTTP handlers (e.g. /create, /transform, /curve/join) skip DSPy command
resolution entirely. DSPy is preserved for the long tail of Rhino commands
that only exist as command strings (Loft, Sweep, Pipe, NetworkSrf, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("rook.learning.intent_runtime")


# ---------------------------------------------------------------------------
# Failure typing
# ---------------------------------------------------------------------------

class FailureLayer(str, Enum):
    """Where in the execution pipeline a failure occurred.

    Each layer implies a different correction strategy:
      PLANNING           -> intent was misunderstood, re-parse
      ROUTING            -> wrong execution substrate chosen
      PARAMETER_SYNTHESIS -> correct operation but wrong/missing params
      COMMAND_EXECUTION   -> command string was malformed or Rhino rejected it
      INTERACTIVE_PROMPT  -> command stalled waiting for input we didn't provide
      WRONG_RESULT        -> execution succeeded but produced wrong geometry
      TIMEOUT             -> Rhino UI thread didn't respond in time
    """
    PLANNING = "planning"
    ROUTING = "routing"
    PARAMETER_SYNTHESIS = "parameter_synthesis"
    COMMAND_EXECUTION = "command_execution"
    INTERACTIVE_PROMPT = "interactive_prompt"
    WRONG_RESULT = "wrong_result"
    TIMEOUT = "timeout"


@dataclass
class ExecutionFailure:
    """Typed, layer-tagged failure for precise correction recording."""
    layer: FailureLayer
    operation: str
    attempted_route: str
    error_detail: str
    recovery_suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "layer": self.layer.value,
            "operation": self.operation,
            "attempted_route": self.attempted_route,
            "error_detail": self.error_detail,
        }
        if self.recovery_suggestion:
            d["recovery_suggestion"] = self.recovery_suggestion
        return d

    def to_correction(self) -> dict[str, Any]:
        """Format for knowledge_record storage in the learning loop.

        Deprecated: Use TypedReflection.reflect() for richer corrections
        with diagnosis, gap_type, and full knowledge_record() compatibility.
        """
        return {
            "type": "execution_failure",
            "layer": self.layer.value,
            "operation": self.operation,
            "route": self.attempted_route,
            "error": self.error_detail,
            "suggestion": self.recovery_suggestion,
        }


# ---------------------------------------------------------------------------
# Route specification
# ---------------------------------------------------------------------------

@dataclass
class RouteSpec:
    """Specification for a direct HTTP API route on the C++ plugin.

    When the CapabilityRouter finds a match, the executor builds the payload as:
        payload = {**base_params, **user_params}
    and calls:
        call_rhino(endpoint, method, payload)
    """
    endpoint: str
    method: str = "POST"
    base_params: dict[str, Any] = field(default_factory=dict)
    required_params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()
    description: str = ""


# ---------------------------------------------------------------------------
# Execution plan and result
# ---------------------------------------------------------------------------

@dataclass
class ExecutionPlan:
    """A typed, inspectable execution plan for a Rhino operation.

    This is the intermediate representation between intent parsing (P1) and
    execution (P2). It carries everything needed to execute without re-parsing
    the original intent.
    """
    intent: str
    operation: str
    params: dict[str, Any] = field(default_factory=dict)
    execution_route: str = "unknown"  # direct_api | known_command | interactive | unknown

    # Direct API fields (set when execution_route == "direct_api")
    route_spec: RouteSpec | None = None

    # Command path fields (set when execution_route in ("known_command", "interactive"))
    command: str | None = None
    mode: str | None = None
    syntax: str | None = None

    # Metadata
    fallbacks: list[str] = field(default_factory=list)
    confidence: float = 0.0
    knowledge_context: list[str] = field(default_factory=list)
    reasoning_trace: list[str] = field(default_factory=list)
    time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "intent": self.intent,
            "operation": self.operation,
            "params": self.params,
            "execution_route": self.execution_route,
            "confidence": self.confidence,
        }
        if self.time_ms > 0:
            d["time_ms"] = round(self.time_ms, 1)
        if self.route_spec:
            d["endpoint"] = self.route_spec.endpoint
        if self.command:
            d["command"] = self.command
        if self.mode:
            d["mode"] = self.mode
        if self.syntax:
            d["syntax"] = self.syntax
        if self.fallbacks:
            d["fallbacks"] = self.fallbacks
        if self.knowledge_context:
            d["knowledge_context"] = self.knowledge_context
        if self.reasoning_trace:
            d["reasoning_trace"] = self.reasoning_trace
        return d


@dataclass
class ExecutionResult:
    """Structured result from executing a plan."""
    success: bool
    intent: str
    plan_summary: dict[str, Any] = field(default_factory=dict)

    # Success data
    created_ids: list[str] = field(default_factory=list)
    objects_created: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    # Failure data
    failure: ExecutionFailure | None = None

    # Execution metadata
    route_taken: str = ""
    time_ms: float = 0.0
    reasoning_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "success": self.success,
            "intent": self.intent,
            "plan": self.plan_summary,
            "route_taken": self.route_taken,
            "time_ms": round(self.time_ms, 1),
        }
        if self.success:
            d["created_ids"] = self.created_ids
            d["objects_created"] = self.objects_created
            if self.data:
                d["data"] = self.data
        if self.failure:
            d["failure"] = self.failure.to_dict()
        if self.reasoning_trace:
            d["trace"] = self.reasoning_trace
        return d


# ---------------------------------------------------------------------------
# Route table: 95 semantic operations -> direct HTTP endpoints
# ---------------------------------------------------------------------------

def _build_route_table() -> dict[str, RouteSpec]:
    """Build the complete operation -> route mapping.

    Covers every typed HTTP handler in the C++ plugin (RookNative).
    Operations not in this table fall through to command-string resolution.
    """
    routes: dict[str, RouteSpec] = {}

    # === Creation: NURBS primitives via /create ===
    _create_types: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
        "create_point": (
            "POINT", ("location",), ("name", "layer", "color"),
        ),
        "create_line": (
            "LINE", ("start", "end"), ("name", "layer", "color"),
        ),
        "create_polyline": (
            "POLYLINE", ("points",), ("name", "layer", "color"),
        ),
        "create_circle": (
            "CIRCLE", ("center", "radius"), ("plane", "name", "layer", "color"),
        ),
        "create_arc": (
            "ARC", ("center", "radius", "startAngle", "endAngle"),
            ("plane", "name", "layer", "color"),
        ),
        "create_rectangle": (
            "RECTANGLE", ("origin", "width", "height"), ("name", "layer", "color"),
        ),
        "create_box": (
            "BOX", ("origin", "width", "depth", "height"), ("name", "layer", "color"),
        ),
        "create_sphere": (
            "SPHERE", ("center", "radius"), ("name", "layer", "color"),
        ),
        "create_cylinder": (
            "CYLINDER", ("center", "radius", "height"), ("name", "layer", "color"),
        ),
        "create_cone": (
            "CONE", ("center", "radius", "height"), ("name", "layer", "color"),
        ),
        "create_extrusion": (
            "EXTRUDE", ("curveId", "direction", "distance"),
            ("cap", "name", "layer", "color"),
        ),
        "create_interpolated_curve": (
            "INTERPOLATED_CURVE", ("points",), ("degree", "name", "layer", "color"),
        ),
        "create_control_point_curve": (
            "CONTROL_POINT_CURVE", ("points",), ("degree", "name", "layer", "color"),
        ),
    }
    for op, (type_val, req, opt) in _create_types.items():
        routes[op] = RouteSpec(
            endpoint="/create",
            base_params={"type": type_val},
            required_params=req,
            optional_params=opt,
            description=f"Create {type_val.lower().replace('_', ' ')}",
        )

    # === Creation: Phase 1 typed surface routes ===
    # Plan: rook_docs/2026-04-17-typed-route-phase1-plan.md
    # Semantic constraints enforced natively:
    #   - Pipe: radius XOR startRadius+endRadius
    #   - Loft: closed=true incompatible with startPoint/endPoint
    routes["create_pipe"] = RouteSpec(
        endpoint="/surface/pipe",
        required_params=("curveId",),
        optional_params=(
            "radius", "startRadius", "endRadius",
            "cap", "tolerance",
            "name", "layer", "color", "visible",
        ),
        description="Create pipe brep along rail curve",
    )
    routes["create_loft"] = RouteSpec(
        endpoint="/surface/loft",
        required_params=("curveIds",),
        optional_params=(
            "loftType", "closed",
            "startPoint", "endPoint",
            # `tolerance` intentionally omitted — Brep.CreateFromLoft's
            # non-refit overload uses doc tolerance implicitly. Honoring a
            # caller-supplied value requires CreateFromLoftRefit (different
            # semantics) and is deferred to a future PR.
            "name", "layer", "color", "visible",
        ),
        description="Create lofted brep(s) through 2+ profile curves",
    )
    routes["create_sweep1"] = RouteSpec(
        endpoint="/surface/sweep1",
        required_params=("railId", "profileIds"),
        optional_params=(
            "closed", "style", "roadlikeUp",
            "name", "layer", "color", "visible",
        ),
        description="Sweep profile(s) along one rail",
    )
    routes["create_sweep2"] = RouteSpec(
        endpoint="/surface/sweep2",
        required_params=("rail1Id", "rail2Id", "profileIds"),
        optional_params=(
            "closed", "maintainHeight",
            "name", "layer", "color", "visible",
        ),
        description="Sweep profile(s) between two rails",
    )
    routes["create_revolve"] = RouteSpec(
        endpoint="/surface/revolve",
        required_params=("curveId", "axisStart", "axisEnd"),
        optional_params=(
            "startAngle", "endAngle",
            # `tolerance` intentionally omitted — RevSurface.ToBrep() takes
            # no tolerance parameter. Same API-limitation rationale as Loft.
            "name", "layer", "color", "visible",
        ),
        description="Revolve a curve around a line axis",
    )
    routes["array_linear"] = RouteSpec(
        endpoint="/array/linear",
        required_params=("ids", "direction", "spacing", "count"),
        optional_params=(),
        description="Array objects along a direction vector",
    )
    routes["array_rectangular"] = RouteSpec(
        endpoint="/array/rectangular",
        required_params=("ids", "xCount", "yCount", "xSpacing", "ySpacing"),
        optional_params=("zCount", "zSpacing"),
        description="Array objects in an X/Y/Z grid aligned to the active CPlane",
    )
    routes["array_polar"] = RouteSpec(
        endpoint="/array/polar",
        required_params=("ids", "center", "count"),
        optional_params=("axis", "angle", "rotate"),
        description="Polar (rotational) array around a center + axis",
    )

    # === Creation: Phase 2 typed annotation routes ===
    # Plan: rook_docs/2026-04-19-typed-route-phase2-plan.md
    routes["create_text"] = RouteSpec(
        endpoint="/annotation/text",
        required_params=("text",),
        optional_params=(
            "point", "height", "font", "bold", "italic",
            "name", "layer", "color", "visible",
        ),
        description="Create a 2D text annotation (direct-sdk native; preserves annotation-level typography overrides)",
    )
    routes["create_dim_linear"] = RouteSpec(
        endpoint="/annotation/dim-linear",
        required_params=("start", "end", "offset"),
        optional_params=(
            "direction",
            "name", "layer", "color", "visible",
        ),
        description="Create a LINEAR dimension — measures projected distance of (end-start) onto direction (default world X), NOT direct Euclidean",
    )

    # === Creation: mesh primitives ===
    routes["create_mesh_box"] = RouteSpec(
        endpoint="/mesh/box",
        required_params=("width", "depth", "height"),
        optional_params=("origin", "xCount", "yCount", "zCount"),
        description="Create mesh box",
    )
    routes["create_mesh_sphere"] = RouteSpec(
        endpoint="/mesh/sphere",
        required_params=("radius",),
        optional_params=("center", "rings", "segments"),
        description="Create mesh sphere",
    )
    routes["create_mesh_cylinder"] = RouteSpec(
        endpoint="/mesh/cylinder",
        required_params=("radius", "height"),
        optional_params=("center", "vertical", "around"),
        description="Create mesh cylinder",
    )
    routes["create_mesh_cone"] = RouteSpec(
        endpoint="/mesh/cone",
        required_params=("radius", "height"),
        optional_params=("center", "vertical", "around"),
        description="Create mesh cone",
    )

    # === Creation: SubD primitives ===
    routes["create_subd_box"] = RouteSpec(
        endpoint="/subd/box",
        required_params=("width", "depth", "height"),
        optional_params=("origin", "xFaces", "yFaces", "zFaces"),
        description="Create SubD box",
    )
    routes["create_subd_sphere"] = RouteSpec(
        endpoint="/subd/sphere",
        required_params=("radius",),
        optional_params=("center", "divisions"),
        description="Create SubD sphere",
    )
    routes["create_subd_cylinder"] = RouteSpec(
        endpoint="/subd/cylinder",
        required_params=("radius", "height"),
        optional_params=("center", "circumferenceFaces", "heightFaces"),
        description="Create SubD cylinder",
    )

    # === Transform operations ===
    routes["move"] = RouteSpec(
        endpoint="/transform",
        base_params={"operation": "move"},
        required_params=("ids", "vector"),
        description="Move objects by vector",
    )
    routes["rotate"] = RouteSpec(
        endpoint="/transform",
        base_params={"operation": "rotate"},
        required_params=("ids", "angle"),
        optional_params=("axis", "center"),
        description="Rotate objects",
    )
    routes["scale"] = RouteSpec(
        endpoint="/transform",
        base_params={"operation": "scale"},
        required_params=("ids", "factor"),
        optional_params=("center",),
        description="Scale objects",
    )
    routes["mirror"] = RouteSpec(
        endpoint="/transform",
        base_params={"operation": "mirror"},
        required_params=("ids", "planeOrigin", "planeNormal"),
        description="Mirror objects",
    )
    routes["copy"] = RouteSpec(
        endpoint="/copy",
        required_params=("ids",),
        optional_params=("offset",),
        description="Copy objects",
    )
    routes["delete"] = RouteSpec(
        endpoint="/delete",
        required_params=("ids",),
        description="Delete objects",
    )

    # === Boolean operations (typed params, RunScript internally) ===
    for bool_op in ("union", "difference", "intersection", "split"):
        routes[f"boolean_{bool_op}"] = RouteSpec(
            endpoint="/boolean",
            base_params={"operation": bool_op},
            required_params=("ids",),
            optional_params=("keepOriginals",),
            description=f"Boolean {bool_op}",
        )

    # === Edge operations (typed params, RunScript internally) ===
    routes["fillet_edge"] = RouteSpec(
        endpoint="/fillet",
        required_params=("id", "radius"),
        description="Fillet brep edges",
    )
    routes["chamfer_edge"] = RouteSpec(
        endpoint="/chamfer",
        required_params=("id", "distance"),
        description="Chamfer brep edges",
    )

    # === Offset ===
    routes["offset_brep"] = RouteSpec(
        endpoint="/offset/brep",
        required_params=("brepId", "distance"),
        optional_params=("extend", "shrink", "solid"),
        description="Offset brep surface",
    )

    # === Curve operations ===
    routes["join_curves"] = RouteSpec(
        endpoint="/curve/join",
        required_params=("ids",),
        description="Join curves",
    )
    routes["explode_curve"] = RouteSpec(
        endpoint="/curve/explode",
        required_params=("id",),
        description="Explode polycurve into segments",
    )
    routes["divide_curve"] = RouteSpec(
        endpoint="/curve/divide",
        required_params=("id", "count"),
        description="Divide curve into points",
    )
    routes["extend_curve"] = RouteSpec(
        endpoint="/curve/extend",
        required_params=("id", "end", "length"),
        description="Extend curve",
    )
    routes["trim_curve"] = RouteSpec(
        endpoint="/curve/trim",
        required_params=("id",),
        optional_params=("parameter", "point"),
        description="Trim curve",
    )
    routes["split_curve"] = RouteSpec(
        endpoint="/curve/split",
        required_params=("id", "parameter"),
        description="Split curve at parameter",
    )
    routes["rebuild_curve"] = RouteSpec(
        endpoint="/curve/rebuild",
        required_params=("id",),
        optional_params=("degree", "pointCount"),
        description="Rebuild curve",
    )
    routes["fillet_curves"] = RouteSpec(
        endpoint="/curve/fillet",
        required_params=("id1", "id2", "radius"),
        description="Fillet between two curves",
    )
    routes["project_curve"] = RouteSpec(
        endpoint="/curve/project",
        required_params=("curveIds", "brepIds", "direction"),
        description="Project curves onto surfaces",
    )
    routes["pull_curve"] = RouteSpec(
        endpoint="/curve/pull",
        required_params=("curveId", "brepId"),
        optional_params=("faceIndex",),
        description="Pull curve to surface",
    )
    routes["offset_curve"] = RouteSpec(
        endpoint="/curve/offset",
        required_params=("curveId", "distance"),
        optional_params=("plane", "cornerStyle"),
        description="Offset curve in plane",
    )
    routes["offset_curve_on_surface"] = RouteSpec(
        endpoint="/curve/offset-on-surface",
        required_params=("curveId", "surfaceId", "distance"),
        description="Offset curve on surface",
    )

    # === Intersection operations ===
    routes["intersect_curves"] = RouteSpec(
        endpoint="/intersect/curves",
        required_params=("curveId1", "curveId2"),
        optional_params=("tolerance",),
        description="Curve-curve intersection",
    )
    routes["intersect_curve_surface"] = RouteSpec(
        endpoint="/intersect/curve-surface",
        required_params=("curveId", "surfaceId"),
        optional_params=("tolerance",),
        description="Curve-surface intersection",
    )
    routes["intersect_curve_brep"] = RouteSpec(
        endpoint="/intersect/curve-brep",
        required_params=("curveId", "brepId"),
        optional_params=("tolerance",),
        description="Curve-brep intersection",
    )
    routes["intersect_breps"] = RouteSpec(
        endpoint="/intersect/breps",
        required_params=("brepId1", "brepId2"),
        optional_params=("tolerance",),
        description="Brep-brep intersection",
    )
    routes["intersect_plane"] = RouteSpec(
        endpoint="/intersect/plane",
        required_params=("brepId", "planeOrigin", "planeNormal"),
        optional_params=("tolerance",),
        description="Intersect brep with plane",
    )

    # === Split / Trim ===
    routes["split_brep"] = RouteSpec(
        endpoint="/split/brep",
        required_params=("brepId",),
        optional_params=("planeOrigin", "planeNormal", "cutterIds"),
        description="Split brep with plane or cutters",
    )
    routes["trim_brep"] = RouteSpec(
        endpoint="/trim/brep",
        required_params=("brepId", "planeOrigin", "planeNormal", "keepSide"),
        description="Trim brep keeping one side",
    )
    routes["split_face"] = RouteSpec(
        endpoint="/split/face",
        required_params=("brepId", "faceIndex", "curveIds"),
        description="Split brep face with curves",
    )
    routes["split_disjoint_breps"] = RouteSpec(
        endpoint="/split/disjoint-breps",
        optional_params=("ids", "layer", "redraw"),
        description="Separate disjoint Breps into individual connected components",
    )

    # === Mesh operations ===
    routes["mesh_from_brep"] = RouteSpec(
        endpoint="/mesh/from-brep",
        required_params=("brepId",),
        optional_params=("density", "minEdgeLength", "maxEdgeLength", "jagged", "simple"),
        description="Create mesh from brep",
    )
    routes["mesh_boolean"] = RouteSpec(
        endpoint="/mesh/boolean",
        required_params=("meshIds", "operation"),
        optional_params=("deleteInputs",),
        description="Boolean operation on meshes",
    )
    routes["mesh_repair"] = RouteSpec(
        endpoint="/mesh/repair",
        required_params=("meshId",),
        optional_params=("fillHoles", "rebuildNormals"),
        description="Repair mesh",
    )
    routes["mesh_smooth"] = RouteSpec(
        endpoint="/mesh/smooth",
        required_params=("meshId",),
        optional_params=("factor", "iterations"),
        description="Smooth mesh",
    )
    routes["mesh_weld"] = RouteSpec(
        endpoint="/mesh/weld",
        required_params=("meshId",),
        optional_params=("angle",),
        description="Weld mesh vertices",
    )
    routes["mesh_unweld"] = RouteSpec(
        endpoint="/mesh/unweld",
        required_params=("meshId",),
        optional_params=("angle",),
        description="Unweld mesh vertices",
    )
    routes["mesh_reduce"] = RouteSpec(
        endpoint="/mesh/reduce",
        required_params=("meshId", "targetCount"),
        optional_params=("accuracy",),
        description="Reduce mesh face count",
    )
    routes["quad_remesh"] = RouteSpec(
        endpoint="/mesh/quad-remesh",
        required_params=("meshId",),
        optional_params=("targetQuadCount", "adaptive"),
        description="Quad remesh",
    )

    # === SubD operations ===
    routes["subd_from_mesh"] = RouteSpec(
        endpoint="/subd/from-mesh",
        required_params=("meshId",),
        optional_params=("interpolateVertices",),
        description="Create SubD from mesh",
    )
    routes["subd_from_surface"] = RouteSpec(
        endpoint="/subd/from-surface",
        required_params=("brepId",),
        optional_params=("method",),
        description="Create SubD from surface",
    )
    routes["subd_subdivide"] = RouteSpec(
        endpoint="/subd/subdivide",
        required_params=("subdId",),
        optional_params=("level",),
        description="Subdivide SubD",
    )
    routes["subd_crease"] = RouteSpec(
        endpoint="/subd/crease",
        required_params=("subdId", "edgeIndices"),
        optional_params=("crease",),
        description="Set SubD edge creases",
    )
    routes["subd_to_brep"] = RouteSpec(
        endpoint="/subd/to-brep",
        required_params=("subdId",),
        optional_params=("packFaces",),
        description="Convert SubD to brep",
    )
    routes["subd_to_mesh"] = RouteSpec(
        endpoint="/subd/to-mesh",
        required_params=("subdId",),
        optional_params=("density",),
        description="Convert SubD to mesh",
    )

    # === Layer operations ===
    routes["create_layer"] = RouteSpec(
        endpoint="/layers",
        required_params=("name",),
        optional_params=("parent", "color", "visible", "locked"),
        description="Create layer",
    )
    routes["delete_layer"] = RouteSpec(
        endpoint="/layers",
        method="DELETE",
        required_params=("name",),
        description="Delete layer",
    )
    routes["set_layer_visibility"] = RouteSpec(
        endpoint="/layers/visibility",
        required_params=("name", "visible"),
        description="Show/hide layer",
    )
    routes["lock_layer"] = RouteSpec(
        endpoint="/layers/lock",
        required_params=("name", "locked"),
        description="Lock/unlock layer",
    )
    routes["set_current_layer"] = RouteSpec(
        endpoint="/layers/current",
        required_params=("name",),
        description="Set current layer",
    )
    routes["set_layer_properties"] = RouteSpec(
        endpoint="/layers/properties",
        required_params=("name", "set"),
        description="Set layer properties (rename, parent, color, etc.)",
    )
    routes["set_layer_properties_batch"] = RouteSpec(
        endpoint="/layers/properties-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch set layer properties; per-item {name, set}",
    )

    # === Block operations ===
    routes["create_block"] = RouteSpec(
        endpoint="/block/create",
        required_params=("ids", "name", "basePoint"),
        optional_params=("replaceWithInstance",),
        description="Create block definition",
    )
    routes["insert_block"] = RouteSpec(
        endpoint="/block/insert",
        required_params=("name", "point"),
        optional_params=("scale", "rotation"),
        description="Insert block instance",
    )
    routes["explode_block"] = RouteSpec(
        endpoint="/block/explode",
        required_params=("id",),
        description="Explode block instance",
    )
    routes["delete_block"] = RouteSpec(
        endpoint="/block",
        method="DELETE",
        required_params=("name",),
        optional_params=("deleteInstances",),
        description="Delete block definition",
    )
    routes["rename_block"] = RouteSpec(
        endpoint="/block/rename",
        required_params=("name", "newName"),
        description="Rename block",
    )

    # Block-definition object property mutation (single + batch pairs).
    #
    # Router-coverage scope (intentional, narrower than handler capability):
    #   The handlers for set_block_materials / colors / user_strings accept
    #   either a bulk value OR per-object `mappings` (XOR; handler enforces
    #   "at least one"). CapabilityRouter.validate_params() only checks
    #   required_params, so it cannot express that XOR — encoding both shapes
    #   would let an incomplete payload {name: "X"} pass router validation
    #   and only fail downstream in the HTTP handler. To prevent that
    #   degraded failure mode, the router exposes ONLY the bulk path
    #   (required = "name" + the bulk field) and treats the `mappings` path
    #   as router-unreachable for now. Per-index `mappings` payloads remain
    #   reachable via the MCP tool directly.
    #   See rook_docs/2026-04-14-intent-runtime-followups.md for the deferred
    #   architectural fix (RouteSpec `requires_one_of`) and other followups.
    #
    # set_block_object_names single is intentionally asymmetric with its
    # batch: single requires per-object `mappings`, batch takes per-item
    # `objectName`. That asymmetry is in the handler itself, not the router.
    routes["set_block_layers"] = RouteSpec(
        endpoint="/block/set-layers",
        required_params=("name", "layer"),
        description="Route all objects within a block definition to a layer",
    )
    routes["set_block_layers_batch"] = RouteSpec(
        endpoint="/block/set-layers-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch set block object layers; per-item {name, layer}",
    )
    routes["set_block_materials"] = RouteSpec(
        endpoint="/block/set-materials",
        required_params=("name", "material"),
        description="Set bulk material on all objects within a block definition (router covers bulk path only; per-index mappings stays MCP-direct)",
    )
    routes["set_block_materials_batch"] = RouteSpec(
        endpoint="/block/set-materials-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch set block object materials; per-item {name, material}",
    )
    routes["set_block_object_colors"] = RouteSpec(
        endpoint="/block/set-object-colors",
        required_params=("name", "color"),
        description="Set bulk color on all objects within a block definition (router covers bulk path only; per-index mappings stays MCP-direct)",
    )
    routes["set_block_object_colors_batch"] = RouteSpec(
        endpoint="/block/set-object-colors-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch set block object colors; per-item {name, color}",
    )
    routes["set_block_object_user_strings"] = RouteSpec(
        endpoint="/block/set-object-user-strings",
        required_params=("name", "userStrings"),
        description="Stamp bulk user strings on all objects within a block definition (router covers bulk path only; per-index mappings stays MCP-direct)",
    )
    routes["set_block_object_user_strings_batch"] = RouteSpec(
        endpoint="/block/set-object-user-strings-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch set block object user strings; per-item {name, userStrings}",
    )
    routes["set_block_object_names"] = RouteSpec(
        endpoint="/block/set-object-names",
        required_params=("name", "mappings"),
        description="Set object names within a block definition (per-index mappings)",
    )
    routes["set_block_object_names_batch"] = RouteSpec(
        endpoint="/block/set-object-names-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch set block object names; per-item {name, objectName}",
    )
    routes["transform_block_instance"] = RouteSpec(
        endpoint="/block/transform-instance",
        required_params=("id",),
        optional_params=("move", "rotate", "scale", "mirror"),
        description="Apply incremental transforms to a block instance",
    )
    routes["transform_block_instance_batch"] = RouteSpec(
        endpoint="/block/transform-instance-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch apply incremental transforms to block instances; per-item {id, ...}",
    )

    # Historical block tools — coverage expansion to close the substrate gap
    # that pre-dates the batch-tools work. Same scope discipline as the prior
    # intent-runtime PR: only routes that fit cleanly under the current
    # validate_params() model (required-field check only) are exposed here.
    # Tools with multi-shape XOR (block_array_instances / rebase / rebase_recursive
    # / set_instance_properties / user_strings) and the bulk-shape variants of
    # set_block_materials / colors / user_strings / instance_visibility are
    # documented as router-deferred in
    # rook_docs/2026-04-14-intent-runtime-followups.md and remain MCP-direct
    # callable. The architectural fix (RouteSpec.requires_one_of) unblocks them.
    #
    # set_block_instance_visibility: only the single-id shape is exposed (the
    # bulk `ids` shape is the same XOR pattern). Same precedent as the bulk-
    # only routes from PR #18.
    routes["purge_blocks"] = RouteSpec(
        endpoint="/block/purge",
        optional_params=("unused", "deleted"),
        description="Purge unused or deleted block definitions",
    )
    routes["replace_block_geometry"] = RouteSpec(
        endpoint="/block/replace-geometry",
        required_params=("name", "ids"),
        optional_params=("deleteOriginals",),
        description="Replace a block definition's full geometry with one or more document objects",
    )
    routes["replace_block_object_geometry"] = RouteSpec(
        endpoint="/block/replace-object-geometry",
        required_params=("name", "index", "sourceId"),
        optional_params=("deleteOriginal",),
        description="Replace a single object within a block definition (by index) with a document object",
    )
    routes["transform_block_object"] = RouteSpec(
        endpoint="/block/transform-object",
        required_params=("name", "indices", "transform"),
        description="Transform (move/rotate/scale) objects within a block definition by index",
    )
    routes["replace_block_instance"] = RouteSpec(
        endpoint="/block/replace-instance",
        required_params=("instanceId", "newBlockName"),
        description="Swap a block instance's definition (e.g., RAILING WEST 2 → RAILING WEST)",
    )
    routes["replace_block_instance_batch"] = RouteSpec(
        endpoint="/block/replace-instance-batch",
        required_params=("items",),
        optional_params=("redraw",),
        description="Batch swap block instances to different definitions; per-item {id, newBlockName}",
    )
    routes["reset_block_instance_scale"] = RouteSpec(
        endpoint="/block/reset-scale",
        required_params=("id",),
        optional_params=("mode",),
        description="Reset a block instance's scale to 1.0",
    )
    routes["link_block"] = RouteSpec(
        endpoint="/block/link",
        required_params=("path", "name"),
        optional_params=("updateType", "insertionPoint"),
        description="Link a block definition to an external file",
    )
    routes["unlink_block"] = RouteSpec(
        endpoint="/block/unlink",
        required_params=("name",),
        description="Unlink a block definition from its external file",
    )
    routes["refresh_block"] = RouteSpec(
        endpoint="/block/refresh",
        required_params=("name",),
        description="Refresh a linked block definition from its external file",
    )
    routes["find_block_instances"] = RouteSpec(
        endpoint="/block/find-instances",
        optional_params=("name", "layer", "namePattern", "bbox"),
        description="Find block instances matching name, layer, name pattern, or bbox filter",
    )
    routes["block_objects_detailed"] = RouteSpec(
        endpoint="/block/objects-detailed",
        required_params=("name",),
        optional_params=("geometry",),
        description="Get detailed object info (id, type, layer, material, color, bbox, user strings) within a block definition",
    )
    routes["set_block_instance_visibility"] = RouteSpec(
        endpoint="/block/set-instance-visibility",
        required_params=("id", "visible"),
        description="Set visibility on a single block instance (router covers single-id path only; bulk `ids` shape stays MCP-direct)",
    )

    # === Group operations ===
    routes["create_group"] = RouteSpec(
        endpoint="/group",
        required_params=("ids",),
        optional_params=("name",),
        description="Create group from objects",
    )
    routes["ungroup"] = RouteSpec(
        endpoint="/ungroup",
        optional_params=("name", "index"),
        description="Delete group",
    )

    # === Material operations ===
    routes["create_material"] = RouteSpec(
        endpoint="/materials",
        required_params=("name",),
        optional_params=("color", "transparency", "reflectivity", "shininess"),
        description="Create material",
    )
    routes["delete_material"] = RouteSpec(
        endpoint="/materials",
        method="DELETE",
        required_params=("name",),
        description="Delete material",
    )
    routes["assign_material"] = RouteSpec(
        endpoint="/materials/assign",
        required_params=("name",),
        optional_params=("id", "ids"),
        description="Assign material to objects",
    )

    # === UV Mapping ===
    routes["uv_box_mapping"] = RouteSpec(
        endpoint="/material/uv-box",
        required_params=("ids",),
        optional_params=("channel", "scale"),
        description="Apply box UV mapping",
    )
    routes["uv_planar_mapping"] = RouteSpec(
        endpoint="/material/uv-planar",
        required_params=("ids",),
        optional_params=("plane", "channel", "scale"),
        description="Apply planar UV mapping",
    )
    routes["uv_cylinder_mapping"] = RouteSpec(
        endpoint="/material/uv-cylinder",
        required_params=("ids",),
        optional_params=("axis", "capped", "channel", "scale"),
        description="Apply cylindrical UV mapping",
    )
    routes["uv_sphere_mapping"] = RouteSpec(
        endpoint="/material/uv-sphere",
        required_params=("ids",),
        optional_params=("channel", "scale"),
        description="Apply spherical UV mapping",
    )

    # === Selection ===
    routes["select_objects"] = RouteSpec(
        endpoint="/select",
        optional_params=("ids", "layer", "type", "name", "all", "clear", "invert", "bbox"),
        description="Select objects by criteria",
    )

    # === Document operations ===
    routes["save_document"] = RouteSpec(
        endpoint="/document/save",
        optional_params=("path",),
        description="Save document",
    )
    routes["new_document"] = RouteSpec(
        endpoint="/document/new",
        description="Create new document",
    )
    routes["set_units"] = RouteSpec(
        endpoint="/document/units",
        required_params=("units",),
        description="Set document units",
    )

    # === Import / Export ===
    routes["import_file"] = RouteSpec(
        endpoint="/import",
        required_params=("path",),
        optional_params=("targetLayer",),
        description="Import file",
    )
    routes["export_file"] = RouteSpec(
        endpoint="/export",
        required_params=("path",),
        optional_params=("ids", "selection"),
        description="Export objects to file",
    )

    # === Game export ===
    routes["tag_semantic"] = RouteSpec(
        endpoint="/game-export/tag",
        required_params=("ids",),
        optional_params=(
            "semantic_type", "collision", "nanite", "material_intent", "tags",
        ),
        description="Tag objects with semantic type for game export",
    )
    routes["validate_export"] = RouteSpec(
        endpoint="/game-export/validate",
        optional_params=("ids", "selection"),
        description="Validate geometry for game export",
    )
    routes["game_export"] = RouteSpec(
        endpoint="/game-export/export",
        required_params=("path",),
        optional_params=(
            "ids", "selection", "material_map", "settings", "level_placement",
        ),
        description="Export with manifest for game engine",
    )

    return routes


# ---------------------------------------------------------------------------
# Operation categories (for documentation and debugging)
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, tuple[str, ...]] = {
    "creation": (
        "create_point", "create_line", "create_polyline", "create_circle",
        "create_arc", "create_rectangle", "create_box", "create_sphere",
        "create_cylinder", "create_cone", "create_extrusion",
        "create_interpolated_curve", "create_control_point_curve",
        "create_pipe", "create_loft", "create_sweep1", "create_sweep2",
        "create_revolve", "array_linear", "array_rectangular", "array_polar",
        "create_mesh_box", "create_mesh_sphere", "create_mesh_cylinder",
        "create_mesh_cone", "create_subd_box", "create_subd_sphere",
        "create_subd_cylinder",
    ),
    "transform": ("move", "rotate", "scale", "mirror", "copy", "delete"),
    "boolean": (
        "boolean_union", "boolean_difference",
        "boolean_intersection", "boolean_split",
    ),
    "surface_ops": ("fillet_edge", "chamfer_edge", "offset_brep"),
    "curves": (
        "join_curves", "explode_curve", "divide_curve", "extend_curve",
        "trim_curve", "split_curve", "rebuild_curve", "fillet_curves",
        "project_curve", "pull_curve", "offset_curve", "offset_curve_on_surface",
    ),
    "intersection": (
        "intersect_curves", "intersect_curve_surface", "intersect_curve_brep",
        "intersect_breps", "intersect_plane",
    ),
    "split_trim": ("split_brep", "trim_brep", "split_face", "split_disjoint_breps"),
    "mesh": (
        "mesh_from_brep", "mesh_boolean", "mesh_repair", "mesh_smooth",
        "mesh_weld", "mesh_unweld", "mesh_reduce", "quad_remesh",
    ),
    "subd": (
        "subd_from_mesh", "subd_from_surface", "subd_subdivide",
        "subd_crease", "subd_to_brep", "subd_to_mesh",
    ),
    "layers": (
        "create_layer", "delete_layer", "set_layer_visibility",
        "lock_layer", "set_current_layer",
        "set_layer_properties", "set_layer_properties_batch",
    ),
    "blocks": (
        "create_block", "insert_block", "explode_block",
        "delete_block", "rename_block",
        "set_block_layers", "set_block_layers_batch",
        "set_block_materials", "set_block_materials_batch",
        "set_block_object_colors", "set_block_object_colors_batch",
        "set_block_object_user_strings", "set_block_object_user_strings_batch",
        "set_block_object_names", "set_block_object_names_batch",
        "transform_block_instance", "transform_block_instance_batch",
        "purge_blocks",
        "replace_block_geometry", "replace_block_object_geometry",
        "transform_block_object",
        "replace_block_instance", "replace_block_instance_batch", "reset_block_instance_scale",
        "link_block", "unlink_block", "refresh_block",
        "find_block_instances", "block_objects_detailed",
        "set_block_instance_visibility",
    ),
    "groups": ("create_group", "ungroup"),
    "materials": (
        "create_material", "delete_material", "assign_material",
        "uv_box_mapping", "uv_planar_mapping",
        "uv_cylinder_mapping", "uv_sphere_mapping",
    ),
    "selection": ("select_objects",),
    "document": ("save_document", "new_document", "set_units"),
    "io": ("import_file", "export_file"),
    "game_export": ("tag_semantic", "validate_export", "game_export"),
}


# ---------------------------------------------------------------------------
# CapabilityRouter
# ---------------------------------------------------------------------------

class CapabilityRouter:
    """Maps semantic operations to direct HTTP API endpoints.

    This is the key architectural change over the old execute_intent:
    operations with typed HTTP handlers skip DSPy command resolution entirely.

    Usage:
        router = CapabilityRouter.get()

        # Check if an operation has a direct route
        if router.has_direct_route("create_sphere"):
            spec = router.route("create_sphere")
            payload = router.build_payload("create_sphere", {"center": [0,0,0], "radius": 5})
            # payload = {"type": "SPHERE", "center": [0,0,0], "radius": 5}
            # -> call_rhino("/create", "POST", payload)

        # Validate before execution
        valid, missing = router.validate_params("create_sphere", {"center": [0,0,0]})
        # valid=False, missing=["radius"]
    """

    _instance: CapabilityRouter | None = None

    def __init__(self) -> None:
        self._routes = _build_route_table()
        # Reverse map: operation -> category
        self._op_category: dict[str, str] = {}
        for cat, ops in CATEGORIES.items():
            for op in ops:
                self._op_category[op] = cat

    @classmethod
    def get(cls) -> CapabilityRouter:
        """Singleton access. The route table is immutable after construction."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def route(self, operation: str) -> RouteSpec | None:
        """Look up the direct API route for an operation.

        Returns None if the operation must go through command-string resolution.
        """
        return self._routes.get(operation)

    def has_direct_route(self, operation: str) -> bool:
        return operation in self._routes

    def list_operations(self) -> list[str]:
        """All operations with direct routes, sorted alphabetically."""
        return sorted(self._routes.keys())

    def categories(self) -> dict[str, tuple[str, ...]]:
        """Operations grouped by category."""
        return dict(CATEGORIES)

    def category_for(self, operation: str) -> str | None:
        """Which category an operation belongs to."""
        return self._op_category.get(operation)

    @property
    def operation_count(self) -> int:
        return len(self._routes)

    def validate_params(
        self, operation: str, params: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Check if params satisfy the route's required_params.

        Returns (valid, list_of_missing_param_names).
        Does NOT validate types or values -- that's the C++ handler's job.
        """
        spec = self._routes.get(operation)
        if spec is None:
            return False, [f"unknown operation: {operation}"]
        missing = [p for p in spec.required_params if p not in params]
        return len(missing) == 0, missing

    def build_payload(
        self, operation: str, params: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the HTTP request payload by merging base_params with user params.

        base_params (e.g. {"type": "SPHERE"}) are set first, then user params
        are merged on top. User params win on conflict.
        """
        spec = self._routes.get(operation)
        if spec is None:
            return dict(params)
        return {**spec.base_params, **params}

    def find_operations(self, keyword: str) -> list[str]:
        """Find operations whose name or description contains the keyword.

        Useful for the IntentPlanner to narrow candidates before DSPy.
        """
        kw = keyword.lower()
        matches = []
        for op, spec in self._routes.items():
            if kw in op.lower() or kw in spec.description.lower():
                matches.append(op)
        return sorted(matches)

    def summary(self) -> dict[str, Any]:
        """Summary stats for debugging."""
        return {
            "total_operations": len(self._routes),
            "categories": {
                cat: len(ops) for cat, ops in CATEGORIES.items()
            },
            "endpoints": len({s.endpoint for s in self._routes.values()}),
        }
