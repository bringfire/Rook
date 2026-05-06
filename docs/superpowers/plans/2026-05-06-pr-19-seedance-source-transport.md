# PR-19 Seedance Source Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Seedance 2.0 source-frame data URIs with provider-private fal CDN uploads that accept provider-sized source images while preserving request-id-only durable state and no source URL persistence.

**Architecture:** Keep the change inside managed fal video provider code. Add a Seedance-specific source transport that validates resolved media, uploads source frames to fal CDN, returns only volatile `ImageUrl` / `EndImageUrl`, and lets `FalVideoProvider` submit the queue job with small JSON and retention headers. Extend `FalApiClient` narrowly for the confirmed fal storage initiate-plus-presigned-PUT upload flow and constrained fal platform headers.

**Tech Stack:** C#/.NET 7, xUnit, `System.Net.Http`, `System.Text.Json.Nodes`, existing managed Vision provider/test helpers.

---

## File Structure

- Modify: `src/Rook/Services/Vision/Fal/FalApiClient.cs`
  - Add constrained fal platform headers for JSON submit.
  - Add confirmed fal storage initiate-plus-presigned-PUT helper for source bytes.
  - Keep host restrictions narrow: queue/model calls use `fal.run`; upload initiation uses `rest.fal.ai`; returned CDN file URLs must be HTTPS `v3*.fal.media`.

- Create: `src/Rook/Services/Vision/Video/Fal/IFalSeedanceSourceTransport.cs`
  - Internal interface for provider-private source upload.

- Create: `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceUrls.cs`
  - Internal immutable value object with `ImageUrl` and optional `EndImageUrl`.

- Create: `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceTransport.cs`
  - Owns Seedance frame validation, upload target path generation, fal CDN URL construction/validation, bounded upload retry, and sanitized upload errors.

- Modify: `src/Rook/Services/Vision/Video/Fal/FalSeedanceI2vSourcePayload.cs`
  - Delete after replacement if no callers remain, or reduce to a compatibility wrapper only if tests prove a local caller still requires it. Preferred outcome: remove this data-URI payload builder.

- Modify: `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`
  - Inject optional `IFalSeedanceSourceTransport`.
  - Read API key before source upload.
  - Use uploaded CDN URLs in Seedance submit JSON.
  - Send `X-Fal-Store-IO: 0`, `X-Fal-No-Retry: 1`, and lifecycle preference
    on queue submit.
  - Preserve request-id-only handle and Seedance provider-detail sanitization.

- Modify: `src/Rook.Tests/Services/Vision/Fal/FalApiClientTests.cs`
  - Add constrained header and initiate-plus-PUT upload tests.

- Create: `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceSourceTransportTests.cs`
  - Add validation, upload shape, URL validation, retry, cancellation, and sanitized error tests.

- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceI2vSourcePayloadTests.cs`
  - Delete with production payload builder if replaced fully. If retained as wrapper, convert expectations from data URIs to uploaded URL transport. Preferred outcome: delete this file.

- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`
  - Update Seedance submit tests from data URI to upload URLs.
  - Add provider orchestration tests for no upload when key missing and no submit after upload failure/cancel/end-frame failure.

- Modify: `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`
  - Add raw JSONL and artifact/response leakage checks for source CDN URLs if current Seedance tests do not already scan raw text.

---

## Task 0: Confirm fal Upload REST Contract

**Files:**
- Modify if needed: `docs/superpowers/specs/2026-05-06-pr-19-seedance-source-transport-design.md`
- Modify this plan if docs/probe disprove the expected contract.

Task 0 is complete. Official docs still document the older local multipart
endpoint, but that endpoint returns only a completion boolean and the
controlled non-generation probe against the JavaScript SDK storage flow
confirmed the URL-returning contract PR-19 needs:

- Initiate endpoint: `POST https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3`
- Initiate request body: JSON with `content_type` and generated `file_name`
- Upload lifecycle header on initiate: `X-Fal-Object-Lifecycle: {"expiration_duration_seconds":3600}`
- Initiate response body: JSON with `upload_url` and `file_url`
- Upload body: raw source bytes `PUT` to returned HTTPS presigned `upload_url`
- Upload `PUT` content type: detected source MIME type
- Model input URL: returned HTTPS fal CDN `file_url`
- CDN host evidence: `v3*.fal.media`; the probe observed `v3b.fal.media`

Do not use the boolean-returning local multipart endpoint for PR-19.

- [x] **Step 1: Re-check official docs**

Open and verify these official pages:

- `https://fal.ai/docs/platform-apis/v1/serverless/files/file/local/%7Btarget_path%7D`
- `https://fal.ai/docs/documentation/model-apis/fal-cdn`
- `https://fal.ai/docs/api-reference/client-libraries/javascript/storage`
- `https://fal.ai/docs/documentation/model-apis/common-parameters`

Observed documentation facts:

- upload endpoint uses `multipart/form-data`;
- field name is `file_upload`;
- platform model queue header remains `X-Fal-Object-Lifecycle-Preference`;
- `X-Fal-Store-IO: 0` disables request JSON retention;
- storage upload lifecycle header is `X-Fal-Object-Lifecycle` unless REST docs say otherwise;
- CDN URL format is `https://v3.fal.media/files/{path}` in docs, while the
  live SDK-compatible endpoint may return another `v3*.fal.media` host such
  as `v3b.fal.media`.
- Seedance queue submit should use `X-Fal-No-Retry: 1` to disable fal
  platform retries and avoid duplicate generation jobs.

- [x] **Step 2: Run a controlled non-generation upload probe if docs still do not confirm CDN URL derivation**

Use a 1-byte non-sensitive file and a disposable generated filename. This does not call a generation model.

```powershell
$ErrorActionPreference = "Stop"
$key = [Environment]::GetEnvironmentVariable("FAL_KEY", "User")
if ([string]::IsNullOrWhiteSpace($key)) {
    $key = [Environment]::GetEnvironmentVariable("FAL_KEY", "Process")
}
if ([string]::IsNullOrWhiteSpace($key)) {
    throw "FAL_KEY is required for the upload contract probe"
}

$dir = Join-Path $env:TEMP "rook-fal-upload-probe"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$file = Join-Path $dir "probe.txt"
[IO.File]::WriteAllText($file, "x")

$fileName = "rook-pr19-probe-$([Guid]::NewGuid().ToString('N')).txt"
$lifecycle = '{"expiration_duration_seconds":3600}'
$initBody = @{ content_type = "text/plain"; file_name = $fileName } | ConvertTo-Json -Compress

$init = curl.exe --fail-with-body --silent --show-error `
    --request POST `
    --url "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3" `
    --header "Authorization: Key $key" `
    --header "Content-Type: application/json" `
    --header "X-Fal-Object-Lifecycle: $lifecycle" `
    --data $initBody

$obj = $init | ConvertFrom-Json
if (-not $obj.upload_url -or -not $obj.file_url) {
    throw "initiate response missing upload_url or file_url"
}
```

Expected: initiate response contains `upload_url` and `file_url`. Upload raw
bytes to `upload_url`, then verify `file_url` is accessible without auth:

```powershell
curl.exe --fail-with-body --silent --show-error `
    --request PUT `
    --url $obj.upload_url `
    --header "Content-Type: text/plain" `
    --data-binary "@$file"

$downloaded = curl.exe --fail-with-body --silent --show-error $obj.file_url
if ($downloaded -ne "x") {
    throw "Returned CDN file_url did not return probe content"
}
```

- [x] **Step 3: Record the confirmed contract**

