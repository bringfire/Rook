using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Test substrate for <see cref="IVideoProvider"/>. Lives in the
    /// tests project only — production code does not depend on a fake
    /// provider, so V1a deliberately avoids shipping one in the main
    /// assembly. V1b's real <c>VeoProvider</c> is the single production
    /// implementation.
    ///
    /// Tests compose behaviour by setting <see cref="OnSubmit"/> /
    /// <see cref="OnGetStatus"/> / <see cref="OnCancel"/> /
    /// <see cref="OnFetchResult"/> hooks. Default behaviour returns
    /// trivially-successful envelopes so the type-level invariants
    /// on the result records can be observed end-to-end.
    /// </summary>
    public sealed class FakeVideoProvider : IVideoProvider
    {
        public Func<VideoGenerationRequest, JobSubmitResult>? OnSubmit { get; set; }
        public Func<string, JobStatusResult>? OnGetStatus { get; set; }
        public Func<string, JobCancelResult>? OnCancel { get; set; }
        public Func<string, JobFetchResult>? OnFetchResult { get; set; }

        public List<(string Method, object? Payload)> RecordedCalls { get; } = new();

        public Task<JobSubmitResult> SubmitAsync(
            VideoGenerationRequest request, CancellationToken ct)
        {
            RecordedCalls.Add(("Submit", request));
            var result = OnSubmit?.Invoke(request)
                ?? JobSubmitResult.Ok("fake-job-1", VideoJobState.Submitting);
            return Task.FromResult(result);
        }

        public Task<JobStatusResult> GetStatusAsync(
            string providerJobId, CancellationToken ct)
        {
            RecordedCalls.Add(("GetStatus", providerJobId));
            var result = OnGetStatus?.Invoke(providerJobId)
                ?? JobStatusResult.InFlight(
                    VideoJobState.Polling,
                    new VideoJobProgress(Pct: 50, Stage: "polling", Message: null));
            return Task.FromResult(result);
        }

        public Task<JobCancelResult> CancelAsync(
            string providerJobId, CancellationToken ct)
        {
            RecordedCalls.Add(("Cancel", providerJobId));
            var result = OnCancel?.Invoke(providerJobId)
                ?? JobCancelResult.Ok(VideoJobState.Cancelled);
            return Task.FromResult(result);
        }

        public Task<JobFetchResult> FetchResultAsync(
            string providerJobId, CancellationToken ct)
        {
            RecordedCalls.Add(("FetchResult", providerJobId));
            var result = OnFetchResult?.Invoke(providerJobId)
                ?? JobFetchResult.Failed(
                    VideoJobState.Polling,
                    new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: "Fetch called before completion (default fake behaviour).",
                        Retryable: true));
            return Task.FromResult(result);
        }
    }
}
