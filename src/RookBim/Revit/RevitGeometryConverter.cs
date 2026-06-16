using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Autodesk.Revit.DB;

namespace RookBim.Revit
{
    /// <summary>
    /// Converts a Revit element's geometry to RhinoCommon for in-memory File3dm export.
    /// Path: in-process Rhino.Inside.Revit Brep converter (reflection) -> Face.Triangulate mesh
    /// -> bbox proxy (opt-in). Read-only: never mutates the Revit document.
    /// </summary>
    internal sealed class RevitGeometryConverter
    {
        // converted_brep: a non-tessellated Revit solid converted to a Rhino Brep via the
        // Rhino.Inside.Revit converter. NOT a geometric-exactness claim.
        public const string QualityConvertedBrep = "converted_brep";
        public const string QualityMeshFallback = "mesh_fallback";
        public const string QualityBboxOnly = "bbox_only";
        public const string QualityFailed = "failed";

        public const string RepresentationBrep = "brep";
        public const string RepresentationMesh = "mesh";
        public const string RepresentationBboxProxy = "bbox_proxy";

        private const string RhinoInsideAssemblyName = "RhinoInside.Revit";
        private const double FeetToMeters = 0.3048;

        private readonly double unitScaleFromFeet;
        private readonly MethodInfo? solidToBrep;

        public RevitGeometryConverter(double unitScaleFromFeet)
        {
            this.unitScaleFromFeet = unitScaleFromFeet;
            this.solidToBrep = ResolveSolidToBrepConverter();
        }

        public static double ScaleFromFeet(string targetUnits)
        {
            switch ((targetUnits ?? "meters").Trim().ToLowerInvariant())
            {
                case "millimeters":
                case "mm":
                    return FeetToMeters * 1000.0;
                case "centimeters":
                case "cm":
                    return FeetToMeters * 100.0;
                case "feet":
                case "ft":
                    return 1.0;
                case "inches":
                case "in":
                    return 12.0;
                case "meters":
                case "m":
                default:
                    return FeetToMeters;
            }
        }

        public RevitGeometryConversion Convert(Element element, bool allowBboxProxy)
        {
            var options = new Options
            {
                ComputeReferences = false,
                IncludeNonVisibleObjects = false,
                DetailLevel = ViewDetailLevel.Fine
            };

            var solids = CollectSolids(element.get_Geometry(options)).ToList();

            // 1. Brep path (reflection).
            if (solidToBrep != null)
            {
                var breps = new List<Rhino.Geometry.Brep>();
                foreach (var solid in solids)
                {
                    var brep = TryConvertSolidToBrep(solid);
                    if (brep != null)
                    {
                        Scale(brep);
                        breps.Add(brep);
                    }
                }

                if (breps.Count > 0)
                {
                    return RevitGeometryConversion.FromBrep(breps);
                }
            }

            // 2. Mesh fallback (Face.Triangulate).
            var mesh = TryTessellate(solids);
            if (mesh != null && mesh.Faces.Count > 0)
            {
                Scale(mesh);
                return RevitGeometryConversion.FromMesh(
                    mesh,
                    solidToBrep == null ? "rhino_inside_converter_unavailable" : "brep_conversion_failed");
            }

            // 3. Bbox proxy (opt-in).
            if (allowBboxProxy)
            {
                var box = TryBoundingBox(element);
                if (box != null)
                {
                    return RevitGeometryConversion.FromBboxProxy(box.Value);
                }
            }

            return RevitGeometryConversion.Failed(
                allowBboxProxy ? "no_geometry_extractable" : "no_brep_or_mesh_bbox_proxy_disabled");
        }

        private static IEnumerable<Solid> CollectSolids(GeometryElement? geometry)
        {
            if (geometry == null)
            {
                yield break;
            }

            foreach (var obj in geometry)
            {
                if (obj is Solid solid && solid.Volume > 0 && solid.Faces.Size > 0)
                {
                    yield return solid;
                }
                else if (obj is GeometryInstance instance)
                {
                    foreach (var inner in CollectSolids(instance.GetInstanceGeometry()))
                    {
                        yield return inner;
                    }
                }
            }
        }

        private Rhino.Geometry.Brep? TryConvertSolidToBrep(Solid solid)
        {
            try
            {
                return solidToBrep!.Invoke(null, new object[] { solid }) as Rhino.Geometry.Brep;
            }
            catch (Exception)
            {
                return null;
            }
        }

