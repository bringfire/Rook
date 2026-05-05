# PR-17 fal GPT Image 2 Edit Source-Image Design

Date: 2026-05-05

## Goal

PR-17 adds a curated fal.ai source-image image model:
`openai/gpt-image-2/edit`.

This is the first fal async image-provider slice. Existing fal image support
is sync-only for `fal-ai/flux/schnell`; fal video already proves queue
submit/status/result/cancel. PR-17 brings that queue lifecycle to image jobs
for one curated source-image edit model without adding dynamic discovery,
prompt-only premium text-to-image, public routes, or new upload/provenance
flows.

The product workflow is:

- Rhino/Grasshopper viewport or source image;
- high-quality GPT Image 2 edit through fal queue;
- immediate local materialization into Rook artifacts;
- Gallery persistence through the existing completed-artifact path.

## Background

PR-15 made image jobs durable with an append-only JSONL ledger and startup
reconciliation to `Interrupted`. The ledger is operational-only: job id,
state, provider, model, provider job id, result artifact id, sanitized error,
and timestamps.

PR-16 proved the first serious async source-image model with Replicate Flux 2
Pro. It accepts exactly one `input_image_path`, builds a bounded data URI,
routes through `image_generate_start`, materializes provider output locally,
and does not persist prompt/source/data URI/provider internals in the image
job ledger, bridge job payloads, provider handles, or provider metadata.

fal already has managed substrate and provider code:

- `fal-ai/flux/schnell` uses a sync fal image path.
- fal video uses queue submit/status/result/cancel.
- the shared image job manager already accepts `QueuedSubmitOutcome`.

Official fal docs for `openai/gpt-image-2/edit`, reviewed on 2026-05-05,
describe an edit/source-image endpoint with `prompt`, `image_urls`,
`image_size`, `quality`, `num_images`, `output_format`, optional `mask_url`,
optional `sync_mode`, and downloadable image URLs in the result:
https://fal.ai/models/openai/gpt-image-2/edit/api

The PR-17 design uses that edit endpoint only.

## Non-Goals

- No prompt-only `openai/gpt-image-2` endpoint.
- No premium prompt-only text-to-image UX.
- No dynamic provider or model discovery.
- No unreviewed fal catalog import.
- No `reference_image_paths`.
- No `mask_url`.
- No multi-image output.
- No new upload/provenance flow.
- No public temp hosting.
- No automatic resize/compression unless later live evidence proves a hard
  provider transport constraint.
- No durable ledger schema change.
- No native route changes.
- No edits under `src/RookNative/**`.
- No MCP tool changes.
- No public HTTP parity.
- No `NativeGhBridgeRegistrar` exposure.
- No cross-provider artifact metadata policy rewrite.
- No removal of existing completed-artifact prompt metadata.

## Product Scope

Register one curated model:

- provider: `fal`
- model id: `openai/gpt-image-2/edit`
- display name: `GPT Image 2 Edit`
- submission mode: `async_image_job`
- supports image-to-image: true
- supports text-to-image: false
- max reference images: 0

The request body sent to fal is fixed for this release:

- `prompt`: Rook prompt
- `image_urls`: one data URI derived from the resolved primary source image
- `image_size`: `auto`
- `quality`: `high`
- `num_images`: `1`
- `output_format`: `png`
- `sync_mode`: omitted or `false`

The provider contract is explicit: fal GPT Image 2 edit always sends
`image_size: "auto"` regardless of any UI resolution selector value needed
to keep the existing controls valid.

## Provider And Manager Architecture

PR-17 should not split fal into separate public provider identities or fake
provider names. Provider identity remains `fal`.

Use a single model-aware fal image provider:

- `fal-ai/flux/schnell` remains sync.
- `openai/gpt-image-2/edit` uses async fal queue lifecycle.
- the provider branches internally by model id.
- provider secrets stay under the existing fal credential metadata.
- Settings and picker labels continue to show provider `fal`.

Catalog/model metadata must carry model-level `submission_mode`. The current
registration shape exposes submission mode at registration level, which fits
single-mode providers but not mixed fal image models. PR-17 should make model
resolution expose submission mode per model while keeping a single fal image
provider instance.

The image job manager must use durable `provider + model` for restart
lifecycle lookup:

- if a provider supports mixed modes, model id is part of lifecycle
  resolution;
- lookup resolves the persisted model first and verifies its provider is the
  persisted provider;
- the resulting provider is the same model-aware `fal` provider;
- lifecycle methods branch by model id.

This avoids registry ambiguity after restart. The manager must not rely on
provider-name-only lookup when a provider has mixed sync and async image
models.

Persist only fal `request_id` as the durable `provider_job_id`. Queue URLs are
never persisted.

