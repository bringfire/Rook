using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Phase 1 carve-out enforcement: 3D abstractions, fields, and
    /// vendor-specific 3D names are reserved for Phase 4 and must not
    /// appear under <c>src/Rook/Services/Vision/Generation/</c>.
    ///
    /// <para>The scan is path-scoped so Phase 4 design notes elsewhere
    /// in the repo (docs, spike tooling, mcp_server) don't trigger
    /// the test. Pattern matching is case-insensitive to catch
    /// renames and casing variants.</para>
    /// </summary>
    public class SymbolScanGuardTests
    {
        private static readonly string[] ForbiddenPatterns =
        {
            @"\bIThreeDProvider\b",
            @"\bResolvedThreeDModel\b",
            @"\bThreeDCapability\b",
            @"\bThreeDGenerationRequest\b",
            @"\bIThreeDProviderRegistry\b",
            @"\bIThreeDProviderRegistration\b",
            @"\bmodel_glb\b",
            @"\bmodel_urls\b",
            @"\bthree_d_provider\b",
            @"\btencent_3d\b",
            @"\bhunyuan3d\b",
        };

        [Fact]
        public void Generation_namespace_contains_no_3D_symbols()
        {
            var root = FindGenerationRoot();
            var sources = Directory.EnumerateFiles(root, "*.cs", SearchOption.AllDirectories);
            var matches = new List<string>();
            foreach (var path in sources)
            {
                var content = File.ReadAllText(path);
                foreach (var pattern in ForbiddenPatterns)
                {
                    if (Regex.IsMatch(content, pattern, RegexOptions.IgnoreCase))
                    {
                        matches.Add($"{Path.GetFileName(path)}: {pattern}");
                    }
                }
            }

            Assert.Empty(matches);
        }

        // Walk up from the test binary's directory until we find an
        // ancestor that contains src/Rook/Services/Vision/Generation/.
        // The test binary lives several directories deep under bin/;
        // the repo root contains src/, so we find it deterministically
        // without hardcoding a path.
        private static string FindGenerationRoot()
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                var candidate = Path.Combine(
                    dir.FullName,
                    "src", "Rook", "Services", "Vision", "Generation");
                if (Directory.Exists(candidate))
                {
                    return candidate;
                }
                dir = dir.Parent;
            }
            throw new DirectoryNotFoundException(
                "Could not locate src/Rook/Services/Vision/Generation/ " +
                "by walking up from " + AppContext.BaseDirectory);
        }
    }
}
