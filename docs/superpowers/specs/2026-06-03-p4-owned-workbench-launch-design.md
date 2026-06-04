# P4 — Owned Workbench Session Launch

- **Date:** 2026-06-03
- **Status:** Design approved (Rook ⇄ Codex ⇄ user; spec review folded — invalid-discovery-record code, panel config-error guard, cleanup-ladder accuracy). Ready for the implementation plan.
- **Author:** Claude (synthesis; Codex corrections folded in)
- **Area:** New `mcp_server/src/rook/workbench.py`; `mcp_server/src/rook/runtime_harness.py` (add a typed `DiscoveryFailureReason`); `mcp_server/src/rook/targeting.py` (meta + non-routed-session classification); `mcp_server/src/rook/server.py` (3 tool dispatches + panel-lock guard). Reuses `runtime_harness` primitives (`OwnedRhinoDiscovery`, the cleanup ladder, window enumeration). **No RookNative/C++ change.**
- **Relationship:** Implements **P4** of the north-star P1–P7 roadmap (`docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`). Builds on P1 (`session_id_for_instance` / `classify_session_liveness`), P3 (the `session` selector + the non-routed-`session` exception list), and the owned-Rhino runtime harness. Discipline: P4 **owns process lifecycle, not document lifecycle** — Save/fan-in is the membrane (P6); the durable cross-process registry is P5.

---

## 1. Goal & the gap

The plane can now **see** sessions (P1), tell the **truth** about their failures (P2), and **route** explicit work to a named session (P3). All three are observational or routing — none of them *creates* a session. **P4 is the first slice that owns a process:** it launches a disposable, **owned** Workbench Rhino, waits for it to bind, hands back its `session` id (so P3 routing targets it immediately), and can close it on demand.

Two launch paths exist today and neither is the coordinator capability:
- **`rhino_launch`** (server.py:12746) — a single-client "is THE Rhino up?" convenience. It launches a *generic* Rhino with no PID correlation, polls a generic `/ping`, and auto-binds only when exactly one instance exists. It cannot model "the Rhino I own" among several.
- **The runtime harness** (`runtime_harness.py`) — a *test* tool that already contains the real owned-launch machinery (PID-correlated discovery wait, startup/timeout failure differentiation, a graceful (WM_CLOSE) → force (`taskkill`/`process.kill`) cleanup ladder, window enumeration), but is structured as a one-shot (launch → run smoke → cleanup) with no persistent owned-set and a sync/blocking shape.

P4 **promotes** the harness's primitives into a coordinator-facing capability and adds the ownership boundary.

---

## 2. Scope

**In scope**
- Three **meta** tools: `rhino_workbench_launch`, `rhino_workbench_list`, `rhino_workbench_close` (§4).
- An **in-process** owned-set (this MCP runtime only) with an `asyncio.Lock` guard (§5, §10).
- Async launch + PID-correlated wait-for-bind, reusing `OwnedRhinoDiscovery.wait_for_ready` off-thread (§6).
- A **typed** launch-failure taxonomy (`DiscoveryFailureReason` → structured codes) + a conservative window/blocked-startup hint (§7).
- Close = **direct force by default**, `graceful:true` escape hatch, an explicit `cleanupStatus` mapping, owned-only fail-closed (§8).
- Cross-phase wiring: meta-classification, the P3 non-routed-`session` exception, panel-lock fail-closed on all three tools (§9).

**Out of scope** (explicit)
- Durable / cross-process ownership registry, adopt-on-restart, the `adopted` flag, auto-spawn-on-slotless-call, respawn policy (**P5** — SQLite SlotStore).
- Document open / save / export / merge (**P6** — the Save membrane). P4 launches a **blank** Workbench; opening the assigned `.3dm` is a separate P3-routed `rhino_document_open` to the new session.
- Work allocation / per-file orchestrators (**P7**).
- Any change to `rhino_launch` (legacy single-client convenience stays) or to RookNative/C++.

---

## 3. The constraint (one line)