Add a short note to the implementation PR body during handoff. Do not add
probe filenames, presigned upload URLs, CDN file URLs, or credentials to
committed docs.

## Task 1: Add fal API Client Header And Upload Support

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Fal/FalApiClientTests.cs`
- Modify: `src/Rook/Services/Vision/Fal/FalApiClient.cs`

- [ ] **Step 1: Write failing JSON platform-header tests**

Add tests to `FalApiClientTests`:

```csharp
[Fact]
public async Task PostJsonAsync_can_send_seedance_queue_platform_headers()
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("{\"request_id\":\"r1\"}", Encoding.UTF8, "application/json"),
        },
    };
    var client = new FalApiClient(new HttpClient(handler));

    await client.PostJsonAsync(
        "test-key",
        new Uri("https://queue.fal.run/bytedance/seedance-2.0/image-to-video"),
        "{\"prompt\":\"p\"}",
        FalJsonPlatformHeaders.ForSeedanceSubmit(
            3600,
            disableStoreIo: true,
            disableFalRetry: true),
        CancellationToken.None);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(
        "{\"expiration_duration_seconds\":3600}",
        Assert.Single(request.Headers.GetValues("X-Fal-Object-Lifecycle-Preference")));
    Assert.Equal("0", Assert.Single(request.Headers.GetValues("X-Fal-Store-IO")));
    Assert.Equal("1", Assert.Single(request.Headers.GetValues("X-Fal-No-Retry")));
}

[Fact]
public async Task PostJsonAsync_does_not_send_platform_headers_when_absent()
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("{}", Encoding.UTF8, "application/json"),
        },
    };
    var client = new FalApiClient(new HttpClient(handler));

    await client.PostJsonAsync(
        "test-key",
        new Uri("https://queue.fal.run/fal-ai/wan/v2.7/text-to-video"),
        "{}",
        CancellationToken.None);

    var request = Assert.Single(handler.Requests);
    Assert.False(request.Headers.Contains("X-Fal-Object-Lifecycle-Preference"));
    Assert.False(request.Headers.Contains("X-Fal-Store-IO"));
    Assert.False(request.Headers.Contains("X-Fal-No-Retry"));
}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalApiClientTests"
```

Expected: compile fails because `FalJsonPlatformHeaders` and the new overload do not exist.

- [ ] **Step 3: Implement constrained JSON platform headers**

In `FalApiClient.cs`, add a small value type above `FalApiClient`:

```csharp
public sealed class FalJsonPlatformHeaders
{
    private FalJsonPlatformHeaders(
        int? objectLifecyclePreferenceSeconds,
        bool disableStoreIo,
        bool disableFalRetry)
    {
        ObjectLifecyclePreferenceSeconds = objectLifecyclePreferenceSeconds;
        DisableStoreIo = disableStoreIo;
        DisableFalRetry = disableFalRetry;
    }

    public int? ObjectLifecyclePreferenceSeconds { get; }
    public bool DisableStoreIo { get; }
    public bool DisableFalRetry { get; }

    public static FalJsonPlatformHeaders ForSeedanceSubmit(
        int objectLifecyclePreferenceSeconds,
        bool disableStoreIo,
        bool disableFalRetry)
    {
        if (objectLifecyclePreferenceSeconds <= 0)
            throw new ArgumentOutOfRangeException(nameof(objectLifecyclePreferenceSeconds));

        return new FalJsonPlatformHeaders(
            objectLifecyclePreferenceSeconds,
            disableStoreIo,
            disableFalRetry);
    }
}
```

Add overloads:

```csharp
public Task<FalHttpResponse> PostJsonAsync(
    string apiKey,
    Uri url,
    string bodyJson,
    FalJsonPlatformHeaders platformHeaders,
    CancellationToken ct) =>
    SendAsync(apiKey, HttpMethod.Post, url, bodyJson, platformHeaders, ct);

public Task<FalHttpResponse> SendAsync(
    string apiKey,
    HttpMethod method,
    Uri url,
    string? bodyJson,
    CancellationToken ct) =>
    SendAsync(apiKey, method, url, bodyJson, platformHeaders: null, ct);

private async Task<FalHttpResponse> SendAsync(
    string apiKey,
    HttpMethod method,
    Uri url,
    string? bodyJson,
    FalJsonPlatformHeaders? platformHeaders,
    CancellationToken ct)
```

Inside request creation, add:

```csharp
ApplyJsonPlatformHeaders(request, platformHeaders);
```

Add helper:

```csharp
private static void ApplyJsonPlatformHeaders(
    HttpRequestMessage request,
    FalJsonPlatformHeaders? headers)
{
    if (headers is null)
        return;

    if (headers.ObjectLifecyclePreferenceSeconds is int seconds)
    {
        request.Headers.TryAddWithoutValidation(
            "X-Fal-Object-Lifecycle-Preference",
            "{\"expiration_duration_seconds\":" +
            seconds.ToString(System.Globalization.CultureInfo.InvariantCulture) +
            "}");
    }

    if (headers.DisableStoreIo)
        request.Headers.TryAddWithoutValidation("X-Fal-Store-IO", "0");

    if (headers.DisableFalRetry)
        request.Headers.TryAddWithoutValidation("X-Fal-No-Retry", "1");
}
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalApiClientTests"
```

Expected: all `FalApiClientTests` pass.

- [ ] **Step 5: Write failing initiate-plus-PUT upload tests**

Add tests:

```csharp
[Fact]
public async Task UploadFileToCdnAsync_initiates_upload_then_puts_raw_bytes()
{
    var calls = new List<HttpRequestMessage>();
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            calls.Add(req);
            if (req.RequestUri!.Host == "rest.fal.ai")
            {
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        @"{
                          ""upload_url"": ""https://v3b.fal.media/upload/presigned-token"",
                          ""file_url"": ""https://v3b.fal.media/files/rook-pr19-source.png""
                        }",
                        Encoding.UTF8,
                        "application/json"),
                };
            }

            Assert.Equal("v3b.fal.media", req.RequestUri.Host);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(string.Empty, Encoding.UTF8, "text/plain"),
            };
        },
    };
    var client = new FalApiClient(new HttpClient(handler));

    var url = await client.UploadFileToCdnAsync(
        "test-key",
        "rook-pr19-source.png",
        new byte[] { 1, 2, 3 },
        "image/png",
        FalUploadPlatformHeaders.ForSourceUpload(3600),
        CancellationToken.None);

    Assert.Equal("https://v3b.fal.media/files/rook-pr19-source.png", url);
    Assert.Equal(2, calls.Count);

    var initiate = calls[0];
    Assert.Equal(HttpMethod.Post, initiate.Method);
    Assert.Equal(
        "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3",
        initiate.RequestUri!.ToString());
    Assert.Equal("Key", initiate.Headers.Authorization!.Scheme);
    Assert.Equal("test-key", initiate.Headers.Authorization.Parameter);
    Assert.Equal(
        "{\"expiration_duration_seconds\":3600}",
        Assert.Single(initiate.Headers.GetValues("X-Fal-Object-Lifecycle")));
    var initiateJson = await initiate.Content!.ReadAsStringAsync();
    Assert.Contains(@"""content_type"":""image/png""", initiateJson);
    Assert.Contains(@"""file_name"":""rook-pr19-source.png""", initiateJson);

    var upload = calls[1];
    Assert.Equal(HttpMethod.Put, upload.Method);
    Assert.Null(upload.Headers.Authorization);
    Assert.Equal("image/png", upload.Content!.Headers.ContentType!.MediaType);
    Assert.Equal(new byte[] { 1, 2, 3 }, await upload.Content.ReadAsByteArrayAsync());
}

