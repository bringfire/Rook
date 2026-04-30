# PR-8 Design: fal.ai Video Support

**Date:** 2026-04-29
**Status:** approved design, pre-implementation plan
**Scope:** managed-only fal.ai queue video provider for `fal-ai/wan/v2.7/text-to-video`

## Context

PR #125 added the shared fal substrate and provider secret metadata. PR #126
added fal sync image support for `fal-ai/flux/schnell`, remote image artifact
materialization, `VisionHandler` wiring, pricing, and gated live smoke. PR-8 is
the next Phase 2 provider slice: fal queue video through the existing video job
pipeline.

The main risk is not model registration. The risk is proving fal's async queue
and URL result shape inside Rook's existing `/vision/video/*` contract:

- `VideoOpHandler` currently parses provider options through Veo-only options.
- `VideoJobManager` currently completes only from `InlineArtifactBody`.
- `ProviderJobHandle` already has the right shape for fal queue URLs and cancel
  method, so PR-8 should wire that through rather than alter the route boundary.

Current fal docs checked on 2026-04-29:

- `fal-ai/wan/v2.7/text-to-video` is available through the queue API.
- Wan 2.7 T2V pricing is `$0.10/s`.
- T2V supports 720p/1080p, 2-15s duration, and common aspect ratios.
- Queue submit returns `request_id`, `status_url`, `response_url`, and
  `cancel_url`.
- Queue status values include `IN_QUEUE`, `IN_PROGRESS`, and `COMPLETED`.
- `COMPLETED` is terminal provider state, not proof of successful Rook artifact
  completion. Rook success happens only after result fetch and local artifact
  materialization.
- fal result media URLs are temporary/public provider URLs and must be
  downloaded into Rook storage before being treated as durable artifacts.

Reference sources:

- `docs/rook_docs/2026-04-26-generation-provider-framework.md`
- `docs/rook_docs/2026-04-27-multi-provider-spike.md`
- `docs/rook_docs/2026-04-27-multi-provider-phase1-plan.md`
- `docs/rook_docs/2026-04-29-multi-provider-phase2-fal-plan.md`
- fal T2V API: <https://fal.ai/models/fal-ai/wan/v2.7/text-to-video/api>
- fal I2V API, checked only to defer it: <https://fal.ai/models/fal-ai/wan/v2.7/image-to-video/api>
- fal Wan pricing/capabilities: <https://fal.ai/wan-2.7>
- fal queue docs: <https://fal.ai/docs/documentation/model-apis/inference/queue>

## Goals

- Register only `fal-ai/wan/v2.7/text-to-video` as the first fal queue video
  model.
- Preserve existing `/vision/video/*` public route shapes.
- Keep PR-8 managed-only unless implementation discovers a route-boundary
  blocker.
- Add fal video options codec, capabilities, provider registration, provider,
  and pricing.
- Replace Veo-only route option parsing with registry-resolved options
  deserialization.
- Persist fal queue handle URL fields through `VideoJobLedger`.
- Fetch fal remote mp4 output and write the existing `generated_video` artifact
  shape.
- Pin fal terminal/fetch failure behavior.
- Test cancel through fake/provider-level coverage; keep live cancellation
  optional and spend-gated.
- Add an opt-in paid live smoke for fal T2V.

## Non-Goals

- No `fal-ai/wan/v2.7/image-to-video` registration in PR-8.
- No input-media upload or public hosting strategy for fal I2V.
- No `audio_url`, audio input, or audio generation support from the current
  Wan T2V page.
- No negative prompt or prompt-expansion toggle in the public fal video options
  contract.
- No Replicate, Tencent, 3D, dynamic catalog, settings UI, picker UI, or PR-9
  work.
- No `src/RookNative/**` edits unless a route-boundary blocker is proven.
- No broad shared artifact downloader abstraction in PR-8.

## Architecture

PR-8 adds a new modality-specific fal video slice under:

```text
src/Rook/Services/Vision/Video/Fal/
  FalVideoProvider.cs
  FalVideoProviderRegistration.cs
  FalVideoCapabilities.cs
  FalVideoOptions.cs
  FalVideoOptionsCodec.cs
  FalWanT2vPricingModel.cs
```

Shared fal HTTP/error/lifecycle/pricing helpers stay under
`src/Rook/Services/Vision/Fal/`. The video slice consumes those helpers but
does not move shared substrate into the video namespace.

`VideoSubsystemFactory` constructs fal beside Veo:

```csharp
var falVideoProvider = new FalVideoProvider(
    () => generationSecrets.GetSecret(GenerationSecretKeys.FalApiKey));
```

The factory captures the secret-store reference, not a key snapshot, matching
Veo's current lazy lookup behavior.

