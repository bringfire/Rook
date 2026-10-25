# RookVision configurable fal models implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add compatible fal image and video endpoints, including usable controls in the panel and MCP, by editing packaged JSON definitions and their manifest alone.

**Architecture:** Compile team-maintained definitions into an immutable catalog. Pure adapters translate a normalized request; shared fal execution, existing managers, and artifact services own transport and job lifecycle. UI and MCP consume the same descriptors, and jobs retain their original binding after catalog changes.

**Tech Stack:** Existing C# / System.Text.Json, net48/net7.0/net8.0 companion; native C++ Vision callback; vanilla JavaScript; Python MCP; xUnit, Node's built-in test runner, pytest, PowerShell. No new external dependencies.

**Spec:** [Approved design, 2026-10-25](../specs/2026-10-25-fal-model-definitions-design.md). Read it with this plan. Runtime source baseline is `807bfed4`; approved design was recorded in `f2e9e291`. Reconcile concurrent source changes before execution.

## Global Constraints

- First-release acceptance: one new image endpoint and one new video endpoint, controls usable through both UI and MCP, configuration changes only after runtime freeze.
- Team-maintained catalog only. No user override search path, hot reload, automatic OpenAPI import, or network refresh.
- `schema_version` is initially `1`. JSON definitions live under `src/Rook/Services/Vision/Fal/Models/`; installed JSON lives beside each managed runtime under `vision-models/fal/`.
- Keep all existing public registrations, including FLUX Schnell and Kling v3 Standard. Reference them through test-only synthetic identities; do not migrate their public IDs in this release.
- Support single-result text-to-image, image editing with optional ordered references, text-to-video, image-to-video, and first/last-frame video. Reference-only video needs separate qualification. No new workflow primitives beyond the approved design.
- Configured image jobs are asynchronous in Rook even for synchronous fal invocation. Configured video uses the queue. Preserve current interrupted-on-restart semantics; never automatically replay an unknown submission.
- Adapters are pure. Definitions cannot supply credentials, hosts, headers, executable code, paths to DLLs, or arbitrary expressions.
- Missing pricing makes paid admission unavailable. Configured submissions require quote fingerprint and maximum estimated cost. Legacy confirmation and response contracts stay intact.
- Preserve Google fallback and source-framing behavior. A new definition does not imply fallback equivalence or Veo Fit/Fill qualification.
- Use existing bounded media services; definition limits may tighten runtime ceilings only. New image media references use artifact IDs and roles.
- Native handlers remain thin and use the existing Vision callback ABI. Native and managed route changes must ship together. No `.vcxproj` or `.vcxproj.filters` changes; no Revit references outside RookBim.
- Verify affected managed targets and native changes on Windows with Rhino 8. Native MFC builds use MSVC `14.44.35207`. Do not claim a build, installed verification, or paid smoke test without executing it.
- This document authorizes no paid probes. The execution-stage acceptance run requires selected settings and a concrete total spend cap from the maintainer.

## Review Focus

1. A manifest path escapes through `..`, an absolute path, or a Windows junction; or one definition collides with a legacy ID. Reject the entire configured catalog while preserving legacy discovery. Task 1.
2. A supplied false/zero/null is confused with an absent value; a decimal step or overlapping condition silently changes a control. Preserve suppliedness, reject invalid values, and omit only inapplicable defaults. Task 2.
3. The quote was for different media bytes, a changed audio option, or an old pricing/definition revision. Reject before upload or paid dispatch, including a race between admission and dispatch. Tasks 3 and 6.
4. fal accepted a request but recording the handle failed, or cancellation raced with completion. Never replay, never publish after the stop fence, and preserve uncertainty independently of remote cancellation. Tasks 3 and 5.
5. A catalog entry disappears after restart, or a persisted snapshot has an unsupported version. History and permitted cleanup use the stored binding; neither path resolves the latest model or chooses the first `fal` registration. Task 5.

---

## Delivery and review boundaries

One plan is appropriate: catalog, transport, persistence, UI, MCP, and packaging jointly implement one contract and one release gate. Each task below has a focused commit and verification cycle. A stage can be reviewed and rejected independently; completing a stage is not evidence that the product can ship.

| Stage | Tasks | Reviewable result / exit gate |
| --- | --- | --- |
| A. Definition contract | 1–2 | Closed format, canonical identities, deterministic validation and mapping |
| B. Execution contract | 3–4 | Shared fal protocol and provider wrappers, no configured model-ID branches |
| C. Durable admission | 5–6 | Persisted bindings, interruption semantics, exact/bounded quotes and confirmations |
| D. Managed integration | 7 | Registries and handlers expose the same descriptors and request semantics |
| E. Product surfaces | 8–9 | Panel controls, native routes, and MCP work end to end with fixtures |
| F. Distribution and proof tooling | 10–11 | Packaged catalogs, config-only copy, generic harness, regression evidence; freeze runtime |
| G. Release gate | 12 | Two held-out endpoints, JSON-only diff, four live jobs, unchanged runtime hashes |

Follow this order. Tasks 8 and 9 may proceed independently after Task 7 if the chosen execution method supports it; merge and verify both before Task 11. Do not split core interfaces across simultaneous edits. At each stage review the diff, named test results, and remaining failure cases before continuing.

All paths below are relative to `C:/UDEV/Rook`. New files are explicitly marked **Create**; existing files are **Modify**. Keep tests beside the corresponding existing vision tests. Do not reorganize unrelated source files.

### Shared contract choices

The following types are introduced in the tasks named below; these are implementation choices, not additional product scope:

| Type / owner | Required contents |
| --- | --- |
| `FalCatalogSnapshot`, `FalOperationBinding` / Task 1 | Immutable catalog and operation binding; model/definition IDs, revision/hash, operation, exact submit endpoint, separate lifecycle root, invocation, adapter ID/version, fields/media/constraints/result/pricing/evidence. `GetOperation(modelId, operationId)` does not infer suffixes. |
| `FalModelInput`, `FalMediaInput` / Task 2 | Supplied request-fields JSON, supplied options JSON, explicit/optional operation ID, ordered semantic media bindings. Each media input has semantic role, ordinal, and existing `MediaRef`; the semantic role is distinct from the artifact's stored role. |
| `FalNormalizedRequest`, `FalNormalizationResult` / Task 2 | Pinned binding; supplied/effective request fields and options; inactive fields; selected media instructions and pricing selectors. Result is success or field errors, never a partially valid request. Defensive copies at JSON/list boundaries. |
| `FalPreparedMedia` / Task 2; `FalMediaSnapshot` / Task 3 | Prepared-value contract is declared before adapters use it; preparation later supplies transient transport values. Snapshots own immutable bytes, MIME, source artifact identity/role, semantic role/order and digest. Disposal and existing media ceilings remain explicit. |
| `FalExecutionSnapshot` / Task 5 | Versioned minimal binding, normalized controls, pricing and media provenance, dispatch state, validated handle, result mapping. No credentials or reusable uploaded-media source URLs. |
| `FalPricingSnapshot` / Task 5; `FalQuote`, `FalSubmitConfirmation` / Task 6 | Pricing persistence shape precedes its calculator: decimal quantity/range and USD estimate, unit/rate/revision provenance. Quote fingerprint covers binding, effective inputs, content digests and pricing; confirmation contains fingerprint and `decimal MaxEstimatedCostUsd`. |
| `FalOperationDescriptor` / Task 2 | Published fields, constraints, media, legacy capability projection, identity/source, job entry point, pricing availability, and field errors. Returned JSON is the common panel/MCP contract. |

Use sealed immutable classes and existing result/outcome patterns. Do not expose mutable `JsonObject` instances from catalog or job state. Expected validation failures return typed errors; translate them to the existing handler error envelopes. Co-locate each small named result type with its producing service, and each media/confirmation value type with the owning contract file. Use one normalizer for estimate and submit; JavaScript can provide presentation hints but is never the authoritative validator.

### Verification conventions

