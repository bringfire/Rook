# Agent Capability Recovery After Command Lockdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a lean phase-one capability assessment after `/command` lockdown, plus minimal refusal guidance that points agents toward real existing typed tools.

**Architecture:** Phase one is assessment plus minimal refusal guidance, not capability framework construction. Keep `/command` fail-closed, avoid new typed routes, avoid new artifact generators, and avoid broad formatter/native-envelope refactors. The primary outputs are hand-written recovery artifacts that identify what matters before building machinery.

**Tech Stack:** Markdown recovery docs, existing Python MCP preflight/server tests, existing Rook MCP tool catalog, pytest. No new dependencies.

---

## Approved Spec

Implement against:

`docs/superpowers/specs/2026-05-19-agent-capability-recovery-after-command-lockdown-design.md`

The spec status must remain `Accepted`.

## Phase-One Boundary

This plan intentionally replaces the earlier infrastructure-heavy plan. Treat that earlier material as design context only.

Phase one includes:

- accepted spec status verification
- five canonical recovery artifact paths
- current model-facing tool/route audit
- command fallback and known-command usage audit
- 20-40 row intent matrix
- 8-12 prompt synthetic eval baseline
- ranked recovery queue with owners and verification targets
- minimal refusal advisory cleanup using real existing tools only

Phase one defers:

- `mcp_server/src/rook/runscript_refusals.py`
- artifact generator scripts
- static validator test framework
- broad MCP formatter contract changes
- broad native envelope alignment beyond the existing safety branch
- live smoke expansion for this workstream
- new typed routes
- broad command allowlist expansion

Capture the MCP formatter/envelope consistency issue as a ranked follow-up row rather than phase-one infrastructure.

## File Structure

- Verify: `docs/superpowers/specs/2026-05-19-agent-capability-recovery-after-command-lockdown-design.md`
  - Ensure status is `Accepted`.

- Create directory: `docs/superpowers/capability-recovery/`

- Create: `docs/superpowers/capability-recovery/current-tool-route-map.md`
  - Current model-facing Rhino/GH tool catalog grouped by intent and feedback signal.

- Create: `docs/superpowers/capability-recovery/blocked-command-audit.md`
  - Audit of command fallback surfaces and likely historical/raw-command pressure points.

- Create: `docs/superpowers/capability-recovery/agent-intent-map.md`
  - 20-40 row capability matrix using the accepted spec schema.

- Create: `docs/superpowers/capability-recovery/synthetic-eval-baseline.md`
  - 8-12 representative prompt tasks, expected safe route, disallowed route, and outcome fields.

- Create: `docs/superpowers/capability-recovery/ranked-recovery-queue.md`
  - Ranked work queue with owner, action, verification target, and status.

- Modify: `mcp_server/src/rook/preflight.py`
  - Add minimal candidate-tool advisory fields to RunScript safety refusals for obvious commands only.

- Modify: `mcp_server/tests/test_preflight_rhino_command_safety.py`
  - Assert refusal advisory fields for `_Line` and avoid fake/nonexistent tool names.

- Modify: `mcp_server/tests/test_server_execute_safety.py`
  - Add one MCP formatter-preservation test for the existing `Error: <json>` transport.

---

### Task 1: Verify Accepted Spec and Workspace State

**Files:**
- Verify: `docs/superpowers/specs/2026-05-19-agent-capability-recovery-after-command-lockdown-design.md`
- Verify: git worktree state

- [ ] **Step 1: Verify the spec status**

Run:

```powershell
Select-String -Path docs\superpowers\specs\2026-05-19-agent-capability-recovery-after-command-lockdown-design.md -Pattern '^Status: Accepted$'
```

Expected: one match.

- [ ] **Step 2: Check worktree state**

Run:

```powershell
git status --short
```

Expected: `knowledge/gh/component_observations.json` may be dirty and unrelated. Do not stage or edit it.

- [ ] **Step 3: Commit nothing in this task**

No file changes are required if the spec is already accepted.

---

### Task 2: Inventory Current Model-Facing Tool Routes

**Files:**
- Create: `docs/superpowers/capability-recovery/current-tool-route-map.md`

- [ ] **Step 1: Gather the current model-facing tool names**

Run:

