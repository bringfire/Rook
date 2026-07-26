# RookBIM Gated Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution model:** Before Task 1, use `superpowers:using-git-worktrees` to create a clean `.worktrees/rookbim-gated-diagnostics` checkout on branch `codex/rookbim-gated-diagnostics`. The corrected plan commit must be a documentation-only direct descendant of reviewed base `262d3691`; branch from that corrected commit so the executable plan is present while the implementation source baseline remains `262d3691`. Execute Tasks 1-9 sequentially with `superpowers:subagent-driven-development`, completing each task's implementation review and quality gate before the next task. Do not parallelize tasks. Execute Task 10 inline with the operator because it closes host processes, deploys locally, launches Revit, and requires the original model.

From the original checkout, create and verify the implementation worktree with:

```powershell
$planCommit = (git rev-parse HEAD).Trim()
git merge-base --is-ancestor 262d3691 $planCommit
if ($LASTEXITCODE -ne 0) { throw "Corrected plan commit does not descend from 262d3691" }
git worktree add .worktrees/rookbim-gated-diagnostics -b codex/rookbim-gated-diagnostics $planCommit
if (git -C .worktrees/rookbim-gated-diagnostics status --porcelain) {
    throw "Implementation worktree is not clean"
}
```

The two pre-existing FFmpeg modifications remain only in `C:\Users\aryan\source\repos\Rook`; they must not appear in the implementation worktree or any implementation commit.

**Goal:** Implement an opt-in, request-correlated RookBIM trace that pinpoints the original Revit 2024.3 workshared-model failure without changing route behavior or persisting sensitive model data.

**Architecture:** The managed `Rook` assembly owns exact environment gating, request-local observations, sparse persistence, provenance, manual JSONL encoding, and a BIM-specific bounded writer. The optional `RookBim` assembly receives an immutable context explicitly through `IRookBimRuntime`, carries it through the Rhino.Inside idling queue, and wraps only the existing Revit reads named in the approved design. Every probe updates request-local state; only failures, fixed coarse milestones, and one terminal summary reach persistence.

**Tech Stack:** C# with `net48` compatibility, SDK-style `net8.0;net7.0;net48` targets for `Rook`, xUnit 2.9.2, `System.Text.Json` only for existing HTTP serialization and test parsing, Autodesk Revit 2024 API isolated to `src/RookBim`, and Windows PowerShell for verification/deployment.

## Global Constraints

- Treat `docs/superpowers/specs/2026-07-25-rookbim-diagnostics-design.md` as authoritative; stop for review before deviating.
- Read `ROOK_BIM_DIAGNOSTICS` once per Revit process. Enable only when `String.Equals(value, "1", StringComparison.Ordinal)` is true.
- Require a Revit restart. Use a process-scoped launcher environment and never recommend or invoke `setx`.
- Call `BimDiagnostics.InitializeFromEnvironment()` at the first executable line of `BimHandler.Dispatch`, before parsing, standalone status, and `RookBimModuleLoader.TryActivate()`.
- Expose core/module version and commit unconditionally in `/bim/status`; expose correlation and request outcome only while enabled.
- Execute `CompleteRequest` exactly once after each accepted context is created, including success, validation, runtime exception, serialization exception, and minimal fallback.
- Pass context explicitly through all ten `IRookBimRuntime` methods and the queued Revit work item. Do not use `AsyncLocal`, thread-static state, a global current ID, or a correlation dictionary.
- Keep Autodesk/Revit/Rhino.Inside references out of `src/Rook`; do not add dependencies or modify project files unless compilation proves the SDK include rule insufficient.
- Production probes evaluate each original expression once and rethrow the same exception with bare `throw;`. Auxiliary probes catch locally, record `probe_failure`, return unknown, and never feed route output/control flow.
- Disabled production call sites evaluate the original expression directly. Disabled auxiliary call sites return before constructing or invoking a Revit delegate.
- Preserve both independent `Document.IsWorkshared` reads and existing central-GUID catches. Do not add `InternalException` handling before live evidence.
- Preserve compiler-equivalent enumerator disposal. Iterator creation and `MoveNext` failures remain loud; never return a partial category table as success.
- Never persist exception messages or call `Exception.ToString()`. Never persist/hash model titles, model paths, category names, element/category IDs, GUID values, request bodies, or geometry.
- Persist every failure, only the fixed coarse start/success milestones, and one terminal. Do not persist per-item category start/success observations.
- Keep terminal admission and the sink BIM-specific under `src/Rook/Bim/Diagnostics`; do not create a repository-wide logging framework.
- Revit/handler producer threads perform no filesystem I/O and no blocking queue operation.
- The independent JSONL guarantee begins only after `SerializeForWire` entry. Assembly binding/loading, pre-entry JIT/type initialization, and the outer native envelope remain out of scope.
- Do not change the native callback/envelope, route semantics, `not_rhino_inside` taxonomy, or category degradation behavior.
- Keep `feec425e`, `a4b84d3a`, diagnostic implementation, later hardening, and later taxonomy cleanup independently reviewable.
- Preserve the existing unstaged `third_party/ffmpeg/ffmpeg-provenance.json` and `third_party/ffmpeg/ffmpeg.exe`; stage explicit paths only.
- Commit implementation before deploy so assembly provenance identifies the live-tested commit.
- Source-contract tests are insufficient for acceptance; Task 10 must reproduce against the original workshared model.

---

## File Map

New production files under `src/Rook/Bim/Diagnostics/`:

All production diagnostic types use namespace `Rook.Bim` even though focused files live in the `Diagnostics` directory. This keeps the existing core/optional-module boundary explicit without adding another cross-assembly namespace convention.

- `BimDiagnosticContracts.cs`: public cross-assembly enums/closed fields/context plus internal observation/envelope shapes.
- `BimDiagnosticOutcomeAccumulator.cs`: sequence-based first-failure, last-stage/index, sealing, and saturating request drops.
- `BimDiagnosticSession.cs`: context creation, sparse policy, exactly-once terminal completion, and provenance.
- `BimDiagnostics.cs`: process-wide read-once facade and test-scoped session replacement.
- `BimDiagnosticProbe.cs`: distinct production/auxiliary wrappers.
- `BimDiagnosticEnumerator.cs`: Revit-agnostic non-generic traversal and disposal.
- `BimDiagnosticExceptionCapture.cs`: message-free bounded exception tree and stack redaction.
- `BimDiagnosticJsonEncoder.cs`: fixed-order dependency-free JSONL encoding.
- `BimDiagnosticSink.cs`: one bounded FIFO queue, terminal admission, background writer, limits, and sink state.

New tests under `src/Rook.Tests/Bim/Diagnostics/`: outcome, probe, enumerator, persistence-policy, encoding, privacy, sink, and configuration suites. Add `BimDiagnosticTestHarness.cs` there for a fake envelope sink plus enabled-context/snapshot factories shared by those tests. Add `src/Rook.Tests/Handlers/BimHandlerDiagnosticsTests.cs` for handler lifecycle and serialization, and `src/Rook.Tests/Bim/RookBimModuleLoaderDiagnosticsTests.cs` for activation outcomes.

Modify core files: `BimContracts.cs`, `IRookBimRuntime.cs`, `RookBimUnavailableRuntime.cs`, `RookBimModuleLoader.cs`, `BimHandler.cs`, all runtime fakes/direct callers, and BIM handler export source assertions.

Modify optional-module files: `RookBimModule.cs`, `RevitApiDispatcher.cs`, `RevitRookBimRuntime.cs`, `RevitIdentitySerializer.cs`, `RevitCategoryResolver.cs`, `RevitQueryService.cs`, `RevitPresetResolver.cs`, and relevant `RookBim.Tests` source contracts.

