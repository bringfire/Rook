# GH Locked-Solver Crash — Durable Safe-Solve Policy

- **Date:** 2026-06-02
- **Status:** PR1 implemented and **live-verified 2026-06-02** — no crash, deferral correct across the full lock×enabled matrix, no pin-metadata regression (so the gated Task 6 one-shot restore was confirmed unnecessary). See `docs/superpowers/2026-06-02-gh-locked-solver-live-test-findings.md`. PR2 (sibling `ExpireSolution(true)` migration) and the U3 solve-token settle remain as follow-ups.
- **Author:** Claude (with senior-reviewer corrections folded in)
- **Area:** C# companion (`src/Rook/Handlers/GrasshopperHandler.cs`), `GrasshopperCore`, Python MCP wrapper (`mcp_server/src/rook/server.py`)
- **Reported by:** field user — "locked the GH canvas, asked Rook to update a GH script, Rhino crashed completely and instantly; reproduced multiple times."

---

## 1. TL;DR

`gh_set_script` (and five sibling GH-mutation routes) force a **synchronous** Grasshopper recompute via `IGH_ActiveObject.ExpireSolution(true)` immediately after mutating the canvas. Grasshopper's solver is single-threaded and non-reentrant; forcing a synchronous solve while the solver is **locked** (or otherwise in a state it doesn't expect) re-enters the solver and corrupts native state, producing an **uncatchable access violation** that takes Rhino down instantly.

The durable fix is a **shared safe-solve policy**: never synchronously recompute from an HTTP-driven mutation. Mark the mutated object dirty with `ExpireSolution(false)`, then — only when a solve is wanted *and* the solver is enabled — schedule **one asynchronous** `ScheduleSolution(delay ≥ 1)`. Surface solver state through `gh_status` (without gating edits), and stop the Python layer from claiming a fresh compile/error check when no solve actually ran.

This is **not** a global "block GH work when locked" gate. Edits still succeed while locked; only the recompute is deferred and reported as `verification_deferred`.

---

## 2. Symptom & root cause

### 2.1 Symptom
- Lock the GH canvas (Solution → "Lock Solver" / the padlock toggle).
- Ask Rook to update a GH script (`gh_update_script` → `gh_set_script` → `/gh/script`).
- Rhino terminates instantly, no error dialog. Reproducible every time.

### 2.2 The crash vector
`GrasshopperHandler.SetScript()` writes the new source, then:

```csharp
// GrasshopperHandler.cs:797-799
var expireMethod = obj.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
expireMethod?.Invoke(obj, new object[] { true });   // synchronous recompute
```

`ExpireSolution(true)` does not merely flag the component dirty — the `true` drives the document's `NewSolution(...)` **synchronously, on the calling thread, right now**. Per the Grasshopper API docs, `ExpireSolution(true)` recomputes "straight away," whereas `ScheduleSolution(int)` defers and, if already inside a solution, waits for the current solution to complete.

### 2.3 Why it is a hard crash, not a managed error
Three independent facts establish that this is a native/corrupted-state access violation, not a catchable managed exception:

1. **`SetScript` is wrapped in `try/catch`** (`GrasshopperHandler.cs:850`) that converts *any managed exception* into a JSON error. The user gets an instant process kill *instead* — the signature of an AccessViolation/corrupted-state failure, which .NET does not deliver to ordinary `catch` blocks.
2. **The call already runs on the Rhino UI thread.** The native route only marshals into managed code via `RhinoApp.InvokeOnUiThread` behind a `ManualResetEventSlim` with a 30-second timeout (`NativeGhBridgeRegistrar.cs:2473`). A *deadlock* would surface as a 30 s timeout JSON; an *instant* crash means the failure is below the managed layer. This strongly argues against a simple wrong-thread call as the primary cause; the lock-specific repro points instead at solver re-entrancy/state.
3. **The team already documented this failure mode** in the batch-edit path, which deliberately *defers* solving: *"Doing per-control ExpireSolution calls here can re-enter the GH UI callback and has caused bridge timeouts in practice."* (`GrasshopperHandler.cs:7284`). `SetScript` does exactly what that comment warns against.

### 2.4 Why "locked" is the trigger
There is no solver-state awareness anywhere in the GH handler. The readiness guard only checks visibility:

```csharp
// GrasshopperCore.cs:129
ReadyForEdit = available && canvas != null && document != null && canvasVisible != false;
```

