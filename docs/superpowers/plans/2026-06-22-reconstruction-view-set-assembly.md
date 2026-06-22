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
- `Services/Reconstruction/ReconstructionViewSetRequest.cs` *(new)* — request DTO + parser. *(Task 2)*
- `Services/Reconstruction/ReconstructionViewSetAssembler.cs` *(new)* — `IReconstructionViewSetAssembler` + impl: validation matrix, store-owned blob resolution, `ArtifactStore.Create`, result type. *(Task 1 introduces the interface + a pass-through default; Task 2 delivers the real impl.)*
- `Handlers/ReconstructionOpHandler.cs` — `OpAssembleViewSet` const, `DispatchOffUi` route, `AssembleViewSet` method, `StatusFor` codes, success/error serialization. *(Task 1 wiring + spy; Task 3 real envelope.)*
- `InternalBridge/NativeGhBridgeRegistrar.cs` — off-UI case for the op. *(Task 1)*

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
- Create: `src/Rook/Services/Reconstruction/ReconstructionViewSetAssembler.cs` (interface + minimal result type + a pass-through default impl)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`, `.../GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `mcp_server/src/rook/server.py`, `.../agent/tool_dispatcher.py`, `.../agent/tool_groups.py`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionOpHandlerTests.cs` (locate the actual path during execution; mirror existing reconstruction handler tests), `mcp_server/tests/test_reconstruction_mcp_tools.py`

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
- `ReconstructionViewSetRequest` is defined in Task 2; for Task 1 declare it as a minimal placeholder record in the same new file and expand in Task 2. To avoid a forward dependency, Task 1 defines the **full** request record (Task 2 only adds the *parser*). See the record in Task 2's Interfaces; copy it verbatim into Task 1's new file.

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

- [ ] **Step 3: Add the interface + outcome record + handler wiring**

Create `src/Rook/Services/Reconstruction/ReconstructionViewSetAssembler.cs` with: the `IReconstructionViewSetAssembler` interface, the `ReconstructionViewSetOutcome` record (from Interfaces above), the full `ReconstructionViewSetRequest` record + `ViewBinding` (copy from Task 2 Interfaces), and a `DefaultReconstructionViewSetAssembler` whose `Assemble` returns `new ReconstructionViewSetOutcome(false, null, Array.Empty<string>(), Array.Empty<string>(), false, new ReconstructionFailure("execution_failed","View-set assembler not yet implemented.",false,null,new Dictionary<string,object?>()))`. (Task 2 replaces this body with the real implementation; Task 1 only needs the type to exist and the seam to be wired.)

In `ReconstructionOpHandler.cs`:
1. Add constant after line 29: `public const string OpAssembleViewSet = "assemble_view_set";`
2. Add a ctor param `IReconstructionViewSetAssembler? viewSetAssembler = null` and field `_viewSetAssembler = viewSetAssembler ?? new DefaultReconstructionViewSetAssembler();` (keeps existing callers compiling).
3. In the `DispatchOffUi` switch (line 112-124), add: `OpAssembleViewSet => AssembleViewSet(args, body),`
4. Add a placeholder `AssembleViewSet` method (Task 3 fills serialization):
```csharp
private ApiResponse AssembleViewSet(Dictionary<string, JsonElement> args, string? body)
{
    // Task 1: prove the seam. Parsing + full envelope land in Tasks 2/3.
    var outcome = _viewSetAssembler.Assemble(ReconstructionViewSetRequest.Empty);
    return outcome.Success
        ? Ok(new Dictionary<string, object?> { ["view_set_artifact_id"] = outcome.Artifact?.Id.ToString("D"), ["views"] = outcome.Views })
        : Fail(outcome.Failure!, StatusFor(outcome.Failure!));
}
```
   Add `public static readonly ReconstructionViewSetRequest Empty = new(null, Array.Empty<ViewBinding>(), null, null);` to the request record so Task 1 compiles. Task 2/3 replace this call with a real parse of `body`.

- [ ] **Step 4: Run handler tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: PASS (spy reached via off-UI; async rejects).

- [ ] **Step 5: Wire the bridge off-UI arm**

In `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`, add to the **off-UI** case group (the block at line 1854-1867, alongside `OpModels`/`OpListJobs`/`OpResult`/…):
```csharp
case ReconstructionOpHandler.OpAssembleViewSet:
```
(Do **not** add it to the async case group at 1840-1844 — that absence is the invariant.)

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

- [ ] **Step 7: Verify native compiles**

Run: `cmd /c scripts\build-native.bat Release 14.44.35207`
Expected: build succeeds (route + handler compile).

- [ ] **Step 8: Write the failing Python MCP tests**

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

- [ ] **Step 9: Run Python tests to verify they fail**

Run: `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`
Expected: FAIL (tool/route/group absent).

- [ ] **Step 10: Add the Python tool, dispatch, route, and group**

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

- [ ] **Step 11: Run Python tests to verify they pass**

Run: `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat(reconstruction): wire assemble_view_set off-UI op (routing + invariants, no logic)"
```

---

## Task 2: View-set assembler — contracts, request parser, validation matrix

Deliver the real domain logic: contract constants, the request DTO + parser, and `ReconstructionViewSetAssembler` with the full validation matrix, store-owned blob resolution, artifact creation, and metadata. Replace `DefaultReconstructionViewSetAssembler`'s body with the real implementation (rename the class to `ReconstructionViewSetAssembler` implementing the interface).

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionContracts.cs`
- Create: `src/Rook/Services/Reconstruction/ReconstructionViewSetRequest.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionViewSetAssembler.cs` (real impl)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionViewSetAssemblerTests.cs` *(new)*, `.../ReconstructionViewSetRequestTests.cs` *(new)*

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
- Provenance object ⇒ round-trips verbatim into metadata `views[]`; omitted ⇒ key absent (not null).
- `method` default `manual_assembly`; `note` omitted ⇒ absent.
- Hard rejects, each asserting **no artifact written** (store artifact count unchanged): empty views; duplicate slot; unknown slot; explicit empty `slots_expected`; unknown/dup in `slots_expected`; malformed role string (`"BAD ROLE"`); source not found; source kind not image-capable (seed a `reconstruction_package` or other kind); role absent on artifact; source blob missing/unreadable (seed artifact then delete the blob file on disk, or stub a store that throws); non-string method/note (via parser, but also assert assembler surfaces them); provenance scalar/array.
- Six-slot set ⇒ six `view_<slot>` roles incl. `view_three_quarter`.
- Lineage: after assembly, each source artifact is **unchanged** (same kind/roles/files).

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
public void AssembleViewSet_UnknownSlot_Returns400WithReason()
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

- [ ] **Step 1: Full green build of all suites**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` and `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`. Both green.

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
- **Type consistency:** `IReconstructionViewSetAssembler.Assemble(ReconstructionViewSetRequest) → ReconstructionViewSetOutcome` is stable across Tasks 1-3. If Task 3 adds `Views` to the outcome record, update the record definition and the Task-1 spy in the same step.
- **No placeholders:** the Task-1 `Default...` assembler is an intentional, named, throwaway seam replaced wholesale in Task 2 — not a TODO.
