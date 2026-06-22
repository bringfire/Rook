# Reconstruction: Capability Metadata + Explicit Background Removal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a capability-metadata schema to the reconstruction catalog and an explicit `remove_background` operation that drives the existing job pipeline behind a persisted catalog `task`, materializing a derived `preprocessed_image` artifact linked to its source — never overwriting the source, never masquerading as a 3D package.

**Architecture:** Reuse the reconstruction job pipeline internals (submit→poll→result→ledger→cancel→materialize). A persisted `task` discriminates behavior; materialization and the result envelope branch on it. The op spans C# companion + native route (`src/RookNative/`) + Python MCP tool. No new provider, no UI, no auto-preprocessing.

**Tech Stack:** C# (.NET Framework net48, xUnit), C++ native (httplib routes), Python MCP (`server.py`).

## Global Constraints

- Base: origin/main `f176b2dc`. Worktree `.worktrees/recon-preprocess-bg`, branch `feature/reconstruction-preprocess-bg-removal`.
- Public `submit_job` / `SubmitAsync` stays **3D-only** (rejects `remove_background`). `models` op returns **3D-producing tasks only**.
- Background removal is **explicit** (dedicated op), **never auto-run** on reconstruction submit, and produces a derived `preprocessed_image` artifact with `parent_ids=[source]`; the **source is never modified**.
- Typed result metadata (`ResultKind`/`AssetRoles`) is **owned by the manager result envelope**; the handler only serializes it (never re-infers from artifacts). `PackageSummary` stays strictly 3D.
- `remove_background` is an **async** reconstruction op: in the async branch on both dispatch surfaces, **rejected by `DispatchOffUi`** (mirrors `import_package`).
- Persist the real catalog `task` string (`single_image_to_3d`, `remove_background`). Legacy v2 ledger records default to `single_image_to_3d`.
- Verified facts (do not re-guess): the verified BiRefNet endpoint is **`fal-ai/birefnet/v2`** (Task 2 switches the catalog id from `fal-ai/birefnet`): input field = **`image_url`**; output = **`image` (object, `.url`)** + optional **`mask_image` (object, `.url`)**.
- The new MCP tool must work through **both** the direct front door (`server.py`) **and** the agent path (`tool_groups.py` / `tool_dispatcher.py`); Python MCP tests (`pytest mcp_server/tests/...`) are run explicitly — `dotnet test` does not cover them.
- Out of scope: Replicate, multi-view input-mapping/UI, real multi-view catalog entries, novel-view, topology/texture control metadata, any Reconstruct-tab UI for bg-removal.
- C# tests: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`. Native source-assertion tests follow the repo's `RepoRoot`/`ExtractFunction` convention.

---

### Task 1: Routing & contract safety — the `remove_background` front door (no materializer yet)

