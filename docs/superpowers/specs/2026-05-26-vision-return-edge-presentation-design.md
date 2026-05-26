# Deterministic Vision Return-Edge Presentation

## Status

Draft design for a fresh PR from `main` at `6a40e3b`.

This supersedes PR #192 runtime integration as an implementation direction. PR #192 remains useful failed evidence, but must not be deployed again as the basis for live testing.

## Problem

RookVision has a persistent docked/tabbed WebView2 presentation failure. Previous diagnostics showed the panel can go blank around Rhino app deactivation, tab reselection, and gallery/modal workflows.

PR #192 tested a broader Vision presentation coordinator integration and produced two critical observations:

- Hiding the WebView2 controller on app inactive/non-presentable states can leave Vision blank until a later refocus or structural host refresh.
- Leaving the WebView2 controller visible through Rhino inactive/docked host withdrawal can wedge Rhino itself: command input stops responding, close buttons stop responding, and panel repainting smears during resize.

The stronger rule from this evidence is:

> Rook must not issue WebView2 present-side effects while Rhino, the app, or the panel host is inactive or non-presentable.

Present-side effects include:

- setting WebView2 controller visible to `true`
- pushing controller bounds
- calling parent-position notification
- reloading the WebView
- probing the page/DOM/JS as a recovery mechanism

Protective `IsVisible=false` is allowed narrowly during app deactivation or non-presentable host states, because the evidence says it is safer than leaving the WebView2 child surface visibly active through Rhino host withdrawal. It is not a recovery mechanism.

## Goal

Build a Vision-only runtime integration that makes the return edge deterministic:

1. App inactive or host non-presentable never produces `PresentController`.
2. App deactivated may produce protective `HideController`, but never `PresentController`.
3. `HideOnDeactivate` blocks presentation while inactive, but does not clear durable user intent.
4. Active + selected + host-presentable presents exactly once with:
   1. set bounds if needed
   2. set visible true if needed
   3. notify parent position changed
5. Tab reselection, panel shown, app activation, and layout/size updates trigger fresh snapshot evaluation without becoming a retry storm.

This PR is not a diagnostic PR and not a rewrite of Vision.

## Non-Goals

- No Chat or Knowledge Graph runtime behavior changes.
- No user-facing flag, machine-local switch, or environment variable.
- No hot-path file logging.
- No JS/DOM/page probes.
- No WebView reload recovery.
- No recurring idle loop.
- No full replacement of the old shared `WebViewHostVisibilityCoordinator` outside Vision.

## Existing Contract

PR #191 added the condition-driven `WebViewHostPresentationCoordinator` contract. This PR uses that contract, but wires it only through Vision return-edge lifecycle points.

The coordinator remains a pure decision engine:

- It receives a snapshot.
- It returns a decision/action intent.
- It does not call Rhino, Eto, Win32, WebView2, or timers directly.

Runtime integration owns:

- building fresh snapshots at execution time
- serializing evaluation for one Vision surface
- applying action intents in safe order
- scheduling one bounded idle follow-up

## Lifecycle Model

### Durable Intent

`DesiredVisible=false` means durable user/product intent says the surface should not be visible. Examples:

- user hide
- panel closing
- surface disposed

Durable hidden intent enters `Hidden` and may emit `HideController` if a controller is available and visible.

### Temporary Inactive / Host Blockers

Temporary host withdrawal is not durable hidden intent.

Examples:

- Rhino/application deactivated
- Rhino `HideOnDeactivate`
- panel host not selected when selection is required
- host HWND chain hidden
- host client rect zero
- Eto not loaded/visible/sized

These states keep `DesiredVisible=true` when Rook still logically wants Vision open. They enter pending/non-presentable states and may protectively hide the controller, but they must not present.

`HideOnDeactivate` must update panel facts and block presentation while inactive. It must not become `DesiredVisible=false`.

### Visible Any Tab vs Selected Visible

Vision must track two separate panel facts:

- visible in any tab/container
- selected visible tab when selection is required

`ShowPanelReason.Hide` alone is not enough to infer durable user hide. In Rhino docked/tabbed hosts, a tabbed-behind transition may surface as a hide-like lifecycle reason while the panel still exists and remains visible in another tab group. Durable hidden intent requires either panel closing, explicit true hidden state, or a visibility query showing the panel is not visible anywhere.

