using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Tests.Services.Vision.Image
{
    public sealed class FakeImageProvider : IImageProvider
    {
        public Func<ImageGenerationRequest, IReadOnlyDictionary<MediaRef, ResolvedMedia>, ProviderSubmitOutcome>? OnSubmit { get; set; }
        public Func<ProviderJobHandle, ProviderStatusOutcome>? OnGetStatus { get; set; }
        public Func<ProviderJobHandle, ProviderCancelOutcome>? OnCancel { get; set; }
        public Func<ProviderJobHandle, ProviderResultOutcome>? OnFetchResult { get; set; }

        public List<string> Calls { get; } = new();
        public List<(string Method, object? Payload)> RecordedCalls { get; } = new();

        public string ProviderName => "fake-image";

        public Task<ProviderSubmitOutcome> SubmitAsync(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            Calls.Add("Submit");
            RecordedCalls.Add(("Submit", new { request, resolvedMedia }));
            var result = OnSubmit?.Invoke(request, resolvedMedia) ?? SyncPng();
            return Task.FromResult(result);
        }

        public Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            Calls.Add("GetStatus");
            RecordedCalls.Add(("GetStatus", handle.ProviderJobId));
            var result = OnGetStatus?.Invoke(handle) ?? Complete(handle);
            return Task.FromResult(result);
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            Calls.Add("Cancel");
            RecordedCalls.Add(("Cancel", handle.ProviderJobId));
            var result = OnCancel?.Invoke(handle) ?? new CanceledOutcome();
            return Task.FromResult(result);
        }

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            Calls.Add("FetchResult");
            RecordedCalls.Add(("FetchResult", new
            {
                providerJobId = handle.ProviderJobId,
                providerResultToken = handle.ProviderResultToken,
            }));
            var result = OnFetchResult?.Invoke(handle) ?? ImageResult(new byte[] { 4, 5, 6 });
            return Task.FromResult(result);
        }

        public static ProviderSubmitOutcome SyncPng() =>
            new SyncSubmitOutcome(ImageResult(new byte[] { 1, 2, 3 }));

        public static ProviderSubmitOutcome Queued(string providerJobId) =>
            new QueuedSubmitOutcome(new ProviderJobHandle(providerJobId));

        public static ProviderSubmitOutcome SubmitFailed(GenerationError error) =>
            new FailedSubmitOutcome(error);

        public static ProviderStatusOutcome Running() =>
            new InFlightStatusOutcome(
                GenerationLifecycleState.Running,
                new GenerationProgress(PercentComplete: 50, Message: "running"));

        public static ProviderStatusOutcome Complete(ProviderJobHandle handle) =>
            new ProviderCompleteStatusOutcome(handle);

        public static ProviderStatusOutcome StatusFailed(GenerationError error) =>
            new FailedStatusOutcome(error);

        public static ProviderResultOutcome ImageResult(byte[] bytes) =>
            new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[]
                    {
                        new ResultArtifact(
                            Role: ImageMediaRoles.Image,
                            Body: new InlineArtifactBody(bytes),
                            DeclaredMimeType: "image/png",
                            ProviderMetadata: EmptyMetadata),
                    },
                    EmptyMetadata));

        public static ProviderResultOutcome RemoteImageResult(
            string url,
            string? declaredMime = null,
            bool requiresAuthenticatedFetch = false) =>
            new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[]
                    {
                        new ResultArtifact(
                            Role: ImageMediaRoles.Image,
                            Body: new RemoteArtifactBody(new Uri(url)),
                            DeclaredMimeType: declaredMime,
                            ProviderMetadata: requiresAuthenticatedFetch
                                ? AuthFetchMetadata
                                : EmptyMetadata),
                    },
                    EmptyMetadata));

        public static ProviderResultOutcome ResultFailed(GenerationError error) =>
            new FailedResultOutcome(error);

        private static readonly IReadOnlyDictionary<string, JsonNode> EmptyMetadata
            = new Dictionary<string, JsonNode>();

        private static readonly IReadOnlyDictionary<string, JsonNode> AuthFetchMetadata
            = new Dictionary<string, JsonNode>
            {
                ["requires_authenticated_fetch"] = JsonValue.Create(true)!,
            };
    }
}
