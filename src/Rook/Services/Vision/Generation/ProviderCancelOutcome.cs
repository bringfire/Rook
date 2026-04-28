using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Closed discriminated outcome of
    /// <see cref="IGenerationProvider{TRequest, TCapability}.CancelAsync"/>.
    /// Cancellation has three real outcomes: actually canceled, the
    /// job already terminated before the cancel landed, or cancel
    /// itself failed (transport, auth, etc.).
    ///
    /// <para>Closure: abstract class with <c>private protected</c>
    /// parameterless ctor.</para>
    /// </summary>
    public abstract class ProviderCancelOutcome
    {
        private protected ProviderCancelOutcome() { }
    }

    /// <summary>Provider acknowledged cancellation.</summary>
    public sealed class CanceledOutcome : ProviderCancelOutcome
    {
    }

    /// <summary>The job had already reached a terminal state before
    /// the cancel request landed. Manager treats this as a no-op for
    /// cancellation purposes; the terminal state is the source of
    /// truth.</summary>
    public sealed class AlreadyTerminalOutcome : ProviderCancelOutcome
    {
        public AlreadyTerminalOutcome(GenerationLifecycleState TerminalState)
        {
            if (TerminalState != GenerationLifecycleState.Completed
                && TerminalState != GenerationLifecycleState.Failed
                && TerminalState != GenerationLifecycleState.Canceled)
            {
                throw new ArgumentException(
                    $"AlreadyTerminalOutcome requires a terminal state; got {TerminalState}.",
                    nameof(TerminalState));
            }

            this.TerminalState = TerminalState;
        }

        public GenerationLifecycleState TerminalState { get; }
    }

    /// <summary>Cancel call itself failed.</summary>
    public sealed class FailedCancelOutcome : ProviderCancelOutcome
    {
        public FailedCancelOutcome(GenerationError Error)
        {
            this.Error = Error ?? throw new ArgumentNullException(nameof(Error));
        }

        public GenerationError Error { get; }
    }
}
