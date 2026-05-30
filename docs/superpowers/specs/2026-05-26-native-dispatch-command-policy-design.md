# Native Dispatcher Command-Active Policy

## Scope

This is a P0 Rhino lifecycle safety change. It is not a Vision panel fix and
must not touch managed UI, WebView, Chat, Knowledge Graph, or Vision runtime
behavior.

The observed failure is Rhino startup with the startup screen open: clicking a
recent file enters Rhino's `_Open` command, and Rook can currently drain queued
main-thread startup work through the modal WndProc dispatch path. That can run
managed companion load, panel registration, startup reconcile, or document work
while Rhino owns the command/document-open lifecycle. The symptom is Rhino
getting stuck in `_Open`, unresponsive command line input, ignored close, and
smeared repaint.

`_Open` is the repro, not the abstraction. The invariant is:

```text
Rook must not drain Normal main-thread work while Rhino is in a command-active
or document-open lifecycle.
```

## Dispatcher Policy

Add an explicit policy to queued main-thread work:

```cpp
enum class DispatchPolicy
{
    Normal,
    CommandControl,
};
```

`CMainThreadDispatcher::Dispatch(...)` keeps `Normal` as the default so existing
call sites remain source-compatible. Each queued item stores its policy.

`Normal` includes:

- managed companion load and startup retry work
- scene graph reconcile
- document/object/layer/material/geometry handlers
- `/command` scripted command execution
- `/execute`
- panel/WebView startup or presentation work
- almost all HTTP handlers

`CommandControl` is intentionally narrow:

- `/command/prompt`
- `/command/send`, only after its current `objects_before` model iteration is
  removed or split out of the modal-safe path. The command-control portion may
  only send command-line input to an already active interactive command.
- `/command/cancel`
- prompt timeout escape dispatches such as `PostEscapeToRhino()`

`CommandControl` must not become a backdoor for arbitrary model/document work
during a Rhino command. It may inspect/send command prompt input or cancel, but
must not iterate objects, mutate model data, load panels, start WebViews, or run
startup work.

The existing `/command/send` implementation counts active document objects
before sending input. That count must be removed from the `CommandControl`
dispatch, or split into a separate `Normal` operation that does not run while a
command is active, before `/command/send` is marked `CommandControl`.

## Lifecycle Gate

The dispatcher safety gate must not depend on `SessionRecorder`. Session
recording already observes command begin/end, but dispatch safety is more
fundamental and must continue to work if session recording is disabled or
refactored.

The first implementation should add a dispatcher-owned or dispatcher-adjacent
native lifecycle watcher that tracks command depth:

```text
OnBeginCommand -> BeginCommandGuard()
OnEndCommand   -> EndCommandGuard()
```

When command depth is greater than zero:

```text
Drain CommandControl tasks.
Leave Normal tasks queued.
```

When command depth returns to zero:

```text
Post WM_ROOK_DISPATCH to drain queued Normal work later.
Do not synchronously drain Normal work inside OnEndCommand.
```

Document-open gating is allowed only if it can be implemented through already
verified native hooks in the same small boundary. If the native begin-open
lifecycle is not already proven, do not invent SDK integration under pressure.
Command-depth gating is the required first slice and should cover the recent
file `_Open` repro.

This PR proves the command-active gate. It does not claim to prove the broader
document-open invariant unless document-open gating is actually implemented in
the PR.

Command depth must be defensive:

- extra or out-of-order `OnEndCommand` notifications must not make depth
  negative
- lifecycle watcher registration/unregistration must be balanced
- the watcher must unregister before dispatcher teardown leaves callbacks with
  stale state

## Async Contract Change

Futures for queued `Normal` work may now wait while Rhino is running a command.
That is expected and safer than entering Rhino at an unsafe lifecycle point.

The P0 PR does not need to rewrite every endpoint response. Where practical,
future endpoint work should report this as Rhino busy/deferred rather than an
ambiguous dispatcher failure or broken runtime. The key contract is:

```text
If work needs Rhino model/UI state, dispatch as Normal and accept that it may wait.
If work must control an active command, dispatch as CommandControl.
If work does not need Rhino, do not use the Rhino main-thread dispatcher.
```

## Implementation Boundary

Expected files:

- `src/RookNative/Threading/MainThreadDispatcher.h`
- `src/RookNative/Threading/MainThreadDispatcher.cpp`
- a small dedicated native command lifecycle watcher near the dispatcher, if
  needed
- tiny call-site changes in:
  - `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
  - `src/RookNative/Interactive/PromptManager.cpp`

Do not edit managed UI/WebView/Vision/Chat/KG files in this PR.

Do not add command-name denylists. The policy is command-depth based.

Do not mark broad HTTP/model handlers as `CommandControl`.

## Tests And Review Gates

Automated or source-level checks should prove:

- `Dispatch(...)` defaults to `DispatchPolicy::Normal`.
- queued items store policy per task.
- command-active draining leaves `Normal` work queued.
- command-active draining runs `CommandControl` work.
- queue order is preserved for queued normal work: with `Normal A`,
  `CommandControl B`, `Normal C` enqueued during command-active, only `B` runs
  during the command, and `A` then `C` run after command end.
- after command depth returns to zero, queued `Normal` work can drain.
- companion load dispatch remains default `Normal`.
- only the audited prompt/cancel/send/escape paths are marked
  `CommandControl`.

Native build verification is required before live testing.

## Live Validation

Acceptance for this PR is lifecycle safety, not Vision success.

Required live gate:

```text
1. Launch Rhino.
2. On the Rhino startup screen, click a recent file quickly.
3. Confirm `_Open` completes.
4. Confirm Rhino remains responsive:
   - command line accepts ESC/ENTER
   - main window closes normally
   - resize/repaint is coherent
   - no smeared panels
5. Repeat several times.
```

PR #193 remains paused until this gate passes. After this PR proves the native
lifecycle invariant, Vision-specific validation can resume separately.