```powershell
Select-String -Path mcp_server\src\rook\server.py -Pattern 'name="(rhino_create|rhino_transform|rhino_delete|rhino_objects|rhino_geometry|rhino_select|rhino_select_by_type|rhino_select_none|rhino_measure_|rhino_layer_|rhino_material_ops|rhino_annotation_|rhino_viewport|rhino_views|rhino_import|rhino_export|rhino_block_|gh_status|gh_snapshot|gh_edit|gh_errors|gh_canvas_image|gh_bake_output)"'
```

Expected: matches for real existing model-facing tools. Use this output to keep the route map honest.

- [ ] **Step 2: Create the route map**

Use `apply_patch` to create `docs/superpowers/capability-recovery/current-tool-route-map.md` with this content:

```markdown
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
```

- [ ] **Step 3: Commit the route map**

Run:

```powershell
git add docs/superpowers/capability-recovery/current-tool-route-map.md
git commit -m "docs: inventory typed capability routes"
```

Expected: one doc file committed.

---

### Task 3: Audit Command Fallback Usage

**Files:**
- Create: `docs/superpowers/capability-recovery/blocked-command-audit.md`

- [ ] **Step 1: Gather command fallback references**

Run:

```powershell
rg "rhino_command|known_command|RunScript|/command|interactive_start|interactive_send|command_learner" mcp_server/src mcp_server/tests src/RookNative/Handlers docs -g "!docs/superpowers/capability-recovery/**"
```

Expected: references in preflight/server, SmartExecutor/deprecated interactive paths, native command handlers, tests, and docs.

- [ ] **Step 2: Create the blocked command audit**

Use `apply_patch` to create `docs/superpowers/capability-recovery/blocked-command-audit.md`:

```markdown
# Blocked Command Audit

Status: Phase-one assessment

This audit records where raw command fallback pressure exists after `/command` lockdown. Historical frequency is a weighting signal, not the definition of capability coverage.

| Source | Observed or likely command fallback | Current safety outcome | Typed recovery candidate | Risk class | Follow-up |
| --- | --- | --- | --- | --- | --- |
| MCP `rhino_command` | `_Line`, `_Circle`, `_Box`, other creation commands | rejected unless known safe metadata exists | `rhino_create` | good refusal if advisory names `rhino_create`; bad refusal if no route is discoverable | Add minimal candidate advisory for obvious create commands. |
| MCP `rhino_command` | `_SelNone`, `_SelAll`, `_Sel*` | rejected unless explicitly safe | `rhino_select_none`, `rhino_select`, `rhino_select_by_type` | good refusal when selection route is obvious | Ensure docs/evals teach selection tools. |
| SmartExecutor known-command fallback | stalled command fallback attempts | interactive execution is deprecated/refused | typed route or explicit manual boundary | good refusal | Keep deprecated prompt-driving path out of normal execution. |
| Native `/command` | prompt-inducing commands such as `_Line` without points | fails closed and can quarantine | typed tool with explicit parameters | good refusal | Covered by live RunScript safety smoke. |
| Native `/command` | bare no-effect commands | fail-closed unless explicitly allowlisted | typed route or manual boundary | intentional breaking behavior | Document as compatibility break. |
| Agent behavior | future models reaching for raw commands despite typed tools | refusal expected | stronger tool descriptions and candidate advisories | weak refusal if typed route exists but is hard to discover | Synthetic evals should measure route choice. |
| Formatter/envelope transport | MCP `call_tool` wraps failures as `Error: <json>` text | structured fields are available but not raw JSON transport | parse trailing JSON or future formatter contract | follow-up infrastructure | Queue as phase-two contract cleanup, not phase-one blocker. |
```

- [ ] **Step 3: Commit the audit**

Run:

```powershell
git add docs/superpowers/capability-recovery/blocked-command-audit.md
git commit -m "docs: audit command fallback pressure"
```

Expected: one doc file committed.

---

### Task 4: Build the Agent Intent Matrix

**Files:**
- Create: `docs/superpowers/capability-recovery/agent-intent-map.md`

- [ ] **Step 1: Create the 24-row intent matrix**

Use `apply_patch` to create `docs/superpowers/capability-recovery/agent-intent-map.md`:

```markdown
# Agent Intent Map

Status: Phase-one assessment

`/command` refusal is expected behavior. Lack of typed recovery for common deterministic intent is the product gap.

| Intent | Existing typed route | Model-facing tool | Feedback quality | Postcondition / Verification Signal | Former command fallback | Safety class | Gap severity | Recommended action | Owner | Verification target | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Create point from coordinates | native `/create` | `rhino_create` with `type=POINT` | strong | created object id | `_Point` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Create line from two points | native `/create` | `rhino_create` with `type=LINE` | strong | created object id | `_Line` | good_refusal | low | structured_refusal_advisory | Rook MCP | unit_or_integration_test | covered |
| Create circle from center and radius | native `/create` | `rhino_create` with `type=CIRCLE` | strong | created object id | `_Circle` | good_refusal | low | structured_refusal_advisory | Rook MCP | synthetic_eval_task | covered |
| Create box from corners or dimensions | native `/create` | `rhino_create` with `type=BOX` | strong | created object id | `_Box` | good_refusal | low | structured_refusal_advisory | Rook MCP | synthetic_eval_task | covered |
| Create polyline from points | native `/create` | `rhino_create` with `type=POLYLINE` | strong | created object id | `_Polyline` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Move object by vector | native transform route | `rhino_transform` with `operation=move` | strong | transformed object ids | `_Move` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Rotate object around axis | native transform route | `rhino_transform` with `operation=rotate` | strong | transformed object ids | `_Rotate` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Scale object by factor | native transform route | `rhino_transform` with `operation=scale` | strong | transformed object ids | `_Scale` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Delete objects by id | native delete route | `rhino_delete` | strong | deleted object ids | `_Delete` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Select no objects | native selection route | `rhino_select_none` | strong | selection count is zero | `_SelNone` | good_refusal | low | structured_refusal_advisory | Rook MCP | synthetic_eval_task | covered |
| Select objects by type | native selection route | `rhino_select_by_type` | medium | selected ids/count | `_SelCrv`, `_SelSrf`, `_SelPolysrf` | weak_refusal | medium | tool_description_fix | Rook MCP | synthetic_eval_task | open |
| Query object details | native object/geometry query routes | `rhino_objects`, `rhino_geometry` | strong | object metadata or geometry payload | `_What`, `_List` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Measure bounding box | native measure route | `rhino_measure_bbox` | strong | bounding box min/max | `_BoundingBox` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Measure curve length | native measure route | `rhino_measure_length` | strong | length value | `_Length` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Measure area | native measure route | `rhino_measure_area` | strong | area value | `_Area` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Create layer | native layer route | `rhino_layer_create` | strong | layer metadata | `_Layer` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Move objects to layer | native layer route | `rhino_layer_move_objects` | strong | moved object ids / layer path | `_ChangeLayer` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Create and assign material | native material route | `rhino_material_ops` | medium | material metadata / assigned ids | `_Material`, `_Properties` | weak_refusal | medium | schema_fix | Rook MCP | synthetic_eval_task | open |
| Add text annotation | native annotation route | `rhino_annotation_text` | strong | annotation object id | `_Text` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Create dimensions | native annotation dimension routes | `rhino_annotation_dim_linear`, `rhino_annotation_dim_aligned`, other dimension tools | strong | annotation object id and measured value | `_Dim`, `_DimAligned`, `_DimLinear` | good_refusal | low | tool_description_fix | Rook MCP | synthetic_eval_task | covered |
| Capture viewport or visual state | viewport/capture routes | `rhino_viewport`, `rhino_views_save`, `rhino_capture_depth` | medium | viewport state or capture path | `_ViewCaptureToFile` | bad_refusal | high | typed_route_addition | Rook MCP/RookNative | synthetic_eval_task | open |
| Import model file | native import route | `rhino_import` | medium | import result / object delta if available | `_Import` | weak_refusal | medium | schema_fix | Rook MCP | synthetic_eval_task | open |
| Export selected or document geometry | native export route | `rhino_export` | medium | exported file path | `_Export`, `_SaveAs` | weak_refusal | medium | schema_fix | Rook MCP | synthetic_eval_task | open |
| Mutate block definition object | native/managed block routes | `rhino_block_replace_object_geometry`, `rhino_block_transform_object`, `rhino_block_set_layers`, related block tools | strong | block mutation summary / object ids | raw block edit commands | good_refusal | medium | tool_description_fix | Rook MCP + managed companion | unit_or_integration_test | open |
| Solve or inspect Grasshopper document | managed/native GH bridge | `gh_status`, `gh_snapshot`, `gh_edit`, `gh_errors` | strong | solve status, errors, snapshot | raw Grasshopper/Rhino command attempts | good_refusal | medium | tool_description_fix | Rook MCP + managed companion | synthetic_eval_task | open |
| Bake Grasshopper output | managed/native GH bridge | `gh_bake_output` | strong | baked object ids | `_Bake` | good_refusal | medium | tool_description_fix | Rook MCP + managed companion | synthetic_eval_task | open |
| Recover uncertain command state | native prompt/cancel recovery | `rhino_command_interactive_prompt`, `rhino_command_interactive_cancel` | strong | verified cancel result / idle prompt | interactive start/send | good_refusal | low | no_action | RookNative | live_rhino_smoke_test | covered |
| MCP refusal envelope parseability | existing MCP formatter wraps dict failures as `Error: <json>` | `rhino_command` refusal response | medium | parseable trailing JSON text | raw retry after opaque refusal | weak_refusal | medium | structured_refusal_advisory | Rook MCP | unit_or_integration_test | queued |
```

