using System.Collections.Generic;
using System.Text.Json.Nodes;
using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal static class VideoSourcePreparationErrors
    {
        internal static bool IsLocalCode(string? code) => code is "video_route_unavailable" or "framing_choice_required" or "source_input_too_large" or "source_changed" or "source_animation_unsupported" or "source_preparation_failed";
        internal static VideoPreparationFailure? Extract(GenerationError error)
        {
            if (!IsLocalCode(error.ProviderErrorCode)) return null;
            string? Get(string key) => error.ProviderDetail != null && error.ProviderDetail.TryGetValue(key, out var node) && node is JsonValue value && value.TryGetValue<string>(out var text) ? text : null;
            string? detail = Get("preparation_detail"), mode = Get("framing_mode"), action = Get("action");
            if (detail is not ("render_limits_exceeded" or "preparation_busy" or "invalid_source" or "renderer_unavailable" or "renderer_profile_mismatch" or "enforcement_unavailable" or "renderer_failed" or "invalid_output" or "encoded_output_too_large")) detail = null;
            if (mode is not ("fit" or "fill")) mode = null;
            if (action is not ("choose_fit" or "open_settings")) action = null;
            return new(detail, mode, action);
        }
        internal static JsonObject? Project(GenerationError error)
        {
            var failure = Extract(error); if (failure == null) return null;
            var result = new JsonObject { ["detail_code"] = error.ProviderErrorCode, ["field"] = error.Field, ["retryable"] = error.Retryable };
            foreach (var kv in failure.Details()) result[kv.Key] = kv.Value.DeepClone();
            return result;
        }
        public static GenerationError Create(string code, string field, string? mode = null, string? detail = null, bool retryable = false)
        {
            var message = code switch
            {
                "source_input_too_large" => "A video source must be at most 32 MiB; distinct sources together must be at most 64 MiB.",
                "source_changed" => "The source changed or could not be read consistently. Retry preparation with the current image.",
                "source_animation_unsupported" => "Choose a still PNG, JPEG or WebP image for video framing. Animated sources are not supported.",
                "framing_choice_required" => "Choose Fit or Fill so Rook can prepare this image automatically.",
                _ when detail == "preparation_busy" => "Image preparation is busy. Retry shortly.",
                _ when detail == "render_limits_exceeded" && mode == "fill" => "This Fill would exceed Rook's rendering limits. Choose Fit to keep the whole image.",
                _ when detail == "render_limits_exceeded" => "This source exceeds Rook's image rendering limits.",
                _ => "Rook could not prepare this source image. Retry or choose another still image."
            };
            var details = new Dictionary<string, JsonNode>();
            if (mode != null) details["framing_mode"] = JsonValue.Create(mode)!;
            if (detail != null) details["preparation_detail"] = JsonValue.Create(detail)!;
            if (detail == "render_limits_exceeded" && mode == "fill") details["action"] = JsonValue.Create("choose_fit")!;
            return new GenerationError(retryable ? GenerationErrorCode.DependencyUnavailable : GenerationErrorCode.InvalidRequest,
                message, retryable, field, code, details.Count == 0 ? null : details);
        }
        public static GenerationError Busy(string field) => Create("source_preparation_failed", field, detail: "preparation_busy", retryable: true);
    }
    internal sealed record VideoPreparationFailure(string? Detail, string? Mode, string? Action)
    {
        public Dictionary<string, JsonNode> Details()
        {
            var values = new Dictionary<string, JsonNode>();
            if (Detail != null) values["preparation_detail"] = JsonValue.Create(Detail)!;
            if (Mode != null) values["framing_mode"] = JsonValue.Create(Mode)!;
            if (Action != null) values["action"] = JsonValue.Create(Action)!;
            return values;
        }
    }
}
