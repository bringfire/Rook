using System.Collections.Generic;
using Rook.Services.Vision.Fal.Models;
namespace Rook.Services.Vision.Image
{
    public sealed record ImageModelDescriptor(
        string ModelId,
        string ProviderName,
        ImageSubmissionMode SubmissionMode,
        ImageCapability Capability,
        string PricingSource,
        IReadOnlyList<FalOperationDescriptor>? Operations = null);
}