Pins the right front door + no-deadlock invariant **before** any provider/materializer work: the op is async on both dispatch surfaces, rejected off-UI, reachable via a narrow native route and an MCP tool, and creates a **task-gated** ledger-backed job. Public `submit_job` stays 3D-only.

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs` (add `Task`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`SubmitCoreAsync`, `SubmitRemoveBackgroundAsync`, persist task)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`OpRemoveBackground` + dispatch)
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` (async branch)
- Modify: `src/RookNative/RookServer.cpp`, `src/RookNative/Handlers/GrasshopperProxyHandler.{h,cpp}` (native route)
- Modify: `mcp_server/src/rook/server.py` (MCP tool def + routing case)
- Modify: `mcp_server/src/rook/agent/tool_groups.py` + `mcp_server/src/rook/agent/tool_dispatcher.py` — **check/update** the `rhino_2d_to_3d_*` mappings so the new tool also works through the agent/tool-group path, not only direct MCP. (Grep these for `rhino_2d_to_3d_submit` and add `rhino_2d_to_3d_remove_background` to the same group/dispatch wherever the family is listed.)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`, `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`, `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs` (or nearest existing), MCP tool tests in `mcp_server/tests/test_reconstruction_mcp_tools.py`.

**Interfaces:**
- Produces: `ReconstructionOpHandler.OpRemoveBackground = "remove_background"`; `manager.SubmitRemoveBackgroundAsync(ReconstructionSubmitRequest, ct) → ReconstructionSubmitResult`; native route `POST /reconstruction/2d-to-3d/background-removals`; MCP tool `rhino_2d_to_3d_remove_background`.
- Consumes: existing `IsSubmittableV1Model`, the existing submit body of `SubmitAsync`, `DispatchReconstructionOp`, the `import_package` wiring as the template.

- [ ] **Step 1: Write the routing/contract tests first (they fail to compile/pass)**

Handler tests (`ReconstructionOpHandlerTests.cs`):
```csharp
[Fact]
public void RemoveBackground_OffUi_IsRejected()
{
    var fixture = CreateFixture();
    var body = $"{{\"op\":\"remove_background\",\"source_artifact_id\":\"{Guid.NewGuid():D}\"}}";
    var resp = fixture.Handler.DispatchOffUi(body);
    Assert.False(resp.Success);
    Assert.Equal(400, resp.HttpStatus);
    var data = Assert.IsType<Dictionary<string, object?>>(resp.Data);
    Assert.Equal("invalid_request", data["code"]);   // async op must not run off-UI
}
```

Native source-assertion (`NativeReconstructionDispatchSourceTests.cs`), mirroring the `import_package` test:
```csharp
[Fact]
public void NativeBridge_RoutesRemoveBackgroundThroughAsyncDispatch()
{
    var managed = ReadRepoFile("src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs");
    var fn = ExtractFunction(managed, "int HandleReconstructionDispatch(");
    var asyncBranch = fn.Substring(0, fn.IndexOf("ExecuteOffUiApiResponseCallback", StringComparison.Ordinal));
    Assert.Contains("OpRemoveBackground", asyncBranch);
}
```

Native route source-assertion (new small test or extend an existing native-source test):
```csharp
[Fact]
public void NativeRoute_BackgroundRemovals_DispatchesRemoveBackground()
{
    var cpp = ReadRepoFile("src/RookNative/Handlers/GrasshopperProxyHandler.cpp");
    Assert.Contains("DispatchReconstructionOp(req, res, \"remove_background\")", cpp);
    var server = ReadRepoFile("src/RookNative/RookServer.cpp");
    Assert.Contains("/reconstruction/2d-to-3d/background-removals", server);
}
```

Manager gate tests (`ReconstructionJobManagerTests.cs` or nearest):
```csharp
// public submit stays 3D-only
[Fact] public async Task SubmitAsync_RejectsRemoveBackgroundModel() { /* model=birefnet -> invalid_request */ }
// dedicated entry is remove_background-only and persists task
[Fact] public async Task SubmitRemoveBackgroundAsync_RejectsSingleImageModel() { /* model=hunyuan -> invalid_request */ }
[Fact] public async Task SubmitRemoveBackgroundAsync_AcceptsBirefnet_PersistsTask() {
    // fake provider; assert ledger record for the new job has Task == "remove_background"
}
```

Ledger task round-trip test (`ReconstructionJobLedgerTests.cs`):
```csharp
[Fact] public void Task_RoundTripsAtV3() { /* Append+read a record; Task preserved */ }
[Fact] public void LegacyV2Record_DefaultsTaskToSingleImageTo3d() {
    // hand-write a v2 JSON line without "task"; TryDeserialize -> Task == "single_image_to_3d"
}
```

MCP tool-count/registration test (mirror the existing reconstruction tool test): assert `rhino_2d_to_3d_remove_background` is registered.

- [ ] **Step 2: Run tests — verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~RemoveBackground|FullyQualifiedName~LegacyV2Record|FullyQualifiedName~Task_RoundTrips"`
Expected: FAIL (symbols/route/tool absent).

