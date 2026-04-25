using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Provider-shape seam for video generation. V1a defines the contract
    /// only; V1b ships the real <c>VeoProvider</c> implementation. Tests
    /// substitute a <c>FakeVideoProvider</c> that lives under
    /// <c>src/Rook.Tests/Services/Vision/Video/</c>.
    ///
    /// All four methods return result envelopes — implementations should
    /// translate provider-side errors into typed
    /// <see cref="VideoJobError"/> values rather than throwing for
    /// expected failure modes (auth, quota, validation, provider job
    /// failure). Genuine transport / cancellation exceptions still
    /// propagate as exceptions; the V1b adapter is responsible for the
    /// final exception-to-envelope translation at the public boundary.
    /// </summary>
    public interface IVideoProvider
    {
        Task<JobSubmitResult> SubmitAsync(
            VideoGenerationRequest request,
            CancellationToken ct);

        Task<JobStatusResult> GetStatusAsync(
            string providerJobId,
            CancellationToken ct);

        Task<JobCancelResult> CancelAsync(
            string providerJobId,
            CancellationToken ct);

        Task<JobFetchResult> FetchResultAsync(
            string providerJobId,
            CancellationToken ct);
    }
}
