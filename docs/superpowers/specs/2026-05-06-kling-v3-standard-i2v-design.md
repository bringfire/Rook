# Kling v3 Standard Image-to-Video Design

Date: 2026-05-06

## Goal

Add one curated fal video model:

`fal-ai/kling-video/v3/standard/image-to-video`

This is the first Kling slice. It should be intentionally small: source-frame
image-to-video and interpolation only, using the hardened fal source-frame
transport from PR-19, with no new public video request shape and no provider
URL leakage.

The product workflow is:

- choose a viewport or Gallery image artifact as a start frame;
- optionally choose an end-frame artifact for interpolation;
- submit a prompt and duration through Rook Vision;
- let fal generate one video through Kling v3 Standard;
- materialize the provider output into a local Rook `generated_video`
  artifact.

## Background

Rook already has a managed Vision video lifecycle:

- `VideoOpHandler` owns bridge video ops.
- `DefaultVideoProviderRegistry` exposes curated model rows.
- `VideoJobManager` submits, polls, fetches, materializes, lists, cancels, and
  reconciles video jobs.
- `ArtifactOnlyVideoMediaResolver` resolves artifact-id source media and
  rejects path-kind video refs at the bridge boundary.
- `FalVideoProvider` already supports fal video models through model-aware
  lifecycle calls.
- PR-18 added Seedance request-id-only fal lifecycle handling.
- PR-19 added provider-private fal CDN source-frame upload for Seedance.

The current fal docs reviewed on 2026-05-06 describe Kling v3 Standard I2V at
`fal-ai/kling-video/v3/standard/image-to-video` with:

- `start_image_url` required;
- `prompt` or `multi_prompt`, but Rook will require `prompt`;
- `duration` enum values `3` through `15`, default `5`;
- `generate_audio` default `true`;
- optional `end_image_url`;
- optional `elements`, `negative_prompt`, and `cfg_scale`;
- a single required `video` output object with `video.url`.

Source:
https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api

The same fal model page lists Standard Kling v3 I2V pricing at `$0.084` per
generated second with audio off, `$0.126` per generated second with audio on,
and `$0.154` per generated second with voice-control audio. This first slice
fixes `generate_audio=false`, so Rook uses the audio-off rate.

## Non-Goals

- No Kling text-to-video.
- No Kling Pro, 4K, O3, Omni, fast, or reference-to-video endpoint.
- No dynamic provider discovery.
- No `multi_prompt`.
- No `elements`.
- No `negative_prompt`.
- No `cfg_scale`.
- No audio generation.
- No voice-control audio.
- No provider option expansion.
- No reference frames.
- No multiple videos per request.
- No public native route expansion.
- No MCP tool expansion.
- No `NativeGhBridgeRegistrar` allowlist expansion.
- No public or provider-neutral upload service.
- No local HTTP source server.
- No public temp hosting.
- No video ledger schema migration.
- No artifact retention model change.

## Product Scope

Register one curated model row:

- provider: `fal`
- model id: `fal-ai/kling-video/v3/standard/image-to-video`
- display name: `Kling v3 Standard Image to Video`
- status: `preview`
- modes: `I2V` and `Interp`
- source media: artifact-id image frames only
- reference images: not supported
- max reference images: `0`
- number of videos: exactly `1`

Mode behavior:

- `I2V` requires prompt and start frame.
- `I2V` rejects an end frame.
- `Interp` requires prompt, start frame, and end frame.
- `T2V` is rejected for this model.
- reference frames are rejected for this model.

Capability values:

- resolutions: `auto`
- aspect ratios: `auto`
- durations: `3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15`

The existing Vision UI can display and submit arbitrary capability strings, so
`auto` is honest: Kling v3 Standard I2V does not expose `resolution` or
`aspect_ratio` request fields in the current fal schema. The provider must not
send fake `resolution` or `aspect_ratio` values to fal.

If the UI needs a selected default, use duration `5`. Live smoke should prefer
duration `3` or `5` to limit spend. Tests must pin rejection outside the fal
range, especially `2` and `16`.

## Provider Request Shape

Kling submit JSON sends only:

- `prompt`
- `start_image_url`
- `end_image_url` for `Interp`
- `duration`
- `generate_audio: false`

`duration` should serialize in fal's current `DurationEnum` shape as a string,
for example `"5"`.

Kling submit JSON must not include:

- `resolution`
- `aspect_ratio`
- `multi_prompt`
- `elements`
- `negative_prompt`
- `cfg_scale`
- `seed`
- any audio option other than fixed `generate_audio: false`

