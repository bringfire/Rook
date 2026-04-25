using System;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Public seam for V2 (HTTP routes), V3 (tab UI), V4 (MCP tools)
    /// to consume video-job orchestration. The manager:
    ///   - validates and estimates the request
    ///   - resolves media refs to bytes via <see cref="IVideoMediaResolver"/>
    ///   - mints a Rook-side <c>jobId</c>
    ///   - persists snapshots to <see cref="IVideoJobLedger"/>
    ///   - drives the provider state machine in a background task
    ///   - writes the terminal artifact to <see cref="ArtifactStore"/>
    ///
    /// Consumers see only manager-facing <see cref="JobSubmitResult"/> /
    /// <see cref="JobStatusResult"/> / <see cref="JobCancelResult"/> /
    /// <see cref="JobFetchResult"/>; provider-side types
    /// (<see cref="ProviderSubmitResult"/> etc.) stay internal to the
    /// manager.
    /// </summary>
    public interface IVideoJobManager
    {
        Task<JobSubmitResult> SubmitAsync(
            VideoGenerationRequest request, CancellationToken ct);

        Task<JobStatusResult> GetStatusAsync(
            Guid jobId, CancellationToken ct);

        Task<JobCancelResult> CancelAsync(
            Guid jobId, CancellationToken ct);

        Task<JobFetchResult> FetchResultAsync(
            Guid jobId, CancellationToken ct);

        /// <summary>
        /// Called once at startup. Reads the ledger, finds any records
        /// in non-terminal state (mid-flight at last shutdown), and
        /// appends an Interrupted snapshot for each. V1b does NOT
        /// auto-resume per v3.1 D4 — but the persisted
        /// <c>provider_job_id</c> remains so explicit cancel can clean
        /// up remote provider jobs.
        /// </summary>
        void ReconcileInterruptedJobs();
    }
}
