# Multi-Provider Phase 1 — Implementation Plan

**Date:** 2026-04-27
**Status:** plan, pre-implementation; reviewed twice with Codex through the design pass
**Branch (this doc):** `docs/multi-provider-phase1-plan` (clean worktree at `../Rook-phase1-plan`)
**Predecessors:**
- [`2026-04-26-generation-provider-framework.md`](2026-04-26-generation-provider-framework.md) — strategic frame (v0.2 with Phase 0 binding folded in)
- [`2026-04-27-multi-provider-spike.md`](2026-04-27-multi-provider-spike.md) — Phase 0 evidence + six contract decisions
- [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) — V1c video provider abstraction (the seam being generalized)
- [`2026-04-08-sa-banana-integration.md`](2026-04-08-sa-banana-integration.md) — RookVision image-track architecture (refactor target)

---

## TL;DR

Phase 1 generalizes the V1c video seam into a modality-neutral generation framework that supports both image and video providers. The work is four PRs:

1. **PR-1** — Net-new generic seam types in `Rook.Services.Vision.Generation`. Pure additive, no consumers.
2. **PR-2** — Video subsystem retrofits to consume the generic seam. Veo behavior end-to-end identical.
3. **PR-3** — `IImageProvider` + Gemini provider; `VisionHandler.generate` routed through registry. `enhance_prompt`, `test_api_key`, settings overview, artifact metadata, and depth/viewport ops are byte-identical pre/post.
4. **PR-4** — `IGenerationSecretStore` keyspace with one-shot migration from the legacy `vision.GeminiApiKeyEncrypted` slot. Missing-key error preserved verbatim for Gemini.

The 3D carve-out is enforced mechanically: a path-scoped symbol-scan test fails the build if any of `IThreeDProvider`, `ResolvedThreeDModel`, `ThreeDCapability`, `model_glb`, `model_urls`, or case variants appear under `src/Rook/Services/Vision/Generation/`.

No Phase 1 PR ships a new aggregator (fal/Replicate are Phase 2) or 3D provider (Phase 4). Phase 1 also does not change any user-visible UI, route shape, ledger format, or artifact metadata.

---

## Decisions Bound

Two design decisions were resolved during the planning review pass:

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | `ProviderSubmitOutcome` discrimination | **Sealed-record union (Sync \| Queued \| Failed) with `Queued(ProviderJobHandle)`** | Phase 0 binding requires sync vs async to be explicit and to never share a submit-then-poll-then-fetch contract; sealed-record subtypes give payload coherence at the type level. The exhaustiveness benefit is enforced via test, not the language. |
| 2 | Plan file location | **Committed under `docs/rook_docs/` on a clean worktree** | Plan is now architectural source material, not scratch. Clean worktree (`../Rook-phase1-plan`) keeps it isolated from the dirty primary tree's recovered local changes. |

Three blocking type-shape corrections from the second review pass are folded into the seam definitions below:

- `Queued` carries `ProviderJobHandle`, never a bare string.
- `ProviderResultEnvelope` does not carry an `Error` field; success/failure is `ProviderResultOutcome.Success | Failed`.
- `IVideoProvider` does **not** parameterize over a concrete options type. Options pairing lives at the resolved-model + codec edge.

---

## Generic Seam — Type Shapes

All types ship under `Rook.Services.Vision.Generation` in PR-1. None of them reference `Video*` or `Image*` names; modality-specific subclasses live in the per-modality namespace and inherit from these.

> **Forward-reference convention.** Examples in this section that name `ResolvedVideoModel`, `VideoCapability`, `IVideoProvider`, `ResolvedImageModel`, `ImageCapability`, or `IImageProvider` are illustrative of how the modality-specific subclasses *will* sit on top of the generic seam. Those types do **not** ship in PR-1 — `ResolvedVideoModel` and the video-specific shapes are PR-2 work; `ResolvedImageModel` and the image-specific shapes are PR-3 work. PR-1's deliverable is strictly the modality-neutral primitives.

### Provider interfaces

```csharp
namespace Rook.Services.Vision.Generation;

public interface IGenerationProvider
{
    string ProviderName { get; }
}

// Generic over the request and capability shapes only — NOT options.
// Options pairing lives on ResolvedModel + codec; the provider casts
// request.Options to its concrete type internally and returns
// GenerationError(InvalidRequest) on type mismatch.
public interface IGenerationProvider<TRequest, TCapability> : IGenerationProvider
    where TRequest : GenerationRequest
    where TCapability : IModelCapability
{
    Task<ProviderSubmitOutcome> SubmitAsync(
        TRequest request,
        IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
        CancellationToken ct);

    Task<ProviderStatusOutcome> GetStatusAsync(
        ProviderJobHandle handle,
        CancellationToken ct);

    Task<ProviderCancelOutcome> CancelAsync(
        ProviderJobHandle handle,
        CancellationToken ct);

    Task<ProviderResultOutcome> FetchResultAsync(
        ProviderJobHandle handle,
        CancellationToken ct);
}
```

### Request / capability / options bases

```csharp
public abstract record GenerationRequest(string Model, ProviderOptions Options);

public abstract record ProviderOptions;

public interface IModelCapability
{
    string Id { get; }
    string Name { get; }
    string Status { get; }                          // "stable" | "preview"
    string Modality { get; }                        // "image" | "video"
    IReadOnlyList<string> SubCapabilities { get; }  // e.g. ["text_to_image", "image_to_image"]
}
```

`Modality` is a `string` rather than an enum so a future modality (audio, embedding, tabular) does not require recompiling the core. The 3D carve-out symbol-scan rejects any value containing `3d` or `three_d` from appearing in modality string literals under the Generation path. Phase 4 will widen this when `IThreeDProvider` is designed.

### Job handle (Decision 1 correction)

```csharp
public sealed record ProviderJobHandle(
    string ProviderJobId,                                       // required, non-empty
    Uri? StatusUrl,                                             // fal: status_url; Replicate: urls.get
    Uri? ResponseUrl,                                           // fal: response_url; null when result embeds in poll
    Uri? CancelUrl,                                             // fal: cancel_url; Replicate: urls.cancel
    string? CancelHttpMethod,                                   // "POST" | "PUT" | "DELETE"; null for SDK-mediated providers
    string? ProviderResultToken,                                // Veo: videoUri; absent when ResponseUrl is the fetch addr
    IReadOnlyDictionary<string, JsonNode>? ProviderMetadata);   // free-form provider-specific bag
```

Fields are populated only when the provider actually exposes them. Veo's queued path populates `ProviderJobId` at submit time and leaves the rest null; `ProviderResultToken` (Veo's videoUri) is stamped onto an updated handle later, when status reports `ProviderCompleteStatusOutcome`. fal-queue populates the URL fields. Replicate populates `StatusUrl` + `CancelUrl` + leaves `ResponseUrl` null (terminal poll embeds output). The handle is persisted verbatim into the ledger so a manager restart can resume polling without re-deriving anything.

### Submit outcome (sealed union)

```csharp
public abstract record ProviderSubmitOutcome;

// Sync providers (Gemini direct, fal sync) return the full result inline.
public sealed record SyncSubmitOutcome(ProviderResultOutcome Result)
    : ProviderSubmitOutcome;

// Async providers return a handle for subsequent polling/fetching.
public sealed record QueuedSubmitOutcome(ProviderJobHandle Handle)
    : ProviderSubmitOutcome;

// Submit-time failure (auth, validation, quota).
public sealed record FailedSubmitOutcome(GenerationError Error)
    : ProviderSubmitOutcome;
```

