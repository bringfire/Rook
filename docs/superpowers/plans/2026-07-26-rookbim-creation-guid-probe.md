# RookBIM CreationGUID Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a diagnostics-gated, privacy-safe Revit 2024 probe that determines whether `Document.CreationGUID` can participate in the proposed versioned document identity keys, without changing production identity or matching behavior.

**Architecture:** A small managed-only probe operation uses the existing `BimHandler`/`IRookBimRuntime`/Revit-idling context, but is callable only through explicit operator invocation and only when the read-once `ROOK_BIM_DIAGNOSTICS=1` gate is active. Revit-specific collection remains in `src/RookBim`; one process-local report session owned by the installed runtime spans the operator's capture requests, keeps raw GUID/path equality inputs only in memory, and returns report-local aliases. The live matrix produces a durable redacted report and a proposed spec decision, then stops for reviewer approval before any production resolver, key, wire, or matching change.

**Tech Stack:** C# `net48` RookBIM module with Autodesk Revit 2024 API, multi-target core `Rook` contracts, existing request-correlated BIM diagnostics, xUnit 2.9.2, source-contract tests for the optional module, Rhino `rhino_execute` Python for operator-only managed dispatch, and Windows PowerShell for deployment.

**Execution model:** Execute Tasks 1-3 sequentially in a dedicated worktree. Task 4 is an inline operator-assisted Revit matrix. Task 5 records only the probe report and proposed decision, then stops for review. No task in this plan may implement `documentKey`, modify `DocumentMatches`, add a production identity resolver, or deploy a production identity policy.

Before Task 1, use `superpowers:using-git-worktrees` and create a separate probe branch from the reviewed two-plan documentation commit:

```powershell
Set-Location 'C:\Users\aryan\source\repos\Rook'
$specBaseline = '761a42af1d5c083dd69ee0908531c7d36a7b9995'
$ghPlan = 'docs/superpowers/plans/2026-07-26-rir-grasshopper-document-lifecycle.md'
$bimPlan = 'docs/superpowers/plans/2026-07-26-rookbim-creation-guid-probe.md'
$planCommit = (git log -1 --format=%H -- $bimPlan).Trim()

if ((git rev-parse "$planCommit^").Trim() -ne $specBaseline) {
    throw 'Reviewed plan commit does not directly follow 761a42af'
}
$changed = @(git diff-tree --no-commit-id --name-only -r $planCommit)
$expected = @($bimPlan, $ghPlan) | Sort-Object
if ((Compare-Object ($changed | Sort-Object) $expected)) {
    throw 'Reviewed plan commit changed files outside the two implementation plans'
}

git worktree add .worktrees/rookbim-creation-guid-probe -b codex/rookbim-creation-guid-probe $planCommit
if (git -C .worktrees/rookbim-creation-guid-probe status --porcelain) {
    throw 'RookBIM probe worktree is not clean'
}
```

The Grasshopper implementation plan being present in the same documentation commit creates no runtime dependency. This branch must contain no Grasshopper lifecycle implementation commits.

The two pre-existing FFmpeg modifications remain only in the original checkout. They must not appear in this worktree or any task commit.

## Global Constraints

- Treat `docs/superpowers/specs/2026-07-26-rookbim-file-workshared-identity-design.md` as authoritative; this plan executes only its CreationGUID decision gate.
- Initialize diagnostics through the existing read-once bootstrap. Enable only for exact `ROOK_BIM_DIAGNOSTICS=1`; require a Revit restart and use a process-scoped launcher environment, never `setx`.
- When diagnostics are disabled, reject the probe before invoking `IRookBimRuntime` or constructing any Revit delegate.
- Keep all Autodesk/Revit references and every live `Document`/`ModelPath`/`BasicFileInfo` object in `src/RookBim` and inside one Revit API operation.
- Read every Revit property independently. A diagnostic-only read failure records a closed `failure` outcome with exception type/HResult, classifies the value unknown, and continues.
- Probe failures never change an existing production route's status, payload, exception handling, or identity choice.
- Retain raw `CreationGUID`, `PathName`, converted ModelPath, and alias dictionaries only in the active in-memory probe session. Never persist, log, return, hash deterministically, or place them in diagnostics.
- Persist/return only report-local aliases such as `creation-001` and `path-001`; equal raw values in one report reuse an alias. Destroy all alias-to-value state on successful completion or abort.
- Never read or record document title, model/family filename, category/element name, request identity, or arbitrary exception message.
- A completion request with missing required cases fails without clearing the session; explicit abort always clears it.
- The probe operation is managed-only and operator-invoked. Do not add a public native `/bim/*` route or MCP tool for it.
- Do not add `DocumentKey`, `DocumentKeySource`, a key hash, a production canonicalizer call, a resolver, comparison logic, or a `RevitIdentitySerializer` branch.
- Do not change `WorksharingCentralGUID`, cloud/server classification, `DocumentMatches`, selection, export, or current producer behavior in this plan.
- Build `src/Rook/Rook.csproj` before `src/RookBim/RookBim.csproj`.
- Commit the probe build before deployment so `/bim/status` and the report identify exact provenance.
- Live Revit evidence is mandatory. Unit/source tests cannot choose the production key strategy.

