# P5 — Persistent Owned-Session Registry (durable ownership + adopt-on-restart)

- **Date:** 2026-06-04
- **Status:** Design approved (brainstormed Rook ⇄ Codex ⇄ user; folds the reframe + 5 spec additions from Codex review). Ready for the implementation plan.
- **Author:** Claude (synthesis of the Rook ⇄ Codex deliberation)
- **Area:** `mcp_server/src/rook/{registry,workbench,bridge,server}.py`; reference: `C:\Users\aryan\source\repos\RhinoMCP\rhino\router\SlotStore.cs`
- **Relationship to other docs:**
  - Implements roadmap phase **P5** from `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md` (§7 "where SQLite lands"; §9.1 two-speed spec; §13 decision log). P5 is the inflection point: everything through P4 is in-process; P5 makes ownership **durable + cross-process**.
  - Builds directly on P4 (`2026-06-03-p4-owned-workbench-launch-design.md`) — the in-process `workbench._OWNED` owned-set becomes a derived cache backed by this registry.
  - Reuses P1 liveness (`bridge.classify_session_liveness`, independent pid/port probes) and P3 routing/panel-lock machinery unchanged.

---

## 1. Goal & the gap

P4 owns a disposable Workbench Rhino in an **in-process** dict (`workbench._OWNED: dict[int, OwnedWorkbench]`) holding the live `subprocess.Popen`. An MCP restart dissolves that dict — the launched Rhino keeps running, but the coordinator can no longer see, list, or close it. It is an un-closable orphan.

**P5 closes that gap:** a durable SQLite ledger of Rook-owned Workbench sessions that survives MCP restarts and is safe to share across multiple coordinator runtimes on one workstation. On restart, the coordinator **reconciles** the ledger against live discovery and **reclaims** the Workbenches it (or a dead predecessor) launched — making them closable again.

This is the "a coordinator reclaiming its fleet after a restart" capability named in the north-star.

## 2. Scope

**In:** session ownership durability; ownership/claim state; owner identity; lifecycle status (`launching`/`bound`); last observed pid/port/document snapshot; close eligibility; adopt-on-restart reclaim; cross-process safety against multiple coordinator runtimes.

**Out (deferred):** durable document graph / `documents` table (P6); Save/export lifecycle and merge contracts (P6/P7); work-unit lineage (P6/P7); durable respawn-surviving aliases (`workbench-a`) — `rhino-<pid>` stays the handle; creation-time PID-reuse hardening (seam left, not built); multi-machine transport (PX).

**Sessions-only** (north-star §9.1 two-speed spec; observe-before-theorizing): there is no document *lifecycle* to persist yet, so P5 reserves a schema seam for documents but builds no document subsystem.

## 3. The constraint (one line)

> **The registry is ownership truth, not liveness truth.** SQLite stores claims, owner identity, and last observations. Liveness is always a fresh P1/P2 probe — the ledger must never become a stale "this Rhino is alive" authority.

This is the load-bearing restraint. A registry that also recorded liveness would become a second authority on identity/health — and two authorities disagreeing about who owns a document is exactly the "rails-jumping" bug class P5 must stamp out.

## 4. The reframe — a shared workstation ledger (not a per-lineage list, not a discovery mirror)

The DB is the durable ownership ledger for **all Rook-owned Workbench sessions on this workstation**, shared across external coordinator runtimes:

```
Registry = durable ownership ledger for Rook-owned Workbench sessions on this workstation.
Rows may belong to: this runtime, a dead predecessor, or a live peer coordinator.
This runtime may CLOSE only rows whose owner identity matches current_owner after reconciliation.
rhino_workbench_list lists only rows owned by the current runtime (post-reconcile).
```

It is **not** a mirror of every discovered Rhino — the user's Attached master document and unrelated Rhino windows are *not* in this ledger (they live in the perception layer, `rhino_sessions`). It contains exactly the Rhinos some Rook coordinator *launched as a Workbench*.

## 5. Architecture (Approach 1: registry is truth, `_OWNED` is a derived cache)

