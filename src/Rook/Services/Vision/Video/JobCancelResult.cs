using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoProvider.CancelAsync"/>. Constructed
    /// only via <see cref="Ok"/> or <see cref="Fail"/>; the type system
    /// enforces <c>Error == null ⇔</c> the cancel attempt was processed.
    /// <see cref="Ok"/> reports the resulting job state (typically
    /// <see cref="VideoJobState.Cancelled"/>; may be a non-cancellable
    /// terminal state if the job had already finished).
    /// </summary>
    public sealed record JobCancelResult
    {
        public VideoJobState State { get; }
        public VideoJobError? Error { get; }

        private JobCancelResult(VideoJobState state, VideoJobError? error)
        {
            State = state;
            Error = error;
        }

        public static JobCancelResult Ok(VideoJobState state) =>
            new(state, error: null);

        public static JobCancelResult Fail(VideoJobError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new JobCancelResult(VideoJobState.Error, error);
        }
    }
}
