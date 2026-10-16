using System;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video.Framing
{
    internal static class VideoSourcePreparationEvidence
    {
        internal static bool Validate(VideoJobRecord record, JsonObject data)
        {
            try
            {
                if (data.ContainsKey("source_preparation_error"))
                {
                    var error = data["source_preparation_error"]!.AsObject();
                    if (record.Error == null || !VideoSourcePreparationErrors.IsLocalCode(error["detail_code"]?.GetValue<string>()) ||
                        error["detail_code"]!.GetValue<string>() != record.Error.ProviderErrorCode || error["field"]?.GetValue<string>() != record.Error.Field || error["retryable"]!.GetValue<bool>() != record.Error.Retryable ||
                        error.Any(kv => kv.Key is not ("detail_code" or "field" or "retryable" or "preparation_detail" or "framing_mode" or "action"))) return false;
                    var details = error.Where(kv => kv.Key is "preparation_detail" or "framing_mode" or "action").ToDictionary(kv => kv.Key, kv => kv.Value!);
                    var filtered = VideoSourcePreparationErrors.Extract(record.Error with { ProviderDetail = details })!.Details();
                    if (details.Count != filtered.Count || details.Any(kv => !JsonNode.DeepEquals(kv.Value, filtered[kv.Key]))) return false;
                }
                var request = record.NormalizedRequest;
                if (request.SourceFraming == null) return !data.ContainsKey("source_preparation");
                if (request.Mode is not (VideoMode.I2V or VideoMode.Interp) || (request.ReferenceFrames?.Count ?? 0) != 0) return false;
                var prep = data["source_preparation"]!.AsObject();
                if (prep["version"]!.GetValue<int>() != 1 || prep["mode"]!.GetValue<string>() != request.SourceFraming.Value.Wire() || prep["profile"]!.GetValue<string>() != VideoFramingRecipe.ProfileRevision || !Digest(prep["renderer_sha256"])) return false;
                var quote = data["accepted_quote"]!.AsObject();
                if (!JsonNode.DeepEquals(prep, quote["source_preparation"]) || quote["request"]?["source_framing"]?.GetValue<string>() != request.SourceFraming.Value.Wire()) return false;
                if (data["estimate_fingerprint"]?.GetValue<string>() != VideoEstimateFingerprint.Compute(quote)) return false;
                var slots = prep["slots"]!.AsArray(); var media = quote["media"]!.AsArray();
                int count = request.Mode == VideoMode.I2V ? 1 : 2;
                if (slots.Count != count || media.Count != count || request.StartFrame == null || count == 2 && request.EndFrame == null) return false;
                long originalBytes = 0; var originals = new System.Collections.Generic.HashSet<string>();
                for (int i = 0; i < count; i++)
                {
                    var slot = slots[i]!.AsObject(); var sent = media[i]!.AsObject(); var original = i == 0 ? request.StartFrame! : request.EndFrame!;
                    string role = i == 0 ? "start_frame" : "end_frame";
                    if (slot["role"]!.GetValue<string>() != role || slot["artifact_id"]?.GetValue<string>() != original.ArtifactId?.ToString("D") || slot["source_role"]?.GetValue<string>() != original.Role ||
                        !Digest(slot["original_sha256"]) || !Digest(slot["prepared_sha256"]) || slot["original_byte_length"]!.GetValue<int>() is <= 0 or > (int)VideoPreparationLimits.OriginalBytes ||
                        slot["prepared_byte_length"]!.GetValue<int>() is <= 0 or > VideoPreparationLimits.UploadBytes || slot["original_mime_type"]!.GetValue<string>() is not ("image/png" or "image/jpeg" or "image/webp")) return false;
                    if (originals.Add(original.ArtifactId + ":" + original.Role)) originalBytes += slot["original_byte_length"]!.GetValue<int>();
                    var recipe = slot["recipe"]!.AsObject();
                    var info = new VideoStillImageInfo(slot["original_mime_type"]!.GetValue<string>(), slot["original_width"]!.GetValue<int>(), slot["original_height"]!.GetValue<int>(),
                        recipe["orientation"]!.GetValue<int>(), recipe["native_bit_depth"]!.GetValue<int>(), recipe["native_planes"]!.GetValue<int>());
                    var geometry = VideoFramingGeometry.Create(info, request.Resolution, request.AspectRatio, request.SourceFraming.Value, role);
                    if (geometry.Layout is not { } layout || slot["width"]!.GetValue<int>() != layout.CanvasWidth || slot["height"]!.GetValue<int>() != layout.CanvasHeight ||
                        slot["oriented_width"]!.GetValue<int>() != info.OrientedWidth || slot["oriented_height"]!.GetValue<int>() != info.OrientedHeight || slot["upscaled"]!.GetValue<bool>() != layout.Upscaled) return false;
                    string encoding = recipe["encoding"]!.GetValue<string>(); int? q = recipe["quantizer"]?.GetValue<int>();
                    if (encoding == "png" ? q != null : encoding != "mjpeg" || q is not (2 or 3 or 4)) return false;
                    var expected = new VideoFramingRecipe(request.SourceFraming.Value, info, layout, prep["renderer_sha256"]!.GetValue<string>(), encoding, q).Canonical();
                    if (!JsonNode.DeepEquals(expected, recipe) || slot["prepared_mime_type"]!.GetValue<string>() != (encoding == "png" ? "image/png" : "image/jpeg")) return false;
                    if (sent["role"]?.GetValue<string>() != role || !JsonNode.DeepEquals(sent["sha256"], slot["prepared_sha256"]) ||
                        !JsonNode.DeepEquals(sent["mime_type"], slot["prepared_mime_type"]) || !JsonNode.DeepEquals(sent["byte_length"], slot["prepared_byte_length"]) ||
                        !JsonNode.DeepEquals(sent["artifact_id"], slot["artifact_id"]) || !JsonNode.DeepEquals(sent["source_role"], slot["source_role"])) return false;
                }
                return originalBytes <= VideoPreparationLimits.BundleOriginalBytes && (!data.ContainsKey("prepared_media") || JsonNode.DeepEquals(data["prepared_media"], media));
            }
            catch (Exception ex) when (ex is InvalidOperationException or FormatException or NullReferenceException or ArgumentException or OverflowException or System.Collections.Generic.KeyNotFoundException)
            { return false; }
        }
        private static bool Digest(JsonNode? value) => value is JsonValue v && v.TryGetValue<string>(out var text) && text.Length == 64 && text.All(Uri.IsHexDigit);
    }
}
