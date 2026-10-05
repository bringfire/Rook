# Enterprise Google Media OAuth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` for implementation in this session, or `superpowers:subagent-driven-development` if the user selects that execution approach. Execute task-by-task with the checkpoints below. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Complete Google OAuth image and video generation against a firm's project through RookVision's existing provider, job, ledger, and artifact pipeline.

**Architecture:** Python remains the sole credential owner. Recover the existing owned-service token bridge selectively, then add binding-aware token admission and explicit managed Vertex providers. Reuse existing managers and persistence; extend cancellation outcomes and publication checks only where required to preserve job identity and terminal state.

**Tech Stack:** Windows, current Python runtime, existing `google-auth==2.56.3`/aiohttp/httpx, C# multi-target managed companion and net48 xUnit, HttpClient/System.Text.Json, existing FFmpeg support. No new dependency or native project change.

**Spec:** [Approved design](../../plans/2026-10-05-enterprise-google-media-completion-design.md).

## Global Constraints

- Planning source baseline: `bc19d4afaa5b4807ea944091e33f19d3012579c2`. Preserved work: `174b2675b6ff809acd16bf4627efe8abdfdbcde0`. Recheck current source before execution and reconcile overlapping changes explicitly.
- Reuse `VisionProviderRegistrations`, image/video registries, managers, JSONL ledgers, `ProviderJobHandle.ProviderMetadata`, artifact store/materializer, and sidecar pipeline. No second media backend, poller, generation queue, credential store, or server.
- Keep provider identifier `vertex_ai`. Existing `gemini`, fal, and Replicate transports/defaults retain their behavior. Do not expose retired Director capabilities.
- `VertexRecord.region` remains shared by Vertex text/readiness/Chirp and video. Media status, image `global` admission, and token refresh must not mutate it. An explicitly saved shared project/region changes existing text endpoints and recycles managed Chirp with a new generation; the UI must explain this consequence. Independent text/video regions are not introduced in this scope and would require a distinct field within the existing store, migration tests, and a reviewed plan amendment.
- Persist binding version 1, authorization generation, project, model, and location only. Never persist bearer/refresh tokens, client secrets, raw responses, headers, or video Base64.
- Inline video only, exactly one MP4; omit `storageUri`. `predictLongRunning` is submitted once per local job; polling uses `fetchPredictOperation` on that operation's bound model/project/location.
- Decoded maximum: `250 * 1024 * 1024` bytes. JSON transport maximum: `4 * ((maxDecodedBytes + 2) / 3) + 1024 * 1024` bytes using integer arithmetic. Submit/error envelope maximum: 1 MiB. Reject redirects.
- Provider HTTP operation deadline: 120 seconds aggregate. Lease issuance ceiling: 30 seconds. Local video monitoring deadline: 15 minutes. At most three read-only attempts, bounded 1/2-second backoff; never retry submit.
- Stop/disconnect can produce `Interrupted`, never a false remote-cancellation confirmation. Existing remote-cancel providers retain their semantics. Restart never automatically resumes or resubmits.
- Project/OAuth client are needed only for live acceptance. Automated tests use temporary stores/ledgers, fake HTTP/token refresh, and synthetic credentials.
- Build managed source before final tests. Earlier 150/25/53/211 pass counts are historical baseline evidence only.
- No version bump, release publication, installer redesign, dependency update, native C++ modification, or RookBIM/Revit behavior change. If an existing deployment workflow is invoked, retain its required managed-then-RookBIM ordering.
- Review checkpoints: token boundary (Task 2), race/publication boundary (Task 3), configuration ownership (Task 6), final verification (Tasks 8–9). Each task produces a focused commit; never blanket-cherry-pick the preserved commit.
- At each checkpoint, inspect the resulting code diff and fresh test/evidence output against the relevant invariants before advancing; record findings and any fixes in the verification report. Merely reaching the task or observing an exit code is not a checkpoint review.

## Review Focus

1. Malformed or legacy handles with missing binding must cause no Google request; pin this in Task 5.
2. A completion already in progress when stop/disconnect wins must neither overwrite `Interrupted` nor leave a completed artifact; pin barrier tests in Task 3.
3. Unknown submission outcomes and repeated UI clicks must not create automatic duplicate billed generations; pin transport tests in Task 5 and UI tests in Task 7.
4. Large inline JSON/Base64 can exceed the decoded limit's apparent memory cost; measure real process peaks and two-job concurrency in Task 8.
5. OAuth configuration must not be forwarded into Prime's independent credential store; pin dispatcher/abort tests in Task 6.