- [ ] **Step 2: Check row count**

Run:

```powershell
$rows = (Select-String -Path docs\superpowers\capability-recovery\agent-intent-map.md -Pattern '^\| [^|]+ \|' | Measure-Object).Count - 2; $rows
```

Expected: at least `20`.

- [ ] **Step 3: Commit the intent map**

Run:

```powershell
git add docs/superpowers/capability-recovery/agent-intent-map.md
git commit -m "docs: map agent capability coverage"
```

Expected: one doc file committed.

---

### Task 5: Build a Small Synthetic Eval Baseline

**Files:**
- Create: `docs/superpowers/capability-recovery/synthetic-eval-baseline.md`

- [ ] **Step 1: Create the eval baseline**

Use `apply_patch` to create `docs/superpowers/capability-recovery/synthetic-eval-baseline.md`:

```markdown
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
```

- [ ] **Step 2: Commit the baseline**

Run:

```powershell
git add docs/superpowers/capability-recovery/synthetic-eval-baseline.md
git commit -m "docs: seed synthetic capability evals"
```

Expected: one doc file committed.

---

### Task 6: Produce the Ranked Recovery Queue

**Files:**
- Create: `docs/superpowers/capability-recovery/ranked-recovery-queue.md`

- [ ] **Step 1: Create the queue**

Use `apply_patch` to create `docs/superpowers/capability-recovery/ranked-recovery-queue.md`:

```markdown
# Ranked Recovery Queue

Status: Phase-one assessment

Rows are ranked by workflow importance, safety tractability, signal strength, and verification quality. The queue is executable only when every row has an owner and verification target.

| Rank | Gap | Evidence | Recommended action | Owner | Verification target | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | View capture recovery is unclear for ordinary screenshot/export-image intent. | Current map has `rhino_capture_depth`, viewport routes, and view save/restore, but no confirmed general view-capture-to-file route in the phase-one audit. | typed_route_addition | Rook MCP/RookNative | synthetic_eval_task | open |
| 2 | Material creation/assignment is covered by `rhino_material_ops`, but the action-schema shape may be less discoverable than direct material tools. | Intent map marks material recovery as weak. | schema_fix | Rook MCP | synthetic_eval_task | open |
| 3 | Import/export route postconditions need clearer object-delta and file existence feedback. | Intent map marks import/export as medium severity weak refusals. | schema_fix | Rook MCP/RookNative | unit_or_integration_test | open |
| 4 | Selection by command aliases should redirect toward real selection tools. | `_Sel*` habits are likely after `/command` lockdown. | tool_description_fix | Rook MCP | synthetic_eval_task | open |
| 5 | MCP refusal transport remains `Error: <json>` text; fields are parseable but not a clean raw JSON result. | Formatter currently preserves structured dict failures behind an `Error: ` prefix. | structured_refusal_advisory | Rook MCP | unit_or_integration_test | queued |
| 6 | GH workflows need synthetic evals that confirm agents choose `gh_*` tools instead of Rhino command strings. | Intent map marks GH solve/bake rows as open despite typed coverage. | tool_description_fix | Rook MCP + managed companion | synthetic_eval_task | open |
| 7 | Block-definition mutation tool discovery needs reinforcement because ownership crosses native/managed boundaries. | Intent map marks block mutation as medium severity open. | tool_description_fix | Rook MCP + managed companion | unit_or_integration_test | open |
| 8 | Safe command metadata promotion policy needs concrete candidates only after matrix/eval evidence. | `/command` remains intentionally fail-closed. | safe_command_metadata | RookNative/Rook MCP | live_rhino_smoke_test | deferred |
```

