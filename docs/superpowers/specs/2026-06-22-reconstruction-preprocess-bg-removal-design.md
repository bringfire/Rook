# Reconstruction: Capability Metadata + Explicit Background Removal — Design

**Date:** 2026-06-22
**Status:** Approved
**Base:** origin/main `f176b2dc`. Worktree `.worktrees/recon-preprocess-bg`, branch `feature/reconstruction-preprocess-bg-removal`.

## Goal

Lay the first backend foundation toward high-quality 2D→3D: (1) a **capability-metadata schema** on the catalog that a future UI can render input slots / prompt boxes from, and (2) an **explicit background-removal operation** that produces a derived artifact linked to its source — establishing the derived-artifact pattern that multi-view input generation will reuse. No new provider, no UI surfacing, no automatic preprocessing.

## Spine (approved)

Reuse the existing reconstruction **job pipeline internals** (submit → poll → result → ledger → cancel → materialize) for background removal, behind a **dedicated explicit op** — not the public 2D→3D submit. The job's behavior is discriminated by a persisted **catalog `task`**, and materialization branches on it.

## In scope

1. Capability-metadata schema (`input` + `prompt` descriptors) on catalog entries; populated for the three existing models. Control descriptors (topology/texture) **deferred**.
2. Persist the catalog **`task`** on the ledger record at submit (schema v2→v3).
3. Task-branched materialization: `single_image_to_3d` → current 3D package; `remove_background` → derived `preprocessed_image` artifact linked to source.
4. A dedicated explicit op **`remove_background`** that creates a ledger-backed job through the same manager/provider/poll/cancel machinery.
5. Typed result contract: bg-removal `job_result` returns `result_kind:"preprocessed_image"` + `result_artifact_id` + image-role metadata, with `package:null`. 3D results unchanged.

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
  "view_slots": [                      // present iff mode == multi_view_labeled
    { "role": "front", "field": "front_image_url", "required": true }
  ],
  "array": { "field": "image_urls", "min": 1, "max": 4 }   // present iff mode == multi_view_array
},
"prompt": { "supported": false, "required": false, "kind": null }  // kind: geometry | texture | segmentation | null
```

Populated for current entries:
- `fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d` → `input.mode:"single_image"`, `prompt.supported:false`.
- `fal-ai/meshy/v6/image-to-3d` → `input.mode:"single_image"`, `prompt:{supported:true, required:false, kind:"texture"}`.
- `fal-ai/birefnet` → `task:"remove_background"` (already), `input.mode:"single_image"`, `prompt.supported:false`.

Schema rules (validated by unit fixtures): `view_slots` present **iff** `mode == multi_view_labeled`; `array` present **iff** `mode == multi_view_array`; `prompt.required ⇒ prompt.supported`. The descriptors are **data, not behavior** in slice 1 — nothing reads `view_slots` yet; they exist so the future input-mapping layer and UI render from one source of truth. C# records gain nullable `Input`/`Prompt` properties so older catalog JSON (without the blocks) still deserializes.

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

`manager.Result(jobId)` and the handler's `Result` op branch on the job's `task`:
- 3D tasks → unchanged: `result_artifact_id`, `result_available`, `package` = `PackageSummary(...)`, `warnings`.
- `remove_background` → `result_artifact_id`, `result_available`, **`result_kind: "preprocessed_image"`**, image-role metadata (`asset_roles` of the derived artifact, e.g. `["image","mask"]`), and **`package: null`**. `PackageSummary` stays strictly 3D and is never built for non-3D jobs.

(3D results may also carry `result_kind: "reconstruction_package"` for symmetry, but `package` remains the load-bearing 3D field; adding `result_kind` to 3D results is optional and behavior-neutral.)

## 6. Op surface + dropdown isolation

- New op **`remove_background`** in `ReconstructionOpHandler` (async family, like `submit_job`): args `{ source_artifact_id, source_role?, model_id? }`; calls `manager.SubmitRemoveBackgroundAsync`; returns the job envelope (`job_id`, state). Status/result reuse the existing `job_status` / `job_result` ops (which now branch on task per §5). Cancel reuses `cancel_job`.
- Wire it through the same async dispatch surfaces as the other async ops (native bridge + VisionWebSurface async set, if/when exposed) — but in slice 1 it only needs the **MCP tool path** for the smoke. Expose a thin MCP tool (e.g. `rhino_2d_to_3d_remove_background` / `rhino_remove_background`) so the operation is callable for the smoke and by agents; no Reconstruct-tab button.
- **`models` op filtered to 3D-producing tasks.** The reconstruct model picker must never list bg-removal/preprocess models. The `models` op returns only entries whose `task` is a 3D-producing task (`single_image_to_3d`, future `multi_image_to_3d`/`text_to_3d`); `remove_background` entries are excluded from that list. The `remove_background` op resolves its model internally, so bg-removal models need not be discoverable through the reconstruct picker.

## Test strategy

**C# unit (xUnit, `dotnet test -c Debug`):**
- Catalog: `input`/`prompt` descriptors deserialize; schema-shape fixtures (labeled view_slots, array, text, prompt kinds) round-trip; absent blocks default to null without throwing.
- Ledger: `Task` round-trips at v3; a v2 record (no task) deserializes with `Task == "single_image_to_3d"`.
- Submit gate: `submit_job` / `SubmitAsync` still rejects a `remove_background` model (public surface stays 3D-only); `SubmitRemoveBackgroundAsync` rejects a `single_image_to_3d` model and accepts a `remove_background` model; both persist the correct `task`.
- Materialization: a `remove_background` job materializes a `preprocessed_image` artifact with `parent_ids=[source]` and roles `image`(+`mask`), and the source artifact is unchanged; a `single_image_to_3d` job still materializes a package.
- Result contract: bg-removal `job_result` → `result_kind:"preprocessed_image"`, `package` null, image roles; 3D `job_result` → `package` summary present, unchanged.
- `models` op excludes `remove_background` entries.
- MCP: the new tool registers (tool-count test).

**Live smoke (merge gate):** managed Release build/deploy; with Rhino open, call the bg-removal op on the falling-cat source (`866573ea…`). Verify: a new `preprocessed_image` artifact is created with `parent_ids` linking the source; the **original source artifact is untouched**; `job_result` returns `result_kind:"preprocessed_image"` with `package:null`; the Reconstruct dropdown still lists only 3D models. (The bg-removed image is inspectable via the artifact store / `rhino_vision_artifacts`.)

## Files touched (anticipated)

- `Fal/fal-model-catalog.json` — add `input`/`prompt` blocks to the 3 entries.
- `ReconstructionModelCatalog.cs` — `Input`/`Prompt` record types + properties; `ModelToObj` projection; 3D-task filter helper.
- `ReconstructionJobLedger.cs` — `Task` field, v3, legacy default, serialize/merge/deserialize.
- `ReconstructionJobManager.cs` — `SubmitCoreAsync`, `SubmitRemoveBackgroundAsync`, persist task, materialization branch, result branch.
- `ReconstructionPreprocessMaterializer.cs` (new) + bg-removal result mapping.
- `Handlers/ReconstructionOpHandler.cs` — `remove_background` op; `job_result` result-kind branch; `models` 3D-task filter.
- `mcp_server/...` — new MCP tool for the bg-removal op.
- Tests across the above.
