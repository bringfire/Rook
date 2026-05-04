using System;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobManager
    {
        Task<ImageJobSubmitResult> SubmitAsync(
            ImageJobStartRequest request, CancellationToken ct);

        Task<ImageJobStatusResult> GetStatusAsync(
            Guid jobId, CancellationToken ct);

        Task<ImageJobCancelResult> CancelAsync(
            Guid jobId, CancellationToken ct);

        Task<ImageJobFetchResult> FetchResultAsync(
            Guid jobId, CancellationToken ct);

        Task<ImageJobListResult> ListJobsAsync(int limit, CancellationToken ct);

        void ReconcileInterruptedJobs();
    }
}
