using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Outcome of
    /// <see cref="IProviderOptionsCodec{TRequest, TCapability}.Deserialize"/>.
    /// V1c semantics carry over: codecs fail-closed on unknown
    /// serialized values, surfacing a typed error rather than crashing.
    /// V2+ replay consumers reading records written by a newer binary
    /// may need a <c>RawProviderOptions</c> fallback subtype before
    /// they can tolerate forward-compat envelopes — out of scope for
    /// Phase 1.
    /// </summary>
    public sealed record ProviderOptionsDecodeResult
    {
        public ProviderOptions? Options { get; }
        public GenerationError? Error { get; }

        public bool Success => Error is null && Options is not null;

        private ProviderOptionsDecodeResult(ProviderOptions? options, GenerationError? error)
        {
            Options = options;
            Error = error;
        }

        public static ProviderOptionsDecodeResult Ok(ProviderOptions options)
        {
            if (options is null) throw new ArgumentNullException(nameof(options));
            return new ProviderOptionsDecodeResult(options, error: null);
        }

        public static ProviderOptionsDecodeResult Fail(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new ProviderOptionsDecodeResult(options: null, error);
        }
    }
}
