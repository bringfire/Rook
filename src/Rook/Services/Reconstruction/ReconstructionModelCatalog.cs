using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionModelEntry(
    [property: JsonPropertyName("model_id")] string ModelId,
    [property: JsonPropertyName("provider")] string Provider,
    [property: JsonPropertyName("task")] string Task,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("enabled")] bool Enabled,
    [property: JsonPropertyName("pipeline_roles")] string[] PipelineRoles,
    [property: JsonPropertyName("input_types")] string[] InputTypes,
    [property: JsonPropertyName("output_roles")] string[] OutputRoles,
    [property: JsonPropertyName("preferred_asset_role")] string PreferredAssetRole,
    [property: JsonPropertyName("fallback_order")] string[] FallbackOrder,
    [property: JsonPropertyName("supports_pbr")] bool SupportsPbr,
    [property: JsonPropertyName("preprocessing")] ReconstructionPreprocessingMetadata Preprocessing,
    [property: JsonPropertyName("docs_url")] string DocsUrl);

public sealed record ReconstructionPreprocessingMetadata(
    [property: JsonPropertyName("recommended")] bool Recommended,
    [property: JsonPropertyName("required")] bool Required);

public sealed class ReconstructionModelCatalog
{
    private readonly IReadOnlyList<ReconstructionModelEntry> _models;

    private ReconstructionModelCatalog(IReadOnlyList<ReconstructionModelEntry> models)
    {
        _models = models;
    }

    public static ReconstructionModelCatalog FromJson(string json)
    {
        var envelope = JsonSerializer.Deserialize<CatalogEnvelope>(json)
            ?? throw new InvalidOperationException("Reconstruction catalog JSON is empty.");
        return new ReconstructionModelCatalog(envelope.Models);
    }

    public IReadOnlyList<ReconstructionModelEntry> List(
        bool includeExperimental,
        bool includeHidden)
        => _models
            .Where(m => m.Enabled)
            .Where(m => includeHidden ||
                !string.Equals(m.Status, "hidden", StringComparison.OrdinalIgnoreCase))
            .Where(m => includeExperimental ||
                string.Equals(m.Status, "stable", StringComparison.OrdinalIgnoreCase))
            .ToArray();

    public ReconstructionModelEntry? Find(string modelId)
        => _models.FirstOrDefault(m =>
            string.Equals(m.ModelId, modelId, StringComparison.Ordinal));

    private sealed record CatalogEnvelope(
        [property: JsonPropertyName("schema_version")] int SchemaVersion,
        [property: JsonPropertyName("models")] ReconstructionModelEntry[] Models);
}
