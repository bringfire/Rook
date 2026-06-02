# GH Locked-Solver Crash — PR1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the instant Rhino crash when `gh_set_script` / `gh_update_script` runs against a locked Grasshopper canvas, by introducing a durable shared safe-solve policy (never synchronous recompute) and proving it on the `SetScript` path.

**Architecture:** A pure decision function (`GhSolvePolicy.Decide`) and a shared reflected solver-state inspector (`GhSolverState.Inspect`) feed a thin reflection helper on the GH handler (`RequestPostMutationSolve`) that marks objects dirty with `ExpireSolution(false)` and schedules at most one async `ScheduleSolution(delay ≥ 1)` — only when a solve is wanted and the solver is enabled. `gh_status` surfaces solver state (without gating edits); the Python `gh_update_script` wrapper honors deferral and waits for the scheduled solve to *settle* instead of assuming a synchronous solve completed.

**Tech Stack:** C# (.NET, reflection over Grasshopper), xUnit (`src/Rook.Tests`), Python 3 (`mcp_server`), pytest + `requires_rhino` live suite.

**Spec:** `docs/superpowers/specs/2026-06-02-gh-locked-solver-crash-design.md` (read it first — this plan implements PR1 of the two-PR rollout in §12).

**Commit policy (from spec review):** Do **not** commit on the current `codex/phase-2c-rookbim-diagnostics-design` branch. When ready, branch `fix/gh-locked-solver-crash` (off `main`, handling the unrelated dirty `BimHandlerTests.cs` per the spec note) and stage **only** this plan, the spec, and the implementation/test files below — never `BimHandlerTests.cs`, never `2026-06-02-rook-rhinomcp-architecture-assessment.md`.

**Test commands (reference):**
- C# unit: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~SolvePolicy"` (broaden filter as tasks add classes).
- Python unit: from repo root — `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests -m "not requires_rhino" -v`
- Python live: with Rhino+GH open and Rook deployed — `mcp_server/.venv/Scripts/python -m pytest -m requires_rhino mcp_server/tests/test_gh_locked_solver_live.py -v`
- Deploy C# companion for live tests: `cmd /c scripts\deploy-native.bat` (per repo convention; restart Rhino after).

---

## Task 1: Live probe (throwaway document) — resolve U1 / U2 / U3

**Not a code task.** Run on a **throwaway Grasshopper document** in a live Rhino session — never the user's working file. U1/U3 are read-only; **U2 mutates** (calls `SetSource`), so confirm a throwaway doc before running it. Record answers at the top of the spec (a `## Probe Results (2026-06-02)` section) and adjust Tasks 3/6/9 accordingly.

- [ ] **Step 1: Confirm a throwaway GH document is active** (ask the user; do not run U2 against a real file).

- [ ] **Step 2: U1 — lock-state mapping (read-only).** Run via `rhino_execute`, once with the solver **unlocked** and once **locked** (Solution → Lock Solver):

```python
import Grasshopper as gh
import System.Reflection as R
doc = gh.Instances.ActiveCanvas.Document
T = doc.GetType()
def rd(name, static=False):
    try:
        flags = R.BindingFlags.Public | (R.BindingFlags.Static if static else R.BindingFlags.Instance)
        p = T.GetProperty(name, flags)
        return "<none>" if p is None else p.GetValue(None if static else doc)
    except Exception as e:
        return "ERR:%s" % e
print("EnableSolutions(static)=", rd("EnableSolutions", True))
print("Enabled(instance)   =", rd("Enabled"))
print("SolutionState       =", rd("SolutionState"))
print("SolutionDepth       =", rd("SolutionDepth"))
```

