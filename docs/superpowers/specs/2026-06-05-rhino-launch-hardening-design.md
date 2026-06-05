# Rhino Launch Hardening — Deterministic, Legible Coordinator-Owned Launch

> **Origin:** #222. The #218 live re-verify was blocked because the test harness's launched
> Rhino never reached readiness. Both the harness (`runtime_harness.py:741`) and the product
> (`workbench.py:266` — `launch_owned_workbench`, called by `rhino_workbench_launch` / P4) launch
> Rhino via a bare `subprocess.Popen([Rhino.exe])` — the shared weak seam for autonomous launch.
> This slice **gates the #218 live close** and **precedes P7** (fan-in leans on reliable Workbench
> lifecycle).

## 1. One sentence

Replace the bare `Popen([Rhino.exe])` shared by the test harness and the product Workbench
launcher with one hardened launch primitive that **either** reaches PID-correlated RookNative
discovery + `/ping`, **or** returns a structured readiness failure (reason + evidence) a
coordinator can reason about — **diagnosing** startup/profile/plugin-load blockage, never
**automating** Rhino's UI.

## 2. Binding principles

- **Signals, not control.** Produce evidence; never screen-automate, click dialogs, drive
  windows, or clear global/user Rhino state. Window/OS evidence is *diagnostic only*.
- **Never mutate the user's default profile or documents.** Config-level state changes are
  permitted ONLY inside a dedicated Rook-owned scheme, and only when proven scheme-local.
- **No silent fallback.** An isolated scheme that isn't validated fails structured; it does not
  quietly become the default profile.
- **Fail closed.** Any capability whose safety can't be proven stays **disabled and visible**.

## 3. North-star requirement

A coordinator-owned Rhino launch must EITHER reach a PID-correlated RookNative discovery record +
`/ping`, OR return a structured readiness failure with enough evidence to distinguish failure
classes — and must NEVER rely on a human clearing Rhino startup state.

## 4. Non-goals (hard boundaries)

- No UI automation / computer-use / dialog dismissal / window driving as *control*.
- No mutation of the user's default Rhino profile, global state, or documents.
- **No broad "cleanup recovery files" behavior** (explicitly forbidden; see §9).
- No changes to session routing (P3), registry semantics (P5), artifact registry (P6), or P7.
- Readiness *definition* unchanged: PID-correlated native discovery record + `/ping`.

## 5. Architecture — shared launch primitive

New leaf module **`mcp_server/src/rook/rhino_launch.py`** that **owns the launch + readiness
primitives**, imported by BOTH `runtime_harness.py` and `workbench.py:launch_owned_workbench` (the
two current bare-`Popen` sites).

**Ownership move (avoids a circular import).** These primitives are currently defined *in*
`runtime_harness.py` — `DiscoveryFailureReason` (l.66), `DiscoveryError` (l.76), `OwnedRhinoRecord`
(l.83), `OwnedRhinoDiscovery` (l.949) — and `runtime_harness.py` will import `rhino_launch.py`. If
`rhino_launch.py` imported these *back* from `runtime_harness.py`, that's a cycle. So they **move
into `rhino_launch.py`**:

- `rhino_launch.py` owns: the discovery record types, the readiness wait + ping orchestration, the
  launch (argv / scheme / `/nosplash`), the structured `LaunchOutcome`, the capability flags.
- `runtime_harness.py` keeps **harness orchestration** (`RhinoHarnessResult` (l.134) / manifest,
  smoke run, artifact copy, cleanup) and imports the moved primitives from `rhino_launch.py`.
- **`ping_native`**: confirm its home in the plan — if it already lives in a leaf (e.g.
  `bridge.py`), `rhino_launch.py` imports it from there (no move); if in `runtime_harness.py`, it
  moves too.
- **Blast-radius control:** `runtime_harness.py` keeps **thin re-exports**
  (`from .rhino_launch import DiscoveryError, DiscoveryFailureReason, OwnedRhinoRecord, OwnedRhinoDiscovery`)
  so the current importers — `workbench.py` and the four tests (`test_workbench`,
  `test_runtime_harness`, `test_native_command_control_live`, `test_runscript_safety_live`) — keep
  working unchanged.

The module builds **explicit** argv (`/nosplash` always; `/scheme=<scheme>` only when isolation is
both *requested* and *available*), runs the readiness wait it now owns, and returns a structured
`LaunchOutcome` (§8). It stays a leaf: subprocess + its own discovery/ping primitives; no
session/registry/artifact imports.

## 6. Scheme model — "prefer isolated *when validated*" (NOT unconditional isolated-by-default)

Default scheme names: harness → `RookHarness`; product → `RookWorkbench`. Opt-out to the user's
default profile via explicit env (`ROOK_WORKBENCH_SCHEME=default`, and a harness equivalent).

The isolated scheme is the operational path ONLY once validated. Per-launch state machine:

| State | Meaning | Action |
|---|---|---|
| `scheme_requested` | caller asked for an isolated scheme (the default) | use it ONLY if `schemeIsolationAvailable` AND it reaches `scheme_validated_ready` |
| `scheme_validated_ready` | the scheme has demonstrably autoloaded RookNative (discovery+ping reached) | use it as the operational path |
| `scheme_not_ready` | requested but not validated | **fail structured** (`scheme_autoload_not_validated`); do **not** silently use the default profile |
| `default_explicitly_requested` | caller set the opt-out env | launch in the default profile, no `/scheme=` |

**The spec does NOT claim isolated-by-default as the operational path until §10 Phase 2 establishes
how RookNative autoload is seeded in a named scheme.** Reconciling with the capability flags:

- `schemeIsolationAvailable == false` (Phase 1): scheme isolation is not built yet, so the
  operational path is the **default profile** (with `/nosplash` + structured diagnostics). This is
  *not* a "fallback" — isolation simply isn't available; it's explicit by capability.
- `schemeIsolationAvailable == true` (Phase 2): the operational path is the **isolated scheme**. If
  a specific launch isn't `scheme_validated_ready` → `scheme_autoload_not_validated` structured
  failure; **no silent default fallback** (the caller can explicitly opt out via the env).

## 7. Capability flags (fail-closed, visible)

- **`schemeIsolationAvailable: bool`** — whether scheme isolation (Phase 2) is built + proven.
  **Default false.** Surfaced in every launch outcome. When false → launches use the default
  profile (Phase 1 behavior).
- **`canResetSchemeRecoveryState: bool`** — whether the exact scheme-local crash-recovery marker
  has been identified + proven scheme-local (§9). **Default false.** Gates the reset logic. When
  false → the launcher DETECTS + reports recovery state as evidence but **never mutates** it.

Both flags are explicit so no one ships a half-proven isolation/reset under pressure.

## 8. Readiness outcome — *reason* SEPARATE from *evidence*

`LaunchOutcome`:
- Success: `{ ok: true, pid, port, discoveryRecordPath, evidence }`.
- Failure: `{ ok: false, reason: <code>, evidence }`.

**Reason codes** (the failure REASON — not evidence):

- `launch_exec_failed` — `Popen` raised (exe missing / OSError).
- `process_exited_before_discovery` — process died before any discovery record (exit code in evidence).
- `bind_timeout_no_discovery` — process alive, timeout, no discovery record.
- `bind_timeout_no_ping` — discovery record appeared but `/ping` never succeeded before timeout.
- `invalid_discovery_record` — a record appeared but is malformed / wrong-pid.
- `scheme_autoload_not_validated` — a **preflight/config-validation** failure (the requested
  isolated scheme has not been validated to autoload RookNative). NOT a runtime wait result.

There is deliberately **no window-causal reason** (e.g. no `readiness_blocked_by_startup_window`): a
window is *evidence*, not proof of causation (it could be a normal startup window, disabled
autoload, a modal, a profile issue, or a plugin-load failure). A no-discovery timeout with a window
present stays `bind_timeout_no_discovery`, with the window facts carried as evidence + a non-causal
hint (below).

These reason codes **reconcile with / extend the existing `DiscoveryFailureReason` taxonomy
introduced in P4** — the implementation maps to or extends that enum rather than inventing a
parallel taxonomy.

**Evidence** (attached to every outcome, success or failure): `scheme`, `isolationMode`,
`discoveryRecordPath`, `discoveryLogSeen`, `windows` (hwnd/title/class/visible when cheaply
available), `visibleWindowCount`, `emptyTitleWindowPresent`, `exitCode`, `argv`, `elapsedSeconds`,
and a **non-causal** `diagnosticHint` (e.g. `"startup_window_present_no_discovery"` when a visible
or empty-title window coincides with a no-discovery timeout). A window is **evidence, not proof** —
Rook reports what it saw and never infers that a window *caused* the failure. (Window enumeration
already exists at cleanup — reuse it at readiness-failure time.)

## 9. Loop-break — Option 1 + safety clause, capability-gated

The force-kill → crash-recovery → next-launch-hang loop is broken by resetting ONLY the dedicated
Rook scheme's recovery marker before launch — but ONLY behind `canResetSchemeRecoveryState`
(default false).

**Discovery-step-first (required before any reset ships):**
1. Identify the **exact** crash-recovery/autosave marker (file/registry key) Rhino uses for the
   dedicated scheme.
