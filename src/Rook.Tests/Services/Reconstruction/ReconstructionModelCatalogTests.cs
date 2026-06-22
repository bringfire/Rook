using System.Linq;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionModelCatalogTests
{
    [Fact]
    public void List_Default_ReturnsOnlyEnabledStableModels()
    {
        var catalog = ReconstructionModelCatalog.FromJson(TestCatalogJson);

        var models = catalog.List(includeExperimental: false, includeHidden: false);

        var only = Assert.Single(models);
        Assert.Equal("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", only.ModelId);
        Assert.Equal("stable", only.Status);
        Assert.True(only.Enabled);
    }

    [Fact]
    public void List_WithExperimental_IncludesMeshyAndBirefnet()
    {
        var catalog = ReconstructionModelCatalog.FromJson(TestCatalogJson);

        var ids = catalog.List(includeExperimental: true, includeHidden: false)
            .Select(m => m.ModelId)
            .ToArray();

        Assert.Contains("fal-ai/meshy/v6/image-to-3d", ids);
        Assert.Contains("fal-ai/birefnet/v2", ids);
        Assert.DoesNotContain("dev/hidden", ids);
    }

    [Fact]
    public void Input_SourceField_DeserializesForBirefnetV2()
    {
        // Pins the load-bearing real-submit contract: the bg-removal entry is fal-ai/birefnet/v2 and its
        // input.source_field is image_url. If either drifts the real submit posts the wrong field.
        var catalog = ReconstructionModelCatalog.FromJson(TestCatalogJson);

        var entry = catalog.Find("fal-ai/birefnet/v2");
        Assert.NotNull(entry);
        Assert.Equal("image_url", entry!.Input!.SourceField);
        Assert.Equal("single_image", entry.Input.Mode);
    }

    [Fact]
    public void Input_DefaultsNull_WhenAbsent()
    {
        // Older catalog JSON without an `input` block must still deserialize (Input == null).
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "fal-ai/no-input", "provider": "fal", "task": "single_image_to_3d",
            "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": false,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://fal.ai/x"
          }]
        }
        """;
        var entry = ReconstructionModelCatalog.FromJson(json).Find("fal-ai/no-input");
        Assert.NotNull(entry);
        Assert.Null(entry!.Input);
    }

    [Fact]
    public void DefaultTextureExpected_ParsesTrue_WhenPresent()
    {
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            "provider": "fal", "task": "single_image_to_3d", "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": true,
            "default_texture_expected": true,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://fal.ai/x"
          }]
        }
        """;
        var entry = ReconstructionModelCatalog.FromJson(json).Find("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d");
        Assert.NotNull(entry);
        Assert.True(entry!.DefaultTextureExpected);
    }

    [Fact]
    public void DefaultTextureExpected_DefaultsFalse_WhenAbsent()
    {
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "fal-ai/minimal", "provider": "fal", "task": "single_image_to_3d",
            "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": false,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://fal.ai/x"
          }]
        }
        """;
        var entry = ReconstructionModelCatalog.FromJson(json).Find("fal-ai/minimal");
        Assert.NotNull(entry);
        Assert.False(entry!.DefaultTextureExpected);   // absent → false, no accidental default-true
    }

    private const string TestCatalogJson = """
    {
      "schema_version": 1,
      "models": [
        {"model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d","provider":"fal","task":"single_image_to_3d","status":"stable","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb","model_obj","material_mtl","texture","thumbnail"],"preferred_asset_role":"model_glb","fallback_order":["model_glb","model_obj"],"supports_pbr":true,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"},
        {"model_id":"fal-ai/meshy/v6/image-to-3d","provider":"fal","task":"single_image_to_3d","status":"experimental","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb","thumbnail"],"preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":true,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api"},
        {"model_id":"fal-ai/birefnet/v2","provider":"fal","task":"remove_background","status":"experimental","enabled":true,"pipeline_roles":["preprocess_remove_background"],"input_types":["image_url"],"output_roles":["preprocessed_image","mask"],"preferred_asset_role":"preprocessed_image","fallback_order":["preprocessed_image"],"supports_pbr":false,"input":{"mode":"single_image","source_field":"image_url"},"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/birefnet/v2/api"},
        {"model_id":"dev/hidden","provider":"fal","task":"single_image_to_3d","status":"hidden","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb"],"preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":false,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://example.invalid"}
      ]
    }
    """;
}