A locked canvas passes this guard and reaches the synchronous `ExpireSolution(true)`. The locked solver is the state that turns a normally-survivable synchronous recompute into a guaranteed re-entrancy crash.

### 2.5 Architectural note (where the fix does *not* go)
The native HTTP layer (`GrasshopperProxyHandler.cpp:438`, `DispatchGrasshopperRoute`) only forwards the request to the managed callback. It is not the fix site. The fix is in the **managed GH handler** and, secondarily, the **Python `gh_update_script` wrapper**.

---

## 3. Non-goals (what we will deliberately NOT do)

- **Do not wrap `ExpireSolution(true)` in `try/catch`.** A corrupted-state AV is not reliably catchable; this would mask nothing and fix nothing.
- **Do not auto-unlock the solver.** If the user locked it, Rook preserves that state.
- **Do not make "solver locked" a `ReadyForEdit == false` condition.** Many operations remain valid while locked (status, snapshot, inspection, even source edits). The boundary is **solve-specific, not edit-specific**.
- **Do not use `ScheduleSolution(0)`.** Zero-delay schedules are documented as recursive and risk stack exhaustion. Always `delay ≥ 1`.
- **Do not implement verification as naïve "poll until `SolutionState` is idle."** `gh_status` can report idle *before* the scheduled solve starts; an idle-only poll returns immediately and reads stale errors. See §8.
- **Do not patch only `SetScript`.** The same synchronous-recompute anti-pattern exists at five sibling sites; the fix is a shared helper, not a one-off (see §9).

---

## 4. The safety invariant

> **No HTTP-driven GH mutation handler may call `ExpireSolution(true)` (or any synchronous `NewSolution`). Post-mutation recompute happens only via asynchronous `ScheduleSolution(delay ≥ 1)`, and only when the solver is enabled.**

Everything else in this design (the fail-open default, the predicate, the metadata) is *licensed by* this invariant: because the helper never synchronously recomputes, even a wrong solver-state reading cannot reintroduce the crash — the worst case is a harmlessly-scheduled async solve that GH defers.

---

## 5. Architecture — the shared safe-solve helper (PR1)

New partial file: **`src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs`** (keeps the ~7k-line handler from growing; same class, isolated surface). PR1 introduces the **general** API and proves it on the crash path; PR2 migrates the siblings onto it without redesigning it.

### 5.1 Outcome type

```csharp
internal readonly struct GhSolveOutcome
{
    public bool SolveScheduled { get; init; }       // did we ScheduleSolution?
    public bool SolverLocked { get; init; }          // solver confirmed disabled
    public bool SolverStateKnown { get; init; }      // could we inspect solver state at all?
    public bool VerificationDeferred { get; init; }  // caller MUST NOT claim a fresh compile/error check
    public string[] Warnings { get; init; }          // human-readable notes (e.g. "solver locked; recompute deferred")
}
```

`SolverStateKnown` is what distinguishes "confirmed unlocked" from "could not inspect, used safe async scheduling." Without it, a reflection break would masquerade as "unlocked."

### 5.2 Helper API

```csharp
// Single-object form — covers ~all current call sites (each dirties exactly one target).
private GhSolveOutcome RequestPostMutationSolve(
    object document, object dirtyObject, bool requestSolve, int delayMs = 1);

// Batch form — for multi-target mutations (e.g. gh_edit).
private GhSolveOutcome RequestPostMutationSolve(
    object document, IReadOnlyList<object> dirtyObjects, bool requestSolve, int delayMs = 1);

// Predicate — returns both the enabled flag and whether it could be determined.
private (bool Enabled, bool Known) IsSolverEnabled(object document);
```

The single-object overload is the "helper wrapper for one object" that keeps PR2's mechanical migration to one-liners (e.g. `RequestPostMutationSolve(doc, obj, requestSolve: true)`).

### 5.3 Behavior

1. For each `dirtyObject`: `ExpireSolution(false)` — mark dirty, **no** recompute.
2. `(enabled, known) = IsSolverEnabled(document)`.
3. Construct the outcome per the matrix below; schedule at most **one** `document.ScheduleSolution(delayMs)` when appropriate.

