# Reconstruction: Capability Metadata + Explicit Background Removal — Design

**Date:** 2026-06-22
**Status:** Approved
**Base:** origin/main `f176b2dc`. Worktree `.worktrees/recon-preprocess-bg`, branch `feature/reconstruction-preprocess-bg-removal`.

## Goal

Lay the first backend foundation toward high-quality 2D→3D: (1) a **capability-metadata schema** on the catalog that a future UI can render input slots / prompt boxes from, and (2) an **explicit background-removal operation** that produces a derived artifact linked to its source — establishing the derived-artifact pattern that multi-view input generation will reuse. No new provider, no UI surfacing, no automatic preprocessing.

## Spine (approved)

Reuse the existing reconstruction **job pipeline internals** (submit → poll → result → ledger → cancel → materialize) for background removal, behind a **dedicated explicit op** — not the public 2D→3D submit. The job's behavior is discriminated by a persisted **catalog `task`**, and materialization branches on it.

## In scope

1. Capability-metadata schema (`input` — incl. single-image `source_field` — + `prompt` descriptors) on catalog entries; populated for the three existing models. Control descriptors (topology/texture) **deferred**.
2. Provider reads `source_field` at submit (replaces the hardcoded `input_image_url`; default preserves the Hunyuan path).
3. Persist the catalog **`task`** on the ledger record at submit (schema v2→v3).
4. Task-branched materialization: `single_image_to_3d` → current 3D package; `remove_background` → derived `preprocessed_image` artifact linked to source.
5. A dedicated explicit op **`remove_background`** spanning the full request path — **MCP tool → narrow native route → async bridge → handler → manager** — reusing the existing poll/cancel/ledger/materialize machinery (no duplication).
6. Typed result contract owned by the **manager result envelope** (`ResultKind`/`AssetRoles`), serialized by the handler: bg-removal → `result_kind:"preprocessed_image"` + `result_artifact_id` + image roles, `package:null`. 3D results gain an explicit `result_kind:"reconstruction_package"` but are otherwise unchanged.

## Out of scope (hard boundaries)

- No Replicate provider (different transport: version-hash pinning, separate file upload, per-model output schemas — a separate larger slice with no capability the fal catalog lacks yet).
- No multi-view **input-mapping layer**, no multi-view slot UI, no real multi-view catalog entries (schema shape validated by test fixtures only — no disabled/hidden "fake real" production entries).
- No novel-view generation (no verified geometrically-consistent hosted endpoint).
- No **automatic** preprocessing-on-submit; the public `submit_job` surface does **not** accept bg-removal models.
- No bg-removal **UI surfacing** in the Reconstruct tab (dropdown/`models` op stays 3D-producing-tasks only). Only the direct op/MCP/smoke path needed to prove it.
- No topology/texture control metadata; no quality-options work.

## Multi-view reuse — precise statement

The fal **transport/result** machinery is reusable for multi-view models later, but multi-view does **not** run through the current single-source request model. It will need a future input-mapping layer (multiple source artifacts, role→provider-field mapping like `front_image_url`, and labeled-slot-vs-array handling). Slice 1 builds **none** of that — it only defines the metadata *shape* (`input.mode`, `view_slots`, array spec) so that layer and its UI have a contract to read. The schema is validated with unit fixtures, not by shipping multi-view entries.

## 1. Capability-metadata schema

Extend `ReconstructionModelEntry` with two optional descriptor blocks (additive; existing fields unchanged):

```jsonc
"task": "single_image_to_3d",          // existing — the discriminator
"input": {
  "mode": "single_image",              // single_image | multi_view_labeled | multi_view_array | text
  "source_field": "input_image_url",   // present for single_image: the provider's source-image param name
  "view_slots": [                      // present iff mode == multi_view_labeled
    { "role": "front", "field": "front_image_url", "required": true }
  ],
  "array": { "field": "image_urls", "min": 1, "max": 4 }   // present iff mode == multi_view_array
},
"prompt": { "supported": false, "required": false, "kind": null }  // kind: geometry | texture | segmentation | null
```

**Single-image source field (load-bearing).** The fal provider currently hardcodes `["input_image_url"]` in `BuildSubmitPayload`, but **BiRefNet's API uses `image_url`** (and other models differ). So `input.source_field` carries the provider's source-image param name for `single_image` entries, parallel to the `field` that `view_slots` already carry. The provider reads it at submit instead of hardcoding. This makes single-image consistent with multi-view's per-field mapping and is what lets the bg-removal flow actually submit.

