# LM8K Grasshopper Solve-Readiness Receipt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Deliver a managed, document-scoped solve-readiness receipt for one gh_set_value mutation path and one receipt-fenced gh_inspect_output read.

**Architecture:** A managed lifecycle adapter verifies and subscribes to the actual Grasshopper solution events, then forwards correlated start/end notifications to a bounded GhSolveReceiptRegistry. GrasshopperHandler issues and consumes receipts, the native bridge exposes the routes, and Python forwards their contracts without readiness policy. LM8F, LM8I, and LM8J stay unchanged.

**Tech Stack:** C# / .NET Framework managed companion, Rhino 8 and installed Grasshopper metadata, native C++ MFC bridge ABI, Python 3.10 MCP server, xUnit, pytest.

## Global Constraints

- Preserve existing asynchronous RequestPostMutationSolve safety policy; never request synchronous recompute.
- SolutionState, elapsed delay, and scheduling success are telemetry only, never freshness proof.
- A ready receipt requires a correlated post-schedule start and matching completion.
- Public receipt authority is a random opaque identifier with at least 128 bits of entropy.
- Keep 64 active/pending records, a 10-minute pending expiry, 256 terminal records, and 15-minute nominal terminal retention.
- Supersede older receipts immediately when a newer managed mutation is issued.
- gh_wait_for_solve_readiness must never invoke the Rhino/GH UI dispatcher or use ExecuteApiResponseCallback.
- gh_inspect_output keeps its legacy path with no receipt; a fenced read never waits or falls back.
- Instrument gh_set_value only. Do not migrate gh_connect, gh_delete, gh_edit, script writes, LM8F, LM8I, or LM8J.
- Python adds no polling, sleep, or timing logic.
- Do not run a live Rhino/GH smoke in the implementation PR. The smoke occurs once, after merge.

---

## File Map

| File | Change | Responsibility |
|---|---|---|
| tools/verify_gh_solution_lifecycle_contract.ps1 | Create | Read-only installed-Grasshopper API check for Task 0. |
| src/Rook/InternalBridge/GhSolutionLifecycleAdapter.cs | Create | Reflection-backed solution event attachment or fail-closed unavailable result. |
| src/Rook/InternalBridge/GhCanvasDocumentLifecycleAdapter.cs | Create | Reflection-backed canvas document-change attachment for immediate session invalidation. |
| src/Rook/InternalBridge/GhSolveReceiptRegistry.cs | Create | Sessions, opaque IDs, epochs, waiter signaling, expiry, eviction, and fenced-read gates. |
| src/Rook/Handlers/GrasshopperHandler.Readiness.cs | Create | Handler integration, status/wait operations, and output-read fence. |
| src/Rook/Handlers/GrasshopperHandler.cs | Modify | Issue receipt from SetValue, add optional receipt to InspectOutput, replace session on document changes. |
| src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs | Modify | ABI v18, status/wait callbacks, and dedicated off-UI wait executor. |
| src/RookNative/Handlers/GrasshopperProxyHandler.cpp | Modify | ABI v18 struct append, proxy dispatch, and readiness route handlers. |
| src/RookNative/Handlers/GrasshopperProxyHandler.h | Modify | Proxy readiness handler declarations. |
| src/RookNative/RookServer.cpp | Modify | Register native readiness routes. |
| src/RookNative/RookServer.h | Modify | Server readiness handler declarations. |
| mcp_server/src/rook/server.py | Modify | Tool schemas and thin dispatch only. |
| mcp_server/tools/gh_solve_readiness_live_smoke.py | Create | Post-merge deterministic smoke driver. |
| src/Rook.Tests/InternalBridge/GhSolutionLifecycleAdapterTests.cs | Create | Installed-contract adapter tests with fake lifecycle documents. |
| src/Rook.Tests/InternalBridge/GhCanvasDocumentLifecycleAdapterTests.cs | Create | Canvas document-replacement adapter tests with fake canvas events. |
| src/Rook.Tests/InternalBridge/GhSolveReceiptRegistryTests.cs | Create | State, exact-fence, wait, expiry, supersession, and capacity tests. |
| src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs | Create | Managed mutation/read receipt integration tests. |
| src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs | Modify | ABI v18, route mapping, and off-UI bridge tests. |
| src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs | Modify | Session replacement wiring tests. |
| mcp_server/tests/test_gh_solve_readiness_tools.py | Create | Exact schemas and route forwarding tests. |
| mcp_server/tests/test_server_gh_knowledge_wrappers.py | Modify | Nested receipt preservation through gh_set_value wrapper. |
| mcp_server/tests/test_gh_solve_readiness_live_smoke.py | Create | Fake transport smoke-sequence tests. |

## Task 0: Verify Lifecycle API and Callback Order Before Registry Work

**Files:**
- Create: tools/verify_gh_solution_lifecycle_contract.ps1
- Create: src/Rook/InternalBridge/GhSolutionLifecycleAdapter.cs
- Create: src/Rook/InternalBridge/GhCanvasDocumentLifecycleAdapter.cs
- Test: src/Rook.Tests/InternalBridge/GhSolutionLifecycleAdapterTests.cs
- Test: src/Rook.Tests/InternalBridge/GhCanvasDocumentLifecycleAdapterTests.cs

**Consumes:** Installed Grasshopper.dll and Grasshopper.xml.

**Produces:** A fail-closed adapter and a hard precondition for all later tasks.

- [ ] **Step 1: Add the read-only installed API verifier**

Create tools/verify_gh_solution_lifecycle_contract.ps1. It checks the exact XML members for GH_Document.SolutionStart, GH_Document.SolutionEnd, GH_Document.ScheduleSolution(Int32), and GH_Canvas.DocumentChanged, then loads the installed RhinoCommon and Grasshopper assemblies to inspect the actual event delegate contracts. It must emit the event delegate and Invoke signatures, plus solution-event document and canvas-change old/new document properties, rather than assuming EventHandler.

