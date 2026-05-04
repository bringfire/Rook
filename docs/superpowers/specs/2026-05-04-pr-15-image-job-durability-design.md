# PR-15 Image Job Durability And Restart Recovery Design

Date: 2026-05-04

## Goal

PR-15 makes managed image jobs durable across companion/plugin restart without adding Replicate auto-resume or Vision UI history resurfacing.

The slice mirrors video's lifecycle durability pattern, but with a narrower image-safe durable record. The durable contract is:

- image jobs do not disappear across restart;
- prior non-terminal jobs are reconciled to `Interrupted`;
- completed jobs remain result-fetchable if their local artifact still exists;
- interrupted provider jobs can be explicitly cancelled after restart when a safe `provider_job_id` was persisted.

PR-15 is backend and managed-bridge reliability work. It does not change the visible Generate workflow, add native/MCP/public HTTP parity, or persist user prompt/request summaries.

## Background

PR-12 added the hidden managed image job substrate with in-memory `ImageJobManager` state, bridge-only image job ops, authenticated materialization seams, cancellation race coverage, and boundary tests proving image job ops were not exposed through native, MCP, or `NativeGhBridgeRegistrar`.

PR-13 added the hidden Replicate image provider. It proved fake-HTTP Replicate submit/poll/fetch flows and authenticated output materialization while keeping Replicate hidden from default UI and credential surfaces.

PR-14 made Replicate visible in managed Vision Settings and Generate. `black-forest-labs/flux-schnell` now routes prompt-only text-to-image submissions through bridge-only async image job ops. That makes restart behavior user-visible: if Rhino or the companion/plugin restarts while an image job is running, the current in-memory job record disappears.

Video jobs already have a durable JSONL ledger and startup reconcile. PR-15 should reuse that lifecycle idea, but not copy video's broader record shape. Image jobs have stricter secrecy concerns because Replicate provider handles and metadata can contain output URLs, API URLs, and provider result tokens.

## Non-Goals

- No Replicate auto-resume or provider polling after restart.
- No restart materialization of provider output.
- No retry/reconstruct workflow.
- No Vision UI job-history resurfacing, banners, or Generate result rehydration.
- No prompt, resolution, aspect ratio, options, or parent artifact id persistence in the image job ledger.
- No provider metadata persistence.
- No provider result token persistence.
- No status, cancel, response, output, `replicate.delivery`, or `api.replicate.com` URL persistence.
- No native route changes.
- No edits under `src/RookNative/**`.
- No MCP tool changes.
- No public HTTP parity.
- No `NativeGhBridgeRegistrar` exposure.
- No change to synchronous `generate`; it remains source-image based.
- No live provider calls in normal tests.

## Durable Record

Add an image-specific durable record under `src/Rook/Services/Vision/Image/Jobs`: `ImageJobLedgerRecord`.

Each record is a full lifecycle snapshot. The on-disk schema uses snake_case and the field name `provider` to match video JSONL naming and current `ImageJobRecord.Provider`. Bridge responses can continue projecting the public `provider_name` field.

Persist only operational fields:

- `schema_version`
- `job_id`
- `state`
- `provider`
- `model`
- `provider_job_id`
- `result_artifact_id`
- `error`
- `created_at`
- `updated_at`

The durable `error` shape is sanitized:

- `code`
- `message`
- `retryable`
- `field`
- `provider_error_code` when allowlisted

`provider_error_code` is persisted only when it is a short scalar already present on `GenerationError.ProviderErrorCode`. `GenerationError.ProviderDetail` is not persisted.

Durable error serialization must not write `GenerationError.Message` verbatim. Add an image-ledger error sanitizer that produces the persisted `message`:

- normalize control characters and cap message length;
- scan for banned provider/internal substrings before writing;
- if a banned substring is present, replace the whole message with a generic sanitized message derived from the error code, such as `Image job failed; provider details were redacted.`;
- never persist URLs, provider endpoint names, provider output fields, token-looking values, or materializer request details through the message field.

The same sanitized durable error message is what bridge responses expose when they are built from durable records after restart. Live in-process errors may keep existing bridge behavior, but any error that crosses the ledger boundary must be safe before serialization.

Do not persist:

- prompt text;
- resolution or aspect ratio;
- provider options;
- parent artifact ids;
- credential previews;
- tokens;
- `ProviderJobHandle.StatusUrl`;
- `ProviderJobHandle.CancelUrl`;
- `ProviderJobHandle.ResponseUrl`;
- `ProviderJobHandle.ProviderResultToken`;
- provider metadata;
- provider result envelopes;
- provider output URLs;
- signed or authenticated output requests;
- materializer request details.

Malformed `Complete` records without `result_artifact_id` fail closed during ledger read. A complete image job without a local artifact id is an impossible durable state and must not be admitted as valid after restart.

## Ledger Contract

Add an image-specific ledger abstraction:

- `IImageJobLedger`
- `JsonlImageJobLedger`
- ledger read result type
- ledger read error type
- internal sanitized warning projection type
- fake in-memory ledger for tests

The production ledger is append-only JSONL, stored at:

```text
%APPDATA%\Rook\image\job-ledger.jsonl
```

Each append writes one full durable snapshot. Reads compact by `job_id`, with the last valid line winning. Read failures are line-scoped: malformed or unsupported lines are reported internally but do not hide valid records from other lines.

The ledger should follow proven video behavior where it fits:

- schema version required;
- snake_case keys;
- unsupported schema versions fail line-locally;
- malformed JSON fails line-locally;
- malformed required fields fail line-locally;
- read compacts by `job_id`;
- warning/error messages are sanitized and do not echo raw ledger payloads;
- unknown raw provider/user payload is not serialized into warnings.

Ledger read warnings remain internal in PR-15. Do not add `warnings` to bridge responses unless a later API design explicitly chooses an additive public field.

The image ledger should not reuse `VideoJobRecord`. Video's durable shape carries request and provider-handle concepts that are broader than PR-15 needs and unsafe for Replicate image jobs.

## Manager Semantics

`ImageJobManager` becomes ledger-backed while keeping the existing live `_runningJobs` runtime map. The ledger is the durable source for restarted and completed jobs. `_runningJobs` is only live task state for the current process.

Each successful lifecycle transition produces exactly one in-memory latest record and exactly one appended ledger snapshot. The implementation may choose the safest internal ordering, but tests must prove terminal stale writes do not append if they lose a race to a fresher terminal state.

On submit:

- resolve and validate the image model as today;
- create the initial in-memory record;
- append a durable `Queued` snapshot;
- add `_runningJobs`;
- start the background task.

The initial durable append is fail-closed. If the `Queued` snapshot cannot be appended, `SubmitAsync` returns a `DependencyUnavailable` image job failure before `_runningJobs` is updated, before any background task starts, and before any provider submit call is made.

On async provider submission:

- when a provider returns `QueuedSubmitOutcome`, persist only `ProviderJobHandle.ProviderJobId` as `provider_job_id`;
- do not persist status URL, cancel URL, response URL, result token, or provider metadata.

The first transition that learns a remote `provider_job_id` is also fail-closed. The manager must not continue polling a remote provider job until the durable snapshot containing `provider_job_id` is appended. If that append fails after the provider created the remote job, the manager attempts best-effort provider cancel using the in-memory handle, records an in-memory error for the current process, and does not append a misleading durable in-flight snapshot. This prevents restart from losing the only durable handle needed for later cleanup.

Other post-submit transition append failures are terminal for the local job. The manager must stop advancing the state machine, surface a local `DependencyUnavailable` or `ExecutionFailed` error, and avoid appending later stale terminal snapshots. If a remote provider handle is already known, cancellation behavior follows the same fail-closed principle: do not claim durable cancellation unless the `Cancelled` snapshot append succeeds.

On completion:

- artifact creation remains before `Complete` state publication;
- `Complete` durable records include `result_artifact_id`;
- a crash between artifact creation and durable `Complete` append can leave an orphan artifact. That is acceptable for PR-15 and should be documented as bounded debt, not turned into a cleanup campaign.

Read paths use a freshness merge between durable records and live `_runningJobs` snapshots:

- newer `updated_at` wins;
- on equal timestamps, durable terminal records win;
- otherwise live records may win.

This prevents stale live snapshots from hiding terminal durable records and prevents stale durable in-flight records from hiding current process progress.

`GetStatusAsync` returns status from the freshest merged record. `ListJobsAsync` returns durable-aware records ordered by `updated_at` descending. `FetchResultAsync` works after restart for durable `Complete` records only if the local artifact blob still exists. Missing local artifacts return non-retryable `DependencyUnavailable` with field `result_artifact_id`.

