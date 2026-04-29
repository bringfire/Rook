# Fal Sync Image Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement PR-7 as the first shippable fal image provider integration: register `fal-ai/flux/schnell`, submit sync text-to-image requests through the PR-6 fal substrate, materialize remote image URL results into the existing `ArtifactStore`, and add provider-level pricing/secret metadata without changing native, UI, MCP, or video route contracts.

**Architecture:** Managed-only image-provider slice. Add a `Rook.Services.Vision.Image.Fal` provider package parallel to Gemini, add a provider-agnostic image artifact materializer used by `VisionHandler.GenerateAsync`, and register fal alongside Gemini in the default managed image registry. Keep fal-specific request/response details behind provider/codec/pricing classes so the shared image contract does not silently become the fal contract.

**Tech Stack:** C# net48 managed companion, existing `HttpClient`, `System.Text.Json.Nodes`, existing `ArtifactStore`, existing `Rook.Services.Vision.Generation` substrate, existing xUnit test suite. No new external dependencies.

---

## Sources And Current Evidence

- PR-5 design doc: `docs/rook_docs/2026-04-29-multi-provider-phase2-fal-plan.md`
- PR-6 substrate plan and committed implementation: `docs/superpowers/plans/2026-04-29-fal-substrate-secret-metadata.md`
- Official fal Flux Schnell docs verified on 2026-04-29: https://fal.ai/docs/model-api-reference/image-generation-api/flux-schnell

Current fal evidence from the official docs:

- Endpoint: `POST https://fal.run/fal-ai/flux/schnell`
- Endpoint ID: `fal-ai/flux/schnell`
- Required input: `prompt`
- Supported `image_size` values include `square_hd`, `square`, `portrait_4_3`, `portrait_16_9`, `landscape_4_3`, `landscape_16_9`
- Default `num_images` is `1`, supported range is `1` to `4`
- Default `enable_safety_checker` is `true`
- Default `output_format` is `jpeg`
- Output includes `images[]` entries with `url` and `content_type`
- Published pricing text says `$0.003 per megapixel`, billed by rounding up to the nearest megapixel

The implementation must keep the pricing source/provenance date-stamped. If the fal page changes before execution, update the constants and tests before coding.

---

## Scope

### In Scope

- Add fal sync image provider support for `fal-ai/flux/schnell`.
- Register the fal provider in the default managed image registry.
- Add fal image capability, options codec, provider registration, provider implementation, and pricing model.
- Add remote image artifact materialization for URL-backed provider artifacts.
- Keep Gemini image generation behavior compatible.
- Preserve PR-6 fal secret requirement shape with `GenerationSecretKeys.FalApiKey`.
- Add unit tests for codec validation, provider request/response parsing, pricing, registration metadata, and remote materialization.
- Add an opt-in live smoke test gated by environment variables and explicit spend opt-in.

### Out Of Scope

- No native route changes in `src/RookNative/**`.
- No MCP schema changes in `mcp_server/**`.
- No chat panel or picker UI changes.
- No settings UI changes beyond using the already-committed PR-6 secret key contract.
- No PR-8 fal video implementation.
- No Replicate, Tencent, or dynamic catalog implementation.
- No prompt-only `/vision/generate` public route change.

### Important Route Constraint

The existing public `/vision/generate` route requires `input_image_path`. PR-7 must not widen the native/MCP/UI route contract. The fal Flux Schnell model is text-to-image, so in PR-7:

- The route still accepts and validates `input_image_path`.
- The managed fal provider ignores the primary input image.
- `reference_image_paths` are rejected by the fal options codec because `fal-ai/flux/schnell` is text-to-image.
- Prompt-only ergonomics are deferred to a later route/UI contract PR.

This avoids accidental native/public-surface drift while making fal usable through exact model selection.

---

## Contract Invariants

PR-7 must preserve these PR-5/PR-6 invariants:

- **Lifecycle:** `fal-ai/flux/schnell` returns a `SyncSubmitOutcome` with an inner `SuccessResultOutcome` or typed failure.
- **Secret namespace:** fal uses `GenerationSecretKeys.FalApiKey` through `FalSecretKeys.ApiKey`.
- **Secret metadata:** fal registration exposes `SecretRequirements`, not the older required-only naming from PR-4.
- **Provider isolation:** fal request fields such as `image_size`, `sync_mode`, and `output_format` remain local to the fal provider/codec.
- **Artifact shape:** fal returns `RemoteArtifactBody`; Gemini keeps returning `InlineArtifactBody`.
- **Route behavior:** `/vision/generate` materializes either inline or remote image artifacts before writing the `ArtifactStore`.
- **Pricing:** estimate and actual-spend extraction live in a fal pricing model; no universal fal header formula leaks into shared code.
- **Error hygiene:** route responses stay sanitized; raw provider envelopes stay only in `GenerationError.ProviderDetail` or provider metadata.

