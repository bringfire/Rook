# WebView Presentation Reconciler Design

Date: 2026-06-10
Status: approved design (Claude + Codex review), pre-implementation
Replaces: probe-gated presentation architecture from PR #191 / PR #193
Closes (on completion): issue #233 and the dark-panel bug class behind it

## Problem

RookVision (and potentially any `RookWebSurface` panel) can go dark: the
WebView2-rendered content shows black/stale pixels while the backend, bridge,
and every host-side probe report healthy. Six weeks of fixes (focus repaint
workarounds, dedicated panel hosting, lifecycle hardening, the
`WebViewHostPresentationCoordinator` state machine) each closed one edge and
the bug class survived.

## Root Cause (live-proven 2026-06-10)

Captured in one instrumented session (in-memory presentation ring + injected
JS visibility probe + external HWND watcher), with the user confirming visual
state at each step:

1. Rhino hides and can **recreate** a floating panel's dockbar form across
   app deactivate/reactivate (observed: form HWND `919264` destroyed,
   replaced by `527716`; the WebView2 widget windows were rebuilt with new
   handles).
2. During that transition the host control re-asserts WebView2 controller
   visibility mid-reparent. Sometimes the renderer never receives the
   "visible again" notification: the page's last `visibilitychange` event was
   `hidden` (11:29:33) and **no `visible` event ever followed**, across many
   Rhino refocuses. Chromium does not paint documents it believes are hidden.
3. In that stuck state, every host-side fact is green: controller
   `IsVisible=true`, correct `ParentWindow`, correct bounds, full HWND chain
   `WS_VISIBLE`, `Chrome_RenderWidgetHostHWND` present, Eto loaded/visible,
   Rhino panel visible+selected. The coordinator evaluated
   `Presenting / action None`. **No probe Rook had could see the failure.**
4. Repair was proven live: controller `IsVisible=false` → ~800ms gap →
   `IsVisible=true` restored pixels with Rhino focused, no re-dock, no
   reload. An instantaneous false→true toggle did **not** repair (the
   transition coalesces away); the gap is load-bearing.
5. A second silent failure was captured in the same session: the renderer
   rebuilt its document (injected JS state wiped, fresh page) with **zero
   events** reaching Rook's handlers — no NavigationStarting/Completed, no
   DocumentLoaded, no ProcessFailed.
