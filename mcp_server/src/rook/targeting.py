"""Rhino instance targeting for the MCP dispatcher."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from .bridge import (
    call_rhino,
    discover_instances,
    discovery_diagnostics,
    _process_id_from_session_id,
)


@dataclass(frozen=True)
class InstanceRef:
    port: int
    process_id: int


@dataclass(frozen=True)
class ActiveTargetResolution:
    success: bool
    target: InstanceRef | None = None
    instance: dict[str, Any] | None = None
    error: str | None = None
    stale_target: InstanceRef | None = None
    instances: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ToolRoute:
    success: bool
    target: InstanceRef | None = None
    instance: dict[str, Any] | None = None
    selection: Literal["explicit", "active", "auto", "panel_locked", "session", "none"] = "none"
    warning: str | None = None
    error: str | None = None
    stale_target: InstanceRef | None = None
    instances: list[dict[str, Any]] | None = None
    alternatives: list[dict[str, Any]] | None = None
    document_serial_number: int | None = None
    requested_port: int | None = None
    invalid_port: object | None = None
    invalid_session: object | None = None
    requested_session: object | None = None
    session_process_id: int | None = None
    port_process_id: int | None = None


Risk = Literal["read", "mutate", "meta"]


@dataclass(frozen=True)
class RhinoToolPolicy:
    requires_rhino: bool
    risk: Risk


@dataclass(frozen=True)
class PanelTargetLock:
    mode: Literal["panel_locked"]
    host_generation_id: str
    process_id: int
    document_serial_number: int
    reason: str = "rook_chat_panel"


UNKNOWN_TOOL_POLICY = RhinoToolPolicy(requires_rhino=True, risk="mutate")

_ACTIVE_TARGET: InstanceRef | None = None
_PANEL_TARGET_LOCK: PanelTargetLock | None = None
_PANEL_TARGET_CONFIG_ERROR: dict[str, Any] | None = None
_ENV_INITIALIZED = False


def reset_targeting_state_for_tests() -> None:
    global _ACTIVE_TARGET, _PANEL_TARGET_LOCK, _PANEL_TARGET_CONFIG_ERROR, _ENV_INITIALIZED
    _ACTIVE_TARGET = None
    _PANEL_TARGET_LOCK = None
    _PANEL_TARGET_CONFIG_ERROR = None
    _ENV_INITIALIZED = False


def get_panel_target_lock() -> PanelTargetLock | None:
    return _PANEL_TARGET_LOCK


def get_panel_target_config_error() -> dict[str, Any] | None:
    return None if _PANEL_TARGET_CONFIG_ERROR is None else dict(_PANEL_TARGET_CONFIG_ERROR)


def _parse_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    canonical = str(parsed)
    return canonical if value == canonical else None


def _set_panel_config_error(message: str, *, mode: str | None = None) -> None:
    global _PANEL_TARGET_CONFIG_ERROR, _PANEL_TARGET_LOCK
    _PANEL_TARGET_LOCK = None
    _PANEL_TARGET_CONFIG_ERROR = {
        "error": "target_unavailable",
        "message": message,
        "locked": True,
        "lockMode": mode or "panel_locked",
        "lockReason": "rook_chat_panel",
    }


def initialize_from_environment(env: dict[str, str] | None = None) -> None:
    global _ENV_INITIALIZED, _PANEL_TARGET_LOCK, _PANEL_TARGET_CONFIG_ERROR
    if _ENV_INITIALIZED:
        return
    _ENV_INITIALIZED = True
    source = env if env is not None else os.environ
    mode = (source.get("ROOK_MCP_TARGET_MODE") or "").strip()
    if not mode:
        _PANEL_TARGET_LOCK = None
        _PANEL_TARGET_CONFIG_ERROR = None
        return
    if mode != "panel_locked":
        _set_panel_config_error(
            f"Unknown ROOK_MCP_TARGET_MODE '{mode}'.",
            mode=mode,
        )
        return
    host_generation_id = _parse_canonical_uuid(
        source.get("ROOK_MCP_TARGET_HOST_GENERATION_ID")
    )
    if host_generation_id is None:
        _set_panel_config_error(
            "This Rook MCP server was started in panel-locked mode without a valid host generation id."
        )
        return
    process_id = _parse_positive_int(source.get("ROOK_MCP_TARGET_PROCESS_ID"))
    if process_id is None:
        _set_panel_config_error(
            "This Rook MCP server was started in panel-locked mode without a valid Rhino process id."
        )
        return
    document_serial = _parse_positive_int(
        source.get("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER")
    )
    if document_serial is None:
        _set_panel_config_error(
            "This Rook MCP server was started in panel-locked mode without a valid Rhino document serial number."
        )
        return
    _PANEL_TARGET_LOCK = PanelTargetLock(
        mode="panel_locked",
        host_generation_id=host_generation_id,
        process_id=process_id,
        document_serial_number=document_serial,
    )
    _PANEL_TARGET_CONFIG_ERROR = None


_ALL_KNOWN_TOOLS = {
    "agent_abort",
    "agent_answer",
    "agent_status",
    "openrouter_refresh_catalog",
    "rook_tools_call",
    "rook_tools_ls",
    "rook_tools_read",
    "rook_tools_search",
    "rhino_2d_to_3d_assemble_view_set",
    "rhino_2d_to_3d_cancel",
    "rhino_2d_to_3d_import",
    "rhino_2d_to_3d_jobs",
    "rhino_2d_to_3d_models",
    "rhino_2d_to_3d_remove_background",
    "rhino_2d_to_3d_result",
    "rhino_2d_to_3d_status",
    "rhino_2d_to_3d_submit",
    "rhino_artifact_deregister",
    "rhino_artifact_refresh",
    "rhino_artifact_register",
    "rhino_artifacts",
    "rhino_mesh2splat_export",
    "rhino_work_unit_register",
    "rhino_work_unit_link_artifact",
    "rhino_merge_contract_record",
    "rhino_merge_contract_validate",
    "rhino_work_units",
    "rhino_declared_target_declare",
    "rhino_declared_target_promote",
    "rhino_declared_targets",
    "rhino_planned_contract_record",
    "rhino_planned_contract_activate",
    "rhino_planned_contracts",
    "rhino_merge_contract_execute",
    "capture_script_artifact",
    "chirp_create",
    "gh_add_pattern",
    "gh_align",
    "gh_bake_output",
    "gh_batch_component_info",
    "gh_canvas_cleanup",
    "gh_canvas_focus",
    "gh_canvas_image",
    "gh_canvas_zoom",
    "gh_categories",
    "gh_clear",
    "gh_clear_reference",
    "gh_cluster",
    "gh_consolidate",
    "gh_connect",
    "gh_constraints",
    "gh_create_csharp_script",
    "gh_create_python_script",
    "gh_create_script",
    "gh_distribute",
    "gh_document_new",
    "gh_document_open",
    "gh_edit",
    "gh_end_exploration",
    "gh_errors",
    "gh_explore_component",
    "gh_explore_deep",
    "gh_extract_recipe",
    "gh_get_reference",
    "gh_inspect_output",
    "gh_investigate",
    "gh_knowledge_query",
    "gh_knowledge_reload",
    "gh_learn_canvas",
    "gh_learn_directory",
    "gh_library",
    "gh_migration_status",
    "gh_move",
    "gh_pattern_links",
    "gh_pattern_stats",
    "gh_preview",
    "gh_query_observations",
    "gh_query_patterns",
    "gh_record_investigation",
    "gh_record_learning",
    "gh_record_pattern_use",
    "gh_reflect",
    "gh_save_pattern",
    "gh_save_recipe",
    "gh_selection",
    "gh_session_current",
    "gh_session_end",
    "gh_session_history",
    "gh_session_note",
    "gh_set_reference",
    "gh_set_script",
    "gh_set_script_pins",
    "gh_snapshot",
    "gh_solve_readiness",
    "gh_start_exploration",
    "gh_status",
    "gh_straighten_wires",
    "gh_structure_query",
    "gh_undo",
    "gh_update_script",
    "gh_upgrade_recipe",
    "gh_validate_latency",
    "gh_validate_regression",
    "gh_validate_scenarios",
    "gh_wait_for_solve_readiness",
    "knowledge_query",
    "knowledge_record",
    "metrics_dashboard",
    "metrics_summary",
    "parse_command",
    "rhino_analyze_prompt",
    "rhino_annotation_dim_aligned",
    "rhino_annotation_dim_angle",
    "rhino_annotation_dim_diameter",
    "rhino_annotation_dim_linear",
    "rhino_annotation_dim_radius",
    "rhino_annotation_dot",
    "rhino_annotation_leader",
    "rhino_annotation_text",
    "rhino_apply_uv_box_mapping",
    "rhino_apply_uv_cylinder_mapping",
    "rhino_apply_uv_planar_mapping",
    "rhino_apply_uv_sphere_mapping",
    "rhino_array_linear",
    "rhino_array_polar",
    "rhino_array_rectangular",
    "rhino_blend_curves",
    "rhino_block_add_objects",
    "rhino_block_array_instances",
    "rhino_block_compare",
    "rhino_block_create",
    "rhino_block_delete",
    "rhino_block_description",
    "rhino_block_distribute_along_curve",
    "rhino_block_duplicate",
    "rhino_block_explode",
    "rhino_block_find_instances",
    "rhino_block_info",
    "rhino_block_insert",
    "rhino_block_instances",
    "rhino_block_layer_census",
    "rhino_block_link",
    "rhino_block_merge",
    "rhino_block_nested",
    "rhino_block_objects_detailed",
    "rhino_block_purge",
    "rhino_block_rebase",
    "rhino_block_rebase_recursive",
    "rhino_block_refresh",
    "rhino_block_remove_objects",
    "rhino_block_rename",
    "rhino_block_replace_geometry",
    "rhino_block_replace_instance",
    "rhino_block_replace_instance_batch",
    "rhino_block_replace_object_geometry",
    "rhino_block_replace_object_geometry_batch",
    "rhino_block_reset_scale",
    "rhino_block_reset_scale_batch",
    "rhino_block_set_instance_properties",
    "rhino_block_set_instance_visibility",
    "rhino_block_set_layers",
    "rhino_block_set_layers_batch",
    "rhino_block_set_materials",
    "rhino_block_set_materials_batch",
    "rhino_block_set_object_colors",
    "rhino_block_set_object_colors_batch",
    "rhino_block_set_object_names",
    "rhino_block_set_object_names_batch",
    "rhino_block_set_object_user_strings",
    "rhino_block_set_object_user_strings_batch",
    "rhino_block_transform_instance",
    "rhino_block_transform_instance_batch",
    "rhino_block_transform_object",
    "rhino_block_transform_object_batch",
    "rhino_block_unlink",
    "rhino_block_user_strings",
    "rhino_blocks",
    "rhino_boolean",
    "rhino_brep_edges",
    "rhino_brep_faces",
    "rhino_brep_vertices",
    "rhino_capture_depth",
    "rhino_clear_active_instance",
    "rhino_closest_point",
    "rhino_command",
    "rhino_command_consolidate",
    "rhino_command_experiment",
    "rhino_command_interactive_cancel",
    "rhino_command_interactive_prompt",
    "rhino_command_interactive_send",
    "rhino_command_interactive_start",
    "rhino_command_knowledge",
    "rhino_command_knowledge_reload",
    "rhino_command_observations",
    "rhino_command_queue",
    "rhino_command_select",
    "rhino_copy",
    "rhino_create",
    "rhino_create_edge_srf",
    "rhino_create_loft",
    "rhino_create_network_srf",
    "rhino_create_patch",
    "rhino_create_pipe",
    "rhino_create_revolve",
    "rhino_create_sweep1",
    "rhino_create_sweep2",
    "rhino_curve_boolean_difference",
    "rhino_curve_boolean_intersection",
    "rhino_curve_boolean_union",
    "rhino_curve_frame",
    "rhino_curve_ops",
    "rhino_curve_point_at",
    "rhino_curve_tangent",
    "rhino_curvature_curve",
    "rhino_curvature_surface",
    "rhino_delete",
    "rhino_deselect",
    "rhino_dimension",
    "rhino_display_mode_set",
    "rhino_display_modes",
    "rhino_document",
    "rhino_document_ops",
    "rhino_draft_angle",
    "rhino_enhance_prompt",
    "rhino_execute",
    "rhino_export",
    "rhino_export_with_manifest",
    "rhino_extrude",
    "rhino_geometry",
    "rhino_get_active_instance",
    "rhino_group",
    "rhino_gumball_activate",
    "rhino_gumball_align",
    "rhino_gumball_cut",
    "rhino_gumball_deactivate",
    "rhino_gumball_extrude",
    "rhino_gumball_history",
    "rhino_gumball_settings",
    "rhino_gumball_status",
    "rhino_import",
    "rhino_instances",
    "rhino_mesh2splat_export",
    "rhino_intersect_breps",
    "rhino_intersect_curve_brep",
    "rhino_intersect_curve_surface",
    "rhino_intersect_curves",
    "rhino_intersect_plane",
    "rhino_is_closed",
    "rhino_is_valid",
    "rhino_knowledge_query",
    "rhino_layer_create",
    "rhino_layer_create_batch",
    "rhino_layer_current",
    "rhino_layer_delete",
    "rhino_layer_dependencies",
    "rhino_layer_lock",
    "rhino_layer_merge",
    "rhino_layer_move_objects",
    "rhino_layer_rename",
    "rhino_layer_set_properties",
    "rhino_layer_set_properties_batch",
    "rhino_layer_visibility",
    "rhino_layers",
    "rhino_launch",
    "rhino_learn_interactive",
    "rhino_learn_next",
    "rhino_learn_variations_interactive",
    "rhino_learning_progress",
    "rhino_linetype_purge",
    "rhino_linetypes",
    "rhino_material_ops",
    "rhino_material_purge",
    "rhino_materials",
    "rhino_measure_area",
    "rhino_measure_bbox",
    "rhino_measure_centroid",
    "rhino_measure_distance",
    "rhino_measure_length",
    "rhino_measure_volume",
    "rhino_mesh_boolean",
    "rhino_mesh_box",
    "rhino_mesh_cone",
    "rhino_mesh_cylinder",
    "rhino_mesh_from_brep",
    "rhino_mesh_reduce",
    "rhino_mesh_repair",
    "rhino_mesh_smooth",
    "rhino_mesh_sphere",
    "rhino_mesh_unweld",
    "rhino_mesh_weld",
    "rhino_objects",
    "rhino_offset_brep",
    "rhino_offset_curve",
    "rhino_offset_curve_on_surface",
    "rhino_prepare_for_game_export",
    "rhino_prepare_geometry",
    "rhino_project_curve",
    "rhino_pull_curve",
    "rhino_quad_remesh",
    "rhino_render_video",
    "rhino_render_view",
    "rhino_select",
    "rhino_select_all",
    "rhino_select_by_name",
    "rhino_select_by_type",
    "rhino_select_invert",
    "rhino_select_none",
    "rhino_selection",
    "rhino_session_capabilities",
    "rhino_sessions",
    "rhino_set_active_instance",
    "rhino_workbench_close",
    "rhino_workbench_launch",
    "rhino_workbench_list",
    "rhino_split_brep",
    "rhino_split_disjoint_breps",
    "rhino_split_face",
    "rhino_subd_box",
    "rhino_subd_crease",
    "rhino_subd_cylinder",
    "rhino_subd_from_mesh",
    "rhino_subd_from_surface",
    "rhino_subd_sphere",
    "rhino_subd_subdivide",
    "rhino_subd_to_brep",
    "rhino_subd_to_mesh",
    "rhino_surface_normal",
    "rhino_tag_object_semantic",
    "rhino_tag_objects_from_layers",
    "rhino_text",
    "rhino_transform",
    "rhino_trim_brep",
    "rhino_usertext_document_delete",
    "rhino_usertext_document_get",
    "rhino_usertext_document_set",
    "rhino_usertext_object_delete",
    "rhino_usertext_object_get",
    "rhino_usertext_object_set",
    "rhino_validate_export",
    "rhino_video_cancel",
    "rhino_video_estimate",
    "rhino_video_jobs",
    "rhino_video_models",
    "rhino_video_result",
    "rhino_video_status",
    "rhino_vision_approve",
    "rhino_vision_artifacts",
    "rhino_vision_consume_approved",
    "rhino_vision_delete_artifact",
    "rhino_vision_get_artifact",
    "rhino_vision_presentation",
    "rhino_viewport",
    "rhino_views",
    "rhino_views_restore",
    "rhino_views_save",
    "rookbim_active_document",
    "rookbim_clear_selection",
    "rookbim_element_info",
    "rookbim_element_parameters",
    "rookbim_export_elements",
    "rookbim_export_preset",
    "rookbim_export_preset_to_rhino",
    "rookbim_list_categories",
    "rookbim_query_elements",
    "rookbim_select_elements",
    "rookbim_status",
    "road_intersection_candidates",
    "road_intersection_resolve",
    "scene_bim_facts",
    "scene_classify",
    "scene_context",
    "scene_exact_neighbors",
    "scene_graph",
    "scene_overlay",
    "scene_object_semantic_context",
    "scene_project_bim_relationships",
    "scene_project_relationship_facts",
    "scene_query",
    "scene_refine_containment",
    "scene_relationship_evidence",
    "scene_relationship_profile",
    "scene_semantic_relationships",
    "scene_stats",
    "session_current",
    "session_export",
    "session_history",
    "session_list",
    "run_library_script",
    "script_library_search",
}

_META_TOOLS = {
    "agent_abort",
    "agent_answer",
    "agent_status",
    "openrouter_refresh_catalog",
    "rook_tools_call",
    "rook_tools_ls",
    "rook_tools_read",
    "rook_tools_search",
    "rhino_artifact_deregister",
    "rhino_artifact_refresh",
    "rhino_artifact_register",
    "rhino_artifacts",
    "rhino_work_unit_register",
    "rhino_work_unit_link_artifact",
    "rhino_merge_contract_record",
    "rhino_merge_contract_validate",
    "rhino_work_units",
    "rhino_declared_target_declare",
    "rhino_declared_target_promote",
    "rhino_declared_targets",
    "rhino_planned_contract_record",
    "rhino_planned_contract_activate",
    "rhino_planned_contracts",
    "rhino_clear_active_instance",
    "rhino_get_active_instance",
    "rhino_instances",
    "rhino_launch",
    "rhino_session_capabilities",
    "rhino_sessions",
    "rhino_set_active_instance",
    "rhino_workbench_close",
    "rhino_workbench_launch",
    "rhino_workbench_list",
}

_RHINO_INDEPENDENT_READ_TOOLS = {
    "gh_knowledge_query",
    "gh_migration_status",
    "gh_pattern_links",
    "gh_pattern_stats",
    "gh_query_observations",
    "gh_query_patterns",
    "knowledge_query",
    "metrics_dashboard",
    "metrics_summary",
    "parse_command",
    "rhino_command_knowledge",
    "rhino_knowledge_query",
    "rhino_learning_progress",
    "script_library_search",
    "scene_object_semantic_context",
    "scene_relationship_profile",
    "scene_semantic_relationships",
}

_RHINO_INDEPENDENT_MUTATE_TOOLS = {
    # rhino_merge_contract_execute MUTATES Rhino (via internal pinned sub-calls) but is non-routed
    # at the dispatcher so it can own `session` + pin its own port. (False, "mutate") is the
    # load-bearing policy; the set name is imperfect for a Rhino-mutating tool. See P7 Slice 4.
    "rhino_merge_contract_execute",
    "capture_script_artifact",
    "gh_end_exploration",
    "gh_knowledge_reload",
    "gh_record_investigation",
    "gh_record_learning",
    "gh_record_pattern_use",
    "gh_save_pattern",
    "gh_save_recipe",
    "gh_session_end",
    "gh_session_note",
    "gh_start_exploration",
    "knowledge_record",
    "rhino_command_consolidate",
    "rhino_command_experiment",
    "rhino_command_knowledge_reload",
    "rhino_command_observations",
    "rhino_command_queue",
}

_RHINO_READ_TOOLS = {
    "gh_batch_component_info",
    "gh_canvas_image",
    "gh_categories",
    "gh_errors",
    "gh_get_reference",
    "gh_inspect_output",
    "gh_library",
    "gh_selection",
    "gh_session_current",
    "gh_session_history",
    "gh_solve_readiness",
    "gh_status",
    "gh_structure_query",
    "gh_wait_for_solve_readiness",
    "rhino_2d_to_3d_jobs",
    "rhino_2d_to_3d_models",
    "rhino_2d_to_3d_result",
    "rhino_2d_to_3d_status",
    "rhino_block_compare",
    "rhino_block_find_instances",
    "rhino_block_info",
    "rhino_block_instances",
    "rhino_block_layer_census",
    "rhino_block_nested",
    "rhino_block_objects_detailed",
    "rhino_block_user_strings",
    "rhino_blocks",
    "rhino_brep_edges",
    "rhino_brep_faces",
    "rhino_brep_vertices",
    "rhino_closest_point",
    "rhino_curvature_curve",
    "rhino_curvature_surface",
    "rhino_display_modes",
    "rhino_document",
    "rhino_draft_angle",
    "rhino_geometry",
    "rhino_gumball_history",
    "rhino_gumball_status",
    "rhino_is_closed",
    "rhino_is_valid",
    "rhino_layers",
    "rhino_linetypes",
    "rhino_materials",
    "rhino_measure_area",
    "rhino_measure_bbox",
    "rhino_measure_centroid",
    "rhino_measure_distance",
    "rhino_measure_length",
    "rhino_measure_volume",
    "rhino_objects",
    "rhino_ping",
    "rhino_selection",
    "rhino_usertext_document_get",
    "rhino_usertext_object_get",
    "rhino_video_estimate",
    "rhino_video_jobs",
    "rhino_video_models",
    "rhino_video_result",
    "rhino_video_status",
    "rhino_vision_artifacts",
    "rhino_vision_get_artifact",
    "rhino_views",
    "rookbim_active_document",
    "rookbim_element_info",
    "rookbim_element_parameters",
    "rookbim_list_categories",
    "rookbim_query_elements",
    "rookbim_status",
    "run_library_script",
    "scene_bim_facts",
    "scene_context",
    "scene_exact_neighbors",
    "scene_graph",
    "scene_project_bim_relationships",
    "scene_project_relationship_facts",
    "scene_query",
    "scene_refine_containment",
    "scene_relationship_evidence",
    "scene_stats",
    "session_current",
    "session_history",
    "session_list",
}

_ROOKBIM_SELECTION_MUTATE_TOOLS = {
    "rookbim_clear_selection",
    "rookbim_select_elements",
}

_RHINO_MUTATE_TOOLS = (
    _ROOKBIM_SELECTION_MUTATE_TOOLS
    | (
        _ALL_KNOWN_TOOLS
        - _META_TOOLS
        - _RHINO_INDEPENDENT_READ_TOOLS
        - _RHINO_INDEPENDENT_MUTATE_TOOLS
        - _RHINO_READ_TOOLS
    )
)

TOOL_POLICIES: dict[str, RhinoToolPolicy] = {
    **{name: RhinoToolPolicy(False, "meta") for name in _META_TOOLS},
    **{name: RhinoToolPolicy(False, "read") for name in _RHINO_INDEPENDENT_READ_TOOLS},
    **{name: RhinoToolPolicy(False, "mutate") for name in _RHINO_INDEPENDENT_MUTATE_TOOLS},
    **{name: RhinoToolPolicy(True, "read") for name in _RHINO_READ_TOOLS},
    **{name: RhinoToolPolicy(True, "mutate") for name in _RHINO_MUTATE_TOOLS},
}


def policy_for_tool(name: str) -> RhinoToolPolicy:
    return TOOL_POLICIES.get(name, UNKNOWN_TOOL_POLICY)


# Non-routed tools never execute against a Rhino session, so a `session` argument
# on them is a contract error (rejected, not silently ignored) — EXCEPT tools that
# legitimately own a non-routing `session` argument. This is an explicit exception
# list, NOT a second routing-policy surface; it grows only by intentional addition.
_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {
    "rhino_session_capabilities", "rhino_workbench_close", "rhino_merge_contract_execute"}


def session_not_targetable_result(name: str) -> dict[str, Any]:
    return _error_result(
        "session_not_targetable",
        message=(
            "This tool does not execute against a Rhino session; remove the "
            "'session' argument. Session targeting applies only to Rhino-routed tools."
        ),
        tool=name,
    )


def allows_non_routed_session_argument(name: str) -> bool:
    """Whether a non-routed tool legitimately owns its own `session` argument."""
    return name in _NON_ROUTED_SESSION_ARGUMENT_TOOLS


def get_active_target() -> InstanceRef | None:
    return _ACTIVE_TARGET


def set_active_target(target: InstanceRef) -> None:
    global _ACTIVE_TARGET
    _ACTIVE_TARGET = target


def clear_active_target() -> InstanceRef | None:
    global _ACTIVE_TARGET
    previous = _ACTIVE_TARGET
    _ACTIVE_TARGET = None
    return previous


def instance_ref_from_instance(instance: dict[str, Any]) -> InstanceRef | None:
    port = instance.get("port")
    process_id = instance.get("processId")
    if not isinstance(port, int) or not isinstance(process_id, int):
        return None
    if port <= 0 or process_id <= 0:
        return None
    return InstanceRef(port=port, process_id=process_id)


def _valid_explicit_port(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _native_preferred_instance(
    process_id: int,
    instances: list[dict[str, Any]],
) -> dict[str, Any] | None:
    process_instances = [
        instance
        for instance in instances
        if instance.get("processId") == process_id and instance_ref_from_instance(instance)
    ]
    if not process_instances:
        return None
    for instance in process_instances:
        if instance.get("pluginType") == "native":
            return instance
    return process_instances[0]


def _target_from_instance(instance: dict[str, Any], instances: list[dict[str, Any]]) -> tuple[InstanceRef, dict[str, Any]] | None:
    ref = instance_ref_from_instance(instance)
    if ref is None:
        return None
    canonical = _native_preferred_instance(ref.process_id, instances) or instance
    canonical_ref = instance_ref_from_instance(canonical)
    if canonical_ref is None:
        return None
    return canonical_ref, canonical


def _process_targets(instances: list[dict[str, Any]]) -> list[tuple[InstanceRef, dict[str, Any]]]:
    targets: list[tuple[InstanceRef, dict[str, Any]]] = []
    seen: set[int] = set()
    for instance in instances:
        ref = instance_ref_from_instance(instance)
        if ref is None or ref.process_id in seen:
            continue
        target = _target_from_instance(instance, instances)
        if target is None:
            continue
        seen.add(target[0].process_id)
        targets.append(target)
    return targets


def _canonical_process_instances(instances: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not instances:
        return []
    return [instance for _, instance in _process_targets(instances)]


def _lock_payload(lock: PanelTargetLock | None = None) -> dict[str, Any]:
    current = lock or _PANEL_TARGET_LOCK
    payload: dict[str, Any] = {
        "locked": current is not None or _PANEL_TARGET_CONFIG_ERROR is not None,
        "lockMode": "panel_locked",
        "lockReason": "rook_chat_panel",
    }
    if current is not None:
        payload["target"] = {
            "hostGenerationId": current.host_generation_id,
            "processId": current.process_id,
            "documentSerialNumber": current.document_serial_number,
        }
    return payload


def _panel_error(
    error: str,
    message: str,
    *,
    instances: list[dict[str, Any]] | None = None,
    requested: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = {
        "error": error,
        "message": message,
        **_lock_payload(),
    }
    if instances is not None:
        data["instances"] = instances
    if requested:
        data.update(requested)
    return {"success": False, "data": data}


def panel_target_locked_result(message: str | None = None) -> dict[str, Any]:
    return _panel_error(
        "panel_target_locked",
        message or "This Claude Code tab is locked to the Rhino document that owns the panel.",
        instances=discover_instances(),
    )


def panel_target_unavailable_result(
    message: str | None = None,
    *,
    instances: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _panel_error(
        "target_unavailable",
        message or "The Rook host generation bound to this conversation is unavailable.",
        instances=instances,
    )


def instance_matches_panel_target_lock(
    instance: dict[str, Any],
    lock: PanelTargetLock | None = None,
) -> bool:
    current = lock or _PANEL_TARGET_LOCK
    return bool(
        current is not None
        and instance.get("processId") == current.process_id
        and instance.get("hostGenerationId") == current.host_generation_id
    )


def live_capabilities_match_panel_target_lock(
    capabilities: Any,
    lock: PanelTargetLock | None = None,
) -> bool:
    current = lock or _PANEL_TARGET_LOCK
    return bool(
        current is not None
        and isinstance(capabilities, dict)
        and capabilities.get("hostGenerationId") == current.host_generation_id
    )


def panel_session_matches_target_lock(session_id: Any) -> bool:
    lock = _PANEL_TARGET_LOCK
    return bool(
        lock is not None
        and _process_id_from_session_id(session_id) == lock.process_id
    )


def resolve_panel_target_instance(
    instances: list[dict[str, Any]],
    lock: PanelTargetLock | None = None,
) -> dict[str, Any] | None:
    current = lock or _PANEL_TARGET_LOCK
    if current is None:
        return None
    matches = [
        instance
        for instance in instances
        if instance.get("pluginType") == "native"
        and instance_matches_panel_target_lock(instance, current)
    ]
    return matches[0] if len(matches) == 1 else None


def _resolve_locked_target(instances: list[dict[str, Any]]) -> tuple[InstanceRef, dict[str, Any]] | None:
    locked = resolve_panel_target_instance(instances)
    if locked is None:
        return None
    targets = _process_targets([locked])
    return targets[0] if targets else None


def apply_locked_document_context(arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(arguments) if arguments else {}
    lock = _PANEL_TARGET_LOCK
    if lock is None or not lock.document_serial_number:
        return args
    requested = _parse_positive_int(args.get("documentSerialNumber"))
    if requested is not None and requested != lock.document_serial_number:
        return _panel_error(
            "panel_document_locked",
            "This Claude Code tab is locked to the Rhino document that owns the panel.",
            requested={"requestedDocumentSerialNumber": requested},
        )
    args["documentSerialNumber"] = lock.document_serial_number
    return args


def resolve_active_target() -> ActiveTargetResolution:
    target = get_active_target()
    instances = discover_instances()
    if target is None:
        return ActiveTargetResolution(success=True, instances=instances)

    for instance in instances:
        ref = instance_ref_from_instance(instance)
        if ref == target:
            return ActiveTargetResolution(
                success=True,
                target=target,
                instance=instance,
                instances=instances,
            )

    return ActiveTargetResolution(
        success=False,
        error="active_rhino_instance_unavailable",
        stale_target=target,
        instances=instances,
    )


def resolve_tool_route(
    name: str,
    *,
    explicit_port: object | None = None,
    explicit_session: object | None = None,
    has_explicit_session: bool = False,
) -> ToolRoute:
    policy = policy_for_tool(name)
    if not policy.requires_rhino:
        return ToolRoute(success=True, selection="none")

    instances = discover_instances()
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return ToolRoute(
            success=False,
            error="panel_target_config_error",
            instances=instances,
        )

    pid_s: int | None = None
    if has_explicit_session:
        pid_s = _process_id_from_session_id(explicit_session)
        # _process_id_from_session_id is lenient: "rhino-0" -> 0, "rhino--5" -> -5.
        # A real PID is positive, so reject None OR non-positive as malformed.
        if pid_s is None or pid_s <= 0:
            return ToolRoute(
                success=False,
                error="invalid_session_id",
                invalid_session=explicit_session,
                instances=instances,
            )

    if explicit_port is not None:
        normalized_port = _valid_explicit_port(explicit_port)
        if normalized_port is None:
            return ToolRoute(
                success=False,
                error="invalid_requested_port",
                invalid_port=explicit_port,
                instances=instances,
            )
        explicit_port = normalized_port

    lock = _PANEL_TARGET_LOCK
    if lock is not None:
        locked_target = _resolve_locked_target(instances)
        if locked_target is None:
            return ToolRoute(
                success=False,
                error="target_unavailable",
                instances=instances,
            )
        ref, canonical = locked_target
        if has_explicit_session and pid_s != lock.process_id:
            return ToolRoute(
                success=False,
                error="panel_target_locked",
                instances=instances,
            )
        if explicit_port is not None:
            explicit = next(
                (instance for instance in instances if instance.get("port") == explicit_port),
                None,
            )
            if explicit is None or explicit.get("processId") != lock.process_id:
                return ToolRoute(
                    success=False,
                    error="panel_target_locked",
                    instances=instances,
                )
            target = _target_from_instance(explicit, instances)
            if target is not None:
                ref, canonical = target
        return ToolRoute(
            success=True,
            target=ref,
            instance=canonical,
            selection="panel_locked",
            instances=instances,
            document_serial_number=lock.document_serial_number,
        )

    if has_explicit_session:
        inst_s = next(
            (
                instance
                for instance in instances
                if instance.get("processId") == pid_s
                and instance.get("pluginType") == "native"
                and instance_ref_from_instance(instance) is not None
            ),
            None,
        )
        if inst_s is None:
            return ToolRoute(
                success=False,
                error="rhino_session_not_found",
                requested_session=explicit_session,
                instances=instances,
            )
        if explicit_port is not None:
            owner = next(
                (instance for instance in instances if instance.get("port") == explicit_port),
                None,
            )
            if owner is None:
                return ToolRoute(
                    success=False,
                    error="requested_port_not_discovered",
                    requested_port=explicit_port,
                    instances=instances,
                )
            if owner.get("processId") != pid_s:
                return ToolRoute(
                    success=False,
                    error="selector_conflict",
                    requested_session=explicit_session,
                    requested_port=explicit_port,
                    session_process_id=pid_s,
                    port_process_id=owner.get("processId"),
                    instances=instances,
                )
        ref = instance_ref_from_instance(inst_s)
        return ToolRoute(
            success=True,
            target=ref,
            instance=inst_s,
            selection="session",
            instances=instances,
        )

    targets = _process_targets(instances)

    if explicit_port is not None:
        for instance in instances:
            if instance.get("port") == explicit_port:
                target = _target_from_instance(instance, instances)
                if target is None:
                    break
                ref, canonical = target
                return ToolRoute(
                    success=True,
                    target=ref,
                    instance=canonical,
                    selection="explicit",
                    instances=instances,
                )
        return ToolRoute(
            success=False,
            error="requested_port_not_discovered",
            requested_port=explicit_port,
            instances=instances,
        )

    active = resolve_active_target()
    if active.stale_target is not None:
        return ToolRoute(
            success=False,
            error=active.error,
            stale_target=active.stale_target,
            instances=active.instances,
        )
    if active.target is not None:
        return ToolRoute(
            success=True,
            target=active.target,
            instance=active.instance,
            selection="active",
            instances=instances,
        )

    if not targets:
        return ToolRoute(success=False, error="no_rhino_instance", instances=instances)

    target, instance = targets[0]
    if len(targets) == 1:
        return ToolRoute(
            success=True,
            target=target,
            instance=instance,
            selection="auto",
            instances=instances,
        )

    target_instances = [candidate for _, candidate in targets]
    if policy.risk == "read":
        return ToolRoute(
            success=True,
            target=target,
            instance=instance,
            selection="auto",
            warning="multiple_instances",
            instances=target_instances,
            alternatives=target_instances[1:],
        )

    return ToolRoute(
        success=False,
        error="multiple_rhino_instances",
        instances=target_instances,
    )


def _target_payload(instance: dict[str, Any], ref: InstanceRef | None = None) -> dict[str, Any]:
    if ref is None:
        ref = instance_ref_from_instance(instance)
    payload = dict(instance)
    if ref is not None:
        payload["port"] = ref.port
        payload["processId"] = ref.process_id
    return payload


def _error_result(error: str, **payload: Any) -> dict[str, Any]:
    data = {"error": error, **payload}
    return {"success": False, "data": data}


def _matches_text(instance: dict[str, Any], match: str) -> bool:
    needle = match.lower()
    for key in ("documentName", "documentPath", "windowTitle", "title"):
        value = instance.get(key)
        if isinstance(value, str) and needle in value.lower():
            return True
    return False


async def _enrich_instance(instance: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(instance)
    metadata = await fetch_document_metadata(instance)
    enriched.update(metadata)
    return enriched


async def bind_active_instance(
    *,
    port: int | None = None,
    process_id: int | None = None,
    match: str | None = None,
) -> dict[str, Any]:
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return {"success": False, "data": get_panel_target_config_error()}

    instances = discover_instances()
    matched: list[dict[str, Any]] = []
    lock = _PANEL_TARGET_LOCK

    if port is not None:
        matched = [instance for instance in instances if instance.get("port") == port]
        error = "rhino_target_unavailable"
    elif process_id is not None:
        matched = [instance for instance in instances if instance.get("processId") == process_id]
        error = "rhino_target_unavailable"
    elif match:
        enriched_instances = [await _enrich_instance(instance) for instance in instances]
        matched = [instance for instance in enriched_instances if _matches_text(instance, match)]
        error = "rhino_target_not_found"
    else:
        return _error_result("rhino_target_required", instances=instances)

    if not matched:
        if port is not None:
            return route_error_result(
                ToolRoute(
                    success=False,
                    error="requested_port_not_discovered",
                    requested_port=port,
                    instances=instances,
                )
            )
        return _error_result(error, instances=instances)

    if lock is not None:
        locked_matches = [
            instance
            for instance in matched
            if instance.get("processId") == lock.process_id
        ]
        if not locked_matches:
            return _panel_error(
                "panel_target_locked",
                "This Claude Code tab is locked to the Rhino document that owns the panel.",
                instances=instances,
            )
        matched = locked_matches

    matched_targets: list[tuple[InstanceRef, dict[str, Any]]] = []
    seen: set[InstanceRef] = set()
    for instance in matched:
        target = _target_from_instance(instance, instances)
        if target is None or target[0] in seen:
            continue
        seen.add(target[0])
        matched_targets.append(target)

    if len(matched_targets) != 1:
        return _error_result(
            "multiple_rhino_instances",
            instances=[instance for _, instance in matched_targets],
        )

    ref, instance = matched_targets[0]
    set_active_target(ref)
    active_payload = _target_payload(instance, ref)
    active_payload.update(await fetch_document_metadata(instance))
    response_data: dict[str, Any] = {"active": active_payload}
    if _PANEL_TARGET_LOCK is not None:
        response_data.update(_lock_payload())
    return {"success": True, "data": response_data}


async def get_active_instance_result() -> dict[str, Any]:
    active = resolve_active_target()
    if active.stale_target is not None:
        data: dict[str, Any] = {
            "error": "active_rhino_instance_unavailable",
            "stale_target": {
                "port": active.stale_target.port,
                "processId": active.stale_target.process_id,
            },
            "instances": _canonical_process_instances(active.instances),
        }
        if _PANEL_TARGET_LOCK is not None or _PANEL_TARGET_CONFIG_ERROR is not None:
            data["lock"] = get_lock_state_result()["data"]["lock"]
        return {"success": False, "data": data}
    if active.target is None or active.instance is None:
        data: dict[str, Any] = {"active": None}
        if _PANEL_TARGET_LOCK is not None or _PANEL_TARGET_CONFIG_ERROR is not None:
            data["lock"] = get_lock_state_result()["data"]["lock"]
        return {"success": True, "data": data}
    payload = _target_payload(active.instance, active.target)
    payload.update(await fetch_document_metadata(active.instance))
    data = {"active": payload}
    if _PANEL_TARGET_LOCK is not None or _PANEL_TARGET_CONFIG_ERROR is not None:
        data["lock"] = get_lock_state_result()["data"]["lock"]
    return {"success": True, "data": data}


def clear_active_instance_result() -> dict[str, Any]:
    if _PANEL_TARGET_LOCK is not None:
        return _panel_error(
            "panel_target_locked",
            "This Claude Code tab is locked to the Rhino document that owns the panel.",
        )
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return {"success": False, "data": get_panel_target_config_error()}
    cleared = clear_active_target()
    if cleared is None:
        payload = None
    else:
        payload = {"port": cleared.port, "processId": cleared.process_id}
    return {"success": True, "data": {"cleared": payload}}


async def instances_result() -> dict[str, Any]:
    instances = [await _enrich_instance(instance) for instance in discover_instances()]
    active = await get_active_instance_result()
    data: dict[str, Any] = {"count": len(instances), "instances": instances}
    if active.get("success"):
        data["active"] = active.get("data", {}).get("active")
        if "lock" in active.get("data", {}):
            data["lock"] = active["data"]["lock"]
    else:
        data["active"] = active.get("data")
    if "lock" not in data and (
        _PANEL_TARGET_LOCK is not None or _PANEL_TARGET_CONFIG_ERROR is not None
    ):
        data["lock"] = get_lock_state_result()["data"]["lock"]
    return {"success": True, "data": data}


def get_lock_state_result() -> dict[str, Any]:
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return {"success": True, "data": {"lock": get_panel_target_config_error()}}
    if _PANEL_TARGET_LOCK is None:
        return {"success": True, "data": {"lock": {"locked": False}}}
    payload = _lock_payload()
    payload["live"] = _resolve_locked_target(discover_instances()) is not None
    return {"success": True, "data": {"lock": payload}}


async def _call_document_for_instance(instance: dict[str, Any]) -> dict[str, Any]:
    return await call_rhino("/document", port=instance.get("port"))


async def fetch_document_metadata(instance: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await _call_document_for_instance(instance)
    except Exception:
        return {}
    if not isinstance(result, dict) or not result.get("success"):
        return {}
    data = result.get("data")
    if not isinstance(data, dict):
        return {}

    metadata: dict[str, Any] = {}
    name = data.get("documentName", data.get("name"))
    path = data.get("documentPath", data.get("path"))
    if isinstance(name, str):
        metadata["documentName"] = name
    if isinstance(path, str):
        metadata["documentPath"] = path
    if "objectCount" in data:
        metadata["objectCount"] = data["objectCount"]
    title = data.get("windowTitle", data.get("title"))
    if isinstance(title, str):
        metadata["windowTitle"] = title
    return metadata


def attach_route_metadata(result: dict[str, Any], route: ToolRoute) -> dict[str, Any]:
    if not result.get("success") or route.warning != "multiple_instances" or route.target is None:
        return result

    data = result.get("data")
    if not isinstance(data, dict):
        data = {"result": data}
    else:
        data = dict(data)

    target_payload = _target_payload(route.instance or {}, route.target)
    data["rhino_target"] = target_payload
    data["alternatives"] = route.alternatives or []
    data["auto_selected"] = True
    return {**result, "data": data}


def route_error_result(route: ToolRoute) -> dict[str, Any]:
    if route.error == "panel_target_config_error":
        return {"success": False, "data": get_panel_target_config_error()}
    if route.error == "target_unavailable":
        return panel_target_unavailable_result(instances=route.instances or [])
    if route.error == "panel_target_stale":
        return _panel_error(
            "panel_target_stale",
            "The Rhino process that owns this Claude Code tab is no longer available.",
            instances=route.instances or [],
        )
    if route.error == "panel_target_locked":
        return _panel_error(
            "panel_target_locked",
            "This Claude Code tab is locked to the Rhino document that owns the panel.",
            instances=route.instances or [],
        )
    if route.error == "active_rhino_instance_unavailable":
        stale = route.stale_target
        return _error_result(
            "active_rhino_instance_unavailable",
            message="The active Rhino binding is no longer available. Choose a live instance with rhino_set_active_instance.",
            stale_target=None if stale is None else {"port": stale.port, "processId": stale.process_id},
            instances=_canonical_process_instances(route.instances),
        )
    if route.error == "multiple_rhino_instances":
        return _error_result(
            "multiple_rhino_instances",
            message="Multiple Rhino instances are available. Bind one with rhino_set_active_instance or pass port.",
            instances=route.instances or [],
        )
    if route.error == "requested_port_not_discovered":
        diagnostics = discovery_diagnostics()
        return _error_result(
            "requested_port_not_discovered",
            message=(
                "No discovered RookNative instance owns the requested port. "
                "Native discovery publication may have failed or MCP may be looking in a different discovery folder."
            ),
            requestedPort=route.requested_port,
            discoveryFolder=diagnostics.get("discoveryFolder"),
            discoveryFolders=diagnostics.get("discoveryFolders"),
            selection=diagnostics.get("selection"),
            tempRoot=diagnostics.get("tempRoot"),
            legacyTempDiscoveryFolder=diagnostics.get("legacyTempDiscoveryFolder"),
            instances=route.instances or [],
        )
    if route.error == "invalid_requested_port":
        return _error_result(
            "invalid_requested_port",
            message="Explicit Rhino port must be a positive integer discovered in Rook metadata.",
            invalidPort=repr(route.invalid_port),
            instances=route.instances or [],
        )
    if route.error == "rhino_target_unavailable":
        return _error_result(
            "rhino_target_unavailable",
            message="The requested Rhino target is not available.",
            instances=route.instances or [],
        )
    if route.error == "invalid_session_id":
        return _error_result(
            "invalid_session_id",
            message=(
                "Session selector must be a string like 'rhino-<pid>' from "
                "rhino_sessions; null or malformed is invalid."
            ),
            invalidSession=repr(route.invalid_session),
            instances=route.instances or [],
        )
    if route.error == "rhino_session_not_found":
        diagnostics = discovery_diagnostics()
        return _error_result(
            "rhino_session_not_found",
            message=(
                "No discovered RookNative session owns that id. "
                "Call rhino_sessions for live sessions."
            ),
            session=route.requested_session,
            discoveryFolder=diagnostics.get("discoveryFolder"),
            discoveryFolders=diagnostics.get("discoveryFolders"),
            instances=route.instances or [],
        )
    if route.error == "selector_conflict":
        return _error_result(
            "selector_conflict",
            message=(
                "session and port name different Rhino processes. Pass one selector, "
                "or a port on the same process as the session."
            ),
            session=route.requested_session,
            requestedPort=route.requested_port,
            sessionProcessId=route.session_process_id,
            portProcessId=route.port_process_id,
            instances=route.instances or [],
        )
    return _error_result(route.error or "rhino_target_error", instances=route.instances or [])


def should_auto_bind_launched_instance() -> bool:
    if _PANEL_TARGET_LOCK is not None or _PANEL_TARGET_CONFIG_ERROR is not None:
        return False
    active = resolve_active_target()
    return active.target is None


def bind_single_available_instance() -> InstanceRef | None:
    targets = _process_targets(discover_instances())
    if len(targets) != 1:
        return None
    target, _instance = targets[0]
    set_active_target(target)
    return target
