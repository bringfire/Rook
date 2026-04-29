# Multi-Provider Phase 2 — fal.ai First Provider Plan

**Date:** 2026-04-29
**Status:** PR-5 planning draft; doc-only
**Scope:** fal.ai as the first concrete non-Google provider, with provider-agnostic pressure checks against Replicate, Gemini/Veo, and Tencent.
**Predecessors:**
- [`2026-04-26-generation-provider-framework.md`](2026-04-26-generation-provider-framework.md) — strategic frame and phased rollout.
- [`2026-04-27-multi-provider-spike.md`](2026-04-27-multi-provider-spike.md) — Phase 0 evidence and six contract decisions.
- [`2026-04-27-multi-provider-phase1-plan.md`](2026-04-27-multi-provider-phase1-plan.md) — generic generation seam, image/video retrofit, keyed secret store.
- [`2026-04-28-multi-provider-phase1-pr4-status.md`](2026-04-28-multi-provider-phase1-pr4-status.md) — PR-4 status and deferred secret/status metadata decision.
- [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) — current video job contract and native/managed boundary.

---

## TL;DR

PR-5 is a **doc-only planning PR**. It does not add production provider classes, routes, UI, catalog entries, or settings changes.

Phase 2 starts with fal.ai because Phase 0 has live evidence for both fal sync image and fal queue video. The implementation plan deliberately keeps fal as the first concrete provider, not the hidden framework contract. Every fal-specific choice below is pressure-checked against Replicate, Gemini/Veo, and Tencent when that choice affects shared seams.

The intended implementation sequence after PR-5:

1. **PR-6 — fal substrate:** `FalApiClient`, fal lifecycle/result/error/pricing helpers, secret metadata substrate, fake-provider tests, no user-visible models.
2. **PR-7 — fal image:** first fal sync image models end-to-end, artifact materialization, static catalog registration, live smoke gated by env var.
3. **PR-8 — fal video:** fal queue video models through the existing video job contract, ledger handle metadata, status/fetch/cancel, live smoke gated by env var.
4. **PR-9 — settings/picker:** fal key UI, provider badges, missing/invalid key availability states, picker filtering/disablement.

Replicate, 3D, dynamic catalog discovery, and Tencent direct remain explicitly deferred.

---

## 1. Phase 2 Goals And Non-Goals

### Goals

- Add fal.ai as the first aggregator-backed generation provider for image and video.
- Preserve the Phase 1 generic generation seam rather than introducing fal-specific shortcuts.
- Resolve the PR-4 deferred `RequiredSecretKeys` / `SecretStatus` decision with the smallest durable contract needed by fal and future providers.
- Keep existing Gemini image and Veo video behavior compatible.
- Keep all 3D-shaped names and result semantics out of Phase 2 production code.
- Establish live-smoke gates that prove real fal behavior without making normal tests spend money.

### Non-goals

- No Replicate provider implementation.
- No Tencent provider implementation.
- No 3D provider, 3D registry, 3D route, or 3D artifact role.
- No dynamic model catalog.
- No webhook or streaming result delivery.
- No public native HTTP route changes unless a later implementation PR explicitly adds user-visible model discovery parity.
- No change to the existing `/vision/video/*` job contract shape unless required by a provider-agnostic bug fix.

---

## 2. Phase 0 Contract Invariants

Reviewers should use this as the checklist for every implementation PR in Phase 2.

