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

        [Fact]
        public void Summary_AndRelationships_ArePresetPathOnlyAndFactual()
        {
            var service = Read("src/RookBim/Revit/RevitExportService.cs");
            var rel = Read("src/RookBim/Revit/RevitRelationshipIndex.cs");

            // Summary structured fields + digest.
            Assert.Contains("digest", service);
            Assert.Contains("resolvedCategories", service);
            Assert.Contains("geometryQuality", service);
            Assert.Contains("layerPolicy", service);
            Assert.Contains("warnings", service);

            // Policy echoes use the wire serializers, NOT C# enum names.
            Assert.Contains("BimExportOrganizationPolicy.LayerToWire", service);
            Assert.DoesNotContain("Policy.LayerScheme.ToString()", service);

            // Model audit proves names + stamps from the actual File3dm objects.
            Assert.Contains("BuildModelObjectAudit", service);
            Assert.Contains("namedObjectCount", service);

            // Relationships are facts only (carry source/confidence), three membership lists.
            Assert.Contains("roomMembership", rel);
            Assert.Contains("hostMembership", rel);
            Assert.Contains("levelMembership", rel);
            Assert.Contains("confidence", rel);

            // Decoration stays gated on the preset context.
            Assert.Contains("presetContext == null", service);
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