Focused managed command, replacing `FILTER` with the exact filter in each task:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug -f net48 --filter 'FILTER' -p:RhinoPluginDir=
```

Use the repository virtual environment for Python: `mcp_server/.venv/Scripts/python.exe`. Node and PowerShell tests require no new dependency. Each red step must fail for the missing behavior, not an unrelated environment problem. Each green step must select and pass the intended tests; a zero-test run is a failure. Do not run paid `LiveSmoke` tests in these cycles. The test snippets below name the test and its essential assertions; their `case`/fixture helpers are local test builders introduced in the same test file, not new production APIs.

## Stage A — Definition contract

### Task 1: Compile and atomically load a closed catalog

**Files**

- Create: `src/Rook/Services/Vision/Fal/Models/FalModelDefinition.cs`, `FalOperationBinding.cs`, `FalCatalogSnapshot.cs`, `FalCatalogCompiler.cs`, `FalCatalogLoader.cs`, `FalCanonicalJson.cs`, `catalog.json` in that same directory.
- Create: `docs/vision/fal-model-definition-v1.md` (format, complete synthetic examples, maintainer checklist).
- Create tests: `src/Rook.Tests/Services/Vision/Fal/FalCatalogCompilerTests.cs`, `FalCatalogLoaderTests.cs`, `FalCanonicalJsonTests.cs` in that test directory.

**Interfaces**

- Produce `FalCatalogCompiler.Compile(string rootDirectory, IReadOnlyCollection<string> reservedModelIds) -> FalCatalogLoadResult`; result has `FalCatalogSnapshot? Catalog` and file/pointer diagnostics, with exactly one success/failure state.
- Produce `FalCatalogLoader.Load(string companionAssemblyDirectory, IReadOnlyCollection<string> reservedModelIds) -> FalCatalogLoadResult`; production resolves `vision-models/fal/catalog.json` from the loaded assembly, tests inject a temporary assembly directory.
- Produce `FalCanonicalJson.Hash(JsonNode value) -> string` (SHA-256), `FalCatalogSnapshot.GetOperation(string modelId, string operationId) -> FalOperationBinding` for already validated identities, and `TryGetOperation(string modelId, string operationId, out FalOperationBinding binding) -> bool` for caller validation.
- Initial manifest shape: `{ "schema_version": 1, "definitions": [] }`. Empty is valid; missing/invalid catalog yields diagnostics and no configured models. No reference fixture is shipped as a production registration.

- [ ] **Write the failing tests** with complete synthetic definitions and the following assertions:

```csharp
void Catalog_rejects_escape_or_collision_atomically() {
    var result = Cases.EscapeOrLegacyCollision(); Assert.Null(result.Catalog);
    Assert.All(result.Diagnostics, d => { Assert.NotEmpty(d.File); Assert.NotEmpty(d.Pointer); });
}
void Catalog_rejects_unknown_members_duplicates_and_bad_defaults() {
    Assert.All(Cases.InvalidDefinitions(), result => Assert.Null(result.Catalog));
}
void Canonical_hash_ignores_object_order_and_numeric_spelling() {
    Assert.Equal(Cases.Hash("{\"b\":2,\"a\":1.0}"), Cases.Hash("{\"a\":1,\"b\":2}"));
    Assert.NotEqual(Cases.Hash("[1,2]"), Cases.Hash("[2,1]"));
}
void Loader_uses_assembly_directory_and_copies_state() {
    var run = Cases.ChangeCwdAndMutateSourceJson(); Assert.Equal(run.OriginalHash, run.LoadedBinding.DefinitionHash);
}
```

Include rooted/UNC paths, `..`, junction/reparse-point escapes, duplicate filenames with Windows case differences, and collisions across modalities/legacy IDs. Reject control-vs-constant destination conflicts including parent/child pointer overlap, unsupported adapter IDs/versions, inconsistent media cardinality, invalid lifecycle roots, and executable/configured-host fields. Treat JSON object keys as case-sensitive; filesystem containment follows Windows rules.

- [ ] **Run red:** managed filter `FullyQualifiedName~FalCatalog|FullyQualifiedName~FalCanonicalJson`.
- [ ] **Implement compiler and immutable types.** Parse through `JsonDocument` before converting to nodes so duplicate members cannot be silently overwritten. Use closed members and enum sets; signed integers fit `Int64`, numbers fit invariant `decimal`, no non-finite values. Bounded admission defaults: 1 MiB per definition, 64 definitions, 16 operations per definition, 128 fields and 256 constraints per operation, JSON depth 32. Document those limits and diagnose the exceeded bound. Reject filesystem reparse points in referenced paths instead of following them. Canonicalization sorts object keys ordinally, preserves array order, and writes normalized invariant numeric values (including negative zero as zero).
- [ ] **Document the complete v1 vocabulary.** Pin adapter IDs `fal.image.declarative` and `fal.video.declarative`, version `1`; invocation `sync`/`queue`; explicit lifecycle root for queue; field scopes/types, conditions, mappings, roles, pricing and evidence. Result array mappings include a collection pointer with required cardinality `1`; scalar-object results need no collection pointer. No imports/inheritance or arbitrary transform expressions. Add schema examples as test data, not endpoint registrations.
- [ ] **Run green:** the same filter, including boundary-size fixtures and format-example parsing. Verify invalid catalog admission leaves the legacy registry factory usable.
- [ ] **Commit:** stage only Task 1 files and `git commit -m "feat(vision): compile versioned fal model catalogs"`.

**Stage evidence:** a reviewer can inspect every admitted format primitive and its rejection test without reading transport code.

### Task 2: Normalize inputs, publish descriptors, and map payloads/results

**Files**

- Create in `src/Rook/Services/Vision/Fal/Models/`: `FalModelInput.cs`, `FalModelNormalizer.cs`, `FalNormalizedRequest.cs`, `FalModelOptions.cs`, `FalOperationDescriptor.cs`, `FalDescriptorProjector.cs`, `IFalModelAdapter.cs`, `FalAdapterRegistry.cs`, `FalDeclarativeImageAdapter.cs`, `FalDeclarativeVideoAdapter.cs`, `FalPayloadMapper.cs`.
- Create: `src/Rook/Services/Vision/Fal/FalPreparedMedia.cs` (value contract only; preparation is Task 3).
- Create tests in `src/Rook.Tests/Services/Vision/Fal/`: `FalModelNormalizerTests.cs`, `FalPayloadMapperTests.cs`, `FalDescriptorProjectorTests.cs`.
- Modify: `docs/vision/fal-model-definition-v1.md` to bind example inputs to expected effective values and payloads.

**Interfaces**

- Consume Task 1 binding and canonical hash.
- Produce `FalModelNormalizer.Normalize(FalOperationBinding binding, FalModelInput input) -> FalNormalizationResult`.
- Produce `IFalModelAdapter.BuildPayload(FalNormalizedRequest request, IReadOnlyList<FalPreparedMedia> media) -> JsonObject`; `MapResult(FalOperationBinding binding, JsonObject response) -> ProviderResultOutcome`. `FalPreparedMedia` has read-only semantic role, ordinal and transport value. Mapping returns existing URL-bodied `ResultArtifact`/`ProviderResultEnvelope`; it does not download.
- Produce `FalAdapterRegistry.Resolve(string adapterId, int adapterVersion) -> IFalModelAdapter`, with only the two admitted v1 adapters.
- Produce `FalDescriptorProjector.Describe(FalOperationBinding binding, FalNormalizationResult? validation) -> FalOperationDescriptor`, and `FalOperationDescriptor.ToJson() -> JsonObject`.
- `FalModelOptions : ProviderOptions` preserves `FalModelInput` (including raw common-field suppliedness) and optional selected operation; it cannot authorize an endpoint. Codecs later call this normalizer using the resolved binding. Configured execution reads normalized common fields rather than narrowing an Int64 seed or decimal value through an existing legacy `int` property.

- [ ] **Write the failing tests**:

```csharp
void Suppliedness_is_preserved() {
    Assert.False(Cases.NormalizeBoolean(false).Value); Assert.Equal(0, Cases.NormalizeInteger(0).Value);
    Assert.False(Cases.NormalizeExplicitNull().Success); Assert.False(Cases.NormalizeNumericString("3").Success);
}
void Decimal_step_uses_min_or_zero() {
    Assert.True(Cases.Step(min: .1m, step: .2m, value: .3m).Success);
    Assert.False(Cases.Step(min: .1m, step: .2m, value: .2m).Success);
}
void Conditions_intersect_without_mutation() {
    Assert.False(Cases.InapplicableExplicitOption().Success); Assert.Empty(Cases.InapplicableDefault().EffectiveOptions);
}
void Every_accepted_option_has_one_consumer() { Assert.False(Cases.UnmappedOption().Admitted); }
void Mapping_preserves_reference_order_and_requires_one_result() {
    Assert.Equal(new[] { "first", "second" }, Cases.OrderedReferencePayload());
    Assert.False(Cases.ResultCount(2).Success); Assert.False(Cases.ResultCount(0).Success);
}
void Descriptors_and_effective_values_have_one_source() { Assert.Equal(Cases.DeclaredDefaults, Cases.NormalizedDefaults); }
```

Cover all five scalar types, negative signed bounds, enum lookup, integer-to-string mapping, absent optional fields, required predicates, membership/role presence, overlapping `allowed_values`, escaped JSON pointers, and literal constants. Reject options shadowing common fields or introducing paths/URLs as media. If default-filled conditions produce an impossible combination, return field errors without “repairing” values.

- [ ] **Run red:** filter `FullyQualifiedName~FalModelNormalizer|FullyQualifiedName~FalPayloadMapper|FullyQualifiedName~FalDescriptorProjector`.
- [ ] **Implement the finite normalizer and pure adapters.** Preserve supplied input separately, apply defaults once, evaluate conditions against that default-filled set, intersect active restrictions, then construct effective values and mapping instructions. `omit_when` never silently drops explicit values. Derive old capability projections from the binding; do not maintain another resolution/duration matrix. Only explicit common field mappings are sent; arbitrary options cannot pass through.
- [ ] **Implement descriptor serialization.** Include definition/source/hash, operations, required media, basic/advanced fields in stable order, constraints, pricing availability, field errors, and `submission_contract: "image_job"` for configured images. Expose disabled/unpriced operations with reasons but prohibit paid admission. Plain-text labels/descriptions must remain plain text in clients.
- [ ] **Run green:** same filter. Add synthetic FLUX-like sync image and Kling-like queued video definitions in test builders; assert their mapped request/result shapes against existing wire fixtures without claiming public-model migration. Assert the compiler's admitted adapter IDs/versions exactly match the implemented registry. Request cardinality is fixed at one: explicitly supplied image/video output count `2` fails before transport, and mapped count constants cannot override it.
- [ ] **Commit:** stage Task 2 files and `git commit -m "feat(vision): normalize and map declarative fal controls"`.

**Stage A gate:** schema/normalization decisions are reviewable; no transport, catalog-to-network execution, or model-specific UI code exists in these components.

## Stage B — Execution contract

### Task 3: Implement shared media preparation and fal execution

**Files**

- Create in `src/Rook/Services/Vision/Fal/`: `FalMediaSnapshot.cs`, `FalMediaPreparation.cs`, `FalConfiguredExecutor.cs`, `FalExecutionObserver.cs`, `FalConfiguredLifecycle.cs`.
- Modify: `src/Rook/Services/Vision/Fal/FalApiClient.cs`, `FalErrorMapper.cs`, `FalLifecycleMapper.cs` only for reusable transport/lifecycle seams.
- Modify: `src/Rook/Services/Vision/Generation/ProviderSubmitOutcome.cs`, `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`, `src/Rook/Services/Vision/Video/VideoJobManager.cs` for explicit unknown-dispatch outcome metadata; durable integration follows in Task 5.
- Create tests: `src/Rook.Tests/Services/Vision/Fal/FalConfiguredExecutorTests.cs`, `FalMediaPreparationTests.cs`, `FalConfiguredLifecycleTests.cs`.

**Interfaces**

- Consume normalized binding, adapter, existing `ResolvedMedia`, fal HTTP/upload client and outcome types.
- Produce `FalMediaSnapshot.Capture(FalNormalizedRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media) -> FalMediaSnapshot` (owns copies and stable digests).
- Produce `FalMediaPreparation.PrepareAsync(FalNormalizedRequest request, FalMediaSnapshot media, CancellationToken ct) -> Task<IReadOnlyList<FalPreparedMedia>>`. Fields: semantic role, ordinal, transport value; no persisted authority from uploaded URLs.
- Produce `FalConfiguredExecutor.SubmitAsync(FalNormalizedRequest request, FalMediaSnapshot media, IFalExecutionObserver observer, CancellationToken ct) -> Task<ProviderSubmitOutcome>`; lifecycle methods `GetStatusAsync`, `CancelAsync`, `FetchResultAsync` each take `FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct` and return the existing typed outcome.
- `IFalExecutionObserver.BeforeUploadAsync(CancellationToken ct) -> Task<GenerationError?>`, `BeforeDispatchAsync(CancellationToken ct) -> Task<GenerationError?>`, `AcceptedAsync(ProviderJobHandle handle, CancellationToken ct) -> Task`. Managers supply durable admission callbacks in Task 5; tests supply recording/failing observers.
- Extend `FailedSubmitOutcome` with `SubmissionDisposition Disposition`, constructor argument defaulting to `NotAccepted`; enum values `NotAccepted`, `Unknown`. Preserve the existing closed outcome union and old constructor calls. Configured uncertain dispatch returns `Unknown` with `Retryable=false`; both managers retain uncertainty and never treat it as known zero cost. Existing legacy error-code compatibility remains intact.

- [ ] **Write the failing tests**:

```csharp
void Invalid_or_unconfirmed_input_never_uploads() { var run = Cases.Denied(); Assert.Equal(0, run.Uploads); Assert.Equal(0, run.Submits); }
void Dispatch_intent_precedes_exactly_one_submit() {
    Assert.Equal(new[] { "beforeUpload", "beforeDispatch", "submit", "accepted" }, Cases.AcceptedQueue().Events);
}
void Lost_submit_response_is_unknown_and_never_replayed() {
    var run = Cases.LostResponseThenPollAndCancel(); Assert.Equal(1, run.Submits); Assert.Equal(SubmissionDisposition.Unknown, run.Disposition);
}
void Queue_uses_validated_returned_urls() { Assert.Equal(Cases.ReturnedStatusUrl, Cases.QueuePollUrl); Assert.Equal(0, Cases.WrongHost().LifecycleCalls); }
void Result_validation_precedes_success() { Assert.False(Cases.CompletedWithBadResult().Success); }
void Snapshots_own_bytes_and_preserve_order() { var run = Cases.MutateOriginalBytes(); Assert.Equal(run.BeforeDigest, run.SnapshotDigest); }
```

Cover sync image, queued image, queued video; rejected authentication; provider validation; timeout before/after dispatch; missing handle; status/result failures; cancellation versus accepted/completed; malformed lifecycle URLs; CDN/data-URI profiles. A failed accepted-handle write after provider acceptance must become uncertainty, never a safe-to-retry validation failure.

- [ ] **Run red:** filter `FullyQualifiedName~FalConfiguredExecutor|FullyQualifiedName~FalMediaPreparation|FullyQualifiedName~FalConfiguredLifecycle`.
- [ ] **Implement executor and preparation.** Existing runtime ceilings, MIME sniffing and qualified preparation govern bytes; only explicitly supported transport profiles are selectable. Recheck admission before upload and before dispatch. Await durable dispatch intent immediately before paid HTTP. Invoke accepted persistence before returning a queued handle. Update outcome documentation and manager classification for the explicit disposition above: only `NotAccepted` promises no accepted submission. Cover legacy mappings and the unchanged union closure contract.
- [ ] **Implement lifecycle validation.** Match returned URLs to compiled fal hosts and declared lifecycle root, request identity and operation purpose; reject credentials/fragments and escaping paths. Do not build lifecycle paths by appending to the submit endpoint. Retries may poll/fetch, never resubmit. Result adapters return URLs; existing materializers enforce bounded download and artifact MIME rules.
- [ ] **Run green:** same filter plus `FullyQualifiedName~FalImageProviderTests|FullyQualifiedName~FalVideoProviderTests` to protect existing transport callers.
- [ ] **Commit:** stage Task 3 files and any explicitly needed outcome consumers; `git commit -m "feat(vision): execute configured fal bindings with guarded dispatch"`.

### Task 4: Adapt configured models to the existing provider interfaces

**Files**

- Create: `src/Rook/Services/Vision/Image/Fal/ConfiguredFalImageProvider.cs`, `ConfiguredFalImageOptionsCodec.cs`, `ConfiguredFalImageRegistration.cs` in that directory.
- Create: `src/Rook/Services/Vision/Video/Fal/ConfiguredFalVideoProvider.cs`, `ConfiguredFalVideoOptionsCodec.cs`, `ConfiguredFalVideoRegistration.cs` in that directory.
- Create: `src/Rook/Services/Vision/Generation/IConfiguredGenerationBinding.cs`.
- Modify: `src/Rook/Services/Vision/Image/ImageSubmissionExecutor.cs`.
- Create tests: `src/Rook.Tests/Services/Vision/Fal/ConfiguredFalRegistrationTests.cs`; modify `src/Rook.Tests/Services/Vision/Image/ImageSubmissionExecutorTests.cs`.

**Interfaces**

- Consume Tasks 1–3 and existing `IImageProviderRegistration`, `IVideoProviderRegistration`, `IProviderOptionsCodec<TRequest,TCapability>`.
- Produce wrappers implementing existing image/video provider interfaces plus `IConfiguredGenerationProvider : IConfiguredGenerationBinding` (co-located in the new interface file). Binding members are `GetBinding(string operationId) -> FalOperationBinding` and `RequiresConfirmedSubmission -> bool`. Provider method is `SubmitConfiguredAsync(FalNormalizedRequest request, FalMediaSnapshot media, IFalExecutionObserver observer, CancellationToken ct) -> Task<ProviderSubmitOutcome>`. Managers select this capability; ordinary unconfirmed `SubmitAsync` on configured providers returns a confirmation-required error without transport.
- Add `ImageSubmissionExecutor.UsesExecutionDeadline(ResolvedImageModel model) -> bool` using configured capability plus the existing legacy policy; retain the string overload for legacy callers. Task 5 switches configured manager dispatch to the capability-aware overload and provider method.
- Registration constructors accept the compiled logical model, executor, adapter registry, and modality-specific `IPricingModel` (Task 6). One registration per logical model keeps codec/pricing pairing explicit even though each says provider `fal`.
- Codecs implement the existing `Deserialize(JsonObject)`, `Serialize(ProviderOptions)`, and `Validate(request, options, capability)` signatures, delegating to the shared normalizer. Preserve raw supplied fields before legacy constructors can fill defaults.

- [ ] **Write failing tests**:

```csharp
void Two_fal_registrations_keep_distinct_codecs_and_bindings() { Assert.NotSame(Cases.ModelA.Codec, Cases.ModelB.Codec); Assert.NotEqual(Cases.ModelA.Endpoint, Cases.ModelB.Endpoint); }
void Configured_sync_image_runs_as_a_rook_job() { Assert.Equal("image_job", Cases.SyncImageDescriptor.SubmissionContract); }
void Operation_resolution_is_explicit_or_unambiguous() {
    Assert.Equal("image_to_image", Cases.WithPrimaryImage().OperationId); Assert.False(Cases.AmbiguousOperation().Success);
}
void Legacy_models_keep_their_provider_and_policy() { Assert.Equal(Cases.BaselineLegacyContracts, Cases.CurrentLegacyContracts); }
```

- [ ] **Run red:** filter `FullyQualifiedName~ConfiguredFalRegistration|FullyQualifiedName~ImageSubmissionExecutorTests`.
- [ ] **Implement wrappers and policy seam.** Delegate payload/transport to Tasks 2–3. Generic direct-fal execution uses existing deadlines and stop fences through configured capability metadata; add no individual model-name case to deadline, fallback, framing, or recovery switches. Model-aware lifecycle operations require the pinned binding/handle. Registrations are constructed in tests here; production composition waits for Task 7.
- [ ] **Run green:** same filter and `FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~DefaultVideoProviderRegistryTests`.
- [ ] **Commit:** stage Task 4 files and `git commit -m "feat(vision): register configured fal provider wrappers"`.

**Stage B gate:** synthetic sync image, queue image and queue video work through provider interfaces with one executor; neither adapters nor new registrations contain endpoint-specific branches.

## Stage C — Durable admission

### Task 5: Persist pinned execution bindings and preserve restart/cancel behavior

**Files**

- Create: `src/Rook/Services/Vision/Fal/FalExecutionSnapshot.cs`, `FalExecutionSnapshotCodec.cs`, `FalExecutionRecovery.cs` in that directory.
- Create: `src/Rook/Services/Vision/Fal/Models/FalPricingSnapshot.cs` (immutable persistence contract; calculator follows in Task 6).
- Modify in `src/Rook/Services/Vision/Image/Jobs/`: `ImageJobStartRequest.cs`, `ImageJobManager.cs`, `ImageJobRecord.cs`, `ImageJobLedgerRecord.cs`, `ImageJobLedgerRecordFactory.cs`, `JsonlImageJobLedger.cs`.
- Modify in `src/Rook/Services/Vision/Video/`: `VideoJobManager.cs`, `VideoJobManager.Routing.cs`, `VideoJobRecord.cs`, `VideoJobRecordFactory.cs`, `VideoJobRecordProviderHandle.cs`, `JsonlVideoJobLedger.cs`.
- Create tests: `src/Rook.Tests/Services/Vision/Fal/FalExecutionSnapshotTests.cs`, `FalConfiguredJobLifecycleTests.cs`; modify existing image/video ledger and manager tests in their corresponding test directories.

**Interfaces**

- Consume immutable normalized request, executor observer, existing ledger/stop/publication contracts.
- Produce `FalExecutionSnapshotCodec.Serialize(FalExecutionSnapshot snapshot) -> JsonObject` and `Deserialize(JsonObject json) -> FalExecutionSnapshotReadResult` (supported snapshot or explicit unsupported/corrupt diagnostic).
- Snapshot version `1`; video extension key `configured_fal_execution`; image adds a versioned optional field of the same name without breaking old records. State records `prepared`, `dispatch_intent`, `accepted`, or `unknown`, plus existing job status.
- Produce `FalExecutionRecovery.CancelAsync(FalExecutionSnapshot snapshot, CancellationToken ct) -> Task<ProviderCancelOutcome>`, resolving supported adapter versions from the compiled registry and stored binding only.

- [ ] **Write failing tests**:

```csharp
void Old_image_and_video_records_remain_readable() { Assert.All(Cases.LegacyRecords(), r => Assert.True(r.Readable)); }
void Restart_marks_inflight_interrupted_without_resubmit() { var run = Cases.Restart(); Assert.Equal("Interrupted", run.State); Assert.Equal(0, run.Submits); Assert.Equal(0, run.ResumePolls); }
void Removed_or_changed_catalog_does_not_redirect_cleanup() { var run = Cases.ReplaceCatalogAndCancel(); Assert.Equal(run.StoredCancelUrl, run.CalledUrl); Assert.Equal(0, run.LatestCatalogLookups); }
void Unknown_snapshot_version_does_not_fall_back() { var run = Cases.FutureSnapshotVersion(); Assert.False(run.CleanupAvailable); Assert.Equal(0, run.NetworkCalls); }
void Ledger_failure_before_dispatch_prevents_paid_call() { Assert.Equal(0, Cases.IntentWriteFailure().Submits); }
void Handle_write_failure_and_late_completion_do_not_publish() { var run = Cases.AcceptedWriteFailureThenStop(); Assert.True(run.OutcomeUnknown); Assert.Empty(run.PublishedArtifacts); }
```

Simulate crashes between intent write, POST, response receipt and handle write. Race cancel/timeout against result fetch and publication using controlled tasks, not sleeps. Verify no leaked upload URLs/keys, full effective controls/pricing provenance, immutable stored binding, and accurate local versus remote cancel outcomes.

- [ ] **Run red:** filter `FullyQualifiedName~FalExecutionSnapshot|FullyQualifiedName~FalConfiguredJobLifecycle|FullyQualifiedName~JsonlImageJobLedger|FullyQualifiedName~JsonlVideoJobLedger`.
- [ ] **Implement snapshots and manager observer wiring.** Configured managers invoke `IConfiguredGenerationProvider.SubmitConfiguredAsync` with the pinned request/media and durable observer; legacy dispatch hooks stay on their existing path. Durably write intent before dispatch and accepted handle before progressing. Persist an accepted handle with a bounded manager-owned durability token even if the user's cancellation token has just fired; cancellation still blocks publication. Block paid dispatch on write failure. Persist only fields sufficient for history, result interpretation and permitted explicit cleanup; do not serialize executable adapter objects or credentials. Add image reader compatibility and preserve video extension compatibility. Store the normalized request and provenance used for the artifact, not a later UI request. Pricing snapshot can be absent in isolated Task 5 tests; Task 6 makes it mandatory for production configured admission.
- [ ] **Implement recovery and publication fences.** Keep interrupted-on-restart behavior. Cleanup reads the persisted binding and validated handle even if no current definition exists. Unsupported versions remain visible with a reason and cannot trigger latest-definition lookup. Ensure configured jobs never use provider-name-only recovery. Reuse existing linearized stop/publication barriers.
- [ ] **Run green:** same filter plus both existing modality manager suites and `FullyQualifiedName~VideoExecutionSnapshotTests|FullyQualifiedName~ImageJobLedgerRecordFactoryTests`.
- [ ] **Commit:** stage Task 5 files and `git commit -m "feat(vision): persist configured fal execution bindings"`.

### Task 6: Quote effective inputs and enforce confirmation before paid work

**Files**

- Create in `src/Rook/Services/Vision/Fal/Models/`: `FalDeclarativePricing.cs`, `FalQuoteService.cs`, `FalQuote.cs` (including `FalSubmitConfirmation`). Consume the Task 5 pricing snapshot contract.
- Modify: `src/Rook/Services/Vision/Video/VideoRouteQuoteService.cs`, `VideoJobPricingTranslator.cs`, `VideoCostEstimator.cs`, `VideoEstimateFingerprint.cs`; `src/Rook/Services/Vision/Image/Jobs/ImageJobStartRequest.cs`; both managers from Task 5.
- Create tests: `src/Rook.Tests/Services/Vision/Fal/FalDeclarativePricingTests.cs`, `FalQuoteServiceTests.cs`; modify `src/Rook.Tests/Services/Vision/Video/VideoRouteQuoteTests.cs`.

**Interfaces**

- Produce `FalDeclarativePricing.Estimate(FalNormalizedRequest request) -> FalPricingResult`; success contains decimal quantity bounds, unit, rate/selector, estimate bounds, currency USD and source/revision. Failure identifies unavailable pricing; it is never zero-cost success.
- Produce `FalQuoteService.Estimate(FalNormalizedRequest request, FalMediaSnapshot media) -> FalQuoteResult`; `Validate(FalQuote quote, FalNormalizedRequest request, FalMediaSnapshot media, FalSubmitConfirmation confirmation) -> GenerationError?`.
- `FalQuote` carries the effective pricing snapshot and fingerprint; `FalSubmitConfirmation` carries fingerprint and nonnegative maximum USD. Recompute a current quote server-side at submit; a caller cannot supply its own trusted quote payload.
- Provide image/video `IPricingModel` projections from this one strategy. Keep the richer snapshot authoritative when old video quantity fields cannot express fractional units.

- [ ] **Write failing tests**:

```csharp
void Price_uses_effective_options_and_decimal_quantities() { Assert.Equal(.30m, Cases.PerSecond(quantity: 1.5m, rate: .2m).MaxUsd); }
void Megapixels_follow_declared_dimensions_and_rounding() { Assert.False(Cases.MissingDimensionMapping().Available); Assert.True(Cases.BoundedMegapixels().Available); }
void Any_changed_binding_controls_media_or_price_invalidates_quote() { Assert.All(Cases.ChangedQuoteInputs(), r => Assert.Equal("quote_stale", r.ErrorCode)); }
void Confirmation_caps_upper_bound_before_upload() { Assert.False(Cases.Confirm(.20m, .30m, cap: .29m).Success); Assert.True(Cases.Confirm(.20m, .30m, cap: .30m).Success); }
void Actual_spend_remains_unknown_without_evidence() { Assert.Null(Cases.EstimateWithoutInvoice().ActualUsd); }
```

Add rate-selector gaps, negative/overflow values, invalid rounding units, changed artifact bytes between estimate/submit, and changed values after queue admission. Finite pricing selectors must reference declared normalized fields. Preserve legacy routed quote fixtures and legacy confirmation requirements.

- [ ] **Run red:** filter `FullyQualifiedName~FalDeclarativePricing|FullyQualifiedName~FalQuoteService|FullyQualifiedName~VideoRouteQuoteTests`.
- [ ] **Implement fixed/output, output-second and output-megapixel strategies.** Schema records unit, finite rates/selectors, dimension mapping or conservative bounds, explicit rounding rule and provenance/review date. Arithmetic stays `decimal`; choose the selected table entry from normalized values. Unknown pricing disables admission, never falls through `VideoCostEstimator`'s legacy null-to-zero projection. Only representable legacy fields are projected.
- [ ] **Implement shared confirmation.** Fingerprint canonical effective inputs plus definition hash, operation/adapter version, media identity/order/digests and pricing revision. Store the accepted normalized request/media snapshot; observer checks use that immutable admission state, including cancellation/deadline, immediately before upload/dispatch. The direct-fal quote has one configured candidate and never invokes Google fallback selection. Reuse canonical hashing from Task 1 without changing existing Google fingerprints inadvertently.
- [ ] **Run green:** same filter plus Task 3 preupload and Task 5 dispatch-race tests.
- [ ] **Commit:** stage Task 6 files and `git commit -m "feat(vision): confirm configured fal costs against pinned inputs"`.

**Stage C gate:** missing rates, stale inputs, ledger failures and unknown submissions cannot cause an unconfirmed second paid request. History and artifact metadata retain the exact normalized controls and estimate provenance.

## Stage D — Managed integration

### Task 7: Compose the catalog and expose common managed operations

**Files**

- Modify: `src/Rook/RookSubsystemRoot.cs`, `src/Rook/Services/Vision/VisionProviderRegistrations.cs`, `Image/DefaultImageProviderRegistry.cs`, `Image/ImageModelDescriptor.cs`, `Image/Jobs/ImageJobSubsystemBundle.cs`, `Video/DefaultVideoProviderRegistry.cs`, `Video/VideoModelDescriptor.cs`, `Video/VideoSubsystemFactory.cs` (the latter paths under `src/Rook/Services/Vision/`).
- Modify: `src/Rook/Handlers/VisionHandler.cs`, `ImageJobOpHandler.cs`, `VideoOpHandler.cs` in that directory.
- Create: `src/Rook/Handlers/FalConfiguredRequestParser.cs`.
- Modify tests: `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`, `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`, `VisionHandlerTests.cs`, `VideoOpHandlerTests.cs` in that handlers test directory.
- Create: `src/Rook.Tests/Handlers/ConfiguredFalHandlerTests.cs`.

**Interfaces**

- Produce `FalConfiguredRequestParser.Parse(JsonObject request, FalCatalogSnapshot catalog, string modality) -> FalRequestParseResult`, containing resolved binding and `FalModelInput` or field errors. Preserve raw suppliedness before adapting existing typed image/video requests.
- Produce `VisionProviderRegistrations.GetLegacyModelIds() -> IReadOnlyCollection<string>` from existing registrations, without loading the configured catalog or reading credentials. Composition and the later qualification host use this same reserved-ID set.
- Existing `list_image_models` and video-models operations add the shared `operations` descriptors to configured entries. Add managed discriminator `image_estimate`; reuse `image_generate_start`, `image_job_status`, `image_job_result`, `image_job_cancel`, `image_jobs` unchanged.
- Configured submit/estimate wire fields: `model`, optional `operation`, applicable common fields (`prompt`, `resolution`, `aspect_ratio`, `duration_seconds`, `seed`), `options` object, ordered `media` entries `{semantic_role, artifact_id, artifact_role}`. Submit additionally carries `quote_fingerprint` and `max_estimated_cost_usd`. Missing required common fields are operation-specific, not globally required.
- Existing video start/end/reference fields remain compatibility inputs; configured parser translates them to semantic media. Reject simultaneous conflicting old/new representations. No caller-provided endpoint or provider handle is admitted.

- [ ] **Write failing tests**:

```csharp
void Image_options_reach_the_codec_instead_of_empty_json() { Assert.Equal(7.5m, Cases.ImageRequestWithGuidance(7.5m).Payload["guidance"].GetValue<decimal>()); }
void Panel_and_bridge_share_descriptor_and_normalization() { Assert.Equal(Cases.PanelCapture, Cases.BridgeCapture); }
void Configured_legacy_generate_returns_handoff() { var run = Cases.LegacyEntryWithConfiguredModel(); Assert.Equal("image_job_required", run.ErrorCode); Assert.Equal(0, run.GeminiCalls); }
void Invalid_catalog_preserves_legacy_discovery() { var run = Cases.InvalidCatalog(); Assert.Empty(run.ConfiguredIds); Assert.Equal(run.LegacyBaseline, run.LegacyIds); }
void Configured_request_uses_artifact_roles_and_operation_requirements() { Assert.False(Cases.MissingRequiredStartFrame().Success); Assert.True(Cases.OptionalPromptAbsent().Success); }
```

- [ ] **Run red:** filter `FullyQualifiedName~ConfiguredFalHandler|FullyQualifiedName~VisionProviderRegistrationsTests|FullyQualifiedName~ImageJobOpHandlerTests`.
- [ ] **Wire one catalog snapshot into shared subsystem composition.** Collect legacy reserved IDs before compiling definitions; append configured registrations only on complete admission success. Share identity across image/video bundles and keep root disposal/lazy initialization behavior. Retain per-model codec/pricing even when provider names repeat. Never create separate panel and native catalogs.
- [ ] **Wire parser, quote and submit.** Stop passing an empty options object on the configured image path. Resolve operation explicitly or infer only when unambiguous; video modes map to declared operations. Validate before upload, return field-specific errors, and reuse job manager status/result/history/cancel. Add descriptor-driven direct-fal quote path alongside existing routed video estimates. Legacy image generate returns a stable handoff code/message for configured IDs rather than falling back to Gemini.
- [ ] **Run green:** same filter plus existing `VisionHandlerTests`, `VideoOpHandlerTests`, `ImageFallbackHandlerTests`, and `VideoFallbackEnvelopeTests`.
- [ ] **Commit:** stage Task 7 files and `git commit -m "feat(vision): expose configured models through shared managed operations"`.

**Stage D gate:** managed integration tests demonstrate discovery → estimate → confirmed job → artifact with nondefault controls for both modalities and no changes to old public model behavior.

## Stage E — Product surfaces

### Task 8: Render and submit configured controls in RookVision

**Files**

- Create: `src/Rook/UI/Vision/Resources/model-controls.js`.
- Modify: `src/Rook/UI/Vision/Resources/app.js`, `index.html`, `styles.css` in that directory; `src/Rook/UI/Vision/VisionWebSurface.cs`.
- Create: `src/Rook.Tests/UI/Vision/model-controls.test.cjs`, `configured-models.test.cjs`.
- Modify: existing `image-fallback.test.cjs`, `video-fallback.test.cjs`, `video-framing.test.cjs` only to cover regressions or changed shared fixtures.

**Interfaces**

- Consume Task 7 descriptor/wire contract and existing panel bridge calls. Embedded resource inclusion already uses the UI resource glob; explicitly load the new script before `app.js`.
- Produce `RookModelControls.create(container, descriptor, onChange) -> controller`; controller methods `readOptions()`, `setValidation(errors)`, `dispose()`. Descriptor identity includes model/operation/hash; state is not keyed by labels.
- Produce a single configured-form request builder in `app.js`, `buildConfiguredModelRequest(state) -> object`, used unchanged for estimate and submit (submit appends confirmation).

- [ ] **Write failing Node tests**:

```javascript
test('boolean false and numeric zero survive request serialization', () => { assert.deepEqual(cases.falseAndZero(), {audio: false, seed: 0}); });
test('all five field types honor bounds, order and advanced groups', () => { assert.deepEqual(cases.renderedFieldTypes(), ['boolean','integer','number','string','enum']); });
test('model operation or hash change clears incompatible controls and quote', () => { const form = cases.changedModel(); assert.equal(form.oldOption, undefined); assert.equal(form.canSubmit, false); });
test('nondefault controls reach managed request capture', () => { assert.deepEqual(cases.estimateInputs(), cases.submitInputsWithoutConfirmation()); });
test('late estimate cannot enable current generation', () => { assert.equal(cases.lateEstimate().canSubmit, false); });
```

Use existing VM/fake-DOM harness pattern. Assert behavior, including clear field errors, rather than implementation source strings. Define conditional visibility/inactivity from descriptors, but submit to managed validation before paid work; do not implement independent pricing/default mutation.

- [ ] **Run red:** `node --test src/Rook.Tests/UI/Vision/model-controls.test.cjs src/Rook.Tests/UI/Vision/configured-models.test.cjs`.
- [ ] **Implement generic controls and form state.** Keep common controls, render supported provider controls in basic/advanced groups, and use typed values. Apply definition ordering and operation media cardinality. Changing model, operation, controls or media invalidates the quote; definition revision changes invalidate cached descriptors. Preserve supplied values while reporting conditional errors; omit inactive defaults per managed normalization. Use text nodes for labels/descriptions. Dispose old listeners.
- [ ] **Wire estimate and generation.** Configured image descriptors select the async image-job path. Show USD exact/range estimate, submit fingerprint and selected maximum, and display progress/cancel/artifact via current job experience. Unpriced/disabled operations explain unavailability. Configured video uses the same form contract through existing video operations. Add `image_estimate` to the panel off-UI route table.
- [ ] **Run green:** the same Node command, then all three existing fallback/framing Node suites and Task 7 managed parity tests. Add a fixture export of panel-submitted JSON for Task 11's compiled payload harness.
- [ ] **Commit:** stage Task 8 files and `git commit -m "feat(vision): render catalog controls and confirmed generation in panel"`.

### Task 9: Expose image jobs through native/MCP and enrich video tools

**Files**

- Modify: `src/RookNative/Handlers/VisionHandler.h`, `VisionHandler.cpp` in that directory; `src/RookNative/RookServer.cpp`; `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`.
- Modify: `mcp_server/src/rook/server.py`, `mcp_tool_profiles.py`, `targeting.py`, `agent/tool_groups.py`, `agent/tool_dispatcher.py` under `mcp_server/src/rook/`. Read `tool_lifecycle.py` and `tool_lifecycle_runtime.py` to verify admission; their retirement/tombstone lists need no new entries for these active tools.
- Modify tests: `src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs`; `mcp_server/tests/test_vision_mcp_tools.py`, `test_vision_routes_live.py`, `test_video_mcp_tools.py`, `test_server_tool_profiles.py`, `test_tool_lifecycle.py`.
- Create: `mcp_server/tests/test_image_job_mcp_tools.py`.
- Modify: `docs/CURRENT_ARCHITECTURE.md` only for verified route/surface changes, not speculative counts.

**Interfaces**

Consume Task 7 wire contract and existing Vision dispatch callback. Add exactly these public tools/routes:

| Tool | Route | Managed op |
| --- | --- | --- |
| `rhino_image_models` | `GET /vision/image/models` | `list_image_models` |
| `rhino_image_estimate` | `POST /vision/image/estimate` | `image_estimate` |
| `rhino_generate_image` | `POST /vision/image/jobs` | `image_generate_start` |
| `rhino_image_status` | `GET /vision/image/jobs/{job_id}` | `image_job_status` |
| `rhino_image_result` | `GET /vision/image/jobs/{job_id}/result` | `image_job_result` |
| `rhino_image_cancel` | `POST /vision/image/jobs/{job_id}/cancel` | `image_job_cancel` |
| `rhino_image_jobs` | `GET /vision/image/jobs` | `image_jobs` |

Tool schemas remain stable with an `options` object and generic media list; no model-specific tool names or schemas. Add optional operation/media/confirmation properties to existing video tools without making them required for legacy models. Discovery/status/result/history/estimate are read-only; submit/cancel are mutations. Full profile admits all seven; readonly admits the five read-only tools; lean remains curated and exposes these through the existing capability gateway unless its current policy explicitly requires direct inclusion. Verify that policy with profile tests rather than inventing counts.

- [ ] **Write failing tests**:

```python
def test_image_tools_forward_typed_options_media_and_confirmation():
    assert cases.forwarded_payload() == cases.expected_typed_payload()
