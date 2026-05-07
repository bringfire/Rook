# Kling v3 Standard I2V Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add curated fal `fal-ai/kling-video/v3/standard/image-to-video` support for Rook Vision video I2V and Interp without provider URL leakage.

**Architecture:** Keep the public video job shape unchanged. Add one fal model row, reuse fal provider/model-aware lifecycle, and generalize the PR-19 Seedance source upload code into a provider-private fal video source-frame transport with per-model policy. Kling-specific submit JSON, lifecycle endpoint reconstruction, result parsing, pricing, and tests stay inside `Services/Vision/Video/Fal`.

**Tech Stack:** C#/.NET 7, xUnit, `System.Text.Json.Nodes`, Rook managed Vision video provider abstractions, existing `FalApiClient` upload/queue helpers.

---

## File Structure

Create:

- `src/Rook/Services/Vision/Video/Fal/FalKlingV3StandardI2vPricingModel.cs`
  Kling audio-off per-output-second pricing model.
- `src/Rook/Services/Vision/Video/Fal/FalSourceFramePolicy.cs`
  Provider-private policy object for fal video source-frame validation.
- `src/Rook/Services/Vision/Video/Fal/FalSourceFrameUrls.cs`
  Provider-private volatile start/end CDN URL value object.
- `src/Rook/Services/Vision/Video/Fal/IFalSourceFrameTransport.cs`
  Provider-private source-frame transport seam used by fake tests.
- `src/Rook/Services/Vision/Video/Fal/FalSourceFrameTransport.cs`
  Generalized PR-19 upload implementation.
- `src/Rook.Tests/Services/Vision/Video/Fal/FalKlingV3StandardI2vPricingModelTests.cs`
  Pricing math tests.
- `src/Rook.Tests/Services/Vision/Video/Fal/FalSourceFrameTransportTests.cs`
  Policy-driven transport tests replacing Seedance-named tests.

Modify:

- `src/Rook/Services/Vision/Video/Fal/FalVideoCapabilities.cs`
  Add Kling model id and capability row.
- `src/Rook/Services/Vision/Video/Fal/FalVideoOptionsCodec.cs`
  Require prompt for Kling and keep unknown fal option fields rejected.
- `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`
  Add Kling submit/status/result/cancel branches; use generalized source-frame transport.
- `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderRegistrationTests.cs`
  Pin Kling catalog/capability/pricing.
- `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoOptionsCodecTests.cs`
  Pin Kling prompt requirement and deferred provider-option rejection.
- `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`
  Pin Kling submit body, platform headers, request-id-only handles, lifecycle URLs, result parsing, and sanitized failures.
- `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`
  Update list-model expectations and no-leak marker scan for Kling fields.

Delete after replacement:

- `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceTransport.cs`
- `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceUrls.cs`
- `src/Rook/Services/Vision/Video/Fal/IFalSeedanceSourceTransport.cs`
- `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceSourceTransportTests.cs`

Do not modify:

- `src/RookNative/**`
- `mcp_server/**`
- native route registration
- internal bridge registrar surfaces
- video ledger schema

---

### Task 1: Register Kling Capability And Pricing

**Files:**
- Create: `src/Rook/Services/Vision/Video/Fal/FalKlingV3StandardI2vPricingModel.cs`
- Create: `src/Rook.Tests/Services/Vision/Video/Fal/FalKlingV3StandardI2vPricingModelTests.cs`
- Modify: `src/Rook/Services/Vision/Video/Fal/FalVideoCapabilities.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderRegistrationTests.cs`
- Modify: `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`

- [x] **Step 1: Write failing registration tests**

In `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderRegistrationTests.cs`, update `Registration_exposes_wan_t2v_and_seedance_i2v_models` to include Kling:

```csharp
[Fact]
public void Registration_exposes_wan_seedance_and_kling_models()
{
    var registration = new FalVideoProviderRegistration(new NullVideoProvider());

    Assert.Equal(3, registration.Models.Count);
    Assert.True(registration.Models.ContainsKey(FalVideoCapabilities.WanT2v));
    Assert.True(registration.Models.ContainsKey(FalVideoCapabilities.SeedanceI2v));
    Assert.True(registration.Models.ContainsKey(FalVideoCapabilities.KlingV3StandardI2v));
    Assert.Equal(
        FalVideoCapabilities.WanT2v,
        registration.Models[FalVideoCapabilities.WanT2v].Capability.Id);
    Assert.Equal(
        FalVideoCapabilities.SeedanceI2v,
        registration.Models[FalVideoCapabilities.SeedanceI2v].Capability.Id);
    Assert.Equal(
        FalVideoCapabilities.KlingV3StandardI2v,
        registration.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability.Id);
    Assert.IsType<FalWanT2vPricingModel>(
        registration.Models[FalVideoCapabilities.WanT2v].PricingModel);
    Assert.IsType<FalSeedanceI2vPricingModel>(
        registration.Models[FalVideoCapabilities.SeedanceI2v].PricingModel);
    Assert.IsType<FalKlingV3StandardI2vPricingModel>(
        registration.Models[FalVideoCapabilities.KlingV3StandardI2v].PricingModel);
    Assert.IsType<FalVideoOptionsCodec>(registration.OptionsCodec);
}
```

Add this test in the same file:

```csharp
[Fact]
public void Kling_capability_is_i2v_interp_with_auto_shape_and_3_to_15_durations()
{
    var cap = FalVideoCapabilities.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability;

    Assert.Equal("fal-ai/kling-video/v3/standard/image-to-video", cap.Id);
    Assert.Equal("Kling v3 Standard Image to Video", cap.Name);
    Assert.Equal("preview", cap.Status);
    Assert.Equal(
        new[] { VideoMode.I2V, VideoMode.Interp }.OrderBy(x => x),
        cap.Modes.OrderBy(x => x));
    Assert.DoesNotContain(VideoMode.T2V, cap.Modes);
    Assert.False(cap.SupportsReferenceImages);
    Assert.Equal(0, cap.MaxReferenceImages);
    Assert.Empty(cap.Must8sWith);
    Assert.Equal(new[] { "auto" }, cap.Resolutions);
    Assert.Equal(new[] { "auto" }, cap.AspectRatios);
    Assert.Equal(Enumerable.Range(3, 13), cap.Durations);
    Assert.DoesNotContain(2, cap.Durations);
    Assert.DoesNotContain(16, cap.Durations);
}
```

- [x] **Step 2: Write failing pricing tests**

Create `src/Rook.Tests/Services/Vision/Video/Fal/FalKlingV3StandardI2vPricingModelTests.cs`:

```csharp
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalKlingV3StandardI2vPricingModelTests
    {
        [Fact]
        public void Estimate_prices_audio_off_output_seconds()
        {
            var model = new FalKlingV3StandardI2vPricingModel();
            var capability = FalVideoCapabilities.Models[
                FalVideoCapabilities.KlingV3StandardI2v].Capability;
            var request = Request(durationSeconds: 5);

            var result = model.Estimate(request, capability);

            Assert.True(result.Success);
            Assert.NotNull(result.Pricing);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal(0.084m, result.Pricing.UnitPrice);
            Assert.Equal("output_second", result.Pricing.Unit);
            Assert.Equal(5m, result.Pricing.Quantity);
            Assert.Equal(0.420m, result.Pricing.TotalUsd);
            Assert.Equal(FalKlingV3StandardI2vPricingModel.Source, result.Pricing.PricingSource);
            Assert.NotNull(result.Estimate);
            Assert.False(result.Estimate!.IsExact);
        }

        [Fact]
        public void Estimate_rejects_null_request()
        {
            var model = new FalKlingV3StandardI2vPricingModel();
            var capability = FalVideoCapabilities.Models[
                FalVideoCapabilities.KlingV3StandardI2v].Capability;

            var result = model.Estimate(null!, capability);

            Assert.False(result.Success);
            Assert.Equal("request", result.Error!.Field);
        }

        private static VideoGenerationRequest Request(int durationSeconds) =>
            new(
                Model: FalVideoCapabilities.KlingV3StandardI2v,
                Mode: VideoMode.I2V,
                DurationSeconds: durationSeconds,
                Resolution: "auto",
                AspectRatio: "auto",
                Prompt: "animate this source",
                StartFrame: MediaRef.ForArtifact(System.Guid.NewGuid(), VideoMediaRoles.StartFrame),
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);
    }
}
```