        private static Rhino.Geometry.Mesh? TryTessellate(IEnumerable<Solid> solids)
        {
            var merged = new Rhino.Geometry.Mesh();
            foreach (var solid in solids)
            {
                foreach (Face face in solid.Faces)
                {
                    Mesh triangulated;
                    try
                    {
                        triangulated = face.Triangulate();
                    }
                    catch (Exception)
                    {
                        continue;
                    }

                    if (triangulated == null)
                    {
                        continue;
                    }

                    var baseIndex = merged.Vertices.Count;
                    for (var v = 0; v < triangulated.Vertices.Count; v++)
                    {
                        var p = triangulated.Vertices[v];
                        merged.Vertices.Add(p.X, p.Y, p.Z);
                    }

                    for (var t = 0; t < triangulated.NumTriangles; t++)
                    {
                        var tri = triangulated.get_Triangle(t);
                        merged.Faces.AddFace(
                            baseIndex + (int)tri.get_Index(0),
                            baseIndex + (int)tri.get_Index(1),
                            baseIndex + (int)tri.get_Index(2));
                    }
                }
            }

            if (merged.Vertices.Count == 0)
            {
                return null;
            }

            merged.Normals.ComputeNormals();
            merged.Compact();
            return merged;
        }

        private Rhino.Geometry.Box? TryBoundingBox(Element element)
        {
            var bb = element.get_BoundingBox(null);
            if (bb == null)
            {
                return null;
            }

            var min = new Rhino.Geometry.Point3d(
                bb.Min.X * unitScaleFromFeet, bb.Min.Y * unitScaleFromFeet, bb.Min.Z * unitScaleFromFeet);
            var max = new Rhino.Geometry.Point3d(
                bb.Max.X * unitScaleFromFeet, bb.Max.Y * unitScaleFromFeet, bb.Max.Z * unitScaleFromFeet);
            var bbox = new Rhino.Geometry.BoundingBox(min, max);
            return new Rhino.Geometry.Box(bbox);
        }

        private void Scale(Rhino.Geometry.GeometryBase geometry)
        {
            if (Math.Abs(unitScaleFromFeet - 1.0) < 1e-12)
            {
                return;
            }

            var xform = Rhino.Geometry.Transform.Scale(Rhino.Geometry.Point3d.Origin, unitScaleFromFeet);
            geometry.Transform(xform);
        }

        private static MethodInfo? ResolveSolidToBrepConverter()
        {
            try
            {
                var assembly = AppDomain.CurrentDomain
                    .GetAssemblies()
                    .FirstOrDefault(candidate =>
                        string.Equals(
                            candidate.GetName().Name,
                            RhinoInsideAssemblyName,
                            StringComparison.OrdinalIgnoreCase));
                if (assembly == null)
                {
                    return null;
                }

                // RhinoInside.Revit.Convert.Geometry.GeometryDecoder.ToBrep(this Solid) -> Brep
                var decoder = assembly.GetType(
                    "RhinoInside.Revit.Convert.Geometry.GeometryDecoder",
                    throwOnError: false);

                return decoder?
                    .GetMethods(BindingFlags.Public | BindingFlags.Static)
                    .FirstOrDefault(m =>
                        m.Name == "ToBrep" &&
                        m.GetParameters().Length == 1 &&
                        m.GetParameters()[0].ParameterType == typeof(Solid) &&
                        typeof(Rhino.Geometry.Brep).IsAssignableFrom(m.ReturnType));
            }
            catch (Exception)
            {
                return null;
            }
        }
    }

    internal sealed class RevitGeometryConversion
    {
        private RevitGeometryConversion() { }

        public string Representation { get; private set; } = RevitGeometryConverter.RepresentationBrep;

        public string Quality { get; private set; } = RevitGeometryConverter.QualityFailed;

        public string? FallbackReason { get; private set; }

        public IReadOnlyList<Rhino.Geometry.Brep> Breps { get; private set; } = Array.Empty<Rhino.Geometry.Brep>();

        public Rhino.Geometry.Mesh? Mesh { get; private set; }

        public Rhino.Geometry.Box? Bbox { get; private set; }

        public bool HasGeometry
        {
            get { return Breps.Count > 0 || Mesh != null || Bbox != null; }
        }

        public static RevitGeometryConversion FromBrep(IReadOnlyList<Rhino.Geometry.Brep> breps)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationBrep,
                Quality = RevitGeometryConverter.QualityConvertedBrep,
                FallbackReason = null,
                Breps = breps
            };
        }

        public static RevitGeometryConversion FromMesh(Rhino.Geometry.Mesh mesh, string fallbackReason)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationMesh,
                Quality = RevitGeometryConverter.QualityMeshFallback,
                FallbackReason = fallbackReason,
                Mesh = mesh
            };
        }

        public static RevitGeometryConversion FromBboxProxy(Rhino.Geometry.Box box)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationBboxProxy,
                Quality = RevitGeometryConverter.QualityBboxOnly,
                FallbackReason = "geometry_unconvertible_bbox_proxy",
                Bbox = box
            };
        }

        public static RevitGeometryConversion Failed(string reason)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationBboxProxy,
                Quality = RevitGeometryConverter.QualityFailed,
                FallbackReason = reason
            };
        }
    }
}
