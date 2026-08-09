# Enterprise Vertex Provider Design

**Status:** Proposed for reviewer approval; implementation planning blocked
**Date:** 2026-08-09
**Rook baseline:** `a867f8e06ae8aca904102104c47780d02d5640b8`
**Chirp baseline:** `c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468`
**Research reference:** Hermes Agent `244d296646909aca1dd16c9759491da0ef4cd163`

## Purpose

Add an enterprise, project-based Google Vertex AI provider to Rook's existing
Python/LiteLLM text-model surfaces:

- Rook Chat;
- Rook agents and DSPy;
- Chirp.

The provider identity is `vertex_ai/...`. It is additive. It does not replace,
modify, or silently intercept the existing Gemini Developer API / Google AI
Studio provider identity `gemini/...`.

This is the first of three separately reviewed 1.5.19 workstreams:

1. Enterprise Vertex provider implementation and acceptance.
2. ChatGPT subscription support through official `codex app-server`.
3. Unified Provider Setup presentation and release integration.

The second workstream requires its own specification. The third begins only
after the private provider implementations it will present have been accepted.

## 1. Non-negotiable Google provider split

Rook supports two independent Google provider contracts:

| Provider identity | Authentication | Configuration | Authorized surfaces in this design |
| --- | --- | --- | --- |
| `gemini/...` | Existing Gemini Developer API / AI Studio API key | Existing `GEMINI_API_KEY` behavior | Existing Rook Chat, agents/DSPy, Chirp, RookVision image, and Veo video behavior |
| `vertex_ai/...` | Rook desktop OAuth, explicitly selected ADC, or explicitly selected service-account credential | Organization project ID plus region | Rook Chat, agents/DSPy, and Chirp text-model calls |

The following invariants are normative:

- Existing Gemini API keys, models, settings, callers, and installed users
  continue to work without reconfiguration.
- RookVision image generation and Veo video generation continue using the
  Gemini Developer API key and `generativelanguage.googleapis.com` paths.
- Vertex does not enter RookVision image or video provider registries in this
  workstream.
- A user may configure and use Gemini Developer API and Vertex simultaneously.
- Credentials are never copied, migrated, aliased, or shared between the two
  providers.
- Selecting or configuring one provider does not select, configure, test, or
  disable the other.
- No request falls back from Vertex to Gemini or from Gemini to Vertex.
- Model/provider selection remains explicit. A `gemini/...` identifier cannot
  resolve to Vertex, and a `vertex_ai/...` identifier cannot resolve to the
  Developer API.

The implementation must include source and behavioral guards for these
invariants. A generic "Google" credential slot or status is prohibited.

## 2. Enterprise operating model

Vertex support authenticates an employee into an existing, organization-owned
Google Cloud environment. The required user-provided configuration is:

- Google authorization mode;
- organization-controlled Google Cloud project ID;
- Vertex region;
- explicit `vertex_ai/...` model selection through the existing model-profile
  or allowed model-override mechanisms.

The organization remains solely responsible for:

- creating and administering the Google Cloud project;
- attaching and administering billing;
- enabling the Vertex AI API;
- granting and revoking IAM permissions;
- organization policies and administrator allowlisting;
- data residency, governance, retention, and contractual coverage;
- deciding which employees, regions, and models are permitted.

Rook authenticates, retains the selected authorization safely, submits model
requests, and reports bounded configuration state. Rook must not create or
modify projects, attach billing, enable APIs, grant roles, alter IAM policy,
administer organizations or Workspace, or present Developer API / Vertex
Express Mode coverage as equivalent to the organization-owned Vertex workflow.

## 3. Current process boundary and selected credential ownership

The current text-model consumers are not one process:

- Rook Chat is a Python service launched by the managed companion.
- Rook MCP owns agent and DSPy execution in its Python process.
- Chirp runs in a separate Python environment and is launched by Rook's
  `chirp_manager` for Rook-managed use.
- Current Python provider keys are usually discovered from process environment
  or `.env`; Vertex OAuth credentials must not use that persistence path.