- [x] **Step 3: Update handler list-model test to expect Kling**

In `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`, replace the Kling absence assertion in `ListModels_exposes_seedance_as_fal_i2v_interp_model` with an explicit Kling assertion:

```csharp
var kling = Assert.Single(
    models,
    m => (string?)m["model_id"] == FalVideoCapabilities.KlingV3StandardI2v);
Assert.Equal(FalVideoCapabilities.ProviderName, kling["provider_name"]);
var klingCap = Assert.IsType<Dictionary<string, object?>>(kling["capability"]);
Assert.Equal(FalVideoCapabilities.KlingV3StandardI2v, klingCap["id"]);
AssertNoFalSourceTransportMarkers(JsonSerializer.Serialize(data));
```

Update `AssertNoFalSourceTransportMarkers` in the same file to include Kling source fields:

```csharp
private static void AssertNoFalSourceTransportMarkers(string text)
{
    Assert.DoesNotContain("fal.media", text);
    Assert.DoesNotContain("api.fal.ai", text);
    Assert.DoesNotContain("rest.fal.ai", text);
    Assert.DoesNotContain("image_url", text);
    Assert.DoesNotContain("start_image_url", text);
    Assert.DoesNotContain("end_image_url", text);
    Assert.DoesNotContain("data:image", text);
}
```

- [x] **Step 4: Run tests to verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoProviderRegistrationTests|FalKlingV3StandardI2vPricingModelTests|ListModels_exposes_seedance_as_fal_i2v_interp_model"
```

Expected: fail to compile because `FalVideoCapabilities.KlingV3StandardI2v` and `FalKlingV3StandardI2vPricingModel` do not exist.

- [x] **Step 5: Implement capability and pricing**

In `src/Rook/Services/Vision/Video/Fal/FalVideoCapabilities.cs`, add the model id:

```csharp
public const string KlingV3StandardI2v = "fal-ai/kling-video/v3/standard/image-to-video";
```

Add this dictionary entry after Seedance:

```csharp
[KlingV3StandardI2v] = (
    new VideoCapability(
        Id: KlingV3StandardI2v,
        Name: "Kling v3 Standard Image to Video",
        Status: "preview",
        Resolutions: new[] { "auto" },
        Durations: new[] { 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 },
        AspectRatios: new[] { "auto" },
        Modes: new[] { VideoMode.I2V, VideoMode.Interp },
        SupportsReferenceImages: false,
        MaxReferenceImages: 0,
        Must8sWith: Array.Empty<string>()),
    new FalKlingV3StandardI2vPricingModel()),
```

Create `src/Rook/Services/Vision/Video/Fal/FalKlingV3StandardI2vPricingModel.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalKlingV3StandardI2vPricingModel
        : IPricingModel<VideoGenerationRequest, VideoCapability>
    {
        public const string Source = "fal-ai-kling-video-v3-standard-i2v-output-second-2026-05-06";
        private const decimal UnitPriceUsd = 0.084m;

        public string PricingSource => Source;

        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

        public PricingResult Estimate(
            VideoGenerationRequest request,
            VideoCapability capability)
        {
            if (request is null)
                return PricingResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            if (capability is null)
                return PricingResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Capability is null.",
                    Retryable: false,
                    Field: nameof(VideoCapability)));

            decimal quantity;
            try { quantity = checked(request.DurationSeconds * request.NumberOfVideos); }
            catch (OverflowException)
            {
                return PricingResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    $"Quantity overflow: duration={request.DurationSeconds} x count={request.NumberOfVideos}.",
                    Retryable: false,
                    Field: nameof(request.NumberOfVideos)));
            }

            var total = UnitPriceUsd * quantity;
            var pricing = new JobPricing(
                Currency: "USD",
                UnitPrice: UnitPriceUsd,
                Unit: "output_second",
                Quantity: quantity,
                TotalUsd: total,
                PricingSource: Source);
            var estimate = new CostEstimate(
                Min: total,
                Max: total,
                IsExact: false,
                Provenance: Source);

            return PricingResult.Ok(pricing, estimate);
        }

        public JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody) => null;
    }
}
```

- [x] **Step 6: Run tests to verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoProviderRegistrationTests|FalKlingV3StandardI2vPricingModelTests|ListModels_exposes_seedance_as_fal_i2v_interp_model"
```

Expected: pass.

- [x] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal\FalVideoCapabilities.cs `
        src\Rook\Services\Vision\Video\Fal\FalKlingV3StandardI2vPricingModel.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalVideoProviderRegistrationTests.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalKlingV3StandardI2vPricingModelTests.cs `
        src\Rook.Tests\Handlers\VideoOpHandlerTests.cs
git commit -m "Add Kling v3 video capability and pricing"
```

---

### Task 2: Tighten fal Video Options For Kling

**Files:**
- Modify: `src/Rook/Services/Vision/Video/Fal/FalVideoOptionsCodec.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoOptionsCodecTests.cs`

- [x] **Step 1: Write failing options tests**

Add these tests to `FalVideoOptionsCodecTests`:

```csharp
[Fact]
public void Validate_rejects_missing_prompt_for_kling()
{
    var request = KlingRequest(prompt: " ");

    var result = _codec.Validate(
        request,
        request.Options,
        FalVideoCapabilities.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability);

    Assert.False(result.Success);
    Assert.Equal(nameof(VideoGenerationRequest.Prompt), result.Field);
    Assert.Contains("Kling", result.Message);
}

[Fact]
public void Validate_accepts_prompt_for_kling()
{
    var request = KlingRequest(prompt: "camera glides around the model");

    var result = _codec.Validate(
        request,
        request.Options,
        FalVideoCapabilities.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability);

    Assert.True(result.Success);
}

[Theory]
[InlineData("multi_prompt")]
[InlineData("elements")]
[InlineData("negative_prompt")]
[InlineData("cfg_scale")]
[InlineData("generate_audio")]
public void Deserialize_kling_deferred_provider_fields_fail(string field)
{
    var json = new JsonObject { [field] = "x" };

    var result = _codec.Deserialize(json);

    Assert.False(result.Success);
    Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
    Assert.Equal(field, result.Error.Field);
}

private static VideoGenerationRequest KlingRequest(string? prompt) =>
    new(
        Model: FalVideoCapabilities.KlingV3StandardI2v,
        Mode: VideoMode.I2V,
        DurationSeconds: 5,
        Resolution: "auto",
        AspectRatio: "auto",
        Prompt: prompt,
        StartFrame: MediaRef.ForArtifact(System.Guid.NewGuid(), VideoMediaRoles.StartFrame),
        EndFrame: null,
        ReferenceFrames: null,
        Seed: null,
        Options: new FalVideoOptions(),
        NumberOfVideos: 1);
```

- [x] **Step 2: Run tests to verify missing prompt fails**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoOptionsCodecTests"
```

Expected: `Validate_rejects_missing_prompt_for_kling` fails because only Seedance currently has fal prompt validation.

- [x] **Step 3: Implement Kling prompt validation**

In `FalVideoOptionsCodec.Validate`, replace the Seedance-only prompt branch with:

```csharp
if ((string.Equals(cap.Id, FalVideoCapabilities.SeedanceI2v, StringComparison.Ordinal)
        || string.Equals(cap.Id, FalVideoCapabilities.KlingV3StandardI2v, StringComparison.Ordinal))
    && string.IsNullOrWhiteSpace(request.Prompt))
{
    var modelName = string.Equals(cap.Id, FalVideoCapabilities.KlingV3StandardI2v, StringComparison.Ordinal)
        ? "Kling v3 Standard Image to Video"
        : "Seedance 2.0 Image to Video";
    return Rook.Services.Vision.Generation.ValidationResult.Fail(
        $"{modelName} requires prompt.",
        nameof(VideoGenerationRequest.Prompt));
}
```

- [x] **Step 4: Run tests to verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoOptionsCodecTests"
```

Expected: pass.

- [x] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal\FalVideoOptionsCodec.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalVideoOptionsCodecTests.cs
git commit -m "Validate Kling fal video options"
```

---

### Task 3: Generalize fal Video Source-Frame Transport

**Files:**
- Create: `src/Rook/Services/Vision/Video/Fal/FalSourceFramePolicy.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalSourceFrameUrls.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/IFalSourceFrameTransport.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalSourceFrameTransport.cs`
- Create: `src/Rook.Tests/Services/Vision/Video/Fal/FalSourceFrameTransportTests.cs`
- Modify: `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`
- Delete: `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceTransport.cs`
- Delete: `src/Rook/Services/Vision/Video/Fal/FalSeedanceSourceUrls.cs`
- Delete: `src/Rook/Services/Vision/Video/Fal/IFalSeedanceSourceTransport.cs`
- Delete: `src/Rook.Tests/Services/Vision/Video/Fal/FalSeedanceSourceTransportTests.cs`

- [x] **Step 1: Rename the existing test file before editing**

Run:

```powershell
git mv src\Rook.Tests\Services\Vision\Video\Fal\FalSeedanceSourceTransportTests.cs `
       src\Rook.Tests\Services\Vision\Video\Fal\FalSourceFrameTransportTests.cs
```

- [x] **Step 2: Convert the renamed tests to the new transport names**

In `FalSourceFrameTransportTests.cs`, change:

```csharp
public class FalSeedanceSourceTransportTests
```

to:

```csharp
public class FalSourceFrameTransportTests
```

Replace test helper `Transport` with:

```csharp
private static FalSourceFrameTransport Transport(TestHttpMessageHandler handler) =>
    new(new FalApiClient(new HttpClient(handler)));

private static FalSourceFramePolicy SeedancePolicy() =>
    new(
        ModelLabel: "Seedance",
        FileNamePrefix: "rook-seedance-source",
        AllowedModes: new[] { VideoMode.I2V, VideoMode.Interp },
        MaxSourceFrameBytes: 30L * 1024L * 1024L,
        AllowedMimeTypes: new[] { "image/png", "image/jpeg", "image/webp" },
        RejectEndFrameForI2v: true);

private static FalSourceFramePolicy KlingPolicy(long? maxBytes = null) =>
    new(
        ModelLabel: "Kling",
        FileNamePrefix: "rook-kling-source",
        AllowedModes: new[] { VideoMode.I2V, VideoMode.Interp },
        MaxSourceFrameBytes: maxBytes ?? (30L * 1024L * 1024L),
        AllowedMimeTypes: new[] { "image/png", "image/jpeg", "image/webp" },
        RejectEndFrameForI2v: true);
```

Update every call from:

```csharp
transport.ResolveAndUploadAsync(request, media, "test-fal-key", CancellationToken.None)
```

to:

```csharp
transport.ResolveAndUploadAsync(
    SeedancePolicy(),
    request,
    media,
    "test-fal-key",
    CancellationToken.None)
```

Where a test specifically covers Kling filename/error wording, use `KlingPolicy()`.

- [x] **Step 3: Add Kling-specific failing transport tests**

Add these tests to `FalSourceFrameTransportTests.cs`:

```csharp
[Fact]
public async Task ResolveAndUploadAsync_kling_uses_kling_filename_prefix_and_error_label()
{
    string? initiateBody = null;
    var start = Artifact(VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            if (req.RequestUri!.Host == "rest.fal.ai")
            {
                initiateBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                return Json(HttpStatusCode.OK, """
                    {
                      "upload_url": "https://uploads.example.test/source-token",
                      "file_url": "https://v3b.fal.media/files/source-private.png"
                    }
                    """);
            }

            return new HttpResponseMessage(HttpStatusCode.NoContent);
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        KlingPolicy(),
        Request(
            VideoMode.I2V,
            startFrame: start,
            model: FalVideoCapabilities.KlingV3StandardI2v,
            resolution: "auto",
            aspectRatio: "auto"),
        Media(start, PngBytes(), "image/png"),
        "test-fal-key",
        CancellationToken.None);

    Assert.Null(error);
    Assert.Equal("https://v3b.fal.media/files/source-private.png", urls!.StartImageUrl);
    Assert.Matches(
        "^rook-kling-source-[0-9a-f]{32}\\.png$",
        InitiateFileName(initiateBody!));
}

[Fact]
public async Task ResolveAndUploadAsync_kling_final_failure_is_sanitized_with_kling_message()
{
    var start = Artifact(VideoMediaRoles.StartFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            if (req.RequestUri!.Host == "rest.fal.ai")
            {
                return Json(HttpStatusCode.OK, """
                    {
                      "upload_url": "https://uploads.example.test/source-token",
                      "file_url": "https://v3b.fal.media/files/leak.png"
                    }
                    """);
            }

            return Json(HttpStatusCode.InternalServerError, """
                {
                  "start_image_url": "https://v3b.fal.media/files/leak.png",
                  "upload_url": "https://uploads.example.test/source-token",
                  "prompt": "secret prompt"
                }
                """);
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        KlingPolicy(),
        Request(
            VideoMode.I2V,
            startFrame: start,
            model: FalVideoCapabilities.KlingV3StandardI2v,
            resolution: "auto",
            aspectRatio: "auto",
            prompt: "secret prompt"),
        Media(start, PngBytes(), "image/png"),
        "test-fal-key",
        CancellationToken.None);

    Assert.Null(urls);
    Assert.NotNull(error);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, error!.Code);
    Assert.True(error.Retryable);
    Assert.Null(error.ProviderDetail);
    Assert.Equal("fal Kling source upload failed.", error.Message);
    Assert.DoesNotContain("v3b.fal.media", error.Message);
    Assert.DoesNotContain("uploads.example.test", error.Message);
    Assert.DoesNotContain("secret prompt", error.Message);
}

[Fact]
public async Task ResolveAndUploadAsync_interp_end_upload_failure_does_not_return_partial_urls()
{
    var uploadIndex = 0;
    var start = Artifact(VideoMediaRoles.StartFrame);
    var end = Artifact(VideoMediaRoles.EndFrame);
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            if (req.RequestUri!.Host == "rest.fal.ai")
            {
                uploadIndex++;
                return Json(HttpStatusCode.OK, $$"""
                    {
                      "upload_url": "https://uploads.example.test/source-{{uploadIndex}}",
                      "file_url": "https://v3b.fal.media/files/source-{{uploadIndex}}.png"
                    }
                    """);
            }

            if (req.RequestUri!.AbsolutePath.EndsWith("/source-2", StringComparison.Ordinal))
                return Json(HttpStatusCode.InternalServerError, "{}");

            return new HttpResponseMessage(HttpStatusCode.NoContent);
        },
    };
    var transport = Transport(handler);

    var (urls, error) = await transport.ResolveAndUploadAsync(
        KlingPolicy(),
        Request(
            VideoMode.Interp,
            startFrame: start,
            endFrame: end,
            model: FalVideoCapabilities.KlingV3StandardI2v,
            resolution: "auto",
            aspectRatio: "auto"),
        Media(
            (start, new ResolvedMedia(PngBytes(), "image/png")),
            (end, new ResolvedMedia(PngBytes(), "image/png"))),
        "test-fal-key",
        CancellationToken.None);

    Assert.Null(urls);
    Assert.NotNull(error);
    Assert.Equal("end_frame", error!.Field);
}
```

Update the existing `Request` helper signature in this file to accept model/resolution/aspect ratio:

```csharp
private static VideoGenerationRequest Request(
    VideoMode mode,
    MediaRef? startFrame,
    MediaRef? endFrame = null,
    IReadOnlyList<MediaRef>? referenceFrames = null,
    string? prompt = "clip",
    string? model = null,
    string resolution = "720p",
    string aspectRatio = "16:9") =>
    new(
        Model: model ?? FalVideoCapabilities.SeedanceI2v,
        Mode: mode,
        DurationSeconds: 6,
        Resolution: resolution,
        AspectRatio: aspectRatio,
        Prompt: prompt,
        StartFrame: startFrame,
        EndFrame: endFrame,
        ReferenceFrames: referenceFrames,
        Seed: null,
        Options: new FalVideoOptions(),
        NumberOfVideos: 1);
