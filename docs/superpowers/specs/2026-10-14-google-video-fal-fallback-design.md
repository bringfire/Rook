# Google Veo video generation through fal.ai

Date: 2026-10-14

Status: Written design for human review. No implementation plan or product implementation is approved by this document.

Source baseline: `183ecc52439d1df5a60bf4e814a269e318534eb9` on `codex/vision-prompt-fal-fallback`. This baseline includes the locally deployed prompt-enhancement fallback. Main contains the earlier image fallback at `9057da3a`; the prompt commits must be retained when this feature is integrated.

## 1. Intent and observable outcome

Removing the Gemini API key from RookVision Settings should leave supported Veo 3.1 video requests usable through the existing fal.ai key. A configured Gemini key remains the primary route. Missing or definitively rejected Google credentials permit one compatible fal submission. Users may also deliberately choose a fal Veo model.

The selected model tier, prompt, video mode, duration, resolution, aspect ratio, seed, and ordered media inputs must survive routing. Explicit provider options must either retain their meaning or produce a compatibility error before fal upload or generation. Rook must disclose the effective provider and price, preserve cancellation and dispatch uncertainty across restart, and avoid creating another generation when an earlier submission might have succeeded.

The motivating request was job `a143b6ef-f855-4b5a-9b4b-48279355fa06`: `veo-3.1-generate-preview`, I2V, 1080p, eight seconds. Its persisted provider was `veo`; it failed with a missing-key error before a provider job was created. Acceptance includes that request through the Video panel with an untouched default options form and a valid source image.

The user approved Google-first credential fallback, explicit fal choices, Standard/Fast/Lite mappings, durable jobs, correct pricing and attribution, and deterministic race tests. This spec proposes a 20-minute total job budget and the provider-default option policy below; written-spec approval is needed for those concrete choices.

## 2. Provider availability is a release dependency

On the research date, fal's checked Standard, Fast, and Lite Veo 3.1 API pages carry a **November 17, 2026 deprecation notice**. The pages still publish schemas and queue examples. That establishes documented endpoints, not continued availability after that date. The inspected documentation did not establish a successor binding. [Standard API](https://fal.ai/models/fal-ai/veo3.1/api), [Fast API](https://fal.ai/models/fal-ai/veo3.1/fast/api), [Lite API](https://fal.ai/models/fal-ai/veo3.1/lite/api).

The requested solution is long term. The table in section 5 therefore records verified candidate mappings, not permission to ship a solution whose sole provider bindings expire a month later.

Before execution that enables new provider submissions, the implementation plan must contain authoritative evidence of either a supported successor for each enabled tier/mode or continued support that resolves the published notice. Recheck schemas, pricing, and lifecycle URLs against that evidence, and revise this written spec if identity or semantics change. Also revalidate the Google primary model IDs and REST operation contracts rather than relying solely on the repository's older rate-card comments. A different model family or a Fast-for-Lite substitution requires a revised design; it is not a migration shortcut.

If this evidence remains unavailable, the architecture can be reviewed and planned, but new fal Veo submissions remain disabled and the product is not reported as satisfying the feature. No live probe or successful request overrides a published retirement notice.

Every enabled binding must carry a documentation source, verification date, explicit endpoint identity, and any known new-submission cutoff. When only a retirement date is published, use the start of that UTC date as a conservative cutoff. Check eligibility both during estimation and immediately before dispatch. Expiry blocks new submissions while preserving known-job polling, result retrieval, and cancellation bindings as long as the provider still supports those operations. Rook cannot guarantee that a retired provider will keep its lifecycle API available.

## 3. Scope and chosen approach

Extend the managed video subsystem and existing fal transport. Keep `RookNative` as the HTTP owner and use the existing video operations through its managed callback bridge. Do not add a server, provider SDK, external dependency, webhook service, or new native project configuration.

The chosen approach is a video submission coordinator that selects a provider, translates and validates a request, and obtains durable dispatch admission from `VideoJobManager`. The manager remains the sole owner of jobs, stop reasons, ledger writes, and publication. The providers remain responsible for their transport and result parsing.

Alternatives considered were manual fal choices without automatic fallback, which does not preserve the existing Google-model workflow, and switching all Veo requests to fal, which disregards the approved Google-first behavior. Neither is selected.

Included:

- The three existing Google Veo 3.1 model IDs and corresponding supported fal choices.
- T2V, I2V, interpolation, and reference-conditioned T2V where the exact tier and endpoint support them.
- Estimate, submit, status, list, fetch, cancel, startup reconciliation, artifacts, Video panel, and Settings projections.
- Targeted repairs to shared video transition/publication helpers needed to make the new paths durable, with regression coverage for existing providers.

Excluded:

- Automatic routing for Veo 2, Veo 3.0, Vertex AI, or non-Veo video models.
- Video extension, multiple-output generation, new audio controls, arbitrary endpoint entry, automatic tier changes, or automatic prompt rewriting.
- Automatic job resume or generation resubmission after restart.
- Redesigning image fallback or prompt enhancement; replacing the existing Video panel.

## 4. Current code and ownership

`VideoSubsystemFactory` builds the shared registry and `VideoJobManager` from the generation secret store. Google Veo reads `gemini.api_key`; fal reads `fal.api_key`. `VisionProviderRegistrations` already registers Google, fal, and Vertex video providers.