Do not expose, deserialize, or send Kling provider option fields in this
slice. Unexpected fal video options remain rejected by the existing fal
options boundary.

Kling queue submit must use the same fal platform privacy/cost controls as
Seedance because the request body contains volatile `start_image_url` and
optional `end_image_url` values:

- `X-Fal-Object-Lifecycle-Preference:
  {"expiration_duration_seconds":3600}`
- `X-Fal-Store-IO: 0`
- `X-Fal-No-Retry: 1`

The one-hour value should remain a named fal video source-media lifetime
constant. `X-Fal-Store-IO: 0` prevents fal from storing request JSON payloads
that contain source CDN URLs. `X-Fal-No-Retry: 1` prevents platform retries
from duplicating a generation job after the submit body reaches fal. Rook may
keep only the already reviewed client-side retry shape for connection
establishment failures where the body did not reach fal.

## Endpoint Strategy

Kling uses the exact fal model endpoint for queue submit, then the root
`fal-ai/kling-video` queue path for lifecycle reconstruction. fal queue
variant/version subpaths are used for submit but are not included in
status/result/cancel routes:

- submit:
  `https://queue.fal.run/fal-ai/kling-video/v3/standard/image-to-video`
- status:
  `https://queue.fal.run/fal-ai/kling-video/requests/{request_id}/status`
- result:
  `https://queue.fal.run/fal-ai/kling-video/requests/{request_id}`
- cancel:
  `https://queue.fal.run/fal-ai/kling-video/requests/{request_id}/cancel`

Seedance proved that submit and lifecycle endpoint assumptions can produce
HTTP 405s. The implementation reconstructs Kling status, result, and cancel
from the model base above. Fake provider tests must pin the request URLs for
submit, status, result, and cancel so endpoint drift is visible.

Live fal evidence from May 7, 2026: a request submitted through
`fal-ai/kling-video/v3/standard/image-to-video` returned HTTP 405 for lifecycle
roots under both `.../v3/standard` and `.../v3/standard/image-to-video`, but
HTTP 200 for status/result under
`https://queue.fal.run/fal-ai/kling-video/requests/{request_id}`.

Kling durable handles remain request-id-only:

- persist provider `fal`;
- persist model `fal-ai/kling-video/v3/standard/image-to-video`;
- persist fal `request_id` as provider job id;
- do not persist status, result, cancel, or output URLs.

Lifecycle calls must use explicit model identity. The provider must not infer
Kling from request-id shape, missing handle URLs, or provider-name-only lookup.

## fal Video Source-Frame Transport

Generalize the PR-19 Seedance source upload helper into a narrow fal video
source-frame transport inside `Services/Vision/Video/Fal`.

The target shape is:

- `IFalSourceFrameTransport`
- `FalSourceFrameTransport`
- `FalSourceFramePolicy`
- `FalSourceFrameUrls`

This is not a broad fal upload service and not a provider-neutral Vision upload
layer. It is provider-private fal video source-frame transport.

`FalSourceFrameTransport` owns exactly the PR-19 mechanics:

1. Validate request shape against a model policy.
2. Resolve start/end frames from `ResolvedMedia`.
3. Detect source bytes.
4. Initiate fal CDN upload.
5. PUT raw bytes to the returned upload URL.
6. Return volatile fal CDN URLs.

`FalSourceFrameUrls` contains only:

- `StartImageUrl`
- optional `EndImageUrl`

It has no metadata bag, provider handle fields, result token, request body
storage, or durable participation.

Seedance maps `StartImageUrl` to `image_url`.
Kling maps `StartImageUrl` to `start_image_url`.
Both map `EndImageUrl` to `end_image_url`.

## Source-Frame Policy

Each fal video model passes a small policy into the transport:

- model label for errors;
- generated filename prefix;
- allowed modes;
- max source-frame byte cap;
- allowed MIME set;
- whether `I2V` rejects an end frame.

Do not blindly globalize Seedance's current 30 MB cap or MIME policy. Keep
limits behind per-model constants.

Kling's current fal page advertises accepted image file types including
`jpg`, `jpeg`, `png`, `webp`, `gif`, and `avif`, but Rook's current byte
detector reliably sniffs PNG, JPEG, and WebP. The first Kling slice should
accept only PNG, JPEG, and WebP source bytes, matching what Rook can verify
locally before provider submit. GIF and AVIF support is deferred until Rook has
detector coverage and tests.

