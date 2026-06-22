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
- Verified facts (do not re-guess): BiRefNet (`fal-ai/birefnet`) input field = **`image_url`**; output = **`image` (object, `.url`)** + optional **`mask_image` (object, `.url`)**.
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
- Modify: `mcp_server/src/rook/server.py` (MCP tool)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`, `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`, `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs` (or nearest existing), MCP tool-count test.

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

In `ReconstructionJobLedger.cs`: add `string Task` to the `ReconstructionJobLedgerRecord` record (place after `ModelId`). Bump `CurrentSchemaVersion` 2 → 3. Update the `Queued` factory to take `task` and set it; `Complete` factory sets `Task = string.Empty` (or carries the job's task if available — empty is fine, result-time reads the live record). In `Serialize`, write `"task"`. In `TryDeserialize`/`Merge`, read `"task"`; **when absent, default to `"single_image_to_3d"`** (legacy v2 back-compat). Update all in-repo constructions of the record (compiler will list them) to pass `task`.

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

- [ ] **Step 7: MCP tool**

In `mcp_server/src/rook/server.py`: add a `Tool(name="rhino_2d_to_3d_remove_background", description=..., inputSchema={source_artifact_id (required), source_role?, model_id?, port?})` near `rhino_2d_to_3d_submit`, and a routing case mapping it to `("/reconstruction/2d-to-3d/background-removals", "POST", arguments, port=port)`.

- [ ] **Step 8: Run tests — verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`
Expected: PASS (routing/contract/gate/ledger/MCP tests green; full suite stays green).

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat(reconstruction): remove_background op front door — async route + task-gated submit + ledger task"
```

---

### Task 2: Materialization branch — derived `preprocessed_image` (verify BiRefNet schema first)

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionPreprocessMaterializer.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (materialize branch on task)
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs` (or a sibling bg-removal mapper)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionPreprocessMaterializerTests.cs`

**Interfaces:**
- Consumes: the provider result envelope; `ArtifactStore`; `IReconstructionRemoteAssetDownloader`. Job's persisted `Task` (Task 1).
- Produces: a derived artifact `kind="preprocessed_image"`, `parent_ids=[source]`, roles `image`(+`mask`).

- [ ] **Step 1: Verify BiRefNet response schema (do not guess)**

Confirm against live fal docs (already verified 2026-06-22): `fal-ai/birefnet` returns `image` (object with `.url`) and optional `mask_image` (object with `.url`); input field `image_url`. Record these exact names; the mapper + tests key off them. If a re-check disagrees, update the field names here before coding.

- [ ] **Step 2: Write the failing materializer test**

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

- [ ] **Step 3: Implement the bg-removal result mapping + `ReconstructionPreprocessMaterializer`**

Map the BiRefNet envelope: `image.url` → role `image`; `mask_image.url` → role `mask` (when present). `ReconstructionPreprocessMaterializer.MaterializeAsync(jobId, sourceArtifactIds, provider, modelId, envelope, ct)` downloads those URLs and `_store.Create(kind: "preprocessed_image", blobs: [image(+mask)], parentIds: sourceArtifactIds, metadata: {provider, model_id, job_id})`. Return a result carrying the new artifact (mirror `ReconstructionMaterializeResult`, generalized to an artifact, not specifically a "package").

- [ ] **Step 4: Branch the manager poll-loop materialize on task**

At the `_materializer.MaterializeAsync` call site (`ReconstructionJobManager.PollActiveJobAsync`), branch on the job's `Task`: `remove_background` → `_preprocessMaterializer.MaterializeAsync(...)`; else → `_materializer.MaterializeAsync(...)` (3D package, unchanged). Set the completed record's `ResultArtifactId` from whichever artifact was produced. Inject the new materializer via the manager ctor + `RookSubsystemRoot.CreateReconstruction`.

- [ ] **Step 5: Run tests + commit**

Run the materializer tests + full suite (green). Commit: `feat(reconstruction): task-branched materialization — bg-removal -> linked preprocessed_image`.

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

### Task 4: Capability metadata (`input`/`prompt` + `source_field`) + provider field + `models` 3D-filter

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` (`Input`/`Prompt` types, `ModelToObj`, 3D-task filter)
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` (`SourceField` on request; `BuildSubmitPayload`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (pass `model.Input?.SourceField` into the provider request)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`models` op excludes non-3D tasks)
- Test: catalog + provider + models tests.

**Interfaces:**
- Produces: nullable `ReconstructionModelEntry.Input` (`Mode`, `SourceField`, `ViewSlots`, `Array`) + `.Prompt` (`Supported`, `Required`, `Kind`); `BuildSubmitPayload` keys the source URL on the resolved field; `models` op returns 3D-producing tasks only.

- [ ] **Step 1: Failing tests**

```csharp
[Fact] public void Catalog_InputPromptDescriptors_Deserialize() { /* birefnet source_field=="image_url"; meshy prompt.kind=="texture" */ }
[Fact] public void Catalog_AbsentBlocks_DefaultNull_NoThrow() { /* an entry w/o input/prompt deserializes */ }
[Fact] public void BuildSubmitPayload_UsesSourceField_Birefnet_ImageUrl() { /* SourceField="image_url" -> payload has image_url, not input_image_url */ }
[Fact] public void BuildSubmitPayload_DefaultsToInputImageUrl_WhenAbsent() { /* preserves Hunyuan path */ }
[Fact] public void ModelsOp_Excludes_RemoveBackgroundTasks() { /* models list has no birefnet */ }
```

- [ ] **Step 2: Catalog JSON + record types**

Add `input`/`prompt` blocks per the spec (Hunyuan: `input_image_url`, no prompt; Meshy: `input_image_url`, `prompt.kind:"texture"`; BiRefNet: `image_url`, no prompt). Add nullable `Input`/`Prompt` records (+ `ViewSlot`, `ArraySpec`) to `ReconstructionModelEntry`; emit them in `ModelToObj`.

- [ ] **Step 3: Provider source field**

Add `string? SourceField` to `ReconstructionProviderSubmitRequest`. `BuildSubmitPayload`: `payload[request.SourceField ?? "input_image_url"] = request.InputImageUrl.ToString();`. In `SubmitCoreAsync`, construct the request with `SourceField = model.Input?.SourceField`.

- [ ] **Step 4: `models` op 3D-task filter**

Filter the `models` projection to entries whose `Task` is a 3D-producing task (today `single_image_to_3d`; via a `static readonly HashSet<string> ThreeDTasks`). `remove_background` excluded.

- [ ] **Step 5: Run tests + commit**

Green; commit: `feat(reconstruction): capability metadata + source_field provider mapping; models 3D-only`.

---

### Task 5: Full local deploy + live smoke + finish

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` — all green. Also run the MCP test suite if present (`mcp_server` tests).

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

