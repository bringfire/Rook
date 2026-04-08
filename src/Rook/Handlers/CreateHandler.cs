using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text.Json;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;
using Rhino.Display;
using Rook.Serialization;

namespace Rook.Handlers
{
    /// <summary>
    /// Handles /create endpoint - creates basic geometry.
    /// </summary>
    public class CreateHandler
    {
        /// <summary>
        /// POST /create - Creates geometry in the document.
        /// Body varies by type, see examples below.
        /// </summary>
        public ApiResponse CreateGeometry(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required with 'type' field" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null || !request.TryGetValue("type", out var typeElement))
            {
                return new ApiResponse { Success = false, Data = "Missing 'type' field in request" };
            }

            var type = typeElement.GetString()?.ToUpperInvariant();
            if (string.IsNullOrEmpty(type))
            {
                return new ApiResponse { Success = false, Data = "Invalid type" };
            }

            var record = doc.BeginUndoRecord($"Create {type}");

            try
            {
                // Handle annotation types that need special add methods
                Guid? annotationGuid = type switch
                {
                    "TEXT" => CreateText(doc, request),
                    "DIMENSION_LINEAR" or "DIMENSIONLINEAR" or "LINEAR_DIMENSION" => CreateLinearDimension(doc, request),
                    "DIMENSION_ALIGNED" or "DIMENSIONALIGNED" or "ALIGNED_DIMENSION" => CreateAlignedDimension(doc, request),
                    "DIMENSION_RADIUS" or "DIMENSIONRADIUS" or "RADIUS_DIMENSION" => CreateRadiusDimension(doc, request),
                    "DIMENSION_DIAMETER" or "DIMENSIONDIAMETER" or "DIAMETER_DIMENSION" => CreateDiameterDimension(doc, request),
                    "DIMENSION_ANGLE" or "DIMENSIONANGLE" or "ANGLE_DIMENSION" => CreateAngleDimension(doc, request),
                    "LEADER" => CreateLeader(doc, request),
                    "HATCH" => CreateHatch(doc, request),
                    "DOT" => CreateDot(doc, request),
                    _ => null
                };

                if (annotationGuid.HasValue)
                {
                    if (annotationGuid.Value == Guid.Empty)
                    {
                        return new ApiResponse { Success = false, Data = $"Failed to create {type}" };
                    }
                    var annotationObj = doc.Objects.FindId(annotationGuid.Value);
                    doc.Views.Redraw();
                    return new ApiResponse
                    {
                        Success = true,
                        Data = annotationObj != null ? RhinoSerializer.SerializeObject(annotationObj) : new Dictionary<string, object> { ["id"] = annotationGuid.Value.ToString() }
                    };
                }

                GeometryBase? geometry = type switch
                {
                    "POINT" => CreatePoint(request),
                    "LINE" => CreateLine(request),
                    "POLYLINE" => CreatePolyline(request),
                    "CIRCLE" => CreateCircle(request),
                    "ARC" => CreateArc(request),
                    "RECTANGLE" => CreateRectangle(request),
                    "BOX" => CreateBox(request),
                    "SPHERE" => CreateSphere(request),
                    "CYLINDER" => CreateCylinder(request),
                    "CONE" => CreateCone(request),
                    // Surface creation operations
                    "LOFT" => CreateLoft(doc, request),
                    "SWEEP1" => CreateSweep1(doc, request),
                    "SWEEP2" => CreateSweep2(doc, request),
                    "REVOLVE" => CreateRevolve(doc, request),
                    "EXTRUDE" => CreateExtrude(doc, request),
                    "PIPE" => CreatePipe(doc, request),
                    "PLANAR_SURFACE" or "PLANARSURFACE" => CreatePlanarSurface(doc, request),
                    // Curve types
                    "INTERPOLATED_CURVE" or "INTERPOLATEDCURVE" or "INTERP_CURVE" => CreateInterpolatedCurve(request),
                    "CONTROL_POINT_CURVE" or "CONTROLPOINTCURVE" or "CP_CURVE" => CreateControlPointCurve(request),
                    _ => null
                };

                if (geometry == null)
                {
                    return new ApiResponse { Success = false, Data = $"Unknown or invalid geometry type: {type}" };
                }

                // Set up attributes
                var attributes = new ObjectAttributes();

                if (request.TryGetValue("name", out var nameEl))
                {
                    attributes.Name = nameEl.GetString() ?? "";
                }

                if (request.TryGetValue("layer", out var layerEl))
                {
                    var layerPath = layerEl.GetString();
                    if (!string.IsNullOrEmpty(layerPath))
                    {
                        var layerIndex = doc.Layers.FindByFullPath(layerPath, -1);
                        if (layerIndex >= 0)
                        {
                            attributes.LayerIndex = layerIndex;
                        }
                    }
                }

                if (request.TryGetValue("color", out var colorEl))
                {
                    var color = ParseColor(colorEl);
                    if (color.HasValue)
                    {
                        attributes.ObjectColor = color.Value;
                        attributes.ColorSource = ObjectColorSource.ColorFromObject;
                    }
                }

                // Add the object
                var guid = doc.Objects.Add(geometry, attributes);
                if (guid == Guid.Empty)
                {
                    return new ApiResponse { Success = false, Data = "Failed to add object to document" };
                }

                var obj = doc.Objects.FindId(guid);
                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = obj != null ? RhinoSerializer.SerializeObject(obj) : new Dictionary<string, object> { ["id"] = guid.ToString() }
                };
            }
            catch (Exception ex)
            {
                doc.Undo();
                return new ApiResponse { Success = false, Data = $"Create failed: {ex.Message}" };
            }
            finally
            {
                doc.EndUndoRecord(record);
            }
        }

