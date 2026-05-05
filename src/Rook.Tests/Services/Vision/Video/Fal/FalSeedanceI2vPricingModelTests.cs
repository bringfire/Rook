using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalSeedanceI2vPricingModelTests
    {
        [Fact]
        public void Estimate_prices_i2v_720p_request_per_output_second()
        {
            var model = new FalSeedanceI2vPricingModel();
            var request = new VideoGenerationRequest(
                Model: FalVideoCapabilities.SeedanceI2v,
                Mode: VideoMode.I2V,
                DurationSeconds: 6,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "clip",
                StartFrame: MediaRef.ForArtifact(
                    Guid.Parse("11111111-1111-1111-1111-111111111111"),
                    "image"),
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

            var result = model.Estimate(
                request,
                FalVideoCapabilities.Models[FalVideoCapabilities.SeedanceI2v].Capability);

            Assert.True(result.Success);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal("output_second", result.Pricing.Unit);
            Assert.Equal(6m, result.Pricing.Quantity);
            Assert.Equal(0.3024m, result.Pricing.UnitPrice);
            Assert.Equal(1.8144m, result.Pricing.TotalUsd);
            Assert.Equal(FalSeedanceI2vPricingModel.Source, result.Pricing.PricingSource);
            Assert.False(result.Estimate!.IsExact);
            Assert.Equal(FalSeedanceI2vPricingModel.Source, result.Estimate.Provenance);
        }

        [Fact]
        public void ExtractActualSpend_returns_null()
        {
            var model = new FalSeedanceI2vPricingModel();

            Assert.Null(model.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                responseBody: null));
        }
    }
}
