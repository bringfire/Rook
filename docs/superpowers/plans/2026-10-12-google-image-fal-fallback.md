# Google Image fal Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the two existing AI Studio Nano Banana choices usable through automatic fal fallback for missing or definitively rejected Gemini credentials, with truthful attribution and durable cancellation.

**Architecture:** One image submission executor resolves the closed fallback map and returns effective execution context to both managed submission paths. The existing image manager serializes each job's durable transitions and owns the affected jobs' execution deadline. Catalog, managed bridges, and the panel project the same locally derived routing evidence.

**Tech Stack:** Existing C# / HttpClient / System.Text.Json, net48/net7.0/net8.0 managed companion, xUnit net48 tests, embedded JavaScript, Node core modules.

**Spec:** [Approved design](../specs/2026-10-12-google-image-fal-fallback-design.md), revision a3cab49d, approved in this chat on 2026-10-12. Implementation starts from that revision; do not confuse the spec's historical baseline a6f63be8 with the execution baseline.

**Plan revision:** Incorporates the subsequent human review: persist fal dispatch intent before HTTP, retain direct fal credential evidence without a fallback receipt, and perform 512-resolution translation only in the executor. The new optional fal_dispatch_state is a local durable intent/recovery contract, not proof of cloud acceptance or billing.

## Global Constraints

- Only the two existing AI Studio Nano Banana models have automatic fallback. Their aliases resolve before routing.
- Billing/quota failures, broader outages, and Enterprise authorization failures do not trigger fallback in this scope.
- Preserve existing source-image requirements and admitted workflows.
- Do not persist a provider switch or permanently mark the stored key invalid.
- Preserve the primary source image followed by reference images in the caller's original reference order, including explicitly repeated references.
- Map Rook's Nano Banana 2 resolution 512 to fal's 0.5K; preserve 1K, 2K, and 4K. Pro supports 1K, 2K, and 4K.
- That 512 conversion belongs solely to mapped Gemini fallback; direct fal accepts native 0.5K and rejects 512.
- Use PNG output. Retain the existing Rook input caps (10 MiB per image, 15 MiB aggregate, up to eight references) and generated-image materialization cap (25 MiB).
- Use the provider's default moderation policy; do not change safety tolerance or work around a policy refusal.
- No new external dependency, storage service, or input-upload lifecycle is required.
- Keep the new models synchronous; this feature does not introduce fal queue/poll/cancel machinery for them.
- Preserve schema version 1 with additive optional image_route and credential_failure fields: legacy entries without them remain readable and are not rewritten.
- Also preserve optional fal_dispatch_state through job records and restart. A recorded intent followed by a crash means remote submission outcome is unknown; never interpret generation_dispatch_attempted: false as proof that fal received nothing.
- Manager-backed jobs for the two fallback-capable Gemini models and the two new direct fal choices get a manager-owned 180-second execution deadline. Queue wait is excluded.
- Synchronous panel/native calls keep their existing caller-owned operation deadline.
- No native C++ change/build is expected. Deployment, cloud-account setup, and live billed qualification are separate user requests.
- Follow AGENTS.md: Windows, existing managed handler patterns, no .vcxproj/.vcxproj.filters edits, no Revit references or new public native route. Build all three supported managed targets.

## Review Focus

These additional conditions are pinned in the owning tasks below.

1. An upstream status string mimics a reserved local credential marker: it must not cause an unrequested billed fallback (Task 2).
2. Two simultaneous jobs take different routes: their receipts, model attribution, and deadline/cancellation signals must remain isolated (Task 6).
3. fal returns a generic permission-denied response: display fal failure without asserting that its stored key is invalid (Tasks 3 and 8).
4. Optional persisted routing fields disagree with the job's provider/model or catalog mapping: report a ledger-read error rather than manufacture trusted attribution (Task 1).
5. The native outer timeout fires while a fal transport ignores cancellation: return the latest safe receipt promptly, without waiting for remote settlement or losing attribution (Task 7).

---

## File and responsibility map

Paths below are repository-relative. Create only the listed focused units; keep existing large handlers and manager in place.

| Unit | Responsibility / files |
|---|---|
| Routing contracts | New Image/ImageRoutingContext.cs and Image/ImageRoutingCodec.cs: immutable safe receipt, independent credential evidence, dispatch-intent state, JSON projection/validation. Existing Jobs record/result/factory/JSONL files retain them. |
| Credential evidence | New Image/ImageCredentialErrors.cs; existing Gemini/GeminiImageProvider.cs and Fal/FalImageProvider.cs normalize local evidence without changing shared video error mapping. |
| fal adapter | Existing Fal capabilities/options/registration/provider; new Fal/FalNanoBananaPayload.cs and Fal/FalNanoBananaPricingModel.cs own Google payload and unavailable pricing. |
| Submission policy | New Image/ImageSubmissionExecutor.cs, Image/ImageExecutionContext.cs, and Image/IImageDispatchAwareProvider.cs: effective context, one fallback, local send evidence. |
| Durable lifecycle | Existing Jobs/ImageJobManager.cs: one per-job commit boundary, separate route and dispatch-intent commits, restart uncertainty, artifact ownership; new Jobs/ImageExecutionBudget.cs: distinguish deadline/cancellation/shutdown. |
| Managed projections | Existing VisionHandler.cs, ImageJobOpHandler.cs, RookSubsystemRoot.cs, Jobs/ImageJobSubsystemBundle.cs, VisionWebSurface.cs, NativeGhBridgeRegistrar.cs; new Image/ImageFailureProjection.cs. |
| UI | Existing UI/Vision/Resources/app.js, plus executable tests under Rook.Tests/UI/Vision. |

Image paths above start at src/Rook/Services/Vision; handler paths at src/Rook/Handlers; bridge at src/Rook/InternalBridge; UI at src/Rook/UI/Vision. Each task specifies the exact files it owns.

## Verification conventions

Run commands from the worktree root in PowerShell. The task filters below intentionally build the test project, so newly added tests cannot accidentally run against stale binaries.

    dotnet --list-sdks
    node --version
    Test-Path 'C:/Program Files/Rhino 8/System/RhinoCommon.dll'
    dotnet restore src/Rook.Tests/Rook.Tests.csproj

Expected: usable SDK/Node, Rhino assembly present, restore succeeds. Missing prerequisites are reported as unavailable; they do not establish a passing test result. This machine was inspected during planning, but no builds/tests were run.

Use disposable GUID-named temp roots and explicit ArtifactStore/JSONL paths, following ImageJobManagerTests. Supply fake credential strings and injected HttpMessageHandler instances to every provider and downloader; unexpected HTTP requests fail the test. Use TaskCompletionSource with RunContinuationsAsynchronously or bounded barriers, never a real 180-second sleep. New UI tests use node:assert/strict and node:vm without adding packages.

Each commit step stages only its named task files after inspecting git diff. Do not stage unrelated user changes. A red run must fail because of the new behavior/assertion or missing planned interface, not because Rhino or an assembly is unavailable.

### Task 1: Safe routing contracts and backward-compatible ledger storage

**Files**

