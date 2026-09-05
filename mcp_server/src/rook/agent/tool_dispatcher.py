"""
Tool Dispatcher — Direct tool execution for agents
====================================================

Gives agents direct access to Rhino/GH tools WITHOUT going through MCP.
Matches Engram's architecture where agents are peers of MCP, not consumers.

Three dispatch tiers:
  1. Local tools (knowledge queries, intent execution) → direct Python calls
  2. Transform tools (parameter rewriting needed) → transform → call_rhino()
  3. Bridge tools (simple passthrough) → call_rhino() directly

Eliminates: MCP universal injection, TextContent roundtrip, session recording.
Agents use their own Seam 1-4 knowledge system instead.
"""

import ast
import inspect
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..bridge import call_rhino
from ..gh_authoring_contract import model_facing_script_handoff
from ..gh_edit_contract import admit_gh_edit_request, apply_gh_edit_contract
from ..grasshopper_component_contract import project_gh_library_result
from ..gh_status_contract import normalize_gh_status_result
from ..tool_lifecycle import resolve_contained_tool
from ..tool_lifecycle_runtime import DispatchOrigin, deny_if_contained
from .chat.execution_policy import annotate_result, needs_verification

logger = logging.getLogger(__name__)


def _hoist_nested_verification_fields(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    if not isinstance(data, dict):
        return result

    if "verified" not in result and "verified" in data:
        result["verified"] = data["verified"]

    if "verification_note" not in result:
        note = data.get("verification_note")
        if note is None and data.get("verified") is False:
            note = data.get("message")
        if note is not None:
            result["verification_note"] = note

    return result


GH_READINESS_HOIST_TOOLS: frozenset[str] = frozenset({
    "gh_snapshot",
    "gh_edit",
})


STRICT_NO_ARGUMENT_BRIDGE_TOOLS: frozenset[str] = frozenset({
    "gh_errors",
})


_DEPRECATED_INTERACTIVE_COMMAND_TOOLS: frozenset[str] = frozenset({
    "rhino_command_experiment",
    "rhino_command_interactive_start",
    "rhino_command_interactive_send",
    "rhino_learn_interactive",
    "rhino_learn_next",
    "rhino_learn_variations_interactive",
    "rhino_prepare_geometry",
})


def _interactive_command_deprecated_result(tool_name: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "error": "interactive_command_deprecated",
            "tool": tool_name,
            "verified": False,
            "recovery": (
                "Autonomous Rhino prompt driving is disabled. Use typed Rook tools, "
                "a known-safe fully scripted rhino_command, "
                "rhino_command_interactive_prompt to inspect state, or "
                "rhino_command_interactive_cancel to recover."
            ),
        },
        "_pre_dispatch_failure": True,
    }


_RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS: frozenset[str] = frozenset({
    "GetBoolean",
    "GetBox",
    "GetColor",
    "GetCurveObject",
    "GetInteger",
    "GetLayer",
    "GetMeshObject",
    "GetObject",
    "GetObjects",
    "GetPoint",
    "GetPoints",
    "GetReal",
    "GetRectangle",
    "GetString",
    "GetSurfaceObject",
})