[Theory]
[InlineData("../secret.png")]
[InlineData("/absolute.png")]
[InlineData("rook\\secret.png")]
[InlineData("https://rest.fal.ai/file.png")]
public async Task UploadFileToCdnAsync_rejects_unsafe_file_names(string fileName)
{
    var handler = new TestHttpMessageHandler();
    var client = new FalApiClient(new HttpClient(handler));

    await Assert.ThrowsAsync<ArgumentException>(
        async () => await client.UploadFileToCdnAsync(
            "test-key",
            fileName,
            new byte[] { 1 },
            "image/png",
            FalUploadPlatformHeaders.ForSourceUpload(3600),
            CancellationToken.None));

    Assert.Empty(handler.Requests);
}

[Theory]
[InlineData(null)]
[InlineData("{}")]
[InlineData(@"{""upload_url"":""https://v3b.fal.media/upload/x""}")]
[InlineData(@"{""file_url"":""https://v3b.fal.media/files/x.png""}")]
[InlineData(@"{""upload_url"":""http://v3b.fal.media/upload/x"",""file_url"":""https://v3b.fal.media/files/x.png""}")]
[InlineData(@"{""upload_url"":""https://v3b.fal.media/upload/x"",""file_url"":""https://example.com/files/x.png""}")]
public async Task UploadFileToCdnAsync_rejects_invalid_initiate_response(string? body)
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(body ?? string.Empty, Encoding.UTF8, "application/json"),
        },
    };
    var client = new FalApiClient(new HttpClient(handler));

    await Assert.ThrowsAsync<FalApiException>(
        async () => await client.UploadFileToCdnAsync(
            "test-key",
            "source.png",
            new byte[] { 1 },
            "image/png",
            FalUploadPlatformHeaders.ForSourceUpload(3600),
            CancellationToken.None));
}
```

- [ ] **Step 6: Run tests and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalApiClientTests"
```

Expected: compile fails because `FalUploadPlatformHeaders`,
`UploadFileToCdnAsync`, and `FalApiException` do not exist.

- [ ] **Step 7: Implement upload support**

In `FalApiClient.cs`, add:

```csharp
public sealed class FalUploadPlatformHeaders
{
    private FalUploadPlatformHeaders(int objectLifecycleSeconds)
    {
        ObjectLifecycleSeconds = objectLifecycleSeconds;
    }

    public int ObjectLifecycleSeconds { get; }

    public static FalUploadPlatformHeaders ForSourceUpload(int objectLifecycleSeconds)
    {
        if (objectLifecycleSeconds <= 0)
            throw new ArgumentOutOfRangeException(nameof(objectLifecycleSeconds));

        return new FalUploadPlatformHeaders(objectLifecycleSeconds);
    }
}
```

Add helper response/error types as needed:

```csharp
public sealed class FalApiException : Exception
{
    public FalApiException(string message) : base(message) { }
}
```

Add method:

```csharp
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
    if (string.IsNullOrWhiteSpace(fileName))
        throw new ArgumentException("fal upload file name must be non-empty.", nameof(fileName));
    if (!IsSafeUploadFileName(fileName))
        throw new ArgumentException("fal upload file name is unsafe.", nameof(fileName));
    if (bytes is null || bytes.Length == 0)
        throw new ArgumentException("fal upload bytes must be non-empty.", nameof(bytes));
    if (string.IsNullOrWhiteSpace(contentType))
        throw new ArgumentException("fal upload content type must be non-empty.", nameof(contentType));
    if (platformHeaders is null)
        throw new ArgumentNullException(nameof(platformHeaders));

    using var request = new HttpRequestMessage(
        HttpMethod.Post,
        new Uri("https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3"));
    request.Headers.Authorization = new AuthenticationHeaderValue("Key", apiKey);
    request.Headers.TryAddWithoutValidation(
        "X-Fal-Object-Lifecycle",
        "{\"expiration_duration_seconds\":" +
        platformHeaders.ObjectLifecycleSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture) +
        "}");
    request.Content = new StringContent(
        System.Text.Json.JsonSerializer.Serialize(new
        {
            content_type = contentType,
            file_name = fileName,
        }),
        Encoding.UTF8,
        "application/json");

    using var initiateResponse = await _httpClient.SendAsync(request, ct).ConfigureAwait(false);
    var initiateBody = initiateResponse.Content is null
        ? string.Empty
        : await initiateResponse.Content.ReadAsStringAsync().ConfigureAwait(false);
    if (!initiateResponse.IsSuccessStatusCode)
        throw new FalApiException("fal upload initiation failed.");

    var initiate = System.Text.Json.JsonSerializer.Deserialize<FalUploadInitiateResponse>(initiateBody);
    if (initiate is null
        || !IsValidHttpsUrl(initiate.UploadUrl, out var uploadUrl)
        || !IsValidFalCdnFileUrl(initiate.FileUrl, out _))
    {
        throw new FalApiException("fal upload initiation returned an invalid URL.");
    }

    using var uploadRequest = new HttpRequestMessage(HttpMethod.Put, uploadUrl);
    uploadRequest.Content = new ByteArrayContent(bytes);
    uploadRequest.Content.Headers.ContentType = new MediaTypeHeaderValue(contentType);
    using var uploadResponse = await _httpClient.SendAsync(uploadRequest, ct).ConfigureAwait(false);
    if (!uploadResponse.IsSuccessStatusCode)
        throw new FalApiException("fal upload failed.");

    return initiate.FileUrl!;
}
```

Add helpers:

```csharp
private static bool IsSafeUploadFileName(string fileName)
{
    if (fileName.Contains("/", StringComparison.Ordinal)
        || fileName.Contains("\\", StringComparison.Ordinal)
        || fileName.Contains("://", StringComparison.Ordinal)
        || fileName == "."
        || fileName == "..")
        return false;

    return !string.IsNullOrWhiteSpace(fileName);
}

private static bool IsValidHttpsUrl(string? text, out Uri uri)
{
    if (Uri.TryCreate(text, UriKind.Absolute, out var parsed)
        && parsed.Scheme == Uri.UriSchemeHttps)
    {
        uri = parsed;
        return true;
    }

    uri = null!;
    return false;
}

internal static bool IsValidFalCdnFileUrl(string? text, out Uri uri) =>
    IsValidHttpsUrl(text, out uri)
    && uri.Host.StartsWith("v3", StringComparison.OrdinalIgnoreCase)
    && uri.Host.EndsWith(".fal.media", StringComparison.OrdinalIgnoreCase)
    && uri.AbsolutePath.StartsWith("/files/", StringComparison.Ordinal);

private sealed class FalUploadInitiateResponse
{
    [System.Text.Json.Serialization.JsonPropertyName("upload_url")]
    public string? UploadUrl { get; set; }

    [System.Text.Json.Serialization.JsonPropertyName("file_url")]
    public string? FileUrl { get; set; }
}
```

- [ ] **Step 8: Verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalApiClientTests"
```

Expected: all `FalApiClientTests` pass.

- [ ] **Step 9: Commit**

```powershell
git add src\Rook\Services\Vision\Fal\FalApiClient.cs `
        src\Rook.Tests\Services\Vision\Fal\FalApiClientTests.cs
git commit -m "feat(vision): add constrained fal upload client"
```

## Task 2: Add Seedance Source Transport Validation

**Files:**
- Create: `src/Rook/Services/Vision/Video/Fal/IFalSeedanceSourceTransport.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceUrls.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceTransport.cs`
- Create: `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceSourceTransportTests.cs`

- [ ] **Step 1: Write failing validation tests**

