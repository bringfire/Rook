using System;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoExecutionSnapshot
    {
        private readonly JsonObject _data;
        public VideoExecutionSnapshot(int version, JsonObject data) { Version = version; _data = (JsonObject)data.DeepClone(); }
        public int Version { get; }
        public JsonObject Data => (JsonObject)_data.DeepClone();
        public static VideoJobRecord Write(VideoJobRecord record, VideoExecutionSnapshot snapshot)
        {
            var extension = (JsonObject?)record.Extensions?.DeepClone() ?? new JsonObject();
            var data = snapshot.Data; data["version"] = snapshot.Version; extension["video_execution"] = data;
            return record with { Extensions = extension };
        }
        public static (VideoExecutionSnapshot? Snapshot, GenerationError? Error) Read(VideoJobRecord record)
        {
            if (record.Extensions is null || !record.Extensions.ContainsKey("video_execution")) return (null, null);
            try
            {
                var data = record.Extensions["video_execution"]!.AsObject();
                if (data["version"]!.GetValue<int>() != 1 || string.IsNullOrWhiteSpace(data["requested_provider"]?.GetValue<string>()) || string.IsNullOrWhiteSpace(data["requested_model"]?.GetValue<string>()) || data["accepted_quote"] is not JsonObject || data["attempts"] is not JsonArray attempts || !DateTimeOffset.TryParse(data["deadline_utc"]?.GetValue<string>(), CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out _)) return Invalid();
                foreach (var attempt in attempts)
                {
                    if (attempt is not JsonObject obj || obj["provider"]?.GetValue<string>() is not ("veo" or "fal") || obj["dispatch_state"]?.GetValue<string>() is not ("not_started" or "intent_recorded" or "accepted" or "rejected" or "unknown")) return Invalid();
                }
                if (data["first_stop_reason"] != null && data["first_stop_reason"]!.GetValue<string>() is not ("user" or "deadline" or "shutdown")) return Invalid();
                return (new VideoExecutionSnapshot(1, data), null);
            }
            catch (Exception ex) when (ex is InvalidOperationException or FormatException or NullReferenceException) { return Invalid(); }
        }
        private static (VideoExecutionSnapshot?, GenerationError?) Invalid() => (null, new GenerationError(GenerationErrorCode.DependencyUnavailable, "Video execution evidence is unsupported or corrupt; no new provider work is authorized.", false, null, "execution_evidence_invalid"));
    }
}