---

## Provider-Agnostic Pressure Checks

| fal decision | Replicate pressure | Gemini/Veo pressure | Tencent pressure | contract consequence | deferred work |
| --- | --- | --- | --- | --- | --- |
| fal image provider returns `RemoteArtifactBody` from `images[0].url` | Replicate also returns flat URL outputs | Gemini image returns inline bytes; Veo materializes separately today | Tencent may return object storage URLs | Add provider-agnostic image materializer in managed image layer | Shared artifact downloader hardening can expand later |
| fal codec maps Rook aspect ratio to fal `image_size` | Replicate models use different input field names | Gemini uses aspect ratio directly | Tencent may use width/height or ratio enums | Keep mapping inside fal codec/provider | Per-route model descriptors later |
| fal Flux Schnell ignores primary source image | Replicate text-to-image models may also ignore source media | Gemini route uses primary image today | Tencent has different operation modes | Current route contract remains unchanged | Prompt-only route contract later |
| fal pricing uses per-megapixel estimate plus billable-unit header extraction | Replicate pricing may be per prediction or hardware time | Gemini token pricing differs; Veo per-second differs | Tencent likely account/billing API driven | Pricing model stays per provider/model | Dynamic pricing refresh later |
| fal uses one required API key | Replicate uses one API token | Gemini uses one API key | Tencent may require paired keys plus optional STS | Static `SecretRequirements` stays provider-level | Operation-scoped credential overlays later |

---

## Files To Add

- `src/Rook/Services/Vision/Image/Fal/FalImageCapabilities.cs`
- `src/Rook/Services/Vision/Image/Fal/FalImageOptions.cs`
- `src/Rook/Services/Vision/Image/Fal/FalImageOptionsCodec.cs`
- `src/Rook/Services/Vision/Image/Fal/FalFluxSchnellPricingModel.cs`
- `src/Rook/Services/Vision/Image/Fal/FalImageProvider.cs`
- `src/Rook/Services/Vision/Image/Fal/FalImageProviderRegistration.cs`
- `src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalImageOptionsCodecTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalFluxSchnellPricingModelTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderRegistrationTests.cs`
- `src/Rook.Tests/Services/Vision/Image/ImageArtifactMaterializerTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalImageLiveSmokeTests.cs`

## Files To Modify

- `src/Rook/Handlers/VisionHandler.cs`
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Potentially `src/Rook/Rook.csproj` only if this repo requires explicit compile includes. First inspect project style. Do not modify project files if SDK/glob includes already cover new `.cs` files.

## Files Not To Touch

- `src/RookNative/**`
- `mcp_server/**`
- `src/Rook/Resources/**` UI assets
- `docs/rook_docs/2026-04-29-multi-provider-phase2-fal-plan.md` except if a review explicitly asks to clarify PR-7 follow-up docs
- PR-6 substrate files except for tests if a compile issue reveals a genuine local helper gap

---

## Phase 1: Capability, Options, And Registration

### Tests First

- [ ] Add `FalImageOptionsCodecTests`.
- [ ] Add `FalImageProviderRegistrationTests`.

Required test cases:

- Empty options JSON deserializes to `FalImageOptions`.
- Non-empty provider options JSON fails with `InvalidRequest`.
- Codec accepts `NumberOfImages = 1`.
- Codec rejects `NumberOfImages != 1`.
- Codec rejects reference images.
- Codec accepts only capability-supported resolutions.
- Codec accepts only fal-supported aspect ratios.
- Aspect ratio mapping:
  - empty or whitespace -> `landscape_4_3`
  - `1:1` -> `square_hd`
  - `4:3` -> `landscape_4_3`
  - `3:4` -> `portrait_4_3`
  - `16:9` -> `landscape_16_9`
  - `9:16` -> `portrait_16_9`
- Registration exposes provider name `fal`.
- Registration exposes one required secret requirement with key `GenerationSecretKeys.FalApiKey`.
- Registration exposes `fal-ai/flux/schnell` with provider pricing source.

### Implementation

- [ ] Add `FalImageCapabilities`.

Expected shape:

```csharp
namespace Rook.Services.Vision.Image.Fal
{
    public static class FalImageCapabilities
    {
        public const string ProviderName = "fal";
        public const string FluxSchnell = "fal-ai/flux/schnell";
        public const string DefaultModel = FluxSchnell;

        public static readonly IReadOnlyDictionary<string, ImageCapability> Models =
            new Dictionary<string, ImageCapability>(StringComparer.Ordinal)
            {
                [FluxSchnell] = new ImageCapability(
                    Id: FluxSchnell,
                    Name: "FLUX.1 Schnell",
                    Status: "available",
                    Resolutions: new[] { "1K" },
                    AspectRatios: new[] { "1:1", "4:3", "3:4", "16:9", "9:16" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: false,
                    SupportsTextToImage: true),
            };
    }
}
```

- [ ] Add `FalImageOptions`.

Expected shape:

```csharp
namespace Rook.Services.Vision.Image.Fal
{
    public sealed record FalImageOptions : ProviderOptions;
}
```

- [ ] Add `FalImageOptionsCodec`.

Key details:

- Match `GeminiImageOptionsCodec` style.
- Keep provider-specific fal fields out of shared `ImageGenerationRequest`.
- `Serialize` can return an empty `JsonObject`; the provider builds the fal request body because it needs the full `ImageGenerationRequest`, not only `ProviderOptions`.
- Add a public/internal static helper for aspect mapping so tests can pin it.

Expected helper:

```csharp
internal static string ToFalImageSize(string? aspectRatio)
{
    if (string.IsNullOrWhiteSpace(aspectRatio))
        return "landscape_4_3";

    return aspectRatio switch
    {
        "1:1" => "square_hd",
        "4:3" => "landscape_4_3",
        "3:4" => "portrait_4_3",
        "16:9" => "landscape_16_9",
        "9:16" => "portrait_16_9",
        _ => throw new ArgumentException(
            $"Unsupported fal image aspect ratio '{aspectRatio}'.",
            nameof(aspectRatio)),
    };
}
```

- [ ] Add `FalImageProviderRegistration`.

Expected registration:

```csharp
public sealed class FalImageProviderRegistration : IImageProviderRegistration
{
    public FalImageProviderRegistration(IImageProvider provider)
    {
        Provider = provider ?? throw new ArgumentNullException(nameof(provider));
    }

    public string ProviderName => FalImageCapabilities.ProviderName;
    public IImageProvider Provider { get; }
    public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
        = new FalImageOptionsCodec();

    public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

    private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
        Array.AsReadOnly(new[]
        {
            new ProviderSecretRequirement(
                GenerationSecretKeys.FalApiKey,
                "fal API key",
                isRequired: true),
        });

    public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models
        => _models;

    private static readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models =
        new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal)
        {
            [FalImageCapabilities.FluxSchnell] = (
                FalImageCapabilities.Models[FalImageCapabilities.FluxSchnell],
                new FalFluxSchnellPricingModel()),
        };
}
```

### Commit Gate

