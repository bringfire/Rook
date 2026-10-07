using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Generation.Vertex;
using Rook.Services.Vision.Image.Gemini;

namespace Rook.Services.Vision.Image.Vertex
{
    internal sealed class VertexImageProvider : IImageProvider, IGenerationPublicationGuard
    {
        internal const string ModelKey = "vertex_ai/gemini-3.1-flash-image";
        internal const string Location = "global";
        internal const int MaxDecodedBytes = 25 * 1024 * 1024;
        private readonly IVertexAccessTokenSource _tokens;
        private readonly VertexMediaTransport _transport;
        internal VertexImageProvider(IVertexAccessTokenSource tokens, HttpClient? http = null)
        { _tokens = tokens; _transport = new VertexMediaTransport(http); }
        public string ProviderName => "vertex_ai";

        public async Task<ProviderSubmitOutcome> SubmitAsync(ImageGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia, CancellationToken ct)
        {
            if (request is null || request.Model != ModelKey || request.Options is not GeminiImageOptions)
                return new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.InvalidRequest, "Select a registered Google Enterprise image model and options.", false));
            var validation = new GeminiImageOptionsCodec().Validate(request, request.Options, VertexImageProviderRegistration.Capability);
            if (!validation.Success) return new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.InvalidRequest, validation.Message!, false));
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(VertexMediaTransport.OperationTimeout);
            bool dispatched = false;
            try
            {
                var token = await _tokens.AcquireAsync(ModelKey, Location, null, deadline.Token).ConfigureAwait(false);
                if (token.Lease is null) return new FailedSubmitOutcome(VertexMediaTransport.TokenFailure(token.Failure, false));
                var lease = token.Lease;
                if (!VertexMediaTransport.ValidLease(lease, ModelKey, Location)) return new FailedSubmitOutcome(VertexMediaTransport.Interrupted());
                var response = await _transport.PostAsync(lease, "generateContent",
                    GeminiImageProvider.BuildRequestJson(request, resolvedMedia), 4L * ((MaxDecodedBytes + 2L) / 3) + VertexMediaTransport.SmallResponseLimit, true, deadline.Token,
                    beforeDispatch: () => dispatched = true,
                    validateDispatch: token => ValidatePublicationAsync(lease.Binding.ToMetadata(), token)).ConfigureAwait(false);
                if (response.Error is not null) return new FailedSubmitOutcome(response.Error);
                var error = await ValidatePublicationAsync(lease.Binding.ToMetadata(), deadline.Token).ConfigureAwait(false);
                if (error is not null) return new FailedSubmitOutcome(error);
                return ParseSuccess(response.Body!, lease.Binding);
            }
            catch (System.OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch
            {
                return new FailedSubmitOutcome(dispatched ? VertexMediaTransport.UnknownSubmission() : VertexMediaTransport.TokenFailure(null,false));
            }
        }

        private static ProviderSubmitOutcome ParseSuccess(byte[] body, VertexAuthorizationBinding binding)
        {
            try
            {
                if (!VertexMediaTransport.ValidateEncodedFields(body, "data", MaxDecodedBytes)) return new FailedSubmitOutcome(VertexMediaTransport.InvalidOutput());
                using var document = JsonDocument.Parse(body);
                var artifacts = new List<ResultArtifact>();
                foreach (var candidate in document.RootElement.GetProperty("candidates").EnumerateArray())
                {
                    if (candidate.TryGetProperty("finishReason", out var reason) && reason.GetString() is "SAFETY" or "IMAGE_SAFETY")
                        return new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.ContentPolicy, "Google blocked this image under its content policy.", false));
                    foreach (var part in candidate.GetProperty("content").GetProperty("parts").EnumerateArray())
                    {
                        if (!part.TryGetProperty("inlineData", out var inline)) continue;
                        var mime = inline.GetProperty("mimeType").GetString();
                        if (mime is not ("image/png" or "image/jpeg" or "image/webp")) return new FailedSubmitOutcome(VertexMediaTransport.InvalidOutput());
                        var bytes = inline.GetProperty("data").GetBytesFromBase64();
                        if (bytes.Length == 0 || bytes.Length > MaxDecodedBytes) return new FailedSubmitOutcome(VertexMediaTransport.InvalidOutput());
                        artifacts.Add(new ResultArtifact(ImageMediaRoles.Image, new InlineArtifactBody(bytes), mime, binding.ToMetadata()));
                    }
                }
                if (artifacts.Count != 1) return new FailedSubmitOutcome(VertexMediaTransport.InvalidOutput());
                return new SyncSubmitOutcome(new SuccessResultOutcome(new ProviderResultEnvelope(artifacts, binding.ToMetadata())));
            }
            catch { return new FailedSubmitOutcome(VertexMediaTransport.UnknownSubmission()); }
        }
        public Task<GenerationError?> ValidatePublicationAsync(IReadOnlyDictionary<string, JsonNode> metadata, CancellationToken ct) => VertexMediaTransport.ValidatePublicationAsync(_tokens, metadata, ct);
        public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct) => Task.FromResult<ProviderStatusOutcome>(new FailedStatusOutcome(VertexMediaTransport.InvalidOutput()));
        public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) => Task.FromResult<ProviderCancelOutcome>(new LocalStopOnlyOutcome());
        public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct) => Task.FromResult<ProviderResultOutcome>(new FailedResultOutcome(VertexMediaTransport.InvalidOutput()));
    }
}
