using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class ConfiguredFalRegistrationTests
    {
        [Fact]
        public void Two_fal_registrations_keep_distinct_codecs_and_bindings()
        {
            using var run = new ConfiguredRun();
            var a = ImageModel(); var b = ImageModel("synthetic/other", "fal-ai/other/render");
            var pricingA = new UnavailablePricing<ImageGenerationRequest, ImageCapability>();
            var pricingB = new UnavailablePricing<ImageGenerationRequest, ImageCapability>();
            var ra = new ConfiguredFalImageRegistration(a, run.Executor, new FalAdapterRegistry(), pricingA);
            var rb = new ConfiguredFalImageRegistration(b, run.Executor, new FalAdapterRegistry(), pricingB);
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[] { ra, rb });
            Assert.True(registry.TryResolve(a.ModelId, out var ma)); Assert.True(registry.TryResolve(b.ModelId, out var mb));
            Assert.NotSame(ma.OptionsCodec, mb.OptionsCodec); Assert.Same(pricingA, ma.PricingModel); Assert.Same(pricingB, mb.PricingModel);
            Assert.NotEqual(((IConfiguredGenerationBinding)ma.Provider).GetBinding("text_to_image").EndpointId,
                ((IConfiguredGenerationBinding)mb.Provider).GetBinding("text_to_image").EndpointId);
            Assert.Equal("fal", ma.ProviderName); Assert.Equal("fal", mb.ProviderName);
        }

        [Fact]
        public void Configured_sync_image_runs_as_a_rook_job()
        {
            using var run = new ConfiguredRun(); var model = ImageModel();
            var reg = ImageRegistration(model, run.Executor);
            Assert.Equal(ImageSubmissionMode.AsyncImageJob, reg.SubmissionMode);
            Assert.Equal("image_job", new FalDescriptorProjector().Describe(model.Operations[0], null).ToJson()["submission_contract"]!.GetValue<string>());
        }

        [Fact]
        public void Operation_resolution_is_explicit_or_unambiguous()
        {
            var model = ImageModel(withEdit: true); var codec = new ConfiguredFalImageOptionsCodec(model, new FalAdapterRegistry());
            var primary = new FalMediaInput("primary_image", 0, MediaRef.ForArtifact(Guid.NewGuid(), "image"));
            Assert.Equal("image_to_image", codec.Normalize(new FalModelInput(new JsonObject { ["prompt"] = "edit" }, media: new[] { primary })).Request!.Binding.OperationId);
            Assert.Equal("text_to_image", codec.Normalize(FalModelNormalizerTests.Prompt()).Request!.Binding.OperationId);
            var ambiguous = AmbiguousOperationFixtureBypassingCatalog();
            Assert.False(new ConfiguredFalImageOptionsCodec(ambiguous, new FalAdapterRegistry()).Normalize(FalModelNormalizerTests.Prompt()).Success);
            Assert.True(new ConfiguredFalImageOptionsCodec(ambiguous, new FalAdapterRegistry()).Normalize(new FalModelInput(new JsonObject { ["prompt"] = "draw" }, operationId: "text_to_image")).Success);
            Assert.False(codec.Normalize(new FalModelInput(new JsonObject { ["prompt"] = "draw" }, operationId: "unknown")).Success);
            Assert.False(codec.Normalize(new FalModelInput(new JsonObject { ["prompt"] = "draw" }, operationId: "text_to_image", media: new[] { primary })).Success);
        }

        [Fact]
        public void Single_operation_reports_precise_missing_media_field()
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            var model = Compile(files); var codec = new ConfiguredFalVideoOptionsCodec(model, new FalAdapterRegistry());
            var failure = codec.Normalize(new FalModelInput());
            Assert.False(failure.Success); Assert.Contains(failure.Errors, e => e.Field == "media.start_frame");
            Assert.DoesNotContain(failure.Errors, e => e.Field == "operation");
        }

        [Fact]
        public void Codecs_preserve_raw_supplied_fields_and_descriptor_defaults()
        {
            using var run = new ConfiguredRun();
            var model = ImageModel(); var codec = new ConfiguredFalImageOptionsCodec(model, new FalAdapterRegistry());
            var raw = new JsonObject { ["count"] = 2 }; var decoded = codec.Deserialize(raw); raw["count"] = 3;
            var options = Assert.IsType<FalModelOptions>(decoded.Options);
            Assert.Empty(options.Input.RequestFields); Assert.Equal(2, codec.Serialize(options)["count"]!.GetValue<int>());
            var canonical = new FalModelOptions(new FalModelInput(new JsonObject { ["prompt"] = "draw", ["seed"] = 9007199254740991L }));
            var shell = ImageShell(model.ModelId, canonical);
            var capability = ImageRegistration(model, run.Executor).Models[model.ModelId].Capability;
            Assert.True(codec.Validate(shell, canonical, capability).Success);
            Assert.False(codec.Validate(shell, options, capability).Success); // Shell prompt cannot fill absent canonical input.
            Assert.False(codec.Normalize(new FalModelInput(new JsonObject { ["prompt"] = "draw" }, new JsonObject { ["unknown"] = true })).Success);
            Assert.Equal("small", codec.Normalize(canonical.Input).Request!.EffectiveRequestFields["resolution"]!.GetValue<string>());
        }

        [Fact]
        public void Canonical_video_controls_are_not_narrowed_to_legacy_Int32_fields_or_projection()
        {
            using var run = new ConfiguredRun();
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            files.Operation["operation_id"] = "text_to_video"; files.Operation["media"] = new JsonArray();
            var duration = files.Operation["fields"]![0]!; duration["type"] = "number"; duration["min"] = .5m; duration["max"] = 1000000000; duration["default"] = 5.5m; duration["payload"]!["conversion"] = "identity";
            files.Operation["fields"]!.AsArray().Add(new JsonObject { ["key"] = "seed", ["scope"] = "request", ["type"] = "integer", ["label"] = "Seed", ["min"] = -9007199254740991L, ["max"] = 9007199254740991L, ["payload"] = new JsonObject { ["pointer"] = "/seed", ["conversion"] = "identity" } });
            files.Save(); var model = Compile(files); var reg = VideoRegistration(model, run.Executor);
            var codec = Assert.IsType<ConfiguredFalVideoOptionsCodec>(reg.OptionsCodec);
            var options = new FalModelOptions(new FalModelInput(new JsonObject { ["duration_seconds"] = 5.5m, ["seed"] = 9007199254740991L }));
            var shell = new VideoGenerationRequest(model.ModelId, VideoMode.T2V, 0, "legacy", "legacy", null, null, null, null, null, options, 1);
            Assert.Empty(reg.Models[model.ModelId].Capability.Durations);
            Assert.True(codec.Validate(shell, options, reg.Models[model.ModelId].Capability).Success);
            Assert.Equal(5.5m, codec.Normalize(options.Input).Request!.EffectiveRequestFields["duration_seconds"]!.GetValue<decimal>());
            Assert.False(codec.Normalize(new FalModelInput(new JsonObject { ["duration_seconds"] = "5.5" })).Success);
        }

        [Theory]
        [InlineData("sync", false)]
        [InlineData("queue", false)]
        [InlineData("queue", true)]
        public async Task Synthetic_models_use_one_executor_through_provider_capability(string invocation, bool video)
        {
            using var run = new ConfiguredRun(invocation, video);
            IGenerationProvider ordinary = video ? VideoRegistration(Compile(run.Files), run.Executor).Provider : ImageRegistration(Compile(run.Files), run.Executor).Provider;
            var provider = Assert.IsAssignableFrom<IConfiguredGenerationProvider>(ordinary);
            Assert.True(provider.RequiresConfirmedSubmission);
            using var media = FalMediaSnapshot.Capture(run.Request, new Dictionary<MediaRef, ResolvedMedia>(), run.Resources);
            var outcome = await provider.SubmitConfiguredAsync(run.Request, media, run.Observer, CancellationToken.None);
            if (invocation == "sync") Assert.IsType<SuccessResultOutcome>(Assert.IsType<SyncSubmitOutcome>(outcome).Result);
            else Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Single(run.Events, e => e == "submit");
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Ordinary_submit_and_lifecycle_fail_closed_before_transport(bool video)
        {
            using var run = new ConfiguredRun(video: video); var model = Compile(run.Files);
            IGenerationProvider provider = video ? VideoRegistration(model, run.Executor).Provider : ImageRegistration(model, run.Executor).Provider;
            ProviderSubmitOutcome submit;
            ProviderStatusOutcome status; ProviderCancelOutcome cancel; ProviderResultOutcome result;
            if (provider is IImageProvider image)
            {
                submit = await image.SubmitAsync(ImageShell(model.ModelId, new FalModelOptions(FalModelNormalizerTests.Prompt())), new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);
                status = await image.GetStatusAsync(ConfiguredRun.Handle(), CancellationToken.None); cancel = await image.CancelAsync(ConfiguredRun.Handle(), CancellationToken.None); result = await image.FetchResultAsync(ConfiguredRun.Handle(), CancellationToken.None);
            }
            else
            {
                var v = (IVideoProvider)provider;
                submit = await v.SubmitAsync(null!, new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);
                status = await v.GetStatusAsync(ConfiguredRun.Handle(), CancellationToken.None); cancel = await v.CancelAsync(ConfiguredRun.Handle(), CancellationToken.None); result = await v.FetchResultAsync(ConfiguredRun.Handle(), CancellationToken.None);
            }
            Assert.Equal("confirmation_required", Assert.IsType<FailedSubmitOutcome>(submit).Error.ProviderErrorCode);
            Assert.Equal("configured_binding_required", Assert.IsType<FailedStatusOutcome>(status).Error.ProviderErrorCode);
            Assert.Equal("configured_binding_required", Assert.IsType<FailedCancelOutcome>(cancel).Error.ProviderErrorCode);
            Assert.Equal("configured_binding_required", Assert.IsType<FailedResultOutcome>(result).Error.ProviderErrorCode);
            Assert.Null(run.LastUrl);
        }

        [Fact]
        public async Task Explicit_lifecycle_binding_disambiguates_shared_root_result_mappings()
        {
            using var run = new ConfiguredRun(); var model = ImageModel(withEdit: true, queue: true);
            var provider = (IConfiguredGenerationProvider)ImageRegistration(model, run.Executor).Provider;
            run.Body = "{\"images\":[{\"url\":\"https://fal.media/first.png\"}],\"edited\":[{\"url\":\"https://fal.media/second.png\"}]}";
            foreach (var operation in new[] { "text_to_image", "image_to_image" })
            {
                var result = Assert.IsType<SuccessResultOutcome>(await provider.FetchResultConfiguredAsync(provider.GetBinding(operation), ConfiguredRun.Handle(), CancellationToken.None));
                Assert.Contains(operation == "text_to_image" ? "first.png" : "second.png", Assert.IsType<RemoteArtifactBody>(Assert.Single(result.Envelope.Artifacts).Body).Url.AbsoluteUri);
            }
            run.Body = "{\"status\":\"IN_PROGRESS\"}";
            Assert.IsType<InFlightStatusOutcome>(await provider.GetStatusConfiguredAsync(model.Operations[0], ConfiguredRun.Handle(), CancellationToken.None));
            run.Body = "{\"status\":\"OK\"}";
            Assert.IsType<CanceledOutcome>(await provider.CancelConfiguredAsync(model.Operations[1], ConfiguredRun.Handle(), CancellationToken.None));
        }

        [Fact]
        public async Task Configured_video_lifecycle_uses_explicit_binding_and_rejects_foreign_revision()
        {
            using var run = new ConfiguredRun(video: true); var model = Compile(run.Files);
            var provider = (IConfiguredGenerationProvider)VideoRegistration(model, run.Executor).Provider;
            var binding = provider.GetBinding("text_to_video");
            run.Body = "{\"status\":\"IN_PROGRESS\"}";
            Assert.IsType<InFlightStatusOutcome>(await provider.GetStatusConfiguredAsync(binding, ConfiguredRun.Handle(), CancellationToken.None));
            run.Body = "{\"video\":{\"url\":\"https://fal.media/result.mp4\"}}";
            Assert.IsType<SuccessResultOutcome>(await provider.FetchResultConfiguredAsync(binding, ConfiguredRun.Handle(), CancellationToken.None));
            run.Body = "{\"status\":\"OK\"}";
            Assert.IsType<CanceledOutcome>(await provider.CancelConfiguredAsync(binding, ConfiguredRun.Handle(), CancellationToken.None));
            run.Files.Definition["revision"] = "revision-2"; run.Files.Save(); var foreign = Compile(run.Files).Operations[0]; run.LastUrl = null;
            Assert.IsType<FailedStatusOutcome>(await provider.GetStatusConfiguredAsync(foreign, ConfiguredRun.Handle(), CancellationToken.None));
            Assert.IsType<FailedResultOutcome>(await provider.FetchResultConfiguredAsync(foreign, ConfiguredRun.Handle(), CancellationToken.None));
            Assert.IsType<FailedCancelOutcome>(await provider.CancelConfiguredAsync(foreign, ConfiguredRun.Handle(), CancellationToken.None));
            Assert.Null(run.LastUrl);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Wrappers_leave_media_owned_until_awaited_submission_settles(bool video)
        {
            using var run = new ConfiguredRun(video: video); var model = Compile(run.Files);
            IConfiguredGenerationProvider provider = video ? (IConfiguredGenerationProvider)VideoRegistration(model, run.Executor).Provider : (IConfiguredGenerationProvider)ImageRegistration(model, run.Executor).Provider;
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            run.OnHttp = async (_, _) => { entered.TrySetResult(true); await release.Task; return new System.Net.Http.HttpResponseMessage(System.Net.HttpStatusCode.OK) { Content = new System.Net.Http.StringContent(ConfiguredRun.QueueBody()) }; };
            using var media = FalMediaSnapshot.Capture(run.Request, new Dictionary<MediaRef, ResolvedMedia>(), run.Resources);
            var submit = provider.SubmitConfiguredAsync(run.Request, media, run.Observer, CancellationToken.None);
            try
            {
                Assert.Same(entered.Task, await Task.WhenAny(entered.Task, Task.Delay(5000)));
                Assert.False(submit.IsCompleted); Assert.Equal(1, run.Resources.ActiveBundles);
            }
            finally { release.TrySetResult(true); await submit; }
            Assert.Equal(1, run.Resources.ActiveBundles); media.Dispose(); Assert.Equal(0, run.Resources.ActiveBundles);
        }

        [Theory]
        [InlineData("model")]
        [InlineData("revision")]
        [InlineData("hash")]
        public async Task Foreign_model_revision_or_definition_hash_is_rejected_before_submit_and_lifecycle_HTTP(string difference)
        {
            using var run = new ConfiguredRun(); var model = ImageModel(queue: true);
            using var files = new CatalogFiles();
            if (difference == "hash") files.Operation["fields"]![2]!["default"] = 2;
            else files.Definition[difference == "revision" ? "revision" : "model_id"] = difference == "revision" ? "revision-2" : "synthetic/other";
            files.Operation["invocation"] = "queue"; files.Operation["lifecycle_root"] = "fal-ai/synthetic"; files.Save(); var foreign = Compile(files).Operations[0];
            var provider = (IConfiguredGenerationProvider)ImageRegistration(model, run.Executor).Provider;
            Assert.Equal("configured_binding_mismatch", Assert.IsType<FailedStatusOutcome>(await provider.GetStatusConfiguredAsync(foreign, ConfiguredRun.Handle(), CancellationToken.None)).Error.ProviderErrorCode);
            Assert.IsType<FailedCancelOutcome>(await provider.CancelConfiguredAsync(foreign, ConfiguredRun.Handle(), CancellationToken.None));
            Assert.IsType<FailedResultOutcome>(await provider.FetchResultConfiguredAsync(foreign, ConfiguredRun.Handle(), CancellationToken.None));
            var request = new FalModelNormalizer().Normalize(foreign, FalModelNormalizerTests.Prompt()).Request!;
            using var media = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>(), run.Resources);
            Assert.IsType<FailedSubmitOutcome>(await provider.SubmitConfiguredAsync(request, media, run.Observer, CancellationToken.None));
            Assert.Null(run.LastUrl); Assert.Empty(run.Events);
        }

        [Fact]
        public void Legacy_models_keep_their_provider_and_policy()
        {
            using var run = new ConfiguredRun();
            var legacy = new FalImageProviderRegistration(new FalImageProvider(() => null));
            var before = new DefaultImageProviderRegistry(new[] { legacy });
            var after = new DefaultImageProviderRegistry(new IImageProviderRegistration[] { legacy, ImageRegistration(ImageModel(), run.Executor) });
            foreach (var pair in legacy.Models)
            {
                Assert.True(before.TryResolve(pair.Key, out var a)); Assert.True(after.TryResolve(pair.Key, out var b));
                Assert.Same(a.Provider, b.Provider); Assert.Same(a.OptionsCodec, b.OptionsCodec); Assert.Same(a.PricingModel, b.PricingModel); Assert.Equal(a.SubmissionMode, b.SubmissionMode);
                Assert.Equal(ImageSubmissionExecutor.UsesExecutionDeadline(a), ImageSubmissionExecutor.UsesExecutionDeadline(b));
            }
            var video = new FalVideoProviderRegistration(new FalVideoProvider(() => null));
            var baseline = new DefaultVideoProviderRegistry(new[] { video });
            using var videoRun = new ConfiguredRun(video: true);
            var current = new DefaultVideoProviderRegistry(new IVideoProviderRegistration[] { video, VideoRegistration(Compile(videoRun.Files), run.Executor) });
            foreach (var id in video.Models.Keys) { Assert.True(baseline.TryResolve(id, out var a)); Assert.True(current.TryResolve(id, out var b)); Assert.Same(a.Provider, b.Provider); Assert.Same(a.OptionsCodec, b.OptionsCodec); Assert.Same(a.PricingModel, b.PricingModel); }
        }

        internal static FalModelDefinition ImageModel(string id = "synthetic/image", string endpoint = "fal-ai/synthetic/render", bool withEdit = false, bool queue = false)
        {
            using var files = new CatalogFiles(); files.Definition["model_id"] = id; files.Operation["endpoint_id"] = endpoint;
            if (queue) { files.Operation["invocation"] = "queue"; files.Operation["lifecycle_root"] = "fal-ai/synthetic"; }
            if (withEdit)
            {
                var edit = files.Operation.DeepClone().AsObject(); edit["operation_id"] = "image_to_image"; edit["endpoint_id"] = "fal-ai/synthetic/edit";
                edit["media"] = JsonNode.Parse("""[{"role":"primary_image","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"data_uri","payload":{"pointer":"/source","conversion":"identity"}}]""");
                edit["result"]!["collection_pointer"] = "/edited"; edit["result"]!["url_pointer"] = "/edited/0/url"; edit["result"]!["mime_pointer"] = "/edited/0/content_type";
                files.Definition["operations"]!.AsArray().Add(edit);
            }
            files.Save(); return Compile(files);
        }
        private static FalModelDefinition AmbiguousOperationFixtureBypassingCatalog()
        {
            // Compiled v1 operations are media-disjoint. This deliberately invalid programmatic
            // fixture exercises the defensive guard only; it is not an onboarding acceptance fixture.
            var json = ImageModel(withEdit: true).ToJson(); json["operations"]![1]!["media"]![0]!["min_count"] = 0;
            return new FalModelDefinition(json, "synthetic-ambiguity-test.json");
        }
        internal static FalModelDefinition Compile(CatalogFiles files) { var result = files.Compile(); Assert.Empty(result.Diagnostics); return Assert.Single(result.Catalog!.Definitions); }
        internal static ConfiguredFalImageRegistration ImageRegistration(FalModelDefinition model, FalConfiguredExecutor executor) => new(model, executor, new FalAdapterRegistry(), new UnavailablePricing<ImageGenerationRequest, ImageCapability>());
        private static ConfiguredFalVideoRegistration VideoRegistration(FalModelDefinition model, FalConfiguredExecutor executor) => new(model, executor, new FalAdapterRegistry(), new UnavailablePricing<VideoGenerationRequest, VideoCapability>());
        private static ImageGenerationRequest ImageShell(string model, ProviderOptions options) => new(model, "legacy placeholder", "legacy", "legacy", 1, null, options);
        private sealed class UnavailablePricing<TRequest, TCapability> : IPricingModel<TRequest, TCapability> where TRequest : GenerationRequest where TCapability : IModelCapability
        {
            public string PricingSource => "injected-test-unavailable";
            public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;
            public PricingResult Estimate(TRequest request, TCapability capability) => PricingResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest, "Pricing unavailable in Task 4.", false));
            public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(IReadOnlyDictionary<string, IReadOnlyList<string>> headers, JsonNode? body) => null;
        }
    }
}
