# Flux 2 Pro Resolution Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Flux 2 Pro prompt-only resolution options to provider-shaped `1 MP`, `2 MP`, and `4 MP`, while keeping source-image submissions on `match_input_image` and preserving a legacy `1MP` backend alias.

**Architecture:** This is a narrow Replicate image-provider change. Capability metadata drives the Vision dropdown; provider validation normalizes one legacy value before checking capability lists; provider request JSON serializes only provider-shaped values. Source-image request construction remains separate and continues to override resolution to `match_input_image`.

**Tech Stack:** C#/.NET Framework 4.8 tests via xUnit; Rook managed companion image provider code; Replicate Flux 2 Pro API schema reviewed 2026-05-18.

---

## Files

- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
  - Responsibility: curated Replicate model capability metadata for model catalog/UI.
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs`
  - Responsibility: provider-specific validation and request normalization boundary for Replicate image options.
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
  - Responsibility: Flux 2 Pro request normalization and provider JSON serialization.
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`
  - Responsibility: model catalog/capability regression coverage.
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs`
  - Responsibility: validation and compatibility-alias regression coverage.
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`
  - Responsibility: provider JSON regression coverage for prompt-only and source-image Flux 2 Pro.

## Task 1: Pin Catalog And Validation Tests

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs`

- [ ] **Step 1: Update catalog test to expect provider-shaped Flux 2 Pro resolutions**

In `ReplicateImageProviderRegistrationTests.Registration_exposes_curated_replicate_models`, replace:

```csharp
Assert.Equal(new[] { "1MP" }, flux2.Capability.Resolutions);
```

with:

```csharp
Assert.Equal(new[] { "1 MP", "2 MP", "4 MP" }, flux2.Capability.Resolutions);
```

- [ ] **Step 2: Add validation tests for Flux 2 Pro spaced values, legacy `1MP`, and compact unsupported values**

In `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs`, add a Flux 2 Pro capability field near the existing `_cap` field:

```csharp
private readonly ImageCapability _flux2Cap = ReplicateImageCapabilities.Models[ReplicateImageCapabilities.Flux2Pro];
```

Add these tests after `Validate_rejects_unsupported_resolution`:

```csharp
[Theory]
[InlineData("1 MP")]
[InlineData("2 MP")]
[InlineData("4 MP")]
public void Validate_flux2_accepts_provider_shaped_resolutions(string resolution)
{
    var result = _codec.Validate(
        Flux2Request(resolution: resolution),
        new ReplicateImageOptions(),
        _flux2Cap);

    Assert.True(result.Success);
}

[Fact]
public void Validate_flux2_accepts_legacy_1mp_alias()
{
    var result = _codec.Validate(
        Flux2Request(resolution: "1MP"),
        new ReplicateImageOptions(),
        _flux2Cap);

    Assert.True(result.Success);
}

[Theory]
[InlineData("2MP")]
[InlineData("4MP")]
public void Validate_flux2_rejects_compact_resolution_aliases_other_than_legacy_1mp(string resolution)
{
    var result = _codec.Validate(
        Flux2Request(resolution: resolution),
        new ReplicateImageOptions(),
        _flux2Cap);

    Assert.False(result.Success);
    Assert.Equal("resolution", result.Field);
    Assert.Contains("1 MP, 2 MP, 4 MP", result.Message);
}
```

Add this helper below the existing `Request` helper:

```csharp
private static ImageGenerationRequest Flux2Request(
    string resolution = "1 MP",
    string aspectRatio = "1:1",
    int numberOfImages = 1,
    System.Collections.Generic.IReadOnlyList<MediaRef>? referenceImages = null) =>
    new(
        Model: ReplicateImageCapabilities.Flux2Pro,
        Prompt: "sunlit massing study",
        Resolution: resolution,
        AspectRatio: aspectRatio,
        NumberOfImages: numberOfImages,
        ReferenceImages: referenceImages,
        Options: new ReplicateImageOptions());
```

- [ ] **Step 3: Run the new tests and verify they fail before implementation**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~ReplicateImageProviderRegistrationTests|FullyQualifiedName~ReplicateImageOptionsCodecTests"
```

Expected before implementation:

- Registration test fails because Flux 2 Pro still advertises only `1MP`.
- Flux 2 Pro spaced resolution tests fail because validation does not yet recognize `1 MP`, `2 MP`, or `4 MP`.
- Legacy `1MP` may pass before implementation; that is acceptable, but the suite must still be red for the catalog/spaced-value behavior.