One Rook Python Vertex authorization module is the authoritative persistent
credential owner. It owns:

- the selected authorization mode;
- the DPAPI-protected OAuth refresh credential, when OAuth is selected;
- project ID and region settings;
- connect, disconnect, refresh, and readiness classification;
- construction of in-memory LiteLLM Vertex arguments.

The canonical store is one versioned, atomically replaced file under:

```text
%LOCALAPPDATA%\Rook\data\provider_auth\vertex.json
```

Production resolution is fixed to that current-user path. General data-root
overrides do not redirect production credentials; tests receive an explicit
temporary-store dependency and must never read or write the user's real store.

The store is Vertex-specific, not a new general secret framework. It contains
ordinary configuration in clear JSON and, only for the OAuth mode, one
DPAPI-CurrentUser ciphertext envelope. The plaintext refresh credential,
access tokens, authorization codes, PKCE verifier, and OAuth state are never
persisted. Writes are serialized and atomic; readers must never observe a
partially written record. Unknown schema versions fail closed without rewriting
or deleting the record.

Rook Chat and Rook MCP import the same authorization module from the installed
`rook-mcp` distribution. They resolve Vertex authorization immediately before a
Vertex call and retain access tokens only in process memory.

Chirp does not get a second persistent store or its own Google login. For a
Rook-managed Chirp launch, `chirp_manager` obtains an in-memory authorized-user
credential envelope from the authoritative module and transfers it once through
an anonymous child-stdin bootstrap pipe selected by a non-secret launch flag.
The payload is not placed in command-line arguments, environment variables, or
files. Chirp holds it only in memory and supplies it to its Vertex `dspy.LM`.
When Vertex is not selected or configured, no auth bootstrap is sent. A
standalone Chirp process may use explicitly selected ADC or a service-account
path, but it cannot create or persist a second copy of Rook desktop OAuth.

Disconnect revokes the Google authorization where possible, removes the
encrypted refresh credential, invalidates cached Rook tokens, and stops or
restarts Rook-owned Chat/Chirp processes that received the authorization.
Every Rook-side Vertex call rechecks the current store generation before using
a cached token. No background process may silently recreate a disconnected
authorization.

## 4. Authentication modes

Exactly one Vertex authentication mode is selected at a time. Failure of the
selected mode does not fall through to another mode.

### 4.1 Rook desktop OAuth — primary

The primary user experience is an explicit **Sign in with Google** action. It
uses Google's installed desktop application flow:

- the system browser;
- a fresh PKCE verifier and challenge per attempt;
- a cryptographically random state value validated exactly on return;
- a listener bound only to `127.0.0.1` on an operating-system-selected random
  port;
- one pending attempt with a bounded timeout;
- authorization-code exchange over TLS;
- offline authorization so the user does not sign in for every Rook session;
- immediate listener shutdown after success, rejection, timeout, or malformed
  callback.

Rook requests exactly the Google-documented OAuth scope required by the current
Vertex inference API:

```text
https://www.googleapis.com/auth/cloud-platform
```

Google documents no narrower public Vertex-inference scope for this workflow.
The scope is broad and subject to Google's consent and verification rules. Rook
must request no additional Google user-data scopes. Scope or endpoint changes
require a separately reviewed contract and may require renewed Google
verification.

The desktop client ID is shipped and documented so enterprise administrators
can inspect or allowlist it. An installed desktop application cannot keep a
client credential secret; any Google-issued desktop client material included
with Rook is application identity, not a user/provider secret.

### 4.2 Application Default Credentials — advanced

ADC is an explicit advanced selection for administrators and developers who
already manage Google credentials. Rook delegates discovery and refresh to the
supported Google authentication library and does not copy the ADC file into
Rook storage. Selecting ADC still requires Rook's explicit project ID and region
settings. Missing or incompatible ADC fails as ADC; it never falls back to Rook
OAuth or a Gemini key.

### 4.3 Service-account credential — advanced

