using System;
using System.Globalization;
using System.Text;
using System.Text.Json;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private const string DefaultStrategy = "band_peel_wave";

    private void RunScript(
        object Actors,
        object Start,
        object Progress,
        object MaxH,
        object Spread,
        object FastPreview,
        object Strategy,
        ref object Motion,
        ref object G,
        ref object H,
        ref object Info)
    {
        Motion = "";
        G = null;
        H = "";
        Info = "";

        string strategy = ReadString(Strategy, "").Trim();
        if (string.IsNullOrWhiteSpace(strategy))
            strategy = DefaultStrategy;
        if (!string.Equals(strategy, DefaultStrategy, StringComparison.Ordinal))
        {
            Info = "Unsupported transform strategy: " + strategy;
            return;
        }

        string actorsText = ReadString(Actors, "");
        if (string.IsNullOrWhiteSpace(actorsText))
        {
            Info = "Actors director_actor_runtime_payload is required.";
            return;
        }

        string target = ResolveTarget(actorsText, out string targetError);
        if (target == null)
        {
            Info = targetError;
            return;
        }

        double start = ReadDouble(Start, 0.0);
        double progress = Clamp(ReadDouble(Progress, 0.0), 0.0, 1.0);
        double maxH = ReadDouble(MaxH, 0.0);
        double spread = Math.Max(0.0, ReadDouble(Spread, 0.0));
        bool fastPreview = ReadBool(FastPreview, true);

        string motion = BuildMotionPayload(strategy, target, start, progress, maxH, spread, fastPreview);
        Motion = motion;
        H = "maxH=" + Num(maxH) + "; progress=" + Num(progress);
        Info = $"Director Transform: strategy={strategy}; target={target}; maxH={maxH:0.###}; preview=metadata-only.";
    }

    private static string ResolveTarget(string actorsText, out string error)
    {
        error = null;
        try
        {
            using (var doc = JsonDocument.Parse(actorsText))
            {
                var root = doc.RootElement;
                if (GetString(root, "metadata_kind", "") != "director_actor_runtime_payload")
                {
                    error = "Actors payload metadata_kind must be director_actor_runtime_payload.";
                    return null;
                }

                string actorSetId = GetString(root, "actor_set_id", "");
                if (!string.IsNullOrWhiteSpace(actorSetId))
                    return actorSetId;

                JsonElement groups;
                if (root.TryGetProperty("groups", out groups) && groups.ValueKind == JsonValueKind.Object)
                {
                    foreach (var group in groups.EnumerateObject())
                    {
                        if (!string.IsNullOrWhiteSpace(group.Name))
                            return group.Name;
                    }
                }
            }
        }
        catch (Exception ex)
        {
            error = "Actors payload is not valid JSON: " + ex.GetType().Name;
            return null;
        }

        error = "Actors payload must include actor_set_id or groups.";
        return null;
    }

    private static string BuildMotionPayload(string strategy, string target, double start, double progress, double maxH, double spread, bool fastPreview)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"metadata_kind\":\"director_motion_payload\",");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"strategy\":\"").Append(Escape(strategy)).Append("\",");
        sb.Append("\"target\":\"").Append(Escape(target)).Append("\",");
        sb.Append("\"keyframes\":[");
        sb.Append("{\"t\":\"0.0\",\"translate\":[0,0,0]},");
        sb.Append("{\"t\":\"1.0\",\"translate\":[0,0,").Append(Num(maxH)).Append("]}");
        sb.Append("],");
        sb.Append("\"preview\":{");
        sb.Append("\"start\":").Append(Num(start)).Append(",");
        sb.Append("\"progress\":").Append(Num(progress)).Append(",");
        sb.Append("\"spread\":").Append(Num(spread)).Append(",");
        sb.Append("\"fast_preview\":").Append(fastPreview ? "true" : "false");
        sb.Append("}");
        sb.Append("}");
        return sb.ToString();
    }

    private static string ReadString(object value, string fallback)
    {
        if (value == null) return fallback;
        string text = value.ToString();
        return string.IsNullOrWhiteSpace(text) ? fallback : text.Trim();
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToDouble(value, CultureInfo.InvariantCulture); }
        catch { return fallback; }
    }

    private static bool ReadBool(object value, bool fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToBoolean(value, CultureInfo.InvariantCulture); }
        catch { return fallback; }
    }

    private static double Clamp(double value, double min, double max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private static string Num(double value)
    {
        return value.ToString("G17", CultureInfo.InvariantCulture);
    }

    private static string Escape(string value)
    {
        if (string.IsNullOrEmpty(value)) return "";
        return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }

    private static string GetString(JsonElement element, string propertyName, string fallback)
    {
        JsonElement value;
        if (element.TryGetProperty(propertyName, out value) && value.ValueKind == JsonValueKind.String)
            return value.GetString();
        return fallback;
    }
}
