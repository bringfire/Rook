# RookBIM Gated Diagnostic Tracing Design

**Date:** 2026-07-25
**Status:** Revised specification awaiting user approval
**Target:** `src/Rook` managed BIM boundary and optional `src/RookBim` Revit module

## Purpose

Add an opt-in diagnostic trace that can identify the exact failing layer and Revit API property in the original workshared-model incident. Once the instrumented handler boundary is running, the trace covers module discovery and activation, handler dispatch and DTO serialization, Rhino.Inside idling-queue dispatch, document identity serialization, and category enumeration. It must remain safe to deploy in a normal Rook build because it is disabled unless the Revit process starts with exactly `ROOK_BIM_DIAGNOSTICS=1`.

The diagnostic trace does not claim to fix the original incident. It gathers evidence for a later, independently reviewable fix.

## Scope and non-goals

This change will:

- initialize diagnostics before optional RookBIM module discovery;
- expose build provenance in `/bim/status` unconditionally;
- create an immutable per-request correlation context while diagnostics are enabled;
- propagate that context explicitly across the managed/Revit thread boundary;
- retain every probe observation in a request-scoped outcome accumulator while persisting only failures, coarse lifecycle milestones, and one terminal request summary;
- write fixed-schema, redacted JSONL through a bounded background sink;
- identify failures in document identity, view access, category iteration, individual category properties, and handler serialization;
- expose only bounded status and correlation evidence over HTTP.

This change will not:

- harden category iteration or change per-category degradation behavior;
- change the meaning of `not_rhino_inside` or otherwise revise the error taxonomy;
- swallow, translate, retry, or otherwise change operation exceptions;
- introduce Revit references into `src/Rook`;
- add a persistent flag file, runtime toggle, HTTP toggle, `setx` instruction, or automatic expiry mechanism;
- log request bodies, model titles, model paths, element identifiers, category names, GUID values, or exported geometry;
- use the diagnostic trace as evidence that the original incident is fixed.

## Change and commit boundaries

The active-view defect is already isolated in commit `feec425e` (`fix(rookbim): use active graphical view safely`). The diagnostic specification is a documentation commit. Diagnostic implementation will be a later, separate commit and will be committed before local deployment so assembly commit provenance names the code actually being tested. The unrelated FFmpeg worktree changes remain outside all three commits.

Category hardening and error-taxonomy cleanup remain later changes, each independently reviewable after live evidence identifies the failing stage.

## Architecture

### Shared core service

A new diagnostic service under `src/Rook/Bim` owns configuration, immutable contexts, request-scoped outcome accumulators, sequence assignment, sparse persistence policy, record bounding and redaction, the fixed-schema encoder, the bounded queue, the background writer, module metadata, and sink status. It contains no Autodesk or Rhino.Inside references.

The service exposes operations equivalent to:

- `InitializeFromEnvironment()` — idempotent, thread-safe, and read-once;
- `CreateContext(operation)` — returns either an immutable enabled context with a unique correlation ID and private request outcome accumulator, or a shared disabled context;
- `RegisterModuleMetadata(assembly)` — records the loaded optional module's version and source commit without creating or reconfiguring the sink;
- `Observe(BimDiagnosticContext context, BimDiagnosticStage stage, BimDiagnosticOutcome outcome, BimDiagnosticFields fields)` — accepts only closed diagnostic types, assigns a sequence, and updates the request outcome; it enqueues only when the observation is a failure or a coarse lifecycle milestone;
- `ObserveException(BimDiagnosticContext context, BimDiagnosticStage stage, Exception exception, BimDiagnosticFields fields)` — captures a bounded, redacted exception tree, updates the request outcome, and attempts to enqueue the failure without throwing;
- `CompleteRequest(BimDiagnosticContext context, BimDiagnosticOutcome routeOutcome)` — seals normal observations and enqueues one priority terminal envelope whose writer-time snapshot summarizes the request;
- `SnapshotStatus()` — returns enabled state, sink state, dropped count, and provenance.

All public service entry points are behavior-neutral: they catch their own internal failures, update in-memory sink state when possible, and never throw into BIM route handling.

### Initialization order

`BimHandler.Dispatch` calls `InitializeFromEnvironment()` before parsing or taking the current standalone-status early return, and therefore before `RookBimModuleLoader.TryActivate()`. `TryActivate()` also calls the idempotent initializer as a defensive invariant for future callers. This ordering allows standalone status serialization, module candidate resolution, module-not-found, assembly-load, reflected-activation, and activation-time failures to be recorded.

