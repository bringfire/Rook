using System;
using System.IO;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class RequestPostMutationSolveTests
    {
        [Fact]
        public void Integration_ConsumesLifecyclePolicyAndInvokerWithoutRepairOwnership()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs");

            Assert.Contains("internal GhScheduleResult RequestPostMutationSolve(", source);
            Assert.Contains("IReadOnlyList<object> dirtyObjects", source);
            Assert.Contains("GhSolverRestoreResult? standaloneRestore = null", source);
            Assert.Contains("new GhDocumentLifecycle().InspectRegistration(document)", source);
            Assert.Contains("_runningAsRhinoInside()", source);
            Assert.Contains("GhPostMutationSchedulePolicy.Decide(", source);
            Assert.Contains("GhScheduleInvoker.Invoke(document, decision, delayMs)", source);
            Assert.DoesNotContain("GhSolveReadinessCoordinator", source);
            Assert.DoesNotContain("PrepareForPostMutationSolve", source);
            Assert.DoesNotContain("GetProperty(\"Enabled\"", source);
            Assert.DoesNotContain("SetValue(document", source);
            Assert.DoesNotContain("GetProperty(\"EnableSolutions\"", source);
            Assert.DoesNotContain("SetValue(null", source);
        }

        [Fact]
        public void FailedStandaloneRestore_ReturnsBoundedNotAttemptedResultWithoutInvoking()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs");

            Assert.Contains("standaloneRestore.Value.Attempted", source);
            Assert.Contains("!standaloneRestore.Value.Succeeded", source);
            Assert.Contains("ScheduleAcceptance = GhScheduleAcceptance.NotAttempted", source);
            Assert.Contains("ScheduleFailureCode = GhScheduleFailureCode.StandaloneSolverRestoreFailed", source);
            AssertOrder(source,
                "!standaloneRestore.Value.Succeeded",
                "ScheduleFailureCode = GhScheduleFailureCode.StandaloneSolverRestoreFailed",
                "GhScheduleInvoker.Invoke(document, decision, delayMs)");
        }

        [Fact]
        public void Integration_PassesRegistrationAndSeparateGlobalAndInstanceFlagsIntoPolicy()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs");

            Assert.Contains("RegistrationKnown = registration.Known", source);
            Assert.Contains("DocumentRegistered = registration.Registered", source);
            Assert.Contains("GlobalEnableSolutions = solverState.GlobalEnableSolutions", source);
            Assert.Contains("DocumentEnabled = solverState.DocumentEnabled", source);
            Assert.Contains("RunningAsRhinoInside = runningAsRhinoInside", source);
        }

        [Fact]
        public void BatchSuspension_UsesHostAwareOneShotHelper()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs");

            Assert.Contains("internal GhMutationSolveSuspension BeginPostMutationBatchSolveSuspension(object? document)", source);
            Assert.Contains("GhMutationSolveSuspension.Begin(document, _runningAsRhinoInside())", source);
            Assert.DoesNotContain("class GhDocumentSolveSuspension", source);
        }

        [Fact]
        public void BatchSuspension_InjectsRirAsNoOpAndStandaloneAsOneShotOwnership()
        {
            SuspensionDocument.EnableSolutions = true;
            var rirDocument = new SuspensionDocument { Enabled = true };
            rirDocument.ResetWrites();
            var standaloneDocument = new SuspensionDocument { Enabled = true };
            standaloneDocument.ResetWrites();
            var rir = new GrasshopperHandler(runningAsRhinoInside: () => true);
            var standalone = new GrasshopperHandler(runningAsRhinoInside: () => false);

            var rirSuspension = rir.BeginPostMutationBatchSolveSuspension(rirDocument);
            var standaloneSuspension = standalone.BeginPostMutationBatchSolveSuspension(standaloneDocument);
            var firstRestore = standaloneSuspension.Restore();
            var secondRestore = standaloneSuspension.Restore();

            Assert.False(rirSuspension.Active);
            Assert.Equal(0, rirDocument.EnabledWrites);
            Assert.False(rirSuspension.Restore().Attempted);
            Assert.True(standaloneSuspension.Active);
            Assert.True(firstRestore.Attempted);
            Assert.True(firstRestore.Succeeded);
            Assert.False(secondRestore.Attempted);
            Assert.Equal(2, standaloneDocument.EnabledWrites);
        }

        [Fact]
        public void ApplyEdit_StateTransitionUsesPostRestorationSolverStateInsteadOfOriginalSnapshot()
        {
            TransitionDocument.EnableSolutions = true;
            var document = new TransitionDocument { Enabled = true };
            var handler = new GrasshopperHandler(runningAsRhinoInside: () => false);
            var suspension = handler.BeginPostMutationBatchSolveSuspension(document);

            TransitionDocument.EnableSolutions = false;
            var restore = suspension.Restore();
            var currentResult = handler.RequestPostMutationSolve(
                document,
                Array.Empty<object>(),
                requestSolve: true,
                expireDirtyObjects: false,
                standaloneRestore: restore);
            var staleResult = handler.RequestPostMutationSolve(
                document,
                Array.Empty<object>(),
                requestSolve: true,
                expireDirtyObjects: false,
                solverStateOverride: suspension.OriginalSolverState,
                standaloneRestore: restore);

            Assert.True(restore.Attempted);
            Assert.True(restore.Succeeded);
            Assert.Equal(GhScheduleClassification.GlobalSolverUnavailable, currentResult.ScheduleClassification);
            Assert.Equal(GhScheduleAcceptance.NotAttempted, currentResult.ScheduleAcceptance);
            Assert.False(currentResult.SolveScheduled);
            Assert.Equal(GhScheduleClassification.AsyncScheduleRequested, staleResult.ScheduleClassification);
            Assert.Equal(GhScheduleAcceptance.Accepted, staleResult.ScheduleAcceptance);
            Assert.Equal(1, document.ScheduleCalls);

            var routeSource = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            Assert.DoesNotContain("solverStateOverride: solveSuspension.OriginalSolverState", routeSource);
            Assert.Contains("standaloneRestore: standaloneRestore", routeSource);
        }

        private sealed class SuspensionDocument
        {
            public static bool EnableSolutions { get; set; }
            private bool _enabled;
            public int EnabledWrites { get; private set; }
            public bool Enabled
            {
                get => _enabled;
                set
                {
                    EnabledWrites++;
                    _enabled = value;
                }
            }

            public void ResetWrites() => EnabledWrites = 0;
        }

        private sealed class TransitionDocument
        {
            public static bool EnableSolutions { get; set; }
            public bool Enabled { get; set; }
            public int ScheduleCalls { get; private set; }

            public void ScheduleSolution(int delayMs)
            {
                Assert.True(delayMs > 0);
                ScheduleCalls++;
            }
        }

        private static void AssertOrder(string source, params string[] markers)
        {
            var prior = -1;
            foreach (var marker in markers)
            {
                var index = source.IndexOf(marker, prior + 1, StringComparison.Ordinal);
                Assert.True(index > prior, $"Expected '{marker}' after index {prior}.");
                prior = index;
            }
        }

        private static string ReadSource(params string[] path) => File.ReadAllText(Path.Combine(RepoRoot(), Path.Combine(path)));

        private static string RepoRoot()
        {
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
                dir = dir.Parent;
            Assert.NotNull(dir);
            return dir!.FullName;
        }
    }
}