- [ ] Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalImageOptionsCodecTests|FullyQualifiedName~FalImageProviderRegistrationTests" -p:RhinoPluginDir=
```

Expected if RhinoCommon is available through the PR-6 test fix:

```text
Passed! - Failed: 0
```

- [ ] Commit message:

```text
test(vision): define fal image capability and option contract
```

---

## Phase 2: fal Pricing Model

### Tests First

- [ ] Add `FalFluxSchnellPricingModelTests`.

Required test cases:

- `PricingSource` is date-stamped and fal/model-specific.
- `MetadataLocation` is `PricingMetadataLocation.ResponseHeader`.
- `Estimate` returns a successful non-negative result for `1K` capability.
- `Estimate` uses a non-exact megapixel-rounded range unless exact preset dimensions are verified during execution.
- `ExtractActualSpend` returns null when `x-fal-billable-units` is absent.
- `ExtractActualSpend` returns null for invalid or negative billable units.
- `ExtractActualSpend` parses decimal billable units using invariant culture through `FalPricingHelpers`.
- `ExtractActualSpend` multiplies parsed billable units by the model unit price.

### Implementation

- [ ] Add `FalFluxSchnellPricingModel`.

Use official docs evidence from 2026-04-29:

- Unit: `megapixel`
- Unit price: `0.003m`
- Pricing source: `fal-ai/flux/schnell-megapixel-2026-04-29`
- Estimate provenance: `fal-ai/flux/schnell-pricing-page-2026-04-29`

Important: The pricing model is the only place that interprets `x-fal-billable-units` for Flux Schnell. `FalPricingHelpers` only extracts a provider-reported number.

Do not mark submit-time estimates exact unless execution verifies the exact pixel dimensions for every exposed fal preset. The official docs list preset names and the billing rule, but the visible API reference does not provide all preset pixel dimensions. PR-7 should therefore use a bounded estimate and rely on `x-fal-billable-units` for actual spend extraction.

Suggested implementation details:

```csharp
public sealed class FalFluxSchnellPricingModel
    : IPricingModel<ImageGenerationRequest, ImageCapability>
{
    public const string Source = "fal-ai/flux/schnell-megapixel-2026-04-29";
    public const string Provenance = "fal-ai/flux/schnell-pricing-page-2026-04-29";
    internal const decimal UnitPriceUsdPerMegapixel = 0.003m;

    public string PricingSource => Source;
    public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseHeader;

    public PricingResult Estimate(ImageGenerationRequest request, ImageCapability capability)
    {
        if (request is null)
            return PricingResult.Fail(new GenerationError(
                GenerationErrorCode.InvalidRequest,
                "Image generation request is null.",
                Retryable: false,
                Field: "request"));

        var minBillableMegapixels = 1m;
        var maxBillableMegapixels = 2m;
        var minTotal = minBillableMegapixels * UnitPriceUsdPerMegapixel;
        var maxTotal = maxBillableMegapixels * UnitPriceUsdPerMegapixel;

        return PricingResult.Ok(
            new JobPricing(
                Currency: "USD",
                UnitPrice: UnitPriceUsdPerMegapixel,
                Unit: "megapixel",
                Quantity: null,
                TotalUsd: null,
                PricingSource: Source),
            new CostEstimate(
                Min: minTotal,
                Max: maxTotal,
                IsExact: false,
                Provenance: Provenance));
    }

    public JobPricing? ExtractActualSpend(
        IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
        JsonNode? responseBody)
    {
        if (!FalPricingHelpers.TryGetBillableUnits(responseHeaders, out var units))
            return null;

        return new JobPricing(
            Currency: "USD",
            UnitPrice: UnitPriceUsdPerMegapixel,
            Unit: "megapixel",
            Quantity: units,
            TotalUsd: units * UnitPriceUsdPerMegapixel,
            PricingSource: Source);
    }
}
```

Rationale: the fal docs say billing rounds up to the nearest megapixel, but PR-7 does not expose exact custom width/height. If execution verifies exact dimensions for every exposed preset from an authoritative fal source, it may tighten the estimate and tests in the same PR. Otherwise keep this range conservative and let `ExtractActualSpend` provide exact provider-reported usage after the response.

### Commit Gate

- [ ] Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalFluxSchnellPricingModelTests" -p:RhinoPluginDir=
```

- [ ] Commit message:

```text
feat(vision): add fal image pricing model
```

---

## Phase 3: fal Image Provider

### Tests First

- [ ] Add `FalImageProviderTests`.

Required test cases:

- Missing fal API key returns `FailedSubmitOutcome` with `DependencyUnavailable`, no HTTP call.
- Wrong options type returns `FailedSubmitOutcome` with `InvalidRequest`.
- Successful submit posts to `https://fal.run/fal-ai/flux/schnell`.
- Request includes:
  - `prompt`
  - `image_size`
  - `num_images = 1`
  - `enable_safety_checker = true`
  - `output_format = "jpeg"`
  - `sync_mode = false`
- Provider uses `Authorization: Key <key>` through `FalApiClient`.
- Non-success HTTP maps through `FalErrorMapper`.
- Malformed JSON returns `SyncSubmitOutcome` with an inner `FailedResultOutcome`.
- Missing `images` returns `FailedResultOutcome`.
- Empty `images` returns `FailedResultOutcome`.
- Missing or invalid image URL returns `FailedResultOutcome`.
- Non-HTTP image URL is rejected by `RemoteArtifactBody` invariant and surfaced as provider result failure.
- Valid response returns `SyncSubmitOutcome` with an inner `SuccessResultOutcome`.
- Result artifact:
  - role is `ImageMediaRoles.Image`
  - body is `RemoteArtifactBody`
  - declared MIME comes from `content_type`
  - provider metadata includes URL and dimensions when present
  - envelope metadata includes `seed`, `prompt`, `timings`, and `has_nsfw_concepts` when present

### Implementation

- [ ] Add `FalImageProvider`.

Implementation guidance:

- Constructor:

```csharp
public FalImageProvider(Func<string?> apiKeyProvider, FalApiClient? client = null)
```

- Store `apiKeyProvider` and `client ?? new FalApiClient()`.
- `ProviderName => FalImageCapabilities.ProviderName`.
- Use endpoint:

```csharp
private static readonly Uri FluxSchnellEndpoint =
    new Uri("https://fal.run/fal-ai/flux/schnell");
```

- Build JSON with `System.Text.Json.Nodes` or `Utf8JsonWriter`; avoid string concatenation.
- Do not include the input image bytes in the fal request.
- Do not log or persist the API key.
- HTTP failure path:

```csharp
if (!response.IsSuccessStatusCode)
    return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(response));
```

- Success parse path:

```csharp
JsonNode? root;
try
{
    root = JsonNode.Parse(response.Body);
}
catch (JsonException ex)
{
    return SyncFailure("fal image response was not valid JSON.", ex.Message);
}
```

- Keep public route messages sanitized. Any raw response body should only be in `ProviderDetail` when an error mapper already owns it.
- `GetStatusAsync`, `CancelAsync`, and `FetchResultAsync` should throw `InvalidOperationException`, matching the current Gemini sync provider pattern.

### Provider Error Shape

For provider-local result parsing failures, use typed errors:

```csharp
new GenerationError(
    Code: GenerationErrorCode.ExecutionFailed,
    Message: "fal image response did not contain a usable image URL.",
    Retryable: false,
    Field: "images")
```

Do not include the full fal response body in `Message`.

### Commit Gate

- [ ] Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalImageProviderTests" -p:RhinoPluginDir=
```

- [ ] Commit message:

```text
feat(vision): add fal sync image provider
```

---

## Phase 4: Image Artifact Materialization

### Tests First

- [ ] Add `ImageArtifactMaterializerTests`.

Required test cases:

- Inline artifact returns existing bytes without HTTP.
- Inline artifact requires declared MIME through existing `ResultArtifact` invariant.
- Remote artifact fetches URL and returns response bytes.
- Remote artifact uses provider-declared MIME when present.
- Remote artifact falls back to response `Content-Type` when declared MIME is absent.
- Remote artifact falls back to `image/png` if neither declared nor response MIME exists.
- Remote artifact rejects non-success HTTP status.
- Remote artifact rejects empty response bytes.
- Remote artifact rejects `Content-Length` greater than max before reading.
- Remote artifact rejects read bytes greater than max after reading.
- Remote artifact does not add fal authorization headers. CDN artifact URLs are not fal API calls.

### Implementation

- [ ] Add `ImageArtifactMaterializer`.

Expected API:

```csharp
internal sealed class ImageArtifactMaterializer
{
    internal const long MaxGeneratedImageBytes = 25L * 1024 * 1024;

    public ImageArtifactMaterializer(HttpClient? httpClient = null)
    {
        _httpClient = httpClient ?? new HttpClient();
    }

    public async Task<ImageArtifactMaterializationResult> MaterializeAsync(
        ResultArtifact artifact,
        CancellationToken cancellationToken)
}
```

Add a small internal result type in the same file:

```csharp
internal sealed class ImageArtifactMaterializationResult
{
    private ImageArtifactMaterializationResult(
        bool success,
        byte[]? bytes,
        string? mimeType,
        GenerationError? error)
    {
        Success = success;
        Bytes = bytes;
        MimeType = mimeType;
        Error = error;
    }

    public bool Success { get; }
    public byte[]? Bytes { get; }
    public string? MimeType { get; }
    public GenerationError? Error { get; }

    public static ImageArtifactMaterializationResult Ok(
        byte[] bytes, string mimeType) =>
        new ImageArtifactMaterializationResult(true, bytes, mimeType, null);

    public static ImageArtifactMaterializationResult Fail(
        GenerationError error) =>
        new ImageArtifactMaterializationResult(false, null, null, error);
}
```

Implementation rules:

- For `InlineArtifactBody`, return `inline.Bytes` and `artifact.DeclaredMimeType`.
- For `RemoteArtifactBody`, use plain `HttpClient.SendAsync` with `HttpCompletionOption.ResponseHeadersRead`.
- Do not use `FalApiClient` for artifact downloads because fal output URLs may be CDN URLs outside `fal.run` and should not receive provider API credentials.
- Check `response.Content.Headers.ContentLength` before reading. If it is greater than `MaxGeneratedImageBytes`, return an oversize `ExecutionFailed` error without reading the body.
- Copy the response stream into a `MemoryStream` with a hard cap. Stop and fail if the accumulated bytes exceed `MaxGeneratedImageBytes`, even when `Content-Length` is missing or wrong.
- Do not add authorization headers to the artifact download request.
- Sanitize failure messages. Example:

```text
Remote image artifact fetch failed with HTTP 404.
```

- Use `GenerationErrorCode.DependencyUnavailable` for remote fetch failures and `ExecutionFailed` for empty/oversize bodies.

Expected remote fetch shape:

```csharp
using var request = new HttpRequestMessage(HttpMethod.Get, remote.Url);
using var response = await _httpClient.SendAsync(
    request,
    HttpCompletionOption.ResponseHeadersRead,
    cancellationToken).ConfigureAwait(false);

