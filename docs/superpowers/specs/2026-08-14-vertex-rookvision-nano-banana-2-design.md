# Vertex RookVision Nano Banana 2 Design

**Status:** Amended after specification review; pending reviewer approval
**Date:** 2026-08-14
**Rook baseline:** `61c686c5e1204ded860fc9a22f8acc65c4f99db6`
**Existing Vertex source provenance:** Rook `bca57582f2f3fa18c72760ff8f068268ed9c11e9`; Chirp `1f954c27f796ecfe830d02a76497deffcf31cfc2`

## Purpose

Add one explicit enterprise-billed image provider to RookVision:

| Field | Required value |
| --- | --- |
| Provider | `vertex_ai` |
| Rook model key | `vertex_ai/gemini-3.1-flash-image` |
| Google model ID | `gemini-3.1-flash-image` |
| Display | `Vertex AI — Nano Banana 2` |
| Vertex location | `global` only |

This is a forward-only additive provider. It lets a user deliberately send a
RookVision Nano Banana 2 request through an organization-controlled Vertex AI
project and billing account. It does not replace Google AI Studio, change any
default, or make Rook an owner of enterprise credentials or billing.

The first Vertex image catalog contains exactly this one entry. Vertex Nano
Banana Pro, Vertex Veo, partner models, generic Vertex image routing, and model
fallback are outside this slice.

## 1. Current boundary and problem

Rook already has two relevant capabilities, but they do not meet:

- Python owns the accepted Vertex authorization record, Windows DPAPI handling,
  OAuth/ADC/service-account resolution, Google credential refresh, project,
  location, and authorization generation.
- The managed C# RookVision subsystem owns the image catalog, image request,
  artifact, job, cancellation, and UI behavior.

RookVision's current Gemini provider uses a Google AI Studio API key directly
against `generativelanguage.googleapis.com`. Copying the Vertex refresh token or
service-account material into C# would duplicate credential ownership. Moving
RookVision into Python would unnecessarily relocate a working subsystem.

The KISS correction is one narrow token lease across the existing loopback
process boundary:

1. C# asks the exact Rhino-owned Python service for a short-lived Vertex access
   token for the selected qualified model.
2. Python independently re-admits the current Vertex record, refreshes or
   reuses an in-memory access token, and returns only the bounded lease data.
3. C# uses that access token in memory for one Vertex image request and retains
   the existing RookVision result path.

No second server, helper executable, credential broker, generic provider
framework, or new authentication store is introduced.

### Cold-start ownership and composition

RookVision must work when the user has never opened Rook Chat. Token acquisition
therefore begins with one `ChatServiceManager`-owned operation that:

1. ensures the exact Rhino-owned Python service is running;
2. verifies its existing owner and Rhino-PID contract; and
3. returns one immutable connection snapshot containing the matching base URI
   and session nonce.

The manager captures that pair under its existing lifecycle gate. Callers must
not inspect discovery files themselves or read the URI and nonce through two
separate mutable operations. If the service changes after a snapshot is
returned, that request fails normally and a later request obtains a new
snapshot; the caller never splices state from two service lifetimes.

The managed image provider does not depend directly on UI or process-management
types. Define one narrow managed-side token-source contract whose operation is
conceptually:

```text
AcquireVertexTokenAsync(qualifiedModelKey, cancellationToken) -> token lease
```

The composition boundary supplies an adapter backed by the atomic
`ChatServiceManager` snapshot. `RookSubsystemRoot` receives only that narrow
token-source dependency when composing RookVision. The provider never starts a
process, reads discovery, or reaches into `ChatServiceManager` itself.

## 2. Google AI Studio GA-ID prerequisite

The active AI Studio image catalog still contains two retired preview IDs.
Before adding the Vertex registration, make one tiny prerequisite commit that
changes only the active constants, lifecycle labels, and their focused current
tests:

| Existing ID | Replacement ID |
| --- | --- |
| `gemini-3.1-flash-image-preview` | `gemini-3.1-flash-image` |
| `gemini-3-pro-image-preview` | `gemini-3-pro-image` |

Both capabilities become `ga`, not `preview`. Preserve all other AI Studio
behavior:

- provider remains `gemini`;
- API-key storage and `x-goog-api-key` transport remain unchanged;
- short names remain `nano-banana-2` and `nano-banana-pro`;
- default remains the AI Studio `nano-banana-2` short name;
- existing resolution/reference limits and request behavior remain unchanged;
- no credential migration, alias, fallback, or new setup is added.

Historical evidence retains the preview IDs. Active production code, current
tests, and current user/agent guidance must use the GA IDs. Google records the
preview shutdown and GA replacements in its
[Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations).

This prerequisite is independently reviewable and must not be mixed with the
new Vertex transport implementation.

## 3. Provider and model identity

`DefaultImageProviderRegistry` indexes models by one global model key and
rejects duplicate keys. Therefore the Vertex registration uses the complete
qualified Rook key as its registration key and `ImageCapability.Id`:

```text
vertex_ai/gemini-3.1-flash-image
```

The unqualified `gemini-3.1-flash-image` remains the AI Studio registration.
Both may coexist without changing the registry.

Only the Vertex provider strips the exact `vertex_ai/` prefix, and only while
building Google's URL. It then requires the remaining ID to equal
`gemini-3.1-flash-image`. No generic prefix stripping or model-family fallback
is admitted.

The RookVision catalog and UI contract is:

- render the Vertex choice exactly as `Vertex AI — Nano Banana 2`;
- retain the existing AI Studio labels, short names, and default selection;
- send the qualified Vertex key back in generation requests;
- show no API-key input for `vertex_ai`;
- model enumeration remains local and network-free;
- selecting one provider never tests, selects, or disables the other;
- the static fallback catalog remains the existing AI Studio fallback and does
  not pretend Vertex is available when the live catalog cannot be loaded.

The Vertex entry is listed as an external-authorization provider. Model listing
does not refresh credentials or claim network readiness. Actual generation
performs admission and returns a precise Vertex error when authorization or
configuration is unavailable.

## 4. Global-only model admission and endpoint

Google documents Nano Banana 2 (`gemini-3.1-flash-image`) as GA, supporting
generation and editing, and available only in `global`:
[official model documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-image).

Rook must require the configured Vertex location to equal the exact canonical
value `global` for this model. It must not silently replace, ignore, or rewrite
an organization's regional Vertex setting.

A regional configuration fails before token refresh or Google image transport
with the stable code:

```text
vertex_model_region_unsupported
```

The public message states that Vertex AI Nano Banana 2 requires location
`global` and that the user's configured Vertex location was not changed. It
must not expose credential contents.

For an admitted request, the managed provider constructs exactly the global
Vertex publisher-model endpoint shape:

```text
https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/gemini-3.1-flash-image:generateContent
```

No regional hostname prefix is used. Project and model path segments are
encoded. C# validates the returned location again before constructing the URL,
so raw/internal traffic cannot turn a regional record into a global request.

## 5. Non-browser internal token route

Add exactly one route to the existing Rhino-owned Python service:

```text
POST /internal/providers/vertex/access-token
```

The request has one required field and rejects unknown fields:

```json
{
  "model": "vertex_ai/gemini-3.1-flash-image"
}
```

This is a **nonce-authenticated, non-browser internal route**. The nonce does
not establish a native-only trust boundary because the same service nonce is
also injected into Rook's WebView.

Admission is fail-closed:

- the expected service nonce must exist;
- `X-Rook-Session` must match it exactly;
- every request containing an `Origin` header is rejected, including
  `https://app.rook.invalid` and browser preflight requests;
- the Origin rejection occurs before the generic CORS/preflight path;
- the service used by C# must already satisfy the existing exact owner and
  Rhino-PID checks in `ChatServiceManager`;
- only `POST` is registered;
- the route is absent from MCP schemas, discovery, catalogs, and tools.

The exact internal path receives a route-specific admission wrapper before the
generic CORS/preflight and router-generated error paths. It must produce the
fixed redacted JSON envelope and `Cache-Control: no-store` even when a request
is rejected before the token handler. Do not rely on aiohttp's automatic HTML
or plain-text `405` response.

The HTTP contract is closed:

| Condition | HTTP status | Stable code |
| --- | ---: | --- |
| Success | 200 | none |
| Any `Origin` header, including preflight | 403 | `vertex_internal_access_denied` |
| Expected nonce absent, or supplied nonce missing/wrong | 403 | `vertex_internal_access_denied` |
| Method other than `POST` | 405 with `Allow: POST` | `vertex_internal_method_not_allowed` |
| Malformed JSON, wrong shape, missing/unknown field | 400 | `vertex_internal_request_invalid` |
| Model other than the one admitted key | 400 | `vertex_image_model_unsupported` |
| Configured location not `global` | 400 | `vertex_model_region_unsupported` |
| Signed out, authorization revoked/unavailable, or record invalid | 409 | existing bounded Vertex authorization code |
| Record changes during refresh | 409 | `vertex_authorization_changed` |
| Installed Google authorization dependency unavailable | 503 | `vertex_auth_dependency_missing` |
| Token issuance budget expires | 504 | `vertex_token_issuance_timeout` |
| Unexpected bounded internal failure | 500 | `vertex_token_issuance_failed` |

Admission order is Origin, nonce, method, body/model, local configuration, then
credential refresh. An unauthenticated caller cannot use body or configuration
errors to probe Vertex state.

The route-specific wrapper also catches malformed-content and routing failures
for this exact path. Other chat-service routes keep their existing behavior.

Every success and failure response sets `Cache-Control: no-store`. Successful
responses use one fixed shape with a genuine future expiry, for example:

```json
{
  "success": true,
  "data": {
    "access_token": "<short-lived bearer token>",
    "expires_at_unix_seconds": 1800000000,
    "project_id": "<configured project>",
    "location": "global",
    "generation": "<authorization generation>"
  }
}
```

Failures use one fixed, redacted shape:

```json
{
  "success": false,
  "error": {
    "code": "<stable vertex code>",
    "message": "<bounded public message>"
  }
}
```

The response never contains refresh tokens, service-account paths or contents,
credential mode details, environment contents, raw Google error bodies, or
tracebacks. The access token is never written to logs, discovery, settings,
job ledgers, artifacts, diagnostics, or evidence.

## 6. Token lease and authorization-generation behavior

Python remains the sole credential owner. The route reuses the accepted
`VertexStore` and `google-auth` implementation; it does not parse or decrypt
Vertex credentials in C#.

The Python service may keep one in-memory access-token cache protected by one
async refresh lock. The cache contains only token, expiry, and authorization
generation. It follows these rules:

1. Read and validate the current Vertex record on every issuance request,
   before considering a cached token.
2. Reject any model other than the one exact qualified key.
3. Reject a non-`global` record before credential refresh.
4. Reuse a cached token only when its generation equals the current record and
   more than 300 seconds remain before expiry.
5. Otherwise refresh through `google-auth` off the aiohttp event loop. Give the
   underlying Google token transport an explicit 20-second timeout and the
   complete issuance operation a 30-second budget; do not rely on the
   transport library's larger default.
6. After refresh, re-read the record. If it is absent or its generation
   changed, discard the token and return `vertex_authorization_changed`.
7. Require a non-empty token and a finite future expiry before returning it.

The C# token client requests one lease for each Vertex image submission and
does not persist or independently cache it. Its internal-route wait is 35
seconds, above Python's issuance budget so it cannot preempt a valid refresh.
The existing image request cancellation token remains authoritative after
token admission.

Disconnect or replacement of the Vertex record invalidates cached credentials
by admission: the next issuance request must observe the absent or new
generation before any cached token can be returned, and the local cache entry
is discarded. A token already issued to an in-flight Google request cannot be
retroactively revoked; disconnect prevents subsequent issuance, not completion
of that already-authorized request.

No background refresh, refresh-token copy, token file, or cross-process cache
invalidation framework is added.

## 7. Managed Vertex image provider

Add one synchronous `IImageProvider` registration named `vertex_ai` containing
only the qualified Nano Banana 2 key. It uses the same Gemini
`generateContent` image body and inline-image response semantics as the AI
Studio provider while keeping transport and authentication separate:

- AI Studio continues using `x-goog-api-key` and its existing base URL;
- Vertex uses `Authorization: Bearer <access_token>` and the global Vertex URL;
- only a small pure request/response codec may be shared;
- provider transport, credential ownership, and errors remain distinct;
- the existing five-minute image HTTP ceiling and cancellation behavior remain
  unchanged;
