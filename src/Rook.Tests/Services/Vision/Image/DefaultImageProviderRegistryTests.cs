using System;
using System.Collections.Generic;
using System.Linq;
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

        private static DefaultImageProviderRegistry RegistryWithGemini()
            => new(new IImageProviderRegistration[]
            {
                new GeminiImageProviderRegistration(
                    new GeminiImageProvider(() => "test-key")),
            });
    }
}