if (!response.IsSuccessStatusCode)
{
    return ImageArtifactMaterializationResult.Fail(new GenerationError(
        GenerationErrorCode.DependencyUnavailable,
        $"Remote image artifact fetch failed with HTTP {(int)response.StatusCode}.",
        Retryable: (int)response.StatusCode >= 500));
}

var contentLength = response.Content.Headers.ContentLength;
if (contentLength is { } length && length > MaxGeneratedImageBytes)
{
    return ImageArtifactMaterializationResult.Fail(new GenerationError(
        GenerationErrorCode.ExecutionFailed,
        "Remote image artifact exceeds the maximum generated image size.",
        Retryable: false));
}

using var stream = await response.Content
    .ReadAsStreamAsync()
    .ConfigureAwait(false);
using var buffer = new MemoryStream();
var temp = new byte[81920];
while (true)
{
    var read = await stream
        .ReadAsync(temp, 0, temp.Length, cancellationToken)
        .ConfigureAwait(false);
    if (read == 0) break;
    if (buffer.Length + read > MaxGeneratedImageBytes)
    {
        return ImageArtifactMaterializationResult.Fail(new GenerationError(
            GenerationErrorCode.ExecutionFailed,
            "Remote image artifact exceeds the maximum generated image size.",
            Retryable: false));
    }
    buffer.Write(temp, 0, read);
}

if (buffer.Length == 0)
{
    return ImageArtifactMaterializationResult.Fail(new GenerationError(
        GenerationErrorCode.ExecutionFailed,
        "Remote image artifact was empty.",
        Retryable: false));
}

var observedMimeType = response.Content.Headers.ContentType?.MediaType;
var mimeType = !string.IsNullOrWhiteSpace(artifact.DeclaredMimeType)
    ? artifact.DeclaredMimeType!
    : !string.IsNullOrWhiteSpace(observedMimeType)
        ? observedMimeType!
        : "image/png";

return ImageArtifactMaterializationResult.Ok(
    buffer.ToArray(),
    mimeType);
```

### Commit Gate

- [ ] Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~ImageArtifactMaterializerTests" -p:RhinoPluginDir=
```

- [ ] Commit message:

```text
feat(vision): materialize remote image artifacts
```

---

## Phase 5: Wire fal Into VisionHandler

### Tests First

- [ ] Update `VisionHandlerTests`.

Required tests:

- Existing Gemini registry tests still pass unchanged.
- Default registry can resolve `fal-ai/flux/schnell`.
- Exact fal model ID wins before Gemini short-name fallback.
- Missing fal key surfaces the provider message without requiring Gemini key.
- `GenerateAsync` can persist a remote provider artifact through `ImageArtifactMaterializer`.
- Remote materialization failure returns a sanitized route failure.
- Existing inline fake provider path still writes artifact metadata exactly as before.

### Implementation

- [ ] Add `using Rook.Services.Vision.Image.Fal;`.
- [ ] Add an `_imageArtifactMaterializer` field.
- [ ] Extend internal constructors with optional `ImageArtifactMaterializer? imageArtifactMaterializer = null` for tests.

Preserve existing overloads by adding the new optional parameter only at the end.

Expected private constructor addition:

```csharp
private readonly ImageArtifactMaterializer _imageArtifactMaterializer;
```

```csharp
_imageArtifactMaterializer = imageArtifactMaterializer ?? new ImageArtifactMaterializer();
```

- [ ] Register fal in the default image provider registry:

```csharp
_imageProviderRegistry = imageProviderRegistry
    ?? new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new GeminiImageProviderRegistration(
            new GeminiImageProvider(GetGeminiApiKey)),
        new FalImageProviderRegistration(
            new FalImageProvider(GetFalApiKey)),
    });
```

- [ ] Add `GetFalApiKey`.