        private Rhino.Geometry.Point? CreatePoint(Dictionary<string, JsonElement> request)
        {
            var pt = GetPoint3d(request, "point") ?? GetPoint3d(request, "location") ?? Point3d.Origin;
            return new Rhino.Geometry.Point(pt);
        }

        private LineCurve? CreateLine(Dictionary<string, JsonElement> request)
        {
            var start = GetPoint3d(request, "start");
            var end = GetPoint3d(request, "end");

            if (start == null || end == null)
                return null;

            return new LineCurve(start.Value, end.Value);
        }

        private PolylineCurve? CreatePolyline(Dictionary<string, JsonElement> request)
        {
            if (!request.TryGetValue("points", out var pointsEl))
                return null;

            var points = pointsEl.EnumerateArray()
                .Select(ParsePoint3d)
                .Where(p => p.HasValue)
                .Select(p => p!.Value)
                .ToList();

            if (points.Count < 2)
                return null;

            return new PolylineCurve(points);
        }

        private ArcCurve? CreateCircle(Dictionary<string, JsonElement> request)
        {
            var center = GetPoint3d(request, "center") ?? Point3d.Origin;
            var radius = GetDouble(request, "radius") ?? 1.0;
            var plane = GetPlane(request, "plane") ?? Plane.WorldXY;

            plane.Origin = center;
            var circle = new Circle(plane, radius);
            return new ArcCurve(circle);
        }

        private ArcCurve? CreateArc(Dictionary<string, JsonElement> request)
        {
            var center = GetPoint3d(request, "center") ?? Point3d.Origin;
            var radius = GetDouble(request, "radius") ?? 1.0;
            var startAngle = GetDouble(request, "startAngle") ?? 0.0;
            var endAngle = GetDouble(request, "endAngle") ?? 90.0;

            var plane = Plane.WorldXY;
            plane.Origin = center;
            var arc = new Arc(plane, radius, RhinoMath.ToRadians(endAngle - startAngle));
            arc.Transform(Transform.Rotation(RhinoMath.ToRadians(startAngle), plane.ZAxis, center));
            return new ArcCurve(arc);
        }

        private PolylineCurve? CreateRectangle(Dictionary<string, JsonElement> request)
        {
            var origin = GetPoint3d(request, "origin") ?? GetPoint3d(request, "corner") ?? Point3d.Origin;
            var width = GetDouble(request, "width") ?? 1.0;
            var height = GetDouble(request, "height") ?? 1.0;
            var plane = GetPlane(request, "plane") ?? Plane.WorldXY;

            plane.Origin = origin;
            var rect = new Rectangle3d(plane, width, height);
            return rect.ToPolyline().ToPolylineCurve();
        }

        private Brep? CreateBox(Dictionary<string, JsonElement> request)
        {
            var origin = GetPoint3d(request, "origin") ?? GetPoint3d(request, "corner") ?? Point3d.Origin;
            var width = GetDouble(request, "width") ?? GetDouble(request, "x") ?? 1.0;
            var depth = GetDouble(request, "depth") ?? GetDouble(request, "y") ?? 1.0;
            var height = GetDouble(request, "height") ?? GetDouble(request, "z") ?? 1.0;
            var plane = GetPlane(request, "plane") ?? Plane.WorldXY;

            plane.Origin = origin;
            var box = new Box(plane, new Interval(0, width), new Interval(0, depth), new Interval(0, height));
            return box.ToBrep();
        }

        private Brep? CreateSphere(Dictionary<string, JsonElement> request)
        {
            var center = GetPoint3d(request, "center") ?? Point3d.Origin;
            var radius = GetDouble(request, "radius") ?? 1.0;

            var sphere = new Sphere(center, radius);
            return sphere.ToBrep();
        }

