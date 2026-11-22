using System;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalModelNormalizerTests
    {
        [Fact]
        public void Suppliedness_is_preserved_and_json_boundaries_are_detached()
        {
            using var f = new CatalogFiles();
            var options = JsonNode.Parse("{\"audio\":false,\"count\":1}")!.AsObject();
            var input = new FalModelInput(new JsonObject { ["prompt"] = "draw", ["resolution"] = "large", ["seed"] = 0 }, options);
            options["audio"] = true;
            var r = Normalize(f, input); Assert.True(r.Success);
            Assert.False(r.Request!.EffectiveOptions["audio"]!.GetValue<bool>());
            Assert.Equal(0, r.Request.EffectiveRequestFields["seed"]!.GetValue<int>());
            Assert.False(r.Request.SuppliedOptions["audio"]!.GetValue<bool>());
            var copy = r.Request.EffectiveOptions; copy["audio"] = true;
            Assert.False(r.Request.EffectiveOptions["audio"]!.GetValue<bool>());
            Assert.False(r.Request.SuppliedRequestFields.ContainsKey("duration_seconds"));
            Assert.False(r.Request.SuppliedOptions.ContainsKey("strength"));
            Assert.Equal(.1m, r.Request.EffectiveOptions["strength"]!.GetValue<decimal>());
        }

        [Theory]
        [InlineData("options", "audio", "null")]
        [InlineData("options", "audio", "\"false\"")]
        [InlineData("options", "count", "\"3\"")]
        [InlineData("options", "count", "0")]
        [InlineData("options", "strength", "[]")]
        [InlineData("options", "prompt", "\"shadow\"")]
        [InlineData("request", "duration_seconds", "3")]
        [InlineData("request", "resolution", "\"unknown\"")]
        [InlineData("request", "prompt", "null")]
        public void Invalid_types_unknown_keys_and_null_are_field_errors(string scope, string key, string raw)
        {
            using var f = new CatalogFiles();
            var req = new JsonObject { ["prompt"] = "draw", ["resolution"] = "large" }; var opt = new JsonObject();
            (scope == "options" ? opt : req)[key] = JsonNode.Parse(raw);
            var r = Normalize(f, new FalModelInput(req, opt));
            Assert.False(r.Success); Assert.Null(r.Request);
            Assert.Contains(r.Errors, e => e.Field == scope + "." + key);
        }

        [Theory]
        [InlineData("9007199254740992", false)]
        [InlineData("-9007199254740992", false)]
        [InlineData("9007199254740991", true)]
        [InlineData("-9007199254740991", true)]
        [InlineData("1.0", true)]
        [InlineData("1e0", true)]
        public void Integer_contract_rejects_lossy_values(string raw, bool accepted)
        {
            using var f = new CatalogFiles();
            var r = Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw", ["seed"] = JsonNode.Parse(raw) }));
            Assert.Equal(accepted, r.Success);
            if (accepted) Assert.Equal(decimal.Parse(raw, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture), r.Request!.EffectiveRequestFields["seed"]!.GetValue<decimal>());
        }

        [Theory]
        [InlineData("0.000001", true)]
        [InlineData("0.123456", true)]
        [InlineData("999999999.999999", true)]
        [InlineData("1000000000", true)]
        [InlineData("-1000000000", true)]
        [InlineData("1000000000.000001", false)]
        [InlineData("0.0000001", false)]
        [InlineData("0.1234567890123456789012345678", false)]
        [InlineData("0.1000000", true)]
        public void Numeric_contract_rejects_lossy_values(string raw, bool accepted)
        {
            using var f = new CatalogFiles();
            var field = f.Operation["fields"]![4]!.AsObject(); field["min"] = -1000000000; field["max"] = 1000000000; field.Remove("step"); f.Save();
            var r = Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, new JsonObject { ["strength"] = JsonNode.Parse(raw) }));
            Assert.Equal(accepted, r.Success);
        }

        [Theory]
        [InlineData("0.3", true)]
        [InlineData("0.2", false)]
        public void Decimal_step_uses_minimum(string raw, bool accepted)
        {
            using var f = new CatalogFiles();
            var field = f.Operation["fields"]![4]!; field["min"] = .1m; field["step"] = .2m; f.Save();
            Assert.Equal(accepted, Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, new JsonObject { ["strength"] = JsonNode.Parse(raw) })).Success);
        }

        [Fact]
        public void Conditions_omit_defaults_but_never_silently_drop_supplied_values()
        {
            using var f = new CatalogFiles();
            var defaulted = Normalize(f, Prompt()); Assert.True(defaulted.Success);
            Assert.False(defaulted.Request!.EffectiveOptions.ContainsKey("audio"));
            Assert.Contains("options.audio", defaulted.InactiveFields);
            var explicitValue = Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, new JsonObject { ["audio"] = false }));
            Assert.False(explicitValue.Success); Assert.Contains(explicitValue.Errors, e => e.Field == "options.audio");
        }

        [Fact]
        public void Conditions_intersect_and_do_not_repair_impossible_default_filled_combinations()
        {
            using var f = new CatalogFiles();
            f.Operation["fields"]![2]!.AsObject().Remove("default");
            f.Operation["fields"]![1]!.AsObject().Remove("default");
            f.Operation["constraints"] = JsonNode.Parse("""
            [{"kind":"allowed_values","field":"options.count","values":[1,2],"when":[{"field":"options.audio","operator":"eq","value":true}]},
             {"kind":"allowed_values","field":"options.count","values":[2,3],"when":[{"field":"request.resolution","operator":"in","values":["large"]}]},
             {"kind":"required_when","field":"options.count","when":[{"field":"options.audio","operator":"eq","value":true}]}]
            """); f.Save();
            foreach (var count in new[] { 1, 2, 3 })
            {
                var r = Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw", ["resolution"] = "large" }, new JsonObject { ["audio"] = true, ["count"] = count }));
                Assert.Equal(count == 2, r.Success);
            }
            Assert.False(Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, new JsonObject { ["audio"] = true })).Success);
            // A caller activates one guard while a declared default activates another.
            f.Operation["fields"]![2]!["default"] = 1; f.Save();
            Assert.False(Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw", ["resolution"] = "large" }, new JsonObject { ["audio"] = true })).Success);
        }

        [Fact]
        public void Allowed_when_and_role_predicates_validate_against_original_default_filled_values()
        {
            using var f = new CatalogFiles(CatalogFiles.VideoJson);
            f.Operation["fields"]![0]!.AsObject().Remove("default");
            f.Operation["constraints"] = JsonNode.Parse("""
            [{"kind":"required_when","field":"request.duration_seconds","when":[{"role":"end_frame","present":true}]},
             {"kind":"allowed_when","field":"request.duration_seconds","when":[{"role":"start_frame","present":false}]}]
            """); f.Save();
            var media = Frames();
            var missing = Normalize(f, new FalModelInput(media: media)); Assert.False(missing.Success);
            Assert.Contains(missing.Errors, e => e.Field == "request.duration_seconds");
            Assert.False(Normalize(f, new FalModelInput(new JsonObject { ["duration_seconds"] = 5 }, media: media)).Success);
        }

        [Theory]
        [InlineData("https://example.com/a.png")]
        [InlineData("C:\\image.png")]
        [InlineData("image.png")]
        [InlineData("data:image/png;base64,AA")]
        public void Scalars_cannot_introduce_media_but_prompt_is_text(string locator)
        {
            using var f = new CatalogFiles();
            f.Operation["fields"]!.AsArray().Add(JsonNode.Parse("""{"key":"note","scope":"options","type":"string","max_length":1000,"label":"Note","payload":{"pointer":"/note","conversion":"identity"}}""")); f.Save();
            Assert.True(Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = locator })).Success);
            Assert.False(Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, new JsonObject { ["note"] = locator })).Success);
            var scalar = Normalize(f, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, new JsonObject { ["note"] = "plain value" }));
            Assert.True(scalar.Success); Assert.Equal("plain value", scalar.Request!.EffectiveOptions["note"]!.GetValue<string>());
        }

        [Fact]
        public void Only_declared_common_defaults_apply_and_decimal_duration_is_not_narrowed()
        {
            using var f = new CatalogFiles(CatalogFiles.VideoJson);
            var duration = f.Operation["fields"]![0]!.AsObject(); duration.Remove("default");
            duration["type"] = "number"; duration["step"] = .25m; duration["payload"]!["conversion"] = "identity"; f.Save();
            var absent = Normalize(f, new FalModelInput(media: Frames())); Assert.True(absent.Success);
            Assert.Empty(absent.Request!.EffectiveRequestFields);
            var supplied = Normalize(f, new FalModelInput(new JsonObject { ["duration_seconds"] = 1.25m }, media: Frames())); Assert.True(supplied.Success);
            Assert.Equal(1.25m, supplied.Request!.EffectiveRequestFields["duration_seconds"]!.GetValue<decimal>());
            Assert.Equal(1.25m, supplied.Request.SuppliedRequestFields["duration_seconds"]!.GetValue<decimal>());
            var descriptor = new FalDescriptorProjector().Describe(supplied.Request.Binding, supplied).ToJson();
            Assert.Equal("number", descriptor["request_fields"]![0]!["type"]!.GetValue<string>());
            Assert.Null(descriptor["request_fields"]![0]!["default"]);
        }

        [Fact]
        public void Structural_output_count_is_one_for_images_and_video_and_operation_must_match()
        {
            using var image = new CatalogFiles(); using var video = new CatalogFiles(CatalogFiles.VideoJson);
            Assert.False(Normalize(image, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, outputCount: 2)).Success);
            Assert.False(Normalize(video, new FalModelInput(media: Frames(), outputCount: 2)).Success);
            Assert.False(Normalize(image, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, operationId: "image_to_image")).Success);
        }

        [Fact]
        public void Media_cardinality_roles_ordinals_and_artifact_identity_are_validated()
        {
            using var f = new CatalogFiles(CatalogFiles.VideoJson);
            Assert.False(Normalize(f, new FalModelInput()).Success);
            Assert.True(Normalize(f, new FalModelInput(media: Frames())).Success);
            Assert.False(Normalize(f, new FalModelInput(media: Frames().Concat(new[] { Frames()[0] }).ToArray())).Success);
            Assert.False(Normalize(f, new FalModelInput(media: new[] { new FalMediaInput("start_frame", 0, MediaRef.ForPath("C:/a.png", "image")), Frames()[1] })).Success);
        }

        [Fact]
        public void Every_accepted_option_has_one_consumer_and_common_fields_cannot_be_shadowed()
        {
            using var f = new CatalogFiles();
            f.Operation["fields"]![1]!.AsObject().Remove("payload"); f.Save(); Assert.Null(f.Compile().Catalog);
            using var shadow = new CatalogFiles(); shadow.Operation["fields"]![1]!["key"] = "prompt"; shadow.Save(); Assert.Null(shadow.Compile().Catalog);
        }

        internal static FalModelInput Prompt() => new FalModelInput(new JsonObject { ["prompt"] = "draw" });
        internal static FalMediaInput[] Frames() => new[] { new FalMediaInput("start_frame", 0, MediaRef.ForArtifact(Guid.NewGuid(), "image")), new FalMediaInput("end_frame", 0, MediaRef.ForArtifact(Guid.NewGuid(), "image")) };
        internal static FalOperationBinding Binding(CatalogFiles files)
        {
            var compiled = files.Compile(); Assert.Empty(compiled.Diagnostics);
            return compiled.Catalog!.Definitions.Single().Operations.Single();
        }
        internal static FalNormalizationResult Normalize(CatalogFiles files, FalModelInput input) => new FalModelNormalizer().Normalize(Binding(files), input);
    }
}
