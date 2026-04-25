using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Provider-side snapshot of a job's state. The manager translates this
    /// into a <see cref="JobStatusResult"/> after running its own
    /// post-provider phases (Downloading → Saving → manager-Complete with
    /// artifact id minted).
    ///
    /// Constructed only via <see cref="InFlight"/>, <see cref="Complete"/>,
    /// or <see cref="Failed"/>; the type system enforces v3.1 D3-shaped
    /// invariants at the provider layer:
    /// <list type="bullet">
    ///   <item><description><c>InFlight</c> ⇒ in-flight provider state, no token, no error.</description></item>
    ///   <item><description><c>Complete</c> ⇒ provider-Complete (Veo done; manager has not yet materialized artifact); ProviderResultToken set, no error.</description></item>
    ///   <item><description><c>Failed</c> ⇒ terminal failure state in {Error, Cancelled, Interrupted}; error set, no token.</description></item>
    /// </list>
    ///
    /// Note: <c>State == Complete</c> at the provider layer means
    /// "provider's work done, here's the result handle" — NOT the same as
    /// manager-<c>Complete</c> which means "artifact written, consumer can
    /// fetch it." The manager handles the translation.
    /// </summary>
    public sealed record ProviderStatusResult
    {
        public VideoJobState State { get; }
        public VideoJobProgress? Progress { get; }

        /// <summary>
        /// Provider-specific result handle. For Veo, this is the videoUri.
        /// For other providers it could be an asset id, URL, file id, or
        /// opaque result token. The manager persists this into
        /// <c>VideoJobRecord.provider_result_token</c> and passes it back
        /// to <see cref="IVideoProvider.FetchResultAsync"/>, so providers
        /// stay stateless across calls / restarts.
        /// </summary>
        public string? ProviderResultToken { get; }

        public VideoJobError? Error { get; }

        private ProviderStatusResult(
            VideoJobState state,
            VideoJobProgress? progress,
            string? providerResultToken,
            VideoJobError? error)
        {
            State = state;
            Progress = progress;
            ProviderResultToken = providerResultToken;
            Error = error;
        }

        public static ProviderStatusResult InFlight(
            VideoJobState state, VideoJobProgress? progress)
        {
            if (!IsInFlight(state))
                throw new ArgumentException(
                    $"InFlight requires a non-terminal provider state; got {state}.",
                    nameof(state));

            return new ProviderStatusResult(
                state, progress, providerResultToken: null, error: null);
        }

        public static ProviderStatusResult Complete(string providerResultToken)
        {
            if (string.IsNullOrWhiteSpace(providerResultToken))
                throw new ArgumentException(
                    "ProviderResultToken must be non-empty for Complete.",
                    nameof(providerResultToken));

            return new ProviderStatusResult(
                VideoJobState.Complete,
                progress: null,
                providerResultToken,
                error: null);
        }

        public static ProviderStatusResult Failed(
            VideoJobState terminal, VideoJobError error)
        {
            if (!IsTerminalFailure(terminal))
                throw new ArgumentException(
                    $"Failed requires a terminal failure state; got {terminal}.",
                    nameof(terminal));
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ProviderStatusResult(
                terminal,
                progress: null,
                providerResultToken: null,
                error);
        }

        // Provider-side in-flight states. Note Downloading and Saving are
        // manager-only; they don't appear in provider status results.
        private static bool IsInFlight(VideoJobState s) =>
            s is VideoJobState.Queued
              or VideoJobState.Submitting
              or VideoJobState.Polling;

        private static bool IsTerminalFailure(VideoJobState s) =>
            s is VideoJobState.Error
              or VideoJobState.Cancelled
              or VideoJobState.Interrupted;
    }
}