def _find_blocking_rhinoscriptsyntax_call(code: str) -> Optional[tuple[str, int]]:
    """Return the first obvious blocking rhinoscriptsyntax input call, if any.

    This is intentionally conservative. It catches the common interactive APIs
    that would wedge Rhino's UI thread inside RunScript (for example
    ``rs.GetPoint()``) and rejects them before dispatch.
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return None

    rs_aliases: set[str] = set()
    imported_names: dict[str, str] = {}
    has_star_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "rhinoscriptsyntax":
                    rs_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "rhinoscriptsyntax":
            for alias in node.names:
                if alias.name == "*":
                    has_star_import = True
                    continue
                imported_names[alias.asname or alias.name] = alias.name

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in rs_aliases and func.attr in _RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS:
                return f"{func.value.id}.{func.attr}()", getattr(node, "lineno", 1)

        if isinstance(func, ast.Name):
            original_name = imported_names.get(func.id, func.id if has_star_import else "")
            if original_name in _RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS:
                return f"{func.id}()", getattr(node, "lineno", 1)

    return None


# =============================================================================
# Bridge Routing Table — Simple Passthrough
# =============================================================================
#
# Maps tool_name → (endpoint, method).
# These tools pass arguments directly to call_rhino with no transformation.

BRIDGE_ROUTES: Dict[str, Tuple[str, str]] = {
    # --- Rhino Core ---
    "rhino_ping":               ("/ping", "GET"),
    "rhino_document":           ("/document", "GET"),
    "rhino_layers":             ("/layers", "GET"),
    "rhino_objects":            ("/objects", "GET"),
    "rhino_selection":          ("/selection", "GET"),
    "rhino_select":             ("/select", "POST"),
    "rhino_geometry":           ("/geometry", "GET"),
    # rhino_execute is in TRANSFORM_FUNCTIONS (auto-wraps code in try/except)
    # rhino_command is in TRANSFORM_FUNCTIONS (preflight validation before RunScript)
    # "rhino_command" — REMOVED from bridge passthrough; see _transform_rhino_command
    "rhino_command_prompt":     ("/command/prompt", "GET"),
    "rhino_viewport":           ("/viewport", "POST"),
    "rhino_views":              ("/views", "GET"),
    "rhino_views_restore":      ("/views/restore", "POST"),
    "rhino_views_save":         ("/views/save", "POST"),
    "rhino_display_modes":      ("/display-modes", "GET"),
    "rhino_display_mode_set":   ("/display-mode", "POST"),
    "rhino_create":             ("/create", "POST"),
    "rhino_delete":             ("/delete", "POST"),
    "rhino_transform":          ("/transform", "POST"),
    "rhino_copy":               ("/copy", "POST"),
    "rhino_import":             ("/import", "POST"),
    "rhino_export":             ("/export", "POST"),
    "rhino_group":              ("/group", "POST"),

    # --- Layers ---
    "rhino_layer_create":         ("/layers", "POST"),
    "rhino_layer_create_batch":   ("/layers/batch", "POST"),
    "rhino_layer_delete":         ("/layers", "DELETE"),
    "rhino_layer_visibility":     ("/layers/visibility", "POST"),
    "rhino_layer_lock":           ("/layers/lock", "POST"),
    "rhino_layer_current":        ("/layers/current", "POST"),
    "rhino_layer_set_properties": ("/layers/properties", "POST"),
    "rhino_layer_set_properties_batch": ("/layers/properties-batch", "POST"),
    "rhino_layer_rename":         ("/layers/rename", "POST"),
    "rhino_layer_move_objects":   ("/layers/move-objects", "POST"),
    "rhino_layer_merge":          ("/layers/merge", "POST"),
    "rhino_layer_dependencies":   ("/layers/dependencies", "GET"),

    # --- Materials / Linetypes ---
    "rhino_materials":            ("/materials", "GET"),
    "rhino_material_purge":       ("/materials/purge", "POST"),
    "rhino_linetypes":            ("/linetypes", "GET"),
    "rhino_linetype_purge":       ("/linetypes/purge", "POST"),

    # --- Block analysis ---
    "rhino_block_layer_census":   ("/block/layer-census", "GET"),

    # --- Selection variants ---
    "rhino_select_by_type":     ("/select", "POST"),
    "rhino_select_by_name":     ("/select", "POST"),

    # --- Measurement ---
    "rhino_measure_distance":   ("/measure/distance", "POST"),
    "rhino_measure_area":       ("/measure/area", "POST"),
    "rhino_measure_volume":     ("/measure/volume", "POST"),
    "rhino_measure_length":     ("/measure/length", "POST"),
    "rhino_measure_bbox":       ("/measure/bbox", "POST"),
    "rhino_measure_centroid":   ("/measure/centroid", "POST"),

    # --- Annotation ---
    "rhino_dimension":          ("/create", "POST"),

    # --- Blocks ---
    "rhino_blocks":             ("/blocks", "GET"),
    "rhino_block_create":       ("/block/create", "POST"),
    "rhino_block_insert":       ("/block/insert", "POST"),
    "rhino_block_explode":      ("/block/explode", "POST"),
    "rhino_block_delete":       ("/block", "DELETE"),
    "rhino_block_rename":       ("/block/rename", "POST"),
    "rhino_block_description":  ("/block/description", "POST"),
    "rhino_block_add_objects":  ("/block/add-objects", "POST"),
    "rhino_block_remove_objects": ("/block/remove-objects", "POST"),
    "rhino_block_replace_geometry": ("/block/replace-geometry", "POST"),
    "rhino_block_replace_object_geometry": ("/block/replace-object-geometry", "POST"),
    "rhino_block_replace_object_geometry_batch": ("/block/replace-object-geometry-batch", "POST"),
    "rhino_block_transform_object": ("/block/transform-object", "POST"),
    "rhino_block_transform_object_batch": ("/block/transform-object-batch", "POST"),
    "rhino_block_set_layers":   ("/block/set-layers", "POST"),
    "rhino_block_set_layers_batch": ("/block/set-layers-batch", "POST"),
    "rhino_block_set_materials": ("/block/set-materials", "POST"),
    "rhino_block_set_materials_batch": ("/block/set-materials-batch", "POST"),
    "rhino_block_replace_instance": ("/block/replace-instance", "POST"),
    "rhino_block_replace_instance_batch": ("/block/replace-instance-batch", "POST"),
    "rhino_block_reset_scale":  ("/block/reset-scale", "POST"),
    "rhino_block_reset_scale_batch": ("/block/reset-scale-batch", "POST"),
    "rhino_block_link":         ("/block/link", "POST"),
    "rhino_block_refresh":      ("/block/refresh", "POST"),
    "rhino_block_unlink":       ("/block/unlink", "POST"),
    "rhino_block_purge":        ("/block/purge", "POST"),
    "rhino_block_duplicate":    ("/block/duplicate", "POST"),
    "rhino_block_rebase":       ("/block/rebase", "POST"),
    "rhino_block_rebase_recursive": ("/block/rebase-recursive", "POST"),
    "rhino_block_set_instance_properties": ("/block/set-instance-properties", "POST"),
    "rhino_block_set_instance_visibility": ("/block/set-instance-visibility", "POST"),
    "rhino_block_transform_instance": ("/block/transform-instance", "POST"),
    "rhino_block_transform_instance_batch": ("/block/transform-instance-batch", "POST"),
    "rhino_block_array_instances": ("/block/array-instances", "POST"),
    "rhino_block_set_object_colors": ("/block/set-object-colors", "POST"),
    "rhino_block_set_object_colors_batch": ("/block/set-object-colors-batch", "POST"),
    "rhino_block_set_object_names": ("/block/set-object-names", "POST"),
    "rhino_block_set_object_names_batch": ("/block/set-object-names-batch", "POST"),
    "rhino_block_set_object_user_strings": ("/block/set-object-user-strings", "POST"),
    "rhino_block_set_object_user_strings_batch": ("/block/set-object-user-strings-batch", "POST"),
    "rhino_block_user_strings": ("/block/user-strings", "POST"),
    "rhino_block_find_instances": ("/block/find-instances", "POST"),
    "rhino_block_objects_detailed": ("/block/objects-detailed", "POST"),

    # --- User text (arbitrary metadata; Phase 2 PR-9 + PR-10) ---
    # Object-level (PR-9) and document-level (PR-10 — adds reserved-prefix
    # denylist on document-set writes). Delete routes for both levels
    # land in a follow-up PR.
    "rhino_usertext_object_set": ("/usertext/object-set", "POST"),
    "rhino_usertext_object_get": ("/usertext/object-get", "POST"),
    "rhino_usertext_document_set": ("/usertext/document-set", "POST"),
    "rhino_usertext_document_get": ("/usertext/document-get", "POST"),
    # 2026-04-20 delete PR — closes the usertext family.
    "rhino_usertext_object_delete": ("/usertext/object-delete", "POST"),
    "rhino_usertext_document_delete": ("/usertext/document-delete", "POST"),

    # --- Phase 2 surface/curve extension (PR-1 worked example) ---
    # managed-bridge (reuse) substrate; see
    # rook_docs/2026-04-20-phase2-surface-curve-plan.md.
    "rhino_create_edge_srf": ("/surface/edge", "POST"),
    "rhino_create_patch": ("/surface/patch", "POST"),
    "rhino_create_network_srf": ("/surface/network", "POST"),
    "rhino_blend_curves": ("/curve/blend", "POST"),

    # --- Intersection (simple) ---
    "rhino_intersect_curve_surface": ("/intersect/curve-surface", "POST"),
    "rhino_intersect_curve_brep":    ("/intersect/curve-brep", "POST"),

    # --- Curve operations (simple) ---
    "rhino_project_curve":      ("/curve/project", "POST"),
    "rhino_pull_curve":         ("/curve/pull", "POST"),
    "rhino_offset_curve":       ("/curve/offset", "POST"),
    "rhino_offset_curve_on_surface": ("/curve/offset-on-surface", "POST"),

    # --- Brep (simple) ---
    "rhino_offset_brep":        ("/offset/brep", "POST"),
    "rhino_split_face":         ("/split/face", "POST"),
    "rhino_split_disjoint_breps": ("/split/disjoint-breps", "POST"),

    # --- SubD ---
    "rhino_subd_box":           ("/subd/box", "POST"),
    "rhino_subd_sphere":        ("/subd/sphere", "POST"),
    "rhino_subd_cylinder":      ("/subd/cylinder", "POST"),
    "rhino_subd_from_mesh":     ("/subd/from-mesh", "POST"),
    "rhino_subd_from_surface":  ("/subd/from-surface", "POST"),
    "rhino_subd_subdivide":     ("/subd/subdivide", "POST"),
    "rhino_subd_crease":        ("/subd/crease", "POST"),
    "rhino_subd_to_brep":       ("/subd/to-brep", "POST"),
    "rhino_subd_to_mesh":       ("/subd/to-mesh", "POST"),

    # --- Mesh ---
    "rhino_mesh_from_brep":     ("/mesh/from-brep", "POST"),
    "rhino_mesh_box":           ("/mesh/box", "POST"),
    "rhino_mesh_sphere":        ("/mesh/sphere", "POST"),
    "rhino_mesh_cylinder":      ("/mesh/cylinder", "POST"),
    "rhino_mesh_cone":          ("/mesh/cone", "POST"),
    "rhino_mesh_boolean":       ("/mesh/boolean", "POST"),
    "rhino_mesh_reduce":        ("/mesh/reduce", "POST"),
    "rhino_quad_remesh":        ("/mesh/quad-remesh", "POST"),
    "rhino_mesh_repair":        ("/mesh/repair", "POST"),
    "rhino_mesh_smooth":        ("/mesh/smooth", "POST"),
    "rhino_mesh_weld":          ("/mesh/weld", "POST"),
    "rhino_mesh_unweld":        ("/mesh/unweld", "POST"),

    # --- Analysis ---
    "rhino_curvature_curve":    ("/analysis/curvature-curve", "POST"),
    "rhino_curvature_surface":  ("/analysis/curvature-surface", "POST"),
    "rhino_draft_angle":        ("/analysis/draft-angle", "POST"),
    "rhino_closest_point":      ("/analysis/closest-point", "POST"),
    "rhino_curve_point_at":     ("/analysis/curve-point-at", "POST"),
    "rhino_curve_tangent":      ("/analysis/curve-tangent", "POST"),
    "rhino_curve_frame":        ("/analysis/curve-frame", "POST"),
    "rhino_surface_normal":     ("/analysis/surface-normal", "POST"),
    "rhino_brep_edges":         ("/analysis/brep-edges", "POST"),
    "rhino_brep_faces":         ("/analysis/brep-faces", "POST"),
    "rhino_brep_vertices":      ("/analysis/brep-vertices", "POST"),
    "rhino_is_closed":          ("/analysis/is-closed", "POST"),
    "rhino_is_valid":           ("/analysis/is-valid", "POST"),

    # --- UV Mapping ---
    "rhino_apply_uv_box_mapping":      ("/material/uv-box", "POST"),
    "rhino_apply_uv_planar_mapping":   ("/material/uv-planar", "POST"),
    "rhino_apply_uv_cylinder_mapping": ("/material/uv-cylinder", "POST"),
    "rhino_apply_uv_sphere_mapping":   ("/material/uv-sphere", "POST"),

    # --- Game Export ---
    "rhino_tag_object_semantic":       ("/game-export/tag", "POST"),
    "rhino_tag_objects_from_layers":   ("/game-export/tag-from-layers", "POST"),
    "rhino_validate_export":           ("/game-export/validate", "POST"),
    "rhino_export_with_manifest":      ("/game-export/export", "POST"),
    "rhino_prepare_for_game_export":   ("/game-export/prepare", "POST"),

    # --- Gumball ---
    "rhino_gumball_activate":   ("/gumball/activate", "POST"),
    "rhino_gumball_deactivate": ("/gumball/deactivate", "POST"),
    "rhino_gumball_status":     ("/gumball/status", "GET"),
    "rhino_gumball_history":    ("/gumball/history", "GET"),

    # --- Session Recording ---
    "session_current":          ("/session", "GET"),
    "session_history":          ("/session/history", "GET"),
    "session_list":             ("/session/list", "GET"),
    "session_export":           ("/session/export", "POST"),

    # --- Rhino Interactive Command Recovery/Observability ---
    "rhino_command_interactive_prompt": ("/command/prompt", "GET"),
    "rhino_command_interactive_cancel": ("/command/cancel", "POST"),

    # --- GH Core ---
    "gh_status":                ("/gh/status", "GET"),
    "gh_snapshot":              ("/gh/snapshot", "POST"),
    "gh_edit":                  ("/gh/edit", "POST"),
    "gh_connect":               ("/gh/connect", "POST"),
    "gh_undo":                  ("/gh/undo", "POST"),
    "gh_selection":             ("/gh/selection", "GET"),
    "gh_categories":            ("/gh/categories", "GET"),
    "gh_errors":                ("/gh/errors", "GET"),
    "gh_preview":               ("/gh/preview", "POST"),
    "gh_clear":                 ("/gh/clear", "POST"),
    "gh_document_new":          ("/gh/document/new", "POST"),
    "gh_move":                  ("/gh/move", "POST"),
    "gh_groups":                ("/gh/groups", "GET"),
    "gh_group_resize":          ("/gh/group-resize", "POST"),
    "gh_cluster":               ("/gh/cluster", "POST"),
    "gh_bake_output":           ("/gh/bake", "POST"),

    # --- RoadCreator (RookRoads plugin, pluginType="roadcreator") ---
    "rc_ping":                  ("/rc/ping", "GET"),
    "rc_standards":             ("/rc/standards/categories", "GET"),
    "rc_roads":                 ("/rc/roads", "GET"),
    "rc_clothoid":              ("/rc/alignment/clothoid", "POST"),
    "rc_cubic_parabola":        ("/rc/alignment/cubic-parabola", "POST"),
    "rc_vertical_curve":        ("/rc/alignment/vertical-curve", "POST"),
    "rc_assemble_route":        ("/rc/alignment/assemble-route", "POST"),
    "rc_cross_section":         ("/rc/road/cross-section", "POST"),
    "rc_road_3d":               ("/rc/road/3d", "POST"),
    "rc_extract_offsets":       ("/rc/extract-offsets", "POST"),

    # --- RoadCreator — Urban Design ---
    "rc_sidewalk_profile":      ("/rc/urban/sidewalk-profile", "POST"),
    "rc_roundabout_params":     ("/rc/urban/roundabout-params", "POST"),
    "rc_crossing_params":       ("/rc/urban/crossing-params", "POST"),

    # --- RoadCreator — Accessories ---
    "rc_guardrail_profile":     ("/rc/accessories/guardrail-profile", "GET"),
    "rc_pole_spacing":          ("/rc/accessories/pole-spacing", "POST"),
    "rc_concrete_barrier_profile": ("/rc/accessories/concrete-barrier-profile", "GET"),
    "rc_deltablok_profile":     ("/rc/accessories/deltablok-profile", "POST"),

    # --- RoadCreator — Verge & Slopes ---
    "rc_verge_profile":         ("/rc/verge/profile", "POST"),
    "rc_slope_profile":         ("/rc/slope/profile", "POST"),

    # --- RoadCreator — Standards ---
    "rc_widening":              ("/rc/standards/widening", "POST"),

    # --- RoadCreator — Terrain ---
    "rc_terrain_profile":       ("/rc/terrain/profile-points", "POST"),
    "rc_contour_levels":        ("/rc/terrain/contour-levels", "POST"),

    # --- RoadCreator — Footprint ---
    "rc_validate_profile":      ("/rc/footprint/validate-profile", "POST"),
    "rc_validate_style_set":    ("/rc/footprint/validate-style-set", "POST"),
    "rc_road_footprint":        ("/rc/geometry/road-footprint", "POST"),

    # --- RoadCreator — Network Topology ---
    "rc_resolve_edges":         ("/rc/network/resolve-edges", "POST"),
    "rc_apply_intersection_ownership": ("/rc/network/apply-intersection-ownership", "POST"),
    "rc_apply_sidewalk_ownership": ("/rc/network/apply-sidewalk-ownership", "POST"),
    "rc_sidewalk_corners":      ("/rc/geometry/sidewalk-corners", "POST"),

    # --- RoadCreator — Profile Builder ---
    "rc_build_profile":         ("/rc/profile/build", "POST"),
    "rc_validate_road_profile": ("/rc/profile/validate", "POST"),
    "rc_store_road_profile":    ("/rc/profile/store", "POST"),
    "rc_project_offset_profile":("/rc/profile/project-offset", "POST"),
    "rc_get_road_profile":      ("/rc/profile/get", "POST"),
    "rc_list_road_profiles":    ("/rc/profile/list", "GET"),

    # --- Native road intersection orchestration ---
    "road_intersection_candidates": ("/road/intersection/candidates", "POST"),
    "road_intersection_resolve":    ("/road/intersection/resolve", "POST"),

    # --- RookBIM (Revit bridge, Phase 1) ---
    "rookbim_status":             ("/bim/status", "GET"),
    "rookbim_active_document":    ("/bim/active-document", "GET"),
    "rookbim_list_categories":    ("/bim/categories", "GET"),
    "rookbim_query_elements":     ("/bim/query-elements", "POST"),
    "rookbim_element_info":       ("/bim/element-info", "POST"),
    "rookbim_element_parameters": ("/bim/element-parameters", "POST"),
    "rookbim_select_elements":    ("/bim/select-elements", "POST"),
    "rookbim_clear_selection":    ("/bim/clear-selection", "POST"),
    "rookbim_export_elements":    ("/bim/export-elements", "POST"),
    "rookbim_export_preset":      ("/bim/export-preset", "POST"),

    # --- Vision Video (PR-V4) ---
    # Body-only / no-param tools live here. Path-param tools
    # (status / cancel / result) and the limit-folding list tool
    # (jobs) live in TRANSFORM_FUNCTIONS so the dispatcher can
    # construct the URL by hand and bypass call_rhino's None-stripping
    # behavior on GET params.
    "rhino_render_video":   ("/vision/video/jobs", "POST"),
    "rhino_video_estimate": ("/vision/video/estimate", "POST"),
    "rhino_video_models":   ("/vision/video/models", "GET"),

    # --- Rook Reconstruction (2D to 3D) ---
    # Submit/import are simple body passthroughs. Models/jobs/path-param
    # lifecycle tools live in TRANSFORM_FUNCTIONS for explicit query/path
    # construction and parity with server.call_tool.
    "rhino_2d_to_3d_submit": ("/reconstruction/2d-to-3d/jobs", "POST"),
    "rhino_2d_to_3d_remove_background": ("/reconstruction/2d-to-3d/background-removals", "POST"),
    "rhino_2d_to_3d_assemble_view_set": ("/reconstruction/2d-to-3d/view-sets", "POST"),
    "rhino_2d_to_3d_import": ("/reconstruction/2d-to-3d/import", "POST"),

    # --- Scene Graph (agent bridge access; endpoints mirror the pure call_rhino
    # handlers in server._call_tool_dispatch so the agent path and MCP path hit
    # the identical Rhino route). See #303. scene_graph/context/stats stay parked
    # in LOCAL_TIER_0_DISPATCH_EXCLUSIONS by separate decision.
    "scene_query":    ("/scene/graph/query", "POST"),
    "scene_classify": ("/scene/graph/classify", "POST"),
    "scene_overlay":  ("/scene/graph/overlay", "POST"),
}


# =============================================================================
# Transform Functions
# =============================================================================
#
# Tools that need parameter rewriting before bridge call.
# Each returns (endpoint, method, transformed_data).

def _transform_boolean(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    if a.get("operation") == "difference" and "targetId" in a:
        target_id = a.pop("targetId")
        tool_ids = a.pop("toolIds", [])
        a["ids"] = [target_id] + tool_ids
    return "/boolean", "POST", a


# Phase 2 PR-4 — curve boolean dispatch. Three intent keys share one
# endpoint with an `operation` discriminator; mirrors the brep-boolean
# pattern. MCP executor injects `operation` per case arm; the agent-direct
# path (this module) mirrors that injection via these transforms.
def _transform_curve_boolean_union(args: dict) -> Tuple[str, str, dict]:
    a = dict(args); a["operation"] = "union"
    return "/curve/boolean", "POST", a


def _transform_curve_boolean_difference(args: dict) -> Tuple[str, str, dict]:
    a = dict(args); a["operation"] = "difference"
    return "/curve/boolean", "POST", a


def _transform_curve_boolean_intersection(args: dict) -> Tuple[str, str, dict]:
    a = dict(args); a["operation"] = "intersection"
    return "/curve/boolean", "POST", a


def _transform_extrude(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    a["type"] = "EXTRUDE"
    if "direction" in a and "distance" in a:
        direction = a["direction"]
        distance = a["distance"]
        if isinstance(direction, list) and len(direction) == 3:
            a["direction"] = [d * distance for d in direction]
        del a["distance"]
    return "/create", "POST", a


def _transform_text(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    a["type"] = "TEXT"
    return "/create", "POST", a


def _transform_select_all(args: dict) -> Tuple[str, str, dict]:
    return "/select", "POST", {"all": True}


def _transform_select_none(args: dict) -> Tuple[str, str, dict]:
    return "/select", "POST", {"none": True}


def _transform_select_invert(args: dict) -> Tuple[str, str, dict]:
    return "/select", "POST", {"invert": True}


def _transform_deselect(args: dict) -> Tuple[str, str, dict]:
    return "/select", "POST", {"deselectIds": args.get("ids", []), "clear": False}


def _transform_intersect_curves(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    if "curveId1" in a:
        a["id1"] = a.pop("curveId1")
    if "curveId2" in a:
        a["id2"] = a.pop("curveId2")
    return "/intersect/curves", "POST", a


def _transform_intersect_breps(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    if "brepId1" in a:
        a["id1"] = a.pop("brepId1")
    if "brepId2" in a:
        a["id2"] = a.pop("brepId2")
    return "/intersect/breps", "POST", a


def _transform_intersect_plane(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    if "planeOrigin" in a and "planeNormal" in a:
        a["plane"] = {
            "origin": a.pop("planeOrigin"),
            "normal": a.pop("planeNormal"),
        }
    return "/intersect/plane", "POST", a


def _transform_split_brep(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    if "planeOrigin" in a and "planeNormal" in a:
        a["plane"] = {
            "origin": a.pop("planeOrigin"),
            "normal": a.pop("planeNormal"),
        }
    return "/split/brep", "POST", a


def _transform_trim_brep(args: dict) -> Tuple[str, str, dict]:
    a = dict(args)
    if "planeOrigin" in a and "planeNormal" in a:
        a["plane"] = {
            "origin": a.pop("planeOrigin"),
            "normal": a.pop("planeNormal"),
        }
    if "keepSide" in a:
        ks = a["keepSide"]
        if ks == "positive":
            a["keepSide"] = 0
        elif ks == "negative":
            a["keepSide"] = 1
    return "/trim/brep", "POST", a


def _transform_document_ops(args: dict) -> Tuple[str, str, dict]:
    action = args.get("action") or args.get("operation")
    if action == "undo":
        return "/undo", "POST", {}
    elif action == "redo":
        return "/redo", "POST", {}
    elif action == "save":
        path = args.get("path")
        if not path:
            return None, None, {"success": False, "data": "Missing 'path' for save"}
        return "/document/save", "POST", {"path": path}
    elif action == "new":
        return "/document/new", "POST", {}
    elif action == "set_units":
        units = args.get("units")
        if not units:
            return None, None, {"success": False, "data": "Missing 'units' for set_units"}
        return "/document/units", "POST", {"units": units}
    return None, None, {"success": False, "data": f"Invalid action '{action}'"}


def _transform_curve_ops(args: dict) -> Tuple[str, str, dict]:
    action = args.get("action")
    if action == "join":
        ids = args.get("ids")
        if not ids:
            return None, None, {"success": False, "data": "Missing 'ids' for join"}
        return "/curve/join", "POST", {"ids": ids}
    elif action == "explode":
        cid = args.get("id")
        if not cid:
            return None, None, {"success": False, "data": "Missing 'id' for explode"}
        return "/curve/explode", "POST", {"id": cid}
    elif action == "divide":
        cid = args.get("id")
        count = args.get("count")
        if not cid or not count:
            return None, None, {"success": False, "data": "Missing 'id'/'count' for divide"}
        return "/curve/divide", "POST", {"id": cid, "count": count}
    elif action == "extend":
        cid = args.get("id")
        end = args.get("end")
        length = args.get("length")
        if cid is None or end is None or length is None:
            return None, None, {"success": False, "data": "Missing 'id'/'end'/'length' for extend"}
        end_str = "start" if end == 0 else "end"
        return "/curve/extend", "POST", {"id": cid, "end": end_str, "length": length}
    elif action == "trim":
        cid = args.get("id")
        parameter = args.get("parameter")
        point = args.get("point")
        if not cid or (parameter is None and not point):
            return None, None, {"success": False, "data": "Missing params for trim"}
        payload = {"id": cid}
        if parameter is not None:
            payload["parameter"] = parameter
        if point:
            payload["point"] = point
        return "/curve/trim", "POST", payload
    elif action == "split":
        cid = args.get("id")
        parameter = args.get("parameter")
        if not cid or parameter is None:
            return None, None, {"success": False, "data": "Missing 'id'/'parameter' for split"}
        return "/curve/split", "POST", {"id": cid, "parameter": parameter}
    elif action == "rebuild":
        cid = args.get("id")
        if not cid:
            return None, None, {"success": False, "data": "Missing 'id' for rebuild"}
        payload = {"id": cid}
        if "degree" in args:
            payload["degree"] = args["degree"]
        if "pointCount" in args:
            payload["pointCount"] = args["pointCount"]
        return "/curve/rebuild", "POST", payload
    elif action == "fillet":
        id1 = args.get("id1")
        id2 = args.get("id2")
        radius = args.get("radius")
        if not id1 or not id2 or radius is None:
            return None, None, {"success": False, "data": "Missing 'id1'/'id2'/'radius' for fillet"}
        return "/curve/fillet", "POST", {"id1": id1, "id2": id2, "radius": radius}
    return None, None, {"success": False, "data": f"Invalid action '{action}'"}


def _transform_material_ops(args: dict) -> Tuple[str, str, dict]:
    action = args.get("action")
    if action == "list":
        return "/materials", "GET", {}
    elif action == "create":
        name = args.get("name")
        color = args.get("color")
        if not name or not color:
            return None, None, {"success": False, "data": "Missing 'name'/'color' for create"}
        payload = {"name": name, "color": color}
        for k in ("shininess", "transparency", "reflectivity"):
            if k in args:
                payload[k] = args[k]
        return "/materials", "POST", payload
    elif action == "delete":
        name = args.get("name")
        if not name:
            return None, None, {"success": False, "data": "Missing 'name' for delete"}
        return "/materials", "DELETE", {"name": name}
    elif action == "assign":
        name = args.get("name")
        obj_id = args.get("id")
        obj_ids = args.get("ids")
        if not name or (not obj_id and not obj_ids):
            return None, None, {"success": False, "data": "Missing 'name' and 'id'/'ids' for assign"}
        payload = {"name": name}
        if obj_id:
            payload["id"] = obj_id
        if obj_ids:
            payload["ids"] = obj_ids
        return "/materials/assign", "POST", payload
    return None, None, {"success": False, "data": f"Invalid action '{action}'"}


def _transform_block_info(args: dict) -> Tuple[str, str, dict]:
    name = args.get("name")
    if not name:
        return None, None, {"success": False, "data": "Missing 'name'"}
    return "/block/info", "POST", {"name": name}


def _transform_block_instances(args: dict) -> Tuple[str, str, dict]:
    name = args.get("name")
    if not name:
        return None, None, {"success": False, "data": "Missing 'name'"}
    depth = args.get("depth", 0)
    return "/block/instances", "POST", {"name": name, "depth": depth}


def _transform_block_nested(args: dict) -> Tuple[str, str, dict]:
    name = args.get("name")
    if not name:
        return None, None, {"success": False, "data": "Missing 'name'"}
    return "/block/nested", "POST", {"name": name}


def _transform_gh_set_reference(args: dict) -> Tuple[str, str, dict]:
    param_guid = args.get("paramGuid")
    rhino_obj_id = args.get("rhinoObjectId")
    if not param_guid or not rhino_obj_id:
        return None, None, {"success": False, "data": "Missing 'paramGuid'/'rhinoObjectId'"}
    return "/gh/set-reference", "POST", {"guid": param_guid, "rhinoId": rhino_obj_id}


def _transform_gh_get_reference(args: dict) -> Tuple[str, str, dict]:
    guid = args.get("guid")
    if not guid:
        return None, None, {"success": False, "data": "Missing 'guid'"}
    return "/gh/get-reference", "GET", {"guid": guid}


def _transform_gh_clear_reference(args: dict) -> Tuple[str, str, dict]:
    guid = args.get("guid")
    if not guid:
        return None, None, {"success": False, "data": "Missing 'guid'"}
    return "/gh/clear-reference", "POST", {"guid": guid}


def _transform_gh_set_script(args: dict) -> Tuple[str, str, dict]:
    guid = args.get("guid")
    if not guid:
        return None, None, {"success": False, "data": "Missing 'guid'"}
    payload = {"guid": guid}
    if "script" in args:
        payload["script"] = args["script"]
    return "/gh/script", "POST", payload


async def _local_gh_set_script_pins(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_set_script_pins

    return await _execute_gh_set_script_pins(kwargs, port)


async def _local_gh_update_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_update_script

    return await _execute_gh_update_script(kwargs, port)


def _normalize_gh_create_script_kwargs(kwargs: dict) -> dict:
    """Tolerate common local-model argument aliases before strict execution."""
    normalized = dict(kwargs)
    nested_params = normalized.pop("params", None)
    if isinstance(nested_params, dict):
        for key, value in nested_params.items():
            normalized.setdefault(key, value)

    if not normalized.get("code"):
        for alias in ("source", "script", "script_content"):
            value = normalized.get(alias)
            if value:
                normalized["code"] = value
                break

    for key in ("pins_in", "pins_out"):
        if type(normalized.get(key)) is tuple:
            normalized[key] = list(normalized[key])

    return normalized


async def _local_gh_create_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_create_script

    normalized = _normalize_gh_create_script_kwargs(kwargs)
    return await _execute_gh_create_script(
        normalized.get("language"),
        normalized,
        port,
        tool_name="gh_create_script",
    )


async def _local_gh_create_python_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_create_script

    normalized = _normalize_gh_create_script_kwargs(kwargs)
    return await _execute_gh_create_script(
        "python",
        normalized,
        port,
        tool_name="gh_create_python_script",
    )


async def _local_gh_create_csharp_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_create_script

    normalized = _normalize_gh_create_script_kwargs(kwargs)
    return await _execute_gh_create_script(
        "csharp",
        normalized,
        port,
        tool_name="gh_create_csharp_script",
    )


async def _local_chirp_create(port: int | None = None, **kwargs) -> dict:
    """Use Chirp's shared orchestration without canonical recording side effects."""

    from ..server import _execute_chirp_create

    result, _, _ = await _execute_chirp_create(dict(kwargs), port)
    return result


