using System;
using Rook.Services.Vision.Generation;

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
