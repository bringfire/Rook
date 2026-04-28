using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Body-pricing fake: <see cref="IPricingModel{TRequest, TCapability}.ExtractActualSpend"/>
    /// reads <c>metrics.predict_time</c> from response body and produces
    /// <see cref="JobPricing"/> with the per-second compute rate.
    ///
    /// Phase 0 evidence: Replicate exposes
    /// <c>metrics.predict_time</c> + <c>metrics.total_time</c> in the
    /// terminal poll body. Pricing is per-compute-second on declared
    /// hardware. Estimator <see cref="CostEstimate.IsExact"/> is false
    /// (depends on hardware contention).
    /// </summary>
    public class BodyPricingProviderFake
    {
        private sealed class ReplicateFluxPricing : IPricingModel<TestGenerationRequest, TestCapability>
        {
            public string PricingSource => "replicate-flux-per-compute-second-2026-04-27-stub";
            public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseBody;
            private const decimal PerSecondUsd = 0.000725m;    // declared-hardware stub

            public PricingResult Estimate(TestGenerationRequest request, TestCapability capability)
            {
                // Estimate is a range: 0.5–1.5s typical for FLUX schnell
                var pricing = new JobPricing(
                    Currency: "USD",
                    UnitPrice: PerSecondUsd,
                    Unit: "compute_second",
                    Quantity: 1.0m,
                    TotalUsd: PerSecondUsd,
                    PricingSource: PricingSource);
                var estimate = new CostEstimate(
                    Min: PerSecondUsd * 0.5m,
                    Max: PerSecondUsd * 1.5m,
                    IsExact: false,
                    Provenance: PricingSource);
                return PricingResult.Ok(pricing, estimate);
            }

            public JobPricing? ExtractActualSpend(
                IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
                JsonNode? responseBody)
            {
                if (responseBody is not JsonObject obj) return null;
                if (obj["metrics"] is not JsonObject metrics) return null;
                if (metrics["predict_time"] is not JsonValue v) return null;
                if (!v.TryGetValue<double>(out var predictTime)) return null;

                var quantity = (decimal)predictTime;
                return new JobPricing(
                    Currency: "USD",
                    UnitPrice: PerSecondUsd,
                    Unit: "compute_second",
                    Quantity: quantity,
                    TotalUsd: PerSecondUsd * quantity,
                    PricingSource: PricingSource);
            }
        }

        [Fact]
        public void Extracts_from_metrics_predict_time_body()
        {
            IPricingModel<TestGenerationRequest, TestCapability> pricing = new ReplicateFluxPricing();
            var body = new JsonObject
            {
                ["metrics"] = new JsonObject
                {
                    ["predict_time"] = 0.507,
                    ["total_time"] = 0.543,
                },
            };

            var actual = pricing.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                body);

            Assert.NotNull(actual);
            Assert.Equal("compute_second", actual!.Unit);
            Assert.Equal(0.507m, actual.Quantity);
        }

        [Fact]
        public void Returns_null_when_metrics_object_absent()
        {
            IPricingModel<TestGenerationRequest, TestCapability> pricing = new ReplicateFluxPricing();
            var body = new JsonObject { ["status"] = "succeeded" };

            var actual = pricing.ExtractActualSpend(
                new Dictionary<string, IReadOnlyList<string>>(),
                body);

            Assert.Null(actual);
        }

        [Fact]
        public void Estimate_reports_IsExact_false_with_min_lt_max()
        {
            IPricingModel<TestGenerationRequest, TestCapability> pricing = new ReplicateFluxPricing();
            var request = new TestGenerationRequest("flux-schnell", new TestProviderOptions());
            var capability = new TestCapability("flux-schnell", "FLUX schnell", "stable", new[] { "text_to_image" });

            var result = pricing.Estimate(request, capability);

            Assert.True(result.Success);
            Assert.False(result.Estimate!.IsExact);
            Assert.True(result.Estimate.Min < result.Estimate.Max);
        }
    }
}