> A Workbench is **owned process lifecycle, nothing more**: P4 launches a disposable owned Rhino, waits for PID-correlated discovery to bind, tracks it **in-process**, and closes **only what this runtime owns** — discarding unsaved document state by design. Document persistence is P6; durable ownership is P5.

---

## 4. The three tools (all **meta**, `requires_rhino=False`)

### 4.1 `rhino_workbench_launch`
```
args:  { readinessTimeoutSeconds?: int = 90, rhinoExe?: str }
ok:    { success: true, session: "rhino-<pid>", processId: <pid>, port: <int>,
         owned: true, mode: "workbench", boundInSeconds: <float> }
fail:  { success: false, data: { code: <§7>, message, ...hint } }
```
Launches a **blank** owned Rhino, waits for `instance-<pid>-native.json` + `/ping`, registers it in the owned-set, returns its session. Default readiness **90s** (the P3 live smoke proved 30s flakes on a cold start). `rhinoExe` defaults to `C:/Program Files/Rhino 8/System/Rhino.exe` (override exists for tests/non-default installs).

### 4.2 `rhino_workbench_list`
```
ok:    { success: true, workbenches: [ { session, processId, port, mode: "workbench",
                                         launchedAt, liveness: {state,pidAlive,portListening} } ] }
```
Lists **only** sessions this MCP runtime owns, each annotated with P1 liveness so orphaned/dead owned sessions are visible. **Not** a replacement for `rhino_sessions` (which remains the full fleet/perception surface); `rhino_workbench_list` answers the narrower "what can this coordinator close?"

### 4.3 `rhino_workbench_close`
```
args:  { session: "rhino-<pid>", graceful?: bool = false }
ok:    { success: true, session, owned: true, mode: "workbench", closed: true,
         cleanupStatus: "graceful_exit" | "forced_kill" | "already_exited",
         discardedUnsavedChanges: <bool> }
fail:  { success: false, data: { code: "not_owned" | "invalid_session_id" | "force_kill_failed", message } }
```
Closes/reaps **only** owned sessions. A session not in the owned-set → **`not_owned`** (fail closed), even if it is discovered and alive. Default terminates directly (§8).

---

## 5. Ownership model

- **Owned-set** = an in-process `dict[pid → OwnedWorkbench]`, where `OwnedWorkbench` retains the `OwnedRhinoRecord` (pid/host/port/path), the **`subprocess.Popen` handle** (needed by the cleanup primitives), the `session` id, and `launched_at`. Populated on successful launch, pruned on successful close. **No persistence.**
- **Owned vs adopted vs panel-locked:**
  - *Owned (Workbench)* — this runtime launched it; closable. Disposable.
  - *Adopted* — discovered but not launched here (the user's Rhino or a peer's). Routable (P3); **never closable** here.
  - *Panel-locked / misconfigured panel* — the embedded chat tab, or a malformed panel-mode startup. **All three workbench tools fail closed** under either a panel target **lock** or a panel target **config error** (a single-document Assist tab — or a broken panel config — is not a coordinator; same stance as `spawn_agent`/`plan_and_execute`).