~~~powershell
param(
    [string]$GrasshopperDll = "C:\Program Files\Rhino 8\Plug-ins\Grasshopper\Grasshopper.dll",
    [string]$GrasshopperXml = "C:\Program Files\Rhino 8\Plug-ins\Grasshopper\Grasshopper.xml",
    [string]$RhinoCommonDll = "C:\Program Files\Rhino 8\System\RhinoCommon.dll"
)

if (-not (Test-Path -LiteralPath $GrasshopperDll)) { throw "Missing Grasshopper.dll: $GrasshopperDll" }
if (-not (Test-Path -LiteralPath $GrasshopperXml)) { throw "Missing Grasshopper.xml: $GrasshopperXml" }
if (-not (Test-Path -LiteralPath $RhinoCommonDll)) { throw "Missing RhinoCommon.dll: $RhinoCommonDll" }

[xml]$doc = Get-Content -Raw -LiteralPath $GrasshopperXml
$members = @($doc.doc.members.member)
$start = @($members | Where-Object { $_.name -eq "E:Grasshopper.Kernel.GH_Document.SolutionStart" })
$end = @($members | Where-Object { $_.name -eq "E:Grasshopper.Kernel.GH_Document.SolutionEnd" })
$schedule = @($members | Where-Object { $_.name -eq "M:Grasshopper.Kernel.GH_Document.ScheduleSolution(System.Int32)" })
$canvasChanged = @($members | Where-Object { $_.name -eq "E:Grasshopper.GUI.Canvas.GH_Canvas.DocumentChanged" })

if ($start.Count -ne 1 -or $end.Count -ne 1 -or $schedule.Count -ne 1 -or $canvasChanged.Count -ne 1) {
    throw "Installed Grasshopper lifecycle contract is incomplete."
}

[Reflection.Assembly]::LoadFrom($RhinoCommonDll) | Out-Null
$assembly = [Reflection.Assembly]::LoadFrom($GrasshopperDll)
$documentType = $assembly.GetType("Grasshopper.Kernel.GH_Document", $true)
$eventContracts = foreach ($name in "SolutionStart", "SolutionEnd") {
    $event = $documentType.GetEvent($name)
    $invoke = $event.EventHandlerType.GetMethod("Invoke")
    $parameters = $invoke.GetParameters()
    if ($invoke.ReturnType -ne [void] -or $parameters.Count -ne 2 -or
        -not [EventArgs].IsAssignableFrom($parameters[1].ParameterType) -or
        $parameters[1].ParameterType.GetProperty("Document") -eq $null) {
        throw "Unsupported $name delegate contract: $($event.EventHandlerType.FullName)"
    }

    [pscustomobject]@{
        name = $name
        delegate_type = $event.EventHandlerType.FullName
        invoke_signature = $invoke.ToString()
        event_args_document_type = $parameters[1].ParameterType.GetProperty("Document").PropertyType.FullName
    }
}

$canvasType = $assembly.GetType("Grasshopper.GUI.Canvas.GH_Canvas", $true)
$canvasEvent = $canvasType.GetEvent("DocumentChanged")
$canvasInvoke = $canvasEvent.EventHandlerType.GetMethod("Invoke")
$canvasParameters = $canvasInvoke.GetParameters()
$canvasArgs = $canvasParameters[1].ParameterType
if ($canvasInvoke.ReturnType -ne [void] -or $canvasParameters.Count -ne 2 -or
    -not [EventArgs].IsAssignableFrom($canvasArgs) -or
    $canvasArgs.GetProperty("OldDocument") -eq $null -or
    $canvasArgs.GetProperty("NewDocument") -eq $null) {
    throw "Unsupported DocumentChanged delegate contract: $($canvasEvent.EventHandlerType.FullName)"
}

[pscustomobject]@{
    solution_start_documented = $start[0].summary.Trim()
    solution_end_documented = $end[0].summary.Trim()
    schedule_solution_documented = $schedule[0].summary.Trim()
    grasshopper_dll = $GrasshopperDll
    lifecycle_events = $eventContracts
    canvas_document_changed = [pscustomobject]@{
        delegate_type = $canvasEvent.EventHandlerType.FullName
        invoke_signature = $canvasInvoke.ToString()
        old_document_type = $canvasArgs.GetProperty("OldDocument").PropertyType.FullName
        new_document_type = $canvasArgs.GetProperty("NewDocument").PropertyType.FullName
    }
} | ConvertTo-Json -Depth 3
~~~

- [ ] **Step 2: Run the installed API verifier**

Run:

~~~powershell
powershell -ExecutionPolicy Bypass -File tools\verify_gh_solution_lifecycle_contract.ps1
~~~

Expected: exactly one XML member for each required API, two runtime solution contracts with `void (object, EventArgs-derived)` delegates whose event args expose `Document`, and one canvas document-change contract whose EventArgs expose `OldDocument` and `NewDocument`. The installed Rhino 8 XML must report that SolutionStart is raised for a new solution request, SolutionEnd after the request is handled, and DocumentChanged when a different document is loaded into the canvas. If it fails, stop; do not infer alternate event names, delegates, or event-argument shapes.

- [ ] **Step 3: Write failing adapter tests**

Use a fake document with public custom start/end delegates shaped like the installed contract, a fake missing SolutionEnd, and a fake incompatible delegate. Separately use a fake canvas with a custom DocumentChanged delegate carrying OldDocument/NewDocument. The solution adapter must pass the `Document` object carried by the event arguments to the callback; do not infer it from ambient canvas state. The canvas adapter must pass both old and new document objects without reading the active canvas again.

~~~csharp
[Fact]
public void Attach_CompatibleEvents_ForwardsStartThenEnd()
{
    var document = new FakeDocument();
    var observed = new List<(string Phase, object Document)>();
    using var subscription = new GhSolutionLifecycleAdapter().Attach(
        document,
        callbackDocument => observed.Add(("start", callbackDocument)),
        callbackDocument => observed.Add(("end", callbackDocument)));

    Assert.True(subscription.IsAvailable);
    document.RaiseStart();
    document.RaiseEnd();
    Assert.Equal(new[] { "start", "end" }, observed.Select(item => item.Phase));
    Assert.All(observed, item => Assert.Same(document, item.Document));
}

