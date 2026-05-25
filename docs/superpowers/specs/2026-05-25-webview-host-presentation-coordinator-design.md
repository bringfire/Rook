# WebView Host Presentation Coordinator Design

## Context

Rook's WebView panels run inside a layered desktop host:

- Rhino panel and dockbar lifecycle.
- Eto controls and parent windows.
- Win32 HWND parent/ancestor visibility.
- WebView2 controller and child-window presentation.
- The browser DOM hosted by WebView2.

The dark RookVision panel bug has shown that these layers can disagree. A page
can remain loaded and alive, WebView2 can report a visible controller, and Rhino
can still have a hidden or stale native parent chain that prevents pixels from
presenting. Docking or reparenting the panel can revive the surface, which points
to host presentation state rather than a dead DOM or dead Rook runtime.

Verbose diagnostics also appear to perturb the bug. They can add delay, force
WebView2 COM/property synchronization, trigger JavaScript layout reads, add UI
thread dispatches, or change file I/O and GC timing. The durable fix must not
depend on diagnostics, retries, reloads, or timing side effects.

## Goal

Add a small, testable state machine that defines when a WebView2 surface is
allowed to present inside a Rhino/Eto host.

The first PR is intentionally a contract and skeleton PR:

- Add the coordinator, snapshot, decision, state, action, and reason types.
- Add fake-driven unit tests for state transitions and action flags.
- Add this design note.
- Do not wire the coordinator into runtime behavior yet.
- Do not add dry-run runtime logging.
- Do not replace `WebViewHostVisibilityCoordinator` yet.

Runtime integration belongs in a follow-up PR after the contract is reviewed.

## Old vs. New Model

This is not a second version of `WebViewHostVisibilityCoordinator`.

The old coordinator is an event-driven visibility queue. It tracks desired
visible/hidden state, coalesces requests, and schedules WebView2 `IsVisible`
changes based on callback order and shallow host visibility facts.

The new coordinator is a condition-driven presentation gate. It receives a
complete supplied snapshot of Rhino panel facts, Eto host facts, Win32 HWND facts,
and WebView2 controller facts. It emits state transitions and action intent only
when the snapshot proves that the host is presentable.

The unit of correctness changes from:

```text
An activation/show callback happened, so try to show WebView2.
```

to:

```text
The desired state is visible, the host is physically presentable, and the
controller is ready, so perform one idempotent presentation action.
```

## Ownership Boundaries

The coordinator must not call Rhino, Eto, Win32, or WebView2 APIs directly.

Responsibilities:

```text
HostedPanelLifecycleAdapter / panel layer:
- interprets Rhino panel reasons
- knows document serial
- knows panel visible / selected-visible facts
- knows whether a hide is temporary deactivate vs. durable hide

RookWebSurface / host probe layer:
- knows Eto control state
- knows WebView2 controller state
- knows native HWND parent-chain state

WebViewHostPresentationCoordinator:
- receives one combined snapshot
- decides state transition
- emits action intent
- does not query Rhino, Eto, Win32, or WebView2 itself
```

The coordinator lives in `Rook.UI.Web`, near `RookWebSurface`, because it owns
WebView host presentation semantics rather than Rhino panel ownership.

## Files

First PR:

```text
src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs
src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs
docs/superpowers/specs/2026-05-25-webview-host-presentation-coordinator-design.md
```

The coordinator file may contain all internal records/enums in the first PR. If
it becomes hard to review, records can be split into separate files before code
review.

## Types

All types are internal.

```csharp
namespace Rook.UI.Web;

internal sealed class WebViewHostPresentationCoordinator;
internal sealed record WebViewHostPresentationSnapshot;
internal sealed record WebViewHostPresentationDecision;
internal enum WebViewHostPresentationState;
internal enum WebViewHostPresentationAction;
internal enum WebViewHostNotPresentableReason;
```

The coordinator API is a single evaluation path:

```csharp
WebViewHostPresentationDecision Evaluate(
    WebViewHostPresentationSnapshot snapshot,
    string reason);
```

The coordinator retains small previous state:

```csharp
private WebViewHostPresentationState _state;
```

No timers, polling, Rhino objects, Eto controls, WebView2 objects, HWND handles,
or logging sinks are stored.

