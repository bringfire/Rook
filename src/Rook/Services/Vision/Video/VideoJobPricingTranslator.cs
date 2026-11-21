using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Fal;

namespace Rook.Services.Vision.Video
{
    internal static class VideoJobPricingTranslator
    {
        internal static JobPricing FromConfigured(Rook.Services.Vision.Fal.Models.FalPricingSnapshot p)
        {
            bool integerQuantity = p.QuantityMin == p.QuantityMax && p.QuantityMax == decimal.Truncate(p.QuantityMax) && p.QuantityMax <= int.MaxValue;
            bool preciseRate = p.RateUsd <= 1000000000m && p.RateUsd == decimal.Round(p.RateUsd, 6);
            bool perSecond = p.Unit == "second" && integerQuantity && preciseRate;
            return new JobPricing(perSecond ? PricingKind.PerSecond : PricingKind.External, "USD", integerQuantity ? (int)p.QuantityMax : 0,
                perSecond ? p.RateUsd : null, Rook.Services.Vision.Fal.Models.FalQuote.PublicCeiling(p.EstimateMaxUsd), p.Source);
        }
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
                FalVeoPricingModel => PricingKind.PerSecond,
                FalWanT2vPricingModel => PricingKind.PerSecond,
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
