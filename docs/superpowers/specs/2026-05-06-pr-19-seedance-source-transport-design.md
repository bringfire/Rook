# PR-19 Seedance Source-Frame Transport Design

Date: 2026-05-06

## Goal

PR-19 replaces Seedance 2.0's current data-URI source-frame transport with a
robust provider-private fal CDN upload path.

The target model remains:
`bytedance/seedance-2.0/image-to-video`.

PR-18 proved the model-aware fal Seedance lifecycle but used a conservative
1 MB raw source-frame cap before building `data:` URLs. That cap blocks normal
viewport captures even though fal's current Seedance API accepts JPEG, PNG,
and WebP source frames up to 30 MB each. PR-19 fixes that bottleneck without
changing Rook's public video job contract, durable ledger schema, native
routes, MCP surface, bridge contract, or artifact retention model.

## Background

PR-18 added Seedance as a managed Vision video model:

- provider identity: `fal`;
- model id: `bytedance/seedance-2.0/image-to-video`;
- supported modes: `I2V` and `Interp`;
- source frames: artifact-id image media only;
- lifecycle: model-aware fal queue submit/status/result/cancel;
- durable handle: request-id-only for Seedance;
- privacy boundary: no durable source media, fal URLs, provider envelopes, or
  data URIs.

The current source payload code lives in
`src/Rook/Services/Vision/Video/Fal/FalSeedanceI2vSourcePayload.cs`. It
validates resolved media, caps raw bytes at `1024 * 1024`, and emits data URIs
for `image_url` and optional `end_image_url`.

Official fal docs reviewed on 2026-05-06 state:

- Seedance `image_url` and `end_image_url` accept JPEG, PNG, and WebP source
  images up to 30 MB each:
  https://fal.ai/models/bytedance/seedance-2.0/image-to-video/api
- fal file inputs may use data URIs, hosted URLs, or fal uploads, but data
  URIs inflate request payloads and are not recommended for non-small files:
  https://fal.ai/docs/documentation/model-apis/fal-cdn
- fal CDN URLs are public-by-URL and expire according to media expiration
  settings:
  https://docs.fal.ai/documentation/development/working-with-files
- uploaded input files are CDN files subject to lifecycle controls; request
  JSON retention is controlled separately with `X-Fal-Store-IO`:
  https://docs.fal.ai/documentation/model-apis/media-expiration
- fal model/queue requests retry by default on selected infrastructure
  failures unless callers send `X-Fal-No-Retry`; PR-19 disables those queue
  retries because duplicate Seedance generation jobs are cost-sensitive:
  https://fal.ai/docs/documentation/model-apis/common-parameters
- fal's JavaScript storage API documents uploaded-file lifecycle with
  `X-Fal-Object-Lifecycle`, while model/queue APIs document generated-object
  lifecycle with `X-Fal-Object-Lifecycle-Preference`:
  https://fal.ai/docs/api-reference/client-libraries/javascript/storage

Task 0 on 2026-05-06 confirmed the URL-returning upload contract with a
controlled non-generation one-byte probe and the published JavaScript SDK
source. The local multipart REST page:
`POST https://api.fal.ai/v1/serverless/files/file/local/{target_path}`
returns only an upload-completed boolean and is not the PR-19 implementation
path. The confirmed source-frame upload flow is:

1. `POST https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3`
   with JSON body containing `content_type` and `file_name`.
2. Send `X-Fal-Object-Lifecycle: {"expiration_duration_seconds":3600}` on
   the initiate request.
3. Read `upload_url` and `file_url` from the initiate response.
4. `PUT` raw source bytes with the detected content type to the returned
   HTTPS presigned `upload_url`.
5. Submit the returned HTTPS fal CDN `file_url` as Seedance `image_url` or
   `end_image_url`.

The probe observed a `v3b.fal.media` CDN host, so PR-19 must allow the
reviewed `v3*.fal.media` fal CDN host family instead of hard-coding only
`v3.fal.media`.

## Non-Goals

