# Firm sign-in for Google media in Rook

Date: 2026-10-05

Status: Initial draft for human and technical review; implementation is not authorized by this document.

First identity provider: Microsoft 365 / Microsoft Entra ID, confirmed by the user.

Source baseline: `bc5ae8dded237b9d33e87da0b868cf8babfea96c` on `codex/enterprise-google-media`; documentation baseline `c055a996`.

## 1. Purpose and boundaries

Employees should generate Google images and videos from Rook using their existing firm identity. They should receive firm settings from IT and sign in with Microsoft 365, without manually creating consumer Google accounts, creating individual Cloud projects, or managing OAuth client secrets. The firm owns authorization, project permissions, and Google usage billing. Rook remains a local client, with no Rook-operated credential broker, generation backend, or billing intermediary.

This extends the approved Google media design in `docs/plans/2026-10-05-enterprise-google-media-completion-design.md`. Reuse RookVision's registries, explicit Google providers, generation managers, ledger, publication guard, and artifact pipeline. Preserve existing personal Google OAuth, ADC, service-account, API-key, text, and Chirp behavior. This draft specifies a first Entra adapter, not universal compatibility with every OIDC/SAML provider.

Google describes Workforce Identity Federation as access through an external identity provider without corresponding Google user accounts. Its supported-services list includes Vertex AI. Those product-level statements do not establish that Rook's exact desktop sign-in, models, and polling flow have passed live acceptance. [Federation overview](https://docs.cloud.google.com/iam/docs/workforce-identity-federation), [supported services](https://docs.cloud.google.com/iam/docs/federated-identity-supported-services).

All actual tenant, organization, account, project, pool, client, credential, and private evidence values stay outside the repository and every Git worktree. Examples and committed tests use synthetic values only. No live configuration is included in this specification.

## 2. Existing implementation and reuse

The following are source observations, not new verification claims:

| Existing component | What it provides | Required extension |
| --- | --- | --- |
| `mcp_server/src/rook/providers/vertex_auth.py` | Windows-user credential store, DPAPI protection, mutation generation, OAuth/ADC/service-account modes | Versioned firm configuration and protected Entra session ownership |
| `vertex_oauth.py` | Desktop browser launch, PKCE, state, loopback callback, cancellation | Reuse lifecycle patterns; keep Google's desktop OAuth protocol separate from Entra |
| `vertex_backend.py` | Configuration mutation, readiness, disconnect, text credential loading and Chirp recycling | Federation-aware credentials and readiness; consistent project/header handling |
| `vertex_token_lease.py` | Bounded token refresh, cache, configuration generation and media binding | Stable principal/session binding, quota metadata, identity checks on cache reuse |
| `agent/chat/vertex_configuration_http.py` and `vertex_media_http.py` | Owned internal configuration and token routes | Versioned closed request/response shapes and firm actions |
| `src/Rook/UI/Chat/RookChatConfigurationDialog.Vertex.cs` | Google settings and connect/disconnect UI | Firm settings import, firm sign-in, explicit readiness and session status |
| `ChatServiceVertexAccessTokenSource.cs` and `VertexAccessTokenContract.cs` | C# token bridge and binding contract | Consume the versioned principal/project/header contract |
| `src/Rook/Services/Vision/Generation/Vertex/VertexMediaTransport.cs` | Bounded Google transport, single submission attempt, disabled redirects | Apply only validated quota-project metadata to the fixed Google destination |
| Existing generation managers, ledger and publication guard | Terminal transitions, interruption, restart reconciliation, artifact publication | Extend binding validation; retain existing race and restart behavior |

The current Python loaders use `google.auth.default()` for ADC, but return token strings or token/expiry records. They discard credential quota metadata. Current binding validation checks stored generation/project/location/model, not the principal underlying ambient ADC. Consequently, the existing ADC branch is a useful foundation, not evidence of completed federation support.

The pinned dependency is `google-auth==2.56.3`. Its installed `identity_pool` module exposes `SubjectTokenSupplier`; existing Google libraries can exchange a supplied identity assertion. No dependency installation or product code change is part of this draft.

