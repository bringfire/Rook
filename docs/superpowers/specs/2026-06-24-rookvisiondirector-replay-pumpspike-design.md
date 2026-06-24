# RookVisionDirector Replay — Dispatch-Drain Pump Spike

- **Status:** Approved — ready for plan
- **Date:** 2026-06-24
- **Feature:** RookVisionDirector arbitrary-motion replay (PR2, first slice)
- **Predecessor spec:** `docs/superpowers/specs/2026-06-19-rookvisiondirector-arbitrary-motion-replay-design.md`
- **Branch:** `feature/rookvisiondirector-replay-pumpspike` (off `origin/main`)

## Why this spike exists

PR2 introduces native live replay of a baked animation track (`/director/replay`
+ `/director/replay/cancel`). The locked design says PR2 **must not** start with
route implementation. It must first settle one load-bearing assumption empirically:

> A synchronous replay can hold the Rhino UI thread, run a *bounded* message pump
> so the viewport redraws each frame, and **not** reentrantly execute other queued
> Rook work mid-replay.

If that assumption is false, synchronous bounded-pump replay is the wrong model and
PR2 must instead go async (start/status/cancel, frame-stepped via idle/timer, never
holding the UI thread). We settle this before designing the route so we don't build —
and then have to throw away or rescue — a replay loop founded on a false premise.

### What the dispatch code establishes (observed, not assumed)

- The native HTTP server runs an **8-thread pool** (`httplib::ThreadPool(8)`,
  `RookServer.cpp`). Handlers run on worker threads and marshal to Rhino's UI thread
  via `CMainThreadDispatcher::Instance().Dispatch(lambda)`; the worker blocks on
  `future.get()` while the lambda runs on the UI thread.
- **Two drain paths** execute queued tasks on the UI thread
  (`MainThreadDispatcher.h/.cpp`):
  1. `CRhinoIsIdle::Notify()` — the **idle door**.
  2. A `WM_ROOK_DISPATCH` (`WM_APP + 42`) WndProc subclass — the **WndProc door**,
     which fires even inside modal message loops.