## Snapshot

The snapshot is plain data supplied by adapters.

Required fields:

```text
Disposed
DesiredVisible

AppActive
TemporaryDeactivateHidden
PanelVisible
RequiresSelectedPanel
PanelSelectedVisible

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

`ControllerBoundsMatchHostTarget` is explicit. The coordinator does not infer
the target rectangle from raw dimensions in PR 1. The host adapter will later own
the comparison between WebView2 controller bounds and the current Eto/host target
bounds.

`EtoWidth <= 0` or `EtoHeight <= 0` is a host blocker. Controller bounds mismatch
is not a blocker; it is a corrective action once the host and controller are
otherwise usable.

`Disposed=true` is terminal. Once the coordinator enters `Disposed`, later
snapshots must not leave it.

## States

```text
Hidden
PendingHost
PendingController
Presenting
Disposed
```

Meaning:

- `Hidden`: Rook does not currently want the surface visible.
- `PendingHost`: Rook wants the surface visible, but Rhino/Eto/Win32 host gates
  do not currently allow presentation.
- `PendingController`: the host is presentable, but WebView2 controller gates do
  not currently allow presentation.
- `Presenting`: all known host/controller gates passed; the coordinator has
  emitted or maintained presentation intent. This does not prove pixels are
  visible on screen.
- `Disposed`: no further side effects.

Diagnostic precision belongs in `WebViewHostNotPresentableReason`, not in a
larger state set.

## Actions

```text
None
HideController
PresentController
```

Decision flags:

```text
ShouldSetControllerBounds
ShouldSetControllerVisible
ShouldNotifyParentPositionChanged
```

Rules:

- `PresentController` always implies
  `ShouldNotifyParentPositionChanged=true`.
- `ShouldSetControllerBounds=true` when
  `ControllerBoundsMatchHostTarget=false`.
- `ShouldSetControllerVisible=true` when `Action=PresentController` and
  `ControllerVisible=false`.
- `HideController` does not use `ShouldSetControllerVisible`; the action itself
  means the controller should be hidden.
- Transitioning into `Presenting` emits `PresentController` and notifies parent
  position even when bounds already match and the controller is already visible.
- Repeated healthy `Presenting` emits `None`.
- Repeated `Presenting` with controller drift emits `PresentController` with
  only the needed correction flags plus parent-position notification.

## Host Gate Priority

Gate priority is deterministic. The first matching blocker wins.

Intent/terminal gates:

```text
Disposed
DesiredVisible=false
```

Host blockers:

```text
TemporaryDeactivateHidden when AppActive=false
AppInactive
PanelNotVisible
PanelNotSelected when RequiresSelectedPanel=true
EtoNotLoaded
EtoNotVisible
EtoSizeZero
ParentWindowMissing
HwndChainHidden
HwndClientRectZero
```

Controller blockers:

```text
ControllerUnavailable
ControllerParentWindowMissing
```

`TemporaryDeactivateHidden` is not durable hidden state. It blocks only while
`AppActive=false`. When `AppActive=true`, the coordinator ignores temporary-hide
history and evaluates the physical host facts.

`ControllerBoundsMismatch` is intentionally not a not-presentable reason. Bounds
mismatch is corrected by presentation action after the host and controller gates
pass.

## Transition Rules

Summary:

```text
Disposed => Disposed + None forever
DesiredVisible=false => Hidden + HideController if controller visible
DesiredVisible=true + host blocker => PendingHost
DesiredVisible=true + host blocker + controller visible => PendingHost + HideController
Host ready + controller unavailable => PendingController + None
Host ready + controller parent missing => PendingController + None
Host ready + controller ready => Presenting
```

Important transitions:

```text
Presenting -> PendingHost:
  protective transition when the host becomes non-presentable.
  HideController if ControllerVisible=true.
  Do not clear DesiredVisible.
  Do not enter Hidden.
  Do not reload.

PendingHost -> Presenting:
  when host facts recover and controller gates pass.
  Emit PresentController and notify parent position once.

PendingController -> Presenting:
  when controller facts recover while host remains presentable.
  Emit PresentController and notify parent position once.
```

Tab policy:

```text
User hide / panel closing / true closed:
  DesiredVisible=false
  State=Hidden
  Action=HideController if needed