Create `FalSeedanceSourceTransportTests.cs` with initial validation tests:

```csharp
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalSeedanceSourceTransportTests
    {
        [Fact]
        public async Task ResolveAndUploadAsync_rejects_source_larger_than_seedance_limit_before_http()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var bytes = PngBytes(FalSeedanceSourceTransport.MaxSourceFrameBytes + 1);
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, start),
                Media(start, bytes, "image/png"),
                "test-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "start_frame");
            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("image/png")]
        [InlineData("image/jpeg")]
        [InlineData("image/webp")]
        public async Task ResolveAndUploadAsync_accepts_supported_mime_at_limit(string mime)
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var bytes = mime switch
            {
                "image/png" => PngBytes(FalSeedanceSourceTransport.MaxSourceFrameBytes),
                "image/jpeg" => JpegBytes(FalSeedanceSourceTransport.MaxSourceFrameBytes),
                _ => WebPBytes(FalSeedanceSourceTransport.MaxSourceFrameBytes),
            };
            var handler = UploadOkHandler();
            var transport = Transport(handler);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, start),
                Media(start, bytes, mime),
                "test-key",
                CancellationToken.None);

            Assert.Null(error);
            Assert.NotNull(urls);
            Assert.Equal(2, handler.Requests.Count);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_declared_mime_mismatch_before_http()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, start),
                Media(start, PngBytes(), "image/jpeg"),
                "test-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "start_frame");
            Assert.Empty(handler.Requests);
        }

        private static FalSeedanceSourceTransport Transport(TestHttpMessageHandler handler) =>
            new(new FalApiClient(new HttpClient(handler)));

        private static TestHttpMessageHandler UploadOkHandler() =>
            new()
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        return new HttpResponseMessage(System.Net.HttpStatusCode.OK)
                        {
                            Content = new StringContent(
                                @"{
                                  ""upload_url"": ""https://v3b.fal.media/upload/presigned-token"",
                                  ""file_url"": ""https://v3b.fal.media/files/rook-pr19-source.png""
                                }"),
                        };
                    }

                    return new HttpResponseMessage(System.Net.HttpStatusCode.OK);
                },
            };

        private static VideoGenerationRequest Request(
            VideoMode mode,
            MediaRef? start,
            MediaRef? end = null) =>
            new(
                FalVideoCapabilities.SeedanceI2v,
                mode,
                6,
                "720p",
                "16:9",
                "prompt",
                start,
                end,
                null,
                null,
                new FalVideoOptions(),
                1);

        private static MediaRef Artifact(string role) =>
            MediaRef.ForArtifact(Guid.NewGuid(), role);

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> Media(
            MediaRef mediaRef,
            byte[] bytes,
            string mimeType) =>
            new Dictionary<MediaRef, ResolvedMedia>
            {
                [mediaRef] = new ResolvedMedia(bytes, mimeType),
            };

        private static void AssertInvalid(GenerationError? error, string field)
        {
            Assert.NotNull(error);
            Assert.Equal(GenerationErrorCode.InvalidRequest, error!.Code);
            Assert.False(error.Retryable);
            Assert.Equal(field, error.Field);
        }
    }
}
```

Add byte helpers in the same test class:

```csharp
private static byte[] PngBytes(long length = 12)
{
    var bytes = new byte[length];
    bytes[0] = 0x89; bytes[1] = 0x50; bytes[2] = 0x4E; bytes[3] = 0x47;
    bytes[4] = 0x0D; bytes[5] = 0x0A; bytes[6] = 0x1A; bytes[7] = 0x0A;
    return bytes;
}

private static byte[] JpegBytes(long length = 6)
{
    var bytes = new byte[length];
    bytes[0] = 0xFF; bytes[1] = 0xD8; bytes[2] = 0xFF;
    return bytes;
}

private static byte[] WebPBytes(long length = 16)
{
    var bytes = new byte[length];
    bytes[0] = 0x52; bytes[1] = 0x49; bytes[2] = 0x46; bytes[3] = 0x46;
    bytes[8] = 0x57; bytes[9] = 0x45; bytes[10] = 0x42; bytes[11] = 0x50;
    return bytes;
}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalSeedanceSourceTransportTests"
```

Expected: compile fails because transport types do not exist.

- [ ] **Step 3: Add minimal transport types**

Create `IFalSeedanceSourceTransport.cs`:

```csharp
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal interface IFalSeedanceSourceTransport
    {
        Task<(FalSeedanceSourceUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            string apiKey,
            CancellationToken ct);
    }
}
```

Create `FalSeedanceSourceUrls.cs`:

```csharp
namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSeedanceSourceUrls
    {
        public FalSeedanceSourceUrls(string imageUrl, string? endImageUrl)
        {
            ImageUrl = imageUrl;
            EndImageUrl = endImageUrl;
        }

        public string ImageUrl { get; }
        public string? EndImageUrl { get; }
    }
}
```

Create `FalSeedanceSourceTransport.cs` with validation and one upload path:

```csharp
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSeedanceSourceTransport : IFalSeedanceSourceTransport
    {
        public const long MaxSourceFrameBytes = 30L * 1024L * 1024L;
        public const int SourceMediaExpirationSeconds = 3600;

        private readonly FalApiClient _client;

        public FalSeedanceSourceTransport(FalApiClient client)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
        }

        public async Task<(FalSeedanceSourceUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            string apiKey,
            CancellationToken ct)
        {
            var validation = ValidateRequest(request, media);
            if (validation.Error is not null)
                return (null, validation.Error);

            var start = await UploadAsync(apiKey, validation.Start!, "start_frame", ct)
                .ConfigureAwait(false);
            if (start.Error is not null)
                return (null, start.Error);

            string? endUrl = null;
            if (validation.End is not null)
            {
                var end = await UploadAsync(apiKey, validation.End, "end_frame", ct)
                    .ConfigureAwait(false);
                if (end.Error is not null)
                    return (null, end.Error);

                endUrl = end.Url;
            }

            return (new FalSeedanceSourceUrls(start.Url!, endUrl), null);
        }

        private static (
            ValidatedSource? Start,
            ValidatedSource? End,
            GenerationError? Error) ValidateRequest(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (request is null)
                return (null, null, InvalidSource("Seedance source upload requires a request.", "request"));
            if (media is null)
                return (null, null, InvalidSource("Seedance source upload requires resolved media.", "media"));
            if (request.Mode != VideoMode.I2V && request.Mode != VideoMode.Interp)
                return (null, null, InvalidSource("Seedance source upload supports only I2V and Interp.", "mode"));
            if (request.ReferenceFrames is { Count: > 0 })
                return (null, null, InvalidSource("Seedance source upload does not support reference frames.", "reference_frames"));
            if (request.StartFrame is null)
                return (null, null, InvalidSource("Seedance source upload requires a start frame.", "start_frame"));
            if (request.Mode == VideoMode.I2V && request.EndFrame is not null)
                return (null, null, InvalidSource("Seedance I2V source upload does not accept an end frame.", "end_frame"));
            if (request.Mode == VideoMode.Interp && request.EndFrame is null)
                return (null, null, InvalidSource("Seedance interpolation source upload requires an end frame.", "end_frame"));

            var start = Resolve(media, request.StartFrame, "start_frame");
            if (start.Error is not null)
                return (null, null, start.Error);

            ValidatedSource? end = null;
            if (request.Mode == VideoMode.Interp)
            {
                var resolvedEnd = Resolve(media, request.EndFrame!, "end_frame");
                if (resolvedEnd.Error is not null)
                    return (null, null, resolvedEnd.Error);
                end = resolvedEnd.Source;
            }

            return (start.Source, end, null);
        }

        private static (ValidatedSource? Source, GenerationError? Error) Resolve(
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            MediaRef mediaRef,
            string field)
        {
            if (!media.TryGetValue(mediaRef, out var resolved) || resolved is null)
                return (null, InvalidSource("Seedance source frame was not resolved.", field));
            if (resolved.Bytes is null || resolved.Bytes.Length == 0)
                return (null, InvalidSource("Seedance source frame is empty.", field));
            if (resolved.Bytes.LongLength > MaxSourceFrameBytes)
                return (null, InvalidSource("Seedance source frame exceeds the 30 MB provider limit.", field));

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ImageMimeDetector.IsPngJpegOrWebp(detectedMime))
                return (null, InvalidSource("Seedance source frame must be PNG, JPEG, or WebP.", field));
            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
            {
                return (null, InvalidSource("Seedance source frame MIME does not match its bytes.", field));
            }

            return (new ValidatedSource(resolved.Bytes, detectedMime), null);
        }

        private async Task<(string? Url, GenerationError? Error)> UploadAsync(
            string apiKey,
            ValidatedSource source,
            string field,
            CancellationToken ct)
        {
            var fileName = BuildFileName(source.MimeType);
            try
            {
                var url = await UploadWithRetryAsync(
                    apiKey,
                    fileName,
                    source,
                    ct).ConfigureAwait(false);

                return IsValidFalCdnUrl(url)
                    ? (url, null)
                    : (null, Dependency("fal Seedance source upload returned an invalid URL.", field));
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (TaskCanceledException)
            {
                return (null, Dependency("fal Seedance source upload timed out.", field));
            }
            catch (HttpRequestException)
            {
                return (null, Dependency("fal Seedance source upload failed due to a transport error.", field));
            }
        }

        private static string BuildFileName(string mimeType)
        {
            var ext = mimeType switch
            {
                "image/png" => "png",
                "image/jpeg" => "jpg",
                "image/webp" => "webp",
                _ => "bin",
            };
            return "rook-seedance-source-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture) + "." + ext;
        }

        internal static bool IsValidFalCdnUrl(string text) =>
            Uri.TryCreate(text, UriKind.Absolute, out var uri)
            && uri.Scheme == Uri.UriSchemeHttps
            && uri.Host.StartsWith("v3", StringComparison.OrdinalIgnoreCase)
            && uri.Host.EndsWith(".fal.media", StringComparison.OrdinalIgnoreCase)
            && uri.AbsolutePath.StartsWith("/files/", StringComparison.Ordinal);

        private static GenerationError InvalidSource(string message, string field) =>
            new(GenerationErrorCode.InvalidRequest, message, false, field);

        private static GenerationError Dependency(string message, string field) =>
            new(GenerationErrorCode.DependencyUnavailable, message, true, field);

        private sealed class ValidatedSource
        {
            public ValidatedSource(byte[] bytes, string mimeType)
            {
                Bytes = bytes;
                MimeType = mimeType;
            }

            public byte[] Bytes { get; }
            public string MimeType { get; }
        }
    }
}
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalSeedanceSourceTransportTests"
```

Expected: validation tests pass.

- [ ] **Step 5: Note empty-byte validation coverage**

Do not add an empty-byte test through `ResolvedMedia`; its constructor already
rejects empty byte arrays before provider code can see them. If the
implementation extracts a lower-level helper that accepts `ResolvedMedia`
instances from invariant-bypassing test construction, then add a helper-level
empty-byte test there. Otherwise treat empty-byte rejection as covered by the
`ResolvedMedia` invariant.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal\IFalSeedanceSourceTransport.cs `
        src\Rook\Services\Vision\Video\Fal\FalSeedanceSourceUrls.cs `
        src\Rook\Services\Vision\Video\Fal\FalSeedanceSourceTransport.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalSeedanceSourceTransportTests.cs
git commit -m "feat(vision): validate Seedance source uploads"
```

## Task 3: Add Upload Shape, URL, Retry, And Sanitization Coverage

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceSourceTransportTests.cs`
- Modify: `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceTransport.cs`

- [ ] **Step 1: Add failing upload shape and URL validation tests**

Add tests:

```csharp
[Fact]
public async Task ResolveAndUploadAsync_initiates_upload_with_private_filename_lifecycle_header_and_content_type()
{
    HttpRequestMessage? captured = null;
    var start = Artifact(VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            if (req.RequestUri!.Host == "rest.fal.ai")
            {
                captured = req;
                return new HttpResponseMessage(System.Net.HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        @"{
                          ""upload_url"": ""https://v3b.fal.media/upload/presigned-token"",
                          ""file_url"": ""https://v3b.fal.media/files/rook-pr19-source.png""
                        }"),
                };
            }

            Assert.Equal(HttpMethod.Put, req.Method);
            Assert.Equal("image/png", req.Content!.Headers.ContentType!.MediaType);
            return new HttpResponseMessage(System.Net.HttpStatusCode.OK);
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        Request(VideoMode.I2V, start),
        Media(start, PngBytes(), "image/png"),
        "test-key",
        CancellationToken.None);

    Assert.Null(error);
    Assert.NotNull(urls);
    Assert.NotNull(captured);
    Assert.Equal(
        "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3",
        captured!.RequestUri!.ToString());
    Assert.Equal(
        "{\"expiration_duration_seconds\":3600}",
        Assert.Single(captured.Headers.GetValues("X-Fal-Object-Lifecycle")));
    var initiateJson = await captured.Content!.ReadAsStringAsync();
    Assert.Contains(@"""content_type"":""image/png""", initiateJson);
    Assert.DoesNotContain("rook/seedance-sources", initiateJson, StringComparison.OrdinalIgnoreCase);
    Assert.StartsWith("https://v3", urls!.ImageUrl, StringComparison.Ordinal);
    Assert.Contains(".fal.media/files/", urls.ImageUrl, StringComparison.Ordinal);
    Assert.DoesNotContain("prompt", captured.RequestUri.ToString(), StringComparison.OrdinalIgnoreCase);
}

[Theory]
[InlineData("")]
[InlineData("relative/path.png")]
[InlineData("http://v3b.fal.media/files/x.png")]
[InlineData("file:///C:/x.png")]
[InlineData("data:image/png;base64,abc")]
[InlineData("https://example.com/files/x.png")]
public void IsValidFalCdnUrl_rejects_invalid_upload_urls(string url)
{
    Assert.False(FalSeedanceSourceTransport.IsValidFalCdnUrl(url));
}

[Fact]
public void IsValidFalCdnUrl_accepts_v3_fal_media_files_url()
{
    Assert.True(FalSeedanceSourceTransport.IsValidFalCdnUrl(
        "https://v3b.fal.media/files/source.png"));
}
```

- [ ] **Step 2: Run and verify RED if helpers are not visible**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalSeedanceSourceTransportTests"
```

Expected: tests compile and may pass if Task 2 exposed helpers as `internal`; if not, fail because URL validation helper is not visible. Fix by keeping helper `internal static`.

- [ ] **Step 3: Add failing retry and sanitization tests**

Add:

```csharp
[Fact]
public async Task ResolveAndUploadAsync_retries_one_transient_upload_failure()
{
    var attempts = 0;
    var start = Artifact(VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ =>
        {
            attempts++;
            if (attempts == 1)
                throw new HttpRequestException("temporary upload failure with https://v3b.fal.media/files/leak.png");

            return new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = new StringContent("true"),
            };
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        Request(VideoMode.I2V, start),
        Media(start, PngBytes(), "image/png"),
        "test-key",
        CancellationToken.None);

    Assert.Null(error);
    Assert.NotNull(urls);
    Assert.Equal(2, attempts);
}