Initialization reads `ROOK_BIM_DIAGNOSTICS` exactly once for the process. Only an ordinal comparison with the exact value `1` enables diagnostics. Values such as `true`, `01`, `1 `, `TRUE`, empty, and missing all disable diagnostics. Later environment changes have no effect. Enabling therefore requires a Revit restart because Rhino and Rook inherit Revit's environment.

The supported launch mechanism is process-scoped, for example setting `$env:ROOK_BIM_DIAGNOSTICS='1'` in a launcher shell immediately before `Start-Process` for Revit. Documentation must not recommend `setx`.

`RookBimModule.Activate` calls `RegisterModuleMetadata` before checking Revit/Rhino.Inside assembly availability. Registration extracts the module assembly version and informational version/source revision. It does not create the sink and does not reread the environment.

### Provenance

The shared service captures core assembly version and commit during initialization. Optional RookBIM module version and commit initially have the literal value `unavailable` and are replaced atomically when module metadata is registered. Every JSONL record contains all four fields:

- `coreVersion`
- `coreCommit`
- `moduleVersion`
- `moduleCommit`

`/bim/status` exposes the same fields unconditionally. This makes module-not-found and module-load failures attributable without pretending an unavailable module has metadata.

Assembly informational versions are parsed as bounded strings. A commit is the suffix after `+` when it is a hexadecimal source revision; otherwise the commit is `unavailable`. The diagnostic implementation must be committed before deployment so this value identifies the tested source rather than an uncommitted working tree.

## Correlation and cross-thread propagation

`BimHandler` creates one immutable `BimDiagnosticContext` per accepted BIM operation after the operation discriminator is parsed and before optional module activation. The context contains only:

- diagnostics-enabled state;
- a unique correlation ID generated as a GUID in `D` format;
- the validated operation name;
- a reference to a private, request-scoped `BimDiagnosticOutcomeAccumulator` created with the context.

When diagnostics are disabled, no GUID is generated and the shared disabled context is used.

The context is passed explicitly through every `IRookBimRuntime` method. This is an intentional managed-boundary contract change. It avoids global mutable correlation state and does not depend on `AsyncLocal`, `ExecutionContext`, or delegate behavior.

`RevitRookBimRuntime` captures the immutable context in a local variable before calling `RevitApiDispatcher.InvokeAbandonable`. The queued work-item closure receives or closes over that specific context and passes it to every Revit-side probe. No current/global correlation property is read on the Revit thread. Concurrent requests therefore cannot overwrite or borrow another request's correlation ID.

Module loader calls also receive the same immutable context so activation events correlate with the triggering HTTP request. A later request that observes an already installed module receives its own context and records an activation outcome equivalent to `already_initialized` without rerunning module activation.

### Request outcome semantics

The outcome accumulator is the defined path from Revit-thread evidence back to the handler's bounded HTTP diagnostic. It is never placed in a global dictionary, registry, static current-context property, `AsyncLocal`, or thread-local slot. Its immutable context owns it for the request lifetime. A queued envelope may temporarily retain the same accumulator solely so the writer can account for a delayed drop and, for the terminal envelope, take a writer-time summary. An envelope releases that reference when it is written or dropped. The handler reads snapshots after runtime invocation and each serialization attempt.

The accumulator is thread-safe and records these summaries using diagnostic observation sequence numbers:

- `lastStage` and `lastOutcome` are from the highest-sequence request observation, whether successful or failed;
- `lastItemIndex` is from the highest-sequence observation whose closed fields contain an item index, so later non-item handler milestones do not erase the traversal position;
- `firstFailureStage`, `firstFailureExceptionType`, and `firstFailureHResult` are the lowest-sequence failure whose `failureImpact` is `production`.

`failureImpact=production` means the exception came from an existing production read or serialization step. It remains eligible for `firstFailure` even when an existing production catch intentionally degrades it, so a successful response may still identify a caught production-read failure. An auxiliary diagnostic probe has `failureImpact=auxiliary`; it can update `lastStage` but can never become `firstFailure`. Queue, encoder, and sink failures do not become production failures, but a drop associated with a queued request envelope increments that accumulator's `requestDroppedCount` and makes `traceComplete=false`.

