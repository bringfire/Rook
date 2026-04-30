# PR-11 Replicate Async Image And Materialization Design

Date: 2026-04-30

## Goal

PR-11 is a design-only decision PR for making Replicate image generation user-visible later without baking provider-specific assumptions into the image path.

The design resolves the contracts blocked by PR-10:

- image providers can be async, but `VisionHandler.GenerateAsync` currently accepts only `SyncSubmitOutcome`;
- Replicate output files require authenticated fetch, while `ImageArtifactMaterializer` currently performs unauthenticated remote GETs;
- Replicate outputs expire after a short default retention window, so Rook must copy outputs promptly;
- Replicate is not yet a Settings credential owner, so the UI cannot configure `replicate.api_token`.

No production code, UI, native route, provider registration, or test behavior changes ship in PR-11.

## Background

PR-10 added the managed Replicate substrate under `Rook.Services.Vision.Replicate` and deliberately kept it hidden from user-facing model catalogs and Settings. That was the right boundary: it proved prediction lifecycle, official-model endpoint construction, Bearer auth, error mapping, timing metadata, handle semantics, and authenticated output-fetch request construction without deciding the user-visible async image contract.

The current image route is still synchronous from the Vision panel's perspective. It submits to an image provider, requires a `SyncSubmitOutcome`, materializes the returned artifact, writes it to `ArtifactStore`, and returns the existing generated-image response. That path fits Gemini inline bytes and fal sync image URLs. It does not fit Replicate predictions, where submit returns a prediction handle and output URLs are available only after polling.

## Non-Goals

- No production code.
- No Replicate image model registration.
- No Replicate Settings card or credential owner entry.
- No native route changes.
- No changes under `src/RookNative/**`.
- No live Replicate calls.
- No dynamic catalog discovery.
- No 3D, Tencent, webhook, or streaming implementation.
- No change to fal or Gemini behavior.

## Decision Summary

1. **Use first-class image jobs, not a blocking fallback.**
   Replicate image generation should use an image job contract rather than trying to hide async predictions behind `GenerateAsync`.

2. **Create an image-specific job manager first.**
   Reuse video job concepts and tests where they fit, but do not generalize `VideoJobManager` into a cross-modality manager in the first implementation PR. Extract common helpers only after image jobs and video jobs both prove the shared shape.

3. **Provider-owned authenticated fetch context feeds manager-owned materialization.**
   Providers or provider substrates may construct authenticated request factories or fetch context using their secret, but they do not perform the artifact byte read and do not write Rook artifacts. The image job manager and materializer remain responsible for network reading, size limits, MIME resolution, retry/error classification, and `ArtifactStore` writes.

4. **Copy Replicate outputs immediately after provider completion.**
   A job is not complete when Replicate reports `succeeded`; it is complete only after Rook has fetched and stored the output locally.

5. **Replicate becomes a Settings credential owner in the first user-visible Replicate PR.**
   Hidden backend substrate can use injected secrets in tests, but any visible Replicate model requires `VisionProviderRegistrations.CreateCredentialMetadata()` to expose Replicate credentials and the Settings UI to render the provider card.

## Async Image Contract

PR-12 should add a first-class image job API inside the managed Vision bridge. The managed bridge response shape should mirror the existing video job lifecycle closely enough to be learnable, but remain image-specific where response payloads differ.

Expected managed bridge ops:

- `image_generate_start`
- `image_job_status`
- `image_job_cancel`
- `image_job_result`
- `image_jobs`

These names are the design target for PR-12. Do not overload the existing `generate` op with a "maybe job, maybe artifact" response because that would force every existing caller and test to handle two incompatible response shapes.

`generate` remains the synchronous image path for Gemini and fal sync image. Replicate models should not be routed through `generate` until the UI explicitly uses the job ops.

Image job states should follow the existing generation lifecycle vocabulary:

- queued or submitted;
- running;
- provider-complete but materializing;
- complete;
- failed;
- canceled.

The important distinction is `provider-complete but materializing`. Replicate `succeeded` means the provider has output available. Rook still needs to fetch and persist the output before the user can rely on the artifact.