def test_image_route_methods_ids_and_discriminators_match_contract():
    assert cases.registered_image_routes() == cases.seven_routes_from_table()
def test_readonly_can_estimate_but_cannot_submit_or_cancel():
    names = cases.readonly_names()
    assert "rhino_image_estimate" in names
    assert {"rhino_generate_image", "rhino_image_cancel"}.isdisjoint(names)
def test_legacy_render_view_schema_and_response_remain_compatible():
    assert cases.legacy_result() == cases.baseline_legacy_result()
def test_catalog_changes_do_not_change_tool_inventory():
    assert cases.tools_before_catalog_change() == cases.tools_after_catalog_change()
```

Managed source/dispatch tests assert explicit admission includes the new image operations and does not promote other hidden operations. Route status/result/history off UI; estimate, start and cancel follow existing off-UI/async handlers. Cross-check callback unavailability errors and invalid job IDs.

- [ ] **Run red:** `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_image_job_mcp_tools.py mcp_server/tests/test_vision_mcp_tools.py mcp_server/tests/test_video_mcp_tools.py mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_tool_lifecycle.py -q`; managed filter `FullyQualifiedName~NativeVisionDispatchSourceTests`.
- [ ] **Implement native forwarding and callback routing together.** Add small handler functions and route registrations to existing files; inject managed discriminators server-side. Extend `ExpectedVisionOps` and actual dispatch together using shared handlers from the root. Update live `/capabilities` construction in `RookServer.cpp` with bridge readiness semantics; no new server or ABI.
- [ ] **Implement Python schema/dispatch/classification.** Reuse existing error forwarding and lifecycle admission. Update vision tool groups and targeting/read-only membership; remove touched provider-specific descriptions that wrongly exclude configured models. Review internal-agent dispatch so a listed group cannot invoke an unimplemented tool. Update authoritative count expectations from actual discovery diffs (expected full delta: seven); preserve retired Director policy.
- [ ] **Run green:** same tests, plus `mcp_server/tests/test_capability_inventory.py`, `test_multi_instance_targeting.py`, `test_rookchat_visible_dispatchability.py`, and `test_dispatcher_safety.py` using the same pytest invocation. Build native with the Windows command in Task 11; source tests alone do not verify compilation. Installed route checks run at Task 11, not by bypassing MCP with ad hoc HTTP during live acceptance.
- [ ] **Commit:** stage Task 9 files and `git commit -m "feat(vision): expose configurable image jobs and controls through MCP"`.

**Stage E gate:** both surfaces discover the same fields and serialize nondefault controls; callback admission, HTTP methods, MCP profiles, capabilities and counts agree. Existing clients still operate.

## Stage F — Distribution and proof tooling

### Task 10: Package catalogs and support a genuine config-only deployment

**Files**

- Create: `src/Rook.Vision.Qualification/Rook.Vision.Qualification.csproj`, `Program.cs`, `CatalogQualification.cs` in that project.
- Create: `scripts/deploy-vision-model-catalog.ps1`, `scripts/tests/deploy-vision-model-catalog.tests.ps1`.
- Modify: `src/Rook/Rook.csproj`, `scripts/deploy-local-testing.ps1`, `scripts/validate-release-artifacts.ps1`, `installer/RookSetup.iss`.
- In the same `src/Rook/Rook.csproj` edit, add `<InternalsVisibleTo Include="Rook.Vision.Qualification" />` beside the existing framing qualification host declaration, without making implementation services public.
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`, `release-installer-guards.tests.ps1`, `validate-release-artifacts.tests.ps1` in that test directory.
- Modify: `docs/vision/fal-model-definition-v1.md` with build, validation, copy and restart procedure.

