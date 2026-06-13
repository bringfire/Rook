using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GhEditSolvePathSourceTests
    {
        [Fact]
        public void ApplyEdit_UsesSharedPostMutationSolveScheduler()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

            Assert.Contains("RequestPostMutationSolve(gh.Document!", source);
            Assert.DoesNotContain("ScheduleDocumentSolution(gh.Document!)", source);
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
