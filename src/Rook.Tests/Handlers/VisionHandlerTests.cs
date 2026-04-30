using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Image.Gemini;
using Xunit;

namespace Rook.Tests.Handlers
{
    /// <summary>
    /// Pure-helper tests for <see cref="VisionHandler"/>.
    ///
    /// Dispatch-level tests are NOT here — instantiating VisionHandler and
    /// calling Dispatch triggers RhinoCommon assembly resolution (via
    /// DocumentContext and RhinoApp), which fails in the xUnit test host
    /// where RhinoCommon is not on the probe path. Dispatch-level
    /// validation is covered by the live Python tests at
    /// <c>mcp_server/tests/test_vision_routes_live.py</c>, which run
    /// against a real Rhino instance.
    ///
    /// Covered here:
    /// - Artifact kind constants (pinned strings; changing them
    ///   invalidates previously stored artifacts)
    /// - Validation helpers: ValidateResolution, ParseObjectBody,
    ///   RequireString
    /// - No-secret-leakage: GenericizeProviderError sanitizes API-key
    ///   query parameters from echoed URLs in provider error text
    /// - DPAPI roundtrip: <see cref="VisionSecretStoreTests"/>
    /// </summary>
    public class VisionHandlerTests
    {
        // ─── Artifact kind constants ────────────────────────────────────

        [Fact]
        public void ArtifactKinds_ArePinned()
        {
            Assert.Equal("generated_image", VisionHandler.ArtifactKindGeneratedImage);
            Assert.Equal("enhanced_prompt", VisionHandler.ArtifactKindEnhancedPrompt);
            Assert.Equal("depth_map", VisionHandler.ArtifactKindDepthMap);
            Assert.Equal("captured_viewport", VisionHandler.ArtifactKindCapturedViewport);
        }

        [Fact]
        public void BuildArtifactCountsByKind_IncludesAllVisionKinds()
        {
            var tempDir = Path.Combine(Path.GetTempPath(),
                "rook-vision-artifact-counts-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDir);
            try
            {
                var artifactStore = new ArtifactStore(tempDir);
                artifactStore.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("image", new byte[] { 1 }, "png") });
                artifactStore.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("image", new byte[] { 2 }, "png") });
                artifactStore.Create(
                    VisionHandler.ArtifactKindCapturedViewport,
                    new[] { new BlobInput("image", new byte[] { 3 }, "png") });
                artifactStore.Create(
                    VisionHandler.ArtifactKindEnhancedPrompt,
                    new[] { new BlobInput("prompt", new byte[] { 4 }, "json") });

                var counts = VisionHandler.BuildArtifactCountsByKind(artifactStore.List());