        private Brep? CreateCylinder(Dictionary<string, JsonElement> request)
        {
            var center = GetPoint3d(request, "center") ?? GetPoint3d(request, "base") ?? Point3d.Origin;
            var radius = GetDouble(request, "radius") ?? 1.0;
            var height = GetDouble(request, "height") ?? 1.0;

            var plane = Plane.WorldXY;
            plane.Origin = center;
            var circle = new Circle(plane, radius);
            var cylinder = new Cylinder(circle, height);
            return cylinder.ToBrep(capBottom: true, capTop: true);
        }

        private Brep? CreateCone(Dictionary<string, JsonElement> request)
        {
            var center = GetPoint3d(request, "center") ?? GetPoint3d(request, "base") ?? Point3d.Origin;
            var radius = GetDouble(request, "radius") ?? 1.0;
            var height = GetDouble(request, "height") ?? 1.0;

            var plane = Plane.WorldXY;
            plane.Origin = center;
            var cone = new Cone(plane, height, radius);
            return cone.ToBrep(capBottom: true);
        }

        // Helper methods
        private Point3d? GetPoint3d(Dictionary<string, JsonElement> request, string key)
        {
            if (!request.TryGetValue(key, out var element))
                return null;
            return ParsePoint3d(element);
        }

        private Point3d? ParsePoint3d(JsonElement element)
        {
            if (element.ValueKind == JsonValueKind.Array)
            {
                var arr = element.EnumerateArray().ToArray();
                if (arr.Length >= 3)
                {
                    return new Point3d(
                        arr[0].GetDouble(),
                        arr[1].GetDouble(),
                        arr[2].GetDouble()
                    );
                }
                if (arr.Length == 2)
                {
                    return new Point3d(arr[0].GetDouble(), arr[1].GetDouble(), 0);
                }
            }
            else if (element.ValueKind == JsonValueKind.Object)
            {
                double x = 0, y = 0, z = 0;
                if (element.TryGetProperty("x", out var xEl)) x = xEl.GetDouble();
                if (element.TryGetProperty("y", out var yEl)) y = yEl.GetDouble();
                if (element.TryGetProperty("z", out var zEl)) z = zEl.GetDouble();
                return new Point3d(x, y, z);
            }
            return null;
        }

        private double? GetDouble(Dictionary<string, JsonElement> request, string key)
        {
            if (request.TryGetValue(key, out var element) && element.ValueKind == JsonValueKind.Number)
                return element.GetDouble();
            return null;
        }

        private Plane? GetPlane(Dictionary<string, JsonElement> request, string key)
        {
            if (!request.TryGetValue(key, out var element))
                return null;

            if (element.ValueKind == JsonValueKind.String)
            {
                return element.GetString()?.ToUpperInvariant() switch
                {
                    "XY" or "WORLDXY" => Plane.WorldXY,
                    "XZ" or "WORLDXZ" => Plane.WorldZX,
                    "YZ" or "WORLDYZ" => Plane.WorldYZ,
                    _ => null
                };
            }

            return null;
        }

        private Color? ParseColor(JsonElement element)
        {
            if (element.ValueKind == JsonValueKind.Array)
            {
                var arr = element.EnumerateArray().ToArray();
                if (arr.Length >= 3)
                {
                    return Color.FromArgb(
                        arr[0].GetInt32(),
                        arr[1].GetInt32(),
                        arr[2].GetInt32()
                    );
                }
            }
            else if (element.ValueKind == JsonValueKind.Object)
            {
                int r = 0, g = 0, b = 0;
                if (element.TryGetProperty("r", out var rEl)) r = rEl.GetInt32();
                if (element.TryGetProperty("g", out var gEl)) g = gEl.GetInt32();
                if (element.TryGetProperty("b", out var bEl)) b = bEl.GetInt32();
                return Color.FromArgb(r, g, b);
            }
            else if (element.ValueKind == JsonValueKind.String)
            {
                var colorStr = element.GetString();
                if (!string.IsNullOrEmpty(colorStr))
                {
                    try { return ColorTranslator.FromHtml(colorStr); }
                    catch { }
                }
            }
            return null;
        }

        // Helper to get curve from document by ID
        private Curve? GetCurve(RhinoDoc doc, string? id)
        {
            if (string.IsNullOrEmpty(id) || !Guid.TryParse(id, out var guid))
                return null;

            var obj = doc.Objects.FindId(guid);
            return obj?.Geometry as Curve;
        }

        // Helper to get multiple curves from curveIds array
        private List<Curve> GetCurves(RhinoDoc doc, Dictionary<string, JsonElement> request, string key = "curveIds")
        {
            var curves = new List<Curve>();
            if (!request.TryGetValue(key, out var idsElement))
                return curves;

            foreach (var el in idsElement.EnumerateArray())
            {
                var curve = GetCurve(doc, el.GetString());
                if (curve != null)
                    curves.Add(curve);
            }
            return curves;
        }

