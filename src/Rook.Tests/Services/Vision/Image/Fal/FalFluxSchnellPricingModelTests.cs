using System.Collections.Generic;
using System.Globalization;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Fal
{
    public sealed class FalFluxSchnellPricingModelTests
    {
        private readonly FalFluxSchnellPricingModel _pricing = new();

        [Fact]
        public void PricingSource_IsDateStampedAndModelSpecific()
        {
            Assert.Equal(
                "fal-ai/flux/schnell-megapixel-2026-04-29",
                _pricing.PricingSource);
        }

        [Fact]
        public void MetadataLocation_IsResponseHeader()
        {
            Assert.Equal(PricingMetadataLocation.ResponseHeader, _pricing.MetadataLocation);
        }

        [Fact]
        public void Estimate_ValidRequest_ReturnsNonExactBoundedResult()
        {
            var result = _pricing.Estimate(Request(), Capability());

            Assert.True(result.Success);
            Assert.NotNull(result.Pricing);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal(0.003m, result.Pricing.UnitPrice);
            Assert.Equal("megapixel", result.Pricing.Unit);
            Assert.Null(result.Pricing.Quantity);
            Assert.Null(result.Pricing.TotalUsd);
            Assert.Equal(FalFluxSchnellPricingModel.Source, result.Pricing.PricingSource);
            Assert.NotNull(result.Estimate);
            Assert.Equal(0.003m, result.Estimate!.Min);
            Assert.Equal(0.006m, result.Estimate.Max);
            Assert.False(result.Estimate.IsExact);
            Assert.Equal(FalFluxSchnellPricingModel.Provenance, result.Estimate.Provenance);
        }

        [Fact]
        public void Estimate_NullRequest_FailsInvalidRequest()
        {
            var result = _pricing.Estimate(null!, Capability());

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error?.Code);
            Assert.Equal("request", result.Error?.Field);
        }

        [Fact]
        public void ExtractActualSpend_MissingBillableUnits_ReturnsNull()
        {
            var result = _pricing.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                responseBody: null);

            Assert.Null(result);
        }

        [Theory]
        [InlineData("not-a-number")]
        [InlineData("-1")]
        public void ExtractActualSpend_InvalidOrNegativeBillableUnits_ReturnsNull(
            string units)
        {
            var result = _pricing.ExtractActualSpend(
                Headers(units),
                responseBody: null);

            Assert.Null(result);
        }

        [Fact]
        public void ExtractActualSpend_ParsesBillableUnitsWithInvariantCulture()
        {
            var previousCulture = CultureInfo.CurrentCulture;
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("fr-FR");
            try
            {
                var result = _pricing.ExtractActualSpend(
                    Headers("2.5"),
                    responseBody: null);

                Assert.NotNull(result);
                Assert.Equal(2.5m, result!.Quantity);
            }
            finally
            {
                CultureInfo.CurrentCulture = previousCulture;
            }
        }

        [Fact]
        public void ExtractActualSpend_MultipliesUnitsByUnitPrice()
        {
            var result = _pricing.ExtractActualSpend(
                Headers("2.5"),
                responseBody: null);

            Assert.NotNull(result);
            Assert.Equal("USD", result!.Currency);
            Assert.Equal(0.003m, result.UnitPrice);
            Assert.Equal("megapixel", result.Unit);
            Assert.Equal(2.5m, result.Quantity);
            Assert.Equal(0.0075m, result.TotalUsd);
            Assert.Equal(FalFluxSchnellPricingModel.Source, result.PricingSource);
        }

        private static ImageGenerationRequest Request()
            => new(
                Model: FalImageCapabilities.FluxSchnell,
                Prompt: "test prompt",
                Resolution: "1K",
                AspectRatio: "4:3",
                NumberOfImages: 1,
                ReferenceImages: null,
                Options: new FalImageOptions());

        private static ImageCapability Capability()
            => FalImageCapabilities.Models[FalImageCapabilities.FluxSchnell];

        private static Dictionary<string, IReadOnlyList<string>> Headers(string value)
            => new()
            {
                ["x-fal-billable-units"] = new[] { value },
            };
    }
}
