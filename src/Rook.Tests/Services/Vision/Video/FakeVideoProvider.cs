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
        public Func<VideoGenerationRequest, IReadOnlyDictionary<MediaRef, ResolvedMedia>, ProviderSubmitOutcome>? OnSubmit { get; set; }
        public Func<ProviderJobHandle, ProviderStatusOutcome>? OnGetStatus { get; set; }
        public Func<ProviderJobHandle, ProviderCancelOutcome>? OnCancel { get; set; }
        public Func<ProviderJobHandle, ProviderResultOutcome>? OnFetchResult { get; set; }

        public List<(string Method, object? Payload)> RecordedCalls { get; } = new();

        public string ProviderName => "fake-video";

        public Task<ProviderSubmitOutcome> SubmitAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            RecordedCalls.Add(("Submit", new { request, resolvedMedia }));
            var result = OnSubmit?.Invoke(request, resolvedMedia)
                ?? SubmitQueued("fake-job-1");
            return Task.FromResult(result);
        }

        public Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle, CancellationToken ct)
        {
            RecordedCalls.Add(("GetStatus", handle.ProviderJobId));
            var result = OnGetStatus?.Invoke(handle)
                ?? StatusInFlight(50, "polling");
            return Task.FromResult(result);
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle, CancellationToken ct)
        {
            RecordedCalls.Add(("Cancel", handle.ProviderJobId));
            var result = OnCancel?.Invoke(handle)
                ?? CancelOk();
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
            var result = OnFetchResult?.Invoke(handle)
                ?? ResultFailed(new VideoJobError(
                    Code: VideoErrorCode.ExecutionFailed,
                    Message: "Fetch called before completion (default fake behaviour).",
                    Retryable: true));
            return Task.FromResult(result);
        }

        public static ProviderSubmitOutcome SubmitQueued(string providerJobId) =>
            new QueuedSubmitOutcome(new ProviderJobHandle(providerJobId));

        public static ProviderSubmitOutcome SubmitFailed(VideoJobError error) =>
            new FailedSubmitOutcome(
                VideoProviderOutcomeAdapters.ToGenerationError(error));

        public static ProviderStatusOutcome StatusInFlight(
            int? pct = null, string? message = null) =>
            new InFlightStatusOutcome(
                GenerationLifecycleState.Running,
                pct is null && message is null
                    ? null
                    : new GenerationProgress(
                        PercentComplete: pct,
                        Message: message));

        public static ProviderStatusOutcome StatusComplete(
            ProviderJobHandle handle,
            string providerResultToken) =>
            new ProviderCompleteStatusOutcome(
                handle.WithResultToken(providerResultToken));

        public static ProviderStatusOutcome StatusFailed(VideoJobError error) =>
            new FailedStatusOutcome(
                VideoProviderOutcomeAdapters.ToGenerationError(error));

        public static ProviderCancelOutcome CancelOk() => new CanceledOutcome();

        public static ProviderCancelOutcome CancelFailed(VideoJobError error) =>
            new FailedCancelOutcome(
                VideoProviderOutcomeAdapters.ToGenerationError(error));

        public static ProviderResultOutcome ResultOk(byte[] bytes, string mimeType) =>
            new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[]
                    {
                        new ResultArtifact(
                            Role: VideoMediaRoles.Video,
                            Body: new InlineArtifactBody(bytes),
                            DeclaredMimeType: mimeType,
                            ProviderMetadata: EmptyMetadata),
                    },
                    EmptyMetadata));

        public static ProviderResultOutcome ResultRemote(
            string url,
            string? mimeType = null) =>
            new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[]
                    {
                        new ResultArtifact(
                            Role: VideoMediaRoles.Video,
                            Body: new RemoteArtifactBody(new Uri(url)),
                            DeclaredMimeType: mimeType,
                            ProviderMetadata: EmptyMetadata),
                    },
                    EmptyMetadata));

        public static ProviderResultOutcome ResultFailed(VideoJobError error) =>
            new FailedResultOutcome(
                VideoProviderOutcomeAdapters.ToGenerationError(error));

        private static readonly IReadOnlyDictionary<string, JsonNode> EmptyMetadata
            = new Dictionary<string, JsonNode>();
    }
}
