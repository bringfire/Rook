namespace Rook.Services.Vision.Image
{
    public sealed record ImageModelDescriptor(
        string ModelId,
        string ProviderName,
        ImageCapability Capability,
        string PricingSource);
}
