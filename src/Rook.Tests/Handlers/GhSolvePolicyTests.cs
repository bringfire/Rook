using System;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GhSolvePolicyTests
    {
        [Fact]
        public void ObsoletePolicyAndOutcome_AreRemovedFromProduction()
        {
            var root = RepoRoot();
            var obsoletePolicy = Path.Combine(root, "src", "Rook", "Handlers", "GhSolvePolicy.cs");
            var production = ProductionSource(root);

            Assert.False(File.Exists(obsoletePolicy));
            Assert.DoesNotContain("GhSolveOutcome", production);
        }

        [Fact]
        public void Production_HasNoDeferredSchedulerOrReadinessRepairCoordinator()
        {
            var production = ProductionSource(RepoRoot());
            var forbidden = new[]
            {
                "RequestDeferredPostMutationSolve",
                "postEditScheduleDispatchDelayMs",
                "GhSolveReadinessCoordinator",
                "MarkRookManagedDocument",
                "PrepareForPostMutationSolve",
            };

            foreach (var value in forbidden)
                Assert.DoesNotContain(value, production);

            var solvePolicy = File.ReadAllText(Path.Combine(
                RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs"));
            Assert.DoesNotContain("Task.Run", solvePolicy);
            Assert.DoesNotMatch(@"(?<![A-Za-z0-9_])EnableSolutions\s*=", production);
            Assert.DoesNotContain("SetValue(null", production);
        }

        [Fact]
        public void SetScript_EmitsAuthoritativeScheduleContractWithoutCamelCaseDuplicates()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
            var method = MethodSource(source, "public ApiResponse SetScript", "private static string? GetParamAccessString");

            Assert.Contains("schedule_classification = GhScheduleWire.ToWire(solveResult.ScheduleClassification)", method);
            Assert.Contains("schedule_acceptance = GhScheduleWire.ToWire(solveResult.ScheduleAcceptance)", method);
            Assert.Contains("schedule_failure_code = solveResult.ScheduleFailureCode.HasValue", method);
            Assert.Contains("solve_scheduled = solveResult.SolveScheduled", method);
            Assert.Contains("solve_warnings = solveResult.Warnings.Select(GhScheduleWire.ToWire).ToArray()", method);
            Assert.DoesNotContain("scheduleClassification", method);
            Assert.DoesNotContain("scheduleAcceptance", method);
            Assert.DoesNotContain("scheduleFailureCode", method);
            Assert.DoesNotContain("solveScheduled", method);
        }

        private static string ProductionSource(string root)
        {
            var handlerFiles = Directory.GetFiles(Path.Combine(root, "src", "Rook", "Handlers"), "GrasshopperHandler*.cs");
            var bridgeFiles = Directory.GetFiles(Path.Combine(root, "src", "Rook", "InternalBridge"), "*.cs");
            return string.Join("\n", handlerFiles.Concat(bridgeFiles).Select(File.ReadAllText));
        }

        private static string MethodSource(string source, string startMarker, string endMarker)
        {
            var start = source.IndexOf(startMarker, StringComparison.Ordinal);
            Assert.True(start >= 0);
            var end = source.IndexOf(endMarker, start + startMarker.Length, StringComparison.Ordinal);
            Assert.True(end > start);
            return source.Substring(start, end - start);
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