[Fact]
public void Attach_MissingSolutionEnd_FailsClosed()
{
    using var subscription = new GhSolutionLifecycleAdapter().Attach(
        new MissingEndDocument(),
        _ => { },
        _ => { });

    Assert.False(subscription.IsAvailable);
    Assert.Equal("solution_end_event_missing", subscription.Reason);
}

[Fact]
public void AttachCanvasDocumentChanged_ForwardsOldAndNewDocuments()
{
    var oldDocument = new FakeDocument();
    var newDocument = new FakeDocument();
    var canvas = new FakeCanvas(oldDocument);
    (object? Old, object? New)? observed = null;
    using var subscription = new GhCanvasDocumentLifecycleAdapter().Attach(
        canvas,
        (prior, current) => observed = (prior, current));

    canvas.RaiseDocumentChanged(oldDocument, newDocument);

    Assert.True(observed.HasValue);
    Assert.Same(oldDocument, observed.Value.Old);
    Assert.Same(newDocument, observed.Value.New);
}
~~~

- [ ] **Step 4: Run the adapter test and confirm red**

Run:

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolutionLifecycleAdapterTests|FullyQualifiedName~GhCanvasDocumentLifecycleAdapterTests" --no-restore
~~~

Expected: FAIL because the solution and canvas lifecycle adapters are absent.

- [ ] **Step 5: Implement the lifecycle adapter**

Implement a reflection-only solution adapter that finds exact public instance events named SolutionStart and SolutionEnd, creates delegates of each event's verified runtime delegate type (for example through an expression adapter), and removes both exactly once on Dispose. Implement a separate canvas adapter that attaches to public instance DocumentChanged, requires EventArgs-derived OldDocument/NewDocument properties, forwards them directly, and removes its delegate exactly once on Dispose.

~~~csharp
internal sealed class GhSolutionLifecycleAdapter
{
    internal GhSolutionLifecycleSubscription Attach(
        object document,
        Action<object> onSolutionStart,
        Action<object> onSolutionEnd)
    {
        // Exact event lookup, installed-shape verification, and typed delegate binding.
        // Return IsAvailable=false with a stable reason on every mismatch.
    }
}

internal sealed class GhSolutionLifecycleSubscription : IDisposable
{
    internal bool IsAvailable { get; }
    internal string? Reason { get; }
    public void Dispose() { /* idempotently remove subscribed delegates */ }
}
~~~

Do not read SolutionState. Verify every solution event delegate has `void Invoke(object, EventArgs-derived)` and that the actual argument type has a readable `Document` property. Bind a delegate of the event's real type with an expression/generated adapter that forwards that document; do not cast the event to `EventHandler` or assume a particular Grasshopper delegate name. The canvas adapter applies the same verification to DocumentChanged and its OldDocument/NewDocument properties. Delegate or argument mismatch returns `solution_lifecycle_delegate_incompatible` or `canvas_document_changed_delegate_incompatible`. Neither adapter schedules, waits, reads output, or creates a public route.

- [ ] **Step 6: Run adapter tests and confirm green**

Run both adapter suites:

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolutionLifecycleAdapterTests|FullyQualifiedName~GhCanvasDocumentLifecycleAdapterTests" --no-restore
~~~

Expected: PASS. Add a disposal assertion proving no callback fires after Dispose.

- [ ] **Step 7: Perform the local non-evidence callback-order preflight**

Before Task 1, deploy the Task 0 adapter to a local debug Rhino/Rook instance, attach a debugger or trace breakpoint to its two callbacks, create a fresh GH document, and trigger one existing gh_solve. Instrument immediately before and after the exact `ScheduleSolution(...)` invocation as well. Confirm:

~~~text
SolutionStart callback arrives before the corresponding SolutionEnd callback.
The successful ScheduleSolution return trace arrives before the correlated SolutionStart callback; SolutionStart must not re-enter synchronously before scheduling reports success.
Both event arguments' Document properties reference the active GH document.
One controlled canvas document replacement raises DocumentChanged with the prior and new document references before registry work begins.
Both callbacks run on the GH/UI thread.
~~~

This is a development API confirmation, not LM8K evidence: do not create probe_runs artifacts, do not claim a product result, and do not run it as part of the implementation PR verification. Use an uncommitted DEBUG-only `NativeGhBridgeRegistrar` preflight hook that resolves `Grasshopper.Instances.ActiveCanvas` and its Document by reflection, attaches both Task 0 adapters, writes only debugger/trace output, and returns a disposable handle. Invoke that hook from the Visual Studio Immediate window, trigger one existing `gh_solve`, inspect the ordered trace, dispose the handle, and remove the hook before the Task 0 commit. It creates no route or durable artifact. If the schedule-return/start ordering differs, stop and revise the receipt correlation design before Task 1; do not treat the current post-return `MarkScheduleAccepted` transition as safe by assumption.

- [ ] **Step 8: Commit Task 0**

~~~powershell
git add tools\verify_gh_solution_lifecycle_contract.ps1 src\Rook\InternalBridge\GhSolutionLifecycleAdapter.cs src\Rook\InternalBridge\GhCanvasDocumentLifecycleAdapter.cs src\Rook.Tests\InternalBridge\GhSolutionLifecycleAdapterTests.cs src\Rook.Tests\InternalBridge\GhCanvasDocumentLifecycleAdapterTests.cs
git commit -m "test(lm8k): verify GH solution lifecycle contract"
~~~

## Task 1: Implement the Bounded Managed Receipt Registry

**Files:**
- Create: src/Rook/InternalBridge/GhSolveReceiptRegistry.cs
- Test: src/Rook.Tests/InternalBridge/GhSolveReceiptRegistryTests.cs

**Consumes:** Start/end callbacks from Task 0.

**Produces:** Opaque receipt state, document sessions, mutation/run epochs, asynchronous waiter signaling, and exact solution-run read gates.

- [ ] **Step 1: Write failing state-machine tests**

Add tests for a ready receipt, an uncorrelated completion, stale later runs, timeout ownership release, supersession, replacement, lifecycle unknown, expiry, and terminal eviction.

