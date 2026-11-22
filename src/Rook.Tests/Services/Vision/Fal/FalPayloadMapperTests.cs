using System;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalPayloadMapperTests
    {
        [Fact]
        public void Explicit_mappings_apply_defaults_lookup_integer_conversion_constants_and_escaped_pointers()
        {
            using var f = new CatalogFiles();
            f.Operation["fields"]![4]!["payload"]!["pointer"] = "/a~1b/~0strength";
            f.Operation["fields"]!.AsArray().Add(JsonNode.Parse("""{"key":"optional","scope":"options","type":"string","max_length":10,"label":"Optional","payload":{"pointer":"/optional","conversion":"identity"}}""")); f.Save();
            var binding = FalModelNormalizerTests.Binding(f);
            var normalized = new FalModelNormalizer().Normalize(binding, FalModelNormalizerTests.Prompt());
            Assert.True(normalized.Success);
            var payload = new FalAdapterRegistry().Resolve(binding.AdapterId, binding.AdapterVersion).BuildPayload(normalized.Request!, Array.Empty<FalPreparedMedia>());
            Assert.Equal("draw", payload["prompt"]!.GetValue<string>());
            Assert.Equal("1", payload["count"]!.GetValue<string>());
            Assert.Equal("S", payload["size"]!.GetValue<string>());
            Assert.Equal(.1m, payload["a/b"]!["~strength"]!.GetValue<decimal>());
            Assert.Equal(1, payload["num_images"]!.GetValue<int>());
            Assert.False(payload.ContainsKey("optional")); Assert.False(payload.ContainsKey("audio"));
        }

        [Fact]
        public void Mapping_preserves_reference_ordinals_and_requires_exact_prepared_bindings()
        {
            using var f = new CatalogFiles();
            f.Operation["operation_id"] = "image_to_image";
            f.Operation["media"] = JsonNode.Parse("""
            [{"role":"primary_image","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"data_uri","payload":{"pointer":"/image_url","conversion":"identity"}},
             {"role":"reference_image","min_count":0,"max_count":4,"ordered":true,"preparation":"validated_original","transport":"fal_upload","payload":{"pointer":"/references","conversion":"ordered_array"}}]
            """); f.Save();
            var inputs = new[] { Media("reference_image", 1), Media("primary_image", 0), Media("reference_image", 0) };
            var binding = FalModelNormalizerTests.Binding(f);
            var normalized = new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, media: inputs)); Assert.True(normalized.Success);
            var adapter = new FalAdapterRegistry().Resolve(binding.AdapterId, 1);
            var prepared = new[] { new FalPreparedMedia("reference_image", 1, "second"), new FalPreparedMedia("primary_image", 0, "primary"), new FalPreparedMedia("reference_image", 0, "first") };
            Assert.Equal(new[] { "first", "second" }, adapter.BuildPayload(normalized.Request!, prepared)["references"]!.AsArray().Select(n => n!.GetValue<string>()));
            Assert.Throws<ArgumentException>(() => adapter.BuildPayload(normalized.Request!, prepared.Take(2).ToArray()));
            Assert.Throws<ArgumentException>(() => adapter.BuildPayload(normalized.Request!, prepared.Concat(new[] { prepared[0] }).ToArray()));
            Assert.False(new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, media: new[] { inputs[1], Media("reference_image", 1) })).Success);
        }

        [Fact]
        public void Numeric_values_remain_exact_through_payload_and_descriptor_serialization()
        {
            using var f = new CatalogFiles(); var field = f.Operation["fields"]![4]!.AsObject(); field["max"] = 1000000000; field.Remove("step"); f.Save();
            var binding = FalModelNormalizerTests.Binding(f);
            var result = new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = "draw", ["seed"] = 9007199254740991L }, new JsonObject { ["strength"] = 999999999.999999m })); Assert.True(result.Success);
            var payload = new FalAdapterRegistry().Resolve(binding.AdapterId, 1).BuildPayload(result.Request!, Array.Empty<FalPreparedMedia>());
            Assert.Equal(9007199254740991m, JsonNode.Parse(payload.ToJsonString())!["seed"]!.GetValue<decimal>());
            Assert.Equal(999999999.999999m, JsonNode.Parse(payload.ToJsonString())!["strength"]!.GetValue<decimal>());
            var descriptor = new FalDescriptorProjector().Describe(binding, result).ToJson();
            Assert.Equal(-9007199254740991m, descriptor["request_fields"]!.AsArray().Single(n => n!["key"]!.GetValue<string>() == "seed")!["min"]!.GetValue<decimal>());
        }

        [Theory]
        [InlineData("{\"images\":[]}")]
        [InlineData("{\"images\":[{\"url\":\"https://v3.fal.media/a.png\"},{\"url\":\"https://v3.fal.media/b.png\"}]}")]
        [InlineData("{\"images\":{\"0\":{\"url\":\"https://v3.fal.media/a.png\"}}}")]
        [InlineData("{\"images\":[{\"url\":\"file:///C:/a.png\"}]}")]
        [InlineData("{\"images\":[{\"url\":\"https://v3.fal.media/a.png\",\"content_type\":\"video/mp4\"}]}")]
        [InlineData("{\"images\":[{\"url\":null}]}")]
        public void Invalid_result_shapes_fail_without_truncation(string raw)
        {
            using var f = new CatalogFiles(); var binding = FalModelNormalizerTests.Binding(f);
            Assert.IsType<FailedResultOutcome>(new FalAdapterRegistry().Resolve(binding.AdapterId, 1).MapResult(binding, JsonNode.Parse(raw)!.AsObject()));
        }

        [Fact]
        public void Image_and_video_synthetic_adapters_match_existing_wire_shapes_and_return_url_artifacts()
        {
            using var image = FluxLike(); using var video = KlingLike();
            // Wire shape from the existing FLUX-like sync fixture; synthetic identity remains unchanged.
            var imageBinding = FalModelNormalizerTests.Binding(image);
            var adapter = new FalAdapterRegistry().Resolve(imageBinding.AdapterId, 1);
            var imageRequest = new FalModelNormalizer().Normalize(imageBinding, new FalModelInput(new JsonObject { ["prompt"] = "sunlit massing study" })); Assert.True(imageRequest.Success);
            var imagePayload = adapter.BuildPayload(imageRequest.Request!, Array.Empty<FalPreparedMedia>());
            Assert.Equal("landscape_16_9", imagePayload["image_size"]!.GetValue<string>());
            Assert.Equal(1, imagePayload["num_images"]!.GetValue<int>());
            Assert.True(imagePayload["enable_safety_checker"]!.GetValue<bool>());
            Assert.Equal("jpeg", imagePayload["output_format"]!.GetValue<string>());
            Assert.False(imagePayload["sync_mode"]!.GetValue<bool>());
            Assert.Equal(6, imagePayload.Count);
            var mapped = Assert.IsType<SuccessResultOutcome>(adapter.MapResult(imageBinding, JsonNode.Parse("""{"images":[{"url":"https://fal.media/files/result.jpg","content_type":"image/jpeg","width":1536,"height":864}],"seed":12345,"prompt":"sunlit massing study","timings":{"inference":0.42},"has_nsfw_concepts":[false]}""")!.AsObject()));
            Assert.Single(mapped.Envelope.Artifacts); Assert.Equal("image", mapped.Envelope.Artifacts[0].Role);
            Assert.Equal("image/jpeg", mapped.Envelope.Artifacts[0].DeclaredMimeType);
            Assert.Equal("https://fal.media/files/result.jpg", Assert.IsType<RemoteArtifactBody>(mapped.Envelope.Artifacts[0].Body).Url.ToString());
            // Kling-like queued interpolation payload: first/last uploaded frames and duration text.
            var videoBinding = FalModelNormalizerTests.Binding(video); var videoAdapter = new FalAdapterRegistry().Resolve(videoBinding.AdapterId, 1);
            var normalized = new FalModelNormalizer().Normalize(videoBinding, new FalModelInput(new JsonObject { ["prompt"] = "animate this source" }, media: FalModelNormalizerTests.Frames())); Assert.True(normalized.Success);
            var payload = videoAdapter.BuildPayload(normalized.Request!, new[] { new FalPreparedMedia("end_frame", 0, "https://v3b.fal.media/files/end.jpg"), new FalPreparedMedia("start_frame", 0, "https://v3b.fal.media/files/start.png") });
            Assert.Equal("5", payload["duration"]!.GetValue<string>());
            Assert.Equal("animate this source", payload["prompt"]!.GetValue<string>());
            Assert.Equal("https://v3b.fal.media/files/start.png", payload["start_image_url"]!.GetValue<string>());
            Assert.Equal("https://v3b.fal.media/files/end.jpg", payload["end_image_url"]!.GetValue<string>());
            Assert.False(payload["generate_audio"]!.GetValue<bool>());
            Assert.Equal(5, payload.Count);
            var result = Assert.IsType<SuccessResultOutcome>(videoAdapter.MapResult(videoBinding, JsonNode.Parse("""{"video":{"url":"https://v3.fal.media/video.mp4","content_type":"video/mp4"}}""")!.AsObject()));
            Assert.Equal("video", Assert.Single(result.Envelope.Artifacts).Role);
            Assert.Throws<ArgumentException>(() => adapter.BuildPayload(normalized.Request!, Array.Empty<FalPreparedMedia>()));
        }

        [Fact]
        public void Response_root_mime_and_escaped_result_pointers_are_resolved_after_count_validation()
        {
            using var f = new CatalogFiles();
            f.Operation["result"]!["collection_pointer"] = "/a~1b"; f.Operation["result"]!["url_pointer"] = "/a~1b/0/~0url"; f.Operation["result"]!["mime_pointer"] = "/metadata/content_type"; f.Save();
            var binding = FalModelNormalizerTests.Binding(f);
            var outcome = new FalAdapterRegistry().Resolve(binding.AdapterId, 1).MapResult(binding, JsonNode.Parse("""{"a/b":[{"~url":"https://v3.fal.media/a.png"}],"metadata":{"content_type":"image/png"}}""")!.AsObject());
            Assert.Equal("image/png", Assert.Single(Assert.IsType<SuccessResultOutcome>(outcome).Envelope.Artifacts).DeclaredMimeType);
        }

        [Fact]
        public void Registry_exactly_matches_compiler_adapter_ids_and_versions()
        {
            var registry = new FalAdapterRegistry();
            foreach (var tuple in new[] { (CatalogFiles.ImageJson, "fal.image.declarative"), (CatalogFiles.VideoJson, "fal.video.declarative") })
            {
                using var f = new CatalogFiles(tuple.Item1); var binding = FalModelNormalizerTests.Binding(f);
                Assert.Equal(tuple.Item2, binding.AdapterId); Assert.NotNull(registry.Resolve(tuple.Item2, 1));
                f.Operation["adapter"]!["version"] = 2; f.Save(); Assert.Null(f.Compile().Catalog);
                Assert.Throws<NotSupportedException>(() => registry.Resolve(tuple.Item2, 2));
            }
            Assert.Throws<NotSupportedException>(() => registry.Resolve("untrusted", 1));
        }
        private static CatalogFiles FluxLike()
        {
            var files = new CatalogFiles(); files.Definition["model_id"] = "synthetic/flux-like";
            files.Operation["fields"] = JsonNode.Parse("""
            [{"key":"prompt","scope":"request","type":"string","required":true,"max_length":1000,"label":"Prompt","payload":{"pointer":"/prompt","conversion":"identity"}},
             {"key":"aspect_ratio","scope":"request","type":"enum","values":["16:9"],"default":"16:9","label":"Aspect","payload":{"pointer":"/image_size","conversion":"enum_lookup","lookup":{"16:9":"landscape_16_9"}}}]
            """);
            files.Operation["constraints"] = new JsonArray();
            files.Operation["constants"] = JsonNode.Parse("""
            [{"pointer":"/num_images","value":1},{"pointer":"/enable_safety_checker","value":true},{"pointer":"/output_format","value":"jpeg"},{"pointer":"/sync_mode","value":false}]
            """); files.Save(); return files;
        }
        private static CatalogFiles KlingLike()
        {
            var files = new CatalogFiles(CatalogFiles.VideoJson); files.Definition["model_id"] = "synthetic/kling-like";
            files.Operation["fields"]!.AsArray().Add(JsonNode.Parse("""{"key":"prompt","scope":"request","type":"string","required":true,"max_length":1000,"label":"Prompt","payload":{"pointer":"/prompt","conversion":"identity"}}"""));
            files.Operation["fields"]!.AsArray().Add(JsonNode.Parse("""{"key":"generate_audio","scope":"options","type":"boolean","default":false,"label":"Generate audio","payload":{"pointer":"/generate_audio","conversion":"identity"}}"""));
            files.Operation["media"]![0]!["payload"]!["pointer"] = "/start_image_url";
            files.Operation["media"]![1]!["payload"]!["pointer"] = "/end_image_url"; files.Save(); return files;
        }
        private static FalMediaInput Media(string role, int ordinal) => new FalMediaInput(role, ordinal, MediaRef.ForArtifact(Guid.NewGuid(), "image"));
    }
}
