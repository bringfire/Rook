using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Closed discriminated outcome of
    /// <see cref="IGenerationProvider{TRequest, TCapability}.GetStatusAsync"/>.
    ///
    /// <para>Closure: abstract class with <c>private protected</c>
    /// parameterless ctor.</para>
    /// </summary>
    public abstract class ProviderStatusOutcome
    {
        private protected ProviderStatusOutcome() { }
    }

    /// <summary>Provider is still working. Manager continues
    /// polling.</summary>
    public sealed class InFlightStatusOutcome : ProviderStatusOutcome
    {
        public InFlightStatusOutcome(GenerationLifecycleState State, GenerationProgress? Progress)
        {
            if (State != GenerationLifecycleState.Pending && State != GenerationLifecycleState.Running)
                throw new ArgumentException(
                    $"InFlightStatusOutcome requires a non-terminal state; got {State}.",
                    nameof(State));

            this.State = State;
            this.Progress = Progress;
        }

        public GenerationLifecycleState State { get; }
        public GenerationProgress? Progress { get; }
    }

    /// <summary>Provider's work is done; result handle is on
    /// <see cref="UpdatedHandle"/> (the manager passes this back to
    /// <c>FetchResultAsync</c>). NOT the same as job-Complete from
    /// the manager's perspective — the manager still has to materialize
    /// artifacts before its consumers see Complete.
    ///
    /// <para>Phase 0: for fal queue, lifecycle reaching
    /// <c>COMPLETED</c> is terminal-not-success. Success/failure is
    /// discriminated at the fetch step, not by reading this outcome
    /// alone.</para></summary>
    public sealed class ProviderCompleteStatusOutcome : ProviderStatusOutcome
    {
        public ProviderCompleteStatusOutcome(ProviderJobHandle UpdatedHandle)
        {
            this.UpdatedHandle = UpdatedHandle ?? throw new ArgumentNullException(nameof(UpdatedHandle));
        }

        public ProviderJobHandle UpdatedHandle { get; }
    }

    /// <summary>Terminal failure observed during status polling.
    /// Distinct from <see cref="FailedResultOutcome"/> which is
    /// failure observed at the fetch step on a provider whose
    /// lifecycle reported terminal-success.</summary>
    public sealed class FailedStatusOutcome : ProviderStatusOutcome
    {
        public FailedStatusOutcome(GenerationError Error)
        {
            this.Error = Error ?? throw new ArgumentNullException(nameof(Error));
        }

        public GenerationError Error { get; }
    }
}
