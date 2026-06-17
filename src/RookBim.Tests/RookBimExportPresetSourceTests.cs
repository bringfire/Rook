using System;
using System.IO;
using Xunit;

namespace RookBim.Tests
{
    public class RookBimExportPresetSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void ExportService_ThreadsOrganizationPolicyAndGatesPresetDecoration()
        {
            var src = Read("src/RookBim/Revit/RevitExportService.cs");

            // Generalized: a resolved-export path that takes a policy + optional preset context.
            Assert.Contains("ExportResolved", src);
            Assert.Contains("BimExportOrganizationPolicy", src);
            Assert.Contains("RevitPresetContext", src);

            // Raw path keeps Legacy + null context (parity seam).
            Assert.Contains("BimExportOrganizationPolicy.Legacy", src);

            // Policy-driven layer + name + metadata via the pure helpers.
            Assert.Contains("BimExportLayerNamer.LayerPath", src);
            Assert.Contains("BimExportObjectNamer.ObjectName", src);

            // Read-only invariant preserved.
            Assert.DoesNotContain("Transaction", src);
        }

        internal static string Read(string relativePath)
        {
            return File.ReadAllText(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "Rook.sln")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new InvalidOperationException("Could not find repository root.");
        }
    }
}