A service-account mode stores only the explicitly selected canonical file path
and never copies or persists the JSON contents. The file remains owned and
secured by the organization. Rook validates that the selected path is a regular
file when configuring and again when using it. It passes the path to the
supported Google authentication layer without logging it or returning it in
health/status responses. Missing, unreadable, malformed, or unauthorized
credentials disable only Vertex.

Rook does not create service accounts, generate keys, grant impersonation, or
recommend long-lived service-account keys over the primary OAuth path.

## 5. Runtime integration

### 5.1 Closed model admission

`vertex_ai/...` is a closed provider prefix with provider-specific readiness.
It is not added to the single-environment-key map. The active model resolver
must distinguish:

- Gemini Developer API key readiness for `gemini/...`;
- Vertex authorization plus project/region readiness for `vertex_ai/...`;
- existing API-key and local-provider readiness for all other providers.

Configuring Vertex does not change the active model profile. Users select a
Vertex model explicitly through a declared profile or an allowed model
override. No dynamic model catalog, automatic provider substitution, or
provider-wide fallback is introduced.

### 5.2 Rook Chat

Immediately before `litellm.acompletion`, a `vertex_ai/...` model resolves a
fresh in-memory Vertex argument set containing the explicit project, region,
and supported Google credential representation. Non-Vertex calls do not invoke
the Vertex authorization owner. A Vertex admission failure is returned before
starting the model request and does not affect the chat service's health for
other providers.

### 5.3 Agents and DSPy

The existing DSPy construction seams add one explicit `vertex_ai/...` branch.
Every Vertex `dspy.LM` receives the same authoritative project, region, and
in-memory credential representation. The existing `gemini/...`, Anthropic,
OpenAI API, OpenRouter, and local-model construction paths remain unchanged.

### 5.4 Chirp

Chirp accepts the one-time Rook bootstrap only when started with the private
Rook-managed bootstrap flag and stdin pipe. It rejects malformed, duplicate,
late, or unexpectedly present payloads before initializing a Vertex LM. The
payload is never echoed, logged, cached to disk, included in traces, or returned
by `/health` or `/chirp/*`.

Chirp uses the payload only for `vertex_ai/...` models. Its existing
`gemini/...` and API-key/provider behavior remains unchanged. A Vertex failure
must not disable Chirp's non-Vertex models; if the selected/default Chirp model
is Vertex, `/health` reports Vertex disabled while the sidecar stays available
for a later explicit non-Vertex selection.

## 6. Provider Setup contract

This workstream supplies provider-specific backend operations that the later
unified Provider Setup slice will present. It does not add more installer
password boxes.

The Vertex card is labeled **Google Cloud Vertex AI — Enterprise project** and
is visually separate from **Google AI Studio — Gemini API key**. It exposes:

- authorization mode selection;
- Sign in with Google for desktop OAuth;
- project ID;
- region;
- advanced ADC or service-account selection;
- bounded status/test;
- disconnect.

The card never displays a refresh token, access token, service-account content,
authorization code, DPAPI ciphertext, or raw provider response. Project and
region may be shown because they are configuration, not secrets. The selected
service-account path is not returned through general health or diagnostic
surfaces.

Provider testing performs token acquisition plus one fixed, non-generating
Vertex admission probe against the selected project, region, and configured
model. The implementation plan must pin the exact Google method and verify that
it does not submit user content or request generated output. A successful OAuth
exchange alone is not reported as project readiness.

## 7. Closed configuration and error taxonomy

Vertex status is independent from whole-product health. One of these bounded
codes is reported with a stable remediation message and no raw Google payload:

| Code | Meaning |
| --- | --- |
| `vertex_signed_out` | Rook OAuth is selected but no authorization is stored. |
| `vertex_authorization_declined` | The user declined or cancelled the current OAuth attempt. |
| `vertex_oauth_admin_blocked` | Google reports that administrator policy blocked the OAuth application. |
| `vertex_authorization_revoked` | Stored authorization can no longer refresh or has been revoked. |
| `vertex_adc_unavailable` | ADC was explicitly selected but no supported ADC could be loaded. |
| `vertex_service_account_unavailable` | The selected service-account file is missing, unreadable, or malformed. |
| `vertex_project_required` | Project ID is absent or malformed. |
| `vertex_region_required` | Region is absent or malformed. |
| `vertex_project_inaccessible` | The identity cannot access the configured project. |
| `vertex_api_disabled` | Google identifies the Vertex AI API as disabled for the project. |
| `vertex_billing_unavailable` | Google identifies billing as unavailable for the request. |
| `vertex_permission_missing` | The identity lacks the required Vertex inference permission. |
| `vertex_region_invalid` | The region is unsupported or invalid for the request. |
| `vertex_model_unavailable` | The explicit model is unavailable in the selected project/region. |
| `vertex_auth_dependency_missing` | The installed supported Google auth dependency is absent or incompatible. |
| `vertex_request_failed` | A provider failure occurred but the available structured evidence cannot safely prove a narrower classification. |

Classifiers use structured Google status/reason fields where documented. They
must not infer billing, IAM, API enablement, or administrator policy from free
text. Unknown or changed provider responses map to `vertex_request_failed`.
Messages are bounded, redacted, and never include tokens, credential paths,
raw response bodies, prompts, project metadata beyond the user-supplied project
ID, or organization details.

OAuth login state is not provider inference state. A signed-in identity can
still fail project, billing, IAM, region, API, or model admission, and Provider
Setup must display that distinction.

## 8. Security and lifecycle invariants

- No Google OAuth credential, access token, refresh token, service-account
  content, authorization code, PKCE verifier, or state is written to `.env`.
- None enters command-line arguments, child environment variables, logs,
  diagnostics JSONL, health payloads, crash manifests, installer summaries,
  acceptance artifacts, or user-facing errors.
- OAuth refresh credentials are protected with DPAPI CurrentUser and a
  Vertex-specific purpose/entropy string.
- Access tokens are short-lived, memory-only, and refreshed through supported
  Google authentication libraries.
- The Rook OAuth flow starts only from an explicit user action. Installer,
  startup, health, and model enumeration cannot open a browser.
- Login attempts are single-owner, bounded, cancellable, and cannot overwrite
  a previously working authorization until a new token exchange succeeds.
- A failed save cannot destroy the previous valid store.
- Disconnect is explicit, idempotent, and cannot touch Gemini or another
  provider's credentials.
- Invalid or unavailable Vertex configuration disables only Vertex. Rook
  startup, Rhino/Grasshopper tools, RookVision, local models, and every other
  configured provider remain operational.

## 9. External release prerequisites

The code path alone is insufficient for production readiness. Before Vertex is
advertised or enabled in a release:

- register a dedicated production Rook desktop OAuth client in a
  BringFire-controlled Google Cloud project;
- configure the production consent screen, support/home/privacy URLs, and
  verified domains;
- complete every Google brand/scope verification required for the documented
  `cloud-platform` scope;
- publish the exact client ID and administrator allowlisting guidance;
- document the minimum organization-side setup: existing project, billing,
  Vertex AI API, region/model availability, and minimum inference IAM;
- validate the installed candidate with a managed business identity against an
  organization-owned project;
- keep separate development/test and production OAuth projects/clients.

An unverified test client, personal project, consumer-only identity, Vertex
Express Mode key, or service-account-only test cannot satisfy production
acceptance.

## 10. Verification and acceptance

### 10.1 Permanent automated contracts

- Exact `gemini/...` versus `vertex_ai/...` provider classification.
- Existing Gemini API-key resolution and model behavior remain unchanged.
- RookVision Gemini image and Veo code retain their Developer API hostname and
  API-key authorization path, with no Vertex dependencies.
- Vertex configuration never mutates or falls back to Gemini configuration.
- DPAPI round trip, wrong-user/unprotect failure, atomic write, schema-version
  failure, and disconnect behavior.
- OAuth PKCE/state/loopback/single-attempt/timeout behavior with a fake token
  endpoint; no live credentials in automated tests.
- Exact scope set contains only `cloud-platform`.
- Rook Chat and DSPy obtain Vertex arguments only for `vertex_ai/...` calls.
- Chirp bootstrap uses the anonymous stdin pipe and rejects every other secret
  transport or malformed lifecycle.
