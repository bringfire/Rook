using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;
using GenerationPricingResult = Rook.Services.Vision.Generation.PricingResult;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Pricing math lifted from V1b's <c>VeoCostEstimatorTests</c>.
    /// Estimator orchestration moved to
    /// <see cref="VideoCostEstimatorTests"/>; these tests pin the
    /// per-second math + the typed failure on missing rates.
    /// </summary>
    public class PerSecondPricingModelTests
    {
        private static VideoCapability LiteCap =>
            VeoCapabilities.Models["veo-3.1-lite-generate-preview"].Capability;
        private static VideoCapability Full31Cap =>
            VeoCapabilities.Models["veo-3.1-generate-preview"].Capability;

        [Fact]
        public void Estimate_lite_720p_8s_returns_correct_per_second_pricing()
        {
            var pricing = new PerSecondPricingModel(
                ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.05m },
                pricingSource: "test-rate-card");
            var req = TestVideoFixtures.DefaultT2vRequest(
                resolution: "720p", duration: 8);

            var result = pricing.Estimate(req, LiteCap);

            Assert.True(result.Success);
            Assert.Equal(PricingKind.PerSecond, result.Pricing!.Kind);
            Assert.Equal("USD", result.Pricing.Currency);
            Assert.Equal(8, result.Pricing.Quantity);  // 8s × 1 video
            Assert.Equal(0.05m, result.Pricing.UnitPriceUsd);
            Assert.Equal(0.40m, result.Pricing.TotalUsd);
            Assert.Equal("test-rate-card", result.Pricing.PricingSource);
        }

        [Fact]
        public void Estimate_full_3_1_4k_8s_returns_correct_pricing()
        {
            var pricing = new PerSecondPricingModel(
                ratesPerSecondUsd: new Dictionary<string, decimal> { ["4k"] = 0.60m },
                pricingSource: "veo-rate-card-v1");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview", resolution: "4k", duration: 8);

            var result = pricing.Estimate(req, Full31Cap);

            Assert.True(result.Success);
            Assert.Equal(4.80m, result.Pricing!.TotalUsd);  // 0.60 × 8
        }

        [Fact]
        public void Estimate_returns_typed_failure_for_resolution_with_no_rate()
        {
            var pricing = new PerSecondPricingModel(
                ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.05m },
                pricingSource: "test-rate-card");
            // Cap accepts 1080p, but pricing-model has no rate for it.
            var req = TestVideoFixtures.DefaultT2vRequest(
                resolution: "1080p", duration: 8);

            var result = pricing.Estimate(req, LiteCap);

            Assert.False(result.Success);
            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.UnsupportedMedia, result.Error!.Code);
            Assert.Equal("Resolution", result.Error.Field);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public void Estimate_returns_typed_failure_for_null_request()
        {
            var pricing = new PerSecondPricingModel(
                ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.05m },
                pricingSource: "test-rate-card");

            var result = pricing.Estimate(request: null!, LiteCap);

            Assert.False(result.Success);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        [Fact]
        public void Estimate_returns_typed_failure_for_null_cap()
        {
            var pricing = new PerSecondPricingModel(
                ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.05m },
                pricingSource: "test-rate-card");

            var result = pricing.Estimate(
                TestVideoFixtures.DefaultT2vRequest(), cap: null!);

            Assert.False(result.Success);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        [Fact]
        public void Constructor_rejects_null_rates()
        {
            Assert.Throws<System.ArgumentNullException>(() =>
                new PerSecondPricingModel(
                    ratesPerSecondUsd: null!,
                    pricingSource: "x"));
        }

        [Fact]
        public void Constructor_rejects_empty_pricing_source()
        {
            Assert.Throws<System.ArgumentException>(() =>
                new PerSecondPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal>(),
                    pricingSource: "  "));
        }

        [Fact]
        public void Kind_property_returns_PerSecond()
        {
            var pricing = new PerSecondPricingModel(
                ratesPerSecondUsd: new Dictionary<string, decimal>(),
                pricingSource: "x");

            Assert.Equal(PricingKind.PerSecond, pricing.Kind);
        }

        [Fact]
        public void PricingSource_property_returns_constructor_value()
        {
            var pricing = new PerSecondPricingModel(
                ratesPerSecondUsd: new Dictionary<string, decimal>(),
                pricingSource: "veo-rate-card-v1");

            Assert.Equal("veo-rate-card-v1", pricing.PricingSource);
        }

        [Fact]
        public void PerSecondVideoPricingModel_implements_generic_pricing_seam()
        {
            IPricingModel<VideoGenerationRequest, VideoCapability> pricing =
                new PerSecondVideoPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.05m },
                    pricingSource: "test-rate-card");
            var req = TestVideoFixtures.DefaultT2vRequest(
                resolution: "720p", duration: 8);

            GenerationPricingResult result = pricing.Estimate(req, LiteCap);

            Assert.True(result.Success);
            Assert.Equal(PricingMetadataLocation.NotApplicable, pricing.MetadataLocation);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal(8m, result.Pricing.Quantity);
            Assert.Equal(0.05m, result.Pricing.UnitPrice);
            Assert.Equal("output_second", result.Pricing.Unit);
            Assert.Equal(0.40m, result.Pricing.TotalUsd);
            Assert.Equal(0.40m, result.Estimate!.Min);
            Assert.Equal(0.40m, result.Estimate.Max);
            Assert.True(result.Estimate.IsExact);
            Assert.Equal("test-rate-card", result.Estimate.Provenance);
        }

        [Fact]
        public void VideoJobPricingTranslator_converts_generic_per_second_pricing()
        {
            var generic = new Rook.Services.Vision.Generation.JobPricing(
                Currency: "USD",
                UnitPrice: 0.05m,
                Unit: "output_second",
                Quantity: 8m,
                TotalUsd: 0.40m,
                PricingSource: "test-rate-card");

            var video = VideoJobPricingTranslator.ToVideoJobPricing(
                generic,
                PricingKind.PerSecond);

            Assert.Equal(PricingKind.PerSecond, video.Kind);
            Assert.Equal("USD", video.Currency);
            Assert.Equal(8, video.Quantity);
            Assert.Equal(0.05m, video.UnitPriceUsd);
            Assert.Equal(0.40m, video.TotalUsd);
            Assert.Equal("test-rate-card", video.PricingSource);
        }
    }
}
