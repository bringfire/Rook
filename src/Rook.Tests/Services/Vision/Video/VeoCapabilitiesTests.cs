using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// V1c-slim: <see cref="VeoCapabilities"/> is now a pure data table.
    /// Validation logic moved to <see cref="CapabilityValidator"/> +
    /// <see cref="VeoOptionsCodec"/>; pricing math moved to
    /// <see cref="PerSecondPricingModel"/>. These tests pin the data
    /// shape and the per-model pricing source.
    /// </summary>
    public class VeoCapabilitiesTests
    {
        [Fact]
        public void Models_dictionary_contains_all_six_documented_veo_ids()
        {
            Assert.Equal(6, VeoCapabilities.Models.Count);
            Assert.Contains("veo-3.1-generate-preview", VeoCapabilities.Models.Keys);
            Assert.Contains("veo-3.1-fast-generate-preview", VeoCapabilities.Models.Keys);
            Assert.Contains("veo-3.1-lite-generate-preview", VeoCapabilities.Models.Keys);
            Assert.Contains("veo-3.0-generate-001", VeoCapabilities.Models.Keys);
            Assert.Contains("veo-3.0-fast-generate-001", VeoCapabilities.Models.Keys);
            Assert.Contains("veo-2.0-generate-001", VeoCapabilities.Models.Keys);
        }

        [Fact]
        public void DefaultModelId_resolves_to_a_registered_model()
        {
            Assert.True(VeoCapabilities.Models.ContainsKey(VeoCapabilities.DefaultModelId));
        }

        [Fact]
        public void ProviderName_is_veo()
        {
            // Guardrail #3: Veo provider name is byte-pinned. Drift here
            // breaks every fixture-based bit-identity test.
            Assert.Equal("veo", VeoCapabilities.ProviderName);
        }

        [Fact]
        public void PricingSource_is_veo_rate_card_v1()
        {
            // The pricing-source string is persisted in every JobPricing
            // for Veo models. Drift would corrupt the audit trail.
            Assert.Equal("veo-rate-card-v1", VeoCapabilities.PricingSource);
        }

        [Theory]
        [InlineData("veo-3.1-generate-preview", PricingKind.PerSecond, "veo-rate-card-v1")]
        [InlineData("veo-3.1-fast-generate-preview", PricingKind.PerSecond, "veo-rate-card-v1")]
        [InlineData("veo-3.1-lite-generate-preview", PricingKind.PerSecond, "veo-rate-card-v1")]
        [InlineData("veo-3.0-generate-001", PricingKind.PerSecond, "veo-rate-card-v1")]
        [InlineData("veo-3.0-fast-generate-001", PricingKind.PerSecond, "veo-rate-card-v1")]
        [InlineData("veo-2.0-generate-001", PricingKind.PerSecond, "veo-rate-card-v1")]
        public void Each_model_has_per_second_pricing_with_unified_source(
            string modelId, PricingKind expectedKind, string expectedSource)
        {
            var (_, pricing) = VeoCapabilities.Models[modelId];
            Assert.Equal(expectedKind, VideoJobPricingTranslator.PricingKindFor(pricing));
            Assert.Equal(expectedSource, pricing.PricingSource);
        }

        [Fact]
        public void Lite_model_does_not_support_reference_images()
        {
            var (cap, _) = VeoCapabilities.Models["veo-3.1-lite-generate-preview"];
            Assert.False(cap.SupportsReferenceImages);
            Assert.Equal(0, cap.MaxReferenceImages);
        }

        [Fact]
        public void Full_3_1_supports_reference_images_max_three()
        {
            var (cap, _) = VeoCapabilities.Models["veo-3.1-generate-preview"];
            Assert.True(cap.SupportsReferenceImages);
            Assert.Equal(3, cap.MaxReferenceImages);
        }

        [Fact]
        public void Veo2_only_supports_720p()
        {
            var (cap, _) = VeoCapabilities.Models["veo-2.0-generate-001"];
            Assert.Single(cap.Resolutions);
            Assert.Contains("720p", cap.Resolutions);
        }
    }
}
