using System;
using System.Collections.Generic;
using System.Drawing;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace Rook.Serialization
{
    /// <summary>
    /// Serializes Rhino objects to JSON-friendly dictionaries.
    /// </summary>
    public static class RhinoSerializer
    {
        /// <summary>
        /// Serializes a RhinoObject to a dictionary.
        /// </summary>
        public static Dictionary<string, object?> SerializeObject(RhinoObject obj)
        {
            if (obj == null)
            {
                return new Dictionary<string, object?> { ["error"] = "Null object" };
            }

            var geometry = obj.Geometry;

            // Safely get layer name
            string layerPath = "Default";
            try
            {
                var doc = obj.Document;
                if (doc != null)
                {
                    var layerIndex = obj.Attributes.LayerIndex;
                    if (layerIndex >= 0 && layerIndex < doc.Layers.Count)
                    {
                        var layer = doc.Layers[layerIndex];
                        if (layer != null)
                        {
                            layerPath = layer.FullPath ?? layer.Name ?? "Default";
                        }
                    }
                }
            }
            catch
            {
                // Keep default "Default" layer name
            }

            var result = new Dictionary<string, object?>
            {
                ["id"] = obj.Id.ToString(),
                ["type"] = obj.ObjectType.ToString(),
                ["layer"] = layerPath,
                ["name"] = string.IsNullOrEmpty(obj.Attributes.Name) ? null : obj.Attributes.Name,
                ["visible"] = obj.Visible,
                ["bbox"] = geometry != null ? SerializeBoundingBox(geometry.GetBoundingBox(true)) : null
            };

            // Add color if not by layer
            if (obj.Attributes.ColorSource == ObjectColorSource.ColorFromObject)
            {
                result["color"] = SerializeColor(obj.Attributes.ObjectColor);
            }

            return result;
        }

        /// <summary>
        /// Serializes a RhinoObject with detailed geometry information.
        /// </summary>
        public static Dictionary<string, object?> SerializeObjectDetailed(RhinoObject obj)
        {
            var result = SerializeObject(obj);
            result["geometry"] = SerializeGeometry(obj.Geometry);
            result["attributes"] = SerializeAttributes(obj.Attributes);
            return result;
        }

        /// <summary>
        /// Serializes geometry details based on type.
        /// </summary>
        public static Dictionary<string, object?> SerializeGeometry(GeometryBase? geometry)
        {
            if (geometry == null)
            {
                return new Dictionary<string, object?> { ["error"] = "Null geometry" };
            }

            var result = new Dictionary<string, object?>
            {
                ["type"] = geometry.ObjectType.ToString()
            };

            switch (geometry)
            {
                case Rhino.Geometry.Point point:
                    result["location"] = SerializePoint(point.Location);
                    break;

                case PointCloud cloud:
                    result["pointCount"] = cloud.Count;
                    break;

                case LineCurve line:
                    result["start"] = SerializePoint(line.PointAtStart);
                    result["end"] = SerializePoint(line.PointAtEnd);
                    result["length"] = Math.Round(line.GetLength(), 4);
                    break;

                case PolylineCurve polyline:
                    result["pointCount"] = polyline.PointCount;
                    result["length"] = Math.Round(polyline.GetLength(), 4);
                    result["isClosed"] = polyline.IsClosed;
                    break;

                case ArcCurve arc:
                    result["center"] = SerializePoint(arc.Arc.Center);
                    result["radius"] = Math.Round(arc.Arc.Radius, 4);
                    result["angle"] = Math.Round(arc.Arc.AngleDegrees, 2);
                    result["length"] = Math.Round(arc.GetLength(), 4);
                    result["isClosed"] = arc.IsClosed;
                    result["degree"] = arc.Degree;
                    break;

                case NurbsCurve nurbsCurve:
                    result["length"] = Math.Round(nurbsCurve.GetLength(), 4);
                    result["isClosed"] = nurbsCurve.IsClosed;
                    result["degree"] = nurbsCurve.Degree;
                    result["pointCount"] = nurbsCurve.Points.Count;
                    result["domain"] = new[] { nurbsCurve.Domain.T0, nurbsCurve.Domain.T1 };
                    // Check if it's a circle
                    if (nurbsCurve.TryGetCircle(out var circle))
                    {
                        result["isCircle"] = true;
                        result["center"] = SerializePoint(circle.Center);
                        result["radius"] = Math.Round(circle.Radius, 4);
                    }
                    break;

                case Curve curve:
                    result["length"] = Math.Round(curve.GetLength(), 4);
                    result["isClosed"] = curve.IsClosed;
                    result["degree"] = curve.Degree;
                    result["domain"] = new[] { curve.Domain.T0, curve.Domain.T1 };
                    break;

                case Brep brep:
                    result["faceCount"] = brep.Faces.Count;
                    result["edgeCount"] = brep.Edges.Count;
                    result["vertexCount"] = brep.Vertices.Count;
                    result["isSolid"] = brep.IsSolid;
                    result["isManifold"] = brep.IsManifold;
                    if (brep.IsSolid)
                    {
                        var volume = brep.GetVolume();
                        if (!double.IsNaN(volume))
                            result["volume"] = Math.Round(volume, 4);
                    }
                    var area = brep.GetArea();
                    if (!double.IsNaN(area))
                        result["area"] = Math.Round(area, 4);
                    break;

                case Extrusion extrusion:
                    result["isSolid"] = extrusion.IsSolid;
                    result["capCount"] = extrusion.CapCount;
                    break;

                case Mesh mesh:
                    result["vertexCount"] = mesh.Vertices.Count;
                    result["faceCount"] = mesh.Faces.Count;
                    result["isClosed"] = mesh.IsClosed;
                    break;

                case Surface surface:
                    result["isClosed"] = surface.IsClosed(0) || surface.IsClosed(1);
                    result["domainU"] = new[] { surface.Domain(0).T0, surface.Domain(0).T1 };
                    result["domainV"] = new[] { surface.Domain(1).T0, surface.Domain(1).T1 };
                    break;
            }

            return result;
        }

        /// <summary>
        /// Serializes a Layer to a dictionary.
        /// </summary>
        public static Dictionary<string, object?> SerializeLayer(Layer layer)
        {
            return new Dictionary<string, object?>
            {
                ["id"] = layer.Id.ToString(),
                ["index"] = layer.Index,
                ["name"] = layer.Name,
                ["fullPath"] = layer.FullPath,
                ["color"] = SerializeColor(layer.Color),
                ["visible"] = layer.IsVisible,
                ["locked"] = layer.IsLocked,
                ["parentId"] = layer.ParentLayerId == Guid.Empty ? null : layer.ParentLayerId.ToString()
            };
        }

        /// <summary>
        /// Serializes object attributes.
        /// </summary>
        public static Dictionary<string, object?> SerializeAttributes(ObjectAttributes attrs)
        {
            var result = new Dictionary<string, object?>
            {
                ["name"] = attrs.Name,
                ["colorSource"] = attrs.ColorSource.ToString(),
                ["layerIndex"] = attrs.LayerIndex,
                ["materialIndex"] = attrs.MaterialIndex,
                ["linetype"] = attrs.LinetypeIndex
            };

            // Include user strings if any
            var userStrings = attrs.GetUserStrings();
            if (userStrings.Count > 0)
            {
                var dict = new Dictionary<string, string>();
                foreach (string key in userStrings.AllKeys)
                {
                    dict[key] = userStrings[key] ?? "";
                }
                result["userStrings"] = dict;
            }

            return result;
        }

        /// <summary>
        /// Serializes a Point3d to an array [x, y, z].
        /// </summary>
        public static double[] SerializePoint(Point3d point)
        {
            return new[] { Math.Round(point.X, 4), Math.Round(point.Y, 4), Math.Round(point.Z, 4) };
        }

        /// <summary>
        /// Serializes a BoundingBox to min/max arrays.
        /// </summary>
        public static Dictionary<string, double[]> SerializeBoundingBox(BoundingBox bbox)
        {
            return new Dictionary<string, double[]>
            {
                ["min"] = SerializePoint(bbox.Min),
                ["max"] = SerializePoint(bbox.Max)
            };
        }

        /// <summary>
        /// Serializes a Color to RGB dictionary.
        /// </summary>
        public static Dictionary<string, int> SerializeColor(Color color)
        {
            return new Dictionary<string, int>
            {
                ["r"] = color.R,
                ["g"] = color.G,
                ["b"] = color.B
            };
        }
    }
}