**Interfaces**

- Qualification CLI: `Rook.Vision.Qualification.exe validate-catalog --root <catalog-directory> --report <json-path>`; exit `0` for admitted complete catalog, nonzero for diagnostics. Calls the production compiler with the real legacy reserved IDs; no second schema implementation.
- Config deployment: `scripts/deploy-vision-model-catalog.ps1 -CatalogRoot <directory> -PluginRoot <installed-RookNative> -ValidatorPath <frozen-qualification-exe>`. Resolve absolute roots, require Rhino stopped, validate first, then replace only `vision-models/fal/` in net48/net7.0/net8.0. Stage sibling directories and use rollback on any failure so the three runtimes cannot remain mixed. Verify target containment before recursive file operations.
- Build/installer copy uses generic JSON globs into each runtime's external `vision-models/fal` directory. Normal full deployment includes them; the existing managed-only rhp/pdb contract remains unchanged. Config-only copy never invokes a build or rewrites code.

- [ ] **Write failing PowerShell tests**:

```powershell
Assert-True ($copiedRuntimeCount -eq 3) 'Generic definitions must reach every runtime.'
Assert-True ($invalidCatalogExit -ne 0) 'Reject an invalid catalog before copying.'
Assert-True ($restoredCatalogHashes -ceq $originalCatalogHashes) 'Rollback must restore all runtime catalogs.'
Assert-True ($codeManifestAfter -ceq $codeManifestBefore) 'Config copy must preserve every code payload hash.'
```

