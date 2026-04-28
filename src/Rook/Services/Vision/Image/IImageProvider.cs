using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public interface IImageProvider
        : IGenerationProvider<ImageGenerationRequest, ImageCapability>
    {
    }
}