The proposed work is Python authentication plus the managed C# configuration/token bridge and consumers. No native route, separate public MCP tool, Prime protocol, Revit dependency, or new generation queue is required.

## 3. Approaches and recommendation

| Approach | Benefit | Trade-off | Draft decision |
| --- | --- | --- | --- |
| Rook-owned Entra desktop sign-in and Google federation exchange | Employees use the existing work login; Rook can bind and protect its own session | Requires careful OIDC validation, token refresh and a proven Google exchange contract | Recommended first firm workflow |
| Administrator-prepared federated ADC | Reuses the ADC loader and existing external credentials | Ambient account changes and externally managed sessions need explicit binding; CLI setup is unsuitable as the ordinary employee experience | Keep existing ADC compatibility; not the default firm onboarding flow |
| Firm-hosted broker/service identity | Can centralize credentials and enterprise policy | Adds infrastructure, deployment, identity delegation and different audit semantics | Outside this extension |

The recommended flow uses an Entra public desktop application, authorization code with PKCE, and a validated Entra ID token as the assertion for Google's workforce exchange. Rook owns the local Entra session; Google owns workforce mapping and IAM authorization. [Microsoft's desktop authorization flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [Google's Entra federation setup](https://docs.cloud.google.com/iam/docs/workforce-sign-in-microsoft-entra-id).

Microsoft recommends its supported authentication library rather than hand-written protocol calls. The repository currently prohibits new dependencies. This draft proposes using existing transports, cryptographic dependencies and the Google SDK, with explicit protocol review. Adding MSAL is an alternative requiring a separately approved dependency exception; it must not be silently installed or vendored. Review must settle that trade-off before implementation planning is approved.

### Exchange feasibility checkpoint

Google's current Cloud OAuth API is Preview and recommends that new integrations use it. Its documented application code/refresh exchange requires client authentication, and its user-info endpoint is currently limited to Looker. Rook must not assume this is a proven public desktop client flow or use that user-info endpoint as its identity verifier. [Cloud OAuth overview](https://docs.cloud.google.com/iam/docs/cloud-oauth-api-overview), [application token exchange](https://docs.cloud.google.com/iam/docs/cloud-oauth-exchange-tokens).

The implementation plan must identify one documented, supported external-assertion exchange for the selected Entra registration and workforce pool, including exact endpoint, scope, user-project options, SDK compatibility, launch stage and refresh behavior. Prefer the existing Google SDK's workforce assertion exchange when supported; any choice of the documented STS flow must explain its use against Google's current migration guidance. Preview use requires an explicit review decision. There is no automatic fallback between STS, Cloud OAuth, personal OAuth, ADC or a service account.

A desktop flow that requires a confidential application secret on every employee machine does not satisfy this design. If a supported public-client exchange cannot be established, report the checkpoint as unresolved and revise the spec before implementing or presenting a firm sign-in button as functional. Do not substitute a broker or shared identity without scope approval. [Google's assertion exchange reference](https://docs.cloud.google.com/iam/docs/reference/sts/rest/v1/TopLevel/token).

## 4. Administrator and employee responsibilities

The administrator establishes a Google Cloud organization, workforce pool/provider, billed generation project, required APIs, model access and quota. A standalone project plus the existing desktop OAuth client is insufficient for workforce setup. The administrator registers the Entra public desktop application, pins its tenant and audience, maps a stable principal and approved group/assignment, and grants generation and service-usage permissions. Google-side audience/tenant constraints must match the assertion Rook obtains. Use `google.subject=assertion.oid` with the pinned tenant and appropriate restrictions; the pool's OIDC client ID must match the desktop assertion's audience. Google-hosted console sign-in, if needed by IT, has its own registration/redirect requirements and must not be confused with Rook's direct desktop flow. [Organization and pool prerequisites](https://docs.cloud.google.com/iam/docs/configuring-workforce-identity-federation), [Entra pool mapping](https://docs.cloud.google.com/iam/docs/workforce-sign-in-microsoft-entra-id).

The employee imports an administrator-provided, non-secret connection file, chooses **Sign in with your firm**, completes normal Entra browser authentication/MFA, and uses the existing Google Enterprise media providers. Employees do not grant themselves IAM roles or upload service-account keys. Rook does not request Microsoft mail, files, contacts or directory-reading access merely to authenticate.

Google lists Workforce Identity Federation as free; detailed logging can have usage charges. Model generation remains usage-billed to the firm's generation project. Existing Microsoft licensing and Conditional Access policies must be assessed by IT. The UI and guide must describe this API billing model without promising that a Workspace/Gemini subscription includes these API requests. [Federation pricing](https://cloud.google.com/workforce-identity-federation), [generation pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing?hl=en).

## 5. Firm settings and persistence

Introduce a versioned firm connection object within the existing provider store. Keep one active Google authorization per Windows profile. Switching the active authorization is deliberate and interrupts old jobs. Multi-firm switching is allowed; simultaneous account selection per job is outside this slice.

The administrator's connection file contains only:

- Schema version and a display label.
- Entra tenant ID and public application client ID; the first adapter supports Microsoft's public cloud, tenant-specific v2 OIDC endpoints.
- Google organization, workforce pool and provider identifiers.
- Generation project ID, workforce user-project identifier, and optional explicit API quota-project ID.
- Existing shared text/video location and the supported exchange selection determined at the feasibility checkpoint.

Compute issuer, audience and Google endpoints from these typed fields and the supported adapter. Reject unknown fields, malformed values, conflicting tenant/audience, secrets, arbitrary URLs, executable credential sources, service-account impersonation and sovereign-cloud configurations in the first adapter. Configuration import is bounded to 64 KiB, rejects duplicate JSON keys, and validates before network activity. Import is an explicit local trust action; a file's mere presence does not authenticate its administrator. Managed distribution may use the firm's existing device-management mechanism; no new configuration distribution service is required.

Import copies validated settings into a Rook-owned store; a mutable source path must not become an unchecked runtime authority. A later file edit has no effect until explicitly reimported. Firm settings edits rotate the existing authorization generation even if the employee remains the same.

Keep encrypted Entra refresh/session material, stable identity information and any fingerprint key under the existing Windows-user DPAPI ownership. Protect files with the existing store ACL/mutex/atomic replacement patterns. No plaintext refresh tokens, identity assertions or bearer tokens in manifests, ledgers, diagnostics, browser callback logs or Git. The managed companion receives only a short-lived Google bearer lease and the minimal validated request/binding fields.

Read the existing version-1 store without changing its meaning. Migrate on explicit save/connect to a versioned format that retains all existing modes. Validate schema before decrypting. Failed import or sign-in leaves the prior connection usable. Switching to a new connection commits only after identity and exchange checks succeed; cancellation before commit retains the old authorization. Cancellation after commit reports the committed state accurately. Unknown future formats fail closed. Document rollback limitations for older binaries; any backup remains outside Git.

## 6. Entra sign-in, assertion validation and refresh

Python remains the credential owner. Reuse the existing browser/callback lifecycle, not its Google-specific URLs or client-secret handling. Use the system browser, authorization code, PKCE S256, fresh state and OIDC nonce, and only a loopback callback compatible with the registered desktop redirect URI. Verify callback scheme/host/path, state, single-use code and nonce before committing. Close the listener on success, cancellation or timeout; callback data is never logged.

Use tenant-specific endpoints; never `common`, `organizations` or `consumers` as a silent account-discovery fallback. Ask for `openid` and the minimal refresh capability required by the chosen Entra flow. Additional claims/scopes require a documented purpose. User passwords and MFA responses are handled entirely in Microsoft's browser pages.

Verify the ID token signature with the tenant's supported signing keys, issuer, audience, tenant, expiry/not-before and initial nonce, with a maximum 60-second clock tolerance. Pin supported algorithms; reject unsigned tokens, algorithm confusion and keys from an arbitrary token URL. Resolve discovery/JWKS only through the supported tenant adapter; cap responses at 1 MiB and prohibit transport redirects. A bounded key refresh on an unknown key ID may occur once; failure requires a new sign-in or a classified connection error. [Microsoft ID-token claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).

Identify the Entra principal by validated tenant/object identity, not email, display name or mutable username. The first Google pool mapping must use the corresponding stable object claim with tenant restrictions; Rook does not infer the mapping from an email. A refreshed assertion must retain the principal and expected audience. Never treat an unverified JWT decode or a raw token hash as an identity proof.

Refresh the Entra assertion and exchange it through the selected Google adapter. Rotate any returned Entra refresh material atomically under DPAPI. Google credentials must receive the explicit workforce user-project option where required. Interactive reauthentication is initiated only by a user action: background video polling must not open a browser or repeatedly prompt. Refresh rejection becomes **Sign-in required**, interrupts the bound job, and does not resubmit it.

Preserve the current aggregate token-issuance ceiling of 30 seconds, 20-second per-request maximum and serialized refresh ownership, including lock wait, Entra refresh, key retrieval and Google exchange. Initial interactive sign-in has a 180-second browser deadline and a separately bounded exchange/commit phase. A late worker must not install a session after cancellation or overwrite a newer connection. Transport or refresh errors are mapped to fixed public codes; no raw Entra/Google response bodies or exception strings escape to the UI.

## 7. Credential context, projects and headers

Extend the existing credential result rather than inventing a second token service. Its versioned result carries bearer/expiry, authorization generation, opaque principal/session identity, connection fingerprint, generation project, workforce user project and optional API quota project. Python validates all fields; C# rejects missing, unknown or inconsistent fields for the selected contract version.

Keep these project roles distinct:

| Role | Request use |
| --- | --- |
| Generation project | Fixed project in the model/operation resource path; intended owner and billing context for model generation |
| Workforce user project | Explicit workforce token-exchange accounting/service-usage option where required by Google's contract |
| API quota project | Optional validated `x-goog-user-project` metadata applied to Google API calls when required/configured |

The default firm setup uses the same approved firm project for all three roles. Distinct projects require explicit administrator configuration and documented billing/quota verification; never derive one from an ambient default. Do not claim that a quota header redirects all model charges away from the resource project.

The C# bridge must pass validated quota metadata through the token lease. Media transport derives only the permitted header, never accepts an arbitrary header dictionary, and attaches it only to the fixed Google model endpoint. The bearer and header context belong to one lease. Apply consistent credential context to text readiness, text generation and Chirp consumers through their existing adapters. Personal OAuth/service-account behavior must retain its previous project semantics unless explicitly configured otherwise. Validate Google's requirements for each consumer at the exchange checkpoint. [Workforce credentials and user projects](https://docs.cloud.google.com/iam/docs/workforce-obtaining-short-lived-credentials).

## 8. Binding and lifecycle guarantees

Introduce binding version 2 for newly created firm jobs: authorization generation, opaque principal/session ID, connection fingerprint, generation project, workforce user project, API quota project, location and model. Binding fields contain no tokens, raw tenant/object identifiers or account emails. Use a random local principal identifier backed by an encrypted identity association; connection fingerprints use a protected keyed digest over canonical settings, rather than publishing raw identifiers or unhashed credential material. Existing project fields remain local and are sanitized in shareable evidence.

Refresh for the same verified principal and unchanged connection keeps the authorization generation stable. Any successful new interactive connection, account switch, connection import or project/location/quota change rotates it. New interactive sign-in interrupts old jobs even when the person is the same; this keeps reconnect semantics deterministic.

Check the original binding before cache reuse, before refresh, after refresh before issuing the lease, before request dispatch, and before artifact publication. Publication validation checks the current Rook-owned identity/session/configuration, not only the original generation string. Never search ambient ADC for a replacement if the firm session fails.

For supported externally managed ADC, revalidate a credential-source/principal binding before reuse. If the adapter cannot establish stable principal continuity, do not advertise it as satisfying firm acceptance. Preserve existing legacy ADC behavior without silently reclassifying it as federation. A changed external credential file invalidates its pinned session; there is no automatic adoption of a replacement identity.

Disconnect locally invalidates leases, removes Rook-owned refresh/session material and rotates/removes authorization. It does not sign the employee out of Microsoft 365 globally, revoke the firm's application registration, or promise immediate invalidation of already issued Google tokens. Provider revocation and IAM/group changes can take time to affect cached credentials; report observed denial/refresh failure accurately and do not claim instantaneous detection of an administrator action.

Retain the current terminal transition/publication guard: if stop/disconnect wins, the record is `Interrupted` and late handlers cannot publish or overwrite it. If completion already won, its completed artifact remains terminal. A Google request dispatched before a local change may continue and incur charges. This is not a distributed transaction or confirmed remote cancellation.

At most one media submission dispatch per local job; no submission retries after ambiguous acceptance or authorization failure. Poll/fetch retries retain the same operation and complete binding. Restart reconciles unfinished jobs to `Interrupted`, with zero automatic submit/poll/fetch. Existing version-1 terminal records and artifacts remain readable; old bindings cannot be upgraded into a newly connected firm's authorization. Retain inline video limits, bounded transport, redirect rejection and `LocalStopOnlyOutcome` from the approved media spec.

## 9. Settings, status and error behavior

The Enterprise Google tab offers **Google account** and **Firm sign-in (Microsoft 365)** connection choices. Firm settings are imported once; show the firm label, approved generation project, locations and explicit project changes before save. Offer **Sign in with your firm**, **Check access**, **Disconnect from Rook**, and **Read local settings**. Employees should not see a Google desktop-client JSON field in the firm flow.

Separate states: unconfigured, configured/sign-in required, signing in, connected, checking access, generation ready, permission denied and service unavailable. Local **Connected** means Rook holds a valid bound session, not that both models have passed readiness. Existing image `global` and video `us-central1` remain unchanged. Preserve the existing deliberate-save warning because text/Chirp share the location.

Readiness uses existing probe infrastructure and distinguishes sign-in, exchange, project/API/billing, model/location and permission failures with fixed messages. Any probe that generates billable output requires an explicit user action and is counted in the pilot budget; passive status does not dispatch generation. Directory group authorization is evaluated by Google/Entra policy, not by requesting Microsoft Graph data from every employee.

Keep configuration operations on the existing session-nonce-protected owned route, with closed operation schemas. Do not expose credential export or generic token exchange over the public Rhino/MCP surface. All new authentication errors map through Python and C# consistently. A denied operation never offers an automatic account/project fallback.

## 10. Automated verification

Tests use synthetic providers, principals, assertions and projects. No live credentials are prerequisites for source work. Rebuild affected C# frameworks and Python payload before final verification; existing assemblies and earlier test counts are baseline evidence only.

Required cases:

1. Version-1 compatibility, versioned store/lease/binding round trips, invalid/unknown fields, duplicate keys, cancelled import/connect and safe rollback.
2. PKCE/state/nonce validation; bad signature/issuer/audience/tenant; expired/future tokens; unknown signing key and bounded key rotation; forbidden discovery redirects/URLs; callback replay and timeout cleanup.
3. Same-principal refresh preserves binding; different-principal refresh and a new connection interrupt old jobs. Concurrent refresh/import/disconnect cannot return a late valid lease or commit a cancelled session.
4. Correct workforce exchange options and approved API quota header for submit, poll and text consumers; absent/malformed/conflicting metadata is refused without dispatch. Token and quota fields cannot independently drift.
5. Deterministic stop/disconnect/completion races, including validation-only cache paths and a held network response released after disconnect. Zero publication when interruption wins.
6. External ADC change without a settings save is detected by its supported adapter or classified as unsupported for firm acceptance. No adoption of the ambient replacement identity.
7. Exactly one submission for ambiguous response loss; zero resubmissions after denial, reauthentication or restart. Read-only retries retain the operation and binding.
8. Regression coverage for personal OAuth, service account and ADC readiness; Vertex text/Chirp shared-region behavior, deliberate saves and generation recycling; existing API-key providers and completed artifacts.
9. Synthetic secret-sentinel scans of store serialization, diagnostics, exceptions, leases, ledger and evidence. Verify DPAPI-protected storage and that no arbitrary credential executable or generic header forwarding is admitted.

No source test counts are claimed in this draft. Review must inspect both Python ownership/identity code and C# lease/publication consumers before installed acceptance.

## 11. Installed live acceptance

Live prerequisites are the administrator-approved Entra app/pool configuration, eligible test employees, Cloud billing/IAM/model quota, tested installed runtime and an explicit generation budget. They are prerequisites for live proof, not for resolving design questions or writing mocked tests. The earlier Google-account pilot budget is not automatically authorization to spend it on a different firm project.

Propose one image and three supported short videos after approval: successful completion with a forced in-memory lease refresh, active disconnect, and active restart. For the refresh case, invalidate only Rook's cached Entra assertion and Google access lease through a source-only test seam so an actual Entra refresh and Google exchange are observed; do not alter a signed token, persisted identity, or the job's binding. Stop/completion races and ambiguous submission use automated fixtures. Any extra billed job requires separate authorization; an intervention missed because a video completed early is inconclusive.

| Live criterion | Required evidence |
| --- | --- |
| Existing firm login | Entra browser sign-in/MFA succeeds; employee creates no Google consumer account and supplies no secret; valid assertion exchange under the configured workforce pool |
| Direct firm project use | Sanitized request-path and quota-context correlation; private Cloud billing/audit inspection confirms intended project attribution, with reporting delays recorded; no Rook billing intermediary |
| Image | Exactly one submission; artifact byte count/hash and decoded dimensions match the request/model |
| Video and refresh | Exactly one submission; real Entra assertion refresh and Google exchange observed after polling begins; later poll uses the same principal/projects/operation; duration/dimensions, first/middle/last frame decode and RookVision playback verified |
| Active disconnect | After an observed in-flight poll, local disconnect prevents later dispatch/publication; job `Interrupted`; reconnect does not resume it |
| Active restart | Accepted operation persisted, installed owner restarted, job becomes `Interrupted`; no automatic submit/poll/fetch; completed artifacts still open |
| Account switch | Two approved Entra identities establish distinct opaque bindings; the old binding is refused after switching, using an existing interrupted job or a controlled local fixture; zero extra media submissions |
| Group/permission denial | An administrator-controlled denied test identity/configuration is classified correctly; no fallback identity or new media submission; separately record revocation propagation rather than assuming instant enforcement |
| Privacy | Actual configuration, credential files, private mapping, raw logs and media remain outside Git; sanitized evidence passes a local scan against held private values without printing them |

Sanitized evidence records source commit/dirty state, installed hashes and runtime/dependency versions, Entra/Google adapter and exchange launch stage, models/locations, UTC times, opaque user/firm/project labels, request and refresh counts, ledger transitions, artifact measurements, playback observation and per-case pass/fail/inconclusive/not-run. Natural expiry and forced refresh are distinct coverage. If billing attribution cannot yet be observed, that criterion remains pending rather than passed.

Automated acceptance and live acceptance are reported separately. Feature completion requires both; a functioning browser login or passing mock suite alone is insufficient.

## 12. Review decisions and handoff

Review this draft for the following explicit decisions before implementation planning:

1. Approve Entra as the first adapter and the administrator-distributed, non-secret firm settings workflow.
2. Settle the desktop authentication-library choice: the existing-dependency protocol implementation versus an expressly approved MSAL dependency exception.
3. Resolve the Google external-assertion exchange checkpoint, including current STS migration guidance, Cloud OAuth Preview suitability, SDK support and public-client requirements. Do not replace this with a claim of generic Vertex federation support.
4. Approve version-2 identity/project bindings and the deliberate reconnect/interruption policy, including version-1 compatibility and external ADC limitations.
5. Approve the separate automated/live acceptance criteria; live project, test identities and spend authorization are supplied privately later.

The next deliverable after the user's written-spec approval is an implementation plan with contracts/consumers preceding providers, focused buildable commits, identity/credential and publication checkpoints, an independent whole-branch review, and fresh installed acceptance. This document creates no new OAuth application, permission grant, dependency installation or billed generation.
