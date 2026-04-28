using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Discriminated outcome of <see cref="IGenerationProvider{TRequest, TCapability}.FetchResultAsync"/>
    /// (and the inner result inside <see cref="SyncSubmitOutcome"/>).
    /// Success and failure are type-distinct branches; there is no
    /// nullable error field on the success envelope.
    /// </summary>
    public abstract record ProviderResultOutcome;

    /// <summary>Provider returned a usable result envelope.</summary>
    public sealed record SuccessResultOutcome(ProviderResultEnvelope Envelope) : ProviderResultOutcome
    {
        public ProviderResultEnvelope Envelope { get; init; } =
            Envelope ?? throw new ArgumentNullException(nameof(Envelope));
    }

    /// <summary>Provider's compute completed but the result was a
    /// failure (NSFW filter, content policy, mid-inference OOM,
    /// fal-queue <c>COMPLETED</c> followed by HTTP 422 at the fetch
    /// step). The user MAY have been billed depending on provider
    /// policy — distinct from <see cref="FailedSubmitOutcome"/> which
    /// is pre-meter.</summary>
    public sealed record FailedResultOutcome(GenerationError Error) : ProviderResultOutcome
    {
        public GenerationError Error { get; init; } =
            Error ?? throw new ArgumentNullException(nameof(Error));
    }
}