If a Revit operation fails and its failure DTO serializes successfully, `firstFailureStage` identifies the Revit read while `lastStage` becomes `handler.serialize/success`. If runtime work succeeds but DTO serialization fails, both the first operation failure and last stage identify `handler.serialize`. If failure-detail serialization also fails after an earlier Revit failure, the Revit stage remains first and `handler.serialize/failure` is last. Updates compare sequence values rather than lock-acquisition order, so concurrent observations have deterministic semantics.

## Observation and persistence model

Every observation has a globally monotonic signed 64-bit `sequence` assigned with `Interlocked.Increment` and a UTC timestamp captured at the producer. These fields establish cross-thread ordering. A persisted failure or milestone retains the sequence and timestamp of its source observation. A terminal summary receives its own sequence and timestamp but does not overwrite the accumulator's `lastStage` fields.

Every probe observation with an enabled request context updates that request's accumulator. Persistence is deliberately sparse:

- every `failure` observation is offered to the sink as `recordKind=failure`;
- `start` and `success` observations are offered as `recordKind=milestone` only for `core.initialize`, `module.resolve`, `module.load`, `module.activate`, `module.metadata`, `handler.deserialize`, `handler.runtime`, `handler.serialize`, `revit.dispatch.enqueue`, `revit.dispatch.execute`, and `revit.document.acquire`;
- all other `start` and `success` observations, including every per-item category action and every document/view property probe, remain accumulator-only;
- every accepted request offers exactly one `recordKind=terminal` summary after its final response or fallback response has been constructed. Completion atomically rejects any later probe observations while still permitting delayed sink-drop accounting against the accumulator.

This means category traversal does not produce durable start/success traffic proportional to category count. A per-category failure is still offered immediately, and the terminal summary retains the request's first production failure, last observed stage/outcome/index, and known completeness state. The sink is bounded and behavior-neutral, so “persist every failure” means every failure is selected by this policy and offered once; an actual queue, encoding, or I/O loss is represented by drop and sink-state evidence rather than hidden.

Outcomes are closed to:

- `start`
- `success`
- `failure`

Persisted record kinds are closed to `milestone`, `failure`, and `terminal`.

Not-applicable and short-circuit cases use `success` with a closed `detailCode`, such as `not_workshared`, `already_initialized`, or `no_active_view`. They do not add an open-ended outcome.

There is no property bag. `Observe` and `ObserveException` accept a closed immutable `BimDiagnosticFields` value containing only:

- `BimDiagnosticDetailCode DetailCode`;
- `long? ItemIndex`;
- `BimDiagnosticFailureImpact FailureImpact`.

`BimDiagnosticDetailCode` is a validated closed vocabulary containing only the detail codes required by this design: `none`, `true`, `false`, `null`, `not_applicable`, `not_workshared`, `already_initialized`, `no_active_view`, `unsaved`, `file`, `server`, `cloud`, `detached`, `unknown`, `probe_failure`, `not_disposable`, `truncated`, `serialization_failure`, and `exception_capture_failed`. `BimDiagnosticFailureImpact` is closed to `none`, `production`, and `auxiliary`. Adding a field or value requires an explicit schema and test change.

Stages are closed to the following constants:

| Area | Stages |
| --- | --- |
| Core and loader | `core.initialize`, `module.resolve`, `module.load`, `module.activate`, `module.metadata` |
| Handler | `handler.deserialize`, `handler.runtime`, `handler.serialize`, `handler.terminal` |
| Revit dispatch | `revit.dispatch.enqueue`, `revit.dispatch.execute`, `revit.document.acquire` |
| View | `revit.view.active_graphical` |
| Document identity | `revit.document.central_is_workshared`, `revit.document.central_guid`, `revit.document.title`, `revit.document.path`, `revit.document.is_family`, `revit.document.output_is_workshared` |
| Document state | `revit.document.is_model_in_cloud`, `revit.document.is_detached`, `revit.document.central_model_path`, `revit.document.model_path_empty`, `revit.document.model_path_server`, `revit.document.model_path_cloud` |
| Category map | `revit.categories.settings`, `revit.categories.collection`, `revit.categories.iterator`, `revit.categories.move_next`, `revit.categories.current`, `revit.categories.iterator_dispose` |
| Category properties | `revit.category.id`, `revit.category.name`, `revit.category.built_in`, `revit.category.type` |
| Sink lifecycle | `sink.writer` |