```csharp
private string? GetFalApiKey()
{
    if (_generationSecrets is not null)
        return _generationSecrets.GetSecret(GenerationSecretKeys.FalApiKey);
    return null;
}
```

Rationale: the legacy `VisionSecretStore` is Gemini-only. fal requires the PR-6 `IGenerationSecretStore` path.

- [ ] Replace inline-only extraction in `GenerateAsync`.

Current code rejects non-inline bodies:

```csharp
var providerArtifact = success.Envelope.Artifacts.FirstOrDefault();
if (providerArtifact?.Body is not InlineArtifactBody inline)
{
    return Fail("Image generation failed. Provider result did not contain an inline image artifact.");
}

var imageBytes = inline.Bytes;
var mimeType = providerArtifact.DeclaredMimeType ?? "image/png";
```

Replace with materialization:

```csharp
var providerArtifact = success.Envelope.Artifacts
    .FirstOrDefault(a => string.Equals(a.Role, ImageMediaRoles.Image, StringComparison.Ordinal))
    ?? success.Envelope.Artifacts.FirstOrDefault();
if (providerArtifact is null)
{
    return Fail("Image generation failed. Provider result did not contain an image artifact.");
}

var materialized = await _imageArtifactMaterializer
    .MaterializeAsync(providerArtifact, cancellationToken)
    .ConfigureAwait(false);
if (!materialized.Success || materialized.Bytes is null)
{
    return Fail(
        "Image generation failed. " +
        GenericizeProviderError(materialized.Error?.Message
            ?? "Image artifact could not be materialized."));
}

var imageBytes = materialized.Bytes;
var mimeType = materialized.MimeType ?? "image/png";
```

- [ ] Keep artifact metadata keys backward-compatible:

```csharp
["mime_type"] = mimeType,
```

Do not remove or rename existing metadata fields.

### Missing Key Handling

PR-7 can leave `IsGeminiMissingApiKey` as Gemini-specific if the fal provider's message is already safe. Do not broaden this helper into brittle string matching unless tests show the route is genericizing a useful missing-key message into something worse.

Expected fal missing key message:

```text
fal API key is not configured. Set it via the Vision settings before calling /vision/generate.
```

### Commit Gate

- [ ] Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionHandlerTests" -p:RhinoPluginDir=
```

- [ ] Commit message:

```text
feat(vision): route fal image results into artifacts
```

---

## Phase 6: Live Smoke Test

### Tests First

- [ ] Add `FalImageLiveSmokeTests`.

The live smoke must be opt-in and must not spend money silently.

Required environment variables:

- `ROOK_FAL_IMAGE_LIVE=1`
- `ROOK_FAL_API_KEY=<key>`
- `ROOK_ACCEPT_FAL_SPEND=1`

If `ROOK_FAL_IMAGE_LIVE` is not `1`, the test returns immediately.

If live is enabled but `ROOK_FAL_API_KEY` or `ROOK_ACCEPT_FAL_SPEND` is missing, the test fails with an explicit message.

Live smoke shape:

- Construct `FalImageProvider` with real `FalApiClient`.
- Submit `fal-ai/flux/schnell` with a tiny deterministic prompt.
- Request `1:1`, `1K`, one image.
- Assert `SyncSubmitOutcome`.
- Assert the inner result is `SuccessResultOutcome`.
- Assert the first image artifact is a `RemoteArtifactBody` with an HTTP(S) URL.
- Any `FailedSubmitOutcome`, `FailedResultOutcome`, malformed result, or missing URL fails the paid smoke.
- Do not download/write the generated image in the live smoke unless execution explicitly decides to include materialization in the paid path.

### Commit Gate

- [ ] Run default non-live test suite and verify live test does not spend:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalImageLiveSmokeTests" -p:RhinoPluginDir=
```

Expected without env vars:

```text
Passed! - Failed: 0
```

- [ ] Optional paid smoke only with explicit user approval:

```powershell
$env:ROOK_FAL_IMAGE_LIVE='1'
$env:ROOK_ACCEPT_FAL_SPEND='1'
$env:ROOK_FAL_API_KEY='<redacted>'
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalImageLiveSmokeTests" -p:RhinoPluginDir=
```

- [ ] Commit message:

```text
test(vision): add gated fal image live smoke
```

---

## Phase 7: Full Verification

Run these before requesting review:

```powershell
git diff --check origin/main...HEAD
```

Expected:

```text
<no output>
```

```powershell
dotnet build src/Rook/Rook.csproj --no-restore -p:RhinoPluginDir=
```

