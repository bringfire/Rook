using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Manager-facing outcome of <see cref="IVideoJobManager.SubmitAsync"/>
    /// — what V2/V3/V4 consumers see. The provider-side equivalent is
    /// <see cref="ProviderSubmitResult"/>; the manager translates after
    /// minting a Rook-side <c>jobId</c> and persisting to the ledger.
    ///
    /// Constructed only via <see cref="Ok"/> or <see cref="Fail"/>; the
    /// type system enforces <c>Error == null ⇔ JobId != null</c>.
    /// </summary>
    public sealed record JobSubmitResult
    {
        public VideoJobState State { get; }

        /// <summary>
        /// Rook-side job identifier minted by the manager. Consumers use
        /// this Guid as the handle for subsequent
        /// <see cref="IVideoJobManager.GetStatusAsync"/> /
        /// <see cref="IVideoJobManager.CancelAsync"/> /
        /// <see cref="IVideoJobManager.FetchResultAsync"/> calls.
        /// </summary>
        public Guid? JobId { get; }

        public VideoJobError? Error { get; }

        private JobSubmitResult(
            VideoJobState state, Guid? jobId, VideoJobError? error)
        {
            State = state;
            JobId = jobId;
            Error = error;
        }

        public static JobSubmitResult Ok(Guid jobId, VideoJobState state)
        {
            if (jobId == Guid.Empty)
                throw new ArgumentException(
                    "JobId must be non-empty for a successful submit.",
                    nameof(jobId));

            return new JobSubmitResult(state, jobId, error: null);
        }

        public static JobSubmitResult Fail(VideoJobError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new JobSubmitResult(
                VideoJobState.Error, jobId: null, error);
        }
    }
}
