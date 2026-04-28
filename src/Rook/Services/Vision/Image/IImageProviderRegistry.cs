using System.Collections.Generic;

namespace Rook.Services.Vision.Image
{
    public interface IImageProviderRegistry
    {
        bool TryResolve(string modelId, out ResolvedImageModel model);
        bool TryResolveProviderByName(string providerName, out IImageProvider provider);
        IReadOnlyList<ImageModelDescriptor> EnumerateAllModels();
    }
}
