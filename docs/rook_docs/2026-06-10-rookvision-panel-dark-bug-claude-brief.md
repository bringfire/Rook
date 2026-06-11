# RookVision Panel Dark Bug: Claude Reviewer Brief

Date: 2026-06-10
Status: working investigation brief
Primary issue: GitHub #233, "RookVision panel can go dark when Rhino focus changes or panel is not focused"

## Goal

Solve the RookVision panel dark/blank presentation bug at the architectural
level, not by layering another timing patch on top of the current stack.

The standard for this investigation is understanding. A plausible fix is not
enough. We need a model of how Rhino panels, Eto controls, WebView2 controller
presentation, app activation, dock-tab selection, and shell focus transitions
interact. If the current state-machine approach is sound, we need to prove it
and close its missing edges. If it is not sound, we need to identify the simpler
canonical architecture and migrate toward it.

## Current User-Observed Behavior

- RookVision panel can go dark/blank after focus changes.
- It is correlated with unfocusing the panel.
- It is correlated with opening the Windows file viewer from the artifact page
  through the "open folder" / reveal action, but it does not reproduce every
  time.
- Re-docking or otherwise structurally disturbing the panel brings it back
  immediately.
- Backend Vision work can continue while the panel presentation is dark, so this
  is likely a host/WebView2/Eto presentation issue rather than a Vision API issue.
- RookChat and Knowledge Graph panels do not currently show the same user-visible
  failure pattern.

Important interpretation: re-docking recovering the panel points toward host
parenting, HWND visibility, controller bounds/visibility, or WebView2 controller
presentation state. It does not strongly point toward dead JavaScript, dead
artifact data, or failed model generation.

## Do Not Default To

- Do not assume the current Vision-specific presentation state machine is
  correct just because many tests exist.
- Do not add another arbitrary delay, repaint, reload, focus, or visibility
  toggle without first proving the failing layer.
- Do not rely on diagnostics that perturb timing as proof of correctness.
- Do not treat a single live smoke pass as permanent closure.
- Do not collapse "Rhino panel visible", "selected dock tab visible", "Eto
  control loaded", "HWND chain visible", "WebView2 controller visible", and
  "pixels presenting" into one boolean.

## External References Worth Reviewing

- McNeel points C# dockable-panel users to the Rhino developer samples,
  particularly `SampleCsDockBar`.
  - Forum thread: https://discourse.mcneel.com/t/c-how-to-make-a-type-of-tool-window-rhino-like-the-osnap/142080
  - Sample: https://github.com/mcneel/rhino-developer-samples/tree/8/rhinocommon/cs/SampleCsDockBar
- Rhino Eto guides describe Eto as the cross-platform UI layer and include Rhino
  specific Eto helpers.
  - https://developer.rhino3d.com/guides/eto/
- Microsoft has a tracked WebView2 issue where windows created while not shown
  can remain blank while the browser process/API is still alive. The report is
  not our exact host, but the failure shape is highly relevant: browser alive,
  no pixels.
  - https://github.com/MicrosoftEdge/WebView2Feedback/issues/1077
- Microsoft WebView2 samples are worth comparing against for initialization,
  controller lifetime, and visibility assumptions.
  - https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/wpf

## Current Rook Architecture

### Panel Registration

Source: `src/Rook/RookPlugin.cs`

Rook registers three per-document panels:

- `RookChatPanel`
- `RookVisionPanel`
- `KnowledgeGraphPanel`

All three are registered with:

```csharp
Panels.RegisterPanel(this, panelType, "...", icon, PanelType.PerDoc);
```

`ShowRookVisionCommand` only calls:

```csharp
Panels.OpenPanel(RookVisionPanel.PanelId);
```

### Shared Web Substrate

Source: `src/Rook/UI/Web/RookWebSurface.cs`

`RookWebSurface` owns:

- Eto `WebView`
- WebView2 virtual host at `https://app.rook.invalid`
- embedded resource serving through `WebResourceRequested`
- JS/C# bridge through `WebMessageReceived`
- WebView2 process failure logging/recovery
- optional focus diagnostics
- legacy `WebViewHostVisibilityCoordinator`
- Vision-only `WebViewHostPresentationCoordinator`