| Invariant | Phase 0 binding | Phase 2 consequence |
|---|---|---|
| Lifecycle | Sync and async providers must be discriminated at submit time. fal queue `COMPLETED` is terminal, not proof of success; success/failure is determined at fetch. Replicate terminal poll embeds output; Gemini sync returns inline result; Veo async returns provider operation state. | Provider code must use `SyncSubmitOutcome` vs `QueuedSubmitOutcome`. Queue status parsing cannot mark a Rook job complete until fetch/materialization succeeds. |
| Capability schema | Image and video need per-route capability flags, not flat provider booleans. 3D evidence is captured but not bound in Phase 2. | Fal model descriptors must declare sub-capabilities such as `text_to_image`, `image_to_image`, `text_to_video`, `image_to_video`. No 3D sub-capabilities in production Phase 2 code. |
| Pricing | No shared pricing formula exists. fal alone uses different meanings for `x-fal-billable-units` by model class. Replicate reports body metrics; Gemini reports usage metadata. | Pricing models are per provider and often per model. Actual-spend extraction is owned by the concrete pricing model, not by a shared header parser. |
| Options codec | Submission bodies vary by provider and route. fal field names differ by model; Replicate has official vs community endpoint shapes; Gemini uses content parts; Tencent is SDK-mediated. | Fal options codecs may be per model family. Shared options types must not assume fal's flat JSON body shape. |
| Result/artifact shape | URL-referenced artifacts and inline-byte artifacts are both first-class. Error envelopes are distinct from result envelopes. 3D multi-format output is deferred. | Fal URL artifacts must materialize into `ArtifactStore` before returning Rook artifact IDs. Result parsing must distinguish HTTP success/failure and body shape. |
| Secret namespace | Providers require different auth header conventions. Tencent requires paired credentials. | Secret metadata must support one or more secret keys per provider, with configured/missing/invalid status and future paired-key support. |

---

## 3. Fal Provider Architecture

Fal should enter the tree as a provider family, not as one monolithic class.

Proposed production layout:

```text
src/Rook/Services/Vision/Fal/
  FalApiClient.cs
  FalAuth.cs
  FalErrorMapper.cs
  FalHttpResponse.cs
  FalLifecycleMapper.cs
  FalResultParser.cs
  FalSecretKeys.cs

src/Rook/Services/Vision/Fal/Image/
  FalImageProvider.cs
  FalImageProviderRegistration.cs
  FalImageCapabilities.cs
  FalImageOptions.cs
  FalImageOptionsCodec.cs
  FalImagePricingModels.cs

src/Rook/Services/Vision/Fal/Video/
  FalVideoProvider.cs
  FalVideoProviderRegistration.cs
  FalVideoCapabilities.cs
  FalVideoOptions.cs
  FalVideoOptionsCodec.cs
  FalVideoPricingModels.cs
```

`FalApiClient` owns HTTP mechanics only: base URLs, auth header, request dispatch, queue polling, response fetch, cancellation dispatch, response-header capture. It does not know about Rook artifacts, image/video registries, or UI.

`FalImageProvider` and `FalVideoProvider` adapt the shared fal client into `IImageProvider` and `IVideoProvider`. They own model-family request body construction and result envelope parsing. Artifact writes stay in the existing materializing managers/handlers, not inside provider classes.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Shared `FalApiClient` plus modality-specific providers | Replicate also wants shared HTTP substrate plus image/video providers, but prediction endpoint variants differ. | Gemini image and Veo video remain direct provider classes, not aggregator clients. | Tencent likely uses SDK clients, not shared raw HTTP. | Keep shared client optional behind provider implementation; do not add `IAggregatorClient` yet. | Replicate client design in Phase 3; Tencent SDK client in Phase 4. |
| Provider classes never write artifacts | Replicate URL outputs need the same manager-owned materialization. | Gemini inline bytes and Veo mp4 fetch also materialize outside provider identity. | Tencent outputs should be materialized by managers too. | Providers return `ProviderResultEnvelope`; managers/handlers write `ArtifactStore`. | A reusable materializer may be promoted when fal + Replicate both need URL fetch logic. |

---

## 4. Provider-Agnostic Pressure Checks

