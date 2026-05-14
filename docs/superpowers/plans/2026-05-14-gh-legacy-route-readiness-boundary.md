# GH Legacy Route Readiness Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close remaining Grasshopper phantom-canvas escape hatches by auditing registered `/gh/*` routes, removing stale `gh_query` agent-surface references, and making representative legacy mutation routes fail closed when Grasshopper is not ready.

**Architecture:** Build on the reviewed `gh_edit` readiness branch, reusing `GrasshopperHandler.EnsureGrasshopperReadyForEdit` and the existing Python verification-field hoisting. Managed route handlers are the containment layer; Python dispatch and tool groups are secondary surfaces that must not expose stale `gh_query` names or drop not-ready metadata.

**Tech Stack:** C#/.NET managed companion, RhinoCommon/Grasshopper reflection bridge, native C++ route proxy, Python MCP server, pytest, xUnit.

---

## Execution Prerequisite

Implement this plan on a new branch stacked on top of `codex/gh-edit-partial-failure-contract`, or after that branch has merged. That branch already contains:

- `GrasshopperHandler.EnsureGrasshopperReadyForEdit`
- `GrasshopperHandler.GrasshopperNotReadyResponse`
- `GetGrasshopper(createDocumentIfMissing: false)` support
- guarded `/gh/query`, `/gh/snapshot`, and `/gh/edit`
- Python dispatcher verification-field hoisting
- `gh_status` normalization

Do not implement from this docs-only branch unless it has first been rebased onto the readiness branch.

## File Structure

- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
  - Owns managed GH route behavior and readiness guards.
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
  - Adds testable bridge wrapper methods for representative legacy mutation callbacks.
- Modify: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
  - Pins managed not-ready shape for representative legacy mutation routes.
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Removes stale `gh_query` verification-hoist membership and exposes a testable readiness-hoist constant.
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
  - Confirms `gh_query` is not in any agent-requestable tool group.
- Modify: `mcp_server/tests/test_dispatcher_safety.py`
  - Pins absence of `gh_query` from `BRIDGE_ROUTES`, `TRANSFORM_FUNCTIONS`, readiness hoist tools, and `TOOL_GROUPS`.
- Modify: `mcp_server/tests/test_chat_runner.py`
  - Pins nested `data.verified` and `data.verification_note` fallback for legacy route not-ready shapes.
- Create: `docs/superpowers/audits/2026-05-14-gh-route-readiness-inventory.md`
  - Completed registered-route inventory with route categories and implementation status.
- Create: `mcp_server/tools/gh_readiness_live_harness.py`
  - Optional live Rhino validation harness for closed/open GH scenarios.

---

### Task 1: Route Inventory Audit

**Files:**
- Create: `docs/superpowers/audits/2026-05-14-gh-route-readiness-inventory.md`
- Read: `src/RookNative/RookServer.cpp`
- Read: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Read: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Read: `src/Rook/Handlers/GrasshopperHandler.cs`
- Read: `mcp_server/src/rook/server.py`
- Read: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Read: `mcp_server/src/rook/agent/tool_groups.py`

- [ ] **Step 1: Generate the registered route list**

Run:

```powershell
rg -n '"/gh/' src\RookNative\RookServer.cpp src\RookNative\Handlers\GrasshopperProxyHandler.cpp src\Rook\InternalBridge\NativeGhBridgeRegistrar.cs src\Rook\Handlers\GrasshopperHandler.cs
```

Expected: output includes every registered public `/gh/*` native route and the managed callback or handler methods.

- [ ] **Step 2: Create the audit document**

Create `docs/superpowers/audits/2026-05-14-gh-route-readiness-inventory.md` with this content:

```markdown
# GH Route Readiness Inventory

Date: 2026-05-14

Source spec: `docs/superpowers/specs/2026-05-14-gh-legacy-route-readiness-boundary-design.md`

## Category Definitions

- Read-only status/library: may run without `ready_for_edit` if it has no document/canvas side effects.
- Read-only canvas inspection: requires `ready_for_edit`, fails closed.
- Mutation: requires `ready_for_edit`, fails closed.
- Imperative lifecycle: may change readiness only when explicitly reviewed and documented.

## Inventory

| Route | Native handler | Managed callback / handler | Category | Requires `ready_for_edit` | Side effects allowed | Python tool exposure | Expected not-ready response | Test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/gh/status` | `HandleGrasshopperStatus` | `HandleStatus` -> `Core.GetStatus` | Read-only status/library | No | Status query only | `gh_status` | `success: true`; `data.ready_for_edit: false` allowed | Existing `gh_status` tests; live harness |
| `/gh/document` | `HandleGrasshopperDocument` | `HandleDocument` -> document info | Read-only status/library or inspection after review | No unless it reads canvas internals | Document metadata only | No direct agent bridge expected | Must not create document/canvas | Inventory review |
| `/gh/query` | `HandleGrasshopperQuery` | `HandleQuery` -> query document method | Read-only canvas inspection | Yes | None | No Python agent tool | `success: false`; `data.error: grasshopper_not_ready`; `verified: false` in agent path | Existing query not-ready test |
| `/gh/selection` | `HandleGrasshopperSelection` | `HandleSelection` -> selection method | Read-only canvas inspection | Yes | None | `gh_selection` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard or document existing guard |
| `/gh/categories` | `HandleGrasshopperCategories` | `HandleCategories` -> categories method | Read-only status/library | No | Component catalog query only | `gh_categories` | No readiness failure required unless implementation touches canvas | Existing categories tests or inventory note |
| `/gh/library` | `HandleGrasshopperLibrary` | `HandleLibrary` -> search library method | Read-only status/library | No | Component catalog search only | `gh_library` if exposed | No readiness failure required unless implementation touches canvas | Existing library tests or inventory note |
| `/gh/value` `GET` | `HandleGrasshopperGetValue` | `HandleGetValue` -> value method | Read-only canvas inspection | Yes | None | `gh_get_value` if exposed | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard or document existing guard |
| `/gh/value` `POST` | `HandleGrasshopperSetValue` | `HandleSetValue` -> `Handler.SetValue` | Mutation | Yes | Set value only after readiness | `gh_set_value` or internal caller | `success: false`; `data.error: grasshopper_not_ready` | New representative guard test |
| `/gh/script` | `HandleGrasshopperSetScript` | `HandleSetScript` -> script method | Mutation | Yes | Script source mutation only after readiness | `gh_set_script` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/script-params` | `HandleGrasshopperScriptParams` | `HandleScriptParams` -> script params method | Mutation | Yes | Script pin mutation only after readiness | `gh_set_script_pins` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/connections` | `HandleGrasshopperConnections` | `HandleConnections` -> connection info method | Read-only canvas inspection | Yes | None | internal/readonly callers | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/delete` | `HandleGrasshopperDelete` | `HandleDelete` -> delete method | Mutation | Yes | Delete canvas objects only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/preview` | `HandleGrasshopperPreview` | `HandlePreview` -> preview method | Mutation | Yes | Preview flag mutation only after readiness | `gh_preview` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/clear` | `HandleGrasshopperClear` | `HandleClear` -> `Handler.ClearCanvas` | Lifecycle review item; recommended mutation | Requires review | Clear active document only if classified as mutation | `gh_clear` | Classification-specific | Review checkpoint before behavior change |
| `/gh/document/open` | `HandleGrasshopperOpenDocument` | `HandleOpenDocument` -> `Handler.OpenDocument` | Imperative lifecycle | No `ready_for_edit` precondition | May open active document | `gh_document_open` | Lifecycle response with postcondition status | Review checkpoint before behavior change |
| `/gh/document/new` | `HandleGrasshopperNewDocument` | `HandleNewDocument` -> `Handler.NewDocument` | Imperative lifecycle | No `ready_for_edit` precondition | May create active document | `gh_document_new` | Lifecycle response with postcondition status | Review checkpoint before behavior change |
| `/gh/move` | `HandleGrasshopperMove` | `HandleMove` -> move method | Mutation | Yes | Move canvas objects only after readiness | `gh_move` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/group` | `HandleGrasshopperGroup` | `HandleGroup` -> group method | Mutation | Yes | Create/update group only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/groups` | `HandleGrasshopperGroups` | `HandleGroups` -> groups method | Read-only canvas inspection | Yes | None | `gh_groups` if exposed | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/group-resize` | `HandleGrasshopperGroupResize` | `HandleGroupResize` -> group resize method | Mutation | Yes | Resize group only after readiness | `gh_group_resize` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/cluster` | `HandleGrasshopperCluster` | `HandleCluster` -> cluster method | Mutation | Yes | Cluster creation only after readiness | `gh_cluster` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/explore-selection` | `HandleGrasshopperExploreSelection` | `HandleExploreSelection` -> exploration method | Read-only canvas inspection | Yes | Selection probing only | internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard or document internal-only |
| `/gh/explore-cluster` | `HandleGrasshopperExploreCluster` | `HandleExploreCluster` -> exploration method | Read-only canvas inspection | Yes | Cluster probing only | internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard or document internal-only |
| `/gh/batch-component-info` | `HandleGrasshopperBatchComponentInfo` | `HandleBatchComponentInfo` -> batch info method | Read-only status/library | No | Component type metadata lookup only | `gh_batch_component_info` | No readiness failure required unless implementation touches canvas | Inventory review |
| `/gh/create-component` | `HandleGrasshopperCreateComponent` | `HandleCreateComponent` -> create component method | Mutation | Yes | Create component only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/create-slider` | `HandleGrasshopperCreateSlider` | `HandleCreateSlider` -> `Handler.CreateSlider` | Mutation | Yes | Create slider only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | New representative guard test |
| `/gh/create-panel` | `HandleGrasshopperCreatePanel` | `HandleCreatePanel` -> `Handler.CreatePanel` | Mutation | Yes | Create panel only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/component` | `HandleGrasshopperComponent` | `HandleComponent` -> component info method | Read-only canvas inspection | Yes | None | `gh_component` if exposed | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/inspect-output` | `HandleGrasshopperInspectOutput` | `HandleInspectOutput` -> inspect output method | Read-only canvas inspection | Yes | None | `gh_inspect_output` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/errors` | `HandleGrasshopperErrors` | `HandleErrors` -> errors method | Read-only canvas inspection | Yes | None | `gh_errors` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/connect` | `HandleGrasshopperConnect` | `HandleConnect` -> `Handler.ConnectComponents` | Mutation | Yes | Add wire only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | New representative guard test |
| `/gh/disconnect` | `HandleGrasshopperDisconnect` | `HandleDisconnect` -> disconnect method | Mutation | Yes | Remove wire only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/set-reference` | `HandleGrasshopperSetReference` | `HandleSetReference` -> reference method | Mutation | Yes | Set persistent reference only after readiness | `gh_set_reference` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/get-reference` | `HandleGrasshopperGetReference` | `HandleGetReference` -> reference read method | Read-only canvas inspection | Yes | None | `gh_get_reference` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/clear-reference` | `HandleGrasshopperClearReference` | `HandleClearReference` -> clear reference method | Mutation | Yes | Clear persistent references only after readiness | `gh_clear_reference` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/solve` | `HandleGrasshopperSolve` | `HandleSolve` -> solve method | Mutation | Yes | Recompute only after readiness | legacy/internal | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/bake` | `HandleGrasshopperBakeOutput` | `HandleBakeOutput` -> bake method | Mutation | Yes | Bake geometry only after readiness | `gh_bake_output` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/snapshot` | `HandleGrasshopperSnapshot` | `HandleSnapshot` -> `Handler.TakeSnapshot` | Read-only canvas inspection | Yes | None | `gh_snapshot` | `success: false`; `data.error: grasshopper_not_ready` | Existing readiness tests |
| `/gh/edit` | `HandleGrasshopperEdit` | `HandleEdit` -> `Handler.ApplyEdit` | Mutation | Yes | Batch mutation only after readiness | `gh_edit` | `success: false`; `data.error: grasshopper_not_ready` | Existing contract tests |
| `/gh/undo` | `HandleGrasshopperUndo` | `HandleUndo` -> undo method | Mutation | Yes | Undo only after readiness | `gh_undo` | `success: false`; `data.error: grasshopper_not_ready` | Add managed guard |
| `/gh/canvas/focus` | `HandleGrasshopperCanvasFocus` | `HandleCanvasFocus` -> `Handler.FocusCanvas` | Lifecycle/navigation review item | Requires review | UI navigation only; no document creation unless approved | `gh_canvas_focus` | Classification-specific | Review checkpoint before behavior change |
| `/gh/canvas/zoom` | `HandleGrasshopperCanvasZoom` | `HandleCanvasZoom` -> `Handler.ZoomCanvas` | Lifecycle/navigation review item | Requires review | UI navigation only; no document creation unless approved | `gh_canvas_zoom` | Classification-specific | Review checkpoint before behavior change |
| `/gh/canvas/image` | `HandleGrasshopperCanvasImage` | `HandleCanvasImage` -> `Handler.CaptureCanvasImage` | Inspection/navigation review item | Requires review | Capture only; no document creation unless approved | `gh_canvas_image` | Classification-specific | Review checkpoint before behavior change |
```

