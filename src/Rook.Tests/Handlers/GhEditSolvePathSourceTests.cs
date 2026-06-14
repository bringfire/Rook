using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GhEditSolvePathSourceTests
    {
        [Fact]
        public void ApplyEdit_UsesDeferredPostMutationSolveScheduler()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
            var method = ApplyEditSource(source);

            Assert.Contains("RequestDeferredPostMutationSolve(", method);
            Assert.DoesNotContain("RequestPostMutationSolve(", method);
            Assert.DoesNotContain("ScheduleDocumentSolution(gh.Document!)", method);
        }

        [Fact]
        public void ApplyEdit_ReturnsSolveOutcomeMetadata()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

            Assert.Contains("solve_scheduled", source);
            Assert.Contains("solver_locked", source);
            Assert.Contains("rir_repair_attempted", source);
            Assert.Contains("rir_repair_held", source);
        }

        [Fact]
        public void ApplyEdit_CapturesSnapshotBeforeDeferredSchedulingSolve()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
            var method = ApplyEditSource(source);

            var suspendIndex = method.IndexOf("solveSuspension = BeginPostMutationBatchSolveSuspension(gh.Document!);", System.StringComparison.Ordinal);
            var expireIndex = method.IndexOf("ExpirePostMutationDirtyObjects(dirtyObjects);", System.StringComparison.Ordinal);
            var snapshotIndex = method.IndexOf("var snapshotResult = TakeStructuralSnapshot();", System.StringComparison.Ordinal);
            var scheduleIndex = method.IndexOf("RequestDeferredPostMutationSolve(", snapshotIndex, System.StringComparison.Ordinal);

            Assert.True(suspendIndex >= 0);
            Assert.True(expireIndex > suspendIndex);
            Assert.True(snapshotIndex > expireIndex);
            Assert.True(scheduleIndex > snapshotIndex);
            Assert.Contains("postEditSolveDelayMs = 1", method);
            Assert.Contains("postEditScheduleDispatchDelayMs = 5000", method);
            Assert.Contains("dispatchDelayMs: postEditScheduleDispatchDelayMs", method);
        }

        [Fact]
        public void ApplyEdit_RestoresBatchSolveSuspensionThroughDeferredScheduler()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
            var method = ApplyEditSource(source);

            var scheduleIndex = method.IndexOf("RequestDeferredPostMutationSolve(", System.StringComparison.Ordinal);
            var noScheduleRestoreIndex = method.IndexOf("if (!solveOutcome.SolveScheduled)", scheduleIndex, System.StringComparison.Ordinal);
            var catchRestoreIndex = method.IndexOf("solveSuspension?.Restore();", System.StringComparison.Ordinal);

            Assert.Contains("solverStateOverride: solveSuspension.OriginalSolverState", method);
            Assert.Contains("beforeScheduleOnUiThread: solveSuspension.Restore", method);
            Assert.True(noScheduleRestoreIndex > scheduleIndex);
            Assert.True(catchRestoreIndex > noScheduleRestoreIndex);
        }

        [Fact]
        public void ApplyEdit_ResponseSnapshotOmitsOutputDataPreviews()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
            var method = ApplyEditSource(source);

            Assert.Contains("TakeStructuralSnapshot()", method);
            Assert.Contains("\\\"include_data\\\":false", source);
            Assert.Contains("\\\"max_preview_items\\\":0", source);
        }

        [Fact]
        public void DeferredPostMutationSolve_QueuesScheduleOffCallbackPath()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs"));

            Assert.Contains("RequestDeferredPostMutationSolve", source);
            Assert.Contains("Task.Run(async ()", source);
            Assert.Contains("await Task.Delay(dispatchDelayMs).ConfigureAwait(false);", source);
            Assert.Contains("beforeScheduleOnUiThread?.Invoke();", source);
            Assert.Contains("TrySchedule(document, delayMs);", source);
            Assert.Contains("ScheduleSolution was deferred until after the callback returned", source);
        }

        private static string ApplyEditSource(string source)
        {
            var methodStart = source.IndexOf("public ApiResponse ApplyEdit", System.StringComparison.Ordinal);
            Assert.True(methodStart >= 0);
            var methodEnd = source.IndexOf("/// <summary>", methodStart, System.StringComparison.Ordinal);
            Assert.True(methodEnd > methodStart);
            return source.Substring(methodStart, methodEnd - methodStart);
        }

        private static string RepoRoot()
        {
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
            {
                dir = dir.Parent;
            }

            Assert.NotNull(dir);
            return dir!.FullName;
        }
    }
}
