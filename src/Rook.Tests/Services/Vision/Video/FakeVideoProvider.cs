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
    /// provider, so V1a/V1b deliberately avoid shipping one in the main
    /// assembly. <c>VeoProvider</c> is the single production
    /// implementation.
    ///
    /// Tests compose behaviour by setting <see cref="OnSubmit"/> /
    /// <see cref="OnGetStatus"/> / <see cref="OnCancel"/> /
    /// <see cref="OnFetchResult"/> hooks. Default behaviour returns
    /// trivially-successful envelopes so the type-level invariants on
    /// the result records can be observed end-to-end.
    /// </summary>
    public sealed class FakeVideoProvider : IVideoProvider
    {
        public Func<VideoGenerationRequest, IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia>, ProviderSubmitResult>? OnSubmit { get; set; }
        public Func<string, ProviderStatusResult>? OnGetStatus { get; set; }
        public Func<string, ProviderCancelResult>? OnCancel { get; set; }
        public Func<string, string?, ProviderFetchResult>? OnFetchResult { get; set; }

        public List<(string Method, object? Payload)> RecordedCalls { get; } = new();

        public Task<ProviderSubmitResult> SubmitAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> resolvedMedia,
            CancellationToken ct)
        {
            RecordedCalls.Add(("Submit", new { request, resolvedMedia }));
            var result = OnSubmit?.Invoke(request, resolvedMedia)
                ?? ProviderSubmitResult.Ok("fake-job-1");
            return Task.FromResult(result);
        }

        public Task<ProviderStatusResult> GetStatusAsync(
            string providerJobId, CancellationToken ct)
        {
            RecordedCalls.Add(("GetStatus", providerJobId));
            var result = OnGetStatus?.Invoke(providerJobId)
                ?? ProviderStatusResult.InFlight(
                    VideoJobState.Polling,
                    new VideoJobProgress(Pct: 50, Stage: "polling", Message: null));
            return Task.FromResult(result);
        }

        public Task<ProviderCancelResult> CancelAsync(
            string providerJobId, CancellationToken ct)
        {
            RecordedCalls.Add(("Cancel", providerJobId));
            var result = OnCancel?.Invoke(providerJobId)
                ?? ProviderCancelResult.Ok(VideoJobState.Cancelled);
            return Task.FromResult(result);
        }

        public Task<ProviderFetchResult> FetchResultAsync(
            string providerJobId, string? providerResultToken, CancellationToken ct)
        {
            RecordedCalls.Add(("FetchResult", new { providerJobId, providerResultToken }));
            var result = OnFetchResult?.Invoke(providerJobId, providerResultToken)
                ?? ProviderFetchResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.ExecutionFailed,
                    Message: "Fetch called before completion (default fake behaviour).",
                    Retryable: true));
            return Task.FromResult(result);
        }
    }
}
