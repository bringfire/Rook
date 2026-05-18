# RookVision Provider Media Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Replicate Flux 2 Pro use policy-driven media validation and Replicate file URL transport instead of Rook's 1 MiB data URI cap.

**Architecture:** Add small image-only policy primitives, a dimension reader, and a Replicate file upload transport seam. Keep milestone 1 narrow: prompt-only Flux 2 Pro and the existing single primary local source image workflow; model reference limits are policy-modeled in unit tests but route/UI reference support remains gated.

**Tech Stack:** C# net48/net7 multi-targeted managed Rook plugin, `System.Text.Json`, `System.Net.Http`, xUnit. No native C++ changes and no new dependencies.

---

## File Structure

- Create `src/Rook/Services/Vision/Image/ImageMediaPolicy.cs`
  - Image-only policy records/enums for model input policy, transport policy, and Rook safety policy.
- Create `src/Rook/Services/Vision/Image/ImageDimensions.cs`
  - Header-based dimension reader for PNG, JPEG, GIF, and WebP.
- Modify `src/Rook/Services/Vision/Image/ImageMimeDetector.cs`
  - Add GIF byte detection and update Flux 2 MIME support.
- Modify `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
  - Correct Flux 2 Pro text-to-image capability while keeping public reference UI gated.
- Modify `src/Rook/Services/Vision/Image/Replicate/ReplicateImageSourcePayload.cs`
  - Replace the 1 MiB data URI payload with policy-validated media input URLs.
- Modify `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
  - Add prompt-only Flux 2 Pro request support and route local source bytes through upload transport.
- Modify `src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs`
  - Add authenticated multipart file upload to `/v1/files`.
- Create `src/Rook/Services/Vision/Image/Replicate/IReplicateFileTransport.cs`
  - Test seam for uploading source bytes and returning opaque `urls.get`.
- Create `src/Rook/Services/Vision/Image/Replicate/ReplicateFileTransport.cs`
  - Production implementation using `ReplicateApiClient`.
- Modify `src/Rook/Handlers/VisionHandler.cs`
  - Replace global Gemini-oriented media caps with per-model resolver limits for Flux 2 Pro.
- Test `src/Rook.Tests/Services/Vision/Image/ImageMediaPolicyTests.cs`
  - Policy provenance, 8-image policy, and 9 MP aggregate validation.
- Test `src/Rook.Tests/Services/Vision/Image/ImageDimensionsTests.cs`
  - Header dimension reader and GIF behavior.
- Modify `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`
  - Prompt-only behavior, file upload transport, no data URI, no upload URL persistence, local-media fallback.
- Modify `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`
  - Capability correction tests.
- Modify `src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs`
  - Multipart upload endpoint tests.
- Modify focused `VisionHandlerTests` or `ImageJobOpHandlerTests` only where existing tests already cover Flux 2 Pro route-level behavior.

## Test Commands

Use these commands from `C:/Users/aryan/source/repos/Rook`:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ImageMediaPolicyTests
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ImageDimensionsTests
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateApiClientTests
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateImageProviderTests
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateImageProviderRegistrationTests
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~VisionHandlerTests
```

Run the final managed suite if focused tests pass:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj
```

Do not run native builds for this work.

---

### Task 1: Add Image Media Policy Unit

**Files:**
- Create: `src/Rook/Services/Vision/Image/ImageMediaPolicy.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/ImageMediaPolicyTests.cs`

- [ ] **Step 1: Write failing policy tests**

Create `src/Rook.Tests/Services/Vision/Image/ImageMediaPolicyTests.cs`:

```csharp
using System;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageMediaPolicyTests
    {
        [Fact]
        public void Flux2Pro_policy_models_provider_input_limits_and_provenance()
        {
            var policy = ReplicateImageCapabilities.Flux2ProMediaPolicy;

            Assert.Equal(ReplicateImageCapabilities.Flux2Pro, policy.ModelId);
            Assert.Equal("Flux 2 Pro", policy.ModelLabel);
            Assert.Equal(ImageInputTransportKind.ReplicateHostedFileUrl, policy.Transport.Kind);
            Assert.Equal(8, policy.Model.MaxInputImages);
            Assert.Equal(9_000_000L, policy.Model.MaxAggregatePixels);
            Assert.Contains("image/jpeg", policy.Model.AllowedMimeTypes);
            Assert.Contains("image/png", policy.Model.AllowedMimeTypes);
            Assert.Contains("image/gif", policy.Model.AllowedMimeTypes);
            Assert.Contains("image/webp", policy.Model.AllowedMimeTypes);
            Assert.Equal(ImageLimitProvenance.ProviderDocumented, policy.Model.PixelLimitProvenance);
            Assert.Equal(new DateTime(2026, 5, 18), policy.Model.ProviderReviewedOn);
            Assert.Contains("flux-2-pro", policy.Model.ProviderSourceUrl);
        }

        [Fact]
        public void Flux2Pro_policy_accepts_prompt_only_without_media_transport()
        {
            var policy = ReplicateImageCapabilities.Flux2ProMediaPolicy;

            var result = policy.ValidateInputSet(
                mediaCount: 0,
                aggregatePixels: 0,
                hasPrompt: true);

            Assert.True(result.Success);
        }

        [Fact]
        public void Flux2Pro_policy_rejects_missing_prompt()
        {
            var policy = ReplicateImageCapabilities.Flux2ProMediaPolicy;

            var result = policy.ValidateInputSet(
                mediaCount: 0,
                aggregatePixels: 0,
                hasPrompt: false);

            Assert.False(result.Success);
            Assert.Equal("prompt", result.Field);
            Assert.Contains("requires prompt", result.Message);
        }

        [Fact]
        public void Flux2Pro_policy_rejects_more_than_eight_images_at_policy_level()
        {
            var policy = ReplicateImageCapabilities.Flux2ProMediaPolicy;

            var result = policy.ValidateInputSet(
                mediaCount: 9,
                aggregatePixels: 1,
                hasPrompt: true);

            Assert.False(result.Success);
            Assert.Equal("input_images", result.Field);
            Assert.Contains("up to 8 input images", result.Message);
        }

        [Fact]
        public void Flux2Pro_policy_rejects_aggregate_pixels_over_nine_megapixels()
        {
            var policy = ReplicateImageCapabilities.Flux2ProMediaPolicy;

            var result = policy.ValidateInputSet(
                mediaCount: 1,
                aggregatePixels: 9_000_001,
                hasPrompt: true);

            Assert.False(result.Success);
            Assert.Equal("input_images", result.Field);
            Assert.Contains("9 megapixels or less", result.Message);
        }
    }
}
```

- [ ] **Step 2: Run policy tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ImageMediaPolicyTests
```

Expected: build fails because `ImageMediaPolicy`, `ImageInputTransportKind`, `ImageLimitProvenance`, and `Flux2ProMediaPolicy` do not exist.

- [ ] **Step 3: Implement policy primitives**

Create `src/Rook/Services/Vision/Image/ImageMediaPolicy.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;

namespace Rook.Services.Vision.Image
{
    public enum ImageInputTransportKind
    {
        InlineDataUri = 0,
        ReplicateHostedFileUrl = 1,
        FalHostedFileUrl = 2,
        CallerProvidedHttpsUrl = 3,
        Unsupported = 4,
    }

