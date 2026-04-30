# PR-10 Replicate Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a managed-only Replicate substrate that proves prediction API, lifecycle, error, pricing, handle, credential-key, and authenticated output-fetch contracts without exposing Replicate models or Settings UI.

**Architecture:** Add focused `Rook.Services.Vision.Replicate` substrate types parallel to the existing fal substrate. Keep Replicate out of default provider registries and out of `VisionProviderRegistrations.CreateCredentialMetadata()`. Treat API-host prediction calls and authenticated output-file proof as separate host contracts.

**Tech Stack:** C# multi-targeted `net7.0;net48`, `HttpClient`, `System.Text.Json.Nodes`, xUnit, existing generation seam types under `Rook.Services.Vision.Generation`.

---

## Scope Guard

This plan implements only the approved spec:

- Managed code only.
- Official-model endpoint only.
- No production model registration.
- No Replicate Settings card.
- No native routes.
- No async image UX.
- No production materializer integration.
- No live Replicate calls in normal tests.

Existing unrelated dirty files must remain untouched:

- `docs/rook_docs/work-queue.md`
- `knowledge/substrate_observations.jsonl`

## File Structure

Create:

- `src/Rook/Services/Vision/Replicate/ReplicateHttpResponse.cs`  
  Immutable HTTP response envelope, matching `FalHttpResponse` style.
- `src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs`  
  Bearer-auth prediction API client for `api.replicate.com` plus separate authenticated output-fetch proof seam for `replicate.delivery` hosts.
- `src/Rook/Services/Vision/Replicate/ReplicatePredictionEndpoint.cs`  
  Official-model endpoint descriptor that validates owner/name path segments.
- `src/Rook/Services/Vision/Replicate/ReplicateLifecycleMapper.cs`  
  Prediction body to `ProviderJobHandle` and `ProviderStatusOutcome` mapping.
- `src/Rook/Services/Vision/Replicate/ReplicateErrorMapper.cs`  
  HTTP/prediction/data-retention error mapping into `GenerationError`.
- `src/Rook/Services/Vision/Replicate/ReplicatePredictionPricing.cs`  
  Approximate extraction of `metrics.predict_time` and `metrics.total_time`.
- `src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs`
- `src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionEndpointTests.cs`
- `src/Rook.Tests/Services/Vision/Replicate/ReplicateLifecycleMapperTests.cs`
- `src/Rook.Tests/Services/Vision/Replicate/ReplicateErrorMapperTests.cs`
- `src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionPricingTests.cs`

Modify:

- `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`  
  Add explicit no-Replicate metadata guard.
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`  
  Add default `set_provider_secret` rejection for `provider_name: "replicate"`.

Do not modify:

- `src/RookNative/**`
- `src/Rook/UI/Vision/Resources/**`
- `src/Rook/Services/Vision/VisionProviderRegistrations.cs`, unless a boundary test reveals existing behavior already exposes Replicate. The expected PR-10 implementation leaves production metadata unchanged.

## Task 1: Replicate API Client And Host Boundaries

**Files:**
- Create: `src/Rook/Services/Vision/Replicate/ReplicateHttpResponse.cs`
- Create: `src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs`
- Test: `src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs`

- [ ] **Step 1: Write failing API client tests**

Create `src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs`:

```csharp
using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Replicate;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicateApiClientTests
    {
        [Fact]
        public async Task PostJsonAsync_sends_bearer_auth_and_json_body_to_api_host()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("{\"id\":\"pred-1\"}", Encoding.UTF8, "application/json"),
                    };
                },
            };
            var client = new ReplicateApiClient(new HttpClient(handler));

            var response = await client.PostJsonAsync(
                "r8_token",
                new Uri("https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"),
                "{\"input\":{\"prompt\":\"red cube\"}}",
                CancellationToken.None);

            Assert.Equal(200, response.StatusCode);
            Assert.Equal("{\"id\":\"pred-1\"}", response.Body);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", request.Headers.Authorization.Parameter);
            Assert.Equal("application/json", request.Content!.Headers.ContentType!.MediaType);
            Assert.Equal("{\"input\":{\"prompt\":\"red cube\"}}", body);
        }

        [Fact]
        public async Task SendApiAsync_rejects_non_api_replicate_hosts()
        {
            var handler = new TestHttpMessageHandler();
            var client = new ReplicateApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(() =>
                client.GetJsonAsync(
                    "r8_token",
                    new Uri("https://replicate.delivery/prediction-output.png"),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("https://api.replicate.com.evil.test/v1/predictions/pred-1")]
        [InlineData("https://evil-api.replicate.com/v1/predictions/pred-1")]
        [InlineData("http://api.replicate.com/v1/predictions/pred-1")]
        public async Task SendApiAsync_rejects_api_host_lookalikes_and_http(string url)
        {
            var handler = new TestHttpMessageHandler();
            var client = new ReplicateApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(() =>
                client.GetJsonAsync("r8_token", new Uri(url), CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task BuildAuthenticatedOutputRequest_allows_replicate_delivery_with_bearer_auth()
        {
            using var request = ReplicateApiClient.BuildAuthenticatedOutputRequest(
                "r8_token",
                new Uri("https://replicate.delivery/pbxt/output.png"));

            Assert.Equal(HttpMethod.Get, request.Method);
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", request.Headers.Authorization.Parameter);
            Assert.Equal("https://replicate.delivery/pbxt/output.png", request.RequestUri!.ToString());
        }

        [Fact]
        public async Task BuildAuthenticatedOutputRequest_allows_replicate_delivery_subdomains()
        {
            using var request = ReplicateApiClient.BuildAuthenticatedOutputRequest(
                "r8_token",
                new Uri("https://v3b.replicate.delivery/pbxt/output.png"));

            Assert.Equal("v3b.replicate.delivery", request.RequestUri!.Host);
        }

        [Theory]
        [InlineData("https://replicate.delivery.evil.test/pbxt/output.png")]
        [InlineData("https://evilreplicate.delivery/pbxt/output.png")]
        [InlineData("http://replicate.delivery/pbxt/output.png")]
        public void BuildAuthenticatedOutputRequest_rejects_output_host_lookalikes_and_http(string url)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicateApiClient.BuildAuthenticatedOutputRequest(
                    "r8_token",
                    new Uri(url)));
        }

        [Fact]
        public async Task GetJsonAsync_preserves_headers_case_insensitively()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ =>
                {
                    var response = new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("{\"status\":\"processing\"}", Encoding.UTF8, "application/json"),
                    };
                    response.Headers.TryAddWithoutValidation("X-Replicate-Request-Id", "req-1");
                    return response;
                },
            };
            var client = new ReplicateApiClient(new HttpClient(handler));

            var response = await client.GetJsonAsync(
                "r8_token",
                new Uri("https://api.replicate.com/v1/predictions/pred-1"),
                CancellationToken.None);

            Assert.True(response.Headers.ContainsKey("x-replicate-request-id"));
            Assert.Equal("req-1", response.Headers["x-replicate-request-id"].Single());
        }
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateApiClientTests
```

Expected: compile failure because `Rook.Services.Vision.Replicate` types do not exist.

- [ ] **Step 3: Add HTTP response envelope**

Create `src/Rook/Services/Vision/Replicate/ReplicateHttpResponse.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;

namespace Rook.Services.Vision.Replicate
{
    public sealed class ReplicateHttpResponse
    {
        public ReplicateHttpResponse(
            int statusCode,
            string body,
            IReadOnlyDictionary<string, IReadOnlyList<string>> headers)
        {
            if (headers is null)
                throw new ArgumentNullException(nameof(headers));

            StatusCode = statusCode;
            Body = body ?? string.Empty;

            var copy = new Dictionary<string, IReadOnlyList<string>>(
                StringComparer.OrdinalIgnoreCase);
            foreach (var kvp in headers)
            {
                copy[kvp.Key] = new ReadOnlyCollection<string>(
                    new List<string>(kvp.Value));
            }
            Headers = new ReadOnlyDictionary<string, IReadOnlyList<string>>(copy);
        }

        public int StatusCode { get; }
        public string Body { get; }
        public IReadOnlyDictionary<string, IReadOnlyList<string>> Headers { get; }
        public bool IsSuccessStatusCode => StatusCode >= 200 && StatusCode <= 299;
    }
}
```

- [ ] **Step 4: Add API client**

Create `src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Replicate
{
    public sealed class ReplicateApiClient
    {
        private readonly HttpClient _httpClient;

        public ReplicateApiClient(HttpClient? httpClient = null)
        {
            _httpClient = httpClient ?? new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(5),
            };
        }

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
            string.Equals(host, "replicate.delivery", StringComparison.OrdinalIgnoreCase)
            || host.EndsWith(".replicate.delivery", StringComparison.OrdinalIgnoreCase);

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
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateApiClientTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Replicate\ReplicateHttpResponse.cs `
        src\Rook\Services\Vision\Replicate\ReplicateApiClient.cs `
        src\Rook.Tests\Services\Vision\Replicate\ReplicateApiClientTests.cs
git commit -m "feat(vision): add Replicate API client substrate"
```

## Task 2: Official-Model Endpoint Descriptor

**Files:**
- Create: `src/Rook/Services/Vision/Replicate/ReplicatePredictionEndpoint.cs`
- Test: `src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionEndpointTests.cs`

- [ ] **Step 1: Write failing endpoint tests**

Create `src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionEndpointTests.cs`:

```csharp
using System;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicatePredictionEndpointTests
    {
        [Fact]
        public void OfficialModel_builds_create_url_from_safe_owner_and_name()
        {
            var endpoint = ReplicatePredictionEndpoint.OfficialModel(
                "black-forest-labs",
                "flux-schnell");

            Assert.Equal(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                endpoint.CreatePredictionUrl.ToString());
            Assert.Equal("black-forest-labs/flux-schnell", endpoint.ModelId);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        [InlineData("owner/name")]
        [InlineData("owner?x=1")]
        [InlineData("owner#frag")]
        public void OfficialModel_rejects_unsafe_owner_segments(string owner)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicatePredictionEndpoint.OfficialModel(owner, "flux-schnell"));
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        [InlineData("model/name")]
        [InlineData("model?x=1")]
        [InlineData("model#frag")]
        public void OfficialModel_rejects_unsafe_model_name_segments(string modelName)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", modelName));
        }

        [Fact]
        public void OfficialModel_escapes_segment_safe_reserved_characters()
        {
            var endpoint = ReplicatePredictionEndpoint.OfficialModel(
                "owner name",
                "model+name");

            Assert.Equal(
                "https://api.replicate.com/v1/models/owner%20name/model%2Bname/predictions",
                endpoint.CreatePredictionUrl.ToString());
        }
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicatePredictionEndpointTests
```

Expected: compile failure because `ReplicatePredictionEndpoint` does not exist.

- [ ] **Step 3: Add endpoint descriptor**

Create `src/Rook/Services/Vision/Replicate/ReplicatePredictionEndpoint.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Replicate
{
    public sealed class ReplicatePredictionEndpoint
    {
        private ReplicatePredictionEndpoint(string modelId, Uri createPredictionUrl)
        {
            ModelId = modelId;
            CreatePredictionUrl = createPredictionUrl;
        }

        public string ModelId { get; }
        public Uri CreatePredictionUrl { get; }

        public static ReplicatePredictionEndpoint OfficialModel(
            string modelOwner,
            string modelName)
        {
            ValidateSegment(modelOwner, nameof(modelOwner));
            ValidateSegment(modelName, nameof(modelName));

            var escapedOwner = Uri.EscapeDataString(modelOwner);
            var escapedName = Uri.EscapeDataString(modelName);
            return new ReplicatePredictionEndpoint(
                $"{modelOwner}/{modelName}",
                new Uri(
                    "https://api.replicate.com/v1/models/" +
                    $"{escapedOwner}/{escapedName}/predictions"));
        }

        private static void ValidateSegment(string value, string paramName)
        {
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException(
                    "Replicate model path segment must be non-empty.", paramName);
            if (value.Contains("/") || value.Contains("?") || value.Contains("#"))
                throw new ArgumentException(
                    "Replicate model path segment must not contain '/', '?', or '#'.",
                    paramName);
        }
    }
}
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicatePredictionEndpointTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Replicate\ReplicatePredictionEndpoint.cs `
        src\Rook.Tests\Services\Vision\Replicate\ReplicatePredictionEndpointTests.cs
git commit -m "feat(vision): add Replicate official-model endpoint descriptor"
```

## Task 3: Prediction Lifecycle And Handle Mapping

**Files:**
- Create: `src/Rook/Services/Vision/Replicate/ReplicateLifecycleMapper.cs`
- Test: `src/Rook.Tests/Services/Vision/Replicate/ReplicateLifecycleMapperTests.cs`

- [ ] **Step 1: Write failing lifecycle tests**

Create `src/Rook.Tests/Services/Vision/Replicate/ReplicateLifecycleMapperTests.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicateLifecycleMapperTests
    {
        [Fact]
        public void ParseSubmitHandle_maps_prediction_urls_and_post_cancel()
        {
            var body = Prediction("""
                {
                  "id": "pred-1",
                  "status": "starting",
                  "urls": {
                    "get": "https://api.replicate.com/v1/predictions/pred-1",
                    "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel",
                    "web": "https://replicate.com/p/pred-1"
                  },
                  "model": "black-forest-labs/flux-schnell",
                  "version": "version-1"
                }
                """);

            var handle = ReplicateLifecycleMapper.ParseSubmitHandle(body);

            Assert.Equal("pred-1", handle.ProviderJobId);
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1", handle.StatusUrl!.ToString());
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1/cancel", handle.CancelUrl!.ToString());
            Assert.Equal("POST", handle.CancelHttpMethod);
            Assert.Null(handle.ResponseUrl);
            Assert.Null(handle.ProviderResultToken);
            Assert.Equal("black-forest-labs/flux-schnell", handle.ProviderMetadata!["model"]!.GetValue<string>());
        }

        [Theory]
        [InlineData("starting", GenerationLifecycleState.Pending)]
        [InlineData("processing", GenerationLifecycleState.Running)]
        public void MapStatus_maps_in_flight_states(string status, GenerationLifecycleState expected)
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction($$"""
                { "id": "pred-1", "status": "{{status}}" }
                """));

            var inFlight = Assert.IsType<InFlightStatusOutcome>(outcome);
            Assert.Equal(expected, inFlight.State);
        }

        [Fact]
        public void MapStatus_succeeded_preserves_full_output_and_stamps_single_url_token()
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": ["https://replicate.delivery/pbxt/output.png"],
                  "metrics": { "predict_time": 0.5, "total_time": 0.8 },
                  "data_removed": false,
                  "urls": {
                    "get": "https://api.replicate.com/v1/predictions/pred-1",
                    "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
                  }
                }
                """));

            var completed = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Equal("https://replicate.delivery/pbxt/output.png", completed.UpdatedHandle.ProviderResultToken);
            Assert.NotNull(completed.UpdatedHandle.ProviderMetadata!["output"]);
            Assert.NotNull(completed.UpdatedHandle.ProviderMetadata!["metrics"]);
            Assert.Null(completed.UpdatedHandle.ResponseUrl);
        }

        [Fact]
        public void MapStatus_succeeded_preserves_object_output_without_single_url_token()
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": { "image": "https://replicate.delivery/pbxt/output.png" }
                }
                """));

            var completed = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Null(completed.UpdatedHandle.ProviderResultToken);
            Assert.NotNull(completed.UpdatedHandle.ProviderMetadata!["output"]);
        }

        [Fact]
        public void MapStatus_failed_maps_to_failed_status()
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction("""
                { "id": "pred-1", "status": "failed", "error": "model crashed" }
                """));

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("model crashed", failed.Error.Message);
            Assert.False(failed.Error.Retryable);
        }

        [Fact]
        public void MapStatus_canceled_maps_to_cancelled_error()
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction("""
                { "id": "pred-1", "status": "canceled" }
                """));

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.Cancelled, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
        }

        [Fact]
        public void MapStatus_data_removed_true_maps_to_dependency_unavailable()
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction("""
                { "id": "pred-1", "status": "succeeded", "output": null, "data_removed": true }
                """));

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("expired before Rook copied it", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_succeeded_null_output_without_data_removed_maps_execution_failed()
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction("""
                { "id": "pred-1", "status": "succeeded", "output": null, "data_removed": false }
                """));

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
        }

        [Fact]
        public void MapStatus_omits_logs_from_default_metadata()
        {
            var handle = new ProviderJobHandle("pred-1");
            var outcome = ReplicateLifecycleMapper.MapStatus(handle, Prediction("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": "https://replicate.delivery/pbxt/output.png",
                  "logs": "prompt and model debug details"
                }
                """));

            var completed = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.False(completed.UpdatedHandle.ProviderMetadata!.ContainsKey("logs"));
        }

        private static JsonNode Prediction(string json) => JsonNode.Parse(json)!;
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateLifecycleMapperTests
```

Expected: compile failure because `ReplicateLifecycleMapper` does not exist.

- [ ] **Step 3: Add lifecycle mapper**

Create `src/Rook/Services/Vision/Replicate/ReplicateLifecycleMapper.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Replicate
{
    public static class ReplicateLifecycleMapper
    {
        public static ProviderJobHandle ParseSubmitHandle(JsonNode submitBody)
        {
            if (submitBody is not JsonObject root)
                throw new ArgumentException(
                    "Replicate submit body must be a JSON object.",
                    nameof(submitBody));

            return BuildHandle(root, selectedResultToken: null);
        }

        public static ProviderStatusOutcome MapStatus(
            ProviderJobHandle handle,
            JsonNode statusBody)
        {
            if (handle is null) throw new ArgumentNullException(nameof(handle));
            if (statusBody is not JsonObject root)
            {
                return Failed(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate status body was not a JSON object.",
                    retryable: false);
            }

            var rawStatus = OptionalString(root, "status");
            switch (rawStatus)
            {
                case "starting":
                    return new InFlightStatusOutcome(
                        GenerationLifecycleState.Pending,
                        Progress: null);
                case "processing":
                    return new InFlightStatusOutcome(
                        GenerationLifecycleState.Running,
                        Progress: null);
                case "succeeded":
                    return MapSucceeded(root);
                case "failed":
                    return Failed(
                        GenerationErrorCode.ExecutionFailed,
                        "Replicate prediction failed. " + (OptionalString(root, "error") ?? "No provider error was supplied."),
                        retryable: false,
                        providerErrorCode: "failed",
                        providerDetail: Detail(root, includeOutput: false));
                case "canceled":
                    return Failed(
                        GenerationErrorCode.Cancelled,
                        "Replicate prediction was canceled.",
                        retryable: false,
                        providerErrorCode: "canceled",
                        providerDetail: Detail(root, includeOutput: false));
                default:
                    return Failed(
                        GenerationErrorCode.ExecutionFailed,
                        $"Unknown Replicate lifecycle state '{rawStatus ?? "<missing>"}'.",
                        retryable: false,
                        providerErrorCode: rawStatus);
            }
        }

        private static ProviderStatusOutcome MapSucceeded(JsonObject root)
        {
            var dataRemoved = OptionalBool(root, "data_removed") == true;
            var output = root["output"];
            if (dataRemoved)
            {
                return Failed(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate provider output expired before Rook copied it.",
                    retryable: false,
                    providerErrorCode: "data_removed",
                    providerDetail: Detail(root, includeOutput: false));
            }

            if (output is null)
            {
                return Failed(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate prediction succeeded but output was null.",
                    retryable: false,
                    providerErrorCode: "null_output",
                    providerDetail: Detail(root, includeOutput: false));
            }

            var selectedUrl = TrySelectSingleOutputUrl(output);
            return new ProviderCompleteStatusOutcome(
                BuildHandle(root, selectedUrl));
        }

        private static ProviderJobHandle BuildHandle(
            JsonObject root,
            string? selectedResultToken)
        {
            var id = RequiredString(root, "id");
            var urls = root["urls"] as JsonObject;

            return new ProviderJobHandle(
                providerJobId: id,
                statusUrl: OptionalUri(urls, "get"),
                responseUrl: null,
                cancelUrl: OptionalUri(urls, "cancel"),
                cancelHttpMethod: "POST",
                providerResultToken: selectedResultToken,
                providerMetadata: Metadata(root));
        }

        private static IReadOnlyDictionary<string, JsonNode> Metadata(JsonObject root)
        {
            var metadata = new Dictionary<string, JsonNode>();
            Add(root, metadata, "output");
            Add(root, metadata, "metrics");
            Add(root, metadata, "model");
            Add(root, metadata, "version");
            Add(root, metadata, "data_removed");
            Add(root, metadata, "urls");
            return metadata;
        }

        private static IReadOnlyDictionary<string, JsonNode>? Detail(
            JsonObject root,
            bool includeOutput)
        {
            var detail = new Dictionary<string, JsonNode>();
            Add(root, detail, "error");
            Add(root, detail, "status");
            Add(root, detail, "model");
            Add(root, detail, "version");
            Add(root, detail, "data_removed");
            if (includeOutput) Add(root, detail, "output");
            return detail.Count == 0 ? null : detail;
        }

        private static void Add(
            JsonObject source,
            IDictionary<string, JsonNode> metadata,
            string key)
        {
            var node = source[key]?.DeepClone();
            if (node is not null)
                metadata[key] = node;
        }

        private static string RequiredString(JsonObject root, string name)
        {
            var value = OptionalString(root, name);
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException(
                    $"Replicate response missing required '{name}'.",
                    name);
            return value!;
        }

        private static string? OptionalString(JsonObject root, string name)
        {
            var node = root[name];
            return node is JsonValue value && value.TryGetValue<string>(out var stringValue)
                ? stringValue
                : null;
        }

        private static bool? OptionalBool(JsonObject root, string name)
        {
            var node = root[name];
            return node is JsonValue value && value.TryGetValue<bool>(out var boolValue)
                ? boolValue
                : null;
        }

        private static Uri? OptionalUri(JsonObject? root, string name)
        {
            if (root is null) return null;
            var value = OptionalString(root, name);
            if (string.IsNullOrWhiteSpace(value)) return null;
            if (!Uri.TryCreate(value, UriKind.Absolute, out var uri))
                throw new ArgumentException(
                    $"Replicate response field '{name}' was not a valid absolute URL.",
                    name);
            return uri;
        }

        private static string? TrySelectSingleOutputUrl(JsonNode output)
        {
            if (TryUrl(output, out var direct))
                return direct;

            if (output is JsonArray array && array.Count == 1 && TryUrl(array[0], out var only))
                return only;

            return null;
        }

        private static bool TryUrl(JsonNode? node, out string? url)
        {
            url = null;
            if (node is not JsonValue value || !value.TryGetValue<string>(out var text))
                return false;
            if (!Uri.TryCreate(text, UriKind.Absolute, out var uri))
                return false;
            if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
                return false;
            url = text;
            return true;
        }

        private static FailedStatusOutcome Failed(
            GenerationErrorCode code,
            string message,
            bool retryable,
            string? providerErrorCode = null,
            IReadOnlyDictionary<string, JsonNode>? providerDetail = null) =>
            new FailedStatusOutcome(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                ProviderErrorCode: providerErrorCode,
                ProviderDetail: providerDetail));
    }
}
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateLifecycleMapperTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Replicate\ReplicateLifecycleMapper.cs `
        src\Rook.Tests\Services\Vision\Replicate\ReplicateLifecycleMapperTests.cs
git commit -m "feat(vision): map Replicate prediction lifecycle"
```

## Task 4: Error And Pricing Helpers

**Files:**
- Create: `src/Rook/Services/Vision/Replicate/ReplicateErrorMapper.cs`
- Create: `src/Rook/Services/Vision/Replicate/ReplicatePredictionPricing.cs`
- Test: `src/Rook.Tests/Services/Vision/Replicate/ReplicateErrorMapperTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionPricingTests.cs`

- [ ] **Step 1: Write failing error mapper tests**

Create `src/Rook.Tests/Services/Vision/Replicate/ReplicateErrorMapperTests.cs`:

```csharp
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicateErrorMapperTests
    {
        [Theory]
        [InlineData(400, GenerationErrorCode.InvalidRequest, false)]
        [InlineData(401, GenerationErrorCode.DependencyUnavailable, false)]
        [InlineData(403, GenerationErrorCode.DependencyUnavailable, false)]
        [InlineData(429, GenerationErrorCode.QuotaExceeded, true)]
        [InlineData(500, GenerationErrorCode.DependencyUnavailable, true)]
        public void MapHttpFailure_maps_status_code(int status, GenerationErrorCode code, bool retryable)
        {
            var error = ReplicateErrorMapper.MapHttpFailure(Response(status, "{\"detail\":\"bad\"}"));

            Assert.Equal(code, error.Code);
            Assert.Equal(retryable, error.Retryable);
            Assert.Equal(status.ToString(), error.ProviderErrorCode);
            Assert.NotNull(error.ProviderDetail);
        }

        [Fact]
        public void MissingToken_returns_dependency_unavailable()
        {
            var error = ReplicateErrorMapper.MissingToken();

            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error.Code);
            Assert.False(error.Retryable);
            Assert.Contains("Replicate API token is not configured", error.Message);
        }

        private static ReplicateHttpResponse Response(int status, string body) =>
            new ReplicateHttpResponse(
                status,
                body,
                new Dictionary<string, IReadOnlyList<string>>());
    }
}
```

- [ ] **Step 2: Write failing pricing tests**

Create `src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionPricingTests.cs`:

```csharp
using System.Text.Json.Nodes;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicatePredictionPricingTests
    {
        [Fact]
        public void ExtractActualSpend_uses_predict_time_as_compute_second_quantity()
        {
            var body = JsonNode.Parse("""
                { "metrics": { "predict_time": 0.507, "total_time": 0.543 } }
                """)!;

            var pricing = ReplicatePredictionPricing.ExtractActualSpend(
                body,
                pricingSource: "replicate-predict-time-2026-04-30");

            Assert.NotNull(pricing);
            Assert.Equal("USD", pricing!.Currency);
            Assert.Equal("compute_second", pricing.Unit);
            Assert.Equal(0.507m, pricing.Quantity);
            Assert.Null(pricing.TotalUsd);
            Assert.Equal("replicate-predict-time-2026-04-30", pricing.PricingSource);
        }

        [Fact]
        public void ExtractTimingMetadata_preserves_predict_and_total_time()
        {
            var body = JsonNode.Parse("""
                { "metrics": { "predict_time": 0.507, "total_time": 0.543 } }
                """)!;

            var timing = ReplicatePredictionPricing.ExtractTimingMetadata(body);

            Assert.Equal(0.507m, timing.PredictTimeSeconds);
            Assert.Equal(0.543m, timing.TotalTimeSeconds);
        }

        [Fact]
        public void ExtractActualSpend_returns_null_when_predict_time_missing()
        {
            var body = JsonNode.Parse("""{ "metrics": { "total_time": 0.543 } }""")!;

            Assert.Null(ReplicatePredictionPricing.ExtractActualSpend(
                body,
                "replicate-predict-time-2026-04-30"));
        }
    }
}
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateErrorMapperTests|ReplicatePredictionPricingTests"
```

Expected: compile failure because helper types do not exist.

- [ ] **Step 4: Add error mapper**

Create `src/Rook/Services/Vision/Replicate/ReplicateErrorMapper.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Replicate
{
    public static class ReplicateErrorMapper
    {
        public static GenerationError MissingToken() =>
            new GenerationError(
                GenerationErrorCode.DependencyUnavailable,
                "Replicate API token is not configured.",
                Retryable: false);

        public static GenerationError MapHttpFailure(ReplicateHttpResponse response)
        {
            if (response is null) throw new ArgumentNullException(nameof(response));

            return new GenerationError(
                MapErrorCode(response.StatusCode),
                string.Format(
                    CultureInfo.InvariantCulture,
                    "Replicate request failed with HTTP {0}.",
                    response.StatusCode),
                IsRetryable(response.StatusCode),
                ProviderErrorCode: response.StatusCode.ToString(CultureInfo.InvariantCulture),
                ProviderDetail: TryParseProviderDetail(response.Body));
        }

        private static GenerationErrorCode MapErrorCode(int statusCode)
        {
            switch (statusCode)
            {
                case 400:
                case 422:
                    return GenerationErrorCode.InvalidRequest;
                case 401:
                case 403:
                    return GenerationErrorCode.DependencyUnavailable;
                case 429:
                    return GenerationErrorCode.QuotaExceeded;
                default:
                    return statusCode >= 500
                        ? GenerationErrorCode.DependencyUnavailable
                        : GenerationErrorCode.ExecutionFailed;
            }
        }

        private static bool IsRetryable(int statusCode)
        {
            switch (statusCode)
            {
                case 400:
                case 401:
                case 403:
                case 422:
                    return false;
            }

            return statusCode == 408 || statusCode == 429 || statusCode >= 500;
        }

        private static IReadOnlyDictionary<string, JsonNode>? TryParseProviderDetail(
            string body)
        {
            if (string.IsNullOrWhiteSpace(body))
                return null;

            try
            {
                if (JsonNode.Parse(body) is not JsonObject root)
                    return null;

                var detail = new Dictionary<string, JsonNode>();
                foreach (var kvp in root)
                {
                    if (kvp.Value is not null)
                        detail[kvp.Key] = kvp.Value.DeepClone();
                }

                return new ReadOnlyDictionary<string, JsonNode>(detail);
            }
            catch (JsonException)
            {
                return null;
            }
        }
    }
}
```

- [ ] **Step 5: Add pricing helper**

Create `src/Rook/Services/Vision/Replicate/ReplicatePredictionPricing.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Replicate
{
    public static class ReplicatePredictionPricing
    {
        public static JobPricing? ExtractActualSpend(
            JsonNode predictionBody,
            string pricingSource)
        {
            var timing = ExtractTimingMetadata(predictionBody);
            if (timing.PredictTimeSeconds is not decimal predictTime)
                return null;

            return new JobPricing(
                Currency: "USD",
                UnitPrice: null,
                Unit: "compute_second",
                Quantity: predictTime,
                TotalUsd: null,
                PricingSource: pricingSource);
        }

        public static ReplicateTimingMetadata ExtractTimingMetadata(
            JsonNode predictionBody)
        {
            if (predictionBody is not JsonObject root
                || root["metrics"] is not JsonObject metrics)
            {
                return new ReplicateTimingMetadata(null, null);
            }

            return new ReplicateTimingMetadata(
                TryDecimal(metrics["predict_time"]),
                TryDecimal(metrics["total_time"]));
        }

        private static decimal? TryDecimal(JsonNode? node)
        {
            if (node is null) return null;
            try
            {
                return node.GetValue<decimal>();
            }
            catch
            {
                try
                {
                    return Convert.ToDecimal(node.GetValue<double>());
                }
                catch
                {
                    return null;
                }
            }
        }
    }

    public sealed class ReplicateTimingMetadata
    {
        public ReplicateTimingMetadata(decimal? predictTimeSeconds, decimal? totalTimeSeconds)
        {
            PredictTimeSeconds = predictTimeSeconds;
            TotalTimeSeconds = totalTimeSeconds;
        }

        public decimal? PredictTimeSeconds { get; }
        public decimal? TotalTimeSeconds { get; }
    }
}
```

- [ ] **Step 6: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateErrorMapperTests|ReplicatePredictionPricingTests"
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Replicate\ReplicateErrorMapper.cs `
        src\Rook\Services\Vision\Replicate\ReplicatePredictionPricing.cs `
        src\Rook.Tests\Services\Vision\Replicate\ReplicateErrorMapperTests.cs `
        src\Rook.Tests\Services\Vision\Replicate\ReplicatePredictionPricingTests.cs
git commit -m "feat(vision): add Replicate error and pricing helpers"
```

## Task 5: Credential Metadata And UI Boundary Guards

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Add no-Replicate metadata guard**

In `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`, update `CreateCredentialMetadata_merges_gemini_owner_and_fal_from_image_and_video` to include the Replicate assertion:

```csharp
Assert.DoesNotContain(providers, p => p.ProviderName == "veo");
Assert.DoesNotContain(providers, p => p.ProviderName == "replicate");
Assert.DoesNotContain(
    providers.SelectMany(p => p.SecretRequirements),
    r => r.Key == GenerationSecretKeys.ReplicateApiToken);
```

- [ ] **Step 2: Add default provider-secret rejection test**

In `src/Rook.Tests/Handlers/VisionHandlerTests.cs`, add this test near the existing provider-secret tests:

```csharp
[Fact]
public void SetProviderSecret_RejectsReplicateBecauseDefaultMetadataDoesNotExposeIt()
{
    var store = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(store);

    var response = handler.DispatchOffUi(JsonSerializer.Serialize(new Dictionary<string, object?>
    {
        ["op"] = "set_provider_secret",
        ["provider_name"] = "replicate",
        ["secret_key"] = GenerationSecretKeys.ReplicateApiToken,
        ["value"] = "r8_token",
    }));

    Assert.False(response.Success);
    Assert.Null(store.GetSecret(GenerationSecretKeys.ReplicateApiToken));
    Assert.Contains("Unknown provider", response.Data?.ToString());
}
```

If `VisionHandlerTests.cs` already has a helper for JSON dispatch bodies, use that helper and keep the assertions identical.

- [ ] **Step 3: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionProviderRegistrationsTests|SetProviderSecret_RejectsReplicateBecauseDefaultMetadataDoesNotExposeIt"
```

Expected: PASS. These tests should pass without production changes because default metadata should already be Gemini + fal only.

- [ ] **Step 4: Commit**

```powershell
git add src\Rook.Tests\Services\Vision\VisionProviderRegistrationsTests.cs `
        src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "test(vision): pin Replicate credential UI boundary"
```

## Task 6: Full Verification And Native Boundary Scan

**Files:**
- No production files.
- No test files unless a verification failure reveals a missing guard within PR-10 scope.

- [ ] **Step 1: Run focused Replicate tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateApiClientTests|ReplicatePredictionEndpointTests|ReplicateLifecycleMapperTests|ReplicateErrorMapperTests|ReplicatePredictionPricingTests"
```

Expected: PASS.

- [ ] **Step 2: Run boundary and provider metadata tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionProviderRegistrationsTests|VisionHandlerTests|VisionWebSurfaceTests|NativeGhBridgeRegistrarTests"
```

Expected: PASS.

- [ ] **Step 3: Scan for accidental native or UI exposure**

Run:

```powershell
rg -n "Replicate|replicate|replicate.api_token" src\RookNative src\Rook\UI\Vision src\Rook\InternalBridge src\Rook\Services\Vision\VisionProviderRegistrations.cs
```

Expected:

- No hits under `src\RookNative`.
- No hits under `src\Rook\UI\Vision`.
- No hits under `src\Rook\InternalBridge`.
- `VisionProviderRegistrations.cs` should not contain `replicate` or `Replicate`.

- [ ] **Step 4: Run focused managed suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "Replicate|Fal|Generation|ImageProviderRegistry|VideoProviderRegistry|VisionProviderRegistrations"
```

Expected: PASS.

- [ ] **Step 5: Run full managed tests if practical**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: PASS. If this fails because of local Rhino/toolchain prerequisites, record the exact failure and the focused test results. Do not claim full verification unless this command passes.

- [ ] **Step 6: Confirm worktree scope**

Run:

```powershell
git status --short
git diff --name-only HEAD
```

Expected changed files are limited to:

```text
src/Rook/Services/Vision/Replicate/ReplicateHttpResponse.cs
src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs
src/Rook/Services/Vision/Replicate/ReplicatePredictionEndpoint.cs
src/Rook/Services/Vision/Replicate/ReplicateLifecycleMapper.cs
src/Rook/Services/Vision/Replicate/ReplicateErrorMapper.cs
src/Rook/Services/Vision/Replicate/ReplicatePredictionPricing.cs
src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs
src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionEndpointTests.cs
src/Rook.Tests/Services/Vision/Replicate/ReplicateLifecycleMapperTests.cs
src/Rook.Tests/Services/Vision/Replicate/ReplicateErrorMapperTests.cs
src/Rook.Tests/Services/Vision/Replicate/ReplicatePredictionPricingTests.cs
src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs
src/Rook.Tests/Handlers/VisionHandlerTests.cs
```

Existing unrelated dirty files may still appear and must not be staged as part of PR-10 unless the user explicitly requests it.

## Self-Review Checklist

- [ ] PR-10 adds no user-visible Replicate model.
- [ ] PR-10 adds no Replicate Settings card.
- [ ] `VisionProviderRegistrations.CreateCredentialMetadata()` stays Gemini + fal only.
- [ ] Default `set_provider_secret` rejects `provider_name: "replicate"`.
- [ ] API calls are restricted to `api.replicate.com`.
- [ ] Output proof seam accepts exact `replicate.delivery` or suffix `.replicate.delivery` only.
- [ ] Output host lookalike `replicate.delivery.evil.test` is rejected.
- [ ] Official-model endpoint owner/name path segments reject empty values and `/`, `?`, `#`.
- [ ] Generic `/v1/predictions` is not implemented unless tests cover its version-body shape.
- [ ] `failed` and `canceled` statuses map distinctly.
- [ ] `data_removed: true` maps to non-retryable `DependencyUnavailable`.
- [ ] `succeeded` with `output: null` and `data_removed != true` maps to `ExecutionFailed`.
- [ ] Replicate logs are omitted by default.
- [ ] Full output cardinality is preserved in metadata.
- [ ] `ProviderResultToken` is only a descriptor-specific convenience for a single selected output URL.
- [ ] No files under `src/RookNative/**` changed.
- [ ] No live Replicate tests ran without explicit approval.