Selected-tab loss is a host blocker, not durable hidden intent:

```text
VisibleAnyTab=true
PanelSelectedVisible=false
DesiredVisible=true
=> PendingHost + PanelNotSelected
```

Durable hide:

```text
VisibleAnyTab=false
PanelSelectedVisible=false
DesiredVisible=false
=> Hidden / protective hide if needed
```

## Reconcile Triggers

The Vision integration uses a bounded, named set of direct reconcile requests:

- app deactivated
- app activated
- panel shown
- panel hidden
- panel closing
- selection-visible refresh
- size/layout changed

`app deactivated` is not a return edge, but it is a direct reconcile request because it moves Vision into the no-present zone and permits protective hide. Without this, stale active facts could survive until a later event.

`panel hidden` and `panel closing` are authoritative direct reconcile requests. They must update durable facts, increment authoritative generation, and enqueue a no-present reconcile so `DesiredVisible=false` can hide the controller and prevent stale delayed work from presenting later.

### Selection-Visible Refresh Source

`selection-visible refresh` must have a concrete source in the implementation plan. This is the riskiest live edge because the failure reproduces when Vision is tabbed behind another panel and then reselected without an app refocus.

Acceptable sources, in priority order:

1. A Rhino panel event that fires when Vision becomes the selected visible tab.
2. An Eto/Rhino panel shown/visibility event plus an immediate `Panels.IsPanelVisible(..., isSelectedTab: true)` style query.
3. A bounded follow-up query after panel shown/layout/app activation, guarded by the authoritative generation token.

Do not use WebView focus as the primary selection source. If no reliable direct tab-selection event exists, the implementation must use a bounded visibility query/follow-up rather than an unbounded retry loop.

### Idle Follow-Up

Idle is not an independent recurring source.

After a return-edge or layout trigger, Vision may schedule one coalesced Rhino idle reconcile. That idle reconcile:

- captures the current authoritative generation
- is ignored if superseded
- is ignored if disposed
- is ignored if durable desired visibility is false
- builds a fresh snapshot at execution time
- presents only if the host is presentable

There is at most one pending idle follow-up per Vision surface.

Idle mechanics are one-shot:

- subscribe or schedule once
- execute at most once
- detach/clear immediately after execution

There must be no persistent `RhinoApp.Idle` subscription for this feature and no recurring idle source.

## Authoritative Generation

Each Vision surface owns a monotonically increasing authoritative generation.

Generation increments on:

- durable hide
- close/dispose
- app active/inactive facts change
- selected/tab-visible facts change
- new authoritative panel facts

Generation does not automatically increment for every size/layout event. Size/layout may request reconcile and schedule idle, but should not cancel every pending idle unless it updates authoritative facts. This avoids resize noise canceling the one useful follow-up.

Delayed work captures a generation token. When delayed idle executes:

```text
if capturedGeneration != currentGeneration:
    no-op
if disposed:
    no-op
if DesiredVisible == false:
    no-op
build fresh snapshot
if host presentable:
    present once
else:
    no-op
```

This protects against stale return-edge work presenting after hide, tab-away, close, or newer panel facts.

### Disposed Snapshot

PR #191 defines `Snapshot.Disposed=true` as terminal forever. Runtime integration must only pass `Disposed=true` when the Vision surface is actually disposed, closing, or otherwise unrecoverable.

Do not use `Disposed=true` for transient states such as `_webView == null`, controller not created yet, or WebView not yet loaded. Those states should be represented by controller/host readiness facts so they can recover normally.

## Action Policy

### No-Present Zone

When app inactive or host non-presentable:

- do not set controller visible true
- do not set bounds
- do not notify parent position changed
- do not reload
- do not run JS/page probes

Protective `HideController` is allowed when:

- controller is available
- controller is visible
- the blocker is app inactive, temporary deactivate, or a physical non-presentable host state

### Present Edge

When the fresh execution-time snapshot says:

- desired visible
- app active
- panel visible
- selected if required
- Eto loaded
- Eto visible
- Eto size nonzero
- parent window present
- HWND chain visible
- HWND client rect nonzero
- controller available
- controller parent window present

then Vision may emit one `PresentController` action.

Action application order is fixed:

1. set bounds first if needed
2. set visible true if needed
3. notify parent position changed last

If the controller is already visible and bounds already match, entering the present edge still notifies once. Repeated healthy presenting is a no-op.

## Integration Boundary

This PR should integrate Vision only.

Expected runtime boundary:

- `RookVisionPanel` / Vision panel lifecycle supplies authoritative panel facts.
- `VisionWebSurface` opts into the return-edge presentation path.
- `RookWebSurface` owns Eto/WebView2/HWND snapshot building and action application.
- `WebViewHostPresentationCoordinator` remains the decision engine.

Chat and Knowledge Graph remain on the existing behavior and serve as live controls.

When Vision is on the return-edge path, the old Vision call path must not also call `_surface.ReconcileHostVisibility(...)`. Old and new visibility systems fighting each other is explicitly out of scope and unsafe. Vision lifecycle decisions may still close/forget surfaces, but WebView2 visibility/presentation must flow through `ReconcileHostPresentation(...)` only.

## Diagnostics

Do not add hot-path file logging.

If evidence is needed, use a memory-only ring and explicit dump command only. Ring entries must be plain DTOs and must not store UI objects, controller instances, HWND wrappers, exceptions with stack traces, or DOM state.

This PR should prefer passing behavior with diagnostics off. Diagnostics must not be part of normal recovery.

## Automated Tests

Required tests:

- `AppInactive_DoesNotPresent`
- `NonPresentableHost_DoesNotPresent`
- `Inactive_WithVisibleController_MayProtectivelyHide`
- `AppDeactivated_VisibleController_HidesWithoutPresenting`
- `HideOnDeactivate_DoesNotClearDesiredVisible`
- `PanelHiddenHide_WhenVisibleAnyTab_DoesNotClearDesiredVisible`
- `PanelHiddenHide_WhenNotVisibleAnyTab_ClearsDesiredVisible`
- `ActivatedHostReady_PresentsOnce`
- `TabbedBehindThenReselected_PresentsWithoutAppRefocus`
- `LayoutThenIdle_WhenAlreadyHealthy_NoAction`
- `PresentAction_OrderIsBoundsVisibleNotify`
- `Disposed_PreventsDelayedReturnEdge`
- `DelayedIdleAfterHide_DoesNotPresent`
- `StaleIdleAfterNewerPanelFacts_DoesNotPresent`
- `PanelHidden_DurableHide_UpdatesFactsAndDoesNotAllowStaleIdlePresent`
- `VisionPanel_DoesNotCallLegacyReconcileHostVisibility`
- `SizeLayout_DoesNotInvalidateAuthoritativeGenerationByItself`

Tests should cover the generation/token boundary, not only coordinator source strings.

## Live Validation

Live validation starts with diagnostic flags unset:

```powershell
ROOK_ENABLE_VISION_DARK_DIAGNOSTICS
ROOK_ENABLE_WEBVIEW_FOCUS_DIAGNOSTICS
ROOK_PANEL_LIFECYCLE_TRACE
```

Required matrix:

- Vision docked selected tab: repeated click-away/return cycles.
- Vision tabbed behind another panel, then reselect Vision without relying on another app refocus.
- Vision gallery/modal path.
- Vision floating/undocked.
- Chat and Knowledge Graph in the same Rhino session as old-path controls.

Failure rules:

- If Rhino becomes unresponsive, stop testing and roll back the deployed runtime to `main`.
- If Vision goes dark, do not click inside Vision before collecting available state evidence.
- Do not mark the PR ready until live docked/tabbed validation passes.

## Success Criteria

- No Rhino UI freeze, command-line lock, close-button failure, or smeared repaint behavior.
- No persistent Vision dark state in docked/tabbed return-edge scenarios.
- App inactive/non-presentable states never produce present-side effects.
- Active selected presentable return edge emits exactly one present action.
- Delayed idle cannot present stale state after hide, tab-away, close, or newer authoritative facts.
- Chat and Knowledge Graph do not regress.
