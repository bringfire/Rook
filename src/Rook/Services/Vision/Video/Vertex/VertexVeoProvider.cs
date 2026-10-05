using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Generation.Vertex;
using Rook.Services.Vision.Image.Vertex;

namespace Rook.Services.Vision.Video.Vertex
{
    internal sealed class VertexVeoProvider : IModelAwareVideoProvider, IGenerationPublicationGuard, ILocalMonitoringProvider, ISubmissionDispatchAwareVideoProvider
    {
        internal const string ModelKey = "vertex_ai/veo-3.1-fast-generate-001";
        internal const string Location = "us-central1";
        private readonly IVertexAccessTokenSource _tokens;
        private readonly VertexVeoClient _client;
        private readonly Func<TimeSpan, CancellationToken, Task> _delay;
        private readonly TimeSpan _operationTimeout;
        internal VertexVeoProvider(IVertexAccessTokenSource tokens, VertexVeoClient? client = null,
            Func<TimeSpan, CancellationToken, Task>? delay = null, TimeSpan? operationTimeout = null)
        { _tokens = tokens; _client = client ?? new VertexVeoClient(); _delay = delay ?? Task.Delay;
            _operationTimeout = operationTimeout ?? VertexMediaTransport.OperationTimeout; }
        public string ProviderName => "vertex_ai";
        public Task<GenerationError?> ValidatePublicationAsync(IReadOnlyDictionary<string, JsonNode> metadata, CancellationToken ct)
            => VertexMediaTransport.ValidatePublicationAsync(_tokens, metadata, ct);
        public GenerationError SubmissionInterruptedError => VertexMediaTransport.UnknownSubmission() with
        { Code = GenerationErrorCode.Interrupted, Message = LocalStopOnlyOutcome.Message + " " + VertexMediaTransport.UnknownSubmission().Message };
        public Task<ProviderSubmitOutcome> SubmitAsync(VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia, CancellationToken ct) => SubmitCoreAsync(request,resolvedMedia,null,ct);
        public Task<ProviderSubmitOutcome> SubmitWithDispatchAsync(VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia, Action beforeDispatch, CancellationToken ct) => SubmitCoreAsync(request,resolvedMedia,beforeDispatch,ct);
        private async Task<ProviderSubmitOutcome> SubmitCoreAsync(VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia, Action? beforeDispatch, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var cap = VertexVeoProviderRegistration.Capability;
            if (request.Model != ModelKey || !CapabilityValidator.Validate(cap, request).Success
                || !new VertexVeoOptionsCodec().Validate(request, request.Options, cap).Success
                || request.StartFrame is not null && !resolvedMedia.ContainsKey(request.StartFrame)
                || request.EndFrame is not null && !resolvedMedia.ContainsKey(request.EndFrame)
                || request.ReferenceFrames?.Any(r => !resolvedMedia.ContainsKey(r)) == true
                || resolvedMedia.Values.Any(m => m.Bytes.Length > 20 * 1024 * 1024))
                return new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.InvalidRequest, "Invalid Vertex video request.", false));
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(VertexMediaTransport.OperationTimeout);
            var dispatched = false;
            try
            {
                var acquired = await _tokens.AcquireAsync(ModelKey, Location, null, deadline.Token).ConfigureAwait(false);
                if (acquired.Lease is not { } lease || !VertexMediaTransport.ValidLease(lease, ModelKey, Location))
                    return new FailedSubmitOutcome(VertexMediaTransport.TokenFailure(acquired.Failure, false));
                var response = await _client.SubmitAsync(lease, request, resolvedMedia, deadline.Token,
                    () => { beforeDispatch?.Invoke(); dispatched = true; }).ConfigureAwait(false);
                if (response.Error is not null) return new FailedSubmitOutcome(response.Error);
                // Retain the original accepted handle even when disconnect races submission; the manager fences publication.
                return new QueuedSubmitOutcome(new ProviderJobHandle(response.Operation!, providerMetadata: lease.Binding.ToMetadata()));
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch { return new FailedSubmitOutcome(dispatched ? VertexMediaTransport.UnknownSubmission() : VertexMediaTransport.TokenFailure(null, false)); }
        }
        private async Task<VertexVeoResponse> ReadAsync(string model, ProviderJobHandle handle, bool decode, CancellationToken ct)
        {
            var binding = VertexAuthorizationBinding.FromMetadata(handle.ProviderMetadata);
            if (model != ModelKey || binding is null || binding.ModelId != model || !VertexVeoClient.ValidOperation(binding, handle.ProviderJobId))
                return new(Error: VertexMediaTransport.Interrupted());
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(_operationTimeout);
            try
            {
                for (var attempt = 0; attempt < 3; attempt++)
                {
                    var acquired = await _tokens.AcquireAsync(model, Location, binding, deadline.Token).ConfigureAwait(false);
                    if (acquired.Lease is not { } lease || !VertexMediaTransport.ValidLease(lease, model, Location, binding))
                        return new(Error: VertexMediaTransport.TokenFailure(acquired.Failure, true));
                    var response = await _client.FetchOperationAsync(lease, handle.ProviderJobId, decode, deadline.Token).ConfigureAwait(false);
                    if (await _tokens.ValidateBindingAsync(binding, deadline.Token).ConfigureAwait(false) is not null)
                        return new(Error: VertexMediaTransport.Interrupted());
                    if (!response.RetryableRead || attempt == 2) return response;
                    await _delay(TimeSpan.FromSeconds(attempt + 1), deadline.Token).ConfigureAwait(false);
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (OperationCanceledException) when (deadline.IsCancellationRequested)
            { return new(Error: VertexMediaTransport.MonitoringTimeout()); }
            catch { }
            return new(Error: new GenerationError(GenerationErrorCode.DependencyUnavailable, "Google video operation could not be read.", false));
        }
        public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct) => GetStatusAsync(ModelKey, handle, ct);
        public async Task<ProviderStatusOutcome> GetStatusAsync(string modelId, ProviderJobHandle handle, CancellationToken ct)
        {
            var response = await ReadAsync(modelId, handle, false, ct).ConfigureAwait(false);
            if (response.Error is not null) return new FailedStatusOutcome(response.Error);
            return response.Done ? new ProviderCompleteStatusOutcome(handle) : new InFlightStatusOutcome(GenerationLifecycleState.Running, null);
        }
        public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct) => FetchResultAsync(ModelKey, handle, ct);
        public async Task<ProviderResultOutcome> FetchResultAsync(string modelId, ProviderJobHandle handle, CancellationToken ct)
        {
            var response = await ReadAsync(modelId, handle, true, ct).ConfigureAwait(false);
            if (response.Error is not null) return new FailedResultOutcome(response.Error);
            if (!response.Done || response.Video is null) return new FailedResultOutcome(VertexMediaTransport.InvalidOutput());
            var metadata = VertexAuthorizationBinding.FromMetadata(handle.ProviderMetadata)!.ToMetadata();
            return new SuccessResultOutcome(new ProviderResultEnvelope(new[]
            {
                new ResultArtifact(VideoMediaRoles.Video, new InlineArtifactBody(response.Video), "video/mp4", metadata),
            }, metadata));
        }
        public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) => Task.FromResult<ProviderCancelOutcome>(new LocalStopOnlyOutcome());
        public Task<ProviderCancelOutcome> CancelAsync(string modelId, ProviderJobHandle handle, CancellationToken ct) => CancelAsync(handle, ct);
    }
}
