# PR-10 Replicate Substrate Design

Date: 2026-04-30

## Goal

PR-10 proves Replicate as the second aggregator substrate after fal.ai without making Replicate user-visible.

The slice should validate Replicate's prediction lifecycle, Bearer auth, endpoint shape, handle semantics, output-file contract, error mapping, and approximate pricing metadata against the existing generation seams. It should not add a Replicate image model to the picker, should not add a Replicate Settings card, and should not decide async image UX or authenticated artifact materialization.

## Background

PR-9 made provider-aware credential operations and image catalog enumeration canonical for the Vision panel, while keeping credential ops managed bridge-only. PR-10 should preserve those semantics.

Current code constraints:

- `VisionHandler.GenerateAsync` still expects image providers to return `SyncSubmitOutcome`; it rejects async image providers with "Provider returned an async job."
- `ImageArtifactMaterializer` fetches remote image artifacts without provider authentication.
- Replicate predictions are async-shaped and their file outputs require an authenticated fetch.
- `GenerationSecretKeys.ReplicateApiToken` already exists, but Replicate is not currently a credential-owner provider in the default metadata catalog.

Current Replicate HTTP docs state:

- API requests require `Authorization: Bearer <token>`.
- `Prefer: wait` can leave the request open for up to 60 seconds; if the model is not done, the prediction must be retrieved later.
- Prediction statuses include `starting`, `processing`, `succeeded`, `failed`, and `canceled`.
- Successful file outputs are HTTPS URLs and require the Authorization header when fetched.
- Terminated predictions include `metrics.predict_time`; docs also describe `metrics.total_time`.
- API-created prediction inputs, outputs, output files, and logs are removed after about an hour by default, so Rook must copy any output it wants to keep.

Sources:

- https://replicate.com/docs/reference/http/
- https://replicate.com/docs/topics/predictions/data-retention

## Non-Goals

- No user-visible Replicate image or video model.
- No default Replicate provider registration in image or video registries.
- No Replicate Settings card.
- No Replicate entry from `VisionProviderRegistrations.CreateCredentialMetadata()`.
- No `set_provider_secret` support for `provider_name: "replicate"` through the default UI metadata path.
- No native route changes and no edits under `src/RookNative/**`.
- No async image job UX.
- No blocking-poll image bridge.
- No production authenticated artifact materializer wired into `ImageArtifactMaterializer`.
- No dynamic catalog discovery.
- No Tencent, 3D, or new fal model work.
- No live Replicate calls or spend/network tests without explicit approval.

## Architecture

PR-10 adds a managed-only Replicate substrate under `src/Rook/Services/Vision/Replicate/**`.

The substrate should include a `ReplicateApiClient` for prediction API calls. This client owns Bearer auth, JSON request dispatch, response-header capture, and API-host validation. Prediction API calls are restricted to `https://api.replicate.com`; output files are not API-host calls and must not be folded into that same host contract.

PR-10 should use the official-model prediction endpoint only:

```text
POST https://api.replicate.com/v1/models/{model_owner}/{model_name}/predictions
GET  https://api.replicate.com/v1/predictions/{prediction_id}
POST https://api.replicate.com/v1/predictions/{prediction_id}/cancel
```

Official-model endpoint construction must validate `model_owner` and `model_name` as path segments, not raw path fragments. Empty values and path/query/fragment injection characters such as `/`, `?`, and `#` are invalid. The implementation should use segment-safe construction such as `Uri.EscapeDataString` after validation.

Generic `/v1/predictions` support is deferred unless the implementation also adds focused tests for that endpoint and its `version` body shape. The design target is official-model-only because it matches the Phase 0 FLUX schnell evidence and keeps PR-10 from becoming a broad catalog integration.

The substrate should include an authenticated output-fetch proof seam, not a production materializer. Its purpose is to prove request construction for Replicate file outputs: `replicate.delivery` and subdomains require Bearer auth and are distinct from `api.replicate.com`. PR-10 should not wire this into `ImageArtifactMaterializer`; the next visible Replicate model design must decide where authenticated output fetch lives.

Replicate token handling is intentionally internal to the substrate slice:

- `GenerationSecretKeys.ReplicateApiToken` is a known secret key and may be used in substrate tests or injected fixtures.
- Replicate is not a credential-owner provider in the default metadata catalog for PR-10.
- `VisionProviderRegistrations.CreateCredentialMetadata()` remains Gemini + fal only.
- Default `set_provider_secret` behavior rejects `provider_name: "replicate"` because Replicate is absent from the credential metadata catalog.

## Lifecycle Mapping

Replicate prediction status maps to existing generation outcomes:

| Replicate status | Rook outcome |
|---|---|
| `starting` | `InFlightStatusOutcome(GenerationLifecycleState.Pending, progress)` |
| `processing` | `InFlightStatusOutcome(GenerationLifecycleState.Running, progress)` |
| `succeeded` | `ProviderCompleteStatusOutcome(updatedHandle)` |
| `failed` | `FailedStatusOutcome(error)` based on Replicate's `error` field |
| `canceled` | `FailedStatusOutcome(non-retryable canceled/interrupted-style error)` |

`failed` and `canceled` must not collapse into one bucket. A failed prediction means Replicate/model execution failed or a dependency error occurred; a canceled prediction means the job was intentionally or externally stopped and should map to a non-retryable cancellation/interruption-style generation error.

## Prediction Handle Mapping

Replicate handles should map to `ProviderJobHandle` as follows:

- `ProviderJobId = prediction.id`
- `StatusUrl = prediction.urls.get`
- `CancelUrl = prediction.urls.cancel`
- `CancelHttpMethod = "POST"`
- `ResponseUrl = null`
- `ProviderResultToken` may carry the selected single output URL only for descriptor-specific tests such as a FLUX schnell-shaped single URL result.
- `ProviderMetadata` preserves terminal `output`, `metrics`, `model`, `version`, `data_removed`, and useful URL fields.

Terminal output cardinality must be preserved. Replicate `output` can be a string, array, object, null after data removal, or another JSON shape depending on the model. PR-10 must not encode "Replicate output is always one URL" into shared substrate types. If a test descriptor extracts a single URL into `ProviderResultToken`, the full raw output still belongs in provider metadata.

Replicate logs are omitted by default. They may be captured only as sanitized/truncated provider detail in focused tests, because logs can be bulky and can include prompt, input, or model-debug details.

## Pricing Metadata

PR-10 should add an approximate Replicate pricing model or helper that extracts actual runtime metadata from prediction bodies:

- `metrics.predict_time` is CPU/GPU execution time in seconds.
- `metrics.total_time` is wall-clock prediction completion time when present.
- Estimates are approximate because hardware rate, queueing, and model-specific billing are not fully captured by the generic prediction envelope.

No UI cost display changes ship in PR-10.

## Error Mapping

Replicate error mapping should preserve provider detail without leaking raw envelopes into public route contracts.

Expected mappings:

- Missing token: `DependencyUnavailable`, non-retryable.
- HTTP 401/403: `DependencyUnavailable`, non-retryable, provider detail preserved.
- HTTP 429 or quota/billing-shaped failures: `QuotaExceeded` where distinguishable; retryability depends on provider detail.
- HTTP 5xx or network failure: `DependencyUnavailable`, retryable.
- Request-shape validation errors: `InvalidRequest`, non-retryable.
- Prediction `failed`: `ExecutionFailed` or `DependencyUnavailable` based on the Replicate `error` field and available status/body detail.
- Prediction `canceled`: non-retryable canceled/interrupted-style `GenerationError`.
- Output removed (`data_removed: true`): non-retryable `DependencyUnavailable` with a message that the provider output expired before Rook copied it.
- `succeeded` with `output: null` and `data_removed != true`: `ExecutionFailed`, because that is a malformed or unexpected success envelope rather than a retention-expiry case.

## Testing Strategy

Backend tests should cover:

- Bearer auth is applied to create/get/cancel prediction API calls.
- Prediction API calls reject hosts other than `api.replicate.com`.
- Official-model owner/name endpoint construction rejects empty values and path/query/fragment injection characters such as `/`, `?`, and `#`.
- Authenticated output-fetch proof is separate from API calls and allows only exact `replicate.delivery` or suffix `.replicate.delivery` hosts with Bearer auth.
- Output-host validation rejects substring lookalikes such as `replicate.delivery.evil.test`.
- Official-model create endpoint and body shape.
- Generic `/v1/predictions` is absent or explicitly unsupported unless it has tests.
- `starting`, `processing`, `succeeded`, `failed`, and `canceled` lifecycle mapping.
- `succeeded` maps `urls.get`/`urls.cancel`/`id` into `ProviderJobHandle` correctly and keeps `ResponseUrl = null`.
- Cancel uses HTTP `POST`.
- Prediction `output` is preserved as raw JSON metadata for string, array, object, and null shapes.
- A single-output descriptor test may stamp one URL into `ProviderResultToken`, while still preserving full output metadata.
- `metrics.predict_time` and `metrics.total_time` extraction.
- Error mapping for auth, validation, rate/quota, server, failed prediction, canceled prediction, and data-removed output.
- `GenerationSecretKeys.ReplicateApiToken` can be used by injected substrate fixtures.
- `VisionProviderRegistrations.CreateCredentialMetadata()` remains Gemini + fal only.
- Default provider-secret operations still reject Replicate through metadata absence.
- No hits under `src/RookNative/**` for Replicate credential or provider-route additions.

No normal test should perform live Replicate network calls. Any live smoke must be opt-in, separately approved, and recorded as such.

## Acceptance Criteria

- Replicate substrate types and tests compile in managed code.
- No production Replicate model appears in image or video catalogs.
- No Replicate Settings card appears.
- `list_image_models` remains Gemini + fal only unless tests use explicitly injected registries.
- `set_provider_secret` cannot set `replicate.api_token` through the default metadata path.
- Existing Gemini and fal behavior remains unchanged.
- Existing PR-9 credential semantics remain binding: provider-aware ops are canonical, legacy Gemini ops are shims only, validation state is not persisted, `InvalidCredential` is warning-only, and `MissingRequiredSecret` remains the deterministic blocker.
- Async image UX and authenticated artifact materialization are documented as follow-up design questions, not hidden PR-10 implementation work.

## Follow-Up Decisions

Before a user-visible Replicate image model ships, a later design must answer:

- Are image jobs becoming async like video jobs?
- If not, what happens when `Prefer: wait` exceeds bridge timeout or cold start exceeds 60 seconds?
- Where does authenticated output-file fetch live without persisting provider secrets into artifact metadata or ledgers?
- How does Rook copy Replicate outputs before the default retention window removes them?
- Does a text-to-image-only model require a no-source workflow, or does the current Vision UI continue to require a viewport/source image?
- When should Replicate become a credential-owner provider in Settings?

## Self-Review

- Scope is managed-only.
- Replicate is substrate-only and not user-visible.
- API host and output host contracts are separate.
- Official-model endpoint is the only endpoint mode in scope.
- Output cardinality is preserved.
- `failed` and `canceled` are mapped distinctly.
- No 3D, Tencent, dynamic catalog, visible picker filters, native routes, or new fal models are included.