A test under PR-1 uses pattern-matching exhaustiveness inside a `switch` expression with a default-throws arm to fail the build if a new subtype appears without consumers being updated. C# does not natively enforce exhaustive matching on sealed-record unions; the test is the enforcement.

### Status outcome

```csharp
public abstract record ProviderStatusOutcome;

public sealed record InFlightStatusOutcome(
    GenerationLifecycleState State,                 // canonical lowercase
    GenerationProgress? Progress)
    : ProviderStatusOutcome;

// Provider-Complete: provider's work done, result handle set on
// ProviderJobHandle (typically populated already at submit; provider may
// also update fields here, e.g. Veo's videoUri when the operation
// resolves). The manager does NOT treat this as job-Complete; it then
// invokes FetchResultAsync to materialize the artifact.
public sealed record ProviderCompleteStatusOutcome(
    ProviderJobHandle UpdatedHandle)
    : ProviderStatusOutcome;

public sealed record FailedStatusOutcome(GenerationError Error)
    : ProviderStatusOutcome;

public enum GenerationLifecycleState
{
    Pending = 0,
    Running = 1,
    Completed = 2,
    Failed = 3,
    Canceled = 4,
}

// Helper used by all provider impls. Lowercases the input, then maps
// the canonical set: pending|queued|in_queue|starting → Pending;
// running|processing|in_progress → Running; completed|succeeded|done
// → Completed; failed|error|errored → Failed; canceled|cancelled →
// Canceled. Anything else throws — providers are expected to extend
// the synonym list explicitly when adding a new state name.
public static class GenerationLifecycleStateNormalizer
{
    public static GenerationLifecycleState Normalize(string raw);
}
```

The case-insensitivity finding from Decision 1 (fal queue UPPERCASE vs Replicate lowercase) is handled in the normalizer, not by each provider re-implementing string comparison.

### Result envelope and outcome (Decision 5 + correction #2)

```csharp
public sealed record ProviderResultEnvelope(
    IReadOnlyList<ResultArtifact> Artifacts,
    IReadOnlyDictionary<string, JsonNode> EnvelopeMetadata);

public sealed record ResultArtifact(
    string Role,                                            // "image" | "video" | "thumbnail" | etc.
    ArtifactBody Body,
    string? DeclaredMimeType,                               // provider-asserted; null for flat URL-list providers (Replicate output: [<url>])
    IReadOnlyDictionary<string, JsonNode> ProviderMetadata);

// Sealed union — URL-xor-inline enforced at the type level.
public abstract record ArtifactBody;
public sealed record RemoteArtifactBody(Uri Url, TimeSpan? SignedUrlTtl) : ArtifactBody;
public sealed record InlineArtifactBody(byte[] Bytes) : ArtifactBody;

public abstract record ProviderResultOutcome;
public sealed record SuccessResultOutcome(ProviderResultEnvelope Envelope) : ProviderResultOutcome;
public sealed record FailedResultOutcome(GenerationError Error) : ProviderResultOutcome;

public abstract record ProviderCancelOutcome;
public sealed record CanceledOutcome : ProviderCancelOutcome;
public sealed record AlreadyTerminalOutcome(GenerationLifecycleState TerminalState) : ProviderCancelOutcome;
public sealed record FailedCancelOutcome(GenerationError Error) : ProviderCancelOutcome;
```

The envelope holds an array because fal sync image returns `images: [{url, ...}]`, Gemini returns `candidates: [{content: {parts: [...]}}]`, and Hunyuan's 3D path returns multiple format variants. Even single-artifact providers (Veo, fal queue video) wrap their one artifact in a one-element list, so consumer code does not branch on cardinality.

`ProviderMetadata` and `EnvelopeMetadata` are `JsonNode`-typed bags rather than typed records: provider-native fields like `has_nsfw_concepts`, `seed`, `prompt`, `timings`, `metrics.predict_time`, `usageMetadata` round-trip through them without loss. The bags are persisted into the ledger / artifact metadata so audit + replay can reconstruct exactly what the provider returned.