- [ ] **Step 3: Verify no registered route is missing**

Run:

```powershell
rg -o '"/gh/[^"]+' src\RookNative\RookServer.cpp | Sort-Object -Unique
```

Expected: every route in the command output appears exactly once in the inventory table.

- [ ] **Step 4: Commit**

Run:

```powershell
git add docs\superpowers\audits\2026-05-14-gh-route-readiness-inventory.md
git commit -m "docs: inventory gh route readiness boundary"
```

---

### Task 2: Remove Stale Python `gh_query` Agent Surface

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/tests/test_dispatcher_safety.py`

- [ ] **Step 1: Write failing Python tests**

Add this test to `mcp_server/tests/test_dispatcher_safety.py`:

```python
def test_gh_query_not_exposed_to_agent_dispatch_surfaces():
    """Legacy /gh/query remains native HTTP compatibility only."""
    from rook.agent import tool_dispatcher
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "gh_query" not in tool_dispatcher.BRIDGE_ROUTES
    assert "gh_query" not in tool_dispatcher.TRANSFORM_FUNCTIONS
    assert hasattr(tool_dispatcher, "GH_READINESS_HOIST_TOOLS")
    assert "gh_query" not in tool_dispatcher.GH_READINESS_HOIST_TOOLS

    exposed_groups = [
        group_name
        for group_name, tools in TOOL_GROUPS.items()
        if "gh_query" in tools
    ]
    assert exposed_groups == []
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest mcp_server/tests/test_dispatcher_safety.py::test_gh_query_not_exposed_to_agent_dispatch_surfaces -q
```

Expected before implementation: failure because `GH_READINESS_HOIST_TOOLS` does not exist or `gh_query` is still in the inline hoist set.

- [ ] **Step 3: Add a named hoist constant and remove `gh_query`**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, near `_hoist_nested_verification_fields`, add:

```python
GH_READINESS_HOIST_TOOLS: frozenset[str] = frozenset({
    "gh_snapshot",
    "gh_edit",
})
```

Then replace:

```python
if name in {"gh_snapshot", "gh_edit", "gh_query"}:
    result = _hoist_nested_verification_fields(result)