## File and interface map

Existing files are named below; new files follow their neighboring provider/test patterns. Resolve line numbers from the execution checkout instead of using stale plan offsets.

| Area | Files | Responsibility |
| --- | --- | --- |
| Python authorization | `mcp_server/src/rook/providers/vertex_auth.py`, `vertex_backend.py`, `vertex_oauth.py`; new `vertex_media_policy.py`, recovered `vertex_token_lease.py` | Closed media admission, expected binding, refresh, generation mutations, cancellation-safe OAuth commit. |
| Owned internal service | `mcp_server/src/rook/agent/chat/server.py`; new `vertex_configuration_http.py` beside it | Internal token and Vertex account configuration routes on the current server; exact nonce/Origin/no-store contracts. |
| Managed neutral token contract | recovered `src/Rook/Services/Vision/Image/Vertex/VertexAccessTokenContract.cs`; new `VertexAuthorizationBinding.cs` in the same directory | Lease/result/source and validated nonsecret binding; shared by image/video. |
| Managed owned-service adapter | recovered `src/Rook/UI/Chat/ChatServiceVertexAccessTokenSource.cs`; `ChatServiceManager.cs` | Atomic owned URI/nonce snapshot, closed token responses and binding checks. |
| Vertex image | new `src/Rook/Services/Vision/Image/Vertex/VertexImageCapabilities.cs`, `VertexImageProvider.cs`, `VertexImageProviderRegistration.cs`; new `Image/Gemini/GeminiImageWireCodec.cs`; existing `GeminiImageProvider.cs` | Pure shared image wire codec; distinct OAuth provider transport and registration. |
| Vertex video | new `src/Rook/Services/Vision/Video/Vertex/VertexVeoCapabilities.cs`, `VertexVeoOptionsCodec.cs`, `VertexVeoClient.cs`, `VertexVeoProvider.cs`, `VertexVeoProviderRegistration.cs`; new `Video/VeoRequestWireCodec.cs`; existing `VeoClient.cs` | Bounded inline output and model-specific request/lifecycle contracts. No URL output path. |
| Manager boundary | `Generation/ProviderCancelOutcome.cs`; new `Generation/IGenerationPublicationGuard.cs`; `Video/VideoJobManager.cs`, `Video/VideoJobRecordFactory.cs`; `Image/Jobs/ImageJobManager.cs` | Explicit local stop, serialized terminal transitions, authorization checks around artifact publication, cancellation-race cleanup. |
| Composition | `src/Rook/RookSubsystemRoot.cs`, `RookPlugin.cs`, `Services/Vision/VisionProviderRegistrations.cs`, `Video/VideoSubsystemFactory.cs`, `InternalBridge/NativeGhBridgeRegistrar.cs`, `UI/Vision/VisionWebSurface.cs` | Same provider registry/root for UI and callback paths, token adapter before lazy subsystem access. |
| Account/UI integration | `src/Rook/UI/Chat/RookChatConfigurationDialog.cs`; new `UI/Chat/AgentChatClient.VertexConfiguration.cs`; `src/Rook/UI/Vision/Resources/app.js` | Add Enterprise Google account section to existing settings surface; explicit provider choice/stop label/submit locking. |
| Tests/evidence | corresponding `mcp_server/tests/test_vertex_*.py`, `test_chat_server.py`, new `test_vertex_configuration_http.py`; corresponding managed provider/manager/UI tests; new `scripts/vertex_media_acceptance.py`, `mcp_server/tests/test_vertex_media_acceptance_harness.py`, managed `VertexInlineVideoMemoryTests.cs` | Separate deterministic automated evidence, memory probe, and credentialed installed acceptance. |

New signatures used across tasks:

```text
Python VertexMediaBinding(binding_version:int, authorization_generation:str,
                        project_id:str, location:str, model_id:str)
VertexTokenLeaseService.acquire(model:str, location:str,
                               expected_binding:VertexMediaBinding|None=None) -> VertexTokenLease
VertexTokenLeaseService.validate_binding(binding:VertexMediaBinding) -> None  # no Google request

C# VertexAuthorizationBinding(int BindingVersion, string AuthorizationGeneration,
                             string ProjectId, string Location, string ModelId)
IVertexAccessTokenSource.AcquireAsync(string qualifiedModelKey, string location,
    VertexAuthorizationBinding? expectedBinding, CancellationToken ct) -> Task<VertexAccessTokenResult>
IVertexAccessTokenSource.ValidateBindingAsync(VertexAuthorizationBinding binding,
    CancellationToken ct) -> Task<VertexAccessTokenFailure?>
IGenerationPublicationGuard.ValidatePublicationAsync(
    IReadOnlyDictionary<string, JsonNode> metadata, CancellationToken ct) -> Task<GenerationError?>
LocalStopOnlyOutcome : ProviderCancelOutcome
```

