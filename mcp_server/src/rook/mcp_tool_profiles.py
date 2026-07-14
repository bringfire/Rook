"""Public MCP tool-exposure profiles.

Single source of truth for the ``ROOK_MCP_TOOL_PROFILE`` contract. This module
is intentionally pure: it MUST NOT import ``server.py`` (one-way dependency --
``server.py`` consumes this module, never the reverse).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, List, Mapping

ENV_VAR = "ROOK_MCP_TOOL_PROFILE"


class Profile(str, Enum):
    FULL = "full"
    LEAN = "lean"
    READONLY = "readonly"


class InvalidProfileError(ValueError):
    """Raised when ROOK_MCP_TOOL_PROFILE is set to an unrecognized value."""


def resolve_profile(env: Mapping[str, str]) -> Profile:
    """Resolve the active profile from an environment mapping.

    Absent or empty/whitespace => FULL (backward-compatible default).
    Any other unrecognized value => InvalidProfileError (never a silent fallback).
    """
    raw = env.get(ENV_VAR)
    if raw is None:
        return Profile.FULL
    normalized = raw.strip().lower()
    if normalized == "":
        return Profile.FULL
    try:
        return Profile(normalized)
    except ValueError:
        raise InvalidProfileError(
            f"Invalid {ENV_VAR}={raw!r}. Expected one of: full, lean, readonly."
        ) from None


# --- Pinned name sets (design spec sections 4, 5.4, 5.5) -------------------

PUBLIC_LEAN_TOOL_NAMES = frozenset({
    "rhino_ping",
    "rhino_instances",
    "rhino_sessions",
    "rhino_session_capabilities",
    "rhino_get_active_instance",
    "rhino_set_active_instance",
    "rhino_clear_active_instance",
    "knowledge_query",
    "rhino_knowledge_query",
    "gh_knowledge_query",
    "rhino_objects",
    "rhino_geometry",
    "gh_snapshot",
    "gh_errors",
    "gh_edit",
    "rhino_execute_intent",
    "gh_execute_intent",
    "openrouter_refresh_catalog",
    # Progressive tool disclosure meta-tools (present in every profile).
    "rook_tools_ls",
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
})

SENTINEL_TOOL_NAMES = frozenset({
    "rhino_select",
    "rhino_deselect",
    "rhino_select_all",
    "rhino_select_none",
    "rhino_select_invert",
    "rhino_select_by_name",
    "rhino_select_by_type",
    "rhino_layer_visibility",
    "rhino_layer_lock",
    "rhino_layer_current",
    "gh_edit",
    "gh_clear",
    "gh_bake_output",
    "rhino_create",
    "rhino_transform",
    "rhino_delete",
    "rhino_boolean",
    "capture_script_artifact",
    "gh_add_pattern",
    "knowledge_record",
    "spawn_agent",
    "plan_and_execute",
    "rhino_execute",
    "rhino_command",
    "rhino_execute_intent",
    "gh_execute_intent",
})

PUBLIC_READONLY_TOOL_NAMES = frozenset({
    "agent_status",
    "gh_batch_component_info",
    "gh_categories",
    "gh_constraints",
    "gh_errors",
    "gh_get_reference",
    "gh_inspect_output",
    "gh_knowledge_query",
    "gh_library",
    "gh_migration_status",
    "gh_pattern_links",
    "gh_pattern_stats",
    "gh_query_observations",
    "gh_query_patterns",
    "gh_selection",
    "gh_session_current",
    "gh_session_history",
    "gh_snapshot",
    "gh_status",
    "gh_structure_query",
    "gh_validate_latency",
    "gh_validate_regression",
    "gh_validate_scenarios",
    "knowledge_query",
    "metrics_summary",
    "parse_command",
    "rc_assemble_route",
    "rc_build_profile",
    "rc_clothoid",
    "rc_concrete_barrier_profile",
    "rc_contour_levels",
    "rc_cross_section",
    "rc_crossing_params",
    "rc_cubic_parabola",
    "rc_deltablok_profile",
    "rc_extract_offsets",
    "rc_get_road_profile",
    "rc_guardrail_profile",
    "rc_list_road_profiles",
    "rc_ping",
    "rc_pole_spacing",
    "rc_project_offset_profile",
    "rc_roads",
    "rc_roundabout_params",
    "rc_sidewalk_profile",
    "rc_slope_profile",
    "rc_standards",
    "rc_terrain_profile",
    "rc_validate_profile",
    "rc_validate_road_profile",
    "rc_validate_style_set",
    "rc_verge_profile",
    "rc_vertical_curve",
    "rc_widening",
    "rhino_2d_to_3d_jobs",
    "rhino_2d_to_3d_models",
    "rhino_2d_to_3d_result",
    "rhino_2d_to_3d_status",
    "rhino_analyze_prompt",
    "rhino_artifacts",
    "rhino_block_compare",
    "rhino_block_find_instances",
    "rhino_block_info",
    "rhino_block_instances",
    "rhino_block_layer_census",
    "rhino_block_nested",
    "rhino_block_objects_detailed",
    "rhino_blocks",
    "rhino_brep_edges",
    "rhino_brep_faces",
    "rhino_brep_vertices",
    "rhino_closest_point",
    "rhino_command_knowledge",
    "rhino_command_observations",
    "rhino_command_queue",
    "rhino_curvature_curve",
    "rhino_curvature_surface",
    "rhino_curve_frame",
    "rhino_curve_point_at",
    "rhino_curve_tangent",
    "rhino_declared_targets",
    "rhino_display_modes",
    "rhino_document",
    "rhino_draft_angle",
    "rhino_geometry",
    "rhino_get_active_instance",
    "rhino_gumball_history",
    "rhino_gumball_status",
    "rhino_instances",
    "rhino_is_closed",
    "rhino_is_valid",
    "rhino_knowledge_query",
    "rhino_layer_dependencies",
    "rhino_layers",
    "rhino_learning_progress",
    "rhino_linetypes",
    "rhino_materials",
    "rhino_measure_area",
    "rhino_measure_bbox",
    "rhino_measure_centroid",
    "rhino_measure_distance",
    "rhino_measure_length",
    "rhino_measure_volume",
    "rhino_merge_contract_validate",
    "rhino_objects",
    "rhino_ping",
    "rhino_planned_contracts",
    "rhino_selection",
    "rhino_session_capabilities",
    "rhino_sessions",
    "rhino_surface_normal",
    "rhino_usertext_document_get",
    "rhino_usertext_object_get",
    "rhino_validate_export",
    "rhino_video_estimate",
    "rhino_video_jobs",
    "rhino_video_models",
    "rhino_video_result",
    "rhino_video_status",
    "rhino_views",
    "rhino_vision_artifacts",
    "rhino_vision_get_artifact",
    "rhino_work_units",
    "rhino_workbench_list",
    "road_intersection_candidates",
    "rookbim_active_document",
    "rookbim_element_info",
    "rookbim_element_parameters",
    "rookbim_list_categories",
    "rookbim_query_elements",
    "rookbim_status",
    "scene_bim_facts",
    "scene_context",
    "scene_graph",
    "scene_object_semantic_context",
    "scene_query",
    "scene_relationship_evidence",
    "scene_relationship_profile",
    "scene_semantic_relationships",
    "scene_stats",
    "script_library_search",
    "session_current",
    "session_history",
    "session_list",
    # Progressive tool disclosure meta-tools (present in every profile; readonly discovery is
    # scoped to readonly-safe targets at call time, and rook_tools_call re-enters the wall).
    "rook_tools_ls",
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
})


def filter_tools(all_tools: Iterable[Any], profile: Profile) -> List[Any]:
    """Return the subset of tools advertised under ``profile``.

    Each item must expose a ``.name`` attribute. FULL returns every tool
    unchanged; LEAN/READONLY keep only their pinned name sets.
    """
    if profile is Profile.FULL:
        return list(all_tools)
    allowed = (
        PUBLIC_LEAN_TOOL_NAMES
        if profile is Profile.LEAN
        else PUBLIC_READONLY_TOOL_NAMES
    )
    return [tool for tool in all_tools if tool.name in allowed]


def tool_blocked(name: str, profile: Profile) -> bool:
    """Whether a call to ``name`` must be rejected under ``profile``.

    Only ``readonly`` is an enforced wall (default-deny). ``lean`` is
    advertisement-only and never blocks a call.
    """
    return profile is Profile.READONLY and name not in PUBLIC_READONLY_TOOL_NAMES


def profile_blocked_envelope(name: str, profile: Profile) -> dict:
    """The Rhino-bridge-style result envelope for a profile-blocked call."""
    return {
        "success": False,
        "data": {
            "code": "tool_profile_blocked",
            "tool": name,
            "profile": profile.value,
        },
    }
