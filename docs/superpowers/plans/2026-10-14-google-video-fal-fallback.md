# Google Veo to fal.ai Video Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Keep compatible Veo 3.1 requests usable with the fal.ai credential when Google's credential is missing or definitively rejected, while preserving request meaning, confirmed pricing, durable uncertainty, cancellation, and artifact ownership.

**Architecture:** A submission coordinator selects and validates candidates; `VideoJobManager` owns each job's effective binding, quote, deadline, stop decision, ledger writes, and publication. Providers own transport and parsing. Existing native routes and the managed callback bridge carry additive evidence to the Video panel and Python MCP tools.

**Tech Stack:** Windows, C# net48, existing System.Text.Json/HttpClient/System.Drawing, xUnit, embedded JavaScript with Node's test runner, existing Python pytest environment. No new dependencies or provider SDK.

**Spec:** [Approved design at `e5b79f0c`](../specs/2026-10-14-google-video-fal-fallback-design.md). Read it with this plan. Preserve the prompt fallback commits already on `codex/vision-prompt-fal-fallback`; main currently lacks those commits.

**Execution:** The user previously chose native execution in this chat followed by an independent final review. Preserve that choice. This document needs human review before product edits. Spec approval authorizes planning only.

## Global Constraints

- Google-first routing affects only `veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`, and `veo-3.1-lite-generate-preview`; corresponding direct fal IDs are `fal-ai/veo3.1`, `fal-ai/veo3.1/fast`, and `fal-ai/veo3.1/lite`. No tier/family substitution.
- New fal Veo submissions require authoritative endpoint-continuity evidence. Existing candidate schemas and a successful probe do not resolve the published retirement notices. Unverified/expired bindings cannot submit.
- One **20-minute** budget starts at durable queued admission and includes queue wait, resolution/uploads, both possible attempts, polling, fetching, materialization, sidecars, and publication. Cleanup has a separate maximum **30-second** budget.
- First observed user/deadline/shutdown stop wins atomically and signals execution cancellation immediately, without waiting for a gate, persistence, or cleanup. Durable acknowledgement still requires a successful commit.
- One Rook job ID, timestamp, concurrency slot, quote, and timer survive fallback. No automatic generation retry, provider switch after acceptance/uncertainty, restart resume, or bridge-error replay.
- Fal profile: `generate_audio: true`, `auto_fix: false`, documented default moderation value `"4"`; send `X-Fal-No-Retry: 1`. Revalidation must establish these fields for every enabled endpoint.
- PNG/JPEG/WebP inputs: at most **8,000,000 bytes**, shorter dimension at least **720**. I2V and both interpolation frames exactly match selected 16:9 or 9:16 by 64-bit cross multiplication. References use a separately verified framing policy.
- Durations **4/6/8**, one output, aspect **16:9/9:16**; Standard/Fast **720p/1080p/4k**, Lite **720p/1080p**; require eight seconds for 1080p/4k/references and at most three ordered references. Reject seeded references under the candidate schemas.
- Preserve exact prompt, input roles/order/repeats, artifact parents, supplied options and normalized options. No implicit crop/pad/resize, shortened output, dropped seed/options, or prompt enhancement during routing.
- Bind media confirmation and every affected upload/payload to one immutable prepared-media snapshot. A later source read cannot substitute for proof of the bytes actually prepared; persist their ordered digests, never their raw bytes.
- Preserve schema-1 ledger records and existing `provider_handle`. Add versioned extensions; unknown/corrupt critical extensions cannot authorize provider work. Legacy jobs do not acquire fallback retrospectively.
- Estimates are decimal USD estimates, not charges. Unknown pricing blocks submission. Fingerprint-plus-cap detects snapshot changes even below the cap; legacy cap-only and unbounded contracts stay distinct.
- Credentials, raw provider bodies, exception text, and unnecessary signed URLs must not enter public receipts/errors/logs. Direct fal credential evidence does not require a fallback receipt.
- Keep RookNative the sole HTTP owner; add no route/server/webhook/native project configuration. Preserve Google/Vertex/Wan/Seedance/Kling and image/prompt behavior. Vertex local cancellation must remain local.
- No automatic live/billed requests, merge, push, release, or deployment follows plan approval. Use the repository deployment skill/script when deployment is authorized; Python payload changes require more than managed-only copying.

## Review Focus

1. An omitted people control differs from an explicit value equal to its default; test provenance through request parsing, Google payload, fallback, and fingerprints (Tasks 2, 3, 9).
2. A source artifact changes A→B→A around resolution/preparation; admission must validate the immutable prepared bytes as well as current source state, never validate A while sending B (Tasks 2, 3, 4, 7).
3. A stop arrives while dispatch-intent or terminal persistence holds a lock; signal execution immediately and report pending durability without admitting send or publication (Tasks 5, 7).
4. A fal result supplies a valid HTTPS URL for a different application/request ID; reject it before attaching credentials or downloading media (Task 4).
5. Two jobs share a transport/provider name while taking different routes; their binding, handles, quote, price, timer, and stop state must stay independent, including restart (Tasks 7, 8).

## File and responsibility map

All paths below are relative to `C:/Users/aryan/.codex/worktrees/vision-prompt-fal-fallback/Rook`. A task's file list is its staging boundary. Files named **Create** do not exist at the approved baseline.

| Boundary | Files and responsibility |
| --- | --- |
| Evidence admission | Create `docs/superpowers/research/2026-10-14-veo-provider-bindings.md`: per-binding official evidence, continuity, schemas, lifecycle roots, pricing, preprocessing, and cutoffs. |
| Request and candidates | Create `src/Rook/Services/Vision/Video/VideoRequestIntent.cs`, `VideoPreparedMediaSnapshot.cs`, `VideoSubmissionCoordinator.cs`; create `Video/Fal/FalVeoBindingCatalog.cs`, `FalVeoOptions.cs`, `FalVeoOptionsCodec.cs`, `FalVeoCompatibility.cs`, `FalVeoProviderRegistration.cs`: immutable media ownership, profiles, provenance, mapping, conditional compatibility. |
| Quotes | Create `Video/VideoRouteQuote.cs`, `VideoRouteQuoteService.cs`, `VideoEstimateFingerprint.cs`: canonical candidate snapshot and confirmation validation. |
| Transport | Create `Video/Fal/FalVeoQueueAdapter.cs`, `Video/IPreparedMediaVideoProvider.cs`; extend existing `FalVideoProvider`, source-frame transport, `VeoProvider`/`VeoClient`, shared fal header factory, and error conversion without changing old payloads. |
| Durable execution | Create `Video/VideoExecutionSnapshot.cs`, `VideoExecutionBudget.cs`; extend `JsonlVideoJobLedger` durability and existing manager transition helpers. |
| Orchestration | Extend `VideoJobManager`, `VideoSubsystemFactory`, `VisionProviderRegistrations` and result DTOs; create `Video/IVideoConfirmedJobManager.cs`. Manager is the only ledger writer. |
| Publication | Create `Video/VideoPublicationService.cs`; extend manager publication, `VisionHandler` artifact visibility, and `VisionWebSurface` direct blob streaming with the same durable-completion predicate; retain existing materializer and sidecar bounds. |
| Consumers | Extend `Handlers/VideoOpHandler.cs`, `UI/Vision/VisionWebSurface.cs`, `UI/Vision/Resources/app.js`, `index.html`, Python tool schema/dispatch contracts. Audit native `Handlers/VisionHandler.cpp` passthrough without a planned ABI change. |
| Tests | New focused managed test files below, existing provider/manager/handler regressions, actual VideoTab VM tests, shared managed-envelope fixtures, Python contract tests. |

## Test conventions

Managed commands run from the worktree using `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter '<filter>' --logger 'console;verbosity=minimal'`. Clearing `RhinoPluginDir` prevents test builds from deploying assemblies. Each task gives its filter; use the same command for red and green. Red may initially be a missing-symbol compile failure for a new interface; after it compiles, demonstrate the relevant behavioral failure before completing implementation.

Use temp artifact stores and real temp JSONL ledgers for restart tests, never `%APPDATA%/Rook`. Fake transports, injected clocks/timers, and `TaskCompletionSource` barriers use asynchronous continuations; no network, sleeps as race synchronization, or real 20-minute waits. Named test assertions below specify observable contracts; setup uses existing fixtures or helpers local to that test file.

Every implementation task ends by staging only its listed production/test files, running `git diff --cached --check`, inspecting the staged diff, and committing with its supplied message. Do not stage unrelated edits. Task 1 is documentation-only and has no runtime red/green cycle.

---

### Task 1: Establish the provider admission evidence

**Files:** Create `docs/superpowers/research/2026-10-14-veo-provider-bindings.md`; revise the approved spec only if identity or semantics change, then obtain renewed spec review before using that change.

**Interfaces:** Consumes spec sections 2/5/6/10/12. Produces an evidence table with exact model/tier/mode, submit URL, lifecycle root and allowed origins, schema/profile/framing/pricing revision, documentation URLs, verification date, continuity evidence, and UTC new-submission cutoff. A row without continuity evidence is `unverified`, never `enabled`.

