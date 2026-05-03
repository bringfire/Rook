# PR-14 Replicate Settings And Visible Image Model Design

Date: 2026-05-03

## Goal

PR-14 makes the hidden Replicate image provider from PR-13 visible and usable in the RookVision Generate tab.

The slice exposes one conservative Replicate text-to-image model, `black-forest-labs/flux-schnell`, through managed Vision Settings, model catalog metadata, and bridge-only async image job ops. It does not redefine Studio, add native or MCP parity, add image-to-image support, add provider-specific knobs, or add durable image job recovery.

The key product contract is:

- Replicate becomes visible and usable in Generate.
- Generate supports prompt-only submission when the selected model is text-to-image only and async-job backed.
- Existing synchronous `generate` behavior remains source-image based.
- Studio remains source-image/edit oriented.
- Native/MCP/public HTTP surfaces remain unchanged.

## Background

PR-10 added the managed Replicate prediction substrate.

PR-11 decided visible Replicate image generation should use first-class image jobs, not a blocking synchronous fallback.

PR-12 added the hidden managed image job substrate and bridge-only image job ops:

- `image_generate_start`
- `image_job_status`
- `image_job_cancel`
- `image_job_result`
- `image_jobs`

PR-13 added production Replicate image provider code under `src/Rook/Services/Vision/Image/Replicate`, but kept it hidden from default image composition, Settings metadata, UI picker metadata, native routes, MCP tools, and `NativeGhBridgeRegistrar`.

PR-14 is the visibility slice. It should intentionally flip the default managed Vision boundary while keeping all public/native boundaries closed.

## Non-Goals

- No edits under `src/RookNative/**`.
- No edits under `mcp_server/**`.
- No native route, native trampoline, or MCP exposure for image jobs or provider credentials.
- No `NativeGhBridgeRegistrar` exposure for image job ops or provider credential ops.
- No Studio prompt-only workflow.
- No Studio redesign.
- No explicit global mode toggle.
- No Replicate image-to-image support.
- No reference images for Replicate.
- No additional Replicate models.
- No Replicate-specific user knobs.
- No dynamic Replicate catalog discovery.
- No live Replicate calls in normal tests.
- No durable image job ledger or restart recovery; that remains PR-15 unless PR-14a is promoted first.

## Architecture

PR-14 is managed Vision work.

`VisionProviderRegistrations` is the intentional exposure point:

- `CreateImageRegistrations(...)` adds `ReplicateImageProviderRegistration` alongside Gemini and fal.
- `CreateCredentialMetadata()` adds Replicate as a credential owner with `GenerationSecretKeys.ReplicateApiToken`.
- Existing PR-13 boundary tests that assert Replicate is absent from default managed Vision metadata should be replaced with tests proving Replicate is present only in the scoped managed Vision surfaces.

`RookSubsystemRoot.ImageJobs` must use the same default image registry that now includes Replicate. It must also provide the Replicate authenticated output request selector to `ImageJobManager`, so a visible Replicate job can submit, poll, fetch, and copy provider output into the local artifact store.

No provider URL, signed URL, token, or secret-bearing request may be serialized into job responses, artifact metadata, provider metadata persisted into artifacts, or durable payloads.

## Model Catalog Contract

`list_image_models` becomes the UI's source of truth for both capability and submission routing.

Each image descriptor gains a backend-owned `submission_mode`:

- `sync`
- `async_image_job`

This is not a JavaScript-maintained allowlist. The backend derives it from the registered model/provider contract and emits it with the descriptor. The UI consumes it and must not infer async behavior from model ids or provider names.

For PR-14:

- Gemini descriptors remain `submission_mode = "sync"`.
- fal image descriptors remain `submission_mode = "sync"`.
- Replicate `black-forest-labs/flux-schnell` is `submission_mode = "async_image_job"`.

Capability metadata remains separate from submission mode:

- `supports_text_to_image`
- `supports_image_to_image`
- `max_reference_images`
- `resolutions`
- `aspect_ratios`

Missing Replicate token keeps the model visible with `credential_availability = "missing_required_secret"` and a configure-key message. Present Replicate token makes the model submittable and initially available-but-unverified.

## Backend Work-Item Contract

The existing synchronous `generate` op must remain source-image based.

`VisionHandler.BuildImageGenerationWorkItem` should accept a narrow caller mode or options parameter so `ImageJobOpHandler` can allow prompt-only text-to-image without changing `GenerateAsync`.

Rules:

- `generate` rejects missing `input_image_path` regardless of model capability.
- `generate` continues to reject async providers with the existing "Provider returned an async job" failure.
- `image_generate_start` allows missing `input_image_path` only when:
  - the selected descriptor has `submission_mode = "async_image_job"`;
  - the resolved capability supports text-to-image;
  - no reference images are supplied.