- Create: src/Rook/Services/Vision/Image/ImageRoutingContext.cs
- Create: src/Rook/Services/Vision/Image/ImageRoutingCodec.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobRecord.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecord.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactory.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/JsonlImageJobLedger.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobStatusResult.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobFetchResult.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobSubmitResult.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobCancelResult.cs
- Test: src/Rook.Tests/Services/Vision/Image/ImageRoutingContractTests.cs (new)
- Test: src/Rook.Tests/Services/Vision/Image/Jobs/JsonlImageJobLedgerTests.cs
- Test: src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs
- Test: src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobResultTypesTests.cs

**Interfaces**

- Consumes existing GenerationError, ImageJobRecord/ledger record, and schema version 1.
- Produces public immutable records ImageRouteReceipt(RequestedProvider, RequestedModel, EffectiveProvider, EffectiveModel, ProviderEndpoint, FallbackReason, Phase, GenerationDispatchAttempted), ImageCredentialFailure(Provider, Kind), and ImageRoutingContext(Route, CredentialFailure). Provider/model/endpoint fields are strings; reason/phase/kind use closed enums ImageFallbackReason, ImageExecutionPhase, ImageCredentialFailureKind.
- Declare ImageFallbackReason { GeminiKeyMissing, GeminiKeyRejected }, ImageExecutionPhase { Validation, Submission, Materialization, Publication, Interruption }, and ImageCredentialFailureKind { Missing, Rejected }. Enum values project exactly as the spec: gemini_key_missing/gemini_key_rejected; validation/submission/materialization/publication/interruption; missing/rejected.
- ImageRoutingContext.Route is ImageRouteReceipt? and CredentialFailure is ImageCredentialFailure?. Route may be null with non-null credential evidence: direct fal missing/401 failures have that shape. An empty context is permitted for a structured direct fal generic failure; it does not fabricate requested-provider/model or fallback reason.
- Declare ImageFalDispatchState { NotStarted, IntentRecorded, Attempted }, projected in the optional outer fal_dispatch_state field as not_started/intent_recorded/attempted. NotStarted is trusted only for new affected records written under this fenced dispatch contract; absent state is legacy/unrecorded evidence, not proof of no dispatch. IntentRecorded means a durable pre-send admission exists and an attempt may already have started. Attempted means the local send boundary was observed; neither latter value establishes acceptance, completion, or spend.
- ImageRoutingCodec.ToJson(ImageRoutingContext? context, ImageFalDispatchState? falDispatchState = null): JsonObject; TryRead(JsonObject source, string provider, string model, out ImageRoutingContext? context, out ImageFalDispatchState? falDispatchState, out string? field): bool. It validates optional fields independently. Receipt values must match the two closed mappings/endpoints and the enclosing job provider/model. Credential-only evidence must name the actual provider; the direct fal projections in this plan admit only the two new fal model IDs. Dispatch state is admitted only for those fal models or their eligible Gemini routes and cannot contradict a receipt's send flag.
- Append optional ImageRoutingContext? routing = null and ImageFalDispatchState? falDispatchState = null to ImageJobRecord's constructor. Add nullable ImageRoute, CredentialFailure and FalDispatchState positional fields with defaults to ImageJobLedgerRecord.
- Append optional ResolvedImageModel? effectiveModel = null, ImageRoutingContext? routing = null and ImageFalDispatchState? falDispatchState = null to ImageJobLedgerRecordFactory.WithState. Omitted values preserve prior context/state; a supplied context whose CredentialFailure is null explicitly clears credential evidence. Dispatch state must never regress from IntentRecorded/Attempted to NotStarted. When a receipt selects fal but registry resolution failed, derive provider/model from its validated closed mapping.
- Add nullable string Provider/Model, ImageRoutingContext? Routing and ImageFalDispatchState? FalDispatchState to status/fetch/submit/cancel results through WithRouting(string provider, string model, ImageRoutingContext? routing, ImageFalDispatchState? falDispatchState = null), each returning its own result type and leaving existing factories callable unchanged. List results already contain records.

- [ ] **Step 1: Write failing contract and round-trip tests**

Use the existing JSONL/factory fixtures. New test names and assertions:

    RoutingRoundTrip_KeepsRequestedAndEffectiveRoute:
        Assert.Equal("gemini", read.ImageRoute.RequestedProvider);
        Assert.Equal("fal", read.Provider);
        Assert.Equal("fal-ai/nano-banana-2/edit", read.ImageRoute.ProviderEndpoint);
        Assert.Equal(1, read.SchemaVersion);
    LegacyV1_HasNoFabricatedReceipt:
        Assert.Null(read.ImageRoute);
        Assert.Null(read.CredentialFailure);
    RoutingMismatchOrUnknownValue_IsReadError:
        Assert.Empty(result.Records);
        Assert.Single(result.Errors);
    GenericFailure_ClearsPriorCredentialEvidence:
        Assert.Null(next.CredentialFailure);
        Assert.Equal(prior.ImageRoute, next.ImageRoute);
    DirectFalCredentialEvidence_RoundTripsWithoutReceipt:
        Assert.Null(read.ImageRoute);
        Assert.Equal("fal", read.CredentialFailure.Provider);
        Assert.Equal(ImageCredentialFailureKind.Missing, read.CredentialFailure.Kind);
    DispatchIntent_RoundTripsWithoutClaimingSend:
        Assert.Equal(ImageFalDispatchState.IntentRecorded, read.FalDispatchState);
        Assert.False(read.ImageRoute.GenerationDispatchAttempted);

Parameterize malformed optional objects, wrong field types, unsupported reasons/phases/kinds/dispatch states, unknown fields, wrong endpoints, cross-model mappings, wrong credential provider, and enclosing provider/model mismatches. IntentRecorded with a false send flag is valid; Attempted with a false receipt flag and NotStarted with a true flag are not. Absent or explicit null optional fields provide no evidence; a credential-only object still creates context. Verify direct fal missing and rejected kinds round-trip with no receipt, generic failures clear evidence, and sanitization retains safe routing/dispatch state while dropping ProviderDetail. Inspect JSON for absence of prompts, URLs, bytes, account identifiers, and fake secrets.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageRoutingContractTests|FullyQualifiedName~JsonlImageJobLedgerTests|FullyQualifiedName~ImageJobLedgerRecordFactoryTests|FullyQualifiedName~ImageJobResultTypesTests"

- [ ] **Step 3: Implement the declared contracts and codec**

Keep JSON projection snake_case and optional fields additive. Factory/record conversions carry routing separately from sanitized GenerationError; do not extend the modality-neutral GenerationError or change video serializers. Reject malformed new fields with the existing ledger-read error mechanism. Add no attribution to legacy records.

- [ ] **Step 4: Repeat Step 2; require zero failures**
- [ ] **Step 5: Commit the named files**

    git commit -m "feat(vision): retain safe image routing context in job records"

### Task 2: Definitive Gemini credential evidence

**Files**

- Create: src/Rook/Services/Vision/Image/ImageCredentialErrors.cs
- Modify: src/Rook/Services/Vision/Image/Gemini/GeminiImageProvider.cs
- Test: src/Rook.Tests/Services/Vision/Image/GeminiImageProviderTests.cs

**Interfaces**

- Consumes Task 1's credential kind/provider contract.
- Produces ImageCredentialErrors constants GeminiMissing = "rook.gemini.key_missing", GeminiRejected = "rook.gemini.key_rejected", FalMissing = "rook.fal.key_missing", FalRejected = "rook.fal.key_rejected".
- ImageCredentialErrors.FromError(string provider, GenerationError error): ImageCredentialFailure? recognizes only the corresponding locally assigned marker.
- Existing GeminiImageProvider.SubmitAsync and MapProviderError signatures stay unchanged.