The fal image provider reconstructs queue operations internally from model id
and request id:

- submit URL for `openai/gpt-image-2/edit`;
- status URL;
- response/result URL;
- cancel URL and HTTP method.

The durable provider handle shape for this model is minimal:

- `provider_job_id`: fal `request_id`
- no `status_url`
- no `response_url`
- no `cancel_url`
- no provider metadata
- no provider result token
- no request body
- no `image_urls`
- no result envelope

## fal Queue Lifecycle

Submit:

1. Validate source image and request shape locally.
2. Build the fixed fal request body.
3. Submit to fal queue.
4. Parse fal `request_id`.
5. Return `QueuedSubmitOutcome(new ProviderJobHandle(request_id))`.

Status:

- fal queued states map to image job `Polling` with optional progress when
  safe scalar queue position is available in memory only.
- fal running states map to image job `Polling`.
- fal completed state maps to `ProviderCompleteStatusOutcome`.
- fal failed/cancelled states map to sanitized failure outcomes.

Result:

1. Fetch fal queue response using model id + request id.
2. Parse exactly one `images[0].url`.
3. Reject zero images, multiple images, missing URL, invalid URL, or
   non-http(s) URL.
4. Return a `RemoteArtifactBody`.
5. Let the image job manager materialize bytes and write the local Rook
   artifact before marking the job `Complete`.

Cancel:

- call fal queue cancel using model id + request id;
- map accepted/success to `CanceledOutcome`;
- map already-terminal provider response to `AlreadyTerminalOutcome`;
- map HTTP/transport failures to sanitized typed errors.

The image job manager remains provider-neutral. It sees only
`ProviderSubmitOutcome`, `ProviderStatusOutcome`, `ProviderResultOutcome`, and
`ProviderCancelOutcome`; fal request and response schemas stay inside the fal
image provider.

## Validation And Transport

Add a model-specific fal source payload builder parallel to the Flux 2 Pro
source payload. Do not create a generic fal upload abstraction in PR-17.

Request validation:

- model must be exactly `openai/gpt-image-2/edit`;
- prompt is required through the existing image request validation;
- exactly one primary `input_image_path` is required;
- the primary media role must be `ImageMediaRoles.InputImage`;
- prompt-only calls are rejected locally before provider submit;
- `reference_image_paths` are rejected locally before provider submit;
- provider-specific caller fields such as `mask_url`, `image_urls`,
  `quality`, `output_format`, or `sync_mode` must not reach the fal request
  builder.

If the existing typed bridge request shape drops unknown fields, tests must
prove that caller-supplied `mask_url`, `quality`, `output_format`, and
`image_urls` do not reach the fal request builder. If those fields can reach
request validation, reject them at the bridge/request validation boundary.

Source image validation:

- source bytes must be non-empty;
- raw source bytes are capped by a model-specific constant that starts at
  `1 MB`, matching PR-16's conservative data URI cap;
- MIME is detected from bytes;
- allowed MIME types are PNG, JPEG, and WebP unless live fal evidence proves
  a narrower set;
- declared/resolved MIME must match detected MIME when a declared MIME is
  present;
- no automatic resize or compression is performed in PR-17.

Transport:

- build exactly one data URI from the validated source bytes;
- send that data URI as the only entry in `image_urls`;
- do not use public temp hosting;
- do not use fal storage/upload;
- omit `sync_mode` unless fake/live evidence shows the queue endpoint needs
  explicit `false`;
- never set `sync_mode: true`.

## Privacy And Leakage Controls

Existing completed-artifact prompt metadata is intentionally preserved and out
of scope. PR-17 does not remove or migrate current local artifact metadata
semantics.

The durable image job ledger remains operational-only and must not include
prompt/source/request/provider internals. Ledger records may contain
`provider_job_id` only as the scalar fal request id. Ledger records must not
contain fal envelope keys, queue URLs, fal media URLs, request JSON,
`image_urls`, data URIs, source paths, prompt text, or provider result
envelopes.

Bridge job responses must not echo prompt/source/request/provider internals.
The `image_generate_start` request necessarily accepts a user prompt and source
path from the UI/bridge caller, but its response may return only Rook's local
`job_id` and state. It must not return fal `request_id`, `provider_job_id`,
queue URLs, fal media URLs, request JSON, `image_urls`, source paths, prompts,
or provider result envelopes. The same no-echo rule applies to
`image_job_status`, `image_job_result`, `image_job_cancel`, and `image_jobs`.

Provider handles must persist only what is needed for lifecycle:

- fal request id as `provider_job_id`;
- no fal URLs;
- no request body;
- no response body;
- no result envelope;
- no provider metadata bag for this model.

