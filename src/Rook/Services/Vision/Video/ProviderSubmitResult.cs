using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoProvider.SubmitAsync"/> — provider-side
    /// result before any manager-side work (artifact write, ledger update).
    /// The manager translates this into a <see cref="JobSubmitResult"/>
    /// after persistence.
    ///
    /// Constructed only via <see cref="Ok"/> or <see cref="Fail"/>; the
    /// type system enforces <c>Error == null ⇔ ProviderJobId != null</c>.
    /// </summary>
    public sealed record ProviderSubmitResult
    {
        public VideoJobState State { get; }
        public string? ProviderJobId { get; }
        public VideoJobError? Error { get; }

        private ProviderSubmitResult(
            VideoJobState state, string? providerJobId, VideoJobError? error)
        {
            State = state;
            ProviderJobId = providerJobId;
            Error = error;
        }

        public static ProviderSubmitResult Ok(string providerJobId)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                throw new ArgumentException(
                    "ProviderJobId must be non-empty for a successful submit.",
                    nameof(providerJobId));

            return new ProviderSubmitResult(
                VideoJobState.Submitting, providerJobId, error: null);
        }

        public static ProviderSubmitResult Fail(VideoJobError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ProviderSubmitResult(
                VideoJobState.Error, providerJobId: null, error);
        }
    }
}
