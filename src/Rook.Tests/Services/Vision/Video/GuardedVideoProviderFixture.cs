using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;

namespace Rook.Tests.Services.Vision.Video
{
    internal sealed class GuardedVideoProviderFixture : IVideoProvider, IGenerationPublicationGuard, ILocalMonitoringProvider
    {
        public string ProviderName => "guarded";
        public readonly TaskCompletionSource<bool> Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public readonly TaskCompletionSource<bool> Release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public string BlockAt = "fetch";
        public bool Authorized = true;
        public bool FailStatus;
        public bool MissingBinding;
        public int Calls;
        public int GuardCalls;
        public static readonly IReadOnlyDictionary<string, JsonNode> Metadata = new Dictionary<string, JsonNode>
        { ["vertex_binding"] = new JsonObject { ["authorization_generation"] = "original-generation" } };
        private async Task Barrier(string phase)
        { if (BlockAt == phase) { Entered.TrySetResult(true); await Release.Task; } }
        public async Task<ProviderSubmitOutcome> SubmitAsync(VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolved, CancellationToken ct)
        { Calls++; await Barrier("submit"); return new QueuedSubmitOutcome(new ProviderJobHandle("original-operation", providerMetadata: Metadata)); }
        public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct)
        { Calls++; return Task.FromResult<ProviderStatusOutcome>(FailStatus ? new FailedStatusOutcome(new GenerationError(GenerationErrorCode.Interrupted, "Authorization changed.", false)) : new ProviderCompleteStatusOutcome(handle)); }
        public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) => Task.FromResult<ProviderCancelOutcome>(new LocalStopOnlyOutcome());
        public async Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            Calls++; await Barrier("fetch");
            return new SuccessResultOutcome(new ProviderResultEnvelope(new[] { new ResultArtifact(VideoMediaRoles.Video, new InlineArtifactBody(new byte[] {0,0,0,24,102,116,121,112}), "video/mp4", Metadata) }, MissingBinding ? new Dictionary<string,JsonNode>() : Metadata));
        }
        public async Task<GenerationError?> ValidatePublicationAsync(IReadOnlyDictionary<string, JsonNode> metadata, CancellationToken ct)
        {
            await Barrier("guard" + Interlocked.Increment(ref GuardCalls));
            ct.ThrowIfCancellationRequested();
            return Authorized && metadata.ContainsKey("vertex_binding") ? null : new GenerationError(GenerationErrorCode.Interrupted,"Authorization changed.",false);
        }
    }
}