Use temporary directories and a test-injected process probe/validator, following existing script tests. Installed packaging checks validate manifest references and hash parity with source, not mere directory existence. Confirm an empty pre-acceptance catalog is a valid package.

- [ ] **Run red:** `powershell -NoProfile -File scripts/tests/deploy-vision-model-catalog.tests.ps1`, followed by the three modified existing script test files.
- [ ] **Implement qualification host and generic inclusion.** Follow `Rook.Framing.Qualification.csproj` target/runtime mirror pattern; no new NuGet dependency or solution/project-file rewrite is necessary. The qualifier is verification tooling, not a second production model implementation. Release validation requires successful catalog semantic validation for every packaged runtime and records hashes. Build/deploy/installer assets use one generic inclusion each; future endpoints do not add installer lines.
- [ ] **Implement config-only deployment.** Validation occurs before any replacement; backup/restore only validated directories within explicitly selected plugin roots. Do not modify secrets, generated artifacts or unrelated installed state. Capture before/after code manifest; any code change fails deployment proof. Require restart to load a changed catalog; do not simulate hot reload.
- [ ] **Run green:** all four script test files; build qualifier with `dotnet build src/Rook.Vision.Qualification/Rook.Vision.Qualification.csproj -c Debug -f net48 -p:RhinoPluginDir=`; run `src/Rook.Vision.Qualification/bin/Debug/net48/Rook.Vision.Qualification.exe validate-catalog --root src/Rook/Services/Vision/Fal/Models --report artifacts/fal-catalog-validation.json`.
- [ ] **Commit:** stage Task 10 files and `git commit -m "build(vision): package and deploy external fal catalogs"`.

