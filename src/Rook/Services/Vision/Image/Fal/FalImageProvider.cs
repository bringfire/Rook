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
    public sealed class FalImageProvider : IImageProvider
    {
        private static readonly Uri Endpoint =
            new("https://fal.run/fal-ai/flux/schnell");

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

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal API key is not configured. Set it via the Vision settings " +
                    "before calling /vision/generate.");
            }

            string bodyJson;
            try
            {
                bodyJson = BuildRequestJson(request);
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
                response = await _client.PostJsonAsync(apiKey!, Endpoint, bodyJson, ct)
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
    }
}
