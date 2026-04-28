using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Outcome of <see cref="IMediaResolver.ResolveAllAsync"/>. On
    /// success, exposes a per-ref dictionary the provider receives via
    /// its <c>SubmitAsync</c> argument; on failure, surfaces a typed
    /// <see cref="GenerationError"/>.
    /// </summary>
    public sealed record MediaResolutionResult
    {
        public IReadOnlyDictionary<MediaRef, ResolvedMedia>? Resolved { get; }
        public GenerationError? Error { get; }

        public bool Success => Error is null && Resolved is not null;

        private MediaResolutionResult(
            IReadOnlyDictionary<MediaRef, ResolvedMedia>? resolved,
            GenerationError? error)
        {
            Resolved = resolved;
            Error = error;
        }

        public static MediaResolutionResult Ok(
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolved)
        {
            if (resolved is null) throw new ArgumentNullException(nameof(resolved));
            return new MediaResolutionResult(resolved, error: null);
        }

        public static MediaResolutionResult Fail(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new MediaResolutionResult(resolved: null, error);
        }
    }
}