## ImageJobManager Shape

PR-12 should add an `ImageJobManager` rather than immediately generalizing the video manager.

The manager owns:

- job IDs and in-memory running-job state;
- submit, poll, fetch, materialize, and cancel orchestration;
- bounded concurrency;
- job status snapshots;
- final `ArtifactStore` writes;
- error mapping from provider outcomes and materializer failures into image job responses.

The manager consumes existing `IImageProvider` registrations. It should support both `SyncSubmitOutcome` and `QueuedSubmitOutcome` so it can run Gemini/fal through the same machinery in tests, but PR-12 does not need to move existing `generate` callers onto the manager.

The manager should use image-specific job records first. Do not reuse `VideoJobRecord` or write video-shaped metadata names into image ledgers. A later refactor may extract a generic job-record core after both modalities have stable requirements.

PR-12 should start with an in-memory job manager plus persisted final artifacts, not durable restart/resume. Replicate retention is short enough that stale restart recovery would be unreliable without a broader retry and expiry policy. Durable image job ledgers can be revisited after the first visible Replicate workflow proves the need.

## Authenticated Materialization

`ImageArtifactMaterializer` should remain responsible for turning `ResultArtifact` values into bytes and MIME metadata, but it needs an authenticated fetch extension point before Replicate can be user-visible.

Recommended contract:

- keep unauthenticated remote GET as the default path for fal and other public artifact URLs;
- add an optional provider request factory or artifact-fetch context that can build provider-authenticated requests for selected remote artifact hosts;
- keep the materializer or job-manager-owned fetch service responsible for sending the request, reading the response stream, enforcing byte limits, resolving MIME, and classifying HTTP/transport failures;
- do not store provider secrets in artifact metadata, ledgers, or provider metadata;
- do not expose signed or authenticated provider URLs as durable Rook artifact identities;
- write only local artifact IDs and safe provider audit metadata.

For Replicate, authenticated request construction should be routed through the Replicate provider/substrate using `GenerationSecretKeys.ReplicateApiToken`. The existing `ReplicateApiClient.BuildAuthenticatedOutputRequest` proof seam can become the lower-level request builder, but production materialization must own request sending, response size limits, MIME resolution, retry classification, and byte copying.

Materialization failure after provider success is a job failure, not a successful generation. If Replicate reports `succeeded` but Rook cannot fetch before expiry, the job should fail with a non-retryable dependency error that explains the output expired before Rook copied it.

## Retention Copy Timing

Replicate output retention makes immediate copy part of the job contract.

After a Replicate prediction reaches `succeeded`:

1. The provider maps terminal output into a `ProviderCompleteStatusOutcome` and preserves raw output metadata.
2. The job manager calls `FetchResultAsync`.
3. The provider returns `ResultArtifact` entries with remote bodies and enough metadata for authenticated fetch selection.
4. The materializer fetches bytes immediately, using Replicate auth for `replicate.delivery` hosts.
5. The manager writes local artifacts before marking the image job complete.

No UI should present a Replicate output URL as a durable result. The durable result is only the local Rook artifact.

## Settings Credential Ownership

Replicate should become a Settings credential owner only in the first PR that makes Replicate models visible to users. That PR should add:

- Replicate credential metadata with provider name `replicate`;
- required secret `GenerationSecretKeys.ReplicateApiToken`;
- Settings card rendering through the existing provider-card path;
- provider-aware set, clear, and test behavior for Replicate;
- picker availability derived from missing/present Replicate token state.

PR-12 may implement hidden backend job substrate with injected stores and fake providers, but default UI metadata should continue rejecting `provider_name: "replicate"` until a visible model PR intentionally changes that boundary.

Replicate test-key behavior should be non-generation and non-spend where possible. If no reliable non-spend proof exists, the Settings operation should return `inconclusive` rather than pretending a present token is valid.

## Bridge And UI Implications

The Vision UI needs explicit async image behavior before Replicate models are exposed:

- starting a Replicate image generation creates a job and shows progress/status;
- cancellation is available while the job is pending/running/materializing;
- completed jobs surface the same gallery/artifact affordances as sync images;
- failures distinguish provider failure, cancellation, auth failure, retention expiry, and materialization failure where possible.

The model picker should not silently route Replicate through the existing synchronous Generate button. If the selected model uses async image jobs, the UI should call the image job start op and then poll. This keeps the response shape predictable and avoids bridge timeouts on cold or slow predictions.

## Implementation Split

### PR-12 — Hidden image job substrate

Scope:

- add `ImageJobManager` and image job result/status types;
- add managed bridge ops for image jobs;
- add fake-provider tests covering sync and async image providers;
- add authenticated materialization extension point with fake authenticated fetch tests;
- keep Replicate absent from default Settings and picker metadata.

Acceptance:

- existing `generate` behavior remains unchanged;
- image jobs can submit, poll, fetch, materialize, cancel, and report failures through fake providers;
- no production Replicate model appears in `list_image_models`;
- default provider-secret operations still reject Replicate.

### PR-13 — Replicate image provider hidden registration tests

Scope:

- add Replicate image provider/registration behind injected or test-only registries;
- map official FLUX schnell-style prediction input/output into image job flow;
- use authenticated Replicate output materialization;
- no default UI exposure.

Acceptance:

- Replicate async prediction lifecycle works with fake HTTP;
- retention-expired output maps to the documented non-retryable dependency error;
- output cardinality is preserved in provider metadata;
- no live calls in normal tests.

### PR-14 — Replicate Settings and visible image model

Scope:

- expose Replicate as a Settings credential owner;
- add Replicate card and provider-aware credential operations;
- register one conservative Replicate image model;
- wire UI model selection to image job ops for async models;
- optionally run an approved live smoke with a real key.

Acceptance:

- missing Replicate token keeps model visible but not submittable;
- present token allows job start;
- completed Replicate outputs are copied into local artifacts;
- no provider URL or secret leaks into durable metadata.

## Testing Strategy

Design review for PR-11 should verify that each later implementation PR has a crisp boundary and no hidden UI exposure.

PR-12 tests should cover:

- async image submit returns a job instead of failing with "Provider returned an async job";
- existing `generate` still rejects async providers until UI calls job ops;
- provider-complete is not job-complete until materialization succeeds;
- cancellation before provider completion and during materialization;
- materialization failure after provider success;
- authenticated fetch delegate is used only for matching provider-owned artifacts;
- secret values are not serialized into job records or artifact metadata.

PR-13 tests should cover:

- Replicate `starting`, `processing`, `succeeded`, `failed`, and `canceled` through image jobs;
- authenticated `replicate.delivery` fetch;
- output host lookalike rejection;
- `data_removed: true` retention expiry;
- raw output metadata preservation for string, array, object, and null output shapes.

PR-14 tests should cover:

- Replicate credential metadata appears only when intentionally exposed;
- provider-aware credential operations accept Replicate only after metadata exposure;
- picker availability reflects missing/present Replicate token state;
- UI uses image job ops for async models.

## Review Invariants

- PR-11 is docs-only.
- Replicate image models are not visible until Settings credential ownership and async image UI are implemented.
- Existing synchronous image generation remains compatible.
- `ProviderCompleteStatusOutcome` is not treated as a local artifact success.
- Authenticated output fetch never persists provider secrets.
- Replicate output URLs are copied into local artifacts before completion.
- PR-12 image job ops are managed-bridge-only; no native route changes are needed unless a later native/MCP parity PR explicitly scopes public HTTP exposure.
- Do not generalize video and image job managers before image-specific requirements are proven.

## Self-Review

- The design chooses first-class image jobs over blocking `Prefer: wait`.
- The implementation split keeps hidden backend substrate separate from visible Replicate exposure.
- Materialization ownership is manager-owned and provider-auth-aware without letting providers write artifacts.
- Settings credential ownership remains tied to user-visible model exposure.
- The spec does not include production code, native changes, dynamic catalogs, 3D, Tencent, or live-provider tests.