- the token route and Google request each receive the caller's cancellation;
- no request falls back to AI Studio after any Vertex failure.

The new registration supports the same currently shipped Nano Banana 2 image
generation/editing capability shape. It does not broaden resolution or
reference-image limits in this slice. Pricing remains explicitly unverified
with Vertex-specific provenance; it must not reuse an AI Studio pricing label
or claim an exact cost.

The model is GA, but Google currently classifies its 4K image output as a
Preview feature. Rook may retain the existing 4K option, but active capability
guidance must state that feature-level distinction. Automated and installed
acceptance use 1K or 2K, not 4K.

Provider failures map into the existing `GenerationError` envelope. Stable
Vertex-specific provider codes include:

| Condition | Stable provider code | Classification |
| --- | --- | --- |
| Configured location is not `global` | `vertex_model_region_unsupported` | `InvalidRequest`, not retryable |
| Internal route receives another image model | `vertex_image_model_unsupported` | `InvalidRequest`, not retryable |
| Vertex record absent | existing `vertex_signed_out` | `DependencyUnavailable`, not retryable |
| OAuth/ADC/service-account admission fails | existing bounded Vertex auth code | `DependencyUnavailable`, not retryable |
| Authorization changes during refresh | `vertex_authorization_changed` | `DependencyUnavailable`, retryable after re-admission |
| Internal service unavailable/malformed | `vertex_token_service_unavailable` or `vertex_token_response_invalid` | `DependencyUnavailable`, retryable |
| Google returns 429 | preserved Google status/code | `QuotaExceeded`, retryable |
| Google content policy response | preserved bounded Google status/code | `ContentPolicy`, not retryable unless Google says otherwise |
| Google 5xx or transport timeout | preserved bounded Google status/code | `DependencyUnavailable`, retryable |

The Vertex provider must not reuse the existing AI Studio error mapper's raw
provider-detail behavior. It may retain only:

- the HTTP status class;
- an exact allowlisted Google status identifier such as `INVALID_ARGUMENT`,
  `UNAUTHENTICATED`, `PERMISSION_DENIED`, `RESOURCE_EXHAUSTED`,
  `FAILED_PRECONDITION`, `NOT_FOUND`, `UNAVAILABLE`, `DEADLINE_EXCEEDED`, or
  `INTERNAL`; and
- a Rook-owned fixed bounded message for the resulting classification.

An absent or unrecognized Google status becomes a fixed `UNKNOWN` provider
identifier and message. `GenerationError.ProviderDetail` is null for Vertex
failures. Raw Google response bodies, provider messages, nested details,
prompts, URLs, and headers must never enter errors, logs, job ledgers,
artifacts, diagnostics, or acceptance evidence. Only the pure successful
request/inline-image response codec may be shared with AI Studio; its error
mapper is not shared.

Messages and retained identifiers must not contain access tokens or credential
material. External provider or organization policy failures are not
reclassified as Rook authorization-generation failures.

## 8. Code and release boundary

Expected implementation scope is one Rook repository and two coordinated
commits after this specification and plan:

1. AI Studio GA-ID prerequisite: current constants and focused tests only.
2. Vertex RookVision provider: the existing Python Vertex backend/chat service,
   a small managed Vertex image-provider folder and registration, the managed
   subsystem composition, the narrow RookVision display mapping, and focused
   Python/C# tests.

Likely active boundaries are:

- `mcp_server/src/rook/providers/vertex_backend.py`;
- `mcp_server/src/rook/agent/chat/server.py`;
- their focused tests;
- `src/Rook/Services/Vision/Image/Gemini/GeminiImageCapabilities.cs`;
- `src/Rook/Services/Vision/Image/Vertex/` (new, narrowly scoped);
- `src/Rook/Services/Vision/VisionProviderRegistrations.cs`;
- `src/Rook/RookSubsystemRoot.cs`;
- `src/Rook/UI/Chat/ChatServiceManager.cs` for the one atomic owned-service
  snapshot operation;
- one narrow managed token-source adapter at the existing UI/composition
  boundary;
- `src/Rook/UI/Vision/Resources/app.js` only if needed for the exact display;
- focused managed tests under `src/Rook.Tests`.

