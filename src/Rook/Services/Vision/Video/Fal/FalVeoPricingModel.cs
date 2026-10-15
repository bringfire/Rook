using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalVeoPricingModel : IPricingModel<VideoGenerationRequest, VideoCapability>
    {
        private readonly FalVeoBindingCatalog _catalog;
        internal FalVeoPricingModel(FalVeoBindingCatalog catalog) => _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));

        public string PricingSource => "fal-veo-binding-catalog";
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

        public PricingResult Estimate(VideoGenerationRequest request, VideoCapability capability)
        {
            if (request is null) return PricingResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest, "Request is null.", false, nameof(request)));
            var candidate = _catalog.GetCandidate(request);
            if (candidate.Binding is not { } binding) return PricingResult.Fail(candidate.Error!);
            // Mode and references select the same endpoint as dispatch. The
            // returned audit snapshot carries that endpoint's source and rate.
            return new PerSecondVideoPricingModel(binding.RatesUsdPerSecond, binding.PricingSource).Estimate(request, capability);
        }

        public Generation.JobPricing? ExtractActualSpend(IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders, JsonNode? responseBody) => null;
    }
}