        // Helper to get vector from request
        private Vector3d? GetVector3d(Dictionary<string, JsonElement> request, string key)
        {
            if (!request.TryGetValue(key, out var element))
                return null;
            var pt = ParsePoint3d(element);
            if (pt.HasValue)
                return new Vector3d(pt.Value);
            return null;
        }

        // Helper to get bool from request
        private bool GetBool(Dictionary<string, JsonElement> request, string key, bool defaultValue = false)
        {
            if (request.TryGetValue(key, out var element))
            {
                if (element.ValueKind == JsonValueKind.True) return true;
                if (element.ValueKind == JsonValueKind.False) return false;
            }
            return defaultValue;
        }

        /// <summary>
        /// Creates a lofted surface through multiple curves.
        /// { "type": "LOFT", "curveIds": ["guid1", "guid2", ...], "closed": false }
        /// </summary>
        private Brep? CreateLoft(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var curves = GetCurves(doc, request);
            if (curves.Count < 2)
                return null;

            var closed = GetBool(request, "closed", false);
            var tolerance = doc.ModelAbsoluteTolerance;

            var loftType = closed ? LoftType.Tight : LoftType.Normal;
            var breps = Brep.CreateFromLoft(curves, Point3d.Unset, Point3d.Unset, loftType, closed);

            return breps?.FirstOrDefault();
        }

        /// <summary>
        /// Creates a swept surface along one rail.
        /// { "type": "SWEEP1", "railId": "guid", "profileIds": ["guid1", "guid2"] }
        /// or { "type": "SWEEP1", "railId": "guid", "profileId": "guid" }
        /// </summary>
        private Brep? CreateSweep1(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // Get rail curve
            string? railId = null;
            if (request.TryGetValue("railId", out var railEl))
                railId = railEl.GetString();
            var rail = GetCurve(doc, railId);
            if (rail == null)
                return null;

            // Get profile curves
            var profiles = new List<Curve>();
            if (request.TryGetValue("profileIds", out var profilesEl))
            {
                foreach (var el in profilesEl.EnumerateArray())
                {
                    var curve = GetCurve(doc, el.GetString());
                    if (curve != null)
                        profiles.Add(curve);
                }
            }
            else if (request.TryGetValue("profileId", out var profileEl))
            {
                var curve = GetCurve(doc, profileEl.GetString());
                if (curve != null)
                    profiles.Add(curve);
            }

            if (profiles.Count == 0)
                return null;

            var tolerance = doc.ModelAbsoluteTolerance;
            var sweep = new SweepOneRail();
            sweep.AngleToleranceRadians = doc.ModelAngleToleranceRadians;
            sweep.ClosedSweep = GetBool(request, "closed", false);

            var breps = sweep.PerformSweep(rail, profiles);
            return breps?.FirstOrDefault();
        }

        /// <summary>
        /// Creates a swept surface along two rails.
        /// { "type": "SWEEP2", "rail1Id": "guid", "rail2Id": "guid", "profileIds": ["guid1"] }
        /// </summary>
        private Brep? CreateSweep2(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // Get rail curves
            string? rail1Id = null, rail2Id = null;
            if (request.TryGetValue("rail1Id", out var rail1El))
                rail1Id = rail1El.GetString();
            if (request.TryGetValue("rail2Id", out var rail2El))
                rail2Id = rail2El.GetString();

            var rail1 = GetCurve(doc, rail1Id);
            var rail2 = GetCurve(doc, rail2Id);
            if (rail1 == null || rail2 == null)
                return null;

            // Get profile curves
            var profiles = new List<Curve>();
            if (request.TryGetValue("profileIds", out var profilesEl))
            {
                foreach (var el in profilesEl.EnumerateArray())
                {
                    var curve = GetCurve(doc, el.GetString());
                    if (curve != null)
                        profiles.Add(curve);
                }
            }
            else if (request.TryGetValue("profileId", out var profileEl))
            {
                var curve = GetCurve(doc, profileEl.GetString());
                if (curve != null)
                    profiles.Add(curve);
            }

            if (profiles.Count == 0)
                return null;

            var sweep = new SweepTwoRail();
            sweep.AngleToleranceRadians = doc.ModelAngleToleranceRadians;
            sweep.ClosedSweep = GetBool(request, "closed", false);

            var breps = sweep.PerformSweep(rail1, rail2, profiles);
            return breps?.FirstOrDefault();
        }