Adding a stage later requires updating the fixed constants, encoder validation, and tests. Arbitrary stage strings are rejected as dropped records.

## Probe behavior

Revit-side probes are explicitly divided into two contracts:

- A **production-read probe** wraps exactly one API read that the route already performs. It observes `start`, invokes the read once, observes `success`, and returns the original value. On exception it observes `failure` with `failureImpact=production` and uses a bare `throw;`, preserving the same exception instance, stack, and production catch behavior.
- An **auxiliary diagnostic probe** performs a new classification read used only for diagnostics. It observes `start`, attempts the read, and observes `success`. On exception it observes `failure` with `detailCode=probe_failure` and `failureImpact=auxiliary`, returns an explicit unknown result, and continues the route. Its result never feeds a production DTO, branch, collector, export, or error decision.

Neither wrapper catches failures from the diagnostic service because the service is behavior-neutral and nonthrowing. The two contracts use distinct method names and tests forbid auxiliary state probes from using the production-read wrapper.

Disabled-mode call sites have explicit fast paths. A production read executes its original Revit expression directly when `context.Enabled` is false; it does not allocate or invoke a probe delegate. An auxiliary probe returns its explicit unknown result before constructing or invoking its Revit delegate. Tests use throwing/counting delegates and source-contract assertions to enforce both rules.

### Document identity and state

The detailed document-identity path records each existing property access separately and in source order:

1. the `IsWorkshared` read that guards central GUID access;
2. `WorksharingCentralGUID` when the first read is true;
3. `Title` without recording its value;
4. `PathName` without recording its value;
5. `IsFamilyDocument`;
6. the second `IsWorkshared` read used in the returned DTO.

This preserves the two independent `IsWorkshared` reads rather than caching one and inadvertently changing runtime behavior. The existing documented catches around central GUID access remain unchanged. An `InapplicableDataException` or `InvalidOperationException` is still handled as today; an unhandled `InternalException` still propagates as today, but the log names the exact stage.

The active-document diagnostic path also records these public Revit 2024 state reads independently as auxiliary diagnostic probes:

- `IsModelInCloud`;
- `IsDetached`;
- `GetWorksharingCentralModelPath()`;
- if a model path is returned, its `Empty`, `ServerPath`, and `CloudPath` flags.

Only booleans, null/presence, and a fixed classification (`unsaved`, `file`, `server`, `cloud`, `detached`, or `unknown`) may be recorded. `PathName`, `CentralServerPath`, cloud GUIDs, project GUIDs, model GUIDs, and user-visible paths are never placed in a diagnostic record. The state probes do not replace or feed production identity values. A throw from `GetWorksharingCentralModelPath()` or any other auxiliary state read is recorded as `probe_failure`, produces the classification `unknown`, and cannot fail or otherwise change the active-document route.

Detailed identity tracing is passed only at the top-level document identity call for the incident operations. Element-level identity serialization remains untraced to avoid generating repeated document records for every element.

### Category traversal

The current category-map behavior remains authoritative and unchanged, but the `foreach` is expanded mechanically so these actions are distinguishable:

1. `document.Settings` read;
2. `Settings.Categories` read;
3. iterator creation;
4. each `MoveNext` call, including the final false result;
5. each `Current` read;
6. each existing category property read: `Id`, `Name`, built-in category conversion, and `CategoryType`;
7. iterator disposal in a `finally` block.

The record for an item may contain only its zero-based iteration index. It never contains category name, category ID, built-in enum value, or parent data.

Existing safe property readers keep their existing catches and degradation decisions. The production-read probe immediately around the API read logs and rethrows; the existing safe reader may then catch the same exception. A category iterator creation or `MoveNext` failure remains loud and fails the operation. This diagnostic change must not silently return a partial category table.

Expanding `foreach` must preserve compiler-equivalent enumerator disposal. A small Revit-agnostic shared helper owns iterator creation, `MoveNext`, `Current`, visitor invocation, and disposal so its real control flow can be tested with fake `IEnumerable`/`IEnumerator` implementations in `Rook.Tests`. Its explicit enumerator is enclosed in `try/finally`; the `finally` checks whether it implements `IDisposable` and, if so, invokes `Dispose` through the production-read probe at `revit.categories.iterator_dispose`. A non-disposable iterator observes success with `detailCode=not_disposable`. Disposal runs after normal completion and when `MoveNext`, `Current`, or category processing throws. If `Dispose` itself throws, the failure propagates exactly as it would from the compiler-generated `foreach` disposal path. `RevitCategoryResolver` supplies the category visitor but does not own disposal.