Expected: at least one of `EnableSolutions` / `Enabled` flips `True`→`False` when locked. Record which one(s). (Implementation in Task 3 reads BOTH and ANDs them, so it is correct as long as ≥1 flips — U1 only has to confirm that ≥1 does. If neither flips, record the real lock member here and add it to Task 3's read list.)

- [ ] **Step 3: U1b — confirm async schedule while locked is safe.** With the solver **locked**, run:

```python
import Grasshopper as gh
doc = gh.Instances.ActiveCanvas.Document
doc.ScheduleSolution(50)   # must NOT crash and must NOT force a recompute while locked
print("scheduled ok; state=", doc.SolutionState)
```

Expected: returns normally, no crash, solver stays locked. If it crashes/forces, flip Task 3's predicate to fail-closed (record this).

- [ ] **Step 4: U2 — pin-description clobber timing (MUTATES — throwaway only).** On a throwaway C#/Python script component (capture its GUID first via `gh_snapshot`), read each input/output param `Description` at three points: before `SetSource`, after `SetSource` (no solve), and after `doc.ScheduleSolution(1)` settles. Record where descriptions reset:
  - reset already at "after SetSource" → **immediate restore suffices; skip Task 6.**
  - intact after SetSource but reset after the solve → **Task 6 (one-shot SolutionEnd) is required.**

- [ ] **Step 5: U3 — solve-completion marker (read-only).** Check whether `GH_Document` exposes a monotonic solve counter via reflection (candidates to print: members containing "Solution" / "Counter"):

```python
import Grasshopper as gh
doc = gh.Instances.ActiveCanvas.Document
for m in doc.GetType().GetProperties():
    if any(k in m.Name for k in ("Solution","Counter","Stamp","Version")):
        try: print(m.Name, "=", m.GetValue(doc))
        except Exception as e: print(m.Name, "ERR", e)
```

If a reliable monotonic marker exists, Task 9 uses it (best); otherwise Task 9 uses the edge-detected settle (acceptable). Record the choice.

- [ ] **Step 6: Write a `## Probe Results (2026-06-02)` section into the spec** with the U1/U1b/U2/U3 answers. (Do not commit yet; commit happens with the implementation files per the commit policy above.)

---

## Task 2: Pure decision function + outcome type (C#, unit-tested)

**Files:**
- Create: `src/Rook/Handlers/GhSolvePolicy.cs`
- Test: `src/Rook.Tests/Handlers/GhSolvePolicyTests.cs`

- [ ] **Step 1: Write the failing tests** (the §5.3 matrix):

```csharp
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class GhSolvePolicyTests
    {
        [Fact]
        public void KnownEnabled_RequestSolve_SchedulesAndDoesNotDefer()
        {
            var o = GhSolvePolicy.Decide(requestSolve: true, solverEnabled: true, solverStateKnown: true);
            Assert.True(o.SolveScheduled);
            Assert.False(o.SolverLocked);
            Assert.True(o.SolverStateKnown);
            Assert.False(o.VerificationDeferred);
        }

        [Fact]
        public void KnownLocked_RequestSolve_DoesNotScheduleAndDefers()
        {
            var o = GhSolvePolicy.Decide(requestSolve: true, solverEnabled: false, solverStateKnown: true);
            Assert.False(o.SolveScheduled);
            Assert.True(o.SolverLocked);
            Assert.True(o.SolverStateKnown);
            Assert.True(o.VerificationDeferred);
            Assert.NotEmpty(o.Warnings);
        }

        [Fact]
        public void Unknown_RequestSolve_SchedulesButDefersConservatively()
        {
            var o = GhSolvePolicy.Decide(requestSolve: true, solverEnabled: true, solverStateKnown: false);
            Assert.True(o.SolveScheduled);
            Assert.False(o.SolverLocked);
            Assert.False(o.SolverStateKnown);
            Assert.True(o.VerificationDeferred);  // can't confirm the solve ran
            Assert.NotEmpty(o.Warnings);
        }

        [Fact]
        public void NoRequestSolve_NeverSchedules()
        {
            var o = GhSolvePolicy.Decide(requestSolve: false, solverEnabled: true, solverStateKnown: true);
            Assert.False(o.SolveScheduled);
            Assert.False(o.VerificationDeferred);
        }
    }
}
```

- [ ] **Step 2: Run, verify it fails to compile** (`GhSolvePolicy` undefined):

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~GhSolvePolicyTests"`
Expected: build error — `GhSolvePolicy` does not exist.

- [ ] **Step 3: Implement the outcome type and pure decision:**

```csharp
using System;

namespace Rook.Handlers
{
    /// <summary>Result of the shared post-mutation safe-solve policy. See
    /// docs/superpowers/specs/2026-06-02-gh-locked-solver-crash-design.md §5.
    /// Internal — visible to Rook.Tests via InternalsVisibleTo (Rook.csproj:25).</summary>
    internal readonly struct GhSolveOutcome
    {
        public bool SolveScheduled { get; init; }
        public bool SolverLocked { get; init; }
        public bool SolverStateKnown { get; init; }
        public bool VerificationDeferred { get; init; }
        public string[] Warnings { get; init; }
    }

    /// <summary>Pure decision for post-mutation solve behavior. No Grasshopper
    /// dependency — fully unit-testable. The safety invariant (never a synchronous
    /// recompute) lives in the caller; this only decides whether to SCHEDULE.</summary>
    internal static class GhSolvePolicy
    {
        public static GhSolveOutcome Decide(bool requestSolve, bool solverEnabled, bool solverStateKnown)
        {
            if (!requestSolve)
            {
                return new GhSolveOutcome
                {
                    SolveScheduled = false,
                    SolverLocked = solverStateKnown && !solverEnabled,
                    SolverStateKnown = solverStateKnown,
                    VerificationDeferred = false,
                    Warnings = Array.Empty<string>(),
                };
            }

            if (!solverStateKnown)
            {
                return new GhSolveOutcome
                {
                    SolveScheduled = true,            // safe async; invariant guarantees no crash
                    SolverLocked = false,
                    SolverStateKnown = false,
                    VerificationDeferred = true,      // cannot confirm the solve ran
                    Warnings = new[] { "Grasshopper solver state could not be inspected; used safe async scheduling, verification not guaranteed." },
                };
            }

            if (solverEnabled)
            {
                return new GhSolveOutcome
                {
                    SolveScheduled = true,
                    SolverLocked = false,
                    SolverStateKnown = true,
                    VerificationDeferred = false,
                    Warnings = Array.Empty<string>(),
                };
            }

            return new GhSolveOutcome
            {
                SolveScheduled = false,
                SolverLocked = true,
                SolverStateKnown = true,
                VerificationDeferred = true,
                Warnings = new[] { "Grasshopper solver is locked; recompute deferred until unlock." },
            };
        }
    }
}
```

- [ ] **Step 4: Run tests, verify pass:**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~GhSolvePolicyTests"`
Expected: 4 passed.

- [ ] **Step 5: Commit** (only after the branch exists per commit policy):

```bash
git add src/Rook/Handlers/GhSolvePolicy.cs src/Rook.Tests/Handlers/GhSolvePolicyTests.cs
git commit -m "feat(gh): pure safe-solve decision policy + outcome type"
```

---

## Task 3: Shared solver-state inspector (C#, reflection, unit-tested for fail-open)

**Files:**
- Create: `src/Rook/InternalBridge/GhSolverState.cs`
- Test: `src/Rook.Tests/InternalBridge/GhSolverStateTests.cs`

- [ ] **Step 1: Write the failing test** (fail-open on a non-GH object — no Rhino needed):

```csharp
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class GhSolverStateTests
    {
        private sealed class FakeEnabledDoc { public bool Enabled { get; set; } = true; }

        [Fact]
        public void Inspect_PlainObject_IsUnknownAndFailsOpen()
        {
            var s = GhSolverState.Inspect(new object());
            Assert.False(s.Known);          // nothing readable
            Assert.True(s.Enabled ?? true); // fail-open
        }

        [Fact]
        public void Inspect_ObjectWithEnabledFalse_IsKnownAndDisabled()
        {
            var s = GhSolverState.Inspect(new FakeEnabledDoc { Enabled = false });
            Assert.True(s.Known);
            Assert.False(s.Enabled ?? true);
        }
    }
}
```

- [ ] **Step 2: Run, verify it fails** (`GhSolverState` undefined):

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~GhSolverStateTests"`
Expected: build error.

- [ ] **Step 3: Implement the inspector** (reads static `EnableSolutions` AND instance `Enabled`; ANDs readable flags; `SolutionState` is telemetry only — never part of the enabled decision). Adjust the read list only if Task 1/U1 found a different lock member.

```csharp
using System.Reflection;

namespace Rook.InternalBridge
{
    /// <summary>Reflected Grasshopper solver state, shared by the GH handler's
    /// safe-solve policy and gh_status. SolutionState is telemetry only and MUST
    /// NOT influence the enabled decision. See spec §5.4 / §7.
    /// Internal — visible to Rook.Tests via InternalsVisibleTo (Rook.csproj:25).</summary>
    internal static class GhSolverState
    {
        public readonly struct Result
        {
            public bool? Enabled { get; init; }     // null when unknown
            public bool Known { get; init; }
            public string? SolutionState { get; init; }
        }

        public static Result Inspect(object document)
        {
            bool known = false;
            bool enabled = true; // fail-open
            string? solutionState = null;
            if (document == null)
                return new Result { Enabled = null, Known = false, SolutionState = null };

            var t = document.GetType();
            try
            {
                var enableSolutions = t.GetProperty("EnableSolutions", BindingFlags.Public | BindingFlags.Static);
                if (enableSolutions?.GetValue(null) is bool es) { enabled &= es; known = true; }
            }
            catch { /* keep fail-open */ }
            try
            {
                var enabledProp = t.GetProperty("Enabled", BindingFlags.Public | BindingFlags.Instance);
                if (enabledProp?.GetValue(document) is bool en) { enabled &= en; known = true; }
            }
            catch { /* keep fail-open */ }
            try
            {
                var state = t.GetProperty("SolutionState", BindingFlags.Public | BindingFlags.Instance);
                solutionState = state?.GetValue(document)?.ToString();
            }
            catch { /* telemetry only */ }

            return new Result { Enabled = known ? enabled : (bool?)null, Known = known, SolutionState = solutionState };
        }
    }
}
```

- [ ] **Step 4: Run tests, verify pass.**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~GhSolverStateTests"`
Expected: 2 passed.

- [ ] **Step 5: Commit:**

```bash
git add src/Rook/InternalBridge/GhSolverState.cs src/Rook.Tests/InternalBridge/GhSolverStateTests.cs
git commit -m "feat(gh): shared reflected solver-state inspector (fail-open)"
```

---

## Task 4: The safe-solve helper on the handler (C#, reflection wiring, unit-tested with fakes)

**Files:**
- Create: `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs` (partial of `GrasshopperHandler`)
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs:17` (add the `partial` keyword)
- Test: `src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs`

> **Accessibility:** `GhSolveOutcome`, `GhSolvePolicy`, `GhSolverState`, and `RequestPostMutationSolve` are all `internal`. `InternalsVisibleTo("Rook.Tests")` already exists (`src/Rook/Rook.csproj:25`), so the tests see them — **no csproj edit**.

- [ ] **Step 1: Make `GrasshopperHandler` partial.** In `src/Rook/Handlers/GrasshopperHandler.cs:17`, change `public class GrasshopperHandler` to `public partial class GrasshopperHandler` (behavior-neutral; required so the `.SolvePolicy.cs` partial compiles into the same class).

- [ ] **Step 2: Write the failing test** (fakes exercise the reflection wiring without Rhino):

```csharp
using System.Collections.Generic;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class RequestPostMutationSolveTests
    {
        private sealed class FakeObj
        {
            public List<bool> Expire = new();
            public void ExpireSolution(bool recompute) => Expire.Add(recompute);
        }
        private sealed class FakeDoc
        {
            public bool Enabled { get; set; } = true;
            public List<int> Scheduled = new();
            public void ScheduleSolution(int ms) => Scheduled.Add(ms);
        }

        [Fact]
        public void Enabled_MarksDirtyFalse_AndSchedulesOnce()
        {
            var h = new GrasshopperHandler();
            var obj = new FakeObj();
            var doc = new FakeDoc { Enabled = true };

            var outcome = h.RequestPostMutationSolve(doc, obj, requestSolve: true);

            Assert.Equal(new[] { false }, obj.Expire);   // never true (no sync recompute)
            Assert.Single(doc.Scheduled);
            Assert.True(doc.Scheduled[0] >= 1);           // never 0
            Assert.True(outcome.SolveScheduled);
            Assert.False(outcome.VerificationDeferred);
        }

        [Fact]
        public void Locked_MarksDirtyFalse_AndDoesNotSchedule()
        {
            var h = new GrasshopperHandler();
            var obj = new FakeObj();
            var doc = new FakeDoc { Enabled = false };

            var outcome = h.RequestPostMutationSolve(doc, obj, requestSolve: true);

            Assert.Equal(new[] { false }, obj.Expire);
            Assert.Empty(doc.Scheduled);                  // suppressed while locked
            Assert.True(outcome.SolverLocked);
            Assert.True(outcome.VerificationDeferred);
        }

        private sealed class FakeDocNoSchedule { public bool Enabled { get; set; } = true; }

        [Fact]
        public void ScheduleMethodMissing_DoesNotClaimScheduled()
        {
            var h = new GrasshopperHandler();
            var obj = new FakeObj();
            var doc = new FakeDocNoSchedule();   // enabled, but NO ScheduleSolution method

            var outcome = h.RequestPostMutationSolve(doc, obj, requestSolve: true);

            Assert.Equal(new[] { false }, obj.Expire);
            Assert.False(outcome.SolveScheduled);   // reflection miss corrected — never over-claim scheduling
            Assert.True(outcome.VerificationDeferred);
        }
    }
}
```

> `GrasshopperHandler` is constructable with `new GrasshopperHandler()` — it has no explicit constructor and its `_bridgeCore` is a field initializer (`GrasshopperHandler.cs:19`), so the implicit parameterless ctor suffices for these tests.

- [ ] **Step 3: Run, verify it fails** (`RequestPostMutationSolve` undefined):

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~RequestPostMutationSolveTests"`
Expected: build error.

