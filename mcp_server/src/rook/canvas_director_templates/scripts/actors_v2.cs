using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using Rhino;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
        object ActorSetPath,
        object ActorGroupingPath,
        ref object Actors,
        ref object RuntimePayload,
        ref object ActorSetId,
        ref object GroupCount,
        ref object Info)
    {
        Actors = "";
        RuntimePayload = "";
        ActorSetId = "";
        GroupCount = 0;
        Info = "";

        string actorRef = ReadRequiredRef(ActorSetPath);
        string groupingRef = ReadRequiredRef(ActorGroupingPath);
        var errors = new List<string>();
        if (actorRef == null)
            errors.Add("ActorSetPath is required");
        if (groupingRef == null)
            errors.Add("ActorGroupingPath is required");
        if (errors.Count > 0)
        {
            Info = string.Join("; ", errors);
            return;
        }

        string projectRoot = GetProjectRoot(out string rootError);
        if (projectRoot == null)
        {
            Info = rootError;
            return;
        }

        string actorPath = ResolveMetadataRef(projectRoot, actorRef, out string actorRefError);
        string groupingPath = ResolveMetadataRef(projectRoot, groupingRef, out string groupingRefError);
        if (actorPath == null)
        {
            Info = actorRefError;
            return;
        }

        if (groupingPath == null)
        {
            Info = groupingRefError;
            return;
        }

        if (!File.Exists(actorPath))
        {
            Info = "Actor metadata ref not found: " + actorRef + " -> " + actorPath;
            return;
        }

        if (!File.Exists(groupingPath))
        {
            Info = "Actor grouping metadata ref not found: " + groupingRef + " -> " + groupingPath;
            return;
        }

        ActorMetadata actorMeta = ReadActorMetadata(actorPath);
        ActorGroupingMetadata groupingMeta = ReadActorGroupingMetadata(groupingPath);
        if (actorMeta.SchemaVersion != 2 || actorMeta.MetadataKind != "director_actor_set")
        {
            Info = "Actor metadata is not v2 director_actor_set: " + actorRef;
            return;
        }
        if (groupingMeta.SchemaVersion != 2 || groupingMeta.MetadataKind != "director_actor_grouping")
        {
            Info = "Actor grouping metadata is not v2 director_actor_grouping: " + groupingRef;
            return;
        }

        SourceOccurrence source = ResolveSourceOccurrence(projectRoot, actorMeta.SourceOccurrenceSnapshotRef);
        long actorTicks = File.GetLastWriteTimeUtc(actorPath).Ticks;
        long groupingTicks = File.GetLastWriteTimeUtc(groupingPath).Ticks;
        string key = actorMeta.ActorSetId + "|" + actorRef + "|" + actorTicks + "|" + groupingRef + "|" + groupingTicks;

        string payload = BuildPayload(actorRef, groupingRef, actorPath, groupingPath, actorMeta, groupingMeta, source, actorTicks, groupingTicks, key);

        Actors = $"Director Actors: actorSet={actorMeta.ActorSetId}; members={actorMeta.MemberCount}; groups={groupingMeta.GroupCount}";
        RuntimePayload = payload;
        ActorSetId = actorMeta.ActorSetId;
        GroupCount = groupingMeta.GroupCount;
        Info = $"Director Actors v2: actorSet={actorMeta.ActorSetId}; members={actorMeta.MemberCount}; resolved={actorMeta.ResolvedCount}; groupingKind={groupingMeta.Kind}; groups={groupingMeta.GroupCount}; groupedMembers={groupingMeta.MemberCount}; actorRef={actorRef}; groupingRef={groupingRef}; sourceTop={source.TopLevelInstanceId}; source=metadata-ref.";
    }

    private static string GetProjectRoot(out string error)
    {
        error = null;
        var doc = RhinoDoc.ActiveDoc;
        if (doc == null)
        {
            error = "No active Rhino document.";
            return null;
        }
        if (string.IsNullOrWhiteSpace(doc.Path))
        {
            error = "Active Rhino document must be saved before resolving Director metadata refs.";
            return null;
        }
        return Path.GetDirectoryName(doc.Path);
    }

    private static string ReadRequiredRef(object value)
    {
        if (value == null) return null;
        string text = value.ToString();
        if (string.IsNullOrWhiteSpace(text)) return null;
        return text.Trim().Trim('"').Replace('\\', '/');
    }

    private static string ResolveMetadataRef(string projectRoot, string metadataRef, out string error)
    {
        error = null;
        if (string.IsNullOrWhiteSpace(metadataRef))
        {
            error = "Director metadata ref is empty.";
            return null;
        }
        string normalized = metadataRef.Trim().Trim('"').Replace('\\', '/');
        if (Path.IsPathRooted(normalized) || normalized.StartsWith("//"))
        {
            error = "Director metadata refs must be project-relative .rook refs, not absolute paths: " + metadataRef;
            return null;
        }
        if (!normalized.StartsWith(".rook/", StringComparison.Ordinal) || normalized.Contains("../") || normalized.Contains("/.."))
        {
            error = "Director metadata ref must stay under .rook without '..': " + metadataRef;
            return null;
        }

        string rootFull = Path.GetFullPath(projectRoot);
        string resolved = Path.GetFullPath(Path.Combine(rootFull, normalized.Replace('/', Path.DirectorySeparatorChar)));
        if (!resolved.StartsWith(rootFull + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            error = "Director metadata ref resolved outside the active model directory: " + metadataRef;
            return null;
        }
        return resolved;
    }

    private static ActorMetadata ReadActorMetadata(string path)
    {
        var result = new ActorMetadata { ActorSetId = Path.GetFileNameWithoutExtension(path) };
        using (var doc = JsonDocument.Parse(File.ReadAllText(path)))
        {
            var root = doc.RootElement;
            result.SchemaVersion = GetInt(root, "schema_version", 0);
            result.MetadataKind = GetString(root, "metadata_kind", "");
            result.ActorSetId = GetString(root, "actor_set_id", result.ActorSetId);
            result.SourceOccurrenceSnapshotRef = GetString(root, "source_occurrence_snapshot_ref", "");

            JsonElement summary;
            if (root.TryGetProperty("summary", out summary) && summary.ValueKind == JsonValueKind.Object)
            {
                result.MemberCount = GetInt(summary, "member_count", GetInt(summary, "count", result.MemberCount));
                result.ResolvedCount = GetInt(summary, "resolved_count", result.ResolvedCount);
            }
        }

        return result;
    }

    private static ActorGroupingMetadata ReadActorGroupingMetadata(string path)
    {
        var result = new ActorGroupingMetadata { Kind = "continuous_bands" };
        using (var doc = JsonDocument.Parse(File.ReadAllText(path)))
        {
            var root = doc.RootElement;
            result.SchemaVersion = GetInt(root, "schema_version", 0);
            result.MetadataKind = GetString(root, "metadata_kind", "");
            result.Kind = GetString(root, "status", result.Kind);

            JsonElement summary;
            if (root.TryGetProperty("summary", out summary) && summary.ValueKind == JsonValueKind.Object)
            {
                result.GroupCount = GetInt(summary, "band_count", result.GroupCount);
                result.MemberCount = GetInt(summary, "member_count", result.MemberCount);
            }

            if (result.GroupCount == 0 || result.MemberCount == 0)
            {
                JsonElement bands;
                if (root.TryGetProperty("bands", out bands) && bands.ValueKind == JsonValueKind.Array)
                {
                    result.GroupCount = 0;
                    result.MemberCount = 0;
                    foreach (var band in bands.EnumerateArray())
                    {
                        result.GroupCount++;
                        JsonElement members;
                        if (!band.TryGetProperty("members", out members) || members.ValueKind != JsonValueKind.Array)
                            continue;
                        foreach (var ignored in members.EnumerateArray())
                            result.MemberCount++;
                    }
                }
            }
        }

        return result;
    }

    private static SourceOccurrence ResolveSourceOccurrence(string projectRoot, string sourceRef)
    {
        var source = new SourceOccurrence();
        if (string.IsNullOrWhiteSpace(sourceRef)) return source;
        string path = ResolveMetadataRef(projectRoot, sourceRef, out string error);
        if (path == null || !File.Exists(path)) return source;

        using (var doc = JsonDocument.Parse(File.ReadAllText(path)))
        {
            var root = doc.RootElement;
            JsonElement occurrence;
            if (root.TryGetProperty("source_occurrence", out occurrence) && occurrence.ValueKind == JsonValueKind.Object)
            {
                source.TopLevelInstanceId = GetString(occurrence, "source_top_level_object_id", "");
                source.BlockName = GetString(occurrence, "block_name", "");
                JsonElement blockDef;
                if (string.IsNullOrWhiteSpace(source.BlockName) && occurrence.TryGetProperty("block_definition", out blockDef) && blockDef.ValueKind == JsonValueKind.Object)
                    source.BlockName = GetString(blockDef, "name", "");
            }
        }
        return source;
    }

    private static string BuildPayload(string actorRef, string groupingRef, string actorPath, string groupingPath, ActorMetadata actorMeta, ActorGroupingMetadata groupingMeta, SourceOccurrence source, long actorTicks, long groupingTicks, string key)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        AppendJsonPair(sb, "schema_version", "2", false);
        AppendJsonPair(sb, "metadata_kind", "director_actor_runtime_payload", true);
        AppendJsonPair(sb, "actor_set_ref", actorRef, true);
        AppendJsonPair(sb, "actor_grouping_ref", groupingRef, true);
        AppendJsonPair(sb, "resolved_actor_set_path", actorPath, true);
        AppendJsonPair(sb, "resolved_actor_grouping_path", groupingPath, true);
        AppendJsonPair(sb, "grouping_kind", groupingMeta.Kind, true);
        AppendJsonPair(sb, "actor_set_id", actorMeta.ActorSetId, true);
        AppendJsonPair(sb, "member_count", actorMeta.MemberCount.ToString(), false);
        AppendJsonPair(sb, "resolved_count", actorMeta.ResolvedCount.ToString(), false);
        AppendJsonPair(sb, "group_count", groupingMeta.GroupCount.ToString(), false);
        AppendJsonPair(sb, "grouped_member_count", groupingMeta.MemberCount.ToString(), false);
        AppendJsonPair(sb, "band_count", groupingMeta.GroupCount.ToString(), false);
        AppendJsonPair(sb, "band_member_count", groupingMeta.MemberCount.ToString(), false);
        AppendJsonPair(sb, "actor_file_ticks", actorTicks.ToString(), false);
        AppendJsonPair(sb, "actor_grouping_file_ticks", groupingTicks.ToString(), false);
        AppendJsonPair(sb, "cache_key", key, true);
        sb.Append("\"groups\":{");
        sb.Append("\"").Append(Escape(actorMeta.ActorSetId)).Append("\":[");
        if (!string.IsNullOrWhiteSpace(source.TopLevelInstanceId))
            sb.Append("\"").Append(Escape(source.TopLevelInstanceId)).Append("\"");
        sb.Append("]},");
        sb.Append("\"source_occurrence\":{");
        AppendJsonPair(sb, "source_top_level_object_id", source.TopLevelInstanceId, true);
        AppendJsonPair(sb, "block_name", source.BlockName, true, true);
        sb.Append("},");
        sb.Append("\"source_take_context\":{");
        AppendJsonPair(sb, "take_id", "", true);
        AppendJsonPair(sb, "top_level_instance_id", source.TopLevelInstanceId, true);
        AppendJsonPair(sb, "block_name", source.BlockName, true, true);
        sb.Append("}");
        sb.Append("}");
        return sb.ToString();
    }

    private static void AppendJsonPair(StringBuilder sb, string name, string value, bool quoteValue, bool last = false)
    {
        sb.Append("\"").Append(Escape(name)).Append("\":");
        if (quoteValue)
            sb.Append("\"").Append(Escape(value ?? "")).Append("\"");
        else
            sb.Append(value ?? "0");

        if (!last)
            sb.Append(",");
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

    private static int GetInt(JsonElement element, string propertyName, int fallback)
    {
        JsonElement value;
        if (element.TryGetProperty(propertyName, out value) && value.ValueKind == JsonValueKind.Number)
        {
            int parsed;
            if (value.TryGetInt32(out parsed)) return parsed;
        }

        return fallback;
    }

    private sealed class ActorMetadata
    {
        public int SchemaVersion;
        public string MetadataKind = "";
        public string ActorSetId;
        public string SourceOccurrenceSnapshotRef = "";
        public int MemberCount;
        public int ResolvedCount;
    }

    private sealed class ActorGroupingMetadata
    {
        public int SchemaVersion;
        public string MetadataKind = "";
        public string Kind;
        public int GroupCount;
        public int MemberCount;
    }

    private sealed class SourceOccurrence
    {
        public string TopLevelInstanceId = "";
        public string BlockName = "";
    }
}
