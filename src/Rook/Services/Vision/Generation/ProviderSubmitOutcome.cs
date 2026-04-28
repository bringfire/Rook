using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Closed discriminated outcome of
    /// <see cref="IGenerationProvider{TRequest, TCapability}.SubmitAsync"/>.
    /// Per Phase 0 binding (Decision 1), sync and async paths cannot
    /// share a single submit-then-poll-then-fetch contract; the union
    /// makes the discrimination explicit at the type level.
    ///
    /// <para><b>Closure mechanism:</b> this is an <c>abstract class</c>
    /// (not an <c>abstract record</c>) so the compiler does not generate
    /// a protected copy constructor. The parameterless constructor is
    /// <c>private protected</c>, restricting derivation to same-assembly
    /// + derived classes. External assemblies cannot derive.</para>
    ///
    /// <para>Subtypes are <see cref="SyncSubmitOutcome"/>,
    /// <see cref="QueuedSubmitOutcome"/>, <see cref="FailedSubmitOutcome"/>.
    /// Reflection-based <c>UnionClosureTests</c> enforces this set;
    /// adding a leaf in this assembly fails that test until the
    /// expected list is updated.</para>
    /// </summary>
    public abstract class ProviderSubmitOutcome
    {
        private protected ProviderSubmitOutcome() { }
    }

    /// <summary>Sync providers (Gemini direct, fal sync) return the
    /// full result inline at submit. The inner
    /// <see cref="ProviderResultOutcome"/> still discriminates success
    /// vs failure of the compute (e.g. NSFW filter rejection on a
    /// completed generation).</summary>
    public sealed class SyncSubmitOutcome : ProviderSubmitOutcome
    {
        public SyncSubmitOutcome(ProviderResultOutcome Result)
        {
            this.Result = Result ?? throw new ArgumentNullException(nameof(Result));
        }

        public ProviderResultOutcome Result { get; }
    }

    /// <summary>Async providers (Veo, fal queue, Replicate) return a
    /// handle for subsequent polling and fetching.</summary>
    public sealed class QueuedSubmitOutcome : ProviderSubmitOutcome
    {
        public QueuedSubmitOutcome(ProviderJobHandle Handle)
        {
            this.Handle = Handle ?? throw new ArgumentNullException(nameof(Handle));
        }

        public ProviderJobHandle Handle { get; }
    }

    /// <summary>Pre-meter failure: the submission itself never
    /// reached compute. Auth, request-shape validation, network,
    /// quota returned synchronously. Provider's billing meter never
    /// ran (Phase 0 evidence: fal returns
    /// <c>x-fal-billable-units: 0</c> on input-validation rejection).
    /// Manager logs as no-cost failure.</summary>
    public sealed class FailedSubmitOutcome : ProviderSubmitOutcome
    {
        public FailedSubmitOutcome(GenerationError Error)
        {
            this.Error = Error ?? throw new ArgumentNullException(nameof(Error));
        }

        public GenerationError Error { get; }
    }
}
