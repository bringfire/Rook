"""
Tool Groups & Tiers
====================

Defines Tier 0 (always active), Tier 1 (named groups), and Markov
transitions for Rook's ~211 MCP tools.

Adapted from Engram's tool_registry.py for the Rhino/GH domain.
"""

from typing import Dict, List, Set

# =============================================================================
# Tier 0: Always Active (~12 tools, ~1800 tokens)
#
# These tools are always visible to the agent. They provide:
# - Explicit inspection and mutation entry points
# - Knowledge queries
# - Object inspection
# - Meta-tools for progressive disclosure
# =============================================================================

TIER_0: Set[str] = {
    # Knowledge
    "knowledge_query",
    "rhino_knowledge_query",
    "gh_knowledge_query",
    # Inspection
    "rhino_objects",
    "rhino_ping",
    "gh_snapshot",
    "gh_errors",
    # Scene graph — spatial awareness
    "scene_graph",
    "scene_context",
    "scene_stats",
    # Meta-tools (handled internally by agent)
    "request_tools",
    "search_tools",
}

# These tools are valid MCP/server tools but do not currently have an internal
# internal-agent ToolDispatcher path. Keep them out of local execution-profile Tier 0
# until they are added as internal-agent intercepts, local tools, transforms, or
# bridge routes.
LOCAL_TIER_0_DISPATCH_EXCLUSIONS: Set[str] = {
    "scene_graph",
    "scene_context",
    "scene_stats",
}

# Agent Tier 0 composes GH definitions from explicit canvas and script tools.
AGENT_TIER_0: Set[str] = (
    TIER_0
    - LOCAL_TIER_0_DISPATCH_EXCLUSIONS
) | {
    "gh_snapshot",
    "gh_create_script",
    "gh_create_python_script",
    "gh_create_csharp_script",
    "gh_update_script",
    "session_history",       # per-command success/failure for post-execution verification
    "rhino_command_interactive_prompt",  # Rhino prompt state — detect non-idle after execution
}

# Readonly Tier 0: tools safe for observation-only agents (explorer, etc.).
# Excludes both execute_intent tools (write operations) from AGENT_TIER_0.
READONLY_TIER_0: Set[str] = {
    "rhino_ping",
    "rhino_objects",
    "rhino_geometry",
    "gh_snapshot",
    "gh_errors",
    "knowledge_query",
    "rhino_knowledge_query",
    "gh_knowledge_query",
    "request_tools",
    "search_tools",
}

# Groups that contain only read/inspection tools — safe for readonly agents.
# NOTE: gh_exploration, gh_knowledge, gh_validation are MCP-only and
# unreachable by agents via the HTTP bridge. Included for forward compatibility.
# sessions: all four tools (session_current/history/list/export) are in
# BRIDGE_ROUTES, so agents can reach them normally via the C++ HTTP server.
READONLY_ALLOWED_GROUPS: Set[str] = {
    "rhino_measurement",
    "rhino_selection",
    "layers_readonly",
    "viewport_readonly",
    "gh_exploration",
    "gh_knowledge",
    "gh_validation",
    "gh_canvas_readonly",
    "sessions",
    "scene_graph",
    "rookbim_readonly",
    "reconstruction_readonly",
}


# =============================================================================
# Tier 1: Named Groups
#
# Loaded via request_tools("group_name") or auto-loaded by triggers.
# Each group is a focused set of related tools.
# =============================================================================

