using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Discriminated outcome of
    /// <see cref="IGenerationProvider{TRequest, TCapability}.SubmitAsync"/>.
    /// Per Phase 0 binding (Decision 1), sync and async paths cannot
    /// share a single submit-then-poll-then-fetch contract; the union
    /// makes the discrimination explicit at the type level.
    /// </summary>
    public abstract record ProviderSubmitOutcome
    {
        // Closes external derivation: only same-assembly + derived
        // records can construct the base. Suppresses the auto-generated
        // public ctor.
        private protected ProviderSubmitOutcome() { }
    }

    /// <summary>Sync providers (Gemini direct, fal sync) return the
    /// full result inline at submit. The inner
    /// <see cref="ProviderResultOutcome"/> still discriminates success
    /// vs failure of the compute (e.g. NSFW filter rejection on a
    /// completed generation).</summary>
    public sealed record SyncSubmitOutcome(ProviderResultOutcome Result) : ProviderSubmitOutcome
    {
        public ProviderResultOutcome Result { get; init; } =
            Result ?? throw new ArgumentNullException(nameof(Result));
    }

    /// <summary>Async providers (Veo, fal queue, Replicate) return a
    /// handle for subsequent polling and fetching.</summary>
    public sealed record QueuedSubmitOutcome(ProviderJobHandle Handle) : ProviderSubmitOutcome
    {
        public ProviderJobHandle Handle { get; init; } =
            Handle ?? throw new ArgumentNullException(nameof(Handle));
    }

    /// <summary>Pre-meter failure: the submission itself never
    /// reached compute. Auth, request-shape validation, network,
    /// quota returned synchronously. Provider's billing meter never
    /// ran (Phase 0 evidence: fal returns
    /// <c>x-fal-billable-units: 0</c> on input-validation rejection).
    /// Manager logs as no-cost failure.</summary>
    public sealed record FailedSubmitOutcome(GenerationError Error) : ProviderSubmitOutcome
    {
        public GenerationError Error { get; init; } =
            Error ?? throw new ArgumentNullException(nameof(Error));
    }
}
