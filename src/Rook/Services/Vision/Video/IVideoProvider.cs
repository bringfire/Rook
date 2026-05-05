using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Video provider marker over the modality-neutral generation seam.
    /// Provider implementations return generic generation outcomes; the
    /// video manager translates those into the consumer-facing v3.1 D3
    /// contract (<see cref="JobSubmitResult"/> etc.) after persistence
    /// + artifact write.
    ///
    /// Layering: the provider produces bytes, IDs, and tokens; the manager
    /// owns ArtifactStore writes, artifact-id minting, and ledger
    /// transitions. The provider never knows about Rook artifact IDs.
    ///
    /// Statelessness: providers must not cache per-job state across calls.
    /// All state needed across method invocations
    /// (<c>provider_job_id</c>, <c>provider_result_token</c>) is persisted
    /// by the manager and passed back as method arguments. This lets V1b's
    /// "no auto-resume on restart" stance hold without provider-side
    /// recovery code.
    ///
    /// All methods return result envelopes — implementations should
    /// translate provider-side errors into typed
    /// <see cref="VideoJobError"/> values rather than throwing for
    /// expected failure modes (auth, quota, validation, provider job
    /// failure). Genuine transport / cancellation exceptions still
    /// propagate as exceptions.
    /// </summary>
    public interface IVideoProvider
        : IGenerationProvider<VideoGenerationRequest, VideoCapability>
    {
    }

    public interface IModelAwareVideoProvider : IVideoProvider
    {
        Task<ProviderStatusOutcome> GetStatusAsync(
            string modelId, ProviderJobHandle handle, CancellationToken ct);

        Task<ProviderCancelOutcome> CancelAsync(
            string modelId, ProviderJobHandle handle, CancellationToken ct);

        Task<ProviderResultOutcome> FetchResultAsync(
            string modelId, ProviderJobHandle handle, CancellationToken ct);
    }
}
