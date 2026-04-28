using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Test seam for capturing <see cref="VideoOpHandler"/> output. The
    /// handler delegates submit / cancel / status / fetch / list to an
    /// <see cref="IVideoJobManager"/>; capture tests inject scripted
    /// outcomes so the golden reflects the handler's projection of a
    /// chosen manager-level result.
    ///
    /// <para>Unset behaviors throw, so a capture test that accidentally
    /// reaches an unscripted op fails loudly rather than silently
    /// returning a default and producing a misleading golden.</para>
    /// </summary>
    internal sealed class FakeVideoJobManager : IVideoJobManager
    {
        public Func<VideoGenerationRequest, Task<JobSubmitResult>>? OnSubmit { get; set; }
        public Func<Guid, Task<JobStatusResult>>? OnGetStatus { get; set; }
        public Func<Guid, Task<JobCancelResult>>? OnCancel { get; set; }
        public Func<Guid, Task<JobFetchResult>>? OnFetchResult { get; set; }
        public Func<int, Task<JobListResult>>? OnListJobs { get; set; }
        public Action? OnReconcile { get; set; }

        public Task<JobSubmitResult> SubmitAsync(
            VideoGenerationRequest request, CancellationToken ct) =>
            OnSubmit?.Invoke(request)
                ?? throw new InvalidOperationException(
                    $"{nameof(FakeVideoJobManager)}.{nameof(OnSubmit)} not configured.");

        public Task<JobStatusResult> GetStatusAsync(
            Guid jobId, CancellationToken ct) =>
            OnGetStatus?.Invoke(jobId)
                ?? throw new InvalidOperationException(
                    $"{nameof(FakeVideoJobManager)}.{nameof(OnGetStatus)} not configured.");

        public Task<JobCancelResult> CancelAsync(
            Guid jobId, CancellationToken ct) =>
            OnCancel?.Invoke(jobId)
                ?? throw new InvalidOperationException(
                    $"{nameof(FakeVideoJobManager)}.{nameof(OnCancel)} not configured.");

        public Task<JobFetchResult> FetchResultAsync(
            Guid jobId, CancellationToken ct) =>
            OnFetchResult?.Invoke(jobId)
                ?? throw new InvalidOperationException(
                    $"{nameof(FakeVideoJobManager)}.{nameof(OnFetchResult)} not configured.");

        public Task<JobListResult> ListJobsAsync(int limit, CancellationToken ct) =>
            OnListJobs?.Invoke(limit)
                ?? throw new InvalidOperationException(
                    $"{nameof(FakeVideoJobManager)}.{nameof(OnListJobs)} not configured.");

        public void ReconcileInterruptedJobs() =>
            OnReconcile?.Invoke();
    }
}