```

- [x] **Step 4: Run tests to verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalSourceFrameTransportTests"
```

Expected: compile fails because `FalSourceFrameTransport`, `FalSourceFramePolicy`, and `FalSourceFrameUrls` do not exist.

- [x] **Step 5: Create the generalized transport types**

Create `src/Rook/Services/Vision/Video/Fal/FalSourceFramePolicy.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSourceFramePolicy
    {
        public FalSourceFramePolicy(
            string ModelLabel,
            string FileNamePrefix,
            IReadOnlyList<VideoMode> AllowedModes,
            long MaxSourceFrameBytes,
            IReadOnlyList<string> AllowedMimeTypes,
            bool RejectEndFrameForI2v)
        {
            if (string.IsNullOrWhiteSpace(ModelLabel))
                throw new ArgumentException("Model label must be non-empty.", nameof(ModelLabel));
            if (string.IsNullOrWhiteSpace(FileNamePrefix))
                throw new ArgumentException("Filename prefix must be non-empty.", nameof(FileNamePrefix));
            if (AllowedModes is null || AllowedModes.Count == 0)
                throw new ArgumentException("Allowed modes must be non-empty.", nameof(AllowedModes));
            if (MaxSourceFrameBytes <= 0)
                throw new ArgumentOutOfRangeException(nameof(MaxSourceFrameBytes));
            if (AllowedMimeTypes is null || AllowedMimeTypes.Count == 0)
                throw new ArgumentException("Allowed MIME types must be non-empty.", nameof(AllowedMimeTypes));

            this.ModelLabel = ModelLabel;
            this.FileNamePrefix = FileNamePrefix;
            this.AllowedModes = AllowedModes;
            this.MaxSourceFrameBytes = MaxSourceFrameBytes;
            this.AllowedMimeTypes = AllowedMimeTypes;
            this.RejectEndFrameForI2v = RejectEndFrameForI2v;
        }

        public string ModelLabel { get; }
        public string FileNamePrefix { get; }
        public IReadOnlyList<VideoMode> AllowedModes { get; }
        public long MaxSourceFrameBytes { get; }
        public IReadOnlyList<string> AllowedMimeTypes { get; }
        public bool RejectEndFrameForI2v { get; }
    }
}
```

Create `src/Rook/Services/Vision/Video/Fal/FalSourceFrameUrls.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSourceFrameUrls
    {
        public FalSourceFrameUrls(string startImageUrl, string? endImageUrl)
        {
            if (string.IsNullOrWhiteSpace(startImageUrl))
                throw new ArgumentException("Start image URL must be non-empty.", nameof(startImageUrl));

            StartImageUrl = startImageUrl;
            EndImageUrl = endImageUrl;
        }

        public string StartImageUrl { get; }
        public string? EndImageUrl { get; }
    }
}
```

Create `src/Rook/Services/Vision/Video/Fal/IFalSourceFrameTransport.cs`:

```csharp
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal interface IFalSourceFrameTransport
    {
        Task<(FalSourceFrameUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
            FalSourceFramePolicy policy,
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            string apiKey,
            CancellationToken ct);
    }
}
```

Create `src/Rook/Services/Vision/Video/Fal/FalSourceFrameTransport.cs` by moving the body of `FalSeedanceSourceTransport` and making these concrete changes:

```csharp
internal sealed class FalSourceFrameTransport : IFalSourceFrameTransport
{
    public const int SourceMediaExpirationSeconds = 3600;

    private readonly FalApiClient _client;

    public FalSourceFrameTransport(FalApiClient client)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
    }

    public async Task<(FalSourceFrameUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
        FalSourceFramePolicy policy,
        VideoGenerationRequest request,
        IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
        string apiKey,
        CancellationToken ct)
    {
        var validationError = ValidateRequest(policy, request, media);
        if (validationError is not null)
            return (null, validationError);

        var start = ResolveSourceFrame(policy, media, request.StartFrame!, "start_frame");
        if (start.Error is not null)
            return (null, start.Error);

        SourceFrame? end = null;
        if (request.Mode == VideoMode.Interp)
        {
            var resolvedEnd = ResolveSourceFrame(policy, media, request.EndFrame!, "end_frame");
            if (resolvedEnd.Error is not null)
                return (null, resolvedEnd.Error);

            end = resolvedEnd.Frame;
        }

        var startUpload = await TryUploadAsync(apiKey, policy, start.Frame!, "start_frame", ct)
            .ConfigureAwait(false);
        if (startUpload.Error is not null)
            return (null, startUpload.Error);

        string? endImageUrl = null;
        if (end is not null)
        {
            var endUpload = await TryUploadAsync(apiKey, policy, end, "end_frame", ct)
                .ConfigureAwait(false);
            if (endUpload.Error is not null)
                return (null, endUpload.Error);

            endImageUrl = endUpload.Url;
        }

        return (new FalSourceFrameUrls(startUpload.Url!, endImageUrl), null);
    }

    private async Task<(string? Url, GenerationError? Error)> TryUploadAsync(
        string apiKey,
        FalSourceFramePolicy policy,
        SourceFrame frame,
        string field,
        CancellationToken ct)
    {
        try
        {
            return (await UploadAsync(apiKey, policy, frame, ct).ConfigureAwait(false), null);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (FalApiException)
        {
            return (null, DependencyUnavailable(policy, field));
        }
        catch (TaskCanceledException)
        {
            return (null, DependencyUnavailable(policy, field));
        }
    }

    private static GenerationError? ValidateRequest(
        FalSourceFramePolicy policy,
        VideoGenerationRequest request,
        IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
    {
        if (policy is null)
            return InvalidSource("fal source frame transport requires a policy.", "policy");
        if (request is null)
            return InvalidSource($"fal {policy.ModelLabel} source transport requires a request.", "request");
        if (media is null)
            return InvalidSource($"fal {policy.ModelLabel} source transport requires resolved media.", "media");
        if (!policy.AllowedModes.Contains(request.Mode))
            return InvalidSource(
                $"fal {policy.ModelLabel} source transport only supports image-to-video and interpolation modes.",
                "mode");
        if (request.ReferenceFrames is { Count: > 0 })
            return InvalidSource(
                $"fal {policy.ModelLabel} source transport does not support reference frames.",
                "reference_frames");
        if (request.StartFrame is null)
            return InvalidSource(
                $"fal {policy.ModelLabel} source transport requires a start frame.",
                "start_frame");
        if (request.Mode == VideoMode.I2V && request.EndFrame is not null && policy.RejectEndFrameForI2v)
            return InvalidSource(
                $"fal {policy.ModelLabel} image-to-video source transport does not accept an end frame.",
                "end_frame");
        if (request.Mode == VideoMode.Interp && request.EndFrame is null)
            return InvalidSource(
                $"fal {policy.ModelLabel} interpolation source transport requires an end frame.",
                "end_frame");

        return null;
    }
}
```

Carry forward the existing helper methods from `FalSeedanceSourceTransport`, changing only:

- `MaxSourceFrameBytes` reads from `policy.MaxSourceFrameBytes`.
- MIME allowlist reads from `policy.AllowedMimeTypes`.
- error text uses `policy.ModelLabel`.
- `BuildFileName` accepts `policy` and returns `$"{policy.FileNamePrefix}-{Guid.NewGuid():N}.{ExtensionForMime(mimeType)}"`.
- `DependencyUnavailable` returns `new GenerationError(..., Message: $"fal {policy.ModelLabel} source upload failed.", Retryable: true, Field: field)`.
- `TryUploadAsync` returns `DependencyUnavailable(policy, "end_frame")` when end upload fails; keep validation errors as `InvalidRequest`.

Add these `using` directives to the new implementation:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
```

- [x] **Step 6: Migrate Seedance provider wiring to generalized transport**

In `FalVideoProvider.cs`, replace the Seedance-specific transport field:

```csharp
private readonly IFalSeedanceSourceTransport _seedanceSourceTransport;
```

with:

```csharp
private readonly IFalSourceFrameTransport _sourceFrameTransport;
```

Update the internal constructor signature:

```csharp
internal FalVideoProvider(
    Func<string?> apiKeyProvider,
    FalApiClient? client,
    IFalSourceFrameTransport? sourceFrameTransport)
```

and initialize:

```csharp
_sourceFrameTransport =
    sourceFrameTransport ?? new FalSourceFrameTransport(_client);
```

Add Seedance constants and policy near the existing endpoint constants:

```csharp
private const long SeedanceMaxSourceFrameBytes = 30L * 1024L * 1024L;

private static readonly FalSourceFramePolicy SeedanceSourceFramePolicy = new(
    ModelLabel: "Seedance",
    FileNamePrefix: "rook-seedance-source",
    AllowedModes: new[] { VideoMode.I2V, VideoMode.Interp },
    MaxSourceFrameBytes: SeedanceMaxSourceFrameBytes,
    AllowedMimeTypes: new[] { "image/png", "image/jpeg", "image/webp" },
    RejectEndFrameForI2v: true);
```

In `SubmitSeedanceAsync`, replace the old call with:

```csharp
var (sourceUrls, sourceError) =
    await _sourceFrameTransport.ResolveAndUploadAsync(
        SeedanceSourceFramePolicy,
        request,
        resolvedMedia,
        apiKey!,
        ct).ConfigureAwait(false);
```

Update `BuildSeedanceRequestJson` to accept `FalSourceFrameUrls` and map
`sourceUrls.StartImageUrl` to Seedance `image_url`:

```csharp
private static string BuildSeedanceRequestJson(
    VideoGenerationRequest request,
    FalSourceFrameUrls sourceUrls)
{
    var body = new JsonObject
    {
        ["prompt"] = request.Prompt,
        ["image_url"] = sourceUrls.StartImageUrl,
        ["resolution"] = request.Resolution,
        ["duration"] = request.DurationSeconds.ToString(CultureInfo.InvariantCulture),
        ["aspect_ratio"] = request.AspectRatio,
        ["generate_audio"] = false,
    };

    if (sourceUrls.EndImageUrl is not null)
        body["end_image_url"] = sourceUrls.EndImageUrl;

    if (request.Seed is int seed)
        body["seed"] = seed;

    return body.ToJsonString();
}
```

Replace `FalSeedanceSourceTransport.SourceMediaExpirationSeconds` references
with `FalSourceFrameTransport.SourceMediaExpirationSeconds`.

In `FalVideoProviderTests.cs`, replace fake transport type references:

```csharp
IFalSeedanceSourceTransport
FakeSeedanceSourceTransport
FalSeedanceSourceUrls
```

with:

```csharp
IFalSourceFrameTransport
FakeFalSourceFrameTransport
FalSourceFrameUrls
```

Update the fake class:

```csharp
private sealed class FakeFalSourceFrameTransport : IFalSourceFrameTransport
{
    public int Calls { get; private set; }
    public GenerationError? Error { get; set; }
    public FalSourceFrameUrls? Urls { get; set; }
    public string? LastApiKey { get; private set; }
    public FalSourceFramePolicy? LastPolicy { get; private set; }
    public CancellationToken LastCancellationToken { get; private set; }

    public Task<(FalSourceFrameUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
        FalSourceFramePolicy policy,
        VideoGenerationRequest request,
        IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
        string apiKey,
        CancellationToken ct)
    {
        Calls++;
        LastPolicy = policy;
        LastApiKey = apiKey;
        LastCancellationToken = ct;
        return Task.FromResult((Urls, Error));
    }
}
```

Update existing Seedance provider tests to instantiate `FalSourceFrameUrls`.

- [x] **Step 7: Delete old Seedance-named transport files**

Run:

```powershell
git rm src\Rook\Services\Vision\Video\Fal\FalSeedanceSourceTransport.cs `
       src\Rook\Services\Vision\Video\Fal\FalSeedanceSourceUrls.cs `
       src\Rook\Services\Vision\Video\Fal\IFalSeedanceSourceTransport.cs
```

- [x] **Step 8: Run transport and provider compile tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalSourceFrameTransportTests|Submit_seedance_i2v_uploads_source_then_posts_cdn_url_body_and_returns_request_id_only_handle|Submit_seedance_interp_includes_uploaded_end_image_url"
```

Expected: pass after adapting all renamed properties from `ImageUrl` to
`StartImageUrl` and migrating Seedance provider tests to the generalized fake.

- [x] **Step 9: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal `
        src\Rook.Tests\Services\Vision\Video\Fal\FalSourceFrameTransportTests.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalVideoProviderTests.cs
git commit -m "Generalize fal video source frame transport"
```

---

### Task 4: Add Kling Provider Submit And Lifecycle

**Files:**
- Modify: `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`

- [x] **Step 1: Add failing Kling submit tests**

Add this test:

```csharp
[Fact]
public async Task Submit_kling_i2v_uploads_source_then_posts_start_image_body_and_returns_request_id_only_handle()
{
    string? body = null;
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return Json(HttpStatusCode.OK, @"{
              ""request_id"": ""kling-123"",
              ""status"": ""IN_QUEUE""
            }");
        },
    };
    var sourceTransport = new FakeFalSourceFrameTransport
    {
        Urls = new FalSourceFrameUrls(
            "https://v3b.fal.media/files/start.png",
            endImageUrl: null),
    };
    var provider = Provider(handler, sourceTransport);
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);

    var outcome = await provider.SubmitAsync(
        KlingRequest(VideoMode.I2V, startFrame: start),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
        },
        CancellationToken.None);

    var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
    Assert.Equal("kling-123", queued.Handle.ProviderJobId);
    Assert.Null(queued.Handle.StatusUrl);
    Assert.Null(queued.Handle.ResponseUrl);
    Assert.Null(queued.Handle.CancelUrl);
    Assert.Null(queued.Handle.ProviderMetadata);

    Assert.Equal(1, sourceTransport.Calls);
    Assert.Equal("Kling", sourceTransport.LastPolicy!.ModelLabel);
    Assert.Equal("rook-kling-source", sourceTransport.LastPolicy.FileNamePrefix);
    Assert.Equal("test-fal-key", sourceTransport.LastApiKey);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(HttpMethod.Post, request.Method);
    Assert.Equal(
        "https://queue.fal.run/fal-ai/kling-video/v3/standard/image-to-video",
        request.RequestUri!.ToString());
    Assert.Equal(
        "{\"expiration_duration_seconds\":3600}",
        Assert.Single(request.Headers.GetValues("X-Fal-Object-Lifecycle-Preference")));
    Assert.Equal("0", Assert.Single(request.Headers.GetValues("X-Fal-Store-IO")));
    Assert.Equal("1", Assert.Single(request.Headers.GetValues("X-Fal-No-Retry")));

    var json = JsonNode.Parse(body!)!.AsObject();
    Assert.Equal("animate this source", json["prompt"]!.GetValue<string>());
    Assert.Equal("https://v3b.fal.media/files/start.png", json["start_image_url"]!.GetValue<string>());
    Assert.Equal("5", json["duration"]!.GetValue<string>());
    Assert.False(json["generate_audio"]!.GetValue<bool>());
    Assert.False(json.ContainsKey("end_image_url"));
    Assert.False(json.ContainsKey("resolution"));
    Assert.False(json.ContainsKey("aspect_ratio"));
    Assert.False(json.ContainsKey("multi_prompt"));
    Assert.False(json.ContainsKey("elements"));
    Assert.False(json.ContainsKey("negative_prompt"));
    Assert.False(json.ContainsKey("cfg_scale"));
    Assert.False(json.ContainsKey("seed"));
    Assert.DoesNotContain("data:", body!);
}
```

