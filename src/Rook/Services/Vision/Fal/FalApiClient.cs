using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Fal
{
    public sealed class FalApiClient
    {
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

        public Task<FalHttpResponse> GetAsync(
            string apiKey,
            Uri url,
            CancellationToken ct) =>
            SendAsync(apiKey, HttpMethod.Get, url, bodyJson: null, ct);

        public async Task<FalHttpResponse> SendAsync(
            string apiKey,
            HttpMethod method,
            Uri url,
            string? bodyJson,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(apiKey))
                throw new ArgumentException("fal API key must be non-empty.", nameof(apiKey));
            if (method is null) throw new ArgumentNullException(nameof(method));
            if (url is null) throw new ArgumentNullException(nameof(url));
            if (!url.IsAbsoluteUri)
                throw new ArgumentException("fal URL must be absolute.", nameof(url));
            if (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps)
                throw new ArgumentException(
                    $"fal URL must use http or https scheme; got '{url.Scheme}'.",
                    nameof(url));

            using var request = new HttpRequestMessage(method, url);
            request.Headers.Authorization = new AuthenticationHeaderValue("Key", apiKey);
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

        private static IReadOnlyDictionary<string, IReadOnlyList<string>> CopyHeaders(
            HttpResponseMessage response)
        {
            var headers = new Dictionary<string, IReadOnlyList<string>>(
                StringComparer.OrdinalIgnoreCase);

            foreach (var header in response.Headers)
                headers[header.Key] = new List<string>(header.Value).ToArray();

            if (response.Content is not null)
            {
                foreach (var header in response.Content.Headers)
                    headers[header.Key] = new List<string>(header.Value).ToArray();
            }

            return headers;
        }
    }
}