- [ ] **Step 3: Ledger `task` field (v2 → v3, legacy default)**

In `ReconstructionJobLedger.cs`: add `string Task` to the `ReconstructionJobLedgerRecord` record (place after `ModelId`). Bump `CurrentSchemaVersion` 2 → 3. Update the `Queued` factory to take `task` and set it. The **`Complete` factory must NOT set an empty task** — give it an optional parameter `string task = "single_image_to_3d"` and set `Task = task` (result-kind branches on task, and test-created completed records must carry a real task; never `""`). In `Serialize`, write `"task"`. In `TryDeserialize`/`Merge`, read `"task"`; **when absent, default to `"single_image_to_3d"`** (legacy v2 back-compat). Update all in-repo constructions of the record (compiler will list them) to pass `task`; the manager's completion path uses `materializing with { State = Complete, ... }` which already preserves the queued `Task`.

- [ ] **Step 4: Manager — `SubmitCoreAsync` + two task-gated entries**

In `ReconstructionJobManager.cs`:
- Extract the shared body of `SubmitAsync` (source validate → read bytes → publish to fal CDN → provider submit → ledger append) into `private async Task<ReconstructionSubmitResult> SubmitCoreAsync(ReconstructionSubmitRequest request, ReconstructionModelEntry model, string task, CancellationToken ct)`. It passes `task` to `ReconstructionJobLedgerRecord.Queued(...)`.
- `SubmitAsync` (public `submit_job`): keep `IsSubmittableV1Model` (3D gate) + the `enable_pbr`/`enable_geometry` guard, then `return await SubmitCoreAsync(request, model!, "single_image_to_3d", ct)`. **External behavior unchanged.**
- New `public async Task<ReconstructionSubmitResult> SubmitRemoveBackgroundAsync(ReconstructionSubmitRequest request, CancellationToken ct)`:
  ```csharp
  var model = ResolveRemoveBackgroundModel(request.ModelId);   // request model_id if task==remove_background, else first enabled remove_background entry
  if (model is null)
      return SubmitFail("invalid_request", "No background-removal model is available.", "model_id");
  // (no pbr/geometry guard — irrelevant to bg-removal)
  return await SubmitCoreAsync(request with { ModelId = model.ModelId }, model, "remove_background", ct);
  ```
  Add `IsSubmittableRemoveBackgroundModel(model)` (enabled + `Task == "remove_background"`) and `ResolveRemoveBackgroundModel`.

(Materialization is **not** branched yet — a remove_background job submitted here would fail at materialize. That is Task 2. Task 1 unit tests use the fake provider and assert submit + ledger only.)

- [ ] **Step 5: Handler op + async/off-UI wiring**

In `ReconstructionOpHandler.cs`: add `public const string OpRemoveBackground = "remove_background";`. In `DispatchAsync`'s switch add `OpRemoveBackground => await RemoveBackgroundAsync(body, cancellationToken).ConfigureAwait(false),`. In `DispatchOffUi`'s reject arm add `OpRemoveBackground`: `OpSubmit or OpStatus or OpCancel or OpImportPackage or OpRemoveBackground => Fail(Failure("invalid_request", "Operation must run on the UI dispatch path.", "op"), 400),`. Implement `RemoveBackgroundAsync(body, ct)`: parse `{source_artifact_id (required Guid), source_role?, model_id?}` into a `ReconstructionSubmitRequest` (empty options, empty preprocessing_chain), call `manager.SubmitRemoveBackgroundAsync`, return the job envelope (`job_id`, `state`) exactly like `SubmitAsync`'s success shape, or `Fail(...)` on the submit failure.

- [ ] **Step 6: Native async branch + route**