Artifact metadata may continue to include existing completed-artifact prompt
metadata, but PR-17 must not add fal/source transport leakage:

- no data URI;
- no source path;
- no fal URL;
- no `image_urls`;
- no request JSON;
- no provider response envelope;
- no provider logs;
- no fal request id;
- no queue URL;
- no queue position.

Add fal-specific leakage redaction for sanitized image job errors and any
ledger-bound or bridge-bound error text:

- `fal.media`
- `queue.fal.run`
- `fal.run`
- `image_urls`
- `status_url`
- `response_url`
- `cancel_url`
- `data:image/`
- provider request body fragments

Do not ban every occurrence of the text `request_id` globally. The actual fal
request id is intentionally persisted as `provider_job_id`. Tests should
distinguish that safe scalar field from leaked fal envelope keys such as
`"request_id"`, `status_url`, `response_url`, and `cancel_url`.

Provider HTTP/body parsing failures should map to generic messages. Detailed
fal response bodies should not be surfaced externally or persisted.

## UI Behavior And Routing

PR-17 treats GPT Image 2 edit as another source-image async image model in the
curated catalog. It does not add a new UI mode.

Generate view:

- selecting GPT Image 2 edit requires a captured viewport/source image;
- Generate calls `image_generate_start`, not sync `generate`;
- submitted args include `prompt`, `model`, and `input_image_path`;
- submitted args do not include `reference_image_paths`;
- missing source blocks locally before bridge submit;
- existing local `aspect_ratio: "match_input_image"` hints may be sent by the
  UI for source-image async models, but the fal provider maps GPT Image 2 edit
  to `image_size: "auto"`.

Studio view:

- GPT Image 2 edit is selectable because it supports source-image editing;
- Studio submit calls `image_generate_start`;
- submitted args include exactly one `input_image_path` from
  `studioSource.path`;
- reference controls are disabled and cleared because `max_reference_images`
  is `0`;
- no mask controls appear;
- server-side validation still fails closed if a caller bypasses the UI.

Prompt-only blocking:

- GPT Image 2 edit is not treated as a prompt-only async image model;
- `openai/gpt-image-2` is not registered;
- manual bridge calls without `input_image_path` fail before provider submit;
- manual bridge calls with `reference_image_paths` fail before provider submit;
- sync `generate` with GPT Image 2 edit fails closed because the model is
  async.

The user-facing behavior should match the Flux 2 Pro source-image workflow:
source image in, async job starts, status progresses, local generated artifact
appears in Gallery.

## Testing Strategy

### Provider And Queue Tests

Fake-HTTP fal image tests should prove:

- GPT Image 2 edit submit posts to the fal queue endpoint;
- submit body contains the fixed fields:
  - `prompt`;
  - one-item `image_urls` data URI array;
  - `image_size: "auto"`;
  - `quality: "high"`;
  - `num_images: 1`;
  - `output_format: "png"`;
- submit body does not contain `mask_url` or references;
- caller-supplied provider option fields do not reach the request body;
- successful submit returns `QueuedSubmitOutcome` with only fal request id;
- status maps queued/running/completed/failure states;
- result fetch parses exactly one `images[0].url`;
- zero images, multiple images, malformed image object, invalid URL, and
  non-http(s) URL fail closed;
- cancel maps success/already-terminal/failure responses;
- auth, quota, transport, timeout, and malformed JSON failures are sanitized.

### Source Payload Tests

Tests should prove:

- exactly one primary source image is required;
- prompt-only request is rejected before provider submit;
- `reference_image_paths` are rejected before provider submit;
- empty bytes fail;
- raw bytes over the GPT Image 2 edit cap fail;
- PNG, JPEG, and WebP bytes are accepted;
- unsupported MIME bytes fail;
- declared MIME mismatch fails;
- generated data URI uses the detected MIME;
- provider-specific error messages name GPT Image 2 edit, not Flux 2 Pro.

### Manager And Restart Tests

Image job manager tests should prove:

- model-level submission mode routes GPT Image 2 edit through image jobs;
- one model-aware fal provider can serve sync Schnell and async GPT Image 2
  edit;
- durable restart lifecycle lookup uses persisted `provider + model`;
- lookup resolves the model-aware fal provider and branches by model id;
- only fal request id is persisted as `provider_job_id`;
- queue URLs are not persisted;
- cancel-after-restart reconstructs fal queue operations from model id +
  request id;
- result/status after restart do not require persisted fal URLs.

### Leakage Tests

Serialize ledger lines, bridge start/status/list/result/cancel payloads, image
job errors, and generated artifact metadata for fake GPT Image 2 edit runs.

Assert external bridge responses do not expose:

- fal `request_id`;
- `provider_job_id`;
- queue URLs;
- fal media URLs;
- `image_urls`;
- data URI;
- source path;
- prompt;
- request JSON;
- provider result envelope.

Assert ledger records may contain `provider_job_id` as a scalar fal request id
but do not contain:

- `"request_id"`;
- `status_url`;
- `response_url`;
- `cancel_url`;
- queue URLs;
- fal media URLs;
- request JSON;
- `image_urls`;
- data URI;
- source path;
- prompt;
- provider result envelope.

Assert generated artifact metadata does not add new fal/source transport
leakage:

- no data URI;
- no source path;
- no fal URL;
- no `image_urls`;
- no request JSON;
- no provider response envelope;
- no provider logs;
- no request id.

Existing prompt metadata in completed local artifacts is allowed by this
design and should not fail PR-17 tests.

### UI And Routing Tests

UI/bridge tests should prove:

- GPT Image 2 edit appears as a curated fal image model;
- it is marked `async_image_job`;
- it supports image-to-image and not text-to-image;
- it has `max_reference_images: 0`;
- Generate with captured viewport calls `image_generate_start`;
- Studio with source image calls `image_generate_start`;
- Generate without captured viewport blocks locally;
- Studio reference controls are disabled/cleared;
- prompt-only manual bridge call fails before provider submit;
- reference-image manual bridge call fails before provider submit;
- sync `generate` fails closed for GPT Image 2 edit;
- prompt-only `openai/gpt-image-2` is absent from the catalog.

### Live Rhino Smoke Gate

Before merge, run an explicitly enabled live smoke with a real fal key:

1. Configure fal API key.
2. Capture a Rhino viewport/source image.
3. Select GPT Image 2 edit.
4. Submit through Generate or Studio.
5. Observe image job states through queued/submitting/polling/materializing.
6. Confirm local artifact materialization.
7. Confirm Gallery persistence.
8. Confirm `image_jobs`, `image_job_status`, and `image_job_result` work.
9. Exercise cancel while queued if timing allows.
10. Restart/reload and confirm non-terminal jobs reconcile without leaking fal
    internals.

Live smoke evidence must not be committed with prompts, source images, data
URIs, fal URLs, fal request envelopes, or credentials.

## Acceptance Criteria

- `openai/gpt-image-2/edit` is registered as a curated fal source-image model.
- `openai/gpt-image-2` is not registered.
- Provider identity remains `fal`.
- A single model-aware fal image provider supports sync Schnell and async GPT
  Image 2 edit.
- Image model metadata supports model-level submission mode.
- Image job manager restart lookup uses durable `provider + model`.
- fal queue lifecycle works for submit/status/result/cancel through existing
  image job outcomes.
- Exactly one primary source image is accepted.
- Prompt-only calls and references fail before provider submit.
- Source transport uses bounded data URI, not public hosting or fal upload.
- fal request sends `image_size: "auto"`, `quality: "high"`, `num_images: 1`,
  and `output_format: "png"`.
- The ledger schema does not change.
- The ledger persists only fal request id as `provider_job_id`.
- Queue URLs are never persisted.
- Bridge job responses do not expose fal request id/provider job id or
  provider internals.
- Artifact metadata does not add fal/source transport leakage.
- Existing completed-artifact prompt metadata is preserved and out of scope.
- Normal tests use fake providers/fake HTTP only.
- Live Rhino smoke passes before merge.
- No native, MCP, public HTTP, or `NativeGhBridgeRegistrar` exposure is added.

## Follow-Up

Future slices can decide:

- prompt-only premium GPT Image 2 text-to-image;
- mask support;
- multi-reference editing;
- fal storage/upload abstraction;
- source provenance UX;
- dynamic provider discovery;
- public native/MCP/HTTP exposure;
- cross-provider generated-artifact prompt metadata policy.

## Self-Review

- The scope is fal async image provider plus one curated source-image workflow.
- The design does not register prompt-only GPT Image 2.
- Provider identity remains `fal`.
- The registry/manager architecture avoids fake provider names and provider
  credential duplication.
- Restart lifecycle lookup explicitly uses `provider + model`.
- The durable ledger schema remains unchanged and operational-only.
- fal queue URLs and result envelopes are reconstructed/fetched at runtime, not
  persisted.
- Validation rejects prompt-only calls, references, masks, and provider-specific
  caller fields before provider submit.
- Source transport uses bounded data URI and no public hosting.
- Privacy wording preserves existing local artifact prompt metadata while
  blocking new fal/source transport leakage.
- UI routing uses existing async source-image behavior.
- Tests include fake provider/HTTP, leakage, UI routing, restart lifecycle, and
  live Rhino smoke gates.
