using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Snapshot of a video job's state. Constructed only via
    /// <see cref="InFlight"/>, <see cref="Complete"/>, or
    /// <see cref="Failed"/>; the type system enforces the
    /// invariants pinned in v3.1's D3 status envelope:
    /// <list type="bullet">
    ///   <item><description><c>Complete</c> ⇒ <c>ResultArtifactId != null</c>, no error.</description></item>
    ///   <item><description><c>Failed</c> ⇒ terminal state in {Error, Cancelled, Interrupted}, error set, no artifact id.</description></item>
    ///   <item><description><c>InFlight</c> ⇒ in-flight state, no artifact id, no error.</description></item>
    /// </list>
    /// </summary>
    public sealed record JobStatusResult
    {
        public VideoJobState State { get; }
        public VideoJobProgress? Progress { get; }
        public Guid? ResultArtifactId { get; }
        public VideoJobError? Error { get; }

        private JobStatusResult(
            VideoJobState state,
            VideoJobProgress? progress,
            Guid? resultArtifactId,
            VideoJobError? error)
        {
            State = state;
            Progress = progress;
            ResultArtifactId = resultArtifactId;
            Error = error;
        }

        public static JobStatusResult InFlight(
            VideoJobState state, VideoJobProgress? progress)
        {
            if (!IsInFlight(state))
                throw new ArgumentException(
                    $"InFlight requires a non-terminal state; got {state}.",
                    nameof(state));

            return new JobStatusResult(
                state, progress, resultArtifactId: null, error: null);
        }

        public static JobStatusResult Complete(Guid resultArtifactId)
        {
            if (resultArtifactId == Guid.Empty)
                throw new ArgumentException(
                    "ResultArtifactId must be non-empty for Complete.",
                    nameof(resultArtifactId));

            return new JobStatusResult(
                VideoJobState.Complete,
                progress: null,
                resultArtifactId,
                error: null);
        }

        public static JobStatusResult Failed(VideoJobState terminal, VideoJobError error)
        {
            if (!IsTerminalFailure(terminal))
                throw new ArgumentException(
                    $"Failed requires a terminal failure state; got {terminal}.",
                    nameof(terminal));
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new JobStatusResult(
                terminal,
                progress: null,
                resultArtifactId: null,
                error);
        }

        private static bool IsInFlight(VideoJobState s) =>
            s is VideoJobState.Queued
              or VideoJobState.Submitting
              or VideoJobState.Polling
              or VideoJobState.Downloading
              or VideoJobState.Saving;

        private static bool IsTerminalFailure(VideoJobState s) =>
            s is VideoJobState.Error
              or VideoJobState.Cancelled
              or VideoJobState.Interrupted;
    }
}
