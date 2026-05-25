# Vision WebView Host Presentation Integration Design

## Context

PR #191 added a condition-driven `WebViewHostPresentationCoordinator` contract.
It is pure snapshot-in / decision-out and is not wired into runtime behavior.

The next slice is the first runtime integration for the RookVision dark-panel
bug. The core hypothesis is that Rook should not present WebView2 simply because
Rhino/Eto emitted a show, activation, or WebView event. Rook should present only
when a fresh execution-time snapshot proves that the Rhino/Eto/Win32/WebView2
host is presentable.

The integration must not reintroduce the diagnostic side effects that made this
bug hard to reproduce. Hot-path file logging, JavaScript probes, delayed
diagnostic callbacks, and runtime feature flags are out of scope.

## Scope

PR #192 makes the coordinator path default-on for Vision only.

Chat and Knowledge Graph remain on the existing `WebViewHostVisibilityCoordinator`
path and serve as live controls during validation. There is no environment
variable, user setting, machine-local flag, or hidden runtime toggle for Vision.
Rollback is by reverting code, not by switching runtime modes.

`RookWebSurface` may expose an internal migration seam such as:

```csharp
protected virtual bool UseHostPresentationCoordinator => false;
```

`VisionWebSurface` overrides it to `true`. Chat and Knowledge Graph inherit
`false`. This policy is an internal code-ownership seam, not a user- or
machine-configurable feature flag.

Validation must compare Vision on the coordinator path against Chat/KG on the
old path under the same Rhino session, with relevant diagnostic flags off first.

## Non-Goals

PR #192 does not:

- Move Chat or Knowledge Graph to the coordinator path.
- Add a runtime opt-out switch for Vision.
- Add hot-path file logging.
- Add JavaScript layout, DOM, or visibility probes.
- Add polling loops.
- Reload or navigate WebView2 as normal recovery.
- Add a Vision UI button for diagnostics.
- Reuse the earlier verbose diagnostics spike as production behavior.

## Runtime Architecture

`RookWebSurface` owns the shared integration plumbing because it already knows:

- the Eto `WebView`
- WebView2 controller access
- controller bounds / visibility operations
- parent-position notification
- WebView lifecycle events

The panel layer keeps supplying presentation intent. The old API remains:

```csharp
internal void ReconcileHostVisibility(bool visible, string reason)
```

That overload preserves current behavior for non-coordinator surfaces.

Coordinator-enabled surfaces use a richer facts overload:

```csharp
internal void ReconcileHostVisibility(WebViewHostPanelPresentationFacts facts)
```

When `UseHostPresentationCoordinator == false`, the current old-path behavior
remains unchanged.

When `UseHostPresentationCoordinator == true`, `RookWebSurface` schedules a
serialized UI callback, builds a fresh snapshot inside that callback, evaluates
`WebViewHostPresentationCoordinator`, applies the action intent, and appends a
memory-only ring entry.

Snapshot building must happen at execution time, not request time. If a request
is scheduled via `AsyncInvoke`, WebView/Eto/HWND/controller facts are captured
immediately before `Evaluate`.

## Panel Facts Boundary

`RookWebSurface` must not reconstruct Rhino panel policy from reason strings.

Add a plain-data input type in `Rook.UI.Web`:

```csharp
internal sealed record WebViewHostPanelPresentationFacts
{
    public bool DesiredVisible { get; init; }
    public bool AppActive { get; init; }
    public bool TemporaryDeactivateHidden { get; init; }
    public bool PanelVisible { get; init; }
    public bool RequiresSelectedPanel { get; init; }
    public bool PanelSelectedVisible { get; init; }
    public string Reason { get; init; } = "";
}
```

Vision should use the facts overload. The existing bool overload remains the
old compatibility path.

`DesiredVisible=false` represents durable hide or close intent. Temporary
deactivate and tab-unselected states must keep `DesiredVisible=true` and express
the blocker through `TemporaryDeactivateHidden`, `PanelVisible`, or
`PanelSelectedVisible`.

The first source for Vision facts is the existing panel lifecycle path. If the
current `HostedPanelLifecycleAdapter` does not expose enough facts, add a small
Vision-specific adapter method or facts callback rather than parsing reason
strings inside `RookWebSurface`.