- **The close guard (safety invariant):** `close(session)` parses the pid (malformed → `invalid_session_id`, reusing P3's code); if the pid is **not in the owned-set → `not_owned`**. A coordinator can only dispose what it owns. This is P4's analog of P3's panel-lock fail-closed.
- **Restart / orphan boundary (explicit):** the owned-set (and the `Popen` handles) live in process memory. If the MCP server restarts, the set is empty → previously-owned Rhinos become indistinguishable from adopted → they are **not** closable and will **not** be auto-reaped (safe). Re-adopting them is P5's durable-registry job. `rhino_workbench_list` reflects only what the *current* process owns.

---

## 6. Launch + wait-for-bind (reused, made async)

```
Popen([rhinoExe])  →  pid = process.pid
       │
       ▼  await asyncio.to_thread( OwnedRhinoDiscovery().wait_for_ready, pid, process, ping_native,
       │                          timeout_seconds=readinessTimeoutSeconds )
       ▼
OwnedRhinoRecord(pid, host, port, …)   →  register under the lock  →  session = rhino-<pid>
```
`wait_for_ready` (reused as-is, run off-thread so the event loop never blocks) already: watches `process.poll()` for early exit, polls `instance-<pid>-native.json`, validates it (loopback-only host, pid-match, `pluginType=="native"`, positive port — the hardened `read_owned_record`), and pings the native port. The launch path therefore inherits P-grade discovery hygiene without re-implementing it.

> **Model note:** Rook's bind is *PID-correlated discovery*, not McNeel's *port-env*. We launch, capture the OS pid, and wait for RookNative's self-published discovery file. Discovery stays the single source of truth; there is no port pre-assignment or collision management.

---

## 7. Launch-failure taxonomy (typed, P2-style)

**No substring matching.** A new `DiscoveryFailureReason` enum is added in `runtime_harness.py`, and `DiscoveryError` gains a `reason: DiscoveryFailureReason | None` attribute set at `wait_for_ready`'s **five** terminal raise sites (additive — the harness's `str(exc)` warnings are unchanged). `workbench.py` catches `DiscoveryError`, reads `.reason`, and maps to the public code:

| origin | `DiscoveryFailureReason` | public `code` | `retryable` |
|---|---|---|---|
| exe path missing (pre-launch) | — | `rhino_executable_not_found` | false |
| `Popen` raises `OSError` | — | `workbench_launch_failed` | false |
| process exited **before** discovery appeared | `EXITED_BEFORE_BIND` | `workbench_exited_before_bind` | true |
| process exited **after** discovery, before pingable | `EXITED_BEFORE_READY` | `workbench_exited_before_ready` | true |
| timeout, **no** discovery file ever appeared | `BIND_TIMEOUT_NO_DISCOVERY` | `workbench_bind_timeout` (+ window hint) | true |
| timeout, a file appeared but **failed validation** (malformed JSON / wrong pid / wrong pluginType / non-loopback / bad port) | `INVALID_DISCOVERY_RECORD` | `workbench_discovery_invalid` | true |
| timeout, a **valid** discovery file appeared but never pingable | `BIND_TIMEOUT_NO_PING` | `workbench_listener_unreachable` | true |