In `NativeGhBridgeRegistrar.cs` `HandleReconstructionDispatch`, add `case ReconstructionOpHandler.OpRemoveBackground:` to the **async** group (alongside `OpSubmit`/`OpStatus`/`OpCancel`/`OpImportPackage`).
In `src/RookNative/Handlers/GrasshopperProxyHandler.h`: declare `void HandleReconstructionRemoveBackground(const httplib::Request& req, httplib::Response& res);`.
In `GrasshopperProxyHandler.cpp`: implement `void HandleReconstructionRemoveBackground(const httplib::Request& req, httplib::Response& res) { DispatchReconstructionOp(req, res, "remove_background"); }`.
In `RookServer.cpp`: register `m_server->Post("/reconstruction/2d-to-3d/background-removals", Rook::Handlers::HandleReconstructionRemoveBackground);` (next to the other reconstruction routes) and add `"POST /reconstruction/2d-to-3d/background-removals"` to the route-listing/help block.

- [ ] **Step 7: MCP tool (server.py + agent tool-group path)**

In `mcp_server/src/rook/server.py`: add a `Tool(name="rhino_2d_to_3d_remove_background", description=..., inputSchema={source_artifact_id (required), source_role?, model_id?, port?})` near `rhino_2d_to_3d_submit`, and a routing case mapping it to `("/reconstruction/2d-to-3d/background-removals", "POST", arguments, port=port)`.
Then grep `mcp_server/src/rook/agent/tool_groups.py` and `mcp_server/src/rook/agent/tool_dispatcher.py` for `rhino_2d_to_3d_submit` and add `rhino_2d_to_3d_remove_background` to the **same group/dispatch mapping** wherever the `rhino_2d_to_3d_*` family is listed, so the tool also works through the agent/tool-group path (not only the direct MCP front door). If the family is referenced by prefix/pattern, confirm the new tool is matched and no allow-list addition is needed.