Tab unselected while logically open:
  DesiredVisible=true
  RequiresSelectedPanel=true
  PanelSelectedVisible=false
  State=PendingHost
  NotPresentableReason=PanelNotSelected
  Action=HideController if ControllerVisible=true
```

This keeps user intent separate from temporary host eligibility.

## Event Model

The coordinator is event-driven, not polling.

Adapters should call `Evaluate` only when a real lifecycle event or stabilization
boundary produces a new snapshot, for example:

```text
PanelShown
PanelHidden
ApplicationActivated
ApplicationDeactivated
WebViewCreated
WebViewLoaded
WebViewShown
WebView2ControllerAvailable
SizeChanged / layout-related event if available
RhinoIdle after activation/show/defer
Disposed
```

A bounded `AsyncInvoke` or `RhinoApp.Idle` evaluation is acceptable as a
stabilization boundary. A repeating timer loop is not part of the durable design.

## First PR Tests

Coordinator tests should use fake snapshots only. They must not instantiate
Rhino, Eto, Win32, or WebView2 objects.

Required scenarios:

```text
UserHide_HidesAndEntersHidden
PanelNotSelected_WhenSelectionRequired_EntersPendingHost
PanelNotSelected_WithVisibleController_HidesControllerButKeepsDesiredVisible
PanelSelectedAgain_WithHostReady_Presents

InactiveTemporaryDeactivate_BlocksPresentation
ActiveTemporaryDeactivateWithHostReady_Presents
ActiveTemporaryDeactivateWithHostStillHidden_PendingHost_HwndChainHidden

HostReady_ControllerBoundsMismatch_PresentsAndRequestsBoundsCorrection
HostReady_ControllerHiddenAndBoundsMismatch_PresentsWithBothCorrections
TransitionIntoPresenting_NotifiesParentEvenWhenAlreadyVisibleAndBoundsMatch
RepeatedPresentingHealthy_NoAction
RepeatedPresentingBoundsMismatch_PresentsWithBoundsAndNotify
RepeatedPresentingControllerHidden_PresentsWithVisibleAndNotify

PresentingToPendingHost_WithVisibleController_HidesController
PresentingToPendingHost_WithHiddenController_NoAction
PendingHostToPresenting_WhenHostRecovers_PresentsAndNotifies

ControllerUnavailableOnlyAfterHostPasses
ControllerUnavailable_KeepsPendingControllerWithoutThrowing
ControllerParentWindowMissing_KeepsPendingController

Disposed_IsTerminal
HideAfterPendingVisible_CancelsPendingShow

TemporaryDeactivateWinsOverAppInactive
PanelNotSelectedIgnoredWhenSelectionNotRequired
EtoSizeZeroWinsBeforeParentWindowMissing
```

## Non-Goals

PR 1 does not:

- Wire the coordinator into `RookWebSurface`.
- Add dry-run runtime evaluation.
- Add verbose diagnostics.
- Add hot-path file I/O.
- Replace `WebViewHostVisibilityCoordinator`.
- Reload WebView2 as normal recovery.
- Add polling or fixed sleep loops.
- Change Vision, Chat, or Knowledge Graph runtime behavior.

## Follow-Up PR

The follow-up integration PR should:

```text
RookWebSurface builds Eto/WebView2/HWND snapshot facts.
Panel lifecycle supplies upstream Rhino panel facts.
Coordinator evaluates.
Action sink applies WebView2 bounds / visible / notify side effects.
Minimal always-on state logging records decisions without perturbing timing.
```

The follow-up live validation matrix should include:

```text
Vision docked, click away, return.
Vision floating, click away, return.
Vision tabbed behind another panel, return.
Vision selected tab, return.
Gallery/modal open, click away, return.
Knowledge Graph and Chat as negative controls.
Dock/undock after dark state, to verify whether structural reparenting is still needed.
```

Success is not "the bug did not happen once." Success is:

```text
When Rhino/Eto host is not presentable, Rook does not touch WebView2 presentation.
When host becomes presentable, Rook performs one clean presentation action.
If the panel still goes dark, the decision evidence shows that all host gates
passed and the next investigation should move to WebView2 compositor or DOM
rendering.
```
