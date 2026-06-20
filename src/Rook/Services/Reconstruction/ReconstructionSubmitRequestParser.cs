using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionSubmitRequest(
    Guid SourceArtifactId,
    string SourceRole,
    string ModelId,
    IReadOnlyList<ReconstructionPreprocessingStageRequest> PreprocessingChain,
    JsonObject Options,
    bool EstimateRequested);

public sealed record ReconstructionPreprocessingStageRequest(
    string Role,
    string ModelId,
    string InputRole,
    string OutputRole,
    JsonObject Options);

public sealed record ReconstructionParseResult(
    bool Success,
    ReconstructionSubmitRequest? Request,
    ReconstructionFailure? Failure);

public static class ReconstructionSubmitRequestParser
{
    public static ReconstructionParseResult Parse(string? body)
    {
        if (string.IsNullOrWhiteSpace(body))
            return Fail("invalid_request", "Request body is required.", "body");

        JsonObject root;
        try
        {
            root = JsonNode.Parse(body!) as JsonObject
                ?? throw new JsonException("Expected a JSON object.");
        }
        catch (JsonException ex)
        {
            return Fail("invalid_json", ex.Message, "body");
        }

        if (root.ContainsKey("path"))
        {
            return Fail(
                "invalid_request",
                "source_artifact_id is required; local image paths are not accepted.",
                "source_artifact_id");
        }

        if (!TryReadGuid(root, "source_artifact_id", out var sourceArtifactId))
            return Fail("invalid_request", "source_artifact_id is required.", "source_artifact_id");

        var modelId = ReadString(root, "model_id");
        if (string.IsNullOrWhiteSpace(modelId))
            return Fail("invalid_request", "model_id is required.", "model_id");

        var sourceRole = ReadString(root, "source_role");
        sourceRole = string.IsNullOrWhiteSpace(sourceRole) ? "image" : sourceRole;

        var preprocessing = ParsePreprocessing(root["preprocessing_chain"], out var failure);
        if (failure is not null)
            return new ReconstructionParseResult(false, null, failure);

        var options = root["options"] is JsonObject optionsObject
            ? (JsonObject)optionsObject.DeepClone()
            : new JsonObject();
        var estimateRequested = ReadBool(root, "estimate_requested") ?? false;

        return new ReconstructionParseResult(
            true,
            new ReconstructionSubmitRequest(
                sourceArtifactId,
                sourceRole!,
                modelId!,
                preprocessing,
                options,
                estimateRequested),
            null);
    }

    private static IReadOnlyList<ReconstructionPreprocessingStageRequest> ParsePreprocessing(
        JsonNode? node,
        out ReconstructionFailure? failure)
    {
        failure = null;
        if (node is null)
            return Array.Empty<ReconstructionPreprocessingStageRequest>();

        if (node is not JsonArray chain)
        {
            failure = Failure(
                "invalid_request",
                "preprocessing_chain must be an array.",
                "preprocessing_chain");
            return Array.Empty<ReconstructionPreprocessingStageRequest>();
        }

        if (chain.Count > 0)
        {
            failure = Failure(
                "invalid_request",
                "preprocessing_chain execution is not implemented in v0; submit without preprocessing_chain.",
                "preprocessing_chain");
            return Array.Empty<ReconstructionPreprocessingStageRequest>();
        }

        return Array.Empty<ReconstructionPreprocessingStageRequest>();
    }

    private static bool TryReadGuid(JsonObject obj, string name, out Guid value)
    {
        value = default;
        var text = ReadString(obj, name);
        return !string.IsNullOrWhiteSpace(text)
            && Guid.TryParse(text, out value);
    }

    private static string? ReadString(JsonObject obj, string name)
        => obj.TryGetPropertyValue(name, out var node)
            && node is JsonValue value
            && value.TryGetValue<string>(out var text)
                ? text
                : null;

    private static bool? ReadBool(JsonObject obj, string name)
        => obj.TryGetPropertyValue(name, out var node)
            && node is JsonValue value
            && value.TryGetValue<bool>(out var flag)
                ? flag
                : null;

    private static ReconstructionParseResult Fail(string code, string message, string field)
        => new(false, null, Failure(code, message, field));

    private static ReconstructionFailure Failure(string code, string message, string field)
        => new(code, message, false, field, new Dictionary<string, object?>());
}