Binding serializers validate lengths/closed keys and deep-copy metadata. `ValidateBindingAsync` uses the same internal token boundary with a non-refresh validation operation, not a new broker. The publication guard is an opt-in provider seam; existing providers do not implement it. Video supplies handle metadata; sync image supplies result-envelope metadata.

## Task dependency and commit gates

| Task | Prerequisites | Independently buildable deliverable |
| --- | --- | --- |
| 1 | Approved spec | Isolated checkout and freshly rebuilt baseline; no recovered product code. |
| 2 | 1 | Token/binding adapters and defined `IGenerationPublicationGuard`; shared-region regressions pass. |
| 3 | 2 | `LocalStopOnlyOutcome` plus complete manager/consumer handling and publication fences, tested with synthetic providers. |
| 4 | 2, 3 | Vertex image provider implements the already-defined guard and uses already-tested manager publication handling. |
| 5 | 2, 3 | Vertex Veo provider returns the already-handled local-stop outcome and implements the existing guard. |
| 6 | 2 | Owned Vertex configuration with explicit shared text/video region semantics; native execution performs it after Task 5. |
| 7 | 4, 5, 6 | Registry/UI wiring with tested providers, settings, and interruption semantics. |
| 8 | 1–7 | Freshly rebuilt automated acceptance and measured memory evidence. |
| 9 | 8 plus live prerequisites | Separately recorded installed live acceptance. |

Every task commit must build the affected managed source and pass that task's relevant checks. Do not commit a provider referencing a later-defined contract, introduce a union member without updating its consumers, or defer a compile failure to a later task. Tasks 4/5 remain separate commits, but native execution follows numeric order.

## Task 1: Recover source and establish a rebuilt baseline

**Files:** read current and preserved files listed above; update design/plan status and a new `docs/superpowers/reports/2026-10-05-enterprise-google-media-verification.md`.

**Interfaces:** consumes exact approved spec and recorded commit IDs; produces an isolated execution checkout and fresh baseline evidence, with no recovered product code yet.

- [x] Inspect `git status`, attached worktrees, and the preserved branch. Use `superpowers:using-git-worktrees` at execution time; reuse a suitable attached checkout or create a managed worktree from current main. Preserve the parked branch unchanged.
- [x] Compare preserved/current ownership, startup, configuration, shutdown, and callback wiring. Write a path-by-path recovery list. Preserve current ACP/Prime chat routes; recover only token-specific changes, not the old chat implementation.
- [x] Verify first catalog entries against current primary Google documentation: candidates `vertex_ai/gemini-3.1-flash-image` at `global` and `vertex_ai/veo-3.1-fast-generate-001` at `us-central1`. Pin confirmed IDs/options/locations in the task evidence before coding; stop for a concrete contract discrepancy, not for missing live credentials.
- [x] Run `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter 'FullyQualifiedName~Services.Vision|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~ChatServiceManagerTests' --verbosity minimal` without `--no-build`. Run the five existing Python Vertex test files with the checked-out source interpreter. Record failures/warnings and exact tested head; do not repair unrelated failures.
- [x] Commit the approved design, plan, and baseline report explicitly. These documentation directories are ignored in the current repository; use `git add -f` for these exact files only, not the entire docs tree.

## Task 2: Recover and extend the owned token boundary

**Files:** Python auth/backend/policy/token/server files; managed contract/binding/adapter/manager files in the map; create `src/Rook/Services/Vision/Generation/IGenerationPublicationGuard.cs`. Tests: `test_vertex_token_lease.py`, `test_vertex_auth.py`, `test_vertex_backend.py`, `test_vertex_runtime_integration.py`, `test_chirp_manager.py`, `test_chat_server.py`; `ChatServiceVertexAccessTokenSourceTests.cs`, `ChatServiceManagerTests.cs`, new `GenerationPublicationGuardContractTests.cs` beside the generation tests.