### Handler serialization

Every `ToWireData` call is centralized behind one correlation-aware `SerializeForWire(context, value)` wrapper. `FromBimResponse`, `Ok`, and `Fail(details)` use that wrapper, including standalone `/bim/status`, successful runtime DTOs, and failure-detail DTOs. No code path calls `ToWireData` directly outside the wrapper.

`SerializeForWire` observes `handler.serialize/start` immediately before `ToWireData`, then observes success or failure. A failure is logged with the original correlation context, updates the request outcome as `failureImpact=production`, and is rethrown unchanged into the existing handler catch. The fallback HTTP error uses a dedicated minimal builder composed only of fixed primitive fields; it must not call `ToWireData`, `SerializeForWire`, or itself recursively for diagnostic metadata.

Diagnostics initialization occurs at the beginning of `BimHandler.Dispatch`, before body parsing and before the standalone-status early return. Once a valid operation is known, its context is passed through `DispatchStandaloneStatus`, `DispatchStatus`, `FromBimResponse`, `Ok`, `Fail`, and `SerializeForWire`. Pre-operation parse failures use an uncorrelated initialized context and still use the same wrapper if they contain serializable details.

Once `SerializeForWire` has been entered, its diagnostic failure path does not use `System.Text.Json`; an exception thrown by `ToWireData` after that entry point is therefore offered to the local sink through the dependency-free encoder. This guarantee begins only after `SerializeForWire` is running. Assembly binding/loading, JIT or type-initialization failures that prevent `BimHandler.Dispatch` or `SerializeForWire` from running, and serialization performed by the outer managed/native response envelope are outside this diagnostic boundary. Moving initialization above that bridge/type-loading boundary is not part of this incident investigation.

## JSONL schema and dependency-free encoding

The local trace is UTF-8 JSON Lines with one fixed-schema object per line. Diagnostic records and exception trees are never passed to `System.Text.Json`, `JsonSerializer`, `JsonNode`, reflection-based serialization, or arbitrary-object serialization.

The fixed record fields, emitted in a fixed order, are:

```text
schemaVersion, recordKind, sequence, timestampUtc, processId, threadId,
correlationId, operation, stage, outcome, detailCode, itemIndex, failureImpact,
lastStage, lastOutcome, lastItemIndex,
firstFailureStage, firstFailureExceptionType, firstFailureHResult,
requestDroppedCount, traceComplete,
coreVersion, coreCommit, moduleVersion, moduleCommit,
exceptionType, exceptionHResult, exceptionStack,
innerExceptions, truncated
```

Absent optional strings and indexes are encoded as `null`. `schemaVersion` is `1`. Record kind, stage, outcome, detail code, and failure impact are encoded from their closed typed vocabularies. Milestone and failure records leave terminal-summary fields null except for their then-current `requestDroppedCount`/`traceComplete`; terminal records contain the final writer-time summary and no exception tree of their own. No dictionary, anonymous object, arbitrary property bag, or caller-selected field name is accepted.

A dedicated encoder appends this schema to a `StringBuilder`. Its string escaper handles quotes, backslashes, `\b`, `\f`, `\n`, `\r`, `\t`, every U+0000–U+001F control character as `\u00XX`, and unpaired UTF-16 surrogates as the replacement character. Tests parse every encoded line with an independent JSON parser, but the production encoder has no JSON dependency.

The bounded HTTP diagnostic remains part of the existing `ApiResponse.Diagnostic` transport shape. It is built directly from fixed primitive fields and never passed through `ToWireData`. The existing HTTP transport may encode that already-materialized primitive object as part of the normal response envelope; no local diagnostic record or exception uses that path. This HTTP diagnostic is best-effort. Failures in assembly binding/loading, handler type initialization, or outer-envelope serialization can occur before or after the instrumented boundary and are explicitly not covered by the local-trace guarantee.

## Redaction and exception capture

Production property values that can identify a model are omitted at the probe site. Exception messages are arbitrary application text and are never persisted, hashed, queued, or exposed over HTTP. The diagnostic service does not read `Exception.Message` or call `Exception.ToString()`. Persisted exception evidence is limited to bounded type name, signed HResult, redacted stack, and bounded inner-exception structure.