Expected:

```text
0 Error(s)
```

Run focused tests:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalImage|FullyQualifiedName~ImageArtifactMaterializer|FullyQualifiedName~VisionHandlerTests" -p:RhinoPluginDir=
```

Expected:

```text
Passed! - Failed: 0
```

Run full managed tests if available:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore -p:RhinoPluginDir=
```

Expected:

```text
Passed! - Failed: 0
```

If RhinoCommon is unavailable in the test host, stop and debug. PR-6 added test-host RhinoCommon resolution, so zero discovered tests or xUnit discovery skips are no longer acceptable without a new environment-specific explanation.

Scope guard:

```powershell
$changed = git diff --name-only origin/main...HEAD
$changed | Where-Object {
    $_ -like 'src/RookNative/*' -or
    $_ -like 'mcp_server/*' -or
    $_ -like 'src/Rook/Resources/*'
}
```

Expected:

```text
<no output>
```

Source hygiene scan:

```powershell
$terms = @(
    'TO' + 'DO',
    'TB' + 'D',
    'place' + 'holder',
    'fake' + ' price',
    'hardcode' + ' later',
    'Unknown validation' + ' state',
    'Required' + 'Secrets'
)
rg -n ($terms -join '|') src/Rook src/Rook.Tests
```

Expected:

```text
<no output, except intentional test names or source comments reviewed in context>
```

Plan hygiene is manual for this PR: review this file for stale snippets after implementation and either update snippets to match final code or mark them as historical execution notes before merge.

---

## Review Checklist

- [ ] `fal-ai/flux/schnell` can be selected by exact model ID.
- [ ] Gemini default and Gemini short-name fallback still work.
- [ ] fal missing API key does not require or mention Gemini API key.
- [ ] fal request body uses official field names from the 2026-04-29 docs.
- [ ] fal API key is only sent to `fal.run` through `FalApiClient`.
- [ ] Remote artifact downloads use plain `HttpClient` and never attach fal auth.
- [ ] Remote artifact URLs must be HTTP(S) due to `RemoteArtifactBody`.
- [ ] Route output still writes a normal `generated_image` artifact.
- [ ] Route response does not expose raw fal JSON envelopes.
- [ ] Pricing source/provenance are date-stamped.
- [ ] `x-fal-billable-units` interpretation is isolated to the Flux Schnell pricing model.
- [ ] No native, MCP, UI, video, Replicate, Tencent, or dynamic catalog files changed.
- [ ] Live smoke is opt-in and cannot spend without `ROOK_ACCEPT_FAL_SPEND=1`.

---

## PR Description Draft

```markdown
## Summary

- add `fal-ai/flux/schnell` as the first fal image provider
- materialize URL-backed image artifacts into the existing ArtifactStore path
- add fal image capability, options codec, secret metadata, and pricing model

## Scope

Managed image-provider slice only. No native route, MCP schema, UI, or video changes.

## Verification

- `git diff --check origin/main...HEAD`
- `dotnet build src/Rook/Rook.csproj --no-restore -p:RhinoPluginDir=`
- `dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalImage|FullyQualifiedName~ImageArtifactMaterializer|FullyQualifiedName~VisionHandlerTests" -p:RhinoPluginDir=`
- optional paid smoke only with `ROOK_FAL_IMAGE_LIVE=1`, `ROOK_ACCEPT_FAL_SPEND=1`, and `ROOK_FAL_API_KEY`
```

---

## Explicit Deferrals

- Prompt-only public route shape for text-to-image.
- UI picker availability and settings key-test behavior.
- Dynamic fal catalog refresh.
- Higher-quality fal image models.
- fal video queue/lifecycle support.
- Replicate provider.
- Tencent provider and multi-key operation overlays.
- Shared remote artifact downloader for video and image.
- Persisting image-route actual spend into artifact metadata or audit ledger beyond provider pricing-model extraction tests.

---

## Self-Review Notes

- Every fal-specific decision is either behind the fal provider/codec/pricing model or explicitly called out as route-local compatibility behavior.
- The only provider-agnostic code added is image artifact materialization, which is required by fal and also pressure-tested against Replicate/Tencent URL output shapes.
- Secret/status metadata remains provider-level static `SecretRequirements`; operation-scoped credential overlays are not implied.
- Pricing uses a date-stamped fal model source and isolates `x-fal-billable-units` interpretation to the pricing model.
- The plan keeps PR-7 implementation managed-only and avoids public route contract drift.
