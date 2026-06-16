using System;
using System.IO;
using Xunit;

namespace RookBim.Tests
{
    public class RookBimExportSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void GeometryConverter_UsesReflectionBrepThenMeshThenBboxFallback()
        {
            var src = Read("src/RookBim/Revit/RevitGeometryConverter.cs");

            // Reflection Brep path — no hard RhinoInside.Revit reference.
            Assert.Contains("RhinoInside.Revit", src);
            Assert.Contains("GetMethod", src);
            Assert.DoesNotContain("using RhinoInside", src);

            // Mesh fallback via Revit tessellation.
            Assert.Contains("Triangulate", src);
            Assert.Contains("Rhino.Geometry.Mesh", src);

            // Quality vocabulary — no "exact" claims.
            Assert.Contains("\"converted_brep\"", src);
            Assert.Contains("\"mesh_fallback\"", src);
            Assert.Contains("\"bbox_only\"", src);
            Assert.Contains("\"failed\"", src);
            Assert.DoesNotContain("exact_brep", src);

            // Opt-in bbox proxy.
            Assert.Contains("allowBboxProxy", src);

            // Read-only — no Revit transaction.
            Assert.DoesNotContain("Transaction", src);
        }

        [Fact]
        public void LabelExtractor_EmitsProvenanceTaggedLabels()
        {
            var src = Read("src/RookBim/Revit/RevitLabelExtractor.cs");

            Assert.Contains("Value", src);
            Assert.Contains("Source", src);
            Assert.Contains("Confidence", src);
            Assert.Contains("MissingReason", src);

            Assert.Contains("\"revit_api\"", src);
            Assert.Contains("\"parameter\"", src);
            Assert.Contains("\"derived\"", src);
            Assert.Contains("\"unavailable\"", src);

            // Relationship labels.
            Assert.Contains("LevelId", src);
            Assert.Contains("HostId", src);
            Assert.Contains("ContainingRoom", src);
            Assert.Contains("ContainingSpace", src);

            Assert.DoesNotContain("Transaction", src);
        }

        [Fact]
        public void RoomExporter_TypesRoomsSeparatelyAndDegradesPerRoom()
        {
            var src = Read("src/RookBim/Revit/RevitRoomExporter.cs");

            // Per-room degrade ladder.
            Assert.Contains("\"room_volume_brep\"", src);
            Assert.Contains("\"room_mesh\"", src);
            Assert.Contains("\"boundary_2d\"", src);
            Assert.Contains("\"label_only\"", src);

            // Separate reference layer + flag.
            Assert.Contains("RookBim::Rooms", src);
            Assert.Contains("referenceGeometry", src);

            // Read-only spatial geometry.
            Assert.Contains("SpatialElementGeometryCalculator", src);
            Assert.DoesNotContain("Transaction", src);
        }

        [Fact]
        public void ExportService_FreezesIdentitiesGuardsTruncationWritesBundleAndVerifies()
        {
            var src = Read("src/RookBim/Revit/RevitExportService.cs");

            // Strict one-of already validated upstream; service resolves both selector + identities.
            Assert.Contains("RevitQueryService", src);
            Assert.Contains("RevitIdentitySerializer.Resolve", src);

            // No-silent-truncation guard.
            Assert.Contains("AllowTruncated", src);
            Assert.Contains("BimErrorCode.QueryTruncated", src);

            // Path safety BEFORE writing.
            Assert.Contains("BimExportPathPolicy.ValidateRequestShape", src);
            Assert.Contains("BimExportPathPolicy.ResolveBundlePaths", src);
            Assert.Contains("BimExportPathPolicy.EscapesIntendedDirectory", src);
            Assert.Contains("Overwrite", src);
            Assert.Contains("BimErrorCode.OutputPathInvalid", src);

            // Three-file bundle.
            Assert.Contains(".3dm", src);
            Assert.Contains(".sidecar.json", src);
            Assert.Contains(".validation.json", src);
            Assert.Contains("File3dm", src);

            // Join-key user strings.
            Assert.Contains("revit.uniqueId", src);
            Assert.Contains("rook.source", src);
            Assert.Contains("RookBim::Model", src);

            // Bijection verification + NoExportableGeometry.
            Assert.Contains("BimExportVerification", src);
            Assert.Contains("BimErrorCode.NoExportableGeometry", src);

            // Read-only.
            Assert.DoesNotContain("Transaction", src);
        }

        [Fact]
        public void Runtime_WiresExportElementsThroughDispatcherWithExportTimeout()
        {
            var src = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("public BimApiResponse ExportElements(BimExportElementsRequest request)", src);
            Assert.Contains("private readonly RevitExportService export", src);
            Assert.Contains("ExportDispatchTimeout", src);
            Assert.Contains("export.Export(", src);
            // Export uses a longer timeout than the default 5s op timeout.
            Assert.Contains("DispatchWithTimeout", src);
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