def _transform_gh_library(args: dict) -> Tuple[str, str, dict]:
    params = {}
    if "search" in args and args["search"] != "":
        params["search"] = args["search"]
    if "category" in args and args["category"] != "":
        params["category"] = args["category"]
    if args.get("limit"):
        params["limit"] = args["limit"]
    if "exact" in args:
        params["exact"] = args["exact"]
    return "/gh/library", "GET", params


def _transform_gh_document_open(args: dict) -> Tuple[str, str, dict]:
    path = args.get("path")
    if not path:
        return None, None, {"success": False, "data": "Missing 'path'"}
    return "/gh/document/open", "POST", {"path": path}


def _transform_gh_inspect_output(args: dict) -> Tuple[str, str, dict]:
    return "/gh/inspect-output", "POST", args


def _transform_execute(args: dict) -> Tuple[str, str, dict]:
    """Validate Python syntax before sending the script to Rhino.

    The native /execute route now runs user code inside its own wrapper and
    returns structured syntax/runtime failures instead of relying on Rhino's
    modal error dialogs. We still do a local compile() pre-check here so bad
    scripts fail fast without an HTTP roundtrip.
    """
    a = dict(args)
    code = a.get("code", "")
    if code:
        # Pre-dispatch syntax validation: fail locally for faster feedback.
        try:
            compile(code, "<rook_agent_script>", "exec")
        except SyntaxError as e:
            return None, None, {
                "success": False,
                "data": (
                    f"Python syntax error (line {e.lineno}): {e.msg}. "
                    "Fix the script and retry. The script was NOT sent to Rhino."
                ),
                # Signal to dispatch() that this failed pre-dispatch — skip
                # post-dispatch verification (the tool never reached Rhino,
                # so prompt-polling and modal-risk annotation are misleading).
                "_pre_dispatch_failure": True,
            }

        blocking_call = _find_blocking_rhinoscriptsyntax_call(code)
        if blocking_call:
            call_name, line_no = blocking_call
            return None, None, {
                "success": False,
                "data": (
                    f"Interactive Rhino input call {call_name} detected on line {line_no}. "
                    "rhino_execute must not invoke blocking rhinoscriptsyntax Get* prompts. "
                    "Use typed Rook tools or a non-interactive script instead. "
                    "Use rhino_command_interactive_prompt/cancel only for recovery. "
                    "The script was NOT sent to Rhino."
                ),
                "_pre_dispatch_failure": True,
            }
    return "/execute", "POST", a


