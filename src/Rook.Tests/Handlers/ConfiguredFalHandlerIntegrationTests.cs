using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Rook.Tests.Services.Vision.Fal;
using Xunit;

namespace Rook.Tests.Handlers
{
    public partial class ConfiguredFalHandlerTests
    {
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Discovery_estimate_confirmed_job_artifact_preserve_nondefault_controls(bool video)
        {
            using var run = new HandlerRun(video);
            var discovery = run.Read(new JsonObject { ["op"] = video ? "list_video_models" : "list_image_models" });
            Assert.True(discovery.Success);
            var model = Wire(discovery)["models"]!.AsArray().Single(m => m!["model_id"]!.GetValue<string>() == run.ModelId)!;
            Assert.Single(model["operations"]!.AsArray());
            var request = run.Request(); request["op"] = video ? "estimate_video_job" : "image_estimate";
            var estimated = run.Read(request); Assert.True(estimated.Success, JsonSerializer.Serialize(estimated.Data));
            var quote = Wire(estimated); Assert.StartsWith("fal1:", quote["quote_fingerprint"]!.GetValue<string>());
            Assert.Equal(0, run.Transport.Posts);
            request["op"] = video ? "submit_video_job" : "image_generate_start";
            request["quote_fingerprint"] = quote["quote_fingerprint"]!.DeepClone();
            request["max_estimated_cost_usd"] = quote["max_estimated_cost_usd"]!.DeepClone();
            var submitted = await run.Submit(request); Assert.True(submitted.Success, JsonSerializer.Serialize(submitted.Data));
            var jobId = Wire(submitted)["job_id"]!.GetValue<string>();
            await run.WaitComplete(jobId);
            var result = run.Read(new JsonObject { ["op"] = video ? VideoOpHandler.OpResult : "image_job_result", ["job_id"] = jobId });

            Assert.True(result.Success, JsonSerializer.Serialize(result.Data));
            Assert.NotNull(Wire(result)["result_artifact_id"]);
            Assert.Equal(1, run.Transport.Posts);
            if (video) Assert.Equal(6.5m, run.Transport.Payload!["duration"]!.GetValue<decimal>());
            else
            {
                Assert.Equal(.7m, run.Transport.Payload!["strength"]!.GetValue<decimal>());
                Assert.Equal(7.5m, run.Transport.Payload!["guidance"]!.GetValue<decimal>());
                Assert.Equal(9007199254740991L, run.Transport.Payload["seed"]!.GetValue<long>());
                Assert.False(run.Transport.Payload["audio"]!.GetValue<bool>());
            }
            var history = Wire(run.Read(new JsonObject { ["op"] = video ? VideoOpHandler.OpListJobs : "image_jobs" }));
            var row = history["jobs"]![0]!;
            var saved = row["configured_fal_execution"]!;
            Assert.NotNull(saved);
            Assert.Equal("0.00000001", saved["pricing"]!["rate_usd"]!.GetValue<string>());
            Assert.Equal(video ? 6.5m : 9007199254740991m, row["request_summary"]![video ? "duration_seconds" : "seed"]!.GetValue<decimal>());
            if (video)
            {
                Assert.NotNull(Wire(result)["configured_fal_execution"]);
                Assert.NotNull(Wire(run.Read(new JsonObject { ["op"] = VideoOpHandler.OpStatus, ["job_id"] = jobId }))["configured_fal_execution"]);
            }
            Assert.Equal(0, run.Resources.ActiveBundles);
        }

