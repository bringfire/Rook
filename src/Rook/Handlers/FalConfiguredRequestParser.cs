using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Fal;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
namespace Rook.Handlers
{
    internal sealed class FalRequestParseResult
    {
        public FalModelInput? Input { get; }
        public FalNormalizedRequest? Request { get; }
        public FalOperationBinding? Binding => Request?.Binding;
        public IReadOnlyList<FalFieldError> Errors { get; }
        public bool Success => Request != null;
        internal FalRequestParseResult(FalModelInput? input, FalNormalizedRequest? request, IReadOnlyList<FalFieldError> errors)
        { Input = input; Request = request; Errors = errors; }
    }
    internal static class FalConfiguredRequestParser
    {
        private static readonly string[] Common = { "prompt", "resolution", "aspect_ratio", "duration_seconds", "seed" };
        private static readonly string[] Envelope = { "op", "model", "operation", "options", "media", "mode", "start_frame", "end_frame", "reference_frames", "quote_fingerprint", "max_estimated_cost_usd" };
        public static FalRequestParseResult Parse(JsonObject request, FalCatalogSnapshot catalog, string modality)
        {
            var modelId = String(request["model"]);
            var model = catalog.Definitions.FirstOrDefault(m => m.ModelId == modelId && m.Operations.All(o => o.Result.MimeFamily == modality));
            if (model == null) return Invalid("model", "Unknown or unavailable configured model.");
            foreach (var pair in request)
                if (!Common.Contains(pair.Key) && !Envelope.Contains(pair.Key)) return Invalid(pair.Key, "Unsupported configured request field.");
            string? operation = null;
            if (request.ContainsKey("operation"))
            {
                operation = String(request["operation"]);
                if (string.IsNullOrWhiteSpace(operation)) return Invalid("operation", "Operation must be a non-empty string.");
            }
            if (request.ContainsKey("mode"))
            {
                var mapped = String(request["mode"]) switch { "t2v" => "text_to_video", "i2v" => "image_to_video", "interp" => "first_last_frame_to_video", _ => null };
                if (modality != "video" || mapped == null) return Invalid("mode", "Mode must be t2v, i2v or interp for video.");
                if (operation != null && mapped != operation) return Invalid("operation", "Operation conflicts with video mode.");
                operation = mapped;
            }
            if (request.ContainsKey("options") && request["options"] is not JsonObject) return Invalid("options", "Options must be an object.");
            var fields = new JsonObject();
            foreach (var key in Common) if (request.TryGetPropertyValue(key, out var value)) fields[key] = value?.DeepClone();
            var media = new List<FalMediaInput>();
            bool compatibilityMedia = request.ContainsKey("start_frame") || request.ContainsKey("end_frame") || request.ContainsKey("reference_frames");
            if (request.ContainsKey("media") && compatibilityMedia) return Invalid("media", "Do not combine media with legacy frame inputs.");
            if (compatibilityMedia && modality != "video") return Invalid("media", "Frame inputs require video.");
            if (request.ContainsKey("media"))
            {
                if (request["media"] is not JsonArray entries) return Invalid("media", "Media must be an array.");
                for (int i = 0; i < entries.Count; i++)
                {
                    if (entries[i] is not JsonObject entry) return Invalid($"media[{i}]", "Media entry must be an object.");
                    if (entry.Any(p => p.Key is not ("semantic_role" or "artifact_id" or "artifact_role"))) return Invalid($"media[{i}]", "Only artifact media references are accepted.");
                    var role = String(entry["semantic_role"]);
                    if (string.IsNullOrWhiteSpace(role)) return Invalid($"media[{i}].semantic_role", "Semantic role is required.");
                    var error = AddMedia(entry, role!, "artifact_role", $"media[{i}]", media);
                    if (error != null) return error;
                }
            }
            else if (compatibilityMedia)
            {
                // An explicit interpolation operation or end frame preserves start/end semantics.
                var startRole = operation == "first_last_frame_to_video" || request.ContainsKey("end_frame") ? "start_frame" : "primary_image";
                foreach (var key in new[] { "start_frame", "end_frame" })
                    if (request.ContainsKey(key))
                    {
                        if (request[key] is not JsonObject entry) return Invalid(key, "Frame must be an artifact object.");
                        var error = AddLegacyMedia(entry, key == "start_frame" ? startRole : "end_frame", key, media);
                        if (error != null) return error;
                    }
                if (request.ContainsKey("reference_frames"))
                {
                    if (request["reference_frames"] is not JsonArray entries) return Invalid("reference_frames", "References must be an array.");
                    for (int i = 0; i < entries.Count; i++)
                    {
                        if (entries[i] is not JsonObject entry) return Invalid($"reference_frames[{i}]", "Reference must be an artifact object.");
                        var error = AddLegacyMedia(entry, "reference_image", $"reference_frames[{i}]", media);
                        if (error != null) return error;
                    }
                }
            }
            var input = new FalModelInput(fields, request["options"] as JsonObject, operation, media);
            var normalized = new ConfiguredGenerationBinding(model, new FalAdapterRegistry(), modality).Normalize(input);
            return new FalRequestParseResult(input, normalized.Request, normalized.Errors);
        }
        private static FalRequestParseResult? AddLegacyMedia(JsonObject entry, string role, string field, List<FalMediaInput> media)
        {
            if (String(entry["kind"]) != "artifact_id" || entry.Any(p => p.Key is not ("kind" or "artifact_id" or "role")))
                return Invalid(field, "Only artifact_id media references are accepted.");
            return AddMedia(entry, role, "role", field, media);
        }
        private static FalRequestParseResult? AddMedia(JsonObject entry, string semanticRole, string roleKey, string field, List<FalMediaInput> media)
        {
            if (!Guid.TryParseExact(String(entry["artifact_id"]), "D", out var id) || id == Guid.Empty) return Invalid(field + ".artifact_id", "Artifact ID must be a non-empty GUID.");
            var artifactRole = String(entry[roleKey]);
            try { media.Add(new FalMediaInput(semanticRole, media.Count(m => m.Role == semanticRole), MediaRef.ForArtifact(id, artifactRole!))); }
            catch (ArgumentException) { return Invalid(field + "." + roleKey, "Artifact role is invalid."); }
            return null;
        }
        internal static string? String(JsonNode? node) => node?.GetValueKind() == JsonValueKind.String ? node.GetValue<string>() : null;
        private static FalRequestParseResult Invalid(string field, string message) => new(null, null, new[] { new FalFieldError(field, message) });
        internal static JsonObject ToJson(Dictionary<string, JsonElement> args) => JsonSerializer.SerializeToNode(args)!.AsObject();
        internal static IReadOnlyList<Dictionary<string, object?>> ProjectDiagnostics(IReadOnlyList<FalCatalogDiagnostic>? diagnostics) =>
            (diagnostics ?? Array.Empty<FalCatalogDiagnostic>()).Select(d => new Dictionary<string, object?>
                { ["file"] = d.File, ["pointer"] = d.Pointer, ["message"] = d.Message }).ToArray();
        internal static void AddCancellation(Dictionary<string, object?> data, FalCancellationSnapshot? cancellation)
        {
            if (cancellation == null) return;
            var json = cancellation.ToJson();
            json["remote_cancellation_confirmed"] = cancellation.RemoteCancellationConfirmed;
            data["cancellation"] = json;
        }
        internal static void AddErrorDetail(Dictionary<string, object?> data, GenerationError error)
        {
            if (error.ProviderErrorCode is "quote_confirmation_required" or "quote_confirmation_invalid" or "quote_stale" or "cost_cap_exceeded" or "pricing_unavailable"
                or "media_preparation_busy" or "media_payload_limit" or "fal_submission_unknown" or "fal_cancellation_requested" or "fal_already_completed" or "fal_already_terminal" or "fal_cancel_failed")
                data["detail_code"] = error.ProviderErrorCode;
        }
        internal static ApiResponse Failure(FalRequestParseResult result) => new()
        {
            Success = false, HttpStatus = 400, Data = new Dictionary<string, object?>
            {
                ["code"] = "invalid_request", ["field"] = result.Errors[0].Field, ["message"] = result.Errors[0].Message,
                ["field_errors"] = result.Errors.Select(e => new Dictionary<string, object?> { ["field"] = e.Field, ["message"] = e.Message }).ToArray()
            }
        };
    }
}