`DefaultVideoProviderRegistry` then receives both registrations:

- `new VeoProviderRegistration(veoProvider)`
- `new FalVideoProviderRegistration(falVideoProvider)`

Duplicate provider-name behavior and model-id uniqueness remain registry-owned.

## Registered Model

PR-8 registers exactly one fal model:

```text
fal-ai/wan/v2.7/text-to-video
```

Capability shape:

- `ProviderName`: `fal`
- `Modes`: `[T2V]`
- `SupportsReferenceImages`: `false`
- `MaxReferenceImages`: `0`
- `Must8sWith`: `[]`
- `Resolutions`: `720p`, `1080p`
- `Durations`: supported integer seconds from `2` through `15`
- `AspectRatios`: common fal Wan ratios from current docs
- `Status`: preview or stable according to the checked fal catalog descriptor

`fal-ai/wan/v2.7/image-to-video` is deliberately deferred. I2V needs an input
media upload/hosting/materialization strategy because Rook's public video route
accepts `artifact_id` references and resolves them to bytes internally, while
fal I2V expects media URLs such as `image_url`.

## Fal Video Options

`FalVideoOptions` is an empty sealed option shape for PR-8.

`FalVideoOptionsCodec` behavior:

- `Deserialize({})` succeeds.
- Unknown fields fail with `InvalidRequest`.
- `Deserialize({ "negative_prompt": "x" })` fails.
- `Deserialize({ "enable_prompt_expansion": false })` fails.
- `Serialize(new FalVideoOptions())` returns `{}`.
- `Validate(...)` accepts `FalVideoOptions` for the fal T2V capability and
  rejects null or mismatched provider options.

The public route still requires an `options` object. For fal T2V, callers send:

```json
{
  "options": {}
}
```

Missing `options` remains invalid.

## Route Parsing

`VideoOpHandler` changes from unconditional `ParseVeoOptions` to
registry-resolved codec deserialization.

Parsing sequence for submit and estimate:

1. Parse top-level request fields.
2. Resolve `model` through `IVideoProviderRegistry`.
3. Require `options` to be a JSON object.
4. Call `resolved.OptionsCodec.Deserialize(optionsJson)`.
5. Build `VideoGenerationRequest` with the typed provider options.

The parser rejects unknown model and bad options shape. Capability validation
stays in `VideoCostEstimator` and manager flow; the handler must not duplicate
duration/resolution/aspect-ratio validation beyond existing top-level field
presence/type parsing.

Estimate paths may return both `VideoGenerationRequest` and
`ResolvedVideoModel` from the parse helper so the handler does not resolve the
same model twice. Submit can still let `VideoJobManager` re-resolve
authoritatively before queueing work.

Veo request parsing must remain compatible. Existing Veo callers still send
`options.person_generation`.

## Fal Provider Flow

`FalVideoProvider` owns fal protocol only:

- Submit.
- Status.
- Cancel.
- Result fetch and provider-envelope parsing.

It does not write Rook artifacts and does not know about Rook artifact IDs.

### Submit

`SubmitAsync` requires:

- `VideoGenerationRequest` with `FalVideoOptions`.
- Configured fal API key from `GenerationSecretKeys.FalApiKey`.
- A T2V prompt. This is primarily enforced by `CapabilityValidator`, but the
  provider defensively returns typed `InvalidRequest` if called directly without
  a prompt.

The provider posts to:

```text
https://queue.fal.run/fal-ai/wan/v2.7/text-to-video
```

Request body is built from stable top-level Rook fields:

- `prompt`
- `aspect_ratio`
- `resolution`
- `duration`
- `seed`, only when present
- `enable_safety_checker: true`
- `enable_prompt_expansion: true`

PR-8 does not expose `negative_prompt` or `enable_prompt_expansion` as public
options.

Submit success is parsed with `FalLifecycleMapper.ParseSubmitHandle(...)` into
a `ProviderJobHandle` containing:

- `ProviderJobId` from `request_id`
- `StatusUrl` from `status_url`
- `ResponseUrl` from `response_url`
- `CancelUrl` from `cancel_url`
- `CancelHttpMethod` from the implementation-time method verification step
- provider metadata such as queue position and observed status

The Phase 0 Wan video spike captured `cancel_url` but did not live-exercise
cancellation or capture a Wan-specific HTTP method. The implementation plan must
verify the current fal Wan cancel method from official docs, OpenAPI metadata,
or a non-spend characterization before writing provider tests. Once verified,
provider tests pin that method in `ProviderJobHandle`.

### Status

`GetStatusAsync` calls the handle's `StatusUrl` and maps fal state through the
existing lifecycle normalizer.

Rules:

- `IN_QUEUE` maps to pending/in-flight.
- `IN_PROGRESS` maps to running/in-flight.
- `COMPLETED` maps to `ProviderCompleteStatusOutcome(handle)`.
- Provider-complete means "ready to fetch", not "Rook job complete".
- Unknown or malformed status bodies return typed failure outcomes.

### Fetch

`FetchResultAsync` requires `handle.ResponseUrl`. If it is null, the provider
returns `FailedResultOutcome` with `ExecutionFailed` and a sanitized message.
It does not reconstruct fal response URLs from provider job IDs.

The provider GETs `ResponseUrl` through `FalApiClient`, maps non-2xx responses
through `FalErrorMapper`, and parses successful result JSON:

```json
{
  "video": {
    "url": "...",
    "content_type": "video/mp4",
    "duration": 2,
    "fps": 24,
    "num_frames": 48,
    "width": 1280,
    "height": 720
  }
}
```

The result envelope contains one `ResultArtifact`:

- `Role = VideoMediaRoles.Video`
- `Body = RemoteArtifactBody(video.url)`
- `DeclaredMimeType = video.content_type` when present
- provider metadata copied from `video` fields and useful envelope fields such
  as seed or actual prompt when present

### Cancel

`CancelAsync` requires `CancelUrl` and uses the handle's verified
`CancelHttpMethod`. Provider-level tests verify the request method and URL after
the method is verified. Manager-level fake-provider tests remain the primary
cancel contract coverage. Live cancellation characterization is optional and
requires explicit spend approval.

## Video Artifact Materialization

Add a video-specific materializer, not a broad shared downloader abstraction:

```csharp
internal sealed class VideoArtifactMaterializer
{
    internal const long MaxGeneratedVideoBytes = 250L * 1024 * 1024;
}
```

The production default cap is `250 MB`. Tests may inject a smaller cap to avoid
allocating large byte arrays or streams.

The materializer supports:

- `InlineArtifactBody`
- `RemoteArtifactBody`

Rules:

- The cap applies to both inline and remote bodies.
- Inline body over cap fails with non-retryable `ExecutionFailed`.
- Remote downloads use plain `HttpClient`, never fal auth headers.
- Remote downloads use `HttpCompletionOption.ResponseHeadersRead`.
- `Content-Length > cap` fails before body read.
- Missing or incorrect `Content-Length` is handled by enforcing the same cap
  while streaming.
- Empty body fails.
- Exactly the cap is allowed.
- Declared MIME wins over response content type.
- Response content type fills in when declared MIME is absent.
- Fallback MIME is `video/mp4`.
- File extension still comes from final MIME through existing extension logic.

`VideoJobManager` replaces its inline-only extraction with materialization:

1. Provider fetch returns `SuccessResultOutcome`.
2. Manager finds the video-role artifact.
3. Materializer converts inline or remote body to bytes and final MIME.
4. Manager writes the existing `generated_video` artifact shape:
   - blob role `video`
   - extension from final MIME
   - parent IDs from input media refs
5. Manager appends `Complete` with `result_artifact_id`.

If materialization fails, the manager appends `Error`. Existing
`VideoJobRecordFactory.WithState` preserves prior provider fields/extensions
when no new provider handle is passed, so provider handle URL metadata should
survive materialization failure. PR-8 tests pin that behavior.

## Pricing

Add `FalWanT2vPricingModel`.

Pricing behavior:

- `$0.10/s` from fal Wan docs checked on 2026-04-29.
- Quantity is `duration_seconds * number_of_videos`.
- `number_of_videos` remains subject to existing capability validation.
- `PricingSource` and estimate provenance include the model and docs check date.
- Actual spend extraction may read `x-fal-billable-units` through existing fal
  pricing helpers, but interpretation stays inside this model, not a shared
  fal-header shortcut.

PR-8 does not add 3D flat-call/add-on pricing or Replicate compute-second
pricing.

## Error Handling

Provider and manager errors stay typed:

- Missing fal key: `DependencyUnavailable`, non-retryable.
- Bad fal options fields: `InvalidRequest`, non-retryable.
- Direct provider call without prompt: `InvalidRequest`, non-retryable.
- Queue/status malformed body: typed provider failure, not throw for expected
  provider-contract errors.
- fal terminal queue state followed by fetch failure:
  `FailedResultOutcome`, durable job `Error`, not `Complete`.
- `ResponseUrl` missing at fetch: `ExecutionFailed`, non-retryable.
- Oversize generated video: `ExecutionFailed`, non-retryable.
- Remote artifact fetch 5xx/transport/timeout: `DependencyUnavailable`,
  retryable where appropriate.
- Empty remote body: `ExecutionFailed`, non-retryable.
- User cancellation: `Cancelled`.