~~~csharp
[Fact]
public void MatchingStartThenEnd_MarksLatestReceiptReady()
{
    var registry = CreateRegistry();
    var issue = registry.IssueMutation(DocumentA);
    Assert.True(issue.Issued);
    var receipt = issue.Receipt!;
    registry.MarkScheduleAccepted(receipt.ReceiptId);
    registry.OnSolutionStart(DocumentA);
    registry.OnSolutionEnd(DocumentA);

    var current = registry.Get(receipt.ReceiptId);

    Assert.Equal(GhSolveReadinessStatus.Ready, current.Receipt.Status);
    Assert.Equal(1, current.Receipt.SolutionRunEpoch);
    Assert.Equal(1, current.Receipt.CompletedSolutionRunEpoch);
}

[Fact]
public void LaterCompletedRun_RejectsEarlierFencedRead()
{
    var registry = CreateReadyRegistry(out var receipt);
    registry.OnSolutionStart(DocumentA);
    registry.OnSolutionEnd(DocumentA);

    var gate = registry.CheckFencedRead(receipt.ReceiptId, DocumentA);

    Assert.False(gate.Allowed);
    Assert.Equal("readiness_receipt_stale_solution_run", gate.Error);
}

[Fact]
public void WaitTimeout_LeavesReceiptPending_AndReleasesOwnership()
{
    var registry = CreateRegistry();
    var issue = registry.IssueMutation(DocumentA);
    Assert.True(issue.Issued);
    var receipt = issue.Receipt!;
    registry.MarkScheduleAccepted(receipt.ReceiptId);

    var result = registry.Wait(receipt.ReceiptId, TimeSpan.FromMilliseconds(1), CancellationToken.None);

    Assert.Equal(GhReadinessWaitStatus.Timeout, result.WaitStatus);
    Assert.Equal(GhSolveReadinessStatus.Pending, result.Receipt.Status);
    Assert.True(registry.CanAcquireWaiterForTests(receipt.ReceiptId));
}
~~~

- [ ] **Step 2: Run registry tests and confirm red**

Run:

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~GhSolveReceiptRegistryTests --no-restore
~~~

Expected: FAIL because the registry is absent.

- [ ] **Step 3: Add models and registry API**

Create these internal models and exact entry points:

~~~csharp
internal enum GhSolveReadinessStatus
{
    Pending, Ready, Superseded, DocumentReplaced, SolverLocked, Unknown
}

internal sealed record GhSolveReadinessReceipt(
    string ReceiptId,
    string DocumentSessionId,
    long MutationEpoch,
    long? SolutionRunEpoch,
    long CompletedSolutionRunEpoch,
    GhSolveReadinessStatus Status,
    string? Reason,
    string? CompletionSignal,
    DateTimeOffset IssuedAt,
    DateTimeOffset? CompletedAt);

internal sealed record GhReadinessIssueResult(
    bool Issued,
    GhSolveReadinessReceipt? Receipt,
    string? Error);

internal enum GhReadinessWaitStatus { Ready, Timeout, Terminal }

internal sealed class GhSolveReceiptRegistry
{
    internal GhReadinessIssueResult IssueMutation(object document);
    internal GhSolveReadinessReceipt MarkMutationFailed(string receiptId);
    internal GhSolveReadinessReceipt MarkSolverLocked(string receiptId);
    internal GhSolveReadinessReceipt MarkScheduleAccepted(string receiptId);
    internal void MarkLifecycleUnavailable(string receiptId, string reason);
    internal void OnSolutionStart(object document);
    internal void OnSolutionEnd(object document);
    internal GhReadinessLookup Get(string receiptId);
    internal GhReadinessWaitResult Wait(string receiptId, TimeSpan timeout, CancellationToken cancellationToken);
    internal GhFencedReadGate CheckFencedRead(string receiptId, object activeDocument);
    internal void ReplaceDocument(object? newDocument);
}
~~~

Use injected monotonic clock and ID factories in tests. Production identifiers use RandomNumberGenerator.GetBytes(16). `IssueMutation` returns `Issued=false, Error=readiness_registry_capacity_exceeded` before any mutation when 64 active/pending records are present; terminal retention eviction never returns that error. Each pending record owns an event signal used only to wake the bounded wait; the signal is set by terminal transitions and is never used as a readiness substitute.

- [ ] **Step 4: Implement transitions, retention, and exact fence**

Bind a run only when SolutionStart arrives after MarkScheduleAccepted for the newest same-session non-superseded receipt. Mark ready only on its matching SolutionEnd. Never let an end without a bound start advance a receipt.

Purge terminal expiry, transition pending expiry to Unknown with reason receipt_expired, reject only active/pending capacity 64 before mutation, and evict the oldest terminal record by monotonic terminalized-at time then insertion order. Never evict pending records.

A fenced read permits only Ready receipt, matching active document session/current mutation epoch, exact equality between bound and latest completed run, and no newer active/completed run. It returns readiness_receipt_stale_solution_run without extracting output when any later run exists.

- [ ] **Step 5: Implement bounded wait ownership**

A known terminal receipt returns immediately. A pending receipt atomically owns one waiter. Another waiter returns readiness_wait_already_active. Completion, timeout, cancellation, replacement, supersession, and exceptions release ownership. The wait blocks only on that receipt's event signal and the caller cancellation handle for the supplied bounded duration; it runs only from the dedicated bridge worker path, never from the GH/UI thread.

Wait on a completion signal only; do not use Thread.Sleep, Task.Delay, an application timer, polling, or SolutionState. A bounded `WaitHandle.WaitAny`/equivalent wait is permitted because it waits for the signal or its explicit timeout in one operation rather than re-reading state. The lifecycle callback only transitions registry state and signals the waiter; it never runs a continuation inline.

- [ ] **Step 6: Run registry suite and confirm green**

Run the Task 1 test command again.

Expected: PASS. Add source assertions that the registry contains neither Thread.Sleep, Task.Delay, nor an application timer, and behavior tests proving the wait blocks on the receipt signal rather than polling status.