- **`DrainQueue()` has no reentrancy guard.** It `std::swap`s the entire `m_queue`
  into a local queue and runs every task. The "re-entrant-safe" comment refers only
  to releasing `m_mutex` before executing tasks (so a task calling `Dispatch()`
  won't deadlock) — it does **not** prevent reentrant *execution* of other tasks.

Therefore a replay holding the UI thread and naively pumping messages can let either
door fire reentrantly and run another HTTP request's geometry op nested inside the
replay — shattering the serialize-through-UI-thread invariant that the whole
dispatcher exists to uphold.

- There is already a **proven suspension precedent**: `DrainQueue()` early-returns
  when `IsAllDispatchBlocked()` is true, which today means `m_saveDepth > 0`
  (toggled by `BeginSaveGuard`/`EndSaveGuard` so file-saves freeze dispatch). This
  spike validates a *generalized* version of that mechanism as the candidate
  production primitive.

## Goal — the single contract under test

While a UI-thread task holds the thread and runs a candidate bounded pump, can a
worker-thread `Dispatch(...)` task execute **before the holding task's lambda
returns**?

The **safe** result has three parts, all required:

1. **queued during** — the sentinel task is enqueued while the pump is running, and
2. **not executed during** — it does **not** run at any point before the holding
   lambda returns (see "after" semantics below), and
3. **executed after return** — it **does** run once the holding lambda has fully
   returned and the UI thread is released (liveness — the guard must not starve
   dispatch).

### "after" semantics (precise)

`executed_after_return` means the sentinel runs **after the held UI-thread lambda
returns**, not merely after the RAII guard's scope ends while still inside that
lambda. This distinction is load-bearing: production replay must release the UI
thread naturally and let the next idle/`WM_ROOK_DISPATCH` drain the queue. It must
**not** manually drain queued work after the guard exits but before returning.

Mechanically: immediately after the guard is destroyed and just before the holding
lambda returns, the spike asserts the sentinel has **not** executed. Any sentinel
execution observed at that point — whether during the pump or after guard-scope-exit
but still inside the lambda — counts as `executed_during_pump = true` (unsafe). Only
a sentinel that runs on a later drain pass, after the holding task's future has
resolved, satisfies `executed_after_return`.

## Non-goals

This spike deliberately does **not**:

- animate a mini-replay or apply any object transform / camera state;
- build a production pump helper or any reusable pump loop;
- design the `/director/replay` route, its payload, or cancel semantics;
- conclude "the idle door is closed" in the abstract — only "the queue did/did not
  drain under *this* pump," which is why `idle_fired_during_pump` is recorded rather
  than assumed (see Output).

## Durable artifact — the only non-throwaway code

A narrowly-scoped dispatch-drain suspension primitive in `CMainThreadDispatcher`,
plus its unit tests. This is the real mechanism PR2's replay loop will wrap its pump
in; S2 must validate **this**, not a throwaway stand-in.

- Add `m_suspendDepth` (atomic int), **distinct** from `m_saveDepth`.
- `IsAllDispatchBlocked()` returns true when **save depth OR suspend depth** is
  active.
- Add an RAII guard **`DispatchDrainSuspension`** with exactly one promise:
  *queued dispatcher tasks are not drained while this guard is alive on the UI
  thread.*
  - **Nest-safe** — increments on construction, decrements on destruction;
    nested guards compose.
  - **Restores depth on destruction**, including on exception unwind.
  - **Does not block worker-thread enqueue.** `Dispatch()` still accepts and queues
    tasks while the guard is alive; only UI-thread *draining* is deferred.
  - **Wakes the pump on release.** When suspend depth drops to **zero**, the
    outermost guard's destructor must `PostMessage(m_subclassedHwnd,
    WM_ROOK_DISPATCH, 0, 0)` if the dispatcher has a subclassed window — exactly
    mirroring `EndSaveGuard()`. This makes liveness a property *of the guard itself*:
    queued work drains promptly once the held lambda returns, rather than waiting on
    an incidental later idle event or posted message. (Only the outermost release
    posts, so nested guards don't spam the queue.)
- **Naming:** not "save guard." Replay is not semantically tied to file-save; the
  primitive is a general dispatch-drain suspension. The save guard remains its own
  concern; both simply contribute to `IsAllDispatchBlocked()`.

### Durable tests (real, not scaffolding)

- depth nesting composes (two live guards ⇒ still blocked after the inner exits);
- destruction restores depth (blocked while alive, unblocked after scope, including
  on exception unwind);
- enqueue-still-allowed (a `Dispatch()` during an active guard returns a valid,
  pending future and the task is present in the queue);
- post-guard liveness (a task queued during an active guard drains on the next drain
  pass after the guard exits);
- wake-on-release (the outermost guard's release posts `WM_ROOK_DISPATCH` when
  suspend depth reaches zero, and a *nested* guard's release does **not**) — verified
  via the same window/post seam the dispatcher already exposes for `EndSaveGuard`.

## Throwaway scaffolding — removed before the PR is reviewable

> **Shipping rule:** the spike PR must **not** ship the throwaway route or
> instrumentation. The durable output is **only** the `DispatchDrainSuspension`
> guard + its tests, plus the written evidence (findings) from running the spike.
> The temporary route, sentinel rig, counters, and pump bodies may exist *during*
> the investigation but must be removed before the PR is opened for review. While
> they exist they are gated behind a test-hook env flag (per the existing
> `RunScriptSafetyTestHooks` pattern) and never ship enabled.

- **`/director/_pumpspike`** route (test-hook gated).
- **Sentinel rig** with a handshake (no sleep races): the probe sets an atomic
  `pump_active` at pump start; a worker thread waits on it, then `Dispatch`es the
  sentinel — so the sentinel deterministically lands mid-pump. The sentinel records
  whether it ran before the holding lambda's end-of-lambda marker.
- **Instrumentation** (two distinct metrics — do not conflate "entered" with
  "executed"):
  - `drain_attempt_count` — atomic incremented at `DrainQueue` *entry*, snapshotted
    around the pump. **May be nonzero in S2** and that is *positive* evidence: with a
    working guard, idle/WndProc still *enter* `DrainQueue` and bail at
    `IsAllDispatchBlocked()`, which proves both doors were actually exercised against
    the guard. A nonzero `drain_attempt_count` with zero task execution is the
    ideal S2 result.
  - `tasks_executed_during_pump` — count of queued tasks (the sentinel) that
    *actually ran* before the holding lambda returned. **Must be `0` for safe.** This
    is the real failure signal, separate from mere `DrainQueue` entry.
  - `idle_fired_during_pump` — did `CRhinoIsIdle::Notify` actually fire during the
    pump? Prevents a "safe" S1 from *falsely* reassuring us the idle door is closed
    when idle simply never got a chance to fire.
- **Pump bodies** for S0/S1/S2.

## Strategy matrix (one run each, shared sentinel + instrumentation)

| Run | Pump | Expected | Meaning |
|-----|------|----------|---------|
| **S0 Control** | `PeekMessage` pumping *everything*, no guard | **Unsafe** — sentinel runs before lambda returns | Validates the harness. A *clean* S0 ⇒ suspect instrumentation or an unrepresentative pump — halt and fix before trusting any verdict. |
| **S1 Filtered** | `PeekMessage` excluding the `WM_ROOK_DISPATCH` range, no guard | Informative only | Unsafe ⇒ proves the idle door matters (WndProc filtering alone is insufficient). Safe ⇒ **not trusted** unless `idle_fired_during_pump` shows idle had a real chance and still did not drain. |
| **S2 Guarded** | pump wrapped in `DispatchDrainSuspension` | **Safe** (the goal) | The sole acceptable synchronous-pump path: queued-during, not-executed-during, executed-after-return. |

## Output — decision-grade JSON (per run)

Example shows a **safe (S2)** run. Note `drain_attempt_count` is **nonzero** here —
that is expected and good (both doors entered `DrainQueue` and bailed at the guard).
S0, by contrast, is expected to show `executed_during_pump: true` and
`tasks_executed_during_pump >= 1`.

```json
{
  "pump_strategy": "S0_control | S1_filtered | S2_guarded",
  "queued_during_pump": true,
  "executed_during_pump": false,
  "executed_after_return": true,
  "drain_attempt_count": 3,
  "tasks_executed_during_pump": 0,
  "idle_fired_during_pump": true,
  "messages_processed": 1234
}
```

- `queued_during_pump` — sentinel was enqueued while the pump ran (sanity: the test
  actually exercised the scenario).
- `executed_during_pump` — sentinel ran at any point before the holding lambda
  returned (per "after" semantics above). **Must be `false` for safe.**
- `executed_after_return` — sentinel ran after the holding lambda returned and the
  thread was released. **Must be `true` for safe** (liveness).
- `drain_attempt_count` — `DrainQueue` *entries* during the pump. Nonzero is fine
  (and desirable) in S2 — it shows the doors were exercised and the guard held.
- `tasks_executed_during_pump` — tasks that actually *ran* before the lambda
  returned. **Must be `0` for safe.** This, not `drain_attempt_count`, is the
  failure signal.
- `idle_fired_during_pump` — a **tripwire**, not a coverage metric. During a
  synchronous hold the UI thread is busy in the holding lambda, so Rhino is never
  idle and `CRhinoIsIdle::Notify` structurally **cannot** fire — `false` is the
  expected, correct result and means *the idle door was not a factor for the held
  pump*. This is the key realization: the idle door drains only when the app is
  genuinely idle, which never happens while a replay holds the thread, so the
  **WndProc door is the only reentrancy path during a hold** (which S1 filters and
  S2's guard blocks). A `true` here would be surprising and must be investigated;
  it does not, on its own, make S1's idle behavior "tested-safe."
- `messages_processed` — pump activity, recorded if practical.
- `_inconclusive` (added by the runner) — set when `queued_during_pump` is false:
  the sentinel never queued during the pump, so the run did **not** exercise the
  scenario and must not be scored "safe."

## Decision table → PR2 replay model

- **S2 safe AND S0 unsafe (control validates harness):** the bounded-pump assumption
  holds. PR2 builds **synchronous replay** wrapping its per-frame pump in
  `DispatchDrainSuspension`.
- **S2 unsafe** (the guard cannot close both doors — e.g. Rhino's own pump drains
  the queue underneath us): abandon synchronous pump. PR2 goes **async
  start/status/cancel**, frame-stepped via idle/timer, never holding the UI thread —
  the fallback the roadmap already names.
- **S0 unexpectedly safe:** **halt.** The harness or pump is not representative; fix
  it before trusting any S1/S2 result.
- **S1 safe but `idle_fired_during_pump == false`:** treat as inconclusive for the
  idle door; do not promote filtering as a standalone mitigation.

## Practicalities

- **Empirical / live.** The verdict requires a native build
  (`scripts/build-native.bat` via `cmd /c`) and a running Rhino to exercise — this is
  a UI-thread behavior test, the canonical observe-before-theorizing case. It cannot
  be settled by reading code alone.
- **Branch:** `feature/rookvisiondirector-replay-pumpspike`, off `origin/main` (not
  stacked on unmerged PR1).
- **Native-only change surface** for the durable artifact: `MainThreadDispatcher.h`
  / `.cpp` + a dispatcher test. No managed, no Python, no `server.py`.
- **Evidence is a deliverable.** The recorded per-run JSON (and the chosen PR2 model)
  is written up as the durable, human-readable output of the spike, since the route
  and instrumentation that produced it will have been removed.
