using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class GeminiImagePricingModelTests
    {
        [Fact]
        public void Estimate_returns_non_exact_stub_with_audit_pricing()
        {
            var model = new GeminiImagePricingModel();
            var request = new ImageGenerationRequest(
                Model: GeminiImageCapabilities.NanoBanana2,
                Prompt: "render a facade",
                Resolution: "1K",
                AspectRatio: "1:1",
                NumberOfImages: 1,
                ReferenceImages: null,
                Options: new GeminiImageOptions());

            var result = model.Estimate(
                request,
                GeminiImageCapabilities.Models[GeminiImageCapabilities.NanoBanana2]);

            Assert.True(result.Success);
            Assert.Equal("gemini-per-token-by-modality-stub", model.PricingSource);
            Assert.Equal(Rook.Services.Vision.Generation.PricingMetadataLocation.ResponseBody, model.MetadataLocation);
            Assert.False(result.Estimate!.IsExact);
            Assert.Contains("stub", result.Estimate.Provenance);
            Assert.Equal(0m, result.Estimate.Min);
            Assert.Equal(0m, result.Estimate.Max);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal("gemini-per-token-by-modality-stub", result.Pricing.PricingSource);
        }

        [Fact]
        public void ExtractActualSpend_reads_usage_metadata_token_counts()
        {
            var model = new GeminiImagePricingModel();
            var usage = new JsonObject
            {
                ["usageMetadata"] = new JsonObject
                {
                    ["promptTokenCount"] = 12,
                    ["candidatesTokenCount"] = 1290,
                },
            };

            var pricing = model.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                usage);

            Assert.NotNull(pricing);
            Assert.Equal("token", pricing!.Unit);
            Assert.Equal(1302m, pricing.Quantity);
            Assert.Equal(0m, pricing.TotalUsd);
            Assert.Equal("gemini-per-token-by-modality-stub", pricing.PricingSource);
        }
    }
}
