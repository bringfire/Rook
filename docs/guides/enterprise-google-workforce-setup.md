# Microsoft 365 sign-in for Google media in Rook

Employees use their existing Entra work identities. The firm administers a Google Cloud organization, workforce identity pool and billed generation project. Each Rook installation connects locally; the firm owns its settings and billing. There is no central Rook billing proxy or markup in this implementation. Google's platform branding has changed, while the API endpoints and permissions still use `aiplatform`.

Workforce Identity Federation itself is a no-cost Google feature; detailed logging can incur Cloud Logging charges. Media API usage is charged separately. Existing Microsoft licensing and Conditional Access requirements remain the firm's responsibility. A Gemini/Workspace subscription does not replace this API billing setup. [Google federation costs](https://docs.cloud.google.com/iam/docs/workforce-sign-in-microsoft-entra-id), [media prices](https://cloud.google.com/vertex-ai/generative-ai/pricing).

## First pilot: gather administrators before employee setup

| Owner | Work |
|---|---|
| Entra administrator | Register a single-tenant public desktop application, approve employee access and validate sign-in policy |
| Google Cloud organization administrator | Create the workforce pool/provider and restrict its trusted issuer, audience and permitted identities |
| Cloud project/billing administrator | Enable API services, assign IAM, choose resource/user/quota projects and approve a generation budget |
| Employee | Import the administrator's settings, sign in through the normal browser and use RookVision |

The pool requires a Google Cloud **organization**. A standalone personal project alone is insufficient. The administrator performing setup needs the organization's Workforce Pool Admin permission; employees should not receive that administrative role. [Google setup prerequisites](https://docs.cloud.google.com/iam/docs/workforce-sign-in-microsoft-entra-id).

Keep actual tenant/client IDs, pool/project values, account identities, settings, screenshots and source evidence outside every repository/worktree. For this pilot, use a private directory under `%LOCALAPPDATA%/Rook/data/enterprise-google-pilot/`. Do not paste credentials or settings contents into chat. The example below is synthetic.

## Entra administrator

1. In Entra App registrations, create an application for **Accounts in this organizational directory only**. Record its directory tenant ID and application client ID privately.
2. In Authentication, add **Mobile and desktop applications**, using `http://localhost` for the system browser. Rook binds an ephemeral loopback port. Configure the app as a public client following Microsoft's desktop instructions. This Rook flow uses MSAL authorization code with PKCE and `form_post`; do not replace it with a confidential web app or distribute a client secret. [Desktop configuration](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration).
3. Approve the intended employees/application under the firm's normal enterprise-app policies. Effective OIDC scopes are `openid profile offline_access`. MSAL handles these reserved scopes internally, so Rook passes an empty application-scope list. No Graph permission is requested. Identity binds to verified `tid` and `oid`, never an email address; Microsoft requires `profile` for `oid`. [Claim reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).
4. If access will use groups, configure the relevant **ID-token** group claims and limit the pilot to known assigned groups. Group overage must be resolved administratively; Rook does not fetch missing groups from Graph.