    public enum ImageLimitProvenance
    {
        ProviderDocumented = 0,
        ProviderTransportDocumented = 1,
        RookGuardProviderUnverified = 2,
    }

    public sealed class ImageMediaPolicy
    {
        public ImageMediaPolicy(
            string modelId,
            string modelLabel,
            ImageModelInputPolicy model,
            ImageTransportPolicy transport,
            ImageRookSafetyPolicy safety)
        {
            if (string.IsNullOrWhiteSpace(modelId))
                throw new ArgumentException("Model id must be non-empty.", nameof(modelId));
            if (string.IsNullOrWhiteSpace(modelLabel))
                throw new ArgumentException("Model label must be non-empty.", nameof(modelLabel));
            ModelId = modelId;
            ModelLabel = modelLabel;
            Model = model ?? throw new ArgumentNullException(nameof(model));
            Transport = transport ?? throw new ArgumentNullException(nameof(transport));
            Safety = safety ?? throw new ArgumentNullException(nameof(safety));
        }

        public string ModelId { get; }
        public string ModelLabel { get; }
        public ImageModelInputPolicy Model { get; }
        public ImageTransportPolicy Transport { get; }
        public ImageRookSafetyPolicy Safety { get; }

        public ImagePolicyValidationResult ValidateInputSet(
            int mediaCount,
            long aggregatePixels,
            bool hasPrompt)
        {
            if (!hasPrompt)
                return ImagePolicyValidationResult.Fail(
                    $"{ModelLabel} requires prompt.",
                    "prompt");
            if (mediaCount < 0)
                return ImagePolicyValidationResult.Fail(
                    "Image media count must be non-negative.",
                    "input_images");
            if (mediaCount > Model.MaxInputImages)
                return ImagePolicyValidationResult.Fail(
                    $"{ModelLabel} accepts up to {Model.MaxInputImages} input images; got {mediaCount}.",
                    "input_images");
            if (aggregatePixels > Model.MaxAggregatePixels)
                return ImagePolicyValidationResult.Fail(
                    $"{ModelLabel} input images must total {Model.MaxAggregatePixels / 1_000_000L} megapixels or less.",
                    "input_images");
            return ImagePolicyValidationResult.Ok();
        }
    }

    public sealed class ImageModelInputPolicy
    {
        public ImageModelInputPolicy(
            IReadOnlyList<string> allowedMimeTypes,
            int maxInputImages,
            long maxAggregatePixels,
            ImageLimitProvenance pixelLimitProvenance,
            DateTime providerReviewedOn,
            string providerSourceUrl)
        {
            if (allowedMimeTypes is null || allowedMimeTypes.Count == 0)
                throw new ArgumentException("Allowed MIME types must be non-empty.", nameof(allowedMimeTypes));
            if (maxInputImages < 0)
                throw new ArgumentOutOfRangeException(nameof(maxInputImages));
            if (maxAggregatePixels < 0)
                throw new ArgumentOutOfRangeException(nameof(maxAggregatePixels));
            if (string.IsNullOrWhiteSpace(providerSourceUrl))
                throw new ArgumentException("Provider source URL must be non-empty.", nameof(providerSourceUrl));

            AllowedMimeTypes = new ReadOnlyCollection<string>(allowedMimeTypes.ToArray());
            MaxInputImages = maxInputImages;
            MaxAggregatePixels = maxAggregatePixels;
            PixelLimitProvenance = pixelLimitProvenance;
            ProviderReviewedOn = providerReviewedOn.Date;
            ProviderSourceUrl = providerSourceUrl;
        }

        public IReadOnlyList<string> AllowedMimeTypes { get; }
        public int MaxInputImages { get; }
        public long MaxAggregatePixels { get; }
        public ImageLimitProvenance PixelLimitProvenance { get; }
        public DateTime ProviderReviewedOn { get; }
        public string ProviderSourceUrl { get; }
    }

    public sealed class ImageTransportPolicy
    {
        public ImageTransportPolicy(
            ImageInputTransportKind kind,
            long? maxSingleUploadBytes,
            ImageLimitProvenance byteLimitProvenance,
            DateTime providerReviewedOn,
            string sourceUrl)
        {
            if (string.IsNullOrWhiteSpace(sourceUrl))
                throw new ArgumentException("Transport source URL must be non-empty.", nameof(sourceUrl));

            Kind = kind;
            MaxSingleUploadBytes = maxSingleUploadBytes;
            ByteLimitProvenance = byteLimitProvenance;
            ProviderReviewedOn = providerReviewedOn.Date;
            SourceUrl = sourceUrl;
        }

        public ImageInputTransportKind Kind { get; }
        public long? MaxSingleUploadBytes { get; }
        public ImageLimitProvenance ByteLimitProvenance { get; }
        public DateTime ProviderReviewedOn { get; }
        public string SourceUrl { get; }
    }

    public sealed class ImageRookSafetyPolicy
    {
        public ImageRookSafetyPolicy(long maxSingleReadBytes, long maxAggregateReadBytes)
        {
            if (maxSingleReadBytes <= 0)
                throw new ArgumentOutOfRangeException(nameof(maxSingleReadBytes));
            if (maxAggregateReadBytes <= 0)
                throw new ArgumentOutOfRangeException(nameof(maxAggregateReadBytes));
            MaxSingleReadBytes = maxSingleReadBytes;
            MaxAggregateReadBytes = maxAggregateReadBytes;
        }

        public long MaxSingleReadBytes { get; }
        public long MaxAggregateReadBytes { get; }
    }

    public sealed class ImagePolicyValidationResult
    {
        private ImagePolicyValidationResult(bool success, string? message, string? field)
        {
            Success = success;
            Message = message;
            Field = field;
        }

        public bool Success { get; }
        public string? Message { get; }
        public string? Field { get; }

        public static ImagePolicyValidationResult Ok() => new(true, null, null);
        public static ImagePolicyValidationResult Fail(string message, string field)
            => new(false, message, field);
    }
}
```

- [ ] **Step 4: Add Flux 2 Pro internal media policy**

Modify `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs` by adding constants and policy after `DefaultModel`:

```csharp
        public const long Flux2ProMaxAggregatePixels = 9_000_000L;
        public const long ReplicateFileUploadMaxBytes = 100L * 1024L * 1024L;

        public static readonly ImageMediaPolicy Flux2ProMediaPolicy =
            new(
                modelId: Flux2Pro,
                modelLabel: "Flux 2 Pro",
                model: new ImageModelInputPolicy(
                    allowedMimeTypes: new[] { "image/jpeg", "image/png", "image/gif", "image/webp" },
                    maxInputImages: 8,
                    maxAggregatePixels: Flux2ProMaxAggregatePixels,
                    pixelLimitProvenance: ImageLimitProvenance.ProviderDocumented,
                    providerReviewedOn: new DateTime(2026, 5, 18),
                    providerSourceUrl: "https://replicate.com/black-forest-labs/flux-2-pro/versions/f558a59a8bf126d892ab219846966674f6acc616940c17841aeb242e245952ff/api"),
                transport: new ImageTransportPolicy(
                    kind: ImageInputTransportKind.ReplicateHostedFileUrl,
                    maxSingleUploadBytes: ReplicateFileUploadMaxBytes,
                    byteLimitProvenance: ImageLimitProvenance.ProviderTransportDocumented,
                    providerReviewedOn: new DateTime(2026, 5, 18),
                    sourceUrl: "https://github.com/replicate/replicate-javascript/blob/main/README.md"),
                safety: new ImageRookSafetyPolicy(
                    maxSingleReadBytes: ReplicateFileUploadMaxBytes,
                    maxAggregateReadBytes: ReplicateFileUploadMaxBytes));
