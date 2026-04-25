using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoProvider.CancelAsync"/>. Constructed only
    /// via <see cref="Ok"/> or <see cref="Fail"/>; <see cref="Ok"/> reports
    /// the resulting provider-side state (typically
    /// <see cref="VideoJobState.Cancelled"/>; may be a terminal state if
    /// the job had already completed before cancel reached the provider).
    /// </summary>
    public sealed record ProviderCancelResult
    {
        public VideoJobState State { get; }
        public VideoJobError? Error { get; }

        private ProviderCancelResult(VideoJobState state, VideoJobError? error)
        {
            State = state;
            Error = error;
        }

        public static ProviderCancelResult Ok(VideoJobState state) =>
            new(state, error: null);

        public static ProviderCancelResult Fail(VideoJobError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ProviderCancelResult(VideoJobState.Error, error);
        }
    }
}