- No Kling 3.0.
- No new Seedance model.
- No Seedance text-to-video, fast, or reference-to-video endpoint.
- No dynamic provider discovery.
- No source downscale/compression as the primary fix.
- No fallback to data URI when upload fails.
- No public temp hosting.
- No local HTTP source server.
- No broad provider-neutral Vision upload service.
- No new native route.
- No MCP tool change.
- No public HTTP route change.
- No `NativeGhBridgeRegistrar` expansion.
- No video ledger schema migration.
- No artifact retention model change.
- No exposure of upload URLs through bridge responses, handles, errors, or
  artifacts.

## Product Scope

Seedance keeps the PR-18 product behavior:

- `I2V` requires a start frame artifact and prompt.
- `Interp` requires a start frame artifact, end frame artifact, and prompt.
- reference frames are not accepted.
- `T2V` is not accepted for this model.
- `number_of_videos` must remain `1`.

The only intended workflow change is that normal viewport/source captures up
to fal's provider limit are accepted by uploading source bytes to fal CDN
before queue submit.

## Provider-Private Architecture

Add a Seedance-specific transport seam near the current Seedance payload code:

- `IFalSeedanceSourceTransport`
- `FalSeedanceSourceTransport`
- a small value object such as `FalSeedanceSourceUrls`

`FalSeedanceSourceUrls` contains only:

- `ImageUrl`
- optional `EndImageUrl`

It has no metadata bag, provider handle fields, provider result token, request
body storage, or durable participation.

`FalVideoProvider.SubmitSeedanceAsync` remains the orchestrator:

1. Validate provider options, mode, prompt, and video count.
2. Read the fal API key.
3. If the key is missing, fail before upload HTTP.
4. Call the Seedance source transport with the request, resolved media, API
   key, and cancellation token.
5. Build Seedance submit JSON using returned CDN URLs.
6. Submit the fal queue job with platform headers.
7. Parse fal `request_id`.
8. Return `QueuedSubmitOutcome(new ProviderJobHandle(requestId))`.

The PR changes only provider-private source transport for fal Seedance. It
does not change public video job requests, bridge payloads, native route
wiring, MCP behavior, durable ledger schema, or local artifact semantics.

## Source Validation

Move the current Seedance source validation from
`FalSeedanceI2vSourcePayload` into `FalSeedanceSourceTransport` or a helper it
owns.

Validation remains local and occurs before any queue submit:

- request is present;
- resolved media dictionary is present;
- mode is `I2V` or `Interp`;
- reference frames are absent;
- start frame is required;
- end frame is absent for `I2V`;
- end frame is required for `Interp`;
- resolved bytes exist;
- bytes are non-empty;
- MIME is detected from bytes;
- detected MIME is PNG, JPEG, or WebP;
- declared/resolved MIME matches detected MIME when present;
- each source frame is at most 30 MB raw bytes.

The 30 MB value must be a named Seedance provider constant, not a magic
number. If fal's official limit changes before implementation, update the
constant and spec/plan notes together.

Validation errors are non-retryable `InvalidRequest` failures. They are user
or request problems, not provider availability problems.

## fal Upload Transport

Seedance always uploads source frames to fal CDN in PR-19:

- I2V uploads the start frame.
- Interp uploads the start frame and end frame.
- submit JSON uses returned CDN URLs.
- no data URI fast path exists.
- no data URI fallback exists.

The transport uses the confirmed fal storage initiate-plus-PUT contract:

- initiate upload at `https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3`;
- include `content_type` and generated `file_name` in the JSON request body;
- send the source-upload lifecycle header on the initiate request;
- `PUT` raw bytes to the returned HTTPS presigned `upload_url`;
- use the returned HTTPS fal CDN `file_url` in Seedance submit JSON.

The generated target path/filename must not reveal local source paths, artifact
filenames, prompts, or user-provided text. Use a provider-private prefix plus
random IDs or job-local IDs and a MIME-derived extension. The returned
provider CDN URL is treated as sensitive public-by-URL transport material.

