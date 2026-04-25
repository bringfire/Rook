using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoProvider.SubmitAsync"/>. Constructed
    /// only via <see cref="Ok"/> or <see cref="Fail"/>; the type system
    /// enforces the invariant <c>Error == null ⇔ ProviderJobId != null</c>.
    /// </summary>
    public sealed record JobSubmitResult
    {
        public VideoJobState State { get; }
        public string? ProviderJobId { get; }
        public VideoJobError? Error { get; }

        private JobSubmitResult(
            VideoJobState state, string? providerJobId, VideoJobError? error)
        {
            State = state;
            ProviderJobId = providerJobId;
            Error = error;
        }

        public static JobSubmitResult Ok(string providerJobId, VideoJobState state)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                throw new ArgumentException(
                    "ProviderJobId must be non-empty for a successful submit.",
                    nameof(providerJobId));

            return new JobSubmitResult(state, providerJobId, error: null);
        }

        public static JobSubmitResult Fail(VideoJobError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new JobSubmitResult(
                VideoJobState.Error, providerJobId: null, error);
        }
    }
}