This section records cross-cutting decisions that apply across later detailed sections.

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Use fal queue URLs directly in `ProviderJobHandle` (`StatusUrl`, `ResponseUrl`, `CancelUrl`, method) | Replicate has `urls.get` and `urls.cancel`, but terminal poll embeds output and `ResponseUrl` is null. | Veo handle starts with provider job id only and stamps result token later. | SDK-mediated providers may have no URLs. | `ProviderJobHandle` remains optional-field based; no fal-only required URL fields. | Add provider-metadata serialization tests for populated handle extensions in PR-6/PR-8. |
| Parse fal uppercase states through `GenerationLifecycleStateNormalizer` | Replicate lowercase states must map through the same normalizer. | Veo status adapters already map into canonical states. | Tencent typed statuses can map through normalizer or explicit adapter. | No provider compares raw state names outside its adapter. | Extend normalizer only with observed provider terms. |
| Treat fal fetch failure after terminal queue state as provider result failure | Replicate can fail at terminal poll without a separate fetch. | Gemini sync failure may be `SyncSubmitOutcome(FailedResultOutcome)`. Veo status failure is `FailedStatusOutcome`. | Tencent Query may return terminal job failure. | Rook job completion is success only after result envelope materializes; terminal provider state alone is insufficient. | None for Phase 2. |

---

## 5. Secret/Status Metadata Decision

PR-4 deliberately deferred `IProviderRegistration.RequiredSecretKeys` and `SecretStatus`. Phase 2 should resolve the minimum durable shape before user-visible providers multiply.

### Decision

Add a provider-secret metadata seam in PR-6. The shape deliberately splits
**presence** from **validation** so "a key exists" never gets confused with
"a live provider accepted it."

```csharp
public sealed class ProviderSecretRequirement
{
    public ProviderSecretRequirement(
        string key,
        string displayName,
        bool isRequired,
        bool isSensitive = true)
    {
        Key = key;
        DisplayName = displayName;
        IsRequired = isRequired;
        IsSensitive = isSensitive;
    }

    public string Key { get; }
    public string DisplayName { get; }
    public bool IsRequired { get; }
    public bool IsSensitive { get; }
}

public enum ProviderSecretPresence
{
    Missing = 0,
    Present = 1,
}

public enum ProviderSecretValidationState
{
    NotAttempted = 0,
    Valid = 1,
    Invalid = 2,
    Inconclusive = 3,
}

public sealed class ProviderSecretStatus
{
    public ProviderSecretStatus(
        ProviderSecretRequirement requirement,
        ProviderSecretPresence presence,
        ProviderSecretValidationState validationState,
        string? preview,
        string? message)
    {
        Requirement = requirement;
        Presence = presence;
        ValidationState = validationState;
        Preview = preview;
        Message = message;
    }

    public ProviderSecretRequirement Requirement { get; }
    public ProviderSecretPresence Presence { get; }
    public ProviderSecretValidationState ValidationState { get; }
    public string? Preview { get; }
    public string? Message { get; }
}

public enum ProviderCredentialAvailability
{
    MissingRequiredSecret = 0,
    InvalidCredential = 1,
    Available = 2,
    AvailableButUnverified = 3,
    AvailableWithInconclusiveValidation = 4,
}

public sealed class ProviderCredentialStatus
{
    public ProviderCredentialStatus(
        string providerName,
        ProviderCredentialAvailability availability,
        IReadOnlyList<ProviderSecretStatus> secrets,
        string? message)
    {
        ProviderName = providerName;
        Availability = availability;
        Secrets = secrets;
        Message = message;
    }

    public string ProviderName { get; }
    public ProviderCredentialAvailability Availability { get; }
    public IReadOnlyList<ProviderSecretStatus> Secrets { get; }
    public string? Message { get; }
}
```

Provider registrations should expose:

```csharp
IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
```

Registry or composition code computes per-requirement `ProviderSecretStatus`
from `IGenerationSecretStore`, then aggregates those rows into
`ProviderCredentialStatus`. This computation must be metadata-only unless
explicitly running a test-key operation; settings overview must not decrypt
legacy Gemini ciphertext just to render.

Aggregation is provider-level and deterministic:

- If any required secret has `Presence = Missing`, availability is
  `MissingRequiredSecret`.
- Else if any required secret has `ValidationState = Invalid`, availability is
  `InvalidCredential`.
- Else if any required secret has `ValidationState = Inconclusive`,
  availability is `AvailableWithInconclusiveValidation`.
- Else if every required secret has `ValidationState = Valid`, availability is
  `Available`.
- Else availability is `AvailableButUnverified` because all required key
  material exists but no conclusive live validation result is attached.