### Task 11: Build the generic acceptance harness, verify regression, and freeze

**Files**

- Create: `src/Rook.Vision.Qualification/ConfiguredEndpointQualification.cs`, `RuntimeFreezeManifest.cs`.
- Modify: `src/Rook.Vision.Qualification/Program.cs`.
- Modify: `src/Rook.Tests/Rook.Tests.csproj` with a project reference to the qualification host so focused harness tests build their dependency; its harness entry classes are public for test invocation, with no new package dependency.
- Create: `src/Rook.Tests/Services/Vision/Fal/FalConfiguredConformanceTests.cs`, `FalQualificationHarnessTests.cs`.
- Create data: `src/Rook.Tests/Services/Vision/Fal/Fixtures/configured-sync-image.json`, `configured-queue-image.json`, `configured-queue-video.json`, `configured-cases.json` (synthetic identities and recorded protocol fixtures).
- Create: `scripts/verify-fal-config-acceptance.ps1`, `scripts/tests/verify-fal-config-acceptance.tests.ps1`.
- Modify: `scripts/verify-vision-merge.ps1` to include new Node/Python/qualification checks in its recorded result set.
- Create: `docs/vision/fal-config-acceptance.md` (repeatable runbook and evidence schema).

**Interfaces**

- Extend frozen CLI with `verify-cases --catalog <root> --cases <json> --report <json>` and `freeze-runtime --repo <root> --plugin-root <path> --mcp-root <path> --out <json>`.
- `verify-cases` is deterministic and offline: load arbitrary admitted definitions and generic request cases, normalize/quote/map/execute against protocol fixtures; assert expected provider fields/results/provenance. Cases contain data only, no expressions, callbacks, functions or expected code patches. Panel and MCP request captures feed this same harness.
- Freeze manifest records Git commit, built artifacts, source production code and test/harness hashes, installed native/managed binaries, embedded UI resources, MCP Python payload, adapters and packaged dependencies. It enumerates files so added/deleted code is detected, not only modified known files. Exclude declared mutable logs/artifacts/secrets, never an entire code subtree. Record runtime-loaded paths/version evidence separately.
- Acceptance verifier: `scripts/verify-fal-config-acceptance.ps1 -FreezeManifest <json> -Cases <json> -Evidence <json> -Report <json>` returns `0` only when all required evidence and allowlist checks pass; absent live evidence is incomplete/nonzero.