**Spec coverage:** routing/contract + async invariant + native route + MCP (Task 1); ledger `task` + legacy default + gated submit (Task 1); task-branched materialization → linked `preprocessed_image`, source untouched (Task 2); manager-owned typed result envelope, `package` 3D-only (Task 3); capability metadata + `source_field` provider mapping + `models` 3D-only (Task 4); full-local-deploy live smoke (Task 5). All spec sections covered.

**Pin coverage:** Task 1 IS the routing/contract task, before materializer (Task 2). Task 2 Step 1 verifies BiRefNet schema before coding the mapper, with tests keyed to the verified `image`/`mask_image` fields.

**Placeholder scan:** test bodies are described with exact assertions and the verified field names; native/MCP edits are exact one-liners mirroring `import_package`/`submit_job`. The larger refactors (SubmitCore extraction, ledger record field) state exact insertion points + behavior; implementers follow the compiler for call-site updates.

**Type/symbol consistency:** `OpRemoveBackground`, `SubmitRemoveBackgroundAsync`, `SubmitCoreAsync`, `ResolveRemoveBackgroundModel`, `ReconstructionPreprocessMaterializer`, envelope `ResultKind`/`AssetRoles`, request `SourceField`, catalog `Input`/`Prompt` are introduced once and referenced consistently across tasks. The native route string `/reconstruction/2d-to-3d/background-removals` and op string `remove_background` match across C#, native, MCP, and tests.