**Interfaces:** produces all Python and managed binding/token signatures above, `IGenerationPublicationGuard.ValidatePublicationAsync(metadata, ct)`, and `ChatServiceManager`'s recovered atomic owned connection snapshot. Defines the publication interface only; its manager consumers are implemented in the next task before a production provider implements it. Internal path remains `/internal/providers/vertex/access-token`.

- [x] Add failing tests `expected_binding_rejects_rotation_before_refresh`, `rotation_during_refresh_returns_no_token`, `ordinary_refresh_preserves_binding`, and `locations_are_validated_per_media_model`. Assert zero downstream HTTP calls after generation/project mismatch and no token in errors/repr.
- [x] Add route tests for any Origin, wrong/missing nonce, wrong method, extra JSON keys, absent expected binding on a follow-up operation, and oversized body. Assert no-store on every response and no public MCP discovery entry.
- [x] Add managed tests `OwnedSnapshot_UsesOneServiceLifetime`, `LeaseMismatch_RejectsBeforeGoogleRequest`, `ValidateBinding_DoesNotRefresh`, and caller cancellation/30-second deadline. Run these tests and confirm failure from the missing behavior.
- [x] Add `PublicationGuard_HasMetadataAndCancellationContract` using a minimal test implementation; define the interface with the exact signature in the interface map. Rebuild the managed project/test assembly now so later tasks never reference a missing type. Do not introduce `LocalStopOnlyOutcome` here; its consumers belong to the next task's atomic change.
- [x] Selectively recover the parked lease primitive and adapter. Implement closed acquire/validate wire operations using existing nonce admission; expected binding checks run before credential resolution and after refresh. Keep cached token keyed by generation/project and revalidate requested model/location on reuse. Never admit Veo through the text-only `vertex_gemini_model_name` parser.
- [x] Retain fixed OAuth store/schema/DPAPI ownership and existing backend mutations. Preserve `VertexRecord.region` as the existing shared **text/Chirp and video location**, not a video-specific replacement. Image uses its registered fixed `global` location without changing the record. `save_vertex_configuration` atomically writes an explicitly requested shared project/region update with a fresh generation through the existing mutex/store path. For image acquisition, admit `global` independently of the stored shared region; for Veo, require the requested location to match the record region and supported catalog. A cached bearer may serve both admitted locations, but every returned lease must carry that call's validated location, not a previous caller's cached location.
- [x] Add regression tests `test_media_image_global_does_not_mutate_text_region`, `test_rejected_video_region_preserves_record_bytes`, and `test_media_refresh_preserves_text_kwargs_and_generation`. Assert unchanged credential bytes/generation, unchanged `apply_vertex_litellm_arguments` project/location, and zero configuration-save/recycler calls during passive media status or lease acquisition.
- [x] Add `test_explicit_shared_region_save_rotates_once_and_updates_text_readiness` in `test_vertex_backend.py` and `test_shared_region_save_recycles_managed_chirp` in `test_chirp_manager.py`/runtime integration fixtures. Save from `global` to the supported video region deliberately; assert a fresh generation, unchanged protected OAuth material, original shared project semantics, the exact new regional `countTokens` URL, updated text runtime kwargs, managed-Chirp retirement/relaunch at the same owned port, and rejection of old-generation media handles. A failed/invalid save preserves prior record bytes and routing.
- [x] Run Python token/backend/route tests and rebuilt managed adapter tests. Expected: new contracts pass and existing chat/auth contracts remain intact. Commit the focused token-boundary change.

## Task 3: Make stop, authorization interruption, and completion race-safe

**Files:** `ProviderCancelOutcome.cs` and existing manager/record files in the map; consume (do not introduce) the publication interface from Task 2. Tests `VideoJobManagerTests.cs`, `VideoJobRecordFactoryTests.cs`, `JsonlVideoJobLedgerTests.cs`, `ImageJobManagerTests.cs`, `UnionClosureTests.cs`, `SubmitOutcomeExhaustivenessTests.cs`, `InvariantTests.cs`, `VideoOpHandlerTests.cs`; create `src/Rook.Tests/Services/Vision/Video/GuardedVideoProviderFixture.cs` as a synthetic provider fixture.

**Interfaces:** consumes Task 2's binding/publication contract. Introduces `LocalStopOnlyOutcome` together with all manager/consumer/union-test changes; it maps to `JobCancelResult.Ok(Interrupted)`. Use synthetic guarded providers for tests so this task does not depend on the forthcoming Vertex image/video implementations. No job/ledger schema replacement.

