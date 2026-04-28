namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Documentation hint for where a provider's actual-spend metadata
    /// arrives. NOT load-bearing: each <see cref="IPricingModel{TRequest, TCapability}"/>
    /// implementation owns its own header/body parsing. Phase 0 evidence
    /// notes that fal alone uses three different per-unit rates for the
    /// same <c>x-fal-billable-units</c> header — so the location is
    /// insufficient to identify the cost; the rate must be known by the
    /// per-model pricing implementation.
    /// </summary>
    public enum PricingMetadataLocation
    {
        NotApplicable = 0,
        ResponseHeader = 1,         // fal: x-fal-billable-units
        ResponseBody = 2,           // Replicate: metrics.predict_time; Gemini: usageMetadata
        ProviderSdk = 3,            // Tencent: typed SDK response
    }
}
