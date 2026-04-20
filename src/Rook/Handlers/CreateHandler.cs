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
    /// Thrown by create-geometry code paths to signal a structured
    /// {errorCode, errorMessage} failure that should bubble to the ApiResponse
    /// without the generic "Create failed" wrapper. Used by the Phase 1 typed
    /// surface routes to give callers precise error codes (invalid_input /
    /// not_found) instead of silent-ignore behavior for bad attribute bundles
    /// and wrong-type inputs.
    /// </summary>
    internal class CreateInvalidInputException : Exception
    {
        public string ErrorCode { get; }

        public CreateInvalidInputException(string message, string errorCode = "invalid_input")
            : base(message)
        {
            ErrorCode = errorCode;
        }
    }

    /// <summary>
    /// Thrown by create-geometry code paths to signal a Rhino-side failure
    /// (factory returned empty result, AddBrep returned Guid.Empty, etc.)
    /// that must be surfaced as structured {errorCode:"operation_failed", ...}
    /// and trigger the enclosing undo record's rollback.
    ///
    /// Critical for plural-contract routes: once the AddBrep loop starts,
    /// any mid-loop failure MUST throw (not return) so doc.Undo() rolls
    /// back previously-added breps atomically. Returning failure after
    /// the first successful add would leave the document in a partial
    /// state — violating the "one UndoScope per request" contract.
    /// </summary>
    internal class CreateOperationFailedException : Exception
    {
        public CreateOperationFailedException(string message) : base(message) { }
    }

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

            // Read the strict-attributes flag upfront so geometry factories can
            // pick throw-on-bad-input (strict) vs return-null (legacy) behavior.
            var strictAttributes = request.TryGetValue("_strictAttributes", out var strictEl)
                && strictEl.ValueKind == JsonValueKind.True;

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

                // Phase 1 plural-contract typed routes dispatch here before the
                // singular GeometryBase? switch. Only reachable via the native
                // SurfaceHandler routes (they inject _strictAttributes=true);
                // legacy /create?type=LOFT callers without the flag fall through
                // to the singular CreateLoft path below for compat.
                //
                // ATOMICITY CONTRACT: once a *Plural creator begins inserting
                // breps into the document, any mid-loop failure MUST throw
                // CreateOperationFailedException — NEVER return failure — so
                // the enclosing BeginUndoRecord/doc.Undo() path rolls back
                // partial inserts as a single atomic unit.
                if (strictAttributes)
                {
                    ApiResponse? pluralResult = type switch
                    {
                        "LOFT" => CreateLoftPlural(doc, request),
                        "SWEEP1" => CreateSweep1Plural(doc, request),
                        "SWEEP2" => CreateSweep2Plural(doc, request),
                        _ => null
                    };
                    if (pluralResult != null)
                    {
                        doc.Views.Redraw();
                        return pluralResult;
                    }
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
                    "REVOLVE" => strictAttributes ? CreateRevolveStrict(doc, request) : CreateRevolve(doc, request),
                    "EXTRUDE" => CreateExtrude(doc, request),
                    "PIPE" => CreatePipe(doc, request, strictAttributes),
                    "EDGE_SRF" => CreateEdgeSrf(doc, request),
                    "BLEND_CRV" => CreateBlendCurve(doc, request),
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

                // Set up attributes. When `_strictAttributes` is set (Phase 1
                // typed routes opt in via the native layer), unknown layers
                // and unparseable colors are rejected as structured
                // invalid_input errors rather than silently ignored. Legacy
                // /create callers keep the pre-PR-1 silent-ignore behavior for
                // compat, per Codex review of PR-1 scope containment. `visible`
                // is additive in both modes — a new field, not a behavior
                // change for existing callers.
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
                        if (layerIndex < 0)
                        {
                            if (strictAttributes)
                                throw new CreateInvalidInputException($"Layer not found: {layerPath}");
                            // Legacy silent-ignore path for non-strict callers.
                        }
                        else
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
                    else if (strictAttributes)
                    {
                        throw new CreateInvalidInputException("Invalid color format");
                    }
                    // else: legacy silent-ignore path.
                }

                if (request.TryGetValue("visible", out var visibleEl))
                {
                    if (visibleEl.ValueKind != JsonValueKind.True && visibleEl.ValueKind != JsonValueKind.False)
                    {
                        if (strictAttributes)
                            throw new CreateInvalidInputException("Field 'visible' must be a boolean");
                        // Non-strict callers get silent-ignore for non-boolean visible,
                        // matching the legacy pattern for other attribute fields.
                    }
                    else
                    {
                        attributes.Visible = visibleEl.GetBoolean();
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
            catch (CreateInvalidInputException ex)
            {
                doc.Undo();
                return new ApiResponse
                {
                    Success = false,
                    Data = new Dictionary<string, object>
                    {
                        ["errorCode"] = ex.ErrorCode,
                        ["errorMessage"] = ex.Message,
                    }
                };
            }
            catch (CreateOperationFailedException ex)
            {
                doc.Undo();
                return new ApiResponse
                {
                    Success = false,
                    Data = new Dictionary<string, object>
                    {
                        ["errorCode"] = "operation_failed",
                        ["errorMessage"] = ex.Message,
                    }
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
        private Brep? CreatePipe(RhinoDoc doc, Dictionary<string, JsonElement> request, bool strictAttributes)
        {
            // Get curve — in strict mode (typed /surface/pipe route) we
            // differentiate missing / bad-UUID / not-found / wrong-type and
            // throw structured invalid_input errors. Legacy /create?type=PIPE
            // callers keep the return-null behavior which bubbles up to the
            // "Unknown or invalid geometry type" envelope for compat.
            string? curveId = null;
            if (request.TryGetValue("curveId", out var curveEl))
                curveId = curveEl.GetString();
            if (string.IsNullOrEmpty(curveId))
            {
                if (strictAttributes)
                    throw new CreateInvalidInputException("Missing required field: curveId");
                return null;
            }
            if (!Guid.TryParse(curveId, out var curveGuid))
            {
                if (strictAttributes)
                    throw new CreateInvalidInputException($"Invalid UUID format for curveId: {curveId}");
                return null;
            }
            var curveObj = doc.Objects.FindId(curveGuid);
            if (curveObj == null)
            {
                if (strictAttributes)
                    throw new CreateInvalidInputException(
                        $"curveId {curveId} not found in document", errorCode: "not_found");
                return null;
            }
            var curve = curveObj.Geometry as Curve;
            if (curve == null)
            {
                if (strictAttributes)
                {
                    var typeName = curveObj.Geometry?.GetType().Name ?? "unknown";
                    throw new CreateInvalidInputException(
                        $"curveId {curveId} is not a curve (geometry type: {typeName})");
                }
                return null;
            }

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

        #region Phase 1 plural-contract helpers

        /// <summary>
        /// Builds an ObjectAttributes from the request's attribute bundle
        /// (name, layer, color, visible) with Phase 1 strict semantics:
        /// unknown layers, unparseable colors, and non-boolean visible values
        /// throw CreateInvalidInputException. Shared by plural-contract
        /// creators (CreateLoftPlural, future CreateSweepPlural, etc.).
        /// </summary>
        private ObjectAttributes BuildAttributesStrict(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
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
                    if (layerIndex < 0)
                        throw new CreateInvalidInputException($"Layer not found: {layerPath}");
                    attributes.LayerIndex = layerIndex;
                }
            }

            if (request.TryGetValue("color", out var colorEl))
            {
                var color = ParseColor(colorEl);
                if (!color.HasValue)
                    throw new CreateInvalidInputException("Invalid color format");
                attributes.ObjectColor = color.Value;
                attributes.ColorSource = ObjectColorSource.ColorFromObject;
            }

            if (request.TryGetValue("visible", out var visibleEl))
            {
                if (visibleEl.ValueKind != JsonValueKind.True && visibleEl.ValueKind != JsonValueKind.False)
                    throw new CreateInvalidInputException("Field 'visible' must be a boolean");
                attributes.Visible = visibleEl.GetBoolean();
            }

            return attributes;
        }

        /// <summary>
        /// Creates lofted brep(s) through 2+ profile curves with the Phase 1
        /// plural contract: returns {objects: [ObjectSnapshot, ...]} wrapping
        /// every brep in the Brep.CreateFromLoft result (not FirstOrDefault).
        ///
        /// Reached only via the early plural-dispatch block in CreateGeometry
        /// when _strictAttributes is set. Legacy /create?type=LOFT callers
        /// without the flag fall through to the singular CreateLoft path.
        ///
        /// ATOMICITY: once the per-brep AddBrep loop begins, ANY failure
        /// MUST throw (never return) so the enclosing doc.Undo() rolls back
        /// partial inserts. Pre-loop validation failures throw
        /// CreateInvalidInputException / CreateOperationFailedException;
        /// post-loop-entry failures throw CreateOperationFailedException.
        /// </summary>
        /// <summary>
        /// Resolves a single curve id string to a Curve, differentiating the
        /// four failure modes (missing / bad UUID / not in doc / wrong type)
        /// and throwing structured CreateInvalidInputException with the right
        /// error code. `fieldName` is used in error messages to identify the
        /// source field (e.g. "curveId", "railId", "profileIds[0]").
        /// </summary>
        private Curve ResolveCurveStrict(RhinoDoc doc, string? id, string fieldName)
        {
            if (string.IsNullOrEmpty(id))
                throw new CreateInvalidInputException($"Missing or empty {fieldName}");
            if (!Guid.TryParse(id, out var guid))
                throw new CreateInvalidInputException($"Invalid UUID for {fieldName}: {id}");
            var obj = doc.Objects.FindId(guid);
            if (obj == null)
                throw new CreateInvalidInputException(
                    $"{fieldName} {id} not found in document", errorCode: "not_found");
            var curve = obj.Geometry as Curve;
            if (curve == null)
            {
                var typeName = obj.Geometry?.GetType().Name ?? "unknown";
                throw new CreateInvalidInputException(
                    $"{fieldName} {id} is not a curve (geometry type: {typeName})");
            }
            return curve;
        }

        /// <summary>
        /// Resolves a JSON array of curve ids to a List<Curve> via
        /// ResolveCurveStrict. `arrayFieldName` identifies the array (e.g.
        /// "curveIds", "profileIds") so per-element errors reference the
        /// array position.
        /// </summary>
        private List<Curve> ResolveCurvesStrict(RhinoDoc doc, JsonElement arrayEl, string arrayFieldName)
        {
            var curves = new List<Curve>();
            int i = 0;
            foreach (var el in arrayEl.EnumerateArray())
            {
                var id = el.GetString();
                curves.Add(ResolveCurveStrict(doc, id, $"{arrayFieldName}[{i}]"));
                i++;
            }
            return curves;
        }

        /// <summary>
        /// Atomic insert-and-build for the plural contract. Adds every
        /// non-null brep from `breps` to the document with the given
        /// attributes, throwing CreateOperationFailedException on any failure
        /// (so the enclosing doc.Undo() rolls back partial inserts). Returns
        /// an ApiResponse wrapping {objects: [...]} on success.
        ///
        /// The caller must have already rejected empty/null `breps` with its
        /// route-specific operation_failed message before calling this helper.
        ///
        /// ATOMICITY: any failure inside this loop MUST throw — never return —
        /// to preserve the "one UndoScope per request" contract.
        /// </summary>
        private ApiResponse InsertBrepsAsPluralResponse(
            RhinoDoc doc, Brep[] breps, ObjectAttributes attributes, string factoryName)
        {
            var snapshots = new List<Dictionary<string, object?>>();
            foreach (var brep in breps)
            {
                if (brep == null) continue;
                var guid = doc.Objects.AddBrep(brep, attributes);
                if (guid == Guid.Empty)
                    throw new CreateOperationFailedException(
                        $"Failed to add brep to document during {factoryName} insert");
                var rhinoObj = doc.Objects.FindId(guid);
                if (rhinoObj != null)
                    snapshots.Add(RhinoSerializer.SerializeObject(rhinoObj));
                else
                    snapshots.Add(new Dictionary<string, object?> { ["id"] = guid.ToString() });
            }

            // Guard against the pathological case where the factory returns
            // a non-empty array containing only nulls: the pre-loop check
            // passes (Length > 0), but every entry is skipped here, leaving
            // snapshots empty. An empty success envelope violates the plural
            // contract — normalize to operation_failed.
            if (snapshots.Count == 0)
                throw new CreateOperationFailedException(
                    $"{factoryName} produced no insertable breps");

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["objects"] = snapshots,
                },
            };
        }

        private ApiResponse CreateLoftPlural(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // --- Pre-insert validation: curve resolution ---
            // Native SurfaceHandler has already validated curveIds presence,
            // minimum length (≥ 2), and UUID format. This block resolves
            // each id to a Curve, differentiating not-found vs wrong-type.
            if (!request.TryGetValue("curveIds", out var curveIdsEl) || curveIdsEl.ValueKind != JsonValueKind.Array)
                throw new CreateInvalidInputException("Missing or invalid 'curveIds'");

            var curves = ResolveCurvesStrict(doc, curveIdsEl, "curveIds");

            if (curves.Count < 2)
                throw new CreateInvalidInputException(
                    "Loft requires at least 2 curves", errorCode: "insufficient_curves");

            // --- loftType enum ---
            var loftType = LoftType.Normal;
            if (request.TryGetValue("loftType", out var ltEl) && ltEl.ValueKind == JsonValueKind.String)
            {
                var ltStr = ltEl.GetString() ?? "";
                loftType = ltStr.ToUpperInvariant() switch
                {
                    "NORMAL" => LoftType.Normal,
                    "LOOSE" => LoftType.Loose,
                    "TIGHT" => LoftType.Tight,
                    "STRAIGHT" => LoftType.Straight,
                    "UNIFORM" => LoftType.Uniform,
                    "DEVELOPABLE" => LoftType.Developable,
                    _ => throw new CreateInvalidInputException(
                        $"Invalid loftType: {ltStr}", errorCode: "invalid_loft_type"),
                };
            }

            // --- closed + convergence points ---
            var closed = GetBool(request, "closed", false);
            var startPoint = Point3d.Unset;
            var endPoint = Point3d.Unset;
            if (request.TryGetValue("startPoint", out var spEl))
            {
                var pt = ParsePoint3d(spEl);
                if (!pt.HasValue)
                    throw new CreateInvalidInputException("Invalid 'startPoint' — expected [x,y,z]");
                startPoint = pt.Value;
            }
            if (request.TryGetValue("endPoint", out var epEl))
            {
                var pt = ParsePoint3d(epEl);
                if (!pt.HasValue)
                    throw new CreateInvalidInputException("Invalid 'endPoint' — expected [x,y,z]");
                endPoint = pt.Value;
            }
            if (closed && (startPoint != Point3d.Unset || endPoint != Point3d.Unset))
                throw new CreateInvalidInputException(
                    "Cannot combine closed=true with convergence points (startPoint/endPoint)",
                    errorCode: "convergence_point_conflict");

            // --- Attribute bundle (strict) — builds before any insert so
            //     layer/color/visible errors roll back cleanly ---
            var attributes = BuildAttributesStrict(doc, request);

            // --- Factory invocation ---
            var breps = Brep.CreateFromLoft(curves, startPoint, endPoint, loftType, closed);
            if (breps == null || breps.Length == 0)
                throw new CreateOperationFailedException("Brep.CreateFromLoft produced no result");

            return InsertBrepsAsPluralResponse(doc, breps, attributes, "Brep.CreateFromLoft");
        }

        /// <summary>
        /// Creates swept brep(s) along one rail with the Phase 1 plural
        /// contract. Reached only via the early plural-dispatch block in
        /// CreateGeometry when _strictAttributes is set. Legacy
        /// /create?type=SWEEP1 callers without the flag fall through to the
        /// singular CreateSweep1 path.
        ///
        /// ATOMICITY: inherits from InsertBrepsAsPluralResponse — any
        /// mid-insert failure throws CreateOperationFailedException so
        /// doc.Undo() rolls back partial inserts.
        /// </summary>
        private ApiResponse CreateSweep1Plural(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // --- Rail + profile resolution ---
            string? railId = request.TryGetValue("railId", out var railEl) ? railEl.GetString() : null;
            var rail = ResolveCurveStrict(doc, railId, "railId");

            if (!request.TryGetValue("profileIds", out var profilesEl) || profilesEl.ValueKind != JsonValueKind.Array)
                throw new CreateInvalidInputException("Missing or invalid 'profileIds'");
            var profiles = ResolveCurvesStrict(doc, profilesEl, "profileIds");
            if (profiles.Count == 0)
                throw new CreateInvalidInputException(
                    "Sweep1 requires at least 1 profile curve", errorCode: "no_profiles");

            // --- style + roadlikeUp ---
            // Native handler has already validated style enum membership
            // and roadlikeUp presence rules; this block maps to the
            // SweepOneRail configuration surface.
            var closed = GetBool(request, "closed", false);
            var styleStr = request.TryGetValue("style", out var styleEl) && styleEl.ValueKind == JsonValueKind.String
                ? (styleEl.GetString() ?? "Freeform")
                : "Freeform";
            var isRoadlike = string.Equals(styleStr, "Roadlike", StringComparison.OrdinalIgnoreCase);

            Vector3d? roadlikeUp = null;
            if (isRoadlike && request.TryGetValue("roadlikeUp", out var upEl))
            {
                var pt = ParsePoint3d(upEl);
                if (!pt.HasValue)
                    throw new CreateInvalidInputException(
                        "Invalid 'roadlikeUp' — expected [x,y,z]",
                        errorCode: "missing_roadlike_up");
                roadlikeUp = new Vector3d(pt.Value);
            }

            // --- Attribute bundle (strict) — built before any insert ---
            var attributes = BuildAttributesStrict(doc, request);

            // --- Configure SweepOneRail + invoke ---
            var sweep = new SweepOneRail
            {
                ClosedSweep = closed,
                AngleToleranceRadians = doc.ModelAngleToleranceRadians,
                SweepTolerance = doc.ModelAbsoluteTolerance,
            };
            if (isRoadlike && roadlikeUp.HasValue)
                sweep.SetRoadlikeUpDirection(roadlikeUp.Value);

            var breps = sweep.PerformSweep(rail, profiles);
            if (breps == null || breps.Length == 0)
                throw new CreateOperationFailedException(
                    "SweepOneRail produced no geometry");

            return InsertBrepsAsPluralResponse(doc, breps, attributes, "SweepOneRail");
        }

        /// <summary>
        /// Creates swept brep(s) between two rails with the Phase 1 plural
        /// contract. Native layer has already validated that rail1Id and
        /// rail2Id are UUID-distinct strings (rails_coincident pre-check);
        /// geometric identity of distinct-id-but-same-curve is deferred.
        ///
        /// Empty PerformSweep results classify as operation_failed. The
        /// plan's `rails_disconnected` code is intentionally deferred until
        /// real geometric detection replaces the empty-result heuristic
        /// (Codex review 2026-04-17).
        /// </summary>
        private ApiResponse CreateSweep2Plural(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // --- Rails + profile resolution ---
            string? rail1Id = request.TryGetValue("rail1Id", out var r1El) ? r1El.GetString() : null;
            string? rail2Id = request.TryGetValue("rail2Id", out var r2El) ? r2El.GetString() : null;
            var rail1 = ResolveCurveStrict(doc, rail1Id, "rail1Id");
            var rail2 = ResolveCurveStrict(doc, rail2Id, "rail2Id");

            if (!request.TryGetValue("profileIds", out var profilesEl) || profilesEl.ValueKind != JsonValueKind.Array)
                throw new CreateInvalidInputException("Missing or invalid 'profileIds'");
            var profiles = ResolveCurvesStrict(doc, profilesEl, "profileIds");
            if (profiles.Count == 0)
                throw new CreateInvalidInputException(
                    "Sweep2 requires at least 1 profile curve", errorCode: "no_profiles");

            // --- Attribute bundle (strict) — built before any insert ---
            var attributes = BuildAttributesStrict(doc, request);

            // --- Configure SweepTwoRail + invoke ---
            var sweep = new SweepTwoRail
            {
                ClosedSweep = GetBool(request, "closed", false),
                MaintainHeight = GetBool(request, "maintainHeight", false),
                AngleToleranceRadians = doc.ModelAngleToleranceRadians,
                SweepTolerance = doc.ModelAbsoluteTolerance,
            };

            var breps = sweep.PerformSweep(rail1, rail2, profiles);
            if (breps == null || breps.Length == 0)
                throw new CreateOperationFailedException(
                    "SweepTwoRail produced no geometry");

            return InsertBrepsAsPluralResponse(doc, breps, attributes, "SweepTwoRail");
        }

        /// <summary>
        /// Creates a revolved surface around a line axis with the Phase 1
        /// typed contract. Reached only via the singular switch when
        /// _strictAttributes is set (`"REVOLVE" => strict ? CreateRevolveStrict
        /// : CreateRevolve`). Legacy /create?type=REVOLVE callers continue to
        /// hit the silent-defaults CreateRevolve path — scope containment
        /// per Codex review of the PR-4 scoping pass.
        ///
        /// Contract deltas vs legacy CreateRevolve:
        ///   - axisStart + axisEnd REQUIRED (legacy defaults to Z axis
        ///     through origin)
        ///   - startAngle + endAngle explicit (legacy takes single `angle`
        ///     with implicit 0 start)
        ///   - axis_degenerate / angle_invalid rejections (legacy silently
        ///     accepts any input)
        ///
        /// `curve_intersects_axis` is a DEFERRED PLAN-CODE: detection needs
        /// geometric curve-line intersection (feasible via
        /// Intersection.CurveLine but tolerance-sensitive). Factory failures
        /// — including the curve-crosses-axis case — classify as
        /// operation_failed in PR-4. A future PR replaces the fallthrough
        /// with real detection.
        /// </summary>
        private Brep? CreateRevolveStrict(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            // Native has already validated curveId UUID format, axis presence
            // + shape, axis_degenerate, angle types, angle_invalid, and the
            // attribute bundle. Managed re-resolves for structured error codes.
            string? curveId = request.TryGetValue("curveId", out var curveEl) ? curveEl.GetString() : null;
            var curve = ResolveCurveStrict(doc, curveId, "curveId");

            if (!request.TryGetValue("axisStart", out var axisStartEl) || !request.TryGetValue("axisEnd", out var axisEndEl))
                throw new CreateInvalidInputException("axisStart and axisEnd are required");

            var axisStart = ParsePoint3d(axisStartEl);
            var axisEnd = ParsePoint3d(axisEndEl);
            if (!axisStart.HasValue || !axisEnd.HasValue)
                throw new CreateInvalidInputException("Invalid axisStart or axisEnd — expected [x,y,z]");

            // Belt-and-suspenders: native already rejected coordinate-exact
            // equality. If something slips through (native bypassed via direct
            // /create call with _strictAttributes), catch it here too.
            if (axisStart.Value == axisEnd.Value)
                throw new CreateInvalidInputException(
                    "axisStart and axisEnd are identical; axis has zero length",
                    errorCode: "axis_degenerate");

            var startAngleDeg = GetDouble(request, "startAngle") ?? 0.0;
            var endAngleDeg = GetDouble(request, "endAngle") ?? 360.0;
            if (startAngleDeg == endAngleDeg)
                throw new CreateInvalidInputException(
                    "startAngle and endAngle are identical; revolve sweep is empty",
                    errorCode: "angle_invalid");

            var axis = new Line(axisStart.Value, axisEnd.Value);
            var startRad = RhinoMath.ToRadians(startAngleDeg);
            var endRad = RhinoMath.ToRadians(endAngleDeg);

            var rev = RevSurface.Create(curve, axis, startRad, endRad);
            if (rev == null)
                throw new CreateOperationFailedException(
                    "RevSurface.Create produced no surface "
                    + "(curve may intersect axis or input is otherwise incompatible)");

            var brep = rev.ToBrep();
            if (brep == null)
                throw new CreateOperationFailedException("RevSurface.ToBrep produced no brep");

            return brep;
        }

        /// <summary>
        /// POST /surface/edge — Phase 2 PR-1 worked example. Creates a single
        /// brep from 2–4 boundary curves using Brep.CreateEdgeSurface.
        ///
        /// Substrate: managed-bridge reuse via CreateGeometry callback. Native
        /// has already validated curveIds count (2..4) and UUID format; managed
        /// re-resolves each id with structured errors.
        ///
        /// Factory is empirically permissive (see
        /// rook_docs/2026-04-20-phase2-surface-curve-plan.md §Acceptance Gate
        /// #5 — Common Plan amendment landed 2026-04-20). Null return is
        /// unusual but surfaces as operation_failed for completeness.
        /// </summary>
        private Brep? CreateEdgeSrf(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            if (!request.TryGetValue("curveIds", out var idsEl) || idsEl.ValueKind != JsonValueKind.Array)
                throw new CreateInvalidInputException("Missing or invalid 'curveIds' (expected array of UUID strings)");

            var curves = ResolveCurvesStrict(doc, idsEl, "curveIds");
            if (curves.Count < 2 || curves.Count > 4)
                throw new CreateInvalidInputException(
                    $"EdgeSrf requires 2-4 curves, got {curves.Count}",
                    errorCode: "invalid_curve_count");

            var brep = Brep.CreateEdgeSurface(curves);
            if (brep == null)
                throw new CreateOperationFailedException(
                    "Brep.CreateEdgeSurface produced no result");

            return brep;
        }

        /// <summary>
        /// POST /curve/blend — Phase 2 PR-1 worked example. Creates a blend
        /// curve between two existing curves at a given continuity.
        ///
        /// Substrate: managed-bridge reuse via CreateGeometry callback. First
        /// strict-attribute creator whose factory returns a Curve (not a Brep)
        /// — serialization parity with brep creators under _strictAttributes
        /// pinned by test_blend_curves_live.py (f) + (h).
        ///
        /// Uses Curve.CreateBlendCurve(curveA, curveB, continuity) — overload
        /// 1 (simplest). Reverse flags, bulge doubles, and asymmetric per-end
        /// continuity are deferred per plan-doc §Non-goals.
        ///
        /// Factory is empirically permissive (see Common Plan permissiveness
        /// amendment at rook_docs/2026-04-17-typed-route-phase1-plan.md:257).
        /// </summary>
        private Curve? CreateBlendCurve(RhinoDoc doc, Dictionary<string, JsonElement> request)
        {
            string? id1 = request.TryGetValue("curve1Id", out var id1El) ? id1El.GetString() : null;
            string? id2 = request.TryGetValue("curve2Id", out var id2El) ? id2El.GetString() : null;
            var curve1 = ResolveCurveStrict(doc, id1, "curve1Id");
            var curve2 = ResolveCurveStrict(doc, id2, "curve2Id");

            var continuity = BlendContinuity.Tangency;
            if (request.TryGetValue("continuity", out var contEl))
            {
                var contStr = contEl.GetString();
                continuity = contStr switch
                {
                    "Position" => BlendContinuity.Position,
                    "Tangency" => BlendContinuity.Tangency,
                    "Curvature" => BlendContinuity.Curvature,
                    _ => throw new CreateInvalidInputException(
                        $"Invalid continuity: '{contStr}'. Must be Position, Tangency, or Curvature.",
                        errorCode: "invalid_continuity"),
                };
            }

            var blend = Curve.CreateBlendCurve(curve1, curve2, continuity);
            if (blend == null)
                throw new CreateOperationFailedException(
                    "Curve.CreateBlendCurve produced no result");

            return blend;
        }

        #endregion
    }
}