## Startup Reconcile

Add `ImageJobManager.ReconcileInterruptedJobs()`.

On startup reconcile:

- read compacted durable records;
- append `Interrupted` for prior non-terminal states:
  - `Queued`
  - `Submitting`
  - `Polling`
  - `Materializing`
- preserve `provider_job_id` when present;
- attach a sanitized interrupted `GenerationError`;
- skip terminal records unchanged;
- make no provider calls;
- do not poll status;
- do not fetch result;
- do not materialize output;
- do not spend or require provider credentials.

Reconcile is idempotent once the latest record for a job is terminal `Interrupted`.

`RookSubsystemRoot` gets image reconcile lifecycle support analogous to video:

- `ReconcileImageJobsOnce()` forces or uses image job subsystem construction;
- plugin startup calls image reconcile after the managed bridge/native companion setup path where image jobs are available;
- failures are non-fatal;
- failures reset the once flag so a later startup/retry path can try again;
- shutdown disposal still cancels live in-process jobs.

## Cancel After Restart

Cancellation must use the same terminal-race discipline as video.

If `_runningJobs` contains the job:

- re-check the freshest durable/live terminal state before any provider cancel;
- if a terminal state already won, return that state and do not call provider cancel;
- otherwise follow the live cancellation path.

If `_runningJobs` does not contain the job:

- read the latest durable record;
- `Complete`, `Error`, and `Cancelled` return their existing state;
- `Interrupted` without `provider_job_id` returns `Interrupted` unchanged;
- `Interrupted` with `provider_job_id` resolves provider by persisted `provider`;
- construct a fresh minimal `ProviderJobHandle(provider_job_id)`;
- call provider cancel;
- append `Cancelled` only if provider cancel succeeds;
- if provider cancel fails, leave the durable record unchanged and return the failure.

The manager must not reconstruct or persist status URL, cancel URL, response URL, provider result token, output URL, or provider metadata for cancellation.

## Bridge Behavior

The existing managed bridge op names and response shapes stay stable:

- `image_generate_start`
- `image_job_status`
- `image_job_cancel`
- `image_job_result`
- `image_jobs`

No Vision UI resource changes are required in PR-15.

Bridge behavior becomes durable-aware:

- `image_generate_start` starts a live job and appends the first durable snapshot.
- `image_job_status` works after manager/plugin restart from durable records.
- reconciled jobs report `state = "interrupted"` with sanitized error details.
- `image_jobs` returns durable jobs from prior sessions.
- `image_job_result` works after restart for durable complete records if the local artifact exists.
- `image_job_cancel` can cancel interrupted jobs after restart when `provider_job_id` exists and the provider is still registered.

Bridge responses keep existing public field names, including `provider_name`. They should not expose `provider_job_id`, provider URLs, provider metadata, request prompt/options, tokens, or credential previews.

## Testing Strategy

### Ledger Tests

`JsonlImageJobLedger` tests should prove:

- append and read compact by last valid record per `job_id`;
- schema version is required;
- unsupported schema version fails line-locally;
- malformed JSON fails line-locally;
- malformed `Complete` without `result_artifact_id` fails closed;
- malformed timestamps fail closed;
- malformed state fails closed;
- malformed provider or job id fails closed;
- warning/error messages are sanitized;
- raw line content is not echoed in warnings;
- serialization uses on-disk `provider`, not `provider_name`.
- durable error messages are redacted when the source message contains banned substrings such as provider URLs, `urls.get`, `urls.cancel`, endpoint names, or token-looking values.

### Leakage Tests

Leakage assertions apply to ledger payloads and bridge responses. Existing result artifact metadata for completed jobs can keep its current safe generation metadata.

Tests should prove image ledger and bridge responses do not contain:

- `replicate.delivery`;
- `api.replicate.com`;
- `status_url`;
- `cancel_url`;
- `response_url`;
- `urls`;
- `provider_result_token`;
- prompt text;
- resolution;
- aspect ratio;
- parent artifact ids;
- token-looking fixture values;
- `GenerationError.ProviderDetail`.

### Manager Durability Tests

`ImageJobManager` tests should prove:

- initial ledger append failure returns failure before provider submit and before `_runningJobs` mutation;
- submit appends a queued durable snapshot;
- async submit persists only `provider_job_id` on polling;
- failure appending the first `provider_job_id` snapshot attempts best-effort provider cancel and does not continue polling;
- post-submit transition append failure stops later stale terminal appends;
- each successful transition appends one durable snapshot;
- status survives a new manager over the same ledger;
- list survives a new manager over the same ledger;
- completed result after restart verifies local artifact availability before returning a blob path;
- missing artifact after restart returns `DependencyUnavailable`;
- reconcile marks queued/submitting/polling/materializing as `Interrupted`;
- reconcile does not touch terminal records;
- reconcile makes no provider calls;
- reconcile is idempotent.

### Race And Cancel Tests

Tests should prove:

- stale cancel cannot append `Cancelled` after a fresher `Complete`;
- stale complete cannot append `Complete` after a fresher `Cancelled`;
- live cancel re-checks terminal state before remote cancel;
- cancel-after-restart with `Interrupted + provider_job_id` resolves provider by persisted `provider`, calls fake provider cancel with a minimal handle, and appends `Cancelled`;
- cancel-after-restart with no `provider_job_id` returns `Interrupted` unchanged;
- provider cancel failure after restart leaves the durable record unchanged.

The existing cancellation/artifact cleanup flake is a reliability consideration. PR-15 should preserve and strengthen focused race tests, but should not broaden into an artifact cleanup campaign unless the flake reproduces.

### Lifecycle And Boundary Tests

Tests and scans should prove:

- `RookSubsystemRoot.ReconcileImageJobsOnce()` fires once;
- image reconcile resets its once flag on failure;
- plugin startup calls image reconcile and treats failure as non-fatal;
- bridge image job ops remain managed-bridge-only;
- no changes under `src/RookNative/**`;
- no changes under `mcp_server/**`;
- no `NativeGhBridgeRegistrar` image job exposure;
- no public HTTP route exposure;
- synchronous `generate` remains source-image based;
- normal tests use fake providers and fake HTTP only.

## Acceptance Criteria

- Image jobs are persisted to an append-only JSONL image ledger.
- The image ledger uses an image-safe operational record, not `VideoJobRecord`.
- The ledger persists `provider`, not public `provider_name`.
- The ledger persists only `provider_job_id`, never provider URLs, result tokens, output URLs, provider metadata, request summaries, or secrets.
- Durable error serialization redacts unsafe substrings from `GenerationError.Message` and never persists `GenerationError.ProviderDetail`.
- Initial ledger append failure fails closed before provider submission.
- Failure to persist the first `provider_job_id` snapshot attempts best-effort provider cancel and does not continue the remote polling flow.
- `image_job_status`, `image_jobs`, `image_job_result`, and `image_job_cancel` work against durable records after manager/plugin restart.
- Prior non-terminal records reconcile to `Interrupted` on startup.
- Startup reconcile does not call provider APIs, fetch output, materialize output, spend, or require credentials.
- Completed jobs remain result-fetchable after restart only when their local artifact exists.
- Cancel-after-restart works for interrupted records with `provider_job_id`.
- Provider cancel failure leaves durable state unchanged.
- Terminal race tests prove stale terminal writes do not append losing durable snapshots.
- Bridge response shape stays stable and does not add warning fields.
- No Vision UI job-history resurfacing is added.
- No native, MCP, public HTTP, or `NativeGhBridgeRegistrar` exposure is added.
- Existing sync `generate` behavior remains source-image based.
- All normal tests use fake providers/fake HTTP only.

## Follow-Up

Replicate auto-resume remains a separate design. A future resume slice would need to decide token availability, retention expiry behavior, output materialization after restart, artifact parent semantics, retry policy, and whether any request summary is necessary and acceptable to persist.

Vision UI history resurfacing is also a separate product slice. It should decide where interrupted and completed historical image jobs appear, whether they trigger banners, whether old completed jobs rehydrate into Generate, and how much history users expect.

## Self-Review

- Scope is backend/bridge durability only.
- The durable image record is narrower than video's record.
- Request summary persistence is explicitly out of scope.
- Replicate provider URLs, output URLs, provider metadata, result tokens, and secrets are explicitly out of scope.
- Startup recovery means durable `Interrupted` reconciliation, not auto-resume.
- Cancel-after-restart uses only `provider_job_id` and provider-name resolution.
- Bridge response shape remains stable.
- UI resurfacing is deferred.
- Native/MCP/public HTTP boundaries remain closed.
