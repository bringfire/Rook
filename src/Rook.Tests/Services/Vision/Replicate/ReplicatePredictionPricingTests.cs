using System.Globalization;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicatePredictionPricingTests
    {
        [Fact]
        public void ExtractActualSpend_uses_predict_time_as_compute_second_quantity()
        {
            var body = JsonNode.Parse("""
                { "metrics": { "predict_time": 0.507, "total_time": 0.543 } }
                """)!;

            var pricing = ReplicatePredictionPricing.ExtractActualSpend(
                body,
                pricingSource: "replicate-predict-time-2026-04-30");

            Assert.NotNull(pricing);
            Assert.Equal("USD", pricing!.Currency);
            Assert.Null(pricing.UnitPrice);
            Assert.Equal("compute_second", pricing.Unit);
            Assert.Equal(0.507m, pricing.Quantity);
            Assert.Null(pricing.TotalUsd);
            Assert.Equal("replicate-predict-time-2026-04-30", pricing.PricingSource);
        }

        [Fact]
        public void ExtractTimingMetadata_preserves_predict_and_total_time()
        {
            var body = JsonNode.Parse("""
                { "metrics": { "predict_time": 0.507, "total_time": 0.543 } }
                """)!;

            var timing = ReplicatePredictionPricing.ExtractTimingMetadata(body);

            Assert.Equal(0.507m, timing.PredictTimeSeconds);
            Assert.Equal(0.543m, timing.TotalTimeSeconds);
        }

        [Fact]
        public void ExtractTimingMetadata_preserves_total_time_without_predict_time()
        {
            var body = JsonNode.Parse("""{ "metrics": { "total_time": 0.543 } }""")!;

            var timing = ReplicatePredictionPricing.ExtractTimingMetadata(body);

            Assert.Null(timing.PredictTimeSeconds);
            Assert.Equal(0.543m, timing.TotalTimeSeconds);
        }

        [Theory]
        [InlineData("""{ "metrics": { "total_time": 0.543 } }""")]
        [InlineData("""{ "metrics": { "predict_time": "not-a-number" } }""")]
        [InlineData("""{ "metrics": { "predict_time": -0.1 } }""")]
        public void ExtractActualSpend_returns_null_when_predict_time_missing_invalid_or_negative(
            string json)
        {
            var body = JsonNode.Parse(json)!;

            Assert.Null(ReplicatePredictionPricing.ExtractActualSpend(
                body,
                "replicate-predict-time-2026-04-30"));
        }

        [Fact]
        public void ExtractActualSpend_uses_invariant_culture()
        {
            var previousCulture = CultureInfo.CurrentCulture;
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("fr-FR");
            try
            {
                var body = JsonNode.Parse(
                    """{ "metrics": { "predict_time": 2.5 } }""")!;

                var pricing = ReplicatePredictionPricing.ExtractActualSpend(
                    body,
                    "replicate-predict-time-2026-04-30");

                Assert.NotNull(pricing);
                Assert.Equal(2.5m, pricing!.Quantity);
            }
            finally
            {
                CultureInfo.CurrentCulture = previousCulture;
            }
        }
    }
}