- [ ] **Step 1: Write failing provider tests using real Gemini encoding and TestHttpMessageHandler**

    BlankKey_IsLocalMissing:
        Assert.Equal(ImageCredentialErrors.GeminiMissing, failure.ProviderErrorCode);
        Assert.Empty(http.Requests);
    ValidErrorInfo_IsRejected:
        Assert.Equal(ImageCredentialErrors.GeminiRejected, failure.ProviderErrorCode);
        Assert.Single(http.Requests);
    UnadmittedResponse_HasNoCredentialEvidence:
        Assert.Null(ImageCredentialErrors.FromError("gemini", failure));

Use null/empty/whitespace keys; HTTP 400/401/403 plus the exact ErrorInfo @type/domain/reason and matching or absent metadata.service; HTTP 401 plus status UNAUTHENTICATED. Negative data includes 400/403 without evidence, wrong service/domain/type/reason, malformed JSON/envelopes/metadata, 402/429, 5xx containing the reason, model/policy failures, transport/timeouts, and cancellation. For Review Focus 1, send every reserved local marker as an arbitrary upstream status on an unadmitted response and prove it is not accepted as local evidence. Retain existing direct-success tests.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~GeminiImageProviderTests"

- [ ] **Step 3: Implement local evidence assignment**

Use IsNullOrWhiteSpace before HTTP. Parse ErrorInfo from error.details and service from its metadata; admission uses HTTP status plus well-typed response fields, never message text. Reserve marker strings: an unadmitted upstream code that equals one of them must be escaped/renamed in ProviderErrorCode while preserving useful safe diagnostic information. Store reads that throw remain failures, not missing-key evidence. Do not cache health or mutate credentials.

- [ ] **Step 4: Repeat Step 2; require zero failures**
- [ ] **Step 5: Commit the named files**

    git commit -m "fix(vision): classify definitive Gemini image credential failures"

### Task 3: Synchronous fal Nano Banana adapters and direct choices

**Files**

- Create: src/Rook/Services/Vision/Image/IImageDispatchAwareProvider.cs
- Create: src/Rook/Services/Vision/Image/Fal/FalNanoBananaPayload.cs
- Create: src/Rook/Services/Vision/Image/Fal/FalNanoBananaPricingModel.cs
- Modify: src/Rook/Services/Vision/Image/Fal/FalImageCapabilities.cs
- Modify: src/Rook/Services/Vision/Image/Fal/FalImageOptionsCodec.cs
- Modify: src/Rook/Services/Vision/Image/Fal/FalImageProviderRegistration.cs
- Modify: src/Rook/Services/Vision/Image/Fal/FalImageProvider.cs
- Test: src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderTests.cs
- Test: src/Rook.Tests/Services/Vision/Image/Fal/FalImageOptionsCodecTests.cs
- Test: src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderRegistrationTests.cs
- Test: src/Rook.Tests/Services/Vision/Image/Fal/FalNanoBananaPricingModelTests.cs (new)
- Test: src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs
- Test: src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs

**Interfaces**

- Consumes ImageCredentialErrors and the existing FalApiClient/SyncSubmitOutcome/remote artifact contracts.
- Produces constants NanoBanana2 = "fal-ai/nano-banana-2", NanoBananaPro = "fal-ai/nano-banana-pro" in FalImageCapabilities.
- IImageDispatchAwareProvider : IImageProvider adds Task<ProviderSubmitOutcome> SubmitAsync(ImageGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media, Func<CancellationToken, Task<GenerationError?>> generationDispatchPreparing, Action generationDispatchStarting, CancellationToken ct). FalImageProvider implements it; its existing overload remains usable. The awaited preparing callback can deny dispatch; starting observes the actual local send boundary.
- FalNanoBananaPayload.EndpointId(string model, bool hasMedia): string and Encode(ImageGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media): string own endpoint/payload construction.
- FalNanoBananaPricingModel(string modelId) implements existing IPricingModel<ImageGenerationRequest, ImageCapability>; PricingSource is "fal-nano-banana-unavailable-2026-10-12", UnitPrice/TotalUsd are null, IsExact false, no claimed actual spend.

- [ ] **Step 1: Write failing encoding/registration/pricing tests**

    NanoBananaPayload_PreservesMultiplicity:
        Assert.Equal(new[] { "data:image/png;base64,QQ==",
            "data:image/jpeg;base64,Qg==", "data:image/jpeg;base64,Qg==",
            "data:image/webp;base64,Qw==" }, imageUrls);
    DirectFalNanoBanana2_AcceptsHalfK:
        // The submitted direct fal request already has Resolution = "0.5K".
        Assert.Equal("0.5K", payload["resolution"].GetValue<string>());
        Assert.Equal(1, payload["num_images"].GetValue<int>());
        Assert.True(payload["limit_generations"].GetValue<bool>());
        Assert.Equal("png", payload["output_format"].GetValue<string>());
    DirectFalNanoBanana2_Rejects512:
        Assert.False(validation.Success);
        Assert.Equal("resolution", validation.Field);
        Assert.Empty(http.Requests);
    NanoBananaPro_RejectsExtremeRatio:
        Assert.False(validation.Success);
        Assert.Equal("aspect_ratio", validation.Field);
        Assert.Empty(http.Requests);
    Fal401_IsCredentialRejection_ButGeneric403IsNot:
        Assert.Equal("fal", rejected.Provider);
        Assert.Null(genericForbiddenEvidence);
    DispatchCallback_IsNotCalledForLocalFailure:
        Assert.Equal(0, dispatchPreparationCount);
        Assert.Equal(0, dispatchCount);
    DispatchPreparationFailure_DoesNotSend:
        Assert.Equal(1, dispatchPreparationCount);
        Assert.Equal(0, dispatchCount);
        Assert.Empty(http.Requests);

Cover both families' generation/edit endpoint IDs, empty media at provider level, auto/explicit aspect, all resolutions, primary source plus ordered/repeated refs, prompt text unchanged, omitted/false sync_mode, unchanged moderation defaults, and no upload/queue calls. Reject multiple primary sources, absent referenced bytes, or otherwise unaccounted-for media instead of dropping input. The catalog capability uses 0.5K for direct fal 2; only fallback translation converts Gemini 512. Registered models are Sync and have unavailable pricing with null monetary fields. Update exact model-count assertions by two without changing the provider count or default Gemini ordering.

For normalized fal evidence use a conservative local policy: blank key is missing; HTTP 401 from the fal generation endpoint is rejected; generic 403/402/422/429/5xx and message contents supply no credential evidence. This is an implementation policy for warnings, not a claim that every invalid fal key returns 401. Do not modify shared FalErrorMapper/video behavior. Verify zero/multiple images, malformed image URL/body, and unsupported data-URI output fail instead of silently taking a partial result.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~FalImageProviderTests|FullyQualifiedName~FalImageOptionsCodecTests|FullyQualifiedName~FalImageProviderRegistrationTests|FullyQualifiedName~FalNanoBananaPricingModelTests|FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~VisionProviderRegistrationsTests"

- [ ] **Step 3: Implement the adapter and registrations**