```

Also ensure the file has access to `ImageMediaPolicy` through its existing namespace; no extra `using` is required because `Replicate` is nested under `Rook.Services.Vision.Image`.

- [ ] **Step 5: Run policy tests and commit**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ImageMediaPolicyTests
```

Expected: PASS.

Commit:

```powershell
git add src/Rook/Services/Vision/Image/ImageMediaPolicy.cs src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs src/Rook.Tests/Services/Vision/Image/ImageMediaPolicyTests.cs
git commit -m "feat: add Flux 2 media policy"
```

---

### Task 2: Add GIF MIME Detection And Header Dimension Reader

**Files:**
- Create: `src/Rook/Services/Vision/Image/ImageDimensions.cs`
- Modify: `src/Rook/Services/Vision/Image/ImageMimeDetector.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/ImageDimensionsTests.cs`

- [ ] **Step 1: Write failing dimension and GIF tests**

Create `src/Rook.Tests/Services/Vision/Image/ImageDimensionsTests.cs`:

```csharp
using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageDimensionsTests
    {
        [Fact]
        public void Detect_recognizes_gif_bytes()
        {
            Assert.Equal("image/gif", ImageMimeDetector.Detect(GifBytes(640, 480)));
        }

        [Fact]
        public void IsFlux2SupportedMime_accepts_gif()
        {
            Assert.True(ImageMimeDetector.IsFlux2SupportedMime("image/gif"));
        }

        [Fact]
        public void TryRead_reads_gif_logical_screen_without_expanding_frames()
        {
            Assert.True(ImageDimensions.TryRead(GifBytes(320, 240), "image/gif", out var dimensions));
            Assert.Equal(320, dimensions.Width);
            Assert.Equal(240, dimensions.Height);
            Assert.Equal(76_800L, dimensions.PixelCount);
        }

        [Fact]
        public void TryRead_reads_png_ihdr_dimensions()
        {
            Assert.True(ImageDimensions.TryRead(PngBytes(1024, 768), "image/png", out var dimensions));
            Assert.Equal(1024, dimensions.Width);
            Assert.Equal(768, dimensions.Height);
        }

        [Fact]
        public void TryRead_returns_false_for_truncated_image()
        {
            Assert.False(ImageDimensions.TryRead(new byte[] { 0x47, 0x49 }, "image/gif", out _));
        }

        private static byte[] GifBytes(int width, int height) =>
            new byte[]
            {
                0x47, 0x49, 0x46, 0x38, 0x39, 0x61,
                (byte)(width & 0xFF), (byte)((width >> 8) & 0xFF),
                (byte)(height & 0xFF), (byte)((height >> 8) & 0xFF),
                0x00, 0x00, 0x00,
            };

        private static byte[] PngBytes(int width, int height)
        {
            var bytes = new byte[33];
            bytes[0] = 0x89; bytes[1] = 0x50; bytes[2] = 0x4E; bytes[3] = 0x47;
            bytes[4] = 0x0D; bytes[5] = 0x0A; bytes[6] = 0x1A; bytes[7] = 0x0A;
            bytes[12] = 0x49; bytes[13] = 0x48; bytes[14] = 0x44; bytes[15] = 0x52;
            WriteBigEndian(bytes, 16, width);
            WriteBigEndian(bytes, 20, height);
            return bytes;
        }

        private static void WriteBigEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)((value >> 24) & 0xFF);
            bytes[offset + 1] = (byte)((value >> 16) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 3] = (byte)(value & 0xFF);
        }
    }
}
```

- [ ] **Step 2: Run dimension tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ImageDimensionsTests
```

Expected: build fails because `ImageDimensions` does not exist and GIF is not detected.

- [ ] **Step 3: Implement `ImageDimensions`**

Create `src/Rook/Services/Vision/Image/ImageDimensions.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Image
{
    internal readonly struct ImageDimensions
    {
        public ImageDimensions(int width, int height)
        {
            if (width <= 0) throw new ArgumentOutOfRangeException(nameof(width));
            if (height <= 0) throw new ArgumentOutOfRangeException(nameof(height));
            Width = width;
            Height = height;
        }

        public int Width { get; }
        public int Height { get; }
        public long PixelCount => (long)Width * Height;

        public static bool TryRead(byte[] bytes, string mimeType, out ImageDimensions dimensions)
        {
            dimensions = default;
            if (bytes is null || bytes.Length == 0 || string.IsNullOrWhiteSpace(mimeType))
                return false;

            return mimeType switch
            {
                "image/png" => TryReadPng(bytes, out dimensions),
                "image/gif" => TryReadGif(bytes, out dimensions),
                "image/jpeg" => TryReadJpeg(bytes, out dimensions),
                "image/webp" => TryReadWebp(bytes, out dimensions),
                _ => false,
            };
        }

        private static bool TryReadPng(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;
            if (bytes.Length < 24) return false;
            if (bytes[12] != 0x49 || bytes[13] != 0x48 || bytes[14] != 0x44 || bytes[15] != 0x52)
                return false;
            var width = ReadInt32BigEndian(bytes, 16);
            var height = ReadInt32BigEndian(bytes, 20);
            return TryCreate(width, height, out dimensions);
        }

        private static bool TryReadGif(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;
            if (bytes.Length < 10) return false;
            if (bytes[0] != 0x47 || bytes[1] != 0x49 || bytes[2] != 0x46)
                return false;
            var width = bytes[6] | (bytes[7] << 8);
            var height = bytes[8] | (bytes[9] << 8);
            return TryCreate(width, height, out dimensions);
        }

        private static bool TryReadJpeg(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;
            if (bytes.Length < 4 || bytes[0] != 0xFF || bytes[1] != 0xD8)
                return false;

            var offset = 2;
            while (offset + 9 < bytes.Length)
            {
                if (bytes[offset] != 0xFF)
                    return false;
                var marker = bytes[offset + 1];
                offset += 2;
                if (marker == 0xD9 || marker == 0xDA)
                    return false;
                if (offset + 2 > bytes.Length)
                    return false;
                var length = ReadUInt16BigEndian(bytes, offset);
                if (length < 2 || offset + length > bytes.Length)
                    return false;
                if (IsJpegStartOfFrame(marker))
                {
                    var height = ReadUInt16BigEndian(bytes, offset + 3);
                    var width = ReadUInt16BigEndian(bytes, offset + 5);
                    return TryCreate(width, height, out dimensions);
                }
                offset += length;
            }

            return false;
        }

        private static bool TryReadWebp(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;
            if (bytes.Length < 30) return false;
            if (bytes[0] != 0x52 || bytes[1] != 0x49 || bytes[2] != 0x46 || bytes[3] != 0x46)
                return false;
            if (bytes[8] != 0x57 || bytes[9] != 0x45 || bytes[10] != 0x42 || bytes[11] != 0x50)
                return false;

            if (bytes[12] == 0x56 && bytes[13] == 0x50 && bytes[14] == 0x38 && bytes[15] == 0x58 && bytes.Length >= 30)
            {
                var widthMinusOne = bytes[24] | (bytes[25] << 8) | (bytes[26] << 16);
                var heightMinusOne = bytes[27] | (bytes[28] << 8) | (bytes[29] << 16);
                return TryCreate(widthMinusOne + 1, heightMinusOne + 1, out dimensions);
            }

            return false;
        }

        private static bool TryCreate(int width, int height, out ImageDimensions dimensions)
        {
            dimensions = default;
            if (width <= 0 || height <= 0) return false;
            dimensions = new ImageDimensions(width, height);
            return true;
        }

        private static bool IsJpegStartOfFrame(byte marker) =>
            marker is 0xC0 or 0xC1 or 0xC2 or 0xC3 or 0xC5 or 0xC6 or 0xC7 or 0xC9 or 0xCA or 0xCB or 0xCD or 0xCE or 0xCF;

        private static int ReadInt32BigEndian(byte[] bytes, int offset) =>
            (bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3];

        private static int ReadUInt16BigEndian(byte[] bytes, int offset) =>
            (bytes[offset] << 8) | bytes[offset + 1];
    }
}
```

- [ ] **Step 4: Update MIME detector for GIF**

Modify `src/Rook/Services/Vision/Image/ImageMimeDetector.cs`:

```csharp
            if (bytes.Length >= 6
                && bytes[0] == 0x47
                && bytes[1] == 0x49
                && bytes[2] == 0x46
                && bytes[3] == 0x38
                && (bytes[4] == 0x37 || bytes[4] == 0x39)
                && bytes[5] == 0x61)
            {
                return "image/gif";
            }
