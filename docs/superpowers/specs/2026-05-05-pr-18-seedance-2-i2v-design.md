# PR-18 Seedance 2.0 Image-to-Video Design

Date: 2026-05-05

## Goal

PR-18 adds one curated fal.ai source-video model:
`bytedance/seedance-2.0/image-to-video`.

This is a model-aware fal video lifecycle PR, not just a catalog row. The
existing fal video provider is hardcoded to
`fal-ai/wan/v2.7/text-to-video`; Seedance requires branch-by-model endpoint
selection, request construction, status/result/cancel reconstruction, result
parsing, source-media validation, and fake HTTP coverage.

The product workflow is:

- Rhino/Grasshopper viewport or Gallery image artifact;
- high-quality source-image video generation through fal queue;
- local `generated_video` artifact materialization;
- Gallery persistence through the existing video artifact path.

## Background

RookVision video already has a managed lifecycle:

- `VideoOpHandler` owns bridge video ops.
- `DefaultVideoProviderRegistry` exposes a curated model catalog.
- `VideoJobManager` submits jobs, polls providers, materializes video bytes,
  writes `generated_video` artifacts, lists jobs, handles cancel, and
  reconciles non-terminal jobs to `Interrupted` on restart.
- `ArtifactOnlyVideoMediaResolver` resolves artifact-id media refs and rejects
  path refs as a bridge-boundary and defense-in-depth privacy rule.
- `FalVideoProvider` currently supports only
  `fal-ai/wan/v2.7/text-to-video`.

Official fal docs reviewed on 2026-05-05 describe Seedance 2.0
Image-to-Video as a queue-capable endpoint with required `prompt` and
`image_url`, optional `end_image_url`, `resolution`, `duration`,
`aspect_ratio`, `generate_audio`, `seed`, and a single `video.url` output:
https://fal.ai/models/bytedance/seedance-2.0/image-to-video/api

fal queue docs reviewed on 2026-05-05 describe submit/status/result/cancel
around a `request_id`:
https://fal.ai/docs/documentation/model-apis/inference/queue

Kling 3.0 was reviewed but is deferred. Its fal schema includes extra
branches such as `multi_prompt`, `negative_prompt`, `cfg_scale`, custom
elements, and richer audio behavior:
https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api

Seedance is the better first source-video slice because it fits Rook's
existing start-frame/end-frame video request model with fewer provider
options.

## Non-Goals

- No Kling 3.0 in PR-18.
- No Seedance text-to-video endpoint.
- No Seedance fast endpoint.
- No Seedance reference-to-video endpoint.
- No multi-reference image/video/audio input.
- No provider dynamic discovery.
- No public native route expansion.
- No MCP tool expansion.
- No `NativeGhBridgeRegistrar` allowlist expansion.
- No arbitrary local path media refs.
- No public temp hosting.
- No fal storage/upload abstraction.
- No prompt-only Seedance workflow.
- No `"auto"` duration exposed through Rook's integer duration capability.
- No `multi_prompt`, `negative_prompt`, `cfg_scale`, `elements`, or
  `end_user_id`.
- No video ledger schema rewrite beyond the minimal handle/lifecycle support
  required for request-id-only fal handles.
- No broad provider metadata policy rewrite.

## Product Scope

Register one curated model:

- provider: `fal`
- model id: `bytedance/seedance-2.0/image-to-video`
- display name: `Seedance 2.0 Image to Video`
- modality: video
- modes: `I2V` and `Interp`
- source media: artifact-id image frames only
- supports reference images: false
- max reference images: 0
- number of videos: 1

Seedance is source-driven only in PR-18:

- `I2V` requires a start frame artifact and prompt.
- `Interp` requires start frame artifact, end frame artifact, and prompt.
- `T2V` is rejected for this model.

Capability values should be explicit and conservative:

- resolutions: `480p`, `720p`
- durations: integer values `4` through `15`
- aspect ratios: `auto`, `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16`
- `generate_audio`: fixed by provider-owned options for PR-18, default `true`
  unless live smoke or cost review shows it should default to `false`