```

with:

```python
if name in GH_READINESS_HOIST_TOOLS:
    result = _hoist_nested_verification_fields(result)
```

- [ ] **Step 4: Run the focused test**

Run:

```powershell
python -m pytest mcp_server/tests/test_dispatcher_safety.py::test_gh_query_not_exposed_to_agent_dispatch_surfaces -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add mcp_server\src\rook\agent\tool_dispatcher.py mcp_server\tests\test_dispatcher_safety.py
git commit -m "fix: remove stale gh_query agent exposure"
```

---

### Task 3: Pin Representative Legacy Not-Ready Shape

**Files:**
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Modify: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`

- [ ] **Step 1: Add shared assertion helper**

In `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`, add this private helper inside `NativeGhBridgeRegistrarTests`:

```csharp
private static void AssertGrasshopperNotReady(ApiResponse result, string operation)
{
    Assert.False(result.Success);
    Assert.NotNull(result.Data);

    var dataType = result.Data!.GetType();
    Assert.Equal(
        "grasshopper_not_ready",
        dataType.GetProperty("error")?.GetValue(result.Data));
    Assert.Equal(
        false,
        dataType.GetProperty("ready_for_edit")?.GetValue(result.Data));
    Assert.Equal(
        false,
        dataType.GetProperty("verified")?.GetValue(result.Data));
    Assert.Equal(
        operation,
        dataType.GetProperty("operation")?.GetValue(result.Data));
    Assert.NotNull(dataType.GetProperty("errors")?.GetValue(result.Data));
    Assert.NotNull(dataType.GetProperty("message")?.GetValue(result.Data));
    Assert.NotNull(dataType.GetProperty("verification_note")?.GetValue(result.Data));
    Assert.NotNull(dataType.GetProperty("status")?.GetValue(result.Data));
}
```

Update `QueryDocumentForBridge_NotReady_ReturnsStructuredFailure` to call:

```csharp
AssertGrasshopperNotReady(result, "gh_query");
```

- [ ] **Step 2: Add representative failing tests**

Add these tests to `NativeGhBridgeRegistrarTests`:

```csharp
[Fact]
public void CreateSliderForBridge_NotReady_ReturnsStructuredFailure()
{
    var result = NativeGhBridgeRegistrar.CreateSliderForBridge("{}");

    AssertGrasshopperNotReady(result, "gh_create_slider");
}

[Fact]
public void ConnectForBridge_NotReady_ReturnsStructuredFailure()
{
    var result = NativeGhBridgeRegistrar.ConnectForBridge("{}");

    AssertGrasshopperNotReady(result, "gh_connect");
}

[Fact]
public void SetValueForBridge_NotReady_ReturnsStructuredFailure()
{
    var result = NativeGhBridgeRegistrar.SetValueForBridge("{}");

    AssertGrasshopperNotReady(result, "gh_set_value");
}
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests" --no-restore
```

Expected before implementation: compile failure because `CreateSliderForBridge`, `ConnectForBridge`, and `SetValueForBridge` do not exist, or assertion failure because `verification_note` is missing.

- [ ] **Step 4: Add testable bridge wrapper methods**

In `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`, change the callback lambdas for create-slider, connect, and set-value to call named methods.

For `HandleConnect`, replace:

```csharp
requestJson => Handler.ConnectComponents(requestJson)
```

with:

```csharp
ConnectForBridge
```

Then add:

```csharp
internal static ApiResponse ConnectForBridge(string requestJson)
{
    return Handler.ConnectComponents(requestJson);
}
```

For `HandleCreateSlider`, replace:

```csharp
requestJson => Handler.CreateSlider(requestJson)
```

with:

```csharp
CreateSliderForBridge
```

Then add:

```csharp
internal static ApiResponse CreateSliderForBridge(string requestJson)
{
    return Handler.CreateSlider(requestJson);
}
```

For `HandleSetValue`, replace:

```csharp
requestJson => Handler.SetValue(requestJson)
```

with:

```csharp
SetValueForBridge
```

Then add:

```csharp
internal static ApiResponse SetValueForBridge(string requestJson)
{
    return Handler.SetValue(requestJson);
}
```

- [ ] **Step 5: Add `verification_note` to managed not-ready data**

In `src/Rook/Handlers/GrasshopperHandler.cs`, update `GrasshopperNotReadyResponse` so the anonymous `Data` object includes:

```csharp
verification_note = "Call gh_status to inspect readiness. Use an explicit lifecycle tool only if Grasshopper is the intended substrate.",
```