| Solver state | requestSolve | ScheduleSolution? | `SolveScheduled` | `SolverLocked` | `SolverStateKnown` | `VerificationDeferred` |
|---|---|---|---|---|---|---|
| Known enabled | true | yes | true | false | true | **false** |
| Known locked | true | no | false | true | true | **true** |
| Unknown (reflection miss) | true | yes (safe async) | true | false | false | **true** (conservative — can't confirm the solve ran) |
| Any | false | no | false | (per state) | (per state) | false (nothing to verify) |

Rationale for the "unknown" row: scheduling is still safe (invariant §4), but we cannot *confirm* a solve will run, so we do not let the Python layer claim a verified compile. This is stricter than the floor the reviewer required ("don't report `verification_deferred=false` when unknown unless a solve was scheduled") and is the honest choice.

### 5.4 Predicate (`IsSolverEnabled`) and fail-direction
Read, by reflection, the solver-enable flag(s) the U1 probe identifies (§10): static `GH_Document.EnableSolutions` and, if U1 confirms it tracks the lock, instance `document.Enabled`. **`SolutionState` is explicitly excluded from the lock predicate** — it is transient solve status, not a lock flag, and `ScheduleSolution(delay ≥ 1)` already handles "currently solving" by waiting. Treating non-idle `SolutionState` as disabled would manufacture false deferrals. `SolutionState` is surfaced as telemetry only (§7).

- Both/any reads succeed → `Known = true`, `Enabled =` logical-AND of the readable flags.
- Total reflection miss → `Known = false`, `Enabled = true` (**fail-open**), licensed by §4.

### 5.5 `SetScript` integration (PR1 proof-of-use)
After writing source and capturing pin descriptions (§6), `SetScript`:
1. Calls `RequestPostMutationSolve(gh.Document!, obj, requestSolve: true)`.
2. Calls `RefreshCanvas(gh.Canvas!, scheduleSolution: false)` — repaint only; the helper now owns scheduling (avoids stacking a second solve; see §9).
3. Folds the `GhSolveOutcome` into its JSON response as `solve_scheduled`, `solver_locked`, `solver_state_known`, `verification_deferred`, `warnings`.

---

## 6. Pin-description preservation

`SetScript` (and the pin-edit site at line 1553) restore pin descriptions after recompute because RhinoCode resets `Description` to the framework default on recompile. Today's restore lands correctly *because* the solve is synchronous. Removing the synchronous solve moves the clobber in time, so the restore strategy must be re-derived empirically (probe **U2**, §10), then implemented robustly:

- **Always** restore immediately after `SetSource`. Covers the locked / no-solve path and the case where RhinoCode recompiles eagerly on `SetSource`.
- **Conditionally** (only if U2 proves a *scheduled solve re-clobbers an unchanged-source component*) arm a **one-shot `GH_Document.SolutionEnd` handler** that re-applies descriptions on the next solution, then unsubscribes.

Restoration is **idempotent** (re-applying correct descriptions is a no-op), so "immediate + conditional one-shot" is always safe; the probe only decides whether the one-shot is necessary. Expected happy path: immediate restore alone suffices and no event hook is implemented.

**Known limitation (disclosed, low severity):** if U2 shows the *solve* (not `SetSource`) is what clobbers descriptions, then in the **locked** case the descriptions remain correct after `SetSource` but may reset on the eventual *post-unlock* solve — because §6.1 deliberately does **not** arm a handler while locked (anti-leak, per the reviewer). We accept this rather than hold a permanent captured handler open for an indefinitely-locked solver; the script still functions, only pin *descriptions* are affected, and re-running `gh_set_script` after unlock restores them. If U2 shows `SetSource` clobbers (the likely RhinoCode behavior), this edge does not arise at all.

### 6.1 `SolutionEnd` one-shot lifecycle rules (only if implemented)
To prevent a permanent captured handler from leaking when the solver stays locked or the document closes:
- **Armed only on the scheduled-solve (enabled) path** — never while locked. (The locked path relies on immediate restore.)
- **Fires once, then unsubscribes.**
- **Validity check on fire:** if the target component is no longer in the document, skip the restore and unsubscribe.
- **Bounded lifetime:** a companion timeout (e.g. a one-shot idle/timer) unsubscribes the handler if no solution completes within a small window, so a never-completing solve cannot strand it.

This strategy is reused by the `gh_set_script_pins` site in PR2 (same recompile-clobber dependency), not reinvented.

---

## 7. `gh_status` solver surface (report, never gate)

Add to `GrasshopperStatusDto` and populate in `GrasshopperCore.ObserveStatus` via the same reflection the predicate uses:

- `SolverEnabled` (`bool?`) — confirmed enabled/disabled, or null if unknown.
- `SolverStateKnown` (`bool`).
- `SolutionState` (`string`) — **telemetry only**, for diagnostics and for the settling logic in §8.

**`ReadyForEdit` is unchanged** (`available && canvas && document && visible`). Solver lock is surfaced so clients (the Python layer, tests, agents) can *see* it; it is never a precondition for edits.

---

## 8. Python `gh_update_script` — deferral + bounded settling (PR1)

Two changes in `_execute_gh_update_script` (`server.py:1800`):

### 8.1 Honor deferral
After the `/gh/script` write, read `solver_locked` / `verification_deferred` / `solver_state_known` off `write_data`. If `verification_deferred` is true, **skip** the `sleep + /gh/errors` block entirely (it would be stale — no fresh solve ran) and return `component_errors=[]` with an explicit `verification_deferred` message such as *"Grasshopper solver is locked; unlock and run gh_solve to verify."* plus the solver flags. Today the function implies a compile/error check happened regardless of solver state.

### 8.2 Bounded wait for scheduled-solve *settling* (not naïve idle-poll)
The sync→async change means the write returns *before* the solve runs, so the old fixed `asyncio.sleep(0.3)` becomes a race on heavy scripts, and a level-triggered "poll until idle" can observe the pre-solve idle and return immediately with stale errors. Replace it with a **bounded wait for solve completion/settling**, choosing the strongest mechanism available (probe **U3**, §10):

1. **Best — solve-completion token.** If GH exposes a reliable monotonic solve-completion marker by reflection (surfaced through `gh_status`), capture it before the write and wait until it advances (bounded timeout).
2. **Acceptable — edge-detected settle.** Poll `gh_status` until `SolutionState` is observed **non-idle and then idle**, with a bounded timeout *and* an initial delay ≥ the scheduled delay. This is edge-triggered, so it cannot satisfy on the pre-solve idle.
3. **Floor — bounded best-effort sleep.** If neither a token nor reliable `SolutionState` transitions exist, keep a fixed but bounded sleep and label verification **best-effort** until a real solve token exists.

Verification is labeled best-effort until mechanism (1) is available. Only when a solve was actually scheduled *and* settling was observed does the wrapper report a confident error check.

---

## 9. Call-site inventory & PR1/PR2 split

All synchronous `obj.ExpireSolution(true)` sites in `GrasshopperHandler.cs`:

| # | Line | Route | Dirties | Restores pins? | RefreshCanvas after? | PR |
|---|------|-------|---------|----------------|----------------------|-----|
| 1 | 799  | `gh_set_script` (`SetScript`) | component | **yes** | yes (→ must become `scheduleSolution:false`) | **PR1** |
| 2 | 1553 | `gh_set_script_pins` (var-param + `SetSource`) | component | **yes** | no | PR2 |
| 3 | 1867 | `gh_set_reference` (append persistent) | param | no | no | PR2 |
| 4 | 2042 | `gh_clear_reference` (clear persistent) | param | no | no | PR2 |
| 5 | 5444 | `ConnectComponents` (`AddSource`) | target | no | yes (→ `scheduleSolution:false`) | PR2 |
| 6 | 5566 | `DisconnectComponents` (`RemoveSource`) | target | no | yes (→ `scheduleSolution:false`) | PR2 |

Migration notes baked into both PRs:
- **`RefreshCanvas` double-schedule:** sites 1, 5, 6 currently call `RefreshCanvas(canvas)` (defaults `scheduleSolution: true`, i.e. `canvas.ScheduleSolution(50)`) *in addition to* the synchronous `ExpireSolution(true)`. Post-migration they must call `RefreshCanvas(canvas, scheduleSolution: false)` so the helper is the single scheduler.
- **Pin-restore reuse:** site 2 carries the same recompile-clobber dependency as site 1, so it reuses the §6 strategy.

**PR1** = `GrasshopperHandler.SolvePolicy.cs` (helper + predicate + outcome) + migrate site 1 + pin-description strategy + `gh_status` surface + Python deferral & settling + `requires_rhino` tests.

**PR2** = mechanically migrate sites 2–6 onto the helper (each: "does it preserve prior behavior while using the shared policy?") + their tests + extend the static guard test (below).

---

## 10. Implementation probes (first step of PR1)

Run on an **isolated throwaway GH document/component — never the user's working file.** Honesty note: U1 and U3 are read-only; **U2 is a low-risk mutation** (it calls `SetSource`) and requires explicit confirmation of a throwaway document before running.

- **U1 (read-only) — lock mapping.** With the canvas locked, read candidate members and see which flip: static `GH_Document.EnableSolutions`, instance `Enabled`, `SolutionState`, `SolutionDepth`. Finalizes the §5.4 predicate member set. Also confirm `ScheduleSolution(delay ≥ 1)` while locked is non-crashing and non-forcing (validates the whole approach; if false on some build, flip the predicate to fail-closed).
- **U2 (low-risk mutation, throwaway only) — pin clobber timing.** Measure pin descriptions at three points on a throwaway script component: before `SetSource`, after `SetSource` (pre-solve), after a scheduled async solve completes. Decides immediate-restore-only vs the §6.1 one-shot.
- **U3 (read-only) — solve-completion marker.** Determine whether `GH_Document` exposes a reliable monotonic solve-completion marker via reflection, to pick the §8.2 settling mechanism (token vs edge-detected vs floor).

---

## 11. Test matrix (`requires_rhino`)

**PR1:**
- **Unlocked:** `gh_set_script` compiles, `/gh/errors` reports, pin descriptions survive (3-point check).
- **Locked:** `gh_set_script` **does not crash**; source round-trips; response carries `solver_locked=true, verification_deferred=true`; **solver remains locked** afterward.
- **Unlock + `gh_solve`:** component recomputes; pin descriptions intact.
- **Static guard:** a source-scan test asserting no `ExpireSolution(true)` remains in migrated mutation paths (grows in PR2).
- **Optional / non-blocking:** reflection-miss ("unknown") simulation — schedules safely, `solver_state_known=false`, no crash. Skipped if reflection cannot be faked cleanly; must not block PR1.

**PR2:** per migrated site — locked does not crash; unlocked preserves prior behavior; (site 2) pin descriptions survive.

---

## 12. Rollout

1. **Probe** (U1/U2/U3) on a throwaway document — finalizes predicate members, pin strategy, settling mechanism.
2. **PR1** — durable helper proven on the crash path; stops the reported crash; establishes the general API; status surface; Python deferral + settling; tests.
3. **PR2** — mechanical migration of sites 2–6 onto the helper; narrower review focus; static-guard test extended.

Per house workflow: `fix/` branches, test-before-PR, squash merge. High-stakes (irreversible crash-class) change → expect multiple review rounds.

---

## 13. Risks & open questions

- **`ScheduleSolution`-while-locked semantics** (resolved by U1): the design assumes async scheduling while locked is non-crashing and defers recompute. If a build violates this, the predicate flips to **fail-closed** (unknown → do not schedule) — the only direction change required.
- **Settling robustness** (resolved by U3): without a real completion token, §8.2 is best-effort; a heavy post-unlock solve could still outrun a bounded edge-detected settle. Acceptable for PR1; a token is the principled follow-up.
- **One-shot handler complexity** (gated by U2): if U2 shows immediate restore suffices, §6.1 is not implemented at all, eliminating the lifecycle surface.

---

## 14. References

- Grasshopper API — [`ExpireSolution(Boolean)`](https://developer.rhino3d.com/api/grasshopper/html/M_Grasshopper_Kernel_GH_DocumentObject_ExpireSolution.htm), [`ScheduleSolution(Int32)`](https://developer.rhino3d.com/api/grasshopper/html/M_Grasshopper_Kernel_GH_Document_ScheduleSolution.htm), [`EnableSolutions`](https://developer.rhino3d.com/api/grasshopper/html/P_Grasshopper_Kernel_GH_Document_EnableSolutions.htm), [`SolutionState`](https://developer.rhino3d.com/api/grasshopper/html/P_Grasshopper_Kernel_GH_Document_SolutionState.htm).
- Code: `GrasshopperHandler.cs` (`SetScript` 653–858; sync-expire sites 799/1553/1867/2042/5444/5566; `RefreshCanvas` 5785; batch-edit re-entrancy comment 7284), `GrasshopperCore.cs:129` (`ReadyForEdit`), `NativeGhBridgeRegistrar.cs:2473` (UI-thread marshal), `GrasshopperProxyHandler.cpp:438` (native dispatch), `server.py:1800` (`_execute_gh_update_script`).
- Prior art in-repo: `docs/superpowers/specs/2026-05-14-gh-legacy-route-readiness-boundary-design.md`, `docs/superpowers/specs/2026-05-18-runscript-execution-safety-design.md`.