Add this Interp test:

```csharp
[Fact]
public async Task Submit_kling_interp_includes_uploaded_end_image_url()
{
    string? body = null;
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return Json(HttpStatusCode.OK, @"{
              ""request_id"": ""kling-123"",
              ""status"": ""IN_QUEUE""
            }");
        },
    };
    var sourceTransport = new FakeFalSourceFrameTransport
    {
        Urls = new FalSourceFrameUrls(
            "https://v3b.fal.media/files/start.png",
            "https://v3b.fal.media/files/end.jpg"),
    };
    var provider = Provider(handler, sourceTransport);
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
    var end = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.EndFrame);

    var outcome = await provider.SubmitAsync(
        KlingRequest(VideoMode.Interp, startFrame: start, endFrame: end),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
            [end] = new ResolvedMedia(JpegBytes(), "image/jpeg"),
        },
        CancellationToken.None);

    Assert.IsType<QueuedSubmitOutcome>(outcome);
    var json = JsonNode.Parse(body!)!.AsObject();
    Assert.Equal("https://v3b.fal.media/files/start.png", json["start_image_url"]!.GetValue<string>());
    Assert.Equal("https://v3b.fal.media/files/end.jpg", json["end_image_url"]!.GetValue<string>());
}
```

Add this no-submit-on-upload-failure test:

```csharp
[Fact]
public async Task Submit_kling_upload_failure_never_calls_queue_submit_and_error_is_sanitized()
{
    var handler = new TestHttpMessageHandler();
    var sourceTransport = new FakeFalSourceFrameTransport
    {
        Error = new GenerationError(
            GenerationErrorCode.DependencyUnavailable,
            "fal Kling source upload failed for request body.",
            Retryable: true,
            Field: "start_frame",
            ProviderErrorCode: "source_upload_failed",
            ProviderDetail: new Dictionary<string, JsonNode>
            {
                ["start_image_url"] = JsonValue.Create("https://v3b.fal.media/files/leak.png")!,
                ["upload_url"] = JsonValue.Create("https://uploads.example.test/source-token")!,
                ["body"] = JsonValue.Create("data:image/png;base64,abcd")!,
            }),
    };
    var provider = Provider(handler, sourceTransport);
    var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);

    var outcome = await provider.SubmitAsync(
        KlingRequest(VideoMode.I2V, startFrame: start),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [start] = new ResolvedMedia(PngBytes(), "image/png"),
        },
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
    Assert.True(failed.Error.Retryable);
    Assert.Equal("start_frame", failed.Error.Field);
    Assert.Equal("source_upload_failed", failed.Error.ProviderErrorCode);
    Assert.Null(failed.Error.ProviderDetail);
    Assert.Equal("fal Kling source upload failed.", failed.Error.Message);
    Assert.Empty(handler.Requests);
}
```

Add this helper:

```csharp
private static VideoGenerationRequest KlingRequest(
    VideoMode mode,
    MediaRef? startFrame = null,
    MediaRef? endFrame = null,
    int durationSeconds = 5,
    string? prompt = "animate this source") =>
    new(
        Model: FalVideoCapabilities.KlingV3StandardI2v,
        Mode: mode,
        DurationSeconds: durationSeconds,
        Resolution: "auto",
        AspectRatio: "auto",
        Prompt: prompt,
        StartFrame: startFrame,
        EndFrame: endFrame,
        ReferenceFrames: null,
        Seed: 77,
        Options: new FalVideoOptions(),
        NumberOfVideos: 1);
```

- [x] **Step 2: Add failing Kling lifecycle/result tests**

Add status, cancel, and result tests:

```csharp
[Fact]
public async Task Status_kling_reconstructs_status_url_from_model_and_request_id()
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => Json(HttpStatusCode.OK, @"{ ""status"": ""COMPLETED"" }"),
    };
    var provider = Provider(handler);

    var outcome = await provider.GetStatusAsync(
        FalVideoCapabilities.KlingV3StandardI2v,
        new ProviderJobHandle("kling-123"),
        CancellationToken.None);

    Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
    Assert.Equal(
        "https://queue.fal.run/fal-ai/kling-video/v3/standard/requests/kling-123/status",
        Assert.Single(handler.Requests).RequestUri!.ToString());
}

[Fact]
public async Task Cancel_kling_reconstructs_cancel_url_from_model_and_request_id()
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => Json(HttpStatusCode.Accepted, @"{ ""status"": ""CANCELLATION_REQUESTED"" }"),
    };
    var provider = Provider(handler);

    var outcome = await provider.CancelAsync(
        FalVideoCapabilities.KlingV3StandardI2v,
        new ProviderJobHandle("kling-123"),
        CancellationToken.None);

    Assert.IsType<CanceledOutcome>(outcome);
    var request = Assert.Single(handler.Requests);
    Assert.Equal(HttpMethod.Put, request.Method);
    Assert.Equal(
        "https://queue.fal.run/fal-ai/kling-video/v3/standard/requests/kling-123/cancel",
        request.RequestUri!.ToString());
}

[Fact]
public async Task Fetch_kling_reconstructs_response_url_and_drops_provider_metadata()
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => Json(HttpStatusCode.OK, @"{
          ""video"": {
            ""url"": ""https://v3.fal.media/files/kling.mp4"",
            ""content_type"": ""video/mp4"",
            ""duration"": 5
          },
          ""seed"": 42
        }"),
    };
    var provider = Provider(handler);

    var outcome = await provider.FetchResultAsync(
        FalVideoCapabilities.KlingV3StandardI2v,
        new ProviderJobHandle("kling-123"),
        CancellationToken.None);

    var success = Assert.IsType<SuccessResultOutcome>(outcome);
    var artifact = Assert.Single(success.Envelope.Artifacts);
    var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
    Assert.Equal("https://v3.fal.media/files/kling.mp4", remote.Url.ToString());
    Assert.Equal("video/mp4", artifact.DeclaredMimeType);
    Assert.Empty(artifact.ProviderMetadata);
    Assert.Empty(success.Envelope.EnvelopeMetadata);
    Assert.Equal(
        "https://queue.fal.run/fal-ai/kling-video/v3/standard/requests/kling-123",
        Assert.Single(handler.Requests).RequestUri!.ToString());
}
```

- [x] **Step 3: Run provider tests to verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoProviderTests"
```

Expected: test failures because Kling submit/lifecycle branches are not implemented.

- [x] **Step 4: Implement provider constants and Kling policy**

In `FalVideoProvider.cs`, add endpoints:

```csharp
private static readonly Uri KlingSubmitEndpoint =
    new("https://queue.fal.run/fal-ai/kling-video/v3/standard/image-to-video");
private static readonly Uri KlingLifecycleEndpoint =
    new("https://queue.fal.run/fal-ai/kling-video/v3/standard");