def _transform_rhino_command(params: dict) -> Tuple[str, str, dict]:
    """Preflight validation before rhino_command reaches RunScript."""
    from ..preflight import preflight_rhino_command

    # Try to get the knowledge store for deep validation; fall back to
    # underscore-only check if it's unavailable.
    knowledge_store = None
    try:
        from ..server import command_learner
        knowledge_store = command_learner.knowledge_store
    except Exception:
        pass

    error = preflight_rhino_command(params.get("command"), knowledge_store)
    if error is not None:
        error["_pre_dispatch_failure"] = True
        return None, None, error
    return "/command", "POST", params


# ─── Vision Video transforms (PR-V4) ───────────────────────────────────
#
# Path-param video tools and rhino_video_jobs (manual ?limit folding).
# Mirrors the per-route shape used by server.call_tool exactly so the
# server↔dispatcher parity tests pass after normalizing
# (endpoint, method, data, port) — server passes port as kwarg, this
# dispatcher passes it positionally; the wire request is the same.
# Rationale (Codex review of scope v3):
#   - Path-param routes: cpp-httplib decodes URL-encoded characters
#     BEFORE route matching, so a literal '/' in job_id reroutes to
#     a generic 404. Reject slash/backslash here so the structured
#     Rook envelope returns instead.
#   - rhino_video_jobs: call_rhino drops None GET params (bridge.py
#     :549). A bridge-passthrough {"limit": None} would silently
#     become "absent → default 50" instead of the typed
#     InvalidRequest field:"limit" envelope managed produces. Build
#     the query string manually so explicit null/empty/garbage all
#     reach managed unchanged.

def _encode_video_job_id(jid: Any) -> tuple[str | None, dict | None]:
    """Pre-validate and URL-encode a video job_id for path-param routes
    (/vision/video/jobs/{job_id}, .../{job_id}/cancel, .../{job_id}/result).

    Returns ``(encoded, None)`` on success or ``(None, error_dict)`` on
    rejection — callers early-return the error as the tool result.

    Same posture as server.py's ``_encode_vision_artifact_id``: native
    httplib decodes URL-encoded characters before route matching, so a
    literal slash in job_id misroutes to a generic 404 with no managed
    envelope. Reject slash/backslash here so the structured Rook envelope
    returns instead. ``RequireArtifactId``-equivalent GUID validation
    happens at the managed boundary (``VideoOpHandler.TryParseJobId``).

    The dispatcher transform attaches ``_pre_dispatch_failure: True`` to
    the error dict so ``ToolDispatcher`` skips post-dispatch verification
    annotation. ``server.call_tool`` does not consume that flag.
    """
    from urllib.parse import quote as _quote

    if not isinstance(jid, str) or not jid:
        return None, {
            "success": False,
            "data": "job_id must be a non-empty string.",
        }
    if "/" in jid or "\\" in jid:
        return None, {
            "success": False,
            "data": (
                f"job_id must not contain '/' or '\\\\' "
                f"(got: {jid!r}). Supply a canonical GUID — e.g. "
                "12345678-1234-1234-1234-123456789abc."
            ),
        }
    return _quote(jid, safe=""), None


