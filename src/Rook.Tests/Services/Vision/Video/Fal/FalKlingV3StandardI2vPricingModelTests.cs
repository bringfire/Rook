using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalKlingV3StandardI2vPricingModelTests
    {
        [Fact]
        public void Estimate_prices_audio_off_output_seconds()
        {
            var model = new FalKlingV3StandardI2vPricingModel();
            var request = new VideoGenerationRequest(
                Model: FalVideoCapabilities.KlingV3StandardI2v,
                Mode: VideoMode.I2V,
                DurationSeconds: 5,
                Resolution: "auto",
                AspectRatio: "auto",
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
                FalVideoCapabilities.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability);

            Assert.True(result.Success);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal("output_second", result.Pricing.Unit);
            Assert.Equal(5m, result.Pricing.Quantity);
            Assert.Equal(0.084m, result.Pricing.UnitPrice);
            Assert.Equal(0.420m, result.Pricing.TotalUsd);
            Assert.Equal(FalKlingV3StandardI2vPricingModel.Source, result.Pricing.PricingSource);
            Assert.False(result.Estimate!.IsExact);
            Assert.Equal(FalKlingV3StandardI2vPricingModel.Source, result.Estimate.Provenance);
        }

        [Fact]
        public void Estimate_rejects_null_request()
        {
            var model = new FalKlingV3StandardI2vPricingModel();

            var result = model.Estimate(
                null!,
                new VideoCapability(
                    Id: FalVideoCapabilities.KlingV3StandardI2v,
                    Name: "Kling v3 Standard Image to Video",
                    Status: "preview",
                    Resolutions: new[] { "auto" },
                    Durations: new[] { 5 },
                    AspectRatios: new[] { "auto" },
                    Modes: new[] { VideoMode.I2V },
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>()));

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal("request", result.Error.Field);
        }

        [Fact]
        public void ExtractActualSpend_returns_null()
        {
            var model = new FalKlingV3StandardI2vPricingModel();

            Assert.Null(model.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                responseBody: null));
        }
    }
}
