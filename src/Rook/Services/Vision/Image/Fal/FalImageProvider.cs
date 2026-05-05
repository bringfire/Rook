using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class FalImageProvider : IModelAwareImageProvider
    {
        private static readonly Uri FluxSchnellEndpoint =
            new("https://fal.run/fal-ai/flux/schnell");
        private static readonly Uri GptImage2EditQueueEndpoint =
            new("https://queue.fal.run/openai/gpt-image-2/edit");
        private const string GptImage2EditLifecycleRouteBase =
            "https://queue.fal.run/openai/gpt-image-2/requests";
        private const string GptImage2EditCancelHttpMethod = "PUT";

        private readonly Func<string?> _apiKeyProvider;
        private readonly FalApiClient _client;

        public FalImageProvider(Func<string?> apiKeyProvider, FalApiClient? client = null)
        {
            _apiKeyProvider = apiKeyProvider
                ?? throw new ArgumentNullException(nameof(apiKeyProvider));
            _client = client ?? new FalApiClient();
        }

        public string ProviderName => FalImageCapabilities.ProviderName;

        public async Task<ProviderSubmitOutcome> SubmitAsync(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            CancellationToken ct)
        {
            if (request is null)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "Request is null.",
                    "request");

            if (request.Options is not FalImageOptions)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    $"fal image provider requires {nameof(FalImageOptions)}; got " +
                    $"{request.Options?.GetType().Name ?? "null"}.",
                    "options");

            var isGptImage2Edit = string.Equals(
                request.Model,
                FalImageCapabilities.GptImage2Edit,
                StringComparison.Ordinal);
            var isFluxSchnell = string.Equals(
                request.Model,
                FalImageCapabilities.FluxSchnell,
                StringComparison.Ordinal);
            if (!isGptImage2Edit && !isFluxSchnell)
            {
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    $"fal image provider does not support model '{request.Model}'.",
                    "model");
            }

            FalGptImage2EditSourcePayload? gptSourcePayload = null;
            if (isGptImage2Edit)
            {
                var source = FalGptImage2EditSourcePayload.FromResolvedMedia(media);
                if (source.Error is not null)
                    return new FailedSubmitOutcome(source.Error);
                gptSourcePayload = source.Payload;
            }

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal API key is not configured. Set it via the Vision settings " +
                    "before calling /vision/generate.");
            }

            string bodyJson;
            Uri endpoint;
            try
            {
                if (isGptImage2Edit)
                {
                    bodyJson = BuildGptImage2EditRequestJson(
                        request,
                        gptSourcePayload);
                    endpoint = GptImage2EditQueueEndpoint;
                }
                else
                {
                    bodyJson = BuildRequestJson(request);
                    endpoint = FluxSchnellEndpoint;
                }
            }
            catch (ArgumentException)
            {
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "fal image request has an unsupported aspect ratio.",
                    "aspect_ratio");
            }

            FalHttpResponse response;
            try
            {
                response = await _client.PostJsonAsync(apiKey!, endpoint, bodyJson, ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return FailedSubmit(
                    GenerationErrorCode.Interrupted,
                    "Request cancelled (bridge timeout).");
            }
            catch (TaskCanceledException)
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal image request timed out. Try again.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal image request failed due to a transport error.",
                    retryable: true);
            }

            if (!response.IsSuccessStatusCode)
                return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(response));

            if (isGptImage2Edit)
            {
                return ParseGptImage2EditSubmit(response.Body);
            }

            return ParseSuccess(response.Body);
        }

        public Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct) =>
            throw new InvalidOperationException("fal sync image provider has no status step.");

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken ct) =>
            throw new InvalidOperationException("fal sync image provider has no cancel step.");

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct) =>
            throw new InvalidOperationException("fal sync image provider has no fetch step.");

        public Task<ProviderStatusOutcome> GetStatusAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (!string.Equals(
                    modelId,
                    FalImageCapabilities.GptImage2Edit,
                    StringComparison.Ordinal))
            {
                return Task.FromResult<ProviderStatusOutcome>(FailedStatus(
                    GenerationErrorCode.InvalidRequest,
                    $"fal image provider does not support async status for model '{modelId}'.",
                    "model"));
            }

            return GetGptImage2EditStatusAsync(handle, ct);
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (!string.Equals(
                    modelId,
                    FalImageCapabilities.GptImage2Edit,
                    StringComparison.Ordinal))
            {
                return Task.FromResult<ProviderCancelOutcome>(FailedCancel(
                    GenerationErrorCode.InvalidRequest,
                    $"fal image provider does not support async cancel for model '{modelId}'.",
                    "model"));
            }

            return CancelGptImage2EditAsync(handle, ct);
        }

        public Task<ProviderResultOutcome> FetchResultAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (!string.Equals(
                    modelId,
                    FalImageCapabilities.GptImage2Edit,
                    StringComparison.Ordinal))
            {
                return Task.FromResult<ProviderResultOutcome>(FailedResult(
                    GenerationErrorCode.InvalidRequest,
                    $"fal image provider does not support async result fetch for model '{modelId}'.",
                    "model"));
            }

            return FetchGptImage2EditResultAsync(handle, ct);
        }

        private static string BuildRequestJson(ImageGenerationRequest request)
        {
            var body = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["image_size"] = FalImageOptionsCodec.ToFalImageSize(request.AspectRatio),
                ["num_images"] = 1,
                ["enable_safety_checker"] = true,
                ["output_format"] = "jpeg",
                ["sync_mode"] = false,
            };

            return body.ToJsonString();
        }

        private static string BuildGptImage2EditRequestJson(
            ImageGenerationRequest request,
            FalGptImage2EditSourcePayload? sourcePayload)
        {
            if (sourcePayload is null)
                throw new InvalidOperationException(
                    "GPT Image 2 Edit source payload was not prepared.");

            return new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["image_urls"] = new JsonArray { sourcePayload.DataUri },
                ["image_size"] = "auto",
                ["quality"] = "high",
                ["num_images"] = 1,
                ["output_format"] = "png",
            }.ToJsonString();
        }

        private static ProviderSubmitOutcome ParseGptImage2EditSubmit(
            string responseJson)
        {
            try
            {
                var root = JsonNode.Parse(responseJson) as JsonObject
                    ?? throw new JsonException();
                if (!TryGetString(root["request_id"], out var requestId)
                    || string.IsNullOrWhiteSpace(requestId))
                {
                    return FailedSubmit(
                        GenerationErrorCode.ExecutionFailed,
                        "fal submit response was missing request id.");
                }

                if (!IsSafeFalRequestId(requestId))
                {
                    return FailedSubmit(
                        GenerationErrorCode.ExecutionFailed,
                        "fal submit response contained an invalid request id.",
                        "provider_job_id");
                }

                return new QueuedSubmitOutcome(new ProviderJobHandle(requestId!));
            }
            catch (JsonException)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    "fal submit response was not valid JSON.");
            }
        }

        private async Task<ProviderStatusOutcome> GetGptImage2EditStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedStatus(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    nameof(handle));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return FailedStatus(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal API key is not configured.");

            FalHttpResponse response;
            try
            {
                response = await _client.GetAsync(
                    apiKey!,
                    GptImage2EditRequestUri(handle.ProviderJobId, "status"),
                    ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (TaskCanceledException)
            {
                return FailedStatus(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal status request timed out.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedStatus(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal status request failed due to a transport error.",
                    retryable: true);
            }

            if (!response.IsSuccessStatusCode)
                return new FailedStatusOutcome(FalErrorMapper.MapHttpFailure(response));

            try
            {
                var root = JsonNode.Parse(response.Body);
                return root is null
                    ? FailedStatus(
                        GenerationErrorCode.ExecutionFailed,
                        "fal status response was empty.")
                    : FalLifecycleMapper.MapStatus(handle, root);
            }
            catch (JsonException)
            {
                return FailedStatus(
                    GenerationErrorCode.ExecutionFailed,
                    "fal status response was not valid JSON.");
            }
        }

        private async Task<ProviderCancelOutcome> CancelGptImage2EditAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedCancel(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    nameof(handle));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return FailedCancel(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal API key is not configured.");

            FalHttpResponse response;
            try
            {
                response = await _client.SendAsync(
                    apiKey!,
                    new HttpMethod(GptImage2EditCancelHttpMethod),
                    GptImage2EditRequestUri(handle.ProviderJobId, "cancel"),
                    bodyJson: null,
                    ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (TaskCanceledException)
            {
                return FailedCancel(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal cancel request timed out.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedCancel(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal cancel request failed due to a transport error.",
                    retryable: true);
            }

            if (response.StatusCode == 202 || response.IsSuccessStatusCode)
                return new CanceledOutcome();

            if (response.StatusCode == 400)
                return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);

            return new FailedCancelOutcome(FalErrorMapper.MapHttpFailure(response));
        }

        private async Task<ProviderResultOutcome> FetchGptImage2EditResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedResult(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    nameof(handle));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return FailedResult(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal API key is not configured.");

            FalHttpResponse response;
            try
            {
                response = await _client.GetAsync(
                    apiKey!,
                    GptImage2EditResultUri(handle.ProviderJobId),
                    ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (TaskCanceledException)
            {
                return FailedResult(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal result fetch timed out.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedResult(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal result fetch failed due to a transport error.",
                    retryable: true);
            }

            if (!response.IsSuccessStatusCode)
                return new FailedResultOutcome(FalErrorMapper.MapHttpFailure(response));

            return ParseGptImage2EditResult(response.Body);
        }

        private static ProviderResultOutcome ParseGptImage2EditResult(string body)
        {
            JsonObject root;
            try
            {
                root = JsonNode.Parse(body) as JsonObject
                    ?? throw new JsonException();
            }
            catch (JsonException)
            {
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal result response was not valid JSON.");
            }

            if (root["images"] is not JsonArray images || images.Count != 1)
            {
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal result response must contain exactly one image.",
                    "images");
            }

            if (images[0] is not JsonObject firstImage)
            {
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal result image was not an object.",
                    "images");
            }

            if (!TryGetString(firstImage["url"], out var urlText)
                || !Uri.TryCreate(urlText, UriKind.Absolute, out var url)
                || (url.Scheme != Uri.UriSchemeHttp
                    && url.Scheme != Uri.UriSchemeHttps))
            {
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal result image URL was missing or invalid.",
                    "images.url");
            }

            var artifact = new ResultArtifact(
                Role: ImageMediaRoles.Image,
                Body: new RemoteArtifactBody(url),
                DeclaredMimeType:
                    TryGetString(firstImage["content_type"], out var contentType)
                        ? contentType
                        : null,
                ProviderMetadata: new Dictionary<string, JsonNode>());

            return new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[] { artifact },
                    new Dictionary<string, JsonNode>()));
        }

        private static Uri GptImage2EditRequestUri(
            string requestId,
            string suffix) =>
            new(
                $"{GptImage2EditLifecycleRouteBase}/" +
                $"{Uri.EscapeDataString(requestId)}/{suffix}");

        private static Uri GptImage2EditResultUri(string requestId) =>
            new(
                $"{GptImage2EditLifecycleRouteBase}/" +
                $"{Uri.EscapeDataString(requestId)}");

        private static ProviderSubmitOutcome ParseSuccess(string responseJson)
        {
            JsonNode? root;
            try
            {
                root = JsonNode.Parse(responseJson);
            }
            catch (JsonException ex)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    $"fal response was not valid JSON: {ex.Message}");
            }

            if (root is not JsonObject rootObject)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    "fal response root was not a JSON object.");
            }

            var imagesNode = rootObject["images"];
            if (imagesNode is not JsonArray images)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    "fal response images was not an array.",
                    "images");
            }

            if (images.Count == 0)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    "fal response images was empty.",
                    "images");
            }

            if (images[0] is not JsonObject firstImage)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    "fal response images[0] was not an object.",
                    "images");
            }

            if (!TryGetString(firstImage["url"], out var urlText)
                || string.IsNullOrWhiteSpace(urlText)
                || !Uri.TryCreate(urlText, UriKind.Absolute, out var uri))
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    "fal response image url was missing or invalid.",
                    "images.url");
            }

            if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    "fal response image url must use http or https.",
                    "images.url");
            }

            var artifactMetadata = new Dictionary<string, JsonNode>
            {
                ["url"] = urlText!,
            };
            AddMetadata(firstImage, artifactMetadata, "width");
            AddMetadata(firstImage, artifactMetadata, "height");

            var declaredMimeType = TryGetString(firstImage["content_type"], out var contentType)
                && !string.IsNullOrWhiteSpace(contentType)
                    ? contentType
                    : null;

            var artifact = new ResultArtifact(
                Role: ImageMediaRoles.Image,
                Body: new RemoteArtifactBody(uri),
                DeclaredMimeType: declaredMimeType,
                ProviderMetadata: artifactMetadata);

            var envelopeMetadata = new Dictionary<string, JsonNode>();
            AddMetadata(rootObject, envelopeMetadata, "seed");
            AddMetadata(rootObject, envelopeMetadata, "prompt");
            AddMetadata(rootObject, envelopeMetadata, "timings");
            AddMetadata(rootObject, envelopeMetadata, "has_nsfw_concepts");

            return new SyncSubmitOutcome(
                new SuccessResultOutcome(
                    new ProviderResultEnvelope(
                        new[] { artifact },
                        envelopeMetadata)));
        }

        private static ProviderSubmitOutcome FailedSubmit(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new FailedSubmitOutcome(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));

        private static ProviderSubmitOutcome SyncFailed(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new SyncSubmitOutcome(
                new FailedResultOutcome(new GenerationError(
                    Code: code,
                    Message: message,
                    Retryable: retryable,
                    Field: field)));

        private static ProviderStatusOutcome FailedStatus(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new FailedStatusOutcome(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));

        private static ProviderCancelOutcome FailedCancel(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new FailedCancelOutcome(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));

        private static ProviderResultOutcome FailedResult(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new FailedResultOutcome(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));

        private static void AddMetadata(
            JsonObject source,
            IDictionary<string, JsonNode> metadata,
            string key)
        {
            var node = source[key]?.DeepClone();
            if (node is not null)
                metadata[key] = node;
        }

        private static bool TryGetString(JsonNode? node, out string? value)
        {
            value = null;
            if (node is null) return false;
            try
            {
                value = node.GetValue<string>();
                return true;
            }
            catch
            {
                return false;
            }
        }

        private static bool IsSafeFalRequestId(string? requestId)
        {
            if (string.IsNullOrWhiteSpace(requestId))
                return false;
            if (!string.Equals(requestId, requestId!.Trim(), StringComparison.Ordinal))
                return false;
            if (requestId.Length > 128)
                return false;

            foreach (var ch in requestId)
            {
                if ((ch >= 'a' && ch <= 'z')
                    || (ch >= 'A' && ch <= 'Z')
                    || (ch >= '0' && ch <= '9')
                    || ch == '-'
                    || ch == '_')
                {
                    continue;
                }

                return false;
            }

            return true;
        }
    }
}
