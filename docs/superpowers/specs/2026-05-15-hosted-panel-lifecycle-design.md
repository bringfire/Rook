# Hosted Panel Lifecycle Design

Date: 2026-05-15

## 1. Problem

Rook has recurring blank-panel failures across hosted browser/native UI surfaces. The issue first showed up in Rook Vision and later reproduced in the Claude Code tab inside Rook Chat. In live use, the Claude Code tab went blank, then docking the Rhino panel caused the text to return. That points to a Rhino/Eto panel lifecycle, reparenting, layout, or visibility synchronization problem rather than a failed chat process or MCP route.

Recent fixes added WebView-focused visibility recovery in `RookWebSurface`, including controller visibility synchronization and parent-position notifications. Those helped specific symptoms, but they do not model the higher-level Rhino panel lifecycle. Today, `RookChatPanel`, `RookVisionPanel`, and `KnowledgeGraphPanel` still translate every `PanelHidden` event into a hosted-surface hidden request. Rhino's `ShowPanelReason.HideOnDeactivate` is explicitly temporary, so treating it like real hide can strand hosted native/browser controls in a stale hidden or zero-size state.

The fix should be a lifecycle/layout fix, not another repaint workaround or WebView2 reflection patch.

## 2. Relevant Rhino/Eto Guidance

The design follows the official Rhino/Eto guidance:

- Rhino tabbed panels reuse the same panel instance and reparent it as the host changes.
- Eto `Control.Visible = false` can remove controls from layout calculation and event processing.
- `Control.Parent` and `Control.ParentWindow` are only reliable after the control is hosted.
- `ShowPanelReason.HideOnDeactivate` and `ShowPanelReason.ShowOnDeactivate` represent temporary deactivate/reactivate transitions.
- `Panels.IsPanelVisible(panelType, isSelectedTab: true)` exists to distinguish "panel exists in a visible dock group" from "this panel tab is selected and actually visible."
- Async UI work must be exception-contained and must not block Rhino with `.Result`, `.Wait()`, or `.GetAwaiter().GetResult()`.

## 3. Goals

- Introduce a shared hosted panel lifecycle contract used by Chat, Claude Code, Vision, and Knowledge Graph surfaces.
- Keep lifecycle truth above `RookWebSurface`; WebView code applies final decisions but does not decide panel lifecycle.
- Treat `HideOnDeactivate` as temporary and never as hosted-surface teardown.
- Keep resource cleanup separate from visibility.
- Handle docking, floating, reparenting, temporary zero-size layout, and Rhino dock-tab selection explicitly.
- Provide temporary, gated diagnostics for live validation.
- Keep core decision logic unit-testable without Rhino loaded.

## 4. Non-Goals

- Do not replace `RookWebSurface`.
- Do not rewrite Chat, Vision, or Knowledge UI.
- Do not add another WebView repaint/reload workaround.
- Do not reload or recreate hosted browser surfaces as part of normal panel visibility reconciliation.
- Do not make diagnostics required for correct behavior.
- Do not introduce new external dependencies.

## 5. Architecture

Add a lifecycle layer above `RookWebSurface`:

```text
Rhino IPanel events + tab state + Eto host facts
        |
        v
PanelLifecycleFacts
        |
        v
HostedPanelLifecycleCoordinator
        |
        v
HostedSurfaceDecision
        |
        v
RookWebSurface.ReconcileHostVisibility(...)
```

`HostedPanelLifecycleCoordinator` is pure decision logic. It must be unit-testable without Rhino loaded. The pure types and coordinator must not reference `Rhino.*`, `Eto.*`, or WebView2 types.

`HostedPanelLifecycleAdapter` is the Rhino/Eto boundary. It gathers facts from panel events, tab selection, `Panels.IsPanelVisible`, parent/window attachment, and control size, then passes those facts into the coordinator. It owns bounded deferred scheduling and diagnostics.

`RookWebSurface.ReconcileHostVisibility(bool visible, string reason)` remains a low-level sink. It applies final visibility/positioning decisions. It is not the lifecycle authority.

## 6. Files And Namespaces

New lifecycle code should live under:

```text
src/Rook/UI/Panels/
```

The coordinator is not WebView-specific, so it should not live under `src/Rook/UI/Web/`.

Expected types:

```csharp
internal enum HostedPanelLifecycleReason
{
    Unknown,
    Show,
    Hide,
    HideOnDeactivate,
    ShowOnDeactivate
}

internal enum HostedSurfaceAction
{
    None,
    Show,
    Hide,
    Defer,
    Close
}

internal sealed class PanelLifecycleFacts
{
    public bool PanelReportedVisible { get; init; }
    public HostedPanelLifecycleReason LastReason { get; init; }
    public bool IsSelectedTab { get; init; }
    public bool IsRhinoSelectedPanelVisible { get; init; }
    public bool IsAttachedToParentWindow { get; init; }
    public bool HasNonZeroClientSize { get; init; }
    public bool IsClosing { get; init; }
    public int DeferAttempt { get; init; }
}

internal sealed class HostedSurfaceDecision
{
    public HostedSurfaceAction Action { get; init; }
    public string Reason { get; init; } = "";
    public int DeferAttempt { get; init; }
}

internal sealed class HostedPanelLifecycleCoordinator
{
    public HostedSurfaceDecision Decide(PanelLifecycleFacts facts);
}
```

The Rhino/Eto adapter should be constructed with the panel type so it can query Rhino panel visibility correctly:

```csharp
internal sealed class HostedPanelLifecycleAdapter
{
    public HostedPanelLifecycleAdapter(Type panelType);

    public void PanelShown(uint documentSerialNumber, ShowPanelReason reason);
    public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason);
    public void PanelClosing(uint documentSerialNumber, bool onCloseDocument);

    public void Reconcile(
        string surfaceId,
        bool isSelectedTab,
        Control hostControl,
        Action<HostedSurfaceDecision> apply);
}
```

The adapter may reference `Rhino.UI.Panels`, `ShowPanelReason`, and Eto `Control`. The coordinator may not.

## 7. Surface Identity

Every hosted surface needs a stable `surfaceId` for tracing, coalescing, and bounded defer state.

Required IDs:

- Agent Chat tab: `{documentSerial}:{tabType}:{tabInstanceId}` with `tabType=agent-chat`
- Claude Code tab: `{documentSerial}:{tabType}:{tabInstanceId}` with `tabType=claude-code`
- Vision tab inside Chat: `{documentSerial}:{tabType}:{tabInstanceId}` with `tabType=vision-tab`
- Dedicated Vision panel: `{documentSerial}:vision-panel:{panelInstanceId}`
- Knowledge Graph panel: `{documentSerial}:knowledge-graph:{panelInstanceId}`

Chat tab IDs must not depend only on tab labels. Labels can repeat or change. Each tab should have a per-tab instance ID.

## 8. Lifecycle Rules

### 8.1 Show

If the panel is reported visible, the surface is selected, Rhino reports the panel selected-tab visible, the control is attached to a parent window, and the control has nonzero client size, the coordinator returns `Show`.

### 8.2 Real Hide

Real hide returns `Hide` for reconciled surfaces.

`HideOnDeactivate` is not real hide. A later real `Hide` after temporary deactivate is still real hide.

### 8.3 Temporary Deactivate

`PanelHidden(..., HideOnDeactivate)` records temporary deactivate state but must not produce `Hide`. It must not dispose, reload, tear down, or force-hide hosted browser/native surfaces.

`PanelShown(..., ShowOnDeactivate)` clears temporary deactivate state and schedules normal reconciliation.

### 8.4 Closing

Closing is separate from visibility. `PanelClosing(...)` records closing state only. It must not silently close unknown surfaces.

The owning panel must call `Reconcile(...)` for each known surface. While closing state is active, the coordinator returns `Close` per reconciled `surfaceId`.

Cleanup only happens from:

- `Close` decisions during explicit closing reconciliation
- existing explicit tab close paths
- normal panel disposal paths

The adapter must never call panel or tab cleanup directly from `PanelHidden`.

### 8.5 Rhino Dock Tab Selection

A Rhino panel may exist in a visible dock group while not being the selected Rhino panel tab. `Panels.IsPanelVisible(panelType, isSelectedTab: true)` is the production fact source for this distinction.

If `IsRhinoSelectedPanelVisible` is false, the coordinator must not return `Show`. Depending on the rest of the facts it may return `Hide` or `None`, but not `Show`.

### 8.6 Chat Tab Selection

For Chat-hosted tabs, the selected tab can show when the panel itself is visible and ready. Unselected tabs return `Hide`. This applies to Agent Chat, Claude Code, and the legacy Vision tab hosted inside Chat.