```
SQLite registry (owned_sessions.db)        _OWNED cache (in-memory, per runtime)
  durable ownership truth                    pid -> Popen | PidProcessHandle
  claim state + lifecycle status             rebuildable from registry rows
  owner identity (pid/token/started/scope)   NEVER authoritative for ownership
  last pid/port/doc snapshot                 real Popen for this-session launches
  close eligibility (transaction-guarded)    PidProcessHandle for reclaimed sessions
```

`_OWNED` survives only to hold the one thing SQLite cannot store — the live OS process handle. It is rebuilt from the rows by reconciliation and is never consulted as the *authority* for whether this runtime may close a session (that authority is a transactional row read — §10).

## 6. Schema

```sql
CREATE TABLE owned_sessions (
  session_id   TEXT PRIMARY KEY,        -- 'rhino-<pid>' (the P1/P3 handle)
  rhino_pid    INTEGER NOT NULL,
  port         INTEGER,                 -- NULL while 'launching'
  status       TEXT NOT NULL,           -- 'launching' | 'bound' | 'closing'
  owner_pid    INTEGER NOT NULL,        -- the coordinator runtime that owns the claim
  owner_token  TEXT NOT NULL,           -- uuid minted once per runtime at startup
  owner_started_at INTEGER NOT NULL,    -- runtime start (epoch); PID-reuse seam, see §10
  owner_scope  TEXT NOT NULL,           -- 'external' | 'panel_locked' (provenance/audit)
  launched_at  INTEGER NOT NULL,
  last_document_path TEXT,              -- non-authoritative document snapshot
  last_document_serial_number INTEGER,  --   (reserved seam toward P6; never load-bearing)
  last_document_name TEXT,
  observed_at  INTEGER
);
CREATE INDEX idx_owned_sessions_rhino_pid ON owned_sessions(rhino_pid);
CREATE INDEX idx_owned_sessions_owner_pid ON owned_sessions(owner_pid);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);  -- 'registry_version'
```

**Location:** `resolve_registry_path()` (mirrors `bridge.resolve_discovery_folder`) → `%LOCALAPPDATA%\Rook\registry\owned_sessions.db`, falling back to `%TEMP%\rook\registry\owned_sessions.db` when `LOCALAPPDATA` is absent.

**No `adopted` column — deliberately.** Every P5 row is owned. SlotStore's `adopted` flag is the *Attached-master-document* distinction (never auto-close the user's doc) — that is P6/fan-in, not here. "Owned-by-me vs peer-owned" is **derived at read time** by comparing the row's owner identity to the current `RuntimeOwner`; it is not a stored flag.

## 7. Runtime identity (stable) vs. scope (live)

These are two different things and must not be conflated (Codex finding 3): the **lineage identity** is stable for the process and may be cached; the **permission scope** is a live safety gate and must be recomputed every call, never read from a cached value.

**Stable identity — `get_runtime_owner()`,** a process-global minted **once** at first use:

```
RuntimeOwner:                          # cached for the process lifetime
  pid         = os.getpid()
  token       = uuid4().hex            # changes every restart — lineage identity beyond PID
  started_at  = int(time.time())
```

**Live scope — `current_owner_scope()`,** computed fresh at **every** Workbench-tool entry (lives in `workbench.py`, the only place that imports `targeting`):

```
current_owner_scope() -> 'panel_locked' if targeting.get_panel_target_lock() is not None
                            or targeting.get_panel_target_config_error() is not None
                         else 'external'
```

Each tool call builds a per-call claim `(identity = get_runtime_owner(), scope = current_owner_scope())` and passes it into `registry.py` (which never imports `targeting`). The **live scope** is the reclaim/close permission gate; the scope written onto a row at claim time is **provenance only** (`owner_scope`), never the live permission source. The token is what lets a restarted coordinator tell "a row I own" from "a row a same-PID-but-different-process owns."

## 8. Row lifecycle

```
launch ──INSERT──▶ launching (rhino_pid known, port NULL, owner = me)
                      │ wait_for_ready binds PID-correlated discovery
                      ▼
                    bound (rhino_pid + port observed)   ◀── reclaim: rewrite owner identity; status stays 'bound'
                      │ close: claim-by-UPDATE
                      ▼
                    closing (terminate in flight; row PERSISTS across the off-thread kill)
                      │ process confirmed dead
   ──DELETE──▶ (gone)
```