        /// <summary>
        /// Creates a surface of revolution.
        /// { "type": "REVOLVE", "curveId": "guid", "axis": { "origin": [0,0,0], "direction": [0,0,1] }, "angle": 360 }
        /// </summary>
        private Brep? CreateRevolve(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // Get profile curve
            string? curveId = null;
            if (request.TryGetValue("curveId", out var curveEl))
                curveId = curveEl.GetString();
            var curve = GetCurve(doc, curveId);
            if (curve == null)
                return null;

            // Get axis
            Point3d axisOrigin = Point3d.Origin;
            Vector3d axisDirection = Vector3d.ZAxis;

            if (request.TryGetValue("axis", out var axisEl))
            {
                if (axisEl.TryGetProperty("origin", out var originEl))
                {
                    var pt = ParsePoint3d(originEl);
                    if (pt.HasValue) axisOrigin = pt.Value;
                }
                if (axisEl.TryGetProperty("direction", out var dirEl))
                {
                    var pt = ParsePoint3d(dirEl);
                    if (pt.HasValue) axisDirection = new Vector3d(pt.Value);
                }
            }
            else
            {
                // Default axis through origin along Z
                if (request.TryGetValue("axisOrigin", out var aoEl))
                {
                    var pt = ParsePoint3d(aoEl);
                    if (pt.HasValue) axisOrigin = pt.Value;
                }
                if (request.TryGetValue("axisDirection", out var adEl))
                {
                    var pt = ParsePoint3d(adEl);
                    if (pt.HasValue) axisDirection = new Vector3d(pt.Value);
                }
            }

            var axis = new Line(axisOrigin, axisOrigin + axisDirection);

            // Get angle (degrees, default 360)
            var angleDegrees = GetDouble(request, "angle") ?? 360.0;
            var angleRadians = RhinoMath.ToRadians(angleDegrees);

            var rev = RevSurface.Create(curve, axis, 0, angleRadians);
            return rev?.ToBrep();
        }

        /// <summary>
        /// Extrudes a curve in a direction.
        /// { "type": "EXTRUDE", "curveId": "guid", "direction": [0,0,10], "cap": true }
        /// </summary>
        private Brep? CreateExtrude(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // Get curve
            string? curveId = null;
            if (request.TryGetValue("curveId", out var curveEl))
                curveId = curveEl.GetString();
            var curve = GetCurve(doc, curveId);
            if (curve == null)
                return null;

            // Get direction
            var direction = GetVector3d(request, "direction");
            if (direction == null || direction.Value.IsZero)
            {
                // Default to Z direction with height
                var height = GetDouble(request, "height") ?? 10.0;
                direction = new Vector3d(0, 0, height);
            }

            var cap = GetBool(request, "cap", true);

            // Create extrusion
            var surface = Surface.CreateExtrusion(curve, direction.Value);
            if (surface == null)
                return null;

            var brep = surface.ToBrep();
            if (brep == null)
                return null;

            // Cap the ends if closed curve and cap requested
            if (cap && curve.IsClosed)
            {
                brep = brep.CapPlanarHoles(doc.ModelAbsoluteTolerance);
            }

            return brep;
        }

        /// <summary>
        /// Creates a pipe along a curve.
        /// { "type": "PIPE", "curveId": "guid", "radius": 5 }
        /// or { "type": "PIPE", "curveId": "guid", "startRadius": 5, "endRadius": 10 }
        /// </summary>
        private Brep? CreatePipe(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // Get curve
            string? curveId = null;
            if (request.TryGetValue("curveId", out var curveEl))
                curveId = curveEl.GetString();
            var curve = GetCurve(doc, curveId);
            if (curve == null)
                return null;

            // Get radius/radii
            var radius = GetDouble(request, "radius");
            var startRadius = GetDouble(request, "startRadius") ?? radius ?? 1.0;
            var endRadius = GetDouble(request, "endRadius") ?? startRadius;

            var cap = GetBool(request, "cap", true);
            var tolerance = doc.ModelAbsoluteTolerance;

            Brep[]? breps = null;
            var capType = cap ? PipeCapMode.Round : PipeCapMode.None;

            // Try variable radius pipe if radii differ
            if (Math.Abs(startRadius - endRadius) > tolerance)
            {
                // Build parameters for variable radius
                var parameters = new List<double> { curve.Domain.T0, curve.Domain.T1 };
                var radii = new List<double> { startRadius, endRadius };

                breps = Brep.CreatePipe(curve, parameters, radii, false, capType, true, tolerance, tolerance);
            }

            // If variable radius failed or same radius, use simpler overload
            if (breps == null || breps.Length == 0)
            {
                breps = Brep.CreatePipe(curve, startRadius, false, capType, true, tolerance, tolerance);
            }

            return breps?.FirstOrDefault();
        }

