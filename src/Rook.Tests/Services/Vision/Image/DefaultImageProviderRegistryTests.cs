using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class DefaultImageProviderRegistryTests
    {
        [Fact]
        public void TryResolve_exact_model_id_returns_resolved_image_model()
        {
            var registry = RegistryWithGemini();

            var ok = registry.TryResolve(GeminiImageCapabilities.NanoBanana2, out var model);

            Assert.True(ok);
            Assert.Equal(GeminiImageCapabilities.NanoBanana2, model.ModelId);
            Assert.Equal(GeminiImageCapabilities.ProviderName, model.ProviderName);
            Assert.Equal("image", model.Capability.Modality);
            Assert.True(model.Capability.SupportsTextToImage);
            Assert.True(model.Capability.SupportsImageToImage);
            Assert.NotNull(model.Provider);
            Assert.NotNull(model.PricingModel);
            Assert.NotNull(model.OptionsCodec);
        }

        [Fact]
        public void TryResolve_unknown_model_returns_false()
        {
            var registry = RegistryWithGemini();

            Assert.False(registry.TryResolve("gemini-does-not-exist", out _));
        }

        [Fact]
        public void EnumerateAllModels_pins_gemini_order()
        {
            var registry = RegistryWithGemini();

            var ids = registry.EnumerateAllModels().Select(m => m.ModelId).ToArray();

            Assert.Equal(new[]
            {
                GeminiImageCapabilities.NanoBanana2,
                GeminiImageCapabilities.NanoBananaPro,
            }, ids);
        }

        [Fact]
        public void Resolved_and_described_gemini_models_are_sync_submission_mode()
        {
            var registry = RegistryWithGemini();

            Assert.True(registry.TryResolve(GeminiImageCapabilities.NanoBanana2, out var resolved));
            Assert.Equal(ImageSubmissionMode.Sync, resolved.SubmissionMode);

            var descriptor = Assert.Single(
                registry.EnumerateAllModels(),
                m => m.ModelId == GeminiImageCapabilities.NanoBanana2);
            Assert.Equal(ImageSubmissionMode.Sync, descriptor.SubmissionMode);
        }

        [Fact]
        public void Gemini_registration_declares_gemini_secret_requirement()
        {
            var registration = new GeminiImageProviderRegistration(
                new GeminiImageProvider(() => "key"));

            var requirement = Assert.Single(registration.SecretRequirements);
            Assert.Equal(GenerationSecretKeys.GeminiApiKey, requirement.Key);
            Assert.Equal("Gemini API key", requirement.DisplayName);
            Assert.True(requirement.IsRequired);
            Assert.True(requirement.IsSensitive);
        }

        [Fact]
        public void Constructor_throws_on_duplicate_model_id()
        {
            var first = new GeminiImageProviderRegistration(
                new GeminiImageProvider(() => "key"));
            var second = new GeminiImageProviderRegistration(
                new GeminiImageProvider(() => "key"));

            var ex = Assert.Throws<InvalidOperationException>(() =>
                new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                {
                    first,
                    second,
                }));

            Assert.Contains("Duplicate model id", ex.Message);
            Assert.Contains(GeminiImageCapabilities.NanoBanana2, ex.Message);
        }

        [Fact]
        public void Registration_can_expose_mixed_submission_modes_per_model()
        {
            var provider = new FakeImageProvider("mixed");
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new MixedModeRegistration(provider),
            });

            Assert.True(registry.TryResolve("mixed-sync", out var sync));
            Assert.True(registry.TryResolve("mixed-async", out var async));
            Assert.Equal(ImageSubmissionMode.Sync, sync.SubmissionMode);
            Assert.Equal(ImageSubmissionMode.AsyncImageJob, async.SubmissionMode);

            var descriptors = registry.EnumerateAllModels();
            Assert.Equal(
                ImageSubmissionMode.Sync,
                Assert.Single(descriptors, m => m.ModelId == "mixed-sync").SubmissionMode);
            Assert.Equal(
                ImageSubmissionMode.AsyncImageJob,
                Assert.Single(descriptors, m => m.ModelId == "mixed-async").SubmissionMode);
        }

        private static DefaultImageProviderRegistry RegistryWithGemini()
            => new(new IImageProviderRegistration[]
            {
                new GeminiImageProviderRegistration(
                    new GeminiImageProvider(() => "test-key")),
            });

        private sealed class MixedModeRegistration
            : IImageProviderRegistration, IImageModelSubmissionModeRegistration
        {
            public MixedModeRegistration(IImageProvider provider)
            {
                Provider = provider;
            }

            public string ProviderName => "mixed";
            public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
            public IImageProvider Provider { get; }
            public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
                = new FakeOptionsCodec();
            public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; } =
                Array.Empty<ProviderSecretRequirement>();

            public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models { get; }
                = new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal)
                {
                    ["mixed-sync"] = (
                        new ImageCapability(
                            "mixed-sync",
                            "Mixed Sync",
                            "available",
                            new[] { "1K" },
                            new[] { "1:1" },
                            0,
                            true,
                            true),
                        new FakePricingModel()),
                    ["mixed-async"] = (
                        new ImageCapability(
                            "mixed-async",
                            "Mixed Async",
                            "available",
                            new[] { "auto" },
                            new[] { "match_input_image" },
                            0,
                            true,
                            false),
                        new FakePricingModel()),
                };

            public ImageSubmissionMode GetSubmissionMode(string modelId) =>
                string.Equals(modelId, "mixed-async", StringComparison.Ordinal)
                    ? ImageSubmissionMode.AsyncImageJob
                    : ImageSubmissionMode.Sync;
        }

        private sealed class FakeOptionsCodec
            : IProviderOptionsCodec<ImageGenerationRequest, ImageCapability>
        {
            public ValidationResult Validate(
                ImageGenerationRequest request,
                ProviderOptions options,
                ImageCapability capability) => ValidationResult.Ok();

            public JsonObject Serialize(ProviderOptions options) => new();

            public ProviderOptionsDecodeResult Deserialize(JsonObject json) =>
                ProviderOptionsDecodeResult.Ok(new GeminiImageOptions());
        }

        private sealed class FakePricingModel
            : IPricingModel<ImageGenerationRequest, ImageCapability>
        {
            public string PricingSource => "fake";
            public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

            public PricingResult Estimate(
                ImageGenerationRequest request,
                ImageCapability capability) =>
                PricingResult.Ok(
                    new JobPricing(
                        "USD",
                        0m,
                        "call",
                        1m,
                        0m,
                        "fake"),
                    new CostEstimate(0m, 0m, false, "fake-test"));

            public JobPricing? ExtractActualSpend(
                IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
                JsonNode? responseBody) => null;
        }

        private sealed class FakeImageProvider : IImageProvider
        {
            public FakeImageProvider(string providerName)
            {
                ProviderName = providerName;
            }

            public string ProviderName { get; }

            public Task<ProviderSubmitOutcome> SubmitAsync(
                ImageGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct) =>
                throw new NotImplementedException();

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotImplementedException();

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotImplementedException();

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotImplementedException();
        }
    }
}