**The invariant behind every transition: a row is deleted only when its process is confirmed dead.** A row must never disappear while its Rhino might still be alive — that recreates the exact orphan P5 exists to prevent (Codex findings 1 & 2).

- **Launch binds** → `UPDATE status='bound', port=<observed>`.
- **Launch fails to bind** → attempt reap; **`DELETE` the launching row only if the process is confirmed dead.** If reap fails (`force_kill_failed`), **retain** the `launching` row and keep its real handle in `_OWNED`, surface `cleanupStatus: force_kill_failed` (retryable) — a live process is never left without a durable claim. (Symmetric with P4's close `force_kill_failed`.)
- **Runtime crashes mid-launch / mid-close** → a `launching` or `closing` row remains; reconciliation reclaims or reaps it by truth (§9), so the live Workbench stays reclaimable.
- **Known residual (irreducible to pid-first identity):** a crash in the microsecond window *between* `Popen` returning and the `launching` `INSERT` leaves a live Rhino with no row (an un-closable orphan, visible only via perception). This is fundamental to a `rhino-<pid>` key — the claim cannot precede the pid. The `INSERT` is the very first statement after `Popen` to keep the window minimal; fully closing it requires name-first slots (durable aliases), deferred. Same risk class as the PID-reuse residual (§10).

## 9. `reconcile_owned_registry(current_owner)` — the one narrow contract

A single, explicit, testable function. Called at the entry of every Workbench tool, **after** the P4 panel guard (so it is structurally unreachable under panel lock — §12). Contract:

```
reconcile_owned_registry(current_owner):
  # Probe liveness OUTSIDE any transaction (probes are slow; holding the write
  # lock across them would serialize every coordinator). Snapshot rows, probe,
  # then apply each change under its own BEGIN IMMEDIATE with a precondition recheck.

  snapshot = SELECT * FROM owned_sessions
  for row in snapshot:
      # RookNative discovery is loopback-only (read_owned_record enforces LOOPBACK_HOSTS),
      # so the port probe always uses DEFAULT_HOST (127.0.0.1); no host column is stored.
      rhino_alive = _is_pid_alive(row.rhino_pid)
      port_up     = rhino_alive and _is_port_listening(DEFAULT_HOST, row.port)   # only if bound
      owner_alive = _is_pid_alive(row.owner_pid)

      # status == 'bound'
      # Two ORTHOGONAL axes. Reaping keys on the RHINO pid; reclaim keys on the OWNER pid.
      # port_up is a pure OBSERVATION — it gates neither (Codex finding 1).
      rhino dead                         -> DELETE                        (persist-intent, probe-truth)
      rhino alive:
          refresh observed_at; record port_up   # down = listener unreachable (plugin reload / the user's
                                                 # live doc); NEVER a reap or reclaim signal — a live pid is
                                                 # never deleted, and ownership is independent of listener health
          owner_pid dead                 -> RECLAIM (if current_owner.scope == 'external')  — REGARDLESS of port_up
          owner_pid alive                -> no ownership change (mine -> _OWNED rebuild below; a peer's -> untouched)

      # status == 'closing'  (a close was interrupted — by this or a predecessor runtime)
      rhino dead                         -> DELETE                  (the close completed, or the Rhino died)
      rhino alive, owner_pid dead        -> RECLAIM, reset status='bound'  (live Workbench again; re-closable)
      rhino alive, owner_pid alive       -> leave (a live owner is mid-close)

      # status == 'launching'
      rhino dead                         -> DELETE
      rhino alive, owner_pid dead        -> re-probe discovery ONCE:
                                              bound now  -> RECLAIM + promote status='bound' (reclaim a late bind)
                                              not bound  -> RECLAIM as owned 'launching' (a closable zombie this
                                                            runtime can finish via an explicit close)
      rhino alive, owner_pid alive       -> leave (an in-flight launch, mine or a peer's)

  rebuild/refresh _OWNED: for every row owned by current_owner with a LIVE rhino_pid (any status),
    ensure _OWNED[rhino_pid] has a handle — PRESERVE an existing real Popen if present
    (this-process launch, or a force_kill_failed retain); otherwise synthesize PidProcessHandle(rhino_pid)
```

**Reconcile never terminates a process.** It deletes rows whose Rhino is confirmed dead, reclaims dead-owner rows (restoring this runtime's authority so a later explicit `close` can finish the job), and leaves live-owner rows untouched. Actual termination only ever happens on the explicit `close` path or the inline launch-failure path — so a mere `rhino_workbench_list` can never kill anything.

**RECLAIM** = under `BEGIN IMMEDIATE`: re-read the row; verify it still shows the dead predecessor observed in the snapshot (compare-and-set on owner identity/status); if so, `UPDATE owner identity = current_owner` (+ status transition where noted); `COMMIT`; then ensure `_OWNED[rhino_pid]` holds a handle (real Popen preserved, else `PidProcessHandle`). If the recheck fails (a peer reclaimed first → owner now live), back off and treat as peer-owned. **Reclaim requires the live `current_owner_scope() == 'external'`** (§7, §10).

**Why per-row transactions are sufficient (not one giant transaction):** the authoritative act is the *write*, and every write re-reads and re-validates its precondition inside `BEGIN IMMEDIATE`. Two runtimes racing to reclaim the same dead-owner row: the first commits `owner→itself`; the second's in-transaction recheck now sees a live owner and aborts. No read/probe/write split can cross an ownership boundary, because the commit decision re-validates atomically against current row state.

## 10. Reclaim semantics + the panel-scope HARD INVARIANT

The reclaim contract (Option A, owner-liveness reclaim):

```
owned row + Rhino pid dead                       -> DELETE row
owned row + Rhino pid alive + owner_pid dead     -> current external runtime may RECLAIM
                                                    (rewrite owner identity; rebuild _OWNED via PidProcessHandle;
                                                     close remains allowed)
owned row + Rhino pid alive + owner_pid alive     -> do NOT reclaim; peer (or self) owns it; observe only
```

**HARD INVARIANT (panel scope):**

> P5 must never let an embedded / panel-scoped agent acquire, reclaim, or close a session outside its panel lock. **Only an `external` coordinator runtime may reclaim orphaned owned Workbench rows.**

- **`panel_locked` runtime:** launches/reclaims/closes **nothing** in this registry; routes only within its locked session/document boundary. (P4's panel guard already blocks all three `rhino_workbench_*` tools before dispatch, so reconcile/launch/close are unreachable — the invariant rides existing machinery; `reconcile_owned_registry` *also* checks `scope == 'external'` for defense in depth.)
- **`external` runtime:** may reclaim only when `owner_pid` is dead and the Rhino pid is alive.
- **Live peer owner:** never stolen.
- **Adopted / user Rhino:** never closed (not in this registry at all).

**Two distinct "scopes," kept separate (Codex finding 3):** the **live** current-runtime scope from `current_owner_scope()` — recomputed every Workbench-tool entry, never a cached value — is the permission gate (panel-locked ⇒ no reclaim/close). The row's stored `owner_scope` is provenance/audit and a future safety check — not the live permission source. (Rows from `rhino_workbench_launch` are normally `owner_scope='external'` because P4 blocks the launch tool under panel lock; storing it prevents future regressions.)

**Conservative owner-liveness:** "owner_pid alive" means "a process with that PID exists and we must not steal," *not* "we verified it is a Rook MCP." If a PID is reused by an unrelated process, the row stays peer-owned longer than ideal — safer than closing the wrong Rhino. The dead-Rhino path still reaps it once its Rhino dies. (`owner_started_at` is stored as the seam for a future creation-time discriminator that would close this hole; not built in P5.)

## 11. Close semantics (transaction-guarded by owner identity)

`rhino_workbench_close(session)` does **not** trust `_OWNED` alone for authority. It is **claim-by-update** — we must not hold a transaction across the ≤10s off-thread WM_CLOSE/taskkill, *and* (Codex finding 1) the durable row must persist through the kill so a crash mid-close cannot strand a live Workbench:

```
1. scope = current_owner_scope(); require scope == 'external'   # defense in depth (P4 guard already blocks pre-dispatch)
   reconcile_owned_registry(get_runtime_owner(), scope)          # rebuild cache, settle ownership
2. validate graceful is a real bool (P4: invalid_graceful_flag)
3. parse pid from session (P4: invalid_session_id)
4. Tx1  BEGIN IMMEDIATE:
     row = SELECT * FROM owned_sessions WHERE session_id = ?
     if row is None or (row.owner_pid, row.owner_token) != (get_runtime_owner().pid, .token):
         ROLLBACK -> return not_owned        # stale cache / concurrent reclaim cannot cross the boundary
     UPDATE status='closing' WHERE session_id = ?     # claim-by-UPDATE; the row PERSISTS across the kill
   COMMIT
5. terminate the handle off-thread (asyncio.to_thread):  # P4 _terminate: direct-force default / graceful opt-in
     handle = _OWNED.get(pid)  (or PidProcessHandle(pid) if cache missing)
6. Tx2  BEGIN IMMEDIATE:
     process confirmed dead -> DELETE row; drop _OWNED[pid]; return closed + cleanupStatus
     else (force_kill_failed) -> leave status='closing' (retain ownership), keep _OWNED[pid];
                                 return force_kill_failed (retryable)
   COMMIT
```

If this process **crashes between Tx1 and Tx2**, a `closing` row remains with a now-dead owner; a later external runtime reclaims it (§9: `closing` + Rhino alive + owner dead → reset `bound`, re-closable) — no orphan. During a normal close, the window between Tx1 (`closing`) and Tx2 is safe against peers: a concurrent reconcile sees `closing` + Rhino alive + owner **alive** (me) → leave.

## 12. Concurrency & durability

- **`BEGIN IMMEDIATE`** on every load-bearing write (launch INSERT, bind UPDATE, reclaim UPDATE, close UPDATE→DELETE) — the SlotStore lesson, adopted from day one. **A row is deleted only when its process is confirmed dead** (§8); transient/terminal intent is durable (`launching`/`closing`) so a crash never strands a live process.
- **WAL** + **`busy_timeout`** (5s) for multi-process reader/writer concurrency.
- **Per-row compare-and-set** in reconcile (§9) — the explicit reason single-pass transactions aren't needed.
- **Ephemeral wipe-on-version:** a `registry_version` constant in `meta`; on mismatch, `DROP TABLE owned_sessions` + rebuild. The registry is runtime state, never user data — wiping on upgrade is correct (SlotStore parity).
- **Blocking primitives off-thread:** all SQLite calls and the terminate path run via `asyncio.to_thread` (never block the MCP event loop) — the established cross-phase seam.

## 13. `PidProcessHandle` — the reclaim surrogate

A pid-backed stand-in for the `Popen` lost across a restart, implementing exactly the surface P4's close path touches (verified against `_terminate` / `force_owned_process_cleanup` / `request_external_graceful_close`):

| Member | Behavior |
|---|---|
| `.pid` | the Rhino pid |
| `.poll()` | `None` if `bridge._is_pid_alive(pid)` else an exit sentinel (e.g. `0`) |
| `.wait(timeout=None)` | poll-loop until dead or timeout; raise `subprocess.TimeoutExpired` on timeout |
| `.kill()` | terminate by pid (the path `force_owned_process_cleanup` already drives via `taskkill /F`; `.kill()` is its fallback) |
| `.returncode` | `None` until observed dead (satisfies the `ProcessLike` protocol) |

Reclaimed Workbenches therefore close as cleanly as freshly-launched ones. The `_handle`/Job-object path is smoke-harness-only and never reached by Workbench close, so the surrogate need not provide it.

## 14. Cross-phase seams

- **P1 reuse:** reaping reuses `bridge`'s independent pid/port probes (`_is_pid_alive`, `_is_port_listening`). **Reaping keys on the Rhino pid only:** dead pid → delete; live pid → never deleted. **Port-down never blocks reclaim or close** — ownership (owner-pid liveness) and listener health are independent, and `close` terminates **by pid** (`taskkill`/WM_CLOSE), not via the native port — so a reclaimed Workbench with a down listener is still closable (Codex finding 1).
- **P3/P4 panel guard:** unchanged. `server.py:19351` returns `panel_target_locked` / `config_error` for all three Workbench tools before dispatch; `reconcile_owned_registry` and `close` additionally self-gate on the live `current_owner_scope() == 'external'`.
- **P4 `_OWNED` refactor:** `launch_owned_workbench` / `list_owned_workbenches` / `close_owned_workbench` keep their public result shapes (`{success, data:{…}}`, `retryable` on failures) but route ownership through `registry.py`; the in-memory dict becomes the derived cache.
- **Result envelope:** all new codes carry `retryable`; close-on-not-owned stays `not_owned` (now registry-backed).

## 15. Components / files

- **New `mcp_server/src/rook/registry.py`** — SQLite store (schema/version, INSERT / bind-UPDATE / reclaim-UPDATE / close-UPDATE→DELETE under `BEGIN IMMEDIATE`) + `reconcile_owned_registry` + `resolve_registry_path` + `get_runtime_owner` + `RuntimeOwner` (stable identity). Pure storage/logic; does not import `targeting` (the live scope is passed in per call).
- **Modified `mcp_server/src/rook/workbench.py`** — `_OWNED` becomes derived; `PidProcessHandle`; owns `current_owner_scope()` (the only place that imports `targeting`); builds the per-call claim (`get_runtime_owner()` identity + live scope); launch/list/close call reconcile and route ownership through `registry.py`.
- **`mcp_server/src/rook/bridge.py`** — expose `_is_pid_alive` / `_is_port_listening` for registry reuse (already module-level).
- **`mcp_server/src/rook/server.py`** — no dispatch change (panel guard already fences the tools).
- **Tests:** new `mcp_server/tests/test_registry.py`; extend `mcp_server/tests/test_workbench.py`. New live smoke `mcp_server/tools/p5_registry_reclaim_live_harness.py` + a `p5-registry-reclaim` choice in `scripts/run_rhino_runtime_harness.py`.

## 16. Scope boundaries — what P5 does **not** do

- No `documents` table, no document graph, no Save/export lifecycle, no merge contracts, no work-unit lineage (P6/P7).
- No durable aliases — `rhino-<pid>` remains the handle.
- No creation-time PID-reuse discrimination (seam only).
- No mirroring of discovered/Attached Rhinos into the registry (perception stays `rhino_sessions`).
- No new MCP tool surface — reconciliation is internal to the existing three Workbench tools; reclaimed Workbenches reappear in `rhino_workbench_list`.
- No process termination inside `reconcile_owned_registry` — reconcile restores ownership and reaps only confirmed-dead rows; all killing happens on the explicit `close` path or the inline launch-failure path.

## 17. Testing

**Unit — `test_registry.py` + extended `test_workbench.py`:**
- schema creation; `registry_version` mismatch wipes + rebuilds.
- launch INSERT (`launching`) → bind UPDATE (`bound`).
- **Durability invariant — a row is deleted only on confirmed death:**
  - launch-fail + process confirmed dead → row deleted; launch-fail + `force_kill_failed` → `launching` row **retained** with its handle, `cleanupStatus: force_kill_failed`, retryable.
  - close uses claim-by-**update** to `closing`; process confirmed dead → row deleted; `force_kill_failed` → `closing` row **retained**, retryable (never re-creates an orphan).
  - **crash-mid-close** — a `closing` row whose owner is dead and Rhino alive is reclaimed by an external runtime and reset to `bound` (re-closable); a `closing` row whose Rhino is dead is reaped.
- reconcile branches: the four `bound` + three `closing` + three `launching` cases, incl. **late-bind promotion** (a `launching` dead-owner row whose Rhino bound after the owner died → re-probe promotes to `bound` + reclaim).
- reclaim rewrites owner identity and rebuilds `_OWNED`, **preserving an existing real `Popen`** over synthesizing a surrogate; compare-and-set aborts a reclaim when a peer won the race.
- **Port-down does not block reclaim (Codex finding 1):** `owner dead + Rhino pid alive + port down` → the row is **reclaimed** (not merely retained), `port_up=false` is recorded as an observation, and the Workbench is **closable by pid** via the surrogate.
- **Required safety tests (Codex):** (a) **panel-locked-no-reclaim** — a panel-locked runtime (live scope computed at call time, not a cached value), given a registry row for another session, claims nothing, rebuilds no `_OWNED`, and close returns `panel_target_locked`/`not_owned`; (b) **external-live-peer-no-steal** — an external runtime, given a row owned by a live peer, observes but never claims.
- close requires an owned row post-reconcile (transaction-guarded `not_owned` on owner mismatch).
- `PidProcessHandle` poll/wait/kill semantics against a fake pid.

**Live smoke — `--smoke p5-registry-reclaim`:** launch a real owned Workbench → assert a `bound` registry row. To exercise reclaim **honestly without killing the smoke's own MCP** (Codex finding 2): spawn a throwaway process, let it exit, confirm `_is_pid_alive` is false for its pid, then rewrite the row's `owner_pid`/`owner_token` to that **real dead pid + stale token** — the exact precondition of a now-dead predecessor MCP that launched this Workbench. Then run `reconcile_owned_registry` with the smoke's own (alive, external) `RuntimeOwner` → assert **reclaim** (owner rewritten to the smoke identity, `_OWNED` rebuilt with a `PidProcessHandle`) and that **close still works** via the surrogate → and separately that a dead-Rhino row is reaped. Verify against `manifest.json`; readiness timeout ≥120s. **Honesty boundary:** the predecessor's death is real (a genuinely exited pid), the Rhino is real, and the reclaim path runs end-to-end — we do not pretend the smoke's own MCP died, and we never fabricate the owner pid. (A naive "fresh `RuntimeOwner` over the same DB while the original MCP still runs" would *correctly refuse* to reclaim — the owner pid would still be alive — so it would prove no-steal, not reclaim.)

**Baseline parity:** prove `failed`/`errors` unchanged vs `main` (pre-existing pollution is not P5's).

## 18. Decision log

- **Sessions-only (Option A).** Durable ownership + reclaim is the purpose; documents stay discovery/session metadata with a non-authoritative snapshot on the row; the `documents` table waits for P6 when Save/fan-in gives it a job (§2, §6).
- **Approach 1:** registry is ownership truth; `_OWNED` is a derived process-handle cache, never authoritative (§5).
- **Shared workstation ledger,** not per-lineage and not a discovery mirror; ownership boundaries enforced by close/reclaim rules; `rhino_workbench_list` = my rows only (§4, §16).
- **Owner-liveness reclaim (Option A)** with `(owner_pid, owner_token, owner_started_at, owner_scope)` identity; conservative "alive PID ⇒ don't steal"; creation-time discriminator deferred (§10).
- **Panel scope is a HARD INVARIANT:** only `external` runtimes reclaim; panel-locked runtimes touch nothing here (§10).
- **Ownership and listener health are orthogonal (Codex finding 1):** reaping keys on the Rhino pid; reclaim keys on the owner pid; `port_up` is a recorded observation that blocks neither. A live-pid / down-listener Workbench with a dead owner is reclaimable and closable by pid (§9, §14).
- **Durability invariant (Codex findings 1 & 2): a row is deleted only when its process is confirmed dead.** Transient/terminal intent is durable — `launching` and `closing` are persisted statuses — so a crash mid-launch or mid-close never strands a live Workbench without a reclaimable record (§8).
- **Close is transaction-guarded by owner identity** via **claim-by-update** (set `closing`, kill off-thread, delete only on confirmed death; retain `closing` on `force_kill_failed`); no transaction held across the off-thread kill (§11).
- **Live scope, not cached (Codex finding 3):** lineage identity (`pid/token/started_at`) is cached; the panel-scope permission gate is recomputed every Workbench-tool entry via `current_owner_scope()` and passed into registry ops (§7).
- **Per-row `BEGIN IMMEDIATE` with compare-and-set** in reconcile; probe outside, validate-and-write inside; reconcile never terminates a process (§9, §12).
- **`reconcile_owned_registry` is one narrow function** called at every Workbench-tool entry after the panel guard (§9).
- **Adopt SlotStore patterns:** `BEGIN IMMEDIATE` + WAL + `busy_timeout`, persist-intent-probe-truth (DELETE dead, never mark dead), ephemeral wipe-on-version. **Diverge** on: PID-first lifecycle (no port reservation — RookNative self-assigns), no `adopted` column (owned-only ledger), reclaim keyed on owner-liveness for same-coordinator restart continuity (§6, §12).
