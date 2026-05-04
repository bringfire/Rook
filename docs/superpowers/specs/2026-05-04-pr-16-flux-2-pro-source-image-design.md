# PR-16 Flux 2 Pro Source-Image Design

## Summary

PR-16 adds Replicate `black-forest-labs/flux-2-pro` as a curated, source-image-first RookVision model.

The slice is not broad catalog discovery and not another prompt-only text-to-image expansion. Its product contract is:

- users provide exactly one primary source image through an existing RookVision source-image workflow;
- the source may come from Generate's viewport capture path or Studio's existing source upload/depth workflow;
- the prompt is required;
- Flux 2 Pro runs through bridge-only async image jobs;
- the generated result is materialized into the local artifact store and appears through the existing Gallery flow.

PR-16 keeps Schnell as the cheap Replicate prompt-only async canary. Flux 2 Pro is the serious source-image enhancement/editing model.

## Context

PR-14 exposed Replicate in Vision Settings and added `black-forest-labs/flux-schnell` as the first visible Replicate image model.

PR-15 added durable image job lifecycle persistence and restart reconciliation for bridge-only image jobs. Live Rhino validation confirmed that Replicate Schnell can complete through RookVision, write the image job JSONL ledger, materialize a local artifact, and keep that artifact visible in Gallery after Rhino restart.

PR-14a mode UX was considered but not promoted. Live use was clear enough for now.

The next product signal is not raw model count. RookVision's core image workflow is Rhino/Grasshopper source imagery: capture a modeled viewport, enhance or edit it into a higher-quality image, and keep the result as a local artifact for downstream work. Text-to-image remains useful, especially for later 2D-to-3D workflows, but it is secondary for this slice.

## Catalog Strategy

The user-visible model list remains curated.

Provider discovery may become an internal catalog-assist process later. It can help find candidates, inspect schemas, detect drift, and draft descriptors, but discovered models do not become visible automatically.

PR-16 does not add dynamic discovery or a provider model browser.

## Product Scope

Flux 2 Pro supports exactly one primary source image through existing `input_image_path` handling.

Allowed:

- Generate tab active viewport capture as the source image.
- Studio primary source image from the existing source workflow, including current picker/depth paths that already converge as `input_image_path`.
- One prompt.
- One async image job.
- Existing PR-15 durable lifecycle records.

Not allowed:

- prompt-only Flux 2 Pro submission;
- `reference_image_paths`;
- multiple reference images;
- new upload/provenance plumbing;
- dynamic provider discovery;
- provider schema metadata in durable records;
- UI mode overhaul from PR-14a.

Flux 2 Pro should be described in the image catalog with:

- provider `replicate`;
- submission mode `async_image_job`;
- `SupportsImageToImage = true`;
- `SupportsTextToImage = false`;
- `MaxReferenceImages = 0`.

The primary source image is not a reference image in Rook's request shape. It is the non-reference `input_image_path` / `ImageMediaRoles.InputImage` media role. `MaxReferenceImages = 0` keeps `reference_image_paths` rejected by existing gating while still allowing source-image generation.

## Architecture And Data Flow

PR-16 keeps the current managed Vision image pipeline:

1. The UI builds an image-generation request.
2. `VisionHandler.BuildImageGenerationWorkItem` validates the selected model and resolves `input_image_path` into primary `ResolvedMedia`.
3. `ImageJobOpHandler` wraps the work item in an `ImageJobStartRequest`.
4. `ImageJobManager` submits to the provider, polls, materializes, writes a local artifact, and appends PR-15 ledger snapshots.

Async image jobs must no longer imply prompt-only. The frontend routing rule becomes:

- sync source-image models keep using `generate`;
- async prompt-only Schnell keeps using `image_generate_start` without `input_image_path`;
- async source-image Flux 2 Pro uses `image_generate_start` with `input_image_path`;
- Studio also uses the async job path when Flux 2 Pro is selected.

`ReplicateImageProvider` must branch request construction by model id. Schnell keeps its current prompt-only schema. Flux 2 Pro gets its own request schema and must not receive Schnell-specific fields accidentally.

Flux 2 Pro provider behavior:

- require exactly one primary source image: one `MediaRef` with role `ImageMediaRoles.InputImage`;
- reject missing input image, zero-byte input, multiple primary input roles, unsupported MIME, oversized payload, and any `ImageMediaRoles.ReferenceImage` entries before any Replicate request;
- construct `input_images: [data-uri]` from the resolved primary source only;
- send `aspect_ratio: "match_input_image"` unconditionally in PR-16;
- omit aspect override, crop, and reframe behavior from this slice.

The data URI is constructed in memory only for the Replicate submit request. It must not be copied into provider metadata, mapped provider errors, logs, artifact metadata, ledger records, or bridge responses.

Durability stays unchanged:

- the image job ledger remains operational-only;
- no prompt, input path, data URI, source bytes, provider URLs, provider request JSON, or provider envelope enters the image job ledger.

## Validation, Limits, And Leakage Controls

PR-16 fails closed before Replicate submit when the Flux 2 Pro source payload is not safe to send.

Required validation:

- exactly one primary source image via `input_image_path`;
- prompt-only Flux 2 Pro rejected;
- `reference_image_paths` rejected;
- missing resolved media rejected;
- zero-byte media rejected;
- multiple `InputImage` media entries rejected;
- any `ReferenceImage` media entry rejected;
- only `image/png`, `image/jpeg`, and `image/webp` allowed when bytes and detected MIME agree;
- do not rely on the current hardcoded `"image/png"` in `VisionHandler`; Flux 2 Pro needs byte sniffing or resolved MIME normalization before data URI construction;
- raw source byte cap is 1 MB for PR-16 data URI transport;
- pixel cap is optional, not required;
- oversized sources return an `InvalidRequest` failure with a clear action message such as: "Source image is too large for Flux 2 Pro data URI upload; capture a smaller viewport or lower resolution.";
- no automatic resize or compression in PR-16.

Local source validation failures are `InvalidRequest`. Provider, network, token, and transport failures remain `DependencyUnavailable` where existing mappings already use that class.

Leakage controls:

- never persist prompt, source path, source bytes, or data URI in the image job ledger;
- never include data URI, input URL, source path, provider request JSON, provider output URLs, provider handles, or raw provider envelope in bridge responses;
- do not put data URI or source path in artifact metadata;
- sanitize mapped provider errors and add banned-substring coverage for `data:image/`;
- fake HTTP tests assert outbound Replicate JSON contains the data URI, while ledger, artifact metadata, bridge list/status/result payloads do not.

## UI Behavior And Model Gating

Flux 2 Pro appears in the curated image model catalog as a source-image async Replicate model.

Model picker behavior:

- before a primary source image exists, Flux 2 Pro is disabled or blocked with a clear local message;
- once Generate has an active viewport/source capture, Flux 2 Pro is enabled;
- in Studio, Flux 2 Pro is enabled when a primary source image is loaded through the existing source workflow;
- Schnell remains the Replicate prompt-only async option;
- existing sync Gemini/fal source-image behavior is unchanged.

Routing behavior:

- frontend routing uses both `submission_mode` and presence of `input_image_path`;
- `generate` remains the sync path;
- `image_generate_start` handles async prompt-only and async source-image jobs;
- Flux 2 Pro requests must include `input_image_path`;
- Schnell requests must not include source or reference image fields in PR-16;
- Studio routes Flux 2 Pro through async status/result handling.

User-facing states:

- missing source image fails locally before submit;
- oversized source image fails with the backend `InvalidRequest` message;
- no silent resize or compression;
- completed Flux 2 Pro artifacts appear through the existing Gallery/artifact flow;
- no new mode UX, discovery UI, multi-reference UI, crop/reframe UI, or upload/provenance UI.

## Implementation Boundaries

Implementation stays inside the managed Vision image stack.

In scope:

- add curated `black-forest-labs/flux-2-pro` constants, capability, and registration;
- extend `ReplicateImageProvider` with model-id-specific request construction;
- add Flux 2 Pro source-image validation and bounded data URI construction;
- add MIME sniffing or normalization for resolved primary media;
- update frontend routing so async source-image models use `image_generate_start`;
- add Studio async result/status handling for Flux 2 Pro if the existing path does not already cover it;
- add leakage tests around ledger, bridge payloads, artifact metadata, provider errors, and outbound fake HTTP.

Out of scope:

- native, MCP, or public HTTP exposure;
- dynamic provider discovery;
- prompt-only Flux 2 Pro;
- multiple reference images or `reference_image_paths`;
- new upload/provenance flows;
- automatic resize or compression;
- new durable ledger fields;
- Replicate auto-resume;
- PR-14a UI mode overhaul.

## Acceptance Gates

Automated tests:

- unit tests use fake provider/fake HTTP only;
- Flux 2 Pro catalog descriptor is visible and source-image-only;
- Generate source-image Flux 2 Pro routes to `image_generate_start` with `input_image_path`;
- Studio source-image Flux 2 Pro routes to async job start, status polling, and result fetch;
- Schnell prompt-only async routing does not send `input_image_path` or `reference_image_paths`;
- Flux 2 Pro submit without `input_image_path` fails before provider HTTP;
- Flux 2 Pro submit with a valid source image sends expected Replicate request JSON;
- oversized, zero-byte, unsupported MIME, and reference-image inputs fail before provider HTTP;
- data URI appears only in outbound fake HTTP request body;
- image job ledger contains no prompt, source path, data URI, provider URLs, or provider request payload;
- bridge `image_jobs`, `image_job_status`, `image_job_result`, and `image_job_cancel` expose no provider internals;
- artifact metadata contains no data URI or source path;
- mapped provider errors do not surface `data:image/`;
- local generated artifact is materialized through the existing PR-15 path and survives restart;
- Schnell async prompt-only behavior remains green;
- existing sync `generate` Gemini/fal source-image behavior remains green;
- boundary scan confirms no native, MCP, public HTTP, or `NativeGhBridgeRegistrar` exposure.

Manual Rhino smoke:

- create or capture a viewport source, select Flux 2 Pro, submit async job, poll to completion, and verify Gallery artifact;
- restart Rhino and verify the completed artifact remains visible;
- try Flux 2 Pro without a source and verify local blocked state;
- try an oversized source and verify clear validation failure.
