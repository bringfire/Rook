using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalWanT2vPricingModelTests
    {
        [Fact]
        public void Estimate_prices_duration_at_ten_cents_per_second()
        {
            var model = new FalWanT2vPricingModel();
            var request = new VideoGenerationRequest(
                Model: FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "clip",
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

            var result = model.Estimate(
                request,
                FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability);

            Assert.True(result.Success);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal(0.10m, result.Pricing.UnitPrice);
            Assert.Equal("output_second", result.Pricing.Unit);
            Assert.Equal(2m, result.Pricing.Quantity);
            Assert.Equal(0.20m, result.Pricing.TotalUsd);
            Assert.True(result.Estimate!.IsExact);
            Assert.Equal(FalWanT2vPricingModel.Source, result.Pricing.PricingSource);
        }

        [Fact]
        public void Pricing_model_classifies_as_per_second()
        {
            Assert.Equal(
                PricingKind.PerSecond,
                VideoJobPricingTranslator.PricingKindFor(new FalWanT2vPricingModel()));
        }
    }
}