Redaction replaces:

- Windows drive, UNC, and URI-like paths with `[path:redacted]`;
- GUID forms with `[guid:redacted]`;
- CR, LF, and other control characters through JSON escaping so one event cannot create extra JSONL lines.

Stack traces retain method names and line numbers when present, but source file paths and GUID forms are redacted. Model titles, model paths, category names, request values, and exception messages never enter the persisted record model, so privacy does not depend on recognizing them with patterns.

Exception capture is iterative and records the root plus at most four nested levels. An `AggregateException` contributes at most eight inner exceptions total across the tree. Additional inner exceptions set `truncated=true`. Each exception stores only bounded type name, signed HResult, redacted bounded stack, and its bounded children. Capturing or redacting a hostile exception object is itself behavior-neutral and degrades to the closed `exception_capture_failed` detail code.

## Nonblocking sparse sink and explicit limits

When enabled, initialization creates one process-session sink. Revit and handler threads only update bounded accumulators, construct the sparse envelopes selected by the persistence policy, and call a zero-timeout enqueue operation. They never open, create, write, flush, rotate, or close files.

The sink uses one bounded FIFO concurrent queue and one background writer thread. There is no normal/failure lane split, priority drain scheduler, or separate file-space budget. The sparse producer policy—not downstream scheduling—prevents ordinary category traversal from flooding the queue.

Each queued envelope contains its immutable observation data plus a temporary reference to its request outcome accumulator when one exists. This is not a global correlation dictionary. An immediate enqueue rejection or a later encode/write failure increments both the global dropped count and that request's saturating `requestDroppedCount`. The reference is released after write or drop.

The writer creates `%LOCALAPPDATA%\Rook\diagnostics` and opens one file named `rookbim-<UTC-start>-<process-id>.jsonl`. It writes with UTF-8 without a byte-order mark and flushes on the writer thread. It does not rotate to another file after reaching the session limit.

Failure and milestone envelopes use one zero-timeout enqueue attempt. A terminal envelope has priority admission without a second queue: if its first enqueue finds the queue full, the queue performs one atomic, nonblocking conditional removal of the oldest envelope only when that envelope is a milestone or failure, accounts the eviction against the evicted envelope's request, and retries the terminal enqueue once. A terminal never evicts another terminal. The terminal record uses `stage=handler.terminal`, its `outcome` is the final route outcome (`success` or `failure`), and it is materialized from its accumulator on the writer thread after preceding FIFO entries have been processed, so it includes all request drops known at that point. If a queue full of terminals or concurrent contention defeats admission, or the terminal record itself cannot be encoded or written, the loss is still reflected in in-memory global/request drop state but cannot be guaranteed to appear in that file. The local trace is therefore intentionally best-effort rather than an observability subsystem with delivery guarantees.

Limits are constants and are covered by tests:

| Limit | Value |
| --- | ---: |
| Total queue capacity | 1,024 envelopes |
| Encoded record, including newline | 16 KiB UTF-8 |
| Session log file | 16 MiB |
| Exception nesting depth | 4 |
| Aggregate inner exceptions | 8 total |
| Exception stack | 8,192 characters before final byte bounding |
| Operation, stage, outcome, detail code | 128 characters each, with stage/outcome additionally vocabulary-validated |

If a record exceeds 16 KiB, the optional stack and inner-exception structure are shortened deterministically and `truncated=true`. If the minimal fixed record cannot fit, it is dropped. Queue-full, priority-eviction, record-invalid, record-oversize, total-file-limit, directory/open/write/flush failure, and encoder failure each increment the global saturating `droppedCount`, increment the owning request's `requestDroppedCount` when present, and update `sinkState` without throwing.

Global and request dropped counts saturate at `long.MaxValue`. `traceComplete` is true only while that request's dropped count is zero; it is a statement about known diagnostic loss, not proof that code outside the instrumented boundary ran. `sinkState` is one of `disabled`, `starting`, `ready`, `degraded`, `file_limit_reached`, `failed`, or `stopped`. The first sink failure is retained as a bounded, closed `sinkFailureCode`; no exception text or path is exposed through status. Because a failed sink cannot reliably record itself, `sinkState`, global `droppedCount`, and `sinkFailureCode` are held in memory and exposed by `/bim/status` and bounded HTTP diagnostics while enabled. Request drop state lives only in the request accumulator and temporarily retained queued envelopes.