2. **Prove it is scheme-local** (under the Rook scheme's storage, not global/default).
3. Provide a **dry-run/logging** path (record exactly what would be / was cleared).
4. **Fail closed:** if it can't be proven scheme-local → `canResetSchemeRecoveryState` stays false;
   the launcher DETECTS + reports recovery state as evidence but NEVER mutates it. The default
   profile and user documents are never touched.

No abstract "clear recovery state"; no broad "cleanup recovery files" patch (§4).

## 10. Phasing (capability-gated, same spec)

- **Phase 1 (ships regardless):** the shared `rhino_launch.py` helper; `/nosplash`; the structured
  `LaunchOutcome` (reason + evidence); both callers wired; capability flags present and **false**.
  Operational path = default profile (no `/scheme=`). This unifies the launch path, removes the
  splash variable, and makes every failure legible. **Phase 1's diagnostics are also the empirical
  gate:** the window evidence on the next blocked launch reveals whether the hang was the splash
  (already fixed by `/nosplash`) or crash-recovery (needs Phase 2) — answered with data, not a guess.
- **Phase 2 (same spec, only if the §9 + scheme-autoload discoveries prove out):** scheme
  validation + autoload seeding (documented, config-level) → `schemeIsolationAvailable:true`;
  scheme-local recovery reset → `canResetSchemeRecoveryState:true`. If either can't be proven
  safely, it stays **disabled and visible** (`false`); the framework is in place to enable later.

## 11. Wiring

- `runtime_harness.py` → uses `rhino_launch` with scheme `RookHarness` (when available); surfaces
  the structured `LaunchOutcome` in its manifest (replacing the ad-hoc readiness warning).
- `workbench.py:launch_owned_workbench` → uses `rhino_launch` with scheme `RookWorkbench` (when
  available); `ROOK_WORKBENCH_SCHEME=default` opt-out; returns the structured outcome to
  `rhino_workbench_launch` so a coordinator gets a **legible failure, not a hang**.
- Both report `scheme`, `isolationMode`, `schemeIsolationAvailable`, and the validation result.

## 12. Discovery steps required (the two live unknowns)

These need inspection of Rhino's scheme storage (registry keys / settings files) or McNeel docs —
**inspection work, not a successful automated launch**, so NOT blocked by the very bug:
- **D1:** how to seed/enable RookNative autoload in a named scheme (→ `schemeIsolationAvailable`).
- **D2:** the exact scheme-local crash-recovery/autosave marker (→ `canResetSchemeRecoveryState`).
Each **fails closed** if not safely identifiable.

## 13. Testing

- **Unit (no Rhino):** argv/env construction (nosplash always; `/scheme=` only when
  available+requested; opt-out env); the classifier (mock signals → correct reason; a window during
  a no-discovery timeout yields `bind_timeout_no_discovery` + `emptyTitleWindowPresent` /
  `diagnosticHint`, never a window-causal reason); the reset logic (dry-run;
  **fail-closed** when the marker isn't provably scheme-local; `canResetSchemeRecoveryState:false` →
  no mutation); capability-flag gating.
- **Live (gated — and literally the #218 unblock):** re-run p3–p6 through the hardened harness.
  Phase 1 alone reports (via diagnostics) whether `/nosplash` suffices; Phase 2 (if enabled)
  breaking the loop is proven by the four sequential smokes reaching readiness reliably.

## 14. Files

- **Create:** `mcp_server/src/rook/rhino_launch.py`, `mcp_server/tests/test_rhino_launch.py`.
- **Modify:** `mcp_server/src/rook/runtime_harness.py` (use the helper; structured manifest);
  `mcp_server/src/rook/workbench.py` (use the helper in `launch_owned_workbench`; opt-out env;
  return structured outcome).
- **Untouched:** session routing, registry, artifact registry, P7.

## 15. Decision log

- "Prefer isolated *when validated*," NOT unconditional isolated-default; 4-state scheme machine;
  no silent fallback; don't claim isolated-default operational until autoload seeding (Phase 2) is
  real. [user]
- Reason codes **separate** from evidence; a window is **evidence, not proof** — no window-causal
  reason; a no-discovery timeout with a window stays `bind_timeout_no_discovery` + non-causal
  `diagnosticHint` / `emptyTitleWindowPresent` / `visibleWindowCount`. `scheme_autoload_not_validated`
  is preflight, not a wait result; no vague `plugin_not_ready_under_scheme` bucket; reconcile with
  the P4 `DiscoveryFailureReason`. [user]
- `rhino_launch.py` **owns** the moved discovery/readiness primitives (`DiscoveryFailureReason` /
  `DiscoveryError` / `OwnedRhinoRecord` / `OwnedRhinoDiscovery`); `runtime_harness.py` imports them
  back via thin re-exports (bounding blast radius) and keeps harness orchestration — avoids the
  circular import. [user]
- Phased **capability flags** (`schemeIsolationAvailable`, `canResetSchemeRecoveryState`), default
  false + visible; Phase 1 ships regardless, Phase 2 only if proven. [user]
- `canResetSchemeRecoveryState` gates all reset; default false until the exact scheme-local marker
  is identified; prevents a broad cleanup-recovery-files patch under pressure. [user]
- Signals-not-control; never mutate default profile/documents; readiness definition unchanged. [user]