## Task 2: Implement Capability Metadata And Validation Normalization

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs`

- [ ] **Step 1: Update Flux 2 Pro capability metadata**

In `ReplicateImageCapabilities.Models`, change the Flux 2 Pro capability from:

```csharp
Resolutions: new[] { "1MP" },
```

to:

```csharp
Resolutions: new[] { "1 MP", "2 MP", "4 MP" },
```

- [ ] **Step 2: Add resolution normalization for validation**

In `ReplicateImageOptionsCodec`, replace the current resolution calculation:

```csharp
var resolution = string.IsNullOrWhiteSpace(request.Resolution)
    ? "1K"
    : request.Resolution.ToUpperInvariant();
```

with:

```csharp
var resolution = NormalizeResolutionForValidation(request, capability);
```

Add this private helper inside `ReplicateImageOptionsCodec` before `Serialize`:

```csharp
private static string NormalizeResolutionForValidation(
    ImageGenerationRequest request,
    ImageCapability capability)
{
    if (string.IsNullOrWhiteSpace(request.Resolution))
    {
        return string.Equals(
            capability.Id,
            ReplicateImageCapabilities.Flux2Pro,
            StringComparison.Ordinal)
            ? "1 MP"
            : "1K";
    }

    var trimmed = request.Resolution.Trim();
    if (string.Equals(
            capability.Id,
            ReplicateImageCapabilities.Flux2Pro,
            StringComparison.Ordinal)
        && string.Equals(trimmed, "1MP", StringComparison.OrdinalIgnoreCase))
    {
        return "1 MP";
    }

    return string.Equals(
        capability.Id,
        ReplicateImageCapabilities.Flux2Pro,
        StringComparison.Ordinal)
        ? trimmed
        : trimmed.ToUpperInvariant();
}
```

This keeps the old `1K` normalization for Flux Schnell, accepts only the legacy `1MP` alias for Flux 2 Pro, and leaves `2MP`/`4MP` unsupported.

- [ ] **Step 3: Run catalog and codec tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~ReplicateImageProviderRegistrationTests|FullyQualifiedName~ReplicateImageOptionsCodecTests"
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit Task 2**

Run:

```powershell
git add src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs
git commit -m "fix: advertise Flux 2 Pro resolution options"
```

## Task 3: Pin Provider JSON Serialization Tests

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`

- [ ] **Step 1: Update existing prompt-only default expectation**

In `SubmitAsync_flux2_prompt_only_posts_prediction_without_input_images_or_match_input_defaults`, replace:

```csharp
Assert.Equal("1MP", inputJson["resolution"]!.GetValue<string>());
```

with:

```csharp
Assert.Equal("1 MP", inputJson["resolution"]!.GetValue<string>());
```

- [ ] **Step 2: Add prompt-only provider JSON tests for `2 MP`, `4 MP`, and legacy `1MP` normalization**

Add this theory after `SubmitAsync_flux2_prompt_only_posts_prediction_without_input_images_or_match_input_defaults`:

```csharp
[Theory]
[InlineData("2 MP", "2 MP")]
[InlineData("4 MP", "4 MP")]
[InlineData("1MP", "1 MP")]
public async Task SubmitAsync_flux2_prompt_only_serializes_provider_resolution_values(
    string requestedResolution,
    string expectedProviderResolution)
{
    string? requestBody = null;
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            requestBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return Json(HttpStatusCode.Created, """
                {
                  "id": "pred-flux2-resolution",
                  "status": "starting",
                  "urls": {
                    "get": "https://api.replicate.com/v1/predictions/pred-flux2-resolution",
                    "cancel": "https://api.replicate.com/v1/predictions/pred-flux2-resolution/cancel"
                  }
                }
                """);
        },
    };
    var provider = Provider("r8-test-token", handler);

    var outcome = await provider.SubmitAsync(
        Request(
            model: ReplicateImageCapabilities.Flux2Pro,
            resolution: requestedResolution,
            aspectRatio: "1:1"),
        EmptyMedia(),
        CancellationToken.None);

    var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
    Assert.Equal("pred-flux2-resolution", queued.Handle.ProviderJobId);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-2-pro/predictions",
        request.RequestUri!.ToString());

    var root = Assert.IsType<JsonObject>(JsonNode.Parse(requestBody!));
    var inputJson = Assert.IsType<JsonObject>(root["input"]);
    Assert.Equal(expectedProviderResolution, inputJson["resolution"]!.GetValue<string>());
    Assert.Equal("1:1", inputJson["aspect_ratio"]!.GetValue<string>());
    Assert.DoesNotContain("input_images", requestBody);
}
```

- [ ] **Step 3: Update source-image tests to use dropdown-shaped request values while expecting `match_input_image`**

In `SubmitAsync_flux2_uploads_source_and_posts_https_input_image_url`, change the request resolution from `"1MP"` to `"4 MP"`:

