using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation.Vertex
{
    // Project-specific billing is not a subscription entitlement or an exact zero-dollar estimate.
    internal sealed class VertexUnpricedModel<TRequest, TCapability> : IPricingModel<TRequest,TCapability>
        where TRequest : GenerationRequest where TCapability : IModelCapability
    {
        public string PricingSource => "vertex-project-billing-unpriced";
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseBody;
        public PricingResult Estimate(TRequest request,TCapability capability) => PricingResult.Ok(
            new JobPricing("USD",null,null,null,null,PricingSource),new CostEstimate(0,0,false,PricingSource));
        public JobPricing? ExtractActualSpend(IReadOnlyDictionary<string,IReadOnlyList<string>> headers,JsonNode? body) => null;
    }
}
