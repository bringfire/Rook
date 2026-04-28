using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Gemini
{
    public sealed class GeminiImageProvider : IImageProvider
    {
        private const string ApiKeyHeader = "x-goog-api-key";
        private const string BaseUrl =
            "https://generativelanguage.googleapis.com/v1beta/models";

        private readonly Func<string?> _apiKeyProvider;
        private readonly HttpClient _httpClient;

        public GeminiImageProvider(Func<string?> apiKeyProvider, HttpClient? httpClient = null)
        {
            _apiKeyProvider = apiKeyProvider ?? throw new ArgumentNullException(nameof(apiKeyProvider));
            _httpClient = httpClient ?? new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
        }

        public string ProviderName => GeminiImageCapabilities.ProviderName;

        public async Task<ProviderSubmitOutcome> SubmitAsync(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            if (request is null)
                return Failed(GenerationErrorCode.InvalidRequest, "Request is null.", "request");

            if (request.Options is not GeminiImageOptions)
                return Failed(
                    GenerationErrorCode.InvalidRequest,
                    $"Gemini image provider requires {nameof(GeminiImageOptions)}; got " +
                    $"{request.Options?.GetType().Name ?? "null"}.",
                    "options");

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
            {
                return Failed(
                    GenerationErrorCode.DependencyUnavailable,
                    "Gemini API key is not configured. Set it via the Vision settings " +
                    "before calling /vision/generate.");
            }

            try
            {
                var url = $"{BaseUrl}/{request.Model}:generateContent";
                var bodyJson = BuildRequestJson(request, resolvedMedia);

                using var httpRequest = new HttpRequestMessage(HttpMethod.Post, url)
                {
                    Content = new StringContent(bodyJson, Encoding.UTF8, "application/json"),
                };
                httpRequest.Headers.Add(ApiKeyHeader, apiKey);

                var response = await _httpClient.SendAsync(httpRequest, ct)
                    .ConfigureAwait(false);
                var responseJson = await response.Content.ReadAsStringAsync()
                    .ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                    return new FailedSubmitOutcome(MapProviderError(response.StatusCode, responseJson));

                var result = ParseSuccess(responseJson);
                if (result is FailedSubmitOutcome failed) return failed;

                return result;
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return Failed(
                    GenerationErrorCode.Interrupted,
                    "Request cancelled (bridge timeout).");
            }
            catch (TaskCanceledException)
            {
                return Failed(
                    GenerationErrorCode.DependencyUnavailable,
                    "Request timed out. Try a simpler prompt or smaller resolution.",
                    retryable: true);
            }
            catch (HttpRequestException ex)
            {
                return Failed(
                    GenerationErrorCode.DependencyUnavailable,
                    $"Gemini image request failed: {ex.Message}",
                    retryable: true);
            }
        }

        public Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle, CancellationToken ct) =>
            throw new InvalidOperationException("Gemini image provider has no status step.");

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle, CancellationToken ct) =>
            throw new InvalidOperationException("Gemini image provider has no cancel step.");

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle, CancellationToken ct) =>
            throw new InvalidOperationException("Gemini image provider has no fetch step.");

        private static string BuildRequestJson(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia)
        {
            var parts = new List<object> { new { text = request.Prompt } };

            var referenceSet = new HashSet<MediaRef>();
            if (request.ReferenceImages is not null)
            {
                foreach (var mediaRef in request.ReferenceImages)
                {
                    referenceSet.Add(mediaRef);
                    if (resolvedMedia.TryGetValue(mediaRef, out var media))
                        parts.Add(InlineDataPart(media));
                }
            }

            foreach (var kvp in resolvedMedia)
            {
                if (!referenceSet.Contains(kvp.Key))
                    parts.Add(InlineDataPart(kvp.Value));
            }

            var requestDict = new Dictionary<string, object>
            {
                ["contents"] = new[]
                {
                    new Dictionary<string, object> { ["parts"] = parts },
                },
                ["generationConfig"] = new Dictionary<string, object>
                {
                    ["responseModalities"] = new[] { "IMAGE" },
                    ["imageConfig"] = BuildImageConfig(request.Resolution, request.AspectRatio),
                },
            };

            return JsonSerializer.Serialize(requestDict, new JsonSerializerOptions
            {
                DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            });
        }

        private static object InlineDataPart(ResolvedMedia media) =>
            new
            {
                inlineData = new
                {
                    mimeType = string.IsNullOrWhiteSpace(media.MimeType)
                        ? "image/png"
                        : media.MimeType,
                    data = Convert.ToBase64String(media.Bytes),
                },
            };

        private static Dictionary<string, object> BuildImageConfig(
            string resolution,
            string aspectRatio)
        {
            var imageConfig = new Dictionary<string, object>
            {
                ["imageSize"] = string.IsNullOrWhiteSpace(resolution)
                    ? "1K"
                    : resolution.ToUpperInvariant(),
            };

            if (!string.IsNullOrWhiteSpace(aspectRatio))
                imageConfig["aspectRatio"] = aspectRatio;

            return imageConfig;
        }

        private static ProviderSubmitOutcome ParseSuccess(string responseJson)
        {
            JsonNode? root;
            try { root = JsonNode.Parse(responseJson); }
            catch (JsonException ex)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    $"Gemini response was not valid JSON: {ex.Message}");
            }
            var rootObject = root as JsonObject;
            if (rootObject is null)
            {
                return SyncFailed(
                    GenerationErrorCode.ExecutionFailed,
                    "Gemini response root was not a JSON object.");
            }

            var artifacts = new List<ResultArtifact>();
            var candidates = rootObject["candidates"] as JsonArray;
            if (candidates is not null)
            {
                foreach (var candidateNode in candidates)
                {
                    if (candidateNode is not JsonObject candidate) continue;
                    var finishReason = CloneNode(candidate["finishReason"]);
                    var contentNode = candidate["content"];
                    if (contentNode is not null && contentNode is not JsonObject)
                    {
                        return SyncFailed(
                            GenerationErrorCode.ExecutionFailed,
                            "Gemini response candidate.content was not a JSON object.",
                            "candidates.content");
                    }

                    var content = contentNode as JsonObject;
                    var partsNode = content?["parts"];
                    if (partsNode is not null && partsNode is not JsonArray)
                    {
                        return SyncFailed(
                            GenerationErrorCode.ExecutionFailed,
                            "Gemini response candidate.content.parts was not an array.",
                            "candidates.content.parts");
                    }

                    var parts = partsNode as JsonArray;
                    if (parts is null) continue;

                    foreach (var partNode in parts)
                    {
                        var part = partNode as JsonObject;
                        if (part is null) continue;

                        var inlineNode = part["inlineData"];
                        if (inlineNode is not null && inlineNode is not JsonObject)
                        {
                            return SyncFailed(
                                GenerationErrorCode.ExecutionFailed,
                                "Gemini response part.inlineData was not a JSON object.",
                                "inlineData");
                        }

                        var inline = inlineNode as JsonObject;
                        if (inline is null) continue;

                        var dataNode = inline["data"];
                        if (dataNode is not null && !TryGetString(dataNode, out _))
                        {
                            return SyncFailed(
                                GenerationErrorCode.ExecutionFailed,
                                "Gemini response inlineData.data was not a string.",
                                "inlineData.data");
                        }

                        var data = TryGetString(dataNode, out var dataText)
                            ? dataText
                            : null;
                        if (string.IsNullOrEmpty(data)) continue;

                        byte[] bytes;
                        try { bytes = Convert.FromBase64String(data!); }
                        catch (FormatException)
                        {
                            return SyncFailed(
                                GenerationErrorCode.ExecutionFailed,
                                "Gemini response image was not valid base64.",
                                "inlineData.data");
                        }

                        var mimeNode = inline["mimeType"];
                        if (mimeNode is not null && !TryGetString(mimeNode, out _))
                        {
                            return SyncFailed(
                                GenerationErrorCode.ExecutionFailed,
                                "Gemini response inlineData.mimeType was not a string.",
                                "inlineData.mimeType");
                        }

                        var mime = TryGetString(mimeNode, out var mimeText)
                            ? mimeText
                            : "image/png";
                        var metadata = new Dictionary<string, JsonNode>();
                        if (finishReason is not null)
                            metadata["finishReason"] = finishReason;
                        var thoughtSignature = CloneNode(part?["thoughtSignature"]);
                        if (thoughtSignature is not null)
                            metadata["thoughtSignature"] = thoughtSignature;

                        artifacts.Add(new ResultArtifact(
                            Role: ImageMediaRoles.Image,
                            Body: new InlineArtifactBody(bytes),
                            DeclaredMimeType: mime,
                            ProviderMetadata: metadata));
                    }
                }
            }

            if (artifacts.Count == 0)
                return SyncFailed(GenerationErrorCode.ExecutionFailed, "No image in response");

            var envelopeMetadata = new Dictionary<string, JsonNode>();
            AddMetadata(rootObject, envelopeMetadata, "modelVersion");
            AddMetadata(rootObject, envelopeMetadata, "responseId");
            AddMetadata(rootObject, envelopeMetadata, "usageMetadata");

            return new SyncSubmitOutcome(
                new SuccessResultOutcome(
                    new ProviderResultEnvelope(artifacts, envelopeMetadata)));
        }

        private static GenerationError MapProviderError(HttpStatusCode status, string responseJson)
        {
            var code = status switch
            {
                HttpStatusCode.BadRequest => GenerationErrorCode.InvalidRequest,
                HttpStatusCode.Unauthorized => GenerationErrorCode.DependencyUnavailable,
                HttpStatusCode.Forbidden => GenerationErrorCode.DependencyUnavailable,
                (HttpStatusCode)429 => GenerationErrorCode.QuotaExceeded,
                _ when (int)status >= 500 => GenerationErrorCode.DependencyUnavailable,
                _ => GenerationErrorCode.ExecutionFailed,
            };

            JsonNode? root = null;
            try { root = JsonNode.Parse(responseJson); }
            catch { }

            var rootObject = root as JsonObject;
            var error = rootObject?["error"];
            var errorObject = error as JsonObject;
            var providerCode = TryGetString(errorObject?["status"], out var statusText)
                ? statusText
                : errorObject?["code"]?.ToJsonString();
            var message = TryGetString(errorObject?["message"], out var messageText)
                ? messageText
                : null;
            if (string.IsNullOrWhiteSpace(message))
                message = $"API Error ({status}): {responseJson}";

            var detail = new Dictionary<string, JsonNode>();
            if (root is not null)
                detail["error"] = CloneNode(error) ?? CloneNode(root)!;

            return new GenerationError(
                Code: code,
                Message: message!,
                Retryable: (int)status >= 500,
                ProviderErrorCode: providerCode,
                ProviderDetail: detail.Count == 0 ? null : detail);
        }

        private static ProviderSubmitOutcome Failed(
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

        private static void AddMetadata(
            JsonNode? root,
            IDictionary<string, JsonNode> metadata,
            string key)
        {
            var node = CloneNode(root?[key]);
            if (node is not null) metadata[key] = node;
        }

        private static JsonNode? CloneNode(JsonNode? node)
        {
            if (node is null) return null;
            return JsonNode.Parse(node.ToJsonString());
        }
    }
}