- [ ] **Step 4: Implement the partial helper:**

```csharp
using System.Collections.Generic;
using System.Reflection;
using Rook.InternalBridge;

namespace Rook.Handlers
{
    public partial class GrasshopperHandler
    {
        // Single-object form — the call shape used by ~all mutation sites.
        internal GhSolveOutcome RequestPostMutationSolve(object document, object dirtyObject, bool requestSolve, int delayMs = 1)
            => RequestPostMutationSolve(document, new[] { dirtyObject }, requestSolve, delayMs);

        // Batch form — for multi-target mutations (e.g. gh_edit).
        internal GhSolveOutcome RequestPostMutationSolve(object document, IReadOnlyList<object> dirtyObjects, bool requestSolve, int delayMs = 1)
        {
            // 1. Mark each dirty WITHOUT recompute. This is the safety invariant: never ExpireSolution(true).
            foreach (var obj in dirtyObjects)
            {
                if (obj == null) continue;
                var expire = obj.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
                expire?.Invoke(obj, new object[] { false });
            }

            // 2. Inspect solver state (shared inspector).
            var state = GhSolverState.Inspect(document);

            // 3. Decide (pure).
            var outcome = GhSolvePolicy.Decide(requestSolve, state.Enabled ?? true, state.Known);

            // 4. Schedule at most one async solution, never delay 0. If reflected
            //    ScheduleSolution is missing or throws, the solve did NOT happen —
            //    correct the outcome so callers never over-claim scheduling.
            if (outcome.SolveScheduled)
            {
                if (delayMs < 1) delayMs = 1;
                if (!TrySchedule(document, delayMs))
                {
                    outcome = new GhSolveOutcome
                    {
                        SolveScheduled = false,
                        SolverLocked = outcome.SolverLocked,
                        SolverStateKnown = outcome.SolverStateKnown,
                        VerificationDeferred = true,
                        Warnings = AppendWarning(outcome.Warnings,
                            "ScheduleSolution was unavailable; solve not scheduled, verification deferred."),
                    };
                }
            }

            return outcome;
        }

        private static bool TrySchedule(object document, int delayMs)
        {
            try
            {
                var schedule = document.GetType().GetMethod("ScheduleSolution", new[] { typeof(int) });
                if (schedule == null) return false;
                schedule.Invoke(document, new object[] { delayMs });
                return true;
            }
            catch { return false; }
        }

        private static string[] AppendWarning(string[] existing, string warning)
        {
            var list = new System.Collections.Generic.List<string>(existing ?? System.Array.Empty<string>());
            list.Add(warning);
            return list.ToArray();
        }
    }
}
```