**Declared vs materialized MIME.** `ResultArtifact.DeclaredMimeType` is the provider's asserted MIME type at submit/status time and is **nullable**. fal sync image, Veo, fal queue video, and Gemini all populate it; Replicate's `output: [<url>]` flat URL list does not (the only known MIME signal lives on the URL's `Content-Type` response header at fetch time). The manager's job is to materialize the artifact:
- if `Body` is `InlineArtifactBody`, MIME must already be known (provider populated `DeclaredMimeType`, or the materializing manager — implemented in PR-2/PR-3 — refuses to materialize and surfaces a typed error; inline-bytes without MIME is an unrecoverable provider contract violation, not a missing-MIME case);
- if `Body` is `RemoteArtifactBody` and `DeclaredMimeType` is null, the manager fetches the URL, reads `Content-Type`, falls back to magic-byte sniffing if the response header is absent or `application/octet-stream`, and writes the materialized MIME into the artifact-store metadata. The provider is never asked to invent a MIME it didn't see.

**Submit outcome discrimination — `FailedSubmitOutcome` vs `SyncSubmitOutcome(FailedResultOutcome)`.** Both encode "the call did not produce a usable artifact," but the discriminating axis is **whether the provider performed compute**:
- `FailedSubmitOutcome(error)` — the submission itself never reached the inference stage. Auth failures, request-shape validation, quota-exceeded responses returned synchronously, network errors. The user is **not charged** (per Phase 0 evidence: fal returns `x-fal-billable-units: 0` on input-validation rejection). Manager logs as a no-cost failure.
- `SyncSubmitOutcome(FailedResultOutcome(error))` — the sync provider performed compute and the compute failed. NSFW filter rejection, content-policy block, mid-inference OOM, model-side execution error. The user **may have been charged** depending on provider policy. Manager records the call against the user's spend ledger.

The line is "did the provider's billing meter run?" Submit-time failures are pre-meter; sync result failures are post-meter. Async providers express the same distinction across `FailedSubmitOutcome` (pre-meter) vs `FailedStatusOutcome`/`FailedResultOutcome` (post-meter).

### Error type

```csharp
public sealed record GenerationError(
    GenerationErrorCode Code,
    string Message,
    bool Retryable,
    string? Field,                                              // populated for InvalidRequest
    string? ProviderErrorCode,                                  // raw provider code (e.g. fal "validation_error")
    IReadOnlyDictionary<string, JsonNode>? ProviderDetail);     // FastAPI detail array, etc.

public enum GenerationErrorCode
{
    InvalidRequest = 0,         // caller-shaped: bad inputs, missing fields, type mismatch
    UnsupportedMedia = 1,       // capability mismatch (resolution unsupported, etc.)
    DependencyUnavailable = 2,  // network / 5xx / auth-failure
    ExecutionFailed = 3,        // provider-side execution error (NSFW filter, OOM, etc.)
    Cancelled = 4,
    Interrupted = 5,
    QuotaExceeded = 6,          // new in Phase 1 — fal/Replicate surface this distinctly from auth
    ContentPolicy = 7,          // new in Phase 1 — separated from ExecutionFailed for UX
}
```

`QuotaExceeded` and `ContentPolicy` are net-new codes; existing `VideoErrorCode` values map onto the first six 1:1 to keep PR-2's compatibility layer mechanical.

### Pricing

```csharp
public sealed record CostEstimate(
    decimal Min,
    decimal Max,
    bool IsExact,
    string Provenance);                 // e.g. "veo-per-second-2026-04-15"

public interface IPricingModel<TRequest, TCapability>
    where TRequest : GenerationRequest
    where TCapability : IModelCapability
{
    string PricingSource { get; }       // human label for descriptors
    PricingMetadataLocation MetadataLocation { get; }   // documentation hint only

    // Estimate at submit time, before the call.
    PricingResult Estimate(TRequest request, TCapability capability);

    // Optional — extract actual spend from a response. Each provider's
    // pricing model owns its own header/body parsing. The argument
    // shape gives the impl access to whatever the provider returns.
    JobPricing? ExtractActualSpend(
        IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
        JsonNode? responseBody);
}

public enum PricingMetadataLocation
{
    NotApplicable = 0,
    ResponseHeader = 1,                 // fal x-fal-billable-units
    ResponseBody = 2,                   // Replicate metrics.predict_time, Gemini usageMetadata
    ProviderSdk = 3,                    // Tencent typed response
}
```

`MetadataLocation` is a documentation hint only; actual extraction is `ExtractActualSpend`'s job. Phase 0's finding that fal alone uses three different per-unit rates for the same `x-fal-billable-units` header is honored: the pricing model, not the location enum, owns interpretation.

### Resolved-model and registry shapes

```csharp
public interface IResolvedModel
{
    string ModelId { get; }
    string ProviderName { get; }
    IModelCapability Capability { get; }
    PricingKind PricingKind { get; }
    string PricingSource { get; }
}

// Modality-specific subclasses retain their typed Provider + PricingModel + OptionsCodec.
public sealed record ResolvedVideoModel(
    string ModelId,
    string ProviderName,
    IVideoProvider Provider,
    VideoCapability Capability,
    IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel,
    IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec)
    : IResolvedModel
{
    PricingKind IResolvedModel.PricingKind => PricingModel switch { /* … */ };
    string IResolvedModel.PricingSource => PricingModel.PricingSource;
    IModelCapability IResolvedModel.Capability => Capability;
}

public sealed record ResolvedImageModel(
    string ModelId,
    string ProviderName,
    IImageProvider Provider,
    ImageCapability Capability,
    IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel,
    IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec)
    : IResolvedModel;
```

The codec's generics live on the resolved-model record, not on the provider interface — that is correction #3.

---

## PR-1 — Generic seam, additive only

**Goal:** Land all of `Rook.Services.Vision.Generation` as net-new code with zero existing-consumer touch. The video subsystem keeps its current types; PR-2 will retrofit them.

**Files added** (all new):

```
src/Rook/Services/Vision/Generation/IGenerationProvider.cs
src/Rook/Services/Vision/Generation/IGenerationProviderTyped.cs       // IGenerationProvider<TRequest, TCapability>
src/Rook/Services/Vision/Generation/GenerationRequest.cs
src/Rook/Services/Vision/Generation/ProviderOptions.cs
src/Rook/Services/Vision/Generation/IModelCapability.cs
src/Rook/Services/Vision/Generation/MediaRef.cs                       // generic media reference (replaces VideoMediaRef shape)
src/Rook/Services/Vision/Generation/ResolvedMedia.cs
src/Rook/Services/Vision/Generation/IMediaResolver.cs

src/Rook/Services/Vision/Generation/ProviderJobHandle.cs
src/Rook/Services/Vision/Generation/ProviderSubmitOutcome.cs          // abstract base + 3 sealed records
src/Rook/Services/Vision/Generation/ProviderStatusOutcome.cs          // abstract base + 3 sealed records
src/Rook/Services/Vision/Generation/ProviderResultOutcome.cs          // abstract base + 2 sealed records
src/Rook/Services/Vision/Generation/ProviderCancelOutcome.cs          // abstract base + 3 sealed records
src/Rook/Services/Vision/Generation/ProviderResultEnvelope.cs
src/Rook/Services/Vision/Generation/ResultArtifact.cs
src/Rook/Services/Vision/Generation/ArtifactBody.cs                   // abstract base + 2 sealed records
src/Rook/Services/Vision/Generation/GenerationLifecycleState.cs
src/Rook/Services/Vision/Generation/GenerationLifecycleStateNormalizer.cs
src/Rook/Services/Vision/Generation/GenerationProgress.cs

src/Rook/Services/Vision/Generation/GenerationError.cs
src/Rook/Services/Vision/Generation/GenerationErrorCode.cs

src/Rook/Services/Vision/Generation/CostEstimate.cs
src/Rook/Services/Vision/Generation/IPricingModel.cs
src/Rook/Services/Vision/Generation/PricingMetadataLocation.cs
src/Rook/Services/Vision/Generation/PricingResult.cs
src/Rook/Services/Vision/Generation/JobPricing.cs                     // generic per-unit/total record (video's existing JobPricing keeps its type until PR-2)

src/Rook/Services/Vision/Generation/IProviderOptionsCodec.cs          // generic over TRequest, TCapability
src/Rook/Services/Vision/Generation/ProviderOptionsDecodeResult.cs
src/Rook/Services/Vision/Generation/ValidationResult.cs

src/Rook/Services/Vision/Generation/IResolvedModel.cs
src/Rook/Services/Vision/Generation/ModelDescriptor.cs                // base for VideoModelDescriptor / ImageModelDescriptor

src/Rook.Tests/Vision/Generation/Fixtures/FalQueueShapeProviderFake.cs
src/Rook.Tests/Vision/Generation/Fixtures/FalQueueErrorAtFetchProviderFake.cs
src/Rook.Tests/Vision/Generation/Fixtures/ReplicatePredictionShapeProviderFake.cs
src/Rook.Tests/Vision/Generation/Fixtures/GeminiSyncShapeProviderFake.cs
src/Rook.Tests/Vision/Generation/Fixtures/UpperCaseStateNameFixture.cs
src/Rook.Tests/Vision/Generation/Fixtures/MetadataPreservationFixture.cs
src/Rook.Tests/Vision/Generation/Fixtures/HeaderPricingProviderFake.cs
src/Rook.Tests/Vision/Generation/Fixtures/BodyPricingProviderFake.cs
src/Rook.Tests/Vision/Generation/Fixtures/PairedCredentialResolverFake.cs
src/Rook.Tests/Vision/Generation/SubmitOutcomeExhaustivenessTests.cs
src/Rook.Tests/Vision/Generation/StateNormalizerTests.cs
src/Rook.Tests/Vision/Generation/SymbolScanGuardTests.cs
```

**Files touched** (no existing consumers): zero.

**Acceptance:**
- New project builds clean with no warnings.
- Symbol-scan test passes (no forbidden 3D symbols under `src/Rook/Services/Vision/Generation/`).
- Submit-outcome exhaustiveness test exercises all three subtypes through a switch.
- State normalizer test exercises lowercase, uppercase, mixed-case, and three synonym groups for each canonical state.
- All fixture tests compile and assert their happy-path expectations against in-memory fakes.
- Existing video tests still pass (no consumer changes).

---

## PR-2 — Video adapts to the generic seam

**Goal:** Retrofit `Rook.Services.Vision.Video` to consume the generic seam. All existing video tests pass unchanged. Veo behavior — submit envelope, ledger record shape, error codes surfaced over HTTP, artifact metadata, cost estimate JSON — is byte-identical pre/post against golden fixtures.

**Type-level changes:**

- `IVideoProvider` becomes `interface IVideoProvider : IGenerationProvider<VideoGenerationRequest, VideoCapability>` with no methods of its own (marker only). Codec generics live on `ResolvedVideoModel`, not the provider interface.
- `ModelCapability` is renamed to `VideoCapability` and made `: IModelCapability` with `Modality => "video"`, `SubCapabilities` derived from `Modes` (`{T2V, I2V, Interpolation}` → string list).
- `VideoGenerationRequest` becomes `record VideoGenerationRequest(...) : GenerationRequest(Model, Options)`.
- `VideoErrorCode` → deleted; replaced by `GenerationErrorCode` mapping. Compatibility:
  - `InvalidRequest`/`UnsupportedMedia`/`DependencyUnavailable`/`ExecutionFailed`/`Cancelled`/`Interrupted` map 1:1 — same int values, same names.
  - Public-facing JSON in HTTP responses uses the same string literal names. A JSON converter test asserts that the on-the-wire string for each pre-existing video error is unchanged.
- `VideoJobError` → deleted; replaced by `GenerationError`. Existing fields (`Code`, `Message`, `Retryable`, `Field`) are preserved; new fields (`ProviderErrorCode`, `ProviderDetail`) are populated from Veo only when available, default null otherwise.
- `ProviderSubmitResult` / `ProviderStatusResult` / `ProviderFetchResult` / `ProviderCancelResult` → deleted. `VeoProvider` and `VideoJobManager` consume the generic outcome types.
- `VideoMediaRef` / `ResolvedVideoMedia` → deleted in favor of generic `MediaRef` / `ResolvedMedia`. `VideoMediaRoles` retained as a static class of role-string constants.
- `IPricingModel` (video-namespace) → deleted; `PerSecondPricingModel` becomes `PerSecondVideoPricingModel : IPricingModel<VideoGenerationRequest, VideoCapability>`.
- `IProviderOptionsCodec` (video-namespace) → deleted; `VeoOptionsCodec : IProviderOptionsCodec<VideoGenerationRequest, VideoCapability>`.
- `VideoJobRecord` → unchanged shape (no schema bump). The handle's extension fields ride in the existing `Extensions["provider_handle"]` JsonObject only when populated; see PR-2 ledger mapping rule above.
- `VideoJobState` retained — it has more granular states (`Submitting`, `Polling`, `Downloading`, `Saving`) than `GenerationLifecycleState`. The two coexist: provider returns canonical lifecycle states; manager translates to ledger-state vocabulary that includes the manager-only `Downloading`/`Saving` phases.

**`VeoProvider` behavioral changes:**

- `SubmitAsync` returns `QueuedSubmitOutcome(ProviderJobHandle)` — Veo is always async-poll. The handle populates `ProviderJobId` from the operation name and `ProviderResultToken=null` until status returns `ProviderCompleteStatusOutcome` with the videoUri stamped in.
- `GetStatusAsync` returns `InFlightStatusOutcome(Running, progress)` while polling, then `ProviderCompleteStatusOutcome(handleWithVideoUri)` when the operation resolves, then `FailedStatusOutcome(error)` on failure. No `Sync` arm — Veo never short-circuits.
- `FetchResultAsync` reads the videoUri off the handle, downloads the bytes, returns `SuccessResultOutcome(envelope)` with one `ResultArtifact { Role: "video", Body: InlineArtifactBody, DeclaredMimeType: "video/mp4", ProviderMetadata: { duration_s, ... } }`.
- `CancelAsync` returns `CanceledOutcome` on success, `AlreadyTerminalOutcome` if the job already completed, `FailedCancelOutcome(error)` otherwise.

**`VideoJobManager` changes:**

- Pattern-matches on `ProviderSubmitOutcome` — Veo only ever produces `Queued`, but the manager handles all three arms with explicit `default → throw` for arms it doesn't expect. The video manager and image manager remain separate (per scope note below); the typed switch makes a future sync-video provider trivial to add.
- Persists handle data into the **existing** `VideoJobRecord` shape — no schema bump. `VideoJobRecord` already has `ProviderJobId`, `ProviderResultToken`, and `JsonObject? Extensions` fields. Mapping rule:
  - `ProviderJobHandle.ProviderJobId` → `VideoJobRecord.ProviderJobId` (top level, unchanged from V1c).
  - `ProviderJobHandle.ProviderResultToken` → `VideoJobRecord.ProviderResultToken` (top level, unchanged from V1c).
  - `ProviderJobHandle.{StatusUrl, ResponseUrl, CancelUrl, CancelHttpMethod, ProviderMetadata}` → only written into `VideoJobRecord.Extensions["provider_handle"]` **when at least one of those fields is non-null**. Veo's handle leaves all five null, so `Extensions["provider_handle"]` is never created on the Veo path. The on-disk JSON for Veo records is byte-identical to V1c.
  - On read, `JsonlVideoJobLedger` reconstructs `ProviderJobHandle` from the top-level fields plus `Extensions["provider_handle"]` if present. Pre-PR-2 records (no `provider_handle` extension key) parse with `StatusUrl=ResponseUrl=CancelUrl=CancelHttpMethod=null` and an empty `ProviderMetadata` — exactly what Veo produces today.
- Translates `GenerationLifecycleState` returned by status into the manager's richer `VideoJobState` vocabulary at the boundary.

**`VideoCostEstimator` changes:**

- Becomes `: IGenerationCostEstimator<VideoGenerationRequest, VideoCapability>` (a thin per-modality wrapper that runs capability validation → options codec validation → pricing in one pass; same logic as today). Returns `VideoCostEstimateResult` whose JSON shape is unchanged.

**Files changed:**

```
src/Rook/Services/Vision/Video/IVideoProvider.cs                          (marker-only)
src/Rook/Services/Vision/Video/ModelCapability.cs → VideoCapability.cs
src/Rook/Services/Vision/Video/VideoGenerationRequest.cs                  (inherit GenerationRequest)
src/Rook/Services/Vision/Video/VideoErrorCode.cs                          (deleted)
src/Rook/Services/Vision/Video/VideoErrorCodeExtensions.cs                (deleted)
src/Rook/Services/Vision/Video/VideoJobError.cs                           (deleted)
src/Rook/Services/Vision/Video/ProviderSubmitResult.cs                    (deleted)
src/Rook/Services/Vision/Video/ProviderStatusResult.cs                    (deleted)
src/Rook/Services/Vision/Video/ProviderFetchResult.cs                     (deleted)
src/Rook/Services/Vision/Video/ProviderCancelResult.cs                    (deleted)
src/Rook/Services/Vision/Video/IPricingModel.cs                           (deleted)
src/Rook/Services/Vision/Video/IProviderOptionsCodec.cs                   (deleted)
src/Rook/Services/Vision/Video/VideoMediaRef.cs                           (deleted; MediaRef in Generation namespace)
src/Rook/Services/Vision/Video/ResolvedVideoMedia.cs                      (deleted; ResolvedMedia in Generation)
src/Rook/Services/Vision/Video/IVideoMediaResolver.cs                     (deleted; IMediaResolver in Generation)
src/Rook/Services/Vision/Video/VeoProvider.cs                             (consumes generic outcomes)
src/Rook/Services/Vision/Video/VeoOptionsCodec.cs                         (typed-codec)
src/Rook/Services/Vision/Video/PerSecondPricingModel.cs                   (typed-pricing-model)
src/Rook/Services/Vision/Video/VideoJobManager.cs                         (pattern-match outcomes; reconstruct handle on read)
src/Rook/Services/Vision/Video/VideoCostEstimator.cs                      (typed-estimator)
src/Rook/Services/Vision/Video/VeoErrorMapper.cs                          (maps to GenerationError)
src/Rook/Services/Vision/Video/JsonlVideoJobLedger.cs                     (writes Extensions["provider_handle"] only when populated; reads legacy + extension shape)
src/Rook/Services/Vision/Video/VideoJobRecord.cs                          (no schema change — Extensions field already exists)
```

**Acceptance:**
- All existing video tests pass with zero edits beyond namespace adjustments.
- New `VeoBehaviorParityTests` exercise four byte-identical-JSON assertions against committed golden fixtures captured pre-PR-2: submit response envelope, **`VideoJobRecord` JSONL line for every state transition** (the no-schema-bump rule above is the constraint that makes this assertable for Veo), HTTP error response shape, and cost estimate. The ledger byte-identity holds for Veo specifically because Veo's handle never populates `StatusUrl`/`ResponseUrl`/`CancelUrl`/`CancelHttpMethod`/`ProviderMetadata`, so `Extensions["provider_handle"]` is never written.
- Legacy ledger reader test confirms records written before PR-2 still parse and surface through `IVideoJobManager` correctly. Forward-compat reader test confirms a synthetic record with `Extensions["provider_handle"]` populated (a future async provider with URL handles) parses and round-trips without dropping fields.
- Symbol-scan still 0 hits.
- Live Veo smoke (manual) confirms a 5-second test job submits, polls, downloads, and surfaces in the chat panel artifact list with unchanged metadata.

---

## PR-3 — Image provider seam, Gemini only

**Goal:** Stand up the image side of the framework. `VisionHandler.GenerateAsync` routes through a new `IImageProviderRegistry`. Every other `VisionHandler` op stays untouched.

**Type additions:**

```csharp
namespace Rook.Services.Vision.Image;

public interface IImageProvider : IGenerationProvider<ImageGenerationRequest, ImageCapability> { }

public sealed record ImageGenerationRequest(
    string Model,
    string Prompt,
    string Resolution,                              // "1K" | "2K" | "4K" | "512"
    string AspectRatio,                             // "1:1" | "16:9" | etc.
    int NumberOfImages,
    IReadOnlyList<MediaRef>? ReferenceImages,
    ProviderOptions Options)
    : GenerationRequest(Model, Options);

public sealed record ImageCapability(
    string Id,
    string Name,
    string Status,
    IReadOnlyList<string> Resolutions,
    IReadOnlyList<string> AspectRatios,
    int MaxReferenceImages,
    bool SupportsImageToImage,
    bool SupportsTextToImage,
    IReadOnlyList<string> SubCapabilities)
    : IModelCapability
{
    public string Modality => "image";
}

public sealed record ResolvedImageModel(
    string ModelId,
    string ProviderName,
    IImageProvider Provider,
    ImageCapability Capability,
    IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel,
    IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec)
    : IResolvedModel;

public interface IImageProviderRegistry { /* parallel to IVideoProviderRegistry */ }
public sealed class DefaultImageProviderRegistry : IImageProviderRegistry { /* … */ }
```

**Gemini provider:**

```
src/Rook/Services/Vision/Image/Gemini/GeminiImageProvider.cs
src/Rook/Services/Vision/Image/Gemini/GeminiImageOptions.cs
src/Rook/Services/Vision/Image/Gemini/GeminiImageOptionsCodec.cs
src/Rook/Services/Vision/Image/Gemini/GeminiImageCapabilities.cs
src/Rook/Services/Vision/Image/Gemini/GeminiImagePricingModel.cs
src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs
```

`GeminiImageProvider` is built by adapting the existing `GeminiClient` — its HTTP client, request body construction, error mapping, and response parsing move into the new provider. `enhance_prompt` does **not** depend on `GeminiClient`; it has always used its own `PromptEnhancer` class with its own HTTP client. PR-3 leaves `PromptEnhancer` byte-identical (no code change). After PR-3, `GeminiClient` has no callers and can be deleted in the same PR; an explicit grep-for-references step in PR-3 acceptance confirms this. Phase 2's prompt-enhancement generalization will refactor `PromptEnhancer` separately when that work is scoped.

**`GeminiImageProvider.SubmitAsync` returns `SyncSubmitOutcome` always.** No async path, no job handle, no fetch step. The envelope inside the sync outcome carries:
- one `ResultArtifact` per generated image (Gemini returns `candidates[].content.parts[].inlineData.data` as base64; provider decodes to `InlineArtifactBody`)
- `ProviderMetadata` per artifact: `{thoughtSignature, finishReason}` round-tripped from the Gemini response
- `EnvelopeMetadata`: `{modelVersion, responseId, usageMetadata: {promptTokenCount, candidatesTokenCount, *TokensDetails: [...]}}`

**Pricing — `GeminiImagePricingModel`:**

- `PricingSource` = `"gemini-per-token-by-modality-stub"` so audit can see this is provisional.
- `MetadataLocation` = `ResponseBody` (for `usageMetadata`).
- `Estimate` returns `CostEstimate(Min: 0.0m, Max: 0.0m, IsExact: false, Provenance: "gemini-stub-2026-04-27")`. **Phase 1 ships with stub rates; concrete per-token rates are a Phase 2 fact-gathering deliverable.** Important condition from review: `IsExact=false` is the contract, and a unit test asserts the Provenance string contains "stub" until concrete rates land.
- `ExtractActualSpend` parses `usageMetadata.{promptTokenCount, candidatesTokenCount}` so the JSON shape is in place; reports `JobPricing` with zero unit price until rates are filled in.

**`VisionHandler.GenerateAsync` migration:**

The existing method does, in order:
1. Read the API key from `_secrets.GetGeminiApiKey()`
2. Resolve short-name (`"nano-banana-2"`) → full ID (`"gemini-3.1-flash-image-preview"`)
3. Validate request shape (resolution, aspect ratio, prompt length, reference image count, byte budgets)
4. Call `_gemini.GenerateAsync(...)` for the network round-trip
5. Decode base64, mint artifact id, write artifact to `_artifactStore`, return envelope.

Post-migration:
1. Read the API key (unchanged for Phase 1; PR-4 widens this).
2. Resolve short-name → full ID via `IImageProviderRegistry.TryResolve`.
3. Validate via `ResolvedImageModel.OptionsCodec.Validate(...)` — same constraint matrix as today's hardcoded validation; `GeminiImageOptionsCodec` ports the existing checks verbatim.
4. Build `ImageGenerationRequest`; invoke `ResolvedImageModel.Provider.SubmitAsync(...)`. Pattern-match on `SyncSubmitOutcome` (the only arm Gemini ever returns); inside the `SuccessResultOutcome.Envelope`, take the first artifact's `InlineArtifactBody.Bytes`.
5. Mint artifact id, write to `_artifactStore`, return the same envelope shape as today.

Steps 1, 5, and the artifact metadata dictionary are the parts that must be byte-identical pre/post; a parity test against committed golden fixtures asserts this.

**Untouched VisionHandler ops** — covered by parity tests:
- `enhance_prompt` (still uses `PromptEnhancer` directly until Phase 2)
- `test_api_key`
- `get_settings_overview`
- `set_api_key`
- `capture_depth`, `capture_viewport`, `preview_viewport`, `list_views`
- `open_image_picker`
- `list_artifacts`, `get_artifact`, `approve_artifact`, `delete_artifact`, `consume_approved`

**Acceptance:**
- Gemini live smoke (manual): a `generate` call against `nano-banana-2` produces an artifact with identical metadata fields and identical artifact-id format pre/post.
- Parity test suite asserts byte-identical request/response JSON for `generate` against ten golden fixtures (text-only, 1K/2K/4K, with/without reference images, single/multi image, error cases for invalid resolution and missing prompt).
- Independent parity test suite asserts byte-identical request/response JSON for the seven untouched ops.
- Symbol-scan still 0 hits.
- New `GeminiSyncShapeProviderTests` exercise `SyncSubmitOutcome` round-trip including `EnvelopeMetadata` `usageMetadata` preservation.

---

## PR-4 — Secret-store keyspace

**Goal:** Replace single-slot `VisionSecretStore` (Gemini-only) with keyed `IGenerationSecretStore` capable of storing per-provider single-token + paired-credential shapes. Phase 1 only widens the keyspace; Settings UI changes are Phase 2.

**Type additions:**

```csharp
namespace Rook.Services.Vision.Generation;

public interface IGenerationSecretStore
{
    string? GetSecret(string secretKey);                    // e.g. "gemini.api_key", "tencent.secret_id"
    void SetSecret(string secretKey, string value);
    void RemoveSecret(string secretKey);
    bool HasSecret(string secretKey);
    string? GetPreview(string secretKey);                   // first4…last4 obscured form
}

public sealed class DpapiGenerationSecretStore : IGenerationSecretStore
{
    // Backed by RookSettingsStore section "generation_secrets".
    // Per-key DPAPI envelope with per-key entropy:
    //   "rook-generation-secret-v1::{secretKey}"
    // The secretKey is part of entropy so a blob encrypted under
    // "gemini.api_key" cannot be decrypted under "fal.api_key" even
    // by the same user — defense in depth against config-file
    // tampering swapping ciphertexts.
}
```

**Migration path:**

1. On first read of `gemini.api_key`, if the new section is empty AND the legacy `vision.GeminiApiKeyEncrypted` exists:
   - Decrypt under the legacy `"rook-vision-gemini-v1"` entropy.
   - Re-encrypt under the new entropy `"rook-generation-secret-v1::gemini.api_key"`.
   - Write the new ciphertext + preview to `generation_secrets` section.
   - Leave the legacy `vision` section in place for one Rook release (rollback safety). Phase 2 deletes the legacy field after one full release cycle.
2. Subsequent reads use the new section.
3. `IGenerationSecretStore.GetPreview("gemini.api_key")` returns the same first4…last4 string as `VisionSecretStore.GetApiKeyPreview()` did, so settings UI is unchanged.

**Provider registration declares secrets:**

```csharp
public interface IProviderRegistration
{
    string ProviderName { get; }
    IReadOnlyList<string> RequiredSecretKeys { get; }       // e.g. ["gemini.api_key"]
}
```

The registry computes a per-provider `SecretStatus { Configured | Missing }` at registration time; a future Settings UI surface (Phase 2) consumes this. **Phase 1 does not change the picker UI** — it still surfaces all registered models. Models with missing keys fail at submit time with the existing `DependencyUnavailable` error message, byte-identical to today's "Gemini API key not configured" string for the Gemini path. A test asserts the verbatim error string.

**Scope update (2026-04-28, PR-4 implementation):** defer `IProviderRegistration.RequiredSecretKeys` and `SecretStatus` to Phase 2 provider/settings metadata. PR-4 only widens credential storage and preserves submit-time missing-key behavior. No Settings UI or picker filtering consumes provider secret status in Phase 1, and freezing the metadata contract before fal/Replicate/Tencent credential shapes are wired would increase review surface without reducing risk. Phase 2 should introduce provider-secret metadata alongside the UI that consumes it.

**`VisionSecretStore` shim:**

`VisionSecretStore` becomes a thin facade over `IGenerationSecretStore` for the remaining `enhance_prompt` consumer. `enhance_prompt` calls `_secrets.GetGeminiApiKey()` exactly as today; the shim delegates to `_store.GetSecret("gemini.api_key")`. Phase 2 will remove the shim when `enhance_prompt` is generalized into a provider too.

**Files added:**

```
src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs
src/Rook/Services/Vision/Generation/DpapiGenerationSecretStore.cs
src/Rook/Services/Vision/Generation/GenerationSecretsSettings.cs
src/Rook.Tests/Services/Vision/Generation/GenerationSecretStoreTests.cs
src/Rook.Tests/Services/Vision/Generation/MissingKeyErrorParityTests.cs
```

**Files changed (composition root + handlers):**

```
src/Rook/Services/Vision/VisionSecretStore.cs                             (shim over IGenerationSecretStore for PromptEnhancer's continued use)
src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs                   (consumes IGenerationSecretStore)
src/Rook/Handlers/VisionHandler.cs                                        (constructor takes IGenerationSecretStore, passes to image provider construction)
src/Rook/RookSubsystemRoot.cs                                             (constructs DpapiGenerationSecretStore once; injects into VisionHandler + VisionWebSurface + NativeGhBridgeRegistrar; legacy VisionSecretStore field becomes the shim)
src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs                        (accepts IGenerationSecretStore for the set_api_key / test_api_key bridge ops)
src/Rook/UI/Vision/VisionWebSurface.cs                                    (accepts IGenerationSecretStore for the in-process JS bridge)
```

**Tests changed:**

```
src/Rook.Tests/Handlers/VisionHandlerTests.cs                             (constructs handler with fake IGenerationSecretStore)
src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs        (constructs factory with fake store)
src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs             (shared-store assertions updated to IGenerationSecretStore)
src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs                         (shared-store assertions updated to IGenerationSecretStore)
```

The shared-store assertion pattern (the same `VisionSecretStore` instance is reachable from `VisionHandler`, `VisionWebSurface`, and `NativeGhBridgeRegistrar` so a `set_api_key` from any surface is visible to all) carries over verbatim — it now asserts shared `IGenerationSecretStore` identity instead. PR-4's review pass explicitly verifies this invariant has not regressed.

**Acceptance:**
- Migration test: a `RookSettings.json` containing only the legacy `vision.GeminiApiKeyEncrypted` field migrates on first read; the decrypted plaintext matches the original.
- Idempotency test: running the migration twice does not double-encrypt or corrupt.
- Verbatim-error test: with no key configured, the `generate` op returns the production missing-Gemini-key error string. **The literal is NOT embedded in this plan.** A pre-PR-3 capture step (no code change) reads the current message verbatim from `VisionHandler.cs` (currently sourced at `src/Rook/Handlers/VisionHandler.cs:436` and `:504` in the V1c tree, but the capture must use whatever the source-of-truth string is at the moment PR-3 starts) into a test constant `MissingGeminiKeyMessage` defined under `src/Rook.Tests/Vision/Generation/`. PR-3 and PR-4 both consume that constant. Same-string parity is asserted for both `generate` and `enhance_prompt` paths. If the production string drifts between PR-3 and PR-4, the test re-captures and the constant changes in one place.
- Roll-back test: deleting the new section and leaving the legacy section restores access via the migration path on the next read.
- Shared-store identity test: `RookSubsystemRoot` constructs a single `IGenerationSecretStore` instance; `VisionHandler`, `VisionWebSurface`, and `NativeGhBridgeRegistrar` all reference the same instance (asserted via `ReferenceEquals` in the existing shared-store test pattern, retargeted to the new interface).
- Overview compatibility test: `HasSecret("gemini.api_key")` and `GetPreview("gemini.api_key")` stay metadata-only for legacy `vision.GeminiApiKeyEncrypted`; malformed or wrong-profile legacy ciphertext must not break settings overview. `GetSecret("gemini.api_key")` remains the migration/decrypt boundary and still surfaces decrypt failures.
- Symbol-scan still 0 hits.

---

## Fixture Matrix (gate enforcement)

Each fixture is a behavioral assertion that a Phase 0 binding holds, exercised against in-memory provider fakes. Fixtures live under `src/Rook.Tests/Vision/Generation/Fixtures/` and are reused across PR-1–PR-4 acceptance.

| Fixture | Phase 0 binding | Asserts |
|---|---|---|
| `FalQueueShapeProviderFake` | Decision 1 | `QueuedSubmitOutcome` → poll `InFlightStatusOutcome(Pending|Running)` → `ProviderCompleteStatusOutcome(handle)` → `FetchResultAsync` → `SuccessResultOutcome` |
| `FalQueueErrorAtFetchProviderFake` | Decision 1 + 5 | Provider state reaches `Completed` but fetch returns `FailedResultOutcome(GenerationError)` with FastAPI-style `ProviderDetail` populated. Manager classifies as job failure, not success. |
| `ReplicatePredictionShapeProviderFake` | Decision 1 | Terminal poll embeds output; `ProviderCompleteStatusOutcome.UpdatedHandle.ProviderResultToken` populated, `ResponseUrl` null; FetchResult reads from token directly |
| `GeminiSyncShapeProviderFake` | Decision 1 | `SubmitAsync` returns `SyncSubmitOutcome(SuccessResultOutcome)` with full envelope, no job handle, no poll, no fetch |
| `UpperCaseStateNameFixture` | Decision 1 | Normalizer maps `IN_QUEUE`/`IN_PROGRESS`/`COMPLETED` to canonical lowercase; case-mixed inputs round-trip; unknown states throw |
| `MetadataPreservationFixture` | Decision 5 | Provider-native fields (`has_nsfw_concepts`, `seed`, `prompt`, `timings`, `usageMetadata`) round-trip through `EnvelopeMetadata` and `ProviderMetadata` JsonNode bags without lossy serialization |
| `HeaderPricingProviderFake` | Decision 3 | `IPricingModel.ExtractActualSpend` reads `x-fal-billable-units` from response headers and produces `JobPricing` with the per-model unit rate |
| `BodyPricingProviderFake` | Decision 3 | `IPricingModel.ExtractActualSpend` reads `metrics.predict_time` from response body and produces `JobPricing` with the per-second rate |
| `PairedCredentialResolverFake` | Decision 6 | `IGenerationSecretStore` round-trips a `(secret_id, secret_key)` pair under separate keys; absence of one key surfaces as `DependencyUnavailable` distinct from absence of both |
| `URLArtifactBodyFixture` | Decision 5 | `RemoteArtifactBody(uri, ttl)` round-trips through serialization; manager test confirms a URL-bodied artifact is fetched and materialized to bytes before artifact-store write |
| `InlineArtifactBodyFixture` | Decision 5 | `InlineArtifactBody(bytes)` does not require a follow-up fetch; manager goes directly to artifact-store write |
| `MissingKeyErrorParityFixture` | (PR-4 important condition) | Verbatim missing-Gemini-key error string for `generate` matches production string captured pre-PR-3 |
| `VeoBehaviorParityFixture` | (PR-2 important condition) | Pre/post-PR-2 byte-identical JSON for submit envelope, ledger record, error response, cost estimate against ten golden video fixtures |

---

## Symbol-Scan Acceptance

`SymbolScanGuardTests` runs in CI for every PR-1–PR-4 build. Implementation:

```csharp
public sealed class SymbolScanGuardTests
{
    private static readonly string[] ForbiddenPatterns =
    {
        @"\bIThreeDProvider\b",
        @"\bResolvedThreeDModel\b",
        @"\bThreeDCapability\b",
        @"\bThreeDGenerationRequest\b",
        @"\bIThreeDProviderRegistry\b",
        @"\bmodel_glb\b",
        @"\bmodel_urls\b",
        @"\bthree_d_provider\b",
        @"\btencent_3d\b",
        @"\bhunyuan3d\b",
    };

    [Fact]
    public void Generation_namespace_contains_no_3D_symbols()
    {
        var generationRoot = Path.Combine(RepoRoot, "src/Rook/Services/Vision/Generation");
        var sources = Directory.EnumerateFiles(generationRoot, "*.cs", SearchOption.AllDirectories);
        var matches = new List<string>();
        foreach (var path in sources)
        {
            var content = File.ReadAllText(path);
            foreach (var pattern in ForbiddenPatterns)
            {
                if (Regex.IsMatch(content, pattern, RegexOptions.IgnoreCase))
                    matches.Add($"{path}: {pattern}");
            }
        }
        Assert.Empty(matches);
        // On failure, xUnit's CollectionException dump shows each violating
        // path:pattern pair so the regression is self-explanatory without
        // needing a custom assertion message.
    }
}
```

(`Rook.Tests` uses xUnit; `[Fact]` + `Assert.Empty` is the project convention.)

The scan is **path-scoped** to `src/Rook/Services/Vision/Generation/` — it does NOT scan `docs/`, `tools/spikes/`, `mcp_server/`, or the rest of the codebase, so Phase 4 design notes elsewhere do not trigger the test. Case-insensitive match is intentional to catch `IThreeDprovider` / `iThreeDProvider` / etc. The pattern list is extended in PR-4 to include `tencent_3d`, `hunyuan3d`, `Tencent3D` — those names appear in spike evidence and could leak in via copy-paste.

---

## 3D Carve-Out — what is forbidden where

| Forbidden in Phase 1 | Allowed location |
|---|---|
| `IThreeDProvider`, `ResolvedThreeDModel`, `ThreeDCapability`, `ThreeDGenerationRequest`, `IThreeDProviderRegistry`, `IThreeDProviderRegistration` | `Rook.Services.Vision.ThreeD` namespace, Phase 4 only — does not exist in Phase 1 |
| `model_glb`, `model_urls`, `three_d_provider`, `tencent_3d`, `hunyuan3d` | Phase 4 design docs and Phase 4 implementation only |
| `Modality` field value containing `"3d"`, `"three_d"`, `"hunyuan3d"`, etc. in any IModelCapability instance under the Generation namespace | Phase 4 — opaque modality string; Phase 1 capability-modality enum check rejects |
| Multi-format result dispatch (Hunyuan-style `model_urls.{glb, obj, fbx, usdz, mtl, texture}`) | Phase 4 — `ProviderResultEnvelope.Artifacts` is single-modality in Phase 1; Phase 4 may extend |
| Per-format `null`-tolerant artifact fields | Phase 4 |

The `Modality` string is a free-form `string` precisely so Phase 4 can add `"3d"` without recompiling Phase 1 code; the enforcement is a Phase 1 build-time test that rejects 3D-shaped values, plus Phase 4's review-pass reverting the test when 3D ships.

---

## Out of Scope for Phase 1

- Aggregator providers (fal, Replicate). Phase 2.
- `IThreeDProvider` and Hunyuan integration. Phase 4.
- Tencent direct API. Phase 4.
- Picker UI capability filter, provider badges, multi-key Settings UI. Phase 2 + 3.
- Concrete Gemini per-token rates; Phase 1 ships stubs marked `IsExact=false`.
- Removal of legacy `vision.GeminiApiKeyEncrypted` settings field (kept for one release after PR-4).
- Generalization of `enhance_prompt`. Phase 2.
- Webhook / streaming result delivery. Phase 2 candidate (Replicate `urls.stream`).
- Dynamic catalog discovery (`*DynamicCatalogSource`). Phase 5.
- Local-model providers (Ollama, ComfyUI). Out of roadmap until usage signal.

---

## Implementation Lessons (post-PR-1, applies to PR-2/PR-3)

PR-1 shipped under five Codex review rounds. Two corrections came out of those rounds that **invalidate prose elsewhere in this plan**. PR-2/PR-3 must follow the corrected patterns; the older prose (e.g. references to "sealed-record union") describes a shape that does not actually achieve closure under C# language semantics.

### Closed unions: abstract class + sealed class, NOT records

C# auto-generates a `protected` copy constructor for non-sealed records, and the language spec disallows making it stricter than `protected` for non-sealed bases. That copy constructor is reachable from external derived records — so a `private protected` parameterless ctor on a `public abstract record` does **not** prevent external-assembly derivation. `with`-expressions and object initializers also let callers bypass constructor validation through `init` setters.

**The pattern PR-1 actually shipped (and PR-2/PR-3 must follow):**
- Closed union bases are `public abstract class` with a `private protected` parameterless constructor. No record. No copy ctor leak.
- Closed union leaves are `sealed class` (not `sealed record`) with explicit constructors and read-only `{ get; }` properties.
- Invariant-bearing types (`CostEstimate`, `JobPricing`, `ProviderJobHandle`, `ResultArtifact`, `ProviderResultEnvelope`, `ResolvedMedia`, `GenerationProgress`) are `sealed class` with read-only `{ get; }` properties — no `init` setters, no `with` syntax.
- `UnionClosureTests` and `InvariantBypassTests` enforce both rules by reflection. Adding a record to either set, or adding an `init` setter to an invariant-bearing type, fails the build.

PR-2's `VideoCapability` and PR-3's `ImageCapability` should follow the existing `IModelCapability` interface pattern. They MAY remain records IF they have no closure or invariant requirements — but the safer default for any new modality-specific subclass is sealed class with read-only props. **Do not introduce sealed-record positional-syntax types into the Generation namespace without re-running `UnionClosureTests` + `InvariantBypassTests` against them.**

The `with`-expression substitute on `ProviderJobHandle` is `WithResultToken(string?)` (and any future `WithX` methods that go through the validating constructor). PR-2's `VideoJobManager` should call `handle.WithResultToken(videoUri)` at the status-complete transition rather than mutating fields.

### net48 multi-targeting traps

`Rook.csproj` multi-targets `net7.0;net48`. Three runtime API gaps bit PR-1 during implementation; PR-2/PR-3 will hit them again unless they're avoided up front:

| Trap | Symptom | Workaround |
|---|---|---|
| `System.HashCode` is netstandard2.1+ | `error CS0103: The name 'HashCode' does not exist` on net48 | Use `(field1, field2, ...).GetHashCode()` — `ValueTuple<...>.GetHashCode` is on net48. |
| `Dictionary<,>` has no `IReadOnlyDictionary` ctor on net48 | `error CS1503: cannot convert from 'IReadOnlyDictionary<...>' to 'int'` (compiler picks capacity overload) | Use explicit `foreach (var kvp in source) copy[kvp.Key] = kvp.Value;` |
| Records on net48 require `IsExternalInit` polyfill | Compile fails on `init` setters / positional records | Polyfill already exists at `src/Rook/Polyfills/IsExternalInit.cs`. Don't remove. |

PR-2's golden-fixture work involves capturing pre-refactor JSON shapes. The byte-identity assertion is sensitive to dictionary iteration order. Use `JsonNode` comparison or an order-insensitive equivalence check; do not rely on `==` between `JsonObject` instances.

---

## Iteration Log

- **v1.0 (2026-04-27):** Initial plan. Bound to two design decisions: sealed-record union with `Queued(ProviderJobHandle)`, committed under `docs/rook_docs/` on a clean worktree. Three blocking type-shape corrections from review pass 2 folded in: `Queued` carries a handle (not a string); `ProviderResultEnvelope` is success-only, paired with `ProviderResultOutcome.Success | Failed`; `IVideoProvider` does not parameterize over options. Four-PR sequence: generic seam (additive) → video adapt → image stand-up → secret-store keyspace. Phase 0 fixture matrix and path-scoped symbol-scan acceptance specified.

- **v1.1 (2026-04-27, review pass 3):** Two blocking findings + four important + two minor folded in.
  - **PR-2 ledger contradiction resolved.** No `VideoJobRecord` schema bump. Handle's optional URL/cancel-method/metadata fields ride in the existing `Extensions["provider_handle"]` JsonObject only when populated. Veo's handle leaves all of them null, so Veo records remain byte-identical to V1c on disk. Forward-compat reader test added for the populated-extensions case.
  - **`ResultArtifact.MimeType` made nullable.** Renamed `DeclaredMimeType`. Manager owns materialization: inline-bytes without declared MIME is a contract violation (typed error); URL-bodied artifacts with no declared MIME are sniffed from `Content-Type` + magic-bytes at fetch time. Replicate's flat URL list is the motivating case.
  - **Forward-reference convention** added to the seam-shapes section so `ResolvedVideoModel`/`ResolvedImageModel` examples are explicitly labeled as PR-2/PR-3 work, not PR-1 deliverables.
  - **`enhance_prompt` lineage corrected.** Owned by `PromptEnhancer` (its own HTTP client), not `GeminiClient`. PR-3 leaves `PromptEnhancer` byte-identical and may delete `GeminiClient` after the grep-for-references step confirms zero remaining callers.
  - **PR-4 composition root + tests expanded.** Added `RookSubsystemRoot`, `NativeGhBridgeRegistrar`, `VisionWebSurface`, `VeoProvider`, and four test files to the changed-files list. Shared-store identity assertion (`ReferenceEquals` across the three surfaces) carries from V1c retargeted to `IGenerationSecretStore`.
  - **Missing-key error string is captured, not embedded.** Pre-PR-3 step reads the live production string from `VisionHandler.cs` into a `MissingGeminiKeyMessage` test constant; the plan no longer contains a literal that could go stale. Same constant is consumed by both `generate` and `enhance_prompt` parity tests.
  - **Symbol-scan converted to xUnit** (`[Fact]` + `Assert.Empty`); pattern list extended with `tencent_3d` and `hunyuan3d`.
  - **Submit-outcome discrimination clarified.** `FailedSubmitOutcome` = pre-meter (provider's billing meter never ran); `SyncSubmitOutcome(FailedResultOutcome)` = post-meter (compute happened, then failed). Async providers express the same axis via `FailedSubmitOutcome` vs `FailedStatusOutcome`/`FailedResultOutcome`. Manager logs no-cost-failure vs charged-failure accordingly.

- **v1.1.1 (2026-04-27, review pass 4 cleanup):** Four text-coherence fixes, no architectural change.
  - Veo handle population at submit corrected: `ProviderJobId` only at submit; `ProviderResultToken` is stamped on the updated handle when status reports `ProviderCompleteStatusOutcome`. The two earlier passages now agree.
  - PR-3 untouched-ops list now correctly says `enhance_prompt` continues to use `PromptEnhancer`, matching the corrected lineage in the GeminiImageProvider section.
  - VeoProvider's example `ResultArtifact` now uses `DeclaredMimeType` to match the v1.1 type shape.
  - Materialization commentary now refers to the "materializing manager — implemented in PR-2/PR-3" instead of "PR-1's manager," reflecting that PR-1 has no consumers.

- **v1.2 (2026-04-28, post-PR-1 implementation lessons):** PR-1 merged as `ff433e1` after five Codex review rounds. Added `## Implementation Lessons` section above documenting the two architectural corrections that didn't make it into v1.0–v1.1.1 prose:
  - Closed unions and invariant-bearing types are `abstract class` + `sealed class` with read-only `{ get; }` properties, NOT records. Records' compiler-generated `protected` copy constructor leaks external derivation; `init` setters allow `with`/object-initializer bypass of constructor validation. `UnionClosureTests` + `InvariantBypassTests` enforce by reflection. Apply to all PR-2/PR-3 types in the Generation namespace.
  - net48 multi-targeting traps documented with workarounds: `System.HashCode` (use `ValueTuple.GetHashCode`), `Dictionary<,>` no `IReadOnlyDictionary` ctor (use explicit `foreach`), `IsExternalInit` polyfill already in place.
  - `ProviderJobHandle.WithResultToken(string?)` is the canonical handle-update path for PR-2's status-complete transition, replacing the `with`-expression that worked when handles were records.
  - Older prose still says "sealed-record union" in places; the v1.2 lessons section is the authoritative correction. Treat any conflict between earlier prose and the lessons section as the lessons section winning.