- `seed`: supported through existing request seed

If `aspect_ratio: "auto"` creates UI or validator friction, the design allows
the implementation plan to choose explicit aspect ratios only and omit `auto`.
Do not introduce a larger capability schema just for this.

## Provider Architecture

Provider identity remains `fal`.

Use one model-aware `FalVideoProvider`:

- `fal-ai/wan/v2.7/text-to-video` remains text-to-video.
- `bytedance/seedance-2.0/image-to-video` uses source-image video.
- provider secrets remain the existing fal API key.
- Settings and model picker continue to show provider `fal`.

The provider branches internally by `request.Model`:

- validate supported model id;
- choose the fal endpoint id;
- validate mode-specific media requirements;
- build the model-specific request JSON;
- parse the model-specific result schema.

The video manager should stay provider-neutral. It sees only
`ProviderSubmitOutcome`, `ProviderStatusOutcome`, `ProviderResultOutcome`, and
`ProviderCancelOutcome`. Seedance JSON shape stays inside the fal video
provider.

## Request-Id-Only fal Lifecycle

PR-18 should move new fal video jobs toward request-id-only durable handles.

For Seedance, durable state should persist only:

- provider: `fal`
- model: `bytedance/seedance-2.0/image-to-video`
- provider job id: fal `request_id`
- existing result artifact id and state fields

Durable Seedance records must not persist:

- fal `status_url`
- fal `response_url`
- fal `cancel_url`
- fal result URL
- fal result envelope
- request JSON
- data URI
- source bytes
- provider logs

The implementation must prove active polling, result fetch, and cancel can be
reconstructed from `provider + model + provider_job_id`.

The current provider lifecycle methods receive only `ProviderJobHandle`.
A request-id-only handle does not carry model identity, so PR-18 must make the
lifecycle contract explicit before Seedance can use request-id-only fal
handles. The implementation must choose one of these reviewed shapes:

1. Add model-aware video provider lifecycle calls, for example an
   `IModelAwareVideoProvider` with:
   - `GetStatusAsync(string modelId, ProviderJobHandle handle, ...)`
   - `FetchResultAsync(string modelId, ProviderJobHandle handle, ...)`
   - `CancelAsync(string modelId, ProviderJobHandle handle, ...)`
2. Add a validated model id to `ProviderJobHandle` or an equivalent durable
   handle type, and require lifecycle callers to populate it from the
   resolved model on active jobs and from the durable record on restart.

For active polling, `VideoJobManager` already carries `RunningJob.Model`; PR-18
must pass that model id through to the provider lifecycle path before calling
fal status/result/cancel. For restart cancel, the manager must read the durable
record, validate that the persisted model resolves to the same persisted
provider, and pass that model id to the provider lifecycle path.

The provider must not infer model identity from missing URLs, empty
`ProviderJobHandle.StatusUrl`, endpoint string heuristics, or provider-name-only
lookup. A request-id-only fal handle is valid only when paired with explicit,
validated model identity.

If request-id-only handles are not feasible after implementation evidence,
stop and review before accepting URL persistence. Persisting fal queue URLs
for Seedance would repeat the current fal video privacy weakness and is not
approved by this design.

## Existing Video Ledger Constraint

The existing video ledger persists `normalized_request`, including prompt and
artifact media refs. PR-18 does not redesign the whole video ledger because
that is larger than the curated model slice.

PR-18 must still avoid adding new Seedance-specific leakage:

- no source bytes;
- no data URI;
- no fal URLs;
- no provider request body;
- no provider result envelope;
- no provider logs;
- no provider media URL;
- no queue URLs in `provider_handle`.

Bridge responses and list summaries already expose only operational state,
job id, model summary, status, result artifact id, local file paths, and
sanitized errors. PR-18 must preserve that boundary and must not echo prompt,
source frame paths, data URIs, fal request ids, or fal URLs through bridge
payloads.

A future hardening PR can decide whether video durable records should move to
the newer image-job operational-only ledger style. PR-18 should not mix that
schema migration with the first Seedance model.