**Window / blocked-startup hint (conservative).** Only on `workbench_bind_timeout` — process alive, **nothing** published (*not* on `workbench_discovery_invalid`, where a file *was* published but is malformed: that is a publication bug, not a blocking modal): enumerate `describe_windows_for_pid(pid)`; if visible windows exist, attach —
```json
{
  "code": "workbench_bind_timeout",
  "blockingWindows": [ { "hwnd": "0x...", "title": "...", "visible": true } ],
  "diagnosticConfidence": "window_present_no_discovery",
  "next_action": "The owned Rhino is alive but RookNative never published discovery — likely a modal startup window (license/activation, 'another instance', or template chooser). Inspect and dismiss, then retry with a longer readinessTimeoutSeconds."
}
```
It is a **hint, not a diagnosis** — window titles are frequently empty, so the field is `diagnosticConfidence: "window_present_no_discovery"`, never `licenseDialogDetected`. (This is the P2-`crash_artifact` discipline: surface a confidence-tagged pointer, don't over-claim.)

---

## 8. Close semantics

- **Default = direct force.** `close` terminates the owned process via `force_owned_process_cleanup` (`taskkill /F /T /PID`, then a `process.kill()` fallback) — no `WM_CLOSE` attempt, so no dirty-document modal stall. `discardedUnsavedChanges: true`. This aligns with discard-by-design: Workbench *compute* is disposable; keeping a result is the explicit Save step (P6).
- **`graceful:true` escape hatch.** Attempts `request_external_graceful_close` (WM_CLOSE) first, falling back to force on timeout. Documented to possibly stall on a dirty document. `discardedUnsavedChanges` reflects whether a forced fallback occurred.
- **`cleanupStatus` — explicit mapping** from the harness `CleanupStatus` primitives to the public surface (P4 does **not** leak the raw enum):

  | internal outcome | public `cleanupStatus` | envelope |
  |---|---|---|
  | pid already gone before cleanup | `already_exited` | success, pruned |
  | `graceful:true` WM_CLOSE exited cleanly | `graceful_exit` | success, pruned |
  | direct force succeeded / graceful→force fallback | `forced_kill` | success, pruned |
  | force failed (process still alive) | — (code `force_kill_failed`) | **success:false**, kept in set |

  The public surface is exactly these four outcomes (the three statuses plus the `force_kill_failed` code); the harness's other `CleanupStatus` members are not leaked. The owned-set entry is pruned **only** on confirmed termination; on `force_kill_failed` the entry is **retained** (still owned, still listable, retry-able).

---

## 9. Cross-phase seams (the parts that touch P1/P3)

- **Meta-classification (the P1 lesson):** add `rhino_workbench_launch` / `rhino_workbench_list` / `rhino_workbench_close` to `targeting._META_TOOLS` **and** `_ALL_KNOWN_TOOLS`, so `policy_for_tool` returns `RhinoToolPolicy(False, "meta")`. Otherwise `UNKNOWN_TOOL_POLICY` (requires_rhino=True, mutate) routes them through `resolve_tool_route` and they break at 0/multiple Rhinos.
- **P3 non-routed-`session` exception:** `rhino_workbench_close` is a non-routed tool that legitimately owns a `session` argument → it must join `targeting._NON_ROUTED_SESSION_ARGUMENT_TOOLS` (alongside `rhino_session_capabilities`) via the public `allows_non_routed_session_argument` set, or P3's guard rejects it with `session_not_targetable`. *(This is the intended payoff of P3's explicit-exception design — exactly the "grows only by intentional addition" case.)*
- **Panel fail-closed (lock OR config error):** in `call_tool`, before dispatch, the three workbench tools return a structured refusal when `get_panel_target_lock() is not None` **or** `get_panel_target_config_error() is not None`. The config-error case is load-bearing because these tools are *meta* (`requires_rhino=False`), so the existing config-error guard at server.py:19294 — which fires only for `requires_rhino or name == "rhino_launch"` — would **not** catch them; P4 guards them explicitly (mirroring the `spawn_agent`/`plan_and_execute` lock guard at server.py:19301).

---

## 10. Concurrency

A **module-level `asyncio.Lock`** in `workbench.py` guards owned-set **reads and writes** — not the long I/O. Granularity:
- **launch:** `Popen` + `wait_for_ready` run **outside** the lock (a 90s wait must not serialize `list`/`close`); only the final owned-set insert is taken under the lock.
- **list:** snapshot the set under the lock, then classify liveness outside it.
- **close:** under the lock, check membership and **pop** the entry (claiming it); run cleanup outside the lock; on `force_kill_failed`, re-insert under the lock.