private const long KlingMaxSourceFrameBytes = 30L * 1024L * 1024L;
```

Add Kling policy beside the Seedance source-frame policy introduced in Task 3:

```csharp
private static readonly FalSourceFramePolicy KlingSourceFramePolicy = new(
    ModelLabel: "Kling",
    FileNamePrefix: "rook-kling-source",
    AllowedModes: new[] { VideoMode.I2V, VideoMode.Interp },
    MaxSourceFrameBytes: KlingMaxSourceFrameBytes,
    AllowedMimeTypes: new[] { "image/png", "image/jpeg", "image/webp" },
    RejectEndFrameForI2v: true);
```

- [x] **Step 5: Implement Kling submit branch**

In `SubmitAsync`, add:

```csharp
if (string.Equals(request.Model, FalVideoCapabilities.KlingV3StandardI2v, StringComparison.Ordinal))
    return await SubmitKlingAsync(request, resolvedMedia, ct).ConfigureAwait(false);
```

Add `SubmitKlingAsync` by copying `SubmitSeedanceAsync` and changing these specifics:

```csharp
private async Task<ProviderSubmitOutcome> SubmitKlingAsync(
    VideoGenerationRequest request,
    IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
    CancellationToken ct)
{
    if (request.Options is not FalVideoOptions)
        return FailedSubmit(
            GenerationErrorCode.InvalidRequest,
            $"fal video provider requires {nameof(FalVideoOptions)}; got " +
            $"{request.Options?.GetType().Name ?? "null"}.",
            nameof(VideoGenerationRequest.Options));

    if (request.Mode != VideoMode.I2V && request.Mode != VideoMode.Interp)
        return FailedSubmit(
            GenerationErrorCode.InvalidRequest,
            "fal Kling only supports image-to-video and interpolation modes.",
            nameof(VideoGenerationRequest.Mode));

    if (string.IsNullOrWhiteSpace(request.Prompt))
        return FailedSubmit(
            GenerationErrorCode.InvalidRequest,
            "fal Kling requires prompt.",
            nameof(VideoGenerationRequest.Prompt));

    if (request.NumberOfVideos != 1)
        return FailedSubmit(
            GenerationErrorCode.InvalidRequest,
            "fal Kling supports exactly one video per request.",
            nameof(VideoGenerationRequest.NumberOfVideos));

    var apiKey = _apiKeyProvider();
    if (string.IsNullOrWhiteSpace(apiKey))
        return FailedSubmit(
            GenerationErrorCode.DependencyUnavailable,
            "fal API key is not configured.");

    var (sourceUrls, sourceError) =
        await _sourceFrameTransport.ResolveAndUploadAsync(
            KlingSourceFramePolicy,
            request,
            resolvedMedia,
            apiKey!,
            ct).ConfigureAwait(false);
    if (sourceError is not null)
        return new FailedSubmitOutcome(SanitizeSourceError(sourceError, "Kling"));
    if (sourceUrls is null)
        return FailedSubmit(
            GenerationErrorCode.ExecutionFailed,
            "fal Kling source upload did not return source URLs.");

    FalHttpResponse response;
    try
    {
        response = await PostKlingSubmitWithConnectRetryAsync(
            apiKey!,
            BuildKlingRequestJson(request, sourceUrls),
            ct).ConfigureAwait(false);
    }
    catch (OperationCanceledException) when (ct.IsCancellationRequested)
    {
        throw;
    }
    catch (TaskCanceledException)
    {
        return FailedSubmit(
            GenerationErrorCode.DependencyUnavailable,
            "fal video submit timed out.",
            retryable: true);
    }
    catch (HttpRequestException)
    {
        return FailedSubmit(
            GenerationErrorCode.DependencyUnavailable,
            "fal video submit failed due to a transport error.",
            retryable: true);
    }

    if (!response.IsSuccessStatusCode)
        return new FailedSubmitOutcome(SanitizeProviderDetail(FalErrorMapper.MapHttpFailure(response)));

    try
    {
        var root = JsonNode.Parse(response.Body) as JsonObject;
        if (root is null)
            return FailedSubmit(
                GenerationErrorCode.ExecutionFailed,
                "fal submit response was empty.");

        if (!TryGetString(root, "request_id", out var requestId))
            return FailedSubmit(
                GenerationErrorCode.ExecutionFailed,
                "fal submit response did not contain request_id.",
                "request_id");

        return new QueuedSubmitOutcome(new ProviderJobHandle(requestId!));
    }
    catch (JsonException)
    {
        return FailedSubmit(
            GenerationErrorCode.ExecutionFailed,
            "fal submit response was not valid JSON.");
    }
}
```

Add submit helper:

```csharp
private async Task<FalHttpResponse> PostKlingSubmitWithConnectRetryAsync(
    string apiKey,
    string bodyJson,
    CancellationToken ct)
{
    try
    {
        return await _client.PostJsonAsync(
            apiKey,
            KlingSubmitEndpoint,
            bodyJson,
            FalJsonPlatformHeaders.ForFalVideoSourceFrameSubmit(
                FalSourceFrameTransport.SourceMediaExpirationSeconds,
                disableStoreIo: true,
                disableFalRetry: true),
            ct).ConfigureAwait(false);
    }
    catch (HttpRequestException ex) when (IsConnectionEstablishmentFailure(ex))
    {
        return await _client.PostJsonAsync(
            apiKey,
            KlingSubmitEndpoint,
            bodyJson,
            FalJsonPlatformHeaders.ForFalVideoSourceFrameSubmit(
                FalSourceFrameTransport.SourceMediaExpirationSeconds,
                disableStoreIo: true,
                disableFalRetry: true),
            ct).ConfigureAwait(false);
    }
}
```

Rename `FalJsonPlatformHeaders.ForSeedanceSubmit` to
`ForFalVideoSourceFrameSubmit` in this task. Both Seedance and Kling submit
paths must use the renamed helper because both submit volatile fal
source-frame CDN URLs.

Add request JSON:

```csharp
private static string BuildKlingRequestJson(
    VideoGenerationRequest request,
    FalSourceFrameUrls sourceUrls)
{
    var body = new JsonObject
    {
        ["prompt"] = request.Prompt,
        ["start_image_url"] = sourceUrls.StartImageUrl,
        ["duration"] = request.DurationSeconds.ToString(CultureInfo.InvariantCulture),
        ["generate_audio"] = false,
    };

    if (sourceUrls.EndImageUrl is not null)
        body["end_image_url"] = sourceUrls.EndImageUrl;

    return body.ToJsonString();
}
```

- [x] **Step 6: Implement Kling lifecycle and result branches**

In `GetStatusAsync(string modelId, ...)`, add Kling:

```csharp
if (string.Equals(modelId, FalVideoCapabilities.KlingV3StandardI2v, StringComparison.Ordinal))
    return GetKlingStatusAsync(handle, ct);
```

In `CancelAsync(string modelId, ...)`, add Kling:

```csharp
if (string.Equals(modelId, FalVideoCapabilities.KlingV3StandardI2v, StringComparison.Ordinal))
    return CancelKlingAsync(handle, ct);
```

In `FetchResultAsync(string modelId, ...)`, add Kling:

```csharp
if (string.Equals(modelId, FalVideoCapabilities.KlingV3StandardI2v, StringComparison.Ordinal))
    return FetchKlingResultAsync(handle, ct);
```

Add methods that mirror Seedance but use `KlingLifecycleEndpoint` and `ParsePrivateFalVideoFetchResult`:

```csharp
private Task<ProviderStatusOutcome> GetKlingStatusAsync(
    ProviderJobHandle handle,
    CancellationToken ct) =>
    GetModelEndpointStatusAsync(KlingLifecycleEndpoint, handle, ct);

private Task<ProviderCancelOutcome> CancelKlingAsync(
    ProviderJobHandle handle,
    CancellationToken ct) =>
    CancelModelEndpointAsync(KlingLifecycleEndpoint, handle, ct);

private Task<ProviderResultOutcome> FetchKlingResultAsync(
    ProviderJobHandle handle,
    CancellationToken ct) =>
    FetchModelEndpointResultAsync(KlingLifecycleEndpoint, handle, ct);