The `Data` object should retain:

```csharp
error = "grasshopper_not_ready",
errors = new[] { reason },
message = reason,
operation,
ready_for_edit = false,
verified = false,
status,
```

- [ ] **Step 6: Run the focused managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests" --no-restore
```

Expected: all `NativeGhBridgeRegistrarTests` pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src\Rook\InternalBridge\NativeGhBridgeRegistrar.cs src\Rook.Tests\InternalBridge\NativeGhBridgeRegistrarTests.cs src\Rook\Handlers\GrasshopperHandler.cs
git commit -m "test: pin legacy gh readiness failures"
```

---

### Task 4: Guard Representative Legacy Mutation Routes

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Test: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`

- [ ] **Step 1: Guard `CreateSlider`**

In `GrasshopperHandler.CreateSlider`, replace the initial `GetGrasshopper()` block with:

```csharp
var notReady = EnsureGrasshopperReadyForEdit("gh_create_slider");
if (notReady != null)
    return notReady;

var gh = GetGrasshopper(createDocumentIfMissing: false);
if (!gh.Success)
    return GrasshopperNotReadyResponse("gh_create_slider", null, gh.Error);
```

- [ ] **Step 2: Guard `ConnectComponents`**

In `GrasshopperHandler.ConnectComponents`, replace the initial `GetGrasshopper()` block with:

```csharp
var notReady = EnsureGrasshopperReadyForEdit("gh_connect");
if (notReady != null)
    return notReady;

var gh = GetGrasshopper(createDocumentIfMissing: false);
if (!gh.Success)
    return GrasshopperNotReadyResponse("gh_connect", null, gh.Error);
```

- [ ] **Step 3: Guard `SetValue`**

In `GrasshopperHandler.SetValue`, replace the initial `GetGrasshopper()` block with:

```csharp
var notReady = EnsureGrasshopperReadyForEdit("gh_set_value");
if (notReady != null)
    return notReady;

var gh = GetGrasshopper(createDocumentIfMissing: false);
if (!gh.Success)
    return GrasshopperNotReadyResponse("gh_set_value", null, gh.Error);
```

- [ ] **Step 4: Run representative managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests" --no-restore
```

Expected: representative not-ready tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\Rook\Handlers\GrasshopperHandler.cs src\Rook.Tests\InternalBridge\NativeGhBridgeRegistrarTests.cs
git commit -m "fix: guard legacy gh mutation routes"
```

---

### Task 5: Preserve Legacy Not-Ready Metadata In Python Paths

**Files:**
- Modify: `mcp_server/tests/test_chat_runner.py`
- Modify: `mcp_server/tests/test_dispatcher_safety.py`
- Modify only if needed: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify only if needed: `mcp_server/src/rook/agent/tool_dispatcher.py`

- [ ] **Step 1: Add dispatcher not-ready preservation test**

In `mcp_server/tests/test_dispatcher_safety.py`, add:

```python
def test_gh_legacy_not_ready_result_hoists_nested_verification_fields():
    from rook.agent.tool_dispatcher import _hoist_nested_verification_fields

    result = {
        "success": False,
        "data": {
            "error": "grasshopper_not_ready",
            "verified": False,
            "message": "No active Grasshopper document.",
            "verification_note": "Call gh_status to inspect readiness.",
        },
    }

    hoisted = _hoist_nested_verification_fields(result)

    assert hoisted["verified"] is False
    assert hoisted["verification_note"] == "Call gh_status to inspect readiness."
```

- [ ] **Step 2: Add chat-runner fallback test**

Add this test beside `test_run_turn_verification_hoisting_from_nested_data` in `mcp_server/tests/test_chat_runner.py`:

```python
@pytest.mark.asyncio
async def test_run_turn_uses_nested_legacy_readiness_verification_note(conversation):
    """Legacy GH route readiness failures preserve explicit nested notes."""
    mock_executor = AsyncMock(return_value={
        "success": False,
        "data": {
            "error": "grasshopper_not_ready",
            "message": "No active Grasshopper canvas",
            "verified": False,
            "verification_note": "Call gh_status to inspect readiness.",
        },
    })
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    tool_response = _make_tool_response(
        "gh_create_slider", {}, tool_call_id="call_gh_legacy_not_ready"
    )
    text_response = _make_text_response("Grasshopper is not ready.")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "create slider", system_prompt="test"):
            events.append(event)

    result_events = [e for e in events if e.type == "tool_result"]
    assert len(result_events) == 1
    assert result_events[0].verified is False
    assert result_events[0].verification_note == "Call gh_status to inspect readiness."
```

- [ ] **Step 3: Run focused Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_dispatcher_safety.py mcp_server/tests/test_chat_runner.py -q
```

Expected: tests pass.

- [ ] **Step 4: Implement only if tests reveal a gap**

If dispatcher hoisting fails, keep `_hoist_nested_verification_fields` behavior:

```python
if "verified" not in result and "verified" in data:
    result["verified"] = data["verified"]

if "verification_note" not in result:
    note = data.get("verification_note")
    if note is None and data.get("verified") is False:
        note = data.get("message")
    if note is not None:
        result["verification_note"] = note
```

If chat-runner fallback fails, preserve the existing top-level-first behavior and fall back to nested data:

```python
verified = result.get("verified")
if verified is None and isinstance(result.get("data"), dict):
    verified = result["data"].get("verified")

verification_note = result.get("verification_note")
if verification_note is None and isinstance(result.get("data"), dict):
    verification_note = result["data"].get("verification_note") or result["data"].get("message")
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add mcp_server\tests\test_dispatcher_safety.py mcp_server\tests\test_chat_runner.py mcp_server\src\rook\agent\tool_dispatcher.py mcp_server\src\rook\agent\chat\chat_runner.py
git commit -m "test: preserve gh readiness metadata in agent paths"
```

---

### Task 6: Guard Remaining Non-Lifecycle Canvas Routes

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `docs/superpowers/audits/2026-05-14-gh-route-readiness-inventory.md`
- Test: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`

- [ ] **Step 1: Add guard tests for one read-only inspection and one additional mutation**

Add bridge wrapper methods only for routes being tested in this task. Use this pattern in `NativeGhBridgeRegistrar.cs`:

```csharp
internal static ApiResponse ErrorsForBridge(string requestJson)
{
    return Handler.GetErrors();
}

internal static ApiResponse CreatePanelForBridge(string requestJson)
{
    return Handler.CreatePanel(requestJson);
}
```

Then add tests:

```csharp
[Fact]
public void ErrorsForBridge_NotReady_ReturnsStructuredFailure()
{
    var result = NativeGhBridgeRegistrar.ErrorsForBridge("{}");

    AssertGrasshopperNotReady(result, "gh_errors");
}

[Fact]
public void CreatePanelForBridge_NotReady_ReturnsStructuredFailure()
{
    var result = NativeGhBridgeRegistrar.CreatePanelForBridge("{}");

    AssertGrasshopperNotReady(result, "gh_create_panel");
}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests" --no-restore
```

Expected before implementation: compile failure for missing wrappers or assertion failure because the handlers are not readiness guarded.

- [ ] **Step 3: Apply guards to read-only canvas inspection methods**

In `GrasshopperHandler.cs`, add this guard pattern at the start of each listed method:

```csharp
var notReady = EnsureGrasshopperReadyForEdit("OPERATION_NAME");
if (notReady != null)
    return notReady;

var gh = GetGrasshopper(createDocumentIfMissing: false);
if (!gh.Success)
    return GrasshopperNotReadyResponse("OPERATION_NAME", null, gh.Error);
```

Use these exact operation names:

| Method | Operation name |
| --- | --- |
| `GetSelection` | `gh_selection` |
| `GetValue` | `gh_get_value` |
| `GetConnections` | `gh_connections` |
| `GetComponent` | `gh_component` |
| `GetErrors` | `gh_errors` |
| `InspectOutput` | `gh_inspect_output` |
| `GetGroups` | `gh_groups` |
| `ExploreSelection` | `gh_explore_selection` |
| `ExploreCluster` | `gh_explore_cluster` |

Do not guard `GetStatus`, `GetDocumentInfo`, `GetCategories`, `SearchLibrary`, or `BatchComponentInfo` unless the implementation proves that a method touches the active canvas/document.

- [ ] **Step 4: Apply guards to remaining non-lifecycle mutation methods**

Use the same guard pattern with these exact operation names:

| Method | Operation name |
| --- | --- |
| `CreatePanel` | `gh_create_panel` |
| `CreateComponent` | `gh_create_component` |
| `SetScript` | `gh_set_script` |
| `ConfigureScriptParams` or local script-param method name | `gh_set_script_pins` |
| `DeleteObjects` | `gh_delete` |
| `SetPreview` | `gh_preview` |
| `MoveObjects` | `gh_move` |
| `CreateGroup` | `gh_group` |
| `ResizeGroup` | `gh_group_resize` |
| `CreateCluster` | `gh_cluster` |
| `DisconnectComponents` | `gh_disconnect` |
| `SetReference` | `gh_set_reference` |
| `ClearReference` | `gh_clear_reference` |
| `Solve` | `gh_solve` |
| `BakeOutput` | `gh_bake_output` |
| `Undo` | `gh_undo` |

Do not change `/gh/document/new`, `/gh/document/open`, `/gh/clear`, `/gh/canvas/focus`, `/gh/canvas/zoom`, or `/gh/canvas/image` in this task.

- [ ] **Step 5: Update the inventory with implementation status**

In `docs/superpowers/audits/2026-05-14-gh-route-readiness-inventory.md`, update the `Test coverage` column for each guarded route with one of:

```text
Guarded; representative managed test
Guarded; covered by route category test
Guarded; live harness coverage
Lifecycle review pending
Read-only no-ready-gate; no canvas side effects
```

- [ ] **Step 6: Run managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests" --no-restore
```