- [ ] **Write failing tests**:

```csharp
void Reference_wire_contracts_match_without_public_registration_changes() { Assert.Equal(Cases.LegacyWire, Cases.DeclarativeWire); Assert.Equal(Cases.LegacyRegistrationsBefore, Cases.LegacyRegistrationsAfter); }
void Generic_cases_cover_queued_image_and_lifecycle_failures() { Assert.All(Cases.ProtocolMatrix(), c => Assert.True(c.ExpectedOutcomeObserved)); }
void Arbitrary_new_model_ids_work_without_test_code_changes() { Assert.True(Cases.SwapDefinitionDataOnly().Passed); }
void Freeze_detects_added_modified_or_removed_code() { Assert.All(Cases.CodeMutations(), r => Assert.False(r.MatchesFreeze)); }
void Acceptance_without_four_live_jobs_is_incomplete() { Assert.NotEqual(0, Cases.AcceptanceWithOnlyFixtures().ExitCode); }
```

Reference all five Review Focus cases in conformance case data. Include malformed options, type/bounds/condition errors before upload, result cardinality/MIME, stale quotes, cancel races and catalog-removal cleanup. Assert nondefault values at the actual fal client boundary from both surface request captures. Sanitize transport evidence: credentials, temporary upload URLs and raw source media must not enter reports; preserve scalar provider fields, media roles/order and digests.

- [ ] **Run red:** managed filter `FullyQualifiedName~FalConfiguredConformance|FullyQualifiedName~FalQualificationHarness`; `powershell -NoProfile -File scripts/tests/verify-fal-config-acceptance.tests.ps1`.
- [ ] **Implement generic harness and fail-closed release checker.** Publish evidence schema in the runbook: endpoint/operation, official documentation review, selected controls/settings, normalized request/payload digest, quote/cap, job/artifact IDs, surface, definition/runtime hashes, timestamps, result MIME, provenance and actual-spend status. Separate test data/reports from deployed configuration. Add no endpoint-specific branch. The harness and surface capture/export support must exist before any held-out endpoint is selected.
- [ ] **Run green:** focused managed/PowerShell tests, qualifier fixture validation, and all affected Python tests.
- [ ] **Commit candidate runtime:** stage Task 11 files and `git commit -m "test(vision): qualify configurable fal runtime and freeze acceptance harness"`. This establishes the source revision that the final builds must describe.
- [ ] **Verify that committed runtime:** run broad existing verification once:

```powershell
powershell -NoProfile -File scripts/verify-vision-merge.ps1 -Python mcp_server/.venv/Scripts/python.exe
```

This existing script includes its required repeated managed runs; do not add gratuitous repetitions. Build all companion targets with deployment suppressed (`-p:RhinoPluginDir=`). Build the native plugin in a fresh developer shell:

```powershell
& $env:ComSpec /d /c 'call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207'
```

Capture MSBuild's selected toolset and exit code. Run package/deploy tests from Task 10. Record unavailable toolchain checks as incomplete, never green. Any source fix creates a new candidate commit and requires affected checks before the final freeze.

- [ ] **Deploy and freeze:** deploy that built Release candidate using the authorized local-testing workflow, with Rhino closed. If the full workflow builds RookBim, build it after the companion as required by the repository; this plan changes no BIM source or dependency. Recheck loaded/installed version paths. Run installed route/discovery/error smoke checks through MCP and inspect the panel with no paid inference; verify native capability declarations and callback operation admission from the installed build. Then create the freeze manifest with the built qualifier. Store evidence under `artifacts/fal-config-acceptance/<attempt-id>/`; store a concise tracked report under `docs/vision/acceptance/`. Missing installed checks mean incomplete qualification.

**Stage F freeze gate:** all deterministic suites, cross-target/native builds, packaging and installed no-cost checks have recorded passes. Runtime source, deployed code, UI/MCP and harness are frozen. No held-out endpoint definition or endpoint-specific case existed in this freeze. Record commit/hash manifest and reviewer sign-off before selecting endpoints.

## Stage G — Release gate

### Task 12: Add held-out image/video definitions and prove configuration-only operation

**Files**

- Create only production files: `src/Rook/Services/Vision/Fal/Models/acceptance-image.json`, `acceptance-video.json` (keep readable public model identities inside the files).
- Modify only production file: `src/Rook/Services/Vision/Fal/Models/catalog.json`.
- Create evidence/data: `docs/vision/acceptance/<attempt-id>.md` plus case/report JSON under `artifacts/fal-config-acceptance/<attempt-id>/`. Evidence files never become runtime configuration or executable tests.

**Interfaces**

Consume the frozen catalog format, installed runtime, generic harness, panel and MCP tools. Produce a release report with a mechanically checked JSON-only production diff and all behavior evidence below. No new endpoint-specific function, adapter, tool schema, UI file, production/test code or packaging line is allowed.

- [ ] **Select and record the two held-out endpoints after freeze.** Verify official fal schema, queue behavior and pricing at that time; record URLs, review date, exact submit endpoint/lifecycle root, supported operation, media/output shape and supported pricing strategy. Prefer text-to-image plus image-to-video to exercise media preparation. Both must be absent from the frozen catalog and case data and fit the approved v1 boundary. Before authoring definitions, name at least two useful non-basic controls per endpoint; across the pair include a numeric control and a boolean or enum. Record why the endpoint/control pair is a meaningful test. Do not choose endpoint names now.
- [ ] **Record economical settings and obtain the concrete total spend cap before any paid call.** Include four required successful jobs and reserve for any approved failure/retry attempt; a failed or uncertain dispatch counts against the remaining cap conservatively. A cap is a maximum, not permission for automatic retries. Do not treat a previously quoted estimate as a final bill.
- [ ] **Prove the negative baseline.** With the frozen catalog, both endpoint IDs are absent in UI and MCP. Freeze verifier confirms source, harness and installed code unchanged. Prepare generic case data with expected nondefault fields, invalid inputs and artifact-role mapping; this is data, not new test logic.
- [ ] **Write and validate the two definitions and manifest entries.** Use only existing schema/adapters. Run frozen `validate-catalog` and `verify-cases`; include unknown option, wrong type, out-of-range input, stale quote, and a conditional-invalid case. A synthetic fixture can provide the conditional rule if neither real endpoint has a useful one. All rejection cases produce zero upload/inference calls.
- [ ] **Deploy JSON only and restart Rhino.** Use the frozen Task 10 copier. Record unchanged native/managed/UI/MCP/harness hashes and the exact file diff. Remove the definitions/manifest entries once, copy/restart and confirm both IDs disappear; restore/copy/restart and confirm they return. Perform this before paid jobs. No rebuild or code replacement is permitted.
- [ ] **Verify both surfaces before spending.** Discover the complete declared controls and consistent defaults/constraints. Set nondefault values in the panel and MCP, capture requests, and run the same frozen harness to show exact expected fields at the fal boundary. Verify estimates follow effective controls, media order/digests and binding revision. Confirm stale quote rejection before upload. Keep descriptor/payload evidence in the report.
- [ ] **Complete four successful live jobs within the agreed cap**:

| Endpoint | Surface | Required evidence |
| --- | --- | --- |
| New image | RookVision UI | Nondefault controls, displayed/confirmed quote, progress, valid image artifact, saved provenance |
| New image | MCP | Discovery → estimate → confirmed submit → status → result; valid image and same control semantics |
| New video | RookVision UI | Artifact frame input, nondefault controls, quote, progress, valid MP4 and saved provenance |
| New video | MCP | Same operation/media requirements; successful status/result; valid MP4 and same control semantics |

Use normal product/MCP entry points; never substitute direct fal or localhost requests for UI/MCP acceptance. If endpoint selection legitimately uses text-to-video, document the selection and prove media handling with existing qualified fixture cases; image-to-video remains the preferred stronger gate. Live artifact appearance alone does not prove option forwarding: retain matching deterministic boundary evidence. Avoid additional paid cancellation/race probes; those are deterministic harness gates. Record actual spend as unknown when no provider billing evidence is available.

- [ ] **Run the frozen acceptance verifier and review the evidence.** Every row below must pass; no waived or skipped gate is a release pass:

| Gate | Pass condition |
| --- | --- |
| Production diff | Exactly definition JSON and manifest changes; no production code, tool schema, tests/harness or packaging edits |
| Deployment | Same frozen runtime/harness/source hashes; only catalog data differs; absence/removal/reappearance verified |
| Discovery/controls | Both models and full declared controls in both surfaces; at least two named non-basic controls per endpoint |
| Payload | Nondefault typed values from both surfaces observed at the fal boundary using the preexisting generic harness |
| Validation/quote | Type/unknown/bounds/condition/stale quote failures before upload or inference; exact/bounded pricing and cap |
| Jobs/artifacts | Four successful live jobs; valid single image/MP4 results and complete saved binding/controls/pricing/media provenance |
| Lifecycle/regression | Frozen deterministic lifecycle, restart, cancellation, legacy fallback/framing, tool/profile and packaging suites passed |
| Evidence | Runtime freeze, paid cap, endpoint sources, job/artifact IDs, failures and remaining actual-spend uncertainty recorded |

- [ ] **Commit only after a passing gate:** stage the two definitions, manifest and concise tracked report; `git commit -m "feat(vision): qualify image and video endpoints through configuration only"`. Release review inspects both the runtime implementation series and this final data-only diff. No release/publish/deploy beyond the authorized acceptance installation is implied.

If any endpoint requires a code or harness change, mark that attempt **failed configuration-only acceptance**. Record the cause, correct the general implementation in a new runtime commit, repeat relevant verification and freeze, then select fresh endpoints absent from that new freeze. Do not quietly fold a fix into the frozen runtime or relabel fixtures as live acceptance. Missing paid authorization, missing live runs, or unavailable Windows tooling means **incomplete**, not passed.

## Coverage and execution handoff

| Approved spec area | Owning tasks |
| --- | --- |
| Scope, additive migration, operation identity and adapter boundaries (§3–7, §14) | 1–4, 7 |
| Defaults/types/conditions/payloads (§8) | 1–2, 7–9 |
| Media, single-result contracts (§9) | 2–3, 5, 11–12 |
| Dispatch, durable bindings, restart and cancellation (§10) | 3–5, 11 |
| Pricing and confirmation (§11) | 6–9, 12 |
| Catalog loading and distribution (§12) | 1, 7, 10–12 |
| UI, native/MCP and legacy compatibility (§13–14) | 7–9, 11 |
| Frozen-runtime proof and regression (§15–16) | 10–12 |

The planning deliverable is this document; no runtime implementation or paid testing has been performed by writing it. Review the stage boundaries and shared interfaces before implementation. Recommended execution method: task-by-task subagent implementation with a fresh review at each gate, because the native/managed/Python contracts and paid-dispatch persistence need independent checks. Inline execution is also supported if preferred. Use an isolated managed worktree when implementation begins, preserve unrelated workspace changes, and follow the selected execution skill.
