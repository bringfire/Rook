# Package → Hunyuan Smart Topology → new package (3D→3D slice 1)

- **Date:** 2026-06-24
- **Status:** Design approved; ready for implementation plan
- **Base:** `origin/main` @ `a4956779`
- **Scope:** managed (`src/Rook`) + MCP (`mcp_server`). No native geometry changes expected (verify the native reconstruction dispatch forwards the new op).
- **Capability family:** first slice of **3D→3D mesh processing** (priority order: Smart Topology → Segmentation/Parts → Remesh → Retexture). This slice = **package-to-Smart-Topology**.
- **Builds on:** the merged image→3D / PBR thread (#347 Meshy v6, #349/#351 material binding).

## Problem & goal

We have a durable `reconstruction_package` produced by image→3D (Meshy/Hunyuan). The next capability is 3D→3D mesh processing, starting with Hunyuan Smart Topology
(`fal-ai/hunyuan-3d/v3.1/smart-topology`): retopologize an existing mesh.

**Goal (v1):** a new operation that takes an existing `reconstruction_package` as its source,
runs Smart Topology against the package's GLB, and materializes the result as a **new**
`reconstruction_package` whose parent is the source package — importable through the existing
import path. KISS: **reuse** the existing submit/poll/materialize/import machinery; add only the
minimum package-mesh front door.

Flow: `reconstruction_package → upload local model_glb to fal → Smart Topology → new reconstruction_package → import`.

## Locked decisions

- **Always upload the package's durable local `model_glb` blob** (`model/gltf-binary`) and use the
  fresh upload URL as `input_file_url`. **No `provider_result_json` URL reuse** (no trustworthy
  freshness signal). **No HEAD/freshness probing.**
- **Preconditions (deterministic, source-side):** source is a `reconstruction_package`; it
  contains a `model_glb` blob; the blob is readable and non-empty. OBJ-only packages fail
  deterministically.
- **`input_file_type` is fixed to `"glb"`** (injected, not a user option).
- **New package only** — no destructive replace; import is the existing explicit op.
- **Rook-orchestrated chaining against public fal model endpoints** — NOT fal Workflow Endpoints
  (users bring their own fal keys; saved workflows under our account wouldn't be reliably
  accessible, and workflows weaken Rook-side job/package/debug lineage).
- **No fal Workflow `workflows/execute`** either (second execution abstraction, weaker lineage).

## Architecture (Approach 1 + T1)

Reuse the proven pipeline; add a package-mesh front that funnels into a shared, source-agnostic
tail. The image submit path is preserved except for extracting that tail.

```
MCP mesh-submit tool
  → op "submit_mesh_job" (async dispatcher)
     → ReconstructionMeshSubmitRequestParser            (new, strict)
     → mesh submit gate  (model must accept mesh input)  (new predicate)
     → options validation (existing ReconstructionOptionsValidator)
     → ReconstructionMeshSourceValidator                 (new, deterministic, PRE-ledger)
     → create job + ledger Queued/Submitting             (SourceArtifactId=pkg, SourceRole="model_glb")
     → read model_glb bytes + upload via existing publisher (POST-ledger; failure = recorded failed job)
     → SubmitResolvedAsync(...)  ── shared tail ──────────┐
                                                          │ (image path also calls this)
  provider.SubmitAsync → ledger Polling → background poll → materialize (ParentIds = [sourcePackageId])
  → existing import_package (unchanged)
```

### Op + parser contract

New async op `submit_mesh_job` (routes through the async dispatcher like `submit_job`; network
upload + provider submit). New `ReconstructionMeshSubmitRequestParser` → strict, field-named
`invalid_request` failures, producing:

```csharp
public sealed record ReconstructionMeshSubmitRequest
{
    public required Guid   SourcePackageId        { get; init; }  // "source_package_id" (required GUID)
    public required string ModelId                { get; init; }  // "model_id" (required, non-empty; NO default resolution)
    public JsonObject      Options                { get; init; } = new();  // "options" (optional; MUST be a JSON object — arrays/scalars rejected)
    public bool            AllowExperimentalModel { get; init; }           // "allow_experimental_model" (optional, strict bool; only meaningful with explicit model_id)
}
```

- `source_package_id` is **distinct** from `submit_job`'s `source_artifact_id` — no image-path overloading.
- `model_id` is **required with no default resolution** (keeps `allow_experimental_model` narrow;
  prevents "default image model" bleed-through).
- `allow_experimental_model` keeps the #347 strict-bool semantics.

### Source-front-specific submit gates (both directions)

`IsSubmittable3DModel` (enabled + status/experimental + has 3D output role + has input) is too
broad now that image and mesh models both output `model_glb`. Add **input-kind-specific gates**
composed from the base, and route each front to its own:

```csharp
// image front (submit_job) — unchanged behavior for all existing image models:
static bool IsSubmittableImageModel(ReconstructionModelEntry? m, bool allowExperimental)
    => IsSubmittable3DModel(m, allowExperimental)
       && m!.InputTypes.Contains("image_url", StringComparer.Ordinal);

// mesh front (submit_mesh_job):
static bool IsSubmittableMeshModel(ReconstructionModelEntry? m, bool allowExperimental)
    => IsSubmittable3DModel(m, allowExperimental)
       && (m!.InputTypes.Contains("model_url", StringComparer.Ordinal)
           || string.Equals(m.Input?.Mode, "single_model", StringComparison.Ordinal));
```

- `submit_job` switches from `IsSubmittable3DModel` to `IsSubmittableImageModel` — behavior-preserving for
  every existing image model (all have `image_url` input), and it now **rejects** the Smart Topology
  model (so an image submit can't upload an image URL into a mesh model).
- `submit_mesh_job` uses `IsSubmittableMeshModel` — **rejects** image→3D models (so a mesh submit can't
  accept Meshy/Hunyuan image models on their shared `model_glb` output).
- The same image-input predicate filters the image Reconstruct picker (`Models` op /
  `ProducesImportable3D`) so Smart Topology doesn't surface as an image→3D option. No mesh listing UI in v1.

### Mesh source validation (deterministic, pre-ledger)

New `ReconstructionMeshSourceValidator` — the mesh analog of the image `ReconstructionSourceValidator`,
deterministic and network-free:

```csharp
public sealed record ReconstructionMeshSourceValidationResult(
    string? ModelGlbAbsolutePath,
    Guid SourcePackageId,
    ReconstructionFailure? Failure);
```

Checks (typed **source-side** failures, fail-closed before any ledger record):
- `store.Get(id)` null / `Kind != reconstruction_package` → `invalid_source_package`
- no `model_glb` file role → `missing_model_glb`
- `model_glb` blob missing / unreadable / **empty** → `invalid_source_package` ("model_glb blob is empty or unreadable")

### Shared tail (source-agnostic — the long-term Remesh/Retexture seam)

Extract the post-publish back-end of `SubmitCoreAsync` into a shared method. It receives
**already-resolved provider inputs** + lineage and knows nothing about their origin:

```csharp
private async Task<ReconstructionSubmitResult> SubmitResolvedAsync(
    Guid jobId,
    ReconstructionModelEntry model,
    JsonObject validatedOptions,
    IReadOnlyList<ReconstructionProviderViewUrl> providerInputs,  // existing type reused; mesh: [("input_file_url", glbUrl)]
    IReadOnlyList<Guid> sourceArtifactIds,                        // lineage parents; mesh: [sourcePackageId]
    CancellationToken ct);
```

Behavior (verbatim from today's image back-end): build
`ReconstructionProviderSubmitRequest(model.ModelId, providerInputs, validatedOptions)` →
`provider.SubmitAsync` → ledger `Polling` → stash `sourceArtifactIds` → start the existing
background poll loop → materialize (sets `package.ParentIds = sourceArtifactIds`). `BuildSubmitPayload`,
the provider, the result mapper, the materializer, reconcile, and import are **untouched**.

**T1 split:** each source front creates its job and appends `Queued`/`Submitting` *before* calling
`SubmitResolvedAsync`; the tail starts at provider submit. The image path keeps its
resolve→validate→publish→job-create flow unchanged and simply calls the tail where it used to inline
the submit+poll. The only non-shared piece is the trivial ledger-start, which legitimately records
source identity per front.

### Ledger source semantics (explicit)

The mesh queued record sets:
- `SourceArtifactId = sourcePackageId`
- `SourceRole = "model_glb"` (the source artifact is the package; the consumed blob role is the GLB)

(Image jobs continue to record `SourceRole = "image"`.) Package-level UI wording can be added later
via optional metadata; ledger semantics are explicit, not implicit.

### Upload + error-handling parity (your caution, explicit)

The mesh front reads the `model_glb` bytes and uploads via the **existing**
`IReconstructionSourceImagePublisher.PublishAsync(bytes, "model/gltf-binary", fileName, ct)` (reused
as-is for v1 — not renamed despite the name). This happens **after** job creation, so:

- **Deterministic source preconditions** (wrong kind, missing `model_glb`, unreadable/empty blob,
  invalid request/options) → **fail before any ledger record** (no orphan job).
- **Upload failure** (missing credential / network / fal upload) → **recorded as a failed job**,
  identical to the image path (which appends `Submitting` before publishing). No divergence.
- The shared upload-failure message must be made **source-neutral** — change "source image upload"
  wording to "source file upload" (or similar) so a mesh upload failure isn't recorded with
  misleading image-specific text.

### `input_file_type` injection

`input_file_type` is **not** a catalog option. The mesh front injects `options["input_file_type"] = "glb"`
**after** `ReconstructionOptionsValidator` runs, so it reaches `BuildSubmitPayload` unchanged and can't be
set to a bad value. Because the options validator already **rejects unknown options**, a user-supplied
`input_file_type` fails cleanly (`invalid_request`) before injection.

## Catalog entry

Add to `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`:

```json
{
  "model_id": "fal-ai/hunyuan-3d/v3.1/smart-topology",
  "provider": "fal", "task": "mesh_to_mesh_topology", "status": "experimental", "enabled": true,
  "pipeline_roles": ["mesh_to_mesh"], "input_types": ["model_url"],
  "output_roles": ["model_glb"], "preferred_asset_role": "model_glb", "fallback_order": ["model_glb"],
  "supports_pbr": false, "default_texture_expected": false,
  "input": { "mode": "single_model", "source_field": "input_file_url" },
  "prompt": { "supported": false, "required": false, "kind": null },
  "preprocessing": { "recommended": false, "required": false },
  "options": [
    { "key": "polygon_type", "label": "Polygon Type", "kind": "enum", "default": "triangle", "allowed_values": ["triangle", "quadrilateral"] },
    { "key": "face_level",   "label": "Face Level",   "kind": "enum", "default": "medium",   "allowed_values": ["high", "medium", "low"] }
  ]
}
```

- `status: experimental` → ships behind `allow_experimental_model`; promote to `stable` after the live
  smoke (Meshy v6 pattern).
- `input_types: ["model_url"]` + `input.mode: "single_model"` drive the mesh submit gate and keep it
  out of the image picker.
- Options exactly `polygon_type` + `face_level`, validated by the existing enum-kind validator.

## Reuse (unchanged components)

- **Provider payload** — `BuildSubmitPayload` writes `field → url` then merges options; `input_file_url`
  + injected `input_file_type` + the two options land correctly. No change.
- **Result mapper** — `FalReconstructionResultMapper` already maps top-level `model_glb` and
  `model_urls.glb`. Smart Topology output (`model_glb` + `model_urls`) maps cleanly. No change.
- **Materializer** — requires `model_glb`/`model_obj`; Smart Topology emits `model_glb`. Sets
  `ParentIds`. No change.
- **Import** — `import_package` is package-id-based and provider-agnostic. No change.
- **MCP** — new **submit** tool only (sends `op: "submit_mesh_job"`). Reuse the existing
  `rhino_2d_to_3d_status` / `_result` / `_import` (job/package-id based, source-agnostic). Verify the
  native reconstruction dispatch forwards the new op (add to its op allowlist if one exists — small).

## Lineage

No new mechanism. The shared tail passes `sourceArtifactIds = [sourcePackageId]`; the materializer sets
`package.ParentIds = [sourcePackageId]`. The Smart-Topology package's parent is the source package.

## Testing (deterministic — no fal calls)

- **Parser:** valid parse; missing `source_package_id`/`model_id` → `invalid_request` (field-named);
  `options` array/scalar → `invalid_request`; `allow_experimental_model` non-bool → `invalid_request`;
  strict-true honored; user-supplied `input_file_type` option → `invalid_request` (unknown option).
- **Mesh source validator:** not-found / wrong-kind → `invalid_source_package`; no `model_glb` role →
  `missing_model_glb`; empty/unreadable blob → `invalid_source_package`.
- **Source-front gates (cross-rejection both ways):** `submit_mesh_job` rejects an image→3D model
  (e.g. Meshy v6) with a typed error; `submit_job` rejects the Smart Topology model; experimental gate
  honored (mesh model rejected without `allow_experimental_model`, accepted with it).
- **Options + payload:** `polygon_type`/`face_level` enum validation; provider payload (via
  `BuildSubmitPayload`) carries `input_file_url` + injected `input_file_type:"glb"` + the two options.
- **Catalog:** production catalog has the entry with expected fields; the image picker / image gate
  **excludes** it.
- **Lineage:** the mesh front passes `[sourcePackageId]` as `sourceArtifactIds` into the tail /
  materialize; ledger record has `SourceArtifactId = sourcePackageId`, `SourceRole = "model_glb"`.
- **Upload-failure parity:** credential-missing during mesh upload → **recorded failed job** (job
  created before upload), not a pre-ledger failure; failure text is source-neutral.

## Live smoke (one paid run — promotion gate)

**Precondition (check first, fail loud):** a real prior image→3D package with a `model_glb` blob still
staged locally (e.g. `d61c3f06-0c85-4e01-a84c-56bd5439a966`, which has `model_glb.glb`). If missing,
STOP and decide whether to run a fresh image→3D first — do not silently substitute.

Run `submit_mesh_job(source_package_id=<pkg>, model_id="fal-ai/hunyuan-3d/v3.1/smart-topology",
allow_experimental_model:true, options{polygon_type, face_level})` → poll to completion → new package →
`import_package` → verify:
- a non-degenerate imported object (non-empty bbox, valid mesh),
- `model_glb` asset role present in the new package,
- the new package's `ParentIds` contains the source package id.

Then promote the catalog entry to `stable` (separate follow-up or same slice per reviewer call).

## Risks / out of scope

- **Provider-URL reuse** deferred until a trustworthy freshness signal exists (YAGNI now).
- **OBJ source / obj input_file_type** out — v1 is GLB-only.
- **Full `IReconstructionSubmitSource` abstraction** (Approach 2) deferred to when the 2nd mesh provider
  (Segmentation/Remesh) gives it a real second consumer.
- **Selected-Rhino-object export** as a mesh source — explicitly a later slice (this slice is
  package-derived input only).
- **Mesh listing UI / picker** — not in v1.
- No fal Workflow Endpoints / `workflows/execute`.
