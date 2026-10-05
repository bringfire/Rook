# Enterprise Google media OAuth completion

Status: scope and revised written specification approved by the user on 2026-10-05. Implementation planning incorporates the reviewer's race, peak-memory, acceptance-separation, and rebuild requirements. Implementation and live acceptance remain incomplete.

## Intended outcome

Firms sign in with Google and deliberately generate images and videos against their organization-controlled Google Cloud project. Python remains the sole owner of refresh credentials. The managed RookVision subsystem receives short-lived access tokens in memory and owns media generation, jobs, and artifacts. Enterprise product naming does not alter the existing `vertex_ai` provider identifier or Google API contracts.

## Recovered work and verified baseline

- Current main: `bc19d4af` at inspection. Existing Vertex desktop OAuth, DPAPI storage, readiness, and text-consumer integration are present.
- Preserved branch: `codex/vertex-rookvision-nano-banana-2-design`, commit `174b2675b6ff809acd16bf4627efe8abdfdbcde0`, in `.worktrees/vertex-rookvision-nano-banana-2-design`.
- The preserved commit contains token leases, an internal Python route, managed access-token adapter, and composition changes. Its image-provider test file currently tests only the unavailable token source and token redaction. The actual Vertex image provider is absent.
- Prior image plan explicitly excludes Veo. Current main also has changes in planned production files, so the preserved commit needs selective reconciliation rather than blind application.
- On 2026-10-05, current source OAuth/backend/runtime/acceptance-harness tests: 150 passed. Preserved source token-lease tests: 25 passed. Current managed Gemini image/Veo client/Veo provider/provider-registration tests: 53 passed after building the net48 test project.
- These are automated component checks. No live Google authorization or Vertex image/video request has been performed, and production readiness has not been established.

## Proposed completion

1. Reconcile the preserved token bridge with current ownership, service startup, shutdown, cancellation, nonce, and Origin checks. Keep refresh credentials in Python; retain bounded, generation-aware token refresh and no-store responses. Test the restored route and managed adapter together.
2. Complete the explicit Vertex image provider and registration through the existing image registry and artifact pipeline. Verify current Google model IDs, lifecycle, region availability, and response contracts before adopting earlier model constants. Preserve existing API-key provider behavior.
3. Add an explicit Vertex Veo provider through the existing video registry, manager, and ledger. Extend token admission to a closed supported media catalog with job-bound authorization. Use `predictLongRunning` submission and `fetchPredictOperation` polling. Support inline video output only in this slice; preserve the existing artifact pipeline. Implement local stop separately from confirmed remote cancellation as specified below.
4. Expose Google account connect/disconnect and organization project/location configuration through the current configuration surface. Reuse the existing OAuth authorization owner; do not add a second credential store. Give users an explicit Enterprise Google media choice.
5. Add focused tests for OAuth refresh/revocation, concurrent acquisition, authorization rotation, cold service startup, provider registration, image response parsing, video submit/poll/download, cancellation, IAM/billing/quota failures, and error redaction. Verify both provider paths through artifact publication.
6. Build the affected managed/Python components and run the measurable installed acceptance below with an approved business identity, OAuth desktop client, billed project, and supported locations/models. Confirm Workspace administrator consent restrictions and OAuth app publishing/verification requirements separately.

## Existing RookVision precedents and exact reuse

The extension uses the existing managed media backend. Python provides authorization only; it does not acquire a second generation queue, poller, artifact store, or media server.

| Responsibility | Existing implementation to reuse | Required addition |
| --- | --- | --- |
| Provider registration and model selection | `VisionProviderRegistrations`, `DefaultImageProviderRegistry`, `DefaultVideoProviderRegistry`, `VideoSubsystemFactory`, `RookSubsystemRoot` | Explicit Vertex registrations and capabilities; reuse validation and options codecs only where Google's contracts match. |
| Image transport and parsing | `GeminiImageProvider.BuildRequestJson` and `ParseSuccess` | Extract pure request/success codecs, add bounded Vertex Bearer transport and fixed errors. Keep credential and endpoint behavior provider-specific. |
| Video provider lifecycle | `IVideoProvider` / `IModelAwareVideoProvider`, existing Veo and fal implementations, generic submit/status/result outcomes | A stateless Vertex provider and small HTTP client; reuse pure Veo request encoding where verified, with Vertex-specific parameters and operation parsing. |
| Queue, concurrency, polling, ledger, artifact publication | `VideoJobManager`, `ImageJobManager`, `JsonlVideoJobLedger`, `VideoJobRecordFactory` | Use the current lifecycle and completion path. Add only the local-stop branch and authorization-failure handling required below. |
| Durable provider context | `ProviderJobHandle.ProviderMetadata`, `VideoJobRecordProviderHandle`, `VideoJobRecord.Extensions` | Persist an allowlisted, versioned authorization binding in existing metadata. No new ledger or credential schema. |
| Video delivery | `InlineArtifactBody`, `VideoArtifactMaterializer`, `CappedStreamReader`, existing artifact store and sidecar producers | Decode the Vertex inline result under transport limits; return the existing inline artifact outcome. |
| Restart | `VideoJobManager.ReconcileInterruptedJobs` | Preserve its current `Interrupted` policy and no automatic resume. Test that Vertex never resubmits on restart. |
| OAuth ownership and service cold start | Existing `VertexStore`/DPAPI/OAuth flow; parked token lease route, managed adapter, atomic `ChatServiceManager` connection snapshot | Selectively reconcile these files with current main and add binding-aware lease admission. |