- [ ] **Step 2: Commit the queue**

Run:

```powershell
git add docs/superpowers/capability-recovery/ranked-recovery-queue.md
git commit -m "docs: rank capability recovery gaps"
```

Expected: one doc file committed.

---

### Task 7: Add Minimal Refusal Advisory Cleanup

**Files:**
- Modify: `mcp_server/src/rook/preflight.py`
- Modify: `mcp_server/tests/test_preflight_rhino_command_safety.py`
- Modify: `mcp_server/tests/test_server_execute_safety.py`

- [ ] **Step 1: Add focused preflight tests for real candidate tools**

In `mcp_server/tests/test_preflight_rhino_command_safety.py`, extend `assert_safety_refusal` to tolerate advisory fields without requiring them on every refusal:

```python
def assert_safety_refusal(result, reason, command=None, mode=None):
    assert result is not None
    assert result["success"] is False
    assert result["data"]["error"] == "run_script_safety_refusal"
    assert result["data"]["error_code"] == "run_script_safety_refusal"
    assert result["data"]["reason"] == reason
    assert result["data"]["verified"] is False
    assert result["data"]["retry_allowed"] is False
    assert result["data"]["safety_class"] == "good_refusal"
    if command is not None:
        assert result["data"]["command"] == command
        assert result["data"]["detected_command"] == command
    if mode is not None:
        assert result["data"]["mode"] == mode
```

Add these tests:

```python
def test_line_refusal_advises_existing_rhino_create_tool():
    result = preflight_rhino_command("_Line", None)

    assert_safety_refusal(result, "command_safety_unavailable", command="_Line")
    assert result["data"]["candidate_tools"] == [
        {
            "tool": "rhino_create",
            "reason": "Create lines through the typed creation schema with explicit start and end points.",
            "required_parameters": ["type", "start", "end"],
        }
    ]


def test_circle_refusal_advises_existing_rhino_create_tool():
    result = preflight_rhino_command("_Circle", None)

    assert_safety_refusal(result, "command_safety_unavailable", command="_Circle")
    assert result["data"]["candidate_tools"] == [
        {
            "tool": "rhino_create",
            "reason": "Create circles through the typed creation schema with explicit center and radius.",
            "required_parameters": ["type", "center", "radius"],
        }
    ]


def test_selection_refusal_advises_existing_selection_tool():
    result = preflight_rhino_command("_SelNone", None)

    assert_safety_refusal(result, "command_safety_unavailable", command="_SelNone")
    assert result["data"]["candidate_tools"] == [
        {
            "tool": "rhino_select_none",
            "reason": "Clear selection through the typed selection tool instead of a raw command.",
            "required_parameters": [],
        }
    ]
```

- [ ] **Step 2: Run the failing preflight tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py::test_line_refusal_advises_existing_rhino_create_tool mcp_server/tests/test_preflight_rhino_command_safety.py::test_circle_refusal_advises_existing_rhino_create_tool mcp_server/tests/test_preflight_rhino_command_safety.py::test_selection_refusal_advises_existing_selection_tool -q
```

Expected: fail until `preflight.py` adds advisory fields.

- [ ] **Step 3: Add minimal advisory helpers in preflight**

In `mcp_server/src/rook/preflight.py`, add this helper above `_runscript_safety_refusal`:

```python
def _normalized_command_token(command: Any) -> str:
    if not isinstance(command, str):
        return ""
    token = command.strip().split(maxsplit=1)[0]
    return token.lstrip("_-!").lower()


def _candidate_tools_for_command(command: Any) -> list[dict[str, Any]]:
    normalized = _normalized_command_token(command)
    if normalized == "line":
        return [
            {
                "tool": "rhino_create",
                "reason": "Create lines through the typed creation schema with explicit start and end points.",
                "required_parameters": ["type", "start", "end"],
            }
        ]
    if normalized == "circle":
        return [
            {
                "tool": "rhino_create",
                "reason": "Create circles through the typed creation schema with explicit center and radius.",
                "required_parameters": ["type", "center", "radius"],
            }
        ]
    if normalized == "box":
        return [
            {
                "tool": "rhino_create",
                "reason": "Create boxes through the typed creation schema with explicit corners or dimensions.",
                "required_parameters": ["type", "corner1", "corner2"],
            }
        ]
    if normalized == "selnone":
        return [
            {
                "tool": "rhino_select_none",
                "reason": "Clear selection through the typed selection tool instead of a raw command.",
                "required_parameters": [],
            }
        ]
    return []
