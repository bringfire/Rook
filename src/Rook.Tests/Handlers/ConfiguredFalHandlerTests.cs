using System;
using System.Linq;
using System.IO;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Rook.Services.Vision.Image.Gemini;
using System.Collections.Generic;
using System.Text.Json;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Xunit;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Rook.Tests.Services.Vision.Fal;

namespace Rook.Tests.Handlers
{
    internal sealed class InMemoryGenerationSecretStore : IGenerationSecretStore { public string? GetSecret(string key) => throw new Exception("No secret reads expected"); public bool HasSecret(string key) => false; public string? GetPreview(string key) => null; public void SetSecret(string key, string value) {} public void RemoveSecret(string key) {} }
    public partial class ConfiguredFalHandlerTests
    {
        [Fact]
        public void Configured_media_resolves_exact_artifact_role_without_legacy_remapping()
        {
            using var files = new CatalogFiles(); var store = new ArtifactStore(Path.Combine(files.Root, "artifacts"));
            var expected = new byte[] { 137, 80, 78, 71, 13, 10, 26, 10, 42 };
            var artifact = store.Create("captured_viewport", new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png"), new BlobInput("input_image", expected, "png") });
            var handler = new VisionHandler(store, new InMemoryGenerationSecretStore(), new PromptEnhancer(), new ViewportHandler());
            var source = MediaRef.ForArtifact(artifact.Id, "input_image");
            using var resolved = handler.ResolveConfiguredImageMedia(new[] { source });
            Assert.True(resolved.Success); Assert.Equal(expected, resolved.Resolved![source].Bytes);
        }

        [Theory]
        [InlineData("null", false)] [InlineData("false", false)] [InlineData("0", true)]
        [InlineData("1.5", false)] [InlineData("9007199254740991", true)] [InlineData("9007199254740992", false)]
        [InlineData("\"3\"", false)]
        public void Parser_keeps_numeric_kinds_and_safe_integer_contract(string value, bool accepted)
        {
            using var files = new CatalogFiles();
            var raw = JsonNode.Parse("{\"model\":\"synthetic/image\",\"prompt\":\"test\",\"seed\":" + value + "}")!.AsObject();
            var result = FalConfiguredRequestParser.Parse(raw, files.Compile().Catalog!, "image");
            Assert.Equal(accepted, result.Success);
            if (accepted) Assert.Equal(raw["seed"]!.ToJsonString(), result.Input!.RequestFields["seed"]!.ToJsonString());
            else Assert.Contains(result.Errors, e => e.Field.Contains("seed"));
        }

        [Theory]
        [InlineData("null")] [InlineData("false")] [InlineData("[]")] [InlineData("0")]
        public void Explicit_nonobject_options_do_not_become_omission(string options)
        {
            using var files = new CatalogFiles();
            var raw = JsonNode.Parse("{\"model\":\"synthetic/image\",\"prompt\":\"test\",\"options\":" + options + "}")!.AsObject();
            var result = FalConfiguredRequestParser.Parse(raw, files.Compile().Catalog!, "image");
            Assert.False(result.Success); Assert.Equal("options", result.Errors[0].Field);
        }

        [Fact]
        public void Operation_requirements_and_legacy_video_media_translation_are_semantic()
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            var catalog = files.Compile().Catalog!;
            var request = new JsonObject { ["model"] = "synthetic/video" };
            Assert.False(FalConfiguredRequestParser.Parse(request, catalog, "video").Success);
            JsonObject Old(string role) => new() { ["kind"] = "artifact_id", ["artifact_id"] = Guid.NewGuid().ToString("D"), ["role"] = role };
            request["start_frame"] = Old("image"); request["end_frame"] = Old("poster");
            var result = FalConfiguredRequestParser.Parse(request, catalog, "video");
            Assert.True(result.Success); Assert.False(result.Input!.RequestFields.ContainsKey("duration_seconds"));
            Assert.Equal(5, result.Request!.EffectiveRequestFields["duration_seconds"]!.GetValue<int>());
            Assert.False(result.Request.EffectiveRequestFields.ContainsKey("prompt"));
            Assert.Equal(new[] { "start_frame", "end_frame" }, result.Input.Media.Select(m => m.Role));
            Assert.Equal(new[] { "image", "poster" }, result.Input.Media.Select(m => m.Source.Role));
            request["media"] = new JsonArray(); Assert.False(FalConfiguredRequestParser.Parse(request, catalog, "video").Success); request.Remove("media");
            request["mode"] = "t2v"; request["operation"] = "first_last_frame_to_video";
            Assert.Equal("operation", FalConfiguredRequestParser.Parse(request, catalog, "video").Errors[0].Field);
            request.Remove("operation"); request["mode"] = "i2v"; request.Remove("end_frame");
            files.Operation["operation_id"] = "image_to_video";
            files.Operation["media"]!.AsArray().RemoveAt(1); files.Operation["media"]![0]!["role"] = "primary_image"; files.Save();
            result = FalConfiguredRequestParser.Parse(request, files.Compile().Catalog!, "video");
            Assert.True(result.Success); Assert.Equal("primary_image", Assert.Single(result.Input!.Media).Role);
        }

