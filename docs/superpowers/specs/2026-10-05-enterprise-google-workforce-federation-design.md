# Firm sign-in for Google media in Rook

Date: 2026-10-05

Status: Revised for review. The user authorized these revisions and implementation-plan writing. Implementation and live spend remain unapproved.

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

Use Python `msal==1.39.0` for Entra public-client sign-in and refresh. The user explicitly approved a scoped exception to the repository dependency prohibition for MSAL and its required dependencies, with version pins, dependency-diff review and packaged-runtime inclusion. Python retains credential ownership and DPAPI persistence. Do not add MSAL Extensions, broker extras, `pymsalruntime`, a CLI or a hosted broker under this exception. Microsoft's supported library replaces the proposed handwritten Entra grant implementation. [Microsoft guidance](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [MSAL 1.39.0 release metadata](https://pypi.org/project/msal/1.39.0/).

Preserve existing dependency pins: development lock `requests==2.34.2`, `PyJWT==2.13.0`, `cryptography==50.0.0`; packaged third-party lock `requests==2.34.2`, `PyJWT==2.14.0`, `cryptography==50.0.1`. These existing profile differences are not permission to upgrade either profile incidentally. MSAL's required ranges accept them. Add the MSAL wheel to both locked dependency graphs and the packaged-runtime hash lock; review any further resolver change before admitting it. Google SDK remains `google-auth==2.56.3`.

### Selected Google exchange and migration decision

Pin the first adapter to `POST https://sts.googleapis.com/v1/token` through `google.auth.identity_pool.Credentials` and a Rook-owned `SubjectTokenSupplier`. Use the following SDK-generated form contract; the assertion is a validated Entra ID token, never an Entra API access token:

| Field | Required value |
| --- | --- |
| `grant_type` | `urn:ietf:params:oauth:grant-type:token-exchange` |
| `requested_token_type` | `urn:ietf:params:oauth:token-type:access_token` |
| `subject_token_type` | `urn:ietf:params:oauth:token-type:id_token` |
| `audience` | `//iam.googleapis.com/locations/global/workforcePools/{pool_id}/providers/{provider_id}` |
| `scope` | `https://www.googleapis.com/auth/cloud-platform` |
| `subject_token` | The Rook-validated, current assertion for the bound Entra principal |
| `options` | SDK serialization of `{"userProject": "<configured-workforce-user-project>"}` |

