using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Replicate
{
    public static class ReplicatePredictionPricing
    {
        public static JobPricing? ExtractActualSpend(
            JsonNode predictionBody,
            string pricingSource)
        {
            var timing = ExtractTimingMetadata(predictionBody);
            if (timing.PredictTimeSeconds is not decimal predictTime
                || predictTime < 0m)
            {
                return null;
            }

            return new JobPricing(
                Currency: "USD",
                UnitPrice: null,
                Unit: "compute_second",
                Quantity: predictTime,
                TotalUsd: null,
                PricingSource: pricingSource);
        }

        public static ReplicateTimingMetadata ExtractTimingMetadata(
            JsonNode predictionBody)
        {
            if (predictionBody is not JsonObject root
                || root["metrics"] is not JsonObject metrics)
            {
                return new ReplicateTimingMetadata(null, null);
            }

            return new ReplicateTimingMetadata(
                TryGetDecimal(metrics["predict_time"]),
                TryGetDecimal(metrics["total_time"]));
        }

        private static decimal? TryGetDecimal(JsonNode? node)
        {
            if (node is null)
                return null;

            try
            {
                return node.GetValue<decimal>();
            }
            catch (InvalidOperationException)
            {
                return null;
            }
            catch (FormatException)
            {
                return null;
            }
        }
    }

    public sealed class ReplicateTimingMetadata
    {
        public ReplicateTimingMetadata(decimal? predictTimeSeconds, decimal? totalTimeSeconds)
        {
            PredictTimeSeconds = predictTimeSeconds;
            TotalTimeSeconds = totalTimeSeconds;
        }

        public decimal? PredictTimeSeconds { get; }
        public decimal? TotalTimeSeconds { get; }
    }
}