Add model-specific codec branches; retain FLUX/GPT behavior. New fal adapters validate their native resolutions and never translate 512. Build image_urls from the source-role entry followed by request.ReferenceImages lookups, never dictionary enumeration order or deduplication. Use https://fal.run plus the locally selected endpoint ID. Finish credential/payload validation, await generationDispatchPreparing, stop on its error, recheck cancellation, then invoke generationDispatchStarting immediately before PostJsonAsync. Thus missing-key/invalid-request failures never record dispatch intent and failed durable preparation never sends HTTP. Parse exactly one HTTPS remote image for the new models and return SyncSubmitOutcome. Leave legacy branches' result rules unchanged.

- [ ] **Step 4: Repeat Step 2; require zero failures**
- [ ] **Step 5: Commit the named files**

    git commit -m "feat(vision): add synchronous fal Nano Banana image models"

### Task 4: One shared image submission policy

**Files**

- Create: src/Rook/Services/Vision/Image/ImageExecutionContext.cs
- Create: src/Rook/Services/Vision/Image/ImageSubmissionExecutor.cs
- Test: src/Rook.Tests/Services/Vision/Image/ImageSubmissionExecutorTests.cs (new)
- Create test fixture: src/Rook.Tests/Services/Vision/Image/ImageFallbackFixture.cs

**Interfaces**

- Consumes Tasks 1–3, existing registry/ResolvedImageModel/options codecs.
- Produces public sealed record ImageExecutionSnapshot(ImageGenerationRequest? EffectiveRequest, ResolvedImageModel? EffectiveModel, ImageRoutingContext? Routing, ImageFalDispatchState? FalDispatchState), public sealed ImageExecutionContext, public sealed ImageSubmissionExecutor, and public sealed record ImageSubmissionResult.
- ImageExecutionContext(): initially empty; Snapshot(): ImageExecutionSnapshot; Initialize(ImageGenerationRequest request, ResolvedImageModel model): void; SelectFallbackTarget(ImageRouteReceipt route): void; SelectFallback(ImageGenerationRequest request, ResolvedImageModel model, ImageRouteReceipt route): void; SetPhase(ImageExecutionPhase phase): void; MarkFalDispatchIntentRecorded(): void; MarkGenerationDispatchAttempted(): void; SetCredentialFailure(ImageCredentialFailure? failure): void. Direct new fal initialization and fallback selection start FalDispatchState at NotStarted. Intent is marked only by the manager after its successful durable append; the send callback advances to Attempted and sets a receipt's send flag if a receipt exists. Neither method creates a fallback receipt for direct fal. SelectFallbackTarget publishes the safe receipt before registry resolution and clears effective request/model until resolved. Updates/read snapshots are thread-safe and scoped to one execution.
- ImageSubmissionExecutor(IImageProviderRegistry registry); Task<ImageSubmissionResult> SubmitAsync(ImageGenerationRequest request, ResolvedImageModel model, IReadOnlyDictionary<MediaRef, ResolvedMedia> media, ImageExecutionContext context, CancellationToken ct, Func<ImageExecutionSnapshot, CancellationToken, Task<GenerationError?>>? prepareEffectiveRouteAsync = null, Func<ImageExecutionContext, CancellationToken, Task<GenerationError?>>? prepareGenerationDispatchAsync = null). The second delegate owns durable fal intent; without it a synchronous handler has no durable job intent to claim.
- ImageSubmissionResult(ProviderSubmitOutcome Outcome, ImageExecutionSnapshot Execution); static ImageSubmissionExecutor.UsesExecutionDeadline(ResolvedImageModel model): bool selects exactly the two admitted Gemini and two new fal models.
- The internal ImageFallbackFixture(string? geminiKey = "fake-gemini", string? falKey = "fake-fal") owns disposable explicit temp storage and synthetic source/reference artifacts. Expose mutable string? GeminiKey/FalKey, ArtifactStore Store, DefaultImageProviderRegistry Registry, ImageSubmissionExecutor Executor, IReadOnlyDictionary<MediaRef, ResolvedMedia> Media, and IReadOnlyList<Guid> ParentArtifactIds. Request(string model, string resolution = "1K", string aspectRatio = "") returns ImageGenerationRequest; Start(string model) returns ImageJobStartRequest.
- The fixture file also defines internal ImageFallbackHttpHandler : HttpMessageHandler with Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? OnSendAsync and IReadOnlyList<RecordedHttpRequest> Requests backed by a concurrent recording queue. RecordedHttpRequest(Uri Uri, string Method, string? Body) captures content before disposal. Fixture properties GoogleHttp/FalHttp/DownloadHttp return that handler type; unconfigured sends fail. These handlers allow a real provider's SendAsync to be held or ignore cancellation without blocking the test controller. Provider key delegates read the fixture's mutable keys. Later handler tests use a fixture-local in-memory IGenerationSecretStore, following VisionHandlerTests, for matching catalog presence. Do not stub executor/provider outcomes or use production credential storage.

- [ ] **Step 1: Write failing real-provider executor tests**

    MissingGemini_FallsBackOnce:
        Assert.Empty(googleHttp.Requests);
        Assert.Single(falGenerationRequests);
        Assert.Equal("fal", result.Execution.EffectiveModel.ProviderName);
        Assert.Equal(ImageFallbackReason.GeminiKeyMissing, result.Execution.Routing.Route.FallbackReason);
    InvalidGemini_FallsBackOnce:
        Assert.Single(googleHttp.Requests);
        Assert.Single(falGenerationRequests);
    FallbackNanoBanana2_Translates512ToHalfK:
        Assert.Equal("512", requested.Resolution);
        Assert.Equal("0.5K", result.Execution.EffectiveRequest.Resolution);
        Assert.Equal("0.5K", capturedFalPayload["resolution"].GetValue<string>());
    DirectFalMissingOr401_HasCredentialEvidenceWithoutReceipt:
        Assert.Null(result.Execution.Routing.Route);
        Assert.Equal("fal", result.Execution.Routing.CredentialFailure.Provider);
    DirectFalGeneric403_HasNoCredentialEvidenceOrReceipt:
        Assert.Null(result.Execution.Routing.Route);
        Assert.Null(result.Execution.Routing.CredentialFailure);
    GoogleSuccessOrUnadmittedFailure_DoesNotFallback:
        Assert.Empty(falGenerationRequests);
    PreparationFailureOrCancellation_DoesNotDispatch:
        Assert.False(context.Snapshot().Routing.Route.GenerationDispatchAttempted);
        Assert.Empty(falGenerationRequests);
    KeyReplacement_IsUsedOnNextRequest:
        Assert.Null(second.Execution.Routing);
        Assert.Equal("gemini", second.Execution.EffectiveModel.ProviderName);

Exercise both model families, missing fal registration/key, generic fal failure, fal 401, Pro aspect rejection, unknown/custom Gemini, Vertex and other providers, direct fal with Google configured, failure inside SyncSubmitOutcome, and changed source paths after first resolution. A Gemini secret-read exception never admits fallback; a fal secret-read exception after selection keeps fal context without fabricating missing-key evidence. Resolve aliases using the existing handler path in Task 7, not a second executor alias implementation.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageSubmissionExecutorTests"

- [ ] **Step 3: Implement the closed policy**

Validate requested options and initialize context. Submit primary Google through its existing overload, permitting one mapped fallback only for Task 2's local evidence. Publish the fallback target before registry resolution, decode fal options and translate only Gemini Nano Banana 2's 512 to 0.5K, then validate and prepare the effective route. Direct new fal requests keep native 0.5K/1K/2K/4K options and skip Google/route switching.