- [ ] **Step 5: Run tests, verify pass.**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~RequestPostMutationSolveTests"`
Expected: 2 passed.

- [ ] **Step 6: Commit:**

```bash
git add src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs src/Rook/Handlers/GrasshopperHandler.cs src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs
git commit -m "feat(gh): safe-solve helper on GH handler (ExpireSolution(false)+async schedule)"
```

---

## Task 5: Migrate `SetScript` onto the helper (C#)

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs` (the `SetScript` WRITE branch, ~lines 797-847)

- [ ] **Step 1: Replace the synchronous expire** at lines 797-799. Remove:

```csharp
// Expire solution to trigger update
var expireMethod = obj.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
expireMethod?.Invoke(obj, new object[] { true });
```

with:

```csharp
// Safe-solve policy: mark dirty (no sync recompute) + async schedule when enabled.
// NEVER ExpireSolution(true) here — that re-enters the solver and crashes a locked canvas.
var solveOutcome = RequestPostMutationSolve(gh.Document!, obj, requestSolve: true);
```

- [ ] **Step 2: Switch the canvas refresh to repaint-only** at line 830 so the helper is the single scheduler. Change:

```csharp
RefreshCanvas(gh.Canvas!);
```
to:
```csharp
RefreshCanvas(gh.Canvas!, scheduleSolution: false);
```

- [ ] **Step 3: Fold the outcome into the response** (the `Data = new { ... }` at lines 832-847). Add these members to the anonymous object (snake_case so the Python contract is naming-policy independent):

```csharp
            solve_scheduled = solveOutcome.SolveScheduled,
            solver_locked = solveOutcome.SolverLocked,
            solver_state_known = solveOutcome.SolverStateKnown,
            verification_deferred = solveOutcome.VerificationDeferred,
            solve_warnings = solveOutcome.Warnings,
