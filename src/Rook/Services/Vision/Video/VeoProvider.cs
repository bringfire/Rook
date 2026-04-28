using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// <see cref="IVideoProvider"/> implementation for Google's Veo.
    /// Composes <see cref="VeoClient"/> (HTTP plumbing) with
    /// <see cref="VeoErrorMapper"/> (status → <see cref="GenerationError"/>).
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

        public string ProviderName => VeoCapabilities.ProviderName;

        public async Task<ProviderSubmitOutcome> SubmitAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            if (request is null)
                return new FailedSubmitOutcome(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            // Provider boundary stays total (per V1c review Finding 2):
            // a request reaching VeoProvider with non-VeoOptions is a
            // programming error (the registry pairs Veo models with the
            // VeoOptionsCodec/VeoProvider; mismatch means someone bypassed
            // the registry), but we surface it as a typed envelope rather
            // than throw so IGenerationProvider's contract remains "every input
            // shape produces an envelope."
            if (request.Options is not VeoOptions veoOptions)
                return new FailedSubmitOutcome(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: $"Veo provider requires {nameof(VeoOptions)}; got " +
                             $"{request.Options?.GetType().Name ?? "null"}.",
                    Retryable: false,
                    Field: nameof(request.Options)));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return new FailedSubmitOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(VeoErrorMapper.MissingApiKey()));

            try
            {
                var resp = await _client.StartGenerationAsync(
                    apiKey!,
                    request,
                    veoOptions,
                    resolvedMedia,
                    ct)
                    .ConfigureAwait(false);

                if (resp.Success && !string.IsNullOrEmpty(resp.OperationName))
                    return new QueuedSubmitOutcome(
                        new ProviderJobHandle(resp.OperationName!));

                return new FailedSubmitOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(
                        VeoErrorMapper.MapStartFailure(resp.StatusCode, resp.ErrorBody)));
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return new FailedSubmitOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(
                        VeoErrorMapper.NetworkError("submit", ex.Message)));
            }
        }

        public async Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle, CancellationToken ct)
        {
            if (handle is null)
                return new FailedStatusOutcome(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "ProviderJobHandle is required.",
                    Retryable: false,
                    Field: nameof(handle)));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return new FailedStatusOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(VeoErrorMapper.MissingApiKey()));

            try
            {
                var resp = await _client.PollOperationAsync(
                    apiKey!, handle.ProviderJobId, ct).ConfigureAwait(false);

                if (resp.Success)
                {
                    if (!resp.Done)
                        return new InFlightStatusOutcome(
                            GenerationLifecycleState.Running,
                            new GenerationProgress(Message: "polling"));

                    if (!string.IsNullOrEmpty(resp.VideoUri))
                        return new ProviderCompleteStatusOutcome(
                            handle.WithResultToken(resp.VideoUri!));

                    // Done but no URI extracted from any documented shape.
                    return new FailedStatusOutcome(
                        new GenerationError(
                            Code: GenerationErrorCode.ExecutionFailed,
                            Message: "Veo reported done but no video URI in response.",
                            Retryable: false));
                }

                return new FailedStatusOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(
                        VeoErrorMapper.MapPollFailure(resp.StatusCode, resp.ErrorBody)));
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return new FailedStatusOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(
                        VeoErrorMapper.NetworkError("poll", ex.Message)));
            }
        }

        public async Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle, CancellationToken ct)
        {
            if (handle is null)
                return new FailedCancelOutcome(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "ProviderJobHandle is required.",
                    Retryable: false,
                    Field: nameof(handle)));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return new FailedCancelOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(VeoErrorMapper.MissingApiKey()));

            try
            {
                var resp = await _client.CancelOperationAsync(
                    apiKey!, handle.ProviderJobId, ct).ConfigureAwait(false);

                if (resp.Success)
                    return new CanceledOutcome();

                return new FailedCancelOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(
                        VeoErrorMapper.MapCancelFailure(resp.StatusCode, resp.ErrorBody)));
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return new FailedCancelOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(
                        VeoErrorMapper.NetworkError("cancel", ex.Message)));
            }
        }

        public async Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return new FailedResultOutcome(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "ProviderJobHandle is required.",
                    Retryable: false,
                    Field: nameof(handle)));

            if (string.IsNullOrWhiteSpace(handle.ProviderResultToken))
                return new FailedResultOutcome(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "ProviderResultToken (videoUri) is required for Veo. " +
                             "The manager should persist it from the status poll that " +
                             "first reported provider-Complete.",
                    Retryable: false,
                    Field: "providerResultToken"));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrEmpty(apiKey))
                return new FailedResultOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(VeoErrorMapper.MissingApiKey()));

            try
            {
                var bytes = await _client.DownloadVideoAsync(
                    apiKey!, handle.ProviderResultToken!, ct).ConfigureAwait(false);

                if (bytes.Length == 0)
                    return new FailedResultOutcome(new GenerationError(
                        Code: GenerationErrorCode.ExecutionFailed,
                        Message: "Veo download returned empty body.",
                        Retryable: true));

                return new SuccessResultOutcome(
                    new ProviderResultEnvelope(
                        new[]
                        {
                            new ResultArtifact(
                                Role: VideoMediaRoles.Video,
                                Body: new InlineArtifactBody(bytes),
                                DeclaredMimeType: "video/mp4",
                                ProviderMetadata: EmptyMetadata),
                        },
                        EmptyMetadata));
            }
            catch (OperationCanceledException) { throw; }
            catch (HttpRequestException ex)
            {
                return new FailedResultOutcome(
                    VideoProviderOutcomeAdapters.ToGenerationError(
                        VeoErrorMapper.NetworkError("download", ex.Message)));
            }
        }

        private static readonly IReadOnlyDictionary<string, JsonNode> EmptyMetadata
            = new Dictionary<string, JsonNode>();
    }
}