        [Theory]
        [InlineData("missing")] [InlineData("invalid")] [InlineData("removed")] [InlineData("never-known")]
        public async Task Catalog_failures_preserve_legacy_and_reject_unknown_on_both_image_entry_points(string kind)
        {
            using var files = new CatalogFiles();
            var directory = Path.Combine(files.Root, "assembly", "vision-models", "fal"); Directory.CreateDirectory(directory);
            File.Copy(Path.Combine(files.Root, "image.json"), Path.Combine(directory, "image.json"));
            if (kind != "missing") File.WriteAllText(Path.Combine(directory, "catalog.json"), kind == "invalid" ? "{}" : "{\"schema_version\":1,\"definitions\":[]}");
            var store = new ArtifactStore(Path.Combine(files.Root, "artifacts"));
            var root = new RookSubsystemRoot(store, new InMemoryGenerationSecretStore(),
                new JsonlVideoJobLedger(Path.Combine(files.Root, "video.jsonl")), new JsonlImageJobLedger(Path.Combine(files.Root, "image.jsonl")), visionCatalogAssemblyDirectory: Path.Combine(files.Root, "assembly"));
            try
            {
            Assert.Empty(root.VisionCatalog.Catalog?.Definitions ?? Array.Empty<FalModelDefinition>());
            if (kind is "missing" or "invalid") Assert.NotEmpty(root.VisionCatalog.Diagnostics);
            var baseline = new DefaultImageProviderRegistry(VisionProviderRegistrations.CreateImageRegistrations(() => null, () => null, () => null));
            Assert.Equal(baseline.EnumerateAllModels().Select(m => m.ModelId), root.ImageJobs.Registry.EnumerateAllModels().Select(m => m.ModelId));
            var vision = new VisionHandler(store, new InMemoryGenerationSecretStore(), new PromptEnhancer(), new ViewportHandler(), root.ImageJobs.Registry);
            var jobs = new ImageJobOpHandler(root.ImageJobs.Manager, vision, new VideoPreparationResources());
            var images = Wire(vision.DispatchOffUi("{\"op\":\"list_image_models\"}"));
            var videoHandler = new VideoOpHandler(root.Video.Manager, root.Video.Registry, root.Video.Estimator, root.Video.Framing, root.Video.MediaResolver);
            var videos = Wire(videoHandler.DispatchOffUi("{\"op\":\"list_video_models\"}"));
            Assert.NotNull(images["catalog_diagnostics"]); Assert.NotNull(videos["catalog_diagnostics"]);
            Assert.Equal(images["catalog_diagnostics"]!.ToJsonString(), videos["catalog_diagnostics"]!.ToJsonString());
            Assert.Equal(root.VisionCatalog.Diagnostics.Count, images["catalog_diagnostics"]!.AsArray().Count);
            if (kind is "missing" or "invalid")
            {
                var diagnostic = images["catalog_diagnostics"]![0]!.AsObject();
                Assert.Equal(new[] { "file", "message", "pointer" }, diagnostic.Select(p => p.Key).OrderBy(k => k));
                Assert.Equal(root.VisionCatalog.Diagnostics[0].File, diagnostic["file"]!.GetValue<string>());
            }

            var body = new JsonObject { ["model"] = kind == "never-known" ? "unknown/model" : "synthetic/image", ["op"] = "generate", ["input_image_path"] = "missing.png" };
            var legacy = await vision.DispatchAsync(body.ToJsonString()); Assert.False(legacy.Success); Assert.Equal("model_unavailable", Wire(legacy)["code"]!.GetValue<string>());
            body["op"] = "image_generate_start";
            var current = await jobs.DispatchAsync(body.ToJsonString()); Assert.False(current.Success); Assert.Equal("model_unavailable", Wire(current)["code"]!.GetValue<string>());
            Assert.Empty(store.List()); Assert.Empty((await root.ImageJobs.Manager.ListJobsAsync(10, default)).Jobs);
            } finally { root.DisposeCreatedSubsystems(); }
        }