- [ ] **Step 8: Run tests — verify they pass (C# + Python MCP)**

Run C#: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` → PASS (routing/contract/gate/ledger tests green; full suite stays green).
Run Python MCP reconstruction tests explicitly (`dotnet test` does NOT cover these):
`python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`
Expected: PASS, including the new `rhino_2d_to_3d_remove_background` registration/mapping. (Extend that test file to assert the new tool is registered and maps to `/reconstruction/2d-to-3d/background-removals`.)

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat(reconstruction): remove_background op front door — async route + task-gated submit + ledger task"
```

---

### Task 2: Make bg-removal real & correct — schema verify, model id, source field, materializer

This task makes a `remove_background` job submit the **correct** payload and materialize a **linked derived image** — i.e. everything needed for a correct real submit, before the live smoke. It folds in the load-bearing `source_field` plumbing (Task 1 left the public submit path untouched and used a fake provider).

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json` (birefnet entry: model id + `source_field`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` (minimal `Input` record with `Mode`/`SourceField`; extended in Task 4)
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` (`SourceField` on request; `BuildSubmitPayload`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (pass `model.Input?.SourceField` into the provider request; materialize branch on task)
- Create: `src/Rook/Services/Reconstruction/ReconstructionPreprocessMaterializer.cs` (+ bg-removal result mapping)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionPreprocessMaterializerTests.cs`; provider source-field tests (nearest fal provider test file).

**Interfaces:**
- Consumes: the provider result envelope; `ArtifactStore`; `IReconstructionRemoteAssetDownloader`; job's persisted `Task` (Task 1).
- Produces: `ReconstructionProviderSubmitRequest.SourceField`; minimal `ReconstructionModelEntry.Input` (`Mode`, `SourceField`); a derived artifact `kind="preprocessed_image"`, `parent_ids=[source]`, roles `image`(+`mask`).

- [ ] **Step 1: Verify BiRefNet schema + pin the model id (do not guess)**

Verified against live fal docs (2026-06-22): the BiRefNet **v2** API page (`fal-ai/birefnet/v2`) documents input field `image_url` and output `image` (object, `.url`) + optional `mask_image` (object, `.url`, present when `output_mask`/`mask_only` requested). **Decision: switch the catalog model id `fal-ai/birefnet` → `fal-ai/birefnet/v2`** — it is the endpoint whose schema we verified (the bare `/birefnet` page did not expose a confirmed schema). Update the birefnet catalog entry's `model_id` accordingly and set `input.source_field: "image_url"`. If a re-check of the live page disagrees on field names, fix them here before coding the mapper.

- [ ] **Step 2: Source-field plumbing (provider keys on the resolved field)**

Tests first (nearest fal provider test file):
```csharp
[Fact] public void BuildSubmitPayload_UsesSourceField_WhenProvided() {
    // request.SourceField = "image_url" -> payload contains "image_url", not "input_image_url"
}
[Fact] public void BuildSubmitPayload_DefaultsToInputImageUrl_WhenNull() {
    // request.SourceField = null -> payload contains "input_image_url" (Hunyuan path unchanged)
}
```
Implement: add `string? SourceField` to `ReconstructionProviderSubmitRequest`; `BuildSubmitPayload` writes `payload[request.SourceField ?? "input_image_url"] = request.InputImageUrl.ToString();`. Add a minimal nullable `Input` record (`Mode`, `SourceField`) to `ReconstructionModelEntry` (Task 4 extends it with view_slots/array/prompt). In the catalog, set the birefnet entry `model_id: "fal-ai/birefnet/v2"`, `input: { "mode":"single_image", "source_field":"image_url" }`; give the two 3D entries `input.source_field: "input_image_url"` (behavior-preserving). In `SubmitCoreAsync`, construct the provider request with `SourceField = model.Input?.SourceField`. Run the provider tests → green.

- [ ] **Step 4: Write the failing materializer test**

```csharp
[Fact]
public async Task RemoveBackground_Materializes_LinkedPreprocessedImage_SourceUntouched()
{
    // fake downloader serves the bg-removed image (+ mask) bytes;
    // envelope models BiRefNet result: image.url, mask_image.url
    // assert: artifact.Kind == "preprocessed_image"; artifact.ParentIds == [sourceId];
    //         roles contain "image" (and "mask"); source artifact bytes/roles unchanged.
}
```

- [ ] **Step 5: Implement the bg-removal result mapping + `ReconstructionPreprocessMaterializer`**

Map the BiRefNet envelope: `image.url` → role `image`; `mask_image.url` → role `mask` (when present). `ReconstructionPreprocessMaterializer.MaterializeAsync(jobId, sourceArtifactIds, provider, modelId, envelope, ct)` downloads those URLs and `_store.Create(kind: "preprocessed_image", blobs: [image(+mask)], parentIds: sourceArtifactIds, metadata: {provider, model_id, job_id})`. Return a result carrying the new artifact (mirror `ReconstructionMaterializeResult`, generalized to an artifact, not specifically a "package").

- [ ] **Step 6: Branch the manager poll-loop materialize on task**

At the `_materializer.MaterializeAsync` call site (`ReconstructionJobManager.PollActiveJobAsync`), branch on the job's `Task`: `remove_background` → `_preprocessMaterializer.MaterializeAsync(...)`; else → `_materializer.MaterializeAsync(...)` (3D package, unchanged). Set the completed record's `ResultArtifactId` from whichever artifact was produced. Inject the new materializer via the manager ctor + `RookSubsystemRoot.CreateReconstruction`.

- [ ] **Step 7: Run tests + commit**

Run the provider source-field tests + materializer tests + full suite (green). Commit: `feat(reconstruction): bg-removal source_field (birefnet/v2) + task-branched materialization -> linked preprocessed_image`.

---

### Task 3: Typed result envelope (manager-owned `ResultKind`/`AssetRoles`)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`ReconstructionJobResultEnvelope` + `Result`)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`Result` op serializes by `ResultKind`)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Produces: envelope `ResultKind` (`"reconstruction_package"`|`"preprocessed_image"`) + `AssetRoles` (for non-3D). Handler `job_result` serializes: 3D → `package` + `result_kind`; bg-removal → `result_kind:"preprocessed_image"`, `asset_roles`, `package:null`.

- [ ] **Step 1: Failing tests**

```csharp
[Fact] public async Task Result_RemoveBackgroundJob_ResultKindPreprocessedImage_PackageNull() {
    // a completed remove_background job -> job_result data: result_kind == "preprocessed_image",
    // package == null, asset_roles contains "image"
}
[Fact] public async Task Result_ReconstructionJob_ResultKindPackage_Unchanged() {
    // existing 3D job -> result_kind == "reconstruction_package", package summary present
}
```

- [ ] **Step 2: Manager envelope carries the typed metadata**

Add `string ResultKind` and `IReadOnlyList<string> AssetRoles` to `ReconstructionJobResultEnvelope`. In `manager.Result(...)`, set `ResultKind` from the job's `Task` (3D family → `"reconstruction_package"`, `remove_background` → `"preprocessed_image"`) and `AssetRoles` from the result artifact's roles (for non-3D). The manager **decides**; the handler must not.

- [ ] **Step 3: Handler serializes by `ResultKind`**

In the `Result` op, branch on `envelope.ResultKind`: `reconstruction_package` → existing dict + `["result_kind"]="reconstruction_package"` + `["package"]=PackageSummary(...)`; `preprocessed_image` → `["result_kind"]="preprocessed_image"`, `["asset_roles"]=envelope.AssetRoles`, `["package"]=null`. `PackageSummary` is called **only** in the package arm.

- [ ] **Step 4: Run tests + commit**

Green; commit: `feat(reconstruction): manager-owned result_kind/asset_roles; handler serializes (package stays 3D-only)`.

---

### Task 4: Capability descriptors (`input` mode/slots + `prompt`) + `models` 3D-filter

(The load-bearing `source_field` + minimal `Input` record + `birefnet/v2` already landed in Task 2. This task adds the remaining **descriptive** metadata the future multi-view/prompt UI will read, and isolates the reconstruct picker.)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json` (`input.mode` + `prompt` blocks)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` (extend `Input` with `ViewSlots`/`Array`; add `Prompt` type; `ModelToObj`; 3D-task filter helper)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`models` op excludes non-3D tasks)
- Test: catalog + models tests.

**Interfaces:**
- Produces: `ReconstructionModelEntry.Input` extended (`ViewSlots`, `Array`) + `.Prompt` (`Supported`, `Required`, `Kind`); `ModelToObj` emits `input`/`prompt`; `models` op returns 3D-producing tasks only.

- [ ] **Step 1: Failing tests**

```csharp
[Fact] public void Catalog_PromptDescriptor_Deserializes() { /* meshy prompt.kind=="texture"; hunyuan prompt.supported==false */ }
[Fact] public void Catalog_InputMode_Deserializes() { /* all 3 entries input.mode=="single_image" */ }
[Fact] public void Catalog_AbsentBlocks_DefaultNull_NoThrow() { /* a fixture entry w/o input/prompt deserializes */ }
[Fact] public void Catalog_SchemaShape_Fixtures_RoundTrip() { /* synthetic multi_view_labeled (view_slots), multi_view_array (array), text fixtures round-trip; rules: view_slots iff labeled, array iff array */ }
[Fact] public void ModelsOp_Excludes_RemoveBackgroundTasks() { /* models list has no birefnet/v2 */ }
```

- [ ] **Step 2: Catalog JSON + record types**

Add `input.mode` to all 3 entries (`single_image`) and `prompt` blocks (Hunyuan: no prompt; Meshy: `{supported:true, required:false, kind:"texture"}`; BiRefNet: no prompt). Extend the `Input` record (from Task 2) with nullable `ViewSlots` (`[{role, field, required}]`) + `Array` (`{field, min, max}`); add the nullable `Prompt` record (`Supported`, `Required`, `Kind`). Emit `input`/`prompt` in `ModelToObj`. Multi-view/text shapes are exercised only by **synthetic test fixtures** — no multi-view entries are added to the production catalog.

- [ ] **Step 3: `models` op 3D-task filter**

Filter the `models` projection to entries whose `Task` is a 3D-producing task (today `single_image_to_3d`; via a `static readonly HashSet<string> ThreeDTasks`). `remove_background` excluded.

- [ ] **Step 4: Run tests + commit**

Green; commit: `feat(reconstruction): capability descriptors (input mode/slots + prompt); models 3D-only`.

---

### Task 5: Full local deploy + live smoke + finish

**Files:** none (verification only).

- [ ] **Step 1: Full suite (C# + Python MCP)**

Run C#: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` — all green.
Run Python MCP explicitly (`dotnet test` does NOT cover these): `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q` — green, incl. the new `rhino_2d_to_3d_remove_background`. (If the agent tool-group path has its own test, run that too.)

- [ ] **Step 2: Full local deploy (C# + native + MCP)**

Because this crosses native + MCP, use the **full local deploy** — `scripts/deploy-local-testing.ps1` (NOT managed-only). Mind the `.mcp.json` front-door shadow (move the repo dev `.mcp.json` aside so the installed RELEASE MCP with the new tool loads, then restore) per `[[project_deploy_bootstrap_venv_selfdelete.md]]`. Rhino closed for the deploy; native build needs VS Installer on PATH.

- [ ] **Step 3: Live smoke (merge gate)**

With Rhino open, `rhino_ping` → pong. Call `rhino_2d_to_3d_remove_background` on the falling-cat source (`866573ea-8767-45f2-9285-3ac6045cb03f`); poll `rhino_2d_to_3d_status`; on complete, `rhino_2d_to_3d_result`. Verify:
- a new `preprocessed_image` artifact exists (`rhino_vision_artifacts`) with `parent_ids` linking the source;
- the **original source artifact is unchanged** (still present, same roles);
- `result` returns `result_kind:"preprocessed_image"`, `package:null`, `asset_roles` incl. `image`;
- `rhino_2d_to_3d_models` still lists **only 3D models** (no BiRefNet).

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch — verify tests, push + open PR (non-squash; smoke marked passed), per user direction.

---

## Self-Review

**Spec coverage:** routing/contract + async invariant + native route + MCP (incl. agent tool-group path) + Python MCP tests (Task 1); ledger `task` + legacy default + non-empty `Complete` task + gated submit (Task 1); `source_field` provider mapping + `birefnet/v2` + task-branched materialization → linked `preprocessed_image`, source untouched (Task 2); manager-owned typed result envelope, `package` 3D-only (Task 3); remaining capability descriptors + `models` 3D-only (Task 4); full-local-deploy live smoke + explicit pytest (Task 5). All spec sections covered.

**Pin coverage:** Task 1 IS the routing/contract task, before materializer (Task 2). Task 2 Step 1 verifies BiRefNet schema before coding the mapper, with tests keyed to the verified `image`/`mask_image` fields.

**Placeholder scan:** test bodies are described with exact assertions and the verified field names; native/MCP edits are exact one-liners mirroring `import_package`/`submit_job`. The larger refactors (SubmitCore extraction, ledger record field) state exact insertion points + behavior; implementers follow the compiler for call-site updates.

**Type/symbol consistency:** `OpRemoveBackground`, `SubmitRemoveBackgroundAsync`, `SubmitCoreAsync`, `ResolveRemoveBackgroundModel`, `ReconstructionPreprocessMaterializer`, envelope `ResultKind`/`AssetRoles`, request `SourceField`, catalog `Input`/`Prompt` are introduced once and referenced consistently across tasks. The native route string `/reconstruction/2d-to-3d/background-removals` and op string `remove_background` match across C#, native, MCP, and tests.
