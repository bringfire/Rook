using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalDescriptorProjectorTests
    {
        [Fact]
        public void Descriptor_defaults_and_effective_values_share_binding_and_preserve_common_field_metadata()
        {
            using var f = new CatalogFiles(); var binding = FalModelNormalizerTests.Binding(f);
            var normalized = new FalModelNormalizer().Normalize(binding, FalModelNormalizerTests.Prompt()); Assert.True(normalized.Success);
            var descriptor = new FalDescriptorProjector().Describe(binding, normalized); var json = descriptor.ToJson();
            Assert.Equal(binding.DefinitionHash, json["definition_hash"]!.GetValue<string>());
            Assert.Equal(binding.SourceFile, json["source_file"]!.GetValue<string>());
            Assert.Equal("image_job", json["submission_contract"]!.GetValue<string>());
            var common = json["request_fields"]!.AsArray();
            Assert.True(common.Single(n => n!["key"]!.GetValue<string>() == "prompt")!["required"]!.GetValue<bool>());
            Assert.Equal("small", common.Single(n => n!["key"]!.GetValue<string>() == "resolution")!["default"]!.GetValue<string>());
            Assert.Equal("small", normalized.Request!.EffectiveRequestFields["resolution"]!.GetValue<string>());
            Assert.Equal("basic", common[0]!["ui"]!["group"]!.GetValue<string>());
            Assert.Contains(json["inactive_fields"]!.AsArray(), n => n!.GetValue<string>() == "options.audio");
            Assert.Equal(new[] { "small", "large" }, json["capabilities"]!["resolutions"]!.AsArray().Select(n => n!.GetValue<string>()));
            Assert.True(json["paid_admission_available"]!.GetValue<bool>());
            json["request_fields"]!.AsArray().Clear(); Assert.NotEmpty(descriptor.ToJson()["request_fields"]!.AsArray());
        }

        [Fact]
        public void Disabled_unpriced_and_unmatched_pricing_are_visible_with_reasons()
        {
            using var f = new CatalogFiles(); f.Definition["status"] = "disabled"; f.Operation.AsObject().Remove("pricing"); f.Save();
            var json = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(f), null).ToJson();
            Assert.False(json["paid_admission_available"]!.GetValue<bool>());
            Assert.Equal(2, json["unavailable_reasons"]!.AsArray().Count); Assert.NotEmpty(json["request_fields"]!.AsArray());
            using var partial = new CatalogFiles();
            partial.Operation["pricing"]!["rates"]![0]!["selectors"] = new JsonObject { ["request.resolution"] = "small" }; partial.Save();
            var binding = FalModelNormalizerTests.Binding(partial);
            var validation = new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = "draw", ["resolution"] = "large" }));
            Assert.True(validation.Success);
            Assert.False(new FalDescriptorProjector().Describe(binding, validation).ToJson()["paid_admission_available"]!.GetValue<bool>());
        }

        [Fact]
        public void Descriptor_exposes_stable_groups_constraints_required_media_and_field_errors()
        {
            using var f = new CatalogFiles(CatalogFiles.VideoJson);
            f.Operation["fields"]![0]!["ui"] = new JsonObject { ["group"] = "advanced", ["order"] = -5 }; f.Save();
            var binding = FalModelNormalizerTests.Binding(f);
            var validation = new FalModelNormalizer().Normalize(binding, new FalModelInput()); Assert.False(validation.Success);
            var descriptor = new FalDescriptorProjector().Describe(binding, validation).ToJson();
            Assert.Equal("advanced", descriptor["request_fields"]![0]!["ui"]!["group"]!.GetValue<string>());
            Assert.Equal(2, descriptor["media"]!.AsArray().Count); Assert.NotEmpty(descriptor["field_errors"]!.AsArray());
            Assert.Equal("video_job", descriptor["submission_contract"]!.GetValue<string>());
            Assert.Equal(5, descriptor["request_fields"]![0]!["default"]!.GetValue<int>());
            Assert.Empty(descriptor["constraints"]!.AsArray());
        }

        [Fact]
        public void Missing_required_selector_remains_selectable_and_validation_errors_stay_pinned()
        {
            using var f = new CatalogFiles();
            f.Operation["fields"]![5]!.AsObject().Remove("default"); f.Operation["fields"]![5]!["required"] = true;
            f.Operation["pricing"]!["rates"]![0]!["selectors"] = new JsonObject { ["request.resolution"] = "small" }; f.Save();
            var binding = FalModelNormalizerTests.Binding(f);
            var descriptor = new FalDescriptorProjector().Describe(binding, null).ToJson();
            Assert.True(descriptor["selectable"]!.GetValue<bool>());
            Assert.True(descriptor["pricing_available"]!.GetValue<bool>());
            Assert.Equal("requires_inputs", descriptor["pricing_status"]!.GetValue<string>());
            Assert.False(descriptor["paid_admission_available"]!.GetValue<bool>());
            var invalid = new FalModelNormalizer().Normalize(binding, FalModelNormalizerTests.Prompt()); Assert.False(invalid.Success);
            Assert.Contains(invalid.Errors, e => e.Field == "request.resolution");
            using var other = new CatalogFiles(CatalogFiles.VideoJson);
            Assert.Throws<System.ArgumentException>(() => new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(other), invalid));
        }

        [Fact]
        public void Stable_field_order_and_plain_text_labels_do_not_change_declared_types()
        {
            using var f = new CatalogFiles();
            f.Operation["fields"]![0]!["label"] = "<b>Prompt</b>";
            f.Operation["fields"]![3]!["ui"] = new JsonObject { ["group"] = "advanced", ["order"] = -99 };
            f.Operation["fields"]![5]!["ui"] = new JsonObject { ["order"] = 20 }; f.Save();
            var fields = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(f), null).ToJson()["request_fields"]!.AsArray();
            Assert.Equal(new[] { "prompt", "resolution", "seed" }, fields.Select(n => n!["key"]!.GetValue<string>()));
            Assert.Equal(new[] { "string", "enum", "integer" }, fields.Select(n => n!["type"]!.GetValue<string>()));
            Assert.Equal("<b>Prompt</b>", fields[0]!["label"]!.GetValue<string>());
        }

        [Fact]
        public void Legacy_workflow_and_reference_projection_comes_from_operation_and_media()
        {
            using var image = new CatalogFiles();
            var text = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(image), null).ToJson()["capabilities"]!;
            Assert.True(text["supports_text_to_image"]!.GetValue<bool>());
            Assert.False(text["supports_image_to_image"]!.GetValue<bool>());
            Assert.False(text["supports_reference_images"]!.GetValue<bool>());
            using var video = new CatalogFiles(CatalogFiles.VideoJson);
            var interpolation = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(video), null).ToJson()["capabilities"]!;
            Assert.Equal("interp", Assert.Single(interpolation["modes"]!.AsArray())!.GetValue<string>());
            Assert.Empty(interpolation["must_8s_with"]!.AsArray());
            image.Operation["operation_id"] = "image_to_image";
            image.Operation["media"] = JsonNode.Parse("""
            [{"role":"primary_image","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"data_uri","payload":{"pointer":"/image_url","conversion":"identity"}},
             {"role":"reference_image","min_count":0,"max_count":4,"ordered":true,"preparation":"validated_original","transport":"data_uri","payload":{"pointer":"/references","conversion":"ordered_array"}}]
            """); image.Save();
            var edit = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(image), null).ToJson()["capabilities"]!;
            Assert.True(edit["supports_image_to_image"]!.GetValue<bool>());
            Assert.False(edit["supports_text_to_image"]!.GetValue<bool>());
            Assert.True(edit["supports_reference_images"]!.GetValue<bool>());
            Assert.Equal(4, edit["max_reference_images"]!.GetValue<int>());
        }

        [Theory]
        [InlineData("integer", "1", "10", null, true, 10)]
        [InlineData("integer", "1", "9", "2", true, 5)]
        [InlineData("integer", "-2", "2", "2", true, 3)]
        [InlineData("integer", "1", "256", null, true, 256)]
        [InlineData("integer", "1", "257", null, false, 0)]
        [InlineData("integer", "1", "2147483648", null, false, 0)]
        [InlineData("integer", "1", "9007199254740991", "9007199254740991", false, 0)]
        [InlineData("number", "1", "10", "0.25", false, 0)]
        public void Legacy_duration_projection_is_bounded_and_never_narrows_canonical_controls(string type, string min, string max, string? step, bool complete, int count)
        {
            using var f = new CatalogFiles(CatalogFiles.VideoJson);
            var field = f.Operation["fields"]![0]!.AsObject(); field.Remove("default");
            field["type"] = type; field["min"] = JsonNode.Parse(min); field["max"] = JsonNode.Parse(max);
            if (step != null) field["step"] = JsonNode.Parse(step);
            if (type == "number") field["payload"]!["conversion"] = "identity";
            // Isolate compatibility projection from independent positive-seconds pricing requirements.
            f.Operation.Remove("pricing"); f.Save();
            var descriptor = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(f), null).ToJson();
            var capability = descriptor["capabilities"]!;
            Assert.Equal(complete, capability["legacy_duration_projection_complete"]!.GetValue<bool>());
            Assert.Equal(count, capability["durations"]!.AsArray().Count);
            if (complete)
            {
                Assert.Equal(int.Parse(min), capability["durations"]![0]!.GetValue<int>());
                if (min == "-2") Assert.Equal(new[] { -2, 0, 2 }, capability["durations"]!.AsArray().Select(n => n!.GetValue<int>()));
            }
            Assert.Equal(type, descriptor["request_fields"]![0]!["type"]!.GetValue<string>());
            Assert.Equal(decimal.Parse(max), descriptor["request_fields"]![0]!["max"]!.GetValue<decimal>());
        }

        [Fact]
        public void Conditional_duration_restrictions_do_not_become_an_unconditional_legacy_matrix()
        {
            using var f = new CatalogFiles(CatalogFiles.VideoJson);
            f.Operation["fields"]![0]!.AsObject().Remove("default");
            f.Operation["constraints"] = JsonNode.Parse("""[{"kind":"allowed_values","field":"request.duration_seconds","values":[2,4],"when":[{"role":"start_frame","present":true}]}]"""); f.Save();
            var json = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(f), null).ToJson();
            Assert.Empty(json["capabilities"]!["durations"]!.AsArray());
            Assert.False(json["capabilities"]!["legacy_duration_projection_complete"]!.GetValue<bool>());
            Assert.NotEmpty(json["constraints"]!.AsArray());
        }

        [Theory]
        [InlineData("text_to_video", "t2v")]
        [InlineData("image_to_video", "i2v")]
        public void Legacy_video_modes_do_not_introduce_undeclared_duration_defaults(string operation, string mode)
        {
            using var f = new CatalogFiles(CatalogFiles.VideoJson);
            f.Operation["operation_id"] = operation; f.Operation["fields"] = new JsonArray(); f.Operation.Remove("pricing");
            f.Operation["media"] = operation == "text_to_video" ? new JsonArray() : JsonNode.Parse("""[{"role":"primary_image","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"fal_upload","payload":{"pointer":"/image_url","conversion":"identity"}}]"""); f.Save();
            var capability = new FalDescriptorProjector().Describe(FalModelNormalizerTests.Binding(f), null).ToJson()["capabilities"]!;
            Assert.Equal(mode, Assert.Single(capability["modes"]!.AsArray())!.GetValue<string>());
            Assert.Empty(capability["durations"]!.AsArray());
            Assert.False(capability["legacy_duration_projection_complete"]!.GetValue<bool>());
            Assert.False(capability["supports_reference_images"]!.GetValue<bool>());
            Assert.Empty(capability["must_8s_with"]!.AsArray());
        }

        [Fact]
        public void Model_options_preserve_raw_common_suppliedness_and_selected_operation()
        {
            var raw = new JsonObject { ["seed"] = 9007199254740991L }; var options = new FalModelOptions(new FalModelInput(raw), "text_to_image"); raw["seed"] = 1;
            Assert.Equal(9007199254740991L, options.Input.RequestFields["seed"]!.GetValue<long>());
            Assert.False(options.Input.RequestFields.ContainsKey("duration_seconds"));
            Assert.Equal("text_to_image", options.SelectedOperation);
        }
    }
}
