# PR-13 Hidden Replicate Image Provider Design

Date: 2026-05-01

## Goal

PR-13 adds a hidden production Replicate image provider path and proves it through fake HTTP and injected registries.

The slice should turn the PR-10 Replicate substrate and PR-12 hidden image job substrate into a real image-provider integration for one conservative model, `black-forest-labs/flux-schnell`, without exposing Replicate through default app wiring.

PR-13 is intentionally not a visibility PR. Replicate remains absent from Settings, picker metadata, default image catalogs, native routes, MCP tools, and credential-owner metadata.

## Background

PR-10 added the managed Replicate substrate under `Rook.Services.Vision.Replicate`. It proved Bearer-authenticated prediction calls, official-model endpoint construction, lifecycle/error mapping, handle semantics, pricing/timing metadata extraction, and authenticated output-request construction.

PR-11 decided that user-visible Replicate image generation should use first-class image jobs instead of trying to hide async predictions behind the synchronous `generate` op.

PR-12 added the hidden image job substrate: `ImageJobManager`, managed-bridge-only image job ops, fake sync/async provider coverage, authenticated materialization request-factory selection, cancellation/materialization race coverage, and guard tests proving image job ops are not exposed through native, MCP, or `NativeGhBridgeRegistrar`.

PR-13 consumes those foundations by adding the first real Replicate image provider implementation while preserving the hidden boundary. This keeps PR-14 focused on Settings, picker visibility, and UI job workflow wiring instead of first discovering provider integration risks.

## Non-Goals

- No default Replicate image registration in `VisionProviderRegistrations.CreateImageRegistrations(...)`.
- No Replicate Settings card.
- No Replicate credential metadata from `VisionProviderRegistrations.CreateCredentialMetadata()`.
- No default `set_provider_secret` support for `provider_name: "replicate"`.
- No UI picker exposure.
- No native route changes and no edits under `src/RookNative/**`.
- No MCP tools.
- No `NativeGhBridgeRegistrar` exposure.
- No changes to existing synchronous `generate` behavior.
- No image-to-image support for Replicate.
- No provider-specific user knobs in Replicate image options.
- No dynamic Replicate catalog discovery.
- No additional Replicate models.
- No generic model-agnostic create-prediction endpoint support.
- No live Replicate calls or spend/network tests without explicit approval.

## Architecture

PR-13 adds a hidden production Replicate image provider slice under `src/Rook/Services/Vision/Image/Replicate`, but no production composition path exposes it. The provider is production code, but it is test-reachable only through explicitly injected registries, not through default app wiring. The provider is reachable only when a caller explicitly constructs a registry containing `ReplicateImageProviderRegistration`, as PR-13 tests do.

The slice adds:

- `ReplicateImageProvider`
- `ReplicateImageProviderRegistration`
- `ReplicateImageCapabilities`
- `ReplicateImageOptions`
- `ReplicateImageOptionsCodec`
- a small internal FLUX-schnell profile/request mapper

It reuses the existing substrate in `src/Rook/Services/Vision/Replicate` for API calls, endpoint construction, lifecycle/error mapping, pricing/timing metadata, and authenticated output-request construction.

Default composition stays unchanged: `VisionProviderRegistrations.CreateImageRegistrations(...)` remains Gemini + fal only, and `CreateCredentialMetadata()` still omits Replicate.

No native route, MCP tool, Settings card, or UI picker exposure changes in PR-13.

## Provider Contract

The only hidden Replicate image model in PR-13 is:

```text
black-forest-labs/flux-schnell
```

Its capability contract is:

- `ProviderName = "replicate"`
- `MaxReferenceImages = 0`
- `SupportsTextToImage = true`
- `SupportsImageToImage = false`
- supported resolution is `"1K"` as Rook-side catalog metadata
- supported aspect ratios are `1:1`, `4:3`, `3:4`, `16:9`, and `9:16`