```

Add that block after JPEG detection and before WebP detection. Then change:

```csharp
        public static bool IsFlux2SupportedMime(string mimeType) =>
            IsPngJpegOrWebp(mimeType);
```

to:

```csharp
        public static bool IsFlux2SupportedMime(string mimeType) =>
            IsPngJpegOrWebp(mimeType)
            || string.Equals(mimeType, "image/gif", StringComparison.Ordinal);
```

- [ ] **Step 5: Run dimension tests and commit**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ImageDimensionsTests
```

Expected: PASS.

Commit:

```powershell
git add src/Rook/Services/Vision/Image/ImageDimensions.cs src/Rook/Services/Vision/Image/ImageMimeDetector.cs src/Rook.Tests/Services/Vision/Image/ImageDimensionsTests.cs
git commit -m "feat: read image dimensions for media policy"
```

---

### Task 3: Add Replicate File Upload Transport

**Files:**
- Modify: `src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs`
- Create: `src/Rook/Services/Vision/Image/Replicate/IReplicateFileTransport.cs`
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateFileTransport.cs`
- Modify: `src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs`

- [ ] **Step 1: Write failing API client upload tests**

Add these tests to `src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs`:

```csharp
        [Fact]
        public async Task UploadFileAsync_posts_multipart_to_files_endpoint()
        {
            string? contentType = null;
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    contentType = req.Content!.Headers.ContentType!.MediaType;
                    body = req.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                    return new HttpResponseMessage(HttpStatusCode.Created)
                    {
                        Content = new StringContent("""
                            {
                              "id": "file-1",
                              "name": "rook-flux2-source.png",
                              "content_type": "image/png",
                              "size": 9,
                              "urls": {
                                "get": "https://api.replicate.com/v1/files/file-1"
                              }
                            }
                            """, Encoding.UTF8, "application/json"),
                    };
                },
            };
            var client = new ReplicateApiClient(new HttpClient(handler));

            var result = await client.UploadFileAsync(
                "r8_token",
                "rook-flux2-source.png",
                new byte[] { 1, 2, 3 },
                "image/png",
                "{\"rook_usage\":\"flux2_input\"}",
                CancellationToken.None);

            Assert.Equal("https://api.replicate.com/v1/files/file-1", result.FileUrl.ToString());
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://api.replicate.com/v1/files", request.RequestUri!.ToString());
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", request.Headers.Authorization.Parameter);
            Assert.Equal("multipart/form-data", contentType);
            Assert.Contains("name=content", body);
            Assert.Contains("rook-flux2-source.png", body);
            Assert.Contains("name=metadata", body);
            Assert.Contains("flux2_input", body);
        }

        [Fact]
        public async Task UploadFileAsync_rejects_missing_file_url()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => new HttpResponseMessage(HttpStatusCode.Created)
                {
                    Content = new StringContent("""{ "id": "file-1", "urls": {} }""", Encoding.UTF8, "application/json"),
                },
            };
            var client = new ReplicateApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(() =>
                client.UploadFileAsync(
                    "r8_token",
                    "rook-flux2-source.png",
                    new byte[] { 1 },
                    "image/png",
                    "{}",
                    CancellationToken.None));
        }
```

- [ ] **Step 2: Run upload tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateApiClientTests
```

Expected: build fails because `UploadFileAsync` does not exist.

- [ ] **Step 3: Implement upload response type and method**

Modify `src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs`.

Add `using System.Net.Http;` already exists, add:

```csharp
using System.Text.Json;
using System.Text.Json.Nodes;
```

Add this nested public result type inside `ReplicateApiClient`:

```csharp
        public sealed class UploadedFile
        {
            public UploadedFile(string id, Uri fileUrl)
            {
                if (string.IsNullOrWhiteSpace(id))
                    throw new ArgumentException("Replicate file id must be non-empty.", nameof(id));
                ValidateApiUrl(fileUrl);
                Id = id;
                FileUrl = fileUrl;
            }

            public string Id { get; }
            public Uri FileUrl { get; }
        }
```

Add this method after `CancelPredictionAsync`:

```csharp
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
                throw new ArgumentException("Replicate upload file name must be non-empty.", nameof(fileName));
            if (bytes is null || bytes.Length == 0)
                throw new ArgumentException("Replicate upload bytes must be non-empty.", nameof(bytes));
            if (string.IsNullOrWhiteSpace(mimeType))
                throw new ArgumentException("Replicate upload MIME type must be non-empty.", nameof(mimeType));
            if (string.IsNullOrWhiteSpace(metadataJson))
                metadataJson = "{}";

            using var request = new HttpRequestMessage(HttpMethod.Post, BuildApiUri("v1/files"));
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
            var multipart = new MultipartFormDataContent();
            var content = new ByteArrayContent(bytes);
            content.Headers.ContentType = new MediaTypeHeaderValue(mimeType);
            multipart.Add(content, "content", fileName);
            var metadata = new StringContent(metadataJson, Encoding.UTF8, "application/json");
            multipart.Add(metadata, "metadata");
            request.Content = multipart;

            using var response = await _httpClient.SendAsync(request, ct).ConfigureAwait(false);
            var body = response.Content is null
                ? string.Empty
                : await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
                throw new HttpRequestException("Replicate file upload failed.");

            var root = JsonNode.Parse(body) as JsonObject
                ?? throw new ArgumentException("Replicate file upload response was not a JSON object.");
            var id = root["id"]?.GetValue<string>();
            var urlText = root["urls"]?["get"]?.GetValue<string>();
            if (string.IsNullOrWhiteSpace(id)
                || string.IsNullOrWhiteSpace(urlText)
                || !Uri.TryCreate(urlText, UriKind.Absolute, out var fileUrl))
            {
                throw new ArgumentException("Replicate file upload response was missing file id or urls.get.");
            }

            return new UploadedFile(id!, fileUrl);
        }
```