- [ ] **Step 7: Commit Task 1**

~~~powershell
git add src\Rook\InternalBridge\GhSolveReceiptRegistry.cs src\Rook.Tests\InternalBridge\GhSolveReceiptRegistryTests.cs
git commit -m "feat(lm8k): add managed solve receipt registry"
~~~

## Task 2: Integrate Receipt Ownership into GrasshopperHandler

**Files:**
- Create: src/Rook/Handlers/GrasshopperHandler.Readiness.cs
- Modify: src/Rook/Handlers/GrasshopperHandler.cs
- Modify: src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs
- Create: src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs

**Consumes:** Task 0 solution/canvas adapters and Task 1 registry.

**Produces:** gh_set_value receipt emission, readiness status/wait operations, document replacement, and receipt-fenced output inspection.

- [ ] **Step 1: Write failing handler tests**

~~~csharp
[Fact]
public void SuccessfulSliderMutation_NestsPendingReceiptWithoutChangingSuccess()
{
    var handler = CreateHandlerWithReadyLifecycle();
    var response = handler.SetValue("{\"guid\":\"slider-1\",\"value\":7.5}");

    Assert.True(response.Success);
    var data = JsonSerializer.SerializeToElement(response.Data);
    Assert.Equal("slider", data.GetProperty("Type").GetString());
    Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
}

[Fact]
public void FencedInspect_StaleReceipt_FailsBeforeExtraction()
{
    var handler = CreateHandlerWithStaleReceipt(out var inspectCalled);
    var response = handler.InspectOutput("addition-1", "R", "receipt-1");

    Assert.False(response.Success);
    Assert.Equal("readiness_receipt_stale_solution_run", ReadError(response));
    Assert.False(inspectCalled);
}
~~~

Also cover lifecycle unavailable returning a terminal Unknown receipt on successful mutation, solver lock, pending/unknown/superseded fence failures, ready provenance, and document replacement. Add envelope tests: a known terminal receipt returns outer `Success=true` with its receipt snapshot; a valid wait returns outer `Success=true` with exactly `wait_status` in `ready|timeout|terminal` plus its receipt snapshot; absent, evicted, or post-restart IDs return outer `Success=false` with `readiness_receipt_not_found_or_evicted_or_process_restarted`. Add an active-registry-capacity test proving SetValue returns `readiness_registry_capacity_exceeded` before touching the slider. Add an externally replaced active-document test proving the next receipt-aware SetValue creates a new session and tombstones the former session's pending receipt.

- [ ] **Step 2: Run handler tests and confirm red**

Run:

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~GrasshopperHandlerReadinessTests --no-restore
~~~

Expected: FAIL because the readiness partial and receipt-aware InspectOutput overload are absent.

- [ ] **Step 3: Add handler dependencies and partial ownership**

Extend the existing constructor after its current optional arguments:

~~~csharp
internal GrasshopperHandler(
    IGrasshopperCore? bridgeCore = null,
    GhSolveReadinessCoordinator? solveReadinessCoordinator = null,
    GhSolveReceiptRegistry? solveReceiptRegistry = null,
    GhSolutionLifecycleAdapter? solutionLifecycleAdapter = null,
    GhCanvasDocumentLifecycleAdapter? canvasDocumentLifecycleAdapter = null)
{
    _bridgeCore = bridgeCore ?? new GrasshopperCore();
    _solveReadinessCoordinator = solveReadinessCoordinator ?? new GhSolveReadinessCoordinator();
    _solveReceiptRegistry = solveReceiptRegistry ?? new GhSolveReceiptRegistry();
    _solutionLifecycleAdapter = solutionLifecycleAdapter ?? new GhSolutionLifecycleAdapter();
    _canvasDocumentLifecycleAdapter = canvasDocumentLifecycleAdapter ?? new GhCanvasDocumentLifecycleAdapter();
}
~~~

The new partial owns attachment/disposal, `EnsureReadinessSession(document, canvas)`, GetSolveReadiness, WaitForSolveReadiness, readiness response envelopes, and fenced-read validation. Attach the canvas adapter once for the active canvas. On its DocumentChanged callback, synchronously tombstone the old session, signal all waiters, dispose the former solution subscription, and attach a solution subscription for the new document before any new receipt can issue. A null NewDocument is a document replacement/close, not a reusable session. Status returns a known receipt snapshot under outer `Success=true`; wait returns outer `Success=true` with `wait_status: ready|timeout|terminal` and that snapshot; lookup absence/eviction/restart returns outer `Success=false` with `readiness_receipt_not_found_or_evicted_or_process_restarted`; a known non-ready or stale receipt used for a fenced read returns outer `Success=false` with its snapshot and pinned fence code. A known terminal receipt with status `unknown` remains a distinct receipt-state error, `readiness_receipt_unknown`. `EnsureReadinessSession` compares the active GH document and canvas objects by reference on every receipt-issuing SetValue; it attaches the canvas and solution adapters before registration for a first-seen existing document, and remains a lazy backstop when the host swaps a canvas/document without delivering the expected callback. Keep registry policy out of the existing large handler file.

- [ ] **Step 4: Emit a receipt from existing SetValue branches**

Call `EnsureReadinessSession(gh.Document!, gh.Canvas!)`, reserve before the value assignment, call existing RequestPostMutationSolve once, then finalize the receipt from its outcome. If reservation reports active-capacity exhaustion, return `readiness_registry_capacity_exceeded` before assigning the value or requesting a solve.

~~~csharp
var issue = BeginSetValueReceipt(gh.Document!, gh.Canvas!);
if (!issue.Issued)
    return ReadinessIssueFailure(issue.Error!);
var receipt = issue.Receipt!;
sliderType.GetProperty("Value")?.SetValue(slider, newValue);

var solveOutcome = RequestPostMutationSolve(gh.Document!, obj, requestSolve: true);
receipt = FinalizeSetValueReceipt(receipt.ReceiptId, solveOutcome);

