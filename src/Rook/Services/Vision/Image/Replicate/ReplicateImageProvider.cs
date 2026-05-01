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
        private static readonly ReplicatePredictionEndpoint Endpoint =
            ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", "flux-schnell");

        private readonly Func<string?> _apiTokenProvider;
        private readonly ReplicateApiClient _client;
        private readonly ReplicateImageOptionsCodec _codec = new();

        public ReplicateImageProvider(
            Func<string?> apiTokenProvider,
            ReplicateApiClient? client = null)
        {
            _apiTokenProvider = apiTokenProvider
                ?? throw new ArgumentNullException(nameof(apiTokenProvider));
            _client = client ?? new ReplicateApiClient();
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

            if (!string.Equals(
                    request.Model,
                    ReplicateImageCapabilities.FluxSchnell,
                    StringComparison.Ordinal))
            {
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    $"Unknown Replicate image model '{request.Model}'.",
                    "model");
            }

            var validation = _codec.Validate(
                request,
                request.Options,
                ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell]);
            if (!validation.Success)
            {
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    validation.Message ?? "Replicate image request is invalid.",
                    validation.Field);
            }

            var apiToken = _apiTokenProvider();
            if (string.IsNullOrWhiteSpace(apiToken))
                return new FailedSubmitOutcome(ReplicateErrorMapper.MissingToken());

            ReplicateHttpResponse response;
            try
            {
                response = await _client.CreatePredictionAsync(
                        apiToken!,
                        Endpoint,
                        BuildRequestJson(request),
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
            CancellationToken ct) =>
            Task.FromResult<ProviderResultOutcome>(
                new FailedResultOutcome(new GenerationError(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate image result extraction is not implemented.",
                    Retryable: false)));

        private static string BuildRequestJson(ImageGenerationRequest request)
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

        private static JsonNode ParseJson(string json)
        {
            var node = JsonNode.Parse(json);
            if (node is null)
                throw new JsonException("Replicate response JSON was empty.");
            return node;
        }

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
    }
}
