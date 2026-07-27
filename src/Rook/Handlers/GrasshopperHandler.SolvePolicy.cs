using System;
using System.Collections.Generic;
using Rook.InternalBridge;

namespace Rook.Handlers
{
    // Shared post-mutation safe-solve integration. HTTP-driven GH mutations
    // expire without recompute and make at most one positive-delay schedule
    // request through the reviewed lifecycle, policy, and invoker helpers.
    public partial class GrasshopperHandler
    {
        internal GhScheduleResult RequestPostMutationSolve(
            object document,
            object dirtyObject,
            bool requestSolve,
            int delayMs = 1)
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

        internal GhScheduleResult RequestPostMutationSolve(
            object document,
            IReadOnlyList<object> dirtyObjects,
            bool requestSolve,
            int delayMs = 1,
            bool expireDirtyObjects = true,
            GhSolverState.Result? solverStateOverride = null,
            GhSolverRestoreResult? standaloneRestore = null)
        {
            if (expireDirtyObjects)
                ExpirePostMutationDirtyObjects(dirtyObjects);

            var registration = new GhDocumentLifecycle().InspectRegistration(document);
            var runningAsRhinoInside = _runningAsRhinoInside();
            var solverState = solverStateOverride ?? GhSolverState.Inspect(document);
            var decision = GhPostMutationSchedulePolicy.Decide(new GhScheduleInputs
            {
                SolveRequested = requestSolve,
                RunningAsRhinoInside = runningAsRhinoInside,
                RegistrationKnown = registration.Known,
                DocumentRegistered = registration.Registered,
                GlobalEnableSolutions = solverState.GlobalEnableSolutions,
                DocumentEnabled = solverState.DocumentEnabled,
            });

            if (standaloneRestore.HasValue &&
                standaloneRestore.Value.Attempted &&
                !standaloneRestore.Value.Succeeded)
            {
                return new GhScheduleResult
                {
                    ScheduleClassification = decision.ScheduleClassification,
                    ScheduleAcceptance = GhScheduleAcceptance.NotAttempted,
                    ScheduleFailureCode = GhScheduleFailureCode.StandaloneSolverRestoreFailed,
                    VerificationDeferred = true,
                    SolverLocked = decision.SolverLocked,
                    SolverStateKnown = decision.SolverStateKnown,
                    Warnings = AppendScheduleWarning(
                        decision.Warnings,
                        GhScheduleWarning.StandaloneRestoreFailed),
                };
            }

            return GhScheduleInvoker.Invoke(document, decision, delayMs);
        }

        internal GhMutationSolveSuspension BeginPostMutationBatchSolveSuspension(object? document)
            => GhMutationSolveSuspension.Begin(document, _runningAsRhinoInside());

        private static GhScheduleWarning[] AppendScheduleWarning(
            GhScheduleWarning[] warnings,
            GhScheduleWarning warning)
        {
            var source = warnings ?? Array.Empty<GhScheduleWarning>();
            var result = new GhScheduleWarning[source.Length + 1];
            Array.Copy(source, result, source.Length);
            result[source.Length] = warning;
            return result;
        }
    }
}
