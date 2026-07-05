using System;
using System.Globalization;
using System.Text;
using Rhino.Geometry;
using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
        object Location,
        object Target,
        object Direction,
        object Up,
        object Lens,
        object Projection,
        object NearClip,
        object FarClip,
        object ViewportName,
        object Enabled,
        object Preview,
        object Mode,
        ref object CameraController,
        ref object Camera,
        ref object LocationOut,
        ref object TargetOut,
        ref object DirectionOut,
        ref object UpOut,
        ref object LensOut,
        ref object ProjectionOut,
        ref object Info)
    {
        Point3d location;
        bool hasLocation = TryReadPoint(Location, out location);
        if (!hasLocation)
            location = Point3d.Origin;

        Vector3d direction;
        bool hasDirection = TryReadVector(Direction, out direction) && direction.Unitize();
        Point3d target;
        bool hasTarget = TryReadPoint(Target, out target);
        string mode = NormalizeMode(ReadString(Mode, hasDirection && !hasTarget ? "direction" : "target"));

        if (mode == "direction" && hasDirection)
        {
            if (!hasTarget)
                target = location + direction;
        }
        else
        {
            if (!hasTarget)
                target = location + Vector3d.YAxis;
            direction = target - location;
            if (!direction.Unitize())
                direction = Vector3d.YAxis;
            mode = "target";
        }

        Vector3d up;
        if (!TryReadVector(Up, out up) || !up.Unitize())
            up = Vector3d.ZAxis;
        up = StabilizeUp(direction, up);

        double lens = Math.Max(0.001, ReadDouble(Lens, 50.0));
        double nearClip = Math.Max(0.0, ReadDouble(NearClip, 0.0));
        double farClip = Math.Max(0.0, ReadDouble(FarClip, 0.0));
        string projection = NormalizeProjection(ReadString(Projection, "perspective"));
        string viewportName = ReadString(ViewportName, "");
        bool enabled = ReadBool(Enabled, true);
        bool preview = ReadBool(Preview, false);

        CameraController = BuildControllerJson(mode, enabled, preview, viewportName, nearClip, farClip);
        Camera = BuildCameraJson(projection, location, target, direction, up, lens, nearClip, farClip);
        LocationOut = location;
        TargetOut = target;
        DirectionOut = direction;
        UpOut = up;
        LensOut = lens;
        ProjectionOut = projection;
        Info = $"Director Camera Controller: mode={mode}; enabled={enabled}; preview={preview}; projection={projection}; lens={lens:0.###}; near={nearClip:0.###}; far={farClip:0.###}; location={(hasLocation ? "input" : "default")}; target={(hasTarget ? "input" : "derived")}.";
    }

    private static string BuildControllerJson(string mode, bool enabled, bool preview, string viewportName, double nearClip, double farClip)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"metadata_kind\":\"director_camera_controller_payload\",");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"mode\":\"").Append(Escape(mode)).Append("\",");
        sb.Append("\"enabled\":").Append(enabled ? "true" : "false").Append(",");
        sb.Append("\"preview\":").Append(preview ? "true" : "false").Append(",");
        sb.Append("\"viewport_name\":\"").Append(Escape(viewportName)).Append("\",");
        sb.Append("\"near_clip\":").Append(Num(nearClip)).Append(",");
        sb.Append("\"far_clip\":").Append(Num(farClip));
        sb.Append("}");
        return sb.ToString();
    }

    private static string BuildCameraJson(string projection, Point3d location, Point3d target, Vector3d direction, Vector3d up, double lens, double nearClip, double farClip)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"metadata_kind\":\"director_camera_state\",");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"projection\":\"").Append(Escape(projection)).Append("\",");
        sb.Append("\"location\":").Append(PointJson(location)).Append(",");
        sb.Append("\"target\":").Append(PointJson(target)).Append(",");
        sb.Append("\"direction\":").Append(VectorJson(direction)).Append(",");
        sb.Append("\"up\":").Append(VectorJson(up)).Append(",");
        sb.Append("\"lens_length\":").Append(Num(lens)).Append(",");
        sb.Append("\"near_clip\":").Append(Num(nearClip)).Append(",");
        sb.Append("\"far_clip\":").Append(Num(farClip));
        sb.Append("}");
        return sb.ToString();
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

    private static Vector3d StabilizeUp(Vector3d direction, Vector3d up)
    {
        if (!direction.Unitize()) direction = Vector3d.YAxis;
        if (!up.Unitize()) up = Vector3d.ZAxis;
        if (Math.Abs(direction * up) < 0.999)
            return up;

        Vector3d candidate = Vector3d.ZAxis;
        if (Math.Abs(direction * candidate) >= 0.999)
            candidate = Vector3d.XAxis;
        Vector3d right = Vector3d.CrossProduct(direction, candidate);
        if (!right.Unitize()) return Vector3d.ZAxis;
        Vector3d stableUp = Vector3d.CrossProduct(right, direction);
        stableUp.Unitize();
        return stableUp;
    }

    private static string NormalizeProjection(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "perspective";
        string text = value.Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "_");
        if (text == "parallel" || text == "orthographic" || text == "ortho") return "parallel";
        if (text == "two_point" || text == "two_point_perspective" || text == "2_point") return "two_point_perspective";
        return "perspective";
    }

    private static string NormalizeMode(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "target";
        string text = value.Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "_");
        if (text == "direction" || text == "dir" || text == "vector") return "direction";
        return "target";
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        double parsed;
        if (double.TryParse(value.ToString(), NumberStyles.Float, CultureInfo.InvariantCulture, out parsed) && IsFinite(parsed))
            return parsed;
        try
        {
            parsed = Convert.ToDouble(value, CultureInfo.InvariantCulture);
            return IsFinite(parsed) ? parsed : fallback;
        }
        catch { return fallback; }
    }

    private static bool ReadBool(object value, bool fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToBoolean(value, CultureInfo.InvariantCulture); }
        catch
        {
            string text = value.ToString();
            if (string.IsNullOrWhiteSpace(text)) return fallback;
            text = text.Trim().ToLowerInvariant();
            if (text == "true" || text == "yes" || text == "1") return true;
            if (text == "false" || text == "no" || text == "0") return false;
            return fallback;
        }
    }

    private static string ReadString(object value, string fallback)
    {
        if (value == null) return fallback;
        string text = value.ToString();
        return string.IsNullOrWhiteSpace(text) ? fallback : text.Trim();
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
        bool parsed = double.TryParse(parts[0], NumberStyles.Float, CultureInfo.InvariantCulture, out x)
            && double.TryParse(parts[1], NumberStyles.Float, CultureInfo.InvariantCulture, out y)
            && double.TryParse(parts[2], NumberStyles.Float, CultureInfo.InvariantCulture, out z);
        return parsed && IsFinite(x) && IsFinite(y) && IsFinite(z);
    }

    private static string PointJson(Point3d point)
    {
        return "[" + Num(point.X) + "," + Num(point.Y) + "," + Num(point.Z) + "]";
    }

    private static string VectorJson(Vector3d vector)
    {
        return "[" + Num(vector.X) + "," + Num(vector.Y) + "," + Num(vector.Z) + "]";
    }

    private static string Num(double value)
    {
        if (!IsFinite(value))
            value = 0.0;
        return value.ToString("G17", CultureInfo.InvariantCulture);
    }

    private static string Escape(string value)
    {
        if (string.IsNullOrEmpty(value)) return "";
        var sb = new StringBuilder(value.Length + 8);
        foreach (char ch in value)
        {
            switch (ch)
            {
                case '\\':
                    sb.Append("\\\\");
                    break;
                case '"':
                    sb.Append("\\\"");
                    break;
                case '\b':
                    sb.Append("\\b");
                    break;
                case '\f':
                    sb.Append("\\f");
                    break;
                case '\n':
                    sb.Append("\\n");
                    break;
                case '\r':
                    sb.Append("\\r");
                    break;
                case '\t':
                    sb.Append("\\t");
                    break;
                default:
                    if (ch < 0x20)
                        sb.Append("\\u").Append(((int)ch).ToString("X4", CultureInfo.InvariantCulture));
                    else
                        sb.Append(ch);
                    break;
            }
        }
        return sb.ToString();
    }

    private static bool IsFinite(double value)
    {
        return !double.IsNaN(value) && !double.IsInfinity(value);
    }
}