Optional missing secrets never block provider availability. Optional
`Invalid` or `Inconclusive` secrets are shown per-key and do not change provider
availability in Phase 2. Operation- or model-scoped credential overlays are
deferred to a later descriptor contract; Phase 2's `SecretRequirements` is a
static provider-registration property.

### Status Semantics

- `Presence = Missing`: no local value exists for this key.
- `Presence = Present`: local key material exists. This says nothing about
  provider acceptance.
- `ValidationState = NotAttempted`: no live test-key operation has been run for
  the current UI/request context.
- `ValidationState = Valid`: a provider-specific test-key operation succeeded
  for the current UI/request context.
- `ValidationState = Invalid`: a provider-specific test-key operation failed
  with an auth-shaped error for the current UI/request context.
- `ValidationState = Inconclusive`: a provider-specific test-key operation ran
  but could not prove validity. Fal catalog/list endpoints may be public or
  redirect without validating credentials, so "present but unproven" must not be
  mislabeled valid.

`Invalid` is **not persisted in the encrypted secret store** in Phase 2. It is
a transient result returned by a test-key operation and may be cached in memory
by the Settings/picker surface for the lifetime of that panel/session. It must
clear when any participating secret changes or when the panel is reopened with
no validation cache. This avoids stale invalid state silently disabling a fixed
credential after the user edits settings outside the current UI flow.

Picker availability should block or mark models only for
`MissingRequiredSecret`. `InvalidCredential` should show a stronger warning in
the current UI session after a failed test-key operation, but submit remains the
authoritative backstop and returns typed dependency errors. The two
"available but not proven valid" states do not block submit, because first paid
call may be the only reliable validation for some providers.

### Required Secret Keys

Initial production keys:

```csharp
public static class GenerationSecretKeys
{
    public const string GeminiApiKey = "gemini.api_key";
    public const string FalApiKey = "fal.api_key";
    public const string ReplicateApiToken = "replicate.api_token";
    public const string TencentSecretId = "tencent.secret_id";
    public const string TencentSecretKey = "tencent.secret_key";
    public const string TencentStsToken = "tencent.sts_token";
}
```

Only `GeminiApiKey` and `FalApiKey` are consumed in Phase 2. Replicate and Tencent constants may be introduced with the metadata contract if doing so keeps tests concrete, but no provider implementation consumes them until later phases.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| `fal.api_key` is a single required secret | Replicate is also a single token but uses a different auth header. | Gemini/Veo use the existing Google key slot today. Missing-key error parity must remain. | Tencent needs paired required keys plus optional STS token. | Requirements are a list, not one `ApiKey` property. Header construction remains provider-owned. | Replicate/Tencent test-key implementations. |
| Presence and validation are separate fields | Replicate auth can be proven by `/v1/models`, but a present token is not automatically valid. | Gemini model listing can prove API key access; Veo may fail only at submit depending API access. | Tencent SDK credential validation may require a signed lightweight API call across a paired secret set. | Settings UI can say "configured, not yet validated" without blocking picker availability. | Provider-specific test endpoints and UX text in PR-9+. |
| Provider-level aggregation owns picker availability | Replicate can aggregate one token; later providers may have several keys. | Existing Gemini/Veo submit-time missing-key behavior remains the backstop. | Paired-key providers disable if either required key is missing. | PR-9 consumes `ProviderCredentialStatus`, not ad hoc per-key scans. | Full picker filtering in PR-9. |
| `Invalid` is transient test-key state, not persisted secret metadata | Replicate can report invalid token from a lightweight call; the UI can cache it for the panel session. | Gemini/Veo invalid state should not permanently poison a corrected key. | Tencent paired-key invalidity may apply to the pair, not one field. | Submit remains authoritative; changing any participating secret clears cached validation state. | Durable validation-cache storage is deferred until there is evidence it is needed. |

---

## 6. Static Catalog Model Choices

Phase 2 should use a hardcoded fal baseline catalog. Dynamic discovery remains Phase 5.

Initial catalog should be deliberately small:

| Model class | Candidate | Reason | Phase |
|---|---|---|---|
| Sync image | `fal-ai/flux/schnell` | Phase 0 live evidence exists; cheap; text-to-image baseline. | PR-7 |
| Higher-quality image | one FLUX Pro/Dev or SDXL-family model after catalog confirmation | Useful user-visible upgrade from Gemini-only image generation. | PR-7 or PR-9 depending scope |
| Queue video | `fal-ai/wan/v2.7/text-to-video` | Phase 0 live evidence exists; exercises queue lifecycle and separate fetch. | PR-8 |
| Image-to-video | one fal I2V model after current catalog confirmation | Exercises media input and video capability filtering. | PR-8 or deferred |

Before PR-7/PR-8 code starts, re-check fal current catalog pages and pricing for chosen model IDs. Model availability is temporally unstable; do not rely only on the 2026-04-27 spike captures.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Hardcode a small fal catalog | Replicate can also start with hardcoded official models. | Gemini/Veo already use static capability tables. | Tencent direct will likely require endpoint-specific static descriptors first. | Static descriptor pattern remains valid; no dynamic catalog source in Phase 2. | Dynamic catalog discovery Phase 5. |
| Re-check model IDs/pricing before coding | Replicate model names and versions also drift. | Google model preview IDs can rename. | Tencent endpoint availability can differ by account/region. | Catalog entries must carry provenance strings and tests pin descriptor shape, not external availability. | Provider health/catalog refresh UX later. |

---

## 7. Image Implementation Path

PR-7 should add fal image support after PR-6 substrate lands.

Expected behavior:

- `FalImageProvider` implements `IImageProvider`.
- Sync fal image submit returns `SyncSubmitOutcome(SuccessResultOutcome(...))`.
- Fal image artifacts are URL-referenced via `RemoteArtifactBody`.
- The image handler/materializer fetches URLs, records materialized MIME, writes artifacts, and returns the existing image generation response shape unless a deliberate route contract change is planned.
- Missing fal key returns `GenerationErrorCode.DependencyUnavailable`.
- Existing Gemini image paths remain unchanged.

No image-specific implementation should assume every image provider is sync. Fal sync image is sync; future Replicate image may be async prediction-shaped.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Start with fal sync image | Replicate image is async prediction-shaped even for fast models. | Gemini image is sync inline bytes. | Tencent image/3D endpoints may be async SDK jobs. | Image handler must dispatch based on `ProviderSubmitOutcome`, not assume image equals sync. | Async image manager extraction if Replicate image requires long-lived jobs. |
| Fal image returns remote URL artifacts | Replicate also returns URL outputs. | Gemini returns inline bytes. | Tencent may return URLs or SDK-managed file fields. | Materializer handles both `RemoteArtifactBody` and `InlineArtifactBody`. | Shared URL materializer promotion after second URL provider. |
| Preserve existing image route response | Replicate should reuse same artifact response once materialized. | Gemini UI/tests depend on existing shape. | Tencent not in image route scope. | Provider expansion should be behavior-compatible at route envelope level. | New model-picker fields in PR-9 may extend descriptors only. |

---

## 8. Video Implementation Path

PR-8 should add fal video support after fal substrate and image URL materialization patterns are proven.

Expected behavior:

- `FalVideoProvider` implements `IVideoProvider`.
- Submit returns `QueuedSubmitOutcome` with `ProviderJobHandle` populated from fal queue response.
- Status maps fal queue state through `GenerationLifecycleStateNormalizer`.
- Provider-complete means "ready to fetch", not "Rook job complete".
- Fetch parses fal `video` result envelope and returns a `RemoteArtifactBody`.
- Cancel uses fal `cancel_url` and its provider-supported method.
- `VideoJobLedger` persists non-null provider handle URL/method/metadata fields without changing Veo byte-identity fixtures.

