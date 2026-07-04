using System;
using System.Globalization;
using Rhino.Geometry;
using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
		object LocalT,
		object Active,
		object CameraPath,
		object TargetMode,
		object TargetPoint,
		object TargetPath,
		object LookAhead,
		object Up,
		object EaseMode,
		ref object Location,
		ref object Target,
		ref object Direction,
		ref object UpOut,
		ref object Distance,
		ref object PathT,
		ref object Info)
    {
        Location = null;
        Target = null;
        Direction = null;
        UpOut = null;
        Distance = null;
        PathT = null;
        Info = null;

        double localT = Clamp(ReadDouble(LocalT, 0.0), 0.0, 1.0);
        bool active = ReadBool(Active, true);
        string targetMode = NormalizeTargetMode(ReadString(TargetMode, "LookAhead"));
        string easeMode = NormalizeEaseMode(ReadString(EaseMode, "Linear"));
        double pathT = ApplyEase(localT, easeMode);

        Curve cameraPath;
        if (!TryReadCurve(CameraPath, out cameraPath) || !cameraPath.IsValid)
        {
            PathT = pathT;
            Info = "Director Camera Path: waiting for a valid CameraPath curve.";
            return;
        }

        double pathLength = SafeLength(cameraPath);
        double cameraParam = ParameterAtNormalizedLength(cameraPath, pathT, pathLength);
        Point3d location = cameraPath.PointAt(cameraParam);
        Vector3d tangent = cameraPath.TangentAt(cameraParam);
        if (!tangent.Unitize())
        {
            Info = "Director Camera Path: CameraPath tangent is invalid at the sampled frame.";
            return;
        }

        Vector3d up;
        if (!TryReadVector(Up, out up) || !up.Unitize())
            up = Vector3d.ZAxis;

        double lookAhead = ReadDouble(LookAhead, 0.0);
        if (lookAhead <= 0.0)
            lookAhead = pathLength > Rhino.RhinoMath.ZeroTolerance ? Math.Max(pathLength * 0.02, 1.0) : 1.0;

        Point3d target;
        string targetInfo;
        if (!TryEvaluateTarget(targetMode, cameraPath, pathLength, pathT, location, tangent, lookAhead, TargetPoint, TargetPath, out target, out targetInfo))
        {
            Info = "Director Camera Path: " + targetInfo;
            return;
        }

        Vector3d direction = target - location;
        double distance = direction.Length;
        if (!direction.Unitize())
        {
            target = location + tangent * Math.Max(lookAhead, 1.0);
            direction = target - location;
            distance = direction.Length;
            if (!direction.Unitize())
            {
                Info = "Director Camera Path: could not derive a valid direction.";
                return;
            }
            targetInfo += "; fell back to tangent target";
        }

        up = StabilizeUp(direction, up);

        Location = location;
        Target = target;
        Direction = direction;
        UpOut = up;
        Distance = distance;
        PathT = pathT;
        Info = string.Format(CultureInfo.InvariantCulture,
            "Director Camera Path: active={0}; localT={1:0.###}; pathT={2:0.###}; ease={3}; targetMode={4}; distance={5:0.###}; {6}.",
            active, localT, pathT, easeMode, targetMode, distance, targetInfo);
    }

    private static bool TryEvaluateTarget(string targetMode, Curve cameraPath, double pathLength, double pathT, Point3d location, Vector3d tangent, double lookAhead, object targetPointInput, object targetPathInput, out Point3d target, out string info)
    {
        target = Point3d.Unset;
        info = "";

        if (targetMode == "FixedTarget")
        {
            if (TryReadPoint(targetPointInput, out target))
            {
                info = "fixed target";
                return true;
            }
            info = "TargetMode=FixedTarget needs a valid TargetPoint.";
            return false;
        }

        if (targetMode == "TargetPath")
        {
            Curve targetPath;
            if (!TryReadCurve(targetPathInput, out targetPath) || !targetPath.IsValid)
            {
                info = "TargetMode=TargetPath needs a valid TargetPath curve.";
                return false;
            }

            double targetLength = SafeLength(targetPath);
            double targetParam = ParameterAtNormalizedLength(targetPath, pathT, targetLength);
            target = targetPath.PointAt(targetParam);
            info = "target path sampled by LocalT";
            return target.IsValid;
        }

        if (targetMode == "Tangent")
        {
            target = location + tangent * Math.Max(lookAhead, 1.0);
            info = "tangent target";
            return true;
        }

        target = LookAheadTarget(cameraPath, pathLength, pathT, location, tangent, lookAhead);
        info = "look-ahead target";
        return target.IsValid;
    }

    private static Point3d LookAheadTarget(Curve curve, double length, double pathT, Point3d location, Vector3d tangent, double lookAhead)
    {
        if (length > Rhino.RhinoMath.ZeroTolerance)
        {
            double currentLength = Clamp(pathT, 0.0, 1.0) * length;
            double targetLength = Clamp(currentLength + lookAhead, 0.0, length);
            double targetParam;
            if (curve.LengthParameter(targetLength, out targetParam))
            {
                Point3d p = curve.PointAt(targetParam);
                if (p.DistanceTo(location) > Rhino.RhinoMath.ZeroTolerance)
                    return p;
            }
        }

        return location + tangent * Math.Max(lookAhead, 1.0);
    }

    private static double ParameterAtNormalizedLength(Curve curve, double normalized, double length)
    {
        normalized = Clamp(normalized, 0.0, 1.0);
        double parameter;
        if (length > Rhino.RhinoMath.ZeroTolerance && curve.NormalizedLengthParameter(normalized, out parameter))
            return parameter;
        return curve.Domain.ParameterAt(normalized);
    }

    private static double SafeLength(Curve curve)
    {
        try
        {
            double length = curve.GetLength();
            return double.IsNaN(length) || double.IsInfinity(length) ? 0.0 : length;
        }
        catch
        {
            return 0.0;
        }
    }

    private static Vector3d StabilizeUp(Vector3d direction, Vector3d up)
    {
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

    private static string NormalizeTargetMode(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "LookAhead";
        string v = value.Trim().ToLowerInvariant().Replace(" ", "_").Replace("-", "_");
        if (v == "fixed" || v == "fixedtarget" || v == "fixed_target" || v == "target_point" || v == "point")
            return "FixedTarget";
        if (v == "targetpath" || v == "target_path" || v == "path")
            return "TargetPath";
        if (v == "tangent" || v == "direction")
            return "Tangent";
        return "LookAhead";
    }

    private static string NormalizeEaseMode(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "Linear";
        string v = value.Trim().ToLowerInvariant().Replace(" ", "_").Replace("-", "_");
        if (v == "smooth" || v == "smoothstep" || v == "smooth_step") return "SmoothStep";
        if (v == "sine" || v == "easeinoutsine" || v == "ease_in_out_sine") return "EaseInOutSine";
        if (v == "ease_in" || v == "easein") return "EaseIn";
        if (v == "ease_out" || v == "easeout") return "EaseOut";
        return "Linear";
    }

    private static double ApplyEase(double t, string mode)
    {
        t = Clamp(t, 0.0, 1.0);
        if (mode == "SmoothStep") return t * t * (3.0 - 2.0 * t);
        if (mode == "EaseInOutSine") return 0.5 - 0.5 * Math.Cos(Math.PI * t);
        if (mode == "EaseIn") return t * t;
        if (mode == "EaseOut") return 1.0 - (1.0 - t) * (1.0 - t);
        return t;
    }

    private static bool TryReadCurve(object value, out Curve curve)
    {
        curve = null;
        if (value == null) return false;
        if (value is Curve c)
        {
            curve = c;
            return curve != null;
        }
        if (value is GH_Curve gc)
        {
            curve = gc.Value;
            return curve != null;
        }
        return false;
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