```

Update `_runscript_safety_refusal` so its `data` literal includes these fields:

```python
    candidate_tools = _candidate_tools_for_command(command)
    data = {
        "error": RUNSCRIPT_REFUSAL_ERROR,
        "error_code": RUNSCRIPT_REFUSAL_ERROR,
        "reason": reason,
        "command": command,
        "detected_command": command,
        "mode": mode,
        "verified": False,
        "safety_class": "good_refusal",
        "retry_allowed": False,
        "prompt_state": "not_checked",
        "recovery": "Use a typed Rook tool with explicit parameters; do not retry the same raw command.",
    }
    if candidate_tools:
        data["candidate_tools"] = candidate_tools
```

Keep the existing `data.update(extra_data)` after this block so older preflight details such as `missing_required` still pass through.

- [ ] **Step 4: Run the preflight suite**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Add one MCP transport test**

`mcp_server/tests/test_server_execute_safety.py` already imports `pytest` and uses `server.call_tool`. Add `import json` at the top and append:

```python
@pytest.mark.asyncio
async def test_rhino_command_refusal_advisory_survives_existing_error_text_transport(monkeypatch):
    from rook import server

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("rhino_command refusal must happen before call_rhino")

    monkeypatch.setattr(server, "call_rhino", fail_call_rhino)
    monkeypatch.setattr(server.command_learner, "knowledge_store", None)

    response = await server.call_tool("rhino_command", {"command": "_Line"})

    assert response[0].text.startswith("Error: ")
    data = json.loads(response[0].text.removeprefix("Error: "))
    assert data["error_code"] == "run_script_safety_refusal"
    assert data["retry_allowed"] is False
    assert data["candidate_tools"][0]["tool"] == "rhino_create"
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit minimal refusal cleanup**

Run:

```powershell
git add mcp_server/src/rook/preflight.py mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py docs/superpowers/capability-recovery/ranked-recovery-queue.md
git commit -m "feat: add typed advisories to command refusals"
```

Expected: commit includes only files touched in this task. If `ranked-recovery-queue.md` was not changed during this task, omit it from `git add`.

---

### Task 8: Final Verification and PR Update

**Files:**
- Read/update as needed: PR #161 body

- [ ] **Step 1: Run documentation and focused test checks**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py -q
git diff --check main...HEAD
```

Expected:

- preflight tests pass
- diff check is clean

- [ ] **Step 2: Verify all five canonical artifacts exist**

Run:

```powershell
Get-ChildItem docs\superpowers\capability-recovery\*.md | Select-Object Name
```

Expected names:

- `agent-intent-map.md`
- `blocked-command-audit.md`
- `current-tool-route-map.md`
- `ranked-recovery-queue.md`
- `synthetic-eval-baseline.md`

- [ ] **Step 3: Verify no unrelated file is staged**

Run:

```powershell
git status --short
```

Expected: no staged unrelated changes. `knowledge/gh/component_observations.json` may remain dirty and unstaged.

- [ ] **Step 4: Update PR description**

Update PR #161 with a short section:

```markdown
### Agent capability recovery phase one

- Added assessment-first recovery artifacts under `docs/superpowers/capability-recovery/`.
- Mapped typed capability coverage after `/command` lockdown.
- Seeded a small synthetic eval baseline for route-choice assessment.
- Ranked recovery gaps before adding new typed routes or safe command metadata.
- Added minimal refusal advisories for obvious raw command attempts using real existing tools only.

Deferred intentionally:

- artifact generator/validator framework
- broad MCP formatter contract changes
- broader native refusal envelope alignment
- live smoke expansion for capability recovery
- new typed routes
```

- [ ] **Step 5: Push the branch**

Run:

```powershell
git push
```

Expected: branch pushed to PR #161.

---

## Self-Review Checklist

- The plan is assessment-first and does not build a framework before the first capability map exists.
- Candidate tools named in refusal advisories are real existing tools: `rhino_create` and `rhino_select_none`.
- The MCP formatter issue is captured as a queue row, not forced into phase-one infrastructure.
- No native code changes are required by this phase-one plan.
- No new typed routes are created by this phase-one plan.
- The five artifact paths match the accepted spec.
- Every queue row has an owner and verification target.
