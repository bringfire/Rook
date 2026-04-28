using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Closed discriminated outcome of
    /// <see cref="IGenerationProvider{TRequest, TCapability}.FetchResultAsync"/>
    /// (and the inner result inside <see cref="SyncSubmitOutcome"/>).
    /// Success and failure are type-distinct; there is no nullable
    /// error field on the success envelope.
    ///
    /// <para>Closure: abstract class with <c>private protected</c>
    /// parameterless ctor. No compiler-generated copy constructor (a
    /// record's <c>protected</c> copy ctor would let external
    /// assemblies derive). External derivation is structurally
    /// blocked.</para>
    /// </summary>
    public abstract class ProviderResultOutcome
    {
        private protected ProviderResultOutcome() { }
    }

    /// <summary>Provider returned a usable result envelope.</summary>
    public sealed class SuccessResultOutcome : ProviderResultOutcome
    {
        public SuccessResultOutcome(ProviderResultEnvelope Envelope)
        {
            this.Envelope = Envelope ?? throw new ArgumentNullException(nameof(Envelope));
        }

        public ProviderResultEnvelope Envelope { get; }
    }

    /// <summary>Provider's compute completed but the result was a
    /// failure (NSFW filter, content policy, mid-inference OOM,
    /// fal-queue <c>COMPLETED</c> followed by HTTP 422 at the fetch
    /// step). The user MAY have been billed depending on provider
    /// policy — distinct from <see cref="FailedSubmitOutcome"/> which
    /// is pre-meter.</summary>
    public sealed class FailedResultOutcome : ProviderResultOutcome
    {
        public FailedResultOutcome(GenerationError Error)
        {
            this.Error = Error ?? throw new ArgumentNullException(nameof(Error));
        }

        public GenerationError Error { get; }
    }
}