The current handle metadata is already round-tripped through the ledger and copied when the result handle is updated. This is the appropriate place for nonsecret job context. However, current providers read the latest credential on each call, and the parked token service accepts only a model and current record. Neither is sufficient for identity-bound video jobs without the additional checks below.

The existing cancel manager deliberately leaves a job running when remote cancellation fails. Preserve that behavior for existing providers; a Vertex local stop needs an explicit outcome rather than an invented success response.

Precedent verification on 2026-10-05: 211 existing registry, job-manager, record-factory, ledger, and materializer tests passed using `dotnet test --no-build` against the previously built net48 test assembly. These verify existing infrastructure, not new Vertex behavior.

## Job authorization and project binding

At submission, capture `{binding_version: 1, authorization_generation, project_id, location, model_id}` from an admitted lease and selected registered model. Persist this allowlisted object in `ProviderJobHandle.ProviderMetadata` with the accepted operation handle. `authorization_generation` is the existing opaque record generation: every account reconnect, authorization-mode change, project change, or configured-location change creates a different generation. It binds a job to one admitted authorization snapshot without recording an email or token.

Location is selected and validated per registered media model, since an image's `global` location and a video's supported region can differ. Store these nonsecret choices in existing settings, not a second credential store. The lease issuer validates the requested location against the registered media policy and binds it to the current authorization generation. Changing a configured media location must rotate that generation; ordinary token refresh must not. Changes to authorization project/default region also rotate the generation as today.

Implementation clarification: the current `VertexRecord.region` already drives Vertex text/readiness endpoints and text/Chirp runtime arguments. This scope retains it as the shared text/video location and uses fixed `global` image admission without writing that image location back into the record. An explicit shared region/project save therefore changes text/Chirp routing, rotates generation, and recycles managed Chirp; the settings UI must explain that effect. Passive settings/status reads and lease refresh cannot migrate or rewrite an existing text configuration. A current text region unsupported by Veo leaves video unavailable until the user explicitly saves a supported shared region. Independent text/video regions would require a distinct field within the existing store and reviewed migration behavior; they are not added here.

For every poll and result fetch, C# supplies the persisted binding to the Python token route. Python checks exact generation/project and admitted model/location before credential resolution, after refresh, and before returning the lease. C# checks the returned binding, builds the endpoint from it, and checks authorization again before publishing an artifact. Missing, malformed, or mismatched metadata fails closed without contacting Google. An operation name must match the bound project's location and publisher model; returned operation identity must also match. Do not turn a returned name into an arbitrary URL.

Tokens remain only in memory for an individual outbound operation. Neither access/refresh tokens, OAuth client secrets, authorization headers, raw Google responses, nor video base64 enter handles, ledger, settings, diagnostics, or evidence. Fresh leases can be issued for the same binding as access tokens expire. The managed provider does not cache refresh credentials or replace a job's binding with current settings.

Disconnect or a changed generation makes the next poll/fetch fail before network access. Stop local work and persist an `Interrupted` record with a fixed authorization-changed/signed-out message and the original remote handle. An already-started request may finish remotely; discard its response after a failed binding check and do not publish. No automatic resume after reconnect, even to the same apparent account, because the generation changed. Never use the new account/project to retrieve or cancel the old operation. Already published local artifacts remain usable.

Translate binding failures into the existing typed `GenerationErrorCode.Interrupted` with `Retryable: false`; update the existing manager's failed-status/failed-result handling to preserve that interruption state rather than converting it to generic `Error`. Do not route on error-message text. Missing/malformed binding is a nonretryable validation failure. Record only fixed Rook messages and allowlisted status codes, with no raw `ProviderDetail`.

No cross-process transaction can recall a Google request already dispatched when disconnect occurs. Define the fence as admission before each outbound request and re-admission before artifact publication. Disconnect is not a promise of remote cancellation or a billing reversal.

