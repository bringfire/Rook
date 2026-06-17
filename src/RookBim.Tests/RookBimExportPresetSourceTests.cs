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

        [Fact]
        public void PresetResolver_LoopsCategoriesUnionsByIdentityAndDegradesGracefully()
        {
            var src = Read("src/RookBim/Revit/RevitPresetResolver.cs");

            // Reuses the existing single-category query path per category.
            Assert.Contains("RevitQueryService", src);
            Assert.Contains("BimPresetCatalog.TryGet", src);

            // Dedup by document GUID + unique id, not display name.
            Assert.Contains("documentGuid", src);
            Assert.Contains("UniqueId", src);

            // include/exclude overrides.
            Assert.Contains("IncludeCategories", src);
            Assert.Contains("ExcludeCategories", src);

            // Missing category = warning; all-missing (non rooms-driven) = NoCategoriesResolved.
            Assert.Contains("category_unavailable", src);
            Assert.Contains("NoCategoriesResolved", src);
            Assert.Contains("RoomsDriven", src);

            // Per-category truncation honors allowTruncated (same rule as v1).
            Assert.Contains("QueryTruncated", src);

            // Read-only.
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