[Fact]
public async Task ResolveAndUploadAsync_retries_one_upload_timeout_when_not_caller_cancelled()
{
    var attempts = 0;
    var start = Artifact(VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ =>
        {
            attempts++;
            if (attempts == 1)
                throw new TaskCanceledException("upload timed out");

            return new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = new StringContent("true"),
            };
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        Request(VideoMode.I2V, start),
        Media(start, PngBytes(), "image/png"),
        "test-key",
        CancellationToken.None);

    Assert.Null(error);
    Assert.NotNull(urls);
    Assert.Equal(2, attempts);
}

[Fact]
public async Task ResolveAndUploadAsync_propagates_caller_cancellation_without_retry()
{
    var attempts = 0;
    var start = Artifact(VideoMediaRoles.StartFrame);
    using var cts = new CancellationTokenSource();
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ =>
        {
            attempts++;
            cts.Cancel();
            throw new OperationCanceledException(cts.Token);
        },
    };
    var transport = Transport(handler);

    await Assert.ThrowsAsync<OperationCanceledException>(
        async () => await transport.ResolveAndUploadAsync(
            Request(VideoMode.I2V, start),
            Media(start, PngBytes(), "image/png"),
            "test-key",
            cts.Token));

    Assert.Equal(1, attempts);
}

[Fact]
public async Task ResolveAndUploadAsync_final_transport_failure_is_sanitized()
{
    var attempts = 0;
    var start = Artifact(VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ =>
        {
            attempts++;
            throw new HttpRequestException("https://v3b.fal.media/files/leak.png data:image/png;base64,abc");
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        Request(VideoMode.I2V, start),
        Media(start, PngBytes(), "image/png"),
        "test-key",
        CancellationToken.None);

    Assert.Null(urls);
    Assert.NotNull(error);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, error!.Code);
    Assert.True(error.Retryable);
    Assert.Null(error.ProviderDetail);
    Assert.DoesNotContain("fal.media", error.Message, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("data:image", error.Message, StringComparison.OrdinalIgnoreCase);
    Assert.Equal(2, attempts);
}

[Fact]
public async Task ResolveAndUploadAsync_final_upload_failure_is_sanitized()
{
    var start = Artifact(VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => new HttpResponseMessage(System.Net.HttpStatusCode.InternalServerError)
        {
            Content = new StringContent("{\"url\":\"https://v3b.fal.media/files/leak.png\",\"image_url\":\"data:image/png;base64,abc\"}"),
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        Request(VideoMode.I2V, start),
        Media(start, PngBytes(), "image/png"),
        "test-key",
        CancellationToken.None);

    Assert.Null(urls);
    Assert.NotNull(error);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, error!.Code);
    Assert.True(error.Retryable);
    Assert.Null(error.ProviderDetail);
    Assert.DoesNotContain("fal.media", error.Message, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("data:image", error.Message, StringComparison.OrdinalIgnoreCase);
}
```

- [ ] **Step 4: Implement bounded retry**

Change `UploadAsync` to call a helper:

```csharp
private async Task<string> UploadWithRetryAsync(
    string apiKey,
    string fileName,
    ValidatedSource source,
    CancellationToken ct)
{
    try
    {
        return await UploadOnceAsync(apiKey, fileName, source, ct).ConfigureAwait(false);
    }
    catch (HttpRequestException)
    {
        return await UploadOnceAsync(apiKey, fileName, source, ct).ConfigureAwait(false);
    }
    catch (TaskCanceledException) when (!ct.IsCancellationRequested)
    {
        return await UploadOnceAsync(apiKey, fileName, source, ct).ConfigureAwait(false);
    }
}

private Task<string> UploadOnceAsync(
    string apiKey,
    string fileName,
    ValidatedSource source,
    CancellationToken ct) =>
    _client.UploadFileToCdnAsync(
        apiKey,
        fileName,
        source.Bytes,
        source.MimeType,
        FalUploadPlatformHeaders.ForSourceUpload(SourceMediaExpirationSeconds),
        ct);
```

Use `UploadWithRetryAsync` from `UploadAsync`. Keep errors generic and provider detail null.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalSeedanceSourceTransportTests"
```

Expected: all transport tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal\FalSeedanceSourceTransport.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalSeedanceSourceTransportTests.cs
git commit -m "test(vision): cover Seedance source upload transport"
```

## Task 4: Wire Seedance Provider Submit To Uploaded URLs

**Files:**
- Modify: `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`
- Delete preferred: `src/Rook/Services/Vision/Video/Fal/FalSeedanceI2vSourcePayload.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`
- Delete preferred: `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceI2vSourcePayloadTests.cs`

- [ ] **Step 1: Add a fake source transport for provider tests**

In `FalVideoProviderTests`, add a private fake so provider tests can pin
orchestration without depending on upload HTTP internals:

```csharp
private sealed class FakeSeedanceSourceTransport : IFalSeedanceSourceTransport
{
    public int Calls { get; private set; }
    public GenerationError? Error { get; set; }
    public FalSeedanceSourceUrls Urls { get; set; } =
        new(
            "https://v3b.fal.media/files/rook-pr19-start.png",
            null);
    public CancellationToken? LastCancellationToken { get; private set; }

    public Task<(FalSeedanceSourceUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
        VideoGenerationRequest request,
        IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
        string apiKey,
        CancellationToken ct)
    {
        Calls++;
        LastCancellationToken = ct;
        return Task.FromResult(Error is null
            ? (Urls, (GenerationError?)null)
            : ((FalSeedanceSourceUrls?)null, Error));
    }
}

private static FalVideoProvider Provider(
    TestHttpMessageHandler handler,
    IFalSeedanceSourceTransport? sourceTransport = null) =>
    new(
        () => "test-fal-key",
        new FalApiClient(new HttpClient(handler)),
        sourceTransport);
```

Replace the existing single-argument `Provider(TestHttpMessageHandler)` helper
with this overload.

- [ ] **Step 2: Add failing provider orchestration tests**

Update the existing Seedance submit tests so they expect upload then queue submit. Example replacement for `Submit_seedance_i2v_posts_data_uri_body_and_returns_request_id_only_handle`:

```csharp
[Fact]
public async Task Submit_seedance_i2v_uploads_source_then_posts_cdn_url_body_and_returns_request_id_only_handle()
{
    string? submitBody = null;
    var sourceTransport = new FakeSeedanceSourceTransport();
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            submitBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return Json(HttpStatusCode.OK, @"{
              ""request_id"": ""seedance-123"",
              ""status"": ""IN_QUEUE""
            }");
        },
    };
    var provider = Provider(handler, sourceTransport);
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);

    var outcome = await provider.SubmitAsync(
        SeedanceRequest(VideoMode.I2V, startFrame: start),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
        },
        CancellationToken.None);

    var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
    Assert.Equal("seedance-123", queued.Handle.ProviderJobId);
    Assert.Null(queued.Handle.StatusUrl);
    Assert.Null(queued.Handle.ResponseUrl);
    Assert.Null(queued.Handle.CancelUrl);
    Assert.Null(queued.Handle.ProviderMetadata);

    Assert.Equal(1, sourceTransport.Calls);
    var submit = Assert.Single(handler.Requests);
    Assert.Equal("queue.fal.run", submit.RequestUri!.Host);

    var json = JsonNode.Parse(submitBody!)!.AsObject();
    var imageUrl = json["image_url"]!.GetValue<string>();
    Assert.StartsWith("https://v3", imageUrl, StringComparison.Ordinal);
    Assert.Contains(".fal.media/files/", imageUrl, StringComparison.Ordinal);
    Assert.DoesNotContain("data:", imageUrl, StringComparison.OrdinalIgnoreCase);
    Assert.False(json.ContainsKey("end_image_url"));

    Assert.Equal(
        "{\"expiration_duration_seconds\":3600}",
        Assert.Single(submit.Headers.GetValues("X-Fal-Object-Lifecycle-Preference")));
    Assert.Equal("0", Assert.Single(submit.Headers.GetValues("X-Fal-Store-IO")));
    Assert.Equal("1", Assert.Single(submit.Headers.GetValues("X-Fal-No-Retry")));
}
```

Add missing-key test:

```csharp
[Fact]
public async Task Submit_seedance_missing_key_does_not_upload_or_submit()
{
    var handler = new TestHttpMessageHandler();
    var sourceTransport = new FakeSeedanceSourceTransport();
    var provider = new FalVideoProvider(
        () => null,
        new FalApiClient(new HttpClient(handler)),
        sourceTransport);
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);

    var outcome = await provider.SubmitAsync(
        SeedanceRequest(VideoMode.I2V, startFrame: start),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
        },
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
    Assert.Equal(0, sourceTransport.Calls);
    Assert.Empty(handler.Requests);
}
```

Add upload-failure ordering test:

```csharp
[Fact]
public async Task Submit_seedance_upload_failure_never_calls_queue_submit_and_error_is_sanitized()
{
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
    var sourceTransport = new FakeSeedanceSourceTransport
    {
        Error = new GenerationError(
            GenerationErrorCode.DependencyUnavailable,
            "fal Seedance source upload failed.",
            true,
            "start_frame"),
    };
    var handler = new TestHttpMessageHandler();
    var provider = Provider(handler, sourceTransport);

    var outcome = await provider.SubmitAsync(
        SeedanceRequest(VideoMode.I2V, startFrame: start),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
        },
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
    Assert.True(failed.Error.Retryable);
    Assert.Null(failed.Error.ProviderDetail);
    Assert.DoesNotContain("fal.media", failed.Error.Message, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("data:image", failed.Error.Message, StringComparison.OrdinalIgnoreCase);
    Assert.Equal(1, sourceTransport.Calls);
    Assert.Empty(handler.Requests);
}
```

Add Interp partial upload test:

```csharp
[Fact]
public async Task Submit_seedance_interp_end_upload_failure_never_calls_queue_submit()
{
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
    var end = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.EndFrame);
    var sourceTransport = new FakeSeedanceSourceTransport
    {
        Error = new GenerationError(
            GenerationErrorCode.DependencyUnavailable,
            "fal Seedance source upload failed.",
            true,
            "end_frame"),
    };
    var handler = new TestHttpMessageHandler();
    var provider = Provider(handler, sourceTransport);

    var outcome = await provider.SubmitAsync(
        SeedanceRequest(VideoMode.Interp, startFrame: start, endFrame: end),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
            [end] = new ResolvedMedia(JpegBytes(), "image/jpeg"),
        },
        CancellationToken.None);

    Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(1, sourceTransport.Calls);
    Assert.Empty(handler.Requests);
}
```

- [ ] **Step 3: Add failing real-transport integration submit test**

Keep one provider test using the real transport and fake HTTP to prove
upload-before-submit integration across `FalVideoProvider`,
`FalSeedanceSourceTransport`, and `FalApiClient`:

```csharp
[Fact]
public async Task Submit_seedance_real_transport_uploads_before_queue_submit()
{
    var hosts = new List<string>();
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            hosts.Add(req.RequestUri!.Host);
            if (req.RequestUri.Host == "rest.fal.ai")
            {
                return Json(HttpStatusCode.OK, @"{
                  ""upload_url"": ""https://v3b.fal.media/upload/presigned-token"",
                  ""file_url"": ""https://v3b.fal.media/files/rook-pr19-source.png""
                }");
            }

            return req.RequestUri.Host == "v3b.fal.media"
                ? Json(HttpStatusCode.OK, "{}")
                : Json(HttpStatusCode.OK, @"{ ""request_id"": ""seedance-123"" }");
        },
    };
    var provider = Provider(handler);

    var outcome = await provider.SubmitAsync(
        SeedanceRequest(VideoMode.I2V, startFrame: start),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
        },
        CancellationToken.None);

    Assert.IsType<QueuedSubmitOutcome>(outcome);
    Assert.Equal(new[] { "rest.fal.ai", "v3b.fal.media", "queue.fal.run" }, hosts);
}
```

- [ ] **Step 4: Run and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoProviderTests"
```