        /// <summary>
        /// Creates a planar surface from a closed curve.
        /// { "type": "PLANAR_SURFACE", "curveId": "guid" }
        /// or { "type": "PLANAR_SURFACE", "curveIds": ["guid1", "guid2"] }
        /// </summary>
        private Brep? CreatePlanarSurface(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var curves = new List<Curve>();

            // Single curve
            if (request.TryGetValue("curveId", out var curveEl))
            {
                var curve = GetCurve(doc, curveEl.GetString());
                if (curve != null)
                    curves.Add(curve);
            }

            // Multiple curves (boundary with holes)
            curves.AddRange(GetCurves(doc, request));

            if (curves.Count == 0)
                return null;

            var breps = Brep.CreatePlanarBreps(curves, doc.ModelAbsoluteTolerance);
            return breps?.FirstOrDefault();
        }

        /// <summary>
        /// Creates an interpolated curve through points.
        /// { "type": "INTERPOLATED_CURVE", "points": [[0,0,0],[5,5,0],[10,0,0]], "degree": 3 }
        /// </summary>
        private Curve? CreateInterpolatedCurve(Dictionary<string, JsonElement> request)
        {
            var points = new List<Point3d>();

            if (request.TryGetValue("points", out var pointsEl))
            {
                foreach (var ptEl in pointsEl.EnumerateArray())
                {
                    var pt = ParsePoint3d(ptEl);
                    if (pt.HasValue)
                        points.Add(pt.Value);
                }
            }

            if (points.Count < 2)
                return null;

            int degree = (int)(GetDouble(request, "degree") ?? 3);
            if (degree < 1) degree = 1;
            if (degree > points.Count - 1) degree = points.Count - 1;

            // Create interpolated curve through points
            return Curve.CreateInterpolatedCurve(points, degree);
        }

        /// <summary>
        /// Creates a NURBS curve with control points.
        /// { "type": "CONTROL_POINT_CURVE", "points": [[0,0,0],[5,5,0],[10,0,0]], "degree": 3 }
        /// </summary>
        private Curve? CreateControlPointCurve(Dictionary<string, JsonElement> request)
        {
            var points = new List<Point3d>();

            if (request.TryGetValue("points", out var pointsEl))
            {
                foreach (var ptEl in pointsEl.EnumerateArray())
                {
                    var pt = ParsePoint3d(ptEl);
                    if (pt.HasValue)
                        points.Add(pt.Value);
                }
            }

            if (points.Count < 2)
                return null;

            int degree = (int)(GetDouble(request, "degree") ?? 3);
            if (degree < 1) degree = 1;
            if (degree > points.Count - 1) degree = points.Count - 1;

            // Create NURBS curve with control points
            return Curve.CreateControlPointCurve(points, degree);
        }

        #region Annotation Creation Methods

        /// <summary>
        /// Creates a text annotation.
        /// { "type": "TEXT", "text": "Hello", "point": [0,0,0], "height": 5, "font": "Arial", "bold": false, "italic": false }
        /// </summary>
        private Guid? CreateText(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var text = "";
            if (request.TryGetValue("text", out var textEl))
                text = textEl.GetString() ?? "";

            if (string.IsNullOrEmpty(text))
                return Guid.Empty;

            var point = GetPoint3d(request, "point") ?? Point3d.Origin;
            var height = GetDouble(request, "height") ?? 1.0;

            // Get font settings
            var fontName = "Arial";
            if (request.TryGetValue("font", out var fontEl))
                fontName = fontEl.GetString() ?? "Arial";

            var bold = GetBool(request, "bold", false);
            var italic = GetBool(request, "italic", false);

            // Create text entity
            var plane = Plane.WorldXY;
            plane.Origin = point;

            var dimStyle = doc.DimStyles.Current;
            var textEntity = new TextEntity
            {
                Plane = plane,
                PlainText = text,
                TextHeight = height,
                DimensionStyleId = dimStyle.Id
            };

            // Set font
            var font = new Rhino.DocObjects.Font(fontName, bold ? Rhino.DocObjects.Font.FontWeight.Bold : Rhino.DocObjects.Font.FontWeight.Normal,
                italic ? Rhino.DocObjects.Font.FontStyle.Italic : Rhino.DocObjects.Font.FontStyle.Upright, false, false);
            textEntity.Font = font;

            return doc.Objects.AddText(textEntity);
        }

