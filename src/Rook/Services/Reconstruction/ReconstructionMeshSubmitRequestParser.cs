using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionMeshSubmitRequest(
    Guid SourcePackageId,
    string ModelId,
    JsonObject Options,
    bool AllowExperimentalModel);

public sealed record ReconstructionMeshParseResult(
    bool Success,
    ReconstructionMeshSubmitRequest? Request,
    ReconstructionFailure? Failure);

public static class ReconstructionMeshSubmitRequestParser
{
    public static ReconstructionMeshParseResult Parse(string? body)
    {
        JsonObject root;
        try
        {
            root = (JsonNode.Parse(string.IsNullOrWhiteSpace(body) ? "{}" : body) as JsonObject)
                ?? throw new FormatException();
        }
        catch
        {
            return Fail("invalid_request", "Request body must be a JSON object.", "body");
        }

        if (!root.TryGetPropertyValue("source_package_id", out var pkgNode)
            || pkgNode is not JsonValue pkgVal
            || !pkgVal.TryGetValue<string>(out var pkgStr)
            || !Guid.TryParse(pkgStr, out var sourcePackageId))
        {
            return Fail("invalid_request", "source_package_id is required.", "source_package_id");
        }

        var modelId = (root["model_id"] as JsonValue)?.TryGetValue<string>(out var m) == true ? m : null;
        if (string.IsNullOrWhiteSpace(modelId))
            return Fail("invalid_request", "model_id is required.", "model_id");

        JsonObject options;
        if (root.TryGetPropertyValue("options", out var optNode) && optNode is not null)
        {
            if (optNode is not JsonObject optObj)
                return Fail("invalid_request", "options must be a JSON object.", "options");
            options = (JsonObject)optObj.DeepClone();
        }
        else
        {
            options = new JsonObject();
        }

        var allowExperimental = false;
        if (root.TryGetPropertyValue("allow_experimental_model", out var allowNode) && allowNode is not null)
        {
            if (allowNode is JsonValue allowValue && allowValue.TryGetValue<bool>(out var allowFlag))
                allowExperimental = allowFlag;
            else
                return Fail("invalid_request", "allow_experimental_model must be a boolean.", "allow_experimental_model");
        }

        return new ReconstructionMeshParseResult(
            true,
            new ReconstructionMeshSubmitRequest(sourcePackageId, modelId!, options, allowExperimental),
            null);
    }

    private static ReconstructionMeshParseResult Fail(string code, string message, string field)
        => new(false, null, new ReconstructionFailure(code, message, false, field,
            new Dictionary<string, object?>(StringComparer.Ordinal)));
}