Public `/vision/video/*` error envelope shape remains unchanged.

## Test Plan

### Provider and Codec Tests

- `FalVideoOptionsCodec.Deserialize({})` succeeds.
- `Deserialize({ "negative_prompt": "x" })` fails with `InvalidRequest`.
- `Deserialize({ "enable_prompt_expansion": false })` fails with
  `InvalidRequest`.
- Unknown fal option fields fail.
- `Serialize(new FalVideoOptions())` returns `{}`.
- `FalVideoProvider.SubmitAsync` sends the expected queue URL.
- Submit body includes prompt, aspect ratio, resolution, duration, fixed safety
  and prompt expansion `true`, and optional seed only when present.
- Submit parses `ProviderJobHandle` with status URL, response URL, cancel URL,
  provider metadata, and the verified cancel method.
- Status maps fal states and treats `COMPLETED` as provider-complete only.
- Fetch fails if `ResponseUrl` is null.
- Fetch maps non-2xx response URL failures through `FalErrorMapper`.
- Fetch parses `video.url`, declared MIME, and provider metadata into
  `RemoteArtifactBody`.
- Cancel calls the persisted `cancel_url` with the verified method.

### Handler Tests

- Unknown model fails before options parsing.
- Existing Veo model with `person_generation` options still parses and
  estimates/submits as before.
- fal model with `{}` options parses.
- fal model with Veo-shaped options fails through `FalVideoOptionsCodec` with
  `InvalidRequest`.
- Missing `options` remains invalid.

### Manager and Materializer Tests

- Inline video artifacts still materialize into the existing `generated_video`
  artifact shape.
- Remote video artifacts materialize into the same `generated_video` artifact
  shape.
- Remote fetch sends no fal auth header.
- Remote `Content-Length = cap + 1` fails before body read.
- Missing `Content-Length` fails once accumulated bytes exceed cap.
- Exactly cap is allowed using an injected small test cap.
- Empty body fails.
- Inline video over cap fails using an injected small test cap.
- Declared MIME `video/mp4` wins over response content type.
- Response content type fills in when declared MIME is absent.
- Fallback MIME is `video/mp4`.
- Extension comes from final MIME.
- Provider-complete plus failed fetch writes durable `Error`, not `Complete`.
- Provider-complete plus materialization failure writes durable `Error`, not
  `Complete`.
- Provider handle URL metadata is preserved on fetch/materialization failure.

### Registry and Regression Tests

- Existing Veo byte-identity fixtures still pass.
- `list_video_models` includes the fal T2V descriptor after factory wiring.
- No fal I2V descriptor appears.
- Wan T2V descriptor has `Modes=[T2V]`, `SupportsReferenceImages=false`,
  `MaxReferenceImages=0`, and `Must8sWith=[]`.
- Existing generation seam tests continue to pass, including union closure,
  invariant bypass, symbol scan, and Phase 0 fixture fakes.

## Live Smoke Gate

Add a skipped-by-default paid live test. It only runs when all are set:

```text
ROOK_FAL_VIDEO_LIVE=1
ROOK_FAL_API_KEY=...
ROOK_ACCEPT_FAL_SPEND=1
```

Smoke defaults:

- Model: `fal-ai/wan/v2.7/text-to-video`
- Duration: `2s`
- Resolution: `720p`
- Synthetic low-risk prompt

The smoke submits, polls, fetches, and materializes enough to prove the queue
and remote artifact path. It records only redacted/safe provider identifiers in
test output. It must never run paid calls silently.

Live cancellation characterization is not part of PR-8 acceptance unless
explicitly approved and budgeted.

## Acceptance Checklist

- Only `fal-ai/wan/v2.7/text-to-video` is registered.
- Existing `/vision/video/*` route request and response shapes are preserved.
- Veo byte-identity fixtures still pass.
- Registry-resolved options parsing replaces the Veo-only branch.
- Fal queue handle URL fields round-trip through the video ledger.
- Fal terminal/fetch failure path is pinned as durable job `Error`.
- Remote mp4 output is fetched without fal auth and written as an existing
  `generated_video` artifact.
- Generated video bytes are capped at `250 MB` in production.
- Cancel path is covered with fake/provider tests.
- Live fal video smoke is spend-gated.
- No `src/RookNative/**` files are changed.

## Follow-Up Work

- Add `fal-ai/wan/v2.7/image-to-video` after designing input media URL
  upload/hosting.
- Add negative prompt and prompt-expansion public options only with deliberate
  validation and UI/MCP docs.
- Promote a shared URL artifact downloader only after image/video/Replicate
  duplication becomes concrete.
- PR-9 settings/picker work: fal key UI, provider badges, and availability
  states.