6. A self-inflicted defect was also captured (ring entry #8): on app
   activation, the coordinator sampled the HWND chain mid-transition
   (`HwndChainHidden`), emitted `HideController`, and **applied it** — hiding
   the controller on the way into activation. The PR #193 carve-out does not
   cover the `Presenting -> PendingHost` path.
7. Heisenbug confirmation: enabling synchronous file-trace diagnostics on the
   UI thread made the bug substantially less reproducible. The failure lives
   in a narrow timing window inside the activation/reparent transition.
   No probe-then-act design can win a race it is inside of.

Secondary observed facts:

- Re-dock recovery is explained mechanically: Eto's WPF WebView2 handler
  detaches/reattaches the control on panel unload/load, forcing a full
  HwndHost rebuild that re-pushes parent/bounds/visibility.
- `NotifyParentWindowPositionChanged` is documented by Microsoft as an
  accessibility/dialog-placement notification, not a repaint trigger
  (confirmed by WebView2Feedback #5398). The old `PresentController` action
  leaned on it as the finishing move; on the stuck path it does nothing.
- **Observed fact, this host stack, not a universal guarantee:** in today's
  Rook/Rhino 8/Eto-WPF/WebView2 host, live evidence showed the host control
  set the controller invisible during true host withdrawal (form hide at
  11:29:33: element visibility propagated and controller read
  `IsVisible=false` without any Rook action). The design records this as an
  observed behavior of the current stack and does not depend on it as a
  contract.

## Architectural Verdict

The prior model inferred pixel presentation from Rhino/Eto/HWND/controller
proxy facts and acted only on detected drift (edge-triggered gate). The
failing layer — the renderer's own visibility belief and its composition
output — is not observable from any of those facts, and the critical
restoring transitions (form re-show, reparent completion) emit no events.
An edge-triggered gate over unobservable levels cannot converge.

The replacement is a **level-triggered reconciler**: on every stabilized
return edge, ask the renderer what it believes, compare with desired state,
and apply a bounded, idempotent repair until they agree.

## Invariants

1. **No present-side effects while Rhino/app is inactive.** This preserves
   the real invariant behind the PR #192 wedge evidence (Rhino lockups when
   WebView2 was mutated through inactive/host-withdrawal intervals). The
   reconciler runs only on return edges and only while the app is active;
   triggers arriving while inactive re-queue for the next activation.
2. **The renderer's belief is the primary liveness probe.** Host-side facts
   (HWND chain, client rect, `Panels.IsPanelVisible`) are demoted to
   diagnostic annotations; they gate nothing.
3. **Durable desired state is owned by the panel lifecycle layer**
   (`HostedPanelLifecycleAdapter` + panel callbacks), never inferred by the
   reconciler. Renderer-hidden is a health symptom, not a desire signal.
4. **Every repair is generation-guarded and bounded.** No unbounded retries,
   no timers that outlive their authorizing state.
5. **One code path for all surfaces.** No per-surface presentation seams
   (`UseHostPresentationCoordinator` is deleted, not replaced).

## Component: `WebViewPresentationReconciler`

Owned by `RookWebSurface`, one instance per surface. Serialized: one
in-flight reconcile per surface, latest-wins coalescing of trigger requests.

### Desired-visible ownership and generation model

`DesiredVisible` is set only by the lifecycle layer. The exact semantics are
per surface kind — this is the boundary that prevents host-probe transients
from re-entering the decision path one layer up:

| Surface kind | Event | DesiredVisible effect |
|---|---|---|
| Dedicated panel (Vision, Knowledge) | `PanelClosing` / dispose | `false` (durable) |
| Dedicated panel | `PanelHidden` with visible-anywhere `false` after a real hide (not `HideOnDeactivate`) | `false` (durable) |
| Dedicated panel | selected-tab probe `false`, `HideOnDeactivate`, app inactive, HWND chain / client-rect readings | **no change** — never durable hide |
| Chat internal tab surface | internal tab unselected | `false` for that tab surface (Chat's own tab control is authoritative, not a Rhino probe) |
| Chat internal tab surface | internal tab selected | `true` |
| All surfaces | renderer-hidden probe result | **never changes DesiredVisible** — health symptom only |

A correctly tabbed-behind dedicated panel therefore keeps
`DesiredVisible=true`; its renderer legitimately reports `hidden`, bounded
repair attempts no-op harmlessly inside the hidden host window, and the
sequence terminates in Degraded-with-annotation — **never reload** (see
repair sequence). Reselecting the tab fires `PanelShown`, which reconciles
and repairs if genuinely stuck.

- `Generation` is a per-surface monotonic counter, incremented on: durable
  hide, close/dispose, panel shown, and app active/inactive change.
- Every delayed continuation (repair gap timer, confirmation probe, queued
  reconcile) captures the generation at schedule time and **aborts silently**
  if the current generation differs or `DesiredVisible` is false.

### Probe contract

`ProbePresentation()` executes one `ExecuteScriptAsync` returning a
structured payload:

```js
JSON.stringify({
  visibilityState: document.visibilityState,
  hidden: document.hidden,
  readyState: document.readyState,
  hasRoot: !!document.body,
  viewport: [window.innerWidth, window.innerHeight],
  appRect: document.body ? (document.body.getBoundingClientRect().toJSON
            ? document.body.getBoundingClientRect().toJSON() : null) : null
})
```

Parsing note (implementation requirement): WebView2 `ExecuteScriptAsync`
returns the script result as a JSON-encoded *string* — the payload above
arrives double-encoded and must be unquoted/decoded before parsing. This is a
known source of false negatives in WebView2 code and gets an explicit unit
test.

Outcomes:

- `Healthy`: parsed payload with `visibilityState == "visible"`. Note this
  certifies only the renderer's belief, not compositor output — see
  *Scope of the probe* below.
- `RendererHidden`: parsed payload with `visibilityState == "hidden"`.
- `RendererUnresponsive`: no answer within `ProbeTimeoutMs`, or
  `ExecuteScriptAsync` faulted. This is a health classification — renderer
  or WebView IPC is unhealthy enough that script-based repair cannot be
  relied on. It does **not** claim the renderer process is dead (causes
  include dead renderer, blocked browser process, navigation in progress,
  disposed controller, host transition timing).
- `ProbeInvalid`: an answer arrived but failed to decode/parse. Handled the
  same as `RendererUnresponsive` (bounded reload path), recorded distinctly
  in the ring.

The full payload is recorded in the diagnostics ring on every probe.

Scope of the probe: `Healthy` covers the live-proven stuck-hidden-renderer
class. A renderer that reports `visible` while the compositor shows stale
pixels (WebView2Feedback #5574 class) is **not** detected by this probe —
that class was not captured in this investigation and is handled by the
operator-forced repair path (the `Repair=Yes` affordance runs the gapped
toggle regardless of probe result). If field evidence later shows a
visible-but-not-compositing recurrence, a `VisibleButSuspect` classification
can be added without changing this architecture.

### Repair sequence (exact, bounded)

On a reconcile trigger with `DesiredVisible=true` and app active:

```text
 1. probe
 2. Healthy            -> record, done (no side effects; the ~95% path)
 3. RendererHidden     -> repair attempt 1:
      a. controller.IsVisible = false
      b. async wait RepairGapMs (UI thread free)
      c. guard: generation current AND DesiredVisible still true, else abort
      d. controller.IsVisible = true
      e. set controller bounds to host target
      f. NotifyParentWindowPositionChanged (a11y/dialog correctness only)
      g. confirmation probe (after ConfirmDelayMs)
 4. still RendererHidden -> repair attempt 2 (same sequence, same guards)
 5. confirmation probe
 6. still RendererHidden  -> Degraded state, ring-logged with lifecycle
                             annotations (selected-tab, visible-anywhere) so
                             an operator can distinguish "legitimately
                             tabbed-behind" from "stuck". NO reload — a
                             correctly hidden panel must never be reloaded.
 7. RendererUnresponsive or ProbeInvalid (at any probe)
                          -> one CoreWebView2.Reload()  (re-runs document-
                             created scripts incl. bridge shim), AND a
                             scheduled post-reload confirmation reconcile
                             (generation-guarded, after ReloadConfirmDelayMs)
                             that runs even if DocumentLoaded never fires —
                             the root-cause evidence showed document rebuilds
                             can emit zero events, so DocumentLoaded is an
                             additional trigger, never the only post-reload
                             path.
 8. if the post-reload confirmation reconcile fails again -> Degraded state:
    ring-logged, surfaced once via RhinoApp.WriteLine, NO further automatic
    action until the next external trigger. No loops.
```

On a reconcile trigger with `DesiredVisible=false` (durable hide only):
`controller.IsVisible = false`. No probe, no toggle. There is **no**
probe-gated "protective hide" anywhere — the ring-#8 class is removed by
construction.

Named constants (single source of truth, internal):

```text
RepairGapMs          = 200
ConfirmDelayMs       = 500
ProbeTimeoutMs       = 2000
ReloadConfirmDelayMs = 3000
MaxRepairAttemptsPerTrigger = 2
MaxReloadsPerTrigger        = 1
```

### Trigger model

| Trigger | Source | Behavior |
|---|---|---|
| App activated | `Application.Instance.IsActiveChanged` (active) | immediate async reconcile + one idle-tick confirmation reconcile |
| Panel shown | lifecycle adapter `Show` decision | reconcile |
| Got focus | Eto `GotFocus` | reconcile (restores click-to-heal on every surface) |
| Size changed | Eto `SizeChanged` | coalesced reconcile |
| Document loaded | `DocumentLoaded` (initial or post-Reload) | reconcile |
| Post-repair confirm | reconciler-internal | bounded per sequence above |

Guards: requests while app inactive are recorded and re-queued for the next
activation (never executed inactive); generation mismatch aborts; disposed
surface aborts. Nothing triggers on deactivate. No HWND-chain, client-rect,
or `Panels.IsPanelVisible` value appears anywhere in the decision path.

## Deletions, Keeps, Boundaries

Deleted:

- `WebViewHostPresentationCoordinator` runtime wiring and class
- `VisionPanelPresentationState`
- `UseHostPresentationCoordinator` seam
- presentation-facts refresher plumbing (`SetPresentationFactsRefresher`,
  `RefreshHostPresentationFacts` overrides)
- `WebViewHostPresentationIdleGate`
- legacy `WebViewHostVisibilityCoordinator` queue (subsumed by the
  reconciler's coalescing)

Kept:

- `HostedPanelLifecycleAdapter` / `HostedPanelLifecycleCoordinator` —
  classes unchanged. They own Rhino lifecycle interpretation
  (show/hide/defer/close) and remain the input to durable desired state.
  What changes is the panels' **mapping** of adapter decisions, per the
  desired-visible table: on dedicated panels, a probe-driven `Hide`
  (tab-unselected / selected-visibility) is recorded as a ring annotation
  and does NOT set `DesiredVisible=false`; only `Close`, dispose, and
  real-hide-with-visible-anywhere-false do. Chat's internal tab selection
  keeps mapping to per-tab desired state as today.
- In-memory diagnostics ring (extended: probe payloads, repair outcomes,
  generation, trigger source), bounded as today.
- Process-failure recovery (`ProcessFailed` classification) — unchanged.
- All bridge / virtual-host / CSP / security machinery — untouched.

Boundary statement (review condition #3): the reconciler owns **renderer
liveness and presentation repair only**. Logical open/closed/durable-hide is
owned by the lifecycle layer. A surface that is logically closed can never be
"repaired visible" (generation + DesiredVisible guards), and renderer-hidden
never demotes a logically open surface to hidden.

## Diagnostics & Operator Affordances (mandatory scope)

The 2026-06-09 recurrence (#233) could not be diagnosed live because the dump
command was unreachable through the MCP safe-command bridge. Therefore, as an
**acceptance criterion** of this design, not a nice-to-have:

1. `RookDumpVisionPresentationState` is generalized to all `RookWebSurface`
   panels and gains an optional `Repair=Yes` mode that runs the gapped-toggle
   repair once **regardless of probe result** (this is the recovery path for
   any visible-but-not-compositing failure the probe cannot detect;
   operator/field-evidence path, not normal UX — automatic convergence
   remains the product behavior).
2. Dump and repair are exposed through a typed companion-bridge route (and
   MCP tool) so they are reachable without keyboard/manual command entry.

## Rollout & Validation Gates

One shared substrate path, enabled for Vision, Chat, and Knowledge Graph in
the same PR chain. Gate (review condition #1): **all three surfaces pass the
live matrix before merge. If Chat or Knowledge fails, the PR does not ship
half-enabled** — the failure is fixed or the chain stops; no per-surface
architecture forks.

Vision is validated first (it is the reproducer), then the identical matrix
runs on Chat and Knowledge in the same session.

### Unit tests (fake probe / clock / controller; no Rhino/Eto/WebView2 types)

- healthy probe → no side effects
- `RendererHidden` → exact repair sequence order (hide, gap, guard, show,
  bounds, notify, confirm)
- generation bump during gap → repair aborts, controller untouched
- durable hide during gap → repair aborts
- repair attempt bounding (2) and reload bounding (1), then Degraded
- persistent `RendererHidden` after bounded repairs → Degraded, **never
  reload** (the tabbed-behind case)
- `RendererUnresponsive` → single reload + scheduled post-reload
  confirmation reconcile that runs **without** a `DocumentLoaded` event
- `ProbeInvalid` (malformed/undecodable result) → classified, reload path
- `ExecuteScriptAsync` double-encoded result is decoded correctly (a
  JSON-encoded string containing JSON)
- trigger while app inactive → recorded, executed on next activation only
- coalescing: N triggers → one in-flight reconcile, latest generation wins
- durable hide → `IsVisible=false`, no probe, no toggle
- desired-visible table: selected-tab false / HideOnDeactivate / HWND
  readings never produce durable hide on dedicated panels; Chat internal
  tab unselected does for that tab surface

### Live validation matrix (merge gate, ring dump captured per scenario)

Reproducer set (today's evidence):

- floating Vision panel on a monitor above primary (negative-Y coords)
- rapid app deactivate/reactivate cycles (alt-tab storms)
- artifact reveal / open-folder Explorer focus steal, returning focus by
  (a) clicking panel content, (b) clicking viewport, (c) alt-tab
- artifact reveal / open-folder while a **video element is loaded/playing or
  recently loaded** in the modal (review condition #6 — video stresses
  composition differently than static images)

PR #192 wedge suite (must show no Rhino lockup, command-line freeze,
close-button failure, or resize smear):

- app deactivate with panel docked; tab away/return; floating panel;
  resize while inactive; Explorer focus steal

General:

- docked tab switch away/return without app refocus
- undock/redock during and after a dark state
- Chat + Knowledge co-resident in the same session, same matrix
- multi-document open/close (per-doc panel lifecycle)
- click-into-dark-panel heals (GotFocus trigger) on all surfaces

## Acceptance Criteria

- A captured stuck-renderer state self-heals on the next return edge without
  re-dock, reload-by-hand, or panel reopen.
- Clicking a dark panel heals it (all surfaces) **for the captured
  stuck-hidden-renderer class**; visible-but-not-compositing failures (not
  observed in this investigation) are recoverable via the operator
  `Repair=Yes` path.
- No present-side effects ever execute while the app is inactive (verified
  by ring inspection across the matrix).
- The #192 wedge suite passes with full Rhino responsiveness.
- Dump + repair reachable via typed route/MCP tool, live-verified.
- Unit suite covers the decision table above.
- The deleted types are gone (no dormant parallel host model remains).

## Non-Goals

- No user-facing settings, env-var modes, or visible repair buttons.
- No recurring timers / polling loops; the reconciler is event-triggered.
- No changes to bridge security, CSP, virtual host, or artifact pipelines.
- No attempt to prevent Rhino from hiding/recreating floating forms (host
  behavior outside our control; the reconciler converges after it).
- `--disable-features=CalculateNativeWinOcclusion` is explicitly out of
  scope for this PR chain; it may be revisited as environment-level hardening
  if field evidence later shows an occlusion-class failure (today's captured
  mechanism was visibility-notification loss, which the flag does not
  address).

## Addendum (2026-06-10 evening): Suspect-Cycle Forced Repair

Live validation Round 1 (branch `521b92f` deployed): Gate 1 PASS (MCP
dump/repair/400 end-to-end, 3 surfaces), Gate 2 user-observed PASS (no wedge),
**Gate 3 Scenario 1 FAIL** — Knowledge Graph went dark on Rhino unfocus,
recurring per deactivate/activate cycle; click-inside did NOT heal; MCP forced
repair DID heal.

Ring evidence (Knowledge, the failed heal): seq 162 probe `RendererHidden` →
163 `repair-attempt 1;GotFocus` → 164 `confirm 1;Healthy` → 165–169 probe
`Healthy` — while pixels stayed dark. Forced repair at 170–173 (same gapped
toggle, quiet window) healed it.

Two model corrections, both live-proven:

1. **A repair executed during host churn can renderer-succeed and
   compositor-fail.** The GotFocus repair ran inside the activation churn its
   own trigger click caused; the confirm probe certifies renderer belief only
   and cannot see the lost compositor present. The identical primitive
   succeeded minutes later in a quiet window.
2. **Controller visibility IS the renderer's visibility source, decoupled from
   presentation.** Toggling a tabbed-behind surface flips its renderer to
   `visible` inside a hidden host window, so `DegradedHidden` was unreachable
   in Gate 2 (hidden probes "repaired" to Healthy). The original assumption
   that a legitimately hidden host re-confirms hidden was wrong.

### Mechanism (exercises the named `VisibleButSuspect` extension point)

**Suspect-cycle forced repair** — per-cycle, post-churn, probe-independent:

- App deactivate: mark the surface `suspect`. NO WebView mutation (preserves
  the no-present-side-effects-while-inactive invariant).
- Activation idle confirm (the existing one-shot `OnActivationIdleConfirm`):
  if app active AND `DesiredVisible` AND generation valid AND suspect → run
  ONE forced gapped toggle (no probe gate), clear suspect. First-idle is the
  best EXISTING hook and approximates the quiet window in which every
  successful manual/forced repair ran — but it is not guaranteed quiet;
  Rhino/Eto/WebView host churn may still be settling at first idle.
  **Round-2 fallback criterion:** if the first-idle suspect repair still
  loses the compositor race in live validation, the next design step is a
  second-idle hop or a short post-idle delay before the toggle — NOT more
  probe logic.
- Ring entries: `suspect-cycle` (set), `suspect-cycle-forced-repair` (run),
  plus the standard forced-repair disposition.
- Cost: one brief blink per app-refocus on healthy panels, during a transition
  where the compositor is already visibly churning.

Unit contract: Healthy probe would normally NoOp, but suspect + activation
idle runs the forced toggle exactly once; inactive / durable-hidden / stale
generation does NOT toggle; suspect does not accumulate (one toggle per cycle).

### Deferred: unselected-host repair skip (NOT in this round)

The Gate 2 anomaly suggests skipping automatic repair when the host dock-tab
is unselected. Review correctly rejected the first proposal: **current
dedicated panels pass `isSelectedTab: true` unconditionally and have no
reliable selected-tab fact** — `Panels.IsPanelVisible(..., isSelectedTab:
true)` is exactly the probe documented as stale during transitions. Until a
reliable Rhino/Eto selected-tab source is identified, this round records
annotations only; no repair-skip. Renderer hidden / WebView state must never
be used to infer durable hidden.

Operator repair (`repair_presentation` / `Repair=Yes`) remains unchanged and
overrides any future automatic skip.

### Revalidation order (Round 2)

1. Gate 3 Scenario 1 FIRST (Rhino unfocus/refocus cycles; Knowledge must not
   stay dark, click-inside must heal or be made moot by the suspect-cycle
   repair).
2. Then Gate 2 (tabbed-behind: expect dispositions to reflect correction #2;
   wedge symptoms re-checked).
3. Then the remaining matrix.
4. Registry hygiene check: confirm the 4th live surface during Chat use is a
   new `Rook.UI.Chat.Resources:<n>` ordinal (additional chat tab), and that
   closing that tab deregisters it (close/dispose check).

## Evidence Artifacts (this investigation)

- Presentation ring dumps: `%TEMP%\rook-vision-presentation-*.json`,
  `%TEMP%\rook-vision-presentation-mcp-dump.json` (2026-06-10 session)
- Focus trace with stuck-hidden timeline: `%TEMP%\rook\webview-focus.log`
  (11:26–11:29:33 entries; silence after 11:29:33 while refocusing = stuck)
- External watcher log: `%TEMP%\rook-darkwatch.log` (form `919264`
  `WS_VISIBLE=False` persisting across `fg=Rhino` samples)
- Live repair confirmation: user-observed gapped-toggle recovery while Rhino
  focused, 2026-06-10 ~11:35
- Prior history: issue #233, PR #191 (`6a40e3b`), PR #193 (`959753f`),
  PR #192 (failed validation branch — wedge evidence),
  `docs/superpowers/specs/2026-05-25-webview-host-presentation-coordinator-design.md`,
  `docs/superpowers/specs/2026-05-26-vision-return-edge-presentation-design.md`