Dedicated Vision and Knowledge Graph panels pass `IsSelectedTab = true` unless they later become internally tabbed.

### 8.7 Docking, Reparenting, And Zero-Size Layout

If the panel is reported visible and selected but the hosted control is not attached to a parent window or has zero client size, the coordinator returns `Defer`.

The adapter schedules a bounded UI-thread retry and captures fresh facts on that retry. It must not block Rhino.

### 8.8 Bounded Defer Policy

The adapter owns scheduling. The coordinator only reports `Defer` from the facts it receives.

Policy:

- At most one pending retry per `surfaceId`.
- Newer events update pending facts; newest facts win.
- Defer budget increments per executed retry, not per noisy event.
- Maximum of 3 executed UI retries per lifecycle transition.
- After retry exhaustion, return/log `None`, keep the surface alive, and stop retrying for that transition.
- Do not reload, dispose, recreate, or force hidden after defer exhaustion.
- The next lifecycle, selection, or layout event resets the defer budget for that surface.

### 8.9 Surface Resurrection After Exhausted Defer

Exhausted defer is not permanent. If a surface exhausts retries while visible but zero-size, a later layout, selection, or show event with nonzero size can return `Show`.

This prevents "gave up forever" behavior after slow docking/reparenting.

## 9. Decision Priority

When facts conflict, the coordinator applies this priority:

1. `IsClosing` => `Close`
2. `LastReason == HideOnDeactivate` => `None` or `Defer`, never `Hide`
3. `!IsSelectedTab` => `Hide`
4. `!IsRhinoSelectedPanelVisible` => `Hide` or `None`, never `Show`
5. `!PanelReportedVisible` => `Hide`
6. visible/selected but unattached or zero-size => `Defer`
7. visible/selected/attached/nonzero => `Show`
8. otherwise => `None`

`ShowOnDeactivate` clears temporary state before applying the normal rules.

## 10. Adapter Responsibilities

The adapter is the only place that maps Rhino/Eto facts into pure lifecycle facts.

It owns:

- mapping `ShowPanelReason` to `HostedPanelLifecycleReason`
- storing latest panel reported visible state
- storing latest document serial number
- storing closing state
- calling `Panels.IsPanelVisible(panelType, isSelectedTab: true)`
- inspecting `Control.Parent`
- inspecting `Control.ParentWindow`
- inspecting `Control.ClientSize`
- tracking defer attempts per `surfaceId`
- coalescing pending retries per `surfaceId`
- scheduling UI-thread retries with exception handling
- diagnostics

It does not own:

- panel or tab cleanup from `PanelHidden`
- WebView2 controller reflection
- WebView reloads
- app-specific tab resource disposal

## 11. Panel Integration

### 11.1 RookChatPanel

`RookChatPanel` creates one `HostedPanelLifecycleAdapter` for `typeof(RookChatPanel)`.

On `PanelShown`, `PanelHidden`, and `PanelClosing`, it records the event in the adapter and reconciles every known hosted tab surface in the relevant document.

On tab selection changes, tab removal, and tab creation, it reconciles affected surfaces.

Each hosted tab provides:

- stable `surfaceId`
- host `Control`
- selected-tab state
- apply callback

The apply callback maps:

- `Show` => `tab.ReconcileHostVisibility(true, reason)`
- `Hide` => `tab.ReconcileHostVisibility(false, reason)`
- `Close` => existing tab close/disposal path when the panel is closing
- `None` => no surface action
- `Defer` => no immediate surface action; adapter schedules retry

### 11.2 RookVisionPanel

`RookVisionPanel` creates one adapter for `typeof(RookVisionPanel)` and reconciles its single `VisionWebSurface`.

It does not treat `PanelHidden(..., HideOnDeactivate)` as hidden.

### 11.3 KnowledgeGraphPanel

`KnowledgeGraphPanel` creates one adapter for `typeof(KnowledgeGraphPanel)` and reconciles its single `KnowledgeGraphSurface`.

Its bootstrap behavior remains unchanged. Lifecycle reconciliation should not trigger bootstrap reloads.

### 11.4 RookWebSurface

`RookWebSurface` remains the low-level sink. It can continue to:

- synchronize WebView2 controller visibility
- notify parent window position changes
- log WebView focus diagnostics
- handle WebView readiness

It should not inspect `ShowPanelReason` and should not infer panel lifecycle from reason strings.

## 12. Diagnostics