Both fallback and direct new fal submission use the dispatch-aware overload. Its preparing callback invokes prepareGenerationDispatchAsync with the live execution context, if supplied; the manager must durably commit intent and update that same context before returning success. Its starting callback marks the local attempt/phase; pre-dispatch key/compatibility failures remain validation. Clear primary credential evidence when selecting fallback, and normalize direct fal failure evidence into ImageRoutingContext(null, evidence). Generic direct fal failures use an empty context for structured projection. Ordinary/custom/Enterprise paths retain legacy handling; direct fal never fabricates a fallback receipt. Expected secret-read exceptions retain actual provider context without becoming missing-key markers. Do not create/reset timers here.

- [ ] **Step 4: Repeat Step 2; require zero failures**
- [ ] **Step 5: Commit the named files**

    git commit -m "feat(vision): centralize the closed Gemini to fal fallback policy"

### Task 5: Ordered image-job commits and artifact ownership

**Files**

- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs
- Test: src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs
- Test: src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobLedger.cs

**Interfaces**

- Consumes Task 1's optional effectiveModel/routing factory arguments.
- Extend private TryTransitionWithLedger(ImageJobRecord prior, ImageJobState state, out ImageJobRecord next, out GenerationError? appendError, ProviderJobHandle? providerHandle = null, Guid? resultArtifactId = null, GenerationError? error = null, ResolvedImageModel? effectiveModel = null, ImageRoutingContext? routing = null, ImageFalDispatchState? falDispatchState = null, Func<bool>? completionAdmission = null): bool.
- Produce internal PrepareEffectiveRouteAsync(Guid jobId, ImageExecutionSnapshot execution, CancellationToken ct): Task<GenerationError?> using that same helper and a post-append cancellation check. Task 6 uses it as the executor preparation callback; Task 5 tests call it directly to control commit ordering.
- Produce internal PrepareGenerationDispatchAsync(Guid jobId, ImageExecutionContext context, CancellationToken ct): Task<GenerationError?>. Under the same per-job gate, check committed state/cancellation, append a Submitting entry with FalDispatchState.IntentRecorded, publish the committed record and call context.MarkFalDispatchIntentRecorded before releasing the gate. Return persistence/interruption errors to deny send. This is used for both new direct fal models and fallback; route may be null.
- Produce one ConcurrentDictionary<Guid, object> per-job gate table owned by the manager. Route changes reuse the Submitting state. All related helpers enter the same gate; nested calls use the same reentrant monitor, never a second ordering lock.
- Add internal Action<Guid>? BeforeTransitionGateForTests hook for the stale-route ordering. Reuse FakeImageJobLedger.BeforeAppend and existing BeforeCompleteTransitionForTests for the other orderings.

- [ ] **Step 1: Write failing deterministic ordering tests**

    CancellationCommitsBeforeStaleRoute:
        Assert.Equal(ImageJobState.Cancelled, live.State);
        Assert.Equal(ImageJobState.Cancelled, fresh.State);
        Assert.Equal(ImageJobState.Cancelled, ledger.AllRecords.Last().State);
    RouteAppendInProgress_CancellationWaitsAndWins:
        Assert.False(cancelTask.IsCompleted); // while route append is held
        Assert.Equal(ImageJobState.Cancelled, ledger.AllRecords.Last().State);
        Assert.Equal(ImageJobState.Cancelled, fresh.State);
    CompletionAdmittedBeforeCancellation_RetainsArtifact:
        Assert.Equal(ImageJobState.Complete, fresh.State);
        Assert.NotNull(store.Get(fresh.ResultArtifactId.Value));
    TerminalAppendFailure_DoesNotClaimDurableCancellation:
        Assert.NotNull(cancelResult.Error);
        Assert.NotEqual(ImageJobState.Cancelled, durable.State);
    DispatchIntentAppendFailure_DeniesSendAdmission:
        Assert.NotNull(prepareError);
        Assert.NotEqual(ImageFalDispatchState.IntentRecorded, durable.FalDispatchState);
        Assert.Equal(ImageFalDispatchState.NotStarted, context.Snapshot().FalDispatchState);

Use bounded barriers and call PrepareEffectiveRouteAsync for the route-only tests; they prove committed state ordering without pretending the manager is already wired to fallback. For route-first ordering, separately prove the execution signal is canceled while the cancel response waits. Test route/cancel/complete append failures, uncommitted artifact cleanup, no deletion of a successful completion, timestamp ties, and subsequent transitions retaining the receipt. Task 6 repeats the route scenarios with the real executor and explicitly asserts zero fal dispatch after cancellation/persistence failure.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageJobManagerTests"

- [ ] **Step 3: Implement the bounded lifecycle change**

Within the per-job gate, read committed state, reject terminal winners, check completion/send admission, build matching memory/durable candidates, append, then publish both _records and RunningJob.LatestRecord. Preparing the route and admitting generation are distinct commits: fal credential/payload checks occur before the latter, and a durable IntentRecorded entry must precede HTTP. Publish that intent into the live execution context inside the gate, even if cancellation arrives before the preparing callback returns. Merge dispatch state monotonically so a stale NotStarted snapshot cannot erase committed intent. Provider calls/downloads remain outside the gate. All terminal/diagnostic writes retain state; failed intent persistence denies send and does not claim a successful durable marker.

Signal affected synchronous jobs before waiting for their commit gate; do not introduce remote cancellation for the new models or change existing async-provider cancel protocol. Admit completion once under the gate. A caller whose artifact never committed owns its cleanup; a later losing cancellation cannot delete the committed winner. Preserve legacy async handles/provider behavior.

- [ ] **Step 4: Repeat Step 2; require zero failures**
- [ ] **Step 5: Commit the named files**

    git commit -m "fix(vision): serialize durable image job terminal transitions"

### Task 6: Manager execution context and one owned deadline

**Files**

- Create: src/Rook/Services/Vision/Image/Jobs/ImageExecutionBudget.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs
- Modify: src/Rook/Services/Vision/Image/Jobs/ImageJobSubsystemBundle.cs
- Modify: src/Rook/RookSubsystemRoot.cs
- Test: src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobFallbackTests.cs (new)
- Test: src/Rook.Tests/Services/Vision/Image/Jobs/ImageExecutionBudgetTests.cs (new)
- Test: src/Rook.Tests/RookSubsystemRootTests.cs

**Interfaces**

- Consumes executor/context and ordered transitions.
- ImageExecutionBudget(CancellationToken userCancellation, CancellationToken shutdown, CancellationTokenSource? deadline): IDisposable exposes Token and StopReason. ImageStopReason is None/UserCancellation/Shutdown/Deadline; the first observed signal wins unless a durable terminal transition already won. It owns/disposes the linked source and optional timer source. Deadline has a fixed nonretryable Interrupted diagnostic: "Image generation execution deadline exceeded (180s)."
- Append optional ImageSubmissionExecutor? submissionExecutor = null and Func<TimeSpan, CancellationTokenSource>? deadlineFactory = null to the manager's internal constructor. Defaults are the supplied registry's executor and duration => new CancellationTokenSource(duration). Tests inject manually canceled sources.
- Add ImageJobSubsystemBundle.Executor and an overload (IImageJobManager manager, IImageProviderRegistry registry, ImageSubmissionExecutor executor); retain the old two-argument constructor for existing callers, deriving its executor from that registry.
- RookSubsystemRoot constructs exactly one registry/executor pair, injects the executor into manager, and publishes it in the bundle. RunningJob retains Start unchanged plus a per-job ImageExecutionContext; remaining lifecycle uses its effective model/request after fallback.