---

## File Map

New core files without Revit references:

- `src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbeContracts.cs`: closed action/case/class/stage/read-status DTOs and privacy-safe public result shapes.
- `src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbePathCanonicalizer.cs`: probe-only Windows path canonicalization used solely to assign equality aliases.
- `src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbeSession.cs`: one-report alias tables, required-case tracking, fixed equality relations, completion/abort clearing, and safe snapshots.

New core tests:

- `src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbeSessionTests.cs`
- `src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbePrivacyTests.cs`
- `src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbePathCanonicalizerTests.cs`

Managed integration files:

- `src/Rook/Rook.csproj`: add `InternalsVisibleTo` for `RookBim` so the optional module can feed raw in-memory observations to the internal session without making them public DTOs.
- `src/Rook/Bim/IRookBimRuntime.cs`
- `src/Rook/Bim/RookBimUnavailableRuntime.cs`
- `src/Rook/Handlers/BimHandler.cs`
- every core test fake implementing `IRookBimRuntime` in `ManagedCapabilityDomainStatusTests.cs`, `BimHandlerDiagnosticsTests.cs`, `BimHandlerTests.cs`, and `CompanionRuntimeStatusTests.cs`.
- `src/RookBim/Revit/RevitCreationGuidProbe.cs`: independent Revit reads, class derivation, raw-to-alias handoff, one active session, and provenance.
- `src/RookBim/Revit/RevitRookBimRuntime.cs`
- `src/RookBim.Tests/RookBimModuleSourceTests.cs`
- `src/Rook.Tests/Handlers/BimCreationGuidProbeHandlerTests.cs`

Created after the live run:

- `docs/superpowers/probes/2026-07-26-rookbim-creation-guid-result.md`

Modified after the live run:

- `docs/superpowers/specs/2026-07-26-rookbim-file-workshared-identity-design.md`: add report link, observed matrix, and a clearly labeled proposed decision awaiting reviewer approval.

Explicitly unchanged:

- `src/RookBim/Revit/RevitIdentitySerializer.cs`
- `src/Rook/Bim/BimContracts.cs` identity DTOs and error enum
- `src/RookNative/**`
- `mcp_server/**`
- public `/bim/*` route list
- production identity, selection, and export behavior

---

### Task 1: Privacy-safe probe contracts, canonical equality, and session lifecycle

**Files:**
- Create: `src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbeContracts.cs`
- Create: `src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbePathCanonicalizer.cs`
- Create: `src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbeSession.cs`
- Modify: `src/Rook/Rook.csproj`
- Create: `src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbeSessionTests.cs`
- Create: `src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbePrivacyTests.cs`
- Create: `src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbePathCanonicalizerTests.cs`

**Interfaces:**
- Produces public request/safe-result DTOs used by Task 2's handler/runtime method.
- Produces internal `BimCreationGuidProbeObservation` and `BimCreationGuidProbeSession`, visible to `RookBim` only through `InternalsVisibleTo`.
- Produces internal `BimCreationGuidProbePathCanonicalizer.TryCanonicalize(string, out string)` for equality aliasing only.
- No production code calls these types in Task 1.

- [ ] **Step 1: Write failing session and required-case tests**

Define these exact cases in a closed enum and test that successful completion requires one capture for each:

```text
SavedProjectInitial
SavedProjectReopen
FileCentral
FileLocal
FileLocalReopen
CopiedCentral
Detached
SavedFamily
UnsavedProject
UnsavedFamily
ReplacementSamePath
```

Start a session with fixed provenance, add observations containing raw fixture values, and assert equal values reuse aliases while unequal values do not:

```csharp
Assert.Equal("creation-001", initial.CreationGuidAlias);
Assert.Equal("creation-001", reopened.CreationGuidAlias);
Assert.Equal("path-001", initial.DocumentPathAlias);
Assert.Equal("path-001", replacement.DocumentPathAlias);
Assert.NotEqual(initial.CreationGuidAlias, replacement.CreationGuidAlias);
```

Assert duplicate case capture is rejected with a closed code, completion with missing cases returns the exact missing-case list and leaves the session active, successful completion seals and clears raw maps, abort clears them, and no capture is accepted after complete/abort.

- [ ] **Step 2: Write failing privacy and equality-relation tests**

Use raw fixtures including a bare model title, `.rvt`/`.rfa` paths, UNC paths, GUIDs, newlines, and exception messages. Serialize only the public result with the same `System.Text.Json` naming/enum options as `BimHandler` and assert none appear. Reflect public DTO fields/properties and reject `Guid`, `Exception`, arbitrary `object`, `Raw*`, `PathValue`, `Title`, `FileName`, or message-bearing members.

The completed result must include fixed explicit relations for:

```text
saved_project_initial ↔ saved_project_reopen
file_central ↔ file_local
file_local ↔ file_local_reopen
file_central ↔ copied_central
saved_project_initial ↔ replacement_same_path
```

Each relation carries nullable booleans for same creation GUID, same document path, and same central path, plus a closed `unavailable` marker when either side lacks evidence. Callers cannot request arbitrary comparisons.

- [ ] **Step 3: Write failing canonicalization golden tests**

Pin the approved byte contract for equality inputs:

```csharp
[Theory]
[InlineData(@"C:\", @"C:\", "433a5c")]
[InlineData(@"c:/Models/../A.rvt", @"C:\A.RVT", "433a5c412e525654")]
[InlineData(@"\\server\share", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
[InlineData(@"\\server\share\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
[InlineData(@"\\server\share\folder\..\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
```

Also reject empty/whitespace, embedded NUL, relative, root-relative, drive-relative, URI, incomplete UNC, and `\\?\`, `\\.\`, `\??\` device/namespace inputs. The helper returns canonical text only to the in-memory alias table and never hashes it.

- [ ] **Step 4: Verify the new tests are red**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimCreationGuidProbeSessionTests|FullyQualifiedName~BimCreationGuidProbePrivacyTests|FullyQualifiedName~BimCreationGuidProbePathCanonicalizerTests" --verbosity minimal
```

Expected: compile failures on the missing probe contracts/session/canonicalizer.

- [ ] **Step 5: Implement closed request, observation, and safe result types**

Use exact request fields and enum wire values:

```csharp
public sealed class BimCreationGuidProbeRequest
{
    public BimCreationGuidProbeAction Action { get; set; }
    public BimCreationGuidProbeCase? CaseId { get; set; }
}

public enum BimCreationGuidProbeAction { Begin, Capture, Complete, Abort }
public enum BimCreationGuidProbeReadStatus { NotAttempted, Success, Failure, NotApplicable }
```

`BimCreationGuidProbeCapture` exposes only case, derived document class, per-property read status, nonempty/stability booleans, `creation-NNN`/`path-NNN` aliases, worksharing/detached/cloud/family booleans when readable, central/local flags when readable, ModelPath kind, and bounded failure facts `(stage, exceptionType, hresult)`. `BimCreationGuidProbeReport` exposes session ID, start/end UTC, PID, Revit/Rhino/RiR/core/module provenance, captures, fixed equality relations, missing cases, and `complete`.

`BimCreationGuidProbeStage` contains exactly `IsWorkshared`, `IsDetached`, `IsModelInCloud`, `IsFamilyDocument`, `CreationGuidFirst`, `CreationGuidSecond`, `DocumentPath`, `CentralModelPath`, `ModelPathServer`, `ModelPathCloud`, `ModelPathConvert`, `DocumentPathCanonicalize`, `CentralPathCanonicalize`, `BasicFileInfoExtract`, `BasicFileInfoIsCentral`, and `BasicFileInfoIsLocal`. Add exhaustive stage/status/action/case/class-to-wire tests; undefined enum values must throw instead of falling through to `ToString()`.