```

Extract common `GetModelEndpointStatusAsync`, `CancelModelEndpointAsync`, and
`FetchModelEndpointResultAsync` helpers in this task rather than duplicating
Seedance code. These helpers must:

- validate `handle` is not null;
- reconstruct URL from `endpoint` and `handle.ProviderJobId`;
- call existing generic HTTP methods;
- sanitize provider detail on failures;
- return request-id-only handles on complete status;
- parse result with no provider metadata.

Rename `ParseSeedanceFetchResult` to `ParsePrivateFalVideoFetchResult` and use it for Seedance and Kling.

- [x] **Step 7: Run provider tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoProviderTests"
```

Expected: pass.

- [x] **Step 8: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal\FalVideoProvider.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalVideoProviderTests.cs
git commit -m "Add Kling fal video provider lifecycle"
```

---

### Task 5: Privacy, Boundary, And Focused Verification

**Files:**
- Modify: `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`

- [x] **Step 1: Add handler estimate rejection tests for Kling out-of-range durations**

In `VideoOpHandlerTests.cs`, add:

```csharp
[Theory]
[InlineData(2)]
[InlineData(16)]
public void Estimate_kling_rejects_duration_outside_3_to_15(int duration)
{
    var handler = NewHandler(registry: RegistryWithVeoAndFal());
    var startId = SampleArtifactId;

    var resp = handler.DispatchOffUi($$"""
        {
          "op": "estimate_video_job",
          "model": "{{FalVideoCapabilities.KlingV3StandardI2v}}",
          "mode": "i2v",
          "duration_seconds": {{duration}},
          "resolution": "auto",
          "aspect_ratio": "auto",
          "prompt": "animate this source",
          "start_frame": {
            "kind": "artifact_id",
            "artifact_id": "{{startId:D}}",
            "role": "start_frame"
          },
          "options": {},
          "number_of_videos": 1
        }
        """);

    AssertFail(resp, GenerationErrorCode.UnsupportedMedia, expectedHttp: 400);
    AssertMessageContains(resp, "duration");
    AssertNoFalSourceTransportMarkers(JsonSerializer.Serialize(resp.Data));
}
```

- [x] **Step 2: Add provider-level no-leak assertions for Kling result parsing**

In `FalVideoProviderTests.cs`, extend Kling result tests to assert:

```csharp
Assert.Empty(artifact.ProviderMetadata);
Assert.Empty(success.Envelope.EnvelopeMetadata);
Assert.DoesNotContain("fal.media", string.Join("|", artifact.ProviderMetadata.Keys));
```

Keep the remote artifact body URL because `VideoJobManager` needs it transiently to materialize the video. The no-leak requirement is durable state and metadata, not the in-memory remote fetch body.

- [x] **Step 3: Run focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalVideoProviderRegistrationTests|FalKlingV3StandardI2vPricingModelTests|FalVideoOptionsCodecTests|FalSourceFrameTransportTests|FalVideoProviderTests|VideoOpHandlerTests"
```

Expected: pass.

- [x] **Step 4: Run boundary scans**

Run:

```powershell
rg -n "KlingV3StandardI2v|kling-video|start_image_url|FalSourceFrameTransport|FalSourceFramePolicy|fal.media|queue.fal.run" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected: no matches in `src/RookNative`, `mcp_server`, or `src/Rook\InternalBridge`. If `rg` exits `1` due to no matches, that is success.

Run:

```powershell
rg -n "FalSeedanceSourceTransport|IFalSeedanceSourceTransport|FalSeedanceSourceUrls" src\Rook src\Rook.Tests
```

Expected: no matches.

- [x] **Step 5: Run managed build**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 -c Release
```

Expected: build succeeds. Existing warnings are acceptable only if unrelated and already present.

- [x] **Step 6: Commit**

```powershell
git add src\Rook.Tests
git commit -m "Cover Kling video privacy boundaries"
```

If Task 5 only changes tests already committed in Task 4, skip this commit and note that no new files were staged.

---

### Task 6: Final Verification And Manual Smoke Prep

**Files:**
- No code files unless verification exposes a defect.

- [x] **Step 1: Run the full managed suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: all tests pass.

- [x] **Step 2: Run final diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: `git diff --check` has no whitespace errors. Status is clean or only contains intended verification notes that must be committed or removed.

- [x] **Step 3: Build deployable managed companion**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 -c Release
```

Expected: succeeds.

- [x] **Step 4: Optional local deploy for Rhino smoke**

Only run after Rhino is closed:

```powershell
Copy-Item -Force src\Rook\bin\Release\net7.0\Rook.rhp "C:\Users\aryan\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.rhp"
Copy-Item -Force src\Rook\bin\Release\net7.0\Rook.deps.json "C:\Users\aryan\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.deps.json"
Copy-Item -Force src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json "C:\Users\aryan\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.runtimeconfig.json"
```

Expected: files copy successfully. Do not run if Rhino has the plugin loaded.

- [ ] **Step 5: Manual smoke checklist**

In Rhino:

1. Start Rhino fresh.
2. Open Rook Vision.
3. Select Kling v3 Standard Image to Video.
4. Use I2V with a non-sensitive source artifact, prompt, and duration `3` or `5`.
5. Confirm job completes and materializes a local `generated_video` artifact.
6. Scan the latest ledger and artifact manifest for forbidden strings:

```powershell
rg -n "fal\.media|queue\.fal\.run|rest\.fal\.ai|api\.fal\.ai|start_image_url|end_image_url|image_url|data:image|status_url|response_url|cancel_url" "$env:APPDATA\Rook"
```

Expected: no forbidden provider/source URL strings in durable Rook ledger or artifact metadata. Ignore unrelated logs only after inspecting the exact file path.

- [x] **Step 6: Final commit if verification fixes were needed**

If Task 6 exposed a defect, return to the task that owns that defect and make
the smallest code/test fix there. Then commit the exact files changed by that
fix with a message naming the defect, for example:

```powershell
git add src\Rook\Services\Vision\Video\Fal\FalVideoProvider.cs `
        src\Rook.Tests\Services\Vision\Video\Fal\FalVideoProviderTests.cs
git commit -m "Fix Kling video verification failure"
```

If no edits were needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- One Kling model row: Task 1.
- I2V/Interp only and T2V rejection: Tasks 1, 4, 5.
- Prompt required and unknown provider options rejected: Task 2.
- Duration `3` through `15`, rejection of `2` and `16`: Tasks 1 and 5.
- `auto` resolution/aspect ratio and no provider fields: Tasks 1 and 4.
- `generate_audio: false`: Task 4.
- Queue submit privacy headers and no fal platform retry duplication: Task 4.
- Exact submit/status/result/cancel endpoint strategy: Task 4.
- Provider-private fal video source-frame transport with per-model policy: Task 3.
- Provisional per-model byte cap and MIME policy: Task 3.
- No partial URLs on end-upload failure: Task 3.
- No queue submit on upload failure: Task 4.
- Request-id-only durable handles: Task 4.
- Result parser accepts one `video.url` and drops provider metadata: Task 4.
- Pricing at `$0.084/output_second`: Task 1.
- Boundary scans and privacy checks: Task 5 and Task 6.

Placeholder scan:

- No `TBD`, `TODO`, or unspecified implementation steps.
- Each code-changing task names exact files and includes concrete code snippets.
- Verification commands have expected outcomes.

Type consistency:

- Transport type names are `IFalSourceFrameTransport`, `FalSourceFrameTransport`, `FalSourceFramePolicy`, and `FalSourceFrameUrls`.
- URL value properties are `StartImageUrl` and `EndImageUrl`.
- Kling model id constant is `FalVideoCapabilities.KlingV3StandardI2v`.
- Pricing type is `FalKlingV3StandardI2vPricingModel`.