        /// <summary>
        /// Creates a linear dimension.
        /// { "type": "DIMENSION_LINEAR", "start": [0,0,0], "end": [10,0,0], "offset": 2 }
        /// </summary>
        private Guid? CreateLinearDimension(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var start = GetPoint3d(request, "start");
            var end = GetPoint3d(request, "end");

            if (start == null || end == null)
                return Guid.Empty;

            var offset = GetDouble(request, "offset") ?? 1.0;

            // Calculate dimension plane
            var direction = end.Value - start.Value;
            direction.Unitize();

            // Default perpendicular direction in XY plane
            var perpDir = Vector3d.CrossProduct(direction, Vector3d.ZAxis);
            if (perpDir.IsZero)
                perpDir = Vector3d.CrossProduct(direction, Vector3d.YAxis);
            perpDir.Unitize();

            var offsetPoint = (start.Value + end.Value) / 2 + perpDir * offset;

            var plane = new Plane(start.Value, direction, perpDir);

            var dimStyle = doc.DimStyles.Current;
            var dim = LinearDimension.Create(AnnotationType.Aligned, dimStyle, plane,
                Vector3d.XAxis, start.Value, end.Value, offsetPoint, 0);

            if (dim == null)
                return Guid.Empty;

            return doc.Objects.AddLinearDimension(dim);
        }

        /// <summary>
        /// Creates an aligned dimension.
        /// { "type": "DIMENSION_ALIGNED", "start": [0,0,0], "end": [10,5,0], "offset": 2 }
        /// </summary>
        private Guid? CreateAlignedDimension(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var start = GetPoint3d(request, "start");
            var end = GetPoint3d(request, "end");

            if (start == null || end == null)
                return Guid.Empty;

            var offset = GetDouble(request, "offset") ?? 1.0;

            var direction = end.Value - start.Value;
            direction.Unitize();

            // Perpendicular direction
            var perpDir = Vector3d.CrossProduct(direction, Vector3d.ZAxis);
            if (perpDir.IsZero)
                perpDir = Vector3d.CrossProduct(direction, Vector3d.YAxis);
            perpDir.Unitize();

            var offsetPoint = (start.Value + end.Value) / 2 + perpDir * offset;
            var plane = new Plane(start.Value, direction, perpDir);

            var dimStyle = doc.DimStyles.Current;
            var dim = LinearDimension.Create(AnnotationType.Aligned, dimStyle, plane,
                Vector3d.XAxis, start.Value, end.Value, offsetPoint, 0);

            if (dim == null)
                return Guid.Empty;

            return doc.Objects.AddLinearDimension(dim);
        }

        /// <summary>
        /// Creates a radius dimension.
        /// { "type": "DIMENSION_RADIUS", "curveId": "guid", "point": [5,0,0] }
        /// </summary>
        private Guid? CreateRadiusDimension(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            string? curveId = null;
            if (request.TryGetValue("curveId", out var curveEl))
                curveId = curveEl.GetString();

            var curve = GetCurve(doc, curveId);
            if (curve == null)
                return Guid.Empty;

            // Try to get arc from curve
            if (!curve.TryGetArc(out var arc))
            {
                // Try to get circle
                if (!curve.TryGetCircle(out var circle))
                    return Guid.Empty;
                arc = new Arc(circle, Math.PI * 2);
            }

            var dimPoint = GetPoint3d(request, "point") ?? arc.MidPoint;

            // Calculate a point on the arc/circle for the dimension
            var pointOnCurve = arc.PointAt(0);

            var dimStyle = doc.DimStyles.Current;
            var dim = RadialDimension.Create(dimStyle, AnnotationType.Radius, arc.Plane, arc.Center, pointOnCurve, dimPoint);

            if (dim == null)
                return Guid.Empty;

            return doc.Objects.AddRadialDimension(dim);
        }

        /// <summary>
        /// Creates a diameter dimension.
        /// { "type": "DIMENSION_DIAMETER", "curveId": "guid", "point": [5,0,0] }
        /// </summary>
        private Guid? CreateDiameterDimension(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            string? curveId = null;
            if (request.TryGetValue("curveId", out var curveEl))
                curveId = curveEl.GetString();

            var curve = GetCurve(doc, curveId);
            if (curve == null)
                return Guid.Empty;

            // Try to get arc from curve
            if (!curve.TryGetArc(out var arc))
            {
                if (!curve.TryGetCircle(out var circle))
                    return Guid.Empty;
                arc = new Arc(circle, Math.PI * 2);
            }

            var dimPoint = GetPoint3d(request, "point") ?? arc.MidPoint;

            // Calculate a point on the arc/circle for the dimension
            var pointOnCurve = arc.PointAt(0);

            var dimStyle = doc.DimStyles.Current;
            var dim = RadialDimension.Create(dimStyle, AnnotationType.Diameter, arc.Plane, arc.Center, pointOnCurve, dimPoint);

            if (dim == null)
                return Guid.Empty;

            return doc.Objects.AddRadialDimension(dim);
        }

