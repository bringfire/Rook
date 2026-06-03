# P2 — Structured Bridge-Failure Diagnosis (+ locate-only crash artifacts)

- **Date:** 2026-06-03
- **Status:** Design approved (Rook ⇄ Codex ⇄ user, with edits folded in). Ready for the implementation plan.
- **Author:** Claude (synthesis; Codex refinements folded in)
- **Area:** `mcp_server/src/rook/bridge.py` (`call_rhino`, `get_session_capabilities`) + a new locate-only crash-artifact finder. Reference: `RhinoMCP/rhino/router/{ProxyDispatcher,RhinoCrashReportFinder}.cs`.
- **Relationship:** Implements **P2** of the north-star P1–P7 roadmap (`docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`). Builds directly on P1's liveness primitives (`_is_pid_alive` / `_is_port_listening` / `classify_session_liveness`), shipped in PR #209 (`05f7909`). Discipline unchanged: **observe, don't own** — no relaunch, no allocation.

---

## 1. Goal & the gap

P1 made Rook's *inspection* tools truthful (`rhino_sessions` / `rhino_session_capabilities`), but the **actual tool-call path still lies on failure**. Today `call_rhino` returns unstructured strings:

- `except httpx.ConnectError` (`bridge.py:1001`) → `{success: False, data: "Cannot connect to Rhino on 127.0.0.1:59306. Available instances on ports: …"}`
- `except Exception as e` → `{success: False, data: str(e)}` — the opaque catch-all.

No `code`, no PID confirmation, no distinction between *gone* / *unreachable* / *timed-out* / *transport*, no `next_action`, no crash evidence. A local coordinator cannot recover from a free-text "Cannot connect…".

**P2 makes the call path's failures structured, diagnosed, and agent-consumable** — the "report liveness/failure truthfully" rung of the roadmap, one layer up from P1's read-only view. It is **diagnosis, not recovery**: no spawn, no relaunch, no ownership.

---

## 2. Scope

**In scope**
- A structured diagnosis envelope returned from `call_rhino` on **transport failure** (`httpx.TransportError` family).
- The **four-code taxonomy** (§4) with a `retryable` flag (§5).
- **Captured target identity** (port + PID + session + endpoint + method) bound *before* the HTTP request (§3).
- **Locate-only crash-artifact metadata** with a confidence tag (§6) — no parsing.
- Enriching `get_session_capabilities`'s existing dead/unreachable branches via the **shared envelope builder** (§7) — additive fields (`crash_artifact`, `retryable`).

**Out of scope** (explicit)
- Relaunch / spawn / auto-recover (P4/P5).
- Crash-artifact **parsing** (minidump/WER internals, managed-exception frames) — a later focused forensics slice.
- Any new reaping policy, including the deferred persistently-unreachable debounce (stays deferred).
- RookNative (C++) changes; any session selector in the general routing path.
- **Reclassifying HTTP-response-received failures.** If a response arrives (any HTTP status, JSON body or not), that is a route/tool/plugin outcome and passes through existing behavior — it is **never** turned into `rook_native_transport_error`. P2 diagnoses *connection/request* failure around the bridge, not *semantic* route failure.

---

## 3. The captured target (load-bearing)

Before issuing the request, `call_rhino` binds a structured target and uses it in every `except`:

```json
{
  "host": "127.0.0.1",
  "port": 59306,
  "processId": 12345,
  "session": "rhino-12345",
  "endpoint": "/objects",
  "method": "GET"
}
```

