using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionOptionsValidatorTests
{
    private static ReconstructionModelEntry ProModel()
        => ReconstructionModelCatalog.FromJson("""
        {
          "schema_version": 1,
          "models": [{
            "model_id": "test/pro", "provider": "fal", "task": "single_image_to_3d",
            "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": true,
            "default_texture_expected": true,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://example.test",
            "options": [
              { "key": "generate_type", "label": "Generate Type", "kind": "enum",
                "default": "Normal", "allowed_values": ["Normal", "Geometry"] },
              { "key": "enable_pbr", "label": "Enable PBR", "kind": "boolean",
                "default": false, "ignored_when": { "key": "generate_type", "equals": "Geometry" } },
              { "key": "face_count", "label": "Face Count", "kind": "integer",
                "default": 500000, "min": 40000, "max": 1500000, "step": 10000 }
            ]
          }]
        }
        """).Find("test/pro")!;

    // Positional ctor (ReconstructionModelCatalog.cs:10-46); Options is the last positional arg.
    private static ReconstructionModelEntry ModelWithOptions(params ReconstructionOptionDescriptor[] options)
        => new(
            "test/model", "fal", "single_image_to_3d", "experimental", true,
            new[] { "single_image_to_3d" }, new[] { "image_url" }, new[] { "model_glb" },
            "model_glb", new[] { "model_glb" }, false,
            new ReconstructionPreprocessingMetadata(false, false), "https://example/docs",
            true, new ReconstructionInputMetadata("single_image", "image_url"), null, options);

    private static ReconstructionModelEntry StringOptModel()
        => ModelWithOptions(new ReconstructionOptionDescriptor(
            "texture_prompt", "Texture Prompt", "string"));

    private static ReconstructionModelEntry UnknownKindModel()
        => ModelWithOptions(new ReconstructionOptionDescriptor(
            "weird", "Weird", "color"));

    [Fact]
    public void Validate_AcceptsStringOption()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["texture_prompt"] = "a red ceramic mug" }, StringOptModel());
        Assert.True(result.Success);
        Assert.Equal("a red ceramic mug", result.Options["texture_prompt"]!.GetValue<string>());
    }

    [Fact]
    public void Validate_RejectsNonStringForStringOption()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["texture_prompt"] = 7 }, StringOptModel());
        Assert.False(result.Success);
    }

    [Fact]
    public void Validate_RejectsUnknownOptionKind()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["weird"] = "x" }, UnknownKindModel());
        Assert.False(result.Success);
    }

    [Fact]
    public void Validate_FillsDefaults_WhenAbsent()
    {
        var result = ReconstructionOptionsValidator.Validate(new JsonObject(), ProModel());
        Assert.True(result.Success);
        Assert.Equal("Normal", result.Options["generate_type"]!.GetValue<string>());
        Assert.False(result.Options["enable_pbr"]!.GetValue<bool>());
        Assert.Equal(500000L, result.Options["face_count"]!.GetValue<long>());
    }

    [Fact]
    public void Validate_OmitsEnablePbr_WhenGeometry()
    {
        var submitted = new JsonObject { ["generate_type"] = "Geometry", ["enable_pbr"] = true };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.True(result.Success);
        Assert.Equal("Geometry", result.Options["generate_type"]!.GetValue<string>());
        Assert.False(result.Options.ContainsKey("enable_pbr"));   // ignored → omitted
    }

    [Fact]
    public void Validate_RejectsUnknownKey()
    {
        var submitted = new JsonObject { ["bogus"] = 1 };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("unknown_option", result.Failure.Details["reason"]);
    }

    [Fact]
    public void Validate_RejectsEnumOutOfRange()
    {
        var submitted = new JsonObject { ["generate_type"] = "Sculpt" };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.False(result.Success);
        Assert.Equal("options.generate_type", result.Failure!.Field);
    }

    [Fact]
    public void Validate_RejectsIntegerOutOfRange()
    {
        var submitted = new JsonObject { ["face_count"] = 10 };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.False(result.Success);
        Assert.Equal("options.face_count", result.Failure!.Field);
    }
}