Rook currently uses browser MSAL without WAM/broker packages. Policies requiring broker/device claims may deny this flow. Ask the administrator to assess compatibility; do not weaken Conditional Access to pass the pilot. Broker support would need separate approval and implementation. [Microsoft broker guidance](https://learn.microsoft.com/en-us/entra/msal/python/advanced/wam).

## Google Cloud administrator

1. Create a workforce identity pool at organization/global scope and an OIDC provider. Trust the exact issuer `https://login.microsoftonline.com/<TENANT-ID>/v2.0`; set the provider's OIDC client ID to the **same Entra desktop application client ID**. Its ID-token audience must match. Rook receives the Entra assertion directly, then exchanges it at `https://sts.googleapis.com/v1/token` using pinned Google auth. No Google client secret or service-account impersonation is used. Cloud OAuth migration is a separate future decision. [Provider contract](https://docs.cloud.google.com/iam/docs/reference/rest/v1/locations.workforcePools.providers), [assertion exchange](https://docs.cloud.google.com/iam/docs/workforce-obtaining-short-lived-credentials).
2. Map `google.subject=assertion.oid`. Optionally map emitted `google.groups=assertion.groups`; restrict acceptance to the intended tenant and identities/groups. Google console/gcloud web SSO is a separate provider configuration: its web redirect/secret examples do not change Rook's public desktop/STS flow. Review the provider's web SSO options with the administrator if console access is also needed. [Entra mapping guide](https://docs.cloud.google.com/iam/docs/workforce-sign-in-microsoft-entra-id).
3. Grant project permissions to specific workforce subjects or the intended group principal set. Avoid granting every member of the pool access. Verify applicable service support, model availability and organizational restrictions for the actual pilot.

| Rook setting | Meaning |
|---|---|
| `project_id` | Resource project in image/video request URLs; enable billing and `aiplatform.googleapis.com`, with appropriate `roles/aiplatform.user` or reviewed restricted equivalent |
| `workforce_pool_user_project` | Project supplied as STS `options.userProject`; federated users require `serviceusage.services.use`, ordinarily `roles/serviceusage.serviceUsageConsumer` |
| `quota_project_id` | Optional API consumer project supplied as `x-goog-user-project`; requires relevant service-use permission and API/billing setup |

These roles can point to one approved project or distinct projects. Do not guess billing attribution from their names: verify private audit/billing evidence after the pilot. Ensure required IAM and STS services are enabled. [STS prerequisite permissions](https://docs.cloud.google.com/iam/docs/workforce-obtaining-short-lived-credentials), [generation project setup](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start).

## Administrator-provided settings

Supply exactly these fields, with no credentials, scripts or configurable URLs. `organization_id` is numeric text; generation uses a project ID. The two consumer-project fields accept the approved project ID or number, with quota optionally null.

```json
{
  "schema_version": 2,
  "label": "Synthetic firm",
  "entra_tenant_id": "11111111-1111-1111-1111-111111111111",
  "entra_client_id": "22222222-2222-2222-2222-222222222222",
  "organization_id": "123456789",
  "pool_id": "synthetic-pool",
  "provider_id": "synthetic-provider",
  "project_id": "synthetic-firm-project",
  "workforce_pool_user_project": "synthetic-firm-project",
  "quota_project_id": "synthetic-firm-project",
  "region": "us-central1",
  "exchange": "sts_id_token_v1"
}
```

## Employee workflow

1. Open RookChat Settings → Enterprise Google → **Firm sign-in (Microsoft 365)**. Read local firm settings.
2. Import the settings file by absolute local path. Imported settings are **pending**. Existing authorization/jobs stay bound to the prior active connection. Discard removes only pending settings.
3. Read the media-only disclosure, then choose **Sign in with your firm**. Complete normal Microsoft login. Only successful verified identity plus Google exchange atomically activates the pending settings. Failed/cancelled sign-in preserves the old connection.
4. Activation interrupts old bound media jobs and retires an owned Vertex Chirp process. Firm authorization currently supports **images/video only**; Vertex text and Vertex Chirp refuse it explicitly. Other providers keep their existing behavior.
5. If retirement reports **Restart required**, close the old Rook/Rhino processes normally, restart and use **Check sign-in** for verified stop-only recovery. Media leases remain blocked until retirement succeeds. Passive reads never clear this flag.
6. **Check sign-in** forces Entra refresh and STS exchange only. Even success leaves image/video access, billing and quota **unverified**. Use separate approved live media tests to establish them.
7. To reconnect, choose **Prepare reconnect with active settings**, then sign in against that displayed pending revision. To change active project/location/quota, reimport settings and sign in deliberately. A new activation rotates the binding even for the same employee.

Tokens/assertions stay in Python. The MSAL cache and identity are DPAPI-protected under the Windows user; the media ledger holds only opaque binding metadata. No personal data is sent through a Rook-owned server.

Disconnect clears active and pending authorization and invalidates late callbacks. Stop/disconnect/restart do not remotely cancel a previously submitted Google operation; it may finish and be billed. Interrupted jobs never automatically resume or resubmit under another identity/project. Already completed artifacts remain accessible locally. IAM/provider revocation propagation is observed, not promised immediate.

## Installed acceptance and private evidence

First finish fresh builds, automated races, packaged dependency qualification and independent authentication review. Then obtain administrator setup, two permitted identities and **explicit spend approval** for one image and three short videos. Test image dimensions; video completion with real Entra/STS refresh during polling; active disconnect; active restart; playback, duration/dimensions, three decoded frames and hashes. Identity switching uses a local controlled binding check rather than another billed job.

Image: `vertex_ai/gemini-3.1-flash-image`, `global`. Video: `vertex_ai/veo-3.1-fast-generate-001`, `us-central1`. A missed intervention is **inconclusive**; there is no automatic fourth video or retry after an ambiguous submit.

`scripts/vertex_media_acceptance.py --mode live` validates operator evidence and makes no Google requests. Its workforce section uses contract version 2, exact adapter/runtime pins, opaque employee/project labels, lifecycle results, separate real Entra/STS counts and resource/user/quota attribution statuses. Existing `oauth_consent_observed` denotes the observed OAuth/OIDC browser consent for the selected adapter, not an assertion that a Google consumer account was used. All original artifact/request/gate requirements remain.

Workforce completion evidence also requires `generation_context`, with the completion case's `operation_label` and `binding_label`, the first `principal_labels` entry as `principal_label`, provenance `account_label`/`project_label`, and the resource/workforce-user/quota project labels. In `poll_refresh.events`, record ordered `entra_refresh`, `sts_exchange`, `poll` triples. Each event contains that identical context, its UTC timestamp and `source_evidence_sha256` for the private source record. Every counted refresh must have a corresponding exchange and later poll on the same operation and authorization. The first exchange/poll timestamps must match the completion case's refresh evidence; all events occur after lease invalidation and before completion. Counts without these correlated records cannot qualify. These remain operator evidence, with private mappings and source records kept outside Git.

An invalid or exceeded submission budget is **failed**, even when installed verification or spend approval is missing; the live validator exits nonzero. Missing prerequisites never erase observed extra submissions or authorize a retry.

Keep raw evidence and its identifier-to-label mapping privately outside Git. Locally scan summaries against held private values without printing them. If billing reports are not yet available, record attribution **pending**. Mock evidence, sign-in checking, a development interpreter or an unavailable live prerequisite cannot qualify installed generation.