## Source Media Contract

Only artifact-id media refs are accepted.

`VideoOpHandler` already rejects path refs for video bridge requests. PR-18
must preserve that and add Seedance-specific tests proving path refs never
reach the fal provider.

Resolved source images:

- must be non-empty;
- must be PNG, JPEG, or WebP;
- must be below a model-specific raw byte cap;
- should reject unsupported MIME types before provider submit;
- should reject GIF, AVIF, MP4, and unknown bytes for PR-18 even if fal UI
  accepts more formats;
- should use detected MIME for data URI construction.

Initial cap:

- use a conservative cap in code and tests, likely `1 MB`, matching recent
  source-image slices;
- if live smoke proves viewport captures routinely exceed that cap for useful
  video, revise through review before raising it broadly.

Transport:

- build bounded base64 data URIs for `image_url` and optional
  `end_image_url`;
- do not use public hosting;
- do not upload to fal storage;
- do not persist data URIs.

## Seedance Request Shape

For `I2V`, send:

- `prompt`: user prompt
- `image_url`: start frame data URI
- `resolution`: selected explicit resolution
- `duration`: selected integer duration serialized in provider-required shape
- `aspect_ratio`: selected aspect ratio
- `generate_audio`: provider-owned default
- `seed`: if present

For `Interp`, additionally send:

- `end_image_url`: end frame data URI

Do not send:

- `end_user_id`
- provider logs setting
- webhook URL
- reference media
- paths
- fal upload URLs
- prompt expansion flags unless official Seedance docs require them

The provider must reject:

- `T2V` mode;
- missing prompt;
- missing start frame;
- missing end frame for `Interp`;
- end frame supplied in unsupported modes if that would make the request
  ambiguous;
- reference frames;
- `number_of_videos != 1`;
- unsupported options fields.

## Result Parsing And Materialization

fal Seedance result parsing should accept exactly one generated video:

- parse `video.url`;
- require absolute `http` or `https`;
- accept `video.content_type` when present;
- ignore or minimally preserve safe scalar metadata only when needed;
- do not include `video.url` in artifact metadata;
- do not preserve fal result envelope metadata in durable state.

The video manager continues to own local materialization:

- download remote video through `VideoArtifactMaterializer`;
- enforce generated video byte cap;
- write a `generated_video` artifact;
- mark complete only after artifact creation succeeds;
- return local artifact/file information through result ops.

If the current fal Wan parser preserves `video.url` as provider metadata, do
not copy that behavior to Seedance. Seedance should follow the stricter
source-model privacy posture from PR-17.

## Restart Behavior

Startup reconciliation remains:

- non-terminal jobs become `Interrupted`;
- no automatic resume is added in PR-18.

Cancel-after-restart is required when the interrupted record has a fal request
id:

- resolve durable record by provider and model where needed;
- reconstruct fal cancel endpoint from model id and request id;
- call fal cancel;
- persist `Cancelled` only after provider confirms cancel or already-terminal
  semantics are safely mapped.

Status/result-after-restart for interrupted jobs should not auto-poll or fetch
provider results in PR-18. The required restart proof is cancel cleanup with a
request-id-only handle.

## UI Behavior

The existing video UI should remain provider-neutral:

- model list receives Seedance capability metadata;
- selecting Seedance enables `I2V` and `Interp`, not `T2V`;
- frame picker continues to list image-bearing artifacts only;
- start frame is required for `I2V`;
- start and end frames are required for `Interp`;
- prompt remains required for Seedance modes;
- reference frame controls remain disabled/cleared because max references is
  `0`;
- generated video appears in Gallery through existing `generated_video`
  rendering.

The PR should not add Seedance-specific strings to JS routing if capability
metadata can express the behavior.

If the existing `person_generation` Veo options UI is hardwired into all video
requests, PR-18 should make the smallest provider-neutral options adjustment
needed so fal Seedance receives `FalVideoOptions`, not `VeoOptions`.

## Pricing

Use conservative fal pricing metadata from the reviewed model page.