- references are rejected for Replicate before submit.
- if source media is supplied for a model with `supports_image_to_image = false`, the backend rejects it before submit; the UI should normally prevent this by disabling source controls.
- prompt-only support must not become a silent global fallback for sync image providers.

This keeps prompt-only behavior tied to the job workflow PR-14 is exposing, not only to capability metadata. Some sync providers may advertise text-to-image while the existing sync UI/backend path still expects source media.

## Generate UI

PR-14 updates only the Generate tab for prompt-only Replicate.

On model change, Generate reads the selected descriptor's `submission_mode` and capability fields.

For `submission_mode = "sync"`:

- current source-image / viewport capture behavior remains;
- source media remains required;
- submit calls `generate`;
- existing result rendering remains.

For `submission_mode = "async_image_job"` and T2I-only capability:

- source and reference controls are disabled, not merely de-emphasized;
- any selected source/reference state is cleared or ignored with visible disabled state;
- submit can run from prompt alone;
- submit calls `image_generate_start`;
- status area shows image job state transitions:
  - `queued`
  - `submitting`
  - `polling`
  - `materializing`
  - `complete`
  - `error`
  - `cancelled`
- on complete, UI calls `image_job_result`;
- result renders from the returned local artifact id like current generated images.

A cancel action can be wired if it is straightforward to connect to `image_job_cancel`, but polished job-management UI is not part of PR-14.

The UI must route by `submission_mode`, not by provider name or model id.

## Studio UI

Studio remains source-image/edit oriented.

PR-14 should not add prompt-only behavior to Studio. T2I-only Replicate should remain visible but marked incompatible or disabled in Studio, matching the PR-9 principle that unavailable or mismatched models remain discoverable. Hiding should be used only if the existing picker pattern already hides incompatible models.

Studio's submit path remains unchanged for PR-14.

## Settings And Credential Testing

Replicate appears as a normal provider credential card in Settings through existing provider-card rendering.

Provider-aware secret operations should accept Replicate:

- `set_provider_secret(provider_name: "replicate", secret_key: "replicate.api_token", value: "...")`
- `clear_provider_secret(provider_name: "replicate", secret_key: "replicate.api_token")`
- `test_provider_secret(provider_name: "replicate", secret_key: "replicate.api_token", candidate_value?)`

Cross-provider writes remain rejected.

Replicate key testing is inconclusive by default in PR-14. The current Replicate substrate has prediction lifecycle calls and authenticated output request construction, but no proven non-spend auth probe. Settings `Test` must not call prediction endpoints. The existing fallback behavior should return `validation_state = "inconclusive"` with an explanatory message.

Submit remains the authoritative credential proof:

- missing token is a deterministic blocker;
- present token is available-but-unverified;
- failed submit due to Replicate auth may update panel-session warning state;
- validation state is not persisted.

Candidate values used for `test_provider_secret` must never be saved or returned.

## Error Handling

PR-14 should keep error mapping predictable:

- Missing Replicate token before submit or authenticated output fetch is `DependencyUnavailable`, non-retryable.
- References for Replicate are `InvalidRequest`, fielded to the reference input when possible.
- Source media supplied to T2I-only Replicate is rejected before submit.
- Replicate submit/auth/provider failures are surfaced through existing structured image job errors.
- Provider-complete does not mean job-complete; output must be copied into local artifacts before completion.
- Materialization failure after provider success is a job failure.

Public UI messages should remain sanitized with no token, provider URL, signed URL, or raw secret-bearing request detail.

## Testing Strategy

### Backend Tests

`VisionProviderRegistrationsTests` should prove:

- `CreateCredentialMetadata()` includes `replicate` with `GenerationSecretKeys.ReplicateApiToken`;
- `CreateImageRegistrations()` includes Replicate FLUX Schnell;
- credential metadata construction stays declarative and does not instantiate provider clients unnecessarily;
- Replicate is exposed only in managed Vision defaults, not native/MCP/native bridge surfaces.

`VisionHandlerTests` should prove:

- `list_image_models` includes Replicate with `submission_mode = "async_image_job"`;
- Gemini/fal descriptors remain `submission_mode = "sync"`;
- missing Replicate token reports `missing_required_secret`;
- present Replicate token reports available-but-unverified and remains listed;
- provider secret set/clear accepts Replicate;
- provider secret ops reject cross-provider keys;
- `test_provider_secret(provider_name: "replicate")` returns `inconclusive`;
- Replicate key testing does not invoke `ReplicateApiClient` prediction HTTP or any generation/spend endpoint.