Important seam:

```csharp
protected virtual bool UseHostPresentationCoordinator => false;
```

Only Vision overrides this to `true`. Chat and Knowledge stay on the legacy
visibility path.

### RookVision

Source: `src/Rook/UI/Vision/RookVisionPanel.cs`

Vision is now a dedicated Rhino panel. Its constructor:

- creates `VisionWebSurface`
- sets a presentation-facts refresher
- calls `_surface.CreateWebContent()`
- assigns the resulting WebView as direct `Content`
- subscribes to `Application.Instance.IsActiveChanged`
- tracks instances for diagnostics

Vision owns two lifecycle layers:

1. `HostedPanelLifecycleAdapter`:
   - interprets Rhino `IPanel` show/hide/closing callbacks
   - probes `Panels.IsPanelVisible(panelType, isSelectedTab: true/false)`
   - has bounded deferred retry

2. Vision presentation facts/state:
   - `VisionPanelPresentationState`
   - tracks durable desired visibility, app active state, temporary deactivate,
     visible-any-tab, selected-visible, disposed, authoritative generation
   - feeds `WebViewHostPresentationCoordinator` through
     `_surface.ReconcileHostPresentation(...)`

`PanelShown` and `PanelHidden` both:

- probe visible-any-tab
- probe selected-visible
- update `VisionPanelPresentationState`
- call `_surface.ReconcileHostPresentation(...)`
- then call `ReconcileSurface(...)`, which routes through
  `HostedPanelLifecycleAdapter`

The lifecycle adapter's `Show` decision calls `RefreshSelectionVisible`, which
can trigger another presentation reconcile.

This overlap is a review target. Vision currently has two separate layers that
interpret panel visibility and both can influence WebView presentation.

### Knowledge Graph

Source: `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`

Knowledge Graph uses a simpler shape:

- creates one `KnowledgeGraphSurface`
- assigns `Content = _surface.CreateWebContent()`
- uses `HostedPanelLifecycleAdapter`
- applies `Show` / `Hide` decisions to `_surface.ReconcileHostVisibility(...)`

Important source comment:

```csharp
// Use the WebView directly as panel content. Wrapping in
// TableLayout caused the WebView to lose its content on
// Rhino panel redraw (when clicking outside the panel).
```

Vision also uses direct content now, but Vision has the additional custom
presentation coordinator path.

### Chat

Source: `src/Rook/UI/Chat/RookChatPanel.cs`

Chat is not comparable one-to-one:

- it hosts a tabbed collection of chat sessions
- it reconciles hosted tabs through `HostedPanelLifecycleAdapter`
- it uses the legacy `ReconcileHostVisibility(...)` path for hosted web surfaces
- the legacy Vision tab path still exists but public `ShowRookVisionCommand`
  opens the dedicated Vision panel

## Current Presentation State Machine

Source: `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs`

States:

- `Hidden`
- `PendingHost`
- `PendingController`
- `Presenting`
- `Disposed`

Inputs include:

- desired visible
- app active
- temporary deactivate hidden
- panel visible
- selected panel visible
- Eto loaded/visible/size
- parent window presence
- HWND chain visible
- HWND client rect nonzero
- WebView2 controller available
- controller parent window present
- controller visible
- controller bounds match host target

Actions:

- `None`
- `HideController`
- `PresentController`

Current rule highlights:

- app inactive blocks presentation
- panel not selected blocks presentation but does not hide a visible controller
- `HwndChainHidden` after a prior `PanelNotSelected` can avoid hiding a visible
  controller if the panel is now selected and client rect is nonzero
- repeated healthy `Presenting` is a no-op
- if bounds drift or controller visible state drifts while otherwise presenting,
  it emits `PresentController`

## Current RookWebSurface Presentation Behavior

Source: `src/Rook/UI/Web/RookWebSurface.cs`

When `UseHostPresentationCoordinator` is true:

- `ReconcileHostPresentation(...)` stores latest facts and schedules one
  `Application.Instance.AsyncInvoke(...)` reconcile.
- optional one-shot `RhinoApp.Idle` follow-up is scheduled through
  `WebViewHostPresentationIdleGate`.
- delayed reconcile refreshes panel facts again through
  `RefreshHostPresentationFacts(...)`.
- it captures a snapshot from Eto/WebView2/Win32/controller state.
- it evaluates the coordinator.
- it applies the decision by reflection:
  - setting controller bounds
  - setting controller visibility
  - calling `NotifyParentWindowPositionChanged`

When `UseHostPresentationCoordinator` is true, the shared
`RookWebSurface.OnApplicationIsActiveChanged` returns early. Vision handles app
active changes in `RookVisionPanel.OnApplicationIsActiveChanged` instead.

This split ownership is another review target.

## Artifact Open Folder / Reveal Path

Source: `src/Rook/Handlers/VisionHandler.cs`

The artifact shell actions are off-UI bridge ops:

- `open_artifacts_folder`
- `reveal_artifact_file`

Implementation:

```csharp
Process.Start(BuildOpenFolderStartInfo(folder));
Process.Start(BuildRevealFileStartInfo(filePath));
```

`BuildOpenFolderStartInfo`:

```csharp
FileName = Path.GetFullPath(folderPath),
UseShellExecute = true
```

`BuildRevealFileStartInfo`:

```csharp
FileName = "explorer.exe",
Arguments = $"/select,\"{Path.GetFullPath(filePath)}\""
```

These shell launches predictably steal focus from Rhino and can trigger
deactivate/reactivate, panel hide/show-on-deactivate, HWND host withdrawal, and
selection-visible timing changes. The bridge op itself is off-UI, but the
system-level focus side effect is central to the bug.

## Diagnostics That Exist

### In-Memory Presentation Ring

Source:

- `RookVisionPanel.DumpPresentationDiagnostics()`
- `RookVisionPanel.DumpPresentationDiagnosticsSummary(int)`
- `RookWebSurface.GetHostPresentationDiagnosticEntries()`

Captures:

- facts
- snapshot
- coordinator decision
- action result
- reason
- timestamp

Bounded to 64 entries per surface.

### Rhino Command

Source: `src/Rook/Commands/RookDumpVisionPresentationStateCommand.cs`

Command:

```text
RookDumpVisionPresentationState
```

Writes a JSON file to `%TEMP%` and prints a compact tail summary in Rhino.

Problem: during the latest investigation, trying to call it through the MCP safe
command bridge failed as `unknown_command` / `run_script_safety_refusal`. That
means the best diagnostic path exists but was not available exactly when needed.

### File Trace

Source: `src/Rook/UI/Panels/HostedPanelLifecycleTrace.cs`

Enable with:

```text
ROOK_PANEL_LIFECYCLE_TRACE=1
```

Writes:

```text
%APPDATA%/Rook/logs/panel-lifecycle.log
```

or under `%ROOK_DATA_DIR%/logs`.

The old trace from 2026-05-26 showed states like:

```text
reportedVisible=True selectedTab=True rhinoSelectedVisible=False hostReady=True action=None decisionReason=rhino-panel-selected-visibility-pending:defer-exhausted
```

But lifecycle trace was not enabled for the latest recurrence.

### WebView Focus Diagnostics

Source: `RookWebSurface.BuildFocusProbeScript()`

Gated by environment variable logic in `IsWebViewFocusDiagnosticsEnabled()`.
Potential problem: JS/layout probing and file/log output may perturb timing, so
it is useful but cannot be the only proof.

## Prior Fix/Investigation Timeline

### 2026-04-24 to 2026-04-30

Relevant commits:

- `fa3a943` / `b75e06a`: Fix RookVision WebView activation recovery
- `ef4cd14` / `5903f73`: gate focus repaint workaround (#132)
- `d678069` / `4ecb0d1`: expand webview focus evidence capture

Interpretation: early fixes were WebView/focus/repaint oriented.

### 2026-05-10

Relevant commits:

- `5a8044e` / `fb7fe45`: host RookVision in dedicated panel

Interpretation: Vision moved out of Chat tab hosting into its own native panel.
This was an architectural improvement, but the dark bug class survived.

### 2026-05-14 to 2026-05-16

Relevant commits:

- `4e9b9e8`: recover visible WebView after stale panel hide
- `ca484e0`: harden hosted panel lifecycle

Design doc:

- `docs/superpowers/specs/2026-05-15-hosted-panel-lifecycle-design.md`

Interpretation: introduced shared lifecycle modeling above WebView visibility.

### PR #191, 2026-05-25

Title: `[codex] Add WebView host presentation coordinator contract`

Merge commit: `6a40e3b`

Scope:

- pure `WebViewHostPresentationCoordinator`
- snapshot-in / decision-out contract
- no runtime wiring

PR explicitly said it changed no runtime behavior and was intended as an
architecture-contract PR.

### PR #193, 2026-05-26

Title: `[codex] Preserve RookVision presentation across docked tab return`

Merge commit: `959753f`

Summary:

- Vision presentation facts
- in-memory diagnostic ring
- `RookDumpVisionPresentationState`
- decision-time refresh of volatile panel visibility facts
- preserve already-visible WebView2 controller across transient inactive or
  tab-selection states
- fixed one live-proven docked tab return edge

Root cause claimed for that edge:

- on return to RookVision tab, diagnostics showed selected-visible and nonzero
  client rect but hidden HWND chain
- coordinator hid the controller, leaving panel dark until a later focus edge
  re-presented it

Important boundary from PR #193:

It did not claim every historical blank state was solved. It said future edges
should be handled with diagnostics rather than guessed fixes.

### Issue #233, 2026-06-09

Open issue:

- current recurrence after PR #193
- likely focus/presentation lifecycle issue
- latest run did not have lifecycle tracing enabled
- diagnostic command could not be captured through MCP

## Open Architectural Questions For Claude

1. Is Vision's two-layer model coherent?
   - `HostedPanelLifecycleAdapter` decides show/hide/defer.
   - `VisionPanelPresentationState` and `WebViewHostPresentationCoordinator`
     separately decide desired/host/controller presentation.
   - Are these layers duplicating responsibility in a way that creates timing
     gaps?

2. Should Vision use the same legacy visibility architecture as Knowledge until
   proven otherwise?
   - Knowledge works with direct WebView content plus lifecycle adapter plus
     `ReconcileHostVisibility`.
   - Vision uses direct WebView content plus lifecycle adapter plus a custom
     presentation coordinator.
   - The coordinator may be solving real edges, but it is also the main
     architectural difference from the panels that behave.

3. Are we creating or initializing WebView2 too early?
   - `RookVisionPanel` constructs the surface and creates WebView content in the
     constructor, before an unquestionably visible/onscreen host state.
   - WebView2 has known blank-window reports when created while the containing
     window is hidden/backgrounded.
   - Does Rhino instantiate per-doc panels in hidden states?
   - Should WebView2 controller initialization be deferred until first verified
     host presentation?

4. Does shell focus steal expose a missing return event?
   - artifact reveal/open-folder launches Explorer
   - Explorer steals focus and may cause app deactivation
   - if Rhino does not emit a clean selected-visible or size/layout event on
     return, the current model may remain in a stale pending/presenting state
     without applying the needed controller presentation action

5. Does `Presenting + action None` falsely assume pixels are visible?
   - The coordinator can report `Presenting` with no action when all probes
     look healthy and controller is visible.
   - But WebView2 can be alive/API-responsive while not painting.
   - Do we need a non-invasive pixel/presentation liveness signal, or is the
     correct architecture to avoid entering that invisible state by construction?

6. Is `Panels.IsPanelVisible(..., isSelectedTab: true)` reliable across these
   transitions?
   - Old trace showed selected tab true at lifecycle layer but Rhino selected
     visibility false until defer exhausted.
   - Current code treats probe failure as coordinator false but records prior
     value separately. Is that too conservative?

7. Are app-active facts split correctly?
   - `RookWebSurface.OnApplicationIsActiveChanged` returns early for Vision.
   - `RookVisionPanel.OnApplicationIsActiveChanged` updates presentation facts.
   - Could ordering between panel callbacks and application active callbacks
     leave a stale authoritative generation?

8. Are WebView2 controller reflection calls sufficient?
   - current action path sets bounds, sets `IsVisible`, calls
     `NotifyParentWindowPositionChanged`
   - no explicit controller parent-window repair exists
   - no controller recreation exists
   - no delayed initialization exists

## Minimum Evidence Needed Before Fixing

We should not implement a new fix until one current-session dark state captures:

- actual reproduction steps
- `RookDumpVisionPresentationState` JSON from the dark state
- lifecycle trace around the transition, if enabled
- whether Rhino app is active
- whether RookVision is selected-visible according to Rhino
- Eto loaded/visible/size
- parent window present
- HWND chain visible
- HWND client rect nonzero
- controller available
- controller parent window present
- controller visible
- controller bounds match
- last action result
- whether JS/DOM is still alive, if focus diagnostics are enabled

If the act of logging perturbs the bug, prefer the memory ring plus a command or
typed route that reads already-captured state after the fact. Avoid adding hot
path file writes or repeated JS layout probes as the primary diagnostic.

## Immediate Diagnostic Improvements To Consider

These are not fixes to the dark bug; they are ways to make the next observation
decisive:

1. Expose `RookDumpVisionPresentationState` through a typed managed/native route
   or MCP tool that bypasses the safe command refusal.
2. Add a one-shot "dump on next non-presentable/defer-exhausted Vision state"
   option that records in memory and writes only after the event, avoiding
   constant hot-path logging.
3. Add a shell-focus scenario smoke script/manual matrix:
   - open RookVision
   - open Gallery
   - open artifact modal
   - click reveal/open-folder
   - return to Rhino
   - record state before/after redocking
4. Capture a side-by-side Knowledge baseline under the same focus sequence.

## Candidate Architectural Directions

These are hypotheses, not recommendations yet.

### Option A: Keep Vision Coordinator, Complete The Missing Edges

Use the current model but make diagnostics reachable and prove the exact missing
transition. Fix only the proven missing event/state/action.

Risk: continues a complex Vision-only architecture that differs from working
panels.

### Option B: Simplify Vision Toward KnowledgeGraphPanel

Temporarily or permanently remove Vision-only presentation coordinator behavior
and use the same direct-WebView + lifecycle-adapter + legacy visibility path as
Knowledge Graph.

Risk: may regress the live-proven docked-tab return edge that PR #193 fixed.
Needs an A/B local build or feature flag for live comparison.

### Option C: Defer WebView2 Creation Until Host Is Presentable

Treat hidden/background initialization as the root class. Do not create or
initialize WebView2 until the panel has a real parent window, nonzero size, and
selected-visible state. Recreate if WebView2 loses its controller/browser
process.

Risk: larger architectural change. Needs careful lifetime handling for bridge
registration, artifact state, and per-doc panel reuse.

### Option D: Canonical Native Host Wrapper

Replace the Eto `WebView` abstraction for Vision with a more direct WinForms/WPF
or RhinoWindows host pattern matching McNeel samples, then put WebView2 inside
that known-good host.

Risk: bigger migration and may not be necessary. Could be justified if Eto
WebView's abstraction prevents correct controller lifecycle handling.

## Proposed Investigation Sequence

1. Read the source files listed below before editing.
2. Reproduce once with current build and current diagnostics reachable if
   possible.
3. If diagnostic command is not reachable, fix diagnostic reachability first.
4. Capture the dark state.
5. Compare the captured state to a healthy state and to the state immediately
   after redocking.
6. Decide whether the failure is:
   - missing event/reconcile
   - wrong state transition
   - wrong WebView2 controller action
   - WebView2 initialized in non-presentable host
   - Eto/Rhino panel host mismatch
   - shell-focus/app activation ordering
7. Only then design the fix.

## Source Files Claude Should Read

Core runtime:

- `src/Rook/RookPlugin.cs`
- `src/Rook/Commands/ShowRookVisionCommand.cs`
- `src/Rook/Commands/RookDumpVisionPresentationStateCommand.cs`
- `src/Rook/UI/Vision/RookVisionPanel.cs`
- `src/Rook/UI/Vision/VisionWebSurface.cs`
- `src/Rook/UI/Vision/VisionPanelPresentationState.cs`
- `src/Rook/UI/Web/RookWebSurface.cs`
- `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs`
- `src/Rook/UI/Web/WebViewHostPresentationIdleGate.cs`
- `src/Rook/UI/Web/WebViewHostPresentationDiagnosticEntry.cs`
- `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`
- `src/Rook/UI/Panels/HostedPanelLifecycleAdapter.cs`
- `src/Rook/UI/Panels/HostedPanelLifecycleCoordinator.cs`
- `src/Rook/UI/Panels/HostedPanelLifecycleTrace.cs`
- `src/Rook/UI/Panels/RhinoPanelVisibilityQuery.cs`
- `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`
- `src/Rook/UI/Chat/RookChatPanel.cs`
- `src/Rook/Handlers/VisionHandler.cs`

Tests:

- `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`
- `src/Rook.Tests/UI/Vision/VisionPanelPresentationStateTests.cs`
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
- `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`
- `src/Rook.Tests/UI/Web/WebViewHostPresentationIdleGateTests.cs`
- `src/Rook.Tests/UI/Panels/HostedPanelLifecycleAdapterTests.cs`
- `src/Rook.Tests/UI/Panels/HostedPanelLifecycleCoordinatorTests.cs`
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

Design/history docs:

- `docs/superpowers/specs/2026-05-15-hosted-panel-lifecycle-design.md`
- `docs/superpowers/plans/2026-05-15-hosted-panel-lifecycle.md`
- `docs/superpowers/specs/2026-05-25-webview-host-presentation-coordinator-design.md`
- `docs/superpowers/plans/2026-05-25-webview-host-presentation-coordinator.md`
- `docs/superpowers/specs/2026-05-26-vision-return-edge-presentation-design.md`
- `docs/superpowers/plans/2026-05-26-vision-return-edge-presentation.md`
- `docs/rook_docs/2026-04-25-vision-reveal-artifact-implementation-plan.md`

GitHub:

- Issue #233
- PR #191
- PR #193

## Commands Used To Gather This Brief

```powershell
gh issue view 233 --repo bringfire/Rook --json number,title,state,body,comments,labels,createdAt,updatedAt
gh pr view 191 --repo bringfire/Rook --json number,title,state,body,mergeCommit,commits,files,createdAt,mergedAt
gh pr view 193 --repo bringfire/Rook --json number,title,state,body,mergeCommit,commits,files,createdAt,mergedAt
git log --all --date=short --pretty=format:"%h %ad %s" -- src/Rook/UI/Vision src/Rook/UI/Web src/Rook/UI/Panels src/Rook/Commands/RookDumpVisionPresentationStateCommand.cs src/Rook.Tests/UI/Web src/Rook.Tests/UI/Vision
rg -n "RookVision|Vision|WebView|WebView2|Eto|Panel|Artifact|open folder|Open Folder|dark|blank|focus|dock|docking|undock" src mcp_server docs scripts -g "*.cs" -g "*.cpp" -g "*.h" -g "*.md" -g "*.py"
```

## Success Criteria

- We can reproduce or at least instrument the current dark-state path.
- Claude and Codex agree on the actual failing layer before code changes.
- The fix removes an architectural ambiguity or closes a proven state gap.
- Diagnostics for this class of bug are reachable through MCP or another
  reliable live path.
- Manual smoke covers:
  - panel open
  - focus away and back
  - docked tab switch and return
  - floating/undocked panel focus changes
  - artifact modal
  - artifact open-folder/reveal
  - redock recovery comparison
- Automated tests pin any new state-machine or lifecycle contract.