Do not send `Authorization`, Google client ID/secret, or an organization authorization code. Construct Google credentials with the explicit `workforce_pool_user_project` and optional `quota_project_id`; preserve the latter in the downstream lease. The SDK owns form/options encoding. Google returns a short-lived access token and expiry; no Google refresh token is assumed for this assertion grant. Refresh means obtaining a fresh Entra assertion through MSAL and repeating this same STS exchange. [Documented workforce assertion flow](https://docs.cloud.google.com/iam/docs/workforce-obtaining-short-lived-credentials), [STS token contract](https://docs.cloud.google.com/iam/docs/reference/sts/rest/v1/TopLevel/token).

Migration decision: retain the documented STS assertion grant for this first implementation. Google's newer Cloud OAuth API is Preview and recommends migration, but the cited organization-token reference exposes Google authorization-code/refresh grants rather than this Entra assertion grant. Replacing the STS hostname would change the contract without evidence of compatibility. Cloud OAuth Preview is not approved; no fallback or endpoint substitution is allowed. Migration requires a separately reviewed documented external-assertion/public-client contract, SDK compatibility, identity/quota equivalence and acceptance evidence. Recheck this decision before release qualification; if Google withdraws the selected contract, report it and revise the design rather than redirect credentials. [Cloud OAuth guidance](https://docs.cloud.google.com/iam/docs/cloud-oauth-api-overview), [organization-token reference](https://docs.cloud.google.com/iam/docs/reference/cloudoauth/rest/v1/organizations/token).

On 2026-10-05, a no-network synthetic evaluation using installed `google-auth==2.56.3` observed one mock STS request with the exact grant/audience/scope/type/options above, no client authentication, parsed expiry and preserved quota-project metadata. This verifies SDK request construction, not assertion validity, IAM/billing or live Google acceptance. Repeat it as a committed automated test during implementation. There is no automatic fallback to personal OAuth, ambient ADC or a service account.

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
- Existing shared text/video location and fixed exchange identifier `sts_id_token_v1`.

Compute issuer, audience and Google endpoints from these typed fields and the supported adapter. Reject unknown fields, malformed values, conflicting tenant/audience, secrets, arbitrary URLs, executable credential sources, service-account impersonation and sovereign-cloud configurations in the first adapter. Configuration import is bounded to 64 KiB, rejects duplicate JSON keys, and validates before network activity. Import is an explicit local trust action; a file's mere presence does not authenticate its administrator. Managed distribution may use the firm's existing device-management mechanism; no new configuration distribution service is required.

Import copies validated settings into a Rook-owned **pending settings** slot, separate from the active authorization. A mutable source path must not become an unchecked runtime authority. Later source-file edits have no effect until explicitly reimported. Import/reimport creates a new pending revision but changes neither active settings, authorization generation, credential cache nor running jobs. Reading pending settings does not report them as connected.

Sign-in captures the pending revision and the active authorization generation/tombstone, and uses an isolated temporary MSAL cache. Only successful Entra identity validation plus successful STS exchange can atomically activate the candidate settings, principal association, DPAPI-protected cache and new authorization generation. Activation uses compare-and-swap under the existing mutation lock: a changed pending revision, disconnect, concurrent active save or another successful login invalidates the candidate. Do not merge candidate refresh material into the active cache before activation.

In workforce mode, project/location/quota edits use pending reimport and successful reactivation; the legacy shared-setting save operation returns a fixed reimport-required error. Existing legacy active saves still rotate their generation and invalidate any pending login ticket captured before that save.

Failed or cancelled login leaves the prior active authorization and its jobs unchanged; the pending settings remain available for a deliberate retry. Activation rotates generation and interrupts prior jobs even for the same employee. Reimport during login invalidates that attempt. **Disconnect from Rook** clears both pending settings and active session, advances a retained mutation tombstone, invalidates outstanding candidates and interrupts active jobs. A late successful response cannot restore a disconnected session. A separate **Discard pending settings** action removes only the pending slot and cancels its candidate; it does not disconnect an active account.

Keep encrypted Entra refresh/session material, stable identity information and any fingerprint key under the existing Windows-user DPAPI ownership. Protect files with the existing store ACL/mutex/atomic replacement patterns. No plaintext refresh tokens, identity assertions or bearer tokens in manifests, ledgers, diagnostics, browser callback logs or Git. The managed companion receives only a short-lived Google bearer lease and the minimal validated request/binding fields.

Bound the serialized MSAL cache to 256 KiB before protection, the version-2 store envelope to 512 KiB on read/write, and each identity assertion/token response to 1 MiB. Keep the existing tighter version-1 limits when parsing version-1 records. These are storage/transport bounds, not permission to persist access leases outside the protected credential store. Public settings imports remain bounded to 64 KiB.

Read the existing version-1 store without changing its meaning. Explicit pending import may persist the versioned envelope without changing the active version-1 authorization/generation; activation or an explicit active save migrates active data. Validate schema before decrypting. Failed import changes neither slot. Sign-in activation obeys the atomic rules above; cancellation after activation reports committed state accurately. Unknown future formats fail closed. Document rollback limitations for older binaries; any backup remains outside Git.

## 6. Entra sign-in, assertion validation and refresh

Python remains the credential owner. Use `msal.PublicClientApplication` with a tenant-specific authority, no client credential and broker disabled. Use MSAL's public `initiate_auth_code_flow` / `acquire_token_by_auth_code_flow` APIs so Rook can own a cancellable, bounded loopback listener while MSAL owns PKCE/state/nonce/grant handling. Use the system browser and a desktop redirect registered as `http://localhost`; preserve its supported ephemeral-port semantics. Restrict callback host/path/port and bounded POST form handling. Close the listener on success, cancellation or timeout; callback data and flow dictionaries are never logged. The adapter must prove PKCE S256/state/nonce behavior with the pinned library, not assume it from a method name.

Use tenant-specific endpoints; never `common`, `organizations` or `consumers` as a silent account-discovery fallback. The required effective scopes are exactly **`openid profile offline_access`**. `profile` supplies `oid`, which this binding requires; `offline_access` enables the MSAL refresh session. With MSAL 1.39.0, these are reserved scopes added by the library: pass an empty resource-scope list, do not pass the reserved strings directly, and do not configure `exclude_scopes` to remove them. Tests inspect both authorization and token requests for all three and zero Graph/resource scopes. Missing `oid` or `tid` is a hard failure before STS or activation; neither email nor `sub` replaces them. User passwords and MFA responses are handled entirely in Microsoft's browser pages. [Required claim scope](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference), [pinned MSAL scope handling](https://github.com/AzureAD/microsoft-authentication-library-for-python/blob/1.39.0/msal/application.py).

Verify the ID token signature with the tenant's supported signing keys, issuer, audience, tenant, expiry/not-before and initial nonce, with a maximum 60-second clock tolerance. Pin supported algorithms; reject unsigned tokens, algorithm confusion and keys from an arbitrary token URL. Resolve discovery/JWKS only through the supported tenant adapter; cap responses at 1 MiB and prohibit transport redirects. A bounded key refresh on an unknown key ID may occur once; failure requires a new sign-in or a classified connection error. [Microsoft ID-token claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).

Identify the Entra principal by validated tenant/object identity, not email, display name or mutable username. The first Google pool mapping must use the corresponding stable object claim with tenant restrictions; Rook does not infer the mapping from an email. A refreshed assertion must retain the principal and expected audience. Never treat an unverified JWT decode or a raw token hash as an identity proof.

Refresh through MSAL's `acquire_token_silent_with_error` for the explicitly bound cache account, forcing refresh when an assertion must be renewed, then validate the returned ID token's signature/claims and unchanged `tid`/`oid` before STS. Missing identity claims or changed identity must issue no Google token and must not overwrite the protected active cache. Load the protected cache and its monotonically increasing cache revision together. Commit the validated updated `SerializableTokenCache` atomically under DPAPI only when the active generation, verified principal and expected cache revision still match. Increment the cache revision on every accepted cache write while preserving authorization generation. A revision conflict refuses the stale result without automatic replay or merging. Google credentials receive the explicit workforce user-project option. Interactive reauthentication is initiated only by a user action: background video polling must not open a browser or repeatedly prompt. Refresh rejection becomes **Sign-in required**, interrupts the bound job, and does not resubmit it.

Each refresh has a thread-safe cancellation event and an absolute monotonic deadline. Timeout or cancellation sets that event before the async refresh lock can be released; cancelling `asyncio.to_thread` is not proof that the underlying worker stopped. Check the event/deadline before each network dispatch, after each response, after acquiring the mutation lock and immediately before atomic cache replacement. Check again before returning or caching the Google lease. Late workers can neither persist refresh material nor install a bearer lease, even if generation is unchanged. The durable revision check also prevents an old worker from overwriting a newer refresh. Tests hold the old response past timeout, commit a newer refresh, then release the old response and assert unchanged new cache/revision and no late lease. A write that already committed before cancellation is reported accurately; do not claim to undo it.

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

The C# bridge must pass validated quota metadata through the token lease. Media transport derives only the permitted header, never accepts an arbitrary header dictionary, and attaches it only to the fixed Google model endpoint. The bearer and header context belong to one lease. Personal OAuth/service-account behavior must retain its previous project semantics unless explicitly configured otherwise. Verify service-usage/quota behavior for both media consumers in automated and installed acceptance; the selected STS contract is fixed above. [Workforce credentials and user projects](https://docs.cloud.google.com/iam/docs/workforce-obtaining-short-lived-credentials).

Scope clarification from source inspection: the first workforce adapter enables images and videos only. Current text uses LiteLLM JSON credential dictionaries, and Chirp serializes credentials into its existing bootstrap; a live `SubjectTokenSupplier` cannot be passed through either contract as-is. Do not introduce a second credential-export server or plaintext assertion file to solve that different integration. Preserve existing text/Chirp behavior in the legacy modes; when workforce mode is active, return a fixed `vertex_text_federation_unsupported` error for Vertex text readiness/generation and refuse Vertex-required Chirp bootstrap before starting a child, with zero ADC fallback. Non-Vertex text and Chirp remain available. Switching the one active profile to firm mode must clearly disclose this limitation and retire prior Vertex Chirp processes. Workforce text/Chirp enablement needs a separate compatible adapter design. Review this boundary explicitly before implementation.

Install those text/Chirp guards in the same commit that first enables workforce activation. After activation, use an explicit stop-only retirement path, before any replacement-credential resolution or child restart. Reuse existing discovery, ownership, retirement-event, bounded-wait and verified forced-termination checks. Conservatively retire an existing Rook-managed Chirp sidecar because it may retain prior Vertex credentials; never terminate an unowned process. No replacement starts during this operation. All live reuse and launch paths recheck active mode, including under the existing replacement lock, so a pre-activation startup cannot subsequently install a Vertex child. Non-Vertex Chirp can start again through its normal path without Vertex bootstrap.

Activation records `chirp_retirement_pending=true`; only generation-conditional, verified retirement clears it. Retirement failure returns fixed `vertex_restart_required` with the committed generation, retains the active firm session and pending retirement flag, and issues no workforce media lease. Do not roll back authorization or label activation successful while an old sidecar may remain. Explicit **Check sign-in**, including after a local restart, may retry stop-only retirement before enabling leases, without credential replacement or generation submission. Passive startup/status never clears the flag or claims retirement. Bound replacement-lock acquisition and retirement waits by the remaining operation deadline; do not hold the credential mutation lock during process or network waits. Tests cover no live child, successful retirement, ownership/timeout failure, unchanged committed identity on failure and concurrent startup. Failed Entra sign-in/exchange before activation never retires the prior sidecar.

## 8. Binding and lifecycle guarantees

Introduce binding version 2 for newly created firm jobs: authorization generation, opaque principal/session ID, connection fingerprint, generation project, workforce user project, API quota project, location and model. Binding fields contain no tokens, raw tenant/object identifiers or account emails. Use a random local principal identifier backed by an encrypted identity association; connection fingerprints use a protected keyed digest over canonical settings, rather than publishing raw identifiers or unhashed credential material. Existing project fields remain local and are sanitized in shareable evidence.

Refresh for the same verified principal and unchanged active connection keeps the authorization generation stable. Successful new interactive activation, account switch or deliberate active project/location/quota save rotates it. Pending import/discard alone never rotates active authorization. New interactive sign-in interrupts old jobs even when the person is the same; this keeps reconnect semantics deterministic.

Check the original binding before cache reuse, before refresh, after refresh before issuing the lease, before request dispatch, and before artifact publication. Publication validation checks the current Rook-owned identity/session/configuration, not only the original generation string. Never search ambient ADC for a replacement if the firm session fails.

Externally managed ADC is not an accepted firm adapter in this slice. Preserve its existing legacy behavior without reclassifying it as federation or using it to repair a failed workforce session. Any later firm ADC adapter must prove source/principal continuity before reuse and reject a changed source without automatically adopting a replacement identity. This release's firm guarantees apply to the Rook-owned MSAL session and its version-2 binding.

Disconnect locally invalidates leases, removes Rook-owned refresh/session material and rotates/removes authorization. It does not sign the employee out of Microsoft 365 globally, revoke the firm's application registration, or promise immediate invalidation of already issued Google tokens. Provider revocation and IAM/group changes can take time to affect cached credentials; report observed denial/refresh failure accurately and do not claim instantaneous detection of an administrator action.

Retain the current terminal transition/publication guard: if stop/disconnect wins, the record is `Interrupted` and late handlers cannot publish or overwrite it. If completion already won, its completed artifact remains terminal. A Google request dispatched before a local change may continue and incur charges. This is not a distributed transaction or confirmed remote cancellation.

At most one media submission dispatch per local job; no submission retries after ambiguous acceptance or authorization failure. Poll/fetch retries retain the same operation and complete binding. Restart reconciles unfinished jobs to `Interrupted`, with zero automatic submit/poll/fetch. Existing version-1 terminal records and artifacts remain readable; old bindings cannot be upgraded into a newly connected firm's authorization. Retain inline video limits, bounded transport, redirect rejection and `LocalStopOnlyOutcome` from the approved media spec.

## 9. Settings, status and error behavior

The Enterprise Google tab offers **Google account** and **Firm sign-in (Microsoft 365)** connection choices. Show pending and active settings distinctly, including firm label, approved generation project, locations and explicit project changes before activation/save. Offer **Import firm settings**, **Discard pending settings**, **Sign in with your firm**, **Check sign-in**, **Disconnect from Rook**, and **Read local settings**. Sign-in consumes the displayed pending revision; active settings can be copied into a new pending revision for deliberate reconnection. Employees should not see a Google desktop-client JSON field in the firm flow.

Firm states are unconfigured, configured/sign-in required, signing in, signed in/model access unverified, checking sign-in, sign-in required, exchange denied, service unavailable, authorization changed and restart required. Successful initial STS exchange or sign-in check never produces **Generation ready**. Local **Signed in** means Rook holds a bound session and confirmed sidecar retirement, not that either model is usable. Passive status shows locally configured model/location support as configured, not remotely verified. Existing image `global` and video `us-central1` remain unchanged. Preserve the existing deliberate-save warning because text/Chirp share the location.

Narrow the firm action to an identity/exchange check, not a model-readiness probe. The owned `check_firm_sign_in` operation captures the displayed active generation, finishes any pending stop-only retirement, forces silent Entra refresh and STS exchange under the existing 30-second aggregate deadline, and rechecks the same binding. No browser, Gemini text probe, model lookup, submit, poll or fetch is allowed. Return a version-2 result with `check_scope=identity_exchange`, a fixed state/code, active generation and `image_access`, `video_access`, `billing`, `quota` each explicitly `unverified`, including after success. A changed authorization discards the result; timeout/refusal cannot leave a successful check displayed. Fixed UI copy: **Sign-in and Google exchange passed. Image/video access, billing and quota remain unverified.**

Keep existing legacy text readiness behavior separate. Actual image/video submissions use existing managers and error classification; successful output proves only that observed request succeeded. Live generation and private billing evidence remain the model/billing acceptance gate. Do not add a billable readiness probe to this slice. Directory group authorization is evaluated by Google/Entra policy, not by requesting Microsoft Graph data from every employee.

Keep configuration operations on the existing session-nonce-protected owned route, with closed operation schemas. Do not expose credential export or generic token exchange over the public Rhino/MCP surface. All new authentication errors map through Python and C# consistently. A denied operation never offers an automatic account/project fallback.

A timed-out sign-in check returns within its 30-second caller ceiling after revoking its worker. Retain/observe the worker and keep the mutation slot occupied until it actually settles; do not extend the response by awaiting an unbounded cleanup. Disconnect can cancel an outstanding worker and invalidate the active store/tombstone immediately. Late cleanup cannot overwrite UI success or clear a newer worker's slot. These route-level cases are tested separately from direct store/refresh tests.

## 10. Automated verification

Tests use synthetic providers, principals, assertions and projects. No live credentials are prerequisites for source work. Rebuild affected C# frameworks and Python payload before final verification; existing assemblies and earlier test counts are baseline evidence only.

Required cases:

1. Version-1 compatibility, versioned store/lease/binding round trips, invalid/unknown fields, duplicate keys and safe rollback. Import followed by failed login or cancellation preserves active credentials/generation/jobs; import followed by disconnect clears both slots. Reimport/discard/disconnect during login defeats late activation by revision/tombstone checks.
2. Required effective `openid profile offline_access` on initial and refresh requests, missing `oid`/`tid` before exchange, PKCE/state/nonce validation; bad signature/issuer/audience/tenant; expired/future tokens; unknown signing key and bounded key rotation; forbidden discovery redirects/URLs; callback replay and timeout cleanup. Assert no Graph scope, broker dependency, client secret or reserved-scope API error.
3. Same-principal refresh preserves binding; different-principal refresh and a new connection interrupt old jobs. Concurrent refresh/import/disconnect cannot return a late valid lease or commit a cancelled session. A timed-out worker and an old worker released after a newer cache commit both fail the cancellation/deadline/revision checks with no cache overwrite or late lease.
4. Correct workforce exchange options and approved API quota header for image/video submission and video polling; absent/malformed/conflicting metadata is refused without dispatch. Token and quota fields cannot independently drift. Workforce text/Chirp refuses dispatch under the first-slice boundary.
5. Deterministic stop/disconnect/completion races, including validation-only cache paths and a held network response released after disconnect. Zero publication when interruption wins.
6. External ADC is classified as unsupported for firm acceptance; replacing ambient credentials cannot repair or replace a failed workforce authorization. Legacy ADC remains a distinct mode with its existing behavior.
7. Exactly one submission for ambiguous response loss; zero resubmissions after denial, reauthentication or restart. Read-only retries retain the operation and binding.
8. Regression coverage for personal OAuth, service account and ADC readiness; Vertex text/Chirp shared-region behavior, deliberate saves and generation recycling; existing API-key providers and completed artifacts. Workforce text/Vertex-Chirp refusal occurs before credential resolution/child startup, with zero ambient ADC fallback; pending imports leave existing active text/Chirp working. Activation's stop-only retirement resolves no replacement credential; retirement failure preserves the committed session, reports restart required and blocks leases until verified recovery.
9. Synthetic secret-sentinel scans of store serialization, diagnostics, exceptions, leases, ledger and evidence. Verify DPAPI-protected storage and that no arbitrary credential executable or generic header forwarding is admitted.
10. **Check sign-in** success verifies only identity/exchange: all four model/billing/quota fields remain unverified. Assert zero model requests, no browser, held-response timeout/disconnect rejection and matching managed UI states; retain legacy readiness regression tests.

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

The user authorized incorporating this review and writing a plan. These decisions are now recorded for review of the revised spec and plan:

1. Approve Entra as the first adapter and the administrator-distributed, non-secret firm settings workflow.
2. The scoped Python MSAL exception is explicitly approved; verify pins, required dependency diff and packaged-runtime inclusion. This does not authorize broker extras or general dependency updates.
3. STS external ID-token exchange through the pinned Google SDK is selected, with mock wire evaluation recorded and an explicit deferred Cloud OAuth migration decision. Human/technical review must accept this contract before implementation; Cloud OAuth Preview remains unapproved. Live exchange is not yet verified.
4. Approve version-2 identity/project bindings and the deliberate reconnect/interruption policy, including version-1 compatibility and external ADC limitations.
5. Approve the separate automated/live acceptance criteria; live project, test identities and spend authorization are supplied privately later.
6. Confirm the image/video-only workforce boundary and explicit Vertex text/Chirp refusal; the audited JSON bootstrap cannot carry a live SDK supplier. Existing legacy and non-Vertex flows retain their behavior.

The user authorized preparing the accompanying `docs/superpowers/plans/2026-10-05-enterprise-google-workforce-federation.md` after these revisions. Review the revised spec and plan before implementation: contracts/consumers precede providers, commits remain buildable, identity/configuration/publication checkpoints inspect fresh evidence, and independent authentication review precedes installed live acceptance. These documents create no new OAuth application, permission grant, dependency installation or billed generation.

Implementation contract: the private Entra candidate carries the absolute post-browser operation deadline into Google exchange, activation and stop-only retirement. Consumers share this deadline rather than granting each phase a new 30-second window.
