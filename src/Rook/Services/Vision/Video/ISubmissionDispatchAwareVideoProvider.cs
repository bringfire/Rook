using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>Notify the manager immediately before a single non-idempotent dispatch.</summary>
    internal interface ISubmissionDispatchAwareVideoProvider
    {
        GenerationError SubmissionInterruptedError { get; }
        Task<ProviderSubmitOutcome> SubmitWithDispatchAsync(VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media, Action beforeDispatch, CancellationToken ct);
    }
}