        [Theory]
        [InlineData(false, "confirmed_cancelled")] [InlineData(true, "confirmed_cancelled")]
        [InlineData(false, "already_completed")] [InlineData(true, "already_completed")]
        [InlineData(false, "cancellation_requested")] [InlineData(true, "cancellation_requested")]
        [InlineData(false, "failed")] [InlineData(true, "failed")]
        public async Task Cancel_projects_remote_evidence_on_success_and_error(bool video, string outcome)
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(video, recoverWithoutRegistration: true);
            run.Transport.CancelDisposition = outcome; run.Seed(run.AcceptedSnapshot());
            var vision = new VisionHandler(run.Store, new InMemoryGenerationSecretStore(), new PromptEnhancer(), new ViewportHandler());
            var image = video ? null : new ImageJobOpHandler(run.Image!, vision, new VideoPreparationResources());
            var videos = video ? new VideoOpHandler(run.Video!, new DefaultVideoProviderRegistry(Array.Empty<IVideoProviderRegistration>()), new VideoCostEstimator()) : null;
            var body = new JsonObject { ["op"] = video ? VideoOpHandler.OpCancel : "image_job_cancel", ["job_id"] = run.Id.ToString("D") }.ToJsonString();
            var response = video ? await videos!.DispatchAsync(body) : await image!.DispatchAsync(body);
            Assert.Equal(outcome == "confirmed_cancelled", response.Success);
            var evidence = Wire(response)["cancellation"]!; Assert.NotNull(evidence);
            Assert.True(evidence["local_stopped"]!.GetValue<bool>());
            Assert.Equal(outcome, evidence["remote_disposition"]!.GetValue<string>());
            Assert.Equal(outcome == "confirmed_cancelled", evidence["remote_cancellation_confirmed"]!.GetValue<bool>());
            var historyBody = new JsonObject { ["op"] = video ? VideoOpHandler.OpListJobs : "image_jobs" }.ToJsonString();
            var history = Wire(video ? videos!.DispatchOffUi(historyBody) : image!.DispatchOffUi(historyBody));
            Assert.Equal(outcome, history["jobs"]![0]!["configured_fal_execution"]!["cancellation"]!["remote_disposition"]!.GetValue<string>());
            if (video)
            {
                foreach (var op in new[] { VideoOpHandler.OpStatus, VideoOpHandler.OpResult })
                {
                    var read = Wire(videos!.DispatchOffUi(new JsonObject { ["op"] = op, ["job_id"] = run.Id.ToString("D") }.ToJsonString()));
                    Assert.Equal(outcome, read["configured_fal_execution"]!["cancellation"]!["remote_disposition"]!.GetValue<string>());
                }
            }
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Unconfirmed_and_stale_submits_fail_before_provider_dispatch(bool video)
        {
            using var run = new HandlerRun(video);
            var request = run.Request(); request["op"] = video ? VideoOpHandler.OpSubmit : "image_generate_start";
            var response = await run.Submit(request); Assert.False(response.Success);
            Assert.Equal("quote_confirmation_required", Wire(response)["detail_code"]!.GetValue<string>());
            request["quote_fingerprint"] = "fal1:" + new string('0', 64); request["max_estimated_cost_usd"] = "1";
            response = await run.Submit(request); Assert.False(response.Success);
            Assert.Equal("quote_confirmation_required", Wire(response)["detail_code"]!.GetValue<string>());
            request["max_estimated_cost_usd"] = 1;
            response = await run.Submit(request); Assert.False(response.Success);
            Assert.Equal("quote_stale", Wire(response)["detail_code"]!.GetValue<string>());
            Assert.Equal(0, run.Transport.Posts); Assert.Equal(0, run.Resources.ActiveBundles);
            Assert.Empty(run.Store.List());
        }

        [Fact]
        public void Configured_omissions_use_only_declared_defaults_and_legacy_requirements_remain_managed()
        {
            using var run = new HandlerRun(true);
            var request = new JsonObject { ["op"] = VideoOpHandler.OpEstimate, ["model"] = run.ModelId };
            var estimate = run.Read(request); Assert.True(estimate.Success, JsonSerializer.Serialize(estimate.Data));
            var effective = Wire(estimate)["candidates"]![0]!["effective_request"]!.AsObject();
            Assert.Single(effective); Assert.Equal(5, effective["duration_seconds"]!.GetValue<int>());
            request["duration_seconds"] = null; Assert.False(run.Read(request).Success);
            request.Remove("duration_seconds"); request["model"] = "veo-3.1-fast-generate-preview";
            var legacy = run.Read(request); Assert.False(legacy.Success); Assert.Equal("mode", Wire(legacy)["field"]!.GetValue<string>());
        }

