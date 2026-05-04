using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Replicate;
using Rook.Tests.Services.Vision.Image.Jobs;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Services.Vision.Image.Replicate
{
    public class ReplicateImageJobManagerTests : IDisposable
    {
        private const string ProviderApiToken = "r8-provider-token";
        private const string SelectorApiToken = "r8-selector-token";

        private readonly string _root;
        private readonly ArtifactStore _artifactStore;
        private readonly FakeImageJobClock _clock = new();
        private readonly FakeImageJobIdGenerator _idGenerator = new();
        private readonly FakeImageJobLedger _ledger = new();

        public ReplicateImageJobManagerTests()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                $"rook-replicate-image-job-manager-{Guid.NewGuid():N}");
            _artifactStore = new ArtifactStore(Path.Combine(_root, "artifacts"));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public void Selector_returns_null_for_null_or_non_replicate_model()
        {
            var selector = new ReplicateImageArtifactRequestFactorySelector(
                () => SelectorApiToken);
            var artifact = RemoteArtifact("https://replicate.delivery/pbxt/out.png");

            Assert.Null(selector.Select(null!, artifact));
            Assert.Null(selector.Select(NonReplicateModel(), artifact));
        }

        [Fact]
        public void Selector_factory_fails_non_remote_replicate_artifact_without_fetch_request()
        {
            var selector = new ReplicateImageArtifactRequestFactorySelector(
                () => SelectorApiToken);
            var artifact = new ResultArtifact(
                ImageMediaRoles.Image,
                new InlineArtifactBody(new byte[] { 1, 2, 3 }),
                "image/png",
                new Dictionary<string, JsonNode>());

            var factory = selector.Select(ReplicateModel(), artifact);
            Assert.NotNull(factory);
            var request = factory(artifact);

            Assert.Null(request.Request);
            Assert.NotNull(request.Error);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, request.Error!.Code);
            Assert.False(request.Error.Retryable);
            AssertNoTokenLeak(request.Error);
        }

        [Fact]
        public async Task Injected_registry_materializes_replicate_output_with_bearer_token()
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = request =>
                    request.Method == HttpMethod.Post
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, Prediction(
                            "pred-1",
                            "succeeded",
                            outputJson: "\"https://replicate.delivery/pbxt/out.png\"")),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: ProviderApiToken,
                selectorApiToken: SelectorApiToken);

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);
            var fetch = await manager.FetchResultAsync(submit.JobId.Value, CancellationToken.None);

            Assert.Equal(ImageJobState.Queued, submit.State);
            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Equal(ImageJobState.Complete, fetch.State);
            Assert.Equal(2, apiHandler.Requests.Count);
            Assert.Equal(1, outputHandler.SendCount);
            Assert.Equal(
                "https://replicate.delivery/pbxt/out.png",
                outputHandler.RequestUri!.ToString());
            Assert.Equal("Bearer", outputHandler.Authorization!.Scheme);
            Assert.Equal(SelectorApiToken, outputHandler.Authorization.Parameter);

            var artifact = _artifactStore.Get(status.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Equal(VisionHandler.ArtifactKindGeneratedImage, artifact!.Kind);
            Assert.Equal("replicate", artifact.Metadata["provider"]!.GetValue<string>());
            Assert.Equal(
                ReplicateImageCapabilities.FluxSchnell,
                artifact.Metadata["model"]!.GetValue<string>());
            Assert.Equal(
                new byte[] { 9, 8, 7 },
                File.ReadAllBytes(_artifactStore.GetBlobAbsolutePath(
                    artifact.Id,
                    ImageMediaRoles.Image)));

            AssertNoTokenLeak(artifact, status, fetch);
            Assert.DoesNotContain(
                "replicate.delivery",
                MetadataJson(artifact),
                StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public async Task Missing_selector_token_fails_before_output_fetch()
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = request =>
                    request.Method == HttpMethod.Post
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, Prediction(
                            "pred-1",
                            "succeeded",
                            outputJson: "\"https://replicate.delivery/pbxt/out.png\"")),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: ProviderApiToken,
                selectorApiToken: " ");

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.NotNull(status.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, status.Error!.Code);
            Assert.False(status.Error.Retryable);
            Assert.Equal(0, outputHandler.SendCount);
            AssertNoTokenLeak(status);
        }

        [Theory]
        [InlineData("https://replicate.delivery.evil.test/out.png")]
        [InlineData("http://replicate.delivery/out.png")]
        public async Task Unsafe_output_url_fails_before_output_fetch(string outputUrl)
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = request =>
                    request.Method == HttpMethod.Post
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, Prediction(
                            "pred-1",
                            "succeeded",
                            outputJson: JsonValue.Create(outputUrl)!.ToJsonString())),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: ProviderApiToken,
                selectorApiToken: SelectorApiToken);

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.NotNull(status.Error);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, status.Error!.Code);
            Assert.False(status.Error.Retryable);
            Assert.Equal(0, outputHandler.SendCount);
            AssertNoTokenLeak(status);
        }

        [Fact]
        public async Task Data_removed_fails_on_status_path_before_output_fetch()
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = request =>
                    request.Method == HttpMethod.Post
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, """
                            {
                              "id": "pred-1",
                              "status": "succeeded",
                              "data_removed": true,
                              "urls": {
                                "get": "https://api.replicate.com/v1/predictions/pred-1",
                                "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
                              }
                            }
                            """),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: ProviderApiToken,
                selectorApiToken: SelectorApiToken);

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.NotNull(status.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, status.Error!.Code);
            Assert.False(status.Error.Retryable);
            Assert.Equal("data_removed", status.Error.ProviderErrorCode);
            Assert.Equal(0, outputHandler.SendCount);
            AssertNoTokenLeak(status);
        }

        private ImageJobManager Manager(
            TestHttpMessageHandler apiHandler,
            HttpMessageHandler outputHandler,
            string? providerApiToken,
            string? selectorApiToken)
        {
            var provider = new ReplicateImageProvider(
                () => providerApiToken,
                new ReplicateApiClient(new HttpClient(apiHandler)));
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new ReplicateImageProviderRegistration(provider),
            });
            var selector = new ReplicateImageArtifactRequestFactorySelector(
                () => selectorApiToken);

            return new ImageJobManager(
                registry,
                _artifactStore,
                _clock,
                _idGenerator,
                TimeSpan.FromMilliseconds(1),
                ImageJobManager.DefaultMaxConcurrentJobs,
                new ImageArtifactMaterializer(outputHandler),
                selector.Select,
                _ledger);
        }

        private static ImageJobStartRequest Start() =>
            new(
                new ImageGenerationRequest(
                    Model: ReplicateImageCapabilities.FluxSchnell,
                    Prompt: "sunlit massing study",
                    Resolution: "1K",
                    AspectRatio: "1:1",
                    NumberOfImages: 1,
                    ReferenceImages: null,
                    Options: new ReplicateImageOptions()),
                new Dictionary<MediaRef, ResolvedMedia>(),
                Array.Empty<Guid>());

        private static ResultArtifact RemoteArtifact(string url) =>
            new(
                ImageMediaRoles.Image,
                new RemoteArtifactBody(new Uri(url)),
                DeclaredMimeType: null,
                ProviderMetadata: new Dictionary<string, JsonNode>());

        private static ResolvedImageModel ReplicateModel() =>
            new(
                ReplicateImageCapabilities.FluxSchnell,
                ReplicateImageCapabilities.ProviderName,
                ImageSubmissionMode.AsyncImageJob,
                new ReplicateImageProvider(() => ProviderApiToken),
                ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell],
                new ReplicateImagePricingModel(),
                new ReplicateImageOptionsCodec());

        private static ResolvedImageModel NonReplicateModel() =>
            new(
                GeminiImageCapabilities.DefaultModel,
                GeminiImageCapabilities.ProviderName,
                ImageSubmissionMode.Sync,
                new Rook.Tests.Services.Vision.Image.FakeImageProvider(),
                GeminiImageCapabilities.Models[GeminiImageCapabilities.DefaultModel],
                new GeminiImagePricingModel(),
                new GeminiImageOptionsCodec());

        private static async Task<ImageJobStatusResult> WaitForTerminalAsync(
            ImageJobManager manager,
            Guid jobId)
        {
            var deadline = DateTime.UtcNow.AddSeconds(5);
            ImageJobStatusResult? last = null;
            while (DateTime.UtcNow < deadline)
            {
                last = await manager.GetStatusAsync(jobId, CancellationToken.None);
                if (last.State is ImageJobState.Complete
                    or ImageJobState.Error
                    or ImageJobState.Cancelled
                    or ImageJobState.Interrupted)
                {
                    return last;
                }

                await Task.Delay(10);
            }

            throw new TimeoutException(
                $"Job did not reach terminal state. Last state: {last?.State}.");
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string json) =>
            new(status)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };

        private static string Prediction(
            string id,
            string status,
            string outputJson = "null") =>
            $$"""
            {
              "id": "{{id}}",
              "status": "{{status}}",
              "output": {{outputJson}},
              "model": "black-forest-labs/flux-schnell",
              "version": "hidden-version",
              "metrics": { "predict_time": 1.25, "total_time": 2.5 },
              "urls": {
                "get": "https://api.replicate.com/v1/predictions/{{id}}",
                "cancel": "https://api.replicate.com/v1/predictions/{{id}}/cancel"
              }
            }
            """;

        private static void AssertNoTokenLeak(params object?[] values)
        {
            var payload = JsonSerializer.Serialize(values);
            Assert.DoesNotContain(
                ProviderApiToken,
                payload,
                StringComparison.Ordinal);
            Assert.DoesNotContain(
                SelectorApiToken,
                payload,
                StringComparison.Ordinal);
        }

        private static string MetadataJson(Artifact artifact)
        {
            var metadata = new JsonObject();
            foreach (var kvp in artifact.Metadata)
                metadata[kvp.Key] = kvp.Value?.DeepClone();
            return metadata.ToJsonString();
        }

        private sealed class CapturingOutputHandler : HttpMessageHandler
        {
            public int SendCount { get; private set; }
            public Uri? RequestUri { get; private set; }
            public AuthenticationHeaderValue? Authorization { get; private set; }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                SendCount++;
                RequestUri = request.RequestUri;
                Authorization = request.Headers.Authorization;

                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 9, 8, 7 }),
                };
                response.Content.Headers.ContentType =
                    new MediaTypeHeaderValue("image/png");
                return Task.FromResult(response);
            }
        }
    }
}