The implementation plan must replace this likely list with an exact changed-path
allowlist before execution. Stop on any unmatched path.

Explicit exclusions:

- no Chirp repository changes;
- no native C++, RookBIM, Grasshopper, video/Veo, chat-model routing, agent,
  DSPy, or MCP-tool changes;
- no Google OAuth registration or Provider Setup UI redesign;
- no dependency, lockfile, Python-runtime, credential-store, installer schema,
  or registry redesign;
- no automatic model fallback, credential migration, compatibility alias, or
  generic token broker;
- no Vertex Nano Banana Pro or Veo registration;
- no public `rook-release` work in the private implementation PR.

No new dependency is expected: the accepted runtime already ships
`google-auth`, and the managed side uses existing .NET HTTP/JSON facilities.

Local deployment and installer packaging use the existing managed assembly and
Python source payload paths. Because no new dependency or payload class is
introduced, no installer behavior change is authorized. Acceptance artifacts
must nevertheless be rebuilt from the eventual private merge SHA; an older or
detached-worktree installation is not evidence for this feature.

## 9. End-to-end lifecycle scenarios

These four scenario traces are normative. They close the operation from cold
start through terminal evidence rather than describing only the middle of the
token bridge.

| Scenario | Lifecycle owner and state | Permitted persistence | Required terminal evidence |
| --- | --- | --- | --- |
| RookVision request before Rook Chat has opened | The injected token source asks `ChatServiceManager` to ensure its owned service and returns one atomic URI/nonce snapshot; the provider owns neither discovery nor process startup | No nonce or token persistence; existing discovery contains no nonce | One owned service start, one matching snapshot, one admitted token request, then the normal image result |
| Internal request rejected before its handler | The exact-path admission wrapper owns Origin, nonce, method, and body rejection before generic CORS/router handling | Stable code, fixed message, and HTTP status only | Exact status/envelope, `no-store`, zero credential refresh, zero Google image request |
| Vertex returns an arbitrary or sensitive error | The managed Vertex provider owns classification and allowlisting before constructing `GenerationError` | HTTP class, allowlisted status identifier or `UNKNOWN`, and fixed Rook message only | Failed job/UI result with null `ProviderDetail`; raw response absent from logs, ledger, artifact, diagnostics, and evidence |
| AI Studio executes after the GA-ID change | The existing AI Studio provider owns the API-key request to the new GA model ID | Existing safe success metadata and normal artifact/ledger records; API key remains secret | Installed 1K/2K generation records provider `gemini`, model `gemini-3.1-flash-image`, and a non-empty image artifact |

Configuration change and disconnect remain governed by Section 6: every new
issuance re-admits the current record; stale cached credentials cannot cross a
missing or changed generation; an already-issued in-flight token is not
retroactively revoked.

## 10. Verification

### Focused automated contracts

The candidate must prove:

- AI Studio short names resolve to the two GA IDs, remain provider `gemini`, and
  retain the existing default and API-key transport;
- active production/tests contain neither retired preview ID, excluding
  historical evidence;
- the image registry simultaneously resolves unqualified AI Studio
  `gemini-3.1-flash-image` and qualified Vertex
  `vertex_ai/gemini-3.1-flash-image` to different providers;
- the Vertex registration contains exactly one model and no Pro/Veo entry;
- the catalog renders exactly `Vertex AI — Nano Banana 2`, preserves the AI
  Studio default, and submits the qualified key;
- model enumeration performs no token refresh or Google call;
- a cold RookVision request uses one manager-owned operation to start/verify the
  service and obtain one matching immutable URI/nonce snapshot; neither the
  provider nor token-source adapter reads discovery directly;
- the internal route rejects missing/incorrect/absent nonce state, every Origin
  header including preflight, wrong method, malformed body, unknown field, and
  wrong model before refresh;
- every listed HTTP condition has its exact status, fixed JSON envelope, and
  `no-store` header even when rejected before the handler; no MCP tool exposes
  the route, and bounded logs/evidence contain no access token;
- regional configuration returns `vertex_model_region_unsupported` before
  refresh or Google transport;
- the token cache reuses only matching, unexpired generations and serializes
  concurrent refresh;
- disconnect, record deletion, and generation rotation prevent subsequent
  cached-token issuance; a refresh racing a change discards its result;