`BimCreationGuidProbeObservation` is internal and may contain raw `Guid?`/canonical path strings. No public result or diagnostic record may reference it.

- [ ] **Step 6: Implement canonicalization and one-report alias ownership**

Implement the seven-step canonicalizer verbatim from the identity spec, including UNC share-root removal and `ToUpperInvariant()`. Use `Encoding.UTF8.GetBytes(canonical)` only in tests to pin bytes; do not compute a path/GUID digest.

The session owns `Dictionary<Guid,string>` and `Dictionary<string,string>` with ordinal canonical-path comparison. Assign aliases monotonically with three-digit suffixes. `Complete()` builds the safe immutable result, then clears both dictionaries and all raw observations in `finally`; `Abort()` clears immediately. Add an internal test-only raw-entry count and never expose it through a public DTO.

- [ ] **Step 7: Run focused/full tests and commit the unused core**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimCreationGuidProbeSessionTests|FullyQualifiedName~BimCreationGuidProbePrivacyTests|FullyQualifiedName~BimCreationGuidProbePathCanonicalizerTests" --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
git add -- src/Rook/Rook.csproj src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbeContracts.cs src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbePathCanonicalizer.cs src/Rook/Bim/CreationGuidProbe/BimCreationGuidProbeSession.cs src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbeSessionTests.cs src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbePrivacyTests.cs src/Rook.Tests/Bim/CreationGuidProbe/BimCreationGuidProbePathCanonicalizerTests.cs
git commit -m "feat(rookbim): add privacy-safe CreationGUID probe session"
```

Do not deploy this unused preparatory commit.

---

### Task 2: Diagnostics-gated managed dispatch and Revit property collector

**Files:**
- Modify: `src/Rook/Bim/IRookBimRuntime.cs`
- Modify: `src/Rook/Bim/RookBimUnavailableRuntime.cs`
- Modify: `src/Rook/Handlers/BimHandler.cs`
- Modify: `src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs`
- Modify: `src/Rook.Tests/Handlers/BimHandlerDiagnosticsTests.cs`
- Modify: `src/Rook.Tests/Handlers/BimHandlerTests.cs`
- Modify: `src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs`
- Create: `src/Rook.Tests/Handlers/BimCreationGuidProbeHandlerTests.cs`
- Create: `src/RookBim/Revit/RevitCreationGuidProbe.cs`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`
- Modify: `src/RookBim.Tests/RookBimModuleSourceTests.cs`

**Interfaces:**
- Adds `BimApiResponse CreationGuidProbe(BimDiagnosticContext diagnostics, BimCreationGuidProbeRequest request)` to `IRookBimRuntime` and every implementation/fake.
- Adds managed dispatch op `creation_guid_probe`; no native handler, HTTP route, or MCP tool is added.
- `RevitCreationGuidProbe.Execute(UIApplication, Document?, BimDiagnosticContext, BimCreationGuidProbeRequest)` owns one in-memory session per installed runtime instance.
- Produces only Task 1 safe DTOs across the optional-module boundary.

- [ ] **Step 1: Write the disabled-gate and dispatch integration tests first**

Install a recording fake runtime and call `BimHandler.Dispatch` with:

```json
{"op":"creation_guid_probe","action":"begin"}
```

With a disabled diagnostic session, assert HTTP-equivalent failure uses `CapabilityUnavailable`, the runtime call count remains zero, and no Revit delegate can be constructed. With an enabled test session, assert the request reaches the runtime once, action/case enums bind from exact snake-case values, the safe result passes through `SerializeForWire`, and `CompleteRequest` still occurs exactly once on success/failure.

Place handler tests in the existing `RookBimRuntimeRegistryCollection` so registry/session replacement cannot race other BIM handler suites.

Add a source assertion that `RookServer.cpp` and `GrasshopperProxyHandler.cpp/.h` contain no creation-guid route/op string.

- [ ] **Step 2: Write the optional-module source contract before implementation**

Require `RevitCreationGuidProbe.cs` to read these stages independently through a local wrapper and to contain no title access:

```text
IsWorkshared
IsDetached
IsModelInCloud
IsFamilyDocument
CreationGUID first read
CreationGUID second read
PathName
GetWorksharingCentralModelPath
ModelPath.ServerPath
ModelPath.CloudPath
ModelPathUtils.ConvertModelPathToUserVisiblePath
BasicFileInfo.Extract
BasicFileInfo.IsCentral
BasicFileInfo.IsLocal
```

The source test must assert each delegate is a separate call, every diagnostic-only exception is caught inside the probe wrapper, and no exception object/message/raw value is assigned to a public result. Require `BasicFileInfo` disposal in `finally`/`using` even when a property read fails.

- [ ] **Step 3: Run handler/source tests red**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~BimCreationGuidProbeHandlerTests --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~CreationGuidProbe --verbosity minimal
```

Expected: the first fails on the missing runtime operation; the second fails its source assertions.

- [ ] **Step 4: Add the managed-only operation with an exact disabled fast path**

Add `creation_guid_probe` to `BimHandler.ExpectedBimOps` and dispatch it through `DeserializeRequest<BimCreationGuidProbeRequest>`. Before reading `RookBimRuntimeRegistry.Current` for this branch, require `diagnostics.Enabled`; otherwise return a bounded capability-unavailable response. The disabled branch must not call the runtime, allocate an observation, or create a delegate.

Add the runtime method to the interface/unavailable implementation and all four test fake files in the file map. The unavailable implementation returns its existing unavailable response. Do not add an overload or compatibility default that bypasses diagnostics.

- [ ] **Step 5: Implement independent Revit reads and safe class derivation**

In `RevitCreationGuidProbe`, use a closed `ProbeValue<T>` that contains success/status/value for internal use and only exception type/HResult for safe projection. Its wrapper is diagnostic-only:

```csharp
private static ProbeValue<T> Read<T>(
    BimCreationGuidProbeStage stage,
    Func<T> read)
{
    try { return ProbeValue<T>.Success(stage, read()); }
    catch (Exception ex) when (!IsProcessFatal(ex))
    {
        return ProbeValue<T>.Failure(stage, ex.GetType().FullName, ex.HResult);
    }
}
```

Never rethrow a probe read failure and never reuse one property's result as evidence that a later property was read. Do not call `BimDiagnostics.ObserveException` with raw values; the safe probe report is the evidence channel.

`IsProcessFatal` returns true exactly for `OutOfMemoryException`, `StackOverflowException`, `AccessViolationException`, `AppDomainUnloadedException`, `BadImageFormatException`, `CannotUnloadAppDomainException`, and `System.Threading.ThreadAbortException`; those exceptions remain outside the local degradation path.

Read `CreationGUID` twice independently and report whether both nonempty successful reads are equal. If `PathName` is nonempty, canonicalize it in memory. If central ModelPath is file-based and convertible, canonicalize that converted path separately. Use `BasicFileInfo.Extract(PathName)` only for a saved file and independently read/dispose its `IsCentral` and `IsLocal` evidence.

Derive one closed class from successful evidence only: `FileWorksharedCentral`, `FileWorksharedLocal`, `FileWorksharedUnknownRole`, `RevitServer`, `CloudWorkshared`, `SavedNonWorksharedProject`, `SavedFamily`, `UnsavedProject`, `UnsavedFamily`, `Detached`, or `Unknown`. Detached wins and remains descriptive only.

- [ ] **Step 6: Integrate one active report session and exact provenance**

`RevitCreationGuidProbe` owns one `BimCreationGuidProbeSession?` under a private lock. Actions behave as follows:

- `Begin`: reject a second active session; capture start UTC, PID, `uiapp.Application.VersionName`/`VersionBuild`, RevitAPI assembly version, loaded Rhino/Grasshopper/Rhino.Inside.Revit assembly versions, and `BimDiagnostics.SnapshotStatus()` core/module version+commit.
- `Capture`: require `CaseId` and an active Revit document, collect independent evidence in the current idling operation, add exactly one observation for that case, and return an alias-only progress snapshot.
- `Complete`: refuse while cases are missing; otherwise return the complete safe report and clear raw state before serialization.
- `Abort`: clear raw state and return a bounded aborted result even when no document is active.

Do not retain `Document`, `ModelPath`, `BasicFileInfo`, delegate, raw exception, or diagnostic context in the session.

- [ ] **Step 7: Run tests and prove production identity files are untouched**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~BimCreationGuidProbe|FullyQualifiedName~BimHandlerDiagnostics|FullyQualifiedName~BimHandlerTests" --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
git diff --exit-code $planCommit -- src/RookBim/Revit/RevitIdentitySerializer.cs src/Rook/Bim/BimContracts.cs src/RookNative mcp_server
rg -n "DocumentKey|documentKey|RevitDocumentIdentityResolver|DocumentMatches\(" src/Rook/Bim/CreationGuidProbe src/RookBim/Revit/RevitCreationGuidProbe.cs
git diff --check
```