`DefaultVideoProviderRegistry` binds a model to its provider, options codec, capability, and pricing model. `VeoProvider` calls Google's long-running prediction API. `FalVideoProvider` currently serves Wan, Seedance, and Kling; no fal Veo model is registered.

`VideoJobManager` currently owns queue admission, background submission/polling, materialization, artifact publication, cancellation, and restart reconciliation. Its dispatch-aware callback sets an in-memory flag; that is insufficient evidence after a crash. Its existing transition gate and provider-handle extension are the starting patterns, not grounds for claiming the new durability requirements already hold.

`JsonlVideoJobLedger` stores schema-version-1 snapshots at `%APPDATA%/Rook/video/job-ledger.jsonl`, preserves extensions, and reconstructs persisted provider handles. `VideoOpHandler` owns wire validation/projection. The Video UI is the module in `src/Rook/UI/Vision/Resources/app.js`; it already owns model controls and cost confirmation.

Keep native, managed, and Python contracts consistent. The intended public changes are additive JSON fields and new model descriptors on existing operations. Audit native/Python parsers and UI consumers during planning; update a consumer if it discards the new evidence. No ABI or new HTTP route is presently required.

## 5. Candidate model and endpoint mapping

The fal public model IDs represent tiers; endpoint selection additionally depends on mode and media. All rows are subject to section 2's admission requirement.

| Requested Google model | Explicit fal model / effective tier ID |
| --- | --- |
| `veo-3.1-generate-preview` | `fal-ai/veo3.1` |
| `veo-3.1-fast-generate-preview` | `fal-ai/veo3.1/fast` |
| `veo-3.1-lite-generate-preview` | `fal-ai/veo3.1/lite` |

| Mode / inputs | Standard endpoint suffix | Fast endpoint suffix | Lite endpoint suffix |
| --- | --- | --- | --- |
| T2V, no media | root | `/fast` | `/lite` |
| I2V, start frame only | `/image-to-video` | `/fast/image-to-video` | `/lite/image-to-video` |
| Interpolation, first and last frames | `/first-last-frame-to-video` | `/fast/first-last-frame-to-video` | `/lite/first-last-frame-to-video` |
| T2V with reference frames | `/reference-to-video` | `/fast/reference-to-video` | unsupported |