- the C# client rejects malformed, expired, invalid-generation-shape,
  non-global, and failed token responses;
- the Vertex provider strips only the exact prefix, builds the global endpoint,
  sends Bearer authentication, preserves request/cancellation behavior, parses
  successful inline images, maps errors, and never falls back;
- arbitrary, malformed, and sensitive Google error bodies yield only an
  allowlisted identifier or `UNKNOWN`, a fixed message, and null
  `ProviderDetail`; raw content is absent from every persistent surface;
- the model is cataloged as GA while 4K is identified as a Preview feature;
- Gemini AI Studio focused provider tests remain green with no credential or
  endpoint behavior change.

Use focused Python and managed suites. Do not require a repository-wide suite
or introduce a new test framework.

### Installed acceptance

After the private PR is reviewed and merged:

1. Record the immutable private merge SHA.
2. Build and locally deploy the candidate from a detached checkout of that
   exact SHA using the sealed installed Python runtime.
3. Verify installed managed/Python payload provenance and dependency health.
4. Configure an approved test identity against an organization-controlled
   Vertex project whose location is exactly `global` and whose IAM/billing/API
   settings permit Nano Banana 2.
5. In installed RookVision, explicitly select `Vertex AI — Nano Banana 2` and
   perform one bounded 1K or 2K image generation/edit request using owned
   disposable input and a fixed prompt.
6. Require a non-empty image artifact whose job evidence records provider
   `vertex_ai` and the qualified model key, with no token or credential material
   in logs, artifacts, or evidence.
7. With an approved AI Studio test key, explicitly select the separate AI
   Studio Nano Banana 2 entry and perform one bounded 1K or 2K request using the
   same owned input and fixed prompt. Require a non-empty artifact whose job
   evidence records provider `gemini` and GA model
   `gemini-3.1-flash-image`.
8. Confirm AI Studio remains the default and no live Nano Banana Pro call was
   made. The two live calls prove the two explicit billing choices; they do not
   authorize fallback between them.
9. Bound all waits and clean only acceptance-owned artifacts in `finally`.

Technical acceptance may use an approved test OAuth client. Production release
readiness still depends on the already-separated production Google OAuth
registration/verification and enterprise-admin guidance. Those activities do
not alter this implementation boundary.

Public plugin/docs promotion and the one-time release note occur separately
from the accepted private merge. The release note should identify the explicit
Vertex model, its `global` requirement, organization-controlled billing/IAM,
and the continued separate AI Studio option.

## 11. Rejected alternatives

### Duplicate Google authorization in C#

Rejected because it would duplicate DPAPI records, refresh-token ownership,
Google auth behavior, configuration generation, and dependency management.

### One-shot Python token helper

Rejected because it adds per-request process startup, executable/runtime
selection, stdout secret transport, new timeout/cleanup behavior, and a second
launch contract despite an owned Python service already existing.

### Move RookVision generation into Python

Rejected because it relocates working managed catalog, artifact, job,
cancellation, and UI behavior merely to avoid one narrow local token lease.

### Register the unqualified Google model ID twice

Rejected because the existing registry correctly rejects duplicate IDs. The
provider-qualified Vertex key resolves the ambiguity without redesigning the
registry.

### Add all Vertex image/video models now

Rejected because Nano Banana Pro and Veo have different capability, region,
pricing, and long-running-operation questions. The first catalog proves the
enterprise billing/auth boundary with the one daily-use model that motivated
the work.

## 12. Approval boundary

Approval authorizes implementation planning for exactly:

- the two AI Studio GA-ID corrections as one tiny prerequisite commit;
- one provider-qualified Vertex Nano Banana 2 RookVision entry;
- one manager-owned cold-start/atomic connection snapshot exposed through a
  narrow injected token-source contract;
- one nonce-authenticated, Origin-rejecting internal token route on the owned
  Python service with the exact fixed HTTP envelope;
- one generation-aware in-memory token lease;
- one managed Vertex image provider and focused display/catalog integration;
- bounded Google error classification with no raw provider persistence;
- focused tests and one installed request through each explicit Nano Banana 2
  billing path: Vertex and AI Studio.

It does not authorize any excluded work above. After approval, invoke
`superpowers:writing-plans`; do not begin implementation directly.
