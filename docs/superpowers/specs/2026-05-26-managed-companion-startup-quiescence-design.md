# Managed Companion Startup Quiescence

## Problem

The startup recent-file `_Open` hang has been isolated to managed companion load timing.

Observed boundary:

```text
RookNative enabled + managed companion registry removed
  => startup recent-file _Open does not wedge Rhino

RookNative enabled + managed companion registry present
  => startup recent-file _Open can wedge Rhino
```

The native companion-autoload A/B was not sufficient because Rhino still loaded the managed companion through its own plugin registry entry. The registry-level absence test was the valid isolation: no fresh `companion-startup.log` was created, RookNative discovery still ran, and Rhino did not wedge.

This means the product fix should not be another native dispatcher variant and should not depend on registry/load-mode behavior. Rhino may load the managed companion at a bad time. The managed companion must make that load harmless.

## Goal

Make managed companion `OnLoad` inert during Rhino startup/open and run meaningful startup work only after Rhino reaches a quiescent idle state.

The intended contract is:

```text
Rhino loads managed companion during startup/open
  -> OnLoad records minimal state, attaches lifecycle hooks, and returns

Rhino reaches stable idle with no active command/open lifecycle
  -> managed companion startup work runs once on the UI thread
```

This PR proves managed companion startup safety. It does not attempt to fix Vision dark-panel behavior directly, and it should not include native dispatcher, WebView, Vision, Chat, Knowledge Graph, or registry behavior changes except where those are startup side effects currently launched from `RookPlugin`.

## Evidence

The decisive diagnostic was:

1. Close Rhino.
2. Export and remove only the managed companion HKCU key:
   `HKCU\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B`.
3. Leave the RookNative key intact.
4. Move `%TEMP%\rook\companion-startup.log`.
5. Launch Rhino and click a recent file from the startup screen.

Result:

- Rhino did not wedge.
- No fresh `companion-startup.log` was created.
- RookNative discovery still wrote and removed its native discovery file.
- Restoring the managed key restored normal machine state.

Interpretation: the wedge requires managed companion load/startup overlap with Rhino startup/open. RookNative alone is not sufficient to reproduce this failure.

## Non-Goals

- Do not prevent Rhino from loading the managed companion.
- Do not change registry `LoadMode` as a product fix.
- Do not add local-machine flags or environment toggles.
- Do not keep adding native dispatcher command/open gates for this bug.
- Do not change Vision/WebView presentation logic in this PR.
- Do not use fixed timer delays as the durable mechanism.
- Do not move individual startup side effects earlier unless proven safe in a later PR.

## Startup Gate

The startup gate should be small and explicit. Startup work may run only from `RhinoApp.Idle` after quiescence is observed.

Quiescence for this PR:

- The callback is running from Rhino idle.
- No Rhino command is active, using RhinoCommon command-state APIs available in this codebase/runtime.
- Any observed document-open lifecycle has completed.
- At least `2` consecutive quiescent idle ticks have been observed.
- Startup has not already completed or exhausted.
- Shutdown has not started.

The two-idle requirement is intentional. A single idle callback can occur between unstable startup phases. Two consecutive quiescent idle ticks are still low-latency, but they avoid treating the first idle pulse during startup/open as stable.

If reliable RhinoCommon document-state APIs are available, use them as additional conservative gates. If they are not clearly available, do not invent unverified SDK usage under pressure. The first version must still use command state, observed document-open events, and consecutive idle ticks.

## `OnLoad` Contract

`OnLoad` must become minimal.

Allowed in `OnLoad`:

- Trace `OnLoad minimal`.
- Detect `Rhino.Runtime.HostUtils.RunningAsRhinoInside`.
- Write a short status line if needed.
- Attach idle/document lifecycle hooks used by the startup gate.
- Start the gate in an inactive/pending state.
- Return `LoadReturnCode.Success`.

Disallowed in `OnLoad`:

- `RegisterStartupPanels()`.
- `RhinoApp.InvokeOnUiThread(new Action(TryInitializeRuntime))`.
- Starting `Timer -> InvokeOnUiThread` startup retries.
- `NativeGhBridgeRegistrar.TryRegister()`.
- `EnsureToolbarLoaded()`.
- image/video job reconcile.
- sidecar backfill scheduling.
- any panel, toolbar, bridge, job, or runtime startup side effect.

## Deferred Startup Work

When the gate reaches quiescence, run the existing companion startup sequence once on the UI thread.

Deferred work includes:

- startup panel registration for Chat, Vision, and Knowledge Graph;
- managed toolbar load for standalone Rhino;
- native GH callback bridge registration;
- companion runtime initialization state currently represented by `_serverStarted`;
- image job reconcile;
- video job reconcile;
- video sidecar backfill scheduling;
- cleanup of idle/document startup hooks after successful completion.

The first implementation should defer these side effects together. The registry isolation proves managed startup timing is dangerous but does not identify which individual side effect wedges Rhino. Splitting startup work before the product-breaking issue is eliminated would be guesswork.

## Retry And Exhaustion

Replace timer-driven startup retries with idle-driven attempts.

Rules:

- If idle fires while not quiescent, trace the reason at low volume and return quickly.
- If idle is quiescent, increment the consecutive quiescent idle count.
- On the second consecutive quiescent idle, run startup.
- If startup cannot complete because the native bridge is not available, keep retrying only through future idle ticks, not timer re-entry.
- Preserve a bounded retry/exhaustion concept so the companion cannot retry forever.
- On exhaustion, leave the companion loaded but inactive and write a clear trace line.

The retry counter should count meaningful idle attempts, not wall-clock timer pulses. The current 250ms `Timer` path is the thing we are removing because it can re-enter during `_Open`.

## Lifecycle Hooks

Use only hooks needed to decide quiescence and detach them after startup completes or shutdown begins.

Expected hooks:

- `RhinoApp.Idle` for the only startup execution path.
- managed document-open begin/end lifecycle if available and already used safely in the repo/runtime.

Document-open tracking should be conservative:

- begin/open observed => block startup and reset consecutive idle count;
- end/open observed => allow future idle to re-check, but do not immediately run startup inline.

Startup work must never run directly from document-open callbacks.

## Trace Markers

Keep lifecycle trace markers low-volume and always useful:

```text
OnLoad minimal
StartupGate idle attempt: commandActive=<bool> documentOpening=<bool> stableIdleCount=<n>
StartupGate blocked: <reason>
StartupGate quiescent: running startup
Startup complete
Startup exhausted
Startup shutdown: hooks detached
```

These are not verbose diagnostics. They are a small audit trail for startup lifecycle and are only written on load/idle attempts/startup completion. They should not include JS probes, WebView probes, reflection-heavy diagnostics, or hot-path file logging outside the existing startup trace.

## Tests

Automated tests should focus on the managed startup gate contract. Prefer pure/fakeable logic where possible; source-level tests are acceptable where Rhino APIs prevent direct unit testing.

Required test coverage:

- `OnLoad_DoesNotRegisterPanelsOrStartRuntime`.
- `OnLoad_DoesNotInvokeTryInitializeRuntime`.
- `OnLoad_DoesNotStartTimerRetry`.
- `CommandActive_DoesNotStart`.
- `DocumentOpenActive_DoesNotStart`.
- `FirstQuiescentIdle_DoesNotStart`.
- `SecondConsecutiveQuiescentIdle_StartsOnce`.
- `InterruptedQuiescence_ResetsStableIdleCount`.
- `StartupComplete_DetachesHooksAndDoesNotRunAgain`.
- `RetryLimitExceeded_LeavesCompanionInactive`.
- existing panel registration remains wrapped as non-fatal when deferred startup runs.
- existing reconcile/backfill failures remain non-fatal when deferred startup runs.

Existing `RookPluginLifecycleSourceTests` currently assert some behavior that is now unsafe, including immediate `RhinoApp.InvokeOnUiThread(new Action(TryInitializeRuntime))` from `OnLoad`. Those tests should be updated to assert the new inert `OnLoad` contract.

## Live Validation

This PR is not complete until live validation passes on the default product path with the managed companion registry restored.

Required live gate:

1. Build and deploy the managed companion normally.
2. Ensure the managed companion registry key is restored.
3. Close all Rhino processes.
4. Launch Rhino.
5. Immediately click a recent file from Rhino's startup/recent-files screen.
6. Rhino must not wedge in `_Open`.
7. After document open completes and stable idle occurs, the companion must finish startup.
8. Verify Rook panels are available.
9. Verify native bridge/MCP behavior still works.
10. Repeat the recent-file startup path several times.

Acceptance is:

```text
startup recent-file _Open does not wedge Rhino
managed companion starts after open/idle
Rook panels/bridge/routes work after startup settles
```

This PR should not be judged by Vision dark-panel validation. If this passes, return to the paused Vision work on a stable startup foundation.

## Rollback

Rollback is a code rollback. There should be no hidden runtime switch, environment variable, registry dependency, or local machine setting that decides whether this behavior is active.

The managed companion must be safe when Rhino loads it at the worst possible time.