        [Fact]
        public void Corrupt_configured_video_reads_only_expose_safe_diagnostics()
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(true, recoverWithoutRegistration: true);
            run.Seed(run.AcceptedSnapshot(), unsupported: true);
            var handler = new VideoOpHandler(run.Video!, new DefaultVideoProviderRegistry(Array.Empty<IVideoProviderRegistration>()), new VideoCostEstimator());
            foreach (var op in new[] { VideoOpHandler.OpStatus, VideoOpHandler.OpResult, VideoOpHandler.OpListJobs })
            {
                var wire = Wire(handler.DispatchOffUi(new JsonObject { ["op"] = op, ["job_id"] = run.Id.ToString("D") }.ToJsonString()));
                var row = op == VideoOpHandler.OpListJobs ? wire["jobs"]![0]! : wire;
                Assert.Null(row["request_summary"]);
                var snapshot = row["configured_fal_execution"]!.AsObject();
                Assert.False(snapshot.ContainsKey("effective_request")); Assert.False(snapshot.ContainsKey("pricing")); Assert.NotEmpty(snapshot);
            }
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Artifact_roles_and_fresh_bytes_bind_quotes_without_retaining_media_owners(bool video)
        {
            using var run = new HandlerRun(video, files =>
            {
                files.Operation["operation_id"] = video ? "image_to_video" : "image_to_image";
                files.Operation["media"] = JsonNode.Parse("[{\"role\":\"primary_image\",\"min_count\":1,\"max_count\":1,\"ordered\":false,\"preparation\":\"validated_original\",\"transport\":\"" + (video ? "fal_upload" : "data_uri") + "\",\"payload\":{\"pointer\":\"/image_url\",\"conversion\":\"identity\"}}]");
                if (!video) files.Operation["fields"]![0]!["required"] = false;
            });
            var artifactRole = video ? "start_frame" : "input_image";
            var original = new byte[] { 137, 80, 78, 71, 13, 10, 26, 10, 42 };
            var artifact = run.Store.Create("captured_viewport", new[] { new BlobInput(artifactRole, original, "png"), new BlobInput("image", new byte[] { 1 }, "png") });
            var request = run.Request(); request.Remove("prompt"); request["op"] = video ? VideoOpHandler.OpEstimate : "image_estimate";
            request["media"] = new JsonArray(new JsonObject { ["semantic_role"] = "primary_image", ["artifact_id"] = artifact.Id.ToString("D"), ["artifact_role"] = artifactRole });
            var estimate = run.Read(request); Assert.True(estimate.Success, JsonSerializer.Serialize(estimate.Data));
            var quote = Wire(estimate); var source = quote["candidates"]![0]!["media"]![0]!;
            Assert.Equal(artifactRole, source["source_role"]!.GetValue<string>());
            using (var sha = System.Security.Cryptography.SHA256.Create())
                Assert.Equal(BitConverter.ToString(sha.ComputeHash(original)).Replace("-", "").ToLowerInvariant(), source["sha256"]!.GetValue<string>());
            Assert.Equal(0, run.Resources.ActiveBundles);
            request["op"] = video ? VideoOpHandler.OpSubmit : "image_generate_start";
            request["quote_fingerprint"] = quote["quote_fingerprint"]!.DeepClone(); request["max_estimated_cost_usd"] = quote["max_estimated_cost_usd"]!.DeepClone();
            var changed = (byte[])original.Clone(); changed[8] = 43; File.WriteAllBytes(run.Store.GetBlobAbsolutePath(artifact.Id, artifactRole), changed);
            var rejected = await run.Submit(request); Assert.False(rejected.Success);
            Assert.Equal("quote_stale", Wire(rejected)["detail_code"]!.GetValue<string>());
            Assert.Equal(0, run.Transport.Posts); Assert.Equal(0, run.Resources.ActiveBundles);
        }

