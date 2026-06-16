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