Expected: Seedance submit tests fail because provider still builds data URIs and sends only one queue request.

- [ ] **Step 5: Wire transport into provider**

In `FalVideoProvider`, add field and constructor parameter:

```csharp
private readonly IFalSeedanceSourceTransport _seedanceSourceTransport;

public FalVideoProvider(
    Func<string?> apiKeyProvider,
    FalApiClient? client = null,
    IFalSeedanceSourceTransport? seedanceSourceTransport = null)
{
    _apiKeyProvider = apiKeyProvider
        ?? throw new ArgumentNullException(nameof(apiKeyProvider));
    _client = client ?? new FalApiClient();
    _seedanceSourceTransport = seedanceSourceTransport
        ?? new FalSeedanceSourceTransport(_client);
}
```

In `SubmitSeedanceAsync`, move API key lookup before source transport:

```csharp
var apiKey = _apiKeyProvider();
if (string.IsNullOrWhiteSpace(apiKey))
    return FailedSubmit(
        GenerationErrorCode.DependencyUnavailable,
        "fal API key is not configured.");

var (sourceUrls, sourceError) =
    await _seedanceSourceTransport.ResolveAndUploadAsync(
        request,
        resolvedMedia,
        apiKey!,
        ct).ConfigureAwait(false);
if (sourceError is not null)
    return new FailedSubmitOutcome(SanitizeProviderDetail(sourceError));
```

Replace `BuildSeedanceRequestJson(request, sourcePayload!)` with:

```csharp
BuildSeedanceRequestJson(request, sourceUrls!)
```

Change builder signature:

```csharp
private static string BuildSeedanceRequestJson(
    VideoGenerationRequest request,
    FalSeedanceSourceUrls sourceUrls)
```

Use `sourceUrls.ImageUrl` and `sourceUrls.EndImageUrl`.

Call queue submit with headers:

```csharp
response = await PostSeedanceSubmitWithConnectRetryAsync(
    apiKey!,
    BuildSeedanceRequestJson(request, sourceUrls!),
    FalJsonPlatformHeaders.ForSeedanceSubmit(
        FalSeedanceSourceTransport.SourceMediaExpirationSeconds,
        disableStoreIo: true,
        disableFalRetry: true),
    ct).ConfigureAwait(false);
```

Update `PostSeedanceSubmitWithConnectRetryAsync` signature to accept `FalJsonPlatformHeaders` and pass it to `_client.PostJsonAsync`.

- [ ] **Step 6: Remove data URI payload builder**

Delete:

- `src/Rook/Services/Vision/Video/Fal/FalSeedanceI2vSourcePayload.cs`
- `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceI2vSourcePayloadTests.cs`

If deletion reveals a non-provider caller, stop and inspect the caller before keeping compatibility.

- [ ] **Step 7: Verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoProviderTests|FalSeedanceSourceTransportTests"
```

Expected: provider and transport tests pass.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal `
        src\Rook.Tests\Services\Vision\Video\Fal