For PR-18, pricing can be approximate if the provider exposes pricing as a
rate card rather than reliable response headers. Tests should prove:

- estimates are deterministic;
- the pricing source is explicit;
- cost UI works for Seedance;
- no live provider call is needed for automated pricing tests.

If pricing is too ambiguous to encode confidently, expose an `External` or
clearly approximate pricing model and call it out in the implementation plan.

## Testing Strategy

### Provider Tests

Fake HTTP tests should prove:

- Seedance submit posts to the fal queue endpoint for
  `bytedance/seedance-2.0/image-to-video`;
- request body contains `prompt`, `image_url`, explicit `resolution`,
  integer duration in the provider-required shape, `aspect_ratio`,
  `generate_audio`, and optional `seed`;
- `Interp` includes `end_image_url`;
- `T2V` is rejected before HTTP;
- missing prompt/start/end frame failures are typed and sanitized;
- reference frames are rejected;
- unsupported media MIME fails before HTTP;
- source bytes over cap fail before HTTP;
- data URI contains detected MIME;
- submit persists only request id in the provider handle for Seedance;
- status maps fal queued/running/complete/error states;
- result fetch parses exactly one `video.url`;
- missing/invalid/non-http video URL fails closed;
- cancel reconstructs endpoint from model id and request id;
- auth, quota, transport, timeout, malformed JSON, and provider error bodies
  are sanitized.

### Manager And Restart Tests

Manager tests should prove:

- model-aware fal video lifecycle routes Wan and Seedance correctly;
- active polling passes explicit model identity to fal status and result
  lifecycle calls;
- Seedance jobs persist request-id-only handles;
- no Seedance queue URLs enter ledger extensions;
- cancel-after-restart works from `provider + model + provider_job_id` and
  passes explicit model identity to fal cancel;
- deprecated-model/provider mismatch cases fail typed rather than using the
  wrong provider;
- request-id-only handles with no model identity fail typed rather than
  inferring Seedance from missing URLs;
- completed Seedance jobs materialize local `generated_video` artifacts;
- artifact metadata does not include fal URL, data URI, request JSON, or result
  envelope.

### Bridge And UI Tests

Bridge/UI tests should prove:

- `list_video_models` exposes Seedance as fal, source-video, `I2V`/`Interp`;
- Seedance does not expose `T2V`;
- path refs are rejected at `VideoOpHandler`;
- artifact-id refs are accepted;
- reference frames are rejected for Seedance;
- `submit_video_job` response does not expose fal request id or URLs;
- `get_video_job`, `list_video_jobs`, and `get_video_job_result` do not expose
  prompt/source/data URI/fal URLs;
- UI routing remains capability-driven and does not hardcode Seedance where
  generic metadata is sufficient.

### Leakage Tests

Serialize ledger records, bridge payloads, generated artifact metadata, and
error payloads for fake Seedance runs.

Assert they do not contain:

- `queue.fal.run`;
- `fal.media`;
- `fal.run`;
- `status_url`;
- `response_url`;
- `cancel_url`;
- `image_url`;
- `end_image_url`;
- `data:image/`;
- `video.url`;
- request JSON;
- provider result envelope;
- provider logs.

Ledger records may contain the safe scalar fal request id only as
`provider_job_id`.

The existing video ledger's normalized prompt/artifact-ref fields are inherited
behavior, not new Seedance provider leakage. Tests should distinguish that
existing schema behavior from forbidden Seedance transport/provider leakage.

### Boundary Tests

Scans should prove PR-18 does not add Seedance or new video ops to:

- `src/RookNative/**`
- `mcp_server/**`
- `src/Rook/InternalBridge/**`

### Live Rhino Smoke Gate

Before merge, run an explicitly enabled live smoke with a real fal key:

1. Confirm fal API key in RookVision Settings.
2. Capture or select a non-sensitive viewport/source image artifact.
3. Select Seedance 2.0 Image to Video.
4. Submit `I2V` with a non-sensitive prompt.
5. Observe queued/submitting/polling/downloading/saving/complete states.
6. Confirm local video artifact materializes.
7. Confirm Gallery playback.
8. Restart Rhino and confirm completed artifact persists.
9. Start another job and cancel while queued if timing allows.
10. Confirm no fal URLs or request ids are shown in UI payloads.