```

(The existing pin-description restore at lines 801-828 stays exactly where it is — that is the "always immediate restore" baseline from spec §6. Task 6 adds the conditional one-shot only if Task 1/U2 proved the solve re-clobbers.)

- [ ] **Step 4: Build the companion** to confirm it compiles.

Run: `cmd /c scripts\deploy-native.bat`
Expected: build succeeds (deploy step may require Rhino closed; a plain `dotnet build src/Rook/Rook.csproj` is sufficient to verify compilation).

- [ ] **Step 5: Commit:**

```bash
git add src/Rook/Handlers/GrasshopperHandler.cs
git commit -m "fix(gh): SetScript uses safe-solve policy instead of synchronous ExpireSolution(true)"
```

---

## Task 6: (CONDITIONAL on U2) One-shot post-solution pin-description restore

**Only implement if Task 1/U2 showed the scheduled *solve* (not `SetSource`) re-clobbers descriptions.** If immediate restore sufficed, **skip this task** and note it in the spec's Probe Results.

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs` (add the one-shot helper)
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs` (`SetScript` arms it on the scheduled-solve path only)

- [ ] **Step 1: Add a leak-proof one-shot restore helper** (lifecycle rules from spec §6.1): armed only when `solveOutcome.SolveScheduled` is true; fires once then unsubscribes; validity-checks the component; self-cancels on a bounded timeout.

```csharp
using System;
using System.Reflection;

namespace Rook.Handlers
{
    public partial class GrasshopperHandler
    {
        /// Arms a one-shot GH_Document.SolutionEnd handler that re-applies the captured
        /// pin descriptions to `component` after the NEXT solution, then unsubscribes.
        /// Leak-proof: fires once, validity-checks the component, and self-cancels after timeoutMs.
        internal void ArmOneShotPinRestore(object document, object component, Action reapply, int timeoutMs = 5000)
        {
            var evt = document.GetType().GetEvent("SolutionEnd");
            if (evt == null) { reapply(); return; } // no event surface → best-effort immediate

            EventHandler? handler = null;
            var armed = true;
            void Disarm()
            {
                if (!armed) return;
                armed = false;
                try { if (handler != null) evt.RemoveEventHandler(document, ConvertDelegate(evt, handler)); } catch { }
            }
            handler = (s, e) =>
            {
                if (!armed) return;
                try { if (ComponentStillInDocument(document, component)) reapply(); }
                finally { Disarm(); }
            };
            evt.AddEventHandler(document, ConvertDelegate(evt, handler));

            // Bounded self-cancel so a never-completing solve cannot strand the handler.
            Rhino.RhinoApp.SetTimeout(timeoutMs / 1000.0, _ => Disarm());
        }

        private static Delegate ConvertDelegate(EventInfo evt, EventHandler handler)
            => Delegate.CreateDelegate(evt.EventHandlerType!, handler.Target, handler.Method);

        private bool ComponentStillInDocument(object document, object component)
        {
            try
            {
                var objects = document.GetType().GetProperty("Objects")?.GetValue(document) as System.Collections.IEnumerable;
                if (objects == null) return false;
                foreach (var o in objects) if (ReferenceEquals(o, component)) return true;
                return false;
            }
            catch { return false; }
        }
    }
}
```

> `Rhino.RhinoApp.SetTimeout` exists in RhinoCommon 8. If U1's environment lacks it, substitute an equivalent one-shot UI-thread timer; the bound is what matters. Verify the exact `SolutionEnd` delegate signature during Task 1/U2 and adjust `ConvertDelegate` if the runtime rejects the conversion.

- [ ] **Step 2: Arm it in `SetScript`** only on the scheduled path. After the pin-restore block, before `return`:

```csharp
            if (solveOutcome.SolveScheduled)
            {
                var componentForRestore = obj;
                ArmOneShotPinRestore(gh.Document!, componentForRestore, () =>
                {
                    var warns = new System.Collections.Generic.List<string>();
                    var pProp = componentForRestore.GetType().GetProperty("Params")?.GetValue(componentForRestore);
                    if (pProp != null)
                    {
                        ApplyPinDescriptions(pProp.GetType().GetProperty("Input")?.GetValue(pProp), savedInputDescriptions, "input", warns, out _, out _);
                        ApplyPinDescriptions(pProp.GetType().GetProperty("Output")?.GetValue(pProp), savedOutputDescriptions, "output", warns, out _, out _, skipFirstN: 1);
                    }
                });
            }