- Token and service-account sentinels are absent from logs, health, errors,
  manifests, environment, command lines, and persisted non-DPAPI fields.
- Every closed error code is behaviorally covered, including unknown-provider
  response fallback.
- Vertex-unavailable tests prove non-Vertex models and Rook startup stay green.

### 10.2 Installed-candidate acceptance

Acceptance must start from exact reviewed Rook and Chirp commits and record the
installed file/wheel inventory and hashes. It must prove:

1. Existing Gemini Developer API configuration remains usable without
   reconfiguration.
2. Gemini Developer API and Vertex can be configured simultaneously and calls
   use their declared provider, endpoint family, and authorization type.
3. A managed organization identity completes Rook desktop OAuth in the system
   browser.
4. The organization-owned project and region pass the bounded readiness probe.
5. One benign installed Rook Chat call succeeds through `vertex_ai/...`.
6. One benign installed DSPy/agent call succeeds through `vertex_ai/...`.
7. One disposable Chirp component succeeds through `vertex_ai/...`, followed
   by owned-canvas cleanup.
8. Disconnect prevents subsequent Vertex refresh/use and leaves Gemini, local
   models, RookVision, and Rook tool operation healthy.
9. Logs, diagnostics, manifests, process command lines/environments, and
   acceptance artifacts contain no credential/token sentinels.
10. Hosts and sidecars close cleanly and the managed test project/model state
    is unchanged except for billed inference usage.

Live provider calls may incur cost. They require explicit acceptance-task
authorization, a named test model/project/region, bounded prompts, and no user
or customer data.

## 11. Commit and release structure

Vertex receives its own specification, implementation plan, private production
commits, review, deployment, and acceptance evidence. It must not include:

- Codex subscription implementation;
- unified Provider Setup presentation beyond the Vertex backend contract;
- installer password pages;
- RookVision provider changes;
- model-default changes;
- general secret-store refactoring;
- automatic Cloud administration;
- version bump, release notes, release build, or public promotion.

The separately specified Codex subscription implementation may proceed or stop
independently. If it cannot satisfy official-runtime and least-privilege gates,
that does not weaken Vertex acceptance or hold a completed Vertex integration
hostage.

Only after the accepted private provider work is on `main` may the 1.5.19
integration slice present both providers in one post-install Provider Setup
experience. The 1.5.19 version bump remains a later mechanical change. Release
artifacts are built, installed, accepted, and promoted only from the resulting
immutable merge provenance.

## 12. Explicitly rejected approaches

- Replacing Gemini Developer API with Vertex.
- One generic Google credential or model prefix.
- Automatic Gemini/Vertex routing or fallback.
- Persisting OAuth or service-account material in `.env`.
- Requiring `gcloud` for the primary user experience.
- Hiding project, billing, IAM, API, region, or model failures behind one
  generic authentication error.
- Creating a general multi-provider secret framework in the Vertex PR.
- Teaching Rook to create or administer the user's Google Cloud resources.
- Combining Vertex and Codex subscription implementation in one PR.

## 13. Planning gate

Implementation planning remains blocked until this written specification is
reviewed and approved. Planning must begin with a Task 0 probe that pins:

- the exact supported Google auth dependency versions in both sealed Python
  environments;
- the installed LiteLLM/DSPy Vertex argument contract;
- the exact non-generating readiness method and structured error evidence;
- the anonymous Chirp bootstrap lifecycle and redaction boundary;
- the exact file allowlist and no-touch guards for Gemini and RookVision.

No production OAuth client is created, no live enterprise login is attempted,
and no implementation code changes before that approval.

## Authoritative references

- [Google OAuth for desktop applications](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Google OAuth application verification](https://support.google.com/cloud/answer/13463073)
- [Google OAuth scope catalog](https://developers.google.com/identity/protocols/oauth2/scopes)
- [Google Application Default Credentials](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment)
- [Vertex AI Gemini quickstart](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/quickstart)
- [Vertex AI inference API errors](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/api-errors)
