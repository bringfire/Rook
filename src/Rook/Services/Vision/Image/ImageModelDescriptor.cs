namespace Rook.Services.Vision.Image
{
    public sealed record ImageModelDescriptor(
        string ModelId,
        string ProviderName,
        ImageSubmissionMode SubmissionMode,
        ImageCapability Capability,
        string PricingSource);
}
