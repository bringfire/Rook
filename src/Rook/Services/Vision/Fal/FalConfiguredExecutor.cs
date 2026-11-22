using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    /// <summary>One-shot configured fal execution. Only lifecycle GET/PUT operations can be
    /// repeated; this service never retries a paid POST.</summary>
    public sealed class FalConfiguredExecutor
    {
        private readonly FalApiClient _client;
        private readonly Func<string?> _apiKeyProvider;
        private readonly FalMediaPreparation _preparation;
        private readonly FalAdapterRegistry _adapters;
        public FalConfiguredExecutor(FalApiClient client, Func<string?> apiKeyProvider,
            FalMediaPreparation? preparation = null, FalAdapterRegistry? adapters = null)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
            _apiKeyProvider = apiKeyProvider ?? throw new ArgumentNullException(nameof(apiKeyProvider));
            _preparation = preparation ?? new FalMediaPreparation(client, apiKeyProvider); _adapters = adapters ?? new FalAdapterRegistry();
        }

        public async Task<ProviderSubmitOutcome> SubmitAsync(FalNormalizedRequest request, FalMediaSnapshot media, IFalExecutionObserver observer, CancellationToken ct)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (media == null) throw new ArgumentNullException(nameof(media));
            if (observer == null) throw new ArgumentNullException(nameof(observer));
            var dispatched = false;
            try
            {
                ct.ThrowIfCancellationRequested();
                var invalidMedia = media.Validate(request);
                if (invalidMedia != null) return new FailedSubmitOutcome(invalidMedia);
                var key = _apiKeyProvider();
                if (string.IsNullOrWhiteSpace(key)) return new FailedSubmitOutcome(MissingKey());
                var binding = request.Binding;
                var adapter = _adapters.Resolve(binding.AdapterId, binding.AdapterVersion);
                var endpoint = new Uri((binding.Invocation == "queue" ? "https://queue.fal.run/" : "https://fal.run/") + binding.EndpointId);
                var admission = await observer.BeforeUploadAsync(ct).ConfigureAwait(false);
                if (admission != null) return new FailedSubmitOutcome(admission);
                using var prepared = await _preparation.PrepareOwnedAsync(request, media, ct).ConfigureAwait(false);
                var payload = adapter.BuildPayload(request, prepared.Values).ToJsonString();
                if (Encoding.UTF8.GetByteCount(payload) > prepared.MaxSerializedBytes)
                    return new FailedSubmitOutcome(FalMediaSnapshot.Invalid("Configured fal serialized payload exceeds its admitted envelope.", "media"));
                admission = await observer.BeforeDispatchAsync(ct).ConfigureAwait(false);
                if (admission != null) return new FailedSubmitOutcome(admission);
                ct.ThrowIfCancellationRequested();
                dispatched = true;
                var response = await _client.PostJsonAsync(key!, endpoint, payload,
                    FalJsonPlatformHeaders.ForSeedanceSubmit(3600, disableStoreIo: true, disableFalRetry: true), ct).ConfigureAwait(false);
                if (!response.IsSuccessStatusCode)
                {
                    // Authentication, quota and request rejection establish nonacceptance. Server
                    // failures/timeouts do not establish whether compute started remotely.
                    if (response.StatusCode >= 400 && response.StatusCode < 500 && response.StatusCode != 408)
                        return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(response) with { ProviderDetail = null });
                    return Unknown();
                }
                if (binding.Invocation == "sync") return new SyncSubmitOutcome(MapResult(binding, response.Body));
                var handle = FalConfiguredLifecycle.ParseSubmitHandle(binding, ParseObject(response.Body));
                await observer.AcceptedAsync(handle, ct).ConfigureAwait(false);
                return new QueuedSubmitOutcome(handle);
            }
            catch (Exception) when (dispatched)
            {
                // This includes cancellation, malformed acceptance and a failed durable accepted
                // write. A local exception cannot prove that a dispatched request cost nothing.
                return Unknown();
            }
            catch (FalMediaPreparationException ex) { return new FailedSubmitOutcome(ex.Error); }
            catch (OperationCanceledException)
            { return new FailedSubmitOutcome(new GenerationError(ct.IsCancellationRequested ? GenerationErrorCode.Cancelled : GenerationErrorCode.DependencyUnavailable, "Configured fal submission stopped before dispatch.", !ct.IsCancellationRequested)); }
            catch (Exception)
            { return new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "Configured fal preparation or admission failed before dispatch.", false)); }
        }

        public async Task<ProviderStatusOutcome> GetStatusAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct)
        {
            var invalid = FalConfiguredLifecycle.Validate(binding, handle);
            if (invalid != null) return new FailedStatusOutcome(invalid);
            var call = await CallAsync(handle.StatusUrl!, HttpMethod.Get, ct).ConfigureAwait(false);
            if (call.Error != null) return new FailedStatusOutcome(call.Error);
            try
            {
                var body = ParseObject(call.Response!.Body);
                if (body["error"] != null) return new FailedStatusOutcome(InvalidResponse());
                var outcome = FalLifecycleMapper.MapStatus(handle, body);
                if (outcome is FailedStatusOutcome failed)
                    return new FailedStatusOutcome(failed.Error.Code == GenerationErrorCode.Cancelled
                        ? new GenerationError(GenerationErrorCode.Cancelled, "fal job was cancelled.", false)
                        : InvalidResponse());
                return outcome;
            }
            catch (JsonException) { return new FailedStatusOutcome(InvalidResponse()); }
        }

        public async Task<ProviderCancelOutcome> CancelAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct)
        {
            var invalid = FalConfiguredLifecycle.Validate(binding, handle);
            if (invalid != null) return new FailedCancelOutcome(invalid);
            var call = await CallAsync(handle.CancelUrl!, HttpMethod.Put, ct, includeFailure: true).ConfigureAwait(false);
            if (call.Error != null) return new FailedCancelOutcome(call.Error);
            try
            {
                var response = call.Response!;
                var status = ParseObject(response.Body)["status"]?.GetValue<string>();
                if (response.StatusCode == 200 && status == "OK") return new CanceledOutcome();
                if (response.StatusCode == 400 && status == "ALREADY_COMPLETED") return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
                if (response.StatusCode == 202 && status == "CANCELLATION_REQUESTED")
                    return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed,
                        "Remote cancellation was requested; the running job may still complete and incur charges.", false, ProviderErrorCode: "fal_cancellation_requested"));
                if (response.StatusCode == 404 && status == "NOT_FOUND")
                    return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "Remote request was not found.", false, ProviderErrorCode: "fal_cancel_not_found"));
                return new FailedCancelOutcome(response.IsSuccessStatusCode ? InvalidResponse() : SanitizedHttpError(response));
            }
            catch (Exception ex) when (ex is JsonException || ex is InvalidOperationException)
            { return new FailedCancelOutcome(InvalidResponse()); }
        }

        public async Task<ProviderResultOutcome> FetchResultAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct)
        {
            var invalid = FalConfiguredLifecycle.Validate(binding, handle);
            if (invalid != null) return new FailedResultOutcome(invalid);
            var call = await CallAsync(handle.ResponseUrl!, HttpMethod.Get, ct).ConfigureAwait(false);
            return call.Error != null ? new FailedResultOutcome(call.Error) : MapResult(binding, call.Response!.Body);
        }

        private ProviderResultOutcome MapResult(FalOperationBinding binding, string json)
        {
            try
            {
                var body = ParseObject(json);
                return body["error"] != null ? new FailedResultOutcome(InvalidResponse()) : _adapters.Resolve(binding.AdapterId, binding.AdapterVersion).MapResult(binding, body);
            }
            catch (JsonException) { return new FailedResultOutcome(InvalidResponse()); }
        }
        private async Task<(FalHttpResponse? Response, GenerationError? Error)> CallAsync(Uri url, HttpMethod method, CancellationToken ct, bool includeFailure = false)
        {
            var key = _apiKeyProvider(); if (string.IsNullOrWhiteSpace(key)) return (null, MissingKey());
            try
            {
                var response = await _client.SendAsync(key!, method, url, null, ct).ConfigureAwait(false);
                return response.IsSuccessStatusCode || includeFailure ? (response, null) : (null, SanitizedHttpError(response));
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (Exception ex) when (ex is OperationCanceledException || ex is HttpRequestException)
            { return (null, new GenerationError(GenerationErrorCode.DependencyUnavailable, "Configured fal lifecycle request failed or timed out.", true)); }
        }
        private static JsonObject ParseObject(string json) => JsonNode.Parse(json) as JsonObject ?? throw new JsonException();
        private static GenerationError SanitizedHttpError(FalHttpResponse response) => FalErrorMapper.MapHttpFailure(response) with { ProviderDetail = null };
        private static GenerationError MissingKey() => new(GenerationErrorCode.DependencyUnavailable, "fal API key is not configured.", false);
        private static GenerationError InvalidResponse() => new(GenerationErrorCode.ExecutionFailed, "Configured fal returned an invalid or failed response.", false);
        private static FailedSubmitOutcome Unknown() => new(new GenerationError(GenerationErrorCode.ExecutionFailed,
            "Configured fal submission outcome is unknown; remote compute may continue and incur charges. Do not resubmit automatically.", false,
            ProviderErrorCode: "fal_submission_unknown"), SubmissionDisposition.Unknown);
    }
}