- [ ] **Step 4: Add file transport seam**

Create `src/Rook/Services/Vision/Image/Replicate/IReplicateFileTransport.cs`:

```csharp
using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    internal interface IReplicateFileTransport
    {
        Task<ReplicateFileUploadResult> UploadAsync(
            string apiToken,
            string fileName,
            byte[] bytes,
            string mimeType,
            CancellationToken ct);
    }

    internal sealed class ReplicateFileUploadResult
    {
        private ReplicateFileUploadResult(Uri? url, GenerationError? error)
        {
            Url = url;
            Error = error;
        }

        public Uri? Url { get; }
        public GenerationError? Error { get; }
        public bool Success => Url is not null && Error is null;

        public static ReplicateFileUploadResult Uploaded(Uri url) => new(url, null);
        public static ReplicateFileUploadResult Failed(GenerationError error) => new(null, error);
    }
}
```

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateFileTransport.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateFileTransport : IReplicateFileTransport
    {
        private readonly ReplicateApiClient _client;

        public ReplicateFileTransport(ReplicateApiClient client)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
        }

        public async Task<ReplicateFileUploadResult> UploadAsync(
            string apiToken,
            string fileName,
            byte[] bytes,
            string mimeType,
            CancellationToken ct)
        {
            try
            {
                var uploaded = await _client.UploadFileAsync(
                        apiToken,
                        fileName,
                        bytes,
                        mimeType,
                        new JsonObject { ["rook_usage"] = "flux2_input" }.ToJsonString(),
                        ct)
                    .ConfigureAwait(false);
                return ReplicateFileUploadResult.Uploaded(uploaded.FileUrl);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception)
            {
                return ReplicateFileUploadResult.Failed(new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate file upload transport is unavailable, so local Flux 2 Pro source images cannot be submitted.",
                    Retryable: true,
                    Field: "input_image_path"));
            }
        }
    }
}
```

- [ ] **Step 5: Run upload tests and commit**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateApiClientTests
```

Expected: PASS.

Commit:

```powershell
git add src/Rook/Services/Vision/Replicate/ReplicateApiClient.cs src/Rook/Services/Vision/Image/Replicate/IReplicateFileTransport.cs src/Rook/Services/Vision/Image/Replicate/ReplicateFileTransport.cs src/Rook.Tests/Services/Vision/Replicate/ReplicateApiClientTests.cs
git commit -m "feat: add Replicate file transport"
```

---

### Task 4: Replace Flux 2 Data URI Payload With Policy-Validated URL Payload

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageSourcePayload.cs`
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`

- [ ] **Step 1: Write failing provider tests for prompt-only, upload URL, and no data URI**

Update `ReplicateImageProviderTests`:

1. Change `SubmitAsync_flux2_prompt_only_fails_before_http_call` to expect success and one prediction POST without `input_images`.
2. Replace `SubmitAsync_flux2_posts_source_image_schema_with_data_uri_only_in_request_body` with a test named `SubmitAsync_flux2_uploads_source_and_posts_https_input_image_url`.
3. Change GIF unsupported theory so GIF is accepted in a dedicated test.

Use this replacement test body:

```csharp
        [Fact]
        public async Task SubmitAsync_flux2_prompt_only_posts_without_input_images()
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

            var outcome = await provider.SubmitAsync(
                Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "1:1"),
                EmptyMedia(),
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2", queued.Handle.ProviderJobId);
            Assert.DoesNotContain("input_images", requestBody);
            Assert.DoesNotContain("data:image/", requestBody);
        }

        [Fact]
        public async Task SubmitAsync_flux2_uploads_source_and_posts_https_input_image_url()
        {
            string? predictionBody = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.AbsolutePath == "/v1/files")
                    {
                        return Json(HttpStatusCode.Created, """
                            {
                              "id": "file-flux2",
                              "urls": { "get": "https://api.replicate.com/v1/files/file-flux2" }
                            }
                            """);
                    }

                    predictionBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
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
                [input] = PngMediaWithDimensions(1024, 768),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            Assert.Equal(2, handler.Requests.Count);
            Assert.Equal("https://api.replicate.com/v1/files", handler.Requests[0].RequestUri!.ToString());
            Assert.Equal("https://api.replicate.com/v1/models/black-forest-labs/flux-2-pro/predictions", handler.Requests[1].RequestUri!.ToString());

            var root = Assert.IsType<JsonObject>(JsonNode.Parse(predictionBody!));
            var inputJson = Assert.IsType<JsonObject>(root["input"]);
            var images = Assert.IsType<JsonArray>(inputJson["input_images"]);
            Assert.Equal("https://api.replicate.com/v1/files/file-flux2", Assert.Single(images)!.GetValue<string>());
            Assert.DoesNotContain("data:image/", predictionBody);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2", queued.Handle.ProviderJobId);
            Assert.NotNull(queued.Handle.ProviderMetadata);
            var metadata = queued.Handle.ProviderMetadata!;
            var urlsJson = metadata["urls"]!.ToJsonString();
            Assert.Contains("predictions/pred-flux2", urlsJson);
            Assert.DoesNotContain("/v1/files/file-flux2", urlsJson);
            Assert.DoesNotContain("data:image/", urlsJson);
            Assert.Null(queued.Handle.ProviderResultToken);
        }
```

Add helper:

```csharp
        private static ResolvedMedia PngMediaWithDimensions(int width, int height) =>
            new(PngBytes(width, height), "image/png");

        private static byte[] PngBytes(int width, int height)
        {
            var bytes = new byte[33];
            bytes[0] = 0x89; bytes[1] = 0x50; bytes[2] = 0x4E; bytes[3] = 0x47;
            bytes[4] = 0x0D; bytes[5] = 0x0A; bytes[6] = 0x1A; bytes[7] = 0x0A;
            bytes[12] = 0x49; bytes[13] = 0x48; bytes[14] = 0x44; bytes[15] = 0x52;
            WriteBigEndian(bytes, 16, width);
            WriteBigEndian(bytes, 20, height);
            return bytes;
        }

        private static void WriteBigEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)((value >> 24) & 0xFF);
            bytes[offset + 1] = (byte)((value >> 16) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 3] = (byte)(value & 0xFF);
        }
```

