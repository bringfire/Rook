using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net.Http;
using System.Net.Sockets;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalVideoProvider : IModelAwareVideoProvider
    {
        private static readonly Uri WanEndpoint =
            new("https://queue.fal.run/fal-ai/wan/v2.7/text-to-video");
        private static readonly Uri SeedanceSubmitEndpoint =
            new("https://queue.fal.run/bytedance/seedance-2.0/image-to-video");
        private static readonly Uri SeedanceLifecycleEndpoint =
            new("https://queue.fal.run/bytedance/seedance-2.0");
        private const long SeedanceMaxSourceFrameBytes = 30L * 1024L * 1024L;
        private static readonly FalSourceFramePolicy SeedanceSourceFramePolicy = new(
            ModelLabel: "Seedance",
            FileNamePrefix: "rook-seedance-source",
            AllowedModes: new[] { VideoMode.I2V, VideoMode.Interp },
            MaxSourceFrameBytes: SeedanceMaxSourceFrameBytes,
            AllowedMimeTypes: new[] { "image/png", "image/jpeg", "image/webp" },
            RejectEndFrameForI2v: true);
        private const string CancelHttpMethod = "PUT";

        private readonly Func<string?> _apiKeyProvider;
        private readonly FalApiClient _client;
        private readonly IFalSourceFrameTransport _sourceFrameTransport;

        public FalVideoProvider(Func<string?> apiKeyProvider, FalApiClient? client = null)
            : this(apiKeyProvider, client, sourceFrameTransport: null)
        {
        }

        internal FalVideoProvider(
            Func<string?> apiKeyProvider,
            FalApiClient? client,
            IFalSourceFrameTransport? sourceFrameTransport)
        {
            _apiKeyProvider = apiKeyProvider
                ?? throw new ArgumentNullException(nameof(apiKeyProvider));
            _client = client ?? new FalApiClient();
            _sourceFrameTransport =
                sourceFrameTransport ?? new FalSourceFrameTransport(_client);
        }

        public string ProviderName => FalVideoCapabilities.ProviderName;

        public async Task<ProviderSubmitOutcome> SubmitAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            if (request is null)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "Request is null.",
                    nameof(request));

            if (string.Equals(request.Model, FalVideoCapabilities.WanT2v, StringComparison.Ordinal))
                return await SubmitWanAsync(request, ct).ConfigureAwait(false);

            if (string.Equals(request.Model, FalVideoCapabilities.SeedanceI2v, StringComparison.Ordinal))
                return await SubmitSeedanceAsync(request, resolvedMedia, ct).ConfigureAwait(false);

            return FailedSubmit(
                GenerationErrorCode.InvalidRequest,
                "fal video provider does not support this model.",
                nameof(VideoGenerationRequest.Model));
        }

        private async Task<ProviderSubmitOutcome> SubmitWanAsync(
            VideoGenerationRequest request,
            CancellationToken ct)
        {
            if (request.Options is not FalVideoOptions)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    $"fal video provider requires {nameof(FalVideoOptions)}; got " +
                    $"{request.Options?.GetType().Name ?? "null"}.",
                    nameof(VideoGenerationRequest.Options));

            if (request.Mode != VideoMode.T2V)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "fal video provider only supports text-to-video mode in PR-8.",
                    nameof(VideoGenerationRequest.Mode));

            if (request.StartFrame is not null
                || request.EndFrame is not null
                || (request.ReferenceFrames is { Count: > 0 }))
            {
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "fal text-to-video does not accept input media in PR-8.",
                    nameof(VideoGenerationRequest.ReferenceFrames));
            }

            if (string.IsNullOrWhiteSpace(request.Prompt))
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "fal text-to-video requires prompt.",
                    nameof(VideoGenerationRequest.Prompt));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal API key is not configured.");

            FalHttpResponse response;
            try
            {
                response = await _client.PostJsonAsync(
                    apiKey!,
                    WanEndpoint,
                    BuildWanRequestJson(request),
                    ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (TaskCanceledException)
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal video submit timed out.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal video submit failed due to a transport error.",
                    retryable: true);
            }

            if (!response.IsSuccessStatusCode)
                return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(response));

            try
            {
                var root = JsonNode.Parse(response.Body);
                if (root is null)
                    return FailedSubmit(
                        GenerationErrorCode.ExecutionFailed,
                        "fal submit response was empty.");

                return new QueuedSubmitOutcome(
                    FalLifecycleMapper.ParseSubmitHandle(root, CancelHttpMethod));
            }
            catch (JsonException)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    "fal submit response was not valid JSON.");
            }
            catch (ArgumentException ex)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    ex.Message);
            }
        }

        private async Task<ProviderSubmitOutcome> SubmitSeedanceAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            if (request.Options is not FalVideoOptions)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    $"fal video provider requires {nameof(FalVideoOptions)}; got " +
                    $"{request.Options?.GetType().Name ?? "null"}.",
                    nameof(VideoGenerationRequest.Options));

            if (request.Mode != VideoMode.I2V && request.Mode != VideoMode.Interp)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "fal Seedance only supports image-to-video and interpolation modes.",
                    nameof(VideoGenerationRequest.Mode));

            if (string.IsNullOrWhiteSpace(request.Prompt))
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "fal Seedance requires prompt.",
                    nameof(VideoGenerationRequest.Prompt));

            if (request.NumberOfVideos != 1)
                return FailedSubmit(
                    GenerationErrorCode.InvalidRequest,
                    "fal Seedance supports exactly one video per request.",
                    nameof(VideoGenerationRequest.NumberOfVideos));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal API key is not configured.");

            var (sourceUrls, sourceError) =
                await _sourceFrameTransport.ResolveAndUploadAsync(
                    SeedanceSourceFramePolicy,
                    request,
                    resolvedMedia,
                    apiKey!,
                    ct).ConfigureAwait(false);
            if (sourceError is not null)
                return new FailedSubmitOutcome(SanitizeSeedanceSourceError(sourceError));
            if (sourceUrls is null)
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    "fal Seedance source upload did not return source URLs.");

            FalHttpResponse response;
            try
            {
                response = await PostSeedanceSubmitWithConnectRetryAsync(
                    apiKey!,
                    BuildSeedanceRequestJson(request, sourceUrls),
                    ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (TaskCanceledException)
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal video submit timed out.",
                    retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedSubmit(
                    GenerationErrorCode.DependencyUnavailable,
                    "fal video submit failed due to a transport error.",
                    retryable: true);
            }

            if (!response.IsSuccessStatusCode)
                return new FailedSubmitOutcome(MapSeedanceHttpFailure(response));

            try
            {
                var root = JsonNode.Parse(response.Body) as JsonObject;
                if (root is null)
                    return FailedSubmit(
                        GenerationErrorCode.ExecutionFailed,
                        "fal submit response was empty.");

                if (!TryGetString(root, "request_id", out var requestId))
                    return FailedSubmit(
                        GenerationErrorCode.ExecutionFailed,
                        "fal submit response did not contain request_id.",
                        "request_id");

                return new QueuedSubmitOutcome(new ProviderJobHandle(requestId!));
            }
            catch (JsonException)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    "fal submit response was not valid JSON.");
            }
            catch (ArgumentException ex)
            {
                return FailedSubmit(
                    GenerationErrorCode.ExecutionFailed,
                    ex.Message);
            }
        }

        private async Task<FalHttpResponse> PostSeedanceSubmitWithConnectRetryAsync(
            string apiKey,
            string bodyJson,
            CancellationToken ct)
        {
            try
            {
                return await _client.PostJsonAsync(
                    apiKey,
                    SeedanceSubmitEndpoint,
                    bodyJson,
                    FalJsonPlatformHeaders.ForSeedanceSubmit(
                        FalSourceFrameTransport.SourceMediaExpirationSeconds,
                        disableStoreIo: true,
                        disableFalRetry: true),
                    ct).ConfigureAwait(false);
            }
            catch (HttpRequestException ex) when (IsConnectionEstablishmentFailure(ex))
            {
                return await _client.PostJsonAsync(
                    apiKey,
                    SeedanceSubmitEndpoint,
                    bodyJson,
                    FalJsonPlatformHeaders.ForSeedanceSubmit(
                        FalSourceFrameTransport.SourceMediaExpirationSeconds,
                        disableStoreIo: true,
                        disableFalRetry: true),
                    ct).ConfigureAwait(false);
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
                    nameof(handle));

            if (handle.StatusUrl is null)
                return FailedStatus(
                    GenerationErrorCode.ExecutionFailed,
                    "fal status URL is missing.");

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
                    handle.StatusUrl,
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

        public Task<ProviderStatusOutcome> GetStatusAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (string.Equals(modelId, FalVideoCapabilities.WanT2v, StringComparison.Ordinal))
                return GetStatusAsync(handle, ct);

            if (string.Equals(modelId, FalVideoCapabilities.SeedanceI2v, StringComparison.Ordinal))
                return GetSeedanceStatusAsync(handle, ct);

            return Task.FromResult<ProviderStatusOutcome>(FailedStatus(
                GenerationErrorCode.InvalidRequest,
                $"fal video provider does not support async status for model '{modelId}'.",
                "model"));
        }

        private async Task<ProviderStatusOutcome> GetSeedanceStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedStatus(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    nameof(handle));

            var transportHandle = new ProviderJobHandle(
                handle.ProviderJobId,
                statusUrl: QueueStatusUri(SeedanceLifecycleEndpoint, handle.ProviderJobId),
                providerResultToken: handle.ProviderResultToken);

            var outcome = await GetStatusAsync(transportHandle, ct).ConfigureAwait(false);
            if (outcome is FailedStatusOutcome failed)
                return new FailedStatusOutcome(SanitizeProviderDetail(failed.Error));

            if (outcome is ProviderCompleteStatusOutcome complete)
            {
                return new ProviderCompleteStatusOutcome(new ProviderJobHandle(
                    complete.UpdatedHandle.ProviderJobId,
                    providerResultToken: complete.UpdatedHandle.ProviderResultToken
                        ?? handle.ProviderResultToken));
            }

            return outcome;
        }

        public async Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedCancel(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    nameof(handle));

            if (handle.CancelUrl is null || string.IsNullOrWhiteSpace(handle.CancelHttpMethod))
                return FailedCancel(
                    GenerationErrorCode.ExecutionFailed,
                    "fal cancel URL or method is missing.");

            var cancelHttpMethod = handle.CancelHttpMethod.Trim();
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
                    new HttpMethod(cancelHttpMethod),
                    handle.CancelUrl,
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

        public Task<ProviderCancelOutcome> CancelAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (string.Equals(modelId, FalVideoCapabilities.WanT2v, StringComparison.Ordinal))
                return CancelAsync(handle, ct);

            if (string.Equals(modelId, FalVideoCapabilities.SeedanceI2v, StringComparison.Ordinal))
                return CancelSeedanceAsync(handle, ct);

            return Task.FromResult<ProviderCancelOutcome>(FailedCancel(
                GenerationErrorCode.InvalidRequest,
                $"fal video provider does not support async cancel for model '{modelId}'.",
                "model"));
        }

        private async Task<ProviderCancelOutcome> CancelSeedanceAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
            {
                return FailedCancel(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    nameof(handle));
            }

            var transportHandle = new ProviderJobHandle(
                handle.ProviderJobId,
                cancelUrl: QueueCancelUri(SeedanceLifecycleEndpoint, handle.ProviderJobId),
                cancelHttpMethod: CancelHttpMethod);

            var outcome = await CancelAsync(transportHandle, ct).ConfigureAwait(false);
            return outcome is FailedCancelOutcome failed
                ? new FailedCancelOutcome(SanitizeProviderDetail(failed.Error))
                : outcome;
        }

        public async Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return FailedResult(
                    GenerationErrorCode.InvalidRequest,
                    "ProviderJobHandle is required.",
                    nameof(handle));

            if (handle.ResponseUrl is null)
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal response URL is missing.");

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
                    handle.ResponseUrl,
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

            return ParseFetchResult(response.Body);
        }

        public Task<ProviderResultOutcome> FetchResultAsync(
            string modelId,
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (string.Equals(modelId, FalVideoCapabilities.WanT2v, StringComparison.Ordinal))
                return FetchResultAsync(handle, ct);

            if (string.Equals(modelId, FalVideoCapabilities.SeedanceI2v, StringComparison.Ordinal))
                return FetchSeedanceResultAsync(handle, ct);

            return Task.FromResult<ProviderResultOutcome>(FailedResult(
                GenerationErrorCode.InvalidRequest,
                $"fal video provider does not support async result fetch for model '{modelId}'.",
                "model"));
        }

        private async Task<ProviderResultOutcome> FetchSeedanceResultAsync(
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
                    QueueResponseUri(SeedanceLifecycleEndpoint, handle.ProviderJobId),
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
                return new FailedResultOutcome(MapSeedanceHttpFailure(response));

            return ParseSeedanceFetchResult(response.Body);
        }

        private static string BuildWanRequestJson(VideoGenerationRequest request)
        {
            var body = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["aspect_ratio"] = request.AspectRatio,
                ["resolution"] = request.Resolution,
                ["duration"] = request.DurationSeconds,
                ["enable_safety_checker"] = true,
                ["enable_prompt_expansion"] = true,
            };

            if (request.Seed is int seed)
                body["seed"] = seed;

            return body.ToJsonString();
        }

        private static string BuildSeedanceRequestJson(
            VideoGenerationRequest request,
            FalSourceFrameUrls sourceUrls)
        {
            var body = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["image_url"] = sourceUrls.StartImageUrl,
                ["resolution"] = request.Resolution,
                ["duration"] = request.DurationSeconds.ToString(CultureInfo.InvariantCulture),
                ["aspect_ratio"] = request.AspectRatio,
                ["generate_audio"] = false,
            };

            if (sourceUrls.EndImageUrl is not null)
                body["end_image_url"] = sourceUrls.EndImageUrl;

            if (request.Seed is int seed)
                body["seed"] = seed;

            return body.ToJsonString();
        }

        private static ProviderResultOutcome ParseFetchResult(string body)
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

            if (root["video"] is not JsonObject video)
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal result response did not contain video object.",
                    "video");

            if (!TryGetString(video, "url", out var urlText)
                || !Uri.TryCreate(urlText, UriKind.Absolute, out var url)
                || (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps))
            {
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal video URL was missing or invalid.",
                    "video.url");
            }

            var artifactMetadata = CloneObject(video);
            if (!artifactMetadata.ContainsKey("url"))
                artifactMetadata["url"] = JsonValue.Create(urlText!)!;

            var envelopeMetadata = new Dictionary<string, JsonNode>();
            AddMetadata(root, envelopeMetadata, "actual_prompt");
            AddMetadata(root, envelopeMetadata, "seed");

            var artifact = new ResultArtifact(
                Role: VideoMediaRoles.Video,
                Body: new RemoteArtifactBody(url),
                DeclaredMimeType: TryGetString(video, "content_type", out var mime)
                    ? mime
                    : null,
                ProviderMetadata: artifactMetadata);

            return new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[] { artifact },
                    envelopeMetadata));
        }

        private static ProviderResultOutcome ParseSeedanceFetchResult(string body)
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

            if (root["video"] is not JsonObject video)
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal result response did not contain video object.",
                    "video");

            if (!TryGetString(video, "url", out var urlText)
                || !Uri.TryCreate(urlText, UriKind.Absolute, out var url)
                || (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps))
            {
                return FailedResult(
                    GenerationErrorCode.ExecutionFailed,
                    "fal video URL was missing or invalid.",
                    "video.url");
            }

            var artifact = new ResultArtifact(
                Role: VideoMediaRoles.Video,
                Body: new RemoteArtifactBody(url),
                DeclaredMimeType: TryGetString(video, "content_type", out var mime)
                    ? mime
                    : null,
                ProviderMetadata: new Dictionary<string, JsonNode>());

            return new SuccessResultOutcome(
                new ProviderResultEnvelope(
                    new[] { artifact },
                    new Dictionary<string, JsonNode>()));
        }

        private static Uri QueueStatusUri(Uri endpoint, string requestId) =>
            new($"{endpoint.ToString().TrimEnd('/')}/requests/" +
                $"{Uri.EscapeDataString(requestId)}/status");

        private static Uri QueueResponseUri(Uri endpoint, string requestId) =>
            new($"{endpoint.ToString().TrimEnd('/')}/requests/" +
                $"{Uri.EscapeDataString(requestId)}");

        private static Uri QueueCancelUri(Uri endpoint, string requestId) =>
            new($"{endpoint.ToString().TrimEnd('/')}/requests/" +
                $"{Uri.EscapeDataString(requestId)}/cancel");

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

        private static GenerationError MapSeedanceHttpFailure(FalHttpResponse response) =>
            SanitizeProviderDetail(FalErrorMapper.MapHttpFailure(response));

        private static GenerationError SanitizeProviderDetail(GenerationError error) =>
            error.ProviderDetail is null
                ? error
                : error with { ProviderDetail = null };

        private static GenerationError SanitizeSeedanceSourceError(GenerationError error)
        {
            var sanitized = SanitizeProviderDetail(error);
            return ContainsSeedanceSourceTransportMarker(sanitized.Message)
                ? sanitized with { Message = "fal Seedance source upload failed." }
                : sanitized;
        }

        private static bool ContainsSeedanceSourceTransportMarker(string message) =>
            message.IndexOf("https://", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("data:", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("image_url", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("upload_url", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("{\"prompt\"", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("request {", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("body {", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("request body", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("request_body", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("request-body", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("request envelope", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("request_envelope", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("request-envelope", StringComparison.OrdinalIgnoreCase) >= 0
            || message.IndexOf("X-Fal-", StringComparison.OrdinalIgnoreCase) >= 0;

        private static bool IsConnectionEstablishmentFailure(Exception ex)
        {
            for (var current = ex; current is not null; current = current.InnerException)
            {
                if (current is SocketException socket)
                {
                    return socket.SocketErrorCode is SocketError.TimedOut
                        or SocketError.HostUnreachable
                        or SocketError.NetworkUnreachable
                        or SocketError.ConnectionRefused
                        or SocketError.HostNotFound
                        or SocketError.NetworkDown;
                }
            }

            return false;
        }

        private static bool TryGetString(JsonObject obj, string key, out string? value)
        {
            value = null;
            try
            {
                value = obj[key]?.GetValue<string>();
                return !string.IsNullOrWhiteSpace(value);
            }
            catch
            {
                return false;
            }
        }

        private static Dictionary<string, JsonNode> CloneObject(JsonObject obj)
        {
            var copy = new Dictionary<string, JsonNode>();
            foreach (var kvp in obj)
            {
                if (kvp.Value is not null)
                    copy[kvp.Key] = kvp.Value.DeepClone();
            }

            return copy;
        }

        private static void AddMetadata(
            JsonObject source,
            IDictionary<string, JsonNode> metadata,
            string key)
        {
            var node = source[key]?.DeepClone();
            if (node is not null)
                metadata[key] = node;
        }
    }
}
