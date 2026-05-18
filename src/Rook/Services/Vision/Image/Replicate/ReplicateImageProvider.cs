using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImageProvider : IImageProvider
    {
        private static readonly ReplicatePredictionEndpoint FluxSchnellEndpoint =
            ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", "flux-schnell");

        private static readonly ReplicatePredictionEndpoint Flux2ProEndpoint =
            ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", "flux-2-pro");

        private readonly Func<string?> _apiTokenProvider;
        private readonly ReplicateApiClient _client;
        private readonly IReplicateFileTransport _fileTransport;
        private readonly ReplicateImageOptionsCodec _codec = new();

        public ReplicateImageProvider(
            Func<string?> apiTokenProvider,
            ReplicateApiClient? client = null)
            : this(apiTokenProvider, client, fileTransport: null)
        {
        }

        internal ReplicateImageProvider(
            Func<string?> apiTokenProvider,
            ReplicateApiClient? client,
            IReplicateFileTransport? fileTransport)
        {
            _apiTokenProvider = apiTokenProvider
                ?? throw new ArgumentNullException(nameof(apiTokenProvider));
            _client = client ?? new ReplicateApiClient();
            _fileTransport = fileTransport ?? new ReplicateFileTransport(_client);
        }

        public string ProviderName => ReplicateImageCapabilities.ProviderName;

        public async Task<ProviderSubmitOutcome> SubmitAsync(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            if (request is null)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "Request is null.",
                    "request");

            if (!ReplicateImageCapabilities.Models.TryGetValue(request.Model, out var capability))
            {
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    $"Unknown Replicate image model '{request.Model}'.",
                    "model");
            }

            var validationRequest = NormalizeFlux2ValidationRequest(request);
            var validation = _codec.Validate(
                validationRequest,
                request.Options,
                capability);
            if (!validation.Success)
            {
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    validation.Message ?? "Replicate image request is invalid.",
                    validation.Field);
            }

            ReplicateImageSourcePayload? sourcePayload = null;
            if (string.Equals(request.Model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal))
            {
                var payload = ReplicateImageSourcePayload.FromResolvedMedia(request, resolvedMedia);
                if (payload.Error is not null)
                    return new FailedSubmitOutcome(payload.Error);
                sourcePayload = payload.Payload;
            }

            var apiToken = _apiTokenProvider();
            if (string.IsNullOrWhiteSpace(apiToken))
                return new FailedSubmitOutcome(ReplicateErrorMapper.MissingToken());

            IReadOnlyList<string>? flux2InputImages = null;
            if (sourcePayload is not null && sourcePayload.InputImages.Count > 0)
            {
                var inputImages = new List<string>(sourcePayload.InputImages.Count);
                foreach (var inputImage in sourcePayload.InputImages)
                {
                    ReplicateFileUploadResult upload;
                    try
                    {
                        upload = await _fileTransport.UploadAsync(
                                apiToken!,
                                BuildFlux2InputFileName(inputImage.MimeType),
                                inputImage.Bytes,
                                inputImage.MimeType,
                                ct)
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
                            "Replicate file upload timed out. Try again.",
                            retryable: true);
                    }
                    catch (HttpRequestException)
                    {
                        return FailedSubmit(
                            GenerationErrorCode.DependencyUnavailable,
                            "Replicate file upload failed due to a transport error.",
                            retryable: true);
                    }
                    catch (ArgumentException)
                    {
                        return FailedSubmit(
                            GenerationErrorCode.ExecutionFailed,
                            "Replicate file upload failed before it could be sent.");
                    }
                    catch (Exception)
                    {
                        return FailedSubmit(
                            GenerationErrorCode.ExecutionFailed,
                            "Replicate file upload failed before the prediction could be created.");
                    }

                    if (!upload.Success || upload.Url is null)
                    {
                        return new FailedSubmitOutcome(
                            upload.Error ?? Flux2UploadFailed());
                    }

                    inputImages.Add(upload.Url.ToString());
                }

                flux2InputImages = inputImages;
            }

            ReplicateHttpResponse response;
            try
            {
                response = await _client.CreatePredictionAsync(
                        apiToken!,
                        EndpointForModel(request.Model),
                        BuildRequestJson(request, flux2InputImages),
                        ct)
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
                    "Replicate image request timed out. Try again.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate image request failed due to a transport error.",
                    retryable: true);
            }
            catch (ArgumentException)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate image request failed before it could be sent.");
            }

            if (!response.IsSuccessStatusCode)
                return new FailedSubmitOutcome(ReplicateErrorMapper.MapHttpFailure(response));

            try
            {
                var body = ParseJson(response.Body);
                return new QueuedSubmitOutcome(
                    ReplicateLifecycleMapper.ParseSubmitHandle(body));
            }
            catch (ArgumentException)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate submit response could not be mapped.");
            }
            catch (JsonException)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate submit response was not valid JSON.");
            }
        }

        public async Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedStatus(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    "handle");

            var apiToken = _apiTokenProvider();
            if (string.IsNullOrWhiteSpace(apiToken))
                return new FailedStatusOutcome(ReplicateErrorMapper.MissingToken());

            ReplicateHttpResponse response;
            try
            {
                response = await _client.GetPredictionAsync(
                        apiToken!,
                        handle.ProviderJobId,
                        ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return FailedStatus(
                    GenerationErrorCode.Interrupted,
                    "Request cancelled (bridge timeout).");
            }
            catch (TaskCanceledException)
            {
                return FailedStatus(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate status request timed out. Try again.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedStatus(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate status request failed due to a transport error.",
                    retryable: true);
            }
            catch (ArgumentException)
            {
                return FailedStatus(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate status request failed before it could be sent.");
            }

            if (!response.IsSuccessStatusCode)
                return new FailedStatusOutcome(ReplicateErrorMapper.MapHttpFailure(response));

            try
            {
                return ReplicateLifecycleMapper.MapStatus(
                    handle,
                    ParseJson(response.Body));
            }
            catch (ArgumentException)
            {
                return FailedStatus(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate status response could not be mapped.");
            }
            catch (JsonException)
            {
                return FailedStatus(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate status response was not valid JSON.");
            }
        }

        public async Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedCancel(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    "handle");

            var apiToken = _apiTokenProvider();
            if (string.IsNullOrWhiteSpace(apiToken))
                return new FailedCancelOutcome(ReplicateErrorMapper.MissingToken());

            ReplicateHttpResponse response;
            try
            {
                response = await _client.CancelPredictionAsync(
                        apiToken!,
                        handle.ProviderJobId,
                        ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return FailedCancel(
                    GenerationErrorCode.Interrupted,
                    "Request cancelled (bridge timeout).");
            }
            catch (TaskCanceledException)
            {
                return FailedCancel(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate cancel request timed out. Try again.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedCancel(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate cancel request failed due to a transport error.",
                    retryable: true);
            }
            catch (ArgumentException)
            {
                return FailedCancel(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate cancel request failed before it could be sent.");
            }

            return response.IsSuccessStatusCode
                ? new CanceledOutcome()
                : new FailedCancelOutcome(ReplicateErrorMapper.MapHttpFailure(response));
        }

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
            {
                return Task.FromResult<ProviderResultOutcome>(
                    FailedResult(
                        GenerationErrorCode.InvalidRequest,
                        "ProviderJobHandle is required.",
                        "handle"));
            }

            if (handle.ProviderMetadata is null
                || !handle.ProviderMetadata.TryGetValue("output", out var output)
                || !TrySelectOutputMetadataUrl(output, out var outputUrl)
                || !TrySelectMaterializableOutputUrl(handle, out var tokenUrl)
                || !string.Equals(
                    outputUrl.AbsoluteUri,
                    tokenUrl.AbsoluteUri,
                    StringComparison.Ordinal))
            {
                return Task.FromResult<ProviderResultOutcome>(
                    FailedResult(
                        GenerationErrorCode.ExecutionFailed,
                        "Replicate image result must contain exactly one image URL."));
            }

            var artifactMetadata = new Dictionary<string, JsonNode>
            {
                ["url"] = outputUrl.ToString(),
                ["requires_authenticated_fetch"] = true,
            };

            var artifact = new ResultArtifact(
                Role: ImageMediaRoles.Image,
                Body: new RemoteArtifactBody(outputUrl),
                DeclaredMimeType: null,
                ProviderMetadata: artifactMetadata);

            return Task.FromResult<ProviderResultOutcome>(
                new SuccessResultOutcome(
                    new ProviderResultEnvelope(
                        new[] { artifact },
                        CopyMetadata(handle.ProviderMetadata))));
        }

        private static ReplicatePredictionEndpoint EndpointForModel(string model) =>
            string.Equals(model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal)
                ? Flux2ProEndpoint
                : FluxSchnellEndpoint;

        private static ImageGenerationRequest NormalizeFlux2ValidationRequest(ImageGenerationRequest request)
        {
            if (!string.Equals(request.Model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal)
                || !string.IsNullOrWhiteSpace(request.Resolution))
            {
                return request;
            }

            return request with { Resolution = "1 MP" };
        }

        private static string BuildRequestJson(
            ImageGenerationRequest request,
            IReadOnlyList<string>? flux2InputImages)
        {
            if (string.Equals(request.Model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal))
                return BuildFlux2ProRequestJson(request, flux2InputImages);

            return BuildFluxSchnellRequestJson(request);
        }

        private static string BuildFluxSchnellRequestJson(ImageGenerationRequest request)
        {
            var input = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["aspect_ratio"] = string.IsNullOrWhiteSpace(request.AspectRatio)
                    ? "1:1"
                    : request.AspectRatio,
                ["num_outputs"] = 1,
                ["output_format"] = "png",
            };

            return new JsonObject
            {
                ["input"] = input,
            }.ToJsonString();
        }

        private static string BuildFlux2ProRequestJson(
            ImageGenerationRequest request,
            IReadOnlyList<string>? inputImageUrls)
        {
            var input = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["output_format"] = "png",
            };

            if (inputImageUrls is not null && inputImageUrls.Count > 0)
            {
                var inputImages = new JsonArray();
                foreach (var url in inputImageUrls)
                    inputImages.Add(url);

                input["input_images"] = inputImages;
                input["aspect_ratio"] = "match_input_image";
                input["resolution"] = "match_input_image";
            }
            else
            {
                input["aspect_ratio"] = ConcreteFlux2PromptOnlyAspectRatio(request.AspectRatio);
                input["resolution"] = ConcreteFlux2PromptOnlyResolution(request.Resolution);
            }

            return new JsonObject
            {
                ["input"] = input,
            }.ToJsonString();
        }

        private static string ConcreteFlux2PromptOnlyAspectRatio(string? aspectRatio)
        {
            if (string.IsNullOrWhiteSpace(aspectRatio)
                || string.Equals(aspectRatio, "match_input_image", StringComparison.Ordinal))
            {
                return "1:1";
            }

            return aspectRatio!.Trim();
        }

        private static string ConcreteFlux2PromptOnlyResolution(string? resolution)
        {
            if (string.IsNullOrWhiteSpace(resolution)
                || string.Equals(resolution, "match_input_image", StringComparison.Ordinal))
            {
                return "1 MP";
            }

            var trimmed = resolution!.Trim();
            return string.Equals(trimmed, "1MP", StringComparison.OrdinalIgnoreCase)
                ? "1 MP"
                : trimmed;
        }

        private static JsonNode ParseJson(string json)
        {
            var node = JsonNode.Parse(json);
            if (node is null)
                throw new JsonException("Replicate response JSON was empty.");
            return node;
        }

        private static bool TrySelectOutputMetadataUrl(
            JsonNode? output,
            out Uri outputUrl)
        {
            outputUrl = null!;

            if (TryUrl(output, out var direct))
            {
                outputUrl = direct;
                return true;
            }

            if (output is JsonArray array
                && array.Count == 1
                && TryUrl(array[0], out var only))
            {
                outputUrl = only;
                return true;
            }

            return false;
        }

        private static bool TryUrl(JsonNode? node, out Uri url)
        {
            url = null!;
            if (node is not JsonValue value
                || !value.TryGetValue<string>(out var text)
                || string.IsNullOrWhiteSpace(text))
            {
                return false;
            }

            if (!Uri.TryCreate(text, UriKind.Absolute, out var uri))
                return false;
            if (!IsReplicateDeliveryOutputUri(uri))
                return false;

            url = uri;
            return true;
        }

        private static bool TrySelectMaterializableOutputUrl(
            ProviderJobHandle handle,
            out Uri outputUrl)
        {
            outputUrl = null!;
            if (string.IsNullOrWhiteSpace(handle.ProviderResultToken))
                return false;

            if (!Uri.TryCreate(
                    handle.ProviderResultToken,
                    UriKind.Absolute,
                    out var uri))
            {
                return false;
            }

            if (!IsReplicateDeliveryOutputUri(uri))
                return false;

            outputUrl = uri;
            return true;
        }

        private static bool IsReplicateDeliveryOutputUri(Uri uri) =>
            uri.Scheme == Uri.UriSchemeHttps && IsReplicateDeliveryHost(uri.Host);

        private static bool IsReplicateDeliveryHost(string host) =>
            string.Equals(host, "replicate.delivery", StringComparison.OrdinalIgnoreCase)
            || host.EndsWith(".replicate.delivery", StringComparison.OrdinalIgnoreCase);

        private static IReadOnlyDictionary<string, JsonNode> CopyMetadata(
            IReadOnlyDictionary<string, JsonNode>? metadata)
        {
            var copy = new Dictionary<string, JsonNode>();
            if (metadata is null)
                return copy;

            foreach (var kvp in metadata)
            {
                copy[kvp.Key] = kvp.Value.DeepClone();
            }

            return copy;
        }

        private static string BuildFlux2InputFileName(string mimeType) =>
            "flux2-input-" + Guid.NewGuid().ToString("N") + ExtensionForMimeType(mimeType);

        private static string ExtensionForMimeType(string mimeType)
        {
            switch (mimeType)
            {
                case "image/png":
                    return ".png";
                case "image/jpeg":
                    return ".jpg";
                case "image/gif":
                    return ".gif";
                case "image/webp":
                    return ".webp";
                default:
                    return ".bin";
            }
        }

        private static GenerationError Flux2UploadFailed() =>
            new(
                Code: GenerationErrorCode.DependencyUnavailable,
                Message: "Replicate file upload failed for Flux 2 Pro source image.",
                Retryable: true,
                Field: "input_image_path");

        private static FailedSubmitOutcome FailedSubmit(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));

        private static FailedStatusOutcome FailedStatus(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));

        private static FailedCancelOutcome FailedCancel(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));

        private static FailedResultOutcome FailedResult(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                Field: field));
    }
}