def _video_status(params: dict) -> Tuple[Optional[str], str, Optional[dict]]:
    encoded, err = _encode_video_job_id(params.get("job_id", ""))
    if err is not None:
        err["_pre_dispatch_failure"] = True
        return None, "", err
    return f"/vision/video/jobs/{encoded}", "GET", None


def _video_cancel(params: dict) -> Tuple[Optional[str], str, Optional[dict]]:
    encoded, err = _encode_video_job_id(params.get("job_id", ""))
    if err is not None:
        err["_pre_dispatch_failure"] = True
        return None, "", err
    # Body shape MUST match server.call_tool's invocation
    # (call_rhino(..., "POST", {}, port=port)) so the parity tests
    # see equivalent (endpoint, method, data, port) tuples after
    # normalization. None would be mechanically accepted by call_rhino
    # but document-context handling can synthesize a body when data is
    # None — silently diverging from the MCP path.
    return f"/vision/video/jobs/{encoded}/cancel", "POST", {}


def _video_result(params: dict) -> Tuple[Optional[str], str, Optional[dict]]:
    encoded, err = _encode_video_job_id(params.get("job_id", ""))
    if err is not None:
        err["_pre_dispatch_failure"] = True
        return None, "", err
    return f"/vision/video/jobs/{encoded}/result", "GET", None


def _video_jobs(params: dict) -> Tuple[Optional[str], str, Optional[dict]]:
    """list_video_jobs — manual ?limit folding.

    Forwards whatever the caller sent (int, string, null, anything) so
    the managed VideoOpHandler.TryGetOptionalPositiveInt is the single
    validation boundary for ``limit``. Bad shapes surface as the typed
    InvalidRequest envelope with ``field:"limit"`` — same wire response
    whether the caller used MCP, agent dispatcher, or curl.
    """
    from urllib.parse import quote as _quote

    if "limit" in params:
        raw = params["limit"]
        limit_str = "" if raw is None else str(raw)
        return (
            f"/vision/video/jobs?limit={_quote(limit_str, safe='')}",
            "GET",
            None,
        )
    return "/vision/video/jobs", "GET", None


def _encode_reconstruction_job_id(jid: Any) -> tuple[str | None, dict | None]:
    """Pre-validate and URL-encode reconstruction job_id path params."""
    from urllib.parse import quote as _quote

    if not isinstance(jid, str) or not jid:
        return None, {
            "success": False,
            "data": "job_id must be a non-empty string.",
        }
    if "/" in jid or "\\" in jid:
        return None, {
            "success": False,
            "data": (
                f"job_id must not contain '/' or '\\\\' "
                f"(got: {jid!r}). Supply a canonical GUID — e.g. "
                "12345678-1234-1234-1234-123456789abc."
            ),
        }
    return _quote(jid, safe=""), None


def _reconstruction_models(params: dict) -> Tuple[str, str, Optional[dict]]:
    from urllib.parse import urlencode as _urlencode

    query = {}
    if "include_experimental" in params:
        value = params["include_experimental"]
        query["include_experimental"] = "true" if value is True else "false" if value is False else str(value)
    if "include_hidden" in params:
        value = params["include_hidden"]
        query["include_hidden"] = "true" if value is True else "false" if value is False else str(value)

    endpoint = "/reconstruction/2d-to-3d/models"
    if query:
        endpoint = f"{endpoint}?{_urlencode(query)}"
    return endpoint, "GET", None


def _reconstruction_jobs(params: dict) -> Tuple[str, str, Optional[dict]]:
    from urllib.parse import quote as _quote

    if "limit" in params:
        raw = params["limit"]
        if raw is None:
            return "/reconstruction/2d-to-3d/jobs", "GET", None
        limit_str = str(raw)
        return (
            f"/reconstruction/2d-to-3d/jobs?limit={_quote(limit_str, safe='')}",
            "GET",
            None,
        )
    return "/reconstruction/2d-to-3d/jobs", "GET", None


def _reconstruction_status(params: dict) -> Tuple[Optional[str], str, Optional[dict]]:
    encoded, err = _encode_reconstruction_job_id(params.get("job_id", ""))
    if err is not None:
        err["_pre_dispatch_failure"] = True
        return None, "", err
    return f"/reconstruction/2d-to-3d/jobs/{encoded}", "GET", None


def _reconstruction_cancel(params: dict) -> Tuple[Optional[str], str, Optional[dict]]:
    encoded, err = _encode_reconstruction_job_id(params.get("job_id", ""))
    if err is not None:
        err["_pre_dispatch_failure"] = True
        return None, "", err
    return f"/reconstruction/2d-to-3d/jobs/{encoded}/cancel", "POST", {}


def _reconstruction_result(params: dict) -> Tuple[Optional[str], str, Optional[dict]]:
    encoded, err = _encode_reconstruction_job_id(params.get("job_id", ""))
    if err is not None:
        err["_pre_dispatch_failure"] = True
        return None, "", err
    return f"/reconstruction/2d-to-3d/jobs/{encoded}/result", "GET", None


# Registry of all transform functions
TRANSFORM_FUNCTIONS: Dict[str, Callable[[dict], Tuple[str, str, dict]]] = {
    "rhino_command":           _transform_rhino_command,
    "rhino_boolean":           _transform_boolean,
    "rhino_curve_boolean_union":        _transform_curve_boolean_union,
    "rhino_curve_boolean_difference":   _transform_curve_boolean_difference,
    "rhino_curve_boolean_intersection": _transform_curve_boolean_intersection,
    "rhino_extrude":           _transform_extrude,
    "rhino_text":              _transform_text,
    "rhino_select_all":        _transform_select_all,
    "rhino_select_none":       _transform_select_none,
    "rhino_select_invert":     _transform_select_invert,
    "rhino_deselect":          _transform_deselect,
    "rhino_intersect_curves":  _transform_intersect_curves,
    "rhino_intersect_breps":   _transform_intersect_breps,
    "rhino_intersect_plane":   _transform_intersect_plane,
    "rhino_split_brep":        _transform_split_brep,
    "rhino_trim_brep":         _transform_trim_brep,
    "rhino_document_ops":      _transform_document_ops,
    "rhino_curve_ops":         _transform_curve_ops,
    "rhino_material_ops":      _transform_material_ops,
    "rhino_block_info":        _transform_block_info,
    "rhino_block_instances":   _transform_block_instances,
    "rhino_block_nested":      _transform_block_nested,
    "gh_set_reference":        _transform_gh_set_reference,
    "gh_get_reference":        _transform_gh_get_reference,
    "gh_clear_reference":      _transform_gh_clear_reference,
    "gh_set_script":           _transform_gh_set_script,
    "gh_library":              _transform_gh_library,
    "gh_document_open":        _transform_gh_document_open,
    "gh_inspect_output":       _transform_gh_inspect_output,
    "rhino_execute":           _transform_execute,

    # --- Vision Video (PR-V4) ---
    "rhino_video_status":      _video_status,
    "rhino_video_cancel":      _video_cancel,
    "rhino_video_result":      _video_result,
    "rhino_video_jobs":        _video_jobs,

    # --- Rook Reconstruction (2D to 3D) ---
    "rhino_2d_to_3d_models":   _reconstruction_models,
    "rhino_2d_to_3d_jobs":     _reconstruction_jobs,
    "rhino_2d_to_3d_status":   _reconstruction_status,
    "rhino_2d_to_3d_cancel":   _reconstruction_cancel,
    "rhino_2d_to_3d_result":   _reconstruction_result,
}


# =============================================================================
# Knowledge-Wrapped Tools
# =============================================================================
#
# These 4 GH tools get operation gotcha injection, correction detection,
# and staleness tracking — matching the server.py wrappers but without
# session recording (agents use their own MetricsStore via Seam 3).
#
# Maps tool_name → (operation_name, context_builder_fn)

KNOWLEDGE_WRAPPED_TOOLS: Dict[str, Tuple[str, Callable[[dict], dict]]] = {
    # Canvas Graph Protocol: gh_edit handles its own knowledge/session recording.
    # This dict is intentionally empty — retained for structural compatibility.
}


# =============================================================================
# Local Tool Builders
# =============================================================================

