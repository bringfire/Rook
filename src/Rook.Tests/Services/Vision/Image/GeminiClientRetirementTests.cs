using System;
using System.Collections.Generic;
using System.IO;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class GeminiClientRetirementTests
    {
        [Fact]
        public void Production_code_has_no_legacy_gemini_client_references()
        {
            var rookRoot = FindRookRoot();
            var legacyClientPath = Path.Combine(rookRoot, "Services", "Vision", "GeminiClient.cs");
            var matches = new List<string>();

            if (File.Exists(legacyClientPath))
                matches.Add("Services/Vision/GeminiClient.cs exists");

            foreach (var path in Directory.EnumerateFiles(rookRoot, "*.cs", SearchOption.AllDirectories))
            {
                var content = File.ReadAllText(path);
                if (content.IndexOf("GeminiClient", StringComparison.Ordinal) < 0)
                    continue;

                var rel = path.Substring(rookRoot.Length)
                    .TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    .Replace(Path.DirectorySeparatorChar, '/');
                matches.Add(rel);
            }

            Assert.Empty(matches);
        }

        private static string FindRookRoot()
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                var candidate = Path.Combine(dir.FullName, "src", "Rook");
                if (Directory.Exists(candidate))
                    return candidate;

                dir = dir.Parent;
            }

            throw new DirectoryNotFoundException(
                "Could not locate src/Rook by walking up from " + AppContext.BaseDirectory);
        }
    }
}