Diagnostics are a first-class implementation aid but not a behavior dependency.

Rules:

- Off by default.
- Enabled with `ROOK_PANEL_LIFECYCLE_TRACE=1`.
- Writes to a bounded rotating file under the normal Rook logs directory.
- Safe to leave dormant after validation.
- Easy to remove later if desired.

Log metadata only:

- timestamp
- panel type
- document serial
- surface ID
- event name
- mapped lifecycle reason
- panel reported visible
- selected tab state
- Rhino selected-panel-visible state
- parent/window attached state
- client size
- defer attempt
- pending retry/coalescing state
- action
- final reason

Do not log:

- prompts
- user messages
- WebView content
- chat transcripts
- model output
- user file contents
- sensitive file paths beyond the log file path itself

Diagnostics must support live validation of the coordinator's decisions during docking, floating, reparenting, tab switching, and Rhino activation/deactivation. Lifecycle behavior must be correct with diagnostics disabled.

## 13. Tests

### 13.1 Coordinator Unit Tests

The coordinator tests must not require Rhino, Eto, or WebView2.

Required cases:

- visible + selected + Rhino selected-panel visible + attached + nonzero size => `Show`
- `HideOnDeactivate` never returns `Hide`
- `ShowOnDeactivate` can return `Show` when attached and sized
- `ShowOnDeactivate` can return `Defer` when unattached or zero-size
- real hide returns `Hide`
- a real hide after temporary deactivate returns `Hide`
- unselected tab returns `Hide`
- Rhino dock group visible but selected-panel visibility false does not return `Show`
- closing returns `Close`
- visible but no parent/window returns `Defer`
- visible but zero-size returns `Defer`
- exhausted defer returns `None`
- later nonzero-size event after exhausted defer can return `Show`
- conflicting facts follow the priority order

### 13.2 Adapter Tests

Required cases:

- maps `ShowPanelReason.HideOnDeactivate` to `HostedPanelLifecycleReason.HideOnDeactivate`
- maps `ShowPanelReason.ShowOnDeactivate` to `HostedPanelLifecycleReason.ShowOnDeactivate`
- does not call cleanup from `PanelHidden`
- uses `Panels.IsPanelVisible(panelType, isSelectedTab: true)` through an injectable/queryable boundary so adapter tests can supply synthetic Rhino visibility facts
- coalesces repeated layout/selection events while a retry is pending
- keeps one pending retry per `surfaceId`
- increments retry budget per executed retry, not per noisy event
- resets defer budget on a later lifecycle/selection/layout transition
- records trace only when enabled
- trace excludes user content

### 13.3 Source/Integration Contract Tests

Required source-level or integration-style checks:

- `RookChatPanel` uses `HostedPanelLifecycleAdapter`
- `RookVisionPanel` uses `HostedPanelLifecycleAdapter`
- `KnowledgeGraphPanel` uses `HostedPanelLifecycleAdapter`
- raw `PanelHidden -> ReconcileHostVisibility(false, ...)` pattern is removed from these panels
- Chat hosted tabs have stable per-tab instance IDs
- `RookWebSurface` remains lower-level and does not inspect `ShowPanelReason`

### 13.4 Manual Rhino Smoke

With a build deployed into Rhino:

1. Set `ROOK_PANEL_LIFECYCLE_TRACE=1`.
2. Open Rook Chat.
3. Open an Agent Chat tab.
4. Open a Claude Code tab.
5. Open dedicated Rook Vision panel.
6. Open Knowledge Graph panel.
7. Float, dock, undock, resize, and switch Rhino dock tabs.
8. Deactivate and reactivate Rhino.
9. Switch Chat tabs repeatedly.
10. Confirm surfaces do not blank.
11. Confirm the trace shows `HideOnDeactivate` did not produce `Hide`.
12. Confirm docking/reparenting shows bounded `Defer -> Show` instead of reload/teardown.

## 14. Rollout

This should land as a focused lifecycle fix:

1. Add pure coordinator and unit tests.
2. Add adapter and adapter tests.
3. Migrate Chat.
4. Migrate Vision.
5. Migrate Knowledge.
6. Keep `RookWebSurface` as the low-level sink.
7. Run managed tests.
8. Deploy to Rhino and run the manual smoke.

The implementation plan should be written separately after this spec is reviewed.

## 15. Open Questions

None. The design intentionally chooses the durable lifecycle coordinator path over another WebView-specific workaround.