- [ ] **Step 1: Write failing end-to-end manager/deadline tests**

    FallbackManager_RetainsEffectiveRouteAfterRestart:
        Assert.Equal("fal", status.Provider);
        Assert.Equal("fal-ai/nano-banana-pro", fresh.Model);
        Assert.Equal(start.ParentArtifactIds, artifact.ParentIds);
    QueueWait_DoesNotStartExecutionDeadline:
        Assert.Equal(0, waitingJobTimerStarts);
    NearExpiry_RejectionDoesNotResetBudget:
        Assert.Single(timerDurations);
        Assert.Equal(TimeSpan.FromSeconds(180), timerDurations[0]);
        Assert.Equal(ImageJobState.Interrupted, status.State);
        Assert.False(status.Error.Retryable);
    ExpiredBeforeSend_HasNoFalRequest:
        Assert.Empty(falGenerationRequests);
    AcceptedSubmitTokenCancellation_DoesNotCancelJob:
        Assert.Equal(ImageJobState.Complete, status.State);
    ConcurrentJobs_DoNotShareExecutionContext:
        Assert.Null(directGoogleStatus.Routing);
        Assert.Equal("fal", fallbackStatus.Routing.Route.EffectiveProvider);
    HeldFalResponse_SnapshotRestoresUnknownSubmission:
        Assert.Equal(ImageFalDispatchState.IntentRecorded, copiedLedgerRecord.FalDispatchState);
        Assert.False(copiedLedgerRecord.ImageRoute.GenerationDispatchAttempted);
        Assert.Equal(ImageJobState.Interrupted, restoredStatus.State);
        Assert.Equal(ImageFalDispatchState.IntentRecorded, restoredStatus.FalDispatchState);
        Assert.Contains("submission outcome is unknown", restoredStatus.Error.Message);
        Assert.False(restoredStatus.Error.Retryable);
        Assert.Empty(restoredFalGenerationRequests);
    DirectFal_HeldResponseAlsoHasDurableIntent:
        Assert.Null(copiedLedgerRecord.ImageRoute);
        Assert.Equal(ImageFalDispatchState.IntentRecorded, copiedLedgerRecord.FalDispatchState);

Use the real fixture providers/executor, synthetic download bytes and real temp JSONL. For the crash test, hold fal's response after its actual send boundary, copy only the physical ledger into an isolated temp root while the original worker remains held, construct a fresh manager on that snapshot and run its normal ReconcileInterruptedJobs/GetStatus path. Do not release or complete the original worker before copying, and do not restore from its in-memory context. Prove recovery retains requested/effective route, reports IntentRecorded uncertainty rather than treating false as unsent, and starts no cloud request. Repeat for direct fal with no receipt. Inject an intent-append failure and prove zero actual fal HTTP requests. Separately pause intent persistence, cancel, then release it and prove the final cancellation retains the intent marker and sends no fal request.

Manually expire the timer during Google, route/intent append, fal, materialization, artifact creation and each side of completion admission. Assert interrupted jobs have no published artifact; admitted successful completions retain theirs. Test cancellation/shutdown provenance, receipt/dispatch state on interrupted status and fresh reads, zero additional attempts, direct fal deadlines, and unchanged other models. Re-run both Task 5 race orderings with real fallback.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageJobFallbackTests|FullyQualifiedName~ImageExecutionBudgetTests|FullyQualifiedName~ImageJobManagerTests|FullyQualifiedName~RookSubsystemRootTests"

- [ ] **Step 3: Wire manager execution and budget lifetime**

Give RunningJob an independent user-cancellation source and use a separately linked user/shutdown token for queue waiting. Acquire the concurrency slot before starting the affected timer; preserve accepted-submit token independence. Route preparation calls PrepareEffectiveRouteAsync(jobId, execution, token). The provider's pre-send admission calls PrepareGenerationDispatchAsync(jobId, context, token); its durable intent must settle successfully before the actual send callback or HTTP. Keep local GenerationDispatchAttempted updates distinct from that persisted intent: while fal is held, the latest ledger may show false plus IntentRecorded, which means an attempt may have happened and never proves unsent.

Initialize new affected records' FalDispatchState to NotStarted, then retain monotonic state through every normal/terminal/failure/reconciliation write. On restart, an unfinished IntentRecorded or Attempted job becomes Interrupted with the fixed nonretryable diagnostic "Image job interrupted after fal dispatch admission; submission outcome is unknown. A deliberately new request may create another billed generation." Preserve its state and safe requested/effective context; do not resume/resubmit. Absent legacy state stays absent and supplies no negative evidence. For live terminal handling re-snapshot context, preserving at least the latest committed dispatch state if a race leaves an older snapshot. Pass the same budget token to downloads/guards/completion admission. Affected shutdown is Interrupted, user cancellation is Cancelled, and deadline is Interrupted/nonretryable; retain the deadline diagnostic for observed deadline expiry. Other models retain existing stop classification. Dispose queue/timer/token registrations in settlement.

Task 5's serialization applies to all racing writes, while the new execution deadline applies only to the closed four-model set. Fresh status/fetch/list records derive routing from persisted fields; do not rerun a completed or interrupted cloud request.

- [ ] **Step 4: Repeat Step 2; require zero failures**
- [ ] **Step 5: Commit the named files**

    git commit -m "feat(vision): execute image fallback jobs within one deadline"

### Task 7: Handler, catalog and both managed timeout projections

**Files**

- Create: src/Rook/Services/Vision/Image/ImageFailureProjection.cs
- Modify: src/Rook/Handlers/VisionHandler.cs
- Modify: src/Rook/Handlers/ImageJobOpHandler.cs
- Modify: src/Rook/UI/Vision/VisionWebSurface.cs
- Modify: src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs
- Test: src/Rook.Tests/Handlers/ImageFallbackHandlerTests.cs (new)
- Test: src/Rook.Tests/Handlers/VisionHandlerTests.cs
- Test: src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs
- Test: src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
- Test: src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs

**Interfaces**