```

- [ ] **Step 3: Build, verify compile.** Run: `dotnet build src/Rook/Rook.csproj` — Expected: success.

- [ ] **Step 4: Commit:**

```bash
git add src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs src/Rook/Handlers/GrasshopperHandler.cs
git commit -m "fix(gh): one-shot post-solution pin-description restore for deferred solve"
```

---

## Task 7: Surface solver state in `gh_status` (C#)

**Files:**
- Modify: `src/Rook/InternalBridge/GrasshopperCore.cs` (`GrasshopperStatusDto` ~line 450; `ObserveStatus`/status builder ~line 115)
- Test: `src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs`

- [ ] **Step 1: Write the failing test** (the DTO carries the new fields and `ReadyForEdit` is independent of solver lock):

```csharp
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class GrasshopperStatusDtoTests
    {
        [Fact]
        public void Dto_CarriesSolverFields_AndReadyForEditIsIndependent()
        {
            var dto = new GrasshopperStatusDto
            {
                ReadyForEdit = true,
                SolverEnabled = false,      // locked
                SolverStateKnown = true,
                SolutionState = "Off",
            };
            Assert.True(dto.ReadyForEdit);  // editing still allowed while locked
            Assert.False(dto.SolverEnabled);
            Assert.True(dto.SolverStateKnown);
            Assert.Equal("Off", dto.SolutionState);
        }
    }
}
```

- [ ] **Step 2: Run, verify it fails** (members undefined):

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~GrasshopperStatusDtoTests"`
Expected: build error.

- [ ] **Step 3: Add the fields** to `GrasshopperStatusDto` (after `ReadyForEdit`, line 461):

```csharp
        public bool? SolverEnabled { get; set; }
        public bool SolverStateKnown { get; set; }
        public string? SolutionState { get; set; }
```

- [ ] **Step 4: Populate them** in the status builder (where the DTO is constructed, ~line 115). Add, before `return new GrasshopperStatusDto`:

```csharp
            var solver = document != null
                ? GhSolverState.Inspect(document)
                : default;
```

and inside the initializer (do **not** modify the existing `ReadyForEdit` line):

```csharp
                SolverEnabled = solver.Enabled,
                SolverStateKnown = solver.Known,
                SolutionState = solver.SolutionState,
```

- [ ] **Step 5: Run tests, verify pass.**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~GrasshopperStatusDtoTests"`
Expected: 1 passed. Also re-run the full C# suite to confirm no regression: `dotnet test src/Rook.Tests/Rook.Tests.csproj`.

- [ ] **Step 6: Commit:**

```bash
git add src/Rook/InternalBridge/GrasshopperCore.cs src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs
git commit -m "feat(gh): surface solver state in gh_status (ReadyForEdit unchanged)"
```

---

## Task 8: Python `gh_update_script` — honor deferral (unit-tested)

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`_execute_gh_update_script` ~line 1800; add a pure helper near it)
- Test: `mcp_server/tests/test_gh_update_script_defer.py`

- [ ] **Step 1: Write the failing unit test:**

```python
from rook.server import _gh_update_script_should_defer


def test_defer_true_when_solver_locked():
    deferred, flags = _gh_update_script_should_defer(
        {"verification_deferred": True, "solver_locked": True, "solver_state_known": True}
    )
    assert deferred is True
    assert flags["solver_locked"] is True


def test_defer_false_when_enabled_and_scheduled():
    deferred, flags = _gh_update_script_should_defer(
        {"verification_deferred": False, "solver_locked": False, "solver_state_known": True, "solve_scheduled": True}
    )
    assert deferred is False


def test_defer_handles_missing_flags():
    deferred, flags = _gh_update_script_should_defer({})
    assert deferred is False
    assert flags == {}
```

- [ ] **Step 2: Run, verify it fails** (function undefined):

Run: `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests/test_gh_update_script_defer.py -v`
Expected: ImportError / failure.

- [ ] **Step 3: Implement the pure helper** (place just above `_execute_gh_update_script`):

```python
def _gh_update_script_should_defer(write_data: Any) -> tuple[bool, dict[str, Any]]:
    """Read the safe-solve flags off the /gh/script write response. Returns
    (deferred, flags). Deferred => no fresh solve ran, so the caller must NOT
    claim a compile/error verification."""
    flags: dict[str, Any] = {}
    if isinstance(write_data, dict):
        for key in ("verification_deferred", "solver_locked", "solver_state_known", "solve_scheduled"):
            if key in write_data:
                flags[key] = write_data[key]
    return bool(flags.get("verification_deferred")), flags
```

- [ ] **Step 4: Wire it into `_execute_gh_update_script`.** Replace the `if bool(arguments.get("check_errors", True)):` block (lines ~1867-1894) so deferral short-circuits the stale error check:

```python
        deferred, solver_flags = _gh_update_script_should_defer(write_data)
        if deferred:
            error_summary = _empty_gh_update_script_error_summary()
            error_summary["verification_deferred"] = True   # stays boolean
            error_summary["verification_note"] = (
                "Grasshopper solver is locked or its state is unknown; the script source was "
                "written but not recompiled. Unlock the solver and run gh_solve to verify."
            )
        elif bool(arguments.get("check_errors", True)):
            await _await_gh_solve_settle(port, scheduled_delay_ms=50)   # Task 9
            error_summary = _summarize_gh_update_script_errors(
                await call_rhino("/gh/errors", "GET", {}, port=port),
                resolved_guid,
            )
            # ... (keep the existing short-id snapshot-fallback block unchanged) ...
        else:
            error_summary = _empty_gh_update_script_error_summary()
```

Then merge `solver_flags` into the returned `data` dict (after the `**error_summary` line ~1905):

```python
        data.update(solver_flags)
```