- [x] Add barrier-driven tests named `StopWinsBeforeFetchReturn_RemainsInterrupted`, `DisconnectWinsBeforeArtifactCreate_NoArtifact`, `DisconnectWinsAfterArtifactCreate_RemovesArtifact`, `StopWinsBeforeCompleteAppend_NoCompleteRecord`, and `CompleteWinsBeforeStop_PreservesComplete`. Use `TaskCompletionSource` with asynchronous continuations, not timing sleeps.
- [x] Add the synthetic fixture, `LocalStopOnlyOutcome`, its video manager translation, all exhaustive consumers, and closure tests as one change. Assert existing image/remote-cancel consumers continue to build and retain their prior semantics. No production provider emits the new outcome until this task's rebuilt checks pass.
- [x] Add `BackgroundCancellation_CannotOverwriteInterrupted`, `AuthChangedStatus_UsesInterruptedNotError`, `MissingBindingCannotPublish`, and `RestartPreservesBindingAndMakesZeroProviderCalls`. Assert the full ledger sequence, final state, artifact-store contents, remote call counts, and cancellation message.
- [x] Introduce a per-running-job transition gate/stop reason in the current manager. Serialize terminal ledger decisions across background/cancel paths; never hold this gate during remote HTTP or sidecar extraction. All terminal writes re-read durable state and cannot overwrite an already committed terminal record. Adapt the existing cancellation handler to preserve `Interrupted` for local-stop/auth reasons, including the Vertex branch before a remote handle is available. Stop during dispatched submission records an unknown remote outcome and never reports remote cancellation.
- [x] Apply publication checks before `ArtifactStore.Create` and before completion commit using original handle/envelope binding. On stop or failed final validation, delete only the artifact minted by this job with `ArtifactStore.Delete(Guid)`; assert cleanup and preserve original remote metadata. Do not delete older completed artifacts. Sidecar finalization may finish independently but must not commit job completion after stop wins.
- [x] Update every outcome consumer and closure test for the new union member. Preserve remote cancellation rejection behavior for fal/API-key Veo/Replicate and preserve completed-job no-op handling.
- [x] Run rebuilt manager/ledger/union/handler/image tests. Repeat the deterministic race suite 25 times as a concurrency check; this repetition is justified by the new interleavings, not a substitute for barriers. Commit the manager-boundary slice after its review checkpoint.

## Task 4: Complete Vertex image generation through the existing registry

**Files:** image/provider/composition files in the map; tests `VertexImageProviderTests.cs`, `GeminiImageProviderTests.cs`, `VisionProviderRegistrationsTests.cs`, `DefaultImageProviderRegistryTests.cs`, `RookSubsystemRootTests.cs`, existing callback/web-surface source tests.

**Interfaces:** `VertexImageProvider : IImageProvider, IGenerationPublicationGuard`; same existing `SubmitAsync` signature; returns `SyncSubmitOutcome` with existing `InlineArtifactBody` and allowlisted `vertex_binding` envelope metadata. Implements the publication guard from the interface map.

- [x] Write failing tests for the confirmed global endpoint/Bearer header, no API-key header, one explicit qualified catalog entry, unchanged AI Studio short-name/default routing, bounded response, malformed image data, fixed error mapping, cancellation, and authorization change after response.
- [x] Extract only pure success/request codec methods from `GeminiImageProvider`; keep its endpoint, credential lookup, and error handling separate. Implement the Vertex provider with registered model/location admission, no redirects/automatic submission retry, and revalidation before returning success.
- [x] Implement the publication guard and include a deep-copied nonsecret binding in the result envelope. Do not create an image-only credential store or special artifact write path.
- [x] Recover root/adapter injection and shared UI/callback registry wiring selectively. Inject the same neutral source into the future video factory. Existing no-Vertex construction remains supported through the unavailable token source.
- [x] Run rebuilt image/registration/root/bridge/web-surface tests and the existing missing-key parity tests. Commit the image slice independently.

## Task 5: Add stateless Vertex Veo transport and provider

**Files:** Vertex video files plus pure Veo request codec; tests new `VertexVeoClientTests.cs`, `VertexVeoProviderTests.cs`, `VertexVeoOptionsCodecTests.cs`, `VertexVeoProviderRegistrationTests.cs`, existing `VeoClientTests.cs`/`VeoOptionsCodecTests.cs`.