- Consumes shared bundle.Executor, ImageExecutionContext/Snapshot, and ImageRoutingCodec.
- ImageFailureProjection.Build(GenerationError error, string provider, string model, ImageRoutingContext? routing, ImageFalDispatchState? falDispatchState = null): Dictionary<string, object?> returns code/safe message/retryable/field, actual local provider/model, and independently optional image_route/credential_failure/fal_dispatch_state. Provider/model come from the admitted model or validated fallback target, never upstream metadata. A null Route cannot suppress explicit credential evidence; a generic direct fal error omits both receipt and credential evidence while retaining actual provider/model. Unrelated legacy failures keep their existing shape.
- Append optional ImageSubmissionExecutor? imageSubmissionExecutor = null to VisionHandler's internal constructor chains. Standalone handlers derive one from their registry; both production BuildSharedVisionHandler helpers inject ImageJobs.Executor.
- Add internal DispatchAsync(string? body, CancellationToken cancellationToken, ImageExecutionContext imageContext): Task<ApiResponse>; existing public overload delegates with a fresh context. GenerateAsync's internal context-aware overload uses that context through publication.
- Add internal GenerateAsync(Dictionary<string, JsonElement> args, CancellationToken cancellationToken, ImageExecutionContext imageContext): Task<ApiResponse>; retain the existing two-argument overload as a delegate.
- Add optional ImageExecutionContext? imageContext = null to VisionWebSurface.DispatchWithTimeoutAsync and ExecuteAsyncApiResponseCallback; non-generate domains pass none. Native generate creates a request-local context and supplies it to both the handler and outer callback.
- Extract internal NativeGhBridgeRegistrar.RunVisionAsyncWithTimeout(string requestJson, Func<string, CancellationToken, Task<ApiResponse>> operation, TimeSpan timeout, ImageExecutionContext? imageContext = null): ApiResponse. The existing pointer-writing callback delegates to it; tests call the same production timeout logic with a short controlled timeout.
- Backend fallback_available descriptor: mapped provider_name/model_id, credential_availability/credential_message from fal status. Keep the requested Gemini credential_availability unchanged. A missing-required-secret descriptor therefore becomes usable only when its structured fallback is available; fal direct choices use their own status.

- [ ] **Step 1: Write failing actual envelope/catalog/timeout tests**

    SynchronousFallback_ArtifactMetadataUsesLocalEffectiveRoute:
        Assert.Equal("fal", artifact.Metadata["provider"].GetValue<string>());
        Assert.Equal("fal-ai/nano-banana-2", artifact.Metadata["model"].GetValue<string>());
        Assert.Equal("gemini", artifact.Metadata["requested_provider"].GetValue<string>());
    GenericFalFailure_KeepsRouteWithoutCredentialEvidence:
        Assert.Equal("fal", data["image_route"]["effective_provider"].GetValue<string>());
        Assert.Null(data["credential_failure"]);
    DirectFalMissingOr401_ProjectsCredentialWithoutReceipt:
        Assert.Equal("fal", data["provider"].GetValue<string>());
        Assert.Null(data["image_route"]);
        Assert.Equal("fal", data["credential_failure"]["provider"].GetValue<string>());
        Assert.Equal(expectedKind, data["credential_failure"]["kind"].GetValue<string>());
    DirectFalGeneric403_ProjectsProviderWithoutCredentialEvidence:
        Assert.Equal("fal", data["provider"].GetValue<string>());
        Assert.Null(data["image_route"]);
        Assert.Null(data["credential_failure"]);
    Catalog_FalOnlyDoesNotClaimGeminiKeyValid:
        Assert.Equal("missing_required_secret", gemini["credential_availability"]);
        Assert.NotEqual("missing_required_secret", gemini["fallback_available"]["credential_availability"]);
    NativeOuterTimeout_PreservesReceiptWithoutAwaitingLateTransport:
        Assert.False(response.Success);
        Assert.Equal("interrupted", data["code"].GetValue<string>());
        Assert.True(data["image_route"]["generation_dispatch_attempted"].GetValue<bool>());
        Assert.False(heldProviderTask.IsCompleted);

Cover both families and aliases, primary Google success, custom/unknown Vertex unchanged, repeated path/artifact references and parent IDs, settings changes, job projections and restart failures. Parameterize direct fal missing-key and HTTP 401 as expectedKind missing/rejected, with no image_route; direct generic 403 has neither receipt nor credential evidence. Assert missing-key makes zero HTTP calls and 401/403 make exactly one fal attempt with zero Google attempts. Exercise both synchronous and manager-backed projections and retain fal_dispatch_state on restored uncertainty. Inject fallback missing credentials, unsupported aspect, malformed result, failed download, cancellation and timeout. Assert no fake secrets/raw payloads escape.

For the native test, hold a real injected fal transport after its send callback, let the outer timeout return, then release the late response and prove no artifact is published. A timeout before context exists has no receipt. Verify panel timeout rewriting and native UTF-8 envelope projection preserve safe context; non-image domain wrappers and unrelated string errors retain current behavior.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageFallbackHandlerTests|FullyQualifiedName~VisionHandlerTests|FullyQualifiedName~ImageJobOpHandlerTests|FullyQualifiedName~VisionWebSurfaceTests|FullyQualifiedName~NativeGhBridgeRegistrarTests"

- [ ] **Step 3: Implement projections and synchronous execution**

Replace direct submission with the shared executor. New direct fal failures use structured projection even when Route is null: project credential evidence independently, and project generic 403 without invented evidence. Fallback artifact model is the admitted effective logical ID; upstream metadata cannot override it. Other success retains existing metadata behavior. Use effective publication guards, retain parents/prompt, catch cancellation with actual context and clean unpublished artifacts. Job operations project provider/model, independent receipt/evidence and fal_dispatch_state. Restored intent uncertainty remains visible through status/list/result errors rather than being flattened into a false send flag.

Catalog fallback_available is present only on the two Gemini descriptors; list direct fal entries intentionally after Gemini defaults. Follow existing secret-presence/status builders without decrypting keys for catalog checks or running probes.

The panel timeout wrapper retains safe provider/model/route/dispatch state but clears credential evidence when timeout replaces a failure. The native wrapper snapshots the request-local context after signaling timeout and returns immediately; it must not wait for the worker. Preserve structured direct fal timeout context without inventing a fallback receipt. Only generate receives this context; other domains remain unchanged. Native C++/Python forward envelopes without routing policy.

- [ ] **Step 4: Repeat Step 2; require zero failures**
- [ ] **Step 5: Commit the named files**

    git commit -m "feat(vision): project fallback attribution through managed image callers"

### Task 8: Executable panel behavior and final acceptance

**Files**

- Modify: src/Rook/UI/Vision/Resources/app.js
- Create: src/Rook.Tests/UI/Vision/image-fallback.test.cjs
- Create: src/Rook.Tests/UI/Vision/Fixtures/image-fallback-bridge.json
- Test: src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
- Test: src/Rook.Tests/Handlers/ImageFallbackHandlerTests.cs

**Interfaces**

- Consumes Task 7's descriptor/bridge/job shapes and artifact metadata.
- Extend normalizeImageModelDescriptor/normalizeLegacyAvailableModel to retain fallback_available.
- Add hasAvailableImageFallback(model): boolean and imageResultNotice(resultOrArtifact): string; existing effectiveCredentialAvailability/validation/disable helpers use the primary-or-fallback availability without declaring Gemini valid.
- bridgeCall retains provider/model, optional image_route, independent credential_failure and fal_dispatch_state on Error; awaitImageJobResult preserves those terminal fields. Identify structured image context from the actual provider/model contract, not from receipt presence. Generate/Studio warn only the provider named by explicit credential_failure; generic structured errors mark neither key invalid. A null/absent Route with fal credential evidence is valid and requires no fallback label.
- The checked-in bridge fixture is generated by a named managed test WriteFallbackBridgeFixtureIfRequested when ROOK_WRITE_IMAGE_FALLBACK_FIXTURE=1. It uses real handler/catalog/manager projections with transport-boundary fixtures. Default runs assert the checked-in JSON matches fresh normalized projections and do not modify files. Exclude volatile IDs/timestamps/absolute temp paths from comparison, without removing routing, credential, capability or result fields.

- [ ] **Step 1: Write failing executable JavaScript tests and projection-fixture test**