                Assert.Equal(2, counts[VisionHandler.ArtifactKindGeneratedImage]);
                Assert.Equal(1, counts[VisionHandler.ArtifactKindCapturedViewport]);
                Assert.Equal(1, counts[VisionHandler.ArtifactKindEnhancedPrompt]);
                Assert.Equal(0, counts[VisionHandler.ArtifactKindDepthMap]);
            }
            finally
            {
                try { Directory.Delete(tempDir, recursive: true); } catch { }
            }
        }

        [Fact]
        public void BuildOpenFolderStartInfo_UsesShellExecuteForCanonicalFolderPath()
        {
            var path = Path.Combine(Path.GetTempPath(), "rook-vision-artifacts-test");

            var psi = VisionHandler.BuildOpenFolderStartInfo(path);

            Assert.Equal(Path.GetFullPath(path), psi.FileName);
            Assert.True(psi.UseShellExecute);
        }

        [Fact]
        public async Task GenerateAsync_routes_through_image_provider_registry()
        {
            var root = CreateTempRoot("rook-vision-generate-registry");
            var settingsPath = Path.Combine(root, "RookSettings.json");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });
                var referencePath = Path.Combine(root, "reference.png");
                File.WriteAllBytes(referencePath, new byte[] { 6, 5, 4 });

                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var secrets = new VisionSecretStore(new RookSettingsStore(settingsPath));
                secrets.SetGeminiApiKey("test-gemini-key");
                var provider = new FakeImageProvider();
                var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                {
                    new GeminiImageProviderRegistration(provider),
                });
                var handler = new VisionHandler(
                    artifactStore,
                    secrets,
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    registry);
                var args = ParseArgs($$"""
                    {
                      "prompt": "make this rendering warmer",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "reference_image_paths": [ "{{JsonEncodedText.Encode(referencePath)}}" ],
                      "model": "nano-banana-2",
                      "resolution": "1K",
                      "aspect_ratio": "16:9"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.True(response.Success);
                Assert.NotNull(provider.CapturedRequest);
                Assert.Equal(GeminiImageCapabilities.NanoBanana2, provider.CapturedRequest!.Model);
                Assert.Equal("1K", provider.CapturedRequest.Resolution);
                Assert.Equal("16:9", provider.CapturedRequest.AspectRatio);
                Assert.Single(provider.CapturedRequest.ReferenceImages!);
                Assert.Equal(2, provider.CapturedMedia!.Count);
                var artifact = Assert.Single(artifactStore.List());
                Assert.Equal(VisionHandler.ArtifactKindGeneratedImage, artifact.Kind);
                Assert.Equal("generated-by-provider", artifact.Metadata["model"]!.GetValue<string>());
                Assert.Equal("image/png", artifact.Metadata["mime_type"]!.GetValue<string>());
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public async Task GenerateAsync_preserves_unknown_full_gemini_model_passthrough()
        {
            var root = CreateTempRoot("rook-vision-generate-unknown-model");
            var settingsPath = Path.Combine(root, "RookSettings.json");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var secrets = new VisionSecretStore(new RookSettingsStore(settingsPath));
                secrets.SetGeminiApiKey("test-gemini-key");
                var provider = new FakeImageProvider();
                var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                {
                    new GeminiImageProviderRegistration(provider),
                });
                var handler = new VisionHandler(
                    artifactStore,
                    secrets,
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    registry);
                var args = ParseArgs($$"""
                    {
                      "prompt": "make this rendering warmer",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "model": "gemini-future-image-preview",
                      "resolution": "1K",
                      "aspect_ratio": "1:1"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.True(response.Success);
                Assert.NotNull(provider.CapturedRequest);
                Assert.Equal("gemini-future-image-preview", provider.CapturedRequest!.Model);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public async Task GenerateAsync_resolved_non_gemini_provider_does_not_require_gemini_key_or_resolution()
        {
            var root = CreateTempRoot("rook-vision-generate-non-gemini");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var secrets = new VisionSecretStore(new RookSettingsStore(
                    Path.Combine(root, "RookSettings.json")));
                var provider = new FakeImageProvider(providerName: "custom");
                var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                {
                    new FakeImageProviderRegistration(
                        provider,
                        providerName: "custom",
                        modelId: "custom-image-model"),
                });
                var handler = new VisionHandler(
                    artifactStore,
                    secrets,
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    registry);
                var args = ParseArgs($$"""
                    {
                      "prompt": "make this rendering warmer",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "model": "custom-image-model",
                      "resolution": "custom-resolution",
                      "aspect_ratio": "custom-aspect"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.True(response.Success);
                Assert.NotNull(provider.CapturedRequest);
                Assert.Equal("custom-image-model", provider.CapturedRequest!.Model);
                Assert.Equal("custom-resolution", provider.CapturedRequest.Resolution);
                Assert.Equal("custom-aspect", provider.CapturedRequest.AspectRatio);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public async Task GenerateAsync_prefers_exact_registry_model_before_gemini_short_name_fallback()
        {
            var root = CreateTempRoot("rook-vision-generate-short-name-collision");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var secrets = new VisionSecretStore(new RookSettingsStore(
                    Path.Combine(root, "RookSettings.json")));
                var provider = new FakeImageProvider(providerName: "custom");
                var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                {
                    new FakeImageProviderRegistration(
                        provider,
                        providerName: "custom",
                        modelId: "nano-banana-2"),
                });
                var handler = new VisionHandler(
                    artifactStore,
                    secrets,
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    registry);
                var args = ParseArgs($$"""
                    {
                      "prompt": "make this rendering warmer",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "model": "nano-banana-2",
                      "resolution": "custom-resolution",
                      "aspect_ratio": "custom-aspect"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.True(response.Success);
                Assert.NotNull(provider.CapturedRequest);
                Assert.Equal("nano-banana-2", provider.CapturedRequest!.Model);
                Assert.Equal("custom", provider.ProviderName);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public async Task GenerateAsync_default_registry_resolves_fal_without_gemini_key()
        {
            var root = CreateTempRoot("rook-vision-generate-default-fal");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

                var handler = new VisionHandler(
                    new ArtifactStore(Path.Combine(root, "artifacts")),
                    new InMemoryGenerationSecretStore(),
                    new PromptEnhancer(),
                    new ViewportHandler());
                var args = ParseArgs($$"""
                    {
                      "prompt": "draw a quiet courtyard",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "model": "fal-ai/flux/schnell",
                      "resolution": "1K",
                      "aspect_ratio": "1:1"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.False(response.Success);
                Assert.Equal(
                    "fal API key is not configured. Set it via the Vision settings " +
                    "before calling /vision/generate.",
                    response.Data);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public async Task GenerateAsync_exact_fal_model_id_wins_before_gemini_fallback()
        {
            var root = CreateTempRoot("rook-vision-generate-exact-fal");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

                var handler = new VisionHandler(
                    new ArtifactStore(Path.Combine(root, "artifacts")),
                    new InMemoryGenerationSecretStore(),
                    new PromptEnhancer(),
                    new ViewportHandler());
                var args = ParseArgs($$"""
                    {
                      "prompt": "draw a quiet courtyard",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "model": "fal-ai/flux/schnell",
                      "resolution": "1K",
                      "aspect_ratio": "4:3"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.False(response.Success);
                var message = Assert.IsType<string>(response.Data);
                Assert.Contains("fal API key is not configured", message);
                Assert.DoesNotContain("Gemini", message);
                Assert.DoesNotContain("Unknown image model", message);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public async Task GenerateAsync_persists_remote_provider_artifact_through_materializer()
        {
            var root = CreateTempRoot("rook-vision-generate-remote-artifact");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

                var responseBytes = new byte[] { 0xFF, 0xD8, 0xFF };
                var httpHandler = new CapturingHttpMessageHandler(_ =>
                {
                    var response = new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new ByteArrayContent(responseBytes),
                    };
                    response.Content.Headers.ContentType =
                        new MediaTypeHeaderValue("image/png");
                    return response;
                });
                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var provider = new FakeImageProvider(
                    providerName: "fal",
                    artifact: RemoteImageArtifact(
                        "https://cdn.example.com/fal/out.jpg?token=secret",
                        declaredMimeType: "image/jpeg"),
                    envelopeMetadata: new Dictionary<string, JsonNode>
                    {
                        ["modelVersion"] = JsonValue.Create("fal-ai/flux/schnell")!,
                    });
                var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                {
                    new FakeImageProviderRegistration(
                        provider,
                        providerName: "fal",
                        modelId: FalImageCapabilities.FluxSchnell,
                        resolutions: new[] { "1K" },
                        aspectRatios: new[] { "1:1" }),
                });
                var handler = new VisionHandler(
                    artifactStore,
                    new VisionSecretStore(new RookSettingsStore(
                        Path.Combine(root, "RookSettings.json"))),
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    registry,
                    new ImageArtifactMaterializer(httpHandler));
                var args = ParseArgs($$"""
                    {
                      "prompt": "draw a quiet courtyard",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "model": "fal-ai/flux/schnell",
                      "resolution": "1K",
                      "aspect_ratio": "1:1"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.True(response.Success);
                Assert.Equal("https://cdn.example.com/fal/out.jpg?token=secret",
                    httpHandler.RequestUri!.ToString());
                Assert.Null(httpHandler.Authorization);
                var artifact = Assert.Single(artifactStore.List());
                Assert.Equal("image/jpeg", artifact.Metadata["mime_type"]!.GetValue<string>());
                Assert.Equal("fal-ai/flux/schnell", artifact.Metadata["model"]!.GetValue<string>());
                var imagePath = artifactStore.GetBlobAbsolutePath(artifact.Id, "image");
                Assert.Equal(responseBytes, File.ReadAllBytes(imagePath));
                Assert.EndsWith(".jpg", imagePath, StringComparison.OrdinalIgnoreCase);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public async Task GenerateAsync_remote_materialization_failure_returns_sanitized_failure()
        {
            var root = CreateTempRoot("rook-vision-generate-remote-failure");
            try
            {
                var inputPath = Path.Combine(root, "input.png");
                File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

                var httpHandler = new CapturingHttpMessageHandler(_ =>
                    new HttpResponseMessage(HttpStatusCode.NotFound)
                    {
                        Content = new StringContent(
                            "raw remote detail https://cdn.example.com/out.png?token=secret"),
                    });
                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var provider = new FakeImageProvider(
                    providerName: "fal",
                    artifact: RemoteImageArtifact(
                        "https://cdn.example.com/out.png?token=secret"));
                var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                {
                    new FakeImageProviderRegistration(
                        provider,
                        providerName: "fal",
                        modelId: FalImageCapabilities.FluxSchnell,
                        resolutions: new[] { "1K" },
                        aspectRatios: new[] { "1:1" }),
                });
                var handler = new VisionHandler(
                    artifactStore,
                    new VisionSecretStore(new RookSettingsStore(
                        Path.Combine(root, "RookSettings.json"))),
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    registry,
                    new ImageArtifactMaterializer(httpHandler));
                var args = ParseArgs($$"""
                    {
                      "prompt": "draw a quiet courtyard",
                      "input_image_path": "{{JsonEncodedText.Encode(inputPath)}}",
                      "model": "fal-ai/flux/schnell",
                      "resolution": "1K",
                      "aspect_ratio": "1:1"
                    }
                    """);

                var response = await handler.GenerateAsync(args, CancellationToken.None);

                Assert.False(response.Success);
                Assert.Equal(
                    "Image generation failed. Remote image artifact fetch failed with HTTP 404.",
                    response.Data);
                var message = Assert.IsType<string>(response.Data);
                Assert.DoesNotContain("token", message);
                Assert.Empty(artifactStore.List());
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        // ─── Reveal artifact file ───────────────────────────────────────

        private static Dictionary<string, JsonElement> ParseArgs(string json)
            => VisionHandler.ParseObjectBody(json);

        private sealed class FakeImageProvider : IImageProvider
        {
            private readonly ResultArtifact? _artifact;
            private readonly IReadOnlyDictionary<string, JsonNode>? _envelopeMetadata;

            public FakeImageProvider(
                string providerName = GeminiImageCapabilities.ProviderName,
                ResultArtifact? artifact = null,
                IReadOnlyDictionary<string, JsonNode>? envelopeMetadata = null)
            {
                ProviderName = providerName;
                _artifact = artifact;
                _envelopeMetadata = envelopeMetadata;
            }

            public string ProviderName { get; }
            public ImageGenerationRequest? CapturedRequest { get; private set; }
            public IReadOnlyDictionary<MediaRef, ResolvedMedia>? CapturedMedia { get; private set; }

            public Task<ProviderSubmitOutcome> SubmitAsync(
                ImageGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct)
            {
                CapturedRequest = request;
                CapturedMedia = resolvedMedia;
                var artifact = _artifact ?? InlineImageArtifact(
                    new byte[] { 1, 2, 3 },
                    "image/png",
                    "generated-by-provider");
                var envelopeMetadata = _envelopeMetadata
                    ?? new Dictionary<string, JsonNode>
                    {
                        ["modelVersion"] = JsonValue.Create("generated-by-provider")!,
                    };
                return Task.FromResult<ProviderSubmitOutcome>(
                    new SyncSubmitOutcome(
                        new SuccessResultOutcome(
                            new ProviderResultEnvelope(
                                new[] { artifact },
                                envelopeMetadata))));
            }

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                throw new InvalidOperationException();

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                throw new InvalidOperationException();

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                throw new InvalidOperationException();
        }

        private sealed class FakeImageProviderRegistration : IImageProviderRegistration
        {
            private readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models;

            public FakeImageProviderRegistration(
                IImageProvider provider,
                string providerName,
                string modelId,
                IReadOnlyList<string>? resolutions = null,
                IReadOnlyList<string>? aspectRatios = null)
            {
                Provider = provider;
                ProviderName = providerName;
                _models = new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>
                {
                    [modelId] = (
                        new ImageCapability(
                            Id: modelId,
                            Name: modelId,
                            Status: "preview",
                            Resolutions: resolutions ?? new[] { "custom-resolution" },
                            AspectRatios: aspectRatios ?? new[] { "custom-aspect" },
                            MaxReferenceImages: 0,
                            SupportsImageToImage: true,
                            SupportsTextToImage: true),
                        new FakeImagePricingModel()),
                };
            }

            public string ProviderName { get; }
            public IImageProvider Provider { get; }
            public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
                = new FakeImageOptionsCodec();
            public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models
                => _models;
            public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
                = Array.Empty<ProviderSecretRequirement>();
        }

        private sealed record FakeImageOptions : ProviderOptions;

        private sealed class FakeImageOptionsCodec
            : IProviderOptionsCodec<ImageGenerationRequest, ImageCapability>
        {
            public ValidationResult Validate(
                ImageGenerationRequest request,
                ProviderOptions options,
                ImageCapability capability) => ValidationResult.Ok();

            public JsonObject Serialize(ProviderOptions options) => new JsonObject();

            public ProviderOptionsDecodeResult Deserialize(JsonObject json) =>
                ProviderOptionsDecodeResult.Ok(new FakeImageOptions());
        }

        private sealed class FakeImagePricingModel
            : IPricingModel<ImageGenerationRequest, ImageCapability>
        {
            public string PricingSource => "test";
            public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

            public PricingResult Estimate(
                ImageGenerationRequest request,
                ImageCapability capability) =>
                PricingResult.Ok(
                    new JobPricing("USD", 0m, "call", 1m, 0m, "test"),
                    new CostEstimate(0m, 0m, false, "test-stub"));

            public JobPricing? ExtractActualSpend(
                IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
                JsonNode? responseBody) => null;
        }

        private static string CreateTempRoot(string name)
        {
            var root = Path.Combine(Path.GetTempPath(), name + "-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            return root;
        }

        private static ResultArtifact InlineImageArtifact(
            byte[] bytes,
            string declaredMimeType,
            string model) =>
            new ResultArtifact(
                Role: ImageMediaRoles.Image,
                Body: new InlineArtifactBody(bytes),
                DeclaredMimeType: declaredMimeType,
                ProviderMetadata: new Dictionary<string, JsonNode>
                {
                    ["model"] = JsonValue.Create(model)!,
                });

        private static ResultArtifact RemoteImageArtifact(
            string url,
            string? declaredMimeType = null) =>
            new ResultArtifact(
                Role: ImageMediaRoles.Image,
                Body: new RemoteArtifactBody(new Uri(url)),
                DeclaredMimeType: declaredMimeType,
                ProviderMetadata: new Dictionary<string, JsonNode>
                {
                    ["model"] = JsonValue.Create("fal-ai/flux/schnell")!,
                });

        private sealed class InMemoryGenerationSecretStore : IGenerationSecretStore
        {
            private readonly Dictionary<string, string> _secrets = new(StringComparer.Ordinal);

            public string? GetSecret(string secretKey) =>
                _secrets.TryGetValue(secretKey, out var value) ? value : null;

            public void SetSecret(string secretKey, string value) =>
                _secrets[secretKey] = value;

            public void RemoveSecret(string secretKey) =>
                _secrets.Remove(secretKey);

            public bool HasSecret(string secretKey) =>
                _secrets.ContainsKey(secretKey);

            public string? GetPreview(string secretKey) =>
                HasSecret(secretKey) ? "test-preview" : null;
        }

        private sealed class CapturingHttpMessageHandler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, HttpResponseMessage> _onSend;

            public CapturingHttpMessageHandler(
                Func<HttpRequestMessage, HttpResponseMessage> onSend)
            {
                _onSend = onSend;
            }

            public Uri? RequestUri { get; private set; }
            public AuthenticationHeaderValue? Authorization { get; private set; }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                RequestUri = request.RequestUri;
                Authorization = request.Headers.Authorization;
                return Task.FromResult(_onSend(request));
            }
        }

        // ─── Provider secret ops ───────────────────────────────────────

        [Fact]
        public void SetProviderSecret_SavesDeclaredFalKey()
        {
            var store = new InMemoryGenerationSecretStore();
            var handler = new VisionHandler(
                new ArtifactStore(CreateTempRoot("rook-provider-secret-set")),
                store,
                new PromptEnhancer(),
                new ViewportHandler());
            var args = VisionHandler.ParseObjectBody(
                "{\"provider_name\":\"fal\",\"secret_key\":\"fal.api_key\",\"value\":\"fal-key-value\"}");

            var response = handler.SetProviderSecret(args);

            Assert.True(response.Success);
            Assert.Equal("fal-key-value", store.GetSecret(GenerationSecretKeys.FalApiKey));
            var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
            Assert.Equal("fal", data["provider_name"]);
            Assert.Equal(GenerationSecretKeys.FalApiKey, data["secret_key"]);
            Assert.Equal(true, data["has_secret"]);
            Assert.Equal("test-preview", data["preview"]);
        }

        [Fact]
        public void SetProviderSecret_RejectsCrossProviderSecretKey()
        {
            var store = new InMemoryGenerationSecretStore();
            var handler = new VisionHandler(
                new ArtifactStore(CreateTempRoot("rook-provider-secret-cross")),
                store,
                new PromptEnhancer(),
                new ViewportHandler());
            var args = VisionHandler.ParseObjectBody(
                "{\"provider_name\":\"gemini\",\"secret_key\":\"fal.api_key\",\"value\":\"fal-key-value\"}");

            var response = handler.SetProviderSecret(args);

            Assert.False(response.Success);
            Assert.Null(store.GetSecret(GenerationSecretKeys.FalApiKey));
            var message = Assert.IsType<string>(response.Data);
            Assert.Contains("fal.api_key", message);
            Assert.Contains("gemini", message);
        }

        [Fact]
        public void ClearProviderSecret_RemovesDeclaredFalKey()
        {
            var store = new InMemoryGenerationSecretStore();
            store.SetSecret(GenerationSecretKeys.FalApiKey, "fal-key-value");
            var handler = new VisionHandler(
                new ArtifactStore(CreateTempRoot("rook-provider-secret-clear")),
                store,
                new PromptEnhancer(),
                new ViewportHandler());
            var args = VisionHandler.ParseObjectBody(
                "{\"provider_name\":\"fal\",\"secret_key\":\"fal.api_key\"}");

            var response = handler.ClearProviderSecret(args);

            Assert.True(response.Success);
            Assert.Null(store.GetSecret(GenerationSecretKeys.FalApiKey));
            var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
            Assert.Equal("fal", data["provider_name"]);
            Assert.Equal(GenerationSecretKeys.FalApiKey, data["secret_key"]);
            Assert.Equal(false, data["has_secret"]);
            Assert.Null(data["preview"]);
        }

        [Fact]
        public void LegacySetApiKey_RemainsGeminiOnly()
        {
            var store = new InMemoryGenerationSecretStore();
            var handler = new VisionHandler(
                new ArtifactStore(CreateTempRoot("rook-provider-secret-legacy")),
                store,
                new PromptEnhancer(),
                new ViewportHandler());
            var args = VisionHandler.ParseObjectBody(
                "{\"api_key\":\"gemini-key-value\",\"provider_name\":\"fal\",\"secret_key\":\"fal.api_key\"}");

            var response = handler.SetApiKey(args);

            Assert.True(response.Success);
            Assert.Equal("gemini-key-value", store.GetSecret(GenerationSecretKeys.GeminiApiKey));
            Assert.Null(store.GetSecret(GenerationSecretKeys.FalApiKey));
        }

        [Fact]
        public void BuildRevealFileStartInfo_SelectsCanonicalFilePath()
        {
            var path = Path.Combine(Path.GetTempPath(), "rook vision image.png");

            var psi = VisionHandler.BuildRevealFileStartInfo(path);

            Assert.Equal("explorer.exe", psi.FileName);
            Assert.Equal($"/select,\"{Path.GetFullPath(path)}\"", psi.Arguments);
        }

        [Fact]
        public void ResolveArtifactFilePathForReveal_ReturnsCanonicalBlobPath()
        {
            var root = CreateTempRoot("rook-vision-reveal-success");
            try
            {
                var store = new ArtifactStore(root);
                var artifact = store.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
                var args = ParseArgs(
                    $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

                var path = VisionHandler.ResolveArtifactFilePathForReveal(store, args);

                Assert.Equal(Path.GetFullPath(Path.Combine(
                    root,
                    artifact.CreatedAt.ToString("yyyy-MM-dd"),
                    artifact.Id.ToString("D"),
                    "image.png")), path);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Theory]
        [InlineData("{}")]
        [InlineData("{\"artifact_id\":42,\"role\":\"image\"}")]
        [InlineData("{\"artifact_id\":\"\",\"role\":\"image\"}")]
        [InlineData("{\"artifact_id\":\"not-a-guid\",\"role\":\"image\"}")]
        public void ResolveArtifactFilePathForReveal_RequiresArtifactId(string json)
        {
            var root = CreateTempRoot("rook-vision-reveal-bad-id");
            try
            {
                var store = new ArtifactStore(root);
                var args = ParseArgs(json);

                Assert.Throws<ArgumentException>(() =>
                    VisionHandler.ResolveArtifactFilePathForReveal(store, args));
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Theory]
        [InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\"}")]
        [InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\",\"role\":42}")]
        [InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\",\"role\":\"\"}")]
        [InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\",\"role\":\"   \"}")]
        public void ResolveArtifactFilePathForReveal_RequiresRole(string json)
        {
            var root = CreateTempRoot("rook-vision-reveal-bad-role");
            try
            {
                var store = new ArtifactStore(root);
                var args = ParseArgs(json);

                Assert.Throws<ArgumentException>(() =>
                    VisionHandler.ResolveArtifactFilePathForReveal(store, args));
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public void ResolveArtifactFilePathForReveal_MissingRole_ThrowsKeyNotFound()
        {
            var root = CreateTempRoot("rook-vision-reveal-missing-role");
            try
            {
                var store = new ArtifactStore(root);
                var artifact = store.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("thumbnail", new byte[] { 1 }, "png") });
                var args = ParseArgs(
                    $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

                Assert.Throws<KeyNotFoundException>(() =>
                    VisionHandler.ResolveArtifactFilePathForReveal(store, args));
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public void ResolveArtifactFilePathForReveal_MissingBlob_ThrowsFileNotFound()
        {
            var root = CreateTempRoot("rook-vision-reveal-missing-file");
            try
            {
                var store = new ArtifactStore(root);
                var artifact = store.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("image", new byte[] { 1 }, "png") });
                var blobPath = store.GetBlobAbsolutePath(artifact.Id, "image");
                File.Delete(blobPath);
                var args = ParseArgs(
                    $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

                Assert.Throws<FileNotFoundException>(() =>
                    VisionHandler.ResolveArtifactFilePathForReveal(store, args));
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public void ResolveArtifactFilePathForReveal_TraversalManifest_SurfacesInvalidData()
        {
            var root = CreateTempRoot("rook-vision-reveal-traversal");
            try
            {
                var store = new ArtifactStore(root);
                var artifact = store.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("image", new byte[] { 1 }, "png") });
                var artifactDir = Path.GetDirectoryName(store.GetBlobAbsolutePath(artifact.Id, "image"))!;
                var manifestPath = Path.Combine(artifactDir, "manifest.json");
                var manifest = File.ReadAllText(manifestPath)
                    .Replace("\"path\": \"image.png\"", "\"path\": \"..\\\\outside.png\"");
                File.WriteAllText(manifestPath, manifest);
                var args = ParseArgs(
                    $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

                var ex = Assert.Throws<InvalidDataException>(() =>
                    VisionHandler.ResolveArtifactFilePathForReveal(store, args));
                Assert.Contains("path", ex.Message, StringComparison.OrdinalIgnoreCase);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public void TryMapRevealArtifactFileException_MapsMissingArtifactAndMissingBlob()
        {
            Assert.True(VisionHandler.TryMapRevealArtifactFileException(
                new KeyNotFoundException("missing"), out var keyMessage));
            Assert.Equal(VisionHandler.RevealFileUnavailableMessage, keyMessage);

            Assert.True(VisionHandler.TryMapRevealArtifactFileException(
                new FileNotFoundException("missing"), out var fileMessage));
            Assert.Equal(VisionHandler.RevealFileUnavailableMessage, fileMessage);
        }

        [Fact]
        public void TryMapRevealArtifactFileException_DoesNotMaskInvalidDataOrBadArgs()
        {
            Assert.False(VisionHandler.TryMapRevealArtifactFileException(
                new InvalidDataException("Manifest path escapes artifact directory."), out var invalidDataMessage));
            Assert.Null(invalidDataMessage);

            Assert.False(VisionHandler.TryMapRevealArtifactFileException(
                new ArgumentException("Missing role."), out var argumentMessage));
            Assert.Null(argumentMessage);
        }

        // ─── Model catalog + short-name resolution ──────────────────────

        [Fact]
        public void Models_AvailableCatalog_OffersTwoPaidOnlyEntries()
        {
            // The UI dropdown is populated from AvailableModels. Changing
            // the count or the short-name set is a user-visible change —
            // surface it as a test diff, not a silent drop.
            var shortNames = GeminiImageCapabilities.AvailableModels
                .Select(m => (string?)m["short_name"])
                .ToList();
            Assert.Equal(2, shortNames.Count);
            Assert.Contains("nano-banana-2", shortNames);
            Assert.Contains("nano-banana-pro", shortNames);
        }

        [Fact]
        public void Models_AvailableCatalog_AdvertisesModelSpecificResolutions()
        {
            var byShortName = GeminiImageCapabilities.AvailableModels
                .ToDictionary(m => (string)m["short_name"]!);

            var flashResolutions = Assert.IsAssignableFrom<IEnumerable<string>>(
                byShortName["nano-banana-2"]["supported_resolutions"]);
            Assert.Contains("512", flashResolutions);
            Assert.Contains("1K", flashResolutions);
            Assert.Contains("2K", flashResolutions);
            Assert.Contains("4K", flashResolutions);

            var proResolutions = Assert.IsAssignableFrom<IEnumerable<string>>(
                byShortName["nano-banana-pro"]["supported_resolutions"]);
            Assert.DoesNotContain("512", proResolutions);
            Assert.Contains("1K", proResolutions);
            Assert.Contains("2K", proResolutions);
            Assert.Contains("4K", proResolutions);
        }

        [Fact]
        public void Models_ResolutionMetadata_SeparatesCommonFromModelSpecificValues()
        {
            Assert.Equal(new[] { "1K", "2K", "4K" }, VisionHandler.CommonResolutions);

            var byModel = VisionHandler.SupportedResolutionsByModelShortName();
            Assert.Equal(
                new[] { "512", "1K", "2K", "4K" },
                byModel["nano-banana-2"]);
            Assert.Equal(
                new[] { "1K", "2K", "4K" },
                byModel["nano-banana-pro"]);
        }

        [Fact]
        public void Models_AvailableCatalog_DoesNotExposeFreeTier()
        {
            // Regression: free-tier models are deliberately NOT exposed
            // because API keys can't invoke free-tier endpoints —
            // including them would only generate 429s. A future addition
            // must be an explicit decision documented on the catalog.
            var shortNames = GeminiImageCapabilities.AvailableModels
                .Select(m => (string?)m["short_name"] ?? "")
                .ToList();
            Assert.DoesNotContain(shortNames, n => n.Contains("2.5-flash"));
            Assert.DoesNotContain(shortNames, n => n.Contains("free"));
        }

        [Fact]
        public void Models_DefaultShortName_MatchesShortNameToIdEntry()
        {
            // The UI selects the "default" option by matching the
            // overview's default_model string against each option's
            // value. If DefaultShortName isn't in ShortNameToId the UI
            // never marks any option selected.
            Assert.Contains(GeminiImageCapabilities.DefaultShortName,
                GeminiImageCapabilities.ShortNameToId.Keys);
        }

        [Fact]
        public void Models_DefaultShortName_ResolvesToDefaultFullId()
        {
            Assert.Equal(
                GeminiImageCapabilities.DefaultModel,
                GeminiImageCapabilities.ResolveShortName(GeminiImageCapabilities.DefaultShortName));
        }

        [Theory]
        [InlineData("nano-banana-2", "gemini-3.1-flash-image-preview")]
        [InlineData("nano-banana-pro", "gemini-3-pro-image-preview")]
        public void Models_ResolveShortName_MapsKnownShortNames(string shortName, string expectedFullId)
        {
            Assert.Equal(expectedFullId, GeminiImageCapabilities.ResolveShortName(shortName));
        }

        [Fact]
        public void Models_ResolveShortName_NullOrEmpty_ReturnsDefault()
        {
            Assert.Equal(GeminiImageCapabilities.DefaultModel, GeminiImageCapabilities.ResolveShortName(null));
            Assert.Equal(GeminiImageCapabilities.DefaultModel, GeminiImageCapabilities.ResolveShortName(""));
        }

        [Fact]
        public void Models_ResolveShortName_UnknownValue_PassesThrough()
        {
            // Power users (and agents targeting a new Google release
            // before Rook catches up) need to be able to request a model
            // by full Gemini ID. The resolver must not clobber anything
            // that isn't a short-name entry.
            const string custom = "gemini-4-hypothetical-image-preview";
            Assert.Equal(custom, GeminiImageCapabilities.ResolveShortName(custom));
        }

        // ─── Input bound constants ──────────────────────────────────────

        [Fact]
        public void InputBounds_ArePinned()
        {
            Assert.Equal(16_000, VisionHandler.MaxPromptLength);
            Assert.Equal(4_000, VisionHandler.MaxContextLength);
            Assert.Equal(10L * 1024 * 1024, VisionHandler.MaxInputImageBytes);
            Assert.Equal(8, VisionHandler.MaxReferenceImages);
            Assert.Equal(15L * 1024 * 1024, VisionHandler.MaxAggregateImageBytes);
            Assert.Equal(4096, VisionHandler.MaxDepthMaxEdge);
            Assert.Equal(1024, VisionHandler.DefaultDepthMaxEdge);
        }

        [Fact]
        public void AggregateCap_IsBelowGeminiInlinePayloadLimit()
        {
            // Gemini's inline-payload guidance is ~20 MB per request;
            // after base64 expansion (~1.33x) and JSON envelope overhead,
            // the raw aggregate must stay under 20 MB. 15 MB raw = ~20 MB
            // base64 leaves safety margin.
            const long GeminiInlineLimit = 20L * 1024 * 1024;
            Assert.True(
                VisionHandler.MaxAggregateImageBytes < GeminiInlineLimit,
                "Aggregate cap must leave headroom under Gemini's inline limit.");
        }

        [Fact]
        public void AggregateCap_IsGreaterThanPerFileCap()
        {
            // Nonsense otherwise — aggregate must accommodate at least
            // one max-sized primary image.
            Assert.True(
                VisionHandler.MaxAggregateImageBytes >= VisionHandler.MaxInputImageBytes,
                "Aggregate cap must accommodate at least one max-sized image.");
        }

        // ─── Resolution validation ──────────────────────────────────────

        [Theory]
        [InlineData("512")]
        [InlineData("1K")]
        [InlineData("2K")]
        [InlineData("4K")]
        [InlineData("1k")]   // case-insensitive
        [InlineData("2k")]
        [InlineData("")]     // empty is "caller didn't specify"; allowed
        public void ValidateResolution_AllowedValues_NoThrow(string resolution)
        {
            VisionHandler.ValidateResolution(resolution);
        }

        [Fact]
        public void ValidateResolution_512RejectedForNanoBananaPro()
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.ValidateResolution(
                    "512", GeminiImageCapabilities.NanoBananaPro));
            Assert.Contains("resolution", ex.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("nano-banana-pro", ex.Message);
        }

        [Theory]
        [InlineData("8K")]
        [InlineData("HD")]
        [InlineData("1080p")]
        [InlineData("bogus")]
        public void ValidateResolution_RejectedValues_Throw(string resolution)
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.ValidateResolution(resolution));
            Assert.Contains("resolution", ex.Message, StringComparison.OrdinalIgnoreCase);
        }

        // ─── Aspect-ratio validation / normalization ───────────────────

        [Fact]
        public void AllowedAspectRatios_MatchesGeminiApiList()
        {
            Assert.Equal(
                new[]
                {
                    "1:1", "1:4", "4:1", "1:8", "8:1",
                    "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                    "9:16", "16:9", "21:9",
                },
                VisionHandler.AllowedAspectRatios);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("auto")]
        [InlineData("AUTO")]
        [InlineData("current")]
        public void NormalizeAspectRatio_AutoValues_ReturnNull(string? raw)
        {
            Assert.Null(VisionHandler.NormalizeAspectRatio(raw));
        }

        [Theory]
        [InlineData("1:1")]
        [InlineData("1:4")]
        [InlineData("4:1")]
        [InlineData("1:8")]
        [InlineData("8:1")]
        [InlineData("2:3")]
        [InlineData("3:2")]
        [InlineData("3:4")]
        [InlineData("4:3")]
        [InlineData("4:5")]
        [InlineData("5:4")]
        [InlineData("9:16")]
        [InlineData("16:9")]
        [InlineData("21:9")]
        public void NormalizeAspectRatio_SupportedValues_ReturnRaw(string ratio)
        {
            Assert.Equal(ratio, VisionHandler.NormalizeAspectRatio(ratio));
        }

        [Theory]
        [InlineData("5:7")]
        [InlineData("square")]
        [InlineData("16/9")]
        public void NormalizeAspectRatio_UnsupportedValues_Throw(string ratio)
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.NormalizeAspectRatio(ratio));
            Assert.Contains("aspect_ratio", ex.Message);
        }

        // ─── GenericizeProviderError: no secret leakage ─────────────────
        // If a provider error response echoes a URL containing ?key=...,
        // the key could leak into our envelope. These tests pin the
        // sanitizer so regressions are caught.

        [Fact]
        public void GenericizeProviderError_RedactsKeyInUrl()
        {
            var raw = "Error calling https://generativelanguage.googleapis.com/" +
                      "v1beta/models/gemini-3.1-flash-image-preview:generateContent" +
                      "?key=AIzaSyExample_SecretKey12345";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.DoesNotContain("AIzaSyExample_SecretKey12345", sanitized);
            Assert.Contains("REDACTED", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_RedactsKeyInAmpersandUrl()
        {
            var raw = "URL: https://example.com/api?foo=bar&key=SECRET_12345&baz=qux";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.DoesNotContain("SECRET_12345", sanitized);
            Assert.Contains("REDACTED", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_CaseInsensitiveKeyParam()
        {
            var raw = "Error: ?Key=SHOULD_ALSO_REDACT";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.DoesNotContain("SHOULD_ALSO_REDACT", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_NullOrEmpty_ReturnsPlaceholder()
        {
            Assert.Equal("(no detail)", VisionHandler.GenericizeProviderError(null));
            Assert.Equal("(no detail)", VisionHandler.GenericizeProviderError(""));
        }

        [Fact]
        public void GenericizeProviderError_TruncatesLongMessages()
        {
            var raw = new string('x', 1000);
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.True(sanitized.Length <= 520,
                $"Sanitized length {sanitized.Length} exceeded cap.");
            Assert.Contains("truncated", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_NoKey_LeavesMessageAlone()
        {
            var raw = "plain error with no key parameter at all";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.Equal(raw, sanitized);
        }

        // ─── ParseObjectBody ────────────────────────────────────────────

        [Fact]
        public void ParseObjectBody_NullEmpty_ReturnsEmpty()
        {
            Assert.Empty(VisionHandler.ParseObjectBody(null));
            Assert.Empty(VisionHandler.ParseObjectBody(""));
        }

        [Fact]
        public void ParseObjectBody_MalformedJson_ThrowsArgumentException()
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.ParseObjectBody("{not-json"));
            Assert.Contains("Invalid JSON", ex.Message);
        }

        [Fact]
        public void ParseObjectBody_ValidObject_ReturnsFields()
        {
            var body = JsonSerializer.Serialize(new { op = "generate", prompt = "x" });
            var args = VisionHandler.ParseObjectBody(body);
            Assert.Equal(2, args.Count);
            Assert.True(args.ContainsKey("op"));
            Assert.True(args.ContainsKey("prompt"));
        }

        // ─── RequireString ──────────────────────────────────────────────

        [Fact]
        public void RequireString_Present_ReturnsValue()
        {
            var args = VisionHandler.ParseObjectBody("{\"x\":\"hello\"}");
            Assert.Equal("hello", VisionHandler.RequireString(args, "x", 100));
        }

        [Fact]
        public void RequireString_Missing_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
            Assert.Contains("x", ex.Message);
        }

        [Fact]
        public void RequireString_WrongType_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"x\":42}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
        }

        [Fact]
        public void RequireString_Empty_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"x\":\"\"}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
        }

        [Fact]
        public void RequireString_OverLength_Throws()
        {
            var big = "\"" + new string('a', 101) + "\"";
            var args = VisionHandler.ParseObjectBody("{\"x\":" + big + "}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
            Assert.Contains("length", ex.Message, StringComparison.OrdinalIgnoreCase);
        }

        // ─── RequireArtifactId (PR-5b) ──────────────────────────────────

        [Fact]
        public void RequireArtifactId_Present_ReturnsGuid()
        {
            var id = Guid.NewGuid();
            var args = VisionHandler.ParseObjectBody(
                "{\"artifact_id\":\"" + id.ToString("D") + "\"}");
            Assert.Equal(id, VisionHandler.RequireArtifactId(args));
        }

        [Fact]
        public void RequireArtifactId_Missing_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
            Assert.Contains("artifact_id", ex.Message);
        }

        [Fact]
        public void RequireArtifactId_WrongType_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"artifact_id\":42}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
        }

        [Fact]
        public void RequireArtifactId_Empty_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"artifact_id\":\"\"}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
        }

        [Theory]
        [InlineData("not-a-guid")]
        [InlineData("12345")]
        [InlineData("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")]
        public void RequireArtifactId_Malformed_Throws(string bad)
        {
            var args = VisionHandler.ParseObjectBody(
                "{\"artifact_id\":\"" + bad + "\"}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
            Assert.Contains("GUID", ex.Message);
        }

        // ─── GetBoolArg (PR-5b) ─────────────────────────────────────────

        [Theory]
        [InlineData("{\"approved\":true}", true)]
        [InlineData("{\"approved\":false}", false)]
        public void GetBoolArg_BooleanValue_Returned(string json, bool expected)
        {
            var args = VisionHandler.ParseObjectBody(json);
            Assert.Equal(expected, VisionHandler.GetBoolArg(args, "approved"));
        }

        [Theory]
        [InlineData("{}")]
        [InlineData("{\"approved\":\"true\"}")]       // string "true" is NOT bool
        [InlineData("{\"approved\":1}")]              // number 1 is NOT bool
        [InlineData("{\"approved\":null}")]
        public void GetBoolArg_NonBoolean_ReturnsNull(string json)
        {
            var args = VisionHandler.ParseObjectBody(json);
            Assert.Null(VisionHandler.GetBoolArg(args, "approved"));
        }

        // ─── IsApproved (PR-5b) ─────────────────────────────────────────

        [Fact]
        public void IsApproved_FlagTrue_ReturnsTrue()
        {
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = JsonValue.Create(true) });
            Assert.True(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagFalse_ReturnsFalse()
        {
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = JsonValue.Create(false) });
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagMissing_ReturnsFalse()
        {
            var artifact = MakeArtifactWithFlags(new Dictionary<string, JsonNode?>());
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagNotBool_ReturnsFalse()
        {
            // Defensive: a flag value of a non-bool type (e.g. string)
            // should not throw — a best-effort "false" is correct.
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = JsonValue.Create("yes") });
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagNull_ReturnsFalse()
        {
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = null });
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        private static Artifact MakeArtifactWithFlags(
            IReadOnlyDictionary<string, JsonNode?> flags)
        {
            return new Artifact(
                Id: Guid.NewGuid(),
                Kind: "generated_image",
                CreatedAt: DateTimeOffset.UtcNow,
                Files: new[] { new ArtifactFile("image", "image.png") },
                ParentIds: Array.Empty<Guid>(),
                Metadata: new Dictionary<string, JsonNode?>(),
                Flags: flags);
        }
    }

    /// <summary>
    /// DPAPI roundtrip tests for <see cref="VisionSecretStore"/>. DPAPI is
    /// CurrentUser-scoped; these tests assume the test runner is the same
    /// user profile that would read the key in production (trivially true
    /// for a local test run).
    ///
    /// No RhinoCommon references — this class stays loadable in the bare
    /// xUnit host.
    /// </summary>
    public class VisionSecretStoreTests : IDisposable
    {
        private readonly string _tempDir;
        private readonly string _settingsPath;
        private readonly RookSettingsStore _settings;
        private readonly VisionSecretStore _store;

        public VisionSecretStoreTests()
        {
            _tempDir = Path.Combine(Path.GetTempPath(),
                "rook-vision-secrets-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(_tempDir);
            _settingsPath = Path.Combine(_tempDir, "settings.json");
            _settings = new RookSettingsStore(_settingsPath);
            _store = new VisionSecretStore(_settings);
        }

        public void Dispose()
        {
            try { Directory.Delete(_tempDir, recursive: true); } catch { }
        }

        [Fact]
        public void NoKey_GetReturnsNull()
        {
            Assert.Null(_store.GetGeminiApiKey());
            Assert.False(_store.HasGeminiApiKey());
        }

        [Fact]
        public void SetThenGet_RoundtripsPlaintext()
        {
            const string plaintext = "AIzaSyExample_KeyForTestsOnly_12345";
            _store.SetGeminiApiKey(plaintext);
            Assert.True(_store.HasGeminiApiKey());
            Assert.Equal(plaintext, _store.GetGeminiApiKey());
        }

        [Fact]
        public void SetWithEmpty_Throws()
        {
            Assert.Throws<ArgumentException>(() => _store.SetGeminiApiKey(""));
            Assert.Throws<ArgumentException>(() => _store.SetGeminiApiKey(null!));
        }

        [Fact]
        public void PersistedCiphertext_IsNotPlaintext()
        {
            const string plaintext = "verysecretkey-should-not-appear-in-file";
            _store.SetGeminiApiKey(plaintext);

            var fileContent = File.ReadAllText(_settingsPath);
            Assert.DoesNotContain(plaintext, fileContent);
        }

        [Fact]
        public void Clear_RemovesKey()
        {
            _store.SetGeminiApiKey("whatever");
            Assert.True(_store.HasGeminiApiKey());
            _store.ClearGeminiApiKey();
            Assert.False(_store.HasGeminiApiKey());
            Assert.Null(_store.GetGeminiApiKey());
        }

        [Fact]
        public void Clear_WhenEmpty_NoThrow()
        {
            _store.ClearGeminiApiKey();
            Assert.False(_store.HasGeminiApiKey());
        }

        [Fact]
        public void MalformedBase64_GetThrowsGenericMessage()
        {
            var section = new VisionSettings { GeminiApiKeyEncrypted = "not!valid@base64===" };
            _settings.SaveSection("vision", section);

            var ex = Assert.Throws<InvalidOperationException>(
                () => _store.GetGeminiApiKey());
            Assert.Contains("base64", ex.Message, StringComparison.OrdinalIgnoreCase);
            // The stored (malformed) value must not appear in the error.
            Assert.DoesNotContain("not!valid@base64", ex.Message);
        }

        [Fact]
        public void ValidBase64ButWrongCiphertext_GetThrowsGenericMessage()
        {
            // Valid base64 but not DPAPI-produced ciphertext — exercises
            // the CryptographicException catch.
            var bogus = Convert.ToBase64String(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 });
            var section = new VisionSettings { GeminiApiKeyEncrypted = bogus };
            _settings.SaveSection("vision", section);

            var ex = Assert.Throws<InvalidOperationException>(
                () => _store.GetGeminiApiKey());
            Assert.Contains("Unable to decrypt", ex.Message);
            // No raw exception detail must leak.
            Assert.DoesNotContain("CryptographicException", ex.Message);
        }

        [Fact]
        public void SetTwice_OverwritesExisting()
        {
            _store.SetGeminiApiKey("first");
            _store.SetGeminiApiKey("second");
            Assert.Equal("second", _store.GetGeminiApiKey());
        }

        // ─── API key preview (UI affordance) ────────────────────────────

        [Fact]
        public void Preview_NoKey_ReturnsNull()
        {
            Assert.Null(_store.GetApiKeyPreview());
        }

        [Fact]
        public void Preview_StoredOnSet_ReturnsTruncated()
        {
            // Arrange/Act
            _store.SetGeminiApiKey("AIzaSyExampleKeyForTesting-abcd1234");

            // Assert — first4…last4 shape
            var preview = _store.GetApiKeyPreview();
            Assert.NotNull(preview);
            Assert.StartsWith("AIza", preview);
            Assert.EndsWith("1234", preview);
            Assert.Contains("…", preview);
        }

        [Fact]
        public void Preview_IsPersistedInSettingsFile()
        {
            _store.SetGeminiApiKey("AIzaSyExampleKeyForTesting-abcd1234");

            var section = _settings.LoadSection<VisionSettings>("vision");
            Assert.NotNull(section);
            Assert.NotNull(section!.ApiKeyPreview);
            Assert.StartsWith("AIza", section.ApiKeyPreview);
            // The MIDDLE of the key must still not appear in the file.
            var fileContent = File.ReadAllText(_settingsPath);
            Assert.DoesNotContain("ExampleKey", fileContent);
        }

        [Fact]
        public void Preview_ShortKey_AllAsterisks()
        {
            // Keys <=8 chars get fully asterisked so we never echo the
            // bulk of a short credential. Defensive — real Gemini keys
            // are much longer; this guards against misuse.
            _store.SetGeminiApiKey("short");
            Assert.Equal("*****", _store.GetApiKeyPreview());
        }

        [Fact]
        public void Preview_ClearedOnClear()
        {
            _store.SetGeminiApiKey("AIzaSyExampleKeyForTesting-abcd1234");
            Assert.NotNull(_store.GetApiKeyPreview());

            _store.ClearGeminiApiKey();
            Assert.Null(_store.GetApiKeyPreview());
        }

        [Fact]
        public void Preview_RebuildOnReSave()
        {
            // User rotates the key — preview must reflect the new value,
            // not the first one that was saved.
            _store.SetGeminiApiKey("AIzaSyFirst--key---EndsHere1111");
            var first = _store.GetApiKeyPreview();
            _store.SetGeminiApiKey("AIzaSySecond-key---EndsHere2222");
            var second = _store.GetApiKeyPreview();

            Assert.NotEqual(first, second);
            Assert.EndsWith("1111", first);
            Assert.EndsWith("2222", second);
        }

        [Fact]
        public void Preview_LegacySettingsFile_ReturnsNull()
        {
            // A settings.json written by a previous companion build has
            // GeminiApiKeyEncrypted but no ApiKeyPreview. Reading must
            // return null (not throw); the UI falls back to the generic
            // "API key configured" placeholder, and the next save
            // rebuilds the preview field.
            var legacy = new VisionSettings
            {
                GeminiApiKeyEncrypted = "anything-looks-encrypted",
                ApiKeyPreview = null,
            };
            _settings.SaveSection("vision", legacy);

            Assert.Null(_store.GetApiKeyPreview());
            Assert.True(_store.HasGeminiApiKey());
        }
    }
}