- [ ] **Step 2: Run provider tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateImageProviderTests
```

Expected: FAIL because Flux 2 Pro still requires source media and sends data URIs.

- [ ] **Step 3: Update source payload to URL-based media input**

Modify `src/Rook/Services/Vision/Image/Replicate/ReplicateImageSourcePayload.cs`.

Replace the `MaxRawBytes` data URI class with a payload that validates bytes and stores uploaded URLs:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateImageSourcePayload
    {
        private ReplicateImageSourcePayload(
            IReadOnlyList<ResolvedFlux2InputImage> localImages)
        {
            LocalImages = localImages;
        }

        public IReadOnlyList<ResolvedFlux2InputImage> LocalImages { get; }

        public static (ReplicateImageSourcePayload? Payload, GenerationError? Error) FromResolvedMedia(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (request is null) throw new ArgumentNullException(nameof(request));

            var policy = ReplicateImageCapabilities.Flux2ProMediaPolicy;
            var hasPrompt = !string.IsNullOrWhiteSpace(request.Prompt);

            if (media is null || media.Count == 0)
            {
                var promptOnlyPolicyResult = policy.ValidateInputSet(
                    mediaCount: 0,
                    aggregatePixels: 0,
                    hasPrompt: hasPrompt);
                if (!promptOnlyPolicyResult.Success)
                    return (null, InvalidSource(
                        promptOnlyPolicyResult.Message!,
                        promptOnlyPolicyResult.Field!));
                return (new ReplicateImageSourcePayload(Array.Empty<ResolvedFlux2InputImage>()), null);
            }

            if (media.Keys.Any(r => string.Equals(
                    r.Role,
                    ImageMediaRoles.ReferenceImage,
                    StringComparison.Ordinal)))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro reference images are policy-modeled but not exposed in this milestone.",
                    "reference_image_paths"));
            }

            var inputs = media
                .Where(kvp => string.Equals(
                    kvp.Key.Role,
                    ImageMediaRoles.InputImage,
                    StringComparison.Ordinal))
                .ToArray();

            if (inputs.Length > 1)
                return (null, InvalidSource(
                    "Flux 2 Pro accepts one primary source image in this milestone.",
                    "input_image_path"));

            if (inputs.Length == 0)
                return (new ReplicateImageSourcePayload(Array.Empty<ResolvedFlux2InputImage>()), null);

            var resolved = inputs[0].Value;
            if (resolved.Bytes is null || resolved.Bytes.Length == 0)
                return (null, InvalidSource("Flux 2 Pro source image is empty.", "input_image_path"));

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ImageMimeDetector.IsFlux2SupportedMime(detectedMime))
                return (null, InvalidSource(
                    "Flux 2 Pro source image must be PNG, JPEG, GIF, or WebP.",
                    "input_image_path"));

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image MIME does not match its bytes.",
                    "input_image_path"));
            }

            if (!ImageDimensions.TryRead(resolved.Bytes, detectedMime, out var dimensions))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image dimensions could not be read safely.",
                    "input_image_path"));
            }

            var policyResult = policy.ValidateInputSet(
                mediaCount: 1,
                aggregatePixels: dimensions.PixelCount,
                hasPrompt: hasPrompt);
            if (!policyResult.Success)
                return (null, InvalidSource(policyResult.Message!, policyResult.Field!));

            return (new ReplicateImageSourcePayload(new[]
            {
                new ResolvedFlux2InputImage(resolved.Bytes, detectedMime, dimensions),
            }), null);
        }

        private static GenerationError InvalidSource(string message, string field) =>
            new(
                Code: GenerationErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);
    }

    internal sealed class ResolvedFlux2InputImage
    {
        public ResolvedFlux2InputImage(byte[] bytes, string mimeType, ImageDimensions dimensions)
        {
            Bytes = bytes ?? throw new ArgumentNullException(nameof(bytes));
            MimeType = mimeType ?? throw new ArgumentNullException(nameof(mimeType));
            Dimensions = dimensions;
        }

        public byte[] Bytes { get; }
        public string MimeType { get; }
        public ImageDimensions Dimensions { get; }
    }
}
```

- [ ] **Step 4: Inject transport into provider and build URL request**

Modify `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`.

Add a field:

```csharp
        private readonly IReplicateFileTransport _fileTransport;
```

Change constructors to:

```csharp
        public ReplicateImageProvider(
            Func<string?> apiTokenProvider,
            ReplicateApiClient? client = null)
            : this(apiTokenProvider, client, fileTransport: null)
        {
        }

        internal ReplicateImageProvider(
            Func<string?> apiTokenProvider,
            ReplicateApiClient? client,
            IReplicateFileTransport? fileTransport)
        {
            _apiTokenProvider = apiTokenProvider
                ?? throw new ArgumentNullException(nameof(apiTokenProvider));
            _client = client ?? new ReplicateApiClient();
            _fileTransport = fileTransport ?? new ReplicateFileTransport(_client);
        }
```

Replace Flux 2 Pro source handling in `SubmitAsync`:

```csharp
            ReplicateImageSourcePayload? sourcePayload = null;
            if (string.Equals(request.Model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal))
            {
                var payload = ReplicateImageSourcePayload.FromResolvedMedia(request, resolvedMedia);
                if (payload.Error is not null)
                    return new FailedSubmitOutcome(payload.Error);
                sourcePayload = payload.Payload;
            }
```

Keep that validation, then after token validation and before `CreatePredictionAsync`, upload local inputs:

```csharp
            IReadOnlyList<Uri>? flux2InputUrls = null;
            if (sourcePayload is not null && sourcePayload.LocalImages.Count > 0)
            {
                var uploaded = await UploadFlux2InputsAsync(apiToken!, sourcePayload, ct)
                    .ConfigureAwait(false);
                if (uploaded.Error is not null)
                    return new FailedSubmitOutcome(uploaded.Error);
                flux2InputUrls = uploaded.Urls;
            }
```

Add helper:

```csharp
        private async Task<(IReadOnlyList<Uri>? Urls, GenerationError? Error)> UploadFlux2InputsAsync(
            string apiToken,
            ReplicateImageSourcePayload sourcePayload,
            CancellationToken ct)
        {
            var urls = new List<Uri>(sourcePayload.LocalImages.Count);
            foreach (var image in sourcePayload.LocalImages)
            {
                var upload = await _fileTransport.UploadAsync(
                        apiToken,
                        BuildFlux2UploadFileName(image.MimeType),
                        image.Bytes,
                        image.MimeType,
                        ct)
                    .ConfigureAwait(false);
                if (!upload.Success)
                    return (null, upload.Error);
                urls.Add(upload.Url!);
            }
            return (urls, null);
        }

        private static string BuildFlux2UploadFileName(string mimeType) =>
            $"rook-flux2-source-{Guid.NewGuid():N}.{ExtensionForMime(mimeType)}";

        private static string ExtensionForMime(string mimeType) =>
            mimeType switch
            {
                "image/png" => "png",
                "image/jpeg" => "jpg",
                "image/gif" => "gif",
                "image/webp" => "webp",
                _ => throw new ArgumentOutOfRangeException(nameof(mimeType)),
            };
```

Change request building signatures:

```csharp
        private static string BuildRequestJson(
            ImageGenerationRequest request,
            IReadOnlyList<Uri>? flux2InputUrls)
        {
            if (string.Equals(request.Model, ReplicateImageCapabilities.Flux2Pro, StringComparison.Ordinal))
                return BuildFlux2ProRequestJson(request, flux2InputUrls);

            return BuildFluxSchnellRequestJson(request);
        }
```

Change `BuildFlux2ProRequestJson`:

```csharp
        private static string BuildFlux2ProRequestJson(
            ImageGenerationRequest request,
            IReadOnlyList<Uri>? inputImageUrls)
        {
            var input = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["output_format"] = "png",
            };

            if (inputImageUrls is { Count: > 0 })
            {
                var inputImages = new JsonArray();
                foreach (var url in inputImageUrls)
                    inputImages.Add(url.ToString());
                input["input_images"] = inputImages;
                input["aspect_ratio"] = "match_input_image";
                input["resolution"] = "match_input_image";
            }
            else
            {
                input["aspect_ratio"] = string.IsNullOrWhiteSpace(request.AspectRatio)
                    ? "1:1"
                    : request.AspectRatio;
                input["resolution"] = string.IsNullOrWhiteSpace(request.Resolution)
                    ? "1MP"
                    : request.Resolution;
            }

            return new JsonObject
            {
                ["input"] = input,
            }.ToJsonString();
        }
```

