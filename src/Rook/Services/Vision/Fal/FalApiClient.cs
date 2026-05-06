using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Fal
{
    public readonly struct FalJsonPlatformHeaders
    {
        private FalJsonPlatformHeaders(
            int objectLifecyclePreferenceSeconds,
            bool disableStoreIo,
            bool disableFalRetry)
        {
            ObjectLifecyclePreferenceSeconds = objectLifecyclePreferenceSeconds;
            DisableStoreIo = disableStoreIo;
            DisableFalRetry = disableFalRetry;
            IsSpecified = true;
        }

        public int ObjectLifecyclePreferenceSeconds { get; }
        public bool DisableStoreIo { get; }
        public bool DisableFalRetry { get; }
        public bool IsSpecified { get; }

        public static FalJsonPlatformHeaders ForSeedanceSubmit(
            int objectLifecyclePreferenceSeconds,
            bool disableStoreIo,
            bool disableFalRetry)
        {
            if (objectLifecyclePreferenceSeconds <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(objectLifecyclePreferenceSeconds),
                    "fal object lifecycle preference seconds must be positive.");

            return new FalJsonPlatformHeaders(
                objectLifecyclePreferenceSeconds,
                disableStoreIo,
                disableFalRetry);
        }
    }

    public readonly struct FalUploadPlatformHeaders
    {
        private FalUploadPlatformHeaders(int objectLifecycleSeconds)
        {
            ObjectLifecycleSeconds = objectLifecycleSeconds;
            IsSpecified = true;
        }

        public int ObjectLifecycleSeconds { get; }
        public bool IsSpecified { get; }

        public static FalUploadPlatformHeaders ForSourceUpload(int objectLifecycleSeconds)
        {
            if (objectLifecycleSeconds <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(objectLifecycleSeconds),
                    "fal object lifecycle seconds must be positive.");

            return new FalUploadPlatformHeaders(objectLifecycleSeconds);
        }
    }

    public sealed class FalApiException : Exception
    {
        public FalApiException(string message)
            : base(message)
        {
        }
    }

    public sealed class FalApiClient
    {
        private static readonly Uri UploadInitiateUrl = new(
            "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3");

        private readonly HttpClient _httpClient;

        public FalApiClient(HttpClient? httpClient = null)
        {
            _httpClient = httpClient ?? new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(5),
            };
        }

        public Task<FalHttpResponse> PostJsonAsync(
            string apiKey,
            Uri url,
            string bodyJson,
            CancellationToken ct) =>
            SendAsync(apiKey, HttpMethod.Post, url, bodyJson, ct);

        public Task<FalHttpResponse> PostJsonAsync(
            string apiKey,
            Uri url,
            string bodyJson,
            FalJsonPlatformHeaders platformHeaders,
            CancellationToken ct) =>
            SendAsync(apiKey, HttpMethod.Post, url, bodyJson, platformHeaders, ct);

        public Task<FalHttpResponse> GetAsync(
            string apiKey,
            Uri url,
            CancellationToken ct) =>
            SendAsync(apiKey, HttpMethod.Get, url, bodyJson: null, ct);

        public Task<FalHttpResponse> SendAsync(
            string apiKey,
            HttpMethod method,
            Uri url,
            string? bodyJson,
            CancellationToken ct)
        {
            return SendAsync(
                apiKey,
                method,
                url,
                bodyJson,
                platformHeaders: null,
                ct);
        }

        private async Task<FalHttpResponse> SendAsync(
            string apiKey,
            HttpMethod method,
            Uri url,
            string? bodyJson,
            FalJsonPlatformHeaders? platformHeaders,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(apiKey))
                throw new ArgumentException("fal API key must be non-empty.", nameof(apiKey));
            if (method is null) throw new ArgumentNullException(nameof(method));
            if (url is null) throw new ArgumentNullException(nameof(url));
            if (!url.IsAbsoluteUri)
                throw new ArgumentException("fal URL must be absolute.", nameof(url));
            if (url.Scheme != Uri.UriSchemeHttps)
                throw new ArgumentException(
                    $"fal URL must use https scheme; got '{url.Scheme}'.",
                    nameof(url));
            if (!IsAllowedFalHost(url.Host))
                throw new ArgumentException(
                    $"fal URL host must be fal.run or a fal.run subdomain; got '{url.Host}'.",
                    nameof(url));

            using var request = new HttpRequestMessage(method, url);
            request.Headers.Authorization = new AuthenticationHeaderValue("Key", apiKey);
            if (platformHeaders.HasValue)
                ApplyJsonPlatformHeaders(request, platformHeaders.Value);

            if (bodyJson is not null)
            {
                request.Content = new StringContent(bodyJson, Encoding.UTF8, "application/json");
            }

            using var response = await _httpClient.SendAsync(request, ct)
                .ConfigureAwait(false);
            var body = response.Content is null
                ? string.Empty
                : await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            return new FalHttpResponse(
                (int)response.StatusCode,
                body,
                CopyHeaders(response));
        }

        public async Task<string> UploadFileToCdnAsync(
            string apiKey,
            string fileName,
            byte[] bytes,
            string contentType,
            FalUploadPlatformHeaders platformHeaders,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(apiKey))
                throw new ArgumentException("fal API key must be non-empty.", nameof(apiKey));
            if (!IsSafeFileName(fileName))
                throw new ArgumentException("fal upload file name must be a safe file name.", nameof(fileName));
            if (bytes is null) throw new ArgumentNullException(nameof(bytes));
            if (bytes.Length == 0)
                throw new ArgumentException("fal upload bytes must be non-empty.", nameof(bytes));
            if (string.IsNullOrWhiteSpace(contentType))
                throw new ArgumentException("fal upload content type must be non-empty.", nameof(contentType));
            if (!MediaTypeHeaderValue.TryParse(contentType, out var parsedContentType))
                throw new ArgumentException("fal upload content type must be valid.", nameof(contentType));
            if (!platformHeaders.IsSpecified)
                throw new ArgumentNullException(nameof(platformHeaders));

            var initiateBody = JsonSerializer.Serialize(new Dictionary<string, string>
            {
                ["content_type"] = contentType,
                ["file_name"] = fileName,
            });

            using var initiateRequest = new HttpRequestMessage(HttpMethod.Post, UploadInitiateUrl);
            initiateRequest.Headers.Authorization = new AuthenticationHeaderValue("Key", apiKey);
            initiateRequest.Headers.TryAddWithoutValidation(
                "X-Fal-Object-Lifecycle",
                LifecycleJson(platformHeaders.ObjectLifecycleSeconds));
            initiateRequest.Content = new StringContent(initiateBody, Encoding.UTF8, "application/json");

            using var initiateResponse = await SendUploadRequestAsync(
                initiateRequest,
                "fal upload initiate request failed.",
                ct).ConfigureAwait(false);
            var initiateResponseBody = initiateResponse.Content is null
                ? string.Empty
                : await initiateResponse.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!initiateResponse.IsSuccessStatusCode)
                throw new FalApiException(
                    $"fal upload initiate request failed with status {(int)initiateResponse.StatusCode}.");

            var uploadInfo = ParseUploadInitiateResponse(initiateResponseBody);

            using var uploadRequest = new HttpRequestMessage(HttpMethod.Put, uploadInfo.UploadUrl);
            uploadRequest.Content = new ByteArrayContent(bytes);
            uploadRequest.Content.Headers.ContentType = parsedContentType;

            using var uploadResponse = await SendUploadRequestAsync(
                uploadRequest,
                "fal CDN upload failed.",
                ct).ConfigureAwait(false);

            if (!uploadResponse.IsSuccessStatusCode)
                throw new FalApiException(
                    $"fal CDN upload failed with status {(int)uploadResponse.StatusCode}.");

            return uploadInfo.FileUrl.ToString();
        }

        private async Task<HttpResponseMessage> SendUploadRequestAsync(
            HttpRequestMessage request,
            string failureMessage,
            CancellationToken ct)
        {
            try
            {
                return await _httpClient.SendAsync(request, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (HttpRequestException)
            {
                throw new FalApiException(failureMessage);
            }
            catch (TaskCanceledException)
            {
                throw new FalApiException(failureMessage);
            }
        }

        private static void ApplyJsonPlatformHeaders(
            HttpRequestMessage request,
            FalJsonPlatformHeaders platformHeaders)
        {
            if (!platformHeaders.IsSpecified)
                throw new ArgumentNullException(nameof(platformHeaders));

            request.Headers.TryAddWithoutValidation(
                "X-Fal-Object-Lifecycle-Preference",
                LifecycleJson(platformHeaders.ObjectLifecyclePreferenceSeconds));
            request.Headers.TryAddWithoutValidation(
                "X-Fal-Store-IO",
                platformHeaders.DisableStoreIo ? "0" : "1");
            request.Headers.TryAddWithoutValidation(
                "X-Fal-No-Retry",
                platformHeaders.DisableFalRetry ? "1" : "0");
        }

        private static (Uri UploadUrl, Uri FileUrl) ParseUploadInitiateResponse(string body)
        {
            try
            {
                using var doc = JsonDocument.Parse(body);
                if (!doc.RootElement.TryGetProperty("upload_url", out var uploadUrlElement) ||
                    !doc.RootElement.TryGetProperty("file_url", out var fileUrlElement))
                {
                    throw InvalidInitiateResponse();
                }

                var uploadUrlText = uploadUrlElement.GetString();
                var fileUrlText = fileUrlElement.GetString();
                if (!Uri.TryCreate(uploadUrlText, UriKind.Absolute, out var uploadUrl) ||
                    uploadUrl.Scheme != Uri.UriSchemeHttps ||
                    !Uri.TryCreate(fileUrlText, UriKind.Absolute, out var fileUrl) ||
                    !IsFalCdnFileUrl(fileUrl))
                {
                    throw InvalidInitiateResponse();
                }

                return (uploadUrl, fileUrl);
            }
            catch (JsonException)
            {
                throw InvalidInitiateResponse();
            }
            catch (InvalidOperationException)
            {
                throw InvalidInitiateResponse();
            }
        }

        private static FalApiException InvalidInitiateResponse() =>
            new("fal upload initiate returned an invalid response.");

        private static string LifecycleJson(int seconds) =>
            $"{{\"expiration_duration_seconds\":{seconds}}}";

        private static bool IsSafeFileName(string fileName)
        {
            if (string.IsNullOrWhiteSpace(fileName))
                return false;
            if (fileName == "." || fileName == "..")
                return false;
            if (fileName.Contains("/") || fileName.Contains("\\"))
                return false;
            if (Uri.TryCreate(fileName, UriKind.Absolute, out _))
                return false;

            return true;
        }

        private static bool IsFalCdnFileUrl(Uri url) =>
            url.Scheme == Uri.UriSchemeHttps &&
            url.Host.StartsWith("v3", StringComparison.OrdinalIgnoreCase) &&
            url.Host.EndsWith(".fal.media", StringComparison.OrdinalIgnoreCase) &&
            url.AbsolutePath.StartsWith("/files/", StringComparison.Ordinal);

        private static bool IsAllowedFalHost(string host) =>
            string.Equals(host, "fal.run", StringComparison.OrdinalIgnoreCase) ||
            host.EndsWith(".fal.run", StringComparison.OrdinalIgnoreCase);

        private static IReadOnlyDictionary<string, IReadOnlyList<string>> CopyHeaders(
            HttpResponseMessage response)
        {
            var headers = new Dictionary<string, IReadOnlyList<string>>(
                StringComparer.OrdinalIgnoreCase);

            foreach (var header in response.Headers)
                headers[header.Key] = new ReadOnlyCollection<string>(
                    new List<string>(header.Value));

            if (response.Content is not null)
            {
                foreach (var header in response.Content.Headers)
                    headers[header.Key] = new ReadOnlyCollection<string>(
                        new List<string>(header.Value));
            }

            return new ReadOnlyDictionary<string, IReadOnlyList<string>>(headers);
        }
    }
}
