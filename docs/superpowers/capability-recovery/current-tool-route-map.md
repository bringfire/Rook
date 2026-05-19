# Current Tool Route Map

Status: Phase-one assessment

This document inventories real model-facing typed routes that can recover capability after `/command` lockdown. It intentionally names only tools present in `mcp_server/src/rook/server.py`.

| Intent category | Existing model-facing tools | Route type | Feedback / postcondition signal | Notes |
| --- | --- | --- | --- | --- |
| Create basic geometry | `rhino_create` | typed MCP tool -> native `/create` | object ids / created object count | Supports `POINT`, `LINE`, `POLYLINE`, `CIRCLE`, `ARC`, `RECTANGLE`, `BOX`, `SPHERE`, `CYLINDER`, `CONE`. |
| Transform geometry | `rhino_transform` | typed MCP tool -> native transform route | transformed ids / success payload | Covers move, rotate, scale, mirror. |
| Delete geometry | `rhino_delete` | typed MCP tool -> native delete route | deleted ids / success payload | Requires explicit object ids. |
| Query document objects | `rhino_objects`, `rhino_geometry` | typed MCP tool -> native query routes | object summaries / geometry detail | Useful recovery from vague command attempts that should inspect before mutating. |
| Selection | `rhino_select`, `rhino_select_by_type`, `rhino_select_none` | typed MCP tools -> native selection routes | selection count / selected ids | Use instead of `_Sel*` raw commands. |
| Measurement | `rhino_measure_distance`, `rhino_measure_area`, `rhino_measure_volume`, `rhino_measure_length`, `rhino_measure_bbox`, `rhino_measure_centroid` | typed MCP tools -> native measure routes | numeric measurement payloads | Use instead of raw `Distance`, `Area`, `BoundingBox`, or similar commands. |
| Layer organization | `rhino_layers`, `rhino_layer_create`, `rhino_layer_move_objects`, `rhino_layer_set_properties`, `rhino_layer_current` | typed MCP tools -> native layer routes | layer metadata / moved object ids | Use for layer creation, movement, visibility, locking, renaming. |
| Materials | `rhino_material_ops`, `rhino_materials` | typed MCP tools -> native material routes | material list / assigned ids | `rhino_material_ops` uses an explicit `action` parameter. |
| Annotation | `rhino_annotation_text`, `rhino_annotation_dot`, `rhino_annotation_leader`, dimension tools | typed MCP tools -> native annotation routes | annotation object ids / measured value for dimensions | Use instead of raw text/dimension command prompts. |
| View and capture | `rhino_viewport`, `rhino_views`, `rhino_views_save`, `rhino_views_restore`, `rhino_capture_depth` | typed MCP tools -> native view/capture routes | viewport state / capture path | `rhino_capture_depth` is specialized; broader screenshot routes should be confirmed before adding queue rows. |
| Import/export | `rhino_import`, `rhino_export` | typed MCP tools -> native import/export routes | file path / import-export result | Requires explicit paths. |
| Blocks | `rhino_blocks`, `rhino_block_create`, `rhino_block_insert`, `rhino_block_*` mutation and query tools | typed MCP tools -> native/managed routes | block name, instance ids, mutation summary | Some block-definition mutation routes are managed by design; preserve current ownership. |
| Grasshopper | `gh_status`, `gh_snapshot`, `gh_edit`, `gh_errors`, `gh_canvas_image`, `gh_bake_output` | typed MCP tools -> managed/native bridge | solve status, errors, snapshot, image path, baked ids | Use GH tools for canvas/document workflows instead of Rhino command strings. |
| Recovery/state | `rhino_command_interactive_prompt`, `rhino_command_interactive_cancel` | recovery-only MCP tools -> native `/command/prompt` and `/command/cancel` | prompt state / verified cancel result | Prompt/cancel are observability and recovery primitives, not execution tools. |
