using System;
using System.Globalization;
using System.Text;
using System.Text.Json;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
        object Actors,
        object Motion,
        object Camera,
        object FPS,
        object FrameCount,
        object ExportId,
        object ProposalId,
        object Resolution,
        ref object Json,
        ref object Info)
    {
        Json = "";
        Info = "";

        var errors = new System.Collections.Generic.List<string>();
        ActorPayload actorPayload = ParseActorPayload(ReadString(Actors, ""), errors);
        MotionPayload motionPayload = ParseMotionPayload(ReadString(Motion, ""), errors);
        string cameraJson = BuildCameraWrapper(ReadString(Camera, ""), errors);
        int fps = ReadPositiveInt(FPS, "FPS", errors);
        int frameCount = ReadPositiveInt(FrameCount, "FrameCount", errors);
        string exportId = ReadRequiredText(ExportId, "ExportId", errors);
        string proposalId = ReadRequiredText(ProposalId, "ProposalId", errors);
        ResolutionValue resolution = ParseResolution(ReadRequiredText(Resolution, "Resolution", errors), errors);

        if (errors.Count > 0)
        {
            Info = string.Join("; ", errors);
            return;
        }

        string json = BuildExportJson(actorPayload, motionPayload, cameraJson, fps, frameCount, exportId, proposalId, resolution);
        Json = json;
        Info = $"CanvasDirector export marker: export_id={exportId}; proposal_id={proposalId}; target={motionPayload.Target}; fps={fps}; frames={frameCount}; camera={(string.IsNullOrWhiteSpace(ReadString(Camera, "")) ? "active_view" : "explicit_camera")}.";
    }

    private static ActorPayload ParseActorPayload(string text, System.Collections.Generic.List<string> errors)
    {
        var payload = new ActorPayload();
        if (string.IsNullOrWhiteSpace(text))
        {
            errors.Add("Actors director_actor_runtime_payload is required");
            return payload;
        }

        try
        {
            using (var doc = JsonDocument.Parse(text))
            {
                var root = doc.RootElement;
                if (GetString(root, "metadata_kind", "") != "director_actor_runtime_payload")
                {
                    errors.Add("Actors metadata_kind must be director_actor_runtime_payload");
                    return payload;
                }

                payload.ActorSetId = GetString(root, "actor_set_id", "");
                JsonElement groups;
                if (root.TryGetProperty("groups", out groups) && groups.ValueKind == JsonValueKind.Object)
                {
                    payload.GroupsRaw = groups.GetRawText();
                    return payload;
                }

                if (string.IsNullOrWhiteSpace(payload.ActorSetId))
                {
                    errors.Add("Actors payload must include groups or actor_set_id");
                    return payload;
                }

                string sourceId = ExtractSourceId(root);
                payload.GroupsRaw = BuildGroupsJson(payload.ActorSetId, sourceId);
            }
        }
        catch (Exception ex)
        {
            errors.Add("Actors payload is not valid JSON: " + ex.GetType().Name);
        }

        return payload;
    }

    private static MotionPayload ParseMotionPayload(string text, System.Collections.Generic.List<string> errors)
    {
        var payload = new MotionPayload();
        if (string.IsNullOrWhiteSpace(text))
        {
            errors.Add("Motion director_motion_payload is required");
            return payload;
        }

        try
        {
            using (var doc = JsonDocument.Parse(text))
            {
                var root = doc.RootElement;
                if (GetString(root, "metadata_kind", "") != "director_motion_payload")
                {
                    errors.Add("Motion metadata_kind must be director_motion_payload");
                    return payload;
                }

                payload.Target = GetString(root, "target", "");
                if (string.IsNullOrWhiteSpace(payload.Target))
                    errors.Add("Motion payload target is required");

                JsonElement keyframes;
                if (root.TryGetProperty("keyframes", out keyframes) && keyframes.ValueKind == JsonValueKind.Array && keyframes.GetArrayLength() > 0)
                    payload.KeyframesRaw = keyframes.GetRawText();
                else
                    errors.Add("Motion payload keyframes must be a non-empty array");
            }
        }
        catch (Exception ex)
        {
            errors.Add("Motion payload is not valid JSON: " + ex.GetType().Name);
        }

        return payload;
    }

    private static string BuildCameraWrapper(string text, System.Collections.Generic.List<string> errors)
    {
        if (string.IsNullOrWhiteSpace(text))
            return "{\"strategy\":\"keyframes\",\"keyframes\":[{\"frame_index\":1,\"source\":{\"kind\":\"active_view\"}}]}";

        try
        {
            using (var doc = JsonDocument.Parse(text))
            {
                var root = doc.RootElement;
                if (GetString(root, "metadata_kind", "") != "director_camera_state")
                {
                    errors.Add("Camera metadata_kind must be director_camera_state when provided");
                    return "";
                }

                string projection = GetString(root, "projection", "");
                string location = RequiredRaw(root, "location", JsonValueKind.Array, errors);
                string target = RequiredRaw(root, "target", JsonValueKind.Array, errors);
                string up = RequiredRaw(root, "up", JsonValueKind.Array, errors);
                string lens = OptionalNumberOrNullRaw(root, "lens_length", errors);
                if (string.IsNullOrWhiteSpace(projection))
                    errors.Add("Camera projection is required");

                if (errors.Count > 0)
                    return "";

                var sb = new StringBuilder();
                sb.Append("{\"strategy\":\"keyframes\",\"keyframes\":[{\"frame_index\":1,\"source\":{");
                sb.Append("\"kind\":\"explicit_camera\",");
                sb.Append("\"camera\":{");
                sb.Append("\"projection\":\"").Append(Escape(projection)).Append("\",");
                sb.Append("\"location\":").Append(location).Append(",");
                sb.Append("\"target\":").Append(target).Append(",");
                sb.Append("\"up\":").Append(up).Append(",");
                sb.Append("\"lens_length\":").Append(lens);
                sb.Append("}}}]}");
                return sb.ToString();
            }
        }
        catch (Exception ex)
        {
            errors.Add("Camera payload is not valid JSON: " + ex.GetType().Name);
            return "";
        }
    }

    private static ResolutionValue ParseResolution(string text, System.Collections.Generic.List<string> errors)
    {
        var resolution = new ResolutionValue();
        if (string.IsNullOrWhiteSpace(text))
            return resolution;

        string[] parts = text.Trim().ToLowerInvariant().Split('x');
        if (parts.Length != 2)
        {
            errors.Add("Resolution must use WIDTHxHEIGHT format");
            return resolution;
        }

        int width;
        int height;
        if (!int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out width) ||
            !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out height) ||
            width < 1 ||
            height < 1)
        {
            errors.Add("Resolution width and height must be positive integers");
            return resolution;
        }

        resolution.Width = width;
        resolution.Height = height;
        return resolution;
    }

    private static string BuildExportJson(ActorPayload actorPayload, MotionPayload motionPayload, string cameraJson, int fps, int frameCount, string exportId, string proposalId, ResolutionValue resolution)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"metadata_kind\":\"rook.canvas_director.export\",");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"export_id\":\"").Append(Escape(exportId)).Append("\",");
        sb.Append("\"proposal_id\":\"").Append(Escape(proposalId)).Append("\",");
        sb.Append("\"template_id\":\"canvas_director.basic_motion\",");
        sb.Append("\"template_version\":\"0.1.0\",");
        sb.Append("\"payload\":{");
        sb.Append("\"timeline\":{\"fps\":").Append(fps.ToString(CultureInfo.InvariantCulture)).Append(",\"frame_count\":").Append(frameCount.ToString(CultureInfo.InvariantCulture)).Append("},");
        sb.Append("\"resolution\":{\"width\":").Append(resolution.Width.ToString(CultureInfo.InvariantCulture)).Append(",\"height\":").Append(resolution.Height.ToString(CultureInfo.InvariantCulture)).Append("},");
        sb.Append("\"groups\":").Append(actorPayload.GroupsRaw).Append(",");
        sb.Append("\"motion\":[{\"target\":\"").Append(Escape(motionPayload.Target)).Append("\",\"keyframes\":").Append(motionPayload.KeyframesRaw).Append("}],");
        sb.Append("\"camera\":").Append(cameraJson).Append(",");
        sb.Append("\"default_easing\":\"ease_in_out\"");
        sb.Append("}");
        sb.Append("}");
        return sb.ToString();
    }

    private static string ExtractSourceId(JsonElement root)
    {
        JsonElement sourceOccurrence;
        if (root.TryGetProperty("source_occurrence", out sourceOccurrence) && sourceOccurrence.ValueKind == JsonValueKind.Object)
        {
            string sourceId = GetString(sourceOccurrence, "source_top_level_object_id", "");
            if (!string.IsNullOrWhiteSpace(sourceId))
                return sourceId;
        }

        JsonElement sourceTakeContext;
        if (root.TryGetProperty("source_take_context", out sourceTakeContext) && sourceTakeContext.ValueKind == JsonValueKind.Object)
            return GetString(sourceTakeContext, "top_level_instance_id", "");

        return "";
    }

    private static string BuildGroupsJson(string actorSetId, string sourceId)
    {
        var sb = new StringBuilder();
        sb.Append("{\"").Append(Escape(actorSetId)).Append("\":[");
        if (!string.IsNullOrWhiteSpace(sourceId))
            sb.Append("\"").Append(Escape(sourceId)).Append("\"");
        sb.Append("]}");
        return sb.ToString();
    }

    private static string RequiredRaw(JsonElement root, string propertyName, JsonValueKind expectedKind, System.Collections.Generic.List<string> errors)
    {
        JsonElement value;
        if (!root.TryGetProperty(propertyName, out value) || value.ValueKind != expectedKind)
        {
            errors.Add("Camera " + propertyName + " is required");
            return "";
        }
        return value.GetRawText();
    }

    private static string OptionalNumberOrNullRaw(JsonElement root, string propertyName, System.Collections.Generic.List<string> errors)
    {
        JsonElement value;
        if (!root.TryGetProperty(propertyName, out value))
        {
            errors.Add("Camera " + propertyName + " is required");
            return "";
        }
        if (value.ValueKind == JsonValueKind.Number || value.ValueKind == JsonValueKind.Null)
            return value.GetRawText();
        errors.Add("Camera " + propertyName + " must be numeric or null");
        return "";
    }

    private static string ReadRequiredText(object value, string name, System.Collections.Generic.List<string> errors)
    {
        string text = ReadString(value, "");
        if (string.IsNullOrWhiteSpace(text))
            errors.Add(name + " is required");
        return text;
    }

    private static int ReadPositiveInt(object value, string name, System.Collections.Generic.List<string> errors)
    {
        if (value == null)
        {
            errors.Add(name + " is required");
            return 0;
        }

        try
        {
            int parsed = Convert.ToInt32(value, CultureInfo.InvariantCulture);
            if (parsed > 0)
                return parsed;
        }
        catch { }

        errors.Add(name + " must be a positive integer");
        return 0;
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

    private static string Escape(string value)
    {
        if (string.IsNullOrEmpty(value)) return "";
        return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }

    private sealed class ActorPayload
    {
        public string ActorSetId = "";
        public string GroupsRaw = "{}";
    }

    private sealed class MotionPayload
    {
        public string Target = "";
        public string KeyframesRaw = "[]";
    }

    private sealed class ResolutionValue
    {
        public int Width;
        public int Height;
    }
}