If Rook receives a blank aspect ratio, PR-13 normalizes it to `1:1` before building the Replicate request body.

`ReplicateImageOptionsCodec` accepts an empty options object only. It validates `number_of_images == 1`, validates Rook resolution/aspect ratio against the capability, and rejects `reference_image_paths` with `field = "reference_image_paths"` before any Replicate HTTP request.

Resolved media that exists because of the current bridge shape is not consumed as Replicate input in PR-13. Only `request.ReferenceImages` is the explicit image-to-image rejection surface.

## Request Body

PR-13 uses the official-model prediction endpoint only:

```text
POST https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions
```

The outgoing Replicate create body is exactly:

```json
{
  "input": {
    "prompt": "...",
    "aspect_ratio": "1:1",
    "num_outputs": 1,
    "output_format": "png"
  }
}
```

`number_of_images` must remain `1` and maps to `num_outputs: 1`.

`resolution` is validated/cataloged on the Rook side but is not sent to Replicate in PR-13.

No Replicate-specific user knobs are exposed in `ReplicateImageOptions` for PR-13. Internally, the provider should still use a small model profile for model id, endpoint, capability, pricing, and request-body mapping so future Replicate models can be added without scattering model-specific conditionals through the provider.

## Lifecycle

`ReplicateImageProvider.SubmitAsync` creates an official-model prediction for `black-forest-labs/flux-schnell` and returns `QueuedSubmitOutcome` with the Replicate handle.

`GetStatusAsync` delegates to the existing Replicate lifecycle mapper for state mapping and raw metadata preservation. `data_removed: true` remains on the status path: if Replicate reports retention expiry before or at terminal poll, the job fails directly with the existing non-retryable `DependencyUnavailable` retention-expiry error instead of becoming a later fetch or materialization failure.

`CancelAsync` uses the Replicate cancel endpoint and preserves Replicate's `POST` cancel contract.

`FetchResultAsync` applies the FLUX-schnell image profile and returns `SuccessResultOutcome` only when the terminal handle/metadata contains exactly one usable image URL.

For this model profile:

- accept `output: "https://..."`
- accept `output: ["https://..."]`
- reject `output: []`, multiple URLs, object output, non-URL output, missing output, and null output
- reject unsupported output shapes as non-retryable `ExecutionFailed`
- preserve raw `output`, `metrics`, `model`, `version`, and `urls` in provider metadata

The generic Replicate substrate preserves provider truth. The FLUX-schnell image profile decides whether the terminal output is materializable as an image.

## Authenticated Materialization

Replicate result artifacts are remote image artifacts with `requires_authenticated_fetch: true` in provider metadata.

`ImageJobManager` uses a request-factory selector that authenticates only when both conditions hold:

- `ResolvedImageModel.ProviderName == "replicate"`
- the artifact body is `RemoteArtifactBody`

The selector builds authenticated output GET requests through:

```csharp
ReplicateApiClient.BuildAuthenticatedOutputRequest(apiToken, outputUrl)
```

Selector behavior is explicit:

- non-Replicate providers do not receive Replicate authentication
- non-remote authenticated artifacts fail non-retryably
- missing Replicate token fails before output fetch with non-retryable `DependencyUnavailable`
- malformed or unsafe output URLs fail before network I/O as non-retryable `ExecutionFailed`
- invalid hosts such as `replicate.delivery.evil.test` and invalid schemes such as `http://replicate.delivery/...` send no output-fetch HTTP request

The materializer still owns HTTP sending, byte limits, MIME resolution, failure classification, and final local artifact bytes. No provider token, signed URL, or secret-bearing request is persisted.

## Testing Strategy

PR-13 tests use fake HTTP only. No normal test makes live Replicate calls.

Provider and registration tests should cover:

- `ReplicateImageProviderRegistration` exposes only `black-forest-labs/flux-schnell`.
- An injected `DefaultImageProviderRegistry` resolves the Replicate model.
- `ReplicateImageOptionsCodec` accepts empty options only.
- Reference images fail validation with `field = "reference_image_paths"`.
- Validation failure sends no Replicate HTTP request.
- Blank aspect ratio normalizes to `1:1`.
- Submit sends Bearer auth and the exact official-model endpoint/body shape.
- Cancel uses Replicate `POST`.
- `FetchResultAsync` rejects unsupported terminal output shapes: empty array, multiple URLs, object output, null/missing output, and non-URL output.

Image job integration tests should cover:

- text-to-image request drives submit, poll, fetch, authenticated materialization, and local artifact creation through fake HTTP.
- `starting` and `processing` remain in-flight image job states.
- `succeeded` can produce a terminal handle, but FLUX-schnell output extraction is enforced in `FetchResultAsync`.
- `failed`, `canceled`, and `data_removed: true` map to the documented job failures.
- successful output fetch from `replicate.delivery` includes Bearer auth added only through the manager selector.
- missing Replicate token in the request-factory selector fails before output fetch and sends no network request.
- unsafe output hosts and schemes fail before output-fetch network I/O.

Boundary tests and scans should cover:

- `VisionProviderRegistrations.CreateImageRegistrations(...)` still omits Replicate.
- `CreateCredentialMetadata()` still omits Replicate and `GenerationSecretKeys.ReplicateApiToken`.
- default `list_image_models` still omits Replicate.
- default provider-secret operations still reject `provider_name: "replicate"`.
- no token appears in job status/result responses, artifact metadata, provider metadata persisted into artifacts, or assertion-captured serialized payloads.
- no PR-13 exposure under `src/RookNative/**`, MCP server files, UI resources, `NativeGhBridgeRegistrar`, or default provider registration/credential metadata.

## Acceptance Criteria

- Production Replicate image provider code exists under `src/Rook/Services/Vision/Image/Replicate`.
- Tests exercise the real provider, real registration, `DefaultImageProviderRegistry`, `ImageJobManager`, Replicate lifecycle mapping, and authenticated materialization path through fake HTTP.
- The injected test registry can resolve only `black-forest-labs/flux-schnell` for Replicate.
- Default image registrations remain Gemini + fal only.
- Default credential metadata remains Gemini + fal only.
- Default image model listing does not expose Replicate.
- Existing Gemini and fal image behavior remains unchanged.
- Existing synchronous `generate` behavior remains unchanged.
- No native, MCP, Settings, picker, or `NativeGhBridgeRegistrar` exposure is added.
- No live provider calls run in normal tests.
- No provider secret is persisted into job responses, artifact metadata, provider metadata persisted into artifacts, or durable serialized payloads.

## Follow-Up

PR-14 should make Replicate user-visible by adding Settings credential ownership, one visible image model, provider-aware credential operations, and UI routing through image job ops for async models.

Future Replicate image-to-image support needs a separate design because it introduces separate risk: input schema, media upload/reference handling, secret-safe request construction, validation semantics, and UI affordances.

Future additional Replicate models should extend the internal model profile shape rather than adding scattered conditionals to `ReplicateImageProvider`.

## Self-Review

- Scope is a hidden production provider slice.
- Replicate is production-code reachable through explicit registry injection only, not default app wiring.
- Only `black-forest-labs/flux-schnell` is in scope.
- The provider is text-to-image only.
- The external options codec is empty.
- The request body is exact and does not send Rook `resolution`.
- Replicate output authentication uses the PR-12 manager/materializer seam.
- The provider marks authenticated artifacts, but the manager selector owns secret injection.
- The materializer owns byte reads and local artifact creation.
- Unsupported Replicate output shapes fail at the provider/profile layer.
- Retention expiry remains the special `data_removed: true` status-path failure.
- No UI, Settings, native, MCP, dynamic catalog, image-to-image, or live-provider testing is included.