Explicitly unchanged: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`, `src/RookNative/**`, category result contracts, and error taxonomy.

---

### Task 1: Closed contracts and request-local outcome state

**Files:**
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticContracts.cs`
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticOutcomeAccumulator.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticOutcomeAccumulatorTests.cs`

**Interfaces:**
- Produces public `BimDiagnosticStage`, `BimDiagnosticOutcome`, `BimDiagnosticRecordKind`, `BimDiagnosticDetailCode`, `BimDiagnosticFailureImpact`, `BimDiagnosticSinkState`, `BimDiagnosticSinkFailureCode`, `BimDiagnosticFields`, and `BimDiagnosticContext`.
- Produces internal observation/request/status snapshots and `BimDiagnosticOutcomeAccumulator`.
- Uses only BCL types available on `net48`; no JSON or Revit types.

- [ ] **Step 1: Write failing sequence and sealing tests**

Deliver observations deliberately out of lock order and assert sequence wins:

```csharp
[Fact]
public void Snapshot_UsesSequenceForFirstFailureLastStageAndLastIndexedItem()
{
    var state = new BimDiagnosticOutcomeAccumulator();
    state.Observe(Failure(40, BimDiagnosticStage.RevitCategoryName, 9,
        BimDiagnosticFailureImpact.Production, typeof(InvalidOperationException), -3));
    state.Observe(Success(50, BimDiagnosticStage.HandlerSerialize));
    state.Observe(Failure(20, BimDiagnosticStage.RevitDocumentCentralGuid, 3,
        BimDiagnosticFailureImpact.Production, typeof(Exception), -1));
    state.Observe(Failure(10, BimDiagnosticStage.RevitDocumentCentralModelPath, null,
        BimDiagnosticFailureImpact.Auxiliary, typeof(Exception), -2));

    var result = state.Snapshot();
    Assert.Equal(BimDiagnosticStage.RevitDocumentCentralGuid, result.FirstFailureStage);
    Assert.Equal(BimDiagnosticStage.HandlerSerialize, result.LastStage);
    Assert.Equal(BimDiagnosticOutcome.Success, result.LastOutcome);
    Assert.Equal(9, result.LastItemIndex);
}
```

Also assert `TrySeal()` succeeds once, post-seal observations are rejected, delayed `RecordDrop()` remains accepted, and `long.MaxValue - 1` saturates at `long.MaxValue`.

Define private test helpers `Failure(long sequence, BimDiagnosticStage stage, long? index, BimDiagnosticFailureImpact impact, Type type, int hresult)` and `Success(long sequence, BimDiagnosticStage stage)` in this test class; each constructs the corresponding closed `BimDiagnosticObservation` without messages.

- [ ] **Step 2: Verify the red state**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~BimDiagnosticOutcomeAccumulatorTests --verbosity minimal
```

Expected: compile failure on missing diagnostic types, not an unrelated toolchain error.

- [ ] **Step 3: Implement the complete closed vocabularies**

`BimDiagnosticStage` contains exactly:

```text
CoreInitialize;
ModuleResolve, ModuleLoad, ModuleActivate, ModuleMetadata;
HandlerDeserialize, HandlerRuntime, HandlerSerialize, HandlerTerminal;
RevitDispatchEnqueue, RevitDispatchExecute, RevitDocumentAcquire;
RevitViewActiveGraphical;
RevitDocumentCentralIsWorkshared, RevitDocumentCentralGuid, RevitDocumentTitle,
RevitDocumentPath, RevitDocumentIsFamily, RevitDocumentOutputIsWorkshared;
RevitDocumentIsModelInCloud, RevitDocumentIsDetached,
RevitDocumentCentralModelPath, RevitDocumentModelPathEmpty,
RevitDocumentModelPathServer, RevitDocumentModelPathCloud;
RevitCategoriesSettings, RevitCategoriesCollection, RevitCategoriesIterator,
RevitCategoriesMoveNext, RevitCategoriesCurrent, RevitCategoriesIteratorDispose;
RevitCategoryId, RevitCategoryName, RevitCategoryBuiltIn, RevitCategoryType;
SinkWriter
```

Define outcomes `Start/Success/Failure`, record kinds `Milestone/Failure/Terminal`, impacts `None/Production/Auxiliary`, and detail codes `None`, `True`, `False`, `Null`, `NotApplicable`, `NotWorkshared`, `AlreadyInitialized`, `NoActiveView`, `Unsaved`, `File`, `Server`, `Cloud`, `Detached`, `Unknown`, `ProbeFailure`, `NotDisposable`, `Truncated`, `SerializationFailure`, `ExceptionCaptureFailed`.

`BimDiagnosticSinkFailureCode` is also closed. Define every member and its exact wire value together; no caller-selected string is permitted:

| Member | Wire value |
|---|---|
| `None` | `none` |
| `QueueFull` | `queue_full` |
| `QueueContention` | `queue_contention` |
| `PriorityEviction` | `priority_eviction` |
| `RecordInvalid` | `record_invalid` |
| `RecordOversize` | `record_oversize` |
| `FileLimitReached` | `file_limit_reached` |
| `DirectoryCreateFailure` | `directory_create_failure` |
| `FileOpenFailure` | `file_open_failure` |
| `FileWriteFailure` | `file_write_failure` |
| `FileFlushFailure` | `file_flush_failure` |
| `EncoderFailure` | `encoder_failure` |

Task 3 adds a theory covering every member/wire pair in this table. Fail closed on undefined numeric enum values so the encoder cannot invent new failure vocabulary.

Validate operation to at most 128 characters before context construction; reject arbitrary enum values during record creation/encoding. Bound version/commit strings to 128 and exception type names to 512 characters without using message text.

The fields type has no dictionary/string escape hatch:

```csharp
public readonly struct BimDiagnosticFields
{
    public BimDiagnosticFields(BimDiagnosticDetailCode detailCode, long? itemIndex,
        BimDiagnosticFailureImpact failureImpact)
    {
        DetailCode = detailCode;
        ItemIndex = itemIndex;
        FailureImpact = failureImpact;
    }
    public BimDiagnosticDetailCode DetailCode { get; }
    public long? ItemIndex { get; }
    public BimDiagnosticFailureImpact FailureImpact { get; }
    public static BimDiagnosticFields None => default;
}
```

Expose only `Enabled`, `CorrelationId`, and `Operation` from the immutable context. Keep session/accumulator references internal/readonly. `BimDiagnosticContext.Disabled` is shared and allocates no GUID/accumulator.

- [ ] **Step 4: Implement deterministic accumulator semantics**

Use a private lock for compound state. Track last stage/outcome by highest sequence, last item by highest indexed sequence, and first production failure by lowest sequence. Store only bounded exception type name and HResult, never exception/message objects. Keep drop increments valid after sealing and saturating.

- [ ] **Step 5: Run focused and full core tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~BimDiagnosticOutcomeAccumulatorTests --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: new and existing tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- src/Rook/Bim/Diagnostics/BimDiagnosticContracts.cs src/Rook/Bim/Diagnostics/BimDiagnosticOutcomeAccumulator.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticOutcomeAccumulatorTests.cs
git commit -m "feat(rookbim): add request diagnostic state model"
```

---

### Task 2: Probe contracts, sparse policy, and disposal-safe enumeration

**Files:**
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticSession.cs`
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticProbe.cs`
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticEnumerator.cs`
- Create: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticTestHarness.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticProbeTests.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticEnumeratorTests.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticPersistencePolicyTests.cs`

**Interfaces:**
- Consumes Task 1 contracts/state.
- Produces `BimDiagnosticSession.CreateContext/Observe/ObserveException/CompleteRequest`, `BimDiagnosticProbe.Production<T>/Auxiliary<T>`, `BimAuxiliaryProbeResult<T>`, and `BimDiagnosticEnumerator.ForEach<T>`.
- Produces internal `IBimDiagnosticEnvelopeSink`, immutable `BimDiagnosticEnvelope`, and fixed `BimDiagnosticRecord`; Task 4 supplies the real sink.
- The test harness produces `TestDiagnostics.EnabledContext(string)`, `Snapshot(context)`, and an in-memory sink; it is test-only and never enters `src/Rook`.

- [ ] **Step 1: Write failing production/auxiliary tests**

```csharp
[Fact]
public void Production_RethrowsSameExceptionAndAuxiliaryReturnsUnknown()
{
    var context = TestDiagnostics.EnabledContext("list_categories");
    var expected = new InvalidOperationException("never persist this message");
    var actual = Assert.Throws<InvalidOperationException>(() =>
        BimDiagnosticProbe.Production<int>(context, BimDiagnosticStage.RevitCategoryId,
            () => throw expected,
            new BimDiagnosticFields(BimDiagnosticDetailCode.None, 7,
                BimDiagnosticFailureImpact.Production)));
    Assert.Same(expected, actual);

    var auxiliary = BimDiagnosticProbe.Auxiliary<int>(context,
        BimDiagnosticStage.RevitDocumentCentralModelPath,
        () => throw new InvalidOperationException("ignored"));
    Assert.False(auxiliary.Known);
}
```

Add a source assertion requiring bare `throw;` and forbidding `throw ex;` in the production wrapper.

- [ ] **Step 2: Write failing sparse-persistence/completion tests**

With an in-memory sink, observe 500 category items with start/success for `MoveNext`, `Current`, and four properties. Assert zero per-item envelopes, last index 499, one property failure envelope, fixed `handler.runtime` milestones, and exactly one terminal. Call completion twice and observe after completion; assert the second completion/post-seal observation add nothing.

- [ ] **Step 3: Write failing iterator-disposal tests**

Use a controlled non-generic `IEnumerable/IEnumerator`. Cover normal completion, final false `MoveNext`, and exceptions from `MoveNext`, `Current`, visitor, and `Dispose`. Assert disposal occurs exactly once after each traversal path; a disposal exception replaces an in-flight exception as compiler-generated `foreach` would. Cover a non-disposable iterator and expect `NotDisposable` success.

- [ ] **Step 4: Verify the red state**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimDiagnosticProbeTests|FullyQualifiedName~BimDiagnosticEnumeratorTests|FullyQualifiedName~BimDiagnosticPersistencePolicyTests" --verbosity minimal
```

Expected: compile failure on missing session/probe/enumerator.

- [ ] **Step 5: Implement sparse observation and exactly-once completion**

Assign a global `long` sequence with `Interlocked.Increment` and producer `DateTime.UtcNow`. Every enabled request observation updates its accumulator. Enqueue all failures; enqueue start/success only for:

```text
CoreInitialize, ModuleResolve, ModuleLoad, ModuleActivate, ModuleMetadata,
HandlerDeserialize, HandlerRuntime, HandlerSerialize,
RevitDispatchEnqueue, RevitDispatchExecute, RevitDocumentAcquire
```

`CompleteRequest` first calls `TrySeal`; only the winner creates a `Terminal` envelope with `HandlerTerminal`. The terminal retains the accumulator for writer-time materialization; later normal observations are ignored while delayed drop accounting remains legal.

- [ ] **Step 6: Implement distinct wrappers**

```csharp
public static T Production<T>(BimDiagnosticContext context, BimDiagnosticStage stage,
    Func<T> read, BimDiagnosticFields fields,
    Func<T, BimDiagnosticDetailCode>? detail = null)

public static BimAuxiliaryProbeResult<T> Auxiliary<T>(BimDiagnosticContext context,
    BimDiagnosticStage stage, Func<T> read,
    Func<T, BimDiagnosticDetailCode>? detail = null)
```

Production observes start/success; its catch observes the exception and uses bare `throw;`. Auxiliary catches locally, observes `ProbeFailure/Auxiliary`, and returns `Unknown`. Catch detail-selector failures internally and fall back to `None`.

- [ ] **Step 7: Implement non-generic traversal with explicit `finally`**

`ForEach<T>(BimDiagnosticContext, IEnumerable, Action<T,long>)` obtains an `IEnumerator`, probes iterator/`MoveNext`/typed `Current`, calls the visitor with zero-based index, and disposes in `finally`. Each disabled branch calls the original operation directly before any diagnostic delegate is constructed. Do not use `foreach` inside the helper.

- [ ] **Step 8: Run focused/full tests and commit**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimDiagnosticProbeTests|FullyQualifiedName~BimDiagnosticEnumeratorTests|FullyQualifiedName~BimDiagnosticPersistencePolicyTests" --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
git add -- src/Rook/Bim/Diagnostics/BimDiagnosticSession.cs src/Rook/Bim/Diagnostics/BimDiagnosticProbe.cs src/Rook/Bim/Diagnostics/BimDiagnosticEnumerator.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticTestHarness.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticProbeTests.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticEnumeratorTests.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticPersistencePolicyTests.cs
git commit -m "feat(rookbim): add sparse diagnostic observations"
```

---

### Task 3: Message-free exception capture and dependency-free JSONL

**Files:**
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticExceptionCapture.cs`
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticJsonEncoder.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticJsonEncoderTests.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticPrivacyTests.cs`

**Interfaces:**
- Consumes Task 1 record shapes and Task 2 failure envelopes.
- Produces `BimDiagnosticExceptionCapture.Capture(Exception)` returning `BimDiagnosticExceptionCaptureResult`, internal `BimDiagnosticRedactor.RedactStack(string)`, `BimDiagnosticJsonEncoder.Encode(BimDiagnosticRecord)`, exhaustive enum-to-wire mappings, and deterministic record shrinking.
- Production files have no `System.Text.Json` dependency.

- [ ] **Step 1: Write failing escaping/schema tests**

Encode a fixed record containing quotes, backslashes, every U+0000-U+001F control, CR/LF/tab, and unpaired high/low surrogates in permitted test strings. Assert one physical line, parse it with `JsonDocument` in tests, and assert unpaired surrogates become U+FFFD.

Assert exact fixed key order:

```text
schemaVersion, recordKind, sequence, timestampUtc, processId, threadId,
correlationId, operation, stage, outcome, detailCode, itemIndex, failureImpact,
lastStage, lastOutcome, lastItemIndex,
firstFailureStage, firstFailureExceptionType, firstFailureHResult,
requestDroppedCount, traceComplete,
coreVersion, coreCommit, moduleVersion, moduleCommit,
exceptionType, exceptionHResult, exceptionStack, innerExceptions, truncated
```

Add exhaustive theories for every closed enum mapping, including every `BimDiagnosticSinkFailureCode` member/wire pair declared in Task 1. Assert undefined numeric values are rejected rather than serialized with `ToString()`.

- [ ] **Step 2: Write failing privacy/bounds tests**

Use a hostile exception whose overridden `Message` and `ToString()` throw. Its hidden text includes `Snowdon Towers`, `Walls`, `.rvt`, GUIDs, and newlines. Assert capture/encoding succeed and those literals are absent.

Test the stack redactor with drive, UNC, file/server/cloud URI-like paths, brace/hyphenated/compact GUIDs, and source paths. Assert replacements preserve method names/line numbers. Test root-plus-four depth and eight aggregate inner exceptions; excess sets `truncated=true`.

- [ ] **Step 3: Verify the red state**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimDiagnosticJsonEncoderTests|FullyQualifiedName~BimDiagnosticPrivacyTests" --verbosity minimal
```

Expected: compile failure on capture/encoder types.

- [ ] **Step 4: Implement bounded capture without messages**

Use this closed exception node:

```csharp
internal sealed class BimDiagnosticExceptionInfo
{
    public string? TypeName { get; set; }
    public int HResult { get; set; }
    public string? Stack { get; set; }
    public IReadOnlyList<BimDiagnosticExceptionInfo> InnerExceptions { get; set; }
        = Array.Empty<BimDiagnosticExceptionInfo>();
    public bool Truncated { get; set; }
}
```

Never access `Message`, `Data`, `Source`, or `ToString()`. Traverse iteratively, bound stack to 8,192 characters after redaction, depth to four nested levels, aggregate children to eight total. Hostile capture degrades to `ExceptionCaptureFailed` and never escapes route handling.

`BimDiagnosticExceptionCaptureResult` contains only the captured root (nullable) and a closed `BimDiagnosticDetailCode`; use `ExceptionCaptureFailed` when capture/redaction itself fails so callers never infer failure from arbitrary text.

- [ ] **Step 5: Implement manual fixed-schema encoding**

Append fields in the approved order to `StringBuilder`. Map each enum with exhaustive switches to exact lower/snake wire values; reject unmapped values rather than calling `ToString()`. Escape quotes, backslashes, `\b/\f/\n/\r/\t`, remaining controls as `\u00XX`, and unpaired surrogates as `\uFFFD`.

Every materialized milestone, failure, and terminal record includes the bounded core/module version and commit snapshot. A record produced before optional-module registration uses literal `unavailable`; subsequent records use the atomically registered module provenance.

For output over 16 KiB including newline: set `truncated`, remove deepest inner nodes, then all inner nodes, then halve the root stack repeatedly to empty and re-encode. Drop the record if its fixed minimal form still exceeds 16 KiB.

- [ ] **Step 6: Assert production independence and run tests**

Source-read both production files and forbid `System.Text.Json`, `JsonSerializer`, `JsonNode`, `Exception.Message`, and `Exception.ToString`.

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimDiagnosticJsonEncoderTests|FullyQualifiedName~BimDiagnosticPrivacyTests" --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: every physical line parses as one object and forbidden privacy fixtures are absent.

- [ ] **Step 7: Commit**

```powershell
git add -- src/Rook/Bim/Diagnostics/BimDiagnosticExceptionCapture.cs src/Rook/Bim/Diagnostics/BimDiagnosticJsonEncoder.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticJsonEncoderTests.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticPrivacyTests.cs
git commit -m "feat(rookbim): encode private bounded diagnostic records"
```

---

### Task 4: Read-once bootstrap, provenance, and BIM-specific sink

**Files:**
- Create: `src/Rook/Bim/Diagnostics/BimDiagnosticSink.cs`
- Create: `src/Rook/Bim/Diagnostics/BimDiagnostics.cs`
- Modify: `src/Rook/Bim/Diagnostics/BimDiagnosticSession.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticSinkTests.cs`
- Test: `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticsConfigurationTests.cs`

**Interfaces:**
- Consumes Tasks 2-3 envelopes/encoder.
- Produces public facade methods `InitializeFromEnvironment`, `CreateContext`, `Observe`, `ObserveException`, `CompleteRequest`, `RegisterModuleMetadata`, `SnapshotRequest`, and `SnapshotStatus`, plus internal `CreateUncorrelatedContext(string operation)` for initialized pre-discriminator parsing/serialization evidence without a correlation ID or terminal.
- Produces internal `BimDiagnosticBootstrap(environmentReader, sinkFactory, coreAssembly)` and `BimDiagnostics.PushSessionForTests(session)`.

- [ ] **Step 1: Write failing exact-gating/read-once tests**

Use a counting environment reader. Missing, empty, `true`, `TRUE`, `01`, `1 `, and ` 1` disable; only exact `1` enables. Change its supplied value after initialization and assert no second read/new session. Disabled initialization must not invoke sink factory, create a GUID/thread, or touch a directory.

Place static facade tests in `[Collection(RookBimRuntimeRegistryCollection.Name)]` to prevent shared-state races.

- [ ] **Step 2: Write failing provenance tests**

Feed assemblies with known `AssemblyName.Version` and `AssemblyInformationalVersionAttribute`. Core version/hex suffix commit are immediate; module fields start `unavailable`; registration atomically changes module fields without environment reread/sink recreation. Nonhex or absent suffix produces `unavailable`.

- [ ] **Step 3: Write failing queue/writer tests**

With capacity 2, cover:

- terminal admission atomically evicts the oldest milestone/failure and accounts global/owning-request drops;
- a terminal never evicts another terminal;
- zero-timeout monitor contention rejects immediately and counts a drop;
- encoder, record-invalid, record-oversize, file-limit, directory-create, open, write, and flush failures set the exact closed state/code and both applicable drop counts;
- queue-full, zero-timeout contention, and priority eviction use `QueueFull`, `QueueContention`, and `PriorityEviction` respectively;
- a writer-time terminal snapshot sees delayed failures of preceding FIFO envelopes;
- envelope accumulator references are explicitly released after write/drop;
- output is UTF-8 without BOM, records are at most 16 KiB, and writing stops without rotation at 16 MiB.

- [ ] **Step 4: Verify the red state**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimDiagnosticSinkTests|FullyQualifiedName~BimDiagnosticsConfigurationTests" --verbosity minimal
```

Expected: compile failure on bootstrap/sink/facade.

- [ ] **Step 5: Implement one atomic FIFO admission rule**

Keep `Queue<BimDiagnosticEnvelope>` private and guard it with a BIM-specific lock. Producers use only `Monitor.TryEnter(sync, 0)`. Under that atomic section:

```csharp
if (queue.Count < capacity)
    queue.Enqueue(envelope);
else if (envelope.Kind == BimDiagnosticRecordKind.Terminal &&
         queue.Peek().Kind != BimDiagnosticRecordKind.Terminal)
{
    var evicted = queue.Dequeue();
    evicted.MarkDropped(BimDiagnosticSinkFailureCode.PriorityEviction);
    evicted.ReleaseAccumulator();
    queue.Enqueue(envelope);
}
else
{
    envelope.MarkDropped(BimDiagnosticSinkFailureCode.QueueFull);
    envelope.ReleaseAccumulator();
    return false;
}
```

Use production capacity 1,024. Signal one background `Thread` using `AutoResetEvent`; only the writer may block on file work.

- [ ] **Step 6: Implement bounded file lifecycle**

On the writer thread only, create `%LOCALAPPDATA%\Rook\diagnostics`, open `rookbim-<UTC-start>-<process-id>.jsonl`, write UTF-8 without BOM, and flush. Never rotate. Expose states `disabled`, `starting`, `ready`, `degraded`, `file_limit_reached`, `failed`, `stopped`; retain only the first `BimDiagnosticSinkFailureCode` from Task 1. Map each queue, validation, size, file-limit, directory, open, write, flush, and encoder failure to its declared code—never to exception text. Process exit signals completion and joins at most 250 ms.

- [ ] **Step 7: Implement behavior-neutral process facade**

The bootstrap uses lock/volatile state to read environment once. Default sink path is fixed; only internal tests inject path/reader/factory. Every public facade method catches its own failures and updates bounded in-memory evidence when possible. `PushSessionForTests` returns `IDisposable` restoring/stopping the prior test session; no production route toggles diagnostics.

Initialization observes `core.initialize` start/success (or bounded failure). `RegisterModuleMetadata` observes `module.metadata` without creating/reconfiguring the sink or rereading environment.

- [ ] **Step 8: Run tests and commit**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimDiagnosticSinkTests|FullyQualifiedName~BimDiagnosticsConfigurationTests" --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
git add -- src/Rook/Bim/Diagnostics/BimDiagnosticSink.cs src/Rook/Bim/Diagnostics/BimDiagnostics.cs src/Rook/Bim/Diagnostics/BimDiagnosticSession.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticSinkTests.cs src/Rook.Tests/Bim/Diagnostics/BimDiagnosticsConfigurationTests.cs
git commit -m "feat(rookbim): add gated bounded diagnostic sink"
```

---

### Task 5: Runtime interface migration, fakes, and source contracts

**Files:**
- Modify: `src/Rook/Bim/IRookBimRuntime.cs:3-25`
- Modify: `src/Rook/Bim/RookBimUnavailableRuntime.cs:3-67`
- Modify: `src/Rook/Handlers/BimHandler.cs:10-472` only for the temporary disabled-context migration scaffold and context-bearing runtime calls.
- Modify mechanically: `src/RookBim/Revit/RevitRookBimRuntime.cs:37-360`
- Modify: `src/Rook.Tests/Bim/RookBimUnavailableRuntimeTests.cs`
- Modify: `src/Rook.Tests/Bim/RookBimUnavailableExportTests.cs`
- Modify: `src/Rook.Tests/Bim/RookBimUnavailablePresetTests.cs`
- Modify: `src/Rook.Tests/Handlers/BimHandlerTests.cs`
- Modify: `src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs`
- Modify: `src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs`
- Modify: `src/Rook.Tests/Handlers/BimHandlerExportSourceTests.cs`
- Modify: `src/Rook.Tests/Handlers/BimHandlerExportPresetSourceTests.cs`
- Modify: `src/RookBim.Tests/RookBimExportSourceTests.cs`
- Modify: `src/RookBim.Tests/RookBimExportPresetSourceTests.cs`

**Interfaces:**
- Consumes Task 1 `BimDiagnosticContext`.
- Produces a context-bearing `IRookBimRuntime` and matching implementations/callers with no compatibility overloads.
- Deliberately leaves request-context creation, completion, serialization, and HTTP evidence for Task 6.

- [ ] **Step 1: Write the failing interface/source contracts**

Update all runtime fakes and direct callers to require/pass `BimDiagnosticContext`. Update both exact optional-module assertions at `RookBimExportSourceTests.cs:127` and `RookBimExportPresetSourceTests.cs:127` to require the new public signatures. Update core handler source assertions to require the context argument at export call sites.

- [ ] **Step 2: Verify the red state includes both exact assertions**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimHandlerTests|FullyQualifiedName~RookBimUnavailable|FullyQualifiedName~ManagedCapabilityDomainStatusTests|FullyQualifiedName~CompanionRuntimeStatusTests|FullyQualifiedName~BimHandlerExportSourceTests|FullyQualifiedName~BimHandlerExportPresetSourceTests" --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~RookBimExportSourceTests|FullyQualifiedName~RookBimExportPresetSourceTests" --verbosity minimal
```

Expected: interface/fake compilation fails and both exact `RevitRookBimRuntime` signature assertions fail before production changes.

- [ ] **Step 3: Change the runtime interface atomically**

Use exactly:

```csharp
BimStatusResponse Status(BimDiagnosticContext diagnostics);
BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics);
BimApiResponse ListCategories(BimDiagnosticContext diagnostics);
BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request);
BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request);
BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request);
BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request);
BimApiResponse ClearSelection(BimDiagnosticContext diagnostics);
BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request);
BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request);
```

- [ ] **Step 4: Migrate implementations and every caller**

Update unavailable runtime, all fakes/direct tests, and public `RevitRookBimRuntime` signatures together. Direct non-handler callers pass `BimDiagnosticContext.Disabled`. In `BimHandler`, introduce one clearly marked Task 5 migration local set to `BimDiagnosticContext.Disabled` and pass it to all ten runtime calls; Task 6 must remove this scaffold when it creates the accepted request context. Do not create a compatibility overload that omits context.

- [ ] **Step 5: Run the complete migration gate**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: all existing tests, both exact export assertions, and the optional module build pass with the new mandatory interface.

- [ ] **Step 6: Commit the interface migration**

```powershell
git add -- src/Rook/Bim/IRookBimRuntime.cs src/Rook/Bim/RookBimUnavailableRuntime.cs src/Rook/Handlers/BimHandler.cs src/RookBim/Revit/RevitRookBimRuntime.cs src/Rook.Tests/Bim/RookBimUnavailableRuntimeTests.cs src/Rook.Tests/Bim/RookBimUnavailableExportTests.cs src/Rook.Tests/Bim/RookBimUnavailablePresetTests.cs src/Rook.Tests/Handlers/BimHandlerTests.cs src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs src/Rook.Tests/Handlers/BimHandlerExportSourceTests.cs src/Rook.Tests/Handlers/BimHandlerExportPresetSourceTests.cs src/RookBim.Tests/RookBimExportSourceTests.cs src/RookBim.Tests/RookBimExportPresetSourceTests.cs
git diff --cached --name-only
git commit -m "refactor(rookbim): require diagnostics context at runtime boundary"
```

---

### Task 6: Handler lifecycle, serialization, terminal completion, and HTTP evidence

**Files:**
- Modify: `src/Rook/Bim/BimContracts.cs:160-173`
- Modify: `src/Rook/Handlers/BimHandler.cs:10-472`
- Modify: `src/Rook.Tests/Handlers/BimHandlerTests.cs`
- Create: `src/Rook.Tests/Handlers/BimHandlerDiagnosticsTests.cs`

**Interfaces:**
- Consumes Task 4 `BimDiagnostics` and Task 5's context-bearing runtime.
- Produces one accepted-request context/terminal lifecycle and instance `SerializeForWire(context,value)` used by every `ToWireData` path.
- Preserves `NativeGhBridgeRegistrar.SerializeBimDispatchEnvelope` unchanged/out of scope.

- [ ] **Step 1: Write failing lifecycle/concurrency tests under shared-state isolation**

Declare the new static-diagnostics suite exactly as:

```csharp
using Rook.Tests.Bim;

[Collection(RookBimRuntimeRegistryCollection.Name)]
public sealed class BimHandlerDiagnosticsTests
```

Test success, runtime exception, typed-request failure after context creation, standalone status, serializer exception, and minimal fallback. Each accepted operation creates one context and one terminal. Dispatch two barrier-controlled runtime requests concurrently; runtime-received correlation IDs must be distinct and each terminal must match its request. The collection prevents these static facade/registry tests from racing other RookBIM tests while retaining concurrency inside the test itself.

Add a source assertion that accepted-request control flow contains exactly one `CompleteRequest(` call, that it is in the outer `finally`, and that route helpers contain none. Assert the Task 5 disabled-context scaffold is gone.

- [ ] **Step 2: Write failing serializer-entry tests**

Add an internal handler constructor accepting `Func<object?, JsonNode?> wireSerializer`. Inject a post-entry throw and assert one `handler.serialize/failure` record (type/HResult, no message), correct first production failure, existing `internal_error` fallback, no recursive serializer call, and one terminal. Source-extract `BimHandler.cs` and assert `ToWireData(` is called only inside `SerializeForWire`.

Do not test or claim coverage for static `JsonOptions`, binding/type initialization, or the outer bridge envelope.

- [ ] **Step 3: Write failing status/HTTP tests**

Standalone and in-host status data always contain `coreVersion`, `coreCommit`, `moduleVersion`, `moduleCommit`, `diagnosticsEnabled`, `sinkState`, `droppedCount`, `sinkFailureCode`.

While enabled, merge `correlationId`, `lastStage`, `lastOutcome`, `lastItemIndex`, `firstFailureStage`, `firstFailureExceptionType`, `firstFailureHResult`, `requestDroppedCount`, `traceComplete`, sink state, and global drops into the existing diagnostic object. Existing `reasonCode`, `failureKind`, and `diagnosticRoute` must survive. Disabled responses contain none of the request fields and keep current shape.

- [ ] **Step 4: Verify the red state**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimHandlerDiagnosticsTests|FullyQualifiedName~BimHandlerTests" --verbosity minimal
```

Expected: the new lifecycle, serialization, provenance, and HTTP assertions fail.

- [ ] **Step 5: Give `Dispatch` one completion `finally`**

Required shape:

```csharp
public ApiResponse Dispatch(string? body)
{
    BimDiagnostics.InitializeFromEnvironment();
    // Parse/validate the discriminator; pre-op failure uses initialized uncorrelated evidence.
    var diagnostics = BimDiagnostics.CreateContext(op!);
    ApiResponse? response = null;
    try
    {
        response = DispatchAcceptedRequest(diagnostics, op!, body);
        return response;
    }
    catch (JsonException ex)
    {
        response = Fail(diagnostics, BimErrorCode.InvalidScope,
            $"Invalid BIM request JSON: {ex.Message}", 400);
        return response;
    }
    catch (ArgumentException ex)
    {
        response = Fail(diagnostics, BimErrorCode.InvalidScope, ex.Message, 400);
        return response;
    }
    catch (Exception ex)
    {
        response = BuildMinimalInternalError(diagnostics, ex);
        return response;
    }
    finally
    {
        BimDiagnostics.CompleteRequest(diagnostics,
            response != null && response.Success
                ? BimDiagnosticOutcome.Success
                : BimDiagnosticOutcome.Failure);
    }
}
```

Create context after a valid operation discriminator and before standalone status or module activation. Observe deserialize/runtime milestones. Pass the same context through standalone/status, typed deserialization, runtime, `FromBimResponse`, `Ok`, and `Fail`.

Before a valid discriminator exists, use `CreateUncorrelatedContext("unparsed")` around `ParseObjectBody` and primitive fallback serialization. It carries no correlation ID/terminal but can persist a bounded `handler.deserialize` failure after initialization. Once the discriminator is accepted, discard that context and use only the request context.

- [ ] **Step 6: Centralize serialization**

Make helper methods instance/context-aware. The only `ToWireData` caller is:

```csharp
private JsonNode? SerializeForWire(BimDiagnosticContext diagnostics, object? value)
{
    BimDiagnostics.Observe(diagnostics, BimDiagnosticStage.HandlerSerialize,
        BimDiagnosticOutcome.Start, BimDiagnosticFields.None);
    try
    {
        var result = wireSerializer(value);
        BimDiagnostics.Observe(diagnostics, BimDiagnosticStage.HandlerSerialize,
            BimDiagnosticOutcome.Success, BimDiagnosticFields.None);
        return result;
    }
    catch (Exception ex)
    {
        BimDiagnostics.ObserveException(diagnostics, BimDiagnosticStage.HandlerSerialize,
            ex, new BimDiagnosticFields(BimDiagnosticDetailCode.SerializationFailure, null,
                BimDiagnosticFailureImpact.Production));
        throw;
    }
}
```

`BuildMinimalInternalError` constructs fixed `JsonObject` primitives and merges bounded diagnostic fields; it never calls `ToWireData`, `SerializeForWire`, or `Fail(details)`.

- [ ] **Step 7: Add status provenance and bounded HTTP merge**

Extend `BimStatusResponse` with the eight unconditional fields and populate before status serialization from `SnapshotStatus()`. Build request fields from `SnapshotRequest(diagnostics)` only while enabled and merge into—not replace—the Phase 2 diagnostic `JsonObject`.

- [ ] **Step 8: Run verification and commit**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal
git add -- src/Rook/Bim/BimContracts.cs src/Rook/Handlers/BimHandler.cs src/Rook.Tests/Handlers/BimHandlerTests.cs src/Rook.Tests/Handlers/BimHandlerDiagnosticsTests.cs
git diff --cached --name-only
git commit -m "feat(rookbim): correlate handler diagnostics"
```

Expected: core/source tests and the optional module build pass; every accepted context completes once.

---

### Task 7: Module-loader instrumentation and activation outcomes

**Files:**
- Modify: `src/Rook/Bim/RookBimModuleLoader.cs:9-111`
- Modify: `src/Rook/Handlers/BimHandler.cs:10-472`
- Create: `src/Rook.Tests/Bim/RookBimModuleLoaderDiagnosticsTests.cs`

**Interfaces:**
- Consumes Task 6's accepted-request context.
- Produces `RookBimModuleLoader.TryActivate(BimDiagnosticContext)` and distinct resolve/load/activate outcomes without changing registry behavior.

- [ ] **Step 1: Write failing activation-outcome tests under shared-state isolation**

Put `RookBimModuleLoaderDiagnosticsTests` in `[Collection(RookBimRuntimeRegistryCollection.Name)]`. Introduce test seams for candidate resolution, `File.Exists`, assembly loading, and reflected activation. Simulate not-found, load failure, activation failure, success, and already initialized. Assert initialization precedes resolution, every outcome has its exact stage/detail, no path/message enters evidence, and current registry outcomes remain unchanged.

- [ ] **Step 2: Verify the red state**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~RookBimModuleLoaderDiagnosticsTests --verbosity minimal
```

Expected: missing injectable core and context-bearing activation fail.

- [ ] **Step 3: Instrument loader without changing outcomes**

`TryActivate(diagnostics)` begins with defensive `BimDiagnostics.InitializeFromEnvironment()`. Its internal injectable core takes candidate resolver, file-exists predicate, assembly loader, and reflected activation delegate so resolution, load, and activation failures remain distinct stages. Wrap the existing production work with probes, preserve existing catches/registry installs, and observe `AlreadyInitialized` when already installed/attempted. Never record candidate/module paths or messages.

- [ ] **Step 4: Pass the accepted context from the handler**

Change the Task 6 call to `RookBimModuleLoader.TryActivate(diagnostics)`. Keep initialization at the first executable line of `Dispatch`; the loader's defensive call must be read-once/idempotent. Do not create another context or terminal in the loader.

- [ ] **Step 5: Run verification and commit**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal
git add -- src/Rook/Bim/RookBimModuleLoader.cs src/Rook/Handlers/BimHandler.cs src/Rook.Tests/Bim/RookBimModuleLoaderDiagnosticsTests.cs
git diff --cached --name-only
git commit -m "feat(rookbim): trace optional module activation"
```

---

### Task 8: Revit-thread propagation, view, and document identity/state

**Files:**
- Modify: `src/RookBim/RookBimModule.cs:8-34`
- Modify: `src/RookBim/Revit/RevitApiDispatcher.cs:11-160`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs:10-537`
- Modify: `src/RookBim/Revit/RevitIdentitySerializer.cs:8-203`
- Modify: `src/RookBim.Tests/RookBimModuleSourceTests.cs`

**Interfaces:**
- Consumes Task 5's context-bearing runtime, Task 6's request lifecycle, Task 7's activation boundary, and Task 2's probes.
- Produces `InvokeAbandonable<T>(BimDiagnosticContext, Func<UIApplication,T>)`, detailed `DocumentIdentity(document,diagnostics,includeAuxiliaryState)`, and context-aware active graphical view resolution.
- Preserves the untraced one-argument identity method for element/result paths.

- [ ] **Step 1: Add failing module/dispatcher source contracts**

Assert `RookBimModule.Activate` registers `typeof(RookBimModule).Assembly` before `IsLoaded`. Assert dispatcher/work item store the passed immutable context and queued `Execute` uses it. Forbid `AsyncLocal`, `[ThreadStatic]`, `ThreadLocal`, and any current/global correlation symbol. Assert runtime captures a local context before `InvokeAbandonable`.

- [ ] **Step 2: Add failing active-view/disabled source contracts**

Retain tests forbidding `UIDocument.ActiveView` and `Document.ActiveView`. Assert document scope returns before any view access. Active scope must branch as:

```csharp
return diagnostics.Enabled
    ? BimDiagnosticProbe.Production(diagnostics,
        BimDiagnosticStage.RevitViewActiveGraphical,
        () => uidoc.ActiveGraphicalView,
        BimDiagnosticFields.None,
        view => view == null
            ? BimDiagnosticDetailCode.NoActiveView
            : BimDiagnosticDetailCode.True)
    : uidoc.ActiveGraphicalView;
```

The lambda occurs only in the enabled arm.

- [ ] **Step 3: Add failing identity/state source contracts**

Assert detailed identity reads in order: guard `IsWorkshared`, conditional `WorksharingCentralGUID`, `Title`, `PathName`, `IsFamilyDocument`, output `IsWorkshared`. Assert the first value is not reused. Retain exact catches for `InapplicableDataException` and current Revit/BCL invalid-operation cases; forbid a new `InternalException` catch.

Assert active document enables auxiliary state. Assert element-level identity remains one-argument/untraced. Auxiliary state starts with `if (!diagnostics.Enabled) return;`; `GetWorksharingCentralModelPath()` is reachable only through `BimDiagnosticProbe.Auxiliary`.

- [ ] **Step 4: Verify the red state**

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~RookBimModuleSourceTests --verbosity minimal
```

Expected: new source assertions fail.

- [ ] **Step 5: Register module provenance first**

At the top of `RookBimModule.Activate`, call `BimDiagnostics.RegisterModuleMetadata(typeof(RookBimModule).Assembly)`. Do not initialize/reread environment there.

- [ ] **Step 6: Carry context through the actual work item**

Change dispatcher entry points to accept context. Observe enqueue start before reflection, success after `EnqueueIdlingAction`, failure in the existing catch. Construct `RevitApiWorkItem<T>` with context. In `Execute`, observe execute start/success/failure around `ActiveUIApplication()` plus work. Preserve state transitions, abandon semantics, continuation options, and original exceptions.

- [ ] **Step 7: Instrument document acquisition without caching away reads**

Pass context into runtime `Dispatch`, `DispatchWithTimeout`, and `ExecuteInDocumentContext`. Instrument the status operation's existing `RevitContext.ActiveDocument(uiapp)` read as well as every existing `ActiveUiDocument`/`uidoc.Document` expression. Enabled arms use `RevitDocumentAcquire`; disabled arms evaluate original expressions directly. Preserve repeated reads when caching would change existing behavior. Leave current catches/DTO taxonomy unchanged.

- [ ] **Step 8: Instrument only required graphical view access**

Add context to `ResolveActiveGraphicalView`/`SerializeActiveView`. Document scope is no-access. Active scope probes only `ActiveGraphicalView`, with no fallback. Keep active-document and export view reads inside their operation-level catches.

- [ ] **Step 9: Implement detailed identity and behavior-neutral auxiliary state**

Keep `DocumentIdentity(Document)` unchanged/untraced. Add the context overload for active document and later list categories. Each enabled production expression uses `Production`; disabled uses the direct property.

After creating the unchanged DTO, optionally call `ProbeDocumentState`. Probe `IsModelInCloud`, `IsDetached`, `GetWorksharingCentralModelPath`, and returned `Empty/ServerPath/CloudPath` independently. Use results only for closed detail codes `unsaved/file/server/cloud/detached/unknown`; never feed route DTO/branch. Each auxiliary failure records `ProbeFailure` and continues.

- [ ] **Step 10: Run tests/build and commit**

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal
git add -- src/RookBim/RookBimModule.cs src/RookBim/Revit/RevitApiDispatcher.cs src/RookBim/Revit/RevitRookBimRuntime.cs src/RookBim/Revit/RevitIdentitySerializer.cs src/RookBim.Tests/RookBimModuleSourceTests.cs
git commit -m "feat(rookbim): trace Revit dispatch and document reads"
```

Expected: source/core tests and Revit 2024 compilation pass; this is not live acceptance.

---

### Task 9: Category traversal and per-property failure isolation

**Files:**
- Modify: `src/RookBim/Revit/RevitCategoryResolver.cs:10-500`
- Modify: `src/RookBim/Revit/RevitQueryService.cs:9-218`
- Modify: `src/RookBim/Revit/RevitPresetResolver.cs:13-130`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs:77-360`
- Modify: `src/RookBim.Tests/RookBimModuleSourceTests.cs`
- Modify: `src/RookBim.Tests/RookBimExportPresetSourceTests.cs`

**Interfaces:**
- Consumes Task 2's enumerator and Task 8's identity overload.
- Produces context-bearing `RevitCategoryResolver.List/Resolve`, `RevitQueryService.Query`, and `RevitPresetResolver.Resolve` chains.
- Preserves current safe-property catches, degradation counts, sorting, and loud iterator failure.

- [ ] **Step 1: Add failing traversal source contracts**

Assert `LiveCategories` separately probes `document.Settings` and `settings.Categories`, delegates traversal to `BimDiagnosticEnumerator.ForEach<Category>`, and has no second disposal path. `TryBuildCategoryEntry` receives zero-based index and supplies it for ID/name/built-in/type. No diagnostic field receives category name/ID/enum/parent/object. Iterator creation/`MoveNext` gain no catch; safe properties retain catch lists.

- [ ] **Step 2: Add failing context-flow contracts**

Assert runtime list calls `categories.List(document, diagnostics)`; `List` uses detailed identity with auxiliary state disabled; runtime query passes diagnostics; query passes it to category resolve; preset passes the same context to every query. `BuildResult`, element identity, selection, and export retain untraced one-argument document identity.

- [ ] **Step 3: Verify the red state**

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~RookBimModuleSourceTests|FullyQualifiedName~RookBimExportPresetSourceTests" --verbosity minimal
```

Expected: new source contracts fail.

- [ ] **Step 4: Split category-map acquisition and delegate traversal**

In `LiveCategories(document,diagnostics)`, enabled conditionals probe `document.Settings` and `settings.Categories`; disabled arms call them directly. Pass the non-generic collection to `BimDiagnosticEnumerator.ForEach<Category>`. Visitor calls `TryBuildCategoryEntry(category,diagnostics,index,out entry)` and preserves existing result accounting.

- [ ] **Step 5: Wrap properties inside existing catch boundaries**

Use this exact structural pattern for name and repeat it for ID, built-in, and type:

```csharp
private static string? SafeCategoryName(Category category,
    BimDiagnosticContext diagnostics, long itemIndex)
{
    try
    {
        return diagnostics.Enabled
            ? BimDiagnosticProbe.Production(diagnostics,
                BimDiagnosticStage.RevitCategoryName,
                () => category.Name,
                new BimDiagnosticFields(BimDiagnosticDetailCode.None, itemIndex,
                    BimDiagnosticFailureImpact.Production))
            : category.Name;
    }
    catch (Autodesk.Revit.Exceptions.InvalidOperationException) { return null; }
    catch (InvalidOperationException) { return null; }
}
```

The probe rethrows first; the pre-existing reader catches only its existing exceptions. Add no catch to iterator creation/`MoveNext`.

- [ ] **Step 6: Pass context through query/preset paths**

Add context as final parameter to category `List/Resolve`, query `Query`, and preset `Resolve`; update runtime/preset callers atomically. Leave result/element identity untraced.

- [ ] **Step 7: Run all tests/build**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: all pass; source tests prove wiring and core behavioral tests prove disposal/probe semantics.

- [ ] **Step 8: Scope-check and commit**

```powershell
git diff --check
git status --short
git add -- src/RookBim/Revit/RevitCategoryResolver.cs src/RookBim/Revit/RevitQueryService.cs src/RookBim/Revit/RevitPresetResolver.cs src/RookBim/Revit/RevitRookBimRuntime.cs src/RookBim.Tests/RookBimModuleSourceTests.cs src/RookBim.Tests/RookBimExportPresetSourceTests.cs
git commit -m "feat(rookbim): trace category traversal failures"
```

Confirm no native, FFmpeg, result-contract, taxonomy, or generic logging files changed.

---

### Task 10: Full verification, committed deploy, and live Revit gate

**Files:**
- Verify: all Tasks 1-9 files from the clean implementation worktree.
- Do not commit HTTP captures or JSONL; normal route payloads may legitimately contain model data even though diagnostic records are redacted.

**Interfaces:**
- Consumes committed implementation and `scripts/deploy-local-testing.ps1`.
- Produces live evidence from the original workshared model, or a precise blocker report if host/model access is unavailable.
- Runs inline/operator-assisted from `.worktrees/rookbim-gated-diagnostics`; do not delegate this task to a subagent.

- [ ] **Step 1: Run final static scope/privacy checks**

```powershell
$implementationRoot = (Resolve-Path .).Path
if ($implementationRoot -notlike '*\.worktrees\rookbim-gated-diagnostics') {
    throw "Task 10 must run from the dedicated implementation worktree"
}
git status --short --branch
if (git status --porcelain) { throw "Implementation worktree must be clean" }
git diff --check
git log --oneline --decorate -8
git -C C:\Users\aryan\source\repos\Rook status --short
rg -n "File\.AppendAllText|AsyncLocal|ThreadStatic|setx|Exception\.Message|Exception\.ToString" src/Rook/Bim/Diagnostics
rg -n "File\.AppendAllText|AsyncLocal|ThreadStatic|CurrentCorrelation" src/RookBim/Revit/RevitApiDispatcher.cs src/RookBim/Revit/RevitRookBimRuntime.cs src/RookBim/Revit/RevitIdentitySerializer.cs src/RookBim/Revit/RevitCategoryResolver.cs
rg -n "\.ActiveView|ActiveGraphicalView" src/RookBim/Revit/RevitRookBimRuntime.cs
```

Expected: the implementation worktree is clean; diagnostics contain no forbidden I/O/correlation/message patterns; Revit view code contains `ActiveGraphicalView` and no legacy accessor. The separate original checkout reports only its pre-existing two FFmpeg modifications.

- [ ] **Step 2: Run the complete managed matrix**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\Rook\Rook.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: exit 0. Record exact test counts and warnings.

- [ ] **Step 3: Confirm committed provenance**

```powershell
$implementationCommit = (git rev-parse HEAD).Trim()
git status --porcelain
Write-Output $implementationCommit
```

Expected: diagnostic implementation is committed and `git status --porcelain` emits nothing in the implementation worktree. Never deploy uncommitted diagnostic assemblies. The FFmpeg files remain visible only in the separately checked original workspace.

- [ ] **Step 4: Close host processes and deploy through the repository workflow**

After the user closes Revit, Rhino, and the Rook MCP process:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -Configuration Release
```

Expected: the prescribed workflow builds native `RookNative`, then managed `Rook`, then `RookBim`, and deploys the net48 module beside the companion. With no `-SkipChirpInstall`, it syncs/installs and verifies Chirp. With no `-LiveSmoke`, it must report that live Rhino/Grasshopper/Chirp smoke did not run.

Capture the workflow's final report and retain these bounded operator facts for handoff:

- implementation repository/worktree path;
- `InstallRoot`, `DataRoot`, `PluginDir`, `ChirpRoot`, and Python runtime path printed by the script;
- whether native, `Rook`, and `RookBim` builds ran and succeeded;
- whether Chirp installation/verification ran;
- whether `-LiveSmoke` ran (expected `false` for the command above).

- [ ] **Step 5: Launch Revit with exact process-scoped gating**

```powershell
$env:ROOK_BIM_DIAGNOSTICS = '1'
Start-Process 'C:\Program Files\Autodesk\Revit 2024\Revit.exe'
Remove-Item Env:ROOK_BIM_DIAGNOSTICS
```

Open Rhino.Inside in that process, then open original workshared `HOPA-GPA-STHE-AAAA-3D-ARCH-000000_eyad_kalaji.rvt`. Do not substitute Snowdon for acceptance.

- [ ] **Step 6: Discover the matching port and capture raw HTTP**

```powershell
$revitProcessId = (Get-Process Revit | Sort-Object StartTime -Descending | Select-Object -First 1).Id
$instance = Get-ChildItem "$env:LOCALAPPDATA\Rook\discovery\*.json" |
    ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json } |
    Where-Object { $_.processId -eq $revitProcessId -and $_.pluginType -eq 'native' } |
    Select-Object -First 1
if (-not $instance) { throw "No native Rook discovery record matched Revit PID $revitProcessId" }
$rookBaseUrl = "http://127.0.0.1:$($instance.port)"

curl.exe -sS -i "$rookBaseUrl/bim/status"
curl.exe -sS -i "$rookBaseUrl/bim/active-document"
curl.exe -sS -i "$rookBaseUrl/bim/categories"
curl.exe -sS -i -H "Content-Type: application/json" -d '{"scope":"active_view","limit":1}' "$rookBaseUrl/bim/query-elements"
```

Store captures only in a user-approved private support location; do not add them to Git.

- [ ] **Step 7: Exercise view-focus cases**

Repeat active-document and active-view captures with: graphical Revit view focused; Project Browser/auxiliary pane focused; Rhino focused; Grasshopper focused. Expect stable `ActiveGraphicalView` behavior and no legacy access.

- [ ] **Step 8: Correlate status, failures, and terminal summaries**

Read the current `%LOCALAPPDATA%\Rook\diagnostics\rookbim-*.jsonl`. For each HTTP correlation, sort by numeric sequence and verify:

- status `coreCommit` equals `$implementationCommit`; module commit matches the built optional module;
- at most one `handler.terminal` record per accepted request;
- `traceComplete=true` exactly when writer-time request drop count is zero;
- production failure gives exact stage/type/HResult and terminal gives last stage/outcome/index;
- no model title, `.rvt` path, category name, GUID, exception message, or multiline record appears;
- any loss has explicit sink/drop evidence.

- [ ] **Step 9: Apply the live acceptance decision**

Acceptance requires all four routes to correlate to a complete or explicitly incomplete trace and the original incident to identify a first failing/last observed boundary. Source tests alone cannot pass this step.

If a category property fails, record evidence but do not harden it here. Iterator creation/`MoveNext` remains loud. Identify exact document property/state failures. Use local serializer evidence only after wrapper entry. If the failure is before handler/type entry or in the outer envelope, report it outside the approved boundary.

- [ ] **Step 10: Hand off evidence without claiming the second fix**

Report: implementation commit, implementation worktree path, exact test/build counts, deploy result, installed `InstallRoot`/`DataRoot`/`PluginDir`/`ChirpRoot`/Python paths, which native/managed builds ran, whether Chirp installation ran, whether `-LiveSmoke` ran, status provenance/sink state, private capture location, correlation IDs, first failure, last stage/index, drop/completeness state, and live-gate result. State that category hardening and taxonomy cleanup remain separate future changes.

---

## Plan Self-Review Checklist

- [ ] Implementation starts from the corrected documentation-only descendant of `262d3691` in clean `codex/rookbim-gated-diagnostics`; original-workspace FFmpeg changes never enter it.
- [ ] Tasks 1-9 execute sequentially with per-task review gates; Task 10 remains inline/operator-assisted.
- [ ] Every approved stage/detail/outcome/kind has one type owner and encoder mapping.
- [ ] Every declared sink failure member has one exact wire value and exhaustive encoder coverage.
- [ ] Every enabled probe updates request state; per-item category success does not enqueue.
- [ ] Every failure is offered once; every accepted request offers exactly one terminal.
- [ ] FIFO terminal admission, release, and delayed drops have behavioral tests.
- [ ] Exact/read-once initialization precedes standalone status and module activation.
- [ ] Version/commit is unconditional in status and present in every persisted record.
- [ ] Every `ToWireData` route uses `SerializeForWire`; coverage claims begin after entry only.
- [ ] Runtime interface migration updates both exact RookBIM export assertions in Task 5 and passes before handler instrumentation begins.
- [ ] Static handler and loader diagnostic suites use `RookBimRuntimeRegistryCollection` isolation.
- [ ] Context is explicit through all runtime methods and actual queued work item; concurrency is tested.
- [ ] Production/auxiliary wrappers and disabled call-site fast paths are distinct/tested.
- [ ] Identity preserves both `IsWorkshared` reads/current catches; auxiliary state never feeds output.
- [ ] Category traversal preserves disposal/loud iterator failure and existing property degradation.
- [ ] Encoder has no STJ/arbitrary fields/messages and passes privacy/bounds tests.
- [ ] Revit-thread code performs no file I/O or blocking queue call.
- [ ] No native, taxonomy, hardening, FFmpeg, or generic logging change is included.
- [ ] Full tests/build pass and implementation is committed before deploy.
- [ ] Deploy uses `powershell -NoProfile` and reports installed paths, builds, Chirp installation, and `-LiveSmoke` status.
- [ ] Original workshared-model reproduction is the acceptance gate.