Kling should use a named provisional Kling max-byte constant. The current
Kling page advertises accepted image file types but does not clearly document
a model-specific source-frame byte cap. The first implementation should fail
closed before queue submit using the provisional cap, and live smoke/review
must revisit the cap if fal rejects normal viewport captures that pass Rook's
local validation.

Validation failures are non-retryable `InvalidRequest` failures and happen
before queue submit.

## Error And Privacy Policy

Error wording should be sanitized and model-specific enough for users:

- acceptable: `fal Kling source upload failed.`
- avoid stale wording such as `Seedance source upload failed.`
- avoid provider request JSON, source URLs, upload URLs, headers, prompts,
  local paths, artifact names, or source bytes in errors.

Source fal CDN URLs are volatile transport material. They must never be
written to:

- `ProviderJobHandle`;
- provider metadata;
- provider result token;
- durable video ledger records;
- raw JSONL ledger text;
- ledger extensions;
- artifact metadata;
- result envelope metadata;
- bridge responses;
- native routes;
- MCP surfaces;
- logs;
- user-facing or provider-detail errors.

Kling result parsing should mirror Seedance's privacy posture:

- parse exactly one `video.url`;
- require an absolute HTTP or HTTPS URL;
- return a remote video artifact body so `VideoJobManager` materializes it;
- omit provider URL and provider response metadata from artifact metadata and
  envelope metadata.

If the provider returns malformed JSON, missing `video`, missing `video.url`,
`data:`, `file:`, or otherwise invalid URL, fail with a typed
`ExecutionFailed` result error.

## Pricing

Add a Kling-specific pricing model:

- source: `fal-ai-kling-video-v3-standard-i2v-output-second-2026-05-06`
- unit: `output_second`
- unit price: `$0.084`
- quantity: `duration_seconds * number_of_videos`
- estimate exactness: `false`, matching the Seedance provider-page pricing
  posture.

The pricing model is intentionally tied to `generate_audio=false`. If audio is
added later, pricing must be reviewed and split by audio mode.

## Testing Strategy

### Capability And Validation Tests

Add or update tests proving:

- Kling model row exists under provider `fal`;
- model id is `fal-ai/kling-video/v3/standard/image-to-video`;
- modes are exactly `I2V` and `Interp`;
- resolutions are exactly `auto`;
- aspect ratios are exactly `auto`;
- durations are exactly `3` through `15`;
- duration `2` and `16` are rejected;
- `T2V` is rejected before HTTP;
- prompt is required;
- `number_of_videos != 1` is rejected;
- reference frames are rejected;
- unexpected fal video options remain rejected.

### Source Transport Tests

Rename or replace the Seedance source transport tests so the shared fal video
source-frame transport is tested through policy.

Policy tests should cover:

- Seedance retains its current behavior and error wording through policy;
- Kling uses Kling filename prefixes and Kling error wording;
- Kling accepts PNG, JPEG, and WebP source bytes;
- Kling rejects unsupported bytes such as GIF until detector support exists;
- model-specific byte caps are enforced before HTTP;
- `I2V` uploads only the start frame;
- `Interp` uploads start and end frames;
- start upload success plus end upload failure does not return partial URLs;
- final upload failure is retryable, sanitized, and does not expose URLs,
  headers, source bytes, prompt, or request bodies;
- caller cancellation propagates and does not return source URLs.

### Provider Tests

Add fake HTTP/fake transport coverage for Kling:

- submit uploads source frames before queue submit;
- submit body uses `start_image_url`;
- `Interp` submit body includes `end_image_url`;
- submit body sends duration as fal `DurationEnum` string;
- submit body sends `generate_audio: false`;
- submit body omits `resolution`, `aspect_ratio`, `multi_prompt`,
  `elements`, `negative_prompt`, `cfg_scale`, and `seed`;
- queue submit sends one-hour `X-Fal-Object-Lifecycle-Preference`;
- queue submit sends `X-Fal-Store-IO: 0`;
- queue submit sends `X-Fal-No-Retry: 1`;
- submit returns `ProviderJobHandle(request_id)` with no URLs or provider
  metadata;
- missing fal API key makes no upload or submit request;
- upload failure never calls queue submit;
- generic submit transport failures are not retried if the request may have
  reached fal;
- any retained connect-establishment retry policy is explicit and tested;
- status reconstructs the exact Kling status URL from model id and request id;
- result reconstructs the exact Kling result URL from model id and request id;
- cancel reconstructs the exact Kling cancel URL from model id and request id;
- result parser returns one video artifact and drops provider metadata;
- invalid or missing `video.url` fails.