return new ApiResponse
{
    Success = true,
    Data = new
    {
        Guid = guid,
        Type = "slider",
        NewValue = newValue,
        Min = actualMin,
        Max = actualMax,
        solve_readiness_receipt = receipt,
    }
};
~~~

Finalize the existing `GhSolveOutcome` deterministically: `SolveScheduled == true` marks schedule accepted; `SolverLocked == true` produces terminal `solver_locked`; every other no-schedule outcome produces terminal `unknown` with a stable schedule-unavailable reason. A lifecycle adapter that could not attach also produces terminal `unknown` after the successful mutation; it must never be represented as ready. On a post-reservation mutation exception, call MarkMutationFailed before preserving the existing failure response. Do not issue a second solve.

- [ ] **Step 5: Add exact receipt fence to InspectOutput**

Change managed signature to accept an optional receipt ID and gate before existing output extraction.

~~~csharp
public ApiResponse InspectOutput(string? guid, string? param, string? readinessReceiptId = null)
{
    if (!string.IsNullOrWhiteSpace(readinessReceiptId))
    {
        var gate = _solveReceiptRegistry.CheckFencedRead(readinessReceiptId, gh.Document!);
        if (!gate.Allowed)
            return ReadinessFenceFailure(gate);
    }

    // Existing output extraction remains below this guard.
}
~~~

On success add readiness_fenced, receipt ID, document session, mutation epoch, bound run epoch, and completed run epoch. A fence failure returns no output and never falls back.

- [ ] **Step 6: Replace sessions on document open/new**

At the existing gh_document_open and gh_document_new managed-document calls, notify the readiness partial after the canvas Document assignment. The DocumentChanged callback is the authoritative eager path: it disposes the old subscription, signals waiters, tombstones old records as DocumentReplaced, attaches the new document, and begins a new session. The direct notification is idempotent only as a defensive compatibility path; it must not create a duplicate session when the canvas callback already ran. `EnsureReadinessSession` remains the required lazy backstop for host/UI paths that fail to deliver the expected callback.

- [ ] **Step 7: Run handler and safe-solve tests**

Run:

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GrasshopperHandlerReadinessTests|FullyQualifiedName~GrasshopperDocumentLifecycleSourceTests|FullyQualifiedName~RequestPostMutationSolveTests|FullyQualifiedName~GhSolveReadinessCoordinatorTests" --no-restore
~~~

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

~~~powershell
git add src\Rook\Handlers\GrasshopperHandler.cs src\Rook\Handlers\GrasshopperHandler.Readiness.cs src\Rook.Tests\Handlers\GrasshopperHandlerReadinessTests.cs src\Rook.Tests\Handlers\GrasshopperDocumentLifecycleSourceTests.cs
git commit -m "feat(lm8k): emit and fence GH solve receipts"
~~~

## Task 3: Extend the Native Bridge With an Off-UI Wait Route

**Files:**
- Modify: src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs
- Modify: src/RookNative/Handlers/GrasshopperProxyHandler.cpp
- Modify: src/RookNative/Handlers/GrasshopperProxyHandler.h
- Modify: src/RookNative/RookServer.cpp
- Modify: src/RookNative/RookServer.h
- Test: src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs

**Consumes:** Task 2 managed methods.

**Produces:** ABI v18, GET /gh/solve-readiness, POST /gh/wait-for-solve-readiness, and a bridge wait that cannot deadlock the lifecycle callback.

- [ ] **Step 1: Write failing ABI and non-UI tests**

~~~csharp
[Fact]
public void ReadinessWait_UsesDedicatedOffUiExecutor()
{
    var source = ReadRegistrarSource();
    var method = ExtractMethod(source, "private static int HandleWaitForSolveReadiness");

    Assert.Contains("ExecuteReadinessWaitCallback", method);
    Assert.DoesNotContain("ExecuteApiResponseCallback", method);
    Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", method);
}

[Fact]
public void ReadinessExecutors_RunDirectlyWithoutUiDispatchOrWorkerHop()
{
    var callerThread = Thread.CurrentThread.ManagedThreadId;
    int? statusThread = null;
    int? waitThread = null;

    NativeGhBridgeRegistrar.ExecuteReadinessStatusForTests(() =>
    {
        statusThread = Thread.CurrentThread.ManagedThreadId;
        return new ApiResponse { Success = true, Data = new { status = "ready" } };
    });
    NativeGhBridgeRegistrar.ExecuteReadinessWaitForTests(() =>
    {
        waitThread = Thread.CurrentThread.ManagedThreadId;
        return new ApiResponse { Success = true, Data = new { wait_status = "ready" } };
    });

    Assert.Equal(callerThread, statusThread);
    Assert.Equal(callerThread, waitThread);
}

[Fact]
public void ReadinessRoutes_AppendAbi18Callbacks()
{
    Assert.Contains("private const uint BridgeAbiVersion = 18", ReadRegistrarSource());
    Assert.Contains("public IntPtr GhSolveReadiness;", ReadRegistrarSource());
    Assert.Contains("public IntPtr GhWaitForSolveReadiness;", ReadRegistrarSource());
    Assert.Contains("constexpr uint32_t kGhBridgeAbiVersion = 18", ReadNativeProxySource());
}
~~~

Add parity assertions for C# and C++ struct append order, callback assignment, proxy registration checks, server declarations, and route registrations. Add source guards for both status and wait handlers/executors: neither may call `ExecuteApiResponseCallback`, `DocumentContext.WithDocument`, `RhinoApp.InvokeOnUiThread`, or `Task.Run`. The native callback is already entered from the HTTP worker in `DispatchGrasshopperRoute`; the direct-executor tests prove LM8K does not consume a second worker or route through the main-thread executor.

- [ ] **Step 2: Run native bridge tests and confirm red**

Run:

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~NativeGhBridgeRegistrarTests --no-restore
~~~

Expected: FAIL because ABI v18 and readiness callbacks do not exist.

- [ ] **Step 3: Apply append-only ABI v18**

Bump both bridge version constants from 17 to 18. Append exactly two fields at the tails of both registration structures:

~~~csharp
public IntPtr GhSolveReadiness;
public IntPtr GhWaitForSolveReadiness;
~~~