## Vertex video wire and output contract

Use Bearer-authenticated `POST` to the bound publisher model's `:predictLongRunning`. Request exactly one video with Vertex `sampleCount: 1`; do not infer this field from the Developer API's parameter names. Poll with Bearer-authenticated `POST` to the same bound model's `:fetchPredictOperation`, supplying the accepted full `operationName` in the JSON body. This follows Google's documented [operation polling contract](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-an-image).

Choose **inline output only** for this slice. Omit `storageUri`; Google documents Base64 video output when no output bucket is supplied in its [Veo reference-image guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-references). Require a successful terminal response with exactly one `response.videos` entry, `mimeType: video/mp4`, and nonempty `bytesBase64Encoded`. Handle operation errors and safety-filtered/no-video responses as typed failures. Reject `gcsUri`, arbitrary HTTP URLs, malformed Base64, conflicting delivery fields, and extra samples. Cloud Storage output requires separate bucket/IAM configuration and is outside this implementation.

Retain the stateless provider lifecycle: `GetStatusAsync` detects terminal success and returns a completed handle containing only the original operation reference and binding. `FetchResultAsync` re-fetches that same completed operation and decodes its inline payload once. This adds one read-only operation fetch at completion, avoids storing Base64 in a result token/ledger, and requires no provider-side per-job cache or new manager callback. Polling must not decode or publish the video payload.

Use the current 250 MiB decoded video limit (`VideoArtifactMaterializer.MaxGeneratedVideoBytes`). Bound response reads before JSON parsing to `4 * ceil(maxDecodedBytes / 3) + 1 MiB` including a small envelope allowance; enforce declared content length and actual bytes read using `ResponseHeadersRead` and `CappedStreamReader`. Reject encoded length before decoding, invalid padding/alphabet, a computed decoded size over the limit, and oversized decoded output. Bound small submit/error responses separately to 1 MiB. Avoid retaining both raw response buffers and decoded video longer than required; respect the existing manager's concurrency limit. Each provider HTTP operation has a 120-second aggregate deadline covering headers/body/decode, token acquisition retains its 30-second ceiling, and local video monitoring has a 15-minute deadline. All propagate cancellation. Timeout stops local monitoring with the remote operation's status unknown.

The Vertex transport disables automatic redirects and rejects all 3xx responses. Endpoints are constructed from validated bound project/location/model fields and the verified Google API host. No media download URL or Cloud Storage downloader is introduced in this slice; the completed inline bytes pass through `InlineArtifactBody`, the existing materializer, artifact store, and sidecar pipeline.

## Local stop and remote cancellation

Do not infer a Veo remote cancel endpoint from the Developer API or the generic long-running-operation API. The verified Veo submission/polling guides do not establish a supported cancellation contract. For this slice, Vertex's UI action is **Stop monitoring** and sends no remote cancellation request.

Add one explicit `LocalStopOnlyOutcome` to the existing provider cancel outcome union. The video manager handles it by cancelling the local task and persisting `Interrupted` with a fixed message: "Local monitoring stopped. The Google operation may continue and incur charges." Return `JobCancelResult.Ok(Interrupted)` through the existing response shape; render that state/message rather than "Cancelled." Keep `CanceledOutcome` reserved for provider-confirmed remote cancellation and retain existing provider behavior. Update exhaustive outcome consumers/tests as required; this is a small contract extension, not a second cancellation framework.

Carry the local stop reason through the running job's existing cancellation state so its background cancellation handler cannot append `Cancelled` over the durable `Interrupted` record. Apply the manager's terminal-state checks to stop, authorization interruption, and completion publication, including a final authorization check immediately before artifact-store creation and another before committing job completion. If authorization changes or local stop wins after creation, remove the new artifact through the existing `ArtifactStore.Delete(Guid)` and retain `Interrupted`; do not expose it as the job's completed result. This cleanup is an addition to the existing manager save path, not an already implemented rollback guarantee. A process crash during publication is handled by restart reconciliation; do not claim a distributed atomic transaction with Google or the credential service.

Preserve the operation ID and authorization binding after local stop or reload for diagnostics. Existing completed/failed records remain terminal and cannot be overwritten by a racing stop. A request that stopped while submission was in flight may have created a Google job without returning an operation name; record its outcome as unknown, not remotely cancelled. Never automatically submit again.

## Submission, retry, and restart policy