Expected: tests pass; protected production files have no diff; the forbidden identity/resolver scan returns no matches; diff check passes.

- [ ] **Step 8: Commit the complete probe build before deployment**

```powershell
git add -- src/Rook/Bim/IRookBimRuntime.cs src/Rook/Bim/RookBimUnavailableRuntime.cs src/Rook/Handlers/BimHandler.cs src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs src/Rook.Tests/Handlers/BimHandlerDiagnosticsTests.cs src/Rook.Tests/Handlers/BimHandlerTests.cs src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs src/Rook.Tests/Handlers/BimCreationGuidProbeHandlerTests.cs src/RookBim/Revit/RevitCreationGuidProbe.cs src/RookBim/Revit/RevitRookBimRuntime.cs src/RookBim.Tests/RookBimModuleSourceTests.cs
git commit -m "feat(rookbim): add gated CreationGUID probe"
```

---

### Task 3: Build, deploy, and validate the probe boundary

**Files:**
- No source files unless a build/test defect is found; any correction repeats Task 2's test and review gate before recommit.

**Interfaces:**
- Consumes the committed Task 1-2 probe implementation.
- Produces an exact deployed probe commit with diagnostics enabled only in the new Revit process.
- Does not begin the document matrix until status provenance and disabled-mode containment pass.

- [ ] **Step 1: Verify clean committed source and build order**

```powershell
$probeCommit = (git rev-parse HEAD).Trim()
if (git status --porcelain) { throw 'Commit probe code before deployment' }
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\Rook\Rook.csproj --configuration Release --framework net48 --no-restore
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore -p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024"
```

- [ ] **Step 2: Verify disabled behavior before enabling diagnostics**

With a fresh Revit/Rhino.Inside process that does not inherit `ROOK_BIM_DIAGNOSTICS=1`, invoke the managed probe op through `rhino_execute`. It must return capability unavailable, and the runtime/source tests must show no Revit delegate was constructed. Close Revit afterward.

- [ ] **Step 3: Stop host processes and run the normal local deployment**