~~~cpp
GhBridgeCallbackFn gh_solve_readiness = nullptr;
GhBridgeCallbackFn gh_wait_for_solve_readiness = nullptr;
~~~

Root both delegates in NativeGhBridgeRegistrar and assign them in the C# registration initializer. Update the C++ core registration check to require both.

- [ ] **Step 4: Add native route mapping**

Add proxy and server handlers for:

~~~text
GET  /gh/solve-readiness
POST /gh/wait-for-solve-readiness
~~~

Use DispatchGrasshopperRoute for response transport. The accepted JSON names are readiness_receipt_id and timeout_ms.

- [ ] **Step 5: Implement dedicated readiness callbacks**

Add HandleSolveReadiness and HandleWaitForSolveReadiness in NativeGhBridgeRegistrar. The status handler calls a direct `ExecuteReadinessStatusCallback`; the wait handler calls a direct `ExecuteReadinessWaitCallback`. Both execute on the HTTP worker already occupying the native callback and serialize the returned ApiResponse there. The wait executor calls the managed bounded signal wait directly; it does not create a Task.Run hop or impose a second native timeout. The handler validates `timeout_ms` before waiting, so that value is the one and only managed wait bound.

Neither executor may call DocumentContext.WithDocument, RhinoApp.InvokeOnUiThread, ExecuteApiResponseCallback, Task.Run, Thread.Sleep, Task.Delay, an application timer, or a polling loop. The status callback is immediate and also stays on the HTTP worker. Test a maximum valid timeout through the managed handler and assert it reaches the registry unchanged; the Python transport bound is tested separately in Task 4.

- [ ] **Step 6: Run bridge tests and build the layers**

Run the Task 3 test command again, then:

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore
~~~

In a fresh Visual Studio developer shell, run:

~~~powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
~~~

Expected: both exit 0. If the native toolchain is unavailable, record the limitation and do not claim the native build passed.

- [ ] **Step 7: Commit Task 3**

~~~powershell
git add src\Rook\InternalBridge\NativeGhBridgeRegistrar.cs src\RookNative\Handlers\GrasshopperProxyHandler.cpp src\RookNative\Handlers\GrasshopperProxyHandler.h src\RookNative\RookServer.cpp src\RookNative\RookServer.h src\Rook.Tests\InternalBridge\NativeGhBridgeRegistrarTests.cs
git commit -m "feat(lm8k): expose solve readiness bridge routes"
~~~

## Task 4: Add Thin Python MCP Exposure

**Files:**
- Modify: mcp_server/src/rook/server.py
- Create: mcp_server/tests/test_gh_solve_readiness_tools.py
- Modify: mcp_server/tests/test_server_gh_knowledge_wrappers.py

**Consumes:** Task 3 native routes.

**Produces:** gh_solve_readiness, gh_wait_for_solve_readiness, and optional receipt forwarding for gh_inspect_output.

- [ ] **Step 1: Write failing schemas and dispatch tests**

~~~python
@pytest.mark.asyncio
async def test_readiness_tools_advertise_exact_inputs():
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert tools["gh_solve_readiness"].inputSchema["required"] == ["readiness_receipt_id"]
    assert tools["gh_wait_for_solve_readiness"].inputSchema["properties"]["timeout_ms"]["default"] == 10_000