Update the `CreatePredictionAsync` call:

```csharp
                        BuildRequestJson(request, flux2InputUrls),
```

- [ ] **Step 5: Run provider tests and commit**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateImageProviderTests
```

Expected: PASS after updating old assertions that expected GIF rejection or data URIs.

Commit:

```powershell
git add src/Rook/Services/Vision/Image/Replicate/ReplicateImageSourcePayload.cs src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs
git commit -m "feat: send Flux 2 inputs through Replicate files"
```

---

### Task 5: Correct Flux 2 Capability Without Enabling References

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`

- [ ] **Step 1: Update registration tests**

In `ReplicateImageProviderRegistrationTests`, change the Flux 2 assertions:

```csharp
            Assert.Equal(0, flux2.Capability.MaxReferenceImages);
            Assert.True(flux2.Capability.SupportsTextToImage);
            Assert.True(flux2.Capability.SupportsImageToImage);
```

Add an assertion for the internal policy:

```csharp
            Assert.Equal(8, ReplicateImageCapabilities.Flux2ProMediaPolicy.Model.MaxInputImages);
```

This keeps public reference controls gated while proving the model policy knows the provider's broader input count.

- [ ] **Step 2: Run registration tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateImageProviderRegistrationTests
```

Expected: FAIL because `SupportsTextToImage` is still false.

- [ ] **Step 3: Update capability metadata**

In `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`, update Flux 2 Pro:

```csharp
                [Flux2Pro] = new ImageCapability(
                    Id: Flux2Pro,
                    Name: "FLUX.2 Pro",
                    Status: "available",
                    Resolutions: new[] { "1MP" },
                    AspectRatios: new[] { "1:1", "4:3", "3:4", "16:9", "9:16", "match_input_image" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: true,
                    SupportsTextToImage: true),
```

`MaxReferenceImages` stays `0` in public capability metadata for milestone 1 so the UI and bridge do not enable references accidentally. The internal `Flux2ProMediaPolicy.Model.MaxInputImages == 8` is the provider policy source for future reference support.

- [ ] **Step 4: Update options codec for prompt-only Flux 2**

In `ReplicateImageOptionsCodec.Validate`, keep the generic reference rejection for public capability count:

```csharp
            var refCount = request.ReferenceImages?.Count ?? 0;
            if (refCount > capability.MaxReferenceImages)
            {
                return ValidationResult.Fail(
                    $"reference_image_paths are not supported for {capability.Name} in this milestone.",
                    "reference_image_paths");
            }
```

Keep aspect ratio validation as-is, now using the expanded Flux 2 aspect ratios.

- [ ] **Step 5: Run registration tests and commit**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateImageProviderRegistrationTests
```

Expected: PASS.

Commit:

```powershell
git add src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs
git commit -m "feat: correct Flux 2 image capabilities"
```

---

### Task 6: Apply Per-Model Resolver Limits In Vision Work Items

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Test: existing `src/Rook.Tests/Handlers/VisionHandlerTests.cs` or `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`

- [ ] **Step 1: Add failing work-item tests for Replicate cap separation**

Add these tests to `src/Rook.Tests/Handlers/VisionHandlerTests.cs` next to the existing artifact media limit tests. They use the fixture's existing `CreateTempRoot`, `ParseArgs`, `InMemoryGenerationSecretStore`, and `FakeImageProviderRegistration` helpers:

```csharp
        [Fact]
        public void BuildImageGenerationWorkItem_allows_flux2_local_source_over_gemini_inline_cap()
        {
            var root = CreateTempRoot("rook-vision-generate-flux2-large-source");
            try
            {
                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var imagePath = Path.Combine(root, "large-flux2.png");
                File.WriteAllBytes(imagePath, SizedPngBytes(12 * 1024 * 1024, width: 1024, height: 768));
                var provider = new FakeImageProvider(providerName: ReplicateImageCapabilities.ProviderName);
                var handler = new VisionHandler(
                    artifactStore,
                    new InMemoryGenerationSecretStore(),
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                    {
                        new FakeImageProviderRegistration(
                            provider,
                            ReplicateImageCapabilities.ProviderName,
                            ReplicateImageCapabilities.Flux2Pro,
                            resolutions: new[] { "1MP" },
                            aspectRatios: new[] { "match_input_image", "1:1" }),
                    }));
                var args = ParseArgs($$"""
                    {
                      "prompt": "massing study",
                      "model": "{{ReplicateImageCapabilities.Flux2Pro}}",
                      "resolution": "1MP",
                      "aspect_ratio": "match_input_image",
                      "input_image_path": "{{JsonEncodedText.Encode(imagePath)}}"
                    }
                    """);

                var result = handler.BuildImageGenerationWorkItem(
                    args,
                    VisionHandler.ImageGenerationWorkItemOptions.AsyncImageJob);

                Assert.True(result.Success);
                Assert.Single(result.WorkItem!.ResolvedMedia);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        [Fact]
        public void BuildImageGenerationWorkItem_keeps_gemini_local_source_inline_cap()
        {
            var root = CreateTempRoot("rook-vision-generate-gemini-large-source");
            try
            {
                var artifactStore = new ArtifactStore(Path.Combine(root, "artifacts"));
                var imagePath = Path.Combine(root, "large-gemini.png");
                File.WriteAllBytes(imagePath, SizedPngBytes(12 * 1024 * 1024, width: 1024, height: 768));
                var handler = new VisionHandler(
                    artifactStore,
                    new InMemoryGenerationSecretStore(),
                    new PromptEnhancer(),
                    new ViewportHandler(),
                    new DefaultImageProviderRegistry(new IImageProviderRegistration[]
                    {
                        new TestImageProviderRegistration(new FakeImageProvider()),
                    }));
                var args = ParseArgs($$"""
                    {
                      "prompt": "massing study",
                      "model": "{{GeminiImageCapabilities.DefaultModel}}",
                      "resolution": "1K",
                      "aspect_ratio": "1:1",
                      "input_image_path": "{{JsonEncodedText.Encode(imagePath)}}"
                    }
                    """);

                var result = handler.BuildImageGenerationWorkItem(args);

                Assert.False(result.Success);
                var message = Assert.IsType<string>(result.Failure?.Data);
                Assert.Contains("size limit", message);
            }
            finally
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }

        private static byte[] SizedPngBytes(int totalBytes, int width, int height)
        {
            var bytes = new byte[totalBytes];
            bytes[0] = 0x89; bytes[1] = 0x50; bytes[2] = 0x4E; bytes[3] = 0x47;
            bytes[4] = 0x0D; bytes[5] = 0x0A; bytes[6] = 0x1A; bytes[7] = 0x0A;
            bytes[12] = 0x49; bytes[13] = 0x48; bytes[14] = 0x44; bytes[15] = 0x52;
            WriteBigEndian(bytes, 16, width);
            WriteBigEndian(bytes, 20, height);
            return bytes;
        }

        private static void WriteBigEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)((value >> 24) & 0xFF);
            bytes[offset + 1] = (byte)((value >> 16) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 3] = (byte)(value & 0xFF);
        }
```

Keep these work-item tests limited to resolver cap selection. Do not test more than 8 input images or 9 MP aggregate here; those are policy/unit tests from Task 1 because milestone 1 still gates references before route-level requests can contain multiple images.

- [ ] **Step 2: Run route/work-item tests and verify Flux 2 fails**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~VisionHandlerTests
```

Expected: Flux 2 test fails because `VisionHandler` still uses `MaxInputImageBytes`.

- [ ] **Step 3: Add model-aware limit helpers**

In `VisionHandler.cs`, add internal helper:

```csharp
        private static (long SingleBytes, long AggregateBytes) MediaLimitsForModel(
            ResolvedImageModel resolvedModel)
        {
            if (string.Equals(
                    resolvedModel.ProviderName,
                    ReplicateImageCapabilities.ProviderName,
                    StringComparison.Ordinal)
                && string.Equals(
                    resolvedModel.ModelId,
                    ReplicateImageCapabilities.Flux2Pro,
                    StringComparison.Ordinal))
            {
                var safety = ReplicateImageCapabilities.Flux2ProMediaPolicy.Safety;
                return (safety.MaxSingleReadBytes, safety.MaxAggregateReadBytes);
            }

            return (MaxInputImageBytes, MaxAggregateImageBytes);
        }
```

Near the start of `BuildImageGenerationWorkItem`, after `resolvedModel` is known, add:

```csharp
            var mediaLimits = MediaLimitsForModel(resolvedModel);
```

Replace `MaxInputImageBytes` file checks in that method with `mediaLimits.SingleBytes`.
Replace `MaxAggregateImageBytes` checks with `mediaLimits.AggregateBytes`.

Change `ResolveImageMediaRefs` signature:

```csharp
        private MediaResolutionResult ResolveImageMediaRefs(
            IReadOnlyList<MediaRef> refs,
            long maxSingleImageBytes,
            long maxAggregateImageBytes)
            => new ArtifactImageMediaResolver(
                    _artifactStore,
                    maxSingleImageBytes,
                    maxAggregateImageBytes)
                .ResolveAllAsync(refs, CancellationToken.None)
                .GetAwaiter().GetResult();
```

Update the call site:

```csharp
            var mediaResolution = ResolveImageMediaRefs(
                mediaRefs,
                mediaLimits.SingleBytes,
                mediaLimits.AggregateBytes);
```

- [ ] **Step 4: Run route/work-item tests and commit**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~VisionHandlerTests
```

Expected: PASS for the focused tests.

Commit:

```powershell
git add src/Rook/Handlers/VisionHandler.cs src/Rook.Tests/Handlers/VisionHandlerTests.cs
git commit -m "feat: apply model media resolver limits"
```

---

### Task 7: Add Leakage And Regression Checks

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs` if existing leakage tests serialize image job ledgers/responses

- [ ] **Step 1: Add provider-level no-transport-leak assertions**

In `ReplicateImageProviderTests`, add:

```csharp
        [Fact]
        public async Task SubmitAsync_flux2_does_not_store_upload_url_in_handle()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.AbsolutePath == "/v1/files")
                    {
                        return Json(HttpStatusCode.Created, """
                            {
                              "id": "file-secret",
                              "urls": { "get": "https://api.replicate.com/v1/files/file-secret" }
                            }
                            """);
                    }

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
                [input] = PngMediaWithDimensions(512, 512),
            };

            var outcome = await provider.SubmitAsync(
                Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2", queued.Handle.ProviderJobId);
            Assert.NotNull(queued.Handle.ProviderMetadata);
            var metadata = queued.Handle.ProviderMetadata!;
            var urlsJson = metadata["urls"]!.ToJsonString();
            Assert.Contains("predictions/pred-flux2", urlsJson);
            Assert.DoesNotContain("/v1/files/file-secret", urlsJson);
            Assert.DoesNotContain("data:image/", urlsJson);
            Assert.Null(queued.Handle.ProviderResultToken);
            Assert.DoesNotContain("file-secret", queued.Handle.ProviderJobId);
        }