On process exit, the service signals completion and gives the background writer at most 250 ms to drain. It never blocks a BIM request waiting for drain or flush.

## HTTP contract

`/bim/status` always adds these bounded fields:

- `coreVersion`
- `coreCommit`
- `moduleVersion`
- `moduleCommit`
- `diagnosticsEnabled`
- `sinkState`
- `droppedCount`
- `sinkFailureCode`

Normal route `data` payloads are unchanged. While diagnostics are enabled, the existing HTTP diagnostic envelope may additionally contain:

- `correlationId`
- `lastStage`
- `lastOutcome`
- `lastItemIndex`
- `firstFailureStage`
- `firstFailureExceptionType`
- `firstFailureHResult`
- `requestDroppedCount`
- `traceComplete`
- `sinkState`
- `droppedCount`

These fields are fixed primitives with bounded strings. They are absent when diagnostics are disabled, except for the unconditional status fields above. Full messages, stack traces, paths, GUIDs, inner exceptions, and module-loading candidate paths never appear in HTTP diagnostics.

The handler reads these values from the request's outcome accumulator after runtime invocation and after each serialization attempt. Auxiliary probe failures never populate the `firstFailure*` fields. `requestDroppedCount` and `traceComplete` are the best-known snapshot when the HTTP diagnostic is built and may change later if the background writer drops an envelope. The terminal envelope takes a later writer-time snapshot after preceding FIFO work. If `ToWireData` throws after `SerializeForWire` has been entered, the handler preserves its existing `internal_error` behavior and adds the bounded correlation, `handler.serialize` first failure, last-stage evidence, and request drop state without calling `ToWireData` again for those fields. This does not cover failures that prevent `BimHandler`/`SerializeForWire` from running or failures in the outer response-envelope serializer.

## Error and behavior invariants

- Environment parsing, logging, encoding, queueing, and writer failures never alter a route's success/failure decision, HTTP status, error code, retry behavior, or exception type.
- Production-read probes rethrow the same exception instance with a bare `throw;`; auxiliary probes catch locally, record `probe_failure`, return unknown, and never affect production behavior.
- Disabled production reads execute the original expression directly; disabled auxiliary probes return unknown without invoking their delegate.
- The Revit thread performs no filesystem I/O and no blocking queue operation.
- Diagnostics do not catch category iterator failures or convert them into partial success.
- Explicit category enumeration disposes the enumerator in `finally`, including after `MoveNext` or `Current` throws.
- Existing central-GUID catches remain unchanged.
- Diagnostics do not revise the `not_rhino_inside` taxonomy.
- Disabled diagnostics add only status provenance and have no per-stage allocation, correlation GUID generation, writer thread, directory creation, or file access.

## Testing strategy

Tests are split along the existing assembly boundary.

### Core behavioral tests in `Rook.Tests`

- exact `ROOK_BIM_DIAGNOSTICS=1` gating and rejection of every near-match;
- process read-once behavior even when the environment changes later;
- disabled mode creates no correlation ID, queue, thread, directory, or file;
- module resolution/not-found/load/activation failures are recorded before module activation;
- module metadata registration does not create or reconfigure the sink;
- two or more concurrent handler requests retain distinct correlation contexts through fake runtime work and serialization;
- request outcome accumulators select the lowest-sequence production failure and highest-sequence last stage while ignoring auxiliary failures for `firstFailure`;
- every probe updates its request accumulator, while per-item start/success observations enqueue no JSONL record;
- every failure and only the closed coarse start/success milestone set is offered to the sink, and each accepted request offers exactly one terminal summary;
- request accumulators track immediate queue drops, priority evictions, and delayed writer drops without a global correlation map;
- terminal priority admission uses the single-queue one-eviction rule, reports the writer-time first-failure/last-stage/index/drop snapshot, and releases all envelope-held accumulator references after write or drop;
- the shared enumeration helper disposes after normal completion and after fake `MoveNext`, `Current`, or visitor failures, while preserving a disposal exception;
- fixed-schema encoder produces valid single-line JSONL with correct escaping;
- encoder has no `System.Text.Json` dependency and accepts only `BimDiagnosticFields`, closed vocabularies, and the fixed exception shape—not arbitrary objects, dictionaries, or caller-selected field names;
- single-queue capacity, zero-timeout drop behavior, record size, file size, exception depth, aggregate count, string limits, and saturating drop counter;
- sink open/write/flush failures update `sinkState`, `droppedCount`, and failure code without changing handler behavior;
- every `ToWireData` entry point (`FromBimResponse`, `Ok`, and `Fail(details)`) uses the correlation-aware wrapper;
- standalone status initializes diagnostics before its early return and records serialization;
- a `ToWireData` exception thrown after `SerializeForWire` entry produces a local `handler.serialize/failure` record and a best-effort bounded HTTP diagnostic without recursively calling `ToWireData`;
- tests and documentation make no coverage claim for STJ assembly-binding, pre-entry JIT/type-initialization, or outer-envelope serialization failures;
- `/bim/status` always contains provenance and sink state while normal route data remains unchanged;
- correlation fields are absent from HTTP diagnostics when disabled.

