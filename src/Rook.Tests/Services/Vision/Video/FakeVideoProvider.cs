using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
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
        public Func<VideoGenerationRequest, IReadOnlyDictionary<MediaRef, ResolvedMedia>, ProviderSubmitOutcome>? OnSubmitOutcome { get; set; }
        public Func<ProviderJobHandle, ProviderStatusOutcome>? OnGetStatusOutcome { get; set; }
        public Func<ProviderJobHandle, ProviderCancelOutcome>? OnCancelOutcome { get; set; }
        public Func<ProviderJobHandle, ProviderResultOutcome>? OnFetchResultOutcome { get; set; }

        public Func<VideoGenerationRequest, IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia>, ProviderSubmitResult>? OnSubmit { get; set; }
        public Func<string, ProviderStatusResult>? OnGetStatus { get; set; }
        public Func<string, ProviderCancelResult>? OnCancel { get; set; }
        public Func<string, string?, ProviderFetchResult>? OnFetchResult { get; set; }

        public List<(string Method, object? Payload)> RecordedCalls { get; } = new();

        public string ProviderName => "fake-video";

        public Task<ProviderSubmitOutcome> SubmitAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            RecordedCalls.Add(("Submit", new { request, resolvedMedia }));
            var result = OnSubmitOutcome?.Invoke(request, resolvedMedia)
                ?? (OnSubmit is null
                    ? new QueuedSubmitOutcome(new ProviderJobHandle("fake-job-1"))
                    : VideoProviderOutcomeAdapters.ToProviderSubmitOutcome(
                        OnSubmit(
                            request,
                            VideoProviderOutcomeAdapters.ToVideoMedia(resolvedMedia))));
            return Task.FromResult(result);
        }

        public Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle, CancellationToken ct)
        {
            RecordedCalls.Add(("GetStatus", handle.ProviderJobId));
            var result = OnGetStatusOutcome?.Invoke(handle)
                ?? (OnGetStatus is null
                    ? new InFlightStatusOutcome(
                        GenerationLifecycleState.Running,
                        new GenerationProgress(PercentComplete: 50, Message: "polling"))
                    : ToStatusOutcome(handle, OnGetStatus(handle.ProviderJobId)));
            return Task.FromResult(result);
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle, CancellationToken ct)
        {
            RecordedCalls.Add(("Cancel", handle.ProviderJobId));
            var result = OnCancelOutcome?.Invoke(handle)
                ?? (OnCancel is null
                    ? new CanceledOutcome()
                    : VideoProviderOutcomeAdapters.ToProviderCancelOutcome(
                        OnCancel(handle.ProviderJobId)));
            return Task.FromResult(result);
        }

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle, CancellationToken ct)
        {
            RecordedCalls.Add(("FetchResult", new
            {
                providerJobId = handle.ProviderJobId,
                providerResultToken = handle.ProviderResultToken,
            }));
            var result = OnFetchResultOutcome?.Invoke(handle)
                ?? (OnFetchResult is null
                    ? new FailedResultOutcome(new GenerationError(
                        Code: GenerationErrorCode.ExecutionFailed,
                        Message: "Fetch called before completion (default fake behaviour).",
                        Retryable: true))
                    : ToResultOutcome(
                        OnFetchResult(handle.ProviderJobId, handle.ProviderResultToken)));
            return Task.FromResult(result);
        }

        private static ProviderStatusOutcome ToStatusOutcome(
            ProviderJobHandle handle,
            ProviderStatusResult result)
        {
            if (result.Error is not null)
                return new FailedStatusOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(result.Error));

            if (result.State == VideoJobState.Complete)
                return new ProviderCompleteStatusOutcome(
                    handle.WithResultToken(result.ProviderResultToken));

            return new InFlightStatusOutcome(
                GenerationLifecycleState.Running,
                result.Progress is null
                    ? null
                    : new GenerationProgress(
                        PercentComplete: result.Progress.Pct,
                        Message: result.Progress.Message));
        }

        private static ProviderResultOutcome ToResultOutcome(ProviderFetchResult result)
        {
            if (result.Error is not null)
                return new FailedResultOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(result.Error));

            return new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[]
                    {
                        new ResultArtifact(
                            Role: VideoMediaRoles.Video,
                            Body: new InlineArtifactBody(result.Bytes!),
                            DeclaredMimeType: result.MimeType,
                            ProviderMetadata: EmptyMetadata),
                    },
                    EmptyMetadata));
        }

        private static readonly IReadOnlyDictionary<string, JsonNode> EmptyMetadata
            = new Dictionary<string, JsonNode>();
    }
}
