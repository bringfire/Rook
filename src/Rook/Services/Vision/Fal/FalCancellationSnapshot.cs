using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    /// <summary>Local monitoring stop and remote cancellation are independent facts.</summary>
    public sealed class FalCancellationSnapshot
    {
        public bool LocalStopped { get; }
        public string RemoteDisposition { get; }
        public GenerationLifecycleState? RemoteTerminalState { get; }
        public bool Automatic { get; }
        public bool RemoteCancellationConfirmed => RemoteDisposition == "confirmed_cancelled";

        public FalCancellationSnapshot(bool localStopped, string remoteDisposition, bool automatic,
            GenerationLifecycleState? remoteTerminalState = null)
        {
            if (remoteDisposition is not ("confirmed_cancelled" or "cancellation_requested" or "already_completed"
                or "already_terminal" or "failed" or "unavailable" or "local_stop_only" or "not_requested"))
                throw new ArgumentException("Unsupported remote cancellation disposition.");
            if (remoteDisposition == "already_completed" && remoteTerminalState != GenerationLifecycleState.Completed
                || remoteDisposition == "already_terminal" && remoteTerminalState == null
                || remoteTerminalState != null && remoteDisposition is not ("already_completed" or "already_terminal"))
                throw new ArgumentException("Invalid remote terminal-state evidence.");
            if (remoteTerminalState != null && remoteTerminalState is not (GenerationLifecycleState.Completed or GenerationLifecycleState.Canceled or GenerationLifecycleState.Failed))
                throw new ArgumentException("Expected a remote terminal state.");
            LocalStopped = localStopped;
            RemoteDisposition = remoteDisposition;
            RemoteTerminalState = remoteTerminalState;
            Automatic = automatic;
        }

        internal JsonObject ToJson() => new()
        {
            ["local_stopped"] = LocalStopped,
            ["remote_disposition"] = RemoteDisposition,
            ["remote_terminal_state"] = RemoteTerminalState?.ToString(),
            ["automatic"] = Automatic,
        };

        internal static FalCancellationSnapshot FromJson(JsonObject json)
        {
            GenerationLifecycleState? terminal = null;
            if (json["remote_terminal_state"] != null)
            {
                if (!Enum.TryParse<GenerationLifecycleState>(json["remote_terminal_state"]!.GetValue<string>(), out var parsed)
                    || !Enum.IsDefined(typeof(GenerationLifecycleState), parsed)) throw new ArgumentException("Invalid remote terminal state.");
                terminal = parsed;
            }
            return new(json["local_stopped"]!.GetValue<bool>(), json["remote_disposition"]!.GetValue<string>(), json["automatic"]!.GetValue<bool>(), terminal);
        }

        internal static (FalCancellationSnapshot Evidence, GenerationError? Error) Observe(ProviderCancelOutcome outcome, bool automatic)
        {
            if (outcome is CanceledOutcome) return (new(true, "confirmed_cancelled", automatic), null);
            if (outcome is AlreadyTerminalOutcome terminal)
            {
                var completed = terminal.TerminalState == GenerationLifecycleState.Completed;
                return (new(true, completed ? "already_completed" : "already_terminal", automatic, terminal.TerminalState),
                    new GenerationError(GenerationErrorCode.ExecutionFailed,
                        completed ? "Local monitoring stopped, but remote generation already completed; remote cancellation was not confirmed."
                            : "Local monitoring stopped; the provider reports an already-terminal request.", false,
                        ProviderErrorCode: completed ? "fal_already_completed" : "fal_already_terminal"));
            }
            if (outcome is FailedCancelOutcome failed)
            {
                var disposition = failed.Error.ProviderErrorCode == "fal_cancellation_requested" ? "cancellation_requested"
                    : failed.Error.Code == GenerationErrorCode.DependencyUnavailable ? "unavailable" : "failed";
                return (new(true, disposition, automatic), failed.Error);
            }
            return (new(true, "local_stop_only", automatic), new GenerationError(GenerationErrorCode.Interrupted, LocalStopOnlyOutcome.Message, false));
        }
    }
}