TOOL_GROUPS: Dict[str, List[str]] = {
    # --- Rhino Geometry Creation & Manipulation ---
    "rhino_geometry": [
        "rhino_create", "rhino_geometry", "rhino_boolean", "rhino_extrude",
        # rhino_prepare_geometry excluded — requires CommandObserver (MCP-only)
    ],
    "rhino_transform": [
        "rhino_transform", "rhino_copy", "rhino_delete",
    ],
    "rhino_curves": [
        "rhino_curve_ops", "rhino_curve_point_at", "rhino_curve_tangent",
        "rhino_curve_frame", "rhino_offset_curve", "rhino_offset_curve_on_surface",
        "rhino_project_curve", "rhino_pull_curve",
    ],
    "rhino_surfaces": [
        "rhino_brep_edges", "rhino_brep_faces", "rhino_brep_vertices",
        "rhino_intersect_curves", "rhino_intersect_curve_brep",
        "rhino_intersect_curve_surface", "rhino_intersect_breps",
        "rhino_intersect_plane",
        "rhino_split_brep", "rhino_split_face", "rhino_split_disjoint_breps", "rhino_trim_brep",
        "rhino_offset_brep",
        "rhino_closest_point", "rhino_is_closed", "rhino_is_valid",
        "rhino_surface_normal", "rhino_draft_angle",
    ],
    "rhino_mesh": [
        "rhino_mesh_from_brep", "rhino_mesh_boolean",
        "rhino_mesh_box", "rhino_mesh_cone", "rhino_mesh_cylinder", "rhino_mesh_sphere",
        "rhino_mesh_reduce", "rhino_mesh_repair", "rhino_mesh_smooth",
        "rhino_mesh_unweld", "rhino_mesh_weld", "rhino_quad_remesh",
    ],
    "rhino_subd": [
        "rhino_subd_box", "rhino_subd_cylinder", "rhino_subd_sphere",
        "rhino_subd_from_mesh", "rhino_subd_from_surface",
        "rhino_subd_crease", "rhino_subd_subdivide",
        "rhino_subd_to_brep", "rhino_subd_to_mesh",
    ],
    "rhino_blocks": [
        "rhino_blocks", "rhino_block_create", "rhino_block_delete",
        "rhino_block_insert", "rhino_block_info", "rhino_block_instances",
        "rhino_block_add_objects", "rhino_block_remove_objects",
        "rhino_block_rename", "rhino_block_description",
        "rhino_block_duplicate", "rhino_block_explode",
        "rhino_block_replace_geometry", "rhino_block_replace_object_geometry",
        "rhino_block_replace_object_geometry_batch",
        "rhino_block_transform_object", "rhino_block_transform_object_batch",
        "rhino_block_transform_instance_batch",
        "rhino_block_replace_instance", "rhino_block_replace_instance_batch",
        "rhino_block_reset_scale", "rhino_block_reset_scale_batch", "rhino_block_nested",
        "rhino_block_link", "rhino_block_unlink", "rhino_block_refresh",
        "rhino_block_rebase",
        "rhino_block_rebase_recursive",
        "rhino_block_purge",
        "rhino_block_layer_census",
    ],

    # --- Rhino Selection ---
    "rhino_selection": [
        "rhino_select", "rhino_select_all", "rhino_select_by_name",
        "rhino_select_by_type", "rhino_select_none", "rhino_select_invert",
        "rhino_selection", "rhino_deselect",
    ],

    # --- Rhino Measurement ---
    "rhino_measurement": [
        "rhino_measure_distance", "rhino_measure_length",
        "rhino_measure_area", "rhino_measure_volume",
        "rhino_measure_bbox", "rhino_measure_centroid",
        "rhino_curvature_curve", "rhino_curvature_surface",
    ],

    # --- Rhino Layers ---
    "layers": [
        "rhino_layers", "rhino_layer_create", "rhino_layer_create_batch", "rhino_layer_delete",
        "rhino_layer_current", "rhino_layer_visibility", "rhino_layer_lock",
        "rhino_layer_set_properties", "rhino_layer_set_properties_batch", "rhino_layer_rename",
        "rhino_layer_move_objects", "rhino_layer_merge", "rhino_layer_dependencies",
    ],
    # Read-only subset: excludes create, delete, set-current, rename, merge, move (all modify state)
    "layers_readonly": [
        "rhino_layers", "rhino_layer_visibility", "rhino_layer_lock",
        "rhino_layer_dependencies",
    ],

    # --- Rhino Viewport & Document ---
    "viewport": [
        "rhino_viewport", "rhino_views", "rhino_views_restore", "rhino_views_save",
        "rhino_display_modes", "rhino_display_mode_set",
        "rhino_document", "rhino_document_ops",
    ],
    # Read-only subset: excludes document_ops (undo, save, new, set_units) and views_save
    "viewport_readonly": [
        "rhino_viewport", "rhino_views", "rhino_views_restore",
        "rhino_display_modes",
        "rhino_document",
    ],

    # --- Vision (PR-6): Gemini generation + artifact management ---
    # MCP-only: internal agents do not have BRIDGE_ROUTES entries for
    # these, so the group is registered in MCP_ONLY_GROUPS below. When
    # agent-side dispatch is added (future PR), remove from the
    # MCP_ONLY_GROUPS set.
    "vision": [
        "rhino_render_view", "rhino_enhance_prompt", "rhino_capture_depth",
        "rhino_vision_artifacts", "rhino_vision_get_artifact",
        "rhino_vision_approve", "rhino_vision_delete_artifact",
        "rhino_vision_consume_approved",
    ],
    # Read-only subset: excludes render_view (spends API quota),
    # enhance_prompt (spends API quota), capture_depth (writes an
    # artifact), approve (mutates flags), and delete (mutates store).
    "vision_readonly": [
        "rhino_vision_artifacts", "rhino_vision_get_artifact",
        "rhino_vision_consume_approved",
    ],

    # --- Vision Video (PR-V4): Veo generation + job lifecycle ---
    # Agent-direct dispatch is wired via BRIDGE_ROUTES (render_video,
    # estimate, models) and TRANSFORM_FUNCTIONS (status, cancel, result,
    # jobs) in tool_dispatcher.py — NOT in MCP_ONLY_GROUPS. Image-side
    # vision groups remain MCP-only by separate decision; flipping them
    # is a follow-up scope.
    "video": [
        "rhino_render_video", "rhino_video_estimate",
        "rhino_video_status", "rhino_video_cancel", "rhino_video_result",
        "rhino_video_jobs", "rhino_video_models",
    ],
    # Read-only subset: excludes render_video (spends API quota,
    # creates a job) and cancel (mutates job state). Estimate stays
    # in — it's a pure pricing read.
    "video_readonly": [
        "rhino_video_estimate",
        "rhino_video_status", "rhino_video_result",
        "rhino_video_jobs", "rhino_video_models",
    ],

    # --- Rook Reconstruction (2D to 3D): package/job lifecycle ---
    # Agent-direct dispatch is wired via BRIDGE_ROUTES (submit/import)
    # and TRANSFORM_FUNCTIONS (models/jobs/status/cancel/result).
    "reconstruction": [
        "rhino_2d_to_3d_models",
        "rhino_2d_to_3d_submit",
        "rhino_2d_to_3d_remove_background",
        "rhino_2d_to_3d_assemble_view_set",
        "rhino_2d_to_3d_jobs",
        "rhino_2d_to_3d_status",
        "rhino_2d_to_3d_cancel",
        "rhino_2d_to_3d_result",
        "rhino_2d_to_3d_import",
    ],
    # Read-only subset: excludes submit (creates provider job), cancel
    # (mutates job state), and import (mutates Rhino document).
    "reconstruction_readonly": [
        "rhino_2d_to_3d_models",
        "rhino_2d_to_3d_jobs",
        "rhino_2d_to_3d_status",
        "rhino_2d_to_3d_result",
    ],

    # --- RookBIM (Revit bridge, Phase 1) ---
    "rookbim": [
        "rookbim_status",
        "rookbim_active_document",
        "rookbim_list_categories",
        "rookbim_query_elements",
        "rookbim_element_info",
        "rookbim_element_parameters",
        "rookbim_select_elements",
        "rookbim_clear_selection",
        "rookbim_export_elements",
        "rookbim_export_preset",
        "rookbim_export_preset_to_rhino",
    ],
    "rookbim_readonly": [
        "rookbim_status",
        "rookbim_active_document",
        "rookbim_list_categories",
        "rookbim_query_elements",
        "rookbim_element_info",
        "rookbim_element_parameters",
    ],

    # --- Rhino Commands (direct) ---
    "rhino_commands": [
        "rhino_command", "rhino_execute",
        "rhino_command_interactive_prompt", "rhino_command_interactive_cancel",
    ],

    # --- Materials & UV Mapping ---
    "materials": [
        "rhino_material_ops", "rhino_materials", "rhino_material_purge",
        "rhino_apply_uv_box_mapping", "rhino_apply_uv_planar_mapping",
        "rhino_apply_uv_cylinder_mapping", "rhino_apply_uv_sphere_mapping",
    ],

    # --- Rhino Linetypes ---
    "linetypes": [
        "rhino_linetypes", "rhino_linetype_purge",
    ],

    # --- Game Export Pipeline ---
    "game_export": [
        "rhino_tag_object_semantic", "rhino_tag_objects_from_layers",
        "rhino_prepare_for_game_export", "rhino_validate_export",
        "rhino_export_with_manifest",
    ],

    # --- Gumball ---
    "gumball": [
        "rhino_gumball_activate", "rhino_gumball_deactivate",
        "rhino_gumball_status", "rhino_gumball_history",
    ],

    # --- Road intersections ---
    "road_intersections": [
        "road_intersection_candidates",
        "road_intersection_resolve",
    ],

    # --- Annotation & Text ---
    "annotation": [
        "rhino_dimension", "rhino_text",
    ],

    # --- Import/Export ---
    "import_export": [
        "rhino_export", "rhino_import", "rhino_instances",
    ],

    # --- Groups ---
    "rhino_groups": [
        "rhino_group",
    ],

    # --- GH Canvas Operations ---
    "gh_canvas": [
        "gh_status", "gh_snapshot", "gh_edit", "gh_undo",
        "gh_errors", "gh_update_script", "gh_set_script", "gh_set_script_pins",
        "gh_create_script", "gh_create_python_script", "gh_create_csharp_script",
        "gh_move",
        "gh_selection", "gh_clear",
        "gh_canvas_cleanup", "gh_align", "gh_distribute",
        "gh_straighten_wires",
        "gh_inspect_output", "gh_preview", "gh_bake_output",
        # gh_canvas_focus, gh_canvas_zoom, gh_canvas_image, and chirp_create
        # are MCP/server-side tools today. Do not expose them to local
        # RookChat execution profiles until ToolDispatcher paths exist.
    ],

    # --- GH Canvas Read-Only (subset for explorer/readonly agents) ---
    "gh_canvas_readonly": [
        "gh_errors", "gh_selection",
        "gh_inspect_output", "gh_constraints",
        "gh_snapshot",
        # gh_canvas_image intentionally NOT exposed here: MCP/server-side only
        # (returns a canvas PNG, no agent ToolDispatcher path), consistent with
        # the read-write gh_canvas group's deliberate omission. See #303.
    ],

    # --- GH Exploration ---
    "gh_exploration": [
        "gh_explore_component", "gh_explore_deep",
        "gh_start_exploration", "gh_end_exploration",
        "gh_investigate",
        "gh_preview", "gh_status",
    ],

    # --- GH Patterns & Recipes ---
    "gh_patterns": [
        "gh_query_patterns", "gh_pattern_links", "gh_pattern_stats",
        "gh_save_pattern", "gh_save_recipe", "gh_extract_recipe",
        "gh_add_pattern", "gh_record_pattern_use",
        "gh_reflect", "gh_cluster", "gh_consolidate",
    ],

    # --- GH Knowledge & Learning ---
    "gh_knowledge": [
        "gh_knowledge_query", "gh_knowledge_reload",
        "gh_record_learning", "gh_record_investigation", "gh_learn_directory",
        "gh_query_observations",
        "gh_categories", "gh_library", "gh_structure_query",
    ],

    # --- GH Document ---
    "gh_document": [
        "gh_document_new", "gh_document_open",
    ],

    # --- GH Session ---
    "gh_session": [
        "gh_session_current", "gh_session_end",
        "gh_session_history", "gh_session_note",
    ],

    # --- GH References ---
    "gh_references": [
        "gh_set_reference", "gh_get_reference", "gh_clear_reference",
    ],

    # --- GH Validation ---
    "gh_validation": [
        "gh_validate_latency", "gh_validate_regression",
        "gh_validate_scenarios",
    ],

    # --- Rhino Command Learning ---
    "command_learning": [
        "rhino_command_knowledge", "rhino_knowledge_query", "rhino_command_knowledge_reload",
        "rhino_command_observations",
        "rhino_command_consolidate", "rhino_learning_progress",
        "rhino_command_select", "rhino_command_queue",
    ],

    # --- Knowledge & Metrics ---
    "knowledge_meta": [
        "knowledge_query", "rhino_knowledge_query", "knowledge_record",
        "metrics_dashboard", "metrics_summary",
        "parse_command", "rhino_analyze_prompt",
    ],

    # --- Sessions ---
    "sessions": [
        "session_current", "session_export",
        "session_history", "session_list",
    ],

    # --- Scene Graph / Spatial Intelligence ---
    # Agents access these via the Rhino HTTP bridge (/scene/graph/*)
    "scene_graph": [
        "scene_graph", "scene_context", "scene_query",
        "scene_stats", "scene_classify", "scene_overlay",
        "scene_exact_neighbors", "scene_refine_containment",
        "scene_project_bim_relationships", "scene_bim_facts",
        "scene_project_relationship_facts", "scene_relationship_profile",
        "scene_semantic_relationships", "scene_relationship_evidence",
        "scene_object_semantic_context",
    ],
}


