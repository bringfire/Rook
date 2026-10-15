using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal static class VideoSourcePreparationErrors
    {
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
}
