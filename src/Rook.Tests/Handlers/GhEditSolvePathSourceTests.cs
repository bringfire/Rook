using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GhEditSolvePathSourceTests
    {
        [Fact]
        public void ApplyEdit_RestoresExactlyOnceBeforeOneScheduleAndResponseConstruction()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var method = ApplyEditSource(source);

            AssertOrder(method,
                "ExpirePostMutationDirtyObjects(dirtyObjects)",
                "TakeStructuralSnapshot()",
                "solveSuspension.Restore()",
                "RequestPostMutationSolve(",
                "return snapshotResult");
            Assert.Equal(2, Count(method, "solveSuspension.Restore()"));
            Assert.Contains("standaloneRestore: standaloneRestore", method);
            Assert.DoesNotContain("RequestDeferredPostMutationSolve", source);
            Assert.DoesNotContain("5000", method);
        }

        [Fact]
        public void SolvePolicy_HasNoTaskHandoffUiRedispatchOrSecondScheduler()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs");

            Assert.DoesNotContain("RequestDeferredPostMutationSolve", source);
            Assert.DoesNotContain("TryScheduleDeferred", source);
            Assert.DoesNotContain("Task.Run", source);
            Assert.DoesNotContain("System.Threading.Tasks", source);
            Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", source);
            Assert.DoesNotContain("TrySchedule(", source);
            Assert.Equal(1, Count(source, "GhScheduleInvoker.Invoke("));
        }

        [Fact]
        public void ApplyEdit_EmitsAuthoritativeSnakeCaseScheduleAndRegistrationEvidenceInEveryShape()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var method = ApplyEditSource(source);

            Assert.Contains("var editSummary = new", method);
            Assert.Equal(2, Count(method, "schedule_classification ="));
            Assert.Equal(2, Count(method, "schedule_acceptance ="));
            Assert.Equal(2, Count(method, "schedule_failure_code ="));
            Assert.Equal(2, Count(method, "solve_scheduled ="));
            Assert.Equal(2, Count(method, "solve_warnings ="));
            Assert.Equal(2, Count(method, "registration_known ="));
            Assert.Equal(2, Count(method, "document_registered ="));
            Assert.Contains("registration_known = solveResult.RegistrationKnown", method);
            Assert.Contains("document_registered = solveResult.DocumentRegistered", method);
            Assert.Contains("solve_warnings = solveResult.Warnings.Select(GhScheduleWire.ToWire).ToArray()", method);
            Assert.DoesNotContain("scheduleClassification", method);
            Assert.DoesNotContain("scheduleAcceptance", method);
            Assert.DoesNotContain("scheduleFailureCode", method);
            Assert.DoesNotContain("solveScheduled", method);
            Assert.DoesNotContain("rir_repair_source", method);
        }

        [Fact]
        public void ApplyEdit_FailedSnapshotRetainsScheduleAndStandaloneRestoreEvidence()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var method = ApplyEditSource(source);

            AssertOrder(method,
                "standaloneRestore = solveSuspension.Restore()",
                "scheduleResult = RequestPostMutationSolve(",
                "var solveResult = scheduleResult.Value",
                "var editSummary = new",
                "if (snapshotResult.Success && snapshotResult.Data is Dictionary",
                "else if (snapshotResult.Success)",
                "var snapshotFailure = snapshotResult.Data",
                "return snapshotResult");
            Assert.Contains("snapshot_failure = snapshotFailure", method);
            Assert.Contains("edit_summary = editSummary", method);
            Assert.Contains("standalone_restore_attempted = standaloneRestore.Value.Attempted", method);
            Assert.Contains("standalone_restore_succeeded = standaloneRestore.Value.Succeeded", method);
            Assert.Contains("observed_document_enabled = standaloneRestore.Value.ObservedDocumentEnabled", method);
        }

        [Fact]
        public void ApplyEdit_CapturesStructuralSnapshotWithoutSynchronousSolve()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var method = ApplyEditSource(source);

            Assert.Contains("TakeStructuralSnapshot()", method);
            Assert.Contains("\\\"include_data\\\":false", source);
            Assert.Contains("\\\"max_preview_items\\\":0", source);
            Assert.DoesNotContain("NewSolution", method);
            Assert.DoesNotContain("ExpireSolution(true)", method);
            Assert.DoesNotContain("ScheduleDocumentSolution", method);
        }

        [Fact]
        public void ApplyEdit_RestoreFailureBeforeSchedulingReportsSolveNotRequested()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var method = ApplyEditSource(source);
            var failure = method.Substring(method.IndexOf("catch (Exception ex)", StringComparison.Ordinal));

            Assert.Contains("GhScheduleClassification.SolveNotRequested", failure);
            Assert.Contains("FinalizePostReservationFailureReceipt(", failure);
            Assert.DoesNotContain("GhScheduleClassification.AsyncScheduleRequested", failure);
        }

        private static string ApplyEditSource(string source) => MethodSource(source, "public ApiResponse ApplyEdit", "/// <summary>");

        private static string ReadSource(params string[] path) => File.ReadAllText(Path.Combine(RepoRoot(), Path.Combine(path)));

        private static string MethodSource(string source, string startMarker, string endMarker)
        {
            var start = source.IndexOf(startMarker, StringComparison.Ordinal);
            Assert.True(start >= 0);
            var end = source.IndexOf(endMarker, start + startMarker.Length, StringComparison.Ordinal);
            Assert.True(end > start);
            return source.Substring(start, end - start);
        }

        private static int Count(string source, string value)
        {
            var count = 0;
            for (var index = 0; (index = source.IndexOf(value, index, StringComparison.Ordinal)) >= 0; index += value.Length)
                count++;
            return count;
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