        private static JsonObject Wire(ApiResponse response) => JsonSerializer.SerializeToNode(response.Data)!.AsObject();
        private sealed class HandlerRun : IDisposable
        {
            internal readonly CatalogFiles Files;
            internal readonly HttpTransport Transport = new();
            private readonly HttpClient _client;
            internal readonly VideoPreparationResources Resources = new();
            internal readonly ArtifactStore Store;
            internal readonly VisionHandler Vision;
            internal readonly ImageJobOpHandler? ImageHandler;
            internal readonly VideoOpHandler? VideoHandler;
            internal readonly ImageJobManager? Image;
            internal readonly VideoJobManager? Video;
            internal readonly string ModelId;
            private readonly bool _video;
            internal HandlerRun(bool video, Action<CatalogFiles>? configure = null)
            {
                _video = video; Transport.Video = video;
                Files = new CatalogFiles(video ? CatalogFiles.VideoJson : CatalogFiles.ImageJson);
                if (video)
                {
                    Files.Operation["operation_id"] = "text_to_video"; Files.Operation["media"] = new JsonArray();
                    Files.Operation["fields"]![0]!["type"] = "number";
                    Files.Operation["fields"]![0]!["payload"]!["conversion"] = "identity";
                }
                if (!video) Files.Operation["fields"]!.AsArray().Add(JsonNode.Parse("{\"key\":\"guidance\",\"scope\":\"options\",\"type\":\"number\",\"min\":0,\"max\":10,\"step\":0.5,\"default\":2,\"label\":\"Guidance\",\"payload\":{\"pointer\":\"/guidance\",\"conversion\":\"identity\"}}"));
                Files.Operation["pricing"]!["rates"]![0]!["rate_usd"] = .00000001m;
                configure?.Invoke(Files);
                Files.Save(); var catalog = Files.Compile().Catalog!; ModelId = catalog.Definitions[0].ModelId;
                _client = new HttpClient(Transport); var executor = new FalConfiguredExecutor(new FalApiClient(_client), () => "test-key");
                Store = new ArtifactStore(Path.Combine(Files.Root, "artifacts"));
                var imageRegistry = new DefaultImageProviderRegistry(VisionProviderRegistrations.CreateImageRegistrations(() => null, () => null, () => null,
                    catalog: catalog, configuredExecutor: executor), catalog);
                Vision = new VisionHandler(Store, new InMemoryGenerationSecretStore(), new PromptEnhancer(), new ViewportHandler(), imageRegistry);
                if (video)
                {
                    var registry = new DefaultVideoProviderRegistry(VisionProviderRegistrations.CreateVideoRegistrations(() => null, () => null,
                        catalog: catalog, configuredExecutor: executor), catalog);
                    var media = new ArtifactOnlyVideoMediaResolver(Store, Resources);
                    Video = new VideoJobManager(registry, media, new JsonlVideoJobLedger(Path.Combine(Files.Root, "video.jsonl")), new VideoCostEstimator(), Store,
                        null, null, TimeSpan.FromMilliseconds(1), 2, new VideoArtifactMaterializer(Transport),
                        new Rook.Tests.Services.Vision.Video.FakePosterProducer(Store), new Rook.Tests.Services.Vision.Video.FakeFrameProducer(Store));
                    VideoHandler = new VideoOpHandler(Video, registry, new VideoCostEstimator(), null, media, Resources);
                }
                else
                {
                    Image = new ImageJobManager(imageRegistry, Store, null, null, TimeSpan.FromMilliseconds(1), 2, new ImageArtifactMaterializer(Transport), null,
                        new JsonlImageJobLedger(Path.Combine(Files.Root, "image.jsonl")));
                    ImageHandler = new ImageJobOpHandler(Image, Vision, Resources);
                }
            }
            internal JsonObject Request() => _video ? new JsonObject { ["model"] = ModelId, ["duration_seconds"] = 6.5m }
                : new JsonObject { ["model"] = ModelId, ["prompt"] = "a rook", ["seed"] = 9007199254740991L, ["resolution"] = "large",
                    ["options"] = new JsonObject { ["strength"] = .7m, ["audio"] = false, ["guidance"] = 7.5m } };
            internal ApiResponse Read(JsonObject request) => _video ? VideoHandler!.DispatchOffUi(request.ToJsonString())
                : request["op"]!.GetValue<string>() == "list_image_models" ? Vision.DispatchOffUi(request.ToJsonString()) : ImageHandler!.DispatchOffUi(request.ToJsonString());
            internal Task<ApiResponse> Submit(JsonObject request) => _video ? VideoHandler!.DispatchAsync(request.ToJsonString()) : ImageHandler!.DispatchAsync(request.ToJsonString());
            internal async Task WaitComplete(string id)
            {
                for (var i = 0; i < 250; i++)
                {
                    var result = Read(new JsonObject { ["op"] = _video ? VideoOpHandler.OpStatus : "image_job_status", ["job_id"] = id });
                    var state = Wire(result)["state"]?.GetValue<string>();
                    if (state is "complete" or "error" or "interrupted") { Assert.Equal("complete", state); return; }
                    await Task.Delay(20);
                }
                Assert.Fail("Job did not settle within five seconds.");
            }
            public void Dispose() { Image?.Dispose(); Video?.Dispose(); _client.Dispose(); Files.Dispose(); }
        }
        private sealed class HttpTransport : HttpMessageHandler
        {
            internal bool Video; internal int Posts; internal JsonObject? Payload;
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                if (request.Method == HttpMethod.Post)
                {
                    Posts++; Payload = JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
                    return Json(Video ? "{\"request_id\":\"id\",\"status_url\":\"https://queue.fal.run/fal-ai/synthetic/requests/id/status\",\"response_url\":\"https://queue.fal.run/fal-ai/synthetic/requests/id\",\"cancel_url\":\"https://queue.fal.run/fal-ai/synthetic/requests/id/cancel\"}" : "{\"images\":[{\"url\":\"https://fal.media/image.png\",\"content_type\":\"image/png\"}]}");
                }
                if (request.RequestUri!.Host == "fal.media") return new(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[] { 1, 2, 3, 4 }) { Headers = { ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(Video ? "video/mp4" : "image/png") } } };
                return Json(request.RequestUri.AbsolutePath.EndsWith("/status") ? "{\"status\":\"COMPLETED\"}" : "{\"video\":{\"url\":\"https://fal.media/video.mp4\"}}");
            }
            private static HttpResponseMessage Json(string text) => new(HttpStatusCode.OK) { Content = new StringContent(text) };
        }
    }
}