        /// <summary>
        /// Creates an angle dimension.
        /// { "type": "DIMENSION_ANGLE", "vertex": [0,0,0], "start": [10,0,0], "end": [0,10,0], "point": [5,5,0] }
        /// </summary>
        private Guid? CreateAngleDimension(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var vertex = GetPoint3d(request, "vertex") ?? GetPoint3d(request, "center");
            var startPt = GetPoint3d(request, "start");
            var endPt = GetPoint3d(request, "end");

            if (vertex == null || startPt == null || endPt == null)
                return Guid.Empty;

            var dimPoint = GetPoint3d(request, "point") ?? ((startPt.Value + endPt.Value) / 2);

            var v1 = startPt.Value - vertex.Value;
            var v2 = endPt.Value - vertex.Value;
            var normal = Vector3d.CrossProduct(v1, v2);
            if (normal.IsZero)
                normal = Vector3d.ZAxis;
            normal.Unitize();

            var plane = new Plane(vertex.Value, normal);

            var dimStyle = doc.DimStyles.Current;
            var dim = AngularDimension.Create(dimStyle, plane, Vector3d.XAxis, vertex.Value, startPt.Value, endPt.Value, dimPoint);

            if (dim == null)
                return Guid.Empty;

            return doc.Objects.AddAngularDimension(dim);
        }

        /// <summary>
        /// Creates a leader annotation.
        /// { "type": "LEADER", "points": [[10,0,0],[5,5,0],[0,5,0]], "text": "Note" }
        /// </summary>
        private Guid? CreateLeader(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var points = new List<Point3d>();
            if (request.TryGetValue("points", out var pointsEl))
            {
                foreach (var ptEl in pointsEl.EnumerateArray())
                {
                    var pt = ParsePoint3d(ptEl);
                    if (pt.HasValue)
                        points.Add(pt.Value);
                }
            }

            if (points.Count < 2)
                return Guid.Empty;

            var text = "";
            if (request.TryGetValue("text", out var textEl))
                text = textEl.GetString() ?? "";

            var dimStyle = doc.DimStyles.Current;

            // Create leader with 3D points
            var plane = Plane.WorldXY;
            var points3d = points.ToArray();

            var leader = Leader.Create(text, plane, dimStyle, points3d);
            if (leader == null)
                return Guid.Empty;

            return doc.Objects.AddLeader(leader);
        }

        /// <summary>
        /// Creates a hatch pattern inside a closed curve.
        /// { "type": "HATCH", "curveId": "guid", "pattern": "Solid", "scale": 1.0, "rotation": 0 }
        /// </summary>
        private Guid? CreateHatch(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var curves = new List<Curve>();

            // Single curve
            if (request.TryGetValue("curveId", out var curveEl))
            {
                var curve = GetCurve(doc, curveEl.GetString());
                if (curve != null)
                    curves.Add(curve);
            }

            // Multiple curves
            curves.AddRange(GetCurves(doc, request));

            if (curves.Count == 0)
                return Guid.Empty;

            // Get pattern name
            var patternName = "Solid";
            if (request.TryGetValue("pattern", out var patternEl))
                patternName = patternEl.GetString() ?? "Solid";

            // Find hatch pattern
            int patternIndex = doc.HatchPatterns.Find(patternName, true);
            if (patternIndex < 0)
            {
                // Try to find any pattern
                patternIndex = doc.HatchPatterns.CurrentHatchPatternIndex;
                if (patternIndex < 0)
                    patternIndex = 0;
            }

            var scale = GetDouble(request, "scale") ?? 1.0;
            var rotation = GetDouble(request, "rotation") ?? 0.0;
            var rotationRadians = RhinoMath.ToRadians(rotation);

            var hatches = Hatch.Create(curves, patternIndex, rotationRadians, scale, doc.ModelAbsoluteTolerance);
            if (hatches == null || hatches.Length == 0)
                return Guid.Empty;

            return doc.Objects.AddHatch(hatches[0]);
        }

        /// <summary>
        /// Creates a text dot annotation.
        /// { "type": "DOT", "point": [5,5,0], "text": "A", "secondary": "Point A" }
        /// </summary>
        private Guid? CreateDot(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            var point = GetPoint3d(request, "point") ?? Point3d.Origin;

            var text = "";
            if (request.TryGetValue("text", out var textEl))
                text = textEl.GetString() ?? "";

            var secondaryText = "";
            if (request.TryGetValue("secondary", out var secEl))
                secondaryText = secEl.GetString() ?? "";

            var dot = new TextDot(text, point);
            if (!string.IsNullOrEmpty(secondaryText))
                dot.SecondaryText = secondaryText;

            // Set font height if provided
            var height = GetDouble(request, "height");
            if (height.HasValue)
                dot.FontHeight = (int)height.Value;

            return doc.Objects.AddTextDot(dot);
        }

        #endregion
    }
}
