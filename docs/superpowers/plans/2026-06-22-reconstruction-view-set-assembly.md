# Reconstruction View-Set Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a synchronous, off-UI, full-stack `assemble_view_set` op that builds a lineage-preserving `reconstruction_view_set` artifact from existing image artifacts — no job, ledger, provider, polling, or UI.

**Architecture:** MCP tool `rhino_2d_to_3d_assemble_view_set` → native `POST /reconstruction/2d-to-3d/view-sets` → P/Invoke bridge **off-UI arm** → `ReconstructionOpHandler.DispatchOffUi` → `IReconstructionViewSetAssembler` → `ArtifactStore.Create`. It mirrors the background-removal stack (PR #327) but uses the synchronous off-UI dispatch arm, not the async job arm.

**Tech Stack:** C# (.NET Framework companion, xUnit), C++ native (httplib route), Python MCP (pytest). Base: `origin/main` @ `0123f80a`. Worktree: `.worktrees/reconstruction-view-set`, branch `feature/reconstruction-view-set-assembly`.

**Spec:** `docs/superpowers/specs/2026-06-22-reconstruction-view-set-assembly-design.md` (read it; this plan implements it verbatim).

## Global Constraints

- Synchronous **off-UI only**: no async dispatcher, no job ledger, no provider call, no polling, no UI, no auto background-removal.
- Assembler must resolve source bytes through `ArtifactStore.GetBlobAbsolutePath(artifactId, role)` — **never** trust/concatenate `ArtifactFile.Path`. Unreadable blob = hard reject **before any write**.
- Slot vocabulary is **closed**: `front`, `left`, `right`, `back`, `top`, `three_quarter` (underscore, never hyphen) → file roles `view_<slot>`. Unknown slot = hard reject.
- Allowed source kinds (assembler-specific, more permissive than submit): `generated_image`, `imported_image`, `captured_viewport`, `preprocessed_image`.
- `slots_expected`: omitted ⇒ canonical four (`front`,`left`,`right`,`back`); explicit `[]` ⇒ hard reject. `slots_present` derived from accepted views only; `complete = slots_expected ⊆ slots_present`.
- `method`/`note`: optional JSON strings; non-string ⇒ hard reject (no coercion). `provenance`: optional JSON object only; array/scalar ⇒ hard reject; stored verbatim; omitted ⇒ omitted (never `null`).
- Sources are **never mutated**; the only write is the new artifact.
- Error envelope: existing `Fail(Failure(code,message,field,retryable), StatusFor)`. New codes `invalid_view_set`, `invalid_provenance` (both → 400); reuse `invalid_source_artifact` / `invalid_source_role`. `details.reason` discriminates sub-cases.
- MCP tool belongs to the **mutating** `reconstruction` tool group, **not** `reconstruction_readonly`.
- Verification = **full local deploy or fresh-native-copy** (never bare `-PayloadOnly` for native bits); Rhino closed/restarted; live smoke is the merge gate. **No panel-dark gate** (no UI).

---

## File Structure

**C# companion (`src/Rook/`):**
- `Services/Reconstruction/ReconstructionContracts.cs` — add `ViewSet` kind, `view_*` roles, slot vocabulary + slot→role map + assembly allowed-source-kinds. *(Task 2)*
- `Services/Reconstruction/ReconstructionViewSetRequest.cs` *(new)* — the **stable** request DTO (`ReconstructionViewSetRequest` + `ViewBinding` + `Empty`). *(Task 1 creates the record; Task 2 adds the `TryParse` parser body to the same file.)*
- `Services/Reconstruction/ReconstructionViewSetAssembler.cs` *(new)* — `IReconstructionViewSetAssembler`, `ReconstructionViewSetOutcome`, and a temporary `DefaultReconstructionViewSetAssembler`. *(Task 1)* The real `ReconstructionViewSetAssembler` impl replaces the default. *(Task 2)*
- `Handlers/ReconstructionOpHandler.cs` — `OpAssembleViewSet` const, **required** `IReconstructionViewSetAssembler` ctor param, `DispatchOffUi` route, `AssembleViewSet` method, `StatusFor` codes, success/error serialization. *(Task 1 wiring + spy; Task 3 real envelope.)*
- `InternalBridge/NativeGhBridgeRegistrar.cs` — off-UI case for the op + the composition site that constructs the handler. *(Task 1 wires a temporary default; Task 3 swaps in the real assembler.)*

**C++ native (`src/RookNative/`):**
- `Handlers/GrasshopperProxyHandler.{h,cpp}` — `HandleReconstructionAssembleViewSet`. *(Task 1)*
- `RookServer.cpp` — route registration + route-list entry. *(Task 1)*

**Python MCP (`mcp_server/`):**
- `src/rook/server.py` — tool def + dispatch case. *(Task 1)*
- `src/rook/agent/tool_dispatcher.py` — `BRIDGE_ROUTES` entry. *(Task 1)*
- `src/rook/agent/tool_groups.py` — add to `reconstruction` group. *(Task 1)*

**Tests:**
- `src/Rook.Tests/.../ReconstructionOpHandlerTests.cs` — dispatch invariants, envelope. *(Task 1, Task 3)*
- `src/Rook.Tests/.../ReconstructionViewSetAssemblerTests.cs` *(new)* — validation matrix. *(Task 2)*
- `src/Rook.Tests/.../ReconstructionViewSetRequestTests.cs` *(new)* — parser. *(Task 2)*
- `mcp_server/tests/test_reconstruction_mcp_tools.py` — tool registration/route/group. *(Task 1)*

---

## Task 1: Full-stack routing + off-UI invariant (no assembler logic)

Wire the op end-to-end with a **spy/interface seam** so routing and the off-UI invariant are provable before any domain logic exists. The handler depends on an `IReconstructionViewSetAssembler`; Task 1 ships the interface + a trivial default; Task 2 ships the real impl; Task 3 ships the real envelope.

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionViewSetRequest.cs` (stable `ReconstructionViewSetRequest` + `ViewBinding` + `Empty`; **no `TryParse` yet** — Task 2 adds it here)
- Create: `src/Rook/Services/Reconstruction/ReconstructionViewSetAssembler.cs` (interface + `ReconstructionViewSetOutcome` + temporary `DefaultReconstructionViewSetAssembler`)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` (off-UI case + handler construction)
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`, `.../GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `mcp_server/src/rook/server.py`, `.../agent/tool_dispatcher.py`, `.../agent/tool_groups.py`
- Test: `src/Rook.Tests/.../ReconstructionOpHandlerTests.cs` (locate the actual path; mirror existing reconstruction handler tests), `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`, `mcp_server/tests/test_reconstruction_mcp_tools.py`

**Interfaces:**
- Produces (consumed by Tasks 2 & 3):
  ```csharp
  public interface IReconstructionViewSetAssembler
  {
      // Pure synchronous artifact transform. Never writes to the job ledger.
      ReconstructionViewSetOutcome Assemble(ReconstructionViewSetRequest request);
  }

  // Result envelope. Defined in full here so the type is stable across Tasks 1-3.
  // Task 1: spy returns empty Views. Task 2: assembler populates Artifact + Views.
  // Task 3: handler serializes Views directly (no record change mid-plan).
  public sealed record ReconstructionViewSetOutcome(
      bool Success,
      Rook.Artifacts.Artifact? Artifact,
      System.Collections.Generic.IReadOnlyList<string> SlotsExpected,
      System.Collections.Generic.IReadOnlyList<string> SlotsPresent,
      bool Complete,
      // Per-view response rows: {slot, source_artifact_id, source_role, view_role, provenance?}
      System.Collections.Generic.IReadOnlyList<
          System.Collections.Generic.IReadOnlyDictionary<string, object?>> Views,
      ReconstructionFailure? Failure);
  ```
- `ReconstructionViewSetRequest` + `ViewBinding` + `Empty` are created **in this task** in their own file `ReconstructionViewSetRequest.cs` (the full, stable record — see Task 2's Interfaces for the exact shape; copy it verbatim, but **omit** the `TryParse` member, which Task 2 adds to the same file). This keeps the type defined once, in one file, with no mid-plan move.

- [ ] **Step 1: Write the failing handler invariant tests**

In `ReconstructionOpHandlerTests.cs`, add (mirror existing handler-test construction of `ReconstructionOpHandler` — find how the suite builds it with a catalog/manager/store; inject a spy assembler via the new ctor param added in Step 3):

```csharp
[Fact]
public void DispatchOffUi_AssembleViewSet_ReachesAssembler()
{
    var spy = new RecordingViewSetAssembler();   // test double implementing IReconstructionViewSetAssembler
    var handler = BuildHandler(assembler: spy);   // extend the test's builder to pass the assembler
    var body = """{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001"}]}""";

    var resp = handler.DispatchOffUi(body);

    Assert.True(spy.Called);
    Assert.Equal(200, resp.HttpStatus);   // spy returns success
}

[Fact]
public async Task DispatchAsync_AssembleViewSet_IsRejectedAsUnknown_NotAsync()
{
    var spy = new RecordingViewSetAssembler();
    var handler = BuildHandler(assembler: spy);
    var body = """{"op":"assemble_view_set","views":[]}""";

    var resp = await handler.DispatchAsync(body);

    // assemble_view_set is off-UI only; it must NOT be handled by the async dispatcher.
    Assert.False(spy.Called);
    Assert.Equal(400, resp.HttpStatus);
}
```

Add the test double in the test project:
```csharp
internal sealed class RecordingViewSetAssembler : IReconstructionViewSetAssembler
{
    public bool Called { get; private set; }
    public ReconstructionViewSetOutcome Assemble(ReconstructionViewSetRequest request)
    {
        Called = true;
        return new ReconstructionViewSetOutcome(
            true, null,
            new[] { "front", "left", "right", "back" },
            new[] { "front" }, false,
            System.Array.Empty<System.Collections.Generic.IReadOnlyDictionary<string, object?>>(),
            null);
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: FAIL — `IReconstructionViewSetAssembler`/`OpAssembleViewSet`/ctor param do not exist (compile error).

- [ ] **Step 3: Add the request record, interface, outcome, default, and handler wiring**

Create `ReconstructionViewSetRequest.cs` with the stable record + `ViewBinding` + `public static readonly ReconstructionViewSetRequest Empty = new(null, Array.Empty<ViewBinding>(), null, null);` (no `TryParse` yet).

Create `ReconstructionViewSetAssembler.cs` with: `IReconstructionViewSetAssembler`, `ReconstructionViewSetOutcome` (from Interfaces above), and a temporary `DefaultReconstructionViewSetAssembler` whose `Assemble` returns `new ReconstructionViewSetOutcome(false, null, Array.Empty<string>(), Array.Empty<string>(), false, Array.Empty<IReadOnlyDictionary<string,object?>>(), new ReconstructionFailure("execution_failed","View-set assembler not yet implemented.",false,null,new Dictionary<string,object?>()))`. Task 2 replaces this whole class with the real impl; Task 4 greps to confirm it's gone.

In `ReconstructionOpHandler.cs`:
1. Add constant after line 29: `public const string OpAssembleViewSet = "assemble_view_set";`
2. Add a **required** ctor param `IReconstructionViewSetAssembler viewSetAssembler` (place it before the optional `importClient` param) and field `_viewSetAssembler = viewSetAssembler ?? throw new ArgumentNullException(nameof(viewSetAssembler));`. **No `?? new Default…` fallback** — the dependency is explicit so the final branch cannot silently ship the stub.
3. Update **every** construction site: the composition root in `NativeGhBridgeRegistrar.cs` (Step 5a) and the test builder(s). In Task 1, the composition root passes `new DefaultReconstructionViewSetAssembler()`; Task 3 changes it to `new ReconstructionViewSetAssembler(store)`.
4. In the `DispatchOffUi` switch (line 112-124), add: `OpAssembleViewSet => AssembleViewSet(args, body),`
5. Add a placeholder `AssembleViewSet` method (Task 3 fills real parse + serialization):
```csharp
private ApiResponse AssembleViewSet(Dictionary<string, JsonElement> args, string? body)
{
    // Task 1: prove the seam. Real parse + full envelope land in Tasks 2/3.
    var outcome = _viewSetAssembler.Assemble(ReconstructionViewSetRequest.Empty);
    return outcome.Success
        ? Ok(new Dictionary<string, object?> { ["view_set_artifact_id"] = outcome.Artifact?.Id.ToString("D"), ["views"] = outcome.Views })
        : Fail(outcome.Failure!, StatusFor(outcome.Failure!));
}
```

- [ ] **Step 4: Run handler tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: PASS (spy reached via off-UI; async rejects).

- [ ] **Step 5: Wire the bridge off-UI arm + the composition site**

In `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`:
- **5a.** At the site where the Reconstruction `ReconstructionOpHandler` is constructed (the composition root — locate via `new ReconstructionOpHandler(` or the `RookSubsystemRoot.Instance.Reconstruction` factory), pass the new **required** assembler arg. In Task 1, pass `new DefaultReconstructionViewSetAssembler()`. (Task 3 changes this single line to `new ReconstructionViewSetAssembler(store)` using the same `ArtifactStore` the handler already receives.)
- **5b.** Add to the **off-UI** case group (the block at line 1854-1867, alongside `OpModels`/`OpListJobs`/`OpResult`/…):
```csharp
case ReconstructionOpHandler.OpAssembleViewSet:
```
(Do **not** add it to the async case group at 1840-1844 — that absence is the invariant, pinned by the source test in Step 8.)

- [ ] **Step 6: Add the native route + handler**

In `src/RookNative/Handlers/GrasshopperProxyHandler.h`, declare next to `HandleReconstructionRemoveBackground`:
```cpp
void HandleReconstructionAssembleViewSet(const httplib::Request& req, httplib::Response& res);
```
In `GrasshopperProxyHandler.cpp`, after `HandleReconstructionRemoveBackground` (line 1370-1373), add:
```cpp
void HandleReconstructionAssembleViewSet(const httplib::Request& req, httplib::Response& res)
{
    DispatchReconstructionOp(req, res, "assemble_view_set");
}
```
In `src/RookNative/RookServer.cpp`, after line 1085 add:
```cpp
    m_server->Post("/reconstruction/2d-to-3d/view-sets", Rook::Handlers::HandleReconstructionAssembleViewSet);
```
And add `"POST /reconstruction/2d-to-3d/view-sets",` to the route-list array near line 2140.

**No ABI bump.** The new op routes through the *existing* `ReconstructionDispatch` P/Invoke callback (`DispatchReconstructionOp` → `ForwardReconstructionDispatch` → the existing `InvokeReconstructionDispatchWithBody`). Do **not** change `BridgeAbiVersion`/`kGhBridgeAbiVersion` — they stay `16`, and `NativeReconstructionDispatchSourceTests.BridgeAbiVersion_IsBumpedOnBothSides` must keep passing unchanged.

- [ ] **Step 7: Add native route + off-UI invariant source-pin tests**

In `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`, add (mirroring `NativeRoute_BackgroundRemovals_DispatchesRemoveBackground` and the off-UI/async grouping tests already in this file):
```csharp
[Fact]
public void NativeRoute_ViewSets_DispatchesAssembleViewSet()
{
    var cpp = File.ReadAllText(Path.Combine(
        RepoRoot, "src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp"));
    Assert.Contains("DispatchReconstructionOp(req, res, \"assemble_view_set\")", cpp);

    var server = File.ReadAllText(Path.Combine(RepoRoot, "src", "RookNative", "RookServer.cpp"));
    Assert.Contains("/reconstruction/2d-to-3d/view-sets", server);
}

[Fact]
public void NativeBridge_RoutesAssembleViewSetThroughOffUiDispatch_NotAsync()
{
    var managed = File.ReadAllText(Path.Combine(
        RepoRoot, "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));
    var fn = ExtractFunction(managed, "int HandleReconstructionDispatch(");

    var offUiBoundary = fn.IndexOf("ExecuteOffUiApiResponseCallback", System.StringComparison.Ordinal);
    Assert.True(offUiBoundary >= 0, "Off-UI callback boundary not found.");

    var asyncBranch = fn.Substring(0, offUiBoundary);
    var offUiBranch = fn.Substring(offUiBoundary);

    // Off-UI only: present after the boundary, absent before it (the async branch).
    Assert.DoesNotContain("OpAssembleViewSet", asyncBranch);
    Assert.Contains("OpAssembleViewSet", offUiBranch);
}
```

- [ ] **Step 8: Run the native source-pin tests; verify native compiles**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests"` (proves route→op + off-UI-not-async from source). Then `cmd /c scripts\build-native.bat Release 14.44.35207` (route + handler compile).
Expected: source tests PASS; native build succeeds.

- [ ] **Step 9: Write the failing Python MCP tests**

In `mcp_server/tests/test_reconstruction_mcp_tools.py`, mirror the `remove_background` tests:
```python
@pytest.mark.asyncio
async def test_reconstruction_assemble_view_set_registered_and_requires_views():
    by_name = {t.name: t for t in await server.list_tools()}
    assert "rhino_2d_to_3d_assemble_view_set" in by_name
    tool = by_name["rhino_2d_to_3d_assemble_view_set"]
    assert "views" in tool.inputSchema["required"]

@pytest.mark.asyncio
async def test_reconstruction_assemble_view_set_dispatches_owned_route(monkeypatch):
    args = capture_call_rhino(monkeypatch)   # reuse the suite's existing capture helper
    args_in = {"views": [{"slot": "front", "artifact_id": "x"}]}
    await server.call_tool("rhino_2d_to_3d_assemble_view_set", args_in)
    assert args == ("/reconstruction/2d-to-3d/view-sets", "POST", args_in)

def test_reconstruction_assemble_view_set_bridge_route():
    assert tool_dispatcher.BRIDGE_ROUTES["rhino_2d_to_3d_assemble_view_set"] == (
        "/reconstruction/2d-to-3d/view-sets", "POST")

def test_reconstruction_assemble_view_set_is_mutating_group_only():
    from rook.agent import tool_groups
    assert "rhino_2d_to_3d_assemble_view_set" in tool_groups.TOOL_GROUPS["reconstruction"]
    assert "rhino_2d_to_3d_assemble_view_set" not in tool_groups.TOOL_GROUPS["reconstruction_readonly"]
```
(Match the exact helper/import names already used in this test file — adapt `capture_call_rhino`/`tool_groups` references to the file's conventions.)

- [ ] **Step 10: Run Python tests to verify they fail**

Run: `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`
Expected: FAIL (tool/route/group absent).

- [ ] **Step 11: Add the Python tool, dispatch, route, and group**

In `mcp_server/src/rook/server.py`, add a `Tool(...)` after the `rhino_2d_to_3d_remove_background` def (line 12717):
```python
        Tool(
            name="rhino_2d_to_3d_assemble_view_set",
            description=(
                "Assemble a reconstruction_view_set artifact from existing image "
                "artifacts (captured viewports, imported/generated images, or "
                "background-removed images). Synchronous artifact transform: no "
                "provider job, no polling. Copies each view into a view_<slot> file "
                "role, links parent_ids to the sources (never modified), and records "
                "slots_expected/slots_present/complete. Slots: front, left, right, "
                "back, top, three_quarter."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "views": {
                        "type": "array",
                        "description": "Slot bindings. Each: {slot, artifact_id, role?, provenance?}.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slot": {"type": "string", "description": "One of front,left,right,back,top,three_quarter."},
                                "artifact_id": {"type": "string", "description": "Source image artifact id."},
                                "role": {"type": "string", "description": "Source file role (default image)."},
                                "provenance": {"type": "object", "description": "Optional free-form provenance object stored verbatim."},
                            },
                            "required": ["slot", "artifact_id"],
                        },
                    },
                    "slots_expected": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional expected slots for completeness. Omitted defaults to front,left,right,back. Must not be empty.",
                    },
                    "method": {"type": "string", "description": "Optional assembly method label (default manual_assembly)."},
                    "note": {"type": "string", "description": "Optional free-form note."},
                    "port": {"type": "integer", "description": "Specific Rhino port to target."},
                },
                "required": ["views"],
            },
        ),
```
Add the dispatch case after `rhino_2d_to_3d_remove_background` (line 20221):
```python
        case "rhino_2d_to_3d_assemble_view_set":
            result = await call_rhino(
                "/reconstruction/2d-to-3d/view-sets", "POST", arguments, port=port
            )
```
In `mcp_server/src/rook/agent/tool_dispatcher.py`, add after line 478:
```python
    "rhino_2d_to_3d_assemble_view_set": ("/reconstruction/2d-to-3d/view-sets", "POST"),
```
In `mcp_server/src/rook/agent/tool_groups.py`, add `"rhino_2d_to_3d_assemble_view_set",` to the `reconstruction` list (after line 273) — **not** `reconstruction_readonly`.

- [ ] **Step 12: Run Python tests to verify they pass**

Run: `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`
Expected: PASS.

- [ ] **Step 13: Commit**

```bash
git add -A
git commit -m "feat(reconstruction): wire assemble_view_set off-UI op (routing + invariants, no logic)"
```

---

## Task 2: View-set assembler — contracts, request parser, validation matrix

Deliver the real domain logic: contract constants, the request parser, and `ReconstructionViewSetAssembler` with the full validation matrix, store-owned blob resolution, artifact creation, and metadata. **Delete** the temporary `DefaultReconstructionViewSetAssembler` and add `public sealed class ReconstructionViewSetAssembler : IReconstructionViewSetAssembler` in the same file.

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionContracts.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionViewSetRequest.cs` (add `TryParse` to the record created in Task 1 — do **not** re-declare the record)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionViewSetAssembler.cs` (delete the default; add the real impl)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionViewSetAssemblerTests.cs` *(new)*, `.../ReconstructionViewSetRequestTests.cs` *(new)*

**Validation ownership (parser vs assembler):** the **parser** owns structural/shape rejects that cannot exist on a typed DTO — empty `views`, explicit empty `slots_expected`, non-string `method`/`note`, non-object `provenance`, malformed `artifact_id`, missing `slot`. The **assembler** owns semantic/store rejects that *can* exist on a structurally-valid DTO — unknown slot, duplicate slot, unknown/duplicate slot in `slots_expected`, malformed role string, source kind not image-capable, role absent, blob unreadable — plus lineage/metadata/copied-bytes. (The assembler keeps a cheap defensive guard for empty `views`, but the *test* for it lives with the parser.)

**Interfaces:**
- Consumes: `IReconstructionViewSetAssembler`, `ReconstructionViewSetOutcome` (Task 1); `ArtifactStore.Create(string kind, IReadOnlyList<BlobInput> blobs, IReadOnlyList<Guid>? parentIds, IReadOnlyDictionary<string,JsonNode?>? metadata)`, `ArtifactStore.Get(Guid)`, `ArtifactStore.GetBlobAbsolutePath(Guid, string)`; `BlobInput(string Role, byte[] Content, string FileExtension)`.
- Produces:
  ```csharp
  public sealed record ReconstructionViewSetRequest(
      IReadOnlyList<string>? SlotsExpected,   // null = omitted (=> canonical four); empty = explicit (=> reject)
      IReadOnlyList<ViewBinding> Views,
      string? Method,
      string? Note)
  {
      public static readonly ReconstructionViewSetRequest Empty = new(null, Array.Empty<ViewBinding>(), null, null);
      // Parser entry point (Task 2):
      public static ReconstructionViewSetRequest? TryParse(string? body, out ReconstructionFailure? failure);
  }

  public sealed record ViewBinding(
      string Slot,
      Guid ArtifactId,
      string? Role,                  // null => "image"
      System.Text.Json.Nodes.JsonObject? Provenance);
  ```
- Contract constants added:
  ```csharp
  // ReconstructionArtifactKinds
  public const string ViewSet = "reconstruction_view_set";
  // ReconstructionFileRoles
  public const string ViewFront = "view_front"; // + ViewLeft/ViewRight/ViewBack/ViewTop/ViewThreeQuarter
  // New static class ReconstructionViewSlots:
  public static readonly IReadOnlyList<string> Canonical = new[] { "front", "left", "right", "back" };
  public static readonly IReadOnlySet<string> Allowed = new HashSet<string>(StringComparer.Ordinal)
      { "front","left","right","back","top","three_quarter" };
  public static string FileRole(string slot) => "view_" + slot;   // slot already validated
  public static readonly IReadOnlySet<string> AssemblySourceKinds = new HashSet<string>(StringComparer.Ordinal)
      { "generated_image","imported_image","captured_viewport","preprocessed_image" };
  ```

- [ ] **Step 1: Write failing parser tests**

`ReconstructionViewSetRequestTests.cs` — cover: valid full body parses (views, slots_expected, method, note, provenance object); `slots_expected` omitted ⇒ `SlotsExpected == null`; `slots_expected: []` ⇒ failure `invalid_view_set`/`empty_slots_expected`; non-string `method` ⇒ `invalid_view_set`/`non_string_method`; non-string `note` ⇒ `non_string_note`; provenance scalar ⇒ `invalid_provenance`/`provenance_not_object`; provenance array ⇒ `invalid_provenance`; missing `views` or empty ⇒ `invalid_view_set`/`empty_views`; non-guid `artifact_id` ⇒ `invalid_view_set`. Example:
```csharp
[Fact]
public void TryParse_ExplicitEmptySlotsExpected_Fails()
{
    var req = ReconstructionViewSetRequest.TryParse(
        """{"views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001"}],"slots_expected":[]}""",
        out var failure);
    Assert.Null(req);
    Assert.Equal("invalid_view_set", failure!.Code);
    Assert.Equal("empty_slots_expected", failure.Details["reason"]);
}
```

- [ ] **Step 2: Run to verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionViewSetRequestTests"`
Expected: FAIL (`TryParse` not implemented).

- [ ] **Step 3: Implement the parser**

Implement `ReconstructionViewSetRequest.TryParse` in `ReconstructionViewSetRequest.cs`: parse the JSON object; distinguish absent `slots_expected` (null) from present (must be a non-empty array of strings — reject `[]` and non-array); validate `views` is a non-empty array; per view read `slot` (string), `artifact_id` (parse Guid — reject malformed), optional `role` (string), optional `provenance` (must be `JsonObject`); validate `method`/`note` are strings if present. On any structural problem return null + a `ReconstructionFailure` with `Details["reason"]` set per the spec §6 table. Slot-vocabulary and source-artifact checks are **not** here — those are the assembler's job (Step 6) so the failure `field` can point at the slot.

- [ ] **Step 4: Run to verify pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionViewSetRequestTests"`
Expected: PASS.

- [ ] **Step 5: Write failing assembler tests**

`ReconstructionViewSetAssemblerTests.cs` — build a real `ArtifactStore` over a temp dir (mirror how other reconstruction tests construct a store + seed image artifacts; reuse their helper to create a `generated_image`/`preprocessed_image` artifact with an `image` role PNG blob). Cover the full matrix:
- Happy path (four valid views, no `slots_expected`) ⇒ `Success`, artifact kind `reconstruction_view_set`, four `view_<slot>` files with bytes copied, `parent_ids` = distinct sources, `SlotsExpected` = canonical four, `Complete == true`.
- Partial (front+left only) ⇒ `Complete == false`, `SlotsPresent == [front,left]`.
- `complete` formula with explicit `slots_expected` superset/subset.
- Provenance object (valid DTO `JsonObject`) ⇒ round-trips verbatim into metadata `views[]` **and** into `outcome.Views`; omitted ⇒ key absent (not null).
- `method` default `manual_assembly`; `note` omitted ⇒ absent.
- **Semantic/store hard rejects** (all from structurally-valid DTOs), each asserting **no artifact written** (store artifact count unchanged): duplicate slot; unknown slot; unknown/dup in `slots_expected`; malformed role string (`"BAD ROLE"`); source not found; source kind not image-capable (seed a `reconstruction_package` or other kind); role absent on artifact; source blob missing/unreadable (seed artifact then delete the blob file on disk so `GetBlobAbsolutePath`/`ReadAllBytes` throws).
- Six-slot set ⇒ six `view_<slot>` roles incl. `view_three_quarter`.
- Lineage: after assembly, each source artifact is **unchanged** (same kind/roles/files).

> **Not assembler tests** (the DTO types make them impossible — `method`/`note` are `string?`, `provenance` is `JsonObject?`, `slots_expected` empty/`views` empty are shape-level): non-string `method`/`note`, provenance scalar/array, explicit empty `slots_expected`, empty `views`. Those are **parser tests** (Step 1) and are additionally proven to serialize correctly at the handler in Task 3.

Example reject:
```csharp
[Fact]
public void Assemble_DuplicateSlot_RejectsAndWritesNothing()
{
    var store = NewStore(out var dir);
    var src = SeedImageArtifact(store, "generated_image");
    var before = CountArtifacts(store);
    var req = new ReconstructionViewSetRequest(null, new[]
    {
        new ViewBinding("front", src.Id, null, null),
        new ViewBinding("front", src.Id, null, null),
    }, null, null);

    var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

    Assert.False(outcome.Success);
    Assert.Equal("invalid_view_set", outcome.Failure!.Code);
    Assert.Equal("duplicate_slot", outcome.Failure.Details["reason"]);
    Assert.Equal(before, CountArtifacts(store));
}
```

- [ ] **Step 6: Run to verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionViewSetAssemblerTests"`
Expected: FAIL (real assembler not implemented).

- [ ] **Step 7: Implement the assembler**

Replace `DefaultReconstructionViewSetAssembler` with `public sealed class ReconstructionViewSetAssembler : IReconstructionViewSetAssembler` taking `ArtifactStore store` in its ctor. `Assemble(request)`:
1. Resolve `slotsExpected = request.SlotsExpected ?? ReconstructionViewSlots.Canonical`. (Parser already rejected explicit empty.)
2. Validate each expected slot ∈ `Allowed`, no duplicates (else `invalid_view_set`).
3. For each view, in order: validate `slot ∈ Allowed` (else `invalid_view_set`/`unknown_slot`, field=slot); detect duplicate slot across views (`invalid_view_set`/`duplicate_slot`); resolve `role = view.Role ?? "image"`; validate role matches `^[a-z0-9][a-z0-9_-]*$` (else `invalid_source_role`/`invalid_role_format`); `store.Get(view.ArtifactId)` — null ⇒ `invalid_source_artifact`/`source_not_found`; kind ∈ `AssemblySourceKinds` else `invalid_source_artifact`/`source_kind_not_image`; role present on `artifact.Files` else `invalid_source_role`/`role_not_present`.
4. Resolve bytes: `var path = store.GetBlobAbsolutePath(view.ArtifactId, role);` wrapped in try/catch → on any exception, `invalid_source_artifact`/`source_blob_unreadable` (field=slot). `var bytes = File.ReadAllBytes(path);` (also in the try). Derive `ext = Path.GetExtension(path).TrimStart('.')`.
5. Build `BlobInput(ReconstructionViewSlots.FileRole(slot), bytes, ext)` per accepted view.
6. Compute `slotsPresent` = distinct accepted slots (in canonical-then-insertion order is fine); `complete = slotsExpected.All(slotsPresent.Contains)`.
7. Build metadata `JsonObject`: `method` (request.Method ?? "manual_assembly"), `note` (only if present), `slots_expected`, `slots_present`, `complete`, `views` (array of `{slot, source_artifact_id, source_role, view_role, provenance?}` — provenance only when supplied, cloned).
8. `parentIds` = distinct `view.ArtifactId`.
9. `var artifact = store.Create(ReconstructionArtifactKinds.ViewSet, blobs, parentIds, metadata);`
10. Build `views` response rows (one `Dictionary<string,object?>` per accepted view: `slot`, `source_artifact_id` (`.ToString("D")`), `source_role`, `view_role`, and `provenance` only when supplied) and return `new ReconstructionViewSetOutcome(true, artifact, slotsExpected, slotsPresent, complete, views, null)`. (Reuse the same rows you wrote into metadata so response and metadata cannot drift.)
All hard rejects return `Success=false` **before** step 9 (no write). Use a private `Fail(code, message, field, reason)` helper that sets `Details["reason"]=reason`.

Also add contract constants to `ReconstructionContracts.cs` (the `ViewSet` kind, `view_*` roles, and the new `ReconstructionViewSlots` static class).

- [ ] **Step 8: Run to verify pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionViewSet"`
Expected: PASS (parser + assembler).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(reconstruction): view-set assembler — contracts, parser, validation matrix"
```

---

## Task 3: Handler envelope — wire real assembler, serialize result, StatusFor codes

Wire the real assembler into the handler, parse the request body, and serialize the outcome into the spec §6 success/error envelopes. Extend `StatusFor`.

**Files:**
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` (construct the handler with the real assembler — locate where `ReconstructionOpHandler`/the Reconstruction subsystem is built; pass `new ReconstructionViewSetAssembler(store)`).
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionViewSetRequest.TryParse`, `IReconstructionViewSetAssembler.Assemble`, `ReconstructionViewSetOutcome`.

- [ ] **Step 1: Write failing envelope tests**

Add to `ReconstructionOpHandlerTests.cs` (using a real `ReconstructionViewSetAssembler` over a seeded temp store, not the spy):
```csharp
[Fact]
public void AssembleViewSet_Success_ReturnsSpecEnvelope()
{
    var store = NewStore(); var a = SeedImageArtifact(store, "generated_image");
    var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
    var body = $$"""{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"{{a.Id:D}}"}]}""";

    var resp = handler.DispatchOffUi(body);

    Assert.Equal(200, resp.HttpStatus);
    var data = (IDictionary<string, object?>)resp.Data!;
    Assert.NotNull(data["view_set_artifact_id"]);
    Assert.Equal("reconstruction_view_set", data["kind"]);
    Assert.Equal(new[]{"front","left","right","back"}, ((IEnumerable<string>)data["slots_expected"]!).ToArray());
    Assert.Equal(new[]{"front"}, ((IEnumerable<string>)data["slots_present"]!).ToArray());
    Assert.Equal(false, data["complete"]);
    Assert.NotNull(data["views"]);
    Assert.NotNull(data["parent_ids"]);
    Assert.NotNull(data["warnings"]);
}

[Fact]
public void AssembleViewSet_UnknownSlot_Returns400WithReason()   // assembler-side reject
{
    var store = NewStore(); var a = SeedImageArtifact(store, "generated_image");
    var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
    var body = $$"""{"op":"assemble_view_set","views":[{"slot":"frnot","artifact_id":"{{a.Id:D}}"}]}""";

    var resp = handler.DispatchOffUi(body);

    Assert.Equal(400, resp.HttpStatus);
    var data = (IDictionary<string, object?>)resp.Data!;
    Assert.Equal("invalid_view_set", data["code"]);
}

[Fact]
public void AssembleViewSet_ParseFailure_SerializesEnvelope()   // parser-side reject must serialize correctly
{
    var store = NewStore(); var a = SeedImageArtifact(store, "generated_image");
    var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
    // provenance as an array is a parser-level structural reject (cannot exist on the typed DTO).
    var body = $$"""{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"{{a.Id:D}}","provenance":[]}]}""";

    var resp = handler.DispatchOffUi(body);

    Assert.Equal(400, resp.HttpStatus);
    var data = (IDictionary<string, object?>)resp.Data!;
    Assert.Equal("invalid_provenance", data["code"]);
    var details = (IReadOnlyDictionary<string, object?>)data["details"]!;
    Assert.Equal("provenance_not_object", details["reason"]);
}

[Fact]
public void AssembleViewSet_DoesNotWriteLedger()
{
    var store = NewStore(); var a = SeedImageArtifact(store, "generated_image");
    var ledgerProbe = ...; // assert the manager's ledger dir/record count is unchanged before/after
    var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
    handler.DispatchOffUi($$"""{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"{{a.Id:D}}"}]}""");
    // Assert no ledger record was written (use the suite's existing ledger inspection helper).
}
```
Add a test that `views[]` echoes `provenance` when supplied, and that `StatusFor(new Failure("invalid_provenance",...))` and `invalid_view_set` both return 400.

- [ ] **Step 2: Run to verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: FAIL (placeholder `AssembleViewSet` returns only `view_set_artifact_id`; `StatusFor` lacks new codes).

- [ ] **Step 3: Implement the real envelope + StatusFor codes**

In `ReconstructionOpHandler.cs`:
1. Extend `StatusFor` (line 1030-1033): add `invalid_view_set` and `invalid_provenance` to the `=> 400` arm.
2. Replace `AssembleViewSet`:
```csharp
private ApiResponse AssembleViewSet(Dictionary<string, JsonElement> args, string? body)
{
    var request = ReconstructionViewSetRequest.TryParse(body, out var parseFailure);
    if (request is null)
        return Fail(parseFailure!, StatusFor(parseFailure!));

    var outcome = _viewSetAssembler.Assemble(request);
    if (!outcome.Success)
        return Fail(outcome.Failure!, StatusFor(outcome.Failure!));

    var artifact = outcome.Artifact!;
    return Ok(new Dictionary<string, object?>
    {
        ["view_set_artifact_id"] = artifact.Id.ToString("D"),
        ["kind"] = artifact.Kind,
        ["slots_expected"] = outcome.SlotsExpected,
        ["slots_present"] = outcome.SlotsPresent,
        ["complete"] = outcome.Complete,
        ["parent_ids"] = artifact.ParentIds.Select(p => p.ToString("D")).ToArray(),
        ["views"] = outcome.Views,   // assembler-built rows; same source as the artifact metadata (no drift)
        ["warnings"] = Array.Empty<object>(),
    });
}
```
3. Construct the handler/subsystem with the real assembler (the `?? new Default...` fallback is replaced by an explicit `new ReconstructionViewSetAssembler(store)` at the composition root).

- [ ] **Step 4: Run to verify pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: PASS.

- [ ] **Step 5: Run the full C# reconstruction suite + whole suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Reconstruction"` then the full `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`.
Expected: all green (no regressions).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(reconstruction): assemble_view_set handler envelope + StatusFor codes"
```

---

## Task 4: Deploy + live smoke gate

Named verification gate. **Avoid the #327 native-staleness trap.**

**Files:** none (build/deploy/smoke only).

- [ ] **Step 1: Full green build of all suites + stub-escape gate**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` and `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`. Both green.
**Stub-escape gate (P2):** confirm the temporary default assembler is gone and not wired anywhere:
`git grep -n "DefaultReconstructionViewSetAssembler"` → **must return nothing**. (The composition root must construct `new ReconstructionViewSetAssembler(store)`; the required ctor param guarantees a missed swap is a compile error, and this grep guarantees the stub class itself is deleted.)

- [ ] **Step 2: Build native + managed (Rhino closed)**

Close Rhino and any `python -m rook`. Run `cmd /c scripts\build-native.bat Release 14.44.35207` and `dotnet build src/Rook/Rook.csproj -c Release` (its DeployToRhino target stages managed `Rook.rhp`).

- [ ] **Step 3: Deploy with fresh native (NOT bare -PayloadOnly)**

Per spec §9, use **one**:
1. Full deploy: `powershell -File scripts/deploy-local-testing.ps1` (Rhino + `python -m rook` closed), OR
2. `scripts/deploy-local-testing.ps1 -PayloadOnly -AllowRunning` for MCP/managed sync, **then** copy `src/RookNative/bin/Release/x64/RookNative.rhp` over `%APPDATA%\...\RookNative\RookNative.rhp`.
Confirm the deployed `.rhp` timestamp/size matches the fresh build.

- [ ] **Step 4: Restart Rhino + fresh MCP connection**

Launch Rhino (loads the new route). Restart Claude Code so the new `rhino_2d_to_3d_assemble_view_set` tool is callable.

- [ ] **Step 5: Live smoke (merge gate)**

Obtain/seed ≥2 image artifacts (e.g. a `captured_viewport` and a bg-removed `preprocessed_image`; list via `rhino_vision_artifacts`). Then:
1. `rhino_2d_to_3d_assemble_view_set(views=[{slot:front,artifact_id:A},{slot:left,artifact_id:B}])` (omit `slots_expected`). Assert: `reconstruction_view_set` artifact created; `parent_ids` link A and B; **A and B unchanged**; `view_front`/`view_left` roles present; `slots_expected==[front,left,right,back]`; `complete==false`; `views[]` shape correct (verify via `rhino_vision_get_artifact`).
2. A four-slot assembly ⇒ `complete==true`.
3. One reject (e.g. unknown slot) ⇒ 400 `invalid_view_set`.

- [ ] **Step 6: Finish the branch**

**REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch (verify tests, push, open PR non-squash, smoke marked passed).

---

## Self-Review Notes

- **Spec coverage:** §2 dispatch invariants → Task 1 (off-UI reach, async-absence, native route, group pin) + Task 2/3 (no-ledger). §3 request → Task 2 parser. §4 validation → Task 2 assembler matrix. §5 output + safe blob resolution → Task 2 (GetBlobAbsolutePath, copied `view_<slot>`, distinct parents, metadata). §6 response/error → Task 3 envelope + StatusFor. §8 tests → Tasks 1-3. §9 verification → Task 4 (fresh-native gate).
- **Type consistency:** `ReconstructionViewSetRequest` (+`ViewBinding`+`Empty`) lives in one file, created in Task 1; Task 2 only adds `TryParse` to it (no re-declaration). `ReconstructionViewSetOutcome` is defined in full in Task 1 (incl. `Views`), so no record changes mid-plan. `IReconstructionViewSetAssembler.Assemble(ReconstructionViewSetRequest) → ReconstructionViewSetOutcome` is stable across Tasks 1-3.
- **No hidden stub:** the handler ctor **requires** `IReconstructionViewSetAssembler` (no `??` fallback); the Task-1 `DefaultReconstructionViewSetAssembler` is an explicit, named, throwaway seam deleted in Task 2 and gated by `git grep` in Task 4 — it cannot silently ship.
- **Validation split:** parser owns shape-impossible-on-DTO rejects (empty views/slots_expected, non-string method/note, non-object provenance, malformed id); assembler owns semantic/store rejects; Task 3 proves a parser reject serializes at the handler.
- **Native pins are source assertions** (P4), not just compile: route→op and off-UI-not-async are checked in `NativeReconstructionDispatchSourceTests`. No ABI bump (existing dispatch callback).
