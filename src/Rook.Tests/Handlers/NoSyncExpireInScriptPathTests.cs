using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class NoSyncExpireInScriptPathTests
    {
        // Guards the safety invariant: SetScript must never force a synchronous solve
        // (Invoke(obj, new object[] { true }) on ExpireSolution), which re-enters the
        // GH solver and hard-crashes a locked canvas. See spec §4.
        [Fact]
        public void SetScript_DoesNotCallExpireSolutionTrue()
        {
            var src = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

            // Extract the SetScript method body up to the next member declaration.
            var start = src.IndexOf("public ApiResponse SetScript(");
            Assert.True(start >= 0, "SetScript not found");
            var end = src.IndexOf("\n        private", start);
            var body = end > start ? src.Substring(start, end - start) : src.Substring(start);

            // Normalize ALL whitespace on both sides so the match actually works.
            var normalized = System.Text.RegularExpressions.Regex.Replace(body, @"\s+", "");
            // The banned synchronous recompute reflects as Invoke(obj, new object[] { true }).
            Assert.DoesNotContain("newobject[]{true}", normalized);
        }

        [Fact]
        public void GrasshopperMutationPaths_DoNotCallNewSolution()
        {
            foreach (var file in GrasshopperMutationFiles())
            {
                var source = File.ReadAllText(file);
                Assert.DoesNotContain(".NewSolution(", source);
            }
        }

        [Fact]
        public void GrasshopperMutationPaths_DoNotUseSynchronousExpireSolution()
        {
            foreach (var file in GrasshopperMutationFiles())
            {
                var source = File.ReadAllText(file);
                Assert.DoesNotContain("ExpireSolution(true", source);
            }
        }

        [Fact]
        public void RirSchedulingPath_DoesNotOwnGlobalOrInstanceSolverWrites()
        {
            var root = RepoRoot();
            var integration = File.ReadAllText(Path.Combine(root, "src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs"));
            var suspension = File.ReadAllText(Path.Combine(root, "src", "Rook", "Handlers", "GhMutationSolveSuspension.cs"));

            Assert.DoesNotMatch(@"(?<![A-Za-z0-9_])EnableSolutions\s*=", integration);
            Assert.DoesNotContain("SetValue(null", integration);
            Assert.DoesNotContain("GetProperty(\"Enabled\"", integration);
            Assert.DoesNotContain("SetValue(document", integration);
            Assert.True(
                suspension.IndexOf("runningAsRhinoInside", System.StringComparison.Ordinal) <
                suspension.IndexOf("enabledProperty.SetValue(document, false)", System.StringComparison.Ordinal));
        }

        [Fact]
        public void GrasshopperHandler_HasNoOrphanDocumentScheduler()
        {
            var source = File.ReadAllText(Path.Combine(
                RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

            Assert.DoesNotContain("private void ScheduleDocumentSolution", source);
        }

        private static string[] GrasshopperMutationFiles()
        {
            var root = RepoRoot();
            return new[]
            {
                Path.Combine(root, "src", "Rook", "Handlers", "GrasshopperHandler.cs"),
                Path.Combine(root, "src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs"),
                Path.Combine(root, "src", "Rook", "Handlers", "GhMutationSolveSuspension.cs"),
            };
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