**Interfaces:** `VertexVeoProvider : IModelAwareVideoProvider, IGenerationPublicationGuard`; existing submit/status/result/cancel signatures. `VertexVeoClient.SubmitAsync(binding, accessToken, request, resolvedMedia, ct)` returns an accepted operation or fixed failure; `FetchOperationAsync(binding, accessToken, operationName, decodeVideo, ct)` returns in-flight/terminal/failure data without retaining per-job state. Only the provider constructs handles/envelopes.

- [x] Add failing wire tests: submit uses `sampleCount:1` and omits `storageUri`; poll is POST `fetchPredictOperation` with the original full name; URI/project/model/location mismatch is rejected before HTTP; legacy unbound handles cause zero HTTP calls.
- [x] Add `Submit_ResponseLost_SendsExactlyOnce`, including 401/429/5xx/timeout/invalid success/redirect cases. Assert one POST and `Retryable:false`; local source/lease failures produce zero submits. A seed is never treated as idempotency.
- [x] Add inline result tests for one MP4, empty/malformed Base64, encoded/decoded cap, overlarge headers/actual stream, `gcsUri`/HTTP output, conflicting fields, extra samples, terminal operation errors, and safety filtering. Use streamed fixtures rather than allocating a second expected 250 MiB video.
- [x] Implement pure shared Veo input encoding only where current Google contracts match; keep Vertex's person-generation mapping/options separate when Developer API values differ. Implement fixed allowlisted errors with null `ProviderDetail`, redirect-disabled transport, bounded UTF-8 reads, one decode in result-fetch only, and per-operation deadline/retry policy.
- [x] Implement handles with original operation/binding, status completion without Base64 in the handle, and result fetch of the same operation. Bind and acquire each read-only retry independently; at most three attempts within one aggregate deadline. `CancelAsync` returns `LocalStopOnlyOutcome` and performs zero remote requests.
- [x] Run rebuilt new/existing Veo tests plus secret-sentinel scans of handles/envelopes. Commit the provider slice.

## Task 6: Reuse account configuration UI while preserving credential ownership

**Files:** Python `vertex_configuration_http.py`, server, OAuth/backend/media-policy files; managed dialog and new `AgentChatClient.VertexConfiguration.cs`; tests new `test_vertex_configuration_http.py`, existing `test_vertex_oauth.py`, `RookChatConfigurationTests.cs`, and new `VertexConfigurationClientTests.cs`.

**Interfaces:** one internal `/internal/providers/vertex/configuration` POST surface on the existing owned server; closed operations `status`, `connect`, `save`, `disconnect`. Managed `ReadVertexConfigurationAsync(ct)`, `ConnectVertexAccountAsync(clientConfigurationPath, projectId, videoLocation, ct)`, `SaveVertexMediaConfigurationAsync(projectId, videoLocation, ct)`, `DisconnectVertexAccountAsync(ct)` return fixed status/result DTOs. Image location is the registered `global` constant; the approved video location is explicit.

- [x] Write failing tests proving Vertex operations never spawn Prime or write Prime credentials. Test any Origin/wrong nonce/unknown operation/extra fields/body cap, two overlapping connects, stream/client abort, browser refusal, no refresh token, failed settings persistence, and shutdown. Assert cancellation preserves prior credential bytes and no orphan mutation occurs after the caller aborts.
- [x] Add an Enterprise Google section to the existing dialog with shared project, **Vertex text and video location**, desktop OAuth configuration file path, connect/disconnect/save controls, and fixed local status. Show: "Changing this project or location also changes Vertex text and Chirp routing and interrupts active Vertex media jobs." Preserve current values on opening/status reads; require an explicit save to change them. If the current text region is unsupported by video, keep it and report video unavailable until the user deliberately chooses a supported shared region. Read the client file only in Python; client-secret material never crosses to managed UI. Reuse browser opening/operation busy/cancellation UI patterns without sending Vertex into the closed Prime configuration protocol.
- [x] Implement the narrow internal handler with exact nonce/no-Origin/no-store requirements and a single in-flight mutation slot. Call existing `connect_vertex_oauth`, `save_vertex_configuration`, and `disconnect_vertex`; add cooperative cancellation checks in OAuth callback waiting and immediately before commit. Hold the slot until a cancelled worker actually settles, with the existing bounded OAuth deadline; no background queue or persistent operation registry.
- [x] Validate account/project/location mutations against Task 2's generation fence. Status is local/network-free and never calls a generation/readiness endpoint. Failed login preserves prior settings/credential material.
- [x] Add UI/client regressions `OpenMediaSettings_PreservesExistingTextRegion`, `UnsupportedVideoLocation_DoesNotAutoMigrateText`, and `ExplicitSharedRegionSave_ExplainsTextAndChirpImpact`; rerun Task 2's readiness/text/generation/Chirp regression tests. Never rewrite an existing region merely to populate a supported dropdown default.
- [x] Run Python OAuth/configuration tests, rebuilt dialog/client tests, and existing Prime configuration tests. Commit this configuration slice after its ownership checkpoint.

