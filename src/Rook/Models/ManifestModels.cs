using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rook.Models
{
    public class ExportManifest
    {
        [JsonPropertyName("version")]
        public string Version { get; set; } = "1.0";

        [JsonPropertyName("source")]
        public ManifestSource? Source { get; set; }

        [JsonPropertyName("settings")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public ManifestSettings? Settings { get; set; }

        [JsonPropertyName("objects")]
        public List<ManifestObject> Objects { get; set; } = new();

        [JsonPropertyName("material_map")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public Dictionary<string, MaterialMapping>? MaterialMap { get; set; }

        [JsonPropertyName("level_placement")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public LevelPlacement? LevelPlacement { get; set; }
    }

    public class ManifestSource
    {
        [JsonPropertyName("tool")]
        public string Tool { get; set; } = "Rook";

        [JsonPropertyName("rhino_version")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? RhinoVersion { get; set; }

        [JsonPropertyName("file")]
        public string File { get; set; } = "";

        [JsonPropertyName("exported_at")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? ExportedAt { get; set; }
    }

    public class ManifestSettings
    {
        [JsonPropertyName("tessellation")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? Tessellation { get; set; }

        [JsonPropertyName("chord_tolerance")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public double? ChordTolerance { get; set; }

        [JsonPropertyName("stitching")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? Stitching { get; set; }

        [JsonPropertyName("up_axis")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? UpAxis { get; set; }

        [JsonPropertyName("default_collision")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? DefaultCollision { get; set; }

        [JsonPropertyName("default_nanite")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public bool? DefaultNanite { get; set; }
    }

    public class ManifestObject
    {
        [JsonPropertyName("rhino_uuid")]
        public string RhinoUuid { get; set; } = "";

        [JsonPropertyName("name")]
        public string Name { get; set; } = "";

        [JsonPropertyName("layer")]
        public string Layer { get; set; } = "";

        [JsonPropertyName("semantic_type")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? SemanticType { get; set; }

        [JsonPropertyName("material_intent")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public JsonElement? MaterialIntent { get; set; }

        [JsonPropertyName("collision")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? Collision { get; set; }

        [JsonPropertyName("nanite")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public bool? Nanite { get; set; }

        [JsonPropertyName("tags")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public List<string>? Tags { get; set; }

        [JsonPropertyName("properties")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public Dictionary<string, object>? Properties { get; set; }
    }

    public class MaterialMapping
    {
        [JsonPropertyName("ue_material")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? UeMaterial { get; set; }

        [JsonPropertyName("ue_material_instance")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public bool? UeMaterialInstance { get; set; }

        [JsonPropertyName("parameters")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public Dictionary<string, object>? Parameters { get; set; }
    }

    public class LevelPlacement
    {
        [JsonPropertyName("origin_offset")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public double[]? OriginOffset { get; set; }

        [JsonPropertyName("scale_factor")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public double? ScaleFactor { get; set; }

        [JsonPropertyName("target_level")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? TargetLevel { get; set; }
    }
}
