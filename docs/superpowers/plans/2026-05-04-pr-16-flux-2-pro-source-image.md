# PR-16 Flux 2 Pro Source-Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Replicate `black-forest-labs/flux-2-pro` as a curated async source-image RookVision model using exactly one existing `input_image_path`, bounded data URI transport, and no new public/native/MCP exposure.

**Architecture:** Keep implementation inside the managed Vision image stack. Extend the existing Replicate image provider with model-specific capabilities and request builders: Schnell remains prompt-only, Flux 2 Pro requires one primary `ImageMediaRoles.InputImage` and sends `input_images: [data-uri]`. Update the Vision frontend so async jobs can carry source images from Generate and Studio while preserving PR-15 operational-only durability.

**Tech Stack:** C#/.NET 7 managed companion, xUnit tests, RookVision WebView JavaScript resource tests, fake `HttpMessageHandler` provider tests, JSONL image job ledger tests, no live provider calls in automated tests.

---

## Files And Responsibilities

Modify:

- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
  Add Flux 2 Pro constants and curated source-image-only capability.

- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
  Expose Flux 2 Pro through the Replicate image registration with existing async submission mode and pricing model.

- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs`
  Validate Replicate requests by model/capability without hardcoding Schnell-only messages.

- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
  Branch by model id, keep Schnell schema unchanged, add Flux 2 Pro source-image validation and data URI request JSON.

- `src/Rook/Handlers/VisionHandler.cs`
  Normalize resolved media MIME for `input_image_path` and `reference_image_paths` instead of hardcoding `"image/png"`.

- `src/Rook/UI/Vision/Resources/app.js`
  Route async source-image models through `image_generate_start` with `input_image_path`; route Studio Flux 2 Pro through async status/result handling; keep Schnell prompt-only source-free.

Create:

- `src/Rook/Services/Vision/Image/ImageMimeDetector.cs`
  Shared MIME detector for PNG/JPEG/WebP bytes plus extension fallback used by `VisionHandler` and Flux 2 Pro validation.

- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageSourcePayload.cs`
  Internal helper that selects exactly one primary input media item, validates size/MIME, and constructs an in-memory data URI.

- `src/Rook.Tests/Services/Vision/Image/ImageMimeDetectorTests.cs`
  Focused byte-signature tests for PNG/JPEG/WebP detection and unsupported bytes.

Modify tests:

- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`
- `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageJobManagerTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs`

Do not modify:

- `src/RookNative/**`
- `mcp_server/**`
- `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- image job durable record fields

---

## Task 1: Add Flux 2 Pro Catalog Capability

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`

- [ ] **Step 1: Update the registration test to expect Schnell plus Flux 2 Pro**

Replace `Registration_exposes_only_flux_schnell_model` with:

```csharp
[Fact]
public void Registration_exposes_curated_replicate_models()
{
    var registration = new ReplicateImageProviderRegistration(
        new FakeImageProvider());

    Assert.Equal("replicate", registration.ProviderName);

    var models = registration.Models;
    Assert.Equal(2, models.Count);

    var schnell = models[ReplicateImageCapabilities.FluxSchnell];
    Assert.Equal(ReplicateImageCapabilities.FluxSchnell, schnell.Capability.Id);
    Assert.Equal("FLUX.1 Schnell", schnell.Capability.Name);
    Assert.Equal("available", schnell.Capability.Status);
    Assert.Equal(new[] { "1K" }, schnell.Capability.Resolutions);
    Assert.Equal(new[] { "1:1", "4:3", "3:4", "16:9", "9:16" }, schnell.Capability.AspectRatios);
    Assert.Equal(0, schnell.Capability.MaxReferenceImages);
    Assert.True(schnell.Capability.SupportsTextToImage);
    Assert.False(schnell.Capability.SupportsImageToImage);
    Assert.IsType<ReplicateImagePricingModel>(schnell.PricingModel);

    var flux2 = models[ReplicateImageCapabilities.Flux2Pro];
    Assert.Equal(ReplicateImageCapabilities.Flux2Pro, flux2.Capability.Id);
    Assert.Equal("FLUX.2 Pro", flux2.Capability.Name);
    Assert.Equal("available", flux2.Capability.Status);
    Assert.Equal(new[] { "1MP" }, flux2.Capability.Resolutions);
    Assert.Equal(new[] { "match_input_image" }, flux2.Capability.AspectRatios);
    Assert.Equal(0, flux2.Capability.MaxReferenceImages);
    Assert.False(flux2.Capability.SupportsTextToImage);
    Assert.True(flux2.Capability.SupportsImageToImage);
    Assert.IsType<ReplicateImagePricingModel>(flux2.PricingModel);
}
```

Replace `Injected_registry_resolves_only_replicate_flux_schnell` with:

```csharp
[Fact]
public void Injected_registry_resolves_curated_replicate_models()
{
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new ReplicateImageProviderRegistration(new FakeImageProvider()),
    });

    Assert.True(registry.TryResolve(ReplicateImageCapabilities.FluxSchnell, out var schnell));
    Assert.Equal(ReplicateImageCapabilities.FluxSchnell, schnell.ModelId);
    Assert.Equal("replicate", schnell.ProviderName);

    Assert.True(registry.TryResolve(ReplicateImageCapabilities.Flux2Pro, out var flux2));
    Assert.Equal(ReplicateImageCapabilities.Flux2Pro, flux2.ModelId);
    Assert.Equal("replicate", flux2.ProviderName);
    Assert.True(flux2.Capability.SupportsImageToImage);
    Assert.False(flux2.Capability.SupportsTextToImage);

    Assert.False(registry.TryResolve("replicate/other-model", out _));

    var all = registry.EnumerateAllModels()
        .OrderBy(d => d.ModelId, StringComparer.Ordinal)
        .ToArray();
    Assert.Equal(2, all.Length);
    Assert.Contains(all, d => d.ModelId == ReplicateImageCapabilities.FluxSchnell);
    Assert.Contains(all, d => d.ModelId == ReplicateImageCapabilities.Flux2Pro);
}
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderRegistrationTests"
```

Expected: fail because `ReplicateImageCapabilities.Flux2Pro` has not been added and registration still exposes one model.

- [ ] **Step 3: Add Flux 2 Pro capability**

In `ReplicateImageCapabilities.cs`, add:

```csharp
public const string Flux2Pro = "black-forest-labs/flux-2-pro";
```

Add the model entry:

```csharp
[Flux2Pro] = new ImageCapability(
    Id: Flux2Pro,
    Name: "FLUX.2 Pro",
    Status: "available",
    Resolutions: new[] { "1MP" },
    AspectRatios: new[] { "match_input_image" },
    MaxReferenceImages: 0,
    SupportsImageToImage: true,
    SupportsTextToImage: false),
```

Keep:

```csharp
public const string DefaultModel = FluxSchnell;
```

- [ ] **Step 4: Register Flux 2 Pro**

In `ReplicateImageProviderRegistration.cs`, add:

```csharp
[ReplicateImageCapabilities.Flux2Pro] = (
    ReplicateImageCapabilities.Models[ReplicateImageCapabilities.Flux2Pro],
    new ReplicateImagePricingModel()),
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderRegistrationTests"
```

Expected: all `ReplicateImageProviderRegistrationTests` pass.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Replicate\ReplicateImageCapabilities.cs src\Rook\Services\Vision\Image\Replicate\ReplicateImageProviderRegistration.cs src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageProviderRegistrationTests.cs
git commit -m "feat(vision): add Flux 2 Pro image catalog entry"
```

---

## Task 2: Add Shared Image MIME Detection

**Files:**
- Create: `src/Rook/Services/Vision/Image/ImageMimeDetector.cs`
- Create: `src/Rook.Tests/Services/Vision/Image/ImageMimeDetectorTests.cs`
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Modify: existing tests that use minimal PNG bytes if strict sniffing makes them fail

- [ ] **Step 1: Write MIME detector tests**

Create `src/Rook.Tests/Services/Vision/Image/ImageMimeDetectorTests.cs`:

```csharp
using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageMimeDetectorTests
    {
        [Fact]
        public void Detects_png_signature()
        {
            var bytes = new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 };

            Assert.Equal("image/png", ImageMimeDetector.Detect(bytes, "source.png"));
        }

        [Fact]
        public void Detects_jpeg_signature()
        {
            var bytes = new byte[] { 0xFF, 0xD8, 0xFF, 0xE0, 0x00 };

            Assert.Equal("image/jpeg", ImageMimeDetector.Detect(bytes, "source.jpg"));
        }

        [Fact]
        public void Detects_webp_signature()
        {
            var bytes = new byte[]
            {
                0x52, 0x49, 0x46, 0x46, 0x10, 0x00, 0x00, 0x00,
                0x57, 0x45, 0x42, 0x50
            };

            Assert.Equal("image/webp", ImageMimeDetector.Detect(bytes, "source.webp"));
        }

        [Theory]
        [InlineData("source.png")]
        [InlineData("source.jpg")]
        [InlineData("source.webp")]
        public void Returns_octet_stream_when_bytes_do_not_match_supported_image(string path)
        {
            Assert.Equal(
                "application/octet-stream",
                ImageMimeDetector.Detect(new byte[] { 1, 2, 3, 4 }, path));
        }

        [Theory]
        [InlineData(".png", "image/png")]
        [InlineData(".jpg", "image/jpeg")]
        [InlineData(".jpeg", "image/jpeg")]
        [InlineData(".webp", "image/webp")]
        [InlineData(".bmp", "image/bmp")]
        [InlineData(".gif", "image/gif")]
        [InlineData(".bin", "application/octet-stream")]
        public void FromExtension_matches_existing_picker_contract(string ext, string expected)
        {
            Assert.Equal(expected, ImageMimeDetector.FromExtension("x" + ext));
        }
    }
}
```

- [ ] **Step 2: Run the MIME detector tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageMimeDetectorTests"
```

Expected: fail because `ImageMimeDetector` has not been added.

- [ ] **Step 3: Add the shared detector**

Create `src/Rook/Services/Vision/Image/ImageMimeDetector.cs`:

```csharp
using System;
using System.IO;

namespace Rook.Services.Vision.Image
{
    internal static class ImageMimeDetector
    {
        public static string Detect(byte[] bytes, string? path = null)
        {
            if (bytes is null || bytes.Length == 0)
                return "application/octet-stream";

            if (bytes.Length >= 8
                && bytes[0] == 0x89
                && bytes[1] == 0x50
                && bytes[2] == 0x4E
                && bytes[3] == 0x47
                && bytes[4] == 0x0D
                && bytes[5] == 0x0A
                && bytes[6] == 0x1A
                && bytes[7] == 0x0A)
            {
                return "image/png";
            }

            if (bytes.Length >= 3
                && bytes[0] == 0xFF
                && bytes[1] == 0xD8
                && bytes[2] == 0xFF)
            {
                return "image/jpeg";
            }

            if (bytes.Length >= 12
                && bytes[0] == 0x52
                && bytes[1] == 0x49
                && bytes[2] == 0x46
                && bytes[3] == 0x46
                && bytes[8] == 0x57
                && bytes[9] == 0x45
                && bytes[10] == 0x42
                && bytes[11] == 0x50)
            {
                return "image/webp";
            }

            return "application/octet-stream";
        }

        public static string FromExtension(string path)
        {
            var ext = Path.GetExtension(path ?? string.Empty).ToLowerInvariant();
            return ext switch
            {
                ".png" => "image/png",
                ".jpg" or ".jpeg" => "image/jpeg",
                ".webp" => "image/webp",
                ".gif" => "image/gif",
                ".bmp" => "image/bmp",
                _ => "application/octet-stream",
            };
        }

        public static bool IsFlux2SupportedMime(string mimeType) =>
            string.Equals(mimeType, "image/png", StringComparison.Ordinal)
            || string.Equals(mimeType, "image/jpeg", StringComparison.Ordinal)
            || string.Equals(mimeType, "image/webp", StringComparison.Ordinal);
    }
}
```

- [ ] **Step 4: Update `VisionHandler` to use the detector for resolved media**

Add:

```csharp
using Rook.Services.Vision.Image;
```

where the other Vision image namespaces are imported.

Replace the private `GuessImageMimeFromExtension` body with:

```csharp
private static string GuessImageMimeFromExtension(string path)
    => ImageMimeDetector.FromExtension(path);
```

When reading reference images, replace:

```csharp
resolvedMedia[mediaRef] = new ResolvedMedia(
    File.ReadAllBytes(path),
    "image/png");
```

with:

```csharp
var bytes = File.ReadAllBytes(path);
resolvedMedia[mediaRef] = new ResolvedMedia(
    bytes,
    ImageMimeDetector.Detect(bytes, path));
```

When reading the primary input image, replace:

```csharp
var inputBytes = File.ReadAllBytes(inputImagePath);
resolvedMedia[inputRef] = new ResolvedMedia(inputBytes, "image/png");
```

with:

```csharp
var inputBytes = File.ReadAllBytes(inputImagePath);
resolvedMedia[inputRef] = new ResolvedMedia(
    inputBytes,
    ImageMimeDetector.Detect(inputBytes, inputImagePath));
```

- [ ] **Step 5: Update tests that create fake PNG files**

Any test that writes only:

```csharp
new byte[] { 0x89, 0x50, 0x4E, 0x47 }
```

and expects a valid image source should write:

```csharp
new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 }
```

Use `rg "0x89, 0x50, 0x4E, 0x47" src\Rook.Tests` to find these fixtures.

- [ ] **Step 6: Run focused handler and MIME tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageMimeDetectorTests|ImageJobOpHandlerTests|VisionHandlerTests"
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\ImageMimeDetector.cs src\Rook\Handlers\VisionHandler.cs src\Rook.Tests\Services\Vision\Image\ImageMimeDetectorTests.cs src\Rook.Tests
git commit -m "feat(vision): normalize source image MIME detection"
```

---

## Task 3: Add Flux 2 Pro Provider Validation And Data URI Helper

**Files:**
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageSourcePayload.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`

- [ ] **Step 1: Add provider tests for Flux 2 Pro fail-closed validation**

In `ReplicateImageProviderTests.cs`, add tests before `SubmitAsync_posts_official_model_endpoint_and_exact_body`:

```csharp
[Fact]
public async Task SubmitAsync_flux2_prompt_only_fails_before_http_call()
{
    var handler = new TestHttpMessageHandler();
    var provider = Provider("r8-test-token", handler);

    var outcome = await provider.SubmitAsync(
        Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
        EmptyMedia(),
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
    Assert.Equal("input_image_path", failed.Error.Field);
    Assert.Contains("requires exactly one source image", failed.Error.Message);
    Assert.Empty(handler.Requests);
}

[Fact]
public async Task SubmitAsync_flux2_rejects_reference_image_roles_before_http_call()
{
    var handler = new TestHttpMessageHandler();
    var provider = Provider("r8-test-token", handler);
    var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);

    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [input] = PngMedia(),
        [MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage)] = PngMedia(),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
        media,
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
    Assert.Equal("reference_image_paths", failed.Error.Field);
    Assert.Empty(handler.Requests);
}

[Theory]
[InlineData("image/gif")]
[InlineData("application/octet-stream")]
public async Task SubmitAsync_flux2_rejects_unsupported_mime_before_http_call(string mimeType)
{
    var handler = new TestHttpMessageHandler();
    var provider = Provider("r8-test-token", handler);
    var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [input] = new ResolvedMedia(
            new byte[] { 0x47, 0x49, 0x46, 0x38 },
            mimeType),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
        media,
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
    Assert.Equal("input_image_path", failed.Error.Field);
    Assert.Contains("PNG, JPEG, or WebP", failed.Error.Message);
    Assert.Empty(handler.Requests);
}

[Fact]
public async Task SubmitAsync_flux2_rejects_oversized_source_before_http_call()
{
    var handler = new TestHttpMessageHandler();
    var provider = Provider("r8-test-token", handler);
    var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
    var bytes = new byte[1024 * 1024 + 1];
    bytes[0] = 0x89;
    bytes[1] = 0x50;
    bytes[2] = 0x4E;
    bytes[3] = 0x47;
    bytes[4] = 0x0D;
    bytes[5] = 0x0A;
    bytes[6] = 0x1A;
    bytes[7] = 0x0A;
    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [input] = new ResolvedMedia(bytes, "image/png"),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
        media,
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
    Assert.Equal("input_image_path", failed.Error.Field);
    Assert.Contains("too large", failed.Error.Message);
    Assert.Empty(handler.Requests);
}
```

Add helper methods near `EmptyMedia()`:

```csharp
private static ResolvedMedia PngMedia() =>
    new(
        new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 },
        "image/png");
```

Also update the existing `Request` helper signature to accept `resolution`:

```csharp
private static ImageGenerationRequest Request(
    string model = ReplicateImageCapabilities.FluxSchnell,
    string aspectRatio = "1:1",
    string resolution = "1K",
    ProviderOptions? options = null,
    System.Collections.Generic.IReadOnlyList<MediaRef>? referenceImages = null) =>
    new(
        Model: model,
        Prompt: "sunlit massing study",
        Resolution: resolution,
        AspectRatio: aspectRatio,
        NumberOfImages: 1,
        ReferenceImages: referenceImages,
        Options: options ?? new ReplicateImageOptions());
```

- [ ] **Step 2: Run provider tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderTests"
```

Expected: fail because Flux 2 Pro is not yet accepted and payload validation has not been added.

- [ ] **Step 3: Add the source payload helper**

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImageSourcePayload.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateImageSourcePayload
    {
        public const long MaxRawBytes = 1024 * 1024;

        private ReplicateImageSourcePayload(string mimeType, string dataUri)
        {
            MimeType = mimeType;
            DataUri = dataUri;
        }

        public string MimeType { get; }
        public string DataUri { get; }

        public static (ReplicateImageSourcePayload? Payload, GenerationError? Error) FromResolvedMedia(
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (media is null)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro requires exactly one source image.",
                    "input_image_path"));
            }

            if (media.Keys.Any(r => string.Equals(
                    r.Role,
                    ImageMediaRoles.ReferenceImage,
                    StringComparison.Ordinal)))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro does not support reference_image_paths in this release.",
                    "reference_image_paths"));
            }

            var inputs = media
                .Where(kvp => string.Equals(
                    kvp.Key.Role,
                    ImageMediaRoles.InputImage,
                    StringComparison.Ordinal))
                .ToArray();

            if (inputs.Length != 1)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro requires exactly one source image.",
                    "input_image_path"));
            }

            var resolved = inputs[0].Value;
            if (resolved.Bytes is null || resolved.Bytes.Length == 0)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image is empty.",
                    "input_image_path"));
            }

            if (resolved.Bytes.LongLength > MaxRawBytes)
            {
                return (null, InvalidSource(
                    "Source image is too large for Flux 2 Pro data URI upload; capture a smaller viewport or lower resolution.",
                    "input_image_path"));
            }

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ImageMimeDetector.IsFlux2SupportedMime(detectedMime))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image must be PNG, JPEG, or WebP.",
                    "input_image_path"));
            }

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image MIME does not match its bytes.",
                    "input_image_path"));
            }

            var dataUri = $"data:{detectedMime};base64,{Convert.ToBase64String(resolved.Bytes)}";
            return (new ReplicateImageSourcePayload(detectedMime, dataUri), null);
        }

        private static GenerationError InvalidSource(string message, string field) =>
            new(
                Code: GenerationErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);
    }
}
```

- [ ] **Step 4: Update provider model validation to allow Flux 2 Pro**

In `ReplicateImageProvider.SubmitAsync`, replace the Schnell-only model check:

```csharp
if (!string.Equals(
        request.Model,
        ReplicateImageCapabilities.FluxSchnell,
        StringComparison.Ordinal))
{
    return FailedSubmit(
        GenerationErrorCode.InvalidRequest,
        $"Unknown Replicate image model '{request.Model}'.",
        "model");
}
```

with:

```csharp
if (!ReplicateImageCapabilities.Models.TryGetValue(request.Model, out var capability))
{
    return FailedSubmit(
        GenerationErrorCode.InvalidRequest,
        $"Unknown Replicate image model '{request.Model}'.",
        "model");
}
```

Replace:

```csharp
ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell]);
```

with:

```csharp
capability);
```

Do not wire the payload helper into request JSON yet in this task; the new Flux 2 submit success test comes in Task 4.

- [ ] **Step 5: Validate Flux 2 Pro source payload before token lookup and HTTP**

In `ReplicateImageProvider.SubmitAsync`, after options validation succeeds and before API token lookup, add:

```csharp
ReplicateImageSourcePayload? sourcePayload = null;
if (string.Equals(request.Model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal))
{
    var payload = ReplicateImageSourcePayload.FromResolvedMedia(resolvedMedia);
    if (payload.Error is not null)
        return new FailedSubmitOutcome(payload.Error);
    sourcePayload = payload.Payload;
}
```

Task 4 will pass `sourcePayload` into the Flux 2 Pro request builder so the data URI is not computed twice.

- [ ] **Step 6: In `ReplicateImageOptionsCodec`, remove Schnell-only wording**

Replace:

```csharp
"reference_image_paths are not supported for Replicate FLUX Schnell."
```

with:

```csharp
$"reference_image_paths are not supported for {capability.Name}."
```

- [ ] **Step 7: Run provider tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderTests|ReplicateImageOptionsCodecTests"
```

Expected: new Flux 2 validation tests pass and existing Schnell tests remain green.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Replicate\ReplicateImageSourcePayload.cs src\Rook\Services\Vision\Image\Replicate\ReplicateImageProvider.cs src\Rook\Services\Vision\Image\Replicate\ReplicateImageOptionsCodec.cs src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageProviderTests.cs
git commit -m "feat(vision): validate Flux 2 Pro source payloads"
```

---

## Task 4: Build Flux 2 Pro Replicate Request JSON

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`

- [ ] **Step 1: Add a request-shape test for Flux 2 Pro**

In `ReplicateImageProviderTests.cs`, add:

```csharp
[Fact]
public async Task SubmitAsync_flux2_posts_source_image_schema_with_data_uri_only_in_request_body()
{
    string? requestBody = null;
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            requestBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return Json(HttpStatusCode.Created, """
                {
                  "id": "pred-flux2",
                  "status": "starting",
                  "urls": {
                    "get": "https://api.replicate.com/v1/predictions/pred-flux2",
                    "cancel": "https://api.replicate.com/v1/predictions/pred-flux2/cancel"
                  }
                }
                """);
        },
    };
    var provider = Provider("r8-test-token", handler);
    var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [input] = PngMedia(),
    };

    var outcome = await provider.SubmitAsync(
        Request(
            model: ReplicateImageCapabilities.Flux2Pro,
            resolution: "1MP",
            aspectRatio: "match_input_image"),
        media,
        CancellationToken.None);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(HttpMethod.Post, request.Method);
    Assert.Equal(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-2-pro/predictions",
        request.RequestUri!.ToString());

    var root = Assert.IsType<JsonObject>(JsonNode.Parse(requestBody!));
    Assert.Equal(new[] { "input" }, root.Select(kvp => kvp.Key).OrderBy(k => k));
    var inputJson = Assert.IsType<JsonObject>(root["input"]);
    Assert.Equal(
        new[] { "aspect_ratio", "input_images", "output_format", "prompt", "resolution" },
        inputJson.Select(kvp => kvp.Key).OrderBy(k => k));
    Assert.Equal("sunlit massing study", inputJson["prompt"]!.GetValue<string>());
    Assert.Equal("match_input_image", inputJson["aspect_ratio"]!.GetValue<string>());
    Assert.Equal("1MP", inputJson["resolution"]!.GetValue<string>());
    Assert.Equal("png", inputJson["output_format"]!.GetValue<string>());

    var images = Assert.IsType<JsonArray>(inputJson["input_images"]);
    var dataUri = Assert.IsType<JsonValue>(Assert.Single(images)).GetValue<string>();
    Assert.StartsWith("data:image/png;base64,", dataUri, StringComparison.Ordinal);
    Assert.DoesNotContain("num_outputs", requestBody);
    Assert.DoesNotContain("reference", requestBody);

    var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
    Assert.Equal("pred-flux2", queued.Handle.ProviderJobId);
    Assert.DoesNotContain("data:image/", JsonNode.Parse(requestBody!)!["input"]!.ToJsonString().Replace(dataUri, ""));
}
```

- [ ] **Step 2: Run the request-shape test and verify it fails**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "SubmitAsync_flux2_posts_source_image_schema"
```

Expected: fail because Flux 2 Pro currently uses the Schnell request builder.

- [ ] **Step 3: Add model-specific endpoint selection**

In `ReplicateImageProvider.cs`, replace the single static endpoint:

```csharp
private static readonly ReplicatePredictionEndpoint Endpoint =
    ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", "flux-schnell");
```

with:

```csharp
private static readonly ReplicatePredictionEndpoint FluxSchnellEndpoint =
    ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", "flux-schnell");

private static readonly ReplicatePredictionEndpoint Flux2ProEndpoint =
    ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", "flux-2-pro");
```

Add:

```csharp
private static ReplicatePredictionEndpoint EndpointForModel(string model) =>
    string.Equals(model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal)
        ? Flux2ProEndpoint
        : FluxSchnellEndpoint;
```

Change `CreatePredictionAsync` to call:

```csharp
EndpointForModel(request.Model),
BuildRequestJson(request, sourcePayload),
```

- [ ] **Step 4: Branch `BuildRequestJson` by model id**

Replace:

```csharp
private static string BuildRequestJson(ImageGenerationRequest request)
```

with:

```csharp
private static string BuildRequestJson(
    ImageGenerationRequest request,
    ReplicateImageSourcePayload? sourcePayload)
{
    if (string.Equals(request.Model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal))
        return BuildFlux2ProRequestJson(request, sourcePayload);

    return BuildFluxSchnellRequestJson(request);
}

private static string BuildFluxSchnellRequestJson(ImageGenerationRequest request)
{
    var input = new JsonObject
    {
        ["prompt"] = request.Prompt,
        ["aspect_ratio"] = string.IsNullOrWhiteSpace(request.AspectRatio)
            ? "1:1"
            : request.AspectRatio,
        ["num_outputs"] = 1,
        ["output_format"] = "png",
    };

    return new JsonObject
    {
        ["input"] = input,
    }.ToJsonString();
}

private static string BuildFlux2ProRequestJson(
    ImageGenerationRequest request,
    ReplicateImageSourcePayload? sourcePayload)
{
    if (sourcePayload is null)
        throw new InvalidOperationException("Flux 2 Pro source payload was not prepared.");

    var inputImages = new JsonArray { sourcePayload.DataUri };
    var input = new JsonObject
    {
        ["prompt"] = request.Prompt,
        ["input_images"] = inputImages,
        ["aspect_ratio"] = "match_input_image",
        ["resolution"] = string.IsNullOrWhiteSpace(request.Resolution)
            ? "1MP"
            : request.Resolution,
        ["output_format"] = "png",
    };

    return new JsonObject
    {
        ["input"] = input,
    }.ToJsonString();
}
```

The Flux 2 Pro local validation path already returns `FailedSubmitOutcome` before token lookup and HTTP in Task 3. The `InvalidOperationException` above is a programming-error guard and should be caught by the existing generic submit error mapping.

- [ ] **Step 5: Run provider tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderTests"
```

Expected: all provider tests pass. Schnell exact-body test must remain unchanged.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Replicate\ReplicateImageProvider.cs src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageProviderTests.cs
git commit -m "feat(vision): submit Flux 2 Pro source image requests"
```

---

## Task 5: Pin Backend Work-Item Gating For Async Source Models

**Files:**
- Modify: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- Modify: `src/Rook/Handlers/VisionHandler.cs` only if tests expose a gating bug

- [ ] **Step 1: Add image job op tests for source-image async models**

In `ImageJobOpHandlerTests.cs`, add after `DispatchAsync_Start_AllowsPromptOnlyForAsyncTextToImageModel`:

```csharp
[Fact]
public async Task DispatchAsync_Start_AllowsSourceImageForAsyncImageToImageModel()
{
    using var temp = TempDir.Create();
    var inputPath = Path.Combine(temp.Path, "input.png");
    File.WriteAllBytes(inputPath, new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 });

    ImageJobStartRequest? captured = null;
    var manager = new StubImageJobManager
    {
        SubmitImpl = (request, _) =>
        {
            captured = request;
            return ImageJobSubmitResult.Ok(SampleJobId, ImageJobState.Queued);
        },
    };

    var handler = new ImageJobOpHandler(
        manager,
        NewVisionHandlerWithImageProvider(
            new FakeAsyncTextToImageProvider(),
            "replicate",
            "black-forest-labs/flux-2-pro",
            ImageSubmissionMode.AsyncImageJob,
            supportsImageToImage: true,
            supportsTextToImage: false,
            maxReferenceImages: 0,
            resolutions: new[] { "1MP" },
            aspectRatios: new[] { "match_input_image" }));

    var response = await handler.DispatchAsync($$"""
        {
          "op": "image_generate_start",
          "prompt": "enhance this viewport",
          "input_image_path": "{{Escape(inputPath)}}",
          "model": "black-forest-labs/flux-2-pro",
          "resolution": "1MP",
          "aspect_ratio": "match_input_image"
        }
        """);

    AssertOk(response);
    Assert.NotNull(captured);
    Assert.Equal("black-forest-labs/flux-2-pro", captured!.Request.Model);
    Assert.NotEmpty(captured.ResolvedMedia);
    Assert.Contains(
        captured.ResolvedMedia,
        kvp => kvp.Key.Role == ImageMediaRoles.InputImage
            && kvp.Value.MimeType == "image/png");
    Assert.Null(captured.Request.ReferenceImages);
}

[Fact]
public async Task DispatchAsync_Start_RejectsPromptOnlyForAsyncImageToImageModel()
{
    var manager = new StubImageJobManager();
    var handler = new ImageJobOpHandler(
        manager,
        NewVisionHandlerWithImageProvider(
            new FakeAsyncTextToImageProvider(),
            "replicate",
            "black-forest-labs/flux-2-pro",
            ImageSubmissionMode.AsyncImageJob,
            supportsImageToImage: true,
            supportsTextToImage: false,
            maxReferenceImages: 0,
            resolutions: new[] { "1MP" },
            aspectRatios: new[] { "match_input_image" }));

    var response = await handler.DispatchAsync("""
        {
          "op": "image_generate_start",
          "prompt": "enhance this viewport",
          "model": "black-forest-labs/flux-2-pro",
          "resolution": "1MP",
          "aspect_ratio": "match_input_image"
        }
        """);

    AssertFail(response, GenerationErrorCode.InvalidRequest, expectedHttp: 400);
}

[Fact]
public async Task DispatchAsync_Start_RejectsReferencesForAsyncImageToImageModelWhenMaxReferenceImagesIsZero()
{
    using var temp = TempDir.Create();
    var inputPath = Path.Combine(temp.Path, "input.png");
    var referencePath = Path.Combine(temp.Path, "ref.png");
    var png = new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 };
    File.WriteAllBytes(inputPath, png);
    File.WriteAllBytes(referencePath, png);

    var manager = new StubImageJobManager();
    var handler = new ImageJobOpHandler(
        manager,
        NewVisionHandlerWithImageProvider(
            new FakeAsyncTextToImageProvider(),
            "replicate",
            "black-forest-labs/flux-2-pro",
            ImageSubmissionMode.AsyncImageJob,
            supportsImageToImage: true,
            supportsTextToImage: false,
            maxReferenceImages: 0,
            resolutions: new[] { "1MP" },
            aspectRatios: new[] { "match_input_image" }));

    var response = await handler.DispatchAsync($$"""
        {
          "op": "image_generate_start",
          "prompt": "enhance this viewport",
          "input_image_path": "{{Escape(inputPath)}}",
          "reference_image_paths": [ "{{Escape(referencePath)}}" ],
          "model": "black-forest-labs/flux-2-pro",
          "resolution": "1MP",
          "aspect_ratio": "match_input_image"
        }
        """);

    AssertFail(response, GenerationErrorCode.InvalidRequest, expectedHttp: 400);
}
```

- [ ] **Step 2: Update the image provider test helper for source-only models**

In `ImageJobOpHandlerTests.cs`, change `NewVisionHandlerWithImageProvider` to accept explicit reference and option lists:

```csharp
private static VisionHandler NewVisionHandlerWithImageProvider(
    IImageProvider provider,
    string providerName,
    string modelId,
    ImageSubmissionMode submissionMode,
    bool supportsImageToImage,
    bool supportsTextToImage,
    int maxReferenceImages = 0,
    string[]? resolutions = null,
    string[]? aspectRatios = null)
```

Pass the new arguments into `SingleImageProviderRegistration`:

```csharp
new SingleImageProviderRegistration(
    provider,
    providerName,
    modelId,
    submissionMode,
    supportsImageToImage,
    supportsTextToImage,
    maxReferenceImages,
    resolutions,
    aspectRatios)
```

Change `SingleImageProviderRegistration` to the same optional constructor shape:

```csharp
private sealed class SingleImageProviderRegistration : IImageProviderRegistration
{
    public SingleImageProviderRegistration(
        IImageProvider provider,
        string providerName,
        string modelId,
        ImageSubmissionMode submissionMode,
        bool supportsImageToImage,
        bool supportsTextToImage,
        int maxReferenceImages = 0,
        string[]? resolutions = null,
        string[]? aspectRatios = null)
    {
        Provider = provider;
        ProviderName = providerName;
        SubmissionMode = submissionMode;
        _models = new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>
        {
            [modelId] = (
                new ImageCapability(
                    Id: modelId,
                    Name: modelId,
                    Status: "preview",
                    Resolutions: resolutions ?? new[] { "1K" },
                    AspectRatios: aspectRatios ?? new[] { "1:1" },
                    MaxReferenceImages: maxReferenceImages,
                    SupportsImageToImage: supportsImageToImage,
                    SupportsTextToImage: supportsTextToImage),
                new FakeImagePricingModel()),
        };
    }

    public string ProviderName { get; }
    public ImageSubmissionMode SubmissionMode { get; }
    public IImageProvider Provider { get; }
    public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; } =
        new FakeImageOptionsCodec();
    public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models => _models;
    public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; } = Array.Empty<ProviderSecretRequirement>();
}
```

Keep the existing `_models` field above the constructor:

```csharp
private readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models;
```

- [ ] **Step 3: Run focused image job op tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobOpHandlerTests"
```

Expected: all `ImageJobOpHandlerTests` pass. The tests pin the existing backend work-item behavior: async image-to-image models require `input_image_path`, and reference images are rejected when `MaxReferenceImages == 0`.

- [ ] **Step 4: Commit**

```powershell
git add src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs src\Rook\Handlers\VisionHandler.cs
git commit -m "test(vision): pin async source image job gating"
```

---

## Task 6: Update RookVision Frontend Routing

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add JS source-regression tests for routing**

In `VisionWebSurfaceTests.cs`, add after `AppJs_GenerateRoutesAsyncModelsThroughImageJobOps`:

```csharp
[Fact]
public void AppJs_GenerateRoutesSourceImageAsyncModelsWithInputImagePath()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("function isSourceImageAsyncImageModel", js);
    Assert.Contains("const sourcePath = capturedViewport && capturedViewport.file_path;", js);
    Assert.Contains("await generateImageJob(prompt, model, sourcePath);", js);
    Assert.Contains("if (sourcePath && isSourceImageAsyncImageModel(model)) args.input_image_path = sourcePath;", js);
    Assert.Contains("if (sourcePath && isSourceImageAsyncImageModel(model)) args.aspect_ratio = \"match_input_image\";", js);
    Assert.Contains("if (isPromptOnlyAsyncImageModel(model))", js);

    var jobStart = js.IndexOf("async function generateImageJob", StringComparison.Ordinal);
    var jobEnd = js.IndexOf("function showImageJobStatus", StringComparison.Ordinal);
    Assert.True(jobStart >= 0);
    Assert.True(jobEnd > jobStart);
    var jobBody = js.Substring(jobStart, jobEnd - jobStart);
    Assert.DoesNotContain("reference_image_paths", jobBody);
}

[Fact]
public void AppJs_StudioRoutesAsyncModelsThroughImageJobOps()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("async function studioGenerateImageJob", js);
    Assert.Contains("await studioGenerateImageJob(args, model);", js);
    Assert.Contains("bridgeCall(\"image_generate_start\", args)", js);
    Assert.Contains("bridgeCall(\"image_job_status\"", js);
    Assert.Contains("bridgeCall(\"image_job_result\"", js);
    Assert.Contains("showStudioImageJobStatus", js);
}
```

Update the existing `AppJs_GenerateRoutesAsyncModelsThroughImageJobOps` test if needed so it does not require the old `generateImageJob(prompt, model)` signature.

- [ ] **Step 2: Run JS resource tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests"
```

Expected: fail because source-image async routing and Studio async routing do not exist yet.

- [ ] **Step 3: Add source-image async helpers in `app.js`**

Near `isPromptOnlyAsyncImageModel`, add:

```javascript
function isSourceImageAsyncImageModel(model) {
    return isAsyncImageJobModel(model)
        && model.supports_image_to_image !== false;
}
```

In `generateImage`, replace:

```javascript
if (isAsyncImageJobModel(model)) {
    await generateImageJob(prompt, model);
    return;
}
```

with:

```javascript
if (isAsyncImageJobModel(model)) {
    const sourcePath = capturedViewport && capturedViewport.file_path;
    await generateImageJob(prompt, model, sourcePath);
    return;
}
```

Change the signature:

```javascript
async function generateImageJob(prompt, model, sourcePath) {
```

Inside `generateImageJob`, after model assignment, add:

```javascript
if (sourcePath && isSourceImageAsyncImageModel(model)) args.input_image_path = sourcePath;
if (sourcePath && isSourceImageAsyncImageModel(model)) args.aspect_ratio = "match_input_image";
```

Do not add `reference_image_paths` in `generateImageJob`.

- [ ] **Step 4: Add shared async polling helper for Generate and Studio**

Replace the polling loop body in `generateImageJob` with a helper:

```javascript
async function awaitImageJobResult(args, statusHandler) {
    const start = await bridgeCall("image_generate_start", args);
    if (!start || typeof start.job_id !== "string" || start.job_id.length === 0) {
        throw new Error("Image job did not return a job id.");
    }
    const jobId = start.job_id;
    let terminal = null;
    for (let attempt = 0; attempt < 180; attempt++) {
        const status = await bridgeCall("image_job_status", { job_id: jobId });
        if (!status || typeof status.state !== "string" || status.state.length === 0) {
            throw new Error("Image job returned an invalid status.");
        }
        statusHandler(status);
        if (["complete", "error", "cancelled", "interrupted"].includes(status.state)) {
            terminal = status;
            break;
        }
        await delay(1000);
    }
    if (!terminal) throw new Error("Image job did not finish before the UI timeout.");
    if (terminal.state !== "complete") {
        const err = terminal.error && terminal.error.message;
        throw new Error(err || `Image job ended with state ${terminal.state}.`);
    }
    const result = await bridgeCall("image_job_result", { job_id: jobId });
    if (!result || !result.result_artifact_id) {
        throw new Error("Image job completed without an artifact.");
    }
    return result;
}
```

Then `generateImageJob` should call:

```javascript
const result = await awaitImageJobResult(args, showImageJobStatus);
renderGeneratedArtifact({ artifact_id: result.result_artifact_id }, "Image generated.");
```

Add Studio status rendering:

```javascript
function showStudioImageJobStatus(status) {
    const state = status && status.state || "unknown";
    if (state === "queued") showStudioStatus("Image job queued...", "info");
    else if (state === "submitting") showStudioStatus("Submitting image job...", "info");
    else if (state === "polling") showStudioStatus("Image job running...", "info");
    else if (state === "materializing") showStudioStatus("Saving generated image...", "info");
    else if (state === "complete") showStudioStatus("Image job complete.", "success");
    else if (state === "cancelled") showStudioStatus("Image job cancelled.", "error");
    else if (state === "error") showStudioStatus("Image job failed.", "error");
    else showStudioStatus(`Image job ${state}...`, "info");
}
```

Add Studio async helper:

```javascript
async function studioGenerateImageJob(args, model) {
    if (model && isSourceImageAsyncImageModel(model)) args.aspect_ratio = "match_input_image";
    const result = await awaitImageJobResult(args, showStudioImageJobStatus);
    latestStudioArtifactId = result.result_artifact_id;
    if (result.result_artifact_id) {
        el.studioResultImage.src = `/blob/${encodeURIComponent(result.result_artifact_id)}/image?ts=${Date.now()}`;
        el.studioResultPanel.classList.remove("hidden");
        showStudioStatus("Image generated.", "success");
    } else {
        showStudioStatus("Generation returned no artifact.", "error");
    }
}
```

In `studioGenerate`, after args are built and before sync `bridgeCall("generate", args)`, add:

```javascript
const model = selectedImageModel(el.studioModelSelect);
if (isAsyncImageJobModel(model)) {
    await studioGenerateImageJob(args, model);
    return;
}
```

Keep the existing sync `bridgeCall("generate", args)` path for non-async models.

- [ ] **Step 5: Keep Schnell source-free**

Because `validateGenerateModelForSubmit` allows prompt-only async models without capture, and `generateImageJob` only adds `input_image_path` when `isSourceImageAsyncImageModel(model)`, Schnell must continue to call `image_generate_start` with prompt/model/resolution/aspect only.

Do not add `reference_image_paths` to async requests.

- [ ] **Step 6: Run JS resource tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests"
```

Expected: all Vision web surface tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\UI\Vision\Resources\app.js src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): route async source image jobs from UI"
```

---

## Task 7: Add Leakage And Durable Compatibility Tests

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactory.cs`
- Modify: `src/Rook/Handlers/ImageJobOpHandler.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageJobManagerTests.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs`
- Modify: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`

- [ ] **Step 1: Add durable error sanitizer coverage for data URI**

In `ImageJobLedgerRecordFactoryTests.cs`, add:

```csharp
[Fact]
public void FromRecord_RedactsDataUriInErrorMessage()
{
    var initial = ImageJobLedgerRecordFactory.FromInitial(
        Guid.Parse("11111111-1111-1111-1111-111111111111"),
        "replicate",
        "black-forest-labs/flux-2-pro",
        ImageJobState.Polling,
        DateTimeOffset.Parse("2026-05-04T12:00:00Z"));

    var error = new GenerationError(
        GenerationErrorCode.ExecutionFailed,
        "Provider rejected data:image/png;base64,abcdef",
        Retryable: false);

    var next = ImageJobLedgerRecordFactory.WithState(
        initial,
        ImageJobState.Error,
        initial.UpdatedAt.AddSeconds(1),
        error: error);

    Assert.NotNull(next.Error);
    Assert.DoesNotContain("data:image/", next.Error!.Message, StringComparison.OrdinalIgnoreCase);
    Assert.Contains("redacted", next.Error.Message, StringComparison.OrdinalIgnoreCase);
}
```

- [ ] **Step 2: Add data URI to the durable error redaction list**

In `ImageJobLedgerRecordFactory.cs`, add `data:image/` to `BannedSubstrings`:

```csharp
private static readonly string[] BannedSubstrings =
{
    "http://",
    "https://",
    "replicate.delivery",
    "api.replicate.com",
    "urls.get",
    "urls.cancel",
    "status_url",
    "cancel_url",
    "response_url",
    "provider_result_token",
    "data:image/",
    "Bearer ",
    "api_token",
    "r8_",
};
```

- [ ] **Step 3: Add manager integration leakage test for Flux 2 Pro**

In `ReplicateImageJobManagerTests.cs`, add:

```csharp
[Fact]
public async Task Flux2_job_materializes_without_leaking_data_uri_to_ledger_or_artifact_metadata()
{
    string? submitBody = null;
    var apiHandler = new TestHttpMessageHandler
    {
        OnSend = request =>
        {
            if (request.Method == HttpMethod.Post)
            {
                submitBody = request.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                return Json(HttpStatusCode.Created, Prediction("pred-flux2", "starting"));
            }

            return Json(HttpStatusCode.OK, Prediction(
                "pred-flux2",
                "succeeded",
                outputJson: "\"https://replicate.delivery/pbxt/flux2.png\""));
        },
    };
    var outputHandler = new CapturingOutputHandler();
    using var manager = Manager(
        apiHandler,
        outputHandler,
        providerApiToken: ProviderApiToken,
        selectorApiToken: SelectorApiToken);

    var submit = await manager.SubmitAsync(Flux2Start(), CancellationToken.None);
    var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);
    var fetch = await manager.FetchResultAsync(submit.JobId.Value, CancellationToken.None);

    Assert.Contains("data:image/png;base64,", submitBody);
    Assert.Equal(ImageJobState.Complete, status.State);
    Assert.Equal(ImageJobState.Complete, fetch.State);

    var artifact = _artifactStore.Get(status.ResultArtifactId!.Value);
    Assert.NotNull(artifact);
    var artifactMetadata = MetadataJson(artifact!);
    Assert.DoesNotContain("data:image/", artifactMetadata, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("input.png", artifactMetadata, StringComparison.OrdinalIgnoreCase);

    var ledgerJson = JsonSerializer.Serialize(_ledger.Records);
    Assert.DoesNotContain("data:image/", ledgerJson, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("sunlit massing study", ledgerJson, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("replicate.delivery", ledgerJson, StringComparison.OrdinalIgnoreCase);
}
```

Add helper:

```csharp
private static ImageJobStartRequest Flux2Start()
{
    var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
    return new ImageJobStartRequest(
        new ImageGenerationRequest(
            Model: ReplicateImageCapabilities.Flux2Pro,
            Prompt: "sunlit massing study",
            Resolution: "1MP",
            AspectRatio: "match_input_image",
            NumberOfImages: 1,
            ReferenceImages: null,
            Options: new ReplicateImageOptions()),
        new Dictionary<MediaRef, ResolvedMedia>
        {
            [input] = new ResolvedMedia(
                new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 },
                "image/png"),
        },
        Array.Empty<Guid>());
}
```

- [ ] **Step 4: Strengthen bridge payload leakage tests**

In `ImageJobOpHandlerTests.cs`, add:

```csharp
[Fact]
public void DispatchOffUi_Status_DoesNotExposeDataUriInError()
{
    var manager = new StubImageJobManager
    {
        StatusImpl = _ => ImageJobStatusResult.Failed(
            ImageJobState.Error,
            new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "Provider rejected data:image/png;base64,abcdef",
                Retryable: false)),
    };
    var handler = new ImageJobOpHandler(manager, NewVisionHandler());

    var response = handler.DispatchOffUi(StatusBody());

    var payload = JsonSerializer.Serialize(response);
    Assert.DoesNotContain("data:image/", payload, StringComparison.OrdinalIgnoreCase);
}
```

- [ ] **Step 5: Sanitize bridge-facing image job errors**

In `ImageJobOpHandler.cs`, replace `ErrorToObj` with:

```csharp
private static Dictionary<string, object?> ErrorToObj(
    GenerationError error)
{
    var safe = ImageJobLedgerRecordFactory.SanitizeError(error) ?? error;
    return new Dictionary<string, object?>
    {
        ["code"] = ErrorCodeToString(safe.Code),
        ["message"] = safe.Message,
        ["retryable"] = safe.Retryable,
        ["field"] = safe.Field,
    };
}
```

This intentionally reuses the image-safe sanitizer already used at the durable ledger boundary. Bridge responses must not expose source data URIs, provider URLs, provider result tokens, or provider detail.

- [ ] **Step 6: Run leakage-focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageJobManagerTests|ImageJobLedgerRecordFactoryTests|ImageJobOpHandlerTests"
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerRecordFactory.cs src\Rook\Handlers\ImageJobOpHandler.cs src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageJobManagerTests.cs src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobLedgerRecordFactoryTests.cs src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs
git commit -m "test(vision): guard Flux 2 Pro payload leakage"
```

---

## Task 8: Final Verification And Boundary Scan

**Files:**
- No code changes expected.

- [ ] **Step 1: Run focused provider and handler suites**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderTests|ReplicateImageProviderRegistrationTests|ReplicateImageOptionsCodecTests|ImageMimeDetectorTests|ImageJobOpHandlerTests|VisionWebSurfaceTests"
```

Expected: all selected tests pass.

- [ ] **Step 2: Run image job durability and Replicate manager suites**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobLedger|ImageJobManagerTests|ReplicateImageJobManagerTests"
```

Expected: all selected tests pass.

- [ ] **Step 3: Run sync image provider regression suites**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "GeminiImageProviderTests|FalImageProviderTests|VisionHandlerTests"
```

Expected: existing Gemini/fal sync source-image behavior remains green.

- [ ] **Step 4: Run full managed test suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: full test suite passes.

- [ ] **Step 5: Run diff check**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: no whitespace errors.

- [ ] **Step 6: Run boundary scan**

Run:

```powershell
rg -n "flux-2-pro|Flux2Pro|image_generate_start|image_job_status|image_job_result|image_jobs|ReplicateImageSourcePayload" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected:

- no hits in `src/RookNative`;
- no hits in `mcp_server`;
- no image job op exposure added to `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`.

If hits appear only in comments unrelated to route exposure, review manually and remove or justify them before PR.

- [ ] **Step 7: Record manual Rhino smoke instructions in PR body**

Use this checklist in the PR description:

```text
Manual Rhino smoke for PR-16:
- Build/deploy companion.
- Open Rhino and run ShowRookVision.
- Capture viewport source in Generate, select Flux 2 Pro, submit, wait for completion, verify Gallery artifact.
- Restart Rhino and verify artifact remains visible.
- Try Flux 2 Pro without a source and verify local blocked state.
- Try an oversized source and verify clear backend validation failure.
```

- [ ] **Step 8: Commit final documentation updates if verification notes are tracked in repo**

Keep PR-body-only verification notes out of the repository. When `docs/rook_docs/work-queue.md` is updated as part of handoff, run:

```powershell
git add docs\rook_docs\work-queue.md
git commit -m "docs(vision): record Flux 2 Pro verification"
```

---

## Execution Notes

Recommended execution mode: **Inline Execution**. The tasks are sequential and touch the same provider, handler, and UI files. Parallel workers would create merge risk with little speedup.

Use live Replicate only during the final manual Rhino smoke. Automated tests must remain fake HTTP/fake provider only.
