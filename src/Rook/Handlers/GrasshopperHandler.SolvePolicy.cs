using System.Collections.Generic;
using Rook.InternalBridge;

namespace Rook.Handlers
{
    // Shared post-mutation safe-solve policy. The safety invariant: HTTP-driven GH
    // mutations NEVER request synchronous expiration (that re-enters
    // the solver and hard-crashes a locked canvas). They mark dirty with
    // ExpireSolution(false) and schedule at most one async ScheduleSolution(delay >= 1).
    // See docs/superpowers/specs/2026-06-02-gh-locked-solver-crash-design.md.
    public partial class GrasshopperHandler
    {
        // Single-object form — the call shape used by ~all mutation sites.
        internal GhSolveOutcome RequestPostMutationSolve(object document, object dirtyObject, bool requestSolve, int delayMs = 1)
            => RequestPostMutationSolve(document, new[] { dirtyObject }, requestSolve, delayMs);

        // Batch form — for multi-target mutations (e.g. gh_edit).
        internal GhSolveOutcome RequestPostMutationSolve(object document, IReadOnlyList<object> dirtyObjects, bool requestSolve, int delayMs = 1)
        {
            // 1. Mark each dirty WITHOUT recompute. This is the safety invariant: never request synchronous expiration.
            foreach (var obj in dirtyObjects)
            {
                if (obj == null) continue;
                var expire = obj.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
                expire?.Invoke(obj, new object[] { false });
            }

            // 2. In RIR, repair a Rook-driven document instance before deciding whether async scheduling is allowed.
            var readiness = _solveReadinessCoordinator.PrepareForPostMutationSolve(
                document,
                requestSolve,
                currentMutationIsRookDriven: true);

            // 3. Inspect solver state after any schedule-time repair.
            var state = GhSolverState.Inspect(document);

            // 4. Decide (pure).
            var outcome = GhSolvePolicy.Decide(
                requestSolve,
                state.Enabled ?? true,
                state.Known,
                readiness.RepairAttempted,
                readiness.RepairHeld,
                readiness.Reason);

            // 5. Schedule at most one async solution, never delay 0. If reflected
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
                        RirRepairAttempted = outcome.RirRepairAttempted,
                        RirRepairHeld = outcome.RirRepairHeld,
                        RirRepairReason = outcome.RirRepairReason,
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
