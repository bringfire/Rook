using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
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
    [property: JsonPropertyName("docs_url")] string DocsUrl,
    [property: JsonPropertyName("default_texture_expected")] bool DefaultTextureExpected,
    [property: JsonPropertyName("input")] ReconstructionInputMetadata? Input = null,
    [property: JsonPropertyName("prompt")] ReconstructionPromptMetadata? Prompt = null,
    [property: JsonPropertyName("options")] ReconstructionOptionDescriptor[]? Options = null);

public sealed record ReconstructionPreprocessingMetadata(
    [property: JsonPropertyName("recommended")] bool Recommended,
    [property: JsonPropertyName("required")] bool Required);

/// <summary>
/// Input descriptor: the provider input <see cref="Mode"/> (e.g. <c>single_image</c>) and the
/// provider input field (<see cref="SourceField"/>, e.g. <c>image_url</c> for fal-ai/birefnet/v2, or
/// <c>input_image_url</c> for the 3D models) the source image URL is keyed under. The descriptive
/// <see cref="ViewSlots"/> (labeled multi-view) and <see cref="Array"/> (array multi-view) shapes are
/// additive metadata for a future multi-view/prompt UI; no production catalog entry uses them today
/// (exercised by synthetic fixtures only). Nullable on the entry so catalog JSON lacking an
/// <c>input</c> block still deserializes (Input == null).
/// </summary>
public sealed record ReconstructionInputMetadata(
    [property: JsonPropertyName("mode")] string? Mode,
    [property: JsonPropertyName("source_field")] string? SourceField,
    [property: JsonPropertyName("view_slots")] ReconstructionViewSlot[]? ViewSlots = null,
    [property: JsonPropertyName("array")] ReconstructionArraySpec? Array = null);

/// <summary>Labeled multi-view slot descriptor (e.g. {role:"front", field:"front_image_url", required:true}).</summary>
public sealed record ReconstructionViewSlot(
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("field")] string Field,
    [property: JsonPropertyName("required")] bool Required);

/// <summary>Array multi-view descriptor (a single field taking min..max images).</summary>
public sealed record ReconstructionArraySpec(
    [property: JsonPropertyName("field")] string Field,
    [property: JsonPropertyName("min")] int Min,
    [property: JsonPropertyName("max")] int Max);

/// <summary>
/// Prompt-capability descriptor for a model: whether a text prompt is <see cref="Supported"/>,
/// whether it is <see cref="Required"/>, and the prompt <see cref="Kind"/> (e.g. <c>texture</c>).
/// Additive/nullable so older catalog JSON without a <c>prompt</c> block still deserializes.
/// </summary>
public sealed record ReconstructionPromptMetadata(
    [property: JsonPropertyName("supported")] bool Supported,
    [property: JsonPropertyName("required")] bool Required,
    [property: JsonPropertyName("kind")] string? Kind);

/// <summary>
/// Bounded, structured descriptor for a single model option (e.g. generate_type / enable_pbr /
/// face_count). Consumed by the shared <see cref="ReconstructionOptionsValidator"/> and surfaced to
/// the UI via the models endpoint. <see cref="Kind"/> ∈ { "enum", "boolean", "integer" }. Additive /
/// nullable on the entry so catalog JSON without an <c>options</c> block still deserializes.
/// </summary>
public sealed record ReconstructionOptionDescriptor(
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("label")] string Label,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("default")] JsonNode? Default = null,
    [property: JsonPropertyName("allowed_values")] string[]? AllowedValues = null,
    [property: JsonPropertyName("min")] long? Min = null,
    [property: JsonPropertyName("max")] long? Max = null,
    [property: JsonPropertyName("step")] long? Step = null,
    [property: JsonPropertyName("ignored_when")] ReconstructionOptionIgnoredWhen? IgnoredWhen = null);

/// <summary>
/// Conditional-omit rule for an option: when the sibling option <see cref="Key"/> equals
/// <see cref="EqualsValue"/>, this option is ignored (omitted from the submit payload). The C#
/// property is <c>EqualsValue</c> (not <c>Equals</c>, which would collide with the record's
/// synthesized equality members); the JSON key remains <c>equals</c>.
/// </summary>
public sealed record ReconstructionOptionIgnoredWhen(
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("equals")] string EqualsValue);

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