Load the actual app.js in node:vm with a small fake DOM and stub rookBridge serving Task 7's real projected fixture. Invoke its real normalization, selection, validation, submit, bridge-error and result-rendering functions. Stub only host DOM/bridge plumbing, never the availability or routing decisions.

    GeminiFalOnly_RemainsSelectable:
        assert.equal(shouldDisableGenerateModel(model), false);
        assert.equal(shouldDisableStudioModel(model), false);
    NeitherCredential_BlocksSubmission:
        assert.equal(submitCalls, 0);
    GenericFal403_DoesNotInvalidateCredentials:
        assert.equal(sessionValidationBySecret.size, 0);
        assert.equal(submitCalls, 1);
    Fal401_WarnsOnlyFal:
        assert.equal(sessionValidationBySecret.get(falOverlayKey), 'invalid');
        assert.equal(sessionValidationBySecret.has(geminiOverlayKey), false);
    DirectFalMissingKey_WarnsConfigurationWithoutFallbackReceipt:
        assert.equal(error.image_route == null, true);
        assert.equal(error.credential_failure.kind, 'missing');
        assert.notEqual(sessionValidationBySecret.get(falOverlayKey), 'invalid');
        assert.equal(sessionValidationBySecret.has(geminiOverlayKey), false);
    DirectFal401_WarnsOnlyFalWithoutFallbackReceipt:
        assert.equal(error.image_route == null, true);
        assert.equal(sessionValidationBySecret.get(falOverlayKey), 'invalid');
        assert.equal(sessionValidationBySecret.has(geminiOverlayKey), false);
    DirectFal403_HasNoCredentialWarningOrFallbackReceipt:
        assert.equal(error.image_route == null, true);
        assert.equal(error.credential_failure == null, true);
        assert.equal(sessionValidationBySecret.size, 0);
    RestoredDispatchIntent_DoesNotImplyUnsentOrRetry:
        assert.equal(error.fal_dispatch_state, 'intent_recorded');
        assert.match(error.message, /submission outcome is unknown/);
        assert.equal(extraSubmitCalls, 0);
    FallbackResults_ShowProviderNotice:
        assert.equal(generateStatus.textContent, 'Generated with fal.ai');
        assert.equal(studioStatus.textContent, 'Generated with fal.ai');

Run direct fal missing/401/generic-403 cases through real managed fixture projections and the actual Generate/Studio sync/job error consumers. To reach a missing-key backend failure through UI, simulate a selectable stale catalog followed by key removal before submit; separately keep fresh missing-key choices disabled. Verify actionable fal configuration text, only fal's explicit rejection warning, no Gemini warning, and no fabricated fallback notice. Also cover restored intent uncertainty/no retry, incompatible ratio, failed materialization, timeout, text-probe overlay, refreshed keys, preserved selection and single bridge submission.

- [ ] **Step 2: Run the red tests**

    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageFallbackHandlerTests"
    node src/Rook.Tests/UI/Vision/image-fallback.test.cjs

- [ ] **Step 3: Implement the UI consumers**

Keep workflows and selection. Retain independent provider/model, routing, credential and dispatch fields through bridge/job errors and result rendering. Structured failures use explicit credential evidence without requiring a receipt; missing produces configuration guidance, rejection marks only that provider, generic 403 marks neither. Display restored unknown-outcome text with no automatic retry or new confirmation flow. Success fallback notices require a real fallback receipt/metadata, not merely provider fal. Keep unrelated legacy handling scoped.

- [ ] **Step 4: Generate and inspect the real-projection fixture**

Generate it once with the opt-in flag, remove that flag in finally even if the test fails, then use default assertion-only fixture tests.

    $env:ROOK_WRITE_IMAGE_FALLBACK_FIXTURE = '1'
    try {
        dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~WriteFallbackBridgeFixtureIfRequested"
        if ($LASTEXITCODE -ne 0) { throw 'Fixture generation failed.' }
    } finally { Remove-Item Env:ROOK_WRITE_IMAGE_FALLBACK_FIXTURE }

- [ ] **Step 5: Repeat Step 2; require zero failures**
- [ ] **Step 6: Run final managed builds and acceptance/regressions**

    dotnet build src/Rook/Rook.csproj -c Debug -f net48
    dotnet build src/Rook/Rook.csproj -c Debug -f net7.0
    dotnet build src/Rook/Rook.csproj -c Debug -f net8.0
    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "(FullyQualifiedName~Services.Vision.Image|FullyQualifiedName~VisionProviderRegistrationsTests|FullyQualifiedName~VisionHandlerTests|FullyQualifiedName~ImageFallbackHandlerTests|FullyQualifiedName~ImageJobOpHandlerTests|FullyQualifiedName~NativeVisionDispatchSourceTests|FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~VisionWebSurfaceTests|FullyQualifiedName~RookSubsystemRootTests)&FullyQualifiedName!~LiveSmoke"
    dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~VertexDispatchAuthorizationTests|FullyQualifiedName~VertexBindingV2Tests|FullyQualifiedName~VertexVeoTests|FullyQualifiedName~VertexVeoManagerAcceptanceTests|FullyQualifiedName~VideoOpHandlerTests|FullyQualifiedName~GuardedVideoJobManagerTests"
    node src/Rook.Tests/UI/Vision/image-fallback.test.cjs
    git diff --check

Expected: all three builds succeed, tests exit zero, no unexpected skips or live requests, UI assertions pass, whitespace check clean. The filters cover existing Gemini, fal FLUX/GPT, Replicate, image manager, catalog/root/native dispatch and the named Enterprise authorization/publication suites; live smoke classes are excluded. Report preexisting failures and unavailable prerequisites explicitly. No native/BIM build, deployment or billed smoke run is part of acceptance.

- [ ] **Step 7: Commit the named UI/fixture/test files after verification**

    git commit -m "feat(vision): keep Nano Banana choices usable with fal fallback"

## Coverage and handoff

| Spec acceptance | Owning tasks |
|---|---|
| 1–4: missing/rejected keys, exclusions, no loop, replacement key | 2, 3, 4, 7 |
| 5: native fal options; executor-only 512 translation; bytes/multiplicity | 3, 4, 7 |
| 6: lineage, independent credential evidence, durable intent/restart | 1, 5, 6, 7 |
| 7: route/intent append failure, races, held-response crash snapshot | 5, 6 |
| 8–9: direct/fallback UI errors, selectable choices, notices/no retry | 7, 8 |
| 10: deadline, queue exclusion, token ownership, late outcomes | 6, 7 |
| 11: existing providers, native forwarding, Enterprise guards | 7, 8 |

Inline plan self-review updated on 2026-10-12: every acceptance case and the three subsequent review findings have owning tasks/assertions; nullable receipt and independent credential/dispatch fields are consistent across codec, executor, manager and UI; durable intent precedes fal HTTP and a held-response ledger-copy test proves conservative restart behavior; only the executor translates 512. The five Review Focus cases remain assigned. Native timeout changes are managed-only; exact existing paths/build targets were checked; regression commands include Enterprise coverage and exclude live smoke. Execution stays sequential across shared contracts and lifecycle ownership.

After implementation, report actual command outcomes and remaining risks; mocked verification establishes local routing/lifecycle behavior, not funded account access or image quality. The present artifact is a plan only. Human review of this plan and selection of its execution method are required before product implementation.