Benign race (accepted for P4's single-coordinator, deliberate-close model): a concurrent second `close` of the same session during cleanup sees it already popped → `not_owned`. A `close` racing a not-yet-bound `launch` sees `not_owned` (you cannot close what has not bound) — correct.

---

## 11. Scope boundaries (what P4 does **not** do)

- No durable/cross-process registry, no adopt-on-restart, no `adopted` flag, no auto-spawn, no respawn (P5).
- No document open/save/export/merge; launches a blank Workbench (P6).
- No work allocation (P7). No change to `rhino_launch`. No RookNative/C++ change.

---

## 12. Testing

**Unit** (`tests/test_workbench.py`, plus a `DiscoveryFailureReason` test in `tests/test_runtime_harness.py`):
- **Typed taxonomy** — feed `wait_for_ready` a fake `ProcessLike` and a fake `ping` to drive each of the **five** `DiscoveryFailureReason` values: exits before/after a faked discovery file (`EXITED_BEFORE_BIND` / `EXITED_BEFORE_READY`), times out with no file (`BIND_TIMEOUT_NO_DISCOVERY`), times out with a **present-but-invalid** file — wrong pid / non-loopback / bad port (`INVALID_DISCOVERY_RECORD`), and times out with a valid-but-unpingable file (`BIND_TIMEOUT_NO_PING`); then assert `workbench.py` maps each → the right public code, and that `workbench_discovery_invalid` gets **no** window hint. (Proves no substring matching.)
- **Owned-set** — launch (monkeypatched `Popen` + `wait_for_ready`) registers the session; `list` projects it with liveness; `close` prunes it.
- **Close guard** — `close` on a pid **not** in the owned-set → `not_owned`; on an already-exited owned pid → `already_exited` (pruned); a `force_kill_failed` keeps the entry.
- **`cleanupStatus` mapping** — default path → `forced_kill`; `graceful:true` clean exit → `graceful_exit`.
- **Window hint** — `workbench_bind_timeout` with a monkeypatched `describe_windows_for_pid` returning a visible window → `blockingWindows` + `diagnosticConfidence: "window_present_no_discovery"` present; with none → absent.
- **Cross-phase** — the three tools resolve as `meta` (`policy_for_tool`); `allows_non_routed_session_argument("rhino_workbench_close") is True`; `call_tool` refuses all three under a panel lock; concurrency-lock serializes interleaved set ops.

**Live smoke (owned Rhino — the established pattern, and the cleanest one yet):** `scripts/run_rhino_runtime_harness.py --smoke p4-workbench-lifecycle` + a new `mcp_server/tools/p4_workbench_lifecycle_live_harness.py`. Unlike P3's, this smoke needs **no synthetic records** — it genuinely launches and closes a real owned Rhino through `server.call_tool`:
- `rhino_workbench_launch` binds a real new owned Rhino → returns `session`/`port`/`boundInSeconds`.
- `rhino_workbench_list` shows exactly that one owned session, `liveness.state == "live"`.
- a P3-routed mutation (`rhino_execute` with `session=<the new one>`) lands in it (P3↔P4 compose).
- `rhino_workbench_close` terminates it → `cleanupStatus: "forced_kill"`, and a follow-up `list` no longer shows it.
- `rhino_workbench_close` on an **adopted** pid (the harness's own owned Rhino is launched by the *runner*, not by the in-process owned-set — so from the smoke's perspective it is not owned) → `not_owned`.

---

## 13. Decision log

- **P4 = owned process lifecycle, not document lifecycle.** Launch a disposable owned Workbench; Save/fan-in is the membrane (P6); the durable registry is P5.
- **Three new `rhino_workbench_*` meta tools** (`launch`/`list`/`close`); `rhino_launch` untouched; `rhino_sessions` remains the perception surface, `rhino_workbench_list` the narrower ownership surface.
- **Owned = in-process only** (retains the `Popen` handle); MCP restart drops ownership → orphans become safe/adopted (never auto-reaped). Explicit P4/P5 boundary.
- **Close guard:** only owned sessions are closable; adopted/panel/user → `not_owned` (fail closed).
- **Bind = PID-correlated discovery** (reuse `wait_for_ready` off-thread), not McNeel's port-env.
- **Typed failure taxonomy** via `DiscoveryFailureReason` on `DiscoveryError` — no substring matching in production; seven public codes (incl. `workbench_discovery_invalid` for a present-but-invalid discovery file, distinct from the no-file `workbench_bind_timeout`).
- **License/window detection is a hint, not a diagnosis** — `blockingWindows` + `diagnosticConfidence: "window_present_no_discovery"`, never `licenseDialogDetected`.
- **Close defaults to direct force** (discard-by-design, no dirty-doc stall); `graceful:true` opt-in WM_CLOSE ladder; explicit `cleanupStatus` mapping from the harness enum; entry pruned only on confirmed termination.
- **Panel-lock fail-closed on all three tools.** Meta-classification + the P3 non-routed-`session` exception are required wiring.
- **`asyncio.Lock` guards owned-set ops** at fine granularity (not across the launch wait).