def build_local_tools() -> Dict[str, Any]:
    """Build dict of local tool handlers for agent use.

    These execute as pure Python, never touching the MCP dispatcher.
    Each is an async callable(params) -> dict.
    """
    tools: Dict[str, Any] = {}

    # --- knowledge_query ---
    try:
        from ..knowledge import query_knowledge_tiered

        async def _knowledge_query(
            intent: str = None, tool: str = None,
            depth: str = None, context_name: str = None, **kwargs
        ) -> dict:
            result = query_knowledge_tiered(
                intent=intent, tool=tool, depth=depth, context_name=context_name,
            )
            return {"success": True, "data": result}

        tools["knowledge_query"] = _knowledge_query
    except ImportError:
        logger.debug("knowledge_query local tool unavailable (import failed)")

    # --- rhino_command_knowledge / rhino_knowledge_query ---
    try:
        from ..learning.command_knowledge_store import get_command_knowledge_store

        async def _rhino_command_knowledge(command: str = None, **kwargs) -> dict:
            store = get_command_knowledge_store()
            if command:
                pattern = store.get(command)
                if pattern:
                    return {"success": True, "data": pattern.to_dict()}
                return {"success": False, "data": f"No knowledge found for {command}"}

            all_patterns = store.get_all()
            return {
                "success": True,
                "data": {
                    "total_commands": len(all_patterns),
                    "commands": {
                        name: {
                            "description": p.description,
                            "modes": list(p.modes.keys()),
                            "observations_count": p.observations_count,
                        }
                        for name, p in all_patterns.items()
                    },
                },
            }

        tools["rhino_command_knowledge"] = _rhino_command_knowledge
        tools["rhino_knowledge_query"] = _rhino_command_knowledge
    except ImportError:
        logger.debug("rhino_command_knowledge local tool unavailable (import failed)")

    # --- gh_knowledge_query ---
    try:
        from ..learning.gh_knowledge import gh_query_knowledge

        async def _gh_knowledge_query(intent: str = "", depth: str = "context", **kwargs) -> dict:
            result = gh_query_knowledge(intent, depth)
            return {"success": True, "data": result}

        tools["gh_knowledge_query"] = _gh_knowledge_query
    except ImportError:
        logger.debug("gh_knowledge_query local tool unavailable (import failed)")

    # --- scene_exact_neighbors (Python-side projection over the OCCT exact route) ---
    try:
        from ..scene.scene_graph import get_scene_graph
        from ..scene.exact_projection import get_exact_projector

        async def _scene_exact_neighbors(
            object_ids=None, candidate_scope="broad_phase_default",
            port: int | None = None, **kwargs,
        ) -> dict:
            if not object_ids:
                return {"success": False, "data": "Missing object_ids parameter"}
            sg = get_scene_graph()
            projector = get_exact_projector(sg)
            payload = await projector.project(
                object_ids, candidate_scope=candidate_scope, port=port)
            if not payload.get("success", True):
                return {"success": False, "data": payload.get("error", "exact projection failed")}
            return {"success": True, "data": payload}

        tools["scene_exact_neighbors"] = _scene_exact_neighbors
    except ImportError:
        logger.debug("scene_exact_neighbors local tool unavailable (import failed)")

    # --- scene_refine_containment (Python-side semantic containment refinement) ---
    try:
        from ..scene.scene_graph import get_scene_graph
        from ..scene.containment_refinement import get_containment_refiner

        async def _scene_refine_containment(object_ids=None, port: int | None = None, **kwargs) -> dict:
            if not object_ids:
                return {"success": False, "data": "Missing object_ids parameter"}
            sg = get_scene_graph()
            refiner = get_containment_refiner(sg)
            payload = await refiner.refine(object_ids, port=port)
            if not payload.get("success", True):
                return {"success": False, "data": payload.get("error", "containment refine failed")}
            return {"success": True, "data": payload}

        tools["scene_refine_containment"] = _scene_refine_containment
    except ImportError:
        logger.debug("scene_refine_containment local tool unavailable (import failed)")

    tools["gh_create_script"] = _local_gh_create_script
    tools["gh_create_python_script"] = _local_gh_create_python_script
    tools["gh_create_csharp_script"] = _local_gh_create_csharp_script
    tools["chirp_create"] = _local_chirp_create

    # --- scene_project_bim_relationships (Python-side BIM relationship projection) ---
    try:
        from ..scene.bim_relationship_projection import (
            BimProjectionValidationError,
            project_bim_relationships_for_tool,
        )

        async def _scene_project_bim_relationships(
            sidecar_path=None,
            object_ids=None,
            category_filters=None,
            include_rooms=True,
            include_levels=True,
            port: int | None = None,
            **kwargs,
        ) -> dict:
            if not sidecar_path:
                return {
                    "success": False,
                    "error": "bim_projection_invalid_sidecar",
                    "message": "Missing required sidecar_path parameter.",
                }
            try:
                return await project_bim_relationships_for_tool(
                    sidecar_path,
                    object_ids=object_ids,
                    category_filters=category_filters,
                    include_rooms=include_rooms,
                    include_levels=include_levels,
                    port=port,
                )
            except BimProjectionValidationError as exc:
                return {
                    "success": False,
                    "error": "bim_projection_invalid_sidecar",
                    "message": str(exc),
                }

        tools["scene_project_bim_relationships"] = _scene_project_bim_relationships
    except ImportError:
        logger.debug("scene_project_bim_relationships local tool unavailable (import failed)")

    # --- scene_project_relationship_facts (Python-side relationship fact projection) ---
    try:
        from ..scene.relationship_fact_projection import project_relationship_facts_for_tool

        async def _scene_project_relationship_facts(
            graph_source=None,
            graph_revision=None,
            poses=None,
            object_ids=None,
            source_mode="authored_graph_user_strings",
            strict=False,
            port: int | None = None,
            **kwargs,
        ) -> dict:
            return await project_relationship_facts_for_tool(
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                object_ids=object_ids,
                source_mode=source_mode,
                strict=strict,
                port=port,
            )

        tools["scene_project_relationship_facts"] = _scene_project_relationship_facts
    except ImportError:
        logger.debug("scene_project_relationship_facts local tool unavailable (import failed)")

    # --- scene_semantic_relationships (Python-side semantic relationship inspector) ---
    try:
        from ..scene.scene_graph import get_scene_graph
        from ..scene.semantic_relationship_inspector import query_semantic_relationships

        async def _scene_semantic_relationships(
            object_ids=None,
            graph_source=None,
            graph_revision=None,
            poses=None,
            relationship_types=None,
            status=None,
            provenance=None,
            direction="both",
            **kwargs,
        ) -> dict:
            return query_semantic_relationships(
                get_scene_graph(),
                object_ids=object_ids,
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                relationship_types=relationship_types,
                status=status,
                provenance=provenance,
                direction=direction,
            )

        tools["scene_semantic_relationships"] = _scene_semantic_relationships
    except ImportError:
        logger.debug("scene_semantic_relationships local tool unavailable (import failed)")

    # --- scene_relationship_evidence (Python-side relationship geometry evidence) ---
    try:
        from ..scene.relationship_geometry_evidence import query_relationship_evidence_for_tool

        async def _scene_relationship_evidence(
            object_ids=None,
            graph_source=None,
            graph_revision=None,
            poses=None,
            relationship_types=None,
            relationship_fact_ids=None,
            tolerance_m=0.01,
            port: int | None = None,
            **kwargs,
        ) -> dict:
            return await query_relationship_evidence_for_tool(
                object_ids=object_ids,
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                relationship_types=relationship_types,
                relationship_fact_ids=relationship_fact_ids,
                tolerance_m=tolerance_m,
                port=port,
            )

        tools["scene_relationship_evidence"] = _scene_relationship_evidence
    except ImportError:
        logger.debug("scene_relationship_evidence local tool unavailable (import failed)")

    # --- scene_relationship_profile (Python-side relationship vocabulary profile) ---
    try:
        from ..scene.relationship_profile import resolve_relationship_profile

        async def _scene_relationship_profile(
            project_root=None,
            **kwargs,
        ) -> dict:
            return resolve_relationship_profile(project_root=project_root)

        tools["scene_relationship_profile"] = _scene_relationship_profile
    except ImportError:
        logger.debug("scene_relationship_profile local tool unavailable (import failed)")

    # --- scene_object_semantic_context (Python-side semantic context cards) ---
    try:
        from ..scene.object_semantic_context import query_object_semantic_context
        from ..scene.scene_graph import get_scene_graph

        async def _scene_object_semantic_context(
            object_ids=None,
            graph_source=None,
            graph_revision=None,
            poses=None,
            relationship_types=None,
            status=None,
            provenance=None,
            direction="both",
            max_groups=None,
            max_facts_per_group=None,
            project_root=None,
            **kwargs,
        ) -> dict:
            return query_object_semantic_context(
                get_scene_graph(),
                object_ids=object_ids,
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                relationship_types=relationship_types,
                status=status,
                provenance=provenance,
                direction=direction,
                max_groups=max_groups,
                max_facts_per_group=max_facts_per_group,
                project_root=project_root,
            )

        tools["scene_object_semantic_context"] = _scene_object_semantic_context
    except ImportError:
        logger.debug("scene_object_semantic_context local tool unavailable (import failed)")

    # --- scene_bim_facts (Python-side BIM facts query) ---
    try:
        from ..scene.scene_graph import get_scene_graph
        from ..scene.bim_facts_query import query_bim_facts

        async def _scene_bim_facts(
            mode=None,
            object_ids=None,
            room_id=None,
            room_name=None,
            level_name=None,
            host_object_id=None,
            detail="compact",
            limit=None,
            sample_limit=None,
            **kwargs,
        ) -> dict:
            return query_bim_facts(
                get_scene_graph(),
                mode=mode or "",
                object_ids=object_ids,
                room_id=room_id,
                room_name=room_name,
                level_name=level_name,
                host_object_id=host_object_id,
                detail=detail,
                limit=limit,
                sample_limit=sample_limit,
            )

        tools["scene_bim_facts"] = _scene_bim_facts
    except ImportError:
        logger.debug("scene_bim_facts local tool unavailable (import failed)")

    # --- rookbim_export_preset_to_rhino (Python-side demo workflow orchestration) ---
    try:
        from .. import rookbim_export_to_rhino
        from ..scene.bim_relationship_projection import (
            BimProjectionValidationError,
            project_bim_relationships_for_tool,
        )
        from ..scene.bim_facts_query import query_bim_facts
        from ..scene.scene_graph import get_scene_graph

        async def _rookbim_export_preset_to_rhino(**kwargs) -> dict:
            def _query_bim_facts_for_workflow(**query_kwargs):
                return query_bim_facts(get_scene_graph(), **query_kwargs)

            return await rookbim_export_to_rhino.export_preset_to_rhino(
                dict(kwargs),
                call_rhino_fn=call_rhino,
                project_relationships_fn=project_bim_relationships_for_tool,
                query_bim_facts_fn=_query_bim_facts_for_workflow,
                projection_exception_types=(BimProjectionValidationError,),
            )

        tools["rookbim_export_preset_to_rhino"] = _rookbim_export_preset_to_rhino
    except ImportError:
        logger.debug("rookbim_export_preset_to_rhino local tool unavailable (import failed)")

    tools["gh_update_script"] = _local_gh_update_script
    tools["gh_set_script_pins"] = _local_gh_set_script_pins

    # --- rhino_instances ---
    try:
        from ..bridge import discover_instances

        async def _rhino_instances(**kwargs) -> dict:
            instances = discover_instances()
            return {
                "success": True,
                "data": {
                    "count": len(instances),
                    "instances": instances,
                },
            }

        tools["rhino_instances"] = _rhino_instances
    except ImportError:
        logger.debug("rhino_instances local tool unavailable (import failed)")

    # --- gh_constraints ---
    try:
        from ..learning.constraints import get_constraint_checker

        async def _gh_constraints(
            component: str = None, components: list = None,
            category: str = None, **kwargs
        ) -> dict:
            checker = get_constraint_checker()
            if component:
                constraints = checker.get_constraints(component)
                if constraints:
                    return {
                        "success": True,
                        "data": {
                            "component": constraints.component_name,
                            "category": constraints.category,
                            "constraints": constraints.to_dict(),
                            "summary": checker.get_constraint_summary(component),
                        },
                    }
                return {
                    "success": True,
                    "data": {
                        "component": component,
                        "message": f"No constraints defined for '{component}'",
                        "available_components": checker.get_all_constrained_components(),
                    },
                }
            elif components:
                warnings = checker.get_warnings_for_components(components)
                return {
                    "success": True,
                    "data": {
                        "components_queried": components,
                        "warnings": [w.to_dict() for w in warnings],
                        "error_count": sum(1 for w in warnings if w.severity == "error"),
                        "warning_count": sum(1 for w in warnings if w.severity == "warning"),
                    },
                }
            elif category:
                warnings = checker.get_warnings_by_category(category)
                return {
                    "success": True,
                    "data": {
                        "category": category,
                        "warnings": [w.to_dict() for w in warnings],
                        "component_count": len(set(w.component for w in warnings)),
                    },
                }
            else:
                return {
                    "success": True,
                    "data": {
                        "total_components": len(checker),
                        "available_components": checker.get_all_constrained_components(),
                        "hint": "Use 'component', 'components', or 'category' to query",
                    },
                }

        tools["gh_constraints"] = _gh_constraints
    except ImportError:
        logger.debug("gh_constraints local tool unavailable (import failed)")

    # --- rhino_command_select ---
    try:
        from ..learning.command_learner import CommandLearner

        async def _rhino_command_select(intent: str = "", **kwargs) -> dict:
            if not intent:
                return {"success": False, "data": "Missing required parameter: intent"}
            learner = CommandLearner()
            selection = learner.select_command(intent)
            return {"success": True, "data": selection}

        tools["rhino_command_select"] = _rhino_command_select
    except ImportError:
        logger.debug("rhino_command_select local tool unavailable (import failed)")

    # --- rhino_command_queue ---
    try:
        from ..learning.command_learner import CommandLearner as _CL

        async def _rhino_command_queue(priority: str = None, **kwargs) -> dict:
            learner = _CL()
            queue = learner.get_learning_queue()
            if priority:
                queue = [q for q in queue if q.get("priority") == priority]
            return {
                "success": True,
                "data": {"total_commands": len(queue), "queue": queue},
            }

        tools["rhino_command_queue"] = _rhino_command_queue
    except ImportError:
        logger.debug("rhino_command_queue local tool unavailable (import failed)")

    # --- gh_canvas_cleanup (CanvasLayout pipeline) ---
    try:
        from ..learning.canvas_align import component_guid
        from ..learning.canvas_layout import CanvasLayout, LayoutSettings

        async def _gh_canvas_cleanup(
            start_x: int = 50, start_y: int = 50,
            horizontal_gap: int = 30, vertical_gap: int = 20,
            max_layer_width: int = 4, dry_run: bool = False,
            style: str = "expanded",
            collision_detection: bool = True,
            expand_by_height: bool = True,
            center_branches: bool = True,
            anchor_guid: str | None = None,
            snap_to_grid: bool = False,
            grid_size: float = 8.0,
            **kwargs,
        ) -> dict:
            # 1. Query canvas
            query_result = await call_rhino("/gh/query", "GET", {})
            if not query_result.get("success"):
                return {"success": False, "data": "Failed to query canvas"}

            query_data = query_result.get("data", {})
            if isinstance(query_data, dict):
                components = query_data.get("objects", [])
            elif isinstance(query_data, list):
                components = query_data
            else:
                components = []
            components = [comp for comp in components if isinstance(comp, dict)]
            if not components:
                return {"success": True, "data": {"moved": 0, "message": "Canvas is empty"}}

            # 2. Get connections for each component
            connections: dict = {}
            for comp in components:
                guid = component_guid(comp)
                if not guid:
                    continue
                conn_result = await call_rhino("/gh/connections", "GET", {"guid": guid})
                if conn_result.get("success"):
                    connections[guid] = conn_result.get("data", {})
                else:
                    connections[guid] = {"inputs": [], "outputs": []}

            # 3. Query groups
            groups_data = []
            try:
                groups_result = await call_rhino("/gh/groups", "GET", {})
                if groups_result.get("success"):
                    group_payload = groups_result.get("data", {})
                    if isinstance(group_payload, dict):
                        groups_data = group_payload.get("groups", [])
                    elif isinstance(group_payload, list):
                        groups_data = group_payload
            except Exception:
                pass

            # 4. Build settings and run CanvasLayout
            settings = LayoutSettings(
                horizontal_gap=horizontal_gap,
                vertical_gap=vertical_gap,
                style=style,
                collision_detection=collision_detection,
                expand_by_height=expand_by_height,
                center_branches=center_branches,
                snap_to_grid=snap_to_grid,
                grid_size=grid_size,
                anchor_guid=anchor_guid,
            )

            canvas_layout = CanvasLayout(settings)
            positions = canvas_layout.run(
                components=components,
                connections=connections,
                groups=groups_data,
                start_x=start_x,
                start_y=start_y,
                max_layer_width=max_layer_width,
            )

            result_data = {
                "success": True,
                "components_analyzed": len(components),
                "layers": canvas_layout.num_layers,
                "positions": positions,
            }

            # 5. Move components (unless dry run)
            if not dry_run and positions:
                move_positions = [
                    {"guid": guid, "x": pos["x"], "y": pos["y"]}
                    for guid, pos in positions.items()
                ]
                move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions})
                result_data["move_result"] = move_result
                result_data["dry_run"] = False

                # 6. Resize groups to fit members
                if groups_data:
                    for group in groups_data:
                        if not isinstance(group, dict):
                            continue
                        group_guid = group.get("guid") or group.get("Guid")
                        if group_guid:
                            try:
                                await call_rhino("/gh/group-resize", "POST", {
                                    "guid": group_guid,
                                    "padding": settings.group_padding,
                                })
                            except Exception:
                                pass
            else:
                result_data["dry_run"] = True

            return result_data

        tools["gh_canvas_cleanup"] = _gh_canvas_cleanup
    except ImportError:
        logger.debug("gh_canvas_cleanup local tool unavailable (import failed)")

    # --- gh_align ---
    try:
        from ..learning.canvas_align import align_positions, canvas_objects_from_payload, component_guid

        async def _gh_align(
            guids: list[str],
            direction: str = "left",
            anchor: str = "first",
            **kwargs,
        ) -> dict:
            if not guids or len(guids) < 2:
                return {"success": False, "data": "Need at least 2 GUIDs"}

            query_result = await call_rhino("/gh/query", "GET", {})
            if not query_result.get("success"):
                return {"success": False, "data": "Failed to query canvas"}

            all_comps = canvas_objects_from_payload(query_result.get("data", {}))
            guid_set = set(guids)
            comps = [c for c in all_comps if component_guid(c) in guid_set]
            if len(comps) < 2:
                return {"success": False, "data": f"Found {len(comps)} of {len(guids)} components"}

            move_positions = align_positions(comps, direction, anchor)
            move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions})
            return {"success": True, "data": {"aligned": len(move_positions), "direction": direction, "move_result": move_result}}

        tools["gh_align"] = _gh_align
    except ImportError:
        logger.debug("gh_align local tool unavailable (import failed)")

    # --- gh_distribute ---
    try:
        from ..learning.canvas_align import canvas_objects_from_payload, component_guid, distribute_positions

        async def _gh_distribute(
            guids: list[str],
            axis: str = "horizontal",
            spacing: float | None = None,
            **kwargs,
        ) -> dict:
            if not guids or len(guids) < 2:
                return {"success": False, "data": "Need at least 2 GUIDs"}

            query_result = await call_rhino("/gh/query", "GET", {})
            if not query_result.get("success"):
                return {"success": False, "data": "Failed to query canvas"}

            all_comps = canvas_objects_from_payload(query_result.get("data", {}))
            guid_set = set(guids)
            comps = [c for c in all_comps if component_guid(c) in guid_set]
            if len(comps) < 2:
                return {"success": False, "data": f"Found {len(comps)} of {len(guids)} components"}

            move_positions = distribute_positions(comps, axis, spacing)
            move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions})
            return {"success": True, "data": {"distributed": len(move_positions), "axis": axis, "move_result": move_result}}

        tools["gh_distribute"] = _gh_distribute
    except ImportError:
        logger.debug("gh_distribute local tool unavailable (import failed)")

    # --- gh_straighten_wires ---
    try:
        from ..learning.canvas_align import canvas_objects_from_payload, component_guid, straighten_wire_positions

        async def _gh_straighten_wires(
            guids: list[str] | None = None,
            **kwargs,
        ) -> dict:
            query_result = await call_rhino("/gh/query", "GET", {})
            if not query_result.get("success"):
                return {"success": False, "data": "Failed to query canvas"}

            components = canvas_objects_from_payload(query_result.get("data", {}))
            if not components:
                return {"success": True, "data": {"straightened": 0, "message": "Canvas is empty"}}

            connections: dict = {}
            for comp in components:
                guid = component_guid(comp)
                if not guid:
                    continue
                conn_result = await call_rhino("/gh/connections", "GET", {"guid": guid})
                if conn_result.get("success"):
                    connections[guid] = conn_result.get("data", {})
                else:
                    connections[guid] = {"inputs": [], "outputs": []}

            move_positions = straighten_wire_positions(components, connections, guids)
            if move_positions:
                move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions})
                return {"success": True, "data": {"straightened": len(move_positions), "move_result": move_result}}
            return {"success": True, "data": {"straightened": 0, "message": "No wires to straighten"}}

        tools["gh_straighten_wires"] = _gh_straighten_wires
    except ImportError:
        logger.debug("gh_straighten_wires local tool unavailable (import failed)")

    return tools


