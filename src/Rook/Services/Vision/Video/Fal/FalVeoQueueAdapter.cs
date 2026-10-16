using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalVeoQueueAdapter
    {
        private readonly Func<string?> _key;
        private readonly FalApiClient _client;
        private readonly FalVeoBindingCatalog _catalog;
        private readonly IFalVeoSourceFrameTransport _sources;
        public FalVeoQueueAdapter(Func<string?> key, FalApiClient client, FalVeoBindingCatalog catalog, IFalVeoSourceFrameTransport sources) { _key = key; _client = client; _catalog = catalog; _sources = sources; }
        public async Task<ProviderSubmitOutcome> SubmitPreparedAsync(VideoGenerationRequest request, VideoPreparedMediaSnapshot preparedMedia, Action beforeDispatch, CancellationToken ct, VideoPreparationLease? phase = null)
        {
            string? key;
            try { key = _key(); } catch { return new FailedSubmitOutcome(VideoCredentialErrors.AccessFailed()); }
            if (string.IsNullOrWhiteSpace(key)) return new FailedSubmitOutcome(VideoCredentialErrors.Missing("fal"));
            VideoPreparationLease? acquired;
            try { acquired = phase == null ? await VideoPreparationResources.Shared.AcquireAsync(ct).ConfigureAwait(false) : null; }
            catch (VideoPreparationBusyException) { return new FailedSubmitOutcome(VideoSourcePreparationErrors.Busy("source_framing")); }
            using var ownedPhase = acquired;
            phase ??= ownedPhase!;
            var resolution = _catalog.Resolve(request, DateTimeOffset.UtcNow);
            if (resolution.Error != null) return new FailedSubmitOutcome(resolution.Error);
            var binding = resolution.Binding!;
            var validation = FalVeoCompatibility.ValidateMetadata(VideoRequestIntent.Normalize(request, new FalVeoOptionsCodec().Serialize(request.Options)), binding, preparedMedia);
            if (validation != null) return new FailedSubmitOutcome(validation);
            (FalVeoSourceUrls? Urls, GenerationError? Error) uploaded;
            try { uploaded = await _sources.ResolveAndUploadVeoAsync(binding, request, preparedMedia, key!, ct, phase).ConfigureAwait(false); }
            catch (VideoPreparationBusyException) { return new FailedSubmitOutcome(VideoSourcePreparationErrors.Busy("source_framing")); }
            catch (FalApiException ex) when (ex.StatusCode != null && (ex.StatusCode != 401 || ex.AuthenticatedRequest)) { return new FailedSubmitOutcome(VideoCredentialErrors.FromHttp("fal", ex.StatusCode.Value, string.Empty)); }
            catch (Exception ex) when (ex is HttpRequestException or FalApiException) { return new FailedSubmitOutcome(Error("fal source upload failed.")); }
            if (uploaded.Error != null) return new FailedSubmitOutcome(uploaded.Error);
            long textUnits = (request.Prompt?.Length ?? 0) + (uploaded.Urls!.Start?.Length ?? 0) + (uploaded.Urls.End?.Length ?? 0) + uploaded.Urls.References.Sum(u => (long)u.Length);
            long capacity = 1_048_576 + textUnits * 64;
            if (capacity > VideoPreparationLimits.TransientBytes) return new FailedSubmitOutcome(VideoSourcePreparationErrors.Busy("source_framing"));
            VideoBufferReservation serialized;
            try { serialized = phase.Buffers.Reserve((int)capacity); }
            catch (VideoPreparationBusyException) { return new FailedSubmitOutcome(VideoSourcePreparationErrors.Busy("source_framing")); }
            using var serializationOwner = serialized;
            var body = new JsonObject { ["prompt"] = request.Prompt, ["duration"] = request.DurationSeconds + "s", ["resolution"] = request.Resolution, ["aspect_ratio"] = request.AspectRatio, ["generate_audio"] = true, ["auto_fix"] = false, ["safety_tolerance"] = "4" };
            if (request.Seed.HasValue) body["seed"] = request.Seed.Value;
            if (request.Mode == VideoMode.I2V) body["image_url"] = uploaded.Urls!.Start;
            if (request.Mode == VideoMode.Interp) { body["first_frame_url"] = uploaded.Urls!.Start; body["last_frame_url"] = uploaded.Urls.End; }
            if ((request.ReferenceFrames?.Count ?? 0) > 0) body["image_urls"] = new JsonArray(uploaded.Urls!.References.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray());
            string payload = body.ToJsonString();
            beforeDispatch();
            ct.ThrowIfCancellationRequested();
            if (_catalog.Resolve(request, DateTimeOffset.UtcNow).Error is { } expired) return new FailedSubmitOutcome(expired);
            FalHttpResponse response;
            try { response = await _client.PostJsonAsync(key!, new Uri("https://queue.fal.run/" + binding.SubmitEndpoint), payload, FalJsonPlatformHeaders.ForVeoSubmit(3600), ct).ConfigureAwait(false); }
            catch (Exception ex) when (ex is HttpRequestException || ex is OperationCanceledException && !ct.IsCancellationRequested) { return new FailedSubmitOutcome(VideoCredentialErrors.Unknown()); }
            if (!response.IsSuccessStatusCode) return new FailedSubmitOutcome(VideoCredentialErrors.FromHttp("fal", response.StatusCode, response.Body));
            try
            {
                var json = JsonNode.Parse(response.Body)!.AsObject();
                var id = json["request_id"]!.GetValue<string>();
                var metadata = new Dictionary<string, JsonNode> { ["veo_lifecycle_root"] = JsonValue.Create(binding.LifecycleRoot)!, ["veo_endpoint"] = JsonValue.Create(binding.SubmitEndpoint)! };
                var handle = new ProviderJobHandle(id, new Uri(json["status_url"]!.GetValue<string>()), new Uri(json["response_url"]!.GetValue<string>()), new Uri(json["cancel_url"]!.GetValue<string>()), "PUT", providerMetadata: metadata);
                return ValidHandle(handle) ? new QueuedSubmitOutcome(handle) : new FailedSubmitOutcome(VideoCredentialErrors.Unknown());
            }
            catch (Exception ex) when (ex is System.Text.Json.JsonException or InvalidOperationException or NullReferenceException or ArgumentException or FormatException) { return new FailedSubmitOutcome(VideoCredentialErrors.Unknown()); }
        }
        private bool ValidHandle(ProviderJobHandle handle)
        {
            if (!Regex.IsMatch(handle.ProviderJobId, "^[A-Za-z0-9_-]{1,200}$")) return false;
            if (!handle.ProviderMetadata.TryGetValue("veo_lifecycle_root", out var rootNode) || rootNode is not JsonValue rootValue || !rootValue.TryGetValue<string>(out var root)) return false;
            if (!handle.ProviderMetadata.TryGetValue("veo_endpoint", out var endpointNode) || endpointNode is not JsonValue endpointValue || !endpointValue.TryGetValue<string>(out var endpoint)) return false;
            if (!_catalog.All.Any(b => b.LifecycleRoot == root && b.SubmitEndpoint == endpoint)) return false;
            var prefix = "https://queue.fal.run/" + root + "/requests/" + handle.ProviderJobId;
            return handle.StatusUrl?.AbsoluteUri == prefix + "/status" && handle.ResponseUrl?.AbsoluteUri == prefix && handle.CancelUrl?.AbsoluteUri == prefix + "/cancel" && handle.CancelHttpMethod == "PUT";
        }
        public async Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            if (!ValidHandle(handle)) return new FailedStatusOutcome(Error("Invalid fal Veo lifecycle binding."));
            var response = await CallAsync(handle.StatusUrl!, HttpMethod.Get, ct).ConfigureAwait(false);
            if (response.Error != null) return new FailedStatusOutcome(response.Error);
            var status = ParseStatus(response.Response!.Body);
            return status switch { "COMPLETED" => new ProviderCompleteStatusOutcome(handle), "IN_QUEUE" => new InFlightStatusOutcome(GenerationLifecycleState.Pending, null), "IN_PROGRESS" => new InFlightStatusOutcome(GenerationLifecycleState.Running, null), _ => new FailedStatusOutcome(Error("fal queue returned a failed or invalid video state.")) };
        }
        public async Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            if (!ValidHandle(handle)) return new FailedCancelOutcome(Error("Invalid fal Veo lifecycle binding."));
            var response = await CallAsync(handle.CancelUrl!, HttpMethod.Put, ct, allowCancelFailure: true).ConfigureAwait(false);
            if (response.Error != null) return new FailedCancelOutcome(response.Error);
            var status = ParseStatus(response.Response!.Body);
            if (response.Response.StatusCode == 202 && status == "CANCELLATION_REQUESTED") return new CanceledOutcome();
            if (response.Response.StatusCode == 400 && status == "ALREADY_COMPLETED") return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
            var outcome = response.Response.StatusCode == 404 && status == "NOT_FOUND" ? "not_found" : response.Response.StatusCode == 202 ? "unknown" : "failed";
            return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "Remote video cleanup outcome: " + outcome + ".", false, null, "fal_cleanup_" + outcome));
        }
        public static string CleanupOutcome(ProviderCancelOutcome outcome) => outcome switch { CanceledOutcome => "accepted", AlreadyTerminalOutcome => "already_completed", FailedCancelOutcome fail when fail.Error.ProviderErrorCode == "fal_cleanup_not_found" => "not_found", FailedCancelOutcome fail when fail.Error.ProviderErrorCode == "fal_cleanup_unknown" => "unknown", LocalStopOnlyOutcome => "unknown", _ => "failed" };
        public async Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            if (!ValidHandle(handle)) return new FailedResultOutcome(Error("Invalid fal Veo lifecycle binding."));
            var response = await CallAsync(handle.ResponseUrl!, HttpMethod.Get, ct).ConfigureAwait(false);
            if (response.Error != null) return new FailedResultOutcome(response.Error);
            try
            {
                var video = JsonNode.Parse(response.Response!.Body)?["video"] as JsonObject;
                if (video is null || !Uri.TryCreate(video["url"]?.GetValue<string>(), UriKind.Absolute, out var url) || url.Scheme != "https" || !url.IsDefaultPort || url.UserInfo.Length != 0 || !(url.Host == "fal.media" || url.Host.EndsWith(".fal.media", StringComparison.OrdinalIgnoreCase))) return new FailedResultOutcome(Error("fal result did not contain a safe video URL."));
                var mime = video["content_type"]?.GetValue<string>();
                if (mime != null && mime != "video/mp4") return new FailedResultOutcome(Error("fal result has an unsupported video type."));
                return new SuccessResultOutcome(new ProviderResultEnvelope(new[] { new ResultArtifact("video", new RemoteArtifactBody(url), mime ?? "video/mp4", new Dictionary<string, JsonNode>()) }, new Dictionary<string, JsonNode>()));
            }
            catch (Exception ex) when (ex is System.Text.Json.JsonException or InvalidOperationException) { return new FailedResultOutcome(Error("fal result was malformed.")); }
        }
        private async Task<(FalHttpResponse? Response, GenerationError? Error)> CallAsync(Uri url, HttpMethod method, CancellationToken ct, bool allowCancelFailure = false)
        {
            string? key;
            try { key = _key(); } catch { return (null, VideoCredentialErrors.AccessFailed()); }
            if (string.IsNullOrWhiteSpace(key)) return (null, VideoCredentialErrors.Missing("fal"));
            try
            {
                var result = await _client.SendAsync(key!, method, url, null, ct).ConfigureAwait(false);
                return result.IsSuccessStatusCode || allowCancelFailure && result.StatusCode is 400 or 404 ? (result, null) : (null, VideoCredentialErrors.FromHttp("fal", result.StatusCode, result.Body));
            }
            catch (Exception ex) when (ex is HttpRequestException || ex is OperationCanceledException && !ct.IsCancellationRequested) { return (null, Error("fal video lifecycle request failed.")); }
        }
        private static string? ParseStatus(string body) { try { return JsonNode.Parse(body)?["status"]?.GetValue<string>(); } catch { return null; } }
        private static GenerationError Error(string message) => new(GenerationErrorCode.ExecutionFailed, message, false);
    }
}