Privacy fixtures explicitly include:

- exception messages containing a model title with and without `.rvt` and a category name;
- drive-letter and UNC `.rvt` paths;
- file, server, and cloud-looking URIs;
- brace, hyphenated, and compact GUID forms;
- CR/LF and every JSON control character;
- a stack trace containing a user source path and a model path;
- nested and aggregate exceptions beyond both limits.

Tests assert that `Exception.Message` and `Exception.ToString()` are never read, forbidden message/path/GUID literals do not occur in encoded output, every physical line parses as exactly one JSON object, and required type/HResult/redacted-stack evidence remains.

### Revit wiring tests in `RookBim.Tests`

The existing RookBIM tests are source-contract tests because the test assembly does not load a live Revit host. They will assert:

- explicit diagnostic-context parameters at the runtime boundary;
- context capture before `InvokeAbandonable` and use inside the queued closure;
- no `AsyncLocal`, thread-static, or global current-correlation access;
- module metadata registration during `RookBimModule.Activate` without environment reads;
- the two `IsWorkshared` reads and central GUID access have distinct stages;
- `Title`, `PathName`, `IsFamilyDocument`, model-state, and view reads have distinct stages;
- category settings, collection, iterator creation, `MoveNext`, `Current`, and each property are distinct probes;
- category traversal delegates iterator ownership to the tested shared enumeration helper and does not add a second disposal path;
- production-read probe failure uses a bare rethrow and current production catches remain present;
- auxiliary model-state probes catch locally, record `probe_failure`, return unknown, and cannot feed production results;
- disabled production reads bypass probe-delegate construction while disabled auxiliary probes return before delegate invocation;
- no Revit-thread file API calls;
- no silent catch around iterator creation or `MoveNext`.

### Live reproduction acceptance

After tests and builds pass, commit the diagnostic implementation, run the repository's `scripts\deploy-local-testing.ps1`, and launch Revit 2024 from a process-scoped PowerShell environment with `ROOK_BIM_DIAGNOSTICS=1`. A Revit restart is mandatory.

Reproduce in the original workshared `HOPA-GPA-STHE-AAAA-3D-ARCH-000000_eyad_kalaji.rvt` model, not the Snowdon sample. Capture:

- the complete raw HTTP response for status, active document, list categories, and active-view query;
- `/bim/status` provenance and sink status;
- the correlation IDs returned while diagnostics are enabled;
- the matching JSONL records sorted by sequence;
- focus cases for a graphical Revit view, Project Browser/auxiliary focus, Rhino focus, and Grasshopper focus.

The diagnostic pass is accepted when each raw response that reaches the instrumented handler boundary correlates to a complete or explicitly incomplete trace, the deployed commit matches status and records, and the trace identifies the last successful and first failing stage without exposing a model path, title, GUID, category name, or multiline record.

## Evidence-driven follow-up

The second fix is selected only from live evidence:

- If one category property fails and the iterator remains valid, extend that property's existing degradation behavior without weakening other properties.
- If iterator creation or `MoveNext` fails, keep the operation loud and return an explicit failure; do not return an incomplete category table as success.
- If a document-identity property fails, handle only the documented state-specific exception when the desired contract permits degradation.
- If handler serialization fails, fix the DTO/wire boundary independently of Revit category or identity behavior.
- If the failure is a host/dispatch classification error, address the broader taxonomy in its own change.

No follow-up category, identity, serialization, or taxonomy change is part of this diagnostic implementation.