The upload response URL must be validated before it is used in `image_url` or
`end_image_url`. Reject:

- missing URL;
- relative URL;
- `http:` URL;
- `file:` URL;
- `data:` URL;
- non-fal media/CDN URL when the official upload endpoint is expected to
  return fal-hosted media.

Validation should prefer a narrowly reviewed fal CDN host allowlist based on
official docs and live endpoint evidence, not a broad arbitrary URL policy.

## fal Client Changes

Extend `src/Rook/Services/Vision/Fal/FalApiClient.cs` narrowly.

Required support:

- initiate a source upload through fal's confirmed REST storage endpoint;
- PUT raw source bytes to the returned HTTPS presigned upload URL with the
  detected content type;
- return only the confirmed `file_url` value from the upload helper;
- send only the fal platform headers needed by PR-19;
- post JSON with the same constrained platform header support.

Do not add a generic arbitrary-header escape hatch. The supported platform
headers for PR-19 queue submit are:

- `X-Fal-Object-Lifecycle-Preference`
- `X-Fal-Store-IO`
- `X-Fal-No-Retry`

The supported lifecycle header for source upload is the confirmed
storage-upload header:
`X-Fal-Object-Lifecycle`.

The upload endpoint host policy must remain narrow. Existing queue calls are
limited to `fal.run` and subdomains. Upload initiation is limited to
`rest.fal.ai`. Returned upload URLs must be absolute HTTPS presigned URLs and
are used only inside the upload helper. Returned source `file_url` values must
be absolute HTTPS fal CDN URLs in the reviewed `v3*.fal.media` host family.

## Retention And Platform Headers

Use a named provider constant for source media lifetime:

`SeedanceSourceMediaExpirationSeconds = 3600`

Source upload initiate requests send:

`X-Fal-Object-Lifecycle: {"expiration_duration_seconds":3600}`.

Seedance queue submit sends:

- `X-Fal-Object-Lifecycle-Preference: {"expiration_duration_seconds":3600}`
- `X-Fal-Store-IO: 0`
- `X-Fal-No-Retry: 1`

This intentionally disables fal request JSON retention for the submit payload
containing `image_url` and optional `end_image_url`.

`X-Fal-No-Retry: 1` intentionally disables fal platform queue retries for the
Seedance submit call. Rook keeps its own narrow client-side retry only for
connection-establishment failures where the submit body did not reach fal.

Do not rely on fal dashboard/history for retry, debugging, or recovery because
request IO storage is disabled by design.

Applying the one-hour lifecycle header to queue submit may also shorten
generated output CDN lifetime. That is acceptable for PR-19 because
`VideoJobManager` materializes provider output into local Rook artifacts as
soon as the job completes. Tests should still pin that provider output URLs do
not persist in durable records or artifact metadata.

## Privacy Invariants

Source upload URLs are allowed only as provider-private volatile transport.
They may exist only in local variables between upload completion and queue
submit.

They must never be written to:

- `ProviderJobHandle`;
- `ProviderMetadata`;
- `ProviderResultToken`;
- `GenerationError.ProviderDetail`;
- provider-facing or user-facing error messages;
- video ledger records or raw JSONL text;
- ledger `extensions`;
- artifact metadata;
- result envelopes;
- bridge responses;
- native routes;
- MCP surfaces;
- logs.

Seedance durable handles remain request-id-only. The only fal scalar durable
state for Seedance is the provider job id/request id already approved in
PR-18.

## Error And Retry Policy

Missing API key fails before upload HTTP.

Validation failures fail before upload HTTP and are non-retryable
`InvalidRequest`.

Upload failures happen before a Seedance generation job exists. Retrying an
upload is safe with respect to generation cost and duplicate jobs until an
upload operation returns a CDN URL. If the first upload succeeds but the
response is lost, retry may create an orphaned CDN input object. The one-hour
lifecycle makes that orphan risk acceptable.

The transport may retry bounded transient upload failures. If upload
ultimately fails:

- return retryable `DependencyUnavailable`;
- sanitize provider detail;
- do not include source URL, request JSON, upload response body, headers, or
  source bytes in errors;
- do not call the queue submit endpoint.

For Interp, if start upload succeeds and end upload fails, queue submit must
not be called.

Queue submit remains conservative. Send `X-Fal-No-Retry: 1` to disable fal
platform retries for the submit request. Keep the current client-side one-shot
retry only for connection-establishment failures, or replace it with an
equally explicit safe-connect policy. Do not retry generic/ambiguous submit
timeouts or transport failures because a provider job may already exist.

If fal submit/status/result errors clearly indicate expired or inaccessible
input media, classify that provider/dependency failure as retryable. Do not
overfit parser logic to unknown messages in PR-19.

If generated output expires after fal completes but before
`VideoJobManager` fetches/materializes it, map recognizable expiry/not-found
shapes to retryable `DependencyUnavailable`. Otherwise keep the existing
sanitized provider error mapping.

## Testing Strategy

### Source Transport Tests

Add focused tests for `FalSeedanceSourceTransport`.

Validation:

- accepts PNG, JPEG, and WebP source bytes up to 30 MB;
- rejects 30 MB plus 1 byte before HTTP;
- rejects missing start frame;
- rejects missing end frame for `Interp`;
- rejects end frame for `I2V`;
- rejects reference frames;
- rejects unresolved media;
- rejects empty bytes;
- rejects unsupported bytes;
- rejects declared MIME mismatch.

Upload behavior:

- uploads start frame once for `I2V`;
- uploads start and end frame for `Interp`;
- initiates upload at `rest.fal.ai/storage/upload/initiate` with JSON
  `content_type` and generated `file_name`;
- PUTs raw source bytes to the returned HTTPS presigned upload URL;
- sends the detected content type;
- sends the exact confirmed storage-upload lifecycle header with the named
  one-hour value;
- uses generated target paths/filenames that contain no local path, artifact
  filename, prompt, or user text;
- validates returned URL;
- rejects missing, relative, `http:`, `file:`, `data:`, and non-fal media
  upload response URLs;
- returns only `ImageUrl` and optional `EndImageUrl`.

Retry/cancel:

- retries bounded transient upload failures before a CDN URL is returned;
- final upload failure returns retryable sanitized dependency error;
- cancellation during upload returns before a CDN URL is available.

### Provider Tests

Update `FalVideoProviderTests`.

Provider orchestration:

- missing fal API key makes no upload or submit request;
- provider/options/prompt/count validation still happens correctly;
- Seedance submit body contains fal CDN URLs and no `data:`;
- Interp maps uploaded end frame URL to `end_image_url`;
- queue submit sends `X-Fal-Store-IO: 0`;
- queue submit sends `X-Fal-No-Retry: 1`;
- queue submit sends one-hour lifecycle header.

Error/privacy:

- upload failure returns retryable sanitized dependency error;
- upload failure never calls queue submit, pinned by fake request counts;
- start upload success plus end upload failure never calls queue submit;
- cancellation during upload never calls queue submit;
- upload and submit failures do not put source URL, request JSON, upload
  response body, or header data into `GenerationError.ProviderDetail` or
  provider/user-facing error messages;
- generic/ambiguous submit transport failure is not auto-retried;
- connection-establishment submit retry remains one-shot if retained.

### Manager, Ledger, And Artifact Tests

Update `VideoJobManagerTests` and related privacy tests.

Prove:

- Seedance handles remain request-id-only after submit, restart, cancel,
  status, and result flows;
- source CDN URLs never appear in provider-handle extensions;
- source CDN URLs never appear in parsed ledger records;
- source CDN URLs never appear in raw JSONL text;
- source CDN URLs never appear in artifact metadata;
- source CDN URLs never appear in bridge/list/status/result responses;
- source CDN URLs never appear in result envelopes;
- materialized video artifacts are local Rook artifacts;
- provider output URL does not persist after materialization.

### Boundary Tests And Scans

Prove PR-19 does not expose source upload transport through:

- `src/RookNative/**`;
- `mcp_server/**`;
- `src/Rook/InternalBridge/**`;
- `NativeGhBridgeRegistrar`;
- public HTTP route tables.

Expected result: no new Seedance upload operation, upload URL field, source
URL field, or fal media URL surface outside managed fal provider internals.

## Verification

Normal verification should use fake HTTP and fake providers. Live fal/Rhino
smoke is optional/manual for PR handoff because it spends provider credits.

Focused commands should include:

- fal/Seedance source transport tests;
- fal video provider tests;
- video job manager tests;
- bridge/privacy tests that cover video job responses;
- native/MCP/internal bridge boundary scans;
- `git diff --check`;
- managed `net7.0` build.

Run the full managed test suite before PR handoff when practical.

If live smoke is run, use a non-sensitive source frame and prompt, then scan
the latest ledger/artifact metadata for forbidden strings:

- `fal.media`;
- `queue.fal.run`;
- `api.fal.ai`;
- `rest.fal.ai`;
- `image_url`;
- `end_image_url`;
- `data:image`;
- `status_url`;
- `response_url`;
- `cancel_url`;
- provider upload response body fragments.

Do not commit prompts, source images, CDN URLs, provider envelopes, generated
videos, or credentials from live smoke.

## Acceptance Criteria

- Seedance source frames always upload to fal CDN.
- No Seedance data URI fast path exists.
- No data URI fallback exists.
- JPEG, PNG, and WebP source frames up to the current fal 30 MB limit are
  accepted.
- Source frames larger than the current fal limit fail before HTTP.
- fal source media expiration is a named one-hour provider constant.
- Source upload sends the exact officially confirmed storage-upload lifecycle
  header with the one-hour value.
- Source upload uses the confirmed initiate-plus-presigned-PUT storage
  contract.
- Queue submit sends the one-hour lifecycle header, `X-Fal-Store-IO: 0`, and
  `X-Fal-No-Retry: 1`.
- Missing API key fails before upload HTTP.
- Upload failure fails before queue submit.
- Upload retries may not duplicate generation jobs.
- Generic/ambiguous queue submit transport failure is not auto-retried.
- Queue submit remains request-id-only for durable Seedance handles.
- Source CDN URLs never persist in handles, ledger records, raw JSONL,
  artifacts, result envelopes, bridge responses, errors, native routes, MCP
  tools, or logs.
- Upload response URLs are validated before being used in submit JSON.
- No public/native/MCP/internal bridge surface is added.
- Tests use fake HTTP/fake providers for normal verification.
- Live fal/Rhino smoke is optional/manual.

## Follow-Up

Future work can decide:

- a shared fal media upload helper if another curated fal model needs it;
- configurable media expiration;
- source-image downscale/compression as an explicit user option;
- a broader video ledger privacy hardening migration;
- Kling 3.0 I2V after source-video transport is hardened;
- fal queue idempotency support if fal documents an official idempotency key.

## Self-Review

- Scope is only provider-private Seedance source-frame transport.
- Public video job contracts, durable ledger schema, native routes, MCP, and
  artifact retention are unchanged.
- The design uses fal CDN upload because fal docs confirm 30 MB source frames
  and recommend uploads over large data URIs.
- fal CDN URLs are treated as public-by-URL and sensitive.
- The design always uploads and never falls back to data URI.
- One-hour retention, `X-Fal-Store-IO: 0`, and `X-Fal-No-Retry: 1` are
  explicit, with source-upload lifecycle header confirmation called out as an
  implementation blocker.
- Missing API key, validation, upload, and submit failure ordering are
  specified.
- Upload retry can orphan short-lived input CDN objects but cannot duplicate
  generation jobs.
- Queue submit retry remains conservative and disables fal platform retries.
- Tests cover initiate-plus-presigned-PUT upload shape, exact upload lifecycle header, URL
  validation, raw JSONL leakage, upload/end-frame failure ordering, error
  privacy, and boundaries.
- No placeholders or implementation-only assumptions remain.
