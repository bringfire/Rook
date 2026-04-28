using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Header-pricing fake: <see cref="IPricingModel{TRequest, TCapability}.ExtractActualSpend"/>
    /// reads <c>x-fal-billable-units</c> from response headers and
    /// produces <see cref="JobPricing"/> with the per-model unit rate.
    ///
    /// Phase 0 evidence: fal alone uses three different per-unit rates
    /// for the same header (<c>$0.003/MP</c>, <c>$0.10/output-second</c>,
    /// <c>$0.015/per-call-unit</c>). The header is not a portable cost
    /// signal — the per-model pricing model owns interpretation.
    /// </summary>
    public class HeaderPricingProviderFake
    {
        // Per-model rate stub: $0.003 per megapixel for fal FLUX schnell
        private sealed class FalFluxSchnellPricing : IPricingModel<TestGenerationRequest, TestCapability>
        {
            public string PricingSource => "fal-flux-schnell-per-mp-2026-04-27";
            public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseHeader;
            private const decimal PerMpUsd = 0.003m;

            public PricingResult Estimate(TestGenerationRequest request, TestCapability capability)
            {
                // Estimate at submit time: assume 1 MP for shape demo
                var pricing = new JobPricing(
                    Currency: "USD",
                    UnitPrice: PerMpUsd,
                    Unit: "megapixel",
                    Quantity: 1.0m,
                    TotalUsd: PerMpUsd,
                    PricingSource: PricingSource);
                var estimate = new CostEstimate(
                    Min: PerMpUsd, Max: PerMpUsd, IsExact: true, Provenance: PricingSource);
                return PricingResult.Ok(pricing, estimate);
            }

            public JobPricing? ExtractActualSpend(
                IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
                JsonNode? responseBody)
            {
                // HTTP headers are case-insensitive (RFC 7230 §3.2).
                // Provider pricing implementations must not rely on the
                // caller's dictionary comparer; do a case-insensitive
                // lookup explicitly so the contract works whether the
                // headers come from HttpClient (case-insensitive) or
                // from a test fixture using a default Dictionary.
                IReadOnlyList<string>? values = null;
                foreach (var kvp in responseHeaders)
                {
                    if (string.Equals(kvp.Key, "x-fal-billable-units",
                        StringComparison.OrdinalIgnoreCase))
                    {
                        values = kvp.Value;
                        break;
                    }
                }
                if (values is null || values.Count == 0
                    || !decimal.TryParse(values[0], out var units))
                {
                    return null;
                }

                return new JobPricing(
                    Currency: "USD",
                    UnitPrice: PerMpUsd,
                    Unit: "megapixel",
                    Quantity: units,
                    TotalUsd: PerMpUsd * units,
                    PricingSource: PricingSource);
            }
        }

        [Fact]
        public void Extracts_from_x_fal_billable_units_header()
        {
            IPricingModel<TestGenerationRequest, TestCapability> pricing = new FalFluxSchnellPricing();
            var headers = new Dictionary<string, IReadOnlyList<string>>
            {
                ["x-fal-billable-units"] = new[] { "2.0" },
                ["content-type"] = new[] { "application/json" },
            };

            var actual = pricing.ExtractActualSpend(headers, responseBody: null);

            Assert.NotNull(actual);
            Assert.Equal("megapixel", actual!.Unit);
            Assert.Equal(2.0m, actual.Quantity);
            Assert.Equal(0.006m, actual.TotalUsd);
        }

        [Theory]
        [InlineData("x-fal-billable-units")]
        [InlineData("X-FAL-Billable-Units")]
        [InlineData("X-Fal-Billable-Units")]
        [InlineData("X-FAL-BILLABLE-UNITS")]
        public void Header_lookup_is_case_insensitive(string headerName)
        {
            IPricingModel<TestGenerationRequest, TestCapability> pricing = new FalFluxSchnellPricing();
            var headers = new Dictionary<string, IReadOnlyList<string>>
            {
                [headerName] = new[] { "1.5" },
            };

            var actual = pricing.ExtractActualSpend(headers, responseBody: null);

            Assert.NotNull(actual);
            Assert.Equal(1.5m, actual!.Quantity);
        }

        [Fact]
        public void Returns_null_when_header_absent()
        {
            IPricingModel<TestGenerationRequest, TestCapability> pricing = new FalFluxSchnellPricing();
            var headers = new Dictionary<string, IReadOnlyList<string>>
            {
                ["content-type"] = new[] { "application/json" },
            };

            var actual = pricing.ExtractActualSpend(headers, responseBody: null);

            Assert.Null(actual);
        }

        [Fact]
        public void Estimate_reports_IsExact_true_for_per_mp_pricing()
        {
            IPricingModel<TestGenerationRequest, TestCapability> pricing = new FalFluxSchnellPricing();
            var request = new TestGenerationRequest("flux-schnell", new TestProviderOptions());
            var capability = new TestCapability("flux-schnell", "FLUX schnell", "stable", new[] { "text_to_image" });

            var result = pricing.Estimate(request, capability);

            Assert.True(result.Success);
            Assert.True(result.Estimate!.IsExact);
            Assert.Equal(result.Estimate.Min, result.Estimate.Max);
        }
    }
}