# =============================================================================
# All known tool names (for coverage auditing)
# =============================================================================

ALL_DISPATCHER_TOOLS: Set[str] = (
    set(BRIDGE_ROUTES.keys())
    | set(TRANSFORM_FUNCTIONS.keys())
    # Local tools are dynamic, added at runtime
)


# =============================================================================
# ToolDispatcher
# =============================================================================

class ToolDispatcher:
    """Direct tool execution for agents, bypassing MCP dispatcher.

    Three-tier dispatch:
      1. Local tools → direct Python function calls
      2. Transform tools → parameter rewriting → call_rhino()
      3. Bridge tools → call_rhino() directly via routing table

    The dispatch() method has the same signature as _mcp_tool_executor:
        async (name: str, params: dict) -> dict

    This means base_agent.py needs zero changes — it just switches
    which callable is assigned to self._tool_executor.

    Args:
        port: Optional Rhino instance port for multi-instance support.
        local_tools: Dict of tool_name → async callable(**params) -> dict.
    """

    def __init__(
        self,
        port: int | None = None,
        local_tools: Optional[Dict[str, Any]] = None,
    ):
        self._port = port
        self._local_tools: Dict[str, Any] = {
            name: handler
            for name, handler in (local_tools or {}).items()
            if resolve_contained_tool(name) is None
        }
        self._call_count = 0
        # Correction detection state (mirrors server.py's _gh_recent_failures)
        self._recent_failures: Dict[str, dict] = {}
        self._failure_expiry_seconds = 30 * 60  # 30 minutes

    def register_local(self, name: str, handler: Any) -> None:
        """Register a single local tool handler."""
        if resolve_contained_tool(name) is not None:
            return
        self._local_tools[name] = handler

    def register_locals(self, tools: Dict[str, Any]) -> None:
        """Register multiple local tool handlers."""
        self._local_tools.update(
            (name, handler)
            for name, handler in tools.items()
            if resolve_contained_tool(name) is None
        )

    async def dispatch(self, name: str, params: dict) -> dict:
        """Dispatch a tool call to the appropriate handler.

        Returns a plain dict (never TextContent). No MCP knowledge injection,
        no session recording — those are the agent's responsibility via Seam 1-4.

        Post-dispatch verification (execution_policy) runs after all tiers return,
        covering CREATION_TOOLS and MODAL_RISK_TOOLS. This is the single enforcement point — both chat
        and agent paths converge here.
        """
        denial = deny_if_contained(name, DispatchOrigin.TOOL_DISPATCHER)
        if denial is not None:
            return {"success": False, "data": denial}
        self._call_count += 1
        params = dict(params) if params else {}
        handoff = model_facing_script_handoff(name, params)
        if handoff is not None:
            handoff.pop("_is_handoff", None)
            return handoff
        if name == "gh_edit":
            admission = admit_gh_edit_request(params)
            if admission is not None:
                return admission
        port = params.pop("port", None) or self._port

        result = await self._dispatch_inner(name, params, port)

        # --- Post-dispatch verification (single enforcement point) ---
        # Covers CREATION_TOOLS (silent-failure detection via objectsCreated),
        # MODAL_RISK_TOOLS (prompt idle check).
        # Skip when _pre_dispatch_failure is set — the tool never reached Rhino,
        # so prompt-polling and modal-risk notes would be misleading.
        if (
            isinstance(result, dict)
            and not result.pop("_pre_dispatch_failure", False)
            and needs_verification(name, result)
        ):
            prompt_state = None
            prompt_poll_failed = False
            if result.get("success"):
                try:
                    prompt_state = await call_rhino(
                        "/command/prompt", "GET", None, port
                    )
                except Exception:
                    prompt_poll_failed = True
            result = annotate_result(name, result, prompt_state, prompt_poll_failed)

        return result

    async def _dispatch_inner(self, name: str, params: dict, port: int | None) -> dict:
        """Core dispatch logic — routes to the correct tier without verification."""
        denial = deny_if_contained(name, DispatchOrigin.TOOL_DISPATCHER)
        if denial is not None:
            return {"success": False, "data": denial}
        if name in _DEPRECATED_INTERACTIVE_COMMAND_TOOLS:
            return _interactive_command_deprecated_result(name)

        # --- Tier 1: Local Python tools ---
        if name in self._local_tools:
            return await self._call_local(name, params, port)

        # --- Tier 1.5: Knowledge-wrapped tools ---
        if name in KNOWLEDGE_WRAPPED_TOOLS:
            return await self._dispatch_with_knowledge(name, params, port)

        # --- Tier 2: Transform tools ---
        if name in TRANSFORM_FUNCTIONS:
            try:
                endpoint, method, data = TRANSFORM_FUNCTIONS[name](params)
                # Transform returned an error (endpoint is None)
                if endpoint is None:
                    return data  # data contains the error dict
                result = await call_rhino(endpoint, method, data, port)
                if name == "gh_library":
                    result = project_gh_library_result(params, result)
                return result
            except Exception as e:
                logger.error(f"Transform failed for {name}: {e}")
                return {"success": False, "data": f"Transform error: {e}"}

        # --- Tier 3: Simple bridge passthrough ---
        if name in BRIDGE_ROUTES:
            endpoint, method = BRIDGE_ROUTES[name]
            if name in STRICT_NO_ARGUMENT_BRIDGE_TOOLS and params:
                return {
                    "success": False,
                    "error": "unexpected_arguments",
                    "message": (
                        f"{name} does not accept arguments. To create a C# "
                        "script component, call gh_create_csharp_script or "
                        "gh_create_script with language='csharp'."
                    ),
                    "data": {
                        "error": "unexpected_arguments",
                        "unexpected": sorted(params.keys()),
                    },
                    "_pre_dispatch_failure": True,
                }
            data = params if params else None
            result = await call_rhino(endpoint, method, data, port)
            if name == "gh_status":
                result = normalize_gh_status_result(result)
            if name == "gh_edit":
                result = apply_gh_edit_contract(result, strict_partial_success=True)
            if name in GH_READINESS_HOIST_TOOLS:
                result = _hoist_nested_verification_fields(result)
            if not result.get("success"):
                logger.warning(f"Bridge call failed for {name} -> {endpoint}: {result}")
            return result

        # --- Unknown tool ---
        logger.warning(f"Unknown tool: {name}. Checked: local={name in self._local_tools}, "
                       f"knowledge={name in KNOWLEDGE_WRAPPED_TOOLS}, "
                       f"transform={name in TRANSFORM_FUNCTIONS}, bridge={name in BRIDGE_ROUTES}")
        return {
            "success": False,
            "data": f"Unknown tool: {name}. Not in bridge routes or local tools.",
        }

    async def _call_local(self, name: str, params: dict, port: int | None = None) -> dict:
        """Execute a local Python tool."""
        denial = deny_if_contained(name, DispatchOrigin.TOOL_DISPATCHER)
        if denial is not None:
            return {"success": False, "data": denial}
        fn = self._local_tools[name]
        try:
            call_params = dict(params)
            signature = inspect.signature(fn)
            accepts_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in signature.parameters.values()
            )
            if port is not None and (
                "port" in signature.parameters or accepts_kwargs
            ):
                call_params["port"] = port

            result = fn(**call_params)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                result = {"success": True, "data": result}
            return result
        except TypeError as e:
            return {"success": False, "data": f"Invalid parameters for {name}: {e}"}
        except Exception as e:
            logger.error(f"Local tool {name} failed: {e}")
            return {"success": False, "data": str(e)}

    # ================================================================
    # Knowledge middleware for 4 GH wrapper tools
    # ================================================================

    async def _dispatch_with_knowledge(self, name: str, params: dict, port: int | None) -> dict:
        """Wrap knowledge-enriched tools with operation gotchas + correction detection.

        Mirrors server.py's knowledge injection but without session recording
        (agents record via their own MetricsStore in Seam 3).
        Currently empty — gh_edit handles its own knowledge/session recording.
        """
        denial = deny_if_contained(name, DispatchOrigin.TOOL_DISPATCHER)
        if denial is not None:
            return {"success": False, "data": denial}
        from ..learning.gh_knowledge import gh_query_operation, get_gh_knowledge_store

        op_name, ctx_builder = KNOWLEDGE_WRAPPED_TOOLS[name]
        context = ctx_builder(params)

        # 1. Pre-call: query gotchas for this operation
        gotchas: List[str] = []
        try:
            op_knowledge = gh_query_operation(op_name, context)
            gotchas = [g.get("message") for g in op_knowledge.get("gotchas", []) if g.get("message")]
        except Exception as e:
            logger.debug(f"Knowledge query failed for {name}: {e}")

        # 2. Execute via existing bridge/transform tier
        if name in TRANSFORM_FUNCTIONS:
            endpoint, method, data = TRANSFORM_FUNCTIONS[name](params)
            if endpoint is None:
                return data
            result = await call_rhino(endpoint, method, data, port)
        elif name in BRIDGE_ROUTES:
            endpoint, method = BRIDGE_ROUTES[name]
            data = params if params else None
            result = await call_rhino(endpoint, method, data, port)
        else:
            return {"success": False, "data": f"Knowledge-wrapped tool {name} has no route"}

        # 3. Post-call: correction detection + staleness tracking
        success = result.get("success", False)
        if isinstance(result.get("data"), dict):
            success = result["data"].get("success", success)

        correction_detected = False
        if not success:
            error_msg = str(result.get("data", f"{name} failed"))
            self._track_failure(op_name, context, error_msg)
        else:
            correction_info = self._check_correction(op_name, context)
            if correction_info:
                correction_detected = True
            if gotchas:
                try:
                    get_gh_knowledge_store().record_gotcha_success(op_name)
                except Exception:
                    pass

        # 4. Enrich result with correction + gotcha data
        if isinstance(result.get("data"), dict):
            result["data"]["correction_detected"] = correction_detected
            if gotchas:
                result["data"]["gotchas"] = gotchas
        else:
            result["correction_detected"] = correction_detected

        return result

    def _track_failure(self, operation: str, context: dict, error: str) -> None:
        """Track a GH operation failure for potential correction detection."""
        key = f"{operation}:{context.get('target_guid', '')}:{context.get('param', '')}"
        self._recent_failures[key] = {
            "context": context,
            "error": error,
            "timestamp": time.time(),
        }

    def _check_correction(self, operation: str, context: dict) -> Optional[dict]:
        """Check if this success corrects a recent failure. Returns correction info or None."""
        key = f"{operation}:{context.get('target_guid', '')}:{context.get('param', '')}"
        failure = self._recent_failures.pop(key, None)
        if failure and (time.time() - failure["timestamp"]) < self._failure_expiry_seconds:
            return {"failed_context": failure["context"], "error": failure["error"]}
        return None

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def bridge_tool_count(self) -> int:
        return len(BRIDGE_ROUTES) + len(TRANSFORM_FUNCTIONS)

    @property
    def local_tool_count(self) -> int:
        return len(self._local_tools)

    @property
    def all_known_tools(self) -> Set[str]:
        """All tool names this dispatcher can handle."""
        return set(BRIDGE_ROUTES.keys()) | set(TRANSFORM_FUNCTIONS.keys()) | set(self._local_tools.keys())
