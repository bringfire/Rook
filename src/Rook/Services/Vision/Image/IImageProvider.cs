using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public interface IImageProvider
        : IGenerationProvider<ImageGenerationRequest, ImageCapability>
    {
    }

    public interface IModelAwareImageProvider : IImageProvider
    {
        Task<ProviderStatusOutcome> GetStatusAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct);

        Task<ProviderCancelOutcome> CancelAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct);

        Task<ProviderResultOutcome> FetchResultAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct);
    }
}