# =============================================================================
# MCP-Only Groups
#
# These groups contain tools that only work through the MCP server (not
# through the HTTP bridge). Agents dispatch through the bridge, so these
# should be blocked unless tools are registered as local.
# =============================================================================

MCP_ONLY_GROUPS: Set[str] = {
    "knowledge_meta",
    "command_learning",
    "gh_knowledge",
    "gh_patterns",
    "gh_session",
    "gh_exploration",
    "gh_validation",
    # PR-6: Vision tools are MCP-only until agent dispatcher routes
    # exist. External Claude Code / CLI callers discover them via the
    # catalog; internal agents skip them so they don't request groups
    # they cannot execute. When agent-side dispatch is added, remove
    # both entries below.
    "vision",
    "vision_readonly",
    # NOTE: "sessions" is intentionally excluded here — all four tools
    # (session_current/history/list/export) are in BRIDGE_ROUTES and work
    # through the C++ HTTP server, so agents can request them normally.
}


# =============================================================================
# Auto-load Group Triggers
#
# When a tool from the key is used, the corresponding group is auto-loaded.
# This provides just-in-time tool availability.
# =============================================================================

TOOL_GROUP_TRIGGERS: Dict[str, str] = {
    # Creating geometry -> need transform tools
    "rhino_create": "rhino_transform",
    "rhino_extrude": "rhino_transform",
    "rhino_boolean": "rhino_transform",
    # GH intent -> need canvas tools
    "gh_snapshot": "gh_canvas",
    # Materials -> UV mapping
    "rhino_material_ops": "materials",
    # Game export
    "rhino_tag_object_semantic": "game_export",
    "rhino_prepare_for_game_export": "game_export",
}