### Privacy And Boundary Tests

Prove Kling source and result URLs never appear in:

- `ProviderJobHandle` extensions;
- parsed ledger records;
- raw JSONL ledger text;
- artifact metadata;
- result envelope metadata;
- bridge list/status/result responses;
- native route code;
- MCP code;
- internal bridge registrar surfaces.

Boundary scans should confirm there is no new public fal source upload
operation, no upload URL field, and no provider CDN URL surface outside
managed fal video provider internals.

## Verification

Focused verification should include:

- fal video source-frame transport tests;
- fal video provider tests;
- fal video registration/capability tests;
- video cost estimator tests for Kling pricing;
- video job manager privacy/ledger tests;
- bridge response privacy tests;
- boundary scans for native/MCP/internal bridge exposure;
- `git diff --check`;
- managed `net7.0` build.

Run the full managed test suite before merge when practical.

Manual live smoke is optional during implementation handoff but required
before treating the model as product-ready:

1. Build and deploy the managed companion.
2. Start Rhino fresh.
3. Use Vision video with Kling v3 Standard I2V before running Seedance.
4. Use duration `3` or `5`.
5. Confirm fal job completes and Rook materializes a local `generated_video`
   artifact.
6. Confirm the latest ledger and artifact metadata contain no `fal.media`,
   `queue.fal.run`, `rest.fal.ai`, `api.fal.ai`, `start_image_url`,
   `end_image_url`, `image_url`, `data:image`, `status_url`, `response_url`,
   or `cancel_url`.

Do not commit live prompts, source frames, CDN URLs, provider envelopes,
generated videos, or credentials.

## Acceptance Criteria

- One Kling v3 Standard I2V model row is registered.
- Kling supports `I2V` and `Interp`.
- Kling rejects `T2V`.
- Kling requires prompt in Rook.
- Kling exposes durations `3` through `15`.
- Kling uses `resolution: auto` and `aspect_ratio: auto` internally.
- Kling does not send `resolution` or `aspect_ratio` to fal.
- Kling fixed-submit sends `generate_audio: false`.
- Kling queue submit sends one-hour `X-Fal-Object-Lifecycle-Preference`.
- Kling queue submit sends `X-Fal-Store-IO: 0`.
- Kling queue submit sends `X-Fal-No-Retry: 1`.
- Kling does not expose, deserialize, or send `multi_prompt`, `elements`,
  `negative_prompt`, `cfg_scale`, or audio options.
- Kling uses provider-private fal video source-frame transport.
- The transport is generalized from Seedance mechanics but remains inside
  `Services/Vision/Video/Fal`.
- Source-frame policy is per model.
- Kling source-frame validation accepts only locally detected PNG, JPEG, and
  WebP in this slice.
- Submit uses the exact Kling model subpath endpoint; status, result, and
  cancel use the Kling model base without `image-to-video`.
- Fake tests pin submit/status/result/cancel URLs.
- Durable Kling fal handles are request-id-only with explicit model identity.
- Result parsing accepts exactly one `video.url`.
- Provider URLs never persist in handles, ledger, artifact metadata, result
  envelope metadata, bridge responses, errors, native routes, MCP tools, or
  logs.
- Pricing uses current fal audio-off Standard rate `$0.084/output_second`.
- Seedance behavior remains covered after the transport rename/generalization.

## Follow-Up

Future Kling work can separately review:

- `multi_prompt`;
- `elements`;
- `negative_prompt`;
- `cfg_scale`;
- audio generation;
- voice-control audio;
- GIF and AVIF source-frame support;
- Pro, 4K, O3, Omni, or reference-to-video endpoints;
- richer UI defaults or copy for `auto` resolution/aspect ratio;
- live-smoke-driven endpoint changes if fal changes the lifecycle base.

## Self-Review

- Scope is one Kling model and one provider-private transport rename/generalization.
- The spec does not introduce a provider-neutral upload service.
- The spec uses current fal docs for request fields, duration, audio default,
  result shape, and pricing.
- The endpoint strategy is explicit and test-pinned.
- `resolution` and `aspect_ratio` are honest internal capability values and
  are not sent to fal.
- Provider options are phrased as not exposed/deserialized/sent rather than as
  public request fields that already exist.
- Source upload policy remains per model.
- Error and privacy rules preserve the Seedance no-provider-URL posture.
- No implementation plan or code changes are included.
