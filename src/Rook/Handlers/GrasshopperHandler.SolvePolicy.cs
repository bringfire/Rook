using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Rook.InternalBridge;
using Rhino;

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

        internal void ExpirePostMutationDirtyObjects(IReadOnlyList<object> dirtyObjects)
        {
            foreach (var obj in dirtyObjects)
            {
                if (obj == null) continue;
                var expire = obj.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
                expire?.Invoke(obj, new object[] { false });
            }
        }

        // Batch form — for multi-target mutations (e.g. gh_edit).
        internal GhSolveOutcome RequestPostMutationSolve(
            object document,
            IReadOnlyList<object> dirtyObjects,
            bool requestSolve,
            int delayMs = 1,
            bool expireDirtyObjects = true,
            GhSolverState.Result? solverStateOverride = null)
        {
            // 1. Mark each dirty WITHOUT recompute. This is the safety invariant: never request synchronous expiration.
            if (expireDirtyObjects)
                ExpirePostMutationDirtyObjects(dirtyObjects);

            var outcome = DecidePostMutationSolve(document, requestSolve, solverStateOverride);

            // 5. Schedule at most one async solution, never delay 0. If reflected
            //    ScheduleSolution is missing or throws, the solve did NOT happen —
            //    correct the outcome so callers never over-claim scheduling.
            if (outcome.SolveScheduled)
            {
                if (delayMs < 1) delayMs = 1;
                if (!TrySchedule(document, delayMs))
                {
                    outcome = MarkScheduleUnavailable(outcome);
                }
            }

            return outcome;
        }

        internal GhSolveOutcome RequestDeferredPostMutationSolve(
            object document,
            bool requestSolve,
            int delayMs = 1,
            int dispatchDelayMs = 1,
            GhSolverState.Result? solverStateOverride = null,
            Action? beforeScheduleOnUiThread = null)
        {
            var outcome = DecidePostMutationSolve(document, requestSolve, solverStateOverride);

            if (outcome.SolveScheduled)
            {
                if (delayMs < 1) delayMs = 1;
                if (dispatchDelayMs < 1) dispatchDelayMs = 1;

                if (!TryScheduleDeferred(document, delayMs, dispatchDelayMs, beforeScheduleOnUiThread))
                {
                    outcome = MarkScheduleUnavailable(outcome);
                }
                else
                {
                    outcome = MarkVerificationDeferred(outcome,
                        "ScheduleSolution was deferred until after the callback returned; solve completion not verified.");
                }
            }

            return outcome;
        }

        internal GhDocumentSolveSuspension BeginPostMutationBatchSolveSuspension(object? document)
            => GhDocumentSolveSuspension.Begin(document);

        private GhSolveOutcome DecidePostMutationSolve(
            object document,
            bool requestSolve,
            GhSolverState.Result? solverStateOverride = null)
        {
            // In RIR, repair a Rook-driven document instance before deciding whether async scheduling is allowed.
            var readiness = _solveReadinessCoordinator.PrepareForPostMutationSolve(
                document,
                requestSolve,
                currentMutationIsRookDriven: true);

            // Inspect solver state after any schedule-time repair.
            var state = solverStateOverride ?? GhSolverState.Inspect(document);

            // Decide (pure).
            return GhSolvePolicy.Decide(
                requestSolve,
                state.Enabled ?? true,
                state.Known,
                readiness.RepairAttempted,
                readiness.RepairHeld,
                readiness.Reason);
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

        private static bool TryScheduleDeferred(
            object document,
            int delayMs,
            int dispatchDelayMs,
            Action? beforeScheduleOnUiThread)
        {
            try
            {
                // The document can be closed or replaced before this delayed
                // task runs; restore/schedule are best-effort below.
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await Task.Delay(dispatchDelayMs).ConfigureAwait(false);
                        InvokeOnRhinoUiThread(() =>
                        {
                            try
                            {
                                beforeScheduleOnUiThread?.Invoke();
                            }
                            finally
                            {
                                TrySchedule(document, delayMs);
                            }
                        });
                    }
                    catch
                    {
                        // The callback response cannot observe deferred scheduling
                        // failure; the returned metadata marks verification deferred.
                    }
                });

                return true;
            }
            catch
            {
                return false;
            }
        }

        private static void InvokeOnRhinoUiThread(Action action)
        {
            try
            {
                RhinoApp.InvokeOnUiThread(new Action(action));
            }
            catch (DllNotFoundException)
            {
                action();
            }
            catch (EntryPointNotFoundException)
            {
                action();
            }
            catch (BadImageFormatException)
            {
                action();
            }
        }

        private static GhSolveOutcome MarkScheduleUnavailable(GhSolveOutcome outcome)
        {
            return new GhSolveOutcome
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

        private static GhSolveOutcome MarkVerificationDeferred(GhSolveOutcome outcome, string warning)
        {
            return new GhSolveOutcome
            {
                SolveScheduled = outcome.SolveScheduled,
                SolverLocked = outcome.SolverLocked,
                SolverStateKnown = outcome.SolverStateKnown,
                VerificationDeferred = true,
                Warnings = AppendWarning(outcome.Warnings, warning),
                RirRepairAttempted = outcome.RirRepairAttempted,
                RirRepairHeld = outcome.RirRepairHeld,
                RirRepairReason = outcome.RirRepairReason,
            };
        }

        private static string[] AppendWarning(string[] existing, string warning)
        {
            var list = new System.Collections.Generic.List<string>(existing ?? System.Array.Empty<string>());
            list.Add(warning);
            return list.ToArray();
        }

        internal sealed class GhDocumentSolveSuspension
        {
            private readonly object? _document;
            private readonly System.Reflection.PropertyInfo? _enabledProperty;
            private bool _restored;

            private GhDocumentSolveSuspension(
                object? document,
                System.Reflection.PropertyInfo? enabledProperty,
                bool active,
                GhSolverState.Result originalSolverState)
            {
                _document = document;
                _enabledProperty = enabledProperty;
                Active = active;
                OriginalSolverState = originalSolverState;
            }

            public bool Active { get; }
            public GhSolverState.Result OriginalSolverState { get; }

            public static GhDocumentSolveSuspension Begin(object? document)
            {
                var original = GhSolverState.Inspect(document);
                if (document == null || original.Enabled != true || original.DocumentEnabled != true)
                    return new GhDocumentSolveSuspension(document, null, false, original);

                try
                {
                    var property = document.GetType().GetProperty(
                        "Enabled",
                        System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public);
                    if (property == null || !property.CanWrite)
                        return new GhDocumentSolveSuspension(document, null, false, original);

                    property.SetValue(document, false);
                    return new GhDocumentSolveSuspension(document, property, true, original);
                }
                catch
                {
                    return new GhDocumentSolveSuspension(document, null, false, original);
                }
            }

            public void Restore()
            {
                if (!Active || _restored)
                    return;

                _restored = true;
                try
                {
                    _enabledProperty?.SetValue(_document, true);
                }
                catch
                {
                    // Best-effort: never fail the mutation response while restoring
                    // the pre-batch solver flag.
                }
            }
        }
    }
}
