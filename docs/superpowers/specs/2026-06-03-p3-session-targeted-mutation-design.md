# P3 — Explicit Session-Targeted Mutation (the canonical `session` selector)

- **Date:** 2026-06-03
- **Status:** Design approved (Rook ⇄ Codex ⇄ user, with refinements folded in). Ready for the implementation plan.
- **Author:** Claude (synthesis; Codex refinements folded in)
- **Area:** `mcp_server/src/rook/targeting.py` (`resolve_tool_route`, `route_error_result`, the tool-policy sets) + `mcp_server/src/rook/server.py` (`call_tool` wrapper). Reuses `bridge._process_id_from_session_id` (P1). **No `bridge.call_rhino` transport changes; no RookNative/C++ changes.**
- **Relationship:** Implements **P3** of the north-star P1–P7 roadmap (`docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`). Builds on P1's session vocabulary (`session_id_for_instance` / `_process_id_from_session_id`, PR #209 `05f7909`) and P2's truthful call path (structured bridge-failure envelopes, PR #210 `32420d1`). Discipline: **observe, don't own** — no spawn, no allocation, no registry. P3 routes; it does not launch or reap.

---

## 1. Goal & the gap

P1 gave the coordinator **perception** (`rhino_sessions` / `rhino_session_capabilities` — name and read live sessions). P2 gave it **truth on failure** (a dead/unreachable/timed-out session yields a structured, agent-consumable envelope at call time). Both are observational: neither lets a caller **explicitly direct a mutation to a named session**.

Today the only external target selectors on the tool-call path are `port` (explicit), the process-global `_ACTIVE_TARGET` (a single-client default), and `auto` (single-instance, or read-warns/mutate-refuses on ambiguity). A cloud coordinator fanning work across files A/B/C cannot say *"apply this to session B"* — it can only pass a raw `port` (a substrate coordinate it should not have to reason in) or mutate the global active target (unsafe under concurrent multi-file work).

**P3 makes `session` the canonical explicit target selector for the existing routing decision.** It is the "route safely" rung of the roadmap (`name → observe → truth → route → lifecycle → recompose`), one layer up from P2. The layer split is strict:

> **P3 routing answers *who should receive this call?* P2 diagnosis answers *what happened when we tried?*** P3 resolves *identity*; P2 owns *liveness*.

---

## 2. Scope

**In scope**
- A new per-call `session: "rhino-<pid>"` selector, read in `call_tool` and threaded into `resolve_tool_route`.
- Admission = **every `policy_for_tool(name).requires_rhino` tool** (read ∪ mutate ∪ unknown) — *not* a P3 allowlist (§4).
- A new **session rung** in `resolve_tool_route`, above the explicit-port rung, resolving session → PID → native-preferred `InstanceRef` (§5, §6).
- The **five guards** (§7): parse, not-found, panel-lock fail-closed, selector-conflict, active-stays-default.
- **Four new error codes** (§8): `invalid_session_id`, `rhino_session_not_found`, `selector_conflict`, `session_not_targetable`.
- A new `ToolRoute.selection` literal `"session"` for observability (§9).
- Rejecting `session` on **non-routed** tools (`session_not_targetable`), except an explicit own-argument set (§4.3).

**Out of scope** (explicit)
- Any `bridge.call_rhino` / transport change. P3 reuses the unchanged `rhino_request_context` → `select_rhino_instance` path; P2 already owns call-time failure.
- **Liveness probing inside routing.** Resolution is identity-only; a dead session surfaces through P2 at call time (§5.3). Routing performs **no** pid/port probe on the success path.
- Document / document-serial selection (pid-only; in-session document disambiguation is P6). The topology's `(session, document?, endpoint)` tuple is reduced to `(session, endpoint)` for P3.
- Endpoint-aware session→port refinement for multi-plugin PIDs (a `session` resolves to the **native-preferred** instance, exactly as `_ACTIVE_TARGET` does today; rc_* under a session inherits today's behavior — noted §10).
- Adding `session` to `bind_active_instance` / the active binding (YAGNI — `process_id` already works; `session` is `rhino-<pid>`).
- Spawn / kill / registry / reaping (P4/P5). Reaping is unchanged from P1.
- Direct internal `call_rhino(port=…)` callers (the agent/HTTP paths). P3's surface is `call_tool` only.

---

## 3. The constraint (one line)

> Session-targeted routing is **explicit, additive, and identity-only**: it adds a canonical `session` selector to the existing routing decision; it resolves *identity* (never liveness); and it removes/deprecates nothing — `port`, `_ACTIVE_TARGET`, and `auto` all keep working unchanged beneath it.

---

## 4. Selector & surface

### 4.1 The selector
A new per-call argument `session`, a string of the form `rhino-<pid>` (the P1 external handle from `rhino_sessions`). Read in `call_tool` near where `explicit_port = arguments.get("port")` is read today (`server.py:19292`) — but with a **presence flag**, because `dict.get()` collapses *absent* and *present-but-null* (`{"session": null}`) into the same `None`, and those two must diverge (below):

```python
has_explicit_session = "session" in arguments
explicit_session = arguments.get("session")  # may be None when present-but-null
```

**Present-but-null is `invalid_session_id`, not "no session."** A `session` selector is only ever passed deliberately — it is a routing convention, not an auto-filled per-tool schema field — so `{"session": null}` is a real coordinator bug, not a serialization artifact, and surfacing it teaches the contract. The presence flag is threaded into `resolve_tool_route` so the session rung gates on **presence**, never on `explicit_session is not None`. (This is a deliberate asymmetry with the legacy `port` selector, whose `None`-is-absent behavior is left unchanged; P3 sets the stricter contract for its *new* selector from day one.)

### 4.2 Admission = `requires_rhino`
`session` is honored on **every tool for which `policy_for_tool(name).requires_rhino is True`** — i.e. `_RHINO_READ_TOOLS ∪ _RHINO_MUTATE_TOOLS ∪ {unknown→mutate}`. This is the existing routing contract, not a new policy surface. Reads are included deliberately: a coordinator inspecting file B's objects (`rhino_objects`) before deciding where to mutate needs to target session B for a read, and reads-by-session ride the identical funnel.

> **Why not a narrow mutation allowlist?** Routing is already centralized; a per-tool P3 allowlist would be a *second* policy surface that can drift from the real routing policy. The strict thing is **one funnel with strong invariants**, not a parallel gate. (Codex, confirmed.)

### 4.3 Non-routed tools reject `session`
On the non-routed path (`not policy.requires_rhino`), a `session` argument is a contract error (the agent is targeting a meta/Rhino-independent tool that does not execute against a Rhino session). Reject it, **except** an explicit set of tools that own a non-routing `session` argument:

```python
# targeting.py — an explicit exception list, NOT a second routing policy.
_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {"rhino_session_capabilities"}
```

In `call_tool`, in the existing non-routed branch:

```python
if not policy.requires_rhino:
    if "session" in arguments and name not in _NON_ROUTED_SESSION_ARGUMENT_TOOLS:
        return _format_tool_result(_session_not_targetable_result(name))
    raw_result = await _call_tool_dispatch(name, arguments)
    return _format_tool_result(raw_result)
```

Rejecting (not silently ignoring) teaches the correct contract and surfaces planning/prompt bugs. The schema-driven alternative was rejected: tool schemas are built inside `server.list_tools()`, not a cheap central table, so introspecting the whole catalog on every non-routed call is wasteful. The one-entry set is honest and grows only by intentional addition.

### 4.4 `session` is stripped before dispatch (routed path only)
`_call_tool_dispatch` pops `port` (`server.py:12721`) but `rhino_session_capabilities` *reads* `arguments.get("session")` (`:12731`) on the **non-routed** path. So `session` must **not** be popped globally. Strip it only in the `requires_rhino` branch of `call_tool`, after a successful route, so it never leaks into a tool's request body:

```python
dispatch_arguments = dict(arguments)
doc_applied = targeting.apply_locked_document_context(dispatch_arguments)
# ... (existing) ...
dispatch_arguments = doc_applied
if explicit_port is not None:
    dispatch_arguments["port"] = route.target.port
dispatch_arguments.pop("session", None)   # NEW: targeting selector, not tool input
```

No routed tool declares its own `session` argument (confirmed: only `rhino_session_capabilities`, which is meta/non-routed), so stripping on the routed path is always safe.

---

## 5. The resolver (identity only)

### 5.1 Resolution path
```
session "rhino-7101"
   │  _process_id_from_session_id   (reused from bridge — the single pid↔session point, topology §10)
   ▼
pid 7101
   │  _native_preferred_instance(7101, discover_instances())   (existing targeting helper)
   ▼
instance dict (native-preferred for that pid)
   │  instance_ref_from_instance
   ▼
InstanceRef(port, process_id=7101)
   │  rhino_request_context(port, process_id)   (UNCHANGED)
   ▼
dispatch → call_rhino(port=None) → reads contextvars → select_rhino_instance
           (already cross-checks process_id, bridge.py:403-409)
```

`targeting.py` imports `_process_id_from_session_id` from `bridge` (it already imports `call_rhino, discover_instances, discovery_diagnostics` at `targeting.py:9`; `bridge` imports `targeting` only lazily inside a function, so no import cycle).

### 5.2 Lazy, not blind
"Lazy" means routing resolves identity from the **discovery projection** — which already reaps dead-PID records (P1/P2 `_cleanup_stale_discovery_files`). It does **not** mean unchecked: a well-formed `session` whose PID has **no discovered native record** fails *before dispatch* with `rhino_session_not_found`. If a record exists, routing does **not** pre-probe pid/port — it dispatches and lets P2 classify any failure.

### 5.3 P2 owns liveness at the edge
A session can pass any eager probe and die before the HTTP request anyway, so an eager probe removes no race and creates two liveness authorities. After a session resolves and dispatches, P2 classifies a call-time failure exactly as today:

| call-time reality | P2 code |
|---|---|
| PID gone during dispatch | `rhino_session_dead` |
| PID alive, listener down | `rook_native_listener_unreachable` |
| timeout | `rook_native_request_timeout` |
| other transport | `rook_native_transport_error` |

---

## 6. Precedence ladder (`resolve_tool_route`)

New signature: `resolve_tool_route(name, *, explicit_port=None, explicit_session=None)`. The ladder, with P3 changes marked `[NEW]`:

```
1.  requires_rhino == False ........................ ToolRoute(success, selection="none")     (unchanged)
2.  _PANEL_TARGET_CONFIG_ERROR ..................... "panel_target_config_error"              (unchanged)
3.  if has_explicit_session (presence, NOT value):
        explicit_session is null OR not "rhino-<positive int>"  → "invalid_session_id"        [NEW]
        else parse → pid_s
4.  validate explicit_port format
        invalid ..................................... "invalid_requested_port"                 (unchanged)

5.  PANEL LOCK branch (if _PANEL_TARGET_LOCK):                                                 (unchanged shell)
        locked target stale ........................ "panel_target_stale"                     (unchanged)
        explicit_session and pid_s != lock.process_id  → "panel_target_locked"               [NEW, fail-closed]
        explicit_port out-of-lock (existing)  → "panel_target_locked"                          (unchanged)
        → success, selection="panel_locked" (lock dominates; session/port only confirm it)   (label unchanged)

6.  EXPLICIT SESSION rung (no lock), if explicit_session: ................................     [NEW rung]
        inst_s = _native_preferred_instance(pid_s, instances)
        inst_s is None ............................. "rhino_session_not_found"
        if explicit_port is not None:   # both selectors supplied — consistency check
            owner = instance owning explicit_port
            owner is None ........................... "requested_port_not_discovered"   (port error wins)
            owner.processId != pid_s ................ "selector_conflict"               (both resolve & disagree)
            # else same PID → consistent; port ignored, SESSION wins
        → success, target=ref(inst_s), instance=inst_s, selection="session"

7.  EXPLICIT PORT rung (no lock, no session) ....... selection="explicit"                     (unchanged)
8.  ACTIVE target .................................. selection="active"                       (unchanged)
9.  AUTO / single / multiple ....................... "auto" / "multiple_rhino_instances"      (unchanged)
```

Session sits **above** port (rung 6 before 7), so when only `session` is given it is canonical. Because rung 6 returns, the multi-instance ambiguity at rung 9 is **bypassed** — naming a session *is* the disambiguation, exactly as explicit_port is today. Session handling appears in two places (the lock branch and the non-lock rung), mirroring how explicit_port is already handled in both.

**Guard ordering is fail-closed-first.** Under a lock, the lock's guards dominate: a session in-lock + a port out-of-lock returns `panel_target_locked` (not `selector_conflict`), and a PID-level conflict cannot even arise in-lock because both selectors must equal `lock.process_id` or fail closed. Outside a lock, a named-but-missing session returns `rhino_session_not_found` **before** any port-consistency check (rung 6a before 6b) — a canonical session that does not resolve is an error, never silently rescued by a supplied port. Within rung 6b, the undiscovered-port check precedes the PID-comparison (a conflict requires *both* selectors to resolve).

---

## 7. The five guards

1. **Parse / presence.** When `session` is **present** (`"session" in arguments`), it must be `rhino-<positive int>` → else `invalid_session_id` (mirrors `invalid_requested_port`). **Present-but-null** (`{"session": null}`) is `invalid_session_id`, distinct from **absent** (no session rung at all). Validation reuses `bridge._process_id_from_session_id`, which already returns `None` for `None` / `"rhino-"` / `"rhino-abc"`. Done early (rung 3) so a malformed selector never reaches resolution.
2. **Not found.** Well-formed session, no discovered native record for the PID → `rhino_session_not_found`, *before dispatch* (rung 6a).
3. **Panel-lock fail-closed.** Under `_PANEL_TARGET_LOCK`, a session whose PID ≠ `lock.process_id` → `panel_target_locked` (rung 5). Identical in spirit to the explicit-port guard at `targeting.py:907-917`: *a panel-locked MCP process cannot be redirected to another session by a coordinator plan* (topology §6.3, Invariant 5).
4. **Selector conflict (PID-level).** When both `session` and `port` are supplied, they must resolve to the **same PID**. The full rule:

   | inputs | outcome |
   |---|---|
   | `session=rhino-7101` + port owned by **PID 7101** | **allowed — session wins**, port is a consistency check only |
   | `session=rhino-7101` + port owned by **PID 9999** (both resolve) | `selector_conflict` |
   | `session=rhino-7101` + **undiscovered** port | `requested_port_not_discovered` (port error; conflict requires both selectors to resolve) |
   | `session=rhino-7101` + malformed port | `invalid_requested_port` (rung 4, before resolution) |

   A `session` names a Rhino **process** (`rhino-<pid>`), not a transport port; the same PID on a different port is a legitimate same-process companion/native/adapter (topology §6.1, "identity is the pid; the port is endpoint-resolved"). So agreement is PID-level, and a consistent port never overrides the session.
5. **Active stays default-only.** `_ACTIVE_TARGET` is consulted only when **no** explicit selector (`session` or `port`) is supplied — unchanged behavior, now explicitly the bottom of the explicit-selector stack (topology §6.4).

---

## 8. Error taxonomy & envelopes

Four new codes. Routing codes are emitted by `resolve_tool_route` and rendered by `route_error_result`, following the existing `{success:false, data:{error, message, …selector fields, instances}}` shape. `session_not_targetable` is returned directly from `call_tool` (pre-routing, non-routed path) using the same `_error_result` shape.

| code | where | envelope `data` (beyond `error`/`message`/`instances`) | `next`-style message |
|---|---|---|---|
| `invalid_session_id` | `route_error_result` | `invalidSession: <raw value>` | "Session id must look like 'rhino-<pid>' (from rhino_sessions)." |
| `rhino_session_not_found` | `route_error_result` | `session`, `discoveryFolder`, `discoveryFolders` | "No discovered RookNative session owns that id. Call rhino_sessions for live sessions." |
| `selector_conflict` | `route_error_result` | `session`, `requestedPort`, `sessionProcessId`, `portProcessId` | "session and port name different Rhino processes. Pass one, or a port on the same process." |
| `session_not_targetable` | `call_tool` (non-routed) | `name` (the tool) | "This tool does not execute against a Rhino session; remove 'session'." |

`rhino_session_not_found` reuses the diagnostic fields of `requested_port_not_discovered` (discovery-folder pointers) for symmetry. `ToolRoute` gains an `invalid_session: object | None` field (parallel to the existing `invalid_port`) carrying the raw offending value, which `route_error_result` renders as `invalidSession`. `resolve_tool_route` gains a `has_explicit_session: bool` parameter so the session rung gates on presence (§4.1). No code overlaps P2's bridge-failure codes — these are **routing** errors (pre-dispatch), distinct from P2's **transport** errors (at dispatch).

---

## 9. Route metadata / selection label

- New `ToolRoute.selection` literal: `"session"`. Add to the `Literal[...]` on `ToolRoute.selection` (`targeting.py:33`).
- When a session wins (including the same-PID-port consistency case), `selection="session"` — the canonical selector that won is what route metadata reports (`attach_route_metadata`).
- Under a panel lock, `selection="panel_locked"` is retained (the lock is the dominant fact; a session merely confirms it passed the lock). The lock is a constraint, not a selector (topology §6.3).

---

## 10. Scope boundaries (what P3 deliberately does not do)

- **No document selector.** `session` is PID-only. `documentSerialNumber` stays a panel-lock-only context field; general document/worksession disambiguation is P6.
- **No endpoint-aware session→port.** A `session` resolves to the **native-preferred** `InstanceRef` (the pid's native port), identical to `_ACTIVE_TARGET` today. An rc_* call under a session inherits today's behavior; perfecting `(session, endpoint)→port` for multi-plugin PIDs is a future refinement, not a P3 regression.
- **No `bind_active_instance` change.** The active binding still takes `port`/`process_id`/`match`. Adding `session` there is sugar (`session` is `rhino-<pid>`); deferred.
- **No transport, spawn, registry, or reaping changes.** P2 owns call-time truth; P4/P5 own lifecycle. Reaping is unchanged from P1.

---

## 11. Testing

**Unit** (extend `tests/test_multi_instance_targeting.py` and/or a new `tests/test_session_routing.py`), monkeypatching `discover_instances` with synthetic instance dicts:
- `session` selects the target → `selection="session"`, correct `InstanceRef`, with **one** and with **multiple** discovered instances (proves session bypasses the mutate-ambiguity refusal).
- `invalid_session_id` for `"bogus"`, `"rhino-"`, `"rhino-abc"`, and **present-but-null** (`{"session": None}`); **absent** (no `session` key) skips the session rung entirely (no session error). The routed path gates on `has_explicit_session = "session" in arguments`, so present-but-null and absent provably diverge.
- `rhino_session_not_found` for a well-formed id with no matching native record.
- **Conflict matrix** (§7.4): same-PID port → routes, `selection="session"`; different-PID port → `selector_conflict`; undiscovered port → `requested_port_not_discovered`; malformed port → `invalid_requested_port`.
- **Panel lock**: in-lock session → routes (`selection="panel_locked"`); out-of-lock session → `panel_target_locked` (fail closed); in-lock session + out-of-lock port → conflict/locked as applicable.
- **Non-routed rejection**: a `requires_rhino=False` tool + `session` → `session_not_targetable`; `rhino_session_capabilities` + `session` → **not** rejected (own-argument exemption).
- **Dispatch strip**: a routed call carrying `session` → `session` absent from the dict handed to `_call_tool_dispatch`/`call_rhino` body.
- **Regression**: existing `resolve_tool_route` contracts (explicit_port precedence over active, auto/single, multiple-mutate refusal, panel stale, active stale) stay green.

**Live smoke** (the established owned-Rhino harness pattern — `scripts/run_rhino_runtime_harness.py --smoke p3-session-mutation` + a new `mcp_server/tools/p3_session_mutation_live_harness.py`; launches an OWNED throwaway Rhino, sets `ROOK_RHINO_PROCESS_ID`/`ROOK_RHINO_PORT`, cleans up gracefully, never touches the user's session):
- A real session-targeted **mutation** (e.g. create an object) routed by `session="rhino-<owned pid>"` lands in that session and returns success.
- A bogus `session` id → `rhino_session_not_found` (pre-dispatch, no transport attempt).
- A second **synthetic** discovery record (different pid) present → a bare mutate would refuse with `multiple_rhino_instances`, but the same mutate with `session=<owned>` routes cleanly (proves disambiguation). *(Honesty boundary, per the P2 precedent: the second instance is a synthetic discovery record over the owned alive pid where applicable, or a throwaway pid; documented in the harness docstring.)*
- `session` + same-PID port → routes (`selection="session"`); `session` + a different (synthetic) pid's port → `selector_conflict`.

---

## 12. Decision log

- **P3 = explicit session-targeted routing.** `session` is the canonical external selector; `InstanceRef(port,pid)` stays the internal address; `_ACTIVE_TARGET` stays a single-client default. Identity only — **P2 owns liveness**.
- **Admission = `requires_rhino`, not a P3 allowlist.** One funnel with strong invariants beats a second, drift-prone policy surface. Reads included (reads-by-session are useful and ride the same path).
- **Surface = `call_tool` only.** Direct internal `call_rhino` callers are out of scope; `session` is stripped from the routed dispatch payload.
- **Non-routed `session` → `session_not_targetable`,** except `_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {"rhino_session_capabilities"}` (an explicit, intentionally-grown exception, not schema introspection).
- **Lazy resolution.** Resolve from the (already-reaped) discovery projection; well-formed-but-absent → `rhino_session_not_found` pre-dispatch; never pre-probe pid/port on the success path.
- **Session above port; conflict is PID-level.** Same-PID port → session wins (consistency check); different-PID port (both resolve) → `selector_conflict`; undiscovered port → `requested_port_not_discovered` (conflict requires both to resolve).
- **Panel lock fail-closed for session** exactly as for explicit port; `selection="panel_locked"` retained under a lock.
- **Four new codes**, all distinct from P2's transport codes (routing errors are pre-dispatch). New `selection="session"`.
- **Present-but-null `session` is `invalid_session_id`,** not "no session." Routing gates on a **presence flag** (`"session" in arguments`) threaded into `resolve_tool_route`, not on `.get()` — so `{"session": null}` cannot silently behave as absent. Deliberate asymmetry with the legacy `port` selector (whose `None`-is-absent behavior is unchanged).
- **No transport/spawn/registry/document changes.** Reaping unchanged from P1; lifecycle is P4/P5; documents are P6.
