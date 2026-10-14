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
        public static VideoExecutionProjection Project(VideoJobRecord durable, VideoStopReason? localStop, VideoStopPersistence persistence)
        {
            var read = Read(durable);
            if (read.Error != null) return new(new JsonObject { ["execution_evidence_invalid"] = true });
            if (read.Snapshot is null) return new(new JsonObject());
            var data = read.Snapshot.Data;
            var attempts = data["attempts"]!.AsArray();
            var last = attempts.LastOrDefault() as JsonObject;
            var stop = durable.State == VideoJobState.Complete ? null : localStop?.ToString().ToLowerInvariant() ?? data["first_stop_reason"]?.GetValue<string>();
            var fields = new JsonObject {
                ["requested_provider"] = data["requested_provider"]?.DeepClone(), ["requested_model"] = data["requested_model"]?.DeepClone(),
                ["effective_provider"] = durable.Provider, ["effective_model"] = durable.Model,
                ["phase"] = data["phase"]?.DeepClone(), ["dispatch_state"] = last?["dispatch_state"]?.DeepClone(),
                ["generation_dispatch_attempted"] = last?["generation_dispatch_attempted"]?.DeepClone() ?? JsonValue.Create(false),
                ["submission_unknown"] = attempts.Any(a => a?["dispatch_state"]?.GetValue<string>() is "intent_recorded" or "unknown"),
                ["execution_stopped"] = stop != null, ["first_stop_reason"] = stop,
                ["stop_persistence"] = persistence == VideoStopPersistence.None ? data["stop_persistence"]?.DeepClone() : JsonValue.Create(persistence.ToString().ToLowerInvariant()),
                ["durability_unknown"] = persistence == VideoStopPersistence.Failed,
                ["deadline_utc"] = data["deadline_utc"]?.DeepClone(), ["cleanup"] = data["cleanup"]?.DeepClone(),
                ["credential_failure"] = data["credential_failure"]?.DeepClone(), ["video_route"] = durable.Extensions?["video_route"]?.DeepClone(),
                ["estimate_fingerprint"] = data["estimate_fingerprint"]?.DeepClone(), ["max_estimated_cost_usd"] = data["max_estimated_cost_usd"]?.DeepClone(),
                ["accepted_quote"] = data["accepted_quote"]?.DeepClone(), ["effective_estimated_cost_usd"] = durable.Pricing.TotalUsd,
                ["pricing_source"] = durable.Pricing.PricingSource, ["warnings"] = data["warnings"]?.DeepClone()
            };
            return new(fields);
        }
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
