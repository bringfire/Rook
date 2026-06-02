# GH Locked-Solver Crash Fix — Live Verification Findings

**Date:** 2026-06-02
**Branch:** `fix/gh-locked-solver-crash`
**Build under test:** companion deployed 18:19; updated Python MCP layer
**Environment:** Rhino 8 + Grasshopper (assembly `8.31.26126.13431`), live MCP connection
**Companion check:** `gh_status` exposed the new solver fields (`solverEnabled`, `solverStateKnown`, `solutionState`) → new build confirmed loaded.

## Summary

The locked-solver crash is **gone**. Editing a Grasshopper script component while the
solver is locked previously crashed Rhino instantly — a synchronous `ExpireSolution(true)`
re-entered Grasshopper's non-reentrant solver. The fix defers the solve when the solver is
locked (or its state is unknown): it writes the source but does not recompile, and reports
`verification_deferred: true`.

Live testing across the full lock × enabled matrix confirms:

- **No crash in any state.** `rhino_ping` returned `pong` after every edit.
- **The deferral guard keys solely on the global solver lock state** (`solver_locked` /
  `solver_state_known`). A component's enabled/disabled state has no bearing on the decision.
- **Source writes are durable in every state** — the new source round-tripped on read-back
  even when the component was not recompiled.

## Test matrix (all executed live, all survived)

| Solver   | Component | Path taken | `solver_locked` | `verification_deferred` | `solve_scheduled` | Source round-tripped | Crash? |
|----------|-----------|------------|-----------------|-------------------------|-------------------|----------------------|--------|
| Unlocked | Enabled   | normal     | false           | false                   | **true**          | yes                  | No     |
| **Locked**   | Enabled   | **deferred**   | true            | **true**                | false             | yes                  | No     |
| Unlocked | Disabled  | normal     | false           | false                   | **true**          | yes                  | No     |
| **Locked**   | Disabled  | **deferred**   | true            | **true**                | false             | yes                  | No     |

Test component: C# script, `A = Convert.ToDouble(R) * k;`, single `double` in (`R`) / out (`A`).
Each row used a distinct multiplier so the read-back unambiguously confirmed the write.

## Critical regression (locked solver, faithful repro)

The exact pre-fix crash trigger — `gh_update_script` on a script component with the solver
locked — now returns cleanly:

```json
{
  "verification_deferred": true,
  "solver_locked": true,
  "solver_state_known": true,
  "solve_scheduled": false,
  "component_errors": [],
  "verification_note": "Grasshopper solver is locked or its state is unknown; the script source was written but not recompiled. Unlock the solver and run gh_solve to verify."
}
```

- Rhino did not crash (`rhino_ping` → `pong` immediately after).
- The response does **not** claim a clean compile — it flags the edit as deferred.
- Read-back confirmed the new source was written despite no recompilation.

## Unlocked path still behaves normally

With the solver unlocked, `gh_update_script` runs a real compile/error check and schedules a
solve — `verification_deferred: false`, `solve_scheduled: true`, `component_errors` populated
by an actual check. The fix does not regress the normal edit path.

## Crash-mechanism interpretation (disabled component vs. locked solver)

A follow-up test checked whether the crash trigger was a *disabled component* rather than a
*locked solver*. It is not — they are distinct:

- **Disabling a single component** leaves the document-level solver live and unlocked. The
  edit takes the normal path (writes source + schedules `ExpireSolution`); the solver accepts
  the schedule because it is not mid-solve or locked. No re-entrancy, no crash.
- **Locking the solver** puts the document-wide solver into the non-reentrant state. A
  synchronous `ExpireSolution(true)` there re-enters the locked solver → the original crash.
  This is precisely the state the fix detects and defers on.

When **both** conditions hold (solver locked *and* component disabled), the locked-solver
guard dominates: the edit takes the deferred path (`verification_deferred: true`,
`solve_scheduled: false`), not the scheduled-solve path. The original locked-solver reading of
the crash report is therefore correct, and the fix neutralizes it regardless of the target
component's enabled state.

## Probe U2 — pin-metadata clobber on unlocked edit (Task 6 gate)

Settles whether `gh_update_script` clobbers user-customized input-pin metadata (the concern
behind probe U2 / Task 6). Run on a fresh C# script component with the solver **unlocked**.

A user-customized input pin was set via the GH UI (name, nickname, and description all
customized), then `gh_update_script` was run with a new body
(`A = Convert.ToDouble(Radius) - 1.0;`). The canvas was snapshotted before and after.

| Pin field                  | Before edit                 | After edit                  | Result      |
|----------------------------|-----------------------------|-----------------------------|-------------|
| Name                       | `CUSTOM_DESC_KEEPME`        | `CUSTOM_DESC_KEEPME`        | ✅ survived |
| NickName (code identifier) | `Radius`                    | `Radius`                    | ✅ survived |
| **Description**            | `CUSTOM_DESC_KEEPME_tooltip`| `CUSTOM_DESC_KEEPME_tooltip`| ✅ survived |

- No clobber, no reset-to-default — every customized field persisted across the source write.
- The edit genuinely applied and recomputed: output `A` previewed `-1`
  (`Radius` defaulting to `0` → `0 - 1.0`), with zero component errors (post-edit snapshot
  `epoch: 2`, `errors: 0`).

**Verdict: no regression — PR1 is clean on pin-metadata preservation; Task 6 is not needed.**

### Incidental observation (expected GH behavior, not a Rook bug)

Renaming an input pin to a value containing spaces (`"This Is A Test Input Pin Name"`) raised
`"Input parameter name ... is invalid identifier"`. On a C# script component the input pin's
name doubles as the code variable identifier, so it must be a valid C# identifier. The error
cleared as soon as the name was changed to a valid identifier. This is stock Grasshopper
validation, not a Rook regression.

## Verdict

Fix confirmed. Safe to merge with respect to the locked-solver crash. No crashes, no modal
dialogs, prompt responses, durable source writes, and a correctly scoped deferral guard across
all four lock × enabled states. Probe U2 additionally confirms `gh_update_script` preserves
user-customized input-pin metadata (name, nickname, description) on the unlocked edit path —
PR1 is clean and Task 6 is not required.
