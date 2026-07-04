using System;
using System.Globalization;
using System.Text;
using System.Text.Json;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
        object Clock,
        object Start,
        object End,
        object Ease,
        object Enabled,
        ref object Gate,
        ref object Progress,
        ref object Active,
        ref object EaseOut,
        ref object StartOut,
        ref object EndOut,
        ref object T,
        ref object Info)
    {
        double t = ReadClockT(Clock, out string clockInfo);
        double start = ReadDouble(Start, 0.0);
        double end = ReadDouble(End, 1.0);
        string ease = NormalizeEase(ReadString(Ease, "linear"));
        bool enabled = ReadBool(Enabled, true);
        double rawProgress = NormalizeWindowProgress(t, start, end);
        double progress = ApplyEase(rawProgress, ease);
        bool active = enabled && IsWithinWindow(t, start, end);

        Gate = BuildGateJson(start, end, ease, enabled, t, progress, active);
        Progress = progress;
        Active = active;
        EaseOut = ease;
        StartOut = start;
        EndOut = end;
        T = t;
        Info = $"Director Timing Gate: start={start:0.###}; end={end:0.###}; ease={ease}; enabled={enabled}; t={t:0.###}; progress={progress:0.###}; active={active}; {clockInfo}.";
    }

    private static string BuildGateJson(double start, double end, string ease, bool enabled, double t, double progress, bool active)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"metadata_kind\":\"director_timing_gate_payload\",");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"start\":").Append(Num(start)).Append(",");
        sb.Append("\"end\":").Append(Num(end)).Append(",");
        sb.Append("\"ease\":\"").Append(Escape(ease)).Append("\",");
        sb.Append("\"enabled\":").Append(enabled ? "true" : "false").Append(",");
        sb.Append("\"t\":").Append(Num(t)).Append(",");
        sb.Append("\"progress\":").Append(Num(progress)).Append(",");
        sb.Append("\"active\":").Append(active ? "true" : "false");
        sb.Append("}");
        return sb.ToString();
    }

    private static double ReadClockT(object value, out string info)
    {
        info = "clock=default";
        string text = ReadString(value, "");
        if (string.IsNullOrWhiteSpace(text))
            return 0.0;

        try
        {
            using (var doc = JsonDocument.Parse(text))
            {
                var root = doc.RootElement;
                if (GetString(root, "metadata_kind", "") != "director_clock_payload")
                {
                    info = "clock=ignored-kind";
                    return 0.0;
                }

                double t = GetDouble(root, "t", 0.0);
                info = "clock=parsed";
                return Clamp(t, 0.0, 1.0);
            }
        }
        catch
        {
            info = "clock=invalid";
            return 0.0;
        }
    }

    private static double NormalizeWindowProgress(double t, double start, double end)
    {
        if (Math.Abs(end - start) < 1e-9)
            return t >= end ? 1.0 : 0.0;
        double low = Math.Min(start, end);
        double high = Math.Max(start, end);
        return Clamp((t - low) / (high - low), 0.0, 1.0);
    }

    private static bool IsWithinWindow(double t, double start, double end)
    {
        double low = Math.Min(start, end);
        double high = Math.Max(start, end);
        return t >= low && t <= high;
    }

    private static string NormalizeEase(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "linear";
        string text = value.Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "_");
        if (text == "smooth" || text == "smoothstep" || text == "smooth_step") return "smooth_step";
        if (text == "easein" || text == "ease_in") return "ease_in";
        if (text == "easeout" || text == "ease_out") return "ease_out";
        if (text == "easeinout" || text == "ease_in_out" || text == "sine") return "ease_in_out";
        return "linear";
    }

    private static double ApplyEase(double t, string ease)
    {
        t = Clamp(t, 0.0, 1.0);
        if (ease == "smooth_step") return t * t * (3.0 - 2.0 * t);
        if (ease == "ease_in") return t * t;
        if (ease == "ease_out") return 1.0 - ((1.0 - t) * (1.0 - t));
        if (ease == "ease_in_out") return 0.5 - (0.5 * Math.Cos(Math.PI * t));
        return t;
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        try
        {
            double parsed = Convert.ToDouble(value, CultureInfo.InvariantCulture);
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

    private static string GetString(JsonElement element, string propertyName, string fallback)
    {
        JsonElement value;
        if (element.TryGetProperty(propertyName, out value) && value.ValueKind == JsonValueKind.String)
            return value.GetString();
        return fallback;
    }

    private static double GetDouble(JsonElement element, string propertyName, double fallback)
    {
        JsonElement value;
        if (element.TryGetProperty(propertyName, out value) && value.ValueKind == JsonValueKind.Number)
        {
            double parsed;
            if (value.TryGetDouble(out parsed) && IsFinite(parsed)) return parsed;
        }
        return fallback;
    }

    private static double Clamp(double value, double min, double max)
    {
        if (!IsFinite(value)) return min;
        if (value < min) return min;
        if (value > max) return max;
        return value;
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