Suffixes are relative to `fal-ai/veo3.1`. API sources: [Standard I2V](https://fal.ai/models/fal-ai/veo3.1/image-to-video/api), [Fast I2V](https://fal.ai/models/fal-ai/veo3.1/fast/image-to-video/api), [Lite I2V](https://fal.ai/models/fal-ai/veo3.1/lite/image-to-video/api), [Standard interpolation](https://fal.ai/models/fal-ai/veo3.1/first-last-frame-to-video/api), [Fast interpolation](https://fal.ai/models/fal-ai/veo3.1/fast/first-last-frame-to-video/api), [Lite interpolation](https://fal.ai/models/fal-ai/veo3.1/lite/first-last-frame-to-video/api), [Standard references](https://fal.ai/models/fal-ai/veo3.1/reference-to-video/api), [Fast references](https://fal.ai/models/fal-ai/veo3.1/fast/reference-to-video/api).

Expose T2V/I2V/interpolation for all three tiers and references only for Standard/Fast. Advertise Standard/Fast at 720p, 1080p, and `4k`; Lite at 720p and 1080p. Limit durations to 4/6/8 seconds, aspect ratios to 16:9 or 9:16, and output count to one. As a conservative Rook compatibility profile, retain eight seconds for 1080p/4k and reference requests, and at most three ordered references. A permissive schema field does not establish a broader Rook capability.

Reference requests must be T2V with no start/end frames. Reject reference-plus-start/end combinations; do not discard one input family to fit an endpoint. I2V forbids an end frame, and interpolation requires both frames. Lite references remain unsupported even if another tier could generate them.

Preserve the selected aspect ratio explicitly; do not replace it with fal's `auto` default. Convert integer seconds to the endpoint's duration string only in the fal payload builder. Accept optional seeds only on endpoints whose schema exposes that field; the checked reference schemas do not, so reference-plus-seed requests are incompatible. Do not drop the seed.

## 6. Options and media compatibility

### Provider defaults versus explicit Google controls

Fal's checked schemas expose audio and moderation controls, but not Google's `person_generation`. A safety-tolerance value is not evidence of equivalent people-generation semantics. [Fal Standard schema](https://fal.ai/models/fal-ai/veo3.1/api), [Google Veo API parameters](https://ai.google.dev/gemini-api/docs/veo).

The default Video-panel workflow must permit automatic routing without pretending this control translates:

- In the affected Veo 3.1 form, an untouched Google people control is represented as omitted `person_generation` in the supplied `options` object. The Google adapter fills its existing mode-specific default (`allow_all` for T2V without media, `allow_adult` for I2V/interpolation/reference-conditioned requests), and records that the supplied value was omitted. The UI explains that automatic fallback uses the effective provider's defaults. Other Google model families retain their existing option contracts.
- Any explicitly supplied `options.person_generation`, including a value equal to the usual Google default, remains a Google-specific constraint. Such requests may use Google normally, but cannot fall back automatically without documented equivalent support. Report a field-specific incompatibility if fallback becomes necessary.
- Existing API requests that explicitly supply this field remain valid for Google; do not infer that they meant an untouched UI default. New Google requests may send `options: {}` to choose provider defaults. Preserve both the supplied options and the normalized Google options in durable evidence.
- An explicitly chosen fal tier uses a dedicated Veo fal options codec. For this release the profile is fixed: audio enabled, prompt auto-fix disabled, moderation at the documented default. Reject unknown options instead of silently ignoring them. Do not reuse the empty Wan/Seedance/Kling options codec to accept unsupported Veo fields.

The fal payload sends `generate_audio: true`, `auto_fix: false`, and the documented default moderation value explicitly. These values are part of the reviewed profile, not a translation of `person_generation`. No extra audio/moderation UI controls are introduced here. A schema change that removes a required profile field makes that binding unavailable until reviewed.

### Other incompatibilities

Fal requires a nonempty prompt on the proposed endpoints. An otherwise valid Google I2V/interpolation request with no prompt remains eligible for Google, but fallback returns a prompt compatibility error rather than inventing text. Preserve the prompt verbatim when present; do not run enhancement or rewrite it during provider routing.

Validate the effective request before upload or generation. Reject unsupported duration/resolution combinations, extra output counts, unrepresentable options, mixed media roles, or expired bindings. Never downscale, shorten, reorder, deduplicate reference slots, convert Lite to Fast, or replace interpolation with I2V automatically.

Reuse artifact-based media resolution and the fal source-frame transport. Validate all input bytes before the first upload. The initial conservative source profile admits PNG/JPEG/WebP, a maximum of 8,000,000 bytes per image, and decoded dimensions of at least 720 pixels on the shorter side. These byte/size checks alone do not establish framing compatibility. The 8 MB limit and 720p-or-higher guidance are documented for I2V; using this profile for other modes is a deliberate conservative Rook policy, not a claim that fal enforces identical limits everywhere. [I2V API](https://fal.ai/models/fal-ai/veo3.1/image-to-video/api).

Each admitted media endpoint binding owns an explicit source-framing policy, evaluated against decoded input dimensions and the selected output aspect ratio before any fal upload. Standard/Fast I2V documentation says other input ratios are cropped; the Lite I2V schema also specifies 16:9 or 9:16 input. For all three I2V tiers, Rook requires the source to match the selected 16:9 or 9:16 ratio exactly. Compare positive integer dimensions by 64-bit cross multiplication (`width * 9 == height * 16` for 16:9; `width * 16 == height * 9` for 9:16), without a tolerance that could conceal a crop. Matching the selected output ratio is a conservative Rook restriction in addition to the documented supported input ratios. [Standard I2V](https://fal.ai/models/fal-ai/veo3.1/image-to-video/api), [Fast I2V](https://fal.ai/models/fal-ai/veo3.1/fast/image-to-video/api), [Lite I2V](https://fal.ai/models/fal-ai/veo3.1/lite/image-to-video/api).

Apply the same conservative selected-ratio requirement to both frames on interpolation bindings, with errors identifying `start_frame` or `end_frame`. Reference endpoints retain their separately verified policy; do not assume reference images use I2V's framing semantics. Verify source preprocessing/cropping behavior for each admitted binding as part of section 2's profile review. Reject incompatible images rather than allowing Rook or the provider to crop, pad, resize, or switch aspect ratios implicitly.

For example, a 1024x1024 PNG passes the byte/minimum-size checks but must fail I2V compatibility with an actionable `start_frame` error: “fal.ai Veo 3.1 image-to-video requires a source matching the selected 16:9 ratio; this source is 1024x1024. Supply a matching source or use the Google route.” No fal upload or generation is permitted. This is conditional fallback compatibility, so it does not block an otherwise valid Google primary request that succeeds without fallback.

Shared media may be resolved/uploaded once, but the outgoing first/last roles and reference list must preserve every original position, including repeated references. Retain original artifact parents. Uploads are preparation, not proof of generation dispatch. Stop checks apply before each upload and before generation admission. Use existing bounded media lifetime/storage controls; persist no credentials or unneeded upload URLs in user-visible routing evidence.

## 7. Credential routing and failure classification

The coordinator validates the requested Google request using its current codec/capability. It computes conditional fallback compatibility without preventing a valid Google-only request from using Google.

| Situation | Behavior |
| --- | --- |
| Gemini key configured | Make one Google submission attempt. |
| Gemini key absent or whitespace | Select the matching fal tier, subject to credential, compatibility, pricing, and lifecycle admission. No Google HTTP request. |
| Google submission definitively rejects its key | Persist the safe rejection evidence, then select one matching fal attempt if permitted. |
| Explicit fal model selected | Use fal directly; never attempt Google or fabricate an automatic-fallback receipt. |
| Neither relevant key available | Return configuration guidance, with no upload/generation and no false credential validation. |
| Secret lookup throws | Report secret access failure; do not reinterpret it as a missing key. Read the fal secret lazily so an unused unreadable fal credential cannot block Google. |

Use the existing `GoogleCredentialErrors` closed classifier: HTTP 401 with structured `UNAUTHENTICATED`, or the permitted 400/401/403 status with Google `ErrorInfo`, `API_KEY_INVALID`, `googleapis.com`, and compatible service metadata. A generic 403, human-readable message, reserved marker supplied by upstream, or malformed response is not rejection evidence.

Only submission-stage credential failure permits provider switching. No fallback on quota/429, billing or policy errors, ordinary permissions, 5xx, transport failure, timeout, incomplete success response, or failures during polling, fetching, or publication. Once a Google operation or fal request is accepted, the job is permanently bound to that operation/provider.

Normalize fal missing-key and definitive 401 rejection separately from generic 403, quota, policy, transport, and result errors. Carry safe credential evidence through handler errors, durable records, status/list/fetch/cancel responses, and UI. Never invalidate Gemini because fal failed, or fal because an ambiguous permission failure occurred. Credentials remain request headers only; raw provider bodies and exception text do not enter routing receipts, public errors, or console diagnostics.

## 8. One coordinator and one durable job

Estimate and submission must share the same tier/endpoint/options compatibility resolver. Submission additionally performs credential verification through the real attempt and durable dispatch admission. Avoid separate handler-only fallback logic that bypasses the background manager.

For automatic fallback retain one Rook job ID, creation timestamp, concurrency slot, admitted deadline, requested identity, and input provenance. Change the effective request, resolved provider/model, options, and active pricing together under the job transition gate. Every later poll, fetch, remote cancel, and artifact operation uses that effective binding, not the originally selected Google provider.

Route, provider handle, confirmed quote, pricing, timer, first-stop latch/token, and cleanup state are per job. Shared registries/transports/coordinators must not keep a mutable current-provider/current-job binding that can leak between concurrent requests.

Persist typed, validated extensions using versioned keys on the existing schema-1 record:

- `video_execution`: requested provider/model and supplied options; current effective provider/model/endpoint and normalized options; route-reason/phase; accepted quote/fingerprint/cap; execution deadline; first stop reason; per-provider dispatch/response evidence; remote-cleanup status.
- `video_route`: only for automatic Google-to-fal fallback, with requested/effective identity and `gemini_key_missing` or `gemini_key_rejected` reason.
- `credential_failure`: independently optional, naming the actual provider, secret-key identifier, and normalized kind/source. It does not require `video_route`; direct fal failures have no automatic-fallback receipt.
- Existing `provider_handle`: the accepted request/operation ID and validated lifecycle binding. Preserve it when routing/stop snapshots are updated.

Unknown execution-extension versions or corrupt critical routing fields cannot authorize dispatch or price recomputation. Report a safe ledger warning and stop affected work; preserve the original record for diagnosis. Unrelated unknown extensions retain existing round-trip behavior.

Legacy schema-1 jobs without new extensions continue to list/fetch/cancel using their recorded provider and handle. They do not gain fallback retrospectively. The generic registry's first-provider-by-name lookup must not accidentally route a fal Veo handle to a Wan/Seedance/Kling-only implementation. All fal registrations must share a compatible lifecycle dispatcher or select it from a validated persisted binding.

## 9. Durable transitions and dispatch uncertainty

Required ordering for every affected non-idempotent provider submission:

1. Admit the job and persist its deadline, requested identity/options, accepted estimate fingerprint when supplied, and accepted pricing bound.
2. Persist the selected effective route, endpoint/profile revision, and effective estimate before source upload or generation.
3. After preparation, acquire the transition gate, inspect the first-stop latch, deadline, and latest durable state/stop reason, and reject admission if stopped or terminal.
4. Append and durably commit `dispatch_state: intent_recorded` for that provider attempt **before** calling HTTP send. The intent and terminal-stop commits are serialized by the same gate. In-memory callback state cannot substitute for this record.
5. When the intent append returns, recheck the first-stop latch/token before admitting HTTP send; a stop observed while persistence was blocked prevents send. Send at most once. A diagnostic `generation_dispatch_attempted` flag may become true at the send boundary; it is not the authoritative restart evidence. An intent without a definitive response must always be treated as potentially dispatched, even if that flag is false.
6. Persist a valid accepted handle, or closed rejection evidence, before acknowledging the result or attempting fallback. A crash before this append leaves an uncertain attempt; restart cannot infer the missing response.

No new upload/generation is admitted after the first-stop latch wins, even if the stop append is still pending or fails. A stop racing after dispatch admission means submission may have reached the provider; represent that uncertainty rather than claiming no remote work. Ledger append failure prevents any later new submission or publication. Surface a persistence failure, keep any known handle for explicit cleanup, and do not acknowledge a durable state that was not committed.

Do not auto-retry Google/fal generation POSTs, even on nominally retryable failures. Set `X-Fal-No-Retry: 1` on Veo queue submissions to disable provider-side queue retries, and keep `auto_fix: false`. A client request ID or seed does not establish provider idempotency. [Fal queue retry contract](https://fal.ai/docs/documentation/model-apis/inference/queue).

After intent, a timeout, disconnect, malformed acceptance, or success without a valid request/operation ID produces `Interrupted` with safe `submission_unknown` evidence. No provider switch or second generation occurs. The UI says that the remote outcome is unknown and requires a deliberate new generation action, never silently retries.

## 10. Queue lifecycle, stop reasons, and restart

Use fal's queue API for video generation; do not hold a synchronous generation HTTP call open. Persist the accepted request ID and allowlisted status/result/cancel bindings. Validate provider-returned URLs, HTTPS origins, request-ID association, and the expected Veo application binding before attaching the fal key. Do not derive lifecycle paths by blindly appending to a mode suffix. Existing known-endpoint construction may be reused only with verified Veo lifecycle roots. [Fal queue contract](https://fal.ai/docs/documentation/model-apis/inference/queue).

Queue completion is not successful materialization: retrieve and validate the model result, then materialize a bounded video artifact through the existing video materializer. Reject absent/wrong result types, missing or unsafe media URLs, invalid media, and provider-declared failures. Preserve approved output bounds and artifact parent lineage. Provider failures never trigger a fresh generation.

### Budget

Proposed requirement: one **20-minute total job budget**, starting when the initial queued job is durably admitted. It includes local queue wait, media resolution/upload, Google and possible fal submission, fal queue wait, polling, fetching, materialization, sidecar attempts, and final publication. Persist the absolute UTC deadline and use one injected clock/timer for deterministic tests. Fallback and individual HTTP calls cannot reset or extend it. A non-cooperative transport must not hold the local job open beyond the budget or permit late publication.

Existing native bridge request timeouts remain request-level limits; background video generation is still a job. If a bridge start response is lost, the UI refreshes job history and reports uncertainty instead of automatically creating another job.

### First observed stop and cancellation

Capture the first observed user cancellation, shutdown, or deadline atomically when its observer fires, then signal the per-job execution cancellation token immediately. Neither action waits for the transition gate, a ledger append, or remote cleanup. Dispatch/publication fences check the latch as well as the token and durable record; non-cooperative transports remain bounded by cancellation-aware waits. Completion and stop use an explicit shared admission decision: an observed stop before completion admission prevents completion; completion admitted first may finish its durable commit before a later stop. A later Cancel must not erase an already observed deadline or shutdown, even while the earlier observer awaits its terminal append. A durably completed job is immutable to subsequent stop requests.

Persist the selected stop under the transition gate independently of execution signalling. A blocked stop append leaves the durable-acknowledgement request pending, but execution is already stopped: no new upload, generation, poll, fetch, provider switch, or publication may proceed. While the process is alive, status exposes the first local stop reason, `execution_stopped: true`, and `stop_persistence: pending` alongside the last durable state rather than falsely reporting durable cancellation. If the append fails, retain the first-stop latch/cancelled token, return or surface a safe persistence error with `stop_persistence: failed` and durability-unknown evidence, and do not acknowledge durable cancellation or re-enable work. Stop monitoring and publication without implying that remote work stopped. Known-handle cleanup is independently bounded and may proceed best effort despite this persistence failure. A later explicit persistence retry can record the original reason; it cannot restart the job or replace that reason. Restart relies only on surviving records and reports reconciliation/dispatch uncertainty when the stop itself could not be persisted.

Do not acknowledge completion/cancellation before its selected terminal decision is durable, and do not claim completion when its append fails. The 20-minute budget bounds local execution, not the latency or success of an unresponsive persistence device; that device may delay acknowledgement but cannot extend execution.

The terminal record to persist for user cancellation before dispatch admission is `Cancelled` with dispatch-not-started evidence. After admission with no known handle, it is `Interrupted` with submission uncertainty and the original user-cancel reason. With a known handle, user cancellation records `Cancelled`, meaning local cancellation with initially unknown remote cleanup, and attempts remote cancellation against the effective provider independently of execution signalling and persistence success. Deadline/shutdown always select `Interrupted`; do not label them as user cancellation. Cleanup uses an independent bounded token (maximum 30 seconds) and cannot extend local job execution or publication.

Persist cleanup outcomes such as `not_dispatched`, `requested`, `accepted`, `already_completed`, `not_found`, `failed`, and `unknown`, without changing the winning stop reason. An accepted fal cancellation is not a guarantee that running generation or billing stopped. A 400 with documented `ALREADY_COMPLETED` is different from arbitrary 400; a 404 is not completion evidence. Parse the provider's response before classifying it. [Fal cancellation semantics](https://fal.ai/docs/documentation/model-apis/inference/queue).

The accepted submission can return after local interruption. A late valid handle must be appended to the terminal record without reopening the job, publishing an artifact, or changing its reason. Attempt bounded remote cleanup if a handle becomes known in the same process; failure remains visible and permits later explicit cleanup. If the handle cannot be persisted, preserve/report the failure and attempt best-effort cleanup with the known handle; do not conceal remote-work uncertainty.

### Restart

Continue the current no-auto-resume policy. Restore the latest durable snapshot, preserve route/pricing/handle/stop evidence, and mark affected nonterminal jobs `Interrupted`. `intent_recorded` without a definitive response means potentially submitted; an absent provider job ID does not mean no generation occurred.

Do not recreate uploads, resubmit generation, switch providers, or automatically restart polling. Explicit cleanup of an interrupted job with a known handle remains available even when the current model binding is no longer eligible for new submissions. This requires a cleanup path that does not return early merely because the local state is terminal. Cleanup updates metadata only; it cannot turn an interrupted job into a newly completed or cancelled one. If no handle survived the crash, report that Rook cannot cancel unidentified remote work.

## 11. Publication and artifact attribution

For affected jobs, stop/complete decisions use the latest durable snapshot and the same transition gate, not a stale worker record. Publication requires no winning stop and a valid accepted effective binding.

Use the existing create-and-delete-on-failure pattern only while artifact creation is provisional, before a durable `Complete` record references its ID. Include `video_job_id` and a provisional-publication marker in the initial artifact metadata. Gallery/list/fetch visibility for affected artifacts must check the referenced job's durable completion and matching result ID; the artifact's existence alone does not authorize exposure. After a successful terminal commit, finalize its marker as a best-effort operation within the remaining budget; restart can finalize a still-provisional marker when the durable completed record proves ownership.

Marker-finalization failure after durable completion must retain the video and sidecars, leave the job `Complete`, and surface a safe `artifact_marker_pending` warning. The completed ledger record and matching artifact ID remain authoritative for gallery/fetch visibility even while the marker is provisional. No general exception/deletion handler may delete a durably completed artifact, convert its job to Error/Interrupted, or trigger regeneration. Marker retry/restart repair is idempotent and does not reprice or republish the video; repeated repair failure retains the completed artifact and warning.

Recheck the first-stop latch and deadline at completion admission, then serialize the terminal decision with stop commits under the transition gate. If cancellation/deadline/append failure wins, remove the provisional video and sidecars; no completed gallery item is exposed. On startup, remove a provably provisional owned artifact when its known affected job has been durably stopped/reconciled and does not reference it as a completed result. An unknown job or unreadable ledger does not authorize deletion: hide/quarantine the provisional entry and report the inconsistency. Do not sweep unrelated gallery items.

Poster/frame sidecars remain best effort; failures are recorded separately from a valid video's result. They must obey the remaining total budget and cannot keep publication open indefinitely. If the job deadline/stop wins while sidecars are pending, the whole job follows the stop rule and its provisional artifact is removed.

Successful artifact metadata records Rook job ID, requested/effective provider/model, endpoint/profile revision, automatic route receipt if present, original inputs, safe effective options, and effective **estimated** pricing. Never describe an estimate as an invoice or actual charge. Credentials, raw provider errors, and unnecessary signed transport URLs are excluded from public attribution.

## 12. Estimates and cost confirmation

Bind pricing to the effective fal tier/profile and selected endpoint rather than reusing Google's rate card. Audio is enabled in this release's fal profile. Research-date published audio rates per generated second were:

| fal tier | 720p | 1080p | 4k |
| --- | ---: | ---: | ---: |
| Standard | $0.40 | $0.40 | $0.60 |
| Fast | $0.15 | $0.15 | $0.35 |
| Lite | $0.05 | $0.08 | unsupported |

Sources: [Standard pricing](https://fal.ai/models/fal-ai/veo3.1), [Fast pricing](https://fal.ai/models/fal-ai/veo3.1/fast), [Lite pricing](https://fal.ai/models/fal-ai/veo3.1/lite). These are a dated candidate rate card; revalidate per endpoint before enablement and replace with the section-2 admitted binding's documented rates if they differ. Use decimal arithmetic and a distinct pricing source/revision. Unknown pricing blocks new submissions instead of treating cost as zero.

For a missing Gemini key, estimate the compatible fal route immediately. For a configured Google key, return the Google estimate and any compatible/eligible fallback estimate as conditional candidates, plus the maximum single-generation estimate. Do not add the two generation estimates together: a definitive Google authentication rejection is not a successful Google generation. Uncertain Google submission never proceeds to fal.

Extend estimate projections additively with requested/effective identity, route candidates, compatibility/lifecycle eligibility, pricing revisions, `maximum_estimated_cost_usd`, and a versioned `estimate_fingerprint`. Keep the existing primary estimate fields meaningful and source-attributed. The confirmation UI shows both conditional providers/prices where relevant and the maximum bound it is authorizing.

The fingerprint is a snapshot identity, proposed as `v1:` plus SHA-256 of a canonical estimate document. That document contains the normalized request (exact prompt, mode/tier, duration, resolution, aspect, seed, output count, supplied-options provenance and normalized options), ordered media IDs/roles and byte-content digests, configured-secret presence/route eligibility, routing-policy revision, and the complete set of conditionally authorized provider routes. Each candidate includes its binding/endpoint identity, capability/source-framing/profile and lifecycle revisions, pricing source/revision, currency, unit rate, total, and the quoted maximum. Preserve array order/repeats and use deterministic property ordering and decimal formatting; exclude credentials, transport URLs, the fingerprint itself and attempt-result state. Estimation may resolve/read source media to bind their digests, but performs no provider upload or generation.

The UI submits both `estimate_fingerprint` and `max_estimated_cost_usd` from the confirmed quote. The manager recomputes the canonical quote and validates the fingerprint at job admission and again before each generation-dispatch admission. A different request, source bytes, candidate eligibility, binding/profile, lifecycle revision, or pricing revision produces a safe `estimate_stale` error and requires a fresh estimate and human confirmation **even when the new amount is lower or remains within the old cap**. Check the numeric cap independently; a matching fingerprint cannot authorize a chosen route exceeding it. A fingerprint supplied without a numeric cap is invalid. Persist the confirmed fingerprint and accepted quote separately from the effective route/pricing.

Choosing a fal candidate already included in the confirmed route set after a definitive Google credential rejection does not itself invalidate that quote. Recheck that candidate's current binding/profile/rates and cap against the same confirmed snapshot before fal dispatch; changes do invalidate it. Do not fingerprint only the currently selected attempt or treat a normal authorized fallback as repricing. A stale quote discovered after Google rejection or while queued stops before any next provider submission; refresh the quote and ask the user to create a deliberately new job rather than silently continuing or replaying a potentially submitted attempt.

Invalidate cached estimates on every request/route/credential/price-bearing change and bind asynchronous estimate results to the exact current request. Do not auto-confirm a changed quote. The fingerprint detects stale snapshots; it is neither provider idempotency nor a billing guarantee.

Both new submit fields remain optional for legacy API callers: omitting both retains the existing unbounded-submit contract. Supplying only `max_estimated_cost_usd` explicitly authorizes any otherwise compatible, admitted route within that cap; it does not request detection of an old quote's pricing/profile revision. Clients requiring revision-aware confirmation must supply the matching fingerprint and cap. Document these distinct contracts; the Video UI always uses the revision-aware pair. No new mandatory consent field is added to non-Veo routes.

Persist the initial accepted quote/fingerprint/cap separately from the current effective `Pricing` snapshot. On fallback, append the route and fal pricing atomically under the transition gate; retain the original requested estimate for audit. Listing, status, artifact metadata, and fetch report the effective estimate after routing, with the original selection available separately. Existing completed jobs are never repriced using today's card.

## 13. UI, API, and credential presentation

Google model labels stay Google-first and indicate that a compatible fal fallback is configured, unavailable, or expired. Explicit fal tier labels show fal.ai. Settings explain which Veo 3.1 requests can use fallback and which provider controls are incompatible. Key presence is configuration evidence, not a successful credential test.

When neither route is usable, disable submit with an actionable reason. A configured fallback does not disable a Google model just because its Gemini key is absent/rejected. Request-specific incompatibility and lifecycle expiry remain visible. Do not automatically change the selected tier or delete prompt/frames/references after failure.

After routing, the job card, details, status errors, and completed gallery item show the effective provider and the requested selection separately, for example: “Veo 3.1 via fal.ai — Gemini key missing.” Direct fal choices say “Veo 3.1 via fal.ai” without a fallback claim. Failure during upload/validation can identify the selected fallback provider while explicitly saying generation was not dispatched.

All relevant responses carry independent safe provider/model and credential evidence. Use additive `requested_provider`, `requested_model`, `provider`, `model`, `execution_phase`, `dispatch_state`, `stop_reason`, `remote_cleanup`, and `credential_failure` fields on job/error projections; `provider`/`model` name the current selected effective binding, not proof of successful generation. Automatic-fallback responses additionally carry `video_route`. Existing job IDs, state strings, artifacts, request summaries, pricing shapes, and structured-error fields remain usable. Legacy records may omit the additive fields; the UI then uses recorded provider/model and never invents a fallback receipt. Only an explicitly rejected credential changes that provider's warning overlay. Generic 403, compatibility, timeout, materialization, and publication failures do not invalidate keys.

Unknown submission outcomes remain visible across reload/restart using ledger evidence. A deliberate new generation requires a confirmation that another remote generation may already exist. This is an uncertainty warning, not a promise of cross-request or provider idempotency.

## 14. Required deterministic acceptance tests

Hermetic tests exercise real coordinators, codecs, adapters, ledger serialization/restoration, handlers, and the actual embedded UI with injected transports/clocks. Use held responses and commit barriers rather than timing sleeps or calls to live providers. Transport fakes record HTTP method, endpoint, payload, headers, upload count, and generation count; test output must contain no real keys or prompt content from production records.

### Routing and compatibility

1. The motivating Standard I2V 1080p/eight-second Video-panel request, untouched provider defaults, no Gemini key, configured fal key: one fal generation, no Google generation, correct source, prompt, estimate and provider attribution.
2. All admitted tier/mode mappings, including Fast references and Lite interpolation; no Lite references or tier substitution.
3. Configured Google succeeds: zero fal secret reads/uploads/generation. Unreadable unused fal secret does not block Google.
4. Closed missing/rejected-key matrix permits fallback; generic 403, malformed auth body, spoofed markers, quota/429, billing/policy/5xx/network/timeout do not. Google polling/fetch credential failures never switch providers.
5. Direct fal missing-key/401/generic-403 errors survive handler/status/list/UI projection with credential evidence and no fallback receipt.
6. Untouched UI default omission normalizes correctly for Google and permits fal's declared default profile; any explicit Google people control blocks fallback, including values equal to defaults. Explicit legacy API Google requests still use Google normally.
7. Empty prompt, mixed start/reference media, extra end frame, missing interpolation frame, seeded reference request, invalid media/size/dimensions/aspect ratio, unsupported duration/resolution/count, unknown options, or expired binding: no fal upload or generation. Test a 1024x1024 PNG for Standard/Fast/Lite I2V with a decoded-dimension `start_frame` error before upload, including missing-key fallback, rejected-key fallback, and explicit fal selection. Test exact matching 1280x720/720x1280 sources, selected-output orientation mismatch, near-match ratios that would crop, and both interpolation frame roles. An otherwise valid Google primary can still succeed on an input incompatible with fal.
8. Preserve every ordered reference slot, repeats, media roles, aspect, seed where supported, and artifact parents. No implicit crop/resize, prompt rewriting, or output shortening.

### Durable dispatch and stop races

9. Hold each provider's submission response after send. Capture the actual ledger, restore a fresh manager, and assert potentially-dispatched/Interrupted evidence even if `generation_dispatch_attempted` is false. No restored generation or fallback request.
10. Fail the append for route preparation or dispatch intent: no subsequent upload/generation. Fail accepted-handle persistence: no polling/publication, visible persistence error and bounded cleanup of a known handle.
11. Crash after Google rejection before its durable append: no fal attempt on restart. After durable rejection, crash before/after fal intent: correct provider/attempt evidence and no auto-resubmit in either case.
12. Stop while queued, during upload, between route preparation and dispatch, during held Google/fal submission, during poll/result fetch/materialization/sidecars, and while awaiting final commit. The observed first-stop latch and immediately signalled token prevent later work/publication independently of the stop append. Block that append with a deterministic barrier, then separately fail it: execution cancellation must be observable before the barrier is released, no new upload/generation/poll/fetch/publication occurs, no durable cancellation success is acknowledged, and a failed append surfaces persistence/durability-unknown evidence without replacing the reason. Release/retry persistence and restore snapshots to distinguish a durably stopped record from restart reconciliation when the stop could not be saved.
13. Deadline then Cancel, Cancel then deadline, and shutdown races preserve the first stop reason across snapshots/restart, including an observer held before its durable append. Completion checks the first-stop latch and serialized terminal ordering.
14. One timer/cap covers queues, Google and fal attempts, materialization, sidecars and publication. Non-cooperative transport cannot extend it; late results do not publish or retry.
15. A late accepted handle attaches to the existing interrupted record, receives bounded cleanup, and does not reopen/reprice/complete the job. Cancellation API accepted/already-completed/not-found/failed/unknown outcomes retain the original stop reason.
16. Interrupted job cleanup after restart/deprecation uses the persisted effective provider/handle. Same-provider-name registrations cannot misroute it. Unknown/corrupt execution extensions do not authorize work; legacy records remain readable and known-handle cleanup is preserved.

### Pricing, publication, and consumers

17. Distinct Google/fal candidate estimates, decimal totals, cap enforcement, canonical fingerprint determinism (including media order/repeats/options provenance), and actual fallback pricing in the ledger and UI. A price/profile revision change below the old numeric cap must fail fingerprint validation at admission and pre-dispatch with `estimate_stale`, no next generation, and fresh UI confirmation. Also test lower-price revisions, changed source bytes/request/binding/eligibility, normal fallback to an unchanged quoted candidate, rejected stale async estimate responses, fingerprint-without-cap rejection, and the explicitly distinct legacy unbounded/cap-only contracts. No old job repricing, invented charge, or unknown-price zero.
18. Provider Complete without a valid video, download failure/oversize/unsafe URL, sidecar failure, cancellation during provisional creation, and terminal append failure produce the specified result with no leaked completed artifact. Restart cleanup deletes only provably provisional artifacts owned by affected jobs.
19. Real managed envelopes through bridge/HTTP/Python consumers and the embedded Video UI retain route, credential, stop/uncertainty, and pricing evidence. Forms and input media survive errors. Labels contain readable separators and no replacement characters.
20. Regression coverage keeps existing image/prompt fallback and Google/Vertex/Wan/Seedance/Kling video options, handles, pricing, stop semantics and sidecar behavior working. No broadening of Vertex's local-monitoring cancellation into remote cancellation.
21. Lifecycle gate tests refuse expired/unverified bindings and allow documented replacement bindings only after the reviewed mapping/profile/rates are updated. A fake successful endpoint response cannot bypass the gate.
22. Two simultaneously admitted jobs take different routes (Google success for one; definitive Google rejection and fal for the other) with interleaved held submit/poll responses. Each keeps its own effective binding, provider handle, quote/fingerprint, pricing, timer, stop reason, and attribution. Cancelling/expiring one cannot alter, cancel, reprice, or publish the other. Restore the serialized snapshots and verify the two bindings remain distinct; each generation count is correct.
23. Fail marker finalization after the matching `Complete` ledger commit. Status remains Complete, the same video and sidecars remain present and fetchable/gallery-visible, `artifact_marker_pending` is surfaced, and no delete/regeneration/repricing occurs. Restart with the provisional marker and matching completed record: idempotent repair succeeds or retains the artifact/warning on repeated failure. Keep the pre-completion stop/append-failure deletion tests distinct from this post-completion failure.

## 15. Verification and delivery boundary

This document is a specification, not live qualification. Research was limited to source inspection and public official documentation. No build, test, live provider call, generation, billing experiment, process termination, or deployment was performed for this spec.

After written-spec approval, write a separate implementation plan with concrete file boundaries, red/green tests, lifecycle-evidence admission, migration/compatibility checks, and native execution followed by independent final review. Plan review must select/confirm execution before product code changes. Resolve Important/Critical review findings and run appropriate managed/UI/contract checks before local deployment.

Deploy compatible managed/resource changes through the repository's local-testing script; dependency/native contract changes require its corresponding full workflow. Report exact build/test exclusions, installed verification scope, and live limitations. Section 2's endpoint continuity requirement is required for feature completion. Hermetic implementation verification and end-to-end live provider qualification must be reported separately; only an explicitly authorized live test can establish the latter.

Spec approval authorizes planning. It does not authorize product implementation, live paid requests, merging, or release deployment.