@pytest.mark.asyncio
async def test_wait_dispatches_with_a_transport_deadline_that_covers_the_managed_wait(monkeypatch):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, timeout=None):
        calls.append((route, method, payload, timeout))
        return {"success": True, "data": {"wait_status": "ready"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._call_tool_dispatch(
        "gh_wait_for_solve_readiness",
        {"readiness_receipt_id": "opaque", "timeout_ms": 10_000},
    )

    assert result["success"] is True
    assert calls == [(
        "/gh/wait-for-solve-readiness",
        "POST",
        {"readiness_receipt_id": "opaque", "timeout_ms": 10_000},
        15.0,
    )]

    await server._call_tool_dispatch(
        "gh_wait_for_solve_readiness",
        {"readiness_receipt_id": "opaque", "timeout_ms": 300_000},
    )
    assert calls[-1][-1] == 305.0
~~~

Also test gh_inspect_output with and without receipt ID, and preserve solve_readiness_receipt through the existing gh_set_value knowledge wrapper. The wait tests must prove the default and maximum managed waits receive a Python transport deadline equal to `timeout_ms / 1000 + 5.0` seconds, so Python cannot truncate a valid 300-second receipt wait at bridge.py's 120-second default.

- [ ] **Step 2: Run Python tests and confirm red**

Run:

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_gh_solve_readiness_tools.py mcp_server\tests\test_server_gh_knowledge_wrappers.py -q
~~~

Expected: FAIL because the tools and dispatch arms are absent.

- [ ] **Step 3: Add tools and direct dispatch**

Advertise gh_solve_readiness with required non-empty readiness_receipt_id. Advertise gh_wait_for_solve_readiness with required receipt ID and integer timeout_ms default 10000, minimum 1, maximum 300000.

Define `READINESS_TRANSPORT_GRACE_SECONDS = 5.0`. For `gh_wait_for_solve_readiness`, derive `transport_timeout_seconds = timeout_ms / 1000.0 + READINESS_TRANSPORT_GRACE_SECONDS` after the ordinary tool-schema bounds validation. This is a transport budget only: it never changes receipt status, manages retries, or adds timing policy.

Dispatch directly:

~~~python
case "gh_solve_readiness":
    result = await call_rhino("/gh/solve-readiness", "GET", arguments, port=port)

case "gh_wait_for_solve_readiness":
    timeout_ms = arguments.get("timeout_ms", 10_000)
    transport_timeout_seconds = (
        timeout_ms / 1000.0 + READINESS_TRANSPORT_GRACE_SECONDS
    )
    result = await call_rhino(
        "/gh/wait-for-solve-readiness",
        "POST",
        arguments,
        port=port,
        timeout=transport_timeout_seconds,
    )
~~~

In gh_inspect_output, forward readiness_receipt_id only when supplied. Do not add asyncio.sleep, retry loops, response-state branches, or a Python readiness helper.

- [ ] **Step 4: Run focused Python verification**

Run the Task 4 test command again, then:

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server\src\rook\server.py
~~~

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

~~~powershell
git add mcp_server\src\rook\server.py mcp_server\tests\test_gh_solve_readiness_tools.py mcp_server\tests\test_server_gh_knowledge_wrappers.py
git commit -m "feat(lm8k): expose solve readiness MCP tools"
~~~

## Task 5: Add the Post-Merge-Only Smoke Harness

**Files:**
- Create: mcp_server/tools/gh_solve_readiness_live_smoke.py
- Create: mcp_server/tests/test_gh_solve_readiness_live_smoke.py

**Consumes:** Task 4 public MCP tools.

**Produces:** One deterministic no-model smoke command; it is not run in the implementation PR.

- [ ] **Step 1: Write failing fake-transport smoke tests**

~~~python
async def test_smoke_claim_begins_at_receipted_set_value(tmp_path):
    result = await run_smoke(fake_executor, run_dir=tmp_path)

    assert result["decision"]["accepted"] is True
    assert result["decision"]["baseline_setup_only"] is True
    assert result["decision"]["readiness_fenced"] is True
    assert result["decision"]["observed_output_value"] == 7.5
    assert ("gh_wait_for_solve_readiness", {
        "readiness_receipt_id": "opaque-1",
        "timeout_ms": 10_000,
    }) in fake_executor.calls
    assert all(tool != "gh_solve" for tool, _ in fake_executor.calls_after("gh_set_value"))
~~~

Cover missing receipt, wait timeout, terminal wait outcome, fenced read failure, and mismatched output provenance.

- [ ] **Step 2: Run smoke tests and confirm red**

Run:

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_gh_solve_readiness_live_smoke.py -q
~~~

Expected: FAIL because the smoke harness is absent.

- [ ] **Step 3: Implement the harness**

The script uses only direct GH tools:

~~~text
rhino_ping
-> gh_document_new
-> editable slider 0.0 and offset slider 0.0
-> Addition with editable -> A and offset -> B
-> baseline setup recorded separately
-> gh_set_value(editable, 7.5), require solve_readiness_receipt
-> gh_wait_for_solve_readiness, require ready
-> one fenced gh_inspect_output on Addition R, require 7.5 and exact provenance
~~~

Write bounded manifest.json, baseline_setup_summary.json, mutation_receipt.json, wait_result.json, fenced_output_summary.json, and decision.json under probe_runs/lm8k-timestamp-sha. The script contains no model call, Worker, Planner, sleep, or output-read retry loop.

- [ ] **Step 4: Run smoke fake tests and compile**

Run:

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_gh_solve_readiness_live_smoke.py -q
.\mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server\tools\gh_solve_readiness_live_smoke.py
~~~

Expected: PASS. Add a source assertion that the harness has neither asyncio.sleep nor a loop around gh_inspect_output after gh_set_value.

- [ ] **Step 5: Commit Task 5**

~~~powershell
git add mcp_server\tools\gh_solve_readiness_live_smoke.py mcp_server\tests\test_gh_solve_readiness_live_smoke.py
git commit -m "test(lm8k): add solve readiness smoke harness"
~~~

## Task 6: Full Deterministic Verification and PR Boundary

**Files:**
- Modify only Task 0-5 owning files when deterministic verification finds a defect.
- Do not commit probe_runs artifacts.

**Consumes:** Tasks 0-5.

**Produces:** Deterministic implementation evidence. The live smoke remains a post-merge-only operation.

- [ ] **Step 1: Run managed focused tests**

~~~powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolutionLifecycleAdapterTests|FullyQualifiedName~GhSolveReceiptRegistryTests|FullyQualifiedName~GrasshopperHandlerReadinessTests|FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~GrasshopperDocumentLifecycleSourceTests|FullyQualifiedName~RequestPostMutationSolveTests|FullyQualifiedName~GhSolveReadinessCoordinatorTests" --no-restore
~~~

Expected: PASS.

- [ ] **Step 2: Run Python focused tests**

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_gh_solve_readiness_tools.py mcp_server\tests\test_server_gh_knowledge_wrappers.py mcp_server\tests\test_gh_solve_readiness_live_smoke.py mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
~~~

Expected: PASS. LM8F/I/J remain unchanged and green.

- [ ] **Step 3: Run scope and drift checks**

~~~powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
rg -n "readiness_receipt|gh_wait_for_solve_readiness|gh_solve_readiness" scripts\lm8f_scalar_transform_depth_probe.py scripts\lm8i_affine_publication_shape_support_probe.py scripts\lm8j_affine_support_repeatability_probe.py
~~~

Expected: whitespace clean and no receipt modifications in LM8F/I/J.

- [ ] **Step 4: Prepare, but do not run, the post-merge smoke**

The implementation PR description contains this exact post-merge command:

~~~powershell
.\mcp_server\.venv\Scripts\python.exe mcp_server\tools\gh_solve_readiness_live_smoke.py
~~~

The evidence claim begins at the pending receipt returned by gh_set_value. Baseline fixture setup is recorded separately and is not receipt evidence.

## Plan Self-Review

- **Spec coverage:** Task 0 verifies the real lifecycle API before registry work. Task 1 covers receipts, epochs, exact freshness, waits, expiry, supersession, and eviction. Task 2 instruments only gh_set_value and fences gh_inspect_output. Task 3 provides ABI v18 and the non-UI wait path. Task 4 keeps Python thin. Task 5 provides the post-merge smoke harness. Task 6 protects scope and existing LM8 probes.
- **Placeholder scan:** Every task names files, interfaces, commands, failure behavior, and verification. No task defers a required implementation choice.
- **Type consistency:** The lifecycle adapter feeds the registry; registry snapshots feed the handler; handler methods feed ABI callbacks; Python and the smoke harness use only opaque public receipt IDs.
- **Scope check:** This is one vertical product slice. Broader GH mutator migrations remain outside it.