```csharp
Request(
    model: ReplicateImageCapabilities.Flux2Pro,
    resolution: "4 MP",
    aspectRatio: "match_input_image"),
```

Keep this existing assertion unchanged:

```csharp
Assert.Equal("match_input_image", inputJson["resolution"]!.GetValue<string>());
```

This pins that source-image jobs ignore the prompt-only dropdown resolution and preserve Replicate's `match_input_image` semantics.

- [ ] **Step 4: Run the new provider tests and verify they fail before provider implementation**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~SubmitAsync_flux2_prompt_only_posts_prediction_without_input_images_or_match_input_defaults|FullyQualifiedName~SubmitAsync_flux2_prompt_only_serializes_provider_resolution_values|FullyQualifiedName~SubmitAsync_flux2_uploads_source_and_posts_https_input_image_url"
```

Expected before implementation:

- Default prompt-only test fails because provider still serializes `1MP`.
- Legacy `1MP` serialization fails because provider still sends `1MP` instead of `1 MP`.
- `2 MP`/`4 MP` may already pass validation after Task 2 but must be confirmed to serialize exactly.

## Task 4: Implement Provider Request Normalization

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`

- [ ] **Step 1: Update default Flux 2 Pro validation request**

In `NormalizeFlux2ValidationRequest`, replace:

```csharp
return request with { Resolution = "1MP" };
```

with:

```csharp
return request with { Resolution = "1 MP" };
```

- [ ] **Step 2: Normalize Flux 2 Pro prompt-only provider resolution values**

Replace `ConcreteFlux2PromptOnlyResolution` with:

```csharp
private static string ConcreteFlux2PromptOnlyResolution(string? resolution)
{
    if (string.IsNullOrWhiteSpace(resolution)
        || string.Equals(resolution, "match_input_image", StringComparison.Ordinal))
    {
        return "1 MP";
    }

    var trimmed = resolution.Trim();
    return string.Equals(trimmed, "1MP", StringComparison.OrdinalIgnoreCase)
        ? "1 MP"
        : trimmed;
}
```

This ensures provider JSON sends spaced values for the default and the legacy `1MP` alias. `2MP` and `4MP` remain invalid because validation rejects them before serialization.

- [ ] **Step 3: Run the focused provider tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~SubmitAsync_flux2_prompt_only_posts_prediction_without_input_images_or_match_input_defaults|FullyQualifiedName~SubmitAsync_flux2_prompt_only_serializes_provider_resolution_values|FullyQualifiedName~SubmitAsync_flux2_uploads_source_and_posts_https_input_image_url"
```

Expected: all selected tests pass.

- [ ] **Step 4: Run the full Replicate image test slice**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~ReplicateImageProviderRegistrationTests|FullyQualifiedName~ReplicateImageOptionsCodecTests|FullyQualifiedName~ReplicateImageProviderTests|FullyQualifiedName~ReplicateImageJobManagerTests"
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs
git commit -m "fix: send provider-shaped Flux 2 resolutions"
```

## Task 5: Deploy And Manual Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run a full local deploy**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1
```

Expected: deploy completes, native and managed builds run, installed plugin path is reported as:

```text
C:\Users\aryan\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative
```

If the script refuses because Rhino or `python -m rook` is running, close Rhino or stop only `python -m rook` processes, then rerun. Do not kill Rhino if the user has unsaved work.

- [ ] **Step 2: Restart Rhino before UI verification**

After deploy, restart Rhino so the newly copied managed companion assembly is loaded.

- [ ] **Step 3: Verify the Generate dropdown manually**

Open RookVision Generate, select Flux 2 Pro, and verify the resolution dropdown offers exactly:

```text
1 MP
2 MP
4 MP
```

- [ ] **Step 4: Verify source-image behavior manually**

Capture a viewport screenshot and submit a Flux 2 Pro source-image job. Expected: job submits without the old file-upload transport error for small screenshots and behaves as a source-image roundtrip. The dropdown value should not prevent source-image submission because provider JSON uses `match_input_image` for source-image requests.

- [ ] **Step 5: Final status check**

Run:

```powershell
git status --short
```

Expected: clean working tree.

## Self-Review

Spec coverage:

- Catalog emits `1 MP`, `2 MP`, `4 MP`: Task 1 and Task 2.
- Backend accepts legacy `1MP`: Task 1, Task 2, Task 3, Task 4.
- Provider JSON sends spaced values: Task 3 and Task 4.
- Source-image sends `match_input_image`: Task 3 and Task 4.
- No custom width/height: no task introduces custom aspect ratio, width, or height.
- Compact `2MP`/`4MP` intentionally rejected: Task 1 and Task 2.

Placeholder scan: no TBD/TODO placeholders are present.

Type consistency: all referenced types already exist in the Replicate image provider and test namespaces.