Expected: all `NativeGhBridgeRegistrarTests` pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src\Rook\Handlers\GrasshopperHandler.cs src\Rook\InternalBridge\NativeGhBridgeRegistrar.cs src\Rook.Tests\InternalBridge\NativeGhBridgeRegistrarTests.cs docs\superpowers\audits\2026-05-14-gh-route-readiness-inventory.md
git commit -m "fix: guard gh canvas inspection and mutation routes"
```

---

### Task 7: Lifecycle Route Review Checkpoint

**Files:**
- Modify: `docs/superpowers/audits/2026-05-14-gh-route-readiness-inventory.md`
- Modify only after review approval: `src/Rook/Handlers/GrasshopperHandler.cs`
- Test only after review approval: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`

- [ ] **Step 1: Classify lifecycle-adjacent routes in the audit**

Update the audit rows to this explicit classification unless reviewer feedback changes it:

```markdown
| `/gh/document/new` | Imperative lifecycle | No `ready_for_edit` precondition | May create a new active document | Response should include postcondition status when implemented |
| `/gh/document/open` | Imperative lifecycle | No `ready_for_edit` precondition | May open an active document | Response should include postcondition status when implemented |
| `/gh/clear` | Mutation | Requires `ready_for_edit` | Clears existing active document only | Must fail closed when no active document |
| `/gh/canvas/focus` | Canvas navigation | Requires active canvas/document and visible canvas | UI navigation only | Must not create document/canvas |
| `/gh/canvas/zoom` | Canvas navigation | Requires active canvas/document and visible canvas | UI navigation only | Must not create document/canvas |
| `/gh/canvas/image` | Read-only canvas inspection | Requires active canvas/document and visible canvas | Capture only | Must not create document/canvas |
```

- [ ] **Step 2: Stop for review before lifecycle behavior changes**

Post the updated audit rows for review. Do not change lifecycle route behavior until the reviewer confirms these classifications.

- [ ] **Step 3: If approved, guard `/gh/clear` as mutation**

In `GrasshopperHandler.ClearCanvas`, use:

```csharp
var notReady = EnsureGrasshopperReadyForEdit("gh_clear");
if (notReady != null)
    return notReady;

var gh = GetGrasshopper(createDocumentIfMissing: false);
if (!gh.Success)
    return GrasshopperNotReadyResponse("gh_clear", null, gh.Error);
```

- [ ] **Step 4: If approved, guard canvas navigation/inspection routes**

In `FocusCanvas`, `ZoomCanvas`, and `CaptureCanvasImage`, use the same pattern with:

```text
gh_canvas_focus
gh_canvas_zoom
gh_canvas_image
```

Do not add readiness guards to `NewDocument` or `OpenDocument`. They are lifecycle routes.

- [ ] **Step 5: Add postcondition notes for lifecycle routes**

If `NewDocument` and `OpenDocument` responses already include active document information, document that in the audit. If they do not, add a future-work row:

```markdown
Lifecycle enhancement deferred: add postcondition status payload to `/gh/document/new` and `/gh/document/open`.
```

Do not implement postcondition payload changes in this plan unless reviewers explicitly request them.

- [ ] **Step 6: Run managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests" --no-restore
```

Expected: tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add docs\superpowers\audits\2026-05-14-gh-route-readiness-inventory.md src\Rook\Handlers\GrasshopperHandler.cs src\Rook.Tests\InternalBridge\NativeGhBridgeRegistrarTests.cs
git commit -m "docs: classify gh lifecycle readiness routes"
```

If code changes were approved and included, use:

```powershell
git commit -m "fix: guard gh lifecycle-adjacent canvas routes"
```

---

### Task 8: Live Rhino Readiness Harness

**Files:**
- Create: `mcp_server/tools/gh_readiness_live_harness.py`

- [ ] **Step 1: Create the harness script**

Create `mcp_server/tools/gh_readiness_live_harness.py`:

```python
"""Live GH readiness boundary harness.

Run only against a local Rhino/Rook instance. This script does not open
Grasshopper for the user; it verifies response shapes for the current runtime
state.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


def call(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    with httpx.Client(timeout=30.0) as client:
        if method == "GET":
            response = client.get(url, params=payload or {})
        else:
            response = client.request(method, url, json=payload or {})
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"success": False, "error": response.text, "http_status": response.status_code}


def assert_not_ready(name: str, result: dict[str, Any]) -> None:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if result.get("success") is not False:
        raise AssertionError(f"{name}: expected success=false, got {result}")
    if data.get("error") != "grasshopper_not_ready":
        raise AssertionError(f"{name}: expected data.error=grasshopper_not_ready, got {result}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:9877")
    parser.add_argument(
        "--mode",
        choices=("gh-closed", "gh-open"),
        required=True,
        help="Expected Grasshopper runtime state before running this harness.",
    )
    args = parser.parse_args()

    status = call(args.base_url, "GET", "/gh/status")
    print("gh_status", json.dumps(status, indent=2))

    if args.mode == "gh-closed":
        if status.get("success") is not True:
            raise AssertionError(f"gh_status endpoint did not execute: {status}")
        data = status.get("data") if isinstance(status.get("data"), dict) else {}
        if data.get("ready_for_edit") is True:
            raise AssertionError("Expected GH to be not ready for gh-closed mode")

        checks = [
            ("gh_query", "GET", "/gh/query", None),
            ("gh_snapshot", "POST", "/gh/snapshot", {}),
            ("gh_edit", "POST", "/gh/edit", {"epoch": 0, "create": []}),
            ("gh_create_slider", "POST", "/gh/create-slider", {"nickname": "ReadinessProbe"}),
            ("gh_connect", "POST", "/gh/connect", {"source": "missing", "target": "missing"}),
            ("gh_set_value", "POST", "/gh/value", {"guid": "missing", "value": 1}),
        ]
        for name, method, path, payload in checks:
            result = call(args.base_url, method, path, payload)
            print(name, json.dumps(result, indent=2))
            assert_not_ready(name, result)
        return 0

    data = status.get("data") if isinstance(status.get("data"), dict) else {}
    if data.get("ready_for_edit") is not True:
        raise AssertionError("Expected GH to be ready for gh-open mode")

    snapshot = call(args.base_url, "POST", "/gh/snapshot", {})
    print("gh_snapshot", json.dumps(snapshot, indent=2))
    if snapshot.get("success") is not True:
        raise AssertionError(f"gh_snapshot failed while GH ready: {snapshot}")

    create_slider = call(
        args.base_url,
        "POST",
        "/gh/create-slider",
        {"nickname": "ReadinessProbe", "min": 0, "max": 10, "value": 5, "x": 100, "y": 100},
    )
    print("gh_create_slider", json.dumps(create_slider, indent=2))
    if create_slider.get("success") is not True:
        raise AssertionError(f"create-slider failed while GH ready: {create_slider}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
```

- [ ] **Step 2: Run static syntax check**

Run:

```powershell
python -m py_compile mcp_server/tools/gh_readiness_live_harness.py
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Document live commands in the audit**

Append this section to `docs/superpowers/audits/2026-05-14-gh-route-readiness-inventory.md`:

````markdown
## Live Harness Commands

With Rhino/Rook running and Grasshopper closed:

```powershell
python mcp_server/tools/gh_readiness_live_harness.py --base-url http://localhost:9877 --mode gh-closed
```

With Rhino/Rook running, Grasshopper open, and a blank GH document active:

```powershell
python mcp_server/tools/gh_readiness_live_harness.py --base-url http://localhost:9877 --mode gh-open
```
````

- [ ] **Step 4: Commit**

Run:

```powershell
git add mcp_server\tools\gh_readiness_live_harness.py docs\superpowers\audits\2026-05-14-gh-route-readiness-inventory.md
git commit -m "test: add gh readiness live harness"
```

---

### Task 9: Final Verification And Review Prep

**Files:**
- Read: all changed files

- [ ] **Step 1: Run focused Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_dispatcher_safety.py mcp_server/tests/test_chat_runner.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run managed bridge tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests" --no-restore
```

Expected: all selected tests pass.

- [ ] **Step 3: Build managed companion**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 --no-restore /p:RhinoPluginDir=C:\__rook_build_no_deploy__
```

Expected: build succeeds.

- [ ] **Step 4: Run the live harness where available**

With Rhino/Rook running and GH closed:

```powershell
python mcp_server/tools/gh_readiness_live_harness.py --base-url http://localhost:9877 --mode gh-closed
```

Expected: status executes, `/gh/query`, `gh_snapshot`, `gh_edit`, `/gh/create-slider`, `/gh/connect`, and `/gh/value` `POST` fail closed with `data.error: grasshopper_not_ready`.

With Rhino/Rook running, GH open, and a blank GH document active:

```powershell
python mcp_server/tools/gh_readiness_live_harness.py --base-url http://localhost:9877 --mode gh-open
```

Expected: status reports `ready_for_edit: true`; `gh_snapshot` succeeds; `/gh/create-slider` succeeds.

If Rhino is not available, record that live validation was not run. Do not claim the failure class is closed without live harness evidence.

- [ ] **Step 5: Inspect diff**

Run:

```powershell
git diff --stat codex/gh-edit-partial-failure-contract...HEAD
git status --short
```

Expected: only intended files changed and worktree is clean.

- [ ] **Step 6: Prepare review summary**

Include:

```markdown
Implemented:
- Registered route inventory from native route surface.
- `gh_query` removed from stale Python agent-facing surfaces.
- Representative legacy mutation routes fail closed when GH is not ready.
- Not-ready metadata preserved through agent paths.
- Live harness added for GH closed/open validation.

Verification:
- Python focused tests: <result>
- Managed bridge tests: <result>
- Managed build: <result>
- Live harness GH closed: <result or not run>
- Live harness GH open: <result or not run>

Residual:
- Lifecycle route postcondition payloads for `/gh/document/new` and `/gh/document/open` remain deferred unless implemented.
```