Application active state must be fresh at execution time. The facts object may
carry `AppActive`, but coordinator snapshot construction should refresh it in
the serialized callback, or otherwise revalidate panel facts at that point.

## Host Snapshot And Action Sink

`RookWebSurface` adds its own execution-time facts to the panel facts:

```text
Disposed
EtoLoaded
EtoVisible
EtoWidth
EtoHeight
ParentWindowPresent
HwndChainVisible
HwndClientRectNonZero
ControllerAvailable
ControllerParentWindowPresent
ControllerVisible
ControllerBoundsMatchHostTarget
```

Build the snapshot with one local controller reference and pass that same
reference into the action sink for the current callback. This avoids unnecessary
drift between "controller was available" and "controller action target."

If action application still cannot proceed because the target shifted, no-op and
record a short memory-ring action result.

`ControllerBoundsMatchHostTarget` means the current controller bounds match the
exact target bounds that the action sink would set in this callback. PR #192
does not introduce new DPI scaling behavior unless the existing bounds path
already handles it.

HWND probing should be minimal and WebView2/Windows guarded. Probe failures must
be conservative false facts. Unknown state must never force `PresentController`;
it should land in `PendingHost` or `PendingController`.

For `PresentController`, action order is fixed:

```text
1. Set bounds first if needed.
2. Set visible true if needed.
3. NotifyParentWindowPositionChanged last.
```

For `HideController`, only set visible false. No reload, navigation, DOM read,
JS probe, or file I/O.

## Event And Serialization Model

The coordinator is stateful and not thread-safe. For a given Vision surface,
exactly one coordinator evaluation may run at a time, and every evaluation
builds a fresh execution-time snapshot immediately before action application.

Use the existing WebView host visibility scheduling shape as the serialized
owner:

```text
ReconcileHostVisibility(facts)
  -> record latest authoritative panel facts
  -> schedule one UI callback if not already queued
  -> inside callback:
       drain latest facts
       refresh execution-time state
       build snapshot
       Evaluate(snapshot, reason)
       apply action intent
       append ring entry
```

Lifecycle sources that may request reconciliation:

```text
Vision PanelShown / PanelHidden / PanelClosing
WebView Shown
WebView GotFocus
ApplicationActivated
ApplicationDeactivated
WebView2 controller configured
Vision UI operation completed refresh
SizeChanged / layout-related event if available and low-risk
```

No polling loop is allowed. A bounded UI callback is allowed only as the
serialization and lifecycle-stabilization boundary.

Coalescing must preserve durable hide over stale visible refreshes. If
`PanelClosing` or durable user hide arrives, a later stale activation/show
refresh must not overwrite it back to `DesiredVisible=true` unless the panel
lifecycle explicitly reports the surface visible again. "Latest facts wins" is
acceptable only when the latest facts come from the authoritative lifecycle
layer.

`ApplicationDeactivated` must not fight Rhino. It may enqueue a reconcile with
`AppActive=false`; the coordinator should normally land in `PendingHost` and
hide only if the controller is available and visible. Presentation waits until
`AppActive=true` and host facts pass.

`GotFocus` may be a request source, but it is not a primary recovery mechanism.
If it fires repeatedly, coalescing and idempotent `Presenting` decisions must
keep it from spamming WebView2 actions.

## In-Memory Ring Buffer

Add a Vision-only in-memory presentation ring. Normal lifecycle appends only
plain DTO entries and never writes files.

Ring entries contain strings, bools, ints, enums, and timestamps only. They must
not store controller objects, Eto controls, HWND handles, exceptions, or any
references to UI objects.

Each entry includes:

```text
sequence
utc timestamp
elapsed milliseconds if available
event reason
oldState
newState
action
notPresentableReason
desiredVisible
appActive
temporaryDeactivateHidden
panelVisible
requiresSelectedPanel
panelSelectedVisible
etoLoaded
etoVisible
etoWidth
etoHeight
parentWindowPresent
hwndChainVisible
hwndClientRectNonZero
controllerAvailable
controllerParentWindowPresent
controllerVisible
controllerBoundsMatchHostTarget
shouldSetControllerBounds
shouldSetControllerVisible
shouldNotifyParentPositionChanged
actionResult
threadId
```

`actionResult` is short and sanitized:

```text
none
applied
skipped-controller-unavailable
set-bounds-failed:<ExceptionType>
set-visible-failed:<ExceptionType>
notify-parent-failed:<ExceptionType>
```

No stack traces are stored in the ring.

Append is allocation-light and non-throwing. It may allocate the entry object,
but it must not do reflection, file access, JSON serialization, stack trace
capture, or expensive formatting. Serialize only in the dump command.

Use a fixed-size capacity such as 256 entries. Use a lock around append and
snapshot. Dumping must lock only long enough to copy entries into an array; JSON
serialization and file I/O happen after releasing the lock.

## Dump Command

Add a Rhino command:

```text
RookDumpVisionPresentationState
```

Behavior:

```text
- reads the Vision presentation ring
- snapshots the ring quickly under lock
- writes JSON to %TEMP%\rook\vision-presentation-state-<timestamp>.json
- includes a dump-requested marker or metadata timestamp
- writes a valid dump even when no Vision surface exists
- prints the file path to Rhino command line
- never refreshes, focuses, shows, hides, reloads, or otherwise touches the panel
```

Dump JSON metadata includes:

```text
rookVersion
rhinoVersion
processId
threadId
dumpRequestedUtc
surfacePresent
entryCount
capacity
entries
```

The command is explicit and low-frequency. It is intentionally outside the
WebView page so dumping does not click, focus, lay out, or repaint the Vision
DOM.

## Automated Tests

Automated tests should cover integration contracts that do not require live
Rhino:

```text
VisionWebSurface opts into coordinator path.
Chat/KG surfaces do not opt in.
No environment variable or user setting controls coordinator use.
Facts overload is used by the Vision panel path.
Old bool overload remains available and preserves old-path behavior for non-coordinator surfaces.
Coordinator path builds snapshot at execution time, not request time.
Durable hidden facts are not overwritten by stale visible refreshes.
Action sink order is bounds -> visible -> notify.
Hide action requires controller availability.
Ring append stores plain DTO fields only.
Dump command writes valid JSON with surfacePresent=false when no Vision surface exists.
Dump command snapshots ring before file I/O.
```

Run at minimum:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore
git diff --check
```

## Live Validation

Live validation must start with relevant diagnostics flags unset:

```text
ROOK_ENABLE_VISION_DARK_DIAGNOSTICS unset
ROOK_ENABLE_WEBVIEW_FOCUS_DIAGNOSTICS unset
ROOK_PANEL_LIFECYCLE_TRACE unset
```

Then test Vision with the coordinator path and Chat/KG on the old path in the
same Rhino session:

```text
Vision docked, click away, return: 10 cycles.
Vision floating, click away, return: 10 cycles.
Vision selected tab, click away, return: 10 cycles.
Vision tabbed behind another panel, return: 10 cycles.
Vision gallery modal open, click away, return: repeated cycles, more than one.
Chat and Knowledge Graph under the same session as controls.
```

For each live test record:

```text
Rhino version
WebView2 runtime version
Rook build/commit
panel mode: docked/floating/tabbed
whether Vision was selected or background tab
whether dump was taken
```

Chat/KG are negative controls for broad WebView breakage. They do not prove the
Vision fix.

If the dark state appears or behavior is suspicious, run:

```text
RookDumpVisionPresentationState
```

Do not click inside Vision to dump. Inspect whether coordinator decisions stayed
`PendingHost` while the host was invalid and emitted exactly one
`PresentController` when the host became presentable.

Successful validation means:

```text
No dark panel after repeated cycles with diagnostics flags off, and if
suspicious behavior appears, dump entries match the state-machine contract.
```

## Success Criteria

PR #192 succeeds if:

- Vision uses the coordinator path by default.
- Chat and Knowledge Graph remain on the old path.
- No hot-path file logging or JS probes are added.
- No runtime flag or user setting controls the Vision coordinator path.
- If host facts are not presentable, no `PresentController` action is emitted.
- Once host facts become presentable, one clean `PresentController` action is
  emitted with bounds, visible, notify ordering.
- `RookDumpVisionPresentationState` produces evidence without touching panel
  state.
- Full managed tests pass.

If the panel still goes dark after all gates pass, the dump evidence should move
the next investigation to WebView2 compositor or DOM rendering rather than
Rhino/Eto host lifecycle.
