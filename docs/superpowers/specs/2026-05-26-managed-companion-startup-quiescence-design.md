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

One native boundary is in scope only if needed to keep status reporting honest: native currently polls for the managed GH bridge after `LoadPlugIn`. If managed bridge registration is intentionally delayed until quiescence, native must not present that delay as a hard companion-load failure.

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
- Do not treat "bridge unavailable while startup is not yet quiescent" as the same failure mode as "bridge unavailable after quiescent startup attempts are exhausted."

## Startup Gate

The startup gate should be small and explicit. Startup work may run only from `RhinoApp.Idle` after quiescence is observed.

Quiescence for this PR:

- The callback is running from Rhino idle.
- No Rhino command is active, using RhinoCommon command-state APIs available in this codebase/runtime.
- Any observed document-open lifecycle has completed.
- Attach-time document-open state is conservative. If the companion loads after `BeginOpenDocument` already fired, startup must not immediately green-light from the initial `documentOpening=false` default.
- At least `2` consecutive quiescent idle ticks have been observed.
- Startup has not already completed.
- Shutdown has not started.

The two-idle requirement is intentional. A single idle callback can occur between unstable startup phases. Two consecutive quiescent idle ticks are still low-latency, but they avoid treating the first idle pulse during startup/open as stable.

If reliable RhinoCommon document-state APIs are available, use them as additional conservative gates. If they are not clearly available, do not invent unverified SDK usage under pressure. The first version must still use command state, observed document-open events, and consecutive idle ticks.

The implementation plan must name the exact document-open signals used. Existing managed code already uses `RhinoDoc.EndOpenDocument`; if a matching begin-open signal is available in the referenced RhinoCommon API, use it. If begin-open cannot be verified locally, document-open state should be injectable in the startup gate tests but not faked into runtime with guessed API names.

## `OnLoad` Contract

`OnLoad` must become minimal.

Allowed in `OnLoad`:

- Trace `OnLoad minimal`.
- Detect `Rhino.Runtime.HostUtils.RunningAsRhinoInside`.
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

`OnLoad` should not call `RhinoApp.WriteLine` in this PR. For this bug, inert load means trace-to-file and hook attachment only.

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

The first implementation should defer these side effects together until quiescence. After quiescence, split local startup from bridge readiness:

- local startup work runs once after quiescence, including panels, toolbar, image/video reconcile, and sidecar backfill;
- bridge registration retries independently if native bridge readiness is unavailable.

The registry isolation proves managed startup timing is dangerous but does not identify which individual side effect wedges Rhino. Moving any of these side effects back into `OnLoad` before the product-breaking issue is eliminated would be guesswork.

## Native Bridge Contract

`NativeGhBridgeRegistrar.TryRegister()` remains deferred until quiescence. It is not classified as minimal `OnLoad` work for this PR because loading the registrar initializes a broad managed bridge surface, including shared Vision-related handlers and callback delegates. Treating that as "safe enough" would be another unproven startup side effect.

This creates an explicit coordination requirement with native companion-load status:

- Native may load the managed companion before Rhino is quiescent.
- Managed may intentionally delay GH bridge registration until quiescence.
- Native must not report that expected delay as a hard failure.

Acceptable native adjustment, if required:

- Keep `LoadPlugIn` behavior unchanged.
- Change the post-load bridge poll message from a hard "did not register" failure to a deferred/availability message, or extend/retry bridge readiness in a way that does not block Rhino startup/open.
- Do not add new native command/open dispatcher gates for this PR.
- Do not make route behavior depend on background poll success; routes should continue to check actual bridge registration on demand.

If native is not adjusted in the same PR, the PR description and live validation must explicitly acknowledge that a temporary native "bridge did not register" message can appear while managed startup is deliberately waiting for quiescence. That message must not be treated as the managed startup gate failing.

## Retry And Exhaustion

Replace timer-driven startup retries with idle-driven attempts, and split startup gating from bridge dependency readiness.

There are two distinct phases:

1. **Quiescence gate**: Rhino is still command-active, document-opening, or not yet stable. During this phase the companion is intentionally inert.
2. **Bridge readiness**: Rhino is quiescent and deferred startup work is allowed to run, but native bridge registration may not succeed yet.

Rules:

- If idle fires while not quiescent, trace the reason at low volume and return quickly.
- If idle is quiescent, increment the consecutive quiescent idle count.
- On the second consecutive quiescent idle, run startup.
- Quiescence waiting is not a failure. Slow document opens must not permanently exhaust managed startup just because idle fires many times while Rhino is still busy.
- After quiescence, run local panel/toolbar/reconcile/backfill startup once even if bridge registration is unavailable.
- If bridge registration is unavailable after local startup, keep bridge registration retrying only through future idle ticks, not timer re-entry.
- Preserve a bounded bridge retry/exhaustion concept so bridge registration cannot retry forever.
- On bridge exhaustion, leave the companion UI/runtime available where safe, mark bridge-dependent features unavailable, and write a clear trace line.

The bridge retry counter should count meaningful idle attempts after quiescence, not wall-clock timer pulses. The current 250ms `Timer` path is the thing we are removing because it can re-enter during `_Open`.

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
Bridge retries exhausted
StartupGate hooks detached
```

These are not verbose diagnostics. They are a small audit trail for startup lifecycle. They should not include JS probes, WebView probes, reflection-heavy diagnostics, or hot-path file logging outside the existing startup trace.

Idle logging must be throttled:

- log the first blocked reason;
- log when the blocked reason changes;
- log state transitions;
- optionally log every Nth repeated blocked attempt;
- do not append a file line on every idle tick if nothing changed.

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
- `BlockedQuiescence_WaitsUntilLaterQuiescentIdle`.
- `BridgeUnavailableAfterQuiescence_DoesNotRestartTimerRetry`.
- `BridgeRetryExhausted_MarksBridgeUnavailableWithoutSuppressingLocalStartup`.
- local image/video reconcile and sidecar backfill run after quiescence even if bridge registration is unavailable.
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