- `processId` / `session` may be `null` when the target was resolved by **port only** (no explicit PID/session and `select_rhino_instance` returned `None`). Diagnosis degrades gracefully **but never *guesses* death**: when `processId` is null, P2 resolves the PID by looking up `target.port` in a fresh `discover_instances()`. If a record owns that port, its PID is probed normally. If **no** record does, P2 cannot confirm that a specific process died — it returns `rook_native_transport_error` (incomplete diagnosis; `retryable:true`) pointing the caller at `rhino_sessions`, rather than fabricating a `rhino_session_dead`. (Naively handing a PID-less target to `classify_session_liveness` would compute `pidAlive=False` and *falsely* report `dead` — this resolution step exists to prevent that.)
- **Rationale:** at the `except`, `selected_instance` (which carries the PID) can be `None`, while `host`/port are reliable. Capturing the target up front makes diagnosis reliable instead of "guess from discovery-by-port after the fact" (fragile exactly when a dead PID's record is gone or a port was reused). It also doubles as the instance dict fed to `classify_session_liveness`, and enriches the envelope (the agent sees the attempted `endpoint`/`method`).

---

## 4. Error taxonomy & mapping

Diagnosis keys on the **exception category** first, then the **liveness probe**:

| `httpx` exception | probe | → `code` | `retryable` |
|---|---|---|---|
| `ReadTimeout` / `WriteTimeout` / `PoolTimeout` | — | `rook_native_request_timeout` | `true` |
| `ConnectError` / `ConnectTimeout` / `ReadError` / `WriteError` / `CloseError` | `classify_session_liveness` → **dead** | `rhino_session_dead` (+ `crash_artifact`) | `false` |
| same connectivity group | → **unreachable** (PID alive, port down) | `rook_native_listener_unreachable` | `true` |
| same connectivity group | → **live** (listener returned; race/transient) | `rook_native_transport_error` | `true` |
| any other `httpx.TransportError` / `RequestError` (e.g. `ProtocolError`) | — | `rook_native_transport_error` | `true` |
| **response received** (any HTTP status) | — | *(not P2 — pass through existing behavior)* | — |

Notes:
- **Timeout wording is deliberately soft.** `ReadTimeout` usually means *connected, no response*, but `PoolTimeout` is **client-side pool exhaustion** and `WriteTimeout` may be a request-body/socket stall. So the `next_action` says *"the request did not complete before the timeout — Rhino may be busy (a long command or a modal dialog) or a client-side stall; retry shortly,"* not "Rhino is showing a modal dialog."
- **`ConnectTimeout`** sits with the connectivity group (the connect phase did not complete) and is resolved by the same `classify_session_liveness` probe.
- `ReadError`/`WriteError` (connection dropped mid-request) are the *crashed-mid-call* shape — captured as `rhino_session_dead` + `crash_artifact` when the PID probe confirms death. **No separate `rhino_crashed` code** — "dead with a fresh artifact" carries that meaning without overclaiming confidence P2 doesn't have.
- **`rhino_session_dead` requires a *known* PID confirmed not-alive.** A port-only target whose owning record cannot be found in a fresh `discover_instances()` yields `rook_native_transport_error` (incomplete diagnosis), **never** a guessed `rhino_session_dead` (§3).

---

## 5. The envelope

```json
{
  "success": false,
  "data": {
    "code": "rhino_session_dead",
    "session": "rhino-12345",
    "processId": 12345,
    "port": 59306,
    "endpoint": "/objects",
    "method": "GET",
    "liveness": { "state": "dead", "pidAlive": false, "portListening": false },
    "retryable": false,
    "crash_artifact": {
      "available": true,
      "kind": "RhinoDotNetCrash.txt",
      "path": "C:/Users/aryan/Desktop/RhinoDotNetCrash.txt",
      "modifiedUtc": "2026-06-03T15:22:10Z",
      "ageSeconds": 18,
      "sizeBytes": 42137,
      "match": "fresh_near_failure",
      "pidMatched": false
    },
    "next_action": "The Rhino process is gone. Inspect crash_artifact if present, then call rhino_sessions; do not retry this session."
  }
}
```

- `crash_artifact` is present **only** when `liveness.state == "dead"`; otherwise omitted (or `{"available": false}`).
- `retryable` defaults: `rhino_session_dead` → `false`; `rook_native_listener_unreachable` / `rook_native_request_timeout` / `rook_native_transport_error` → `true`. It is the single field an agent reads to decide "retry this same session vs. don't."

---

## 6. crash_artifact — locate-only, confidence-tagged

```
find_recent_rhino_crash_artifact(process_id: int | None = None,
                                 since_utc: datetime | None = None) -> dict | None
```

- **Windows search order** (freshness-gated; default window ~5 min, or `since_utc` when provided):
  1. `RhinoDotNetCrash.txt` on the desktop(s) — `SpecialFolder.Desktop` **and** `%USERPROFILE%\Desktop` (OneDrive redirection).
  2. `%LOCALAPPDATA%\McNeel\Rhinoceros\*\{Crash Reports,CrashDumps,Crashes}\*.dmp`.
  3. `%LOCALAPPDATA%\CrashDumps\Rhino*.dmp` (WER LocalDumps).
- **Returns metadata only** — never opens or parses the artifact:
  `{ available, kind, path, modifiedUtc, ageSeconds, sizeBytes, match, pidMatched }`.
  - **WER dumps** name files `Rhino.exe.<pid>.dmp` → PID recoverable → `pidMatched: true`, `match: "pid_exact"`.
  - **`RhinoDotNetCrash.txt`** has no PID and is overwritten per crash → `pidMatched: false`, `match: "fresh_near_failure"`.
- Non-Windows, missing directories, or nothing within the window → returns `None` (envelope omits `crash_artifact` or sets `available:false`).
- Attached only on confirmed **dead** (§5). The confidence tag is load-bearing: P2 must not imply "this is *the* crash that just happened" when the match is freshness-correlated rather than PID-certain.

---

## 7. Helpers (two, deliberately split)

```
build_session_liveness_error(target, liveness, reason) -> dict     # the shared envelope BUILDER
diagnose_bridge_failure(target, exc) -> dict                       # call_rhino's exception entry
```

- **`build_session_liveness_error`** is pure (probes already done): assembles `code` / `session` / `processId` / `port` / `endpoint` / `method` / `liveness` / `retryable` / `next_action`, and attaches `crash_artifact` when `liveness.state == "dead"`. It owns the code→retryable→next_action mapping. (`reason` is a short caller-context tag — e.g. `"tool_call"` vs `"capability_query"` — that tunes only the `next_action` wording, not the `code`.)
- **`diagnose_bridge_failure`** classifies `exc` (§4): for the timeout and other-transport branches it builds the envelope directly; for the connectivity branch it runs `classify_session_liveness(target)` and delegates to `build_session_liveness_error`.
- **`get_session_capabilities` reuses `build_session_liveness_error`** for its dead/unreachable branches — it already holds the `liveness`, so it calls the builder directly and **does not fabricate an `httpx` exception**. This is the symmetry win (its dead branch gains `crash_artifact` + `retryable`), and it is **additive** to P1's contract (no field removed/renamed).
- `call_rhino` captures the target (§3), then its `except` blocks call `diagnose_bridge_failure(target, exc)`. The current free-text `ConnectError`/`Exception` returns are replaced; **HTTP-response-received paths are untouched** (§2 boundary).

---

## 8. Reaping

**Unchanged from P1.** Dead-PID discovery records are reaped by `discover_instances()` → `_cleanup_stale_discovery_files()`; unreachable/timeout records are retained, never reaped. P2 introduces **no** new reaping and does **not** add the deferred persistently-unreachable debounce. Diagnosis is read-through over the existing reap.

---

## 9. Testing

- **Unit — `diagnose_bridge_failure`:** one test per code path, feeding a fake target + a real `httpx` exception instance + monkeypatched `_is_pid_alive`/`_is_port_listening`. Assert `code`, `retryable`, and that `crash_artifact` appears only on `dead`.
- **Unit — `build_session_liveness_error`:** dead/unreachable/live shapes; crash_artifact attach-on-dead; field stability.
- **Unit — `find_recent_rhino_crash_artifact`:** a `tmp_path` seeded with synthetic artifacts (`RhinoDotNetCrash.txt`, a `Rhino.exe.<pid>.dmp`) → assert `kind`, `pidMatched`/`match`, freshness gating (an old file is ignored), and `None` when nothing qualifies.
- **Integration — `call_rhino`:** monkeypatch the `httpx` client to raise each exception type → assert the structured envelope (not the old strings). Confirm a **response-received** path (e.g. HTTP 500 with JSON body) is *not* reclassified as a bridge error.
- **Integration — real `call_tool`:** a failing call returns the structured envelope end-to-end.
- **`get_session_capabilities` enrichment:** dead branch now carries `crash_artifact` + `retryable` via the shared builder; unreachable unchanged in meaning.
- **Live smoke (held for Rhino):** kill a Rhino mid-call → `rhino_session_dead` + a `crash_artifact` pointer; put Rhino in a modal dialog / long command → `rook_native_request_timeout`, `retryable:true`.

---

## 10. Decision log

- **P2 = structured bridge-failure diagnosis + locate-only crash-artifact metadata.** Diagnosis, not recovery (no spawn/relaunch/allocation).
- **Four codes, no `rhino_crashed`:** `rhino_session_dead` / `rook_native_listener_unreachable` / `rook_native_request_timeout` / `rook_native_transport_error`. Dead + fresh `crash_artifact` conveys "crashed" without overclaiming.
- **Capture the target before the call** (host/port/processId/session/endpoint/method) — the load-bearing fix so PID is reliably available at diagnosis and the envelope is stable for agents.
- **Crash artifacts are located, not parsed**, and carry a **confidence tag** (`match` / `pidMatched`). Parsing is a later slice.
- **Softer timeout semantics** — `PoolTimeout`/`WriteTimeout` aren't necessarily Rhino behavior; describe as "request did not complete before timeout."
- **HTTP-response-received stays out** of transport diagnosis — semantic route/tool failure is not a bridge failure.
- **`retryable` on every bridge error** — the one field agents read to decide whether to retry the same session.
- **Two split helpers** — `diagnose_bridge_failure` (exception path) and `build_session_liveness_error` (shared builder, also used by `get_session_capabilities`); no fabricated exceptions.
- **Reaping unchanged from P1**; persistently-unreachable debounce stays deferred.
