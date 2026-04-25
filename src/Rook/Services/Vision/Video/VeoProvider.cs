using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// <see cref="IVideoProvider"/> implementation for Google's Veo.
    /// Composes <see cref="VeoClient"/> (HTTP plumbing) with
    /// <see cref="VeoErrorMapper"/> (status → <see cref="VideoJobError"/>).
    /// Stateless across calls; <c>provider_job_id</c> +
    /// <c>provider_result_token</c> are persisted by the manager and
    /// passed back as method arguments.
    /// </summary>
    public sealed class VeoProvider : IVideoProvider
    {
        private readonly Func<string?> _apiKeyProvider;
        private readonly VeoClient _client;

        /// <param name="apiKeyProvider">
        /// Called once per provider operation to get the current Veo API
        /// key. Production wiring uses
        /// <c>new VisionSecretStore().GetGeminiApiKey</c>; tests inject a
        /// fixed-value delegate.
        /// </param>
        /// <param name="client">
        /// Optional <see cref="VeoClient"/> override. Tests pass a client
        /// constructed against a mocked <c>HttpMessageHandler</c>;
        /// production passes null and gets the default static-shared
        /// HttpClient.
        /// </param>
        public VeoProvider(Func<string?> apiKeyProvider, VeoClient? client = null)
        {
            _apiKeyProvider = apiKeyProvider ?? throw new ArgumentNullException(nameof(apiKeyProvider));
            _client = client ?? new VeoClient();
        }

        public async Task<ProviderSubmitResult> SubmitAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> resolvedMedia,
            CancellationToken ct)
        {
            if (request is null)
                return ProviderSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            // Provider boundary stays total (per V1c review Finding 2):
            // a request reaching VeoProvider with non-VeoOptions is a
            // programming error (the registry pairs Veo models with the
            // VeoOptionsCodec/VeoProvider; mismatch means someone bypassed
            // the registry), but we surface it as a typed envelope rather
            // than throw so IVideoProvider's contract remains "every input
            // shape produces an envelope."
            if (request.Options is not VeoOptions veoOptions)
                return ProviderSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Veo provider requires {nameof(VeoOptions)}; got " +
                             $"{request.Options?.GetType().Name ?? "null"}.",
                    Retryable: false,
                    Field: nameof(request.Options)));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return ProviderSubmitResult.Fail(VeoErrorMapper.MissingApiKey());

            try
            {
                var resp = await _client.StartGenerationAsync(
                    apiKey!, request, veoOptions, resolvedMedia ?? EmptyResolved, ct)
                    .ConfigureAwait(false);

                if (resp.Success && !string.IsNullOrEmpty(resp.OperationName))
                    return ProviderSubmitResult.Ok(resp.OperationName!);

                return ProviderSubmitResult.Fail(
                    VeoErrorMapper.MapStartFailure(resp.StatusCode, resp.ErrorBody));
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return ProviderSubmitResult.Fail(
                    VeoErrorMapper.NetworkError("submit", ex.Message));
            }
        }

        public async Task<ProviderStatusResult> GetStatusAsync(
            string providerJobId, CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                return ProviderStatusResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: "ProviderJobId must be non-empty.",
                        Retryable: false,
                        Field: nameof(providerJobId)));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return ProviderStatusResult.Failed(
                    VideoJobState.Error, VeoErrorMapper.MissingApiKey());

            try
            {
                var resp = await _client.PollOperationAsync(
                    apiKey!, providerJobId, ct).ConfigureAwait(false);

                if (resp.Success)
                {
                    if (!resp.Done)
                        return ProviderStatusResult.InFlight(
                            VideoJobState.Polling,
                            new VideoJobProgress(Pct: null, Stage: "polling", Message: null));

                    if (!string.IsNullOrEmpty(resp.VideoUri))
                        return ProviderStatusResult.Complete(resp.VideoUri!);

                    // Done but no URI extracted from any documented shape.
                    return ProviderStatusResult.Failed(
                        VideoJobState.Error,
                        new VideoJobError(
                            Code: VideoErrorCode.ExecutionFailed,
                            Message: "Veo reported done but no video URI in response.",
                            Retryable: false));
                }

                return ProviderStatusResult.Failed(
                    VideoJobState.Error,
                    VeoErrorMapper.MapPollFailure(resp.StatusCode, resp.ErrorBody));
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return ProviderStatusResult.Failed(
                    VideoJobState.Error,
                    VeoErrorMapper.NetworkError("poll", ex.Message));
            }
        }

        public async Task<ProviderCancelResult> CancelAsync(
            string providerJobId, CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                return ProviderCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "ProviderJobId must be non-empty.",
                    Retryable: false,
                    Field: nameof(providerJobId)));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return ProviderCancelResult.Fail(VeoErrorMapper.MissingApiKey());

            try
            {
                var resp = await _client.CancelOperationAsync(
                    apiKey!, providerJobId, ct).ConfigureAwait(false);

                if (resp.Success)
                    return ProviderCancelResult.Ok(VideoJobState.Cancelled);

                return ProviderCancelResult.Fail(
                    VeoErrorMapper.MapCancelFailure(resp.StatusCode, resp.ErrorBody));
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return ProviderCancelResult.Fail(
                    VeoErrorMapper.NetworkError("cancel", ex.Message));
            }
        }

        public async Task<ProviderFetchResult> FetchResultAsync(
            string providerJobId,
            string? providerResultToken,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                return ProviderFetchResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "ProviderJobId must be non-empty.",
                    Retryable: false,
                    Field: nameof(providerJobId)));

            if (string.IsNullOrWhiteSpace(providerResultToken))
                return ProviderFetchResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "ProviderResultToken (videoUri) is required for Veo. " +
                             "The manager should persist it from the status poll that " +
                             "first reported provider-Complete.",
                    Retryable: false,
                    Field: nameof(providerResultToken)));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return ProviderFetchResult.Fail(VeoErrorMapper.MissingApiKey());

            try
            {
                var bytes = await _client.DownloadVideoAsync(
                    apiKey!, providerResultToken!, ct).ConfigureAwait(false);

                if (bytes.Length == 0)
                    return ProviderFetchResult.Fail(new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: "Veo download returned empty body.",
                        Retryable: true));

                return ProviderFetchResult.Ok(bytes, "video/mp4");
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return ProviderFetchResult.Fail(
                    VeoErrorMapper.NetworkError("download", ex.Message));
            }
        }

        private static readonly IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> EmptyResolved
            = new Dictionary<VideoMediaRef, ResolvedVideoMedia>();
    }
}
