# Rook Reconstruction 2D-to-3D Design

Date: 2026-06-19

## Goal

Add the first Rook 2D-to-3D reconstruction pipeline as a dedicated Reconstruction domain. The v1 slice turns a Vision image artifact into a durable reconstruction package using fal.ai's Hunyuan 3D rapid image-to-3D model, then imports the selected asset into Rhino with object-level package association.

This is model-backed reconstruction, not RookCAD. Line, curve, floor-plan, constraint, or semantic CAD reconstruction is deferred to the future RookCAD domain.

## Architecture Boundary

Reconstruction is a first-class Rook domain from day one:

- `RookNative` remains the only public HTTP surface.
- Native `/reconstruction/...` routes are thin public proxies.
- The managed companion owns provider calls, job ledger, package materialization, artifact metadata, and UI affordances.
- Shipped architecture uses a dedicated managed `ReconstructionOpHandler` and a dedicated `reconstruction_dispatch` bridge callback, not `vision_dispatch`.
- Vision remains the image source/artifact surface. Reconstruction consumes Vision artifacts and writes reconstruction packages.
- The full Rook Reconstruction panel is deferred to slice 2. V1 UI is a minimal Vision "Send to 3D" affordance that calls reconstruction-owned routes.

Reused infrastructure:

- `ArtifactStore`
- `DpapiGenerationSecretStore`
- `GenerationSecretKeys.FalApiKey`
- existing fal client/error/lifecycle patterns
- existing image/video job-manager, materializer, and JSONL ledger patterns
- native import/ObjectDiffTracker pattern from `ImportExportHandler.cpp`

New managed namespace:

```text
src/Rook/Services/Reconstruction/
```

Initial components:

- `ReconstructionPipelineManager`
- `ReconstructionProviderRegistry`
- `ReconstructionOpHandler`
- `JsonlReconstructionJobLedger`
- `ReconstructionPackageMaterializer`
- `ReconstructionImportManifest`
- `FalReconstructionProvider`
- `FalReconstructionModelCatalog`

## Pipeline

V1 pipeline contract:

```text
source_image
  -> preprocessing_chain[]   // empty by default
  -> reconstruction_model
  -> reconstruction_package
  -> optional Rhino import
```

V1 behavior:

- Default path sends the source image directly to Hunyuan rapid.
- Preprocessing is first-class in the contract but disabled/manual by default.
- At most one manual preprocessing stage is expected in v1.
- Preprocessing stages are inline stages inside the single reconstruction job record.
- Background removal is not automatic.
- BiRefNet can be cataloged as an experimental/manual preprocessing model.

## Provider Model Choice

Primary shipped v1 model:

```text
fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d
```

Cataloged experimental model:

```text
fal-ai/meshy/v6/image-to-3d
```

Hunyuan rapid is the first implementation path because it has a small input surface and still validates the package contract through multi-file output: GLB/OBJ possibilities, material, texture, thumbnail, and provider result metadata.

Meshy v6 is a contract pressure test and follow-up implementation target because it has a richer schema: remesh/topology options, target polycount, PBR/texturing controls, optional rigging/animation outputs, safety controls, and more output roles.

## Routes

All public routes are registered in `RookNative` and proxy into the managed reconstruction dispatch boundary.

```text
GET  /reconstruction/2d-to-3d/models
POST /reconstruction/2d-to-3d/jobs
GET  /reconstruction/2d-to-3d/jobs
GET  /reconstruction/2d-to-3d/jobs/{job_id}
POST /reconstruction/2d-to-3d/jobs/{job_id}/cancel
GET  /reconstruction/2d-to-3d/jobs/{job_id}/result
POST /reconstruction/2d-to-3d/import
```

Every route uses the existing Rook response envelope:

```json
{
  "success": true,
  "data": {}
}
```

or:

```json
{
  "success": false,
  "data": {
    "code": "invalid_request",
    "message": "source_artifact_id is required.",
    "retryable": false,
    "field": "source_artifact_id",
    "details": {}
  }
}
```

Structured failure fields:

- `code`: stable machine-readable reason.
- `message`: operator-readable text.
- `retryable`: whether retrying the same request may succeed.
- `field`: request field associated with the failure, or `null`.
- `details`: structured context; empty object when none.

Partial import failure example:

```json
{
  "success": false,
  "data": {
    "code": "association_failed",
    "message": "Import completed, but object association failed.",
    "retryable": true,
    "field": null,
    "details": {
      "package_id": "00000000-0000-0000-0000-000000000000",
      "job_id": "00000000-0000-0000-0000-000000000000",
      "import_id": "00000000-0000-0000-0000-000000000000",
      "asset_role": "model_glb",
      "imported_ids": ["00000000-0000-0000-0000-000000000000"],
      "association_error": "..."
    }
  }
}
```

## Submit Contract

V1 submit accepts source artifacts only. It does not accept arbitrary local image paths.

```json
{
  "source_artifact_id": "00000000-0000-0000-0000-000000000000",
  "source_role": "image",
  "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
  "preprocessing_chain": [],
  "options": {
    "enable_pbr": true,
    "enable_geometry": false
  },
  "estimate_requested": false
}
```

Success data:

```json
{
  "job_id": "00000000-0000-0000-0000-000000000000",
  "state": "queued",
  "stage": "queued",
  "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
  "source_artifact_id": "00000000-0000-0000-0000-000000000000"
}
```

Source validation:

- `source_artifact_id` exists.
- Artifact kind is allowlisted.
- `source_role` exists; default is `image`.
- Blob path resolves through `ArtifactStore`.
- File is PNG, JPEG, or WebP by extension and/or byte sniffing.
- Byte size fits provider/model limits.
- Dimensions fit provider/model limits when cheap to inspect.
- `reconstruction_package` cannot be used as a source in v1.

Default allowed source artifact kinds:

- `generated_image`
- `imported_image`
- `captured_viewport`

Excluded by default:

- `depth_map`
- `reconstruction_package`
- arbitrary image-looking artifacts from unrelated domains

## Job Ledger

The ledger is mandatory in v1. It is the durable job/history index and remains useful even if result artifacts are deleted.

The package artifact is not a substitute for the ledger.

Ledger responsibilities:

- job status and history
- request summary
- provider/job IDs
- failure diagnostics
- cancellation/interruption records
- result artifact reference
- import summaries or references

Package responsibilities:

- materialized files
- provider result JSON
- import manifest
- asset role map
- source/preprocessing lineage
- import history

Job states:

```text
queued
running
cancellation_requested
cancelled
complete
error
interrupted
```

Job stages:

```text
queued
preprocessing
submitting
polling
materializing
complete
error
cancelled
interrupted
```

Ledger record shape:

```json
{
  "schema_version": 1,
  "job_id": "00000000-0000-0000-0000-000000000000",
  "state": "running",
  "stage": "polling",
  "provider": "fal",
  "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
  "provider_job_id": "...",
  "active_provider_job_id": "...",
  "source_artifact_id": "00000000-0000-0000-0000-000000000000",
  "source_role": "image",
  "preprocessing_chain": [],
  "request": {
    "options": {
      "enable_pbr": true,
      "enable_geometry": false
    }
  },
  "pricing": {
    "kind": "unknown",
    "estimated_usd": null,
    "source": null,
    "confidence": "unavailable",
    "checked_at": null
  },
  "result_artifact_id": null,
  "result_available": false,
  "error": null,
  "created_at": "2026-06-19T00:00:00.0000000Z",
  "updated_at": "2026-06-19T00:00:00.0000000Z"
}
```

Inline preprocessing stage shape:

```json
{
  "stage_id": "00000000-0000-0000-0000-000000000000",
  "role": "remove_background",
  "provider": "fal",
  "model_id": "fal-ai/birefnet",
  "state": "complete",
  "input_artifact_id": "00000000-0000-0000-0000-000000000000",
  "output_artifact_id": "00000000-0000-0000-0000-000000000000",
  "provider_job_id": "...",
  "error": null
}
```

Pricing is advisory in v1. Submit is not blocked when pricing is missing.

## Cancellation

Cancellation is best-effort across the workflow and transitions only at safe boundaries.

- `queued`: cancel locally before work starts.
- `preprocessing`: remote cancel if a provider handle exists; otherwise set cancellation requested and stop before the next stage.
- `submitting`: cannot reliably cancel in-flight submit; mark cancellation requested and stop after submit returns if no remote handle exists.
- `polling`: remote cancel active fal job when a handle exists. This is the most important v1 cancellation case.
- `materializing`: cancel only before package commit or at materializer-owned temp-directory boundaries. Do not promise rollback after package artifact commit.
- Terminal states are idempotent reads.

Implementation model:

```text
cancel request
  -> set local cancellation flag/token
  -> if active provider handle exists, call provider cancel
  -> transition at safe boundary
```

## Reconstruction Package Artifact

The terminal result is a Rook package, not just one model file.

```text
artifact.kind = "reconstruction_package"
```