Populated for current entries:
- `fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d` → `input.mode:"single_image"`, `source_field:"input_image_url"` (unchanged behavior), `prompt.supported:false`.
- `fal-ai/meshy/v6/image-to-3d` → `input.mode:"single_image"`, `source_field:"input_image_url"` (keep current behavior; verify Meshy's true field in the plan and correct only if confirmed — do **not** regress the working path on an unverified change), `prompt:{supported:true, required:false, kind:"texture"}`.
- `fal-ai/birefnet/v2` → `task:"remove_background"` (already), `input.mode:"single_image"`, **`source_field:"image_url"`**, `prompt.supported:false`.

Provider behavior: `BuildSubmitPayload` writes `[sourceField] = url` where `sourceField` flows from the catalog entry's `input.source_field`. **Default = `"input_image_url"`** when a 3D entry omits it, so the proven Hunyuan path is byte-for-byte unchanged; BiRefNet overrides to `image_url`. `ReconstructionProviderSubmitRequest` carries the resolved `SourceField` (set by the manager from the model's catalog entry).

Schema rules (validated by unit fixtures): `view_slots` present **iff** `mode == multi_view_labeled`; `array` present **iff** `mode == multi_view_array`; `source_field` present for `single_image`; `prompt.required ⇒ prompt.supported`. The view/array descriptors are **data, not behavior** in slice 1 — nothing reads `view_slots` yet; they exist so the future input-mapping layer and UI render from one source of truth. `source_field` is the one input descriptor that **is** read in slice 1 (by the provider). C# records gain nullable `Input`/`Prompt` properties so older catalog JSON (without the blocks) still deserializes.

`ModelToObj` (the `models` op projection) emits `input` and `prompt` so a future UI can read them — but see §6: the `models` op is filtered to 3D-producing tasks, so bg-removal models still don't surface in the reconstruct picker.

## 2. Persist `task` on the ledger (v2 → v3)

`ReconstructionJobLedgerRecord` gains a `string Task` field. `CurrentSchemaVersion` 2 → 3. The `Queued` factory takes the normalized task (resolved from the catalog entry at submit). Legacy records (v2, no task) **default to `"single_image_to_3d"`** on deserialize — every existing job is a 3D reconstruction, so this is behavior-preserving and immunizes old jobs against future catalog edits. Serialization/`Merge`/`TryDeserialize` updated to round-trip `Task`.

## 3. Submit: shared core + two gated entries

Refactor `ReconstructionJobManager` so the submit machinery is shared and the **task gate** lives in the public entry:

- Extract the common path (source validate → fal CDN upload → provider submit → ledger append, persisting `task`) into a private `SubmitCoreAsync(request, model, task, ct)`.
- **`SubmitAsync`** (drives the public `submit_job`): keeps the existing `model.Task == "single_image_to_3d"` gate (`IsSubmittableV1Model`) and the `enable_pbr`/`enable_geometry` guard, then calls `SubmitCoreAsync(task: "single_image_to_3d")`. **Unchanged externally** — still rejects non-3D models.
- **`SubmitRemoveBackgroundAsync`** (drives the new `remove_background` op): resolves the bg-removal model (caller-supplied `model_id` must have `task == "remove_background"`, else default to the first enabled `remove_background` model in the catalog), validates the source, then calls `SubmitCoreAsync(task: "remove_background")`. Does **not** apply the pbr/geometry guard (irrelevant to bg-removal).

No duplication of poll/cancel/ledger code — both entries feed one pipeline.

## 4. Materialization branch (poll loop)

`PollActiveJobAsync` currently calls `_materializer.MaterializeAsync` (3D package). Branch on the job's persisted `task`:
- `single_image_to_3d` (and future 3D tasks) → `ReconstructionPackageMaterializer` (unchanged).
- `remove_background` → a new **`ReconstructionPreprocessMaterializer`**: from the provider result envelope (BiRefNet returns a bg-removed `image` + a `mask`), download the assets and persist a derived artifact:
  - `kind = "preprocessed_image"`,
  - `parent_ids = [sourceArtifactId]` (the link),
  - roles: `image` (the bg-removed result) and `mask` (when present),
  - the **source artifact is never modified**.