```

- [ ] **Step 2: Run provider tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ReplicateImageProviderTests
```

Expected: PASS.

- [ ] **Step 3: Preserve output URL materialization tests**

Run existing image job tests:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter FullyQualifiedName~ImageJobManagerTests
```

Expected: PASS. A failure that names `replicate.delivery` in a materialization path means a leakage guard overmatched output URLs; change that guard to reject only source/upload/request transport URLs in durable/public payloads, then rerun this command. Do not remove authenticated output materialization.

- [ ] **Step 4: Commit leakage test changes**

Commit:

```powershell
git add src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs
git commit -m "test: guard Flux 2 transport URL leakage"
```

---

### Task 8: Run Final Verification And Source Scans

**Files:**
- No planned source edits unless verification exposes a failing assertion.

- [ ] **Step 1: Run focused test set**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ImageMediaPolicyTests|FullyQualifiedName~ImageDimensionsTests|FullyQualifiedName~ReplicateApiClientTests|FullyQualifiedName~ReplicateImageProviderTests|FullyQualifiedName~ReplicateImageProviderRegistrationTests|FullyQualifiedName~VisionHandlerTests|FullyQualifiedName~ImageJobManagerTests"
```

Expected: PASS.

- [ ] **Step 2: Run full managed tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj
```

Expected: PASS.

- [ ] **Step 3: Scan for removed arbitrary cap and transport leakage risk**

Run:

```powershell
rg -n "MaxRawBytes|1024 \\* 1024|data:image/|input_images" src/Rook/Services/Vision/Image/Replicate src/Rook.Tests/Services/Vision/Image/Replicate
rg -n "replicate.delivery|api.replicate.com/v1/files|data:image/" src/Rook/Services/Vision/Image/Jobs src/Rook.Tests/Services/Vision/Image/Jobs
```

Expected:

- No `MaxRawBytes` in Replicate Flux 2 source code.
- No `1024 * 1024` source cap in Replicate Flux 2 source code.
- `data:image/` may remain only in tests that prove it is absent or in non-Flux2 legacy assertions.
- `api.replicate.com/v1/files` appears only in transport/client tests and upload implementation.
- Existing `replicate.delivery` output materialization tests may remain.

- [ ] **Step 4: Verify no native or MCP changes**

Run:

```powershell
git diff --name-only HEAD~7..HEAD
```

Expected: changed files are under `src/Rook/**`, `src/Rook.Tests/**`, and docs only. No `src/RookNative/**` or `mcp_server/**`.

---

## Self-Review

- Spec coverage:
  - Provider-specific media transport: Tasks 3 and 4.
  - Model/transport/Rook safety policy split: Task 1.
  - Flux 2 Pro prompt-only support: Tasks 4 and 5.
  - Single primary local source image URL transport: Tasks 3 and 4.
  - References policy-modeled but gated: Tasks 1, 5, and 6.
  - 9 MP validation as policy/unit test: Task 1, with provider validation in Task 4.
  - More than 8 images as policy/unit test: Task 1 only, not route-level.
  - GIF support and safe dimensions: Task 2 and Task 4.
  - Gemini/fal no-regression: Tasks 6 and 8.
  - Source/upload/request URL leakage only: Task 7.
- Placeholder scan: no blocked placeholder markers or vague validation steps remain.
- Type consistency:
  - `ImageMediaPolicy`, `ImageModelInputPolicy`, `ImageTransportPolicy`, and `ImageRookSafetyPolicy` are defined before later tasks use them.
  - `IReplicateFileTransport` is defined before `ReplicateImageProvider` injection.
  - `ImageDimensions` is defined before Flux 2 source validation uses it.
