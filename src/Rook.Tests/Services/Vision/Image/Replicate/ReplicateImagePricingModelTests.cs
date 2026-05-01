using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImagePricingModelTests
    {
        private readonly ReplicateImagePricingModel _pricing = new();

        [Fact]
        public void PricingSource_IsDateStampedAndModelSpecific()
        {
            Assert.Equal(ReplicateImagePricingModel.Source, _pricing.PricingSource);
        }

        [Fact]
        public void MetadataLocation_IsResponseBody()
        {
            Assert.Equal(PricingMetadataLocation.ResponseBody, _pricing.MetadataLocation);
        }

        [Fact]
        public void Estimate_ValidRequest_ReturnsUnknownComputeSecondResult()
        {
            var result = _pricing.Estimate(Request(), Capability());

            Assert.True(result.Success);
            Assert.NotNull(result.Pricing);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Null(result.Pricing.UnitPrice);
            Assert.Equal("compute_second", result.Pricing.Unit);
            Assert.Null(result.Pricing.Quantity);
            Assert.Null(result.Pricing.TotalUsd);
            Assert.Equal(ReplicateImagePricingModel.Source, result.Pricing.PricingSource);
            Assert.NotNull(result.Estimate);
            Assert.Equal(0m, result.Estimate!.Min);
            Assert.Equal(0m, result.Estimate.Max);
            Assert.False(result.Estimate.IsExact);
            Assert.Equal(ReplicateImagePricingModel.Provenance, result.Estimate.Provenance);
        }

        [Fact]
        public void Estimate_NullRequest_FailsInvalidRequest()
        {
            var result = _pricing.Estimate(null!, Capability());

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error?.Code);
            Assert.Equal("request", result.Error?.Field);
            Assert.False(result.Error?.Retryable);
        }

        [Fact]
        public void ExtractActualSpend_NullResponseBody_ReturnsNull()
        {
            var result = _pricing.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                responseBody: null);

            Assert.Null(result);
        }

        [Fact]
        public void ExtractActualSpend_ParsesPredictTimeFromResponseBody()
        {
            var body = JsonNode.Parse(
                """{ "metrics": { "predict_time": 0.507, "total_time": 0.543 } }""")!;

            var result = _pricing.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                body);

            Assert.NotNull(result);
            Assert.Equal("USD", result!.Currency);
            Assert.Null(result.UnitPrice);
            Assert.Equal("compute_second", result.Unit);
            Assert.Equal(0.507m, result.Quantity);
            Assert.Null(result.TotalUsd);
            Assert.Equal(ReplicateImagePricingModel.Source, result.PricingSource);
        }

        private static ImageGenerationRequest Request()
            => new(
                Model: ReplicateImageCapabilities.FluxSchnell,
                Prompt: "test prompt",
                Resolution: "1K",
                AspectRatio: "1:1",
                NumberOfImages: 1,
                ReferenceImages: null,
                Options: new ReplicateImageOptions());

        private static ImageCapability Capability()
            => ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell];
    }
}