File roles:

```text
model_glb
model_obj
model_fbx
model_usdz
model_stl
material_mtl
texture
texture_base_color
texture_metallic
texture_roughness
texture_normal
thumbnail
source_image
preprocessed_image
provider_result_json
import_manifest
```

Package metadata:

```json
{
  "provider": "fal",
  "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
  "job_id": "00000000-0000-0000-0000-000000000000",
  "source_artifact_ids": ["00000000-0000-0000-0000-000000000000"],
  "preprocessing_chain": [],
  "asset_roles": ["model_glb", "thumbnail", "provider_result_json", "import_manifest"]
}
```

`provider_result_json` stores the sanitized provider result envelope. It must not contain secrets. It may preserve provider URLs and metadata needed for diagnostics, but local materialized file references live in the package file list and import manifest.

The materializer should be lossless relative to the sanitized fal result envelope. Even if GLB embeds textures, separately returned textures must still be materialized and tracked.

## Import Manifest

`import_manifest` is a Rook-authored package file. It describes how Rook interprets the package for import and future re-import/repair workflows.

```json
{
  "schema_version": 1,
  "preferred_asset": "model_glb",
  "fallback_order": ["model_glb", "model_obj"],
  "asset_bindings": {
    "model_obj": {
      "companion_roles": ["material_mtl", "texture"]
    }
  },
  "placement": {
    "mode": "document_default",
    "transform": null,
    "units_policy": "provider_default"
  },
  "imports": []
}
```

`asset_bindings` makes OBJ + MTL + texture association explicit rather than relying only on role names.

V1 import options are intentionally minimal:

- `targetLayer`
- optional `assetRole` override for debugging/agent use

No v1 insertion point, scale, rotation, replace, or reimport behavior.

## Import Route

V1 product import path:

```text
POST /reconstruction/2d-to-3d/import
```

Request:

```json
{
  "package_id": "00000000-0000-0000-0000-000000000000",
  "targetLayer": "Rook::Reconstruction",
  "assetRole": "model_glb"
}
```

`assetRole` is optional. If omitted, the route uses `import_manifest.preferred_asset` and `fallback_order`. If present, the route validates that the role exists in the package.

The route wraps:

- package lookup and validation
- import manifest read/validation
- preferred/fallback asset selection
- Rhino import via main-thread `_Import` and `ObjectDiffTracker`
- optional target layer move
- object association writes
- import history append to the package/import manifest

Success data:

```json
{
  "package_id": "00000000-0000-0000-0000-000000000000",
  "job_id": "00000000-0000-0000-0000-000000000000",
  "import_id": "00000000-0000-0000-0000-000000000000",
  "asset_role": "model_glb",
  "imported_ids": ["00000000-0000-0000-0000-000000000000"],
  "associated": true,
  "user_text": {
    "rook.reconstruction.package_id": "00000000-0000-0000-0000-000000000000",
    "rook.reconstruction.job_id": "00000000-0000-0000-0000-000000000000",
    "rook.reconstruction.import_id": "00000000-0000-0000-0000-000000000000",
    "rook.reconstruction.asset_role": "model_glb"
  }
}
```

User text keys:

```text
rook.reconstruction.package_id
rook.reconstruction.job_id
rook.reconstruction.import_id
rook.reconstruction.asset_role
```

If import succeeds but association or manifest history append fails, return `success:false` with code `association_failed` or `import_history_failed`, and include imported IDs in `details`. Do not pretend import did not happen unless a reliable rollback path exists.

## Model Catalog

Catalog file:

```text
src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json
```

Default `/models` returns stable/enabled shipped reconstruction models only. V1 default includes Hunyuan rapid.

Query flags:

```text
GET /reconstruction/2d-to-3d/models
GET /reconstruction/2d-to-3d/models?include_experimental=true
GET /reconstruction/2d-to-3d/models?include_hidden=true
```

`include_experimental=true` returns reviewed but non-default entries, such as Meshy v6 and BiRefNet preprocessing.

`include_hidden=true` returns hidden/dev entries only when explicitly requested. Hidden models are not shown in normal UI or agent model-picking flows.

Required model entry fields:

```json
{
  "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
  "provider": "fal",
  "task": "single_image_to_3d",
  "status": "stable",
  "enabled": true,
  "pipeline_roles": ["single_image_to_3d"],
  "input_types": ["image_url"],
  "output_roles": ["model_glb", "model_obj", "material_mtl", "texture", "thumbnail"],
  "preferred_asset_role": "model_glb",
  "fallback_order": ["model_glb", "model_obj"],
  "supports_pbr": true,
  "preprocessing": {
    "recommended": false,
    "required": false
  },
  "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"
}
```