> Until Task 9 lands, stub `_await_gh_solve_settle` as `async def _await_gh_solve_settle(port, scheduled_delay_ms=50): await asyncio.sleep(0.3)` so this task is independently runnable, then replace it in Task 9.

- [ ] **Step 5: Run unit tests, verify pass.**

Run: `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests/test_gh_update_script_defer.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit:**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_gh_update_script_defer.py
git commit -m "fix(gh): gh_update_script honors solver-locked deferral instead of stale error check"
```

---

## Task 9: Python — bounded best-effort settle (LANDED AS FLOOR)

> **History (non-executable):** an edge-detected busy->idle `/gh/status` poll was implemented
> and reverted (commit `c8a17d2`). Trivial scripts solve instantly, so there is no observable
> "busy" window; the poll burned the full timeout on the common fast path and broke 5
> `gh_update_script` contract tests (unexpected `/gh/status` route). PR1 ships the bounded
> best-effort floor below instead.

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`_await_gh_solve_settle`)
- `mcp_server/tests/test_gh_solve_settle.py` (the edge-detector test) was **removed**.

**Landed implementation.** A fixed delay has nothing to unit-test; its behavior is exercised
by the live regression in Task 10.

```python
async def _await_gh_solve_settle(port: int, scheduled_delay_ms: int = 50) -> None:
    """Best-effort bounded wait for a scheduled GH solve before reading /gh/errors.
    PR1 uses a fixed delay; a precise wait needs a real solve-completion marker (U3),
    so NON-DEFERRED error checks are best-effort until then."""
    await asyncio.sleep(0.3)
```

Called from `_execute_gh_update_script`'s non-deferred `elif check_errors` branch (Task 8),
in place of the prior inline `asyncio.sleep(0.3)`. No new route is introduced, so the 5
`gh_update_script` contract tests stay green.

**Follow-up (post-U3, NOT PR1):** if the U3 probe finds a monotonic solve-completion marker on
`GH_Document`, replace the fixed delay with — read the marker before the write, then poll
`gh_status` until it advances (bounded timeout). Precise, race-free verification.

---

## Task 10: Live `requires_rhino` regression (Python)

**Files:**
- Create: `mcp_server/tests/test_gh_locked_solver_live.py`

**Preconditions:** Rhino + Grasshopper open, Rook deployed (`cmd /c scripts\deploy-native.bat`, restart Rhino), a throwaway GH document active. This suite locks the solver via `rhino_execute`; **if run against UNFIXED code it will crash Rhino** — that is the regression it guards. Run only in a throwaway live session.

- [ ] **Step 1: Write the live tests:**

```python
"""Live-Rhino regression for the locked-solver crash. requires_rhino; throwaway session only.

Run: pytest -m requires_rhino mcp_server/tests/test_gh_locked_solver_live.py
"""
from __future__ import annotations
from typing import Any
import pytest
from .conftest import _is_error

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

# Lock/unlock the solver via the member U1 (Task 1) confirmed tracks "Lock Solver".
# Set it through .NET reflection (mirroring the U1 probe) — Python attribute assignment
# (e.g. `type(doc).EnableSolutions = ...`) does NOT reliably set a reflected/static .NET
# property. Fill _LOCK_MEMBER / _LOCK_STATIC from the U1 result before running; the assert
# fails LOUDLY if the member is wrong, so this test cannot pass without actually locking.
_LOCK_MEMBER = "EnableSolutions"   # from U1 — e.g. "EnableSolutions" (static) or "Enabled" (instance)
_LOCK_STATIC = True                # True if static (EnableSolutions); False if instance (Enabled)

_LOCK = (
    "import Grasshopper as gh\n"
    "import System.Reflection as R\n"
    "doc = gh.Instances.ActiveCanvas.Document\n"
    "T = doc.GetType()\n"
    "flags = R.BindingFlags.Public | (R.BindingFlags.Static if {static} else R.BindingFlags.Instance)\n"
    "p = T.GetProperty('{member}', flags)\n"
    "assert p is not None and p.CanWrite, 'lock member {member} missing or read-only'\n"
    "p.SetValue(None if {static} else doc, {val})\n"
)


async def _set_solver(enabled: bool) -> None:
    from rook.server import _mcp_tool_executor
    code = _LOCK.format(
        member=_LOCK_MEMBER,
        static="True" if _LOCK_STATIC else "False",
        val="True" if enabled else "False",
    )
    await _mcp_tool_executor("rhino_execute", {"code": code})


async def _make_script() -> str:
    from rook.server import _mcp_tool_executor
    r = await _mcp_tool_executor("gh_create_script", {
        "language": "csharp", "code": "A = Convert.ToDouble(R);",
        "pins_in": [{"name": "R", "type": "double"}], "pins_out": [{"name": "A", "type": "double"}],
        "name": "LockedSolverLive", "x": 600, "y": 360,
    })
    if _is_error(r):
        pytest.skip(f"gh_create_script unavailable: {r!r}")
    d = r.get("data", r)
    g = d.get("guid") or d.get("Guid") or d.get("component_guid")
    assert g, f"no guid: {r!r}"
    return g


async def test_update_script_on_locked_canvas_does_not_crash():
    from rook.server import _mcp_tool_executor
    guid = await _make_script()
    try:
        await _set_solver(False)  # LOCK
        result = await _mcp_tool_executor("gh_update_script", {
            "guid": guid, "language": "csharp", "code": "A = Convert.ToDouble(R) * 3.0;",
        })
        assert isinstance(result, dict)
        data = result.get("data", result)
        # Did NOT crash, and reports deferral:
        assert data.get("verification_deferred")
        assert data.get("solver_locked") in (True, None)  # locked or unknown, never a claimed clean check
        # Source round-tripped:
        read_back = await _mcp_tool_executor("gh_set_script", {"guid": guid})
        src = (read_back.get("data") or {}).get("Script") or (read_back.get("data") or {}).get("script") or ""
        assert "* 3.0" in src
        # Ping confirms Rhino is still alive:
        ping = await _mcp_tool_executor("rhino_ping", {})
        assert not _is_error(ping)
    finally:
        await _set_solver(True)  # always restore unlocked


async def test_update_script_on_unlocked_canvas_compiles_and_recomputes():
    from rook.server import _mcp_tool_executor
    guid = await _make_script()
    await _set_solver(True)  # ensure unlocked
    result = await _mcp_tool_executor("gh_update_script", {
        "guid": guid, "language": "csharp", "code": "A = Convert.ToDouble(R) + 1.0;",
    })
    data = result.get("data", result)
    assert data.get("verification_deferred") in (None, False, "")  # a real check happened
    assert "component_errors" in data
```

