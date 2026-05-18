using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Replicate
{
    public sealed class ReplicateApiClient
    {
        private static readonly Uri DefaultApiBaseUri =
            new Uri("https://api.replicate.com/", UriKind.Absolute);

        private readonly Uri _apiBaseUri;
        private readonly HttpClient _httpClient;

        public ReplicateApiClient(HttpClient? httpClient = null, Uri? apiBaseUri = null)
        {
            _apiBaseUri = apiBaseUri ?? DefaultApiBaseUri;
            ValidateApiUrl(_apiBaseUri);

            _httpClient = httpClient ?? new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(5),
            };
        }

        public sealed class UploadedFile
        {
            public UploadedFile(string id, Uri fileUrl)
            {
                if (string.IsNullOrWhiteSpace(id))
                    throw new ArgumentException(
                        "Replicate file id must be non-empty.",
                        nameof(id));
                ValidateApiUrl(fileUrl);

                Id = id;
                FileUrl = fileUrl;
            }

            public string Id { get; }
            public Uri FileUrl { get; }
        }

        public Task<ReplicateHttpResponse> CreatePredictionAsync(
            string apiToken,
            ReplicatePredictionEndpoint endpoint,
            string bodyJson,
            CancellationToken ct)
        {
            if (endpoint is null) throw new ArgumentNullException(nameof(endpoint));
            return PostJsonAsync(apiToken, BuildApiUri(endpoint.CreatePredictionPath), bodyJson, ct);
        }

        public Task<ReplicateHttpResponse> GetPredictionAsync(
            string apiToken,
            string predictionId,
            CancellationToken ct) =>
            GetJsonAsync(apiToken, BuildApiUri(
                "v1/predictions/" + EscapePathSegment(predictionId, nameof(predictionId))), ct);

        public Task<ReplicateHttpResponse> CancelPredictionAsync(
            string apiToken,
            string predictionId,
            CancellationToken ct) =>
            CancelAsync(apiToken, BuildApiUri(
                "v1/predictions/" + EscapePathSegment(predictionId, nameof(predictionId)) + "/cancel"), ct);

        public Task<ReplicateHttpResponse> PostJsonAsync(
            string apiToken,
            Uri url,
            string bodyJson,
            CancellationToken ct) =>
            SendApiAsync(apiToken, HttpMethod.Post, url, bodyJson, ct);

        public Task<ReplicateHttpResponse> GetJsonAsync(
            string apiToken,
            Uri url,
            CancellationToken ct) =>
            SendApiAsync(apiToken, HttpMethod.Get, url, bodyJson: null, ct);

        public Task<ReplicateHttpResponse> CancelAsync(
            string apiToken,
            Uri url,
            CancellationToken ct) =>
            SendApiAsync(apiToken, HttpMethod.Post, url, bodyJson: null, ct);

        public async Task<UploadedFile> UploadFileAsync(
            string apiToken,
            string fileName,
            byte[] bytes,
            string mimeType,
            string metadataJson,
            CancellationToken ct)
        {
            ValidateToken(apiToken);
            if (string.IsNullOrWhiteSpace(fileName))
                throw new ArgumentException(
                    "Replicate file name must be non-empty.",
                    nameof(fileName));
            if (bytes is null || bytes.Length == 0)
                throw new ArgumentException(
                    "Replicate file content must be non-empty.",
                    nameof(bytes));
            if (string.IsNullOrWhiteSpace(mimeType))
                throw new ArgumentException(
                    "Replicate file MIME type must be non-empty.",
                    nameof(mimeType));

            var metadata = string.IsNullOrWhiteSpace(metadataJson) ? "{}" : metadataJson;

            using var request = new HttpRequestMessage(
                HttpMethod.Post,
                BuildApiUri("v1/files"));
            request.Headers.Authorization = new AuthenticationHeaderValue("Token", apiToken);

            using var form = new MultipartFormDataContent();
            var fileContent = new ByteArrayContent(bytes);
            fileContent.Headers.ContentType = new MediaTypeHeaderValue(mimeType);
            form.Add(fileContent, "content", fileName);
            form.Add(new StringContent(metadata, Encoding.UTF8, "application/json"), "metadata");
            request.Content = form;

            using var response = await _httpClient.SendAsync(request, ct)
                .ConfigureAwait(false);
            var body = response.Content is null
                ? string.Empty
                : await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!response.IsSuccessStatusCode)
                throw new HttpRequestException("Replicate file upload failed.");

            return ParseUploadedFile(body);
        }

        public async Task<ReplicateHttpResponse> SendApiAsync(
            string apiToken,
            HttpMethod method,
            Uri url,
            string? bodyJson,
            CancellationToken ct)
        {
            ValidateToken(apiToken);
            if (method is null) throw new ArgumentNullException(nameof(method));
            ValidateApiUrl(url);

            using var request = new HttpRequestMessage(method, url);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
            if (bodyJson is not null)
                request.Content = new StringContent(bodyJson, Encoding.UTF8, "application/json");

            using var response = await _httpClient.SendAsync(request, ct)
                .ConfigureAwait(false);
            var body = response.Content is null
                ? string.Empty
                : await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            return new ReplicateHttpResponse(
                (int)response.StatusCode,
                body,
                CopyHeaders(response));
        }

        public static HttpRequestMessage BuildAuthenticatedOutputRequest(
            string apiToken,
            Uri outputUrl)
        {
            ValidateToken(apiToken);
            ValidateOutputUrl(outputUrl);

            var request = new HttpRequestMessage(HttpMethod.Get, outputUrl);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
            return request;
        }

        private Uri BuildApiUri(string relativePath)
        {
            if (string.IsNullOrWhiteSpace(relativePath))
                throw new ArgumentException(
                    "Replicate API relative path must be non-empty.",
                    nameof(relativePath));
            if (Uri.TryCreate(relativePath, UriKind.Absolute, out _))
                throw new ArgumentException(
                    "Replicate API path must be relative.",
                    nameof(relativePath));

            return new Uri(_apiBaseUri, relativePath.TrimStart('/'));
        }

        private static void ValidateToken(string apiToken)
        {
            if (string.IsNullOrWhiteSpace(apiToken))
                throw new ArgumentException(
                    "Replicate API token must be non-empty.", nameof(apiToken));
        }

        private static void ValidateApiUrl(Uri url)
        {
            if (url is null) throw new ArgumentNullException(nameof(url));
            if (!url.IsAbsoluteUri)
                throw new ArgumentException("Replicate API URL must be absolute.", nameof(url));
            if (url.Scheme != Uri.UriSchemeHttps)
                throw new ArgumentException(
                    $"Replicate API URL must use https scheme; got '{url.Scheme}'.",
                    nameof(url));
            if (!string.Equals(url.Host, "api.replicate.com", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException(
                    $"Replicate API URL host must be api.replicate.com; got '{url.Host}'.",
                    nameof(url));
        }

        private static void ValidateOutputUrl(Uri url)
        {
            if (url is null) throw new ArgumentNullException(nameof(url));
            if (!url.IsAbsoluteUri)
                throw new ArgumentException("Replicate output URL must be absolute.", nameof(url));
            if (url.Scheme != Uri.UriSchemeHttps)
                throw new ArgumentException(
                    $"Replicate output URL must use https scheme; got '{url.Scheme}'.",
                    nameof(url));
            if (!IsReplicateDeliveryHost(url.Host))
                throw new ArgumentException(
                    $"Replicate output URL host must be replicate.delivery or a replicate.delivery subdomain; got '{url.Host}'.",
                    nameof(url));
        }

        private static bool IsReplicateDeliveryHost(string host) =>
            string.Equals(host, "replicate.delivery", StringComparison.OrdinalIgnoreCase) ||
            host.EndsWith(".replicate.delivery", StringComparison.OrdinalIgnoreCase);

        private static string EscapePathSegment(string value, string paramName)
        {
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException(
                    "Replicate prediction id must be non-empty.",
                    paramName);
            if (value.IndexOfAny(new[] { '/', '?', '#' }) >= 0)
                throw new ArgumentException(
                    "Replicate prediction id must be a single path segment.",
                    paramName);

            return Uri.EscapeDataString(value);
        }

        private static UploadedFile ParseUploadedFile(string body)
        {
            try
            {
                using var document = JsonDocument.Parse(body);
                var root = document.RootElement;
                if (root.ValueKind != JsonValueKind.Object)
                    throw MissingUploadResponse();

                var id = root.TryGetProperty("id", out var idElement)
                    && idElement.ValueKind == JsonValueKind.String
                    ? idElement.GetString()
                    : null;
                var fileUrlText =
                    root.TryGetProperty("urls", out var urlsElement)
                    && urlsElement.ValueKind == JsonValueKind.Object
                    && urlsElement.TryGetProperty("get", out var getElement)
                    && getElement.ValueKind == JsonValueKind.String
                        ? getElement.GetString()
                        : null;

                if (string.IsNullOrWhiteSpace(id)
                    || string.IsNullOrWhiteSpace(fileUrlText)
                    || !Uri.TryCreate(fileUrlText, UriKind.Absolute, out var fileUrl))
                {
                    throw MissingUploadResponse();
                }

                return new UploadedFile(id!, fileUrl);
            }
            catch (JsonException)
            {
                throw MissingUploadResponse();
            }
        }

        private static ArgumentException MissingUploadResponse() =>
            new ArgumentException(
                "Replicate file upload response was missing file id or urls.get.");

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
