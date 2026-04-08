using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;
using Rhino.Render;

namespace Rook.Handlers
{
    public class TextureMappingHandler
    {
        public ApiResponse ApplyBoxMapping(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body is required" };

            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body)!;

            // Parse parameters
            if (!request.TryGetValue("ids", out var idsEl))
                return new ApiResponse { Success = false, Data = "ids parameter is required" };

            var ids = idsEl.EnumerateArray().Select(e => e.GetString()!).ToList();
            if (ids.Count == 0)
                return new ApiResponse { Success = false, Data = "ids array is empty" };

            double scale = GetScale(request, doc);
            if (scale <= 0)
                return new ApiResponse { Success = false, Data = "scale must be positive" };

            int channel = 1;
            if (request.TryGetValue("channel", out var chEl))
                channel = chEl.GetInt32();

            // Process each object
            int mappedCount = 0;
            var results = new List<Dictionary<string, object>>();

            foreach (var idStr in ids)
            {
                if (!Guid.TryParse(idStr, out var guid))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "invalid GUID" });
                    continue;
                }

                var rhinoObj = doc.Objects.FindId(guid);
                if (rhinoObj == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "not found" });
                    continue;
                }

                var geometry = rhinoObj.Geometry;
                if (geometry == null || !(geometry is Brep || geometry is Mesh || geometry is Extrusion))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "unsupported geometry type" });
                    continue;
                }

                // Get oriented bounding box
                var (plane, xSize, ySize, zSize) = GetObjectOrientedBoundingBox(geometry);

                // Calculate orientation angle
                var orientationAngle = Math.Atan2(plane.XAxis.Y, plane.XAxis.X) * 180.0 / Math.PI;

                // Create scaled box mapping
                var scaledDx = new Interval(-scale / 2, scale / 2);
                var scaledDy = new Interval(-scale / 2, scale / 2);
                var scaledDz = new Interval(-scale / 2, scale / 2);

                var textureMapping = TextureMapping.CreateBoxMapping(plane, scaledDx, scaledDy, scaledDz, true);
                if (textureMapping == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to create mapping" });
                    continue;
                }

                // Clear existing and apply
                ClearTextureMappings(doc, rhinoObj.Id, channel);
                var success = doc.Objects.ModifyTextureMapping(rhinoObj.Id, channel, textureMapping);

                if (success)
                {
                    mappedCount++;
                    var objName = rhinoObj.Attributes.Name ?? idStr.Substring(0, Math.Min(8, idStr.Length));
                    results.Add(new Dictionary<string, object>
                    {
                        ["id"] = idStr,
                        ["name"] = objName,
                        ["bbox_size"] = $"{xSize:F1} x {ySize:F1} x {zSize:F1}",
                        ["uv_coverage"] = $"{xSize / scale:F2} x {ySize / scale:F2} x {zSize / scale:F2}",
                        ["orientation_angle"] = Math.Round(orientationAngle, 1)
                    });
                }
                else
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to apply mapping" });
                }
            }

            if (mappedCount > 0)
                doc.Views.Redraw();

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["mapped_count"] = mappedCount,
                    ["scale"] = scale,
                    ["channel"] = channel,
                    ["objects"] = results
                }
            };
        }

        public ApiResponse ApplyPlanarMapping(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body is required" };

            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body)!;

            // Parse parameters
            if (!request.TryGetValue("ids", out var idsEl))
                return new ApiResponse { Success = false, Data = "ids parameter is required" };

            var ids = idsEl.EnumerateArray().Select(e => e.GetString()!).ToList();
            if (ids.Count == 0)
                return new ApiResponse { Success = false, Data = "ids array is empty" };

            double scale = GetScale(request, doc);
            if (scale <= 0)
                return new ApiResponse { Success = false, Data = "scale must be positive" };

            string planeMode = "auto";
            if (request.TryGetValue("plane", out var planeEl))
                planeMode = planeEl.GetString() ?? "auto";

            int channel = 1;
            if (request.TryGetValue("channel", out var chEl))
                channel = chEl.GetInt32();

            // Process each object
            int mappedCount = 0;
            var results = new List<Dictionary<string, object>>();

            foreach (var idStr in ids)
            {
                if (!Guid.TryParse(idStr, out var guid))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "invalid GUID" });
                    continue;
                }

                var rhinoObj = doc.Objects.FindId(guid);
                if (rhinoObj == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "not found" });
                    continue;
                }

                var geometry = rhinoObj.Geometry;
                if (geometry == null || !(geometry is Brep || geometry is Mesh || geometry is Extrusion))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "unsupported geometry type" });
                    continue;
                }

                // Get mapping plane
                var (mappingPlane, planeUsed) = GetMappingPlane(geometry, planeMode);

                // Create scaled planar mapping
                var dx = new Interval(-scale / 2, scale / 2);
                var dy = new Interval(-scale / 2, scale / 2);
                var dz = new Interval(-scale / 2, scale / 2);

                var textureMapping = TextureMapping.CreatePlaneMapping(mappingPlane, dx, dy, dz);
                if (textureMapping == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to create mapping" });
                    continue;
                }

                // Clear existing and apply
                ClearTextureMappings(doc, rhinoObj.Id, channel);
                var success = doc.Objects.ModifyTextureMapping(rhinoObj.Id, channel, textureMapping);

                if (success)
                {
                    mappedCount++;
                    var objName = rhinoObj.Attributes.Name ?? idStr.Substring(0, Math.Min(8, idStr.Length));
                    var bbox = geometry.GetBoundingBox(true);
                    var bboxSize = bbox.Max - bbox.Min;
                    results.Add(new Dictionary<string, object>
                    {
                        ["id"] = idStr,
                        ["name"] = objName,
                        ["plane_used"] = planeUsed,
                        ["uv_coverage"] = $"{bboxSize.X / scale:F2} x {bboxSize.Y / scale:F2}"
                    });
                }
                else
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to apply mapping" });
                }
            }

            if (mappedCount > 0)
                doc.Views.Redraw();

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["mapped_count"] = mappedCount,
                    ["scale"] = scale,
                    ["plane"] = planeMode,
                    ["channel"] = channel,
                    ["objects"] = results
                }
            };
        }

        public ApiResponse ApplyCylinderMapping(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body is required" };

            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body)!;

            if (!request.TryGetValue("ids", out var idsEl))
                return new ApiResponse { Success = false, Data = "ids parameter is required" };

            var ids = idsEl.EnumerateArray().Select(e => e.GetString()!).ToList();
            if (ids.Count == 0)
                return new ApiResponse { Success = false, Data = "ids array is empty" };

            double scale = GetScale(request, doc);
            if (scale <= 0)
                return new ApiResponse { Success = false, Data = "scale must be positive" };

            string axisMode = "auto";
            if (request.TryGetValue("axis", out var axisEl))
                axisMode = axisEl.GetString() ?? "auto";

            bool capped = true;
            if (request.TryGetValue("capped", out var cappedEl))
                capped = cappedEl.GetBoolean();

            int channel = 1;
            if (request.TryGetValue("channel", out var chEl))
                channel = chEl.GetInt32();

            int mappedCount = 0;
            var results = new List<Dictionary<string, object>>();

            foreach (var idStr in ids)
            {
                if (!Guid.TryParse(idStr, out var guid))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "invalid GUID" });
                    continue;
                }

                var rhinoObj = doc.Objects.FindId(guid);
                if (rhinoObj == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "not found" });
                    continue;
                }

                var geometry = rhinoObj.Geometry;
                if (geometry == null || !(geometry is Brep || geometry is Mesh || geometry is Extrusion))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "unsupported geometry type" });
                    continue;
                }

                // Determine cylinder axis and oriented dimensions
                var (orientedPlane, xSize, ySize, zSize) = GetObjectOrientedBoundingBox(geometry);
                var (cylinderAxis, axisUsed) = GetCylinderAxis(geometry, axisMode, orientedPlane, xSize, ySize, zSize);

                var bbox = geometry.GetBoundingBox(true);
                var center = bbox.Center;

                // Cylinder: circumference = scale (so 1 UV u-unit = scale doc units around)
                //           height = scale (so 1 UV v-unit = scale doc units along axis)
                var cylinderRadius = scale / (2.0 * Math.PI);
                var cylinderHeight = scale;

                // Base plane perpendicular to cylinder axis, centered on object
                var baseCenter = center - cylinderAxis * (cylinderHeight / 2.0);
                var basePlane = CreatePlanePerpendicular(baseCenter, cylinderAxis);

                var circle = new Circle(basePlane, cylinderRadius);
                var cylinder = new Cylinder(circle, cylinderHeight);

                var textureMapping = TextureMapping.CreateCylinderMapping(cylinder, capped);
                if (textureMapping == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to create mapping" });
                    continue;
                }

                ClearTextureMappings(doc, rhinoObj.Id, channel);
                var success = doc.Objects.ModifyTextureMapping(rhinoObj.Id, channel, textureMapping);

                if (success)
                {
                    mappedCount++;
                    var objName = rhinoObj.Attributes.Name ?? idStr.Substring(0, Math.Min(8, idStr.Length));
                    // Compute cross-section radius and height along cylinder axis
                    var bboxSize = bbox.Max - bbox.Min;
                    results.Add(new Dictionary<string, object>
                    {
                        ["id"] = idStr,
                        ["name"] = objName,
                        ["axis_used"] = axisUsed,
                        ["bbox_size"] = $"{bboxSize.X:F1} x {bboxSize.Y:F1} x {bboxSize.Z:F1}",
                        ["capped"] = capped
                    });
                }
                else
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to apply mapping" });
                }
            }

            if (mappedCount > 0)
                doc.Views.Redraw();

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["mapped_count"] = mappedCount,
                    ["scale"] = scale,
                    ["axis"] = axisMode,
                    ["capped"] = capped,
                    ["channel"] = channel,
                    ["objects"] = results
                }
            };
        }

        public ApiResponse ApplySphericalMapping(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body is required" };

            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body)!;

            if (!request.TryGetValue("ids", out var idsEl))
                return new ApiResponse { Success = false, Data = "ids parameter is required" };

            var ids = idsEl.EnumerateArray().Select(e => e.GetString()!).ToList();
            if (ids.Count == 0)
                return new ApiResponse { Success = false, Data = "ids array is empty" };

            double scale = GetScale(request, doc);
            if (scale <= 0)
                return new ApiResponse { Success = false, Data = "scale must be positive" };

            int channel = 1;
            if (request.TryGetValue("channel", out var chEl))
                channel = chEl.GetInt32();

            int mappedCount = 0;
            var results = new List<Dictionary<string, object>>();

            foreach (var idStr in ids)
            {
                if (!Guid.TryParse(idStr, out var guid))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "invalid GUID" });
                    continue;
                }

                var rhinoObj = doc.Objects.FindId(guid);
                if (rhinoObj == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "not found" });
                    continue;
                }

                var geometry = rhinoObj.Geometry;
                if (geometry == null || !(geometry is Brep || geometry is Mesh || geometry is Extrusion))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "unsupported geometry type" });
                    continue;
                }

                var bbox = geometry.GetBoundingBox(true);
                var center = bbox.Center;

                // Sphere: equatorial circumference = scale (so 1 UV u-unit = scale doc units)
                var sphereRadius = scale / (2.0 * Math.PI);
                var sphere = new Sphere(center, sphereRadius);

                var textureMapping = TextureMapping.CreateSphereMapping(sphere);
                if (textureMapping == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to create mapping" });
                    continue;
                }

                ClearTextureMappings(doc, rhinoObj.Id, channel);
                var success = doc.Objects.ModifyTextureMapping(rhinoObj.Id, channel, textureMapping);

                if (success)
                {
                    mappedCount++;
                    var objName = rhinoObj.Attributes.Name ?? idStr.Substring(0, Math.Min(8, idStr.Length));
                    var bboxSize = bbox.Max - bbox.Min;
                    var maxDim = Math.Max(bboxSize.X, Math.Max(bboxSize.Y, bboxSize.Z));
                    results.Add(new Dictionary<string, object>
                    {
                        ["id"] = idStr,
                        ["name"] = objName,
                        ["bbox_size"] = $"{bboxSize.X:F1} x {bboxSize.Y:F1} x {bboxSize.Z:F1}",
                        ["bounding_radius"] = Math.Round(maxDim / 2.0, 1)
                    });
                }
                else
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr, ["error"] = "failed to apply mapping" });
                }
            }

            if (mappedCount > 0)
                doc.Views.Redraw();

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["mapped_count"] = mappedCount,
                    ["scale"] = scale,
                    ["channel"] = channel,
                    ["objects"] = results
                }
            };
        }

        // ── Private helpers ──────────────────────────────────────────────

        private static double GetScale(Dictionary<string, JsonElement> request, RhinoDoc doc)
        {
            if (request.TryGetValue("scale", out var scaleEl))
                return scaleEl.GetDouble();

            return GetDefaultScale(doc.ModelUnitSystem);
        }

        private static double GetDefaultScale(UnitSystem units)
        {
            switch (units)
            {
                case UnitSystem.Millimeters: return 1000.0;
                case UnitSystem.Centimeters: return 100.0;
                case UnitSystem.Meters: return 1.0;
                case UnitSystem.Inches: return 39.37;
                case UnitSystem.Feet: return 3.28;
                case UnitSystem.Yards: return 0.328;
                default: return 1000.0;
            }
        }

        private static (Vector3d primary, Vector3d secondary) CalculateObjectOrientationXY(GeometryBase geometry)
        {
            var edgeData = new List<(Vector3d vector, double length, double angle)>();

            if (geometry is Brep brep)
            {
                for (int i = 0; i < brep.Edges.Count; i++)
                {
                    var edge = brep.Edges[i];
                    if (!edge.IsValid) continue;

                    var domain = edge.Domain;
                    var startPoint = edge.PointAt(domain.Min);
                    var endPoint = edge.PointAt(domain.Max);

                    var edgeVector = endPoint - startPoint;
                    var edgeVectorXY = new Vector3d(edgeVector.X, edgeVector.Y, 0);
                    var edgeLengthXY = edgeVectorXY.Length;

                    if (edgeLengthXY > 0.001)
                    {
                        edgeVectorXY.Unitize();
                        var edgeAngle = Math.Atan2(edgeVectorXY.Y, edgeVectorXY.X) * 180.0 / Math.PI;
                        if (edgeAngle < 0)
                            edgeAngle += 180;

                        edgeData.Add((edgeVectorXY, edgeLengthXY, edgeAngle));
                    }
                }
            }
            else if (geometry is Extrusion extrusion)
            {
                var brepForm = extrusion.ToBrep();
                if (brepForm != null)
                    return CalculateObjectOrientationXY(brepForm);
            }

            // Fall back to world axes if not enough data
            if (edgeData.Count < 2)
                return (Vector3d.XAxis, Vector3d.YAxis);

            // Group edges by similar angles (within 2 degrees)
            var angleGroups = new Dictionary<double, List<(Vector3d vector, double length, double angle)>>();

            foreach (var (edgeVec, edgeLength, edgeAngle) in edgeData)
            {
                bool foundGroup = false;
                foreach (var groupAngle in angleGroups.Keys.ToList())
                {
                    if (Math.Abs(edgeAngle - groupAngle) < 2.0)
                    {
                        angleGroups[groupAngle].Add((edgeVec, edgeLength, edgeAngle));
                        foundGroup = true;
                        break;
                    }
                }

                if (!foundGroup)
                {
                    angleGroups[edgeAngle] = new List<(Vector3d vector, double length, double angle)>
                    {
                        (edgeVec, edgeLength, edgeAngle)
                    };
                }
            }

            // Find the group with the most total edge length
            var sortedGroups = angleGroups
                .Select(kvp => new { Angle = kvp.Key, TotalLength = kvp.Value.Sum(data => data.length) })
                .OrderByDescending(x => x.TotalLength)
                .ToList();

            if (sortedGroups.Count >= 1)
            {
                var bestAngleDeg = sortedGroups[0].Angle;
                var bestAngleRad = bestAngleDeg * Math.PI / 180.0;
                var primaryAxis = new Vector3d(Math.Cos(bestAngleRad), Math.Sin(bestAngleRad), 0);
                var secondaryAxis = new Vector3d(-Math.Sin(bestAngleRad), Math.Cos(bestAngleRad), 0);

                primaryAxis.Unitize();
                secondaryAxis.Unitize();

                return (primaryAxis, secondaryAxis);
            }

            return (Vector3d.XAxis, Vector3d.YAxis);
        }

        private static (Plane plane, double xSize, double ySize, double zSize)
            GetObjectOrientedBoundingBox(GeometryBase geometry)
        {
            var bbox = geometry.GetBoundingBox(true);
            var (primaryAxis, secondaryAxis) = CalculateObjectOrientationXY(geometry);
            var center = bbox.Center;
            var plane = new Plane(center, primaryAxis, secondaryAxis);

            // Project bounding box corners onto oriented axes
            var corners = new Point3d[]
            {
                new Point3d(bbox.Min.X, bbox.Min.Y, bbox.Min.Z),
                new Point3d(bbox.Max.X, bbox.Min.Y, bbox.Min.Z),
                new Point3d(bbox.Max.X, bbox.Max.Y, bbox.Min.Z),
                new Point3d(bbox.Min.X, bbox.Max.Y, bbox.Min.Z),
                new Point3d(bbox.Min.X, bbox.Min.Y, bbox.Max.Z),
                new Point3d(bbox.Max.X, bbox.Min.Y, bbox.Max.Z),
                new Point3d(bbox.Max.X, bbox.Max.Y, bbox.Max.Z),
                new Point3d(bbox.Min.X, bbox.Max.Y, bbox.Max.Z)
            };

            var xProjections = new List<double>();
            var yProjections = new List<double>();
            var zProjections = new List<double>();

            foreach (var corner in corners)
            {
                var localVec = corner - center;
                xProjections.Add(localVec * primaryAxis);
                yProjections.Add(localVec * secondaryAxis);
                zProjections.Add(localVec * Vector3d.ZAxis);
            }

            var xSize = xProjections.Max() - xProjections.Min();
            var ySize = yProjections.Max() - yProjections.Min();
            var zSize = zProjections.Max() - zProjections.Min();

            return (plane, xSize, ySize, zSize);
        }

        private static (Plane plane, string planeUsed) GetMappingPlane(GeometryBase geometry, string planeMode)
        {
            var bbox = geometry.GetBoundingBox(true);
            var center = bbox.Center;

            switch (planeMode.ToLowerInvariant())
            {
                case "world_xy":
                    return (new Plane(center, Vector3d.XAxis, Vector3d.YAxis), "world_xy");

                case "world_yz":
                    return (new Plane(center, Vector3d.YAxis, Vector3d.ZAxis), "world_yz");

                case "world_zx":
                    return (new Plane(center, Vector3d.ZAxis, Vector3d.XAxis), "world_zx");

                case "auto":
                default:
                    var (primary, secondary) = CalculateObjectOrientationXY(geometry);
                    return (new Plane(center, primary, secondary), "auto");
            }
        }

        private static (Vector3d axis, string name) GetCylinderAxis(
            GeometryBase geometry, string mode,
            Plane orientedPlane, double xSize, double ySize, double zSize)
        {
            switch (mode.ToLowerInvariant())
            {
                case "x": return (Vector3d.XAxis, "x");
                case "y": return (Vector3d.YAxis, "y");
                case "z": return (Vector3d.ZAxis, "z");
                case "auto":
                default:
                    // Pick the longest dimension of the oriented bounding box as the axis
                    if (zSize >= xSize && zSize >= ySize)
                        return (Vector3d.ZAxis, "auto_z");
                    if (xSize >= ySize)
                        return (orientedPlane.XAxis, "auto_primary");
                    return (orientedPlane.YAxis, "auto_secondary");
            }
        }

        private static Plane CreatePlanePerpendicular(Point3d origin, Vector3d normal)
        {
            // Build a plane perpendicular to the given normal at the given origin
            // Math: CrossProduct(xDir, CrossProduct(normal, xDir)) = normal (BAC-CAB identity)
            Vector3d xDir;
            if (Math.Abs(normal * Vector3d.ZAxis) < 0.99)
                xDir = Vector3d.CrossProduct(Vector3d.ZAxis, normal);
            else
                xDir = Vector3d.CrossProduct(Vector3d.XAxis, normal);

            if (!xDir.Unitize())
                return new Plane(origin, normal);

            var yDir = Vector3d.CrossProduct(normal, xDir);
            if (!yDir.Unitize())
                return new Plane(origin, normal);

            return new Plane(origin, xDir, yDir);
        }

        private static void ClearTextureMappings(RhinoDoc doc, Guid objId, int targetChannel)
        {
            // Clear mappings on channels 1-8
            for (int ch = 1; ch <= 8; ch++)
            {
                try
                {
                    doc.Objects.ModifyTextureMapping(objId, ch, null);
                }
                catch
                {
                    // Channel may not exist
                }
            }
        }
    }
}
