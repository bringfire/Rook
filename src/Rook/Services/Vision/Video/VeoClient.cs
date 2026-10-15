using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal sealed class VeoDownloadException : HttpRequestException
    {
        internal VeoDownloadException(int status, bool apiCredentialResponse) : base("Google video download request failed.") { HttpStatus = status; ApiCredentialResponse = apiCredentialResponse; }
        internal int HttpStatus { get; }
        internal bool ApiCredentialResponse { get; }
    }
    /// <summary>
    /// Thin HTTP wrapper for Google's Veo video generation API. Wraps the
    /// long-running operation dance: start → poll → cancel → download.
    /// All calls accept a <see cref="CancellationToken"/> so plugin
    /// shutdown aborts in-flight work cleanly.
    ///
    /// Endpoints (Gemini API):
    ///   POST /v1beta/models/{model}:predictLongRunning  → returns operation name
    ///   GET  /v1beta/{operation-name}                   → poll status
    ///   POST /v1beta/{operation-name}:cancel            → cancel
    ///   GET  {video.uri} (with x-goog-api-key header)   → download MP4
    ///
    /// This client is pure HTTP plumbing — it returns primitive
    /// <see cref="VeoStartResponse"/> / <see cref="VeoPollResponse"/> /
    /// <see cref="VeoCancelResponse"/> records that <see cref="VeoProvider"/>
    /// translates into typed <see cref="VideoJobError"/> values via
    /// <see cref="VeoErrorMapper"/>. The client itself never constructs
    /// domain types or knows about <see cref="VideoErrorCode"/>.
    /// </summary>
    public sealed class VeoClient
    {
        private const string BaseUrl = "https://generativelanguage.googleapis.com/v1beta";

        private static readonly HttpClient s_default = CreateDefaultHttpClient();
        private readonly HttpClient _http;
        private readonly long _maxVideoBytes;

        public VeoClient() : this(s_default) { }

        // Test seam: inject an HttpClient backed by a TestHttpMessageHandler.
        internal VeoClient(HttpClient http, long maxVideoBytes = VideoArtifactMaterializer.MaxGeneratedVideoBytes)
        {
            _http = http ?? throw new ArgumentNullException(nameof(http));
            if (maxVideoBytes <= 0) throw new ArgumentOutOfRangeException(nameof(maxVideoBytes));
            _maxVideoBytes = maxVideoBytes;
        }

        private static HttpClient CreateDefaultHttpClient()
        {
            // Individual HTTP calls are short; videos can take 6+ minutes
            // but that's spread across many polls, not one request. 2 min
            // per call is plenty for start/poll/download chunks.
            return new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromMinutes(2) };
        }

        public async Task<VeoStartResponse> StartGenerationAsync(
            string apiKey,
            VideoGenerationRequest request,
            VeoOptions options,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct, Action? beforeDispatch = null)
        {
            var url = $"{BaseUrl}/models/{request.Model}:predictLongRunning";
            var body = BuildPredictBody(request, options, resolvedMedia);
            var json = JsonSerializer.Serialize(body, JsonOptions);

            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            using var httpRequest = new HttpRequestMessage(HttpMethod.Post, url) { Content = content };
            httpRequest.Headers.Add("x-goog-api-key", apiKey);

            beforeDispatch?.Invoke();
            ct.ThrowIfCancellationRequested();
            using var response = await _http.SendAsync(httpRequest, ct).ConfigureAwait(false);
            var responseJson = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!response.IsSuccessStatusCode)
                return new VeoStartResponse(
                    Success: false,
                    OperationName: null,
                    StatusCode: (int)response.StatusCode,
                    ErrorBody: responseJson);

            using var doc = JsonDocument.Parse(responseJson);
            if (!doc.RootElement.TryGetProperty("name", out var nameEl)
                || nameEl.ValueKind != JsonValueKind.String)
            {
                return new VeoStartResponse(
                    Success: false,
                    OperationName: null,
                    StatusCode: (int)response.StatusCode,
                    ErrorBody: $"Veo response missing 'name' field: {Truncate(responseJson, 500)}");
            }

            return new VeoStartResponse(
                Success: true,
                OperationName: nameEl.GetString(),
                StatusCode: (int)response.StatusCode,
                ErrorBody: null);
        }

        public async Task<VeoPollResponse> PollOperationAsync(
            string apiKey,
            string operationName,
            CancellationToken ct)
        {
            // operationName may come back as either "models/.../operations/abc"
            // or just "operations/abc"; both resolve correctly under /v1beta/{name}.
            var url = $"{BaseUrl}/{operationName}";

            using var httpRequest = new HttpRequestMessage(HttpMethod.Get, url);
            httpRequest.Headers.Add("x-goog-api-key", apiKey);

            using var response = await _http.SendAsync(httpRequest, ct).ConfigureAwait(false);
            var responseJson = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!response.IsSuccessStatusCode)
                return new VeoPollResponse(
                    Success: false,
                    Done: false,
                    VideoUri: null,
                    StatusCode: (int)response.StatusCode,
                    ErrorBody: responseJson);

            using var doc = JsonDocument.Parse(responseJson);
            var root = doc.RootElement;

            var done = root.TryGetProperty("done", out var doneEl)
                       && doneEl.ValueKind == JsonValueKind.True;

            if (!done)
                return new VeoPollResponse(
                    Success: true, Done: false, VideoUri: null,
                    StatusCode: (int)response.StatusCode, ErrorBody: null);

            // Operation done; check for operation-level error first.
            if (root.TryGetProperty("error", out var errEl))
            {
                var errMsg = errEl.TryGetProperty("message", out var m) && m.ValueKind == JsonValueKind.String
                    ? m.GetString()
                    : errEl.GetRawText();
                return new VeoPollResponse(
                    Success: false, Done: true, VideoUri: null,
                    StatusCode: (int)response.StatusCode,
                    ErrorBody: $"Veo operation failed: {errMsg}");
            }

            if (!root.TryGetProperty("response", out var responseEl))
                return new VeoPollResponse(
                    Success: false, Done: true, VideoUri: null,
                    StatusCode: (int)response.StatusCode,
                    ErrorBody: $"Veo completed but response field missing: {Truncate(responseJson, 500)}");

            var videoUri = ExtractVideoUri(responseEl);

            if (!string.IsNullOrEmpty(videoUri))
                return new VeoPollResponse(
                    Success: true, Done: true, VideoUri: videoUri,
                    StatusCode: (int)response.StatusCode, ErrorBody: null);

            return new VeoPollResponse(
                Success: false, Done: true, VideoUri: null,
                StatusCode: (int)response.StatusCode,
                ErrorBody: $"Veo completed but no video URI in response: {Truncate(responseJson, 500)}");
        }

        public async Task<VeoCancelResponse> CancelOperationAsync(
            string apiKey,
            string operationName,
            CancellationToken ct)
        {
            var url = $"{BaseUrl}/{operationName}:cancel";

            using var httpRequest = new HttpRequestMessage(HttpMethod.Post, url);
            httpRequest.Headers.Add("x-goog-api-key", apiKey);

            using var response = await _http.SendAsync(httpRequest, ct).ConfigureAwait(false);
            var responseJson = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!response.IsSuccessStatusCode)
                return new VeoCancelResponse(
                    Success: false,
                    StatusCode: (int)response.StatusCode,
                    ErrorBody: responseJson);

            return new VeoCancelResponse(
                Success: true,
                StatusCode: (int)response.StatusCode,
                ErrorBody: null);
        }

        public async Task<byte[]> DownloadVideoAsync(
            string apiKey,
            string videoUri,
            CancellationToken ct)
        {
            if (!Uri.TryCreate(videoUri, UriKind.Absolute, out var current) || !IsSafeDownloadUri(current)) throw new HttpRequestException("Google video download URI is not trusted.");
            for (int redirects = 0; ; redirects++)
            {
                ct.ThrowIfCancellationRequested();
                using var httpRequest = new HttpRequestMessage(HttpMethod.Get, current);
                // CDN redirects use their signed URL, never the caller's API credential.
                if (current.Host.Equals("generativelanguage.googleapis.com", StringComparison.OrdinalIgnoreCase)) httpRequest.Headers.Add("x-goog-api-key", apiKey);
                using var response = await _http.SendAsync(httpRequest, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
                var code = (int)response.StatusCode;
                if (code is 301 or 302 or 303 or 307 or 308)
                {
                    if (redirects >= 3 || response.Headers.Location is not { } location || !Uri.TryCreate(current, location, out var next) || !IsSafeDownloadUri(next)) throw new HttpRequestException("Google video download redirect is not trusted or exceeds its limit.");
                    current = next; continue;
                }
                if (!response.IsSuccessStatusCode) throw new VeoDownloadException(code, current.Host.Equals("generativelanguage.googleapis.com", StringComparison.OrdinalIgnoreCase));
                if (response.Content.Headers.ContentLength is { } length && length > _maxVideoBytes) throw new HttpRequestException("Google video exceeds the local byte limit.");
#if NETFRAMEWORK
                using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
#else
                using var stream = await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
#endif
                using var ms = new MemoryStream();
                var buffer = new byte[81920];
                while (true)
                {
                    // Read only the remaining allowance plus one byte to detect overflow.
                    var read = await stream.ReadAsync(buffer, 0, (int)Math.Min(buffer.Length, _maxVideoBytes - ms.Length + 1), ct).ConfigureAwait(false);
                    if (read == 0) return ms.ToArray();
                    if (ms.Length + read > _maxVideoBytes) throw new HttpRequestException("Google video exceeds the local byte limit.");
                    ms.Write(buffer, 0, read);
                }
            }
        }
        private static bool IsSafeDownloadUri(Uri uri) => uri.Scheme == "https" && uri.IsDefaultPort && uri.UserInfo.Length == 0 && !uri.IsLoopback && (uri.Host.Equals("generativelanguage.googleapis.com", StringComparison.OrdinalIgnoreCase) || uri.Host.Equals("storage.googleapis.com", StringComparison.OrdinalIgnoreCase) || uri.Host.EndsWith(".googlevideo.com", StringComparison.OrdinalIgnoreCase) || uri.Host.EndsWith(".googleusercontent.com", StringComparison.OrdinalIgnoreCase));

        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
        };

        private static object BuildPredictBody(
            VideoGenerationRequest request,
            VeoOptions options,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia)
        {
            var instance = VeoInputCodec.BuildInstance(request, resolvedMedia);

            var parameters = new Dictionary<string, object?>
            {
                ["aspectRatio"] = request.AspectRatio,
                // durationSeconds MUST be a JSON number, not a string.
                // Sending a string returns 400 INVALID_ARGUMENT.
                ["durationSeconds"] = request.DurationSeconds,
                ["personGeneration"] = MapPersonGeneration(options.PersonGeneration),
                // numberOfVideos is a Vertex parameter and is NOT supported
                // by the Gemini generativelanguage endpoint; it returns
                // 400 "numberOfVideos isn't supported by this model" if
                // included. V1a validates NumberOfVideos == 1 anyway.
            };

            // Veo 2 doesn't accept the resolution parameter (fixed at 720p
            // by API). Send it only for Veo 3.x.
            if (!request.Model.StartsWith("veo-2", StringComparison.OrdinalIgnoreCase))
                parameters["resolution"] = request.Resolution;

            if (request.Seed.HasValue) parameters["seed"] = request.Seed.Value;

            return new
            {
                instances = new[] { instance },
                parameters,
            };
        }

        private static string MapPersonGeneration(PersonGenerationPolicy policy) => policy switch
        {
            PersonGenerationPolicy.DontAllow => "dont_allow",
            PersonGenerationPolicy.AllowAdult => "allow_adult",
            PersonGenerationPolicy.AllowAll => "allow_all",
            _ => throw new ArgumentOutOfRangeException(
                nameof(policy), policy,
                "Unknown PersonGenerationPolicy value (catalog should have rejected this earlier)."),
        };

        // Veo response can carry the video URI under any of these shapes;
        // accept all so a documented API drift doesn't break us.
        private static string? ExtractVideoUri(JsonElement responseEl)
        {
            if (responseEl.TryGetProperty("generatedVideos", out var generatedVideosEl)
                && generatedVideosEl.ValueKind == JsonValueKind.Array
                && generatedVideosEl.GetArrayLength() > 0)
            {
                var uri = ExtractVideoUriFromSample(generatedVideosEl[0]);
                if (!string.IsNullOrEmpty(uri)) return uri;
            }

            if (responseEl.TryGetProperty("generateVideoResponse", out var gvrEl)
                && gvrEl.TryGetProperty("generatedSamples", out var samplesEl)
                && samplesEl.ValueKind == JsonValueKind.Array
                && samplesEl.GetArrayLength() > 0)
            {
                return ExtractVideoUriFromSample(samplesEl[0]);
            }

            return null;
        }

        private static string? ExtractVideoUriFromSample(JsonElement sample)
        {
            if (!sample.TryGetProperty("video", out var videoEl)) return null;

            if (videoEl.ValueKind == JsonValueKind.String)
                return videoEl.GetString();

            if (videoEl.ValueKind != JsonValueKind.Object) return null;

            if (videoEl.TryGetProperty("uri", out var uriEl)
                && uriEl.ValueKind == JsonValueKind.String)
                return uriEl.GetString();

            if (videoEl.TryGetProperty("file", out var fileEl))
            {
                if (fileEl.ValueKind == JsonValueKind.String) return fileEl.GetString();
                if (fileEl.ValueKind == JsonValueKind.Object
                    && fileEl.TryGetProperty("uri", out var fileUriEl)
                    && fileUriEl.ValueKind == JsonValueKind.String)
                    return fileUriEl.GetString();
            }

            if (videoEl.TryGetProperty("name", out var nameEl)
                && nameEl.ValueKind == JsonValueKind.String)
                return nameEl.GetString();

            return null;
        }

        private static string Truncate(string s, int maxLen) =>
            s.Length <= maxLen ? s : s.Substring(0, maxLen) + "...";
    }

    public sealed record VeoStartResponse(
        bool Success,
        string? OperationName,
        int? StatusCode,
        string? ErrorBody);

    public sealed record VeoPollResponse(
        bool Success,
        bool Done,
        string? VideoUri,
        int? StatusCode,
        string? ErrorBody);

    public sealed record VeoCancelResponse(
        bool Success,
        int? StatusCode,
        string? ErrorBody);
}
