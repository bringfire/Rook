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
            // Locate the handler source relative to the test assembly's working directory.
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
                dir = dir.Parent;
            Assert.NotNull(dir);
            var src = File.ReadAllText(Path.Combine(dir!.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

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
    }
}