# =============================================================================
# Markov Tool Transitions (for Seam 1 knowledge prediction)
# =============================================================================

TOOL_TRANSITIONS: Dict[str, List[str]] = {
    # GH canvas operations
    "gh_snapshot": ["gh_edit", "gh_undo"],
    "gh_edit": ["gh_snapshot", "gh_undo"],
    "gh_undo": ["gh_snapshot", "gh_undo"],
    # Rhino geometry
    "rhino_create": ["rhino_transform", "rhino_boolean", "rhino_copy"],
    "rhino_transform": ["rhino_transform", "rhino_objects", "rhino_copy"],
    "rhino_boolean": ["rhino_objects", "rhino_transform", "rhino_geometry"],
    "rhino_copy": ["rhino_transform", "rhino_objects"],
    "rhino_extrude": ["rhino_transform", "rhino_boolean", "rhino_objects"],
    # Materials
    "rhino_material_ops": [
        "rhino_apply_uv_box_mapping", "rhino_apply_uv_planar_mapping",
    ],
    "rhino_apply_uv_box_mapping": [
        "rhino_apply_uv_box_mapping", "rhino_material_ops", "rhino_objects",
    ],
    # Selection / inspection
    "rhino_objects": ["rhino_geometry", "rhino_transform", "rhino_select"],
    "rhino_geometry": ["rhino_transform", "rhino_boolean", "rhino_objects"],
    # Layers
    "rhino_layer_create": ["rhino_layer_current", "rhino_layers", "rhino_layer_create_batch"],
    # Blocks
    "rhino_block_create": ["rhino_block_insert", "rhino_block_info"],
    "rhino_block_insert": ["rhino_transform", "rhino_objects"],
}
