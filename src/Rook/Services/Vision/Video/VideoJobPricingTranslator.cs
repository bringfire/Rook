using System;
using Rook.Services.Vision.Generation;
using GenerationPricingResult = Rook.Services.Vision.Generation.PricingResult;
using VideoPricingResult = Rook.Services.Vision.Video.PricingResult;

namespace Rook.Services.Vision.Video
{
    internal static class VideoJobPricingTranslator
    {
        public static JobPricing ToVideoJobPricing(
            Rook.Services.Vision.Generation.JobPricing pricing,
            PricingKind kind)
        {
            if (pricing is null) throw new ArgumentNullException(nameof(pricing));

            return new JobPricing(
                Kind: kind,
                Currency: pricing.Currency,
                Quantity: ToIntQuantity(pricing.Quantity),
                UnitPriceUsd: pricing.UnitPrice,
                TotalUsd: pricing.TotalUsd,
                PricingSource: pricing.PricingSource);
        }

        public static VideoPricingResult ToVideoPricingResult(
            GenerationPricingResult result,
            PricingKind kind)
        {
            if (result is null) throw new ArgumentNullException(nameof(result));

            if (result.Error is not null)
                return VideoPricingResult.Fail(
                    VideoProviderOutcomeAdapters.ToVideoJobError(result.Error));

            return VideoPricingResult.Ok(
                ToVideoJobPricing(result.Pricing!, kind));
        }

        public static PricingKind PricingKindFor(
            Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability> model)
        {
            if (model is null) throw new ArgumentNullException(nameof(model));

            return model switch
            {
                PerSecondVideoPricingModel => PricingKind.PerSecond,
                _ => PricingKind.External,
            };
        }

        private static int ToIntQuantity(decimal? quantity)
        {
            if (quantity is null)
                return 0;

            if (quantity.Value != decimal.Truncate(quantity.Value))
                throw new InvalidOperationException(
                    $"Video pricing quantity must be an integer; got {quantity.Value}.");

            if (quantity.Value > int.MaxValue)
                throw new InvalidOperationException(
                    $"Video pricing quantity exceeds Int32.MaxValue; got {quantity.Value}.");

            return (int)quantity.Value;
        }
    }
}
