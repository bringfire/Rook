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
    /// <see cref="JobFetchResult"/>; provider outcomes stay internal to
    /// the manager.
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
        /// Returns a newest-first projection of jobs known to the manager,
        /// merging the on-disk ledger with in-memory running snapshots
        /// per the freshness rule documented on the implementation.
        ///
        /// <paramref name="limit"/> is clamped to a hard ceiling
        /// (<see cref="VideoJobManager.MaxListLimit"/>); the actually
        /// applied limit is reported in
        /// <see cref="JobListResult.AppliedLimit"/>. Caller is responsible
        /// for rejecting non-positive or non-integer values before
        /// calling — the manager treats <paramref name="limit"/> as a
        /// positive integer contract.
        ///
        /// Bad ledger lines surface as
        /// <see cref="JobListResult.Warnings"/> entries; they do not
        /// block valid records from appearing in
        /// <see cref="JobListResult.Jobs"/>.
        /// </summary>
        Task<JobListResult> ListJobsAsync(int limit, CancellationToken ct);

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