Do not commit prompts, source images, data URIs, fal URLs, provider envelopes,
videos, or credentials from live smoke.

## Acceptance Criteria

- One model only: `bytedance/seedance-2.0/image-to-video`.
- Kling 3.0 is explicitly deferred.
- Provider identity remains `fal`.
- Scope stays in managed Vision video lifecycle.
- `FalVideoProvider` is model-aware, not hardcoded to Wan.
- Seedance request construction is model-specific.
- Seedance endpoint/status/result/cancel reconstruction is model-specific.
- Active fal video status/result/cancel lifecycle calls receive explicit,
  validated model identity.
- Restart cancel validates persisted `provider + model` before reconstructing
  Seedance cancel from request id.
- The implementation does not infer Seedance from missing queue URLs or
  request-id-only handle shape.
- Source frames are artifact-id only.
- Arbitrary path refs are rejected before media resolution/provider submit.
- PNG/JPEG/WebP source images are accepted within cap.
- Unsupported MIME and oversized source images fail before provider submit.
- Source transport uses bounded data URI.
- No public hosting or fal upload is added.
- No `"auto"` duration is exposed through Rook capability.
- `T2V` is rejected for Seedance.
- `I2V` and `Interp` work through existing video UI/bridge shape.
- Request-id-only durable fal lifecycle is implemented for Seedance if
  feasible.
- If request-id-only is not feasible, implementation stops for review before
  any URL persistence is accepted.
- Seedance durable records do not persist fal queue URLs, fal media URLs, data
  URIs, provider request JSON, provider logs, or provider result envelopes.
- Bridge responses do not expose fal request id, fal URLs, source bytes, data
  URIs, or provider envelopes.
- Generated artifact metadata does not add fal/source transport leakage.
- Automated tests use fake HTTP/fake providers.
- Live provider calls are manual Rhino smoke only.
- No native, MCP, public HTTP, or internal bridge exposure is added.

## Follow-Up

Future slices can decide:

- Kling 3.0 standard/pro image-to-video;
- Seedance fast tier;
- Seedance text-to-video;
- Seedance reference-to-video;
- richer audio options;
- provider-neutral video options UI;
- video ledger operational-only hardening;
- fal storage/upload abstraction;
- dynamic provider discovery;
- native/MCP/public video exposure changes.

## Highest-Risk Areas

1. Request-id-only fal video handles must still support restart cancel. This
   is the load-bearing architectural change.
2. Existing video ledger normalized prompt/media-ref persistence is older than
   the PR-17 image-job privacy posture. PR-18 should avoid new leakage and
   leave broader ledger hardening for a separate reviewed PR.
3. Source image size limits may be too conservative for real viewport captures.
   Keep the cap narrow until live smoke proves a need to raise it.
4. The video UI may assume Veo-style provider options. Seedance needs
   provider-correct `FalVideoOptions` without model-specific JS branching.
5. fal docs and queue response shapes can drift. Implementation must be fake
   HTTP first, with live smoke used only as a final schema check.

## Self-Review

- Scope is one curated Seedance source-video model.
- Kling 3.0 is deferred.
- Provider identity remains `fal`.
- The design treats PR-18 as model-aware fal video lifecycle work.
- Request-id-only durable fal handles are a hard acceptance point unless the
  implementation stops for review.
- Model identity must reach active and restart lifecycle calls explicitly; the
  provider may not infer Seedance from missing URLs.
- Source media is artifact-id only and bounded data URI transport.
- The design avoids native, MCP, public HTTP, and internal bridge exposure.
- Existing video ledger prompt/artifact-ref persistence is called out as
  inherited behavior, not expanded provider leakage.
- Tests cover provider, manager, restart cancel, bridge/UI, leakage, boundary
  scans, and live Rhino smoke.