A task-specific result-mapping path (`FalReconstructionResultMapper` sibling, or a small bg-removal mapper) translates BiRefNet's response shape (image/mask URLs) into the role'd download set — analogous to how the 3D mapper handles `model_urls`.

## 5. Result contract (typed; no masquerade)

**Ownership (pinned):** the typed result metadata is owned by the **manager result envelope**, and `ReconstructionOpHandler` only *serializes* it — the handler does **not** re-infer the result kind from the artifact's roles or the catalog. `manager.Result(jobId)` (its `ReconstructionJobResult`/status-result type) gains:
- `ResultKind` — derived from the job's persisted `task` (`"reconstruction_package"` for 3D tasks, `"preprocessed_image"` for `remove_background`),
- `AssetRoles` — the derived artifact's roles (for non-3D results, e.g. `["image","mask"]`),
- and the existing `ResultArtifactId` / `ResultAvailable`.

The handler's `Result` op serializes by `ResultKind`:
- `reconstruction_package` → unchanged: `result_artifact_id`, `result_available`, `result_kind`, `package` = `PackageSummary(...)`, `warnings`. (`PackageSummary` is built here only because the envelope says it's a 3D package — not by guessing.)
- `preprocessed_image` → `result_artifact_id`, `result_available`, **`result_kind:"preprocessed_image"`**, `asset_roles` from the envelope, and **`package: null`**. `PackageSummary` is never built for non-3D jobs.

So `package` stays the load-bearing 3D field; `result_kind` is now an explicit, manager-owned discriminator present on every result (3D included), and the handler is a pure serializer over it.

## 6. Op surface — full request path (managed + native + MCP)

The smoke is MCP-driven, so the op must be reachable end to end: MCP tool → native HTTP route → `DispatchReconstructionOp` → companion bridge (async) → handler. The existing `POST /reconstruction/2d-to-3d/jobs` route **hard-dispatches `submit_job`** (`DispatchReconstructionOp(req, res, "submit_job")`), so it cannot serve a new op. This slice therefore spans **C# + native (`src/RookNative/`) + Python MCP**.

**Handler op.** New op constant `OpRemoveBackground = "remove_background"` in `ReconstructionOpHandler` (async family): args `{ source_artifact_id, source_role?, model_id? }`; calls `manager.SubmitRemoveBackgroundAsync`; returns the job envelope (`job_id`, state). Status/result reuse `job_status` / `job_result` (which branch on the manager's `ResultKind` per §5); cancel reuses `cancel_job`.

**Async-routing invariant (pinned, mirrors the import slice).** `remove_background` is an **async** reconstruction op:
- In `NativeGhBridgeRegistrar.HandleReconstructionDispatch`, add `case ReconstructionOpHandler.OpRemoveBackground:` to the **async branch** (`ExecuteAsyncApiResponseCallback`), exactly alongside `OpSubmit`.
- In the handler, `OpRemoveBackground` is in the async set and is **rejected by `DispatchOffUi`** (a structured `invalid_request`), so it can never run on a synchronous/off-UI path. A source-assertion test pins it in the async branch (as for `import_package`).

**Narrow native route.** Add `POST /reconstruction/2d-to-3d/background-removals` → a new `HandleReconstructionRemoveBackground` that calls `DispatchReconstructionOp(req, res, "remove_background")` (in `RookServer.cpp` route table + `GrasshopperProxyHandler.cpp` handler, + the route-listing/help block). A narrow, op-specific route — **not** a generic reconstruction-dispatch route.

**MCP tool.** New tool **`rhino_2d_to_3d_remove_background`** in `mcp_server/src/rook/server.py` (tool definition + routing case) → `POST /reconstruction/2d-to-3d/background-removals` with `{source_artifact_id, source_role?, model_id?}`. No Reconstruct-tab button (no UI surfacing this slice).

**`models` op filtered to 3D-producing tasks.** The reconstruct model picker must never list bg-removal/preprocess models. The `models` op returns only entries whose `task` is a 3D-producing task (today: `single_image_to_3d`; future `multi_image_to_3d`/`text_to_3d`); `remove_background` entries are excluded. The `remove_background` op resolves its model internally (optional `model_id` must have `task == "remove_background"`, else default to the first enabled `remove_background` entry), so bg-removal models need not be discoverable through the picker.

## Test strategy

**C# unit (xUnit, `dotnet test -c Debug`):**
- Catalog: `input`/`prompt` descriptors deserialize; schema-shape fixtures (labeled view_slots, array, text, prompt kinds, single-image `source_field`) round-trip; absent blocks default to null without throwing.
- Provider source field: `BuildSubmitPayload` writes the source URL under the request's `SourceField` (BiRefNet → `image_url`); a request with no source field defaults to `input_image_url` (Hunyuan path unchanged).
- Ledger: `Task` round-trips at v3; a v2 record (no task) deserializes with `Task == "single_image_to_3d"`.
- Submit gate: `submit_job` / `SubmitAsync` still rejects a `remove_background` model (public surface stays 3D-only); `SubmitRemoveBackgroundAsync` rejects a `single_image_to_3d` model and accepts a `remove_background` model; both persist the correct `task`.
- Materialization: a `remove_background` job materializes a `preprocessed_image` artifact with `parent_ids=[source]` and roles `image`(+`mask`), and the source artifact is unchanged; a `single_image_to_3d` job still materializes a package.
- Result envelope: the manager result carries `ResultKind`/`AssetRoles`; the handler serializes bg-removal → `result_kind:"preprocessed_image"`, `package` null, image roles; 3D → `result_kind:"reconstruction_package"`, `package` summary present, unchanged.
- `models` op excludes `remove_background` entries.
- Async routing: `OpRemoveBackground` is rejected by `DispatchOffUi` (structured `invalid_request`); a source-assertion test pins `OpRemoveBackground` in the async branch of `HandleReconstructionDispatch`.
- MCP: the new `rhino_2d_to_3d_remove_background` tool registers (tool-count test).

**Live smoke (merge gate) — full local deploy.** Because this crosses **C# companion + native route (`src/RookNative/`) + Python MCP tool**, the smoke must use the **full local deploy** (`scripts/deploy-local-testing.ps1`), not the lighter managed-only Release build — the native route and MCP tool won't be present otherwise (and recall the earlier MCP-front-door/`.mcp.json` shadowing pain). After deploy, with Rhino open, call `rhino_2d_to_3d_remove_background` on the falling-cat source (`866573ea…`). Verify: a new `preprocessed_image` artifact is created with `parent_ids` linking the source; the **original source artifact is untouched**; `rhino_2d_to_3d_result` returns `result_kind:"preprocessed_image"` with `package:null`; the Reconstruct dropdown (`models`) still lists only 3D models. (The bg-removed image is inspectable via `rhino_vision_artifacts`.)

## Files touched (anticipated)

**C#:**
- `Fal/fal-model-catalog.json` — `input` (incl. `source_field`) + `prompt` blocks on the 3 entries.
- `ReconstructionModelCatalog.cs` — `Input`/`Prompt` record types + properties; `ModelToObj` projection; 3D-task filter helper.
- `Fal/FalReconstructionProvider.cs` — `ReconstructionProviderSubmitRequest.SourceField`; `BuildSubmitPayload` uses it (default `input_image_url`).
- `ReconstructionJobLedger.cs` — `Task` field, v3, legacy default, serialize/merge/deserialize.
- `ReconstructionJobManager.cs` — `SubmitCoreAsync`, `SubmitRemoveBackgroundAsync`, persist task + source field, materialization branch, result envelope (`ResultKind`/`AssetRoles`).
- `ReconstructionPreprocessMaterializer.cs` (new) + bg-removal result mapping (BiRefNet image/mask).
- `Handlers/ReconstructionOpHandler.cs` — `OpRemoveBackground` op; `job_result` serializes by manager `ResultKind`; `models` 3D-task filter.
- `InternalBridge/NativeGhBridgeRegistrar.cs` — `OpRemoveBackground` in the async branch of `HandleReconstructionDispatch`.

**Native (`src/RookNative/`):**
- `RookServer.cpp` — `POST /reconstruction/2d-to-3d/background-removals` route + help/listing block.
- `Handlers/GrasshopperProxyHandler.cpp` — `HandleReconstructionRemoveBackground` → `DispatchReconstructionOp(req, res, "remove_background")`.

**Python MCP:**
- `mcp_server/src/rook/server.py` — `rhino_2d_to_3d_remove_background` tool definition + routing case.

**Tests** across the above (C# unit + native source-assertion + MCP tool-count).
