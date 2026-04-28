using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Discriminated outcome of
    /// <see cref="IGenerationProvider{TRequest, TCapability}.GetStatusAsync"/>.
    /// </summary>
    public abstract record ProviderStatusOutcome;

    /// <summary>Provider is still working. Manager continues
    /// polling.</summary>
    public sealed record InFlightStatusOutcome(
        GenerationLifecycleState State,
        GenerationProgress? Progress) : ProviderStatusOutcome
    {
        public GenerationLifecycleState State { get; init; } =
            (State == GenerationLifecycleState.Pending || State == GenerationLifecycleState.Running)
                ? State
                : throw new ArgumentException(
                    $"InFlightStatusOutcome requires a non-terminal state; got {State}.",
                    nameof(State));
    }

    /// <summary>Provider's work is done; result handle is on
    /// <see cref="UpdatedHandle"/> (the manager will pass this back
    /// to <c>FetchResultAsync</c>). This is NOT the same as job-Complete
    /// from the manager's perspective — the manager still has to
    /// materialize artifacts before its consumers see Complete.
    ///
    /// <para>Critical Phase 0 finding: for fal queue, the lifecycle
    /// reaching <c>COMPLETED</c> is terminal-not-success. Success vs
    /// failure is discriminated at the fetch step
    /// (<see cref="ProviderResultOutcome"/>), not by reading this
    /// outcome alone.</para></summary>
    public sealed record ProviderCompleteStatusOutcome(
        ProviderJobHandle UpdatedHandle) : ProviderStatusOutcome
    {
        public ProviderJobHandle UpdatedHandle { get; init; } =
            UpdatedHandle ?? throw new ArgumentNullException(nameof(UpdatedHandle));
    }

    /// <summary>Terminal failure observed during status polling
    /// (provider explicitly reported failed/canceled, or auth/quota
    /// fault on the polling endpoint itself). Distinct from
    /// <see cref="FailedResultOutcome"/> which is failure observed at
    /// the fetch step on a provider whose lifecycle reported
    /// terminal-success.</summary>
    public sealed record FailedStatusOutcome(GenerationError Error) : ProviderStatusOutcome
    {
        public GenerationError Error { get; init; } =
            Error ?? throw new ArgumentNullException(nameof(Error));
    }
}