## MCP Tools

MCP tools mirror the native routes and keep reconstruction-owned names:

```text
rhino_2d_to_3d_models
rhino_2d_to_3d_submit
rhino_2d_to_3d_jobs
rhino_2d_to_3d_status
rhino_2d_to_3d_cancel
rhino_2d_to_3d_result
rhino_2d_to_3d_import
```

Parity expectations:

- tool dispatcher routes to native `/reconstruction/...`
- public `call_tool()` success text is the route data, consistent with current MCP result contracts
- failure output preserves structured `code/message/retryable/field/details` under the existing public error formatting

## Capability Domain

Add first-class capability domain:

```text
reconstruction.2d_to_3d
```

Example domain:

```json
{
  "id": "reconstruction.2d_to_3d",
  "status": "ready",
  "loaded": true,
  "ready": true,
  "reason": "ready",
  "routes": [
    "GET /reconstruction/2d-to-3d/models",
    "POST /reconstruction/2d-to-3d/jobs",
    "GET /reconstruction/2d-to-3d/jobs",
    "GET /reconstruction/2d-to-3d/jobs/{job_id}",
    "POST /reconstruction/2d-to-3d/jobs/{job_id}/cancel",
    "GET /reconstruction/2d-to-3d/jobs/{job_id}/result",
    "POST /reconstruction/2d-to-3d/import"
  ],
  "operations": [
    "model_catalog",
    "submit_job",
    "list_jobs",
    "job_status",
    "cancel_job",
    "job_result",
    "import_package"
  ],
  "evidence": [
    {"kind": "callback", "name": "reconstructionDispatch", "ok": true},
    {"kind": "secret", "name": "falApiKey", "ok": true},
    {"kind": "catalog", "name": "reconstructionModels", "ok": true}
  ]
}
```

Readiness/degraded reasons:

- dispatch not registered: not ready
- malformed catalog: not ready
- missing fal key: submit degraded/not ready, read-only routes may still be ready
- ledger unavailable: jobs not ready
- import route unavailable: import degraded

## V1 UI

V1 UI is deliberately thin:

- Vision artifact row/action: "Send to 3D" or "Reconstruct in 3D"
- compact submit/status/result/import flow
- UI calls `/reconstruction/...`, not hidden Vision ops
- labels say Reconstruction / 2D to 3D
- result exposes package ID, status, thumbnail, primary asset, and import action

Full Rook Reconstruction panel is slice 2, after backend data and package/import telemetry exist.

## Implementation Slices

1. Managed reconstruction contracts: catalog models, ledger records, package/import manifest models, failure shape helpers.
2. Fal Hunyuan rapid provider adapter using existing fal client and shared fal API key.
3. Reconstruction job manager with submit/status/list/result/cancel and JSONL durability.
4. Package materializer producing `reconstruction_package` artifacts with provider result JSON and import manifest.
5. Dedicated managed `ReconstructionOpHandler` and `reconstruction_dispatch` callback.
6. Native `/reconstruction/2d-to-3d/*` route proxies and capabilities domain.
7. Reconstruction import route using native import/ObjectDiffTracker pattern and object user text association.
8. MCP tool registration and dispatcher parity tests.
9. Minimal Vision "Send to 3D" affordance that calls reconstruction routes.

## Validation Strategy

Unit/source-level tests:

- catalog loading/filtering and malformed catalog failures
- source artifact allowlist/content validation
- submit request validation and structured failures
- ledger append/replay state transitions
- cancellation state transitions
- package materializer role mapping for Hunyuan-shaped and Meshy-shaped payloads
- import manifest preferred/fallback asset resolution and `asset_bindings`
- structured partial import failure formatting
- MCP route/tool parity
- capability domain readiness/degraded cases

Live/manual validation:

- fal key absent path
- model list route with and without experimental flag
- Hunyuan submit/status/result with a small approved source artifact
- package materialization includes model, thumbnail, provider result JSON, and import manifest
- import route creates Rhino objects and stamps reconstruction user text
- association failure path is observable if stamping is forced to fail in a test hook

## Deferred Work

- full Rook Reconstruction panel
- automatic preprocessing
- multi-step preprocessing chains
- Meshy v6 shipped support
- model comparison
- placement controls
- replace/reimport
- package-to-package regeneration
- remesh/retexture workflows
- cost-estimate route
- RookCAD line/curve/semantic reconstruction