Ask the operator to save and close Revit, Rhino, Grasshopper, and Rook MCP. Resolve exact remaining process PIDs before terminating anything. Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -Configuration Release
```

Record installed roots and build outcomes. This must build/copy `Rook` before `RookBim`.

- [ ] **Step 4: Launch one diagnostics-enabled Revit process with a nonpersistent environment**

```powershell
$env:ROOK_BIM_DIAGNOSTICS = '1'
Start-Process -FilePath 'C:\Program Files\Autodesk\Revit 2024\Revit.exe'
Remove-Item Env:ROOK_BIM_DIAGNOSTICS
```

Do not use `setx`. Open Rhino.Inside and wait for Rook to load. Call `/bim/status` and require `diagnosticsEnabled == true`, core/module commits matching `$probeCommit`, and a nonfailed sink state before continuing.

- [ ] **Step 5: Prove the public native route surface did not grow**

Capture the registered `/bim/*` route list/capability status and verify there is no creation-guid probe route or MCP tool. The only invocation path is an explicit operator `BimHandler.Dispatch` call within the loaded process.

---

### Task 4: Operator-assisted Revit 2024 CreationGUID matrix

**Files:**
- No repository file until the safe completed report is returned.

**Interfaces:**
- Consumes one diagnostics-enabled Revit process and only disposable test models.
- Produces one alias-only completed `BimCreationGuidProbeReport` held in the operator transcript/work buffer.
- This task must run inline with the operator; do not delegate model creation/open/close/save choices.

- [ ] **Step 1: Begin the report session through managed dispatch**

Invoke `rhino_execute` with this Python, which returns aliases/provenance only:

```python
import clr
import json
clr.AddReference("Rook")
from Rook.Handlers import BimHandler

result = BimHandler().Dispatch(json.dumps({
    "op": "creation_guid_probe",
    "action": "begin"
}))
print(result.Data.ToJsonString())
```

Confirm the response contains the probe commit, PID, UTC start, and exact Revit/Rhino/Grasshopper/Rhino.Inside versions, with no title/path/GUID.

- [ ] **Step 2: Use one closed capture command for every active fixture**

For each case below, substitute only the exact safe case ID in this operator command:

```python
import clr
import json
clr.AddReference("Rook")
from Rook.Handlers import BimHandler

case_id = "saved_project_initial"
result = BimHandler().Dispatch(json.dumps({
    "op": "creation_guid_probe",
    "action": "capture",
    "caseId": case_id
}))
print(result.Data.ToJsonString())
```

The case IDs are exactly:

```text
saved_project_initial
saved_project_reopen
file_central
file_local
file_local_reopen
copied_central
detached
saved_family
unsaved_project
unsaved_family
replacement_same_path
```

- [ ] **Step 3: Capture saved/unsaved non-workshared and family cases**

Using only a disposable probe directory/model set:

1. Create and save a non-workshared project; capture `saved_project_initial`.
2. Close/reopen the same project in the same Revit process; capture `saved_project_reopen`.
3. Create an unsaved project; capture `unsaved_project`, then close without saving.
4. Create and save a family; capture `saved_family`.
5. Create an unsaved family; capture `unsaved_family`, then close without saving.

After each capture, inspect only alias/status output. If any raw title/path/GUID appears, abort immediately and do not persist the output.

- [ ] **Step 4: Capture file-workshared central/local/copy/detached cases**

From a disposable project:

1. Enable worksharing and save a central; capture `file_central`.
2. Open/create a standard local from that central; capture `file_local`.
3. Close/reopen that same local; capture `file_local_reopen`.
4. Create a copied central or Save As Central at a different disposable path; capture `copied_central`.
5. Open a detached copy; capture `detached`.

Keep the Revit process alive so the one-report alias table remains valid. Do not use a customer model or path.

- [ ] **Step 5: Capture the same-path replacement safety case**

Close the original disposable saved non-workshared document. Create a different new document and save it over the same disposable path, then capture `replacement_same_path`. The expected location evidence may reuse the earlier `path-NNN` alias, while the probe must reveal whether `CreationGUID` receives a different `creation-NNN` alias. Do not delete or overwrite any file outside the explicitly created disposable probe directory.

- [ ] **Step 6: Complete the report and verify privacy before saving anything**

```python
import clr
import json
clr.AddReference("Rook")
from Rook.Handlers import BimHandler

result = BimHandler().Dispatch(json.dumps({
    "op": "creation_guid_probe",
    "action": "complete"
}))
print(result.Data.ToJsonString())
```

Completion must refuse if a required case is missing. On success, verify:

- all eleven cases are present once;
- every property has an independent status;
- repeated CreationGUID equality is explicit;
- fixed pairwise equality relations are present;
- no model/family title, filename, `.rvt`/`.rfa` path, raw GUID, deterministic 64-hex path/GUID hash, newline-bearing exception, or message appears;
- the session reports raw state cleared.

If the matrix cannot safely finish, invoke the same command with `"action":"abort"`; confirm raw-state clearing and restart the complete probe later.

---

### Task 5: Durable report, proposed spec decision, rollback, and review stop

**Files:**
- Create: `docs/superpowers/probes/2026-07-26-rookbim-creation-guid-result.md`
- Modify: `docs/superpowers/specs/2026-07-26-rookbim-file-workshared-identity-design.md`

**Interfaces:**
- Consumes only the completed alias-only report from Task 4.
- Produces a durable redacted matrix and a proposed decision for reviewer approval.
- Produces no production identity plan or code.

- [ ] **Step 1: Write the report from alias-only evidence**

Record:

- probe commit, PID, UTC interval, exact Revit/RevitAPI/Rhino/Grasshopper/Rhino.Inside/Rook/RookBIM versions;
- one row per required case with class, property read statuses, nonempty/repeated-read facts, aliases, central/local/ModelPath kind, and bounded failure type/HResult;
- fixed same/different/unavailable relations;
- whether each composite suitability criterion passed;
- missing/unavailable infrastructure, if any;
- explicit confirmation that detached evidence is descriptive only;
- privacy validation and raw-session-clear result.

Use only aliases and closed facts. Do not paste raw tool output until it has passed the privacy check.

- [ ] **Step 2: Add a proposed decision to the identity spec without authorizing production**

Amend the decision-gate section with the report path and observed class matrix. Label the outcome `Proposed — awaiting reviewer approval`, choosing exactly one evidence-backed option:

1. composite suitable for named passing classes;
2. class-limited composite with named fail-closed classes; or
3. composite rejected and all affected classes remain fail closed.

Path-only authorization remains prohibited in every outcome. Do not mark candidate key sources approved and do not change the spec status to implementation-ready until the reviewer responds.

- [ ] **Step 3: Run documentation/privacy checks and protected-source checks**

```powershell
git diff --check
rg -n -i "[A-Z]:\\|\\\\[^ ]+\\[^ ]+|\.rvt|\.rfa|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" docs/superpowers/probes/2026-07-26-rookbim-creation-guid-result.md
git diff --exit-code $planCommit -- src/RookBim/Revit/RevitIdentitySerializer.cs src/Rook/Bim/BimContracts.cs src/RookNative mcp_server
```

Expected: diff check passes; privacy scan has no model path/file/GUID match; describe extensions generically in the report rather than spelling their literals; protected production source remains unchanged.

- [ ] **Step 4: Commit only the redacted result and decision-gate amendment**

```powershell
git add -- docs/superpowers/probes/2026-07-26-rookbim-creation-guid-result.md docs/superpowers/specs/2026-07-26-rookbim-file-workshared-identity-design.md
git commit -m "docs: record RookBIM CreationGUID probe"
```

- [ ] **Step 5: Roll the deployed diagnostic probe back or explicitly retain it for review**

After capture, close Revit. The default operational choice is to redeploy the reviewed pre-probe baseline `761a42af1d5c083dd69ee0908531c7d36a7b9995` from a clean worktree so the temporary managed probe operation is not left installed. If support needs the build retained for a reviewer-requested repeat, document the exact PID/commit and keep `ROOK_BIM_DIAGNOSTICS` absent from future launches.

- [ ] **Step 6: Stop for key-strategy review**

Hand off the report and amended spec. Do not write or execute a production identity implementation plan until the reviewer records the selected key strategy, approved document classes/key sources, unsupported classes, and acceptance requirements in the spec.

---

## Plan Self-Review Checklist

- [ ] This plan is separate from the Grasshopper implementation and creates its own worktree/branch.
- [ ] Every task is probe-only; no `documentKey`, resolver, comparator, or production identity branch is implemented.
- [ ] Exact diagnostics gating occurs before runtime/delegate invocation and is tested disabled.
- [ ] No native route or MCP tool exposes the probe.
- [ ] Revit objects remain in `src/RookBim` and one API operation; the session stores only raw scalar equality inputs temporarily.
- [ ] Each property read is independent, locally caught, and behavior-neutral.
- [ ] CreationGUID is read twice; central/local/copy/detach/reopen/same-path replacement relations are explicit.
- [ ] Report aliases are per-session, nondeterministic across reports, and not hashes.
- [ ] Successful complete/abort destroys raw maps; incomplete completion preserves the session and reports missing cases.
- [ ] Canonical UNC share roots omit a trailing separator and golden UTF-8 vectors pass.
- [ ] Provenance includes exact host/build versions, commit, PID, and UTC.
- [ ] Titles, filenames, paths, GUIDs, messages, deterministic identity hashes, and raw exceptions never enter the durable report or diagnostics.
- [ ] `RevitIdentitySerializer`, identity DTOs, native routes, MCP tools, selection, and export remain unchanged.
- [ ] `Rook` builds before `RookBim`; the probe commit is recorded before deployment.
- [ ] The live matrix is the decision evidence; source tests cannot approve a key.
- [ ] The final spec amendment remains proposed and blocks production implementation until reviewer approval.
