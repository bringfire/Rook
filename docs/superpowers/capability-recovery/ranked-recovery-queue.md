# Ranked Recovery Queue

Status: Phase-one assessment

Rows are ranked by workflow importance, safety tractability, signal strength, and verification quality. The queue is executable only when every row has an owner and verification target.

| Rank | Gap | Evidence | Recommended action | Owner | Verification target | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Material creation/assignment is covered by `rhino_material_ops`, but the action-schema shape may be less discoverable than direct material tools. | Intent map marks material recovery as weak. | schema_fix | Rook MCP | synthetic_eval_task | open |
| 2 | Import/export route postconditions need clearer object-delta and file existence feedback. | Intent map marks import/export as medium severity weak refusals. | schema_fix | Rook MCP/RookNative | unit_or_integration_test | open |
| 3 | Selection by command aliases should redirect toward real selection tools. | `_Sel*` habits are likely after `/command` lockdown. | tool_description_fix | Rook MCP | synthetic_eval_task | open |
| 4 | View capture exists but route choice and returned artifact expectations need clearer evaluation. | `rhino_viewport` captures the current viewport to PNG and returns a path; remaining risk is model discoverability and postcondition clarity. | schema_fix | Rook MCP/RookNative | synthetic_eval_task | open |
| 5 | MCP refusal transport remains `Error: <json>` text; fields are parseable but not a clean raw JSON result. | Formatter currently preserves structured dict failures behind an `Error: ` prefix. | structured_refusal_advisory | Rook MCP | unit_or_integration_test | queued |
| 6 | GH workflows need synthetic evals that confirm agents choose `gh_*` tools instead of Rhino command strings. | Intent map marks GH solve/bake rows as open despite typed coverage. | tool_description_fix | Rook MCP + managed companion | synthetic_eval_task | open |
| 7 | Block-definition mutation tool discovery needs reinforcement because ownership crosses native/managed boundaries. | Intent map marks block mutation as medium severity open. | tool_description_fix | Rook MCP + managed companion | unit_or_integration_test | open |
| 8 | Safe command metadata promotion policy needs concrete candidates only after matrix/eval evidence. | `/command` remains intentionally fail-closed. | safe_command_metadata | RookNative/Rook MCP | live_rhino_smoke_test | deferred |