`ImageJobOpHandlerTests` or focused image-job tests should prove:

- prompt-only `image_generate_start` works for async T2I Replicate;
- missing `input_image_path` remains rejected for sync `generate`;
- references are rejected for Replicate before submit;
- supplied source media is rejected for Replicate before submit when `supports_image_to_image = false`;
- fake HTTP path submits, polls, authenticates output fetch, materializes a local artifact, and returns the artifact id.

Existing PR-13 Replicate provider fake-HTTP tests remain the provider-level safety net.

### UI And Resource Tests

UI/resource tests should prove:

- `app.js` consumes backend `submission_mode`;
- no provider/model-id hardcoded async allowlist exists for Replicate routing;
- Generate calls `image_generate_start` for async image models;
- Generate does not call `generate` for Replicate;
- Generate disables source/reference controls for T2I-only async models;
- Generate status area renders async image job states;
- Studio keeps T2I-only models visible but disabled/incompatible;
- Replicate Settings card appears;
- Settings `Test` maps Replicate to inconclusive/non-spend behavior.

### Boundary Scans

Verification must include source scans proving:

- no PR-14 changes under `src/RookNative/**`;
- no PR-14 changes under `mcp_server/**`;
- `image_generate_start`, image job ops, and provider credential ops are not added to native public route registration;
- image job ops and provider credential ops are not added to `NativeGhBridgeRegistrar`;
- no provider token or `replicate.delivery` URL appears in job responses, artifact metadata, native code, MCP code, or durable serialized payloads.

## Optional Manual Smoke

Normal verification uses fake HTTP only.

No live Replicate calls run by default. A live smoke is optional, manual, and requires explicit user approval immediately before running.

Preconditions:

- focused fake-HTTP Replicate/image-job/UI tests pass;
- a real Replicate token is configured;
- model is `black-forest-labs/flux-schnell`;
- prompt-only Generate flow is selected.

Scope:

- one low-cost prompt-only run;
- no reference images;
- no Studio path;
- no extra models;
- no repeated benchmarking.

Smoke goal:

- prove Settings presence gating;
- prove `image_generate_start` routing;
- prove polling;
- prove authenticated output copy from Replicate;
- prove local artifact rendering;
- prove no provider URL or secret in durable metadata.

This smoke is not part of automated tests, CI, or the merge acceptance gate.

## PR-14a Follow-Up

PR-14 intentionally takes the smallest coherent visible Replicate slice. It makes prompt-only Replicate honest and usable in Generate, but it does not settle the full RookVision mode model.

Record PR-14a as a likely follow-up before PR-15 if the Generate-only path creates visible UX friction.

Potential PR-14a scope:

- explicit text-to-image vs image-to-image mode control;
- clearer source/reference compatibility presentation;
- whether Studio is an edit workspace, a general image lab, or mode-driven;
- async image job progress and cancellation affordances across the full Vision UI;
- whether more model families need a consistent mode/picker design before image job durability work.

PR-15 remains image job durability and restart recovery, but PR-14a may be the better next PR if user-visible workflow friction should be resolved before durability.

## Acceptance Criteria

- Replicate appears as a Settings credential owner.
- Replicate credential save/clear works through provider-aware ops.
- Replicate credential test returns inconclusive without spend/generation.
- `black-forest-labs/flux-schnell` appears in `list_image_models`.
- Replicate descriptor has `submission_mode = "async_image_job"`.
- Gemini/fal descriptors remain `submission_mode = "sync"`.
- Missing Replicate token keeps the model visible but not submittable.
- Present Replicate token allows prompt-only Generate submission.
- Generate routes Replicate through bridge-only image job ops.
- Completed Replicate outputs are copied into local artifacts before result display.
- Generate source/reference controls are disabled for T2I-only Replicate.
- Studio does not gain prompt-only behavior and marks Replicate incompatible/disabled.
- Existing sync `generate` behavior remains source-image based.
- No provider URL or secret leaks into durable metadata or responses.
- No native, MCP, public HTTP, or `NativeGhBridgeRegistrar` exposure is added.
- Normal tests use fake HTTP only.

## Self-Review

- Scope is managed Vision only.
- The first visible Replicate path is honest prompt-only T2I in Generate.
- Studio remains unchanged except for incompatibility/disabled presentation.
- `submission_mode` is backend-owned and provider-neutral.
- Prompt-only support is tied to `async_image_job`, not all T2I-capable models.
- Replicate key testing is non-spend and inconclusive.
- Optional live smoke is documented as explicit-approval only.
- PR-14a is recorded as the mode-UX follow-up if needed before PR-15.
