using System;
using System.Globalization;
using System.Text;
using Rhino;
using Rhino.Display;
using Rhino.Geometry;
using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
		object LocalT,
		object Active,
		object ProjectionMode,
		object AimMode,
		object Location,
		object Target,
		object Direction,
		object Distance,
		object Up,
		object LensLength,
		object Preview,
		object ViewportName,
		ref object Camera,
		ref object LocationOut,
		ref object TargetOut,
		ref object DirectionOut,
		ref object Lens,
		ref object Applied,
		ref object CaptureSupported,
		ref object Info)
    {
        Camera = null;
        LocationOut = null;
        TargetOut = null;
        DirectionOut = null;
        Lens = null;
        Applied = false;
        CaptureSupported = false;

        double localT = Clamp(ReadDouble(LocalT, 0.0), 0.0, 1.0);
        bool active = ReadBool(Active, true);
        string projection = NormalizeProjection(ReadString(ProjectionMode, "perspective"));
        string aimMode = NormalizeAimMode(ReadString(AimMode, "Target"));
        bool preview = ReadBool(Preview, false);
        string viewportName = ReadString(ViewportName, "").Trim();
        double distance = Math.Max(1.0, ReadDouble(Distance, 10000.0));
        double lensLength = Math.Max(0.001, ReadDouble(LensLength, 50.0));

        Point3d location;
        if (!TryReadPoint(Location, out location))
        {
            Info = "Director Camera Controller: invalid Location. Provide a Point3d or coordinate text x,y,z.";
            return;
        }

        Vector3d up;
        if (!TryReadVector(Up, out up))
            up = Vector3d.ZAxis;
        if (!up.Unitize())
        {
            Info = "Director Camera Controller: invalid Up vector.";
            return;
        }

        Point3d target;
        Vector3d direction;
        if (aimMode == "Direction")
        {
            if (!TryReadVector(Direction, out direction) || !direction.Unitize())
            {
                Info = "Director Camera Controller: invalid Direction vector for AimMode=Direction.";
                return;
            }
            target = location + (direction * distance);
        }
        else
        {
            if (!TryReadPoint(Target, out target))
            {
                Info = "Director Camera Controller: invalid Target. Provide a Point3d or coordinate text x,y,z.";
                return;
            }
            direction = target - location;
            if (!direction.Unitize())
            {
                Info = "Director Camera Controller: Location and Target must differ.";
                return;
            }
        }

        double upDot = Math.Abs(direction * up);
        if (upDot >= 0.999)
        {
            Info = "Director Camera Controller: Up vector is too close to camera direction.";
            return;
        }

        bool captureSupported = projection == "perspective";
        string cameraJson = BuildCameraJson(projection, location, target, up, lensLength, captureSupported, localT);

        bool applied = false;
        string applyInfo = "";
        if (preview && active)
            applied = TryApplyPreview(projection, location, target, up, lensLength, viewportName, out applyInfo);
        else if (preview && !active)
            applyInfo = "preview skipped because Active is false";
        else
            applyInfo = "preview disabled";

        Camera = cameraJson;
        LocationOut = location;
        TargetOut = target;
        DirectionOut = direction;
        Lens = lensLength;
        Applied = applied;
        CaptureSupported = captureSupported;
        Info = $"Director Camera Controller: projection={projection}; captureSupported={captureSupported}; active={active}; preview={preview}; applied={applied}; aimMode={aimMode}; localT={localT:0.###}; lens={lensLength:0.###}; {applyInfo}.";
    }

    private bool TryApplyPreview(string projection, Point3d location, Point3d target, Vector3d up, double lensLength, string viewportName, out string info)
    {
        info = "";
        var doc = RhinoDoc.ActiveDoc;
        if (doc == null)
        {
            info = "no active Rhino document";
            return false;
        }

        var view = ResolveView(doc, viewportName);
        if (view == null)
        {
            info = string.IsNullOrWhiteSpace(viewportName)
                ? "no active Rhino view"
                : "viewport not found: " + viewportName;
            return false;
        }

        var vp = view.ActiveViewport;
        double targetDistance = Math.Max(1.0, location.DistanceTo(target));
        bool projectionOk = true;

        if (projection == "parallel")
        {
            projectionOk = vp.ChangeToParallelProjection(true);
        }
        else if (projection == "parallel_reflected")
        {
            projectionOk = vp.ChangeToParallelReflectedProjection();
        }
        else if (projection == "two_point_perspective")
        {
            projectionOk = vp.ChangeToTwoPointPerspectiveProjection(targetDistance, up, lensLength);
        }
        else
        {
            projectionOk = vp.ChangeToPerspectiveProjection(targetDistance, true, lensLength);
        }

        if (!projectionOk)
        {
            info = "projection change rejected by RhinoViewport";
            return false;
        }

        vp.SetCameraLocations(target, location);
        vp.CameraUp = up;
        if (projection == "perspective" || projection == "two_point_perspective")
            vp.Camera35mmLensLength = lensLength;

        view.Redraw();
        info = string.IsNullOrWhiteSpace(viewportName)
            ? "applied to active viewport"
            : "applied to viewport " + viewportName;
        return true;
    }

    private Rhino.Display.RhinoView ResolveView(RhinoDoc doc, string viewportName)
    {
        if (string.IsNullOrWhiteSpace(viewportName))
            return doc.Views.ActiveView;

        foreach (var view in doc.Views)
        {
            if (view != null &&
                view.ActiveViewport != null &&
                string.Equals(view.ActiveViewport.Name, viewportName, StringComparison.OrdinalIgnoreCase))
                return view;
        }

        return null;
    }

    private static string BuildCameraJson(string projection, Point3d location, Point3d target, Vector3d up, double lensLength, bool captureSupported, double localT)
    {
        bool hasLens = projection == "perspective" || projection == "two_point_perspective";
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"metadata_kind\":\"director_camera_state\",");
        sb.Append("\"projection\":\"").Append(projection).Append("\",");
        sb.Append("\"location\":").Append(PointJson(location)).Append(",");
        sb.Append("\"target\":").Append(PointJson(target)).Append(",");
        sb.Append("\"up\":").Append(VectorJson(up)).Append(",");
        sb.Append("\"lens_length\":").Append(hasLens ? Num(lensLength) : "null").Append(",");
        sb.Append("\"capture_supported\":").Append(captureSupported ? "true" : "false").Append(",");
        sb.Append("\"local_t\":").Append(Num(localT));
        sb.Append("}");
        return sb.ToString();
    }

    private static string PointJson(Point3d p)
    {
        return "[" + Num(p.X) + "," + Num(p.Y) + "," + Num(p.Z) + "]";
    }

    private static string VectorJson(Vector3d v)
    {
        return "[" + Num(v.X) + "," + Num(v.Y) + "," + Num(v.Z) + "]";
    }

    private static string Num(double value)
    {
        return value.ToString("G17", CultureInfo.InvariantCulture);
    }

    private static string NormalizeProjection(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "perspective";
        string v = value.Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "_");
        if (v == "twopointperspective" || v == "two_point" || v == "2point" || v == "2_point" || v == "two_point_perspective")
            return "two_point_perspective";
        if (v == "parallelreflected" || v == "parallel_reflected" || v == "reflected")
            return "parallel_reflected";
        if (v == "parallel" || v == "orthographic" || v == "ortho")
            return "parallel";
        return "perspective";
    }

    private static string NormalizeAimMode(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "Target";
        string v = value.Trim().ToLowerInvariant();
        if (v == "direction" || v == "dir" || v == "vector")
            return "Direction";
        return "Target";
    }

    private static bool TryReadPoint(object value, out Point3d point)
    {
        point = Point3d.Unset;
        if (value == null) return false;
        if (value is Point3d p)
        {
            point = p;
            return point.IsValid;
        }
        if (value is GH_Point gp)
        {
            point = gp.Value;
            return point.IsValid;
        }
        double x, y, z;
        if (TryParseTriple(value.ToString(), out x, out y, out z))
        {
            point = new Point3d(x, y, z);
            return point.IsValid;
        }
        return false;
    }

    private static bool TryReadVector(object value, out Vector3d vector)
    {
        vector = Vector3d.Unset;
        if (value == null) return false;
        if (value is Vector3d v)
        {
            vector = v;
            return vector.IsValid;
        }
        if (value is GH_Vector gv)
        {
            vector = gv.Value;
            return vector.IsValid;
        }
        double x, y, z;
        if (TryParseTriple(value.ToString(), out x, out y, out z))
        {
            vector = new Vector3d(x, y, z);
            return vector.IsValid;
        }
        return false;
    }

    private static bool TryParseTriple(string text, out double x, out double y, out double z)
    {
        x = y = z = 0.0;
        if (string.IsNullOrWhiteSpace(text)) return false;
        string cleaned = text.Trim()
            .Replace("[", " ")
            .Replace("]", " ")
            .Replace("(", " ")
            .Replace(")", " ")
            .Replace("{", " ")
            .Replace("}", " ")
            .Replace(";", ",");
        string[] parts = cleaned.Split(new[] { ',', ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 3) return false;
        return double.TryParse(parts[0], NumberStyles.Float, CultureInfo.InvariantCulture, out x)
            && double.TryParse(parts[1], NumberStyles.Float, CultureInfo.InvariantCulture, out y)
            && double.TryParse(parts[2], NumberStyles.Float, CultureInfo.InvariantCulture, out z);
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        double result;
        if (double.TryParse(value.ToString(), NumberStyles.Float, CultureInfo.InvariantCulture, out result))
            return result;
        try { return Convert.ToDouble(value); }
        catch { return fallback; }
    }

    private static bool ReadBool(object value, bool fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToBoolean(value); }
        catch
        {
            string s = value.ToString();
            if (string.IsNullOrWhiteSpace(s)) return fallback;
            s = s.Trim().ToLowerInvariant();
            if (s == "true" || s == "yes" || s == "1") return true;
            if (s == "false" || s == "no" || s == "0") return false;
            return fallback;
        }
    }

    private static string ReadString(object value, string fallback)
    {
        if (value == null) return fallback;
        string s = value.ToString();
        return string.IsNullOrWhiteSpace(s) ? fallback : s;
    }

    private static double Clamp(double value, double min, double max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }
}