        [Fact]
        public void Reserved_ids_cover_legacy_aliases_and_both_registries_share_one_root_snapshot()
        {
            var reserved = VisionProviderRegistrations.GetLegacyModelIds();
            Assert.Contains("nano-banana-2", reserved); Assert.Contains("nano-banana-pro", reserved);
            using var files = new CatalogFiles();
            var directory = Path.Combine(files.Root, "assembly", "vision-models", "fal"); Directory.CreateDirectory(directory);
            File.Copy(Path.Combine(files.Root, "image.json"), Path.Combine(directory, "image.json"));
            File.Copy(Path.Combine(files.Root, "catalog.json"), Path.Combine(directory, "catalog.json"));
            var root = new RookSubsystemRoot(new ArtifactStore(Path.Combine(files.Root, "artifacts")), new InMemoryGenerationSecretStore(),
                new JsonlVideoJobLedger(Path.Combine(files.Root, "video.jsonl")), new JsonlImageJobLedger(Path.Combine(files.Root, "image.jsonl")), visionCatalogAssemblyDirectory: Path.Combine(files.Root, "assembly"));
            try
            {
            var image = Assert.IsType<DefaultImageProviderRegistry>(root.ImageJobs.Registry);
            var video = Assert.IsType<DefaultVideoProviderRegistry>(root.Video.Registry);
            Assert.Same(root.VisionCatalog.Catalog, image.Catalog); Assert.Same(image.Catalog, video.Catalog);
            File.WriteAllText(Path.Combine(directory, "catalog.json"), "{}"); Assert.Same(image.Catalog, root.VisionCatalog.Catalog);
            files.Definition["model_id"] = "nano-banana-2"; files.Save(); Assert.Null(files.Compile(reserved.ToArray()).Catalog);
            } finally { root.DisposeCreatedSubsystems(); }
        }

        [Theory]
        [InlineData("nano-banana-2")] [InlineData("nano-banana-pro")]
        public void Recognized_legacy_aliases_still_resolve_before_media_validation(string alias)
        {
            using var files = new CatalogFiles();
            var handler = new VisionHandler(new ArtifactStore(Path.Combine(files.Root, "artifacts")), new InMemoryGenerationSecretStore(), new PromptEnhancer(), new ViewportHandler());
            var source = handler.BuildImageGenerationWorkItem(JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(new JsonObject { ["model"] = alias, ["prompt"] = "test" }.ToJsonString())!);
            Assert.False(source.Success); Assert.Contains("input_image_path", Assert.IsType<string>(source.Failure!.Data));
        }

        [Fact]
        public void Configured_legacy_generate_returns_handoff_before_required_fields()
        {
            using var files = new CatalogFiles(); var model = files.Compile().Catalog!.Definitions[0];
            var adapters = new FalAdapterRegistry();
            var registry = new DefaultImageProviderRegistry(new[] { new ConfiguredFalImageRegistration(model,
                new FalConfiguredExecutor(new FalApiClient(), () => throw new Exception("No secret reads")), adapters, new FalDeclarativePricing().ForImage(model, adapters)) });
            var handler = new VisionHandler(new ArtifactStore(System.IO.Path.Combine(files.Root, "artifacts")), new InMemoryGenerationSecretStore(), new PromptEnhancer(), new ViewportHandler(), registry);
            var result = handler.BuildImageGenerationWorkItem(JsonSerializer.Deserialize<Dictionary<string, JsonElement>>("{\"model\":\"synthetic/image\"}")!);
            Assert.False(result.Success);
            Assert.Equal("image_job_required", Assert.IsType<Dictionary<string, object?>>(result.Failure!.Data)["code"]);
        }

        [Fact]
        public void Configured_parser_preserves_raw_options_and_common_fields()
        {
            using var files = new CatalogFiles(); var catalog = files.Compile().Catalog!;
            var result = FalConfiguredRequestParser.Parse(JsonNode.Parse("{\"model\":\"synthetic/image\",\"prompt\":\"test\",\"seed\":9007199254740991,\"options\":{\"strength\":0.7}}")!.AsObject(), catalog, "image");
            Assert.True(result.Success, string.Join("; ", System.Linq.Enumerable.Select(result.Errors, e => e.Field + ": " + e.Message)));
            Assert.Equal(.7m, result.Request!.EffectiveOptions["strength"]!.GetValue<decimal>());
            Assert.Equal(9007199254740991L, result.Input!.RequestFields["seed"]!.GetValue<long>());
            Assert.False(result.Input.RequestFields.ContainsKey("resolution"));
            Assert.Equal("small", result.Request.EffectiveRequestFields["resolution"]!.GetValue<string>());
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public void Unresolved_image_model_fails_before_prompt_and_media_validation(bool jobs)
        {
            var handler = new VisionHandler(new ArtifactStore(System.IO.Path.Combine(System.IO.Path.GetTempPath(), Guid.NewGuid().ToString())),
                new InMemoryGenerationSecretStore(), new PromptEnhancer(), new ViewportHandler());
            var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>("{\"model\":\"removed-model\",\"input_image_path\":\"missing.png\"}")!;
            var result = handler.BuildImageGenerationWorkItem(args, jobs ? VisionHandler.ImageGenerationWorkItemOptions.AsyncImageJob : VisionHandler.ImageGenerationWorkItemOptions.SyncGenerate);
            Assert.False(result.Success);
            var data = Assert.IsType<Dictionary<string, object?>>(result.Failure!.Data);
            Assert.Equal("model_unavailable", data["code"]);
        }
    }
}