The existing `/vision/video/jobs`, `/status`, `/cancel`, `/result`, and `/estimate` public contract remains the consumer-facing contract.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Fal queue result fetched from `ResponseUrl` | Replicate terminal poll embeds `output`; `ResponseUrl` is null. | Veo fetch uses result token/video URI. | Tencent Query result may include SDK fields. | `FetchResultAsync` receives the full handle and provider decides where result lives. | Replicate fetch-from-token implementation Phase 3. |
| Fal status `COMPLETED` transitions to provider-complete | Replicate `succeeded` can also be provider-complete but output may already be present. | Veo operation done also requires download/materialization. | Tencent terminal success still needs materialization. | Manager state machine keeps provider terminal separate from Rook complete. | None. |
| Fal cancel method comes from handle | Replicate uses POST. | Veo cancellation is provider API-specific. | Tencent cancellation may be SDK-mediated. | Cancel logic is provider-owned; generic handle only stores available hints. | Live cancellation characterization remains a follow-up unless scoped into PR-8. |

---

## 9. Artifact Materialization

Fal introduces the first production non-Google URL-artifact path for both image and video.

Materialization rules:

- `InlineArtifactBody` writes bytes directly and requires a known MIME type.
- `RemoteArtifactBody` must be fetched before Rook returns an artifact id.
- If `DeclaredMimeType` is present, preserve it as provider-declared metadata.
- If `DeclaredMimeType` is absent or generic, infer materialized MIME from `Content-Type`, then magic bytes where available.
- Signed provider URLs must not be exposed as durable Rook artifacts. Store provider URL only in provider metadata if useful for audit, and only after redaction/TTL judgment.
- Artifact writes remain atomic through `ArtifactStore`.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Fetch remote URL before returning artifact id | Replicate output URLs need the same. | Gemini inline bytes do not fetch; Veo already downloads video bytes. | Tencent may return URLs with different TTLs. | Rook artifact identity always points to local materialized bytes. | URL retry/backoff policy can be refined after Replicate. |
| Preserve declared and materialized MIME separately | Replicate may not declare MIME. | Gemini declares MIME inline; Veo/fal video usually declare content type. | Tencent file descriptors may declare format. | Artifact metadata should distinguish provider claim from local observation. | Metadata field naming finalized in PR-7/PR-8. |

---

## 10. Pricing Estimates And Actual-Spend Capture

Fal pricing must not be modeled as one universal header formula.

Plan:

- Add fal pricing models per model class:
  - per-megapixel image pricing for FLUX schnell-like models;
  - per-output-second video pricing with resolution/tier multiplier;
  - flat per-call or add-on pricing only when a Phase 4 3D provider is actually scoped.
- Keep `CostEstimate` provenance explicit, e.g. `fal-flux-schnell-per-mp-2026-04-29`.
- Add `ExtractActualSpend` support for fal response headers, but route interpretation through the model's pricing model.
- Record actual spend in job/artifact metadata only when provider evidence is present and interpretable.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Interpret `x-fal-billable-units` inside model pricing | Replicate actuals come from body metrics, not headers. | Gemini uses usage metadata; Veo estimate is per second. | Tencent pricing may be SDK/body/account dependent. | `ExtractActualSpend` remains on `IPricingModel`; no shared fal-header shortcut. | Replicate compute-second pricing Phase 3. |
| Use provenance strings with dates | Replicate/Gemini/Tencent pricing can drift too. | Existing Veo pricing already uses provenance-like source strings. | Tencent public pricing varies by product tier. | Tests assert provenance exists, not that external prices are eternally current. | Pricing refresh process later. |

---

## 11. Error Mapping And Retryability

Fal error mapping must preserve provider detail without leaking raw provider envelopes into public route contracts.

Required mappings:

- Validation/body-shape errors before compute: `InvalidRequest`, non-retryable, field populated when known.
- Auth failure: `DependencyUnavailable`, non-retryable, provider code/detail preserved.
- Quota/billing limit: `QuotaExceeded`, retryability depends provider detail.
- Queue/provider temporary failure: `DependencyUnavailable`, retryable when fal signals retry.
- Content-policy/NSFW rejection: `ContentPolicy` or `ExecutionFailed` depending fal body shape; prefer `ContentPolicy` when explicit.
- Fetch error after terminal queue state: `FailedResultOutcome`, not `FailedSubmitOutcome`.
- User cancellation: `Cancelled`.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Preserve FastAPI `detail` in `ProviderDetail` | Replicate has its own error fields. | Gemini and Veo have Google error shapes. | Tencent SDK errors have typed codes/messages. | `GenerationError.ProviderDetail` stays JsonNode bag, not fal-specific DTO. | Provider-specific debug rendering later. |
| Split pre-meter submit failure from post-meter result failure | Replicate and Gemini have same distinction in different shapes. | Veo status failures are post-submit. | Tencent Query failures are likely post-submit. | Error timing determines no-cost vs charged-failure ledger semantics. | Actual billing semantics per provider remain observed, not assumed. |