## Task 7: Wire the provider choice and stop/submit UI into RookVision

**Files:** registration/root/video-factory/web-surface/callback files; `app.js`; tests `VisionProviderRegistrationsTests.cs`, `VideoSubsystemFactoryTests.cs`, `DefaultVideoProviderRegistryTests.cs`, `VisionWebSurfaceTests.cs`, `VisionQueueUiSourceTests.cs`, `VideoOpHandlerIntegrationTests.cs`.

**Interfaces:** existing registry/request/handler envelopes remain in use; optional neutral token source supplied by the root/factory. Vertex stop returns existing state `interrupted` and its fixed message, not a new endpoint/backend.

- [x] Add tests for one explicit Enterprise image/video choice, same registry in panel and native callback, no credential-key slot for Vertex, unchanged default provider, and unavailable source producing a typed failure.
- [x] Add UI tests `VertexStop_ShowsMonitoringStoppedNotCancelled`, `DoubleClickSubmit_DispatchesOnce`, `UnknownSubmission_DoesNotAutoRetry`, and `ExplicitNewSubmission_ShowsPossiblePriorCharge`. Test stop-result/complete-result race rendering against latest job state.
- [x] Add registrations and factory injection. Use existing codecs, price model interfaces, and estimate envelopes; mark Vertex pricing provenance unverified until primary pricing has been checked rather than copying AI Studio rates silently.
- [x] Render the explicit provider label and Vertex stop action through current queue controls. Maintain one in-flight submit lock. Display the specified warning for unknown outcomes before offering a deliberately new job; do not add automatic recovery.
- [x] Run rebuilt composition/UI/handler tests and relevant Python vision MCP schema tests, confirming no public token/configuration tools. Commit the UI/composition slice.

## Task 8: Automated acceptance, bounded-memory probe, and fresh source verification

**Files:** new `src/Rook.Tests/Services/Vision/Video/Vertex/VertexInlineVideoMemoryTests.cs`, new `scripts/vertex_media_acceptance.py`, new `mcp_server/tests/test_vertex_media_acceptance_harness.py`, verification report. Product edits only if a failing check identifies a cause within preceding tasks.

**Interfaces:** source-only acceptance modes `automated` and `live`; JSON evidence has separate `automated`, `memory`, and `live` sections with pass/fail/not-run/inconclusive states. Test-only token-cache invalidation uses dependency injection or the existing harness's owned service instance; no production/MCP invalidation route.

- [x] Write harness tests asserting live cannot be marked passed by mocks, a missing account/project/installed interpreter yields `not_run`, operation completing before intervention yields `inconclusive`, and the default live budget is exactly one image/three videos. Capture fixed evidence fields from the spec and scan secret sentinels.
- [x] Run the deterministic automated scenarios from Tasks 2–7 end to end through managers/artifact store using temporary runtime data. Include local stop, account/project/location mutation, delayed completion, response-loss submission, restart, and forced refresh. Zero real Google calls in this mode.
- [x] Implement an opt-in memory probe in a fresh testhost process with a streaming synthetic JSON/Base64 fixture. Exercise 1, 16, 64, and 250 MiB decoded output; measure pending terminal poll (no decode), result fetch (decode), materialization/publication, and cleanup separately. Sample working set/private bytes every 10 ms and record OS `PeakWorkingSet64` as well as baseline, elapsed time, GC/allocation counters when available, and retained bytes after disposal/full GC. Do not substitute `GC.GetTotalMemory` for process peak.
- [x] Exercise two simultaneous maximum-size jobs, matching `VideoJobManager.DefaultMaxConcurrentJobs == 2`; include oversized and cancelled streams. Record host architecture, available RAM, process limits, and fixture methodology. The probe fixture must not itself hold a second full encoded/decoded video. Any OOM, unbounded growth beyond capped inputs, unexplained retained full payload, or unsafe two-job peak blocks completion. Reduce copies/stream parsing within the existing transport before retrying; do not silently lower the approved cap or concurrency. Report measured peaks, not an invented universal memory threshold.
- [ ] Rebuild all affected managed target frameworks with `dotnet build src/Rook/Rook.csproj --configuration Debug`, then run `dotnet test src/Rook.Tests/Rook.Tests.csproj --configuration Debug --filter 'FullyQualifiedName~Services.Vision|FullyQualifiedName~Handlers.Vision|FullyQualifiedName~VideoOpHandler|FullyQualifiedName~ImageJobOpHandler|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~UI.Chat|FullyQualifiedName~UI.Vision' --verbosity minimal` WITHOUT `--no-build`. Rerun the opt-in memory probe against that output. Record actual assembly timestamp/hash and tested commit/patch.
- [x] Run the Python Vertex/OAuth/backend/token/configuration/acceptance/route suites and existing vision MCP contract suites against the execution checkout. Use current test-data isolation; do not copy old passing evidence or inherited installed credentials into automated tests. Record warnings and failures separately. Run `git diff --check` and review the complete change against the approved spec before committing automated verification evidence.