git commit -m "feat(vision): upload Seedance source frames"
```

## Task 5: Add Privacy, Ledger, And Boundary Coverage

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`
- Modify if needed: `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`
- No production files expected unless tests expose leakage.

- [ ] **Step 1: Strengthen the existing successful Seedance manager privacy test**

Modify the existing test
`Seedance_job_materializes_without_fal_transport_in_ledger_or_artifact_metadata`
in `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`.

Keep its existing fake provider flow and add explicit raw JSONL exclusions
after `var ledgerJson = File.ReadAllText(ledgerPath);`:

```csharp
Assert.DoesNotContain("https://v3.fal.media/files/rook/seedance-sources", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("api.fal.ai", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("rest.fal.ai", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("image_url", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("end_image_url", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("data:image", ledgerJson, StringComparison.OrdinalIgnoreCase);
```

Also add the same source-upload URL exclusion to `artifactMetadataJson` in
that test:

```csharp
Assert.DoesNotContain("https://v3.fal.media/files/rook/seedance-sources", artifactMetadataJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("api.fal.ai", artifactMetadataJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("rest.fal.ai", artifactMetadataJson, StringComparison.OrdinalIgnoreCase);
```

- [ ] **Step 2: Add deterministic failed-submit raw JSONL privacy test**

Modify the existing
`Seedance_submit_failure_does_not_persist_echoed_source_transport` test. In its
fake provider failure, ensure the forbidden strings include source-upload URL,
upload API host, source field names, and data URI:

```csharp
ProviderDetail: new Dictionary<string, JsonNode>
{
    ["image_url"] = JsonValue.Create("https://v3.fal.media/files/rook/seedance-sources/source.png")!,
    ["end_image_url"] = JsonValue.Create("https://v3.fal.media/files/rook/seedance-sources/end.png")!,
    ["upload_url"] = JsonValue.Create("https://v3b.fal.media/upload/presigned-token")!,
    ["initiate_url"] = JsonValue.Create("https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3")!,
    ["body"] = JsonValue.Create("data:image/png;base64," + Convert.ToBase64String(startBytes))!,
}
```

Then assert the raw ledger text excludes all forbidden markers:

```csharp
var ledgerJson = File.ReadAllText(ledgerPath);
Assert.Contains("fal request failed with HTTP 422", ledgerJson);
Assert.DoesNotContain("https://v3.fal.media/files/rook/seedance-sources", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("api.fal.ai", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("rest.fal.ai", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("data:image/", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("image_url", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("end_image_url", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("upload_url", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("initiate_url", ledgerJson, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain(Convert.ToBase64String(startBytes), ledgerJson, StringComparison.OrdinalIgnoreCase);
```

This test exercises real `JsonlVideoJobLedger` serialization because it reads
the raw `seedance-failure-ledger.jsonl` file already created by the test.

- [ ] **Step 3: Add bridge response privacy assertion if missing**

In `VideoOpHandlerTests`, find Seedance/list/result tests:

```powershell
rg -n "Seedance|list_video_models|submit_video_job|get_video_job" src\Rook.Tests\Handlers\VideoOpHandlerTests.cs
```

Add assertions to the Seedance bridge result/status/list payload strings:

```csharp
var payload = result.ToJsonString();
Assert.DoesNotContain("fal.media", payload, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("api.fal.ai", payload, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("rest.fal.ai", payload, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("image_url", payload, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("end_image_url", payload, StringComparison.OrdinalIgnoreCase);
Assert.DoesNotContain("data:image", payload, StringComparison.OrdinalIgnoreCase);
```

- [ ] **Step 4: Run and verify RED/GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VideoJobManagerTests|VideoOpHandlerTests"
```

Expected: pass if provider changes already preserve privacy. If a test fails with actual leakage, fix the leak in the minimal production file and rerun this command.

- [ ] **Step 5: Run boundary scan**

Run:

```powershell
rg -n "SeedanceSource|source upload|fal.media|api.fal.ai|rest.fal.ai|image_url|end_image_url" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected: no new source-upload route/tool/bridge exposure. Existing unrelated strings must be inspected and documented in PR notes if present.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook.Tests\Services\Vision\Video\VideoJobManagerTests.cs `
        src\Rook.Tests\Handlers\VideoOpHandlerTests.cs
git commit -m "test(vision): pin Seedance source upload privacy"
```

## Task 6: Final Verification And Handoff

**Files:**
- No required code files.
- PR notes should cite the contract confirmation from Task 0.

- [ ] **Step 1: Run focused fal/Seedance suite**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalApiClientTests|FalSeedanceSourceTransportTests|FalVideoProviderTests|VideoJobManagerTests|VideoOpHandlerTests"
```

Expected: all selected tests pass.

- [ ] **Step 2: Run leakage scan in changed managed files**

```powershell
rg -n "data:image|image_url|end_image_url|fal.media|api.fal.ai|rest.fal.ai|X-Fal-Object-Lifecycle|X-Fal-Store-IO|X-Fal-No-Retry" src\Rook src\Rook.Tests
```

Expected:

- `rest.fal.ai`, `api.fal.ai`, `fal.media`, and fal headers appear only in fal client/source transport/provider tests and implementation.
- `image_url` / `end_image_url` appear in Seedance submit construction/tests but not ledger/artifact persistence code.
- No `data:image` remains in Seedance source transport or Seedance provider submit tests.

- [ ] **Step 3: Run boundary scan**

```powershell
rg -n "SeedanceSource|source upload|fal.media|api.fal.ai|rest.fal.ai|X-Fal-Object-Lifecycle|X-Fal-No-Retry|image_url|end_image_url" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected: no source-upload exposure outside managed fal internals.

- [ ] **Step 4: Run diff check**

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 5: Build managed companion**

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 -c Release
```

Expected: build succeeds. Existing warnings may remain; new warnings should be inspected.

- [ ] **Step 6: Run full managed suite if time permits**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: full suite passes.

- [ ] **Step 7: Optional manual fal/Rhino smoke**

Only run if provider spend is approved for this handoff.

Use a non-sensitive source image. After completion, scan the latest ledger/artifact manifest for:

```powershell
rg -n "fal.media|api.fal.ai|rest.fal.ai|image_url|end_image_url|data:image|status_url|response_url|cancel_url" "$env:APPDATA\Rook"
```

Expected: no source upload URL, data URI, queue URL, or provider envelope leakage.

## Plan Self-Review

- Spec coverage: Tasks cover REST upload contract confirmation, exact upload lifecycle header, initiate-plus-presigned-PUT upload shape, source validation, always-upload Seedance transport, provider queue headers including `X-Fal-No-Retry`, missing-key ordering, retry policy, no-submit-after-upload-failure, raw JSONL leakage, and boundary scans.
- Placeholder scan: No code step uses `TBD`, `TODO`, or "fill in later". Task 0 is an explicit implementation blocker, not a placeholder.
- Type consistency: The plan consistently uses `FalJsonPlatformHeaders`, `FalUploadPlatformHeaders`, `IFalSeedanceSourceTransport`, `FalSeedanceSourceTransport`, `FalSeedanceSourceUrls`, `FalSeedanceSourceTransport.MaxSourceFrameBytes`, and `FalSeedanceSourceTransport.SourceMediaExpirationSeconds`.
- Provider test seam: Provider orchestration tests use a fake `IFalSeedanceSourceTransport`; one integration test keeps the real transport plus fake HTTP to prove upload-before-submit ordering.
- Scope check: The plan stays in managed Vision fal code/tests and does not add native, MCP, public HTTP, or internal bridge surfaces.