---

## 12. UI/Settings/Picker Scope

User-visible UI changes should wait until provider substrate and first fal model behavior are pinned. PR-9 is the earliest planned UI/settings/picker PR.

Expected UI behavior:

- Settings gains fal.ai key entry and test action.
- Existing Gemini key preview/persistence behavior remains.
- Model picker shows provider as metadata, not as the dominant model identity.
- Missing-key models are visible but disabled or marked "configure key".
- Invalid-key state is visible after failed test-key operation.
- `AvailableButUnverified` and `AvailableWithInconclusiveValidation` states
  are allowed and do not block submit.

No UI PR should introduce Replicate/Tencent settings controls before provider support exists, except possibly hidden/test-only metadata fixtures.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Add fal settings once fal models are registerable | Replicate settings can follow same metadata seam. | Gemini settings must continue reading legacy/migrated key preview. | Tencent needs paired inputs and optional STS token. | Settings UI renders secret requirements from provider metadata where possible. | Paired credential UI in Phase 4. |
| Show provider badges in picker | Replicate will add another provider badge. | Gemini/Veo badges prevent Google direct models from looking special-cased. | Tencent direct badge later. | Picker model descriptors need provider name and capability metadata. | Ranking/recommendation UX later. |

---

## 13. Native/Managed Boundary

Phase 2 fal implementation is managed vision/provider work by default.

The current architecture remains:

- `RookNative` is the public HTTP surface.
- Managed companion owns provider clients, image/video handlers, job manager, and artifact materialization.
- Existing native video routes forward through `vision_dispatch`.
- Existing image and artifact routes remain as wired.

PR-5 plans no native C++ edits. PR-6 through PR-8 should not touch `src/RookNative` unless they add or extend public route parity. If a route parity change becomes necessary, it must be scoped as its own PR section with native and managed changes kept consistent.

### Pressure Check

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
|---|---|---|---|---|---|
| Keep fal provider code managed-only | Replicate provider code should also be managed-only. | Existing Gemini/Veo providers are managed. Native only proxies route calls. | Tencent SDK integration is likely managed or Python-mediated, not native. | No public-surface drift as a side effect of adding providers. | New discovery routes, if needed, get separate native/managed parity PR. |

---

## 14. PR Slicing

### PR-5 — Plan only

Files:

- Add this doc.
- Optional: update work queue with the accepted Phase 2 sequence.

Verification:

- Placeholder-marker scan should show no unresolved markers in the plan body.
- `git diff --name-only` should show docs only.

### PR-6 — fal substrate and secret metadata

Scope:

- Add fal shared client, lifecycle parser, result parser skeleton, error mapper, pricing scaffolding.
- Add provider secret requirement/status metadata.
- Add tests against Phase 0-shaped fal queue and sync fixtures.
- No registered user-visible fal models.

Acceptance:

- No UI route changes.
- Existing Gemini/Veo tests pass.
- Secret/status metadata supports single-key fal and paired-key Tencent fixture without Tencent provider implementation.

### PR-7 — fal image

Scope:

- Register first fal sync image model(s).
- Implement fal image options codec and pricing.
- Materialize URL image results to `ArtifactStore`.
- Live smoke gated behind env var.

Acceptance:

- Existing Gemini image behavior remains compatible.
- Fal image can generate with configured key.
- Missing fal key gives typed dependency error and picker metadata marks model unavailable once PR-9 lands.

### PR-8 — fal video

Scope:

- Register first fal queue video model(s).
- Implement fal video options codec and pricing.
- Wire provider handle URL fields through `VideoJobLedger`.
- Fetch remote mp4 and write existing video artifact shape.
- Live smoke gated behind env var.

Acceptance:

- Existing Veo byte-identity fixtures still pass.
- Fal queue terminal/fetch failure path is pinned.
- Cancel path is tested with fake provider; live cancellation remains optional unless explicitly budgeted.

### PR-9 — settings/picker UX

Scope:

- Render provider secret requirements in Settings.
- Add fal key set/test/clear path.
- Extend model descriptors for provider badge, missing/invalid/unverified/inconclusive availability state, capability filtering.
- Keep provider identity secondary to model identity in UI.

Acceptance:

- Gemini settings overview continues to work with legacy migrated keys.
- Missing fal key disables or annotates fal models without hiding the model catalog.
- Test-key invalid state is visible and recoverable.

---

## 15. Test And Live-Smoke Gates

### Unit and integration tests

- Generation seam tests continue to pass:
  - union closure;
  - invariant bypass;
  - symbol scan excluding 3D-shaped names;
  - Phase 0 fixture fakes.
- Fal substrate tests use captured shapes from:
  - `docs/rook_docs/artifacts/2026-04-27-multi-provider-spike/p1_sync/`;
  - `docs/rook_docs/artifacts/2026-04-27-multi-provider-spike/p1_queue/`;
  - `docs/rook_docs/artifacts/2026-04-27-multi-provider-spike/p2/`.
- Secret/status tests cover:
  - configured/missing single key;
  - invalid state from a fake test-key provider;
  - `AvailableButUnverified` state when no test-key operation has run;
  - `AvailableWithInconclusiveValidation` state from a fake inconclusive validator;
  - paired-key requirement where one Tencent key is missing.
- Video tests cover:
  - populated `ProviderJobHandle` URL/method metadata round-trip;
  - queue terminal but fetch failure;
  - Veo unchanged behavior.

### Live smoke

Live fal tests must be opt-in through environment variables and skipped by default. They should use synthetic prompts and low-cost models only.

Required before a fal implementation PR is merged:

- Confirm current fal model ID and pricing from official/current source.
- Run one live fal image smoke for PR-7 if a key is available and user approves spend.
- Run one live fal video smoke for PR-8 if a key is available and user approves spend.
- Record provider request IDs only in redacted/safe test output or PR notes.

Do not run live paid tests silently.

---

## 16. Explicit Deferrals

- **Replicate:** Phase 3. Pressure checks only in this doc.
- **3D:** Phase 4. No 3D provider or 3D artifact semantics in Phase 2.
- **Tencent direct:** Phase 4. Secret metadata must support paired keys, but no SDK integration in Phase 2.
- **Dynamic catalog:** Phase 5. Phase 2 uses static catalog descriptors.
- **Webhook/streaming:** deferred until a provider implementation proves polling is insufficient.
- **Live cancellation characterization:** optional for PR-8; not a blocker if fake-provider cancellation contract is pinned.
- **Provider health monitoring:** out of scope.
- **Automatic cheapest-provider routing:** out of scope.

---

## Self-Review Notes

Checklist applied while drafting this plan:

- No production code is scoped into PR-5.
- Every fal-specific choice that affects shared contracts has a pressure-check row.
- Fal choices that are local-only are marked as local implementation detail rather than framework law.
- Secret/status metadata defines the minimum shape PR-6+ can implement without reopening PR-4's deferred decision.
- Replicate/Gemini/Veo/Tencent are used as contract pressure only, not implementation scope.
- Native/managed boundary is explicit: managed provider work unless a separate route parity PR is scoped.
- No 3D-shaped production symbols are introduced by this plan.

---

## Iteration Log

- **v1.0 (2026-04-29):** Initial PR-5 planning draft. Defines fal-first Phase 2 sequence, binds Phase 0 invariants into a reviewer checklist, resolves the minimum provider secret/status metadata shape deferred from PR-4, and adds concrete provider-pressure tables without expanding PR-5 into Replicate/Tencent implementation scope.
