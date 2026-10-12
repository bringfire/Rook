using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public interface IImageDispatchAwareProvider : IImageProvider
    {
        Task<ProviderSubmitOutcome> SubmitAsync(ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            Func<CancellationToken, Task<GenerationError?>> generationDispatchPreparing,
            Action generationDispatchStarting, CancellationToken ct);
    }
}