- [x] Recheck official Google [Veo documentation](https://ai.google.dev/gemini-api/docs/veo) for all three primary IDs and long-running REST operation shapes. Record actual submit/status/result/cancel contracts rather than copying old repository comments.
- [x] Recheck official fal [Standard](https://fal.ai/models/fal-ai/veo3.1/api), [Fast](https://fal.ai/models/fal-ai/veo3.1/fast/api), [Lite](https://fal.ai/models/fal-ai/veo3.1/lite/api), all mode pages linked in spec section 5, and [queue documentation](https://fal.ai/docs/documentation/model-apis/inference/queue). Obtain authoritative successor or continued-support evidence resolving retirement for each enabled tier/mode. Revalidate pricing and preprocessing independently per binding. No paid probe or external message is authorized here.
- [x] Record unresolved facts explicitly. The approved spec records November 17, 2026; a later search-index excerpt for Fast I2V advertises October 22, 2026, while direct page retrieval failed during planning. This is unresolved evidence, not a verified replacement date. Read the actual authoritative pages before adopting any cutoff; use the start of their UTC retirement date and the earliest applicable cutoff conservatively. Do not claim continuity from search excerpts.
- [x] Apply the execution gate: if continuity remains unresolved, keep all affected production bindings unavailable. Offline implementation of disabled bindings may proceed after plan approval, but enabling submissions and claiming feature completion remain blocked. If successor identity/options/framing/lifecycle/rates differ, revise and reapprove the spec and relevant plan tasks before implementing that binding. Other independently proven bindings may be admitted individually; never substitute tiers.
- [x] Commit the evidence document with `git add -f docs/superpowers/research/2026-10-14-veo-provider-bindings.md` and message `docs: record Veo provider admission evidence`. Expected review result: every enabled row has complete primary-source evidence; unresolved rows are clearly disabled.

### Task 2: Preserve request intent and resolve compatible tier bindings

**Files:** Create `VideoRequestIntent.cs`, `VideoPreparedMediaSnapshot.cs`, `VideoSubmissionCoordinator.cs`, `Fal/FalVeoBindingCatalog.cs`, `Fal/FalVeoOptions.cs`, `Fal/FalVeoOptionsCodec.cs`, `Fal/FalVeoCompatibility.cs`, `Fal/FalVeoProviderRegistration.cs` under `src/Rook/Services/Vision/Video/`. Test: create `src/Rook.Tests/Services/Vision/Video/Fal/FalVeoCompatibilityTests.cs`, `src/Rook.Tests/Services/Vision/Video/VideoRequestIntentTests.cs`, and `src/Rook.Tests/Services/Vision/Video/VideoPreparedMediaSnapshotTests.cs`.

**Interfaces:** All new orchestration types are internal with defensive copies of supplied JSON/lists.

- Produces `VideoRequestIntent(VideoGenerationRequest Request, JsonObject SuppliedOptions, bool PersonGenerationSupplied)`; `VideoRequestIntent.Normalize(VideoGenerationRequest request, JsonObject suppliedOptions) -> VideoRequestIntent`. Only affected Google IDs accept omission and fill `AllowAll` for T2V without media or `AllowAdult` for image-conditioned modes. A legacy typed `VeoOptions` call is explicit.
- Produces sealed `VideoPreparedMediaSnapshot.Capture(VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolved) -> VideoPreparedMediaSnapshot` and sealed `VideoPreparedMediaSlot` with read-only `string Role`, `MediaRef Ref`, `string MimeType`, `string Sha256`, `int ByteLength`. `IReadOnlyList<VideoPreparedMediaSlot> Slots` is a defensive read-only ordered list, including repeated references. Each slot supplies `CopyBytes() -> byte[]` and `OpenRead() -> Stream`; the former returns a new copy and the latter is read-only with no exposed buffer. Capture owns deep copies of resolved byte arrays before computing SHA-256; neither resolver buffers, dictionaries nor callers can mutate the stored bytes/digests. `ToResolvedMedia() -> IReadOnlyDictionary<MediaRef, ResolvedMedia>` returns disposable working copies for existing pure validators, never the snapshot's buffers. Repeated slots may share privately owned immutable content, never mutable source arrays.
- Produces `FalVeoBinding` with string `ModelId`, `SubmitEndpoint`, `LifecycleRoot`, `ProfileRevision`, `FramingRevision`, `PricingSource`, `PricingRevision`; `VideoCapability Capability`; `IReadOnlyDictionary<string, decimal> RatesUsdPerSecond`; `Uri DocumentationSource`; `DateTimeOffset VerifiedOnUtc`; `bool ContinuityVerified`, `SupportsSeed`; and `DateTimeOffset? NewSubmissionCutoffUtc`. Framing policy is an enum with `ExactSelectedRatio` and a separately reviewed reference policy, never an undocumented permissive default.
- Produces `FalVeoBindingCatalog.Resolve(VideoGenerationRequest request, DateTimeOffset now) -> (FalVeoBinding? Binding, GenerationError? Error)`; `GetCandidate(VideoGenerationRequest request) -> (FalVeoBinding? Binding, GenerationError? Error)` returns known profile data even when unavailable for quote projection. Production catalog is immutable, seeded only by Task 1 evidence; tests inject documented-shaped active/expired fixtures.
- Produces `FalVeoOptions : ProviderOptions` and its dedicated `IProviderOptionsCodec`; accept only reviewed fixed-profile values or omission, reject unknown/conflicting fields. No Google people field is accepted as equivalent.
- Produces `FalVeoCompatibility.Validate(VideoRequestIntent intent, FalVeoBinding binding, IReadOnlyDictionary<MediaRef, ResolvedMedia> media) -> GenerationError?`; errors name the incompatible field.
- Produces `VideoRouteCandidate(ResolvedVideoModel Model, VideoGenerationRequest Request, FalVeoBinding? Binding, VideoCostEstimate? Estimate, GenerationError? EligibilityError)` in `VideoSubmissionCoordinator.cs`. Ineligible candidates remain visible but are never dispatchable; unknown pricing is ineligible, never zero.
- Produces `VideoSubmissionCoordinator(IVideoProviderRegistry registry, FalVeoBindingCatalog catalog, IGenerationSecretStore secrets)` and `ResolveCandidates(VideoRequestIntent intent, IReadOnlyDictionary<MediaRef, ResolvedMedia> media, DateTimeOffset now) -> IReadOnlyList<VideoRouteCandidate>`. It validates Google independently and marks fal incompatibility conditionally; it does not send requests or append records.
- `FalVeoProviderRegistration(FalVideoProvider provider, FalVeoBindingCatalog catalog)` supplies dedicated codec/capability/pricing while sharing the existing fal provider instance. Register it only when the transport delegate is ready in Task 4/7.

- [x] Add named tests `OmittedPeopleControlRetainsProvenance`, `ExplicitDefaultBlocksOnlyFallback`, `TierAndModeMappingIsExact`, `AllInputsValidateBeforeFirstUpload`, `SquareAndNearRatioSourcesRejectWithoutBlockingGoogle`, and `OrderedRepeatedReferencesSurviveTranslation`. Their assertions include:

```csharp
Assert.False(omitted.PersonGenerationSupplied);
Assert.Equal(PersonGenerationPolicy.AllowAdult, ((VeoOptions)omitted.Request.Options).PersonGeneration);
Assert.True(explicitDefault.PersonGenerationSupplied);
Assert.Null(validGoogleError); // explicit people policy or square source may still use Google
Assert.Equal("start_frame", squareFalError.Field); // 1024x1024, all three tiers
Assert.Equal("end_frame", badInterpolationEndError.Field);
Assert.Equal(new[] { referenceA, referenceB, referenceA }, translated.ReferenceFrames);
Assert.Equal(0, uploads);
```

Add `PreparedSnapshotOwnsBytesAndOrderedDigests`: capture A, mutate the original resolver array/dictionary and a returned `CopyBytes()` buffer to B, and assert snapshot reads and SHA-256 still equal A; its stream rejects writes and exposes no mutable buffer. Assert first/last roles and repeated reference slots retain their identities/order. Missing resolved inputs fail capture rather than disappearing.

Use actual decoded 1280x720/720x1280 PNGs as positive inputs, orientation mismatch and 1281x720 as negatives, corrupted image bytes/MIME mismatch, exactly 8,000,000 versus 8,000,001 bytes, and shorter-side 719 versus 720. Reject seeded references, Lite references, blank fal prompt, mixed roles, extra output, missing frames, unknown options, unsupported duration/resolution, and unverified/expired bindings. Retain all original parent IDs and duplicate slots. A byte/size failure in the last input must prevent even the first upload.

- [x] Run managed filter `FullyQualifiedName~FalVeoCompatibilityTests|FullyQualifiedName~VideoRequestIntentTests|FullyQualifiedName~VideoPreparedMediaSnapshotTests`. Expected red: new types unavailable, then incompatible inputs accepted/mapping absent and mutable media aliases retained.
- [x] Implement the listed interfaces and exact spec mappings. Use existing image decoding and media-resolution patterns; perform 64-bit ratio checks after positive decoded dimensions. Keep Google-only compatibility separate; no media transformations. Candidate rate constants are disabled fixture data until Task 1 admission, with Standard `.40/.40/.60`, Fast `.15/.15/.35`, Lite `.05/.08` USD/sec, unless newly reviewed evidence changes them.
- [x] Rerun the same filter; expected all pass. Commit `feat: define Veo routing intent and compatible fal bindings` with this task's exact file list.

### Task 3: Bind confirmation to a canonical route quote

**Files:** Create `src/Rook/Services/Vision/Video/VideoRouteQuote.cs`, `VideoRouteQuoteService.cs`, `VideoEstimateFingerprint.cs`; test create `src/Rook.Tests/Services/Vision/Video/VideoRouteQuoteTests.cs`. Retain `VideoCostEstimator` for legacy providers.

**Interfaces:** Consumes Task 2 candidate type/resolution, immutable prepared-media snapshots, and `IMediaResolver.ResolveAllAsync(IReadOnlyList<MediaRef>, CancellationToken)`.

- Produces `VideoSubmitConfirmation(string? EstimateFingerprint, decimal? MaxEstimatedCostUsd)`.
- Defines `VideoRouteQuote(JsonObject CanonicalSnapshot, IReadOnlyList<VideoRouteCandidate> Candidates, VideoCostEstimate PrimaryEstimate, decimal MaximumEstimatedCostUsd, string EstimateFingerprint)` and `VideoRouteQuoteResult(VideoRouteQuote? Quote, GenerationError? Error)`; successful values cannot contain an error.
- Produces `VideoRouteQuoteService(VideoSubmissionCoordinator coordinator, IMediaResolver mediaResolver, IVideoJobClock clock)`, `QuoteAsync(VideoRequestIntent intent, CancellationToken ct) -> Task<VideoRouteQuoteResult>`, `QuotePreparedAsync(VideoRequestIntent intent, VideoPreparedMediaSnapshot preparedMedia, CancellationToken ct) -> Task<VideoRouteQuoteResult>`, `ValidatePreparedMedia(VideoPreparedMediaSnapshot preparedMedia, VideoRouteQuote quote) -> GenerationError?`, and `ValidateConfirmation(VideoRouteQuote current, VideoSubmitConfirmation confirmation, VideoRouteCandidate? selected) -> GenerationError?`. `QuoteAsync` captures its resolved bytes then delegates canonicalization to `QuotePreparedAsync`; the latter performs no source re-resolution and fingerprints the exact snapshot. `ValidatePreparedMedia` compares ordered roles/IDs/MIME/content digests against the quote, not just artifact IDs or a fresh read.
- Produces `VideoEstimateFingerprint.Compute(JsonObject canonicalSnapshot) -> string`: `v1:` plus lower-case SHA-256 hex; recursively sort object properties ordinally, use invariant decimal JSON numbers, preserve every array position/repeat. Fingerprint excludes itself, credentials, transport URLs, and attempt-result state.

- [x] Add `FingerprintChangesBelowCapAndForLowerPrices`, `ByteReplacementUnderSameArtifactIdInvalidatesQuote`, `CanonicalizationPreservesOrderRepeatsAndProvenance`, `NormalQuotedFallbackDoesNotInvalidateFingerprint`, `LegacyConfirmationContractsRemainDistinct`, `UnknownPriceCannotBecomeZero`, `UnusedFalSecretIsNotRead`. Assertions:

```csharp
Assert.Equal("v1:" + expectedSha256, sameQuote.EstimateFingerprint);
Assert.NotEqual(oldQuote.EstimateFingerprint, lowerPriceQuote.EstimateFingerprint);
Assert.Equal("estimate_stale", staleError.ProviderErrorCode);
Assert.Null(capOnlyError); // compatible admitted route within cap, changed revision allowed
Assert.Null(unboundedError); // both fields omitted
Assert.NotNull(fingerprintWithoutCapError);
Assert.Equal(Math.Max(googleTotal, falTotal), quote.MaximumEstimatedCostUsd);
Assert.Equal(0, falGetSecretCalls);
Assert.Equal(0, uploadOrGenerationCalls);
```

Cover request/prompt changes, reordered/repeated media, options omission versus explicit default, content digests, credential presence, binding/profile/framing/lifecycle/pricing revisions, expiration, numeric cap below selected total, and culture `fr-FR`. Add `PreparedBytesCannotBeValidatedByAnABARead`: accepted/current quote contains A, frozen preparation contains B; the fresh quote fingerprint can equal the accepted one while `ValidatePreparedMedia(preparedB, acceptedA)` and `ValidatePreparedMedia(preparedB, currentA)` both fail. Snapshot-based quote B must not acquire A's digest from a later source read. Media consistency remains mandatory for legacy cap-only/unbounded callers; their pricing revision contracts are unchanged. Rejection of Google's key is attempt evidence and must not remove the originally quoted Google candidate from the fingerprint. All totals use decimal; Standard 1080p eight seconds is `3.20m`, Fast `1.20m`, Lite `.64m` under the dated fixture rates.

- [x] Run managed filter `FullyQualifiedName~VideoRouteQuoteTests`; expected red: no quote/fingerprint implementation, then stale snapshots accepted.
- [x] Implement the interfaces. Canonical snapshot contains normalized request plus supplied-options provenance, ordered media IDs/roles/SHA-256 content digests, configured-secret presence, routing-policy revision, **all** conditional candidates with eligibility and their exact reviewed binding/capability/framing/profile/lifecycle/pricing/currency/rate/total, and maximum. Read Google secret only when relevant, treating exceptions as safe secret-access errors and whitespace as missing. Use `IGenerationSecretStore.HasSecret` for unused fal configuration metadata; never decrypt fal unless its attempt is selected. Direct fal never reads Google. Candidate selection after rejection cannot itself mutate the canonical quote.
- [x] Rerun the same filter; expected pass. Commit `feat: bind video confirmation to request and route quotes` with the four listed files.

### Task 4: Add dispatch-aware Google and fal Veo queue transport

**Files:** Create `src/Rook/Services/Vision/Video/Fal/FalVeoQueueAdapter.cs`, `src/Rook/Services/Vision/Video/VideoCredentialErrors.cs`, `src/Rook/Services/Vision/Video/IPreparedMediaVideoProvider.cs`; modify existing `Video/Fal/FalVideoProvider.cs`, `FalSourceFrameTransport.cs`, `IFalSourceFrameTransport.cs`, `FalSourceFramePolicy.cs`, `Video/VeoProvider.cs`, `Video/VeoClient.cs`, `Video/VideoJobError.cs`, `Video/VideoProviderOutcomeAdapters.cs`, and `src/Rook/Services/Vision/Fal/FalApiClient.cs`. Test create `src/Rook.Tests/Services/Vision/Video/Fal/FalVeoQueueAdapterTests.cs`, `src/Rook.Tests/Services/Vision/Video/VeoCredentialRoutingTests.cs`; extend existing fal provider tests for unchanged payloads.

**Interfaces:** Consume Task 2 compatibility/catalog, existing `GoogleCredentialErrors.IsRejectedKey(HttpStatusCode, JsonObject?)`, `ISubmissionDispatchAwareVideoProvider.SubmitWithDispatchAsync(request, media, Action beforeDispatch, CancellationToken)` and existing `IModelAwareVideoProvider` lifecycle methods.

- Produces internal `IPreparedMediaVideoProvider.SubmitPreparedAsync(VideoGenerationRequest request, VideoPreparedMediaSnapshot preparedMedia, Action beforeDispatch, CancellationToken ct) -> Task<ProviderSubmitOutcome>`, implemented by Google Veo and the shared `FalVideoProvider` for affected routes. `FalVeoQueueAdapter` exposes that exact method; model-aware status/fetch/cancel still delegate through the same fal provider, including after new-submission expiry. Preserve the existing dispatch-aware interface for Vertex and unaffected callers; affected coordinator calls use the prepared-media interface, not a mutable-map fallback.
- Extend source transport with `ResolveAndUploadVeoAsync(FalVeoBinding binding, VideoGenerationRequest request, VideoPreparedMediaSnapshot preparedMedia, string apiKey, CancellationToken ct) -> Task<(FalVeoSourceUrls? Urls, GenerationError? Error)>`; define `FalVeoSourceUrls(string? Start, string? End, IReadOnlyList<string> References)`. Despite its compatibility name, this method uploads snapshot-owned bytes only and never resolves storage again. Existing source transport method stays intact. Deduplicate uploads only by snapshot content/identity; re-expand all original slots and retain the snapshot association for every returned URL.
- Produces `FalJsonPlatformHeaders.ForVeoSubmit(int objectLifecyclePreferenceSeconds)`: preserve existing bounded storage policy, disable queue retries, do not alter Seedance headers.
- Produces `VideoCredentialFailure(string Provider, string Kind)` (`Provider` is `gemini` or `fal`; `Kind` is `missing` or `rejected`) and `VideoCredentialErrors.FromError(string provider, GenerationError error) -> VideoCredentialFailure?`. Define internal trusted markers `rook.veo.key_missing`, `rook.veo.key_rejected`, `rook.fal.key_missing`, `rook.fal.key_rejected`; only adapters construct them after local credential lookup or closed response classification. Scrub upstream reserved marker strings. Route provider name `veo` maps to credential owner `gemini` for Settings.
- Google submit becomes dispatch-aware at the exact `HttpClient.SendAsync` boundary; closed credential rejection is emitted as the internal normalized marker plus safe credential evidence. Extend **both** `VideoJobError` implicit conversion and `VideoProviderOutcomeAdapters` conversion directions to retain trusted markers/detail codes instead of dropping them. Preserve Vertex's existing `vertex_submission_unknown` contract and do not trust provider-supplied marker strings.

- [x] Add `QueuePayloadMatchesTierModeAndFixedProfile`, `IntentCallbackPrecedesOnlyGenerationSend`, `QueueUrlsMustMatchRequestAndApplication`, `CancellationBodyDeterminesCleanupOutcome`, `GoogleClosedRejectionMatrix`, `FalCredentialEvidenceDoesNotRequireFallback`. Assert captured requests and results:

```csharp
Assert.Equal("8s", payload["duration"]!.GetValue<string>());
Assert.True(payload["generate_audio"]!.GetValue<bool>());
Assert.False(payload["auto_fix"]!.GetValue<bool>());
Assert.Equal("4", payload["safety_tolerance"]!.GetValue<string>());
Assert.Equal("1", capturedHeaders["X-Fal-No-Retry"]);
Assert.Equal(1, generationPosts);
Assert.Equal(new[] { "intent", "send" }, generationEvents);
Assert.Equal(0, keyedRequestsToWrongRoot);
Assert.Null(directFalRouteReceipt);
Assert.Equal("fal", directFalCredentialFailure.Provider);
```

Hold Google/fal submit responses; callback failure must prevent send. Validate HTTPS origins, expected queue application root, exact request ID and status/response/cancel paths, reject cross-app/request-ID URLs even on a permitted host, user-info/unsafe redirect cases, malformed/missing acceptance ID and result URL, invalid video type and failed queue result. No retry generation POSTs. Cancellation covers documented `202/CANCELLATION_REQUESTED`, `400/ALREADY_COMPLETED`, `404/NOT_FOUND`, arbitrary 400, malformed body, timeout, and 5xx as distinct outcomes; accepted does not guarantee stopped billing.

Add `UploadsAndGoogleInlinePayloadUseFrozenSnapshot`: capture A, mutate the source and resolver buffers to B at preparation barriers, and capture actual fal multipart bytes and decoded Google inline image bytes. Their SHA-256 must equal A's snapshot digest. All first/last/reference slots come from that snapshot; no provider or payload helper re-reads an artifact/path or receives its mutable source buffer. Stop/admission failure after upload prevents the generation POST.

Google matrix covers allowed structured 401 and `API_KEY_INVALID` ErrorInfo at permitted statuses versus generic 403, wrong service/domain, malformed body, text-only rejection, spoofed marker, quota/billing/policy/5xx/network/timeout. Poll/fetch authentication failure never permits routing. Fal missing key and 401 are credential failures; generic 403 is not definite rejection. Secret exceptions are safe failures, not missing configuration. No raw body/secret appears in public error text.

- [x] Run managed filter `FullyQualifiedName~FalVeoQueueAdapterTests|FullyQualifiedName~VeoCredentialRoutingTests|FullyQualifiedName~FalVideoProviderTests`; expected red: missing adapter and dropped credential evidence.
- [x] Implement the interfaces with the existing fal HTTP client and media upload lifetime (`3600` seconds). Decode/validate **all** inputs before upload. Upload is preparation; invoke `beforeDispatch` only immediately before the single generation POST and check cancellation after the callback returns. Parse handles conservatively and persist lifecycle metadata through the existing handle type. Expiry blocks new submit, not known-handle operations. Transport stores no per-job mutable model/handle state.
- [x] Rerun the filter; expected all pass, with Wan/Seedance/Kling payloads and handles unchanged. Commit `feat: support dispatch-aware fal Veo queue operations` with this task's file list.

### Task 5: Make execution evidence durable and stop signalling independent

**Files:** Create `src/Rook/Services/Vision/Video/VideoExecutionSnapshot.cs`, `VideoExecutionBudget.cs`; modify `JsonlVideoJobLedger.cs`. Test create `src/Rook.Tests/Services/Vision/Video/VideoExecutionSnapshotTests.cs`, `VideoExecutionBudgetTests.cs`; extend `JsonlVideoJobLedgerTests.cs` and existing fake ledger/clock helpers only as required by these tests.

**Interfaces:** Consume existing schema-1 `VideoJobRecord.Extensions`, `IVideoJobClock.UtcNow()` and `IVideoJobLedger.Append(VideoJobRecord)`.

- Produces `VideoExecutionSnapshot(int Version, JsonObject Data)` with validated defensive JSON copies; `VideoExecutionSnapshot.Read(VideoJobRecord record) -> (VideoExecutionSnapshot? Snapshot, GenerationError? Error)` and `Write(VideoJobRecord record, VideoExecutionSnapshot snapshot) -> VideoJobRecord`. Absent extension means legacy, not invalid. Unknown version/corrupt required evidence is invalid and cannot dispatch.
- Extension `video_execution.version=1` stores requested identity/options provenance, selected binding/profile/options, accepted canonical quote/fingerprint/cap, absolute deadline, first stop, execution phase, per-provider attempts with `dispatch_state` and response evidence, cleanup, persistence evidence, publication warning. Store ordered `prepared_media` entries with `role`, input ID, `mime_type`, `sha256`, and `byte_length`, including repeats; each dispatch intent identifies those same prepared digests. Never persist raw media bytes. `video_route.version=1` stores only automatic missing/rejected-key receipts. Preserve existing `provider_handle`; credential failure exists independently of `video_route`.
- Produces `VideoStopReason { User, Deadline, Shutdown }`, `VideoStopPersistence { None, Pending, Durable, Failed }`, and `VideoExecutionBudget(DateTimeOffset deadlineUtc, IVideoJobClock clock, IVideoDeadlineTimer timer)` with `Token`, `FirstStopReason`, `Remaining`, `TryStop(VideoStopReason) -> bool`, `TryAdmitCompletion() -> bool`, `Dispose()`. `TryStop` atomically competes with completion admission and immediately cancels the execution CTS before returning; it performs no ledger IO or transition-gate acquisition.
- Produces `IVideoDeadlineTimer.Schedule(DateTimeOffset deadlineUtc, Action callback) -> IDisposable` and a production implementation in `VideoExecutionBudget.cs`; tests control firing. Register once per job using its original persisted deadline; no fallback reset. A completion-admitted decision defeats later stops, while an earlier stop defeats completion.

- [x] Add `IntentSnapshotSurvivesReopenWithoutSendFlag`, `CriticalExtensionVersionFailsClosedButLegacyReads`, `StopSignalsBeforePersistenceCanRun`, `FirstStopAndCompletionAdmissionHaveOneWinner`, `DeadlineIsNotResetByFallback`. Assertions:

```csharp
Assert.Equal("intent_recorded", reopenedAttempt["dispatch_state"]!.GetValue<string>());
Assert.False(reopenedAttempt["generation_dispatch_attempted"]!.GetValue<bool>());
Assert.True(budget.TryStop(VideoStopReason.Deadline));
Assert.True(budget.Token.IsCancellationRequested);
Assert.False(budget.TryStop(VideoStopReason.User));
Assert.Equal(VideoStopReason.Deadline, budget.FirstStopReason);
Assert.False(budget.TryAdmitCompletion());
Assert.Equal(1, scheduledTimerCount);
```

Use real JSONL reopen, extension round-trip including unknown optional keys, truncated/corrupt critical data, and concurrent stop/completion observers with barriers. Deadline callback fires while a test ledger append is blocked; the latch/token assertion must complete before releasing the append.

- [x] Run managed filter `FullyQualifiedName~VideoExecutionSnapshotTests|FullyQualifiedName~VideoExecutionBudgetTests|FullyQualifiedName~JsonlVideoJobLedgerTests`; expected red: absent durable evidence/budget and no durable flush guarantee.
- [x] Implement snapshot codec and budget. Make successful production ledger append explicitly flush the writer and call `FileStream.Flush(flushToDisk: true)` before returning; readers see only complete committed snapshots. Do not reinterpret failed/partial append as success. Retain extension compatibility and single-manager-writer ownership. Timer callback latches/signals directly, then schedules manager persistence separately in Task 7.
- [x] Rerun the filter; expected pass. Commit `fix: persist video execution intent and latch immediate stops` with this task's file list.

### Task 6: Project execution evidence without breaking legacy results

**Files:** In `src/Rook/Services/Vision/Video/`, create `IVideoConfirmedJobManager.cs`; extend `VideoExecutionSnapshot.cs`, `JobSubmitResult.cs`, `JobStatusResult.cs`, `JobCancelResult.cs`, `JobFetchResult.cs`, `JobListEntry.cs`, `VideoJobError.cs`, `VideoProviderOutcomeAdapters.cs`. Test create `src/Rook.Tests/Services/Vision/Video/VideoExecutionProjectionTests.cs`.

**Interfaces:** Consumes Task 3 quote/confirmation and Task 5 snapshots.

- Produces internal `IVideoConfirmedJobManager.QuoteAsync(VideoRequestIntent, CancellationToken) -> Task<VideoRouteQuoteResult>` and `SubmitConfirmedAsync(VideoRequestIntent, VideoSubmitConfirmation, CancellationToken) -> Task<JobSubmitResult>`. `VideoJobManager` implements it in Task 7; leave public `IVideoJobManager` and old fake implementations source-compatible.
- Produces internal `VideoExecutionProjection(JsonObject Fields)` and `VideoExecutionSnapshot.Project(VideoJobRecord durable, VideoStopReason? localStop, VideoStopPersistence persistence) -> VideoExecutionProjection`. Projection contains safe requested/effective provider/model, phase, per-attempt dispatch/unknown outcome, credential failure, optional automatic route, accepted/effective estimates and confirmed bound, deadline, first stop, `execution_stopped`, `stop_persistence`, cleanup and publication warnings.
- Add an internal optional `Execution` property/factory parameter to each manager result, keeping existing public constructors/factories valid. Error results also carry `Execution`, including failures before job ID admission. Add trusted safe `DetailCode` to `VideoJobError`, preserving it through conversion. Handler retains legacy `code` and additionally emits `detail_code` such as `estimate_stale`, `submission_unknown`, or `persistence_failed`.

- [x] Add `CredentialFailureWithoutRouteIsProjected`, `PendingStopDoesNotClaimDurableCancelled`, `FailedStopPreservesOriginalReason`, `LegacyResultsRemainUnchanged`, `SafeDetailCodesSurviveConversion`. Assertions:

```csharp
Assert.Null(fields["video_route"]);
Assert.Equal("fal", fields["credential_failure"]!["provider"]!.GetValue<string>());
Assert.Equal("Polling", durableStateName); // blocked stop append, last durable state
Assert.True(fields["execution_stopped"]!.GetValue<bool>());
Assert.Equal("pending", fields["stop_persistence"]!.GetValue<string>());
Assert.Equal("deadline", failedFields["first_stop_reason"]!.GetValue<string>());
Assert.Equal("failed", failedFields["stop_persistence"]!.GetValue<string>());
Assert.DoesNotContain(secretOrRawBody, serializedFields);
```

- [x] Run managed filter `FullyQualifiedName~VideoExecutionProjectionTests`; expected red: missing/additive evidence, safe detail codes lost.
- [x] Implement the listed interfaces/DTO additions and safe projection. A result's legacy state/error/artifact and new evidence must come from **one** captured manager snapshot, never a handler read-after-write lookup that can mix routes/states. Pending/failed local persistence is a process-local overlay on the last committed snapshot; do not write it as if it were a successful terminal commit.
- [x] Rerun the filter; expected pass. Commit `feat: expose safe video routing and durability evidence` with this task's file list.

### Task 7: Integrate single-job routing, dispatch, stops, and restart

**Files:** Modify `src/Rook/Services/Vision/Video/VideoJobManager.cs`, `VideoSubmissionCoordinator.cs`, `VideoSubsystemFactory.cs`, `src/Rook/Services/Vision/VisionProviderRegistrations.cs`; add focused helper methods in the manager rather than rewriting existing provider branches. Test create `src/Rook.Tests/Services/Vision/Video/VideoFalFallbackManagerTests.cs`, `VideoFalFallbackRaceTests.cs`; extend `VideoStopSubmissionRaceTests.cs`, `GuardedVideoJobManagerTests.cs`, and `VideoSubsystemFactoryTests.cs`.

**Interfaces:** Consume Tasks 2–6, `VideoPreparedMediaSnapshot`, and `IPreparedMediaVideoProvider` for affected attempts; retain the existing dispatch-aware seam for other providers. Manager implements `IVideoConfirmedJobManager` methods, owns `VideoRouteQuoteService`, and supplies `Action beforeDispatch` via `AdmitGenerationDispatch(RunningJob running, VideoRouteCandidate candidate, VideoPreparedMediaSnapshot preparedMedia) -> void` (throws a safe internal admission failure on rejection). Coordinator produces `SelectInitial(VideoRouteQuote quote) -> VideoRouteCandidate`, `SelectFallback(VideoRouteQuote quote, GenerationError googleSubmissionError) -> VideoRouteCandidate?`, `SubmitAttemptAsync(VideoRouteCandidate candidate, VideoPreparedMediaSnapshot preparedMedia, Action beforeDispatch, CancellationToken ct) -> Task<ProviderSubmitOutcome>`; only closed normalized Google submit rejection selects a fallback. Callback closes over the same snapshot instance used to build that attempt's upload/payload.

Manager adds `ObserveStop(RunningJob running, VideoStopReason reason) -> void`, `PersistObservedStopAsync(RunningJob running) -> Task<JobCancelResult>`, `ObserveLateSubmitAsync(RunningJob running, Task<ProviderSubmitOutcome> submission) -> Task`, and `CleanupKnownHandleAsync(RunningJob running, ProviderJobHandle handle, CancellationToken cleanupToken) -> Task`. These helpers mutate only that job's state; every append remains serialized by its transition gate. Existing providers retain their existing cancellation policies.

Extend the existing **internal** constructor with optional trailing `VideoSubmissionCoordinator? coordinator = null`, `VideoRouteQuoteService? routeQuotes = null`, `IVideoDeadlineTimer? deadlineTimer = null`; retain the public constructor's signature and default legacy behavior. Factory injects affected-route services through that internal constructor. Implement confirmed-interface methods explicitly so internal quote/intent types do not become public API.

- [x] Add `MissingKeyMotivatingI2vUsesSameJobAndFal`, `ConfiguredGoogleDoesNotReadFalSecret`, `RejectedGooglePersistsBeforeFalRoute`, `DirectFalNeverReadsGoogle`, `StoppedIntentAppendPreventsSend`, `HeldResponseSnapshotRestoresUncertainty`, `AcceptedHandleAppendFailureStopsAndCleansUp`, `FirstStopSurvivesBlockedAndFailedAppend`, `ConcurrentJobsKeepDifferentRoutes`. Use a manager fixture with real temp JSONL, fake injected deadline timer, captured HTTP messages, and barriers at each append/transport phase. Key assertions:

```csharp
Assert.Equal(originalJobId, falRecord.JobId);
Assert.Equal(originalCreatedAt, falRecord.CreatedAt);
Assert.Equal(originalDeadline, restoredDeadline);
Assert.Equal(1, falGenerationPosts);
Assert.Equal(0, googlePostsForMissingKey);
Assert.Equal(0, unusedFalSecretReads);
Assert.Equal("fal", falRecord.Provider);
Assert.Equal(3.20m, falEffectiveEstimatedUsd); // admitted Standard fixture, 1080p/8s
Assert.True(executionToken.IsCancellationRequested); // assert while stop append still blocked
Assert.Equal(0, generationSendsAfterStoppedIntentAppend);
Assert.Equal(VideoJobState.Interrupted, restoredUnknown.State);
Assert.Equal(0, restoredGenerationOrPollCalls);
Assert.Equal("deadline", cancelledAfterDeadlineReason);
Assert.Equal(VideoJobState.Complete, unaffectedConcurrentJob.State);
```

Cover actual ledger snapshots while **each** provider response is held, with `generation_dispatch_attempted=false` and persisted intent. Restore a fresh manager from those bytes, not an in-memory fake record. Crash between Google response and rejection append, after durable rejection but before fal intent, and after fal intent: no restart sends. Route-preparation/intent append failure prevents uploads/sends; accepted-handle append failure prevents polling/publication and attempts bounded cleanup. Stale fingerprints at initial admission, while queued, after source bytes change, and after Google rejection prevent the **next** generation; unchanged quoted fal candidate proceeds normally.

Add deterministic `PreparedMediaABACannotAuthorizeDifferentSentBytes` for Google inline preparation and fal I2V/interpolation/references, including rejected-key fallback. Barriers control resolver completion/capture, fal upload or Google payload construction, and dispatch admission. First quote A, return B from worker resolution, restore current storage to A before validation: current quote equals accepted A, but frozen B fails prepared-media validation and no upload/generation is admitted. Separately capture A, change storage/aliased resolver buffers to B while actual preparation is held, restore A before dispatch, and release: either validation safely refuses, or every captured upload/decoded inline byte is A and the dispatch record's ordered digests are A. Never accept a send of B validated by a fresh A quote. Hold storage at B through admission as another negative: no generation. Check duplicate slots and independent concurrent-job snapshots, and that a stale job never recaptures/reuploads/retries to hide the mismatch.

```csharp
Assert.Equal(acceptedA.EstimateFingerprint, currentA.EstimateFingerprint);
Assert.NotEqual(acceptedA.EstimateFingerprint, preparedBQuote.EstimateFingerprint);
Assert.Equal("estimate_stale", preparedMismatch.ProviderErrorCode);
Assert.Equal(0, postsAfterFailedAdmission);
Assert.Equal(snapshotASha256, uploadedOrDecodedInlineSha256); // allowed immutable-A case
Assert.Equal(snapshotASha256, persistedDispatchSlotSha256);
```

Stop cases: queued, upload, prepared route, blocked intent append, held non-cooperative submit, poll, fetch, and final admission. Assert token cancellation before blocked stop append releases; failed append keeps `pending/failed` evidence, fails cancellation acknowledgement, and admits no further work. Explicit later Cancel retries persistence of the original reason only. Deadline-before-Cancel, Cancel-before-deadline, shutdown, and completion admission on both sides of the race preserve the single winner through JSONL/restart. Cleanup is independent of blocked/failed stop persistence and execution CTS. Late handles attach to terminal state and cleanup once, never reprice/reopen/publish. Terminal interrupted jobs with handles support explicit cleanup even after binding expiry; corrupt/unknown extensions fail closed and legacy handles still work.

Concurrent test interleaves Google success for A and closed Google rejection/fal for B through held submit/poll responses. Stop/expire B while A finishes. Assert different handles, binding/profile, quotes/fingerprints/effective prices, timers, reasons, and attribution; restore both snapshots and keep their providers distinct. Use the same fal lifecycle dispatcher that handles existing fal models.

- [x] Run managed filter `FullyQualifiedName~VideoFalFallbackManagerTests|FullyQualifiedName~VideoFalFallbackRaceTests|FullyQualifiedName~VideoStopSubmissionRaceTests|FullyQualifiedName~GuardedVideoJobManagerTests|FullyQualifiedName~VideoSubsystemFactoryTests`; expected red: no fallback/durable admission and cancellation waits behind persistence.
- [x] Implement confirmed admission: validate current quote/cap; persist initial queued request/accepted quote/deadline; create one budget; enter existing concurrency slot; persist selected effective provider/model/options/profile/estimate together before resolution/upload. Resolve worker media inside the budget and immediately capture one job-owned immutable prepared snapshot. Validate its ordered content against the accepted quote before upload/payload preparation; reuse it across Google and any fal attempt. Store only its role/ID/MIME/digests in execution evidence. Quote resolution before creating a job is estimate/admission work, not generation, and has the existing request-level cancellation bound.
- [x] Implement dispatch: quote the exact prepared snapshot with `QuotePreparedAsync`, separately recheck current source/request/candidate state with `QuoteAsync`, and validate prepared media against both the accepted and current quote. Validate accepted fingerprint and cap against both recomputed quotes; a fresh A quote cannot authorize a prepared B payload. In cap-only/unbounded mode still enforce media consistency while retaining its distinct pricing revision contract. Do not replace the snapshot, uploaded URLs, or prepared Google body after admission; a mismatch fails safely (`estimate_stale`) without automatic recapture/resubmit. Then under the transition gate check latest durable state/latch/deadline/binding cutoff, persist `intent_recorded` with the exact snapshot's ordered digests and effective binding, recheck latch/token/cutoff after append, and grant at most one send from that snapshot. Persist a definitive accepted handle or closed rejection before polling or selecting fal. Missing-key routing performs no Google send. Persist fal route/price before any fal upload. Uncertain responses are `Interrupted/submission_unknown`, never fallback/retry.
- [x] Implement stop and restart: observer calls budget latch/cancel directly before scheduling persistence. Blocking synchronous ledger IO must run independently of observers; return status/list from the cached last **successfully committed** snapshot plus local overlay so a blocked ledger lock cannot hide the stop. Cancel acknowledgement awaits its terminal append; append failure returns safe persistence failure. Cancellation-aware waits detach non-cooperative transports at stop and observe late responses safely. Startup marks surviving nonterminal affected jobs Interrupted, preserves attempts/pricing/handles, and never polls/resubmits. Stop reason maps exactly as spec section 10: user before intent Cancelled; user after intent/no handle Interrupted; user with handle Cancelled; deadline/shutdown Interrupted. Cleanup metadata cannot change that winner.
- [x] Wire factory/registrations with the same `FalVideoProvider` for all fal registrations, coordinator, quote service, evidence catalog, and budget injection. Keep direct legacy manager calls explicit in option provenance, unbounded by default; unrelated provider routes follow their existing semantics. Rerun the filter; expected pass. Commit `feat: coordinate durable Google to fal video fallback` with this task's file list.

### Task 8: Fence provisional publication and preserve completed artifacts

**Files:** Create `src/Rook/Services/Vision/Video/VideoPublicationService.cs`; modify `VideoJobManager.cs`, `VideoSubsystemFactory.cs`, `src/Rook/Handlers/VisionHandler.cs`, `src/Rook/UI/Vision/VisionWebSurface.cs`; extend `VideoArtifactMaterializer.cs`, `VideoPosterSidecarProducer.cs`, `VideoFrameSidecarProducer.cs`, `VideoSidecarBackfillService.cs` only where bounded cancellation/visibility requires it. Test create `src/Rook.Tests/Services/Vision/Video/VideoFallbackPublicationTests.cs`; extend `VideoSidecarPublisherTests.cs`, `VideoArtifactMaterializerTests.cs`, `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`, and relevant existing VisionHandler artifact tests.

**Interfaces:** Consume manager durable snapshots and Task 5 completion admission. Produce `VideoPublicationService(ArtifactStore store, VideoArtifactMaterializer materializer, Func<Guid, string, JsonNode, Artifact>? setFlag = null)`, `PrepareAsync(Guid jobId, ResultArtifact result, VideoExecutionSnapshot execution, CancellationToken ct) -> Task<Artifact>` (includes materialization and provisional metadata), `FinalizeMarker(Artifact artifact) -> GenerationError?`, `RemoveOwnedProvisional(Artifact artifact, VideoJobRecord durable) -> void`, `IsVisible(Artifact artifact, VideoJobRecord? durable) -> bool`, `RepairFromLedger(Artifact artifact, VideoJobRecord? durable) -> GenerationError?`. Service never appends the job ledger; manager commits completion. Default marker mutation uses existing `ArtifactStore.SetFlag(Guid, string, JsonNode)`; the injected delegate permits deterministic mutation failure. Add optional trailing `VideoPublicationService? publication = null` to the internal manager constructor from Task 7.

Produce static `VideoPublicationService.IsAffectedArtifact(Artifact artifact) -> bool` and internal `VideoJobManager.IsArtifactVisible(Artifact artifact) -> bool`, which supplies the last successfully committed matching record to the service rule without provider work or UI-thread ledger IO. Recognize either ownership metadata or publication flag presence as affected even when its value is malformed; malformed ownership cannot become a legacy bypass. Share that predicate with handler visibility, backfill, and blob streaming. Add optional trailing `Func<Artifact, bool>? videoArtifactIsVisible = null` to the existing five-argument internal `VisionWebSurface` constructor; preserve shorter overloads and wire the production constructor to the shared manager's predicate. A missing/throwing predicate fails closed for affected artifacts; unmarked legacy artifacts retain existing access.

- [x] Add `StopOrTerminalAppendFailureRemovesOnlyOwnedProvisional`, `SidecarWaitCannotExtendWholeJobBudget`, `MarkerFailureAfterDurableCompleteRetainsSameArtifact`, `RestartMarkerRepairIsIdempotent`, `UnknownLedgerQuarantinesRatherThanDeletes`. Assertions:

```csharp
Assert.False(provisionalGalleryVisible);
Assert.Equal(VideoJobState.Complete, completed.State);
Assert.Equal(originalArtifactId, completed.ResultArtifactId);
Assert.True(videoExists && posterExists && framesExist);
Assert.True(fetchable && galleryVisible); // matching Complete is authoritative despite marker
Assert.Contains("artifact_marker_pending", warningCodes);
Assert.Equal(0, deletesAfterDurableComplete);
Assert.Equal(0, repairGenerationOrRepriceCalls);
Assert.True(unrelatedArtifactStillExists);
```

Test cancellation/deadline during creation, materialization, sidecars, and completion append; invalid/missing video, unsafe download/redirect, 250 MiB overflow, sidecar-only failure, terminal append failure, and cancellation racing after completion admission. Fail marker mutation after committed Complete, restart with unchanged provisional marker, then fail repair repeatedly before succeeding. Marker failure never changes Complete or deletes video/sidecars. Unknown/unreadable ledger hides/quarantines without deleting; stopped/reconciled known ownership permits provisional cleanup only.

Add real resolver tests `BlobStreamRejectsProvisionalOrUnknownOwnership` and `BlobStreamAllowsDurablyCompletedArtifactWithPendingMarker` in `VisionWebSurfaceTests`. Call `ResolveVirtualResourceForTest` for `/blob/{artifact_id}/{role}` on the video and every actual poster/frame sidecar role. Queued/Polling/Interrupted, blocked/failed terminal commit, absent/unreadable owner, malformed ownership, mismatched completed result ID, and absent/throwing visibility predicate return `404` without opening a blob file. Matching durable Complete returns `200` and the original stream bytes despite provisional marker/finalization failure; restart and repeated failed repair preserve this access. Assert content type, `Cache-Control: no-store`, and delete-sharing remain intact. Existing unmarked image/legacy video blob tests stay green. No raw provisional blob bytes appear in a denial response.

```csharp
Assert.Equal(404, provisionalBlob.StatusCode);
Assert.Equal(404, unknownOwnerBlob.StatusCode);
Assert.Equal(404, mismatchedResultBlob.StatusCode);
Assert.Equal(200, completedWithPendingMarkerBlob.StatusCode);
Assert.Equal(originalVideoOrSidecarBytes, streamedBytes);
Assert.Contains("Cache-Control: no-store", completedWithPendingMarkerBlob.ExtraHeaders);
```

- [x] Run managed filter `FullyQualifiedName~VideoFallbackPublicationTests|FullyQualifiedName~VideoSidecarPublisherTests|FullyQualifiedName~VideoArtifactMaterializerTests|FullyQualifiedName~VisionWebSurfaceTests`; expected red: unfenced direct blob/gallery visibility and deletion by the post-completion exception path.
- [x] Implement initial metadata `video_job_id` and initial flag `video_publication: "provisional"`, plus safe requested/effective identity/profile/options/route/estimated pricing/parents. Finalization sets the flag to `"complete"`; metadata remains immutable. Before completion use latest manager snapshot and budget admission, commit matching Complete under the same gate, then finalize marker best effort within remaining budget. Split precommit rollback from postcommit repair; a general catch must never delete a matching durably completed artifact. `VisionHandler.ListArtifacts/GetArtifact`, manager fetch, sidecar backfill, and `VisionWebSurface.TryResolveVirtualResource` use the same visibility rule. The blob path loads/validates artifact ownership and checks that rule **before** `GetBlobAbsolutePath`/`FileStream` for every role of an affected artifact; denied/unknown ownership returns a safe `404`. Durable Complete takes precedence over a stale provisional flag for both gallery and direct video/sidecar streaming. Infer `artifact_marker_pending` from a matching completed record plus unfinished flag even if warning persistence also fails, and do not downgrade completion. Keep sidecars best effort, but a winning whole-job stop while they are pending stops publication and removes owned provisional output.
- [x] Rerun filter plus existing VisionHandler artifact tests; expected pass. Commit `fix: fence video publication with durable completion` with this task's changed files.

### Task 9: Carry route-aware quotes and errors through managed operations

**Files:** Modify `src/Rook/Handlers/VideoOpHandler.cs`, `src/Rook/UI/Vision/VisionWebSurface.cs`, `src/Rook/Services/Vision/Video/VideoModelDescriptor.cs` and `VideoSubsystemFactory.cs` as needed for catalog metadata injection. Test extend `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`, `VideoOpHandlerIntegrationTests.cs`; create `src/Rook.Tests/Handlers/VideoFallbackEnvelopeTests.cs` and `src/Rook.Tests/UI/Vision/Fixtures/video-fallback-bridge.json`.

**Interfaces:** Consume `IVideoConfirmedJobManager` and result `Execution`. Produce `VideoOpHandler.ParseRequestIntent(Dictionary<string, JsonElement> args) -> (VideoRequestIntent? Intent, GenerationError? Error)` and `ParseConfirmation(Dictionary<string, JsonElement> args) -> (VideoSubmitConfirmation? Confirmation, GenerationError? Error)`, while retaining the existing legacy request parser for unaffected models. Add one safe projection helper `ProjectExecution(VideoExecutionProjection? execution, Dictionary<string, object?> response) -> void` to every operation/error envelope. Descriptors add configured-credential presence and new-submission lifecycle/compatibility availability; configured is not validated.

- [x] Add `ActualHandlersRetainEvidenceAcrossAllOperations`, `DirectFalCredentialFailuresNeedNoReceipt`, `UntouchedOptionsAndExplicitLegacyRequestsDiffer`, `FingerprintAndCapParsingIsStrict`, `PendingPersistenceIsNotCancelledSuccess`, `LegacyEnvelopesRemainCompatible`. Assertions on real serialized responses:

```csharp
Assert.Null(directFalData["video_route"]);
Assert.Equal("fal", directFalData["credential_failure"]!["provider"]!.GetValue<string>());
Assert.Equal("estimate_stale", staleData["detail_code"]!.GetValue<string>());
Assert.Equal("pending", pendingStatus["stop_persistence"]!.GetValue<string>());
Assert.NotNull(estimateData["estimate_fingerprint"]);
Assert.NotNull(estimateData["maximum_estimated_cost_usd"]);
Assert.DoesNotContain(secretOrRawBody, envelopeJson);
```

Exercise submit/status/list/fetch/cancel and pre-job failure with direct fal missing-key/401/generic403, fallback failure, unknown dispatch, effective estimates, accepted quote/cap, cleanup outcomes, marker warning, pending/failed persistence. Generic403 never gains definitive credential evidence. Malformed fingerprint/cap, negative/non-number cap, fingerprint without cap, and explicit incompatible option get field-specific errors. Existing error/status/artifact keys retain meaning.

- [x] Run managed filter `FullyQualifiedName~VideoOpHandlerTests|FullyQualifiedName~VideoOpHandlerIntegrationTests|FullyQualifiedName~VideoFallbackEnvelopeTests`; expected red: discarded evidence, omission rejected, no confirmed quote fields.
- [x] Implement affected handler parsing/dispatch and additive projection from each result's single captured snapshot. Estimate may now read local media; keep it off the UI thread and propagate request cancellation through the existing managed dispatcher, without adding native ABI/routes. Add internal `DispatchOffUi(string? body, CancellationToken cancellationToken) -> ApiResponse` if needed, preserve the existing body-only entry, and bound that entry's estimate work with the existing **30-second** off-UI request ceiling. Submit keeps its existing **180-second** request ceiling; neither resets the background job's 20-minute deadline. Submit calls confirmed manager only for affected IDs, leaving legacy fakes/unrelated providers supported. Generate JSON fixture from actual handler envelopes; comparisons normally read the checked-in fixture, regeneration requires an explicit test flag.
- [x] Rerun filter; expected pass and fixture matches actual envelopes. Commit `feat: project confirmed video routing through managed operations` with this task's file list.

### Task 10: Update the actual Video panel confirmation and attribution

**Files:** Modify `src/Rook/UI/Vision/Resources/app.js`, `index.html`; create `src/Rook.Tests/UI/Vision/video-fallback.test.cjs`; consume the Task 9 fixture.

**Interfaces:** Consume existing operation names, Task 9 envelopes and model descriptors. Produce revision-aware VideoTab submit arguments containing `estimate_fingerprint` and `max_estimated_cost_usd`; actual Google 3.1 untouched people control emits `options: {}`. Explicitly changing that control emits the selected value even if later changed back to the default. Other Google families keep existing options. Direct fal uses the dedicated fixed-profile controls/omission policy, not Google's people control.

- [x] Add VM tests running the actual VideoTab code and DOM/bridge events: `untouched_vs_explicit_people_control`, `conditional_prices_and_maximum_are_confirmed`, `stale_estimate_response_cannot_enable_submit`, `price_revision_requires_fresh_confirmation`, `direct_fal_credentials_without_receipt`, `stop_and_unknown_outcome_preserve_form_media`, `marker_warning_keeps_completed_video`, `labels_have_readable_separators`. Assert:

```javascript
assert.deepEqual(untouchedArgs.options, {});
assert.equal(explicitArgs.options.person_generation, 'allow_adult');
assert.equal(submitArgs.estimate_fingerprint, confirmedQuote.estimate_fingerprint);
assert.equal(submitArgs.max_estimated_cost_usd, confirmedQuote.maximum_estimated_cost_usd);
assert.equal(autoReplayCount, 0);
assert.equal(mediaAfterError, mediaBeforeError);
assert.equal(invalidatedProviderForFal401, 'fal');
assert.equal(invalidatedProviderForGeneric403, null);
assert.equal(renderedLabels.includes('\uFFFD'), false);
```

Drive buttons and fake bridge messages rather than duplicating production functions. Test both conditional prices, ineligible fallback explanation without blocking Google-only request, provider-default explanatory copy, lifecycle availability, routing reason/effective price, pending/failed stop persistence, cleanup caveat, and submission_unknown deliberate new action. Settings/provider overlays only mark the actually missing/definitively rejected credential. Lost start response refreshes history, preserves inputs, warns of uncertainty, and never automatically submits another job.

- [x] Run `node --test src/Rook.Tests/UI/Vision/video-fallback.test.cjs`; expected red: unconditional people field, dropped evidence, no fingerprint/cap confirmation.
- [x] Implement form provenance, eligible direct fal model options, quote invalidation on request/media/credentials/models/profile/pricing changes and strict async response request matching. Display conditional prices and maximum; send only the quote actually confirmed. `estimate_stale` clears confirmation and requires a fresh deliberate action. Preserve form/media through all errors. Use readable ` · ` separators, zero literal replacement characters. Leave image/prompt UI behavior unchanged.
- [x] Run `node --test src/Rook.Tests/UI/Vision/image-fallback.test.cjs src/Rook.Tests/UI/Vision/video-fallback.test.cjs`; expected all pass. Commit `feat: confirm and explain video fallback in Vision` with the three listed files.

### Task 11: Preserve additive contracts through native and Python consumers

**Files:** Modify `mcp_server/src/rook/server.py`, and `mcp_server/src/rook/agent/tool_dispatcher.py` only if its current passthrough drops new fields; extend `mcp_server/tests/test_video_mcp_tools.py` and `test_server_tool_profiles.py` only where existing contracts change. Audit `src/RookNative/Handlers/VisionHandler.cpp` and route registrations in `RookServer.cpp`; no native edit is expected. Consume the same Task 9 fixture.

**Interfaces:** Existing seven video operations/HTTP routes and tool names are unchanged. `rhino_render_video` admits optional string `estimate_fingerprint` and numeric `max_estimated_cost_usd`, forwarding both without transformation. Existing result/exception paths preserve additive nested execution fields and safe detail codes. Descriptions explain Google-first compatible fal fallback and estimate media inspection; do not retain the misleading mandatory-Gemini-key or pure-pricing-only statements.

- [x] Add Python tests `test_video_confirmation_fields_forward_unchanged`, `test_video_execution_evidence_survives_managed_envelopes`, `test_video_direct_fal_failure_keeps_credential_without_route`, `test_video_tool_profile_counts_unchanged`. Assert shared fixture fields survive success and error handling:

```python
assert posted["estimate_fingerprint"] == "v1:" + "a" * 64
assert posted["max_estimated_cost_usd"] == 3.20
assert data["credential_failure"]["provider"] == "fal"
assert data.get("video_route") is None
assert data["stop_persistence"] == "failed"
assert data["detail_code"] == "submission_unknown"
```

Include legacy callers omitting fields, cap-only callers, estimate route candidates, list/fetch/cancel evidence, marker warnings, port handling, and error envelopes. Assert native dispatch routes transport the whole JSON object; do not infer contract parity from hand-written UI-only fixtures.

- [x] Run `& 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_video_mcp_tools.py mcp_server/tests/test_server_tool_profiles.py -q`; expected red: schema fields absent or evidence flattened/dropped. Existing local virtualenv is available at planning time; if execution uses a different host, locate the configured environment before running, without introducing dependencies.
- [x] Implement minimal schema/documentation/passthrough changes. Keep lifecycle tool/profile counts and retired Director discovery policy unchanged. If the audit finds a native parser actually discarding fields, document the managed/native dependency and add a targeted native fix/test; do not modify `.vcxproj`/filters or claim native build verification without the Rhino/MFC toolchain. Such a native change requires its deployment workflow and fresh 14.44.35207 toolset build.
- [x] Rerun command; expected all pass. Commit `feat: preserve video quote and execution evidence in MCP` with changed files only. Do not run `test_video_routes_live.py` or paid smoke tests.

### Task 12: Verify the whole branch and obtain independent final review

**Files:** Add/update only tests needed to close a demonstrated gap in the task-owned files. Update the evidence document and this plan's checkboxes/results; no unrelated refactor. Independent review must cover the **whole branch**, including retained prompt fallback commits.

**Interfaces:** Consumes Tasks 1–11 deliverables and all 23 acceptance cases below. Produces an evidence-backed final report and a reviewed branch; feature completion additionally requires the Task 1 admission gate. Native execution preference remains preserved.

- [x] Run targeted tests for every changed boundary, then build managed Release: `dotnet build src/Rook/Rook.csproj -c Release --no-restore -p:RhinoPluginDir=`. Expected: successful build; report existing warnings and any new warnings separately. No native/RookBIM claim follows a managed build. Build RookBIM afterward only if a full deploy/release workflow calls for that module.
- [x] Run full hermetic managed coverage: `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter 'FullyQualifiedName!~LiveSmoke&FullyQualifiedName!~SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign&FullyQualifiedName!~Task7_original_producer_values_survive_managed_http_parser' --logger 'console;verbosity=minimal'`. Existing two fixture-dependent exclusions are named explicitly; verify they remain the same missing baseline artifacts, and report them. Do not silently add exclusions for feature failures. No cached count substitutes for fresh results.
- [x] Run both Vision Node test files from Task 10 and Python contract/profile tests from Task 11. Run relevant existing image/prompt fallback, Google/Vertex/Wan/Seedance/Kling provider/manager and sidecar tests through full managed coverage. Verify `git diff --check`, staged boundaries, no secrets/raw provider bodies, no replacement characters introduced, and no unexpected model/route/tool-count changes. Tests use production response projection and real ledger reopen, not source-string tests alone.
- [ ] Use `superpowers:requesting-code-review` to dispatch **one fresh independent reviewer** after implementation, as the user requested. Review exact HEAD commit and `git diff 9057da3a...HEAD` (refresh main/base SHA if it moved; preserve all prompt commits). Supply approved spec/plan, evidence table, test results/exclusions, and unresolved lifecycle qualification. Reviewer checks first-stop/commit ordering, uncertainty before send, cleanup, quote snapshot identity, framing/repeats, artifact ownership, consumers, and legacy regressions. Implementer does not delegate implementation tasks.
- [ ] Resolve every Critical/Important finding, rerun affected verification, and obtain reviewer follow-up for fixes. Completion claims require fresh output and a cleared endpoint gate; if gate is unresolved, report an offline verified disabled implementation, not working long-term fal fallback. If enabled bindings cover only a subset, explicitly report unavailable tier/mode combinations.
- [ ] Present the tested reviewable branch for the user's next action. This task does not merge/deploy or send live requests. When locally deploying is authorized, read `rook:deploy-local-testing` and use its script mode appropriate to changed managed/UI **and Python payload** (managed-only alone is insufficient for Task 11). Report installed verification and process actions. A live paid provider test requires explicit authorization and is separate from hermetic tests; billing, video quality, deployed behavior, and remote cancellation guarantees remain unverified until that testing.

## Acceptance coverage and review checklist

| Spec acceptance cases | Owning plan tasks |
| --- | --- |
| 1 motivating I2V; 2 exact tiers/modes | 2, 4, 7, 10 |
| 3 unused fal key; 4 closed credential matrix; 5 direct fal evidence | 3, 4, 7, 9, 10, 11 |
| 6 options provenance; 7 incompatibilities/framing; 8 ordered media/parents | 2, 3, 4, 7, 8, 9, 10 (immutable preparation/actual sent-byte checks) |
| 9 snapshot during held submit; 10 failing route/intent/handle commits; 11 rejection crash windows | 4, 5, 7 |
| 12 blocked/failed stop append; 13 first stop/completion; 14 one budget/non-cooperation | 5, 6, 7, 8 |
| 15 late handle/cleanup; 16 restart/expiry/critical extensions/legacy dispatcher | 4, 5, 7 |
| 17 canonical quotes/caps/prices/stale UI | 2, 3, 4, 7, 9, 10, 11 (including A→B→A prepared-media barriers) |
| 18 provisional publication/media failures; 23 completed marker repair | 8, 9, 10 (including direct `/blob/{artifact_id}/{role}` video/sidecar streaming) |
| 19 real envelope consumers; 20 existing-provider/image/prompt regressions | 4, 7, 8, 9, 10, 11, 12 |
| 21 lifecycle evidence; 22 simultaneous independent jobs | 1, 2, 3, 7, 8, 12 |

Planning self-review: all spec sections map to tasks; the five Review Focus cases have owning regression tests; new interfaces are defined at their owning tasks; schema/legacy paths are explicit; implementation stays behind plan approval and binding admission. The review amendments bind quoted/prepared/sent media to deep-owned bytes and extend the completion fence to direct blob streams, with A→B→A barriers and actual resolver regressions. Test code blocks specify assertions and contracts, not production bodies. Documentation checks performed at plan delivery are recorded in the chat, separately from future runtime verification.


Execution checkpoint (2026-10-14): Tasks 1–11 are implemented and verified offline. Task 12 pre-review gates passed: 4,558 managed tests under the exact filter above; 55 Node UI tests; 89 Python contract/profile tests; managed Release build, zero errors and 481 existing compiler/platform/analyzer warnings. The newly introduced nullable dispatcher warning was corrected. The two exclusions remain the missing historical lifecycle spec and the absent ROOK_TASK7_HTTP_FIXTURE producer input. The baseline timing failure passed in the final full run. Endpoint continuity remains unqualified: every production fal Veo binding remains disabled. Native/RookBIM builds, deployment, live access, billing, quality, and remote cancellation guarantees were not tested. Independent whole-branch review is pending.