- Each local job causes at most one dispatch of `predictLongRunning`. Disable HTTP/SDK automatic retries and redirects for submission. Obtain/refresh the lease before dispatch; a lease failure means no submission occurred.
- After dispatch, timeout, disconnect, cancellation, response loss, malformed success, or a 5xx is potentially ambiguous. Persist a fixed submission-outcome-unknown error with `Retryable: false` and any safely recovered operation handle. Do not automatically resubmit, including after an authentication response. A seed is not an idempotency key.
- The UI locks an in-flight submit action against repeated clicks. An explicitly created later job is a new potentially billed generation; for an unknown prior outcome, show that consequence before offering a new submission. Do not promise exactly-once execution across a crash between Google acceptance and ledger persistence.
- Read-only polling/fetch may retry transport errors, 429, and 5xx at most three total attempts per call, using bounded 1/2-second backoff (honor a valid `Retry-After` only within the aggregate deadline). Acquire/check a lease for the original binding for each attempt. Retry never changes project, location, model, or operation ID; do not retry authorization mismatch, malformed response, or terminal provider error.
- Restart uses current reconciliation: unfinished records become `Interrupted`; zero automatic submissions, polls, or fetches. Completed artifacts remain available. Reconnection is for future jobs; recovery/resume of interrupted remote operations is outside this slice.

## Measurable acceptance

Automated tests must exercise these scenarios with injected clocks, HTTP handlers, token refresh, and ledger fixtures before any live credentials are needed. Then installed acceptance must satisfy every live criterion; a missing prerequisite is recorded as not run, never passed.

| Scenario | Required observable result |
| --- | --- |
| Image generation | Exactly one image submission; artifact can be decoded; measured pixel width/height equal the selected model's documented dimensions/aspect ratio; record hash and byte count. |
| Video generation | Exactly one video submission; accepted operation ID is bound to project/location/model; terminal inline MP4 is stored by the existing manager; decoded width/height and duration match the selected supported request (duration within 0.5 s); decode first, middle, and last frames with existing FFmpeg support and play the artifact in RookVision. Record playback as a separate explicit pass/fail observation. |
| Refresh during active polling | After at least one in-flight poll, expire/invalidate only the in-memory access-token lease using a source-only test seam. Observe an actual Google refresh and a later successful poll of the same operation under the unchanged authorization generation/project/location/model; zero additional submit calls. Mark this forced lease refresh distinctly from natural token-expiry coverage. |
| Disconnect during active job | Observe at least one in-flight poll, disconnect, then verify no subsequent Google request is admitted for that binding and no artifact is published. Local record becomes `Interrupted`; remote cancellation is unconfirmed. Reconnect and prove the old job neither resumes nor issues requests with the new generation. Run the equivalent controlled test for account/project/location changes. |
| Restart during active job | Restart the installed owner/companion after an accepted operation is persisted. Reconcile to `Interrupted`, preserve operation/binding, and count zero automatic submits/polls/fetches. Prior completed artifacts still open. |
| Local stop | Stop an active job, record `Interrupted` and the remote-may-continue message, zero remote cancel requests, and no later artifact publication. Test the stop/completion race deterministically. |
| Ambiguous submit | Inject an accepted request whose response is lost. The manager must issue exactly one submission, persist the unknown outcome, and perform zero resubmissions across retry UI handling and restart. Use an HTTP fixture; do not deliberately create duplicate live billed jobs. |
| Secret hygiene | Scan sanitized evidence and ledger from all cases for synthetic secret sentinels and locally held real credential values without printing them. No headers, refresh material, OAuth client secrets, video Base64, or raw Google response body is persisted. |

The refresh test may require a separate video from disconnect/restart tests. Record the intended bounded job count and supported short durations before the live run; incomplete attempts can still be billed. Prefer one image and three short videos: successful completion/refresh, active disconnect, and active restart with local-stop behavior verified automatically. If an operation completes before the required intervention, mark the case inconclusive rather than passed; do not silently increase the billed job count.

Sanitized evidence identifies exact tested Rook/Chirp commits where applicable, dirty-tree status or patch hash, installed versions, selected qualified and Google model IDs, project ID (or a stable redacted project label consistently used), image/video locations, UTC timestamps, elapsed times, local job/operation correlation labels, request counts by action, refresh count, ledger transitions, artifact SHA-256/size/dimensions/duration, frame-decode/playback results, and pass/fail/not-run status for each criterion. Account identity is represented by an approved business-account label, not tokens or raw provider diagnostics. No acceptance success claim is permitted unless every required case passes.

## Review decisions and prerequisites

The user has approved scope and this revised written specification. Review the resulting implementation plan and select its execution approach before implementation. The project ID and desktop OAuth client configuration path are prerequisites only for live acceptance, not design, mocked tests, or implementation. Do not put tokens or client secrets in chat or acceptance evidence.

Completion means the implementation is integrated, relevant automated checks pass, installed account sign-in and refresh work, and both real media artifacts are verified. Passing mocked tests alone does not meet that criterion.
