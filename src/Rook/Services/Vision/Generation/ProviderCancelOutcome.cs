using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Discriminated outcome of
    /// <see cref="IGenerationProvider{TRequest, TCapability}.CancelAsync"/>.
    /// Cancellation has three real outcomes: actually canceled, the job
    /// already terminated before the cancel landed, or cancel itself
    /// failed (transport, auth, etc.).
    /// </summary>
    public abstract record ProviderCancelOutcome;

    /// <summary>Provider acknowledged cancellation. The job is now in
    /// <see cref="GenerationLifecycleState.Canceled"/>.</summary>
    public sealed record CanceledOutcome : ProviderCancelOutcome;

    /// <summary>The job had already reached a terminal state
    /// (Completed/Failed/Canceled) before the cancel request landed.
    /// Manager treats this as a no-op for cancellation purposes; the
    /// terminal state is the source of truth.</summary>
    public sealed record AlreadyTerminalOutcome(
        GenerationLifecycleState TerminalState) : ProviderCancelOutcome
    {
        public GenerationLifecycleState TerminalState { get; init; } =
            (TerminalState == GenerationLifecycleState.Completed
                || TerminalState == GenerationLifecycleState.Failed
                || TerminalState == GenerationLifecycleState.Canceled)
                ? TerminalState
                : throw new ArgumentException(
                    $"AlreadyTerminalOutcome requires a terminal state; got {TerminalState}.",
                    nameof(TerminalState));
    }

    /// <summary>Cancel call itself failed.</summary>
    public sealed record FailedCancelOutcome(GenerationError Error) : ProviderCancelOutcome
    {
        public GenerationError Error { get; init; } =
            Error ?? throw new ArgumentNullException(nameof(Error));
    }
}