- [ ] **Step 2: Run (throwaway live session):**

Run: `mcp_server/.venv/Scripts/python -m pytest -m requires_rhino mcp_server/tests/test_gh_locked_solver_live.py -v`
Expected: 2 passed; Rhino still responsive afterward. (Preflight `rhino_ping` first per the test skill.)

- [ ] **Step 3: Commit:**

```bash
git add mcp_server/tests/test_gh_locked_solver_live.py
git commit -m "test(gh): live requires_rhino regression for locked-solver crash"
```

---

## Task 11: Static guard against re-introduction (C#)

**Files:**
- Test: `src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs`

- [ ] **Step 1: Write the guard test** (source-scans `SetScript` for the banned synchronous expire):

```csharp
using System.IO;
using System.Linq;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class NoSyncExpireInScriptPathTests
    {
        [Fact]
        public void SetScript_DoesNotCallExpireSolutionTrue()
        {
            // Locate the handler source relative to the test assembly.
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
                dir = dir.Parent;
            Assert.NotNull(dir);
            var src = File.ReadAllText(Path.Combine(dir!.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

            // Extract the SetScript method body and assert it does not force a synchronous solve.
            var start = src.IndexOf("public ApiResponse SetScript(");
            Assert.True(start >= 0, "SetScript not found");
            var end = src.IndexOf("\n        private", start);  // next member
            var body = end > start ? src[start..end] : src[start..];
            // Normalize ALL whitespace on both sides so the match actually works.
            var normalized = System.Text.RegularExpressions.Regex.Replace(body, @"\s+", "");
            // The banned synchronous recompute reflects as Invoke(obj, new object[] { true }).
            Assert.DoesNotContain("newobject[]{true}", normalized);
        }
    }
}
```

> If the source-relative path resolution proves brittle in CI, replace the directory walk with a path computed from a known build property; the assertion (no `ExpireSolution(true)` in `SetScript`) is the invariant to preserve.

- [ ] **Step 2: Run, verify it passes** (it should, because Task 5 already removed the call):

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NoSyncExpireInScriptPathTests"`
Expected: 1 passed.

- [ ] **Step 3: Commit:**

```bash
git add src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs
git commit -m "test(gh): static guard that SetScript never forces a synchronous solve"
```

---

## Final verification

- [ ] **C# full suite:** `dotnet test src/Rook.Tests/Rook.Tests.csproj` — all green.
- [ ] **Python unit:** `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests -m "not requires_rhino" -v` — all green.
- [ ] **Python live (throwaway Rhino):** `mcp_server/.venv/Scripts/python -m pytest -m requires_rhino mcp_server/tests/test_gh_locked_solver_live.py -v` — 2 passed, Rhino responsive.
- [ ] **Manual smoke:** lock the solver, run `gh_update_script` from the chat/agent path → no crash, response says deferred; unlock + `gh_solve` → recompute, pin descriptions intact.

---

## Self-Review (run against the spec)

**Spec coverage:** §4 invariant → Tasks 4/5 (ExpireSolution(false) + async only). §5 helper/outcome/predicate → Tasks 2/3/4. §6 pin strategy → Task 5 (immediate) + Task 6 (gated one-shot). §7 status surface → Task 7. §8.1 deferral → Task 8. §8.2 settling → Task 9. §9 inventory/PR1 split → Task 5 (sites 2-6 are PR2, out of scope here). §10 probes → Task 1. §11 tests → Tasks 2/3/4/7/8/9/10/11 (the "unknown reflection-miss" test is covered by Task 2's `Unknown_*` + Task 3's fail-open and is non-blocking). 

**Placeholder scan:** the two "stub then replace" notes (Task 8 `_await_gh_solve_settle`, Task 9) are explicit, ordered, and self-resolving — not vague TODOs. The conditional Task 6 and the U1-dependent read list in Task 3 are gated on recorded probe results, with concrete most-likely code provided.

**Type consistency:** `GhSolveOutcome` (Task 2) is consumed by Task 4 and Task 5; `GhSolverState.Inspect` → `Result{Enabled,Known,SolutionState}` (Task 3) is consumed by Task 4 and Task 7; `RequestPostMutationSolve` signature (Task 4) matches its call in Task 5; the response keys `solve_scheduled/solver_locked/solver_state_known/verification_deferred` (Task 5) match the Python reader (Task 8). Consistent.
