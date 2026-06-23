using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionModelCatalogTests
{
    // Loads the SHIPPED embedded production catalog (the same resource RookSubsystemRoot loads), so the
    // production-entry assertions below pin the real fal-model-catalog.json, not a test fixture.
    private static ReconstructionModelCatalog ProductionCatalog()
    {
        var assembly = typeof(ReconstructionModelEntry).Assembly;
        const string resourceName = "Rook.Services.Reconstruction.Fal.fal-model-catalog.json";
        using var stream = assembly.GetManifestResourceStream(resourceName)
            ?? throw new InvalidOperationException(
                $"Embedded reconstruction model catalog '{resourceName}' was not found.");
        using var reader = new StreamReader(stream);
        return ReconstructionModelCatalog.FromJson(reader.ReadToEnd());
    }

    [Fact]
    public void FromJson_ParsesOptionsBlock_EnumBooleanInteger_WithIgnoredWhenAndDefaults()
    {
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "test/pro", "provider": "fal", "task": "single_image_to_3d",
            "status": "experimental", "enabled": true,
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
        """;

        var catalog = ReconstructionModelCatalog.FromJson(json);
        var model = catalog.Find("test/pro");

        Assert.NotNull(model!.Options);
        Assert.Equal(3, model.Options!.Length);

        var gen = model.Options[0];
        Assert.Equal("generate_type", gen.Key);
        Assert.Equal("enum", gen.Kind);
        Assert.Equal("Normal", gen.Default!.GetValue<string>());
        Assert.Equal(new[] { "Normal", "Geometry" }, gen.AllowedValues);

        var pbr = model.Options[1];
        Assert.Equal("boolean", pbr.Kind);
        Assert.False(pbr.Default!.GetValue<bool>());
        Assert.Equal("generate_type", pbr.IgnoredWhen!.Key);
        Assert.Equal("Geometry", pbr.IgnoredWhen.EqualsValue);

        var fc = model.Options[2];
        Assert.Equal("integer", fc.Kind);
        Assert.Equal(500000L, fc.Default!.GetValue<long>());
        Assert.Equal(40000L, fc.Min);
        Assert.Equal(1500000L, fc.Max);
        Assert.Equal(10000L, fc.Step);
    }

    [Fact]
    public void ProductionCatalog_IncludesHunyuanPro_WithEightSlotsAndThreeOptions()
    {
        var pro = ProductionCatalog().Find("fal-ai/hunyuan-3d/v3.1/pro/image-to-3d");

        Assert.NotNull(pro);
        Assert.Equal("experimental", pro!.Status);          // flips to stable in Slice 4
        Assert.True(pro.SupportsPbr);
        Assert.True(pro.DefaultTextureExpected);
        Assert.Equal("multi_view_labeled", pro.Input!.Mode);
        Assert.Equal("input_image_url", pro.Input.SourceField);

        var slots = pro.Input.ViewSlots!;
        Assert.Equal(8, slots.Length);
        Assert.Equal(
            new[] { "front", "back", "left", "right", "top", "bottom", "left_front", "right_front" },
            slots.Select(s => s.Role).ToArray());
        Assert.Equal("input_image_url", slots[0].Field);
        Assert.Equal("back_image_url", slots[1].Field);
        Assert.Equal("right_front_image_url", slots[7].Field);
        Assert.True(slots[0].Required);
        Assert.False(slots[1].Required);

        Assert.Equal(3, pro.Options!.Length);
        Assert.Equal(new[] { "generate_type", "enable_pbr", "face_count" },
            pro.Options.Select(o => o.Key).ToArray());
    }

    [Fact]
    public void FromJson_ModelWithoutOptions_DeserializesWithNullOptions()
    {
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "test/legacy", "provider": "fal", "task": "single_image_to_3d",
            "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": false,
            "default_texture_expected": true,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://example.test"
          }]
        }
        """;
        var model = ReconstructionModelCatalog.FromJson(json).Find("test/legacy");
        Assert.Null(model!.Options);
    }

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

    [Fact]
    public void Catalog_PromptDescriptor_Deserializes()
    {
        // Prompt capability is descriptive metadata a future prompt UI reads. Meshy supports a texture
        // prompt; Hunyuan does not.
        var catalog = ProductionCatalog();

        var meshy = catalog.Find("fal-ai/meshy/v6/image-to-3d");
        Assert.NotNull(meshy);
        Assert.NotNull(meshy!.Prompt);
        Assert.True(meshy.Prompt!.Supported);
        Assert.Equal("texture", meshy.Prompt.Kind);

        var hunyuan = catalog.Find("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d");
        Assert.NotNull(hunyuan);
        Assert.NotNull(hunyuan!.Prompt);
        Assert.False(hunyuan.Prompt!.Supported);
    }

    [Fact]
    public void ProductionCatalog_HunyuanRapid_DoesNotAdvertisePbrButStillExpectsDefaultTexture()
    {
        var catalog = ProductionCatalog();

        var hunyuan = catalog.Find("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d");

        Assert.NotNull(hunyuan);
        Assert.False(hunyuan!.SupportsPbr);
        Assert.True(hunyuan.DefaultTextureExpected);
    }

    [Fact]
    public void Catalog_InputMode_Deserializes()
    {
        // Every production entry is single-image input today.
        var catalog = ProductionCatalog();

        foreach (var id in new[]
                 {
                     "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
                     "fal-ai/meshy/v6/image-to-3d",
                     "fal-ai/birefnet/v2",
                 })
        {
            var entry = catalog.Find(id);
            Assert.NotNull(entry);
            Assert.NotNull(entry!.Input);
            Assert.Equal("single_image", entry.Input!.Mode);
        }
    }

    [Fact]
    public void Catalog_AbsentBlocks_DefaultNull_NoThrow()
    {
        // A synthetic entry without input/prompt blocks must still deserialize (both null), proving the
        // new descriptors are additive and back-compatible.
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "fal-ai/no-descriptors", "provider": "fal", "task": "single_image_to_3d",
            "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": false,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://fal.ai/x"
          }]
        }
        """;
        var entry = ReconstructionModelCatalog.FromJson(json).Find("fal-ai/no-descriptors");
        Assert.NotNull(entry);
        Assert.Null(entry!.Input);
        Assert.Null(entry.Prompt);
    }

    [Fact]
    public void Catalog_SchemaShape_Fixtures_RoundTrip()
    {
        // Synthetic-only multi-view + text shapes (no production entry uses them). Pins that view_slots,
        // array and a text mode deserialize and carry their fields.
        const string json = """
        {
          "schema_version": 1,
          "models": [
            {
              "model_id": "synthetic/multi-view-labeled", "provider": "fal", "task": "multi_image_to_3d",
              "status": "experimental", "enabled": true,
              "pipeline_roles": ["multi_image_to_3d"], "input_types": ["image_url"],
              "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
              "fallback_order": ["model_glb"], "supports_pbr": false,
              "input": {
                "mode": "multi_view_labeled",
                "view_slots": [
                  {"role": "front", "field": "front_image_url", "required": true},
                  {"role": "back", "field": "back_image_url", "required": false}
                ]
              },
              "preprocessing": {"recommended": false, "required": false},
              "docs_url": "https://fal.ai/x"
            },
            {
              "model_id": "synthetic/multi-view-array", "provider": "fal", "task": "multi_image_to_3d",
              "status": "experimental", "enabled": true,
              "pipeline_roles": ["multi_image_to_3d"], "input_types": ["image_url"],
              "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
              "fallback_order": ["model_glb"], "supports_pbr": false,
              "input": {
                "mode": "multi_view_array",
                "array": {"field": "image_urls", "min": 2, "max": 8}
              },
              "preprocessing": {"recommended": false, "required": false},
              "docs_url": "https://fal.ai/x"
            },
            {
              "model_id": "synthetic/text", "provider": "fal", "task": "text_to_3d",
              "status": "experimental", "enabled": true,
              "pipeline_roles": ["text_to_3d"], "input_types": ["text"],
              "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
              "fallback_order": ["model_glb"], "supports_pbr": false,
              "input": {"mode": "text"},
              "prompt": {"supported": true, "required": true, "kind": "geometry"},
              "preprocessing": {"recommended": false, "required": false},
              "docs_url": "https://fal.ai/x"
            }
          ]
        }
        """;
        var catalog = ReconstructionModelCatalog.FromJson(json);

        var labeled = catalog.Find("synthetic/multi-view-labeled");
        Assert.NotNull(labeled);
        Assert.Equal("multi_view_labeled", labeled!.Input!.Mode);
        Assert.NotNull(labeled.Input.ViewSlots);
        Assert.Equal(2, labeled.Input.ViewSlots!.Length);
        Assert.Equal("front", labeled.Input.ViewSlots[0].Role);
        Assert.Equal("front_image_url", labeled.Input.ViewSlots[0].Field);
        Assert.True(labeled.Input.ViewSlots[0].Required);
        Assert.False(labeled.Input.ViewSlots[1].Required);
        Assert.Null(labeled.Input.Array);

        var array = catalog.Find("synthetic/multi-view-array");
        Assert.NotNull(array);
        Assert.Equal("multi_view_array", array!.Input!.Mode);
        Assert.NotNull(array.Input.Array);
        Assert.Equal("image_urls", array.Input.Array!.Field);
        Assert.Equal(2, array.Input.Array.Min);
        Assert.Equal(8, array.Input.Array.Max);
        Assert.Null(array.Input.ViewSlots);

        var text = catalog.Find("synthetic/text");
        Assert.NotNull(text);
        Assert.Equal("text", text!.Input!.Mode);
        Assert.NotNull(text.Prompt);
        Assert.True(text.Prompt!.Required);
        Assert.Equal("geometry", text.Prompt.Kind);
    }

    [Fact]
    public void Catalog_BirefnetV2_OutputRoles_AreImageAndMask()
    {
        // Carry-forward: the bg-removal entry advertises file roles image/mask (not the artifact kind).
        var entry = ProductionCatalog().Find("fal-ai/birefnet/v2");

        Assert.NotNull(entry);
        Assert.Equal(new[] { "image", "mask" }, entry!.OutputRoles);
        Assert.Equal("image", entry.PreferredAssetRole);
        Assert.Equal(new[] { "image" }, entry.FallbackOrder);
    }

    private const string TestCatalogJson = """
    {
      "schema_version": 1,
      "models": [
        {"model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d","provider":"fal","task":"single_image_to_3d","status":"stable","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb","model_obj","material_mtl","texture","thumbnail"],"preferred_asset_role":"model_glb","fallback_order":["model_glb","model_obj"],"supports_pbr":true,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"},
        {"model_id":"fal-ai/meshy/v6/image-to-3d","provider":"fal","task":"single_image_to_3d","status":"experimental","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb","thumbnail"],"preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":true,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api"},
        {"model_id":"fal-ai/birefnet/v2","provider":"fal","task":"remove_background","status":"experimental","enabled":true,"pipeline_roles":["preprocess_remove_background"],"input_types":["image_url"],"output_roles":["image","mask"],"preferred_asset_role":"image","fallback_order":["image"],"supports_pbr":false,"input":{"mode":"single_image","source_field":"image_url"},"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/birefnet/v2/api"},
        {"model_id":"dev/hidden","provider":"fal","task":"single_image_to_3d","status":"hidden","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb"],"preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":false,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://example.invalid"}
      ]
    }
    """;
}
