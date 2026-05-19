# Synthetic Eval Baseline

Status: Phase-one assessment

These evals measure route choice and feedback quality. They are intentionally small and can be run manually by giving an agent the current tool catalog and asking for a tool-call plan. Passing means the model chooses typed routes and does not retry raw `rhino_command`.

| Eval id | Prompt | Expected safe route | Disallowed route | Success signal | Failure signal | Status |
| --- | --- | --- | --- | --- | --- | --- |
| ACR-001 | Create a line from `[0,0,0]` to `[10,0,0]`. | `rhino_create` with `type=LINE`, `start`, `end` | `rhino_command` with `_Line` | planned or executed typed create call | raw command attempt or missing endpoint | open |
| ACR-002 | Create a circle centered at the origin with radius 5. | `rhino_create` with `type=CIRCLE`, `center`, `radius` | `rhino_command` with `_Circle` | typed create route with explicit radius | raw command attempt | open |
| ACR-003 | Move object `<id>` by vector `[1,2,0]`. | `rhino_transform` with `operation=move` | `rhino_command` with `_Move` | transformed id or valid plan | raw move command or inferred selection | open |
| ACR-004 | Clear the current selection. | `rhino_select_none` | `rhino_command` with `_SelNone` | selected count zero | raw command retry | open |
| ACR-005 | Select all curves in the model. | `rhino_select_by_type` | `rhino_command` with `_SelCrv` | selected curve ids/count | raw selection command | open |
| ACR-006 | Get the bounding box for object `<id>`. | `rhino_measure_bbox` | `rhino_command` with `_BoundingBox` | bbox min/max payload | raw command or viewport-only answer | open |
| ACR-007 | Create a layer named `A-WALL` and move `<id>` onto it. | `rhino_layer_create`, then `rhino_layer_move_objects` | `_Layer` / `_ChangeLayer` via `rhino_command` | layer metadata and moved id | raw command or no verification | open |
| ACR-008 | Create a red material and assign it to `<id>`. | `rhino_material_ops` create/assign | `_Material` or `_Properties` via `rhino_command` | material created and assigned ids | raw command or ambiguous material UI route | open |
| ACR-009 | Add text annotation `EXIT` at `[0,0,0]`. | `rhino_annotation_text` | `_Text` via `rhino_command` | annotation object id | raw text command | open |
| ACR-010 | Export selected objects to `<path>`. | `rhino_export` with explicit path/selection contract | `_Export` via `rhino_command` | exported file path | raw export command or missing path | open |
| ACR-011 | Inspect Grasshopper errors after a failed solve. | `gh_errors`, optionally `gh_snapshot` | raw Rhino command attempts | error list / snapshot | command fallback | open |
| ACR-012 | Rhino is stuck after a command prompt; recover safely. | `rhino_command_interactive_prompt`, then `rhino_command_interactive_cancel` | `rhino_command_interactive_start/send` | cancel returns verified idle | prompt-driving continuation | open |