## Task 9: Installed live acceptance, separately reported

**Files:** source-only harness and verification report; deployment uses the repository's existing reviewed workflow rather than a new packaging/backend path.

**Interfaces:** consumes passing rebuilt automated gates, installed exact commit/patch, desktop OAuth client configuration path, approved business identity/project, chosen supported model/location, and an explicit one-image/three-video budget. Produces sanitized live evidence, or explicit incomplete/not-run evidence.

- [ ] Verify installed provenance and use the existing local deployment skill only when deploying is authorized. Do not install the parked build or source-unverified payload. Live OAuth browser consent is completed by the user; preserve prior production authorization unless the acceptance procedure explicitly calls for its replacement/disconnect.
- [ ] Generate one image and decode/hash/measure it. Use the registered model's confirmed pixel/aspect-ratio contract, not file-extension inspection.
- [ ] Video 1: exactly one short submit; after an observed in-flight poll invalidate only its in-memory lease, observe actual Google refresh and subsequent same-binding poll, fetch inline MP4, check dimensions/duration within 0.5 s, decode first/middle/last frames using existing FFmpeg, and explicitly verify playback in RookVision. Record forced refresh as distinct from natural expiration.
- [ ] Video 2: exactly one short submit; disconnect after an observed in-flight poll. Verify `Interrupted`, no later admitted Google calls/artifact publication, and no resume or identity switch after reconnect. Report remote cancellation unconfirmed.
- [ ] Video 3: exactly one short submit; restart after operation/binding persistence. Verify `Interrupted`, preserved nonsecret handle, zero automatic submits/polls/fetches, and previously completed artifacts still accessible. Do not submit a fourth live video to exercise local stop: local-stop/race coverage belongs to the automated section in this budget.
- [ ] Account/project/location changes, local stop, response-loss, redirect/cap errors, and the worst-case memory probe are automated acceptance entries, not claimed as live tests. Report exactly which three-video cases ran; early completion is inconclusive and needs a separately authorized budget increase for a retry.
- [ ] Write sanitized evidence with tested Rook/Chirp commits where applicable, dirty/patch hash, installed versions/assembly hash, models/locations, consistent project/account labels, timestamps, per-action counts, refresh count, ledger transitions, artifact hashes/sizes/dimensions/duration, decode/playback observation, memory report linkage, and separate status for every automated/live case. Scan secrets locally without emitting them.
- [ ] Final review checks all spec requirements, current diffs, fresh build/test evidence, and live evidence. Mark full completion only when required live cases pass; otherwise report implementation/automated completion and the specific outstanding live case without pretending production assurance.

## Self-review and execution handoff

Spec coverage: ownership/recovery and publication-interface definition Tasks 1–2; binding/cancellation/publication/restart races Task 3; image/provider reuse Task 4; wire/output/retry Task 5; OAuth UI/ownership Task 6; registry/UI parity Task 7; fresh build, deterministic acceptance and peak memory Task 8; measured installed business-account assurance Task 9. All five Review Focus items have owning tests.

The user approved the written specification on 2026-10-05. The user has technically approved this plan conditional on dependency and shared-region corrections and recommended native execution. Both corrections are incorporated. Execute natively through substantive code/evidence review checkpoints when implementation is started by the user; this correction turn does not start product implementation or establish verification of new code.
