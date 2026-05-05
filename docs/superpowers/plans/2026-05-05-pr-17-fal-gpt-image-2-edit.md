# PR-17 fal GPT Image 2 Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add curated fal.ai `openai/gpt-image-2/edit` as a source-image-only async image job model using one primary source image and local artifact materialization.

**Architecture:** Keep provider identity as `fal` and make the fal image provider model-aware: existing `fal-ai/flux/schnell` remains sync while `openai/gpt-image-2/edit` uses fal queue submit/status/result/cancel. Persist only fal `request_id` as `provider_job_id`; reconstruct queue URLs at runtime from model id plus request id and keep all source/data URI/fal URL/provider envelope details out of ledger, bridge job payloads, provider handles, and artifact metadata.

**Tech Stack:** C#/.NET managed Rook Vision stack, existing fal REST client, existing image job manager/ledger/materializer, Vision WebView resources, xUnit fake HTTP tests.

---

## File Structure

Create:

- `src/Rook/Services/Vision/Image/Fal/FalGptImage2EditSourcePayload.cs`
  Model-specific validator and data URI builder for exactly one primary source image.

Modify:

- `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs`
  Add a registration method for model-level submission mode.
- `src/Rook/Services/Vision/Image/DefaultImageProviderRegistry.cs`
  Use model-level submission mode when building `ResolvedImageModel` and descriptors.
- `src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs`
  Return sync submission mode for all Gemini models.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
  Return async submission mode for all Replicate registered models.
- `src/Rook/Services/Vision/Image/Fal/FalImageCapabilities.cs`
  Add `openai/gpt-image-2/edit` capability.
- `src/Rook/Services/Vision/Image/Fal/FalImageProviderRegistration.cs`
  Register GPT Image 2 edit and return model-specific submission mode.
- `src/Rook/Services/Vision/Image/Fal/FalImageOptionsCodec.cs`
  Validate GPT Image 2 edit as source-image-only with `resolution: auto` and `aspect_ratio: match_input_image`.
- `src/Rook/Services/Vision/Image/Fal/FalImageProvider.cs`
  Branch by model id: keep sync Flux Schnell and add async GPT Image 2 edit queue lifecycle.
- `src/Rook/Services/Vision/Image/IImageProvider.cs`
  Add a small model-aware lifecycle interface in this file, without changing existing `IImageProvider` method signatures.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
  Resolve persisted `provider + model` for restart lifecycle and call model-aware lifecycle methods when available.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactory.cs`
  Add fal-specific durable/bridge error redaction strings.
- `src/Rook/UI/Vision/Resources/app.js`
  Only if tests prove existing source-image async routing needs a tiny model-gating adjustment.

Test:

- `src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderRegistrationTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalImageOptionsCodecTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs`
- `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
- `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`

Do not modify:

- `src/RookNative/**`
- `mcp_server/**`
- public HTTP/native registrar surfaces

---

### Task 1: Model-Level Image Submission Mode

**Files:**
- Modify: `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/DefaultImageProviderRegistry.cs`
- Modify: `src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/Fal/FalImageProviderRegistration.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs`

- [ ] **Step 1: Write failing registry tests for model-level submission mode**

Add this test fixture support to `DefaultImageProviderRegistryTests.cs`:

```csharp
[Fact]
public void Registration_can_expose_mixed_submission_modes_per_model()
{
    var provider = new FakeImageProvider("mixed");
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new MixedModeRegistration(provider),
    });

    Assert.True(registry.TryResolve("mixed-sync", out var sync));
    Assert.True(registry.TryResolve("mixed-async", out var async));
    Assert.Equal(ImageSubmissionMode.Sync, sync.SubmissionMode);
    Assert.Equal(ImageSubmissionMode.AsyncImageJob, async.SubmissionMode);

    var descriptors = registry.EnumerateAllModels();
    Assert.Equal(
        ImageSubmissionMode.Sync,
        Assert.Single(descriptors, m => m.ModelId == "mixed-sync").SubmissionMode);
    Assert.Equal(
        ImageSubmissionMode.AsyncImageJob,
        Assert.Single(descriptors, m => m.ModelId == "mixed-async").SubmissionMode);
}

private sealed class MixedModeRegistration : IImageProviderRegistration
{
    public MixedModeRegistration(IImageProvider provider)
    {
        Provider = provider;
    }

    public string ProviderName => "mixed";
    public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
    public IImageProvider Provider { get; }
    public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
        = new FakeOptionsCodec();
    public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => Array.Empty<ProviderSecretRequirement>();

    public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models { get; }
        = new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal)
        {
            ["mixed-sync"] = (
                new ImageCapability("mixed-sync", "Mixed Sync", "available", new[] { "1K" }, new[] { "1:1" }, 0, true, true),
                new FakePricingModel()),
            ["mixed-async"] = (
                new ImageCapability("mixed-async", "Mixed Async", "available", new[] { "auto" }, new[] { "match_input_image" }, 0, true, false),
                new FakePricingModel()),
        };

    public ImageSubmissionMode GetSubmissionMode(string modelId) =>
        string.Equals(modelId, "mixed-async", StringComparison.Ordinal)
            ? ImageSubmissionMode.AsyncImageJob
            : ImageSubmissionMode.Sync;
}
```

If the test file lacks fake codec/provider/pricing helpers, add small private helpers that return success and never perform network I/O:

```csharp
private sealed class FakeOptionsCodec
    : IProviderOptionsCodec<ImageGenerationRequest, ImageCapability>
{
    public ValidationResult Validate(
        ImageGenerationRequest request,
        ProviderOptions options,
        ImageCapability capability) => ValidationResult.Ok();

    public JsonObject Serialize(ProviderOptions options) => new();

    public ProviderOptionsDecodeResult Deserialize(JsonObject json) =>
        ProviderOptionsDecodeResult.Ok(new GeminiImageOptions());
}

private sealed class FakePricingModel
    : IPricingModel<ImageGenerationRequest, ImageCapability>
{
    public string PricingSource => "fake";
    public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

    public PricingResult Estimate(
        ImageGenerationRequest request,
        ImageCapability capability) =>
        PricingResult.Ok(
            new JobPricing(
                Currency: "USD",
                UnitPrice: 0m,
                Unit: "call",
                Quantity: 1m,
                TotalUsd: 0m,
                PricingSource: "fake"),
            new CostEstimate(
                Min: 0m,
                Max: 0m,
                IsExact: false,
                Provenance: "fake-test"));

    public JobPricing? ExtractActualSpend(
        IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
        JsonNode? responseBody) => null;
}

private sealed class FakeImageProvider : IImageProvider
{
    public FakeImageProvider(string providerName) => ProviderName = providerName;
    public string ProviderName { get; }
    public Task<ProviderSubmitOutcome> SubmitAsync(ImageGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia, CancellationToken ct) => throw new NotImplementedException();
    public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct) => throw new NotImplementedException();
    public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) => throw new NotImplementedException();
    public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct) => throw new NotImplementedException();
}
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "DefaultImageProviderRegistryTests"
```

Expected: compile fails because `IImageProviderRegistration.GetSubmissionMode` does not exist.

- [ ] **Step 3: Add model-level submission mode to registration interface**

Modify `IImageProviderRegistration.cs`:

```csharp
ImageSubmissionMode GetSubmissionMode(string modelId);
```

Keep the existing `SubmissionMode` property so older tests and callers continue to compile.

- [ ] **Step 4: Implement default per-model methods in registrations**

In Gemini and Replicate registrations:

```csharp
public ImageSubmissionMode GetSubmissionMode(string modelId) => SubmissionMode;
```

In fal registration, use sync until GPT Image 2 edit is added in Task 3:

```csharp
public ImageSubmissionMode GetSubmissionMode(string modelId) => SubmissionMode;
```

- [ ] **Step 5: Use per-model mode in the registry**

In `DefaultImageProviderRegistry.cs`, replace both uses of `reg.SubmissionMode` for resolved model construction with:

```csharp
var submissionMode = reg.GetSubmissionMode(kvp.Key);
if (!Enum.IsDefined(typeof(ImageSubmissionMode), submissionMode))
    throw new InvalidOperationException(
        $"Provider '{reg.ProviderName}' model '{kvp.Key}' has invalid SubmissionMode '{submissionMode}'.");
```

Pass `submissionMode` to `ResolvedImageModel`.

- [ ] **Step 6: Run registry tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "DefaultImageProviderRegistryTests|FalImageProviderRegistrationTests|ReplicateImageProviderRegistrationTests|VisionProviderRegistrationsTests"
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\IImageProviderRegistration.cs `
        src\Rook\Services\Vision\Image\DefaultImageProviderRegistry.cs `
        src\Rook\Services\Vision\Image\Gemini\GeminiImageProviderRegistration.cs `
        src\Rook\Services\Vision\Image\Replicate\ReplicateImageProviderRegistration.cs `
        src\Rook\Services\Vision\Image\Fal\FalImageProviderRegistration.cs `
        src\Rook.Tests\Services\Vision\Image\DefaultImageProviderRegistryTests.cs
git commit -m "feat(vision): support model-level image submission mode"
```

---

### Task 2: Model-Aware Image Job Lifecycle Dispatch

**Files:**
- Modify: `src/Rook/Services/Vision/Image/IImageProvider.cs`
- Modify: `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`

- [ ] **Step 1: Write failing manager tests for provider + model restart lookup**

Add tests to `ImageJobManagerTests.cs` using a fake provider that implements the new model-aware lifecycle interface:

```csharp
[Fact]
public async Task Cancel_after_restart_resolves_provider_by_model_and_passes_model_to_provider()
{
    var provider = new ModelAwareLifecycleProvider("fal");
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new SingleModelRegistration(
            provider,
            providerName: "fal",
            modelId: "openai/gpt-image-2/edit",
            mode: ImageSubmissionMode.AsyncImageJob),
    });
    var ledger = new FakeImageJobLedger();
    var now = DateTimeOffset.Parse("2026-05-05T12:00:00Z", CultureInfo.InvariantCulture);
    ledger.Append(ImageJobLedgerRecordFactory.WithState(
        ImageJobLedgerRecordFactory.FromInitial(
            Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "fal",
            "openai/gpt-image-2/edit",
            ImageJobState.Queued,
            now),
        ImageJobState.Interrupted,
        now.AddSeconds(1),
        providerJobId: "fal-request-1"));
    var manager = MakeManager(registry, ledger: ledger);

    var result = await manager.CancelAsync(
        Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        CancellationToken.None);

    Assert.Null(result.Error);
    Assert.Equal(ImageJobState.Cancelled, result.State);
    Assert.Equal(new[] { "openai/gpt-image-2/edit" }, provider.CancelModels);
    Assert.Equal(new[] { "fal-request-1" }, provider.CancelJobIds);
}
```

Add a negative test:

```csharp
[Fact]
public async Task Cancel_after_restart_fails_when_model_provider_does_not_match_durable_provider()
{
    var provider = new ModelAwareLifecycleProvider("fal");
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new SingleModelRegistration(
            provider,
            providerName: "fal",
            modelId: "openai/gpt-image-2/edit",
            mode: ImageSubmissionMode.AsyncImageJob),
    });
    var ledger = new FakeImageJobLedger();
    var jobId = Guid.Parse("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
    var now = DateTimeOffset.Parse("2026-05-05T12:00:00Z", CultureInfo.InvariantCulture);
    ledger.Append(ImageJobLedgerRecordFactory.WithState(
        ImageJobLedgerRecordFactory.FromInitial(
            jobId,
            "other-provider",
            "openai/gpt-image-2/edit",
            ImageJobState.Queued,
            now),
        ImageJobState.Interrupted,
        now.AddSeconds(1),
        providerJobId: "fal-request-1"));
    var manager = MakeManager(registry, ledger: ledger);

    var result = await manager.CancelAsync(jobId, CancellationToken.None);

    Assert.NotNull(result.Error);
    Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
    Assert.Empty(provider.CancelModels);
}
```

Use local helper classes shaped like:

```csharp
private sealed class ModelAwareLifecycleProvider : IImageProvider, IModelAwareImageProvider
{
    public ModelAwareLifecycleProvider(string providerName) => ProviderName = providerName;
    public string ProviderName { get; }
    public List<string> CancelModels { get; } = new();
    public List<string> CancelJobIds { get; } = new();

    public Task<ProviderSubmitOutcome> SubmitAsync(ImageGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia, CancellationToken ct) => throw new NotImplementedException();
    public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct) => throw new InvalidOperationException("legacy status should not be used");
    public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) => throw new InvalidOperationException("legacy cancel should not be used");
    public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct) => throw new InvalidOperationException("legacy result should not be used");

    public Task<ProviderStatusOutcome> GetStatusAsync(string modelId, ProviderJobHandle handle, CancellationToken ct) =>
        Task.FromResult<ProviderStatusOutcome>(new InFlightStatusOutcome(GenerationLifecycleState.Running, null));

    public Task<ProviderCancelOutcome> CancelAsync(string modelId, ProviderJobHandle handle, CancellationToken ct)
    {
        CancelModels.Add(modelId);
        CancelJobIds.Add(handle.ProviderJobId);
        return Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
    }

    public Task<ProviderResultOutcome> FetchResultAsync(string modelId, ProviderJobHandle handle, CancellationToken ct) =>
        Task.FromResult<ProviderResultOutcome>(new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "not used", false)));
}
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "Cancel_after_restart_resolves_provider_by_model_and_passes_model_to_provider|Cancel_after_restart_fails_when_model_provider_does_not_match_durable_provider"
```

Expected: compile fails because `IModelAwareImageProvider` does not exist.

- [ ] **Step 3: Add model-aware lifecycle interface**

Add to `IImageProvider.cs`:

```csharp
public interface IModelAwareImageProvider : IImageProvider
{
    Task<ProviderStatusOutcome> GetStatusAsync(
        string modelId,
        ProviderJobHandle handle,
        CancellationToken ct);

    Task<ProviderCancelOutcome> CancelAsync(
        string modelId,
        ProviderJobHandle handle,
        CancellationToken ct);

    Task<ProviderResultOutcome> FetchResultAsync(
        string modelId,
        ProviderJobHandle handle,
        CancellationToken ct);
}
```

- [ ] **Step 4: Resolve durable lifecycle provider by provider + model**

In `ImageJobManager.cs`, replace `ResolveProviderByName` with:

```csharp
private bool ResolveProviderForRecord(
    ImageJobRecord record,
    out IImageProvider provider)
{
    provider = null!;
    if (record is null) return false;
    if (!_registry.TryResolve(record.Model, out var resolved))
        return false;
    if (!string.Equals(resolved.ProviderName, record.Provider, StringComparison.Ordinal))
        return false;

    provider = resolved.Provider;
    return true;
}
```

Use `ResolveProviderForRecord(record, out var provider)` in cancel-after-restart instead of provider-name-only lookup. Preserve a clear error message:

```csharp
$"Cannot cancel job {record.JobId:D}: provider/model '{record.Provider}/{record.Model}' is no longer registered."
```

- [ ] **Step 5: Route lifecycle calls through model-aware methods**

Add helpers:

```csharp
private static Task<ProviderStatusOutcome> GetProviderStatusAsync(
    IImageProvider provider,
    string modelId,
    ProviderJobHandle handle,
    CancellationToken ct) =>
    provider is IModelAwareImageProvider modelAware
        ? modelAware.GetStatusAsync(modelId, handle, ct)
        : provider.GetStatusAsync(handle, ct);

private static Task<ProviderCancelOutcome> CancelProviderAsync(
    IImageProvider provider,
    string modelId,
    ProviderJobHandle handle,
    CancellationToken ct) =>
    provider is IModelAwareImageProvider modelAware
        ? modelAware.CancelAsync(modelId, handle, ct)
        : provider.CancelAsync(handle, ct);

private static Task<ProviderResultOutcome> FetchProviderResultAsync(
    IImageProvider provider,
    string modelId,
    ProviderJobHandle handle,
    CancellationToken ct) =>
    provider is IModelAwareImageProvider modelAware
        ? modelAware.FetchResultAsync(modelId, handle, ct)
        : provider.FetchResultAsync(handle, ct);
```

Replace existing calls to:

```csharp
provider.GetStatusAsync(handle, ct)
provider.CancelAsync(handle, ct)
provider.FetchResultAsync(handle, ct)
TryRemoteCancelAsync(provider, handle, ct)
```

with helpers that pass `running.Model.ModelId` for active jobs and `record.Model` for restart cancellation. Update `TryRemoteCancelAsync` signature to include model id:

```csharp
private async Task<(GenerationError? Error, bool AlreadyTerminal)> TryRemoteCancelAsync(
    IImageProvider provider,
    string modelId,
    ProviderJobHandle handle,
    CancellationToken ct)
```

- [ ] **Step 6: Run image job manager tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobManagerTests"
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\IImageProvider.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobManagerTests.cs
git commit -m "feat(vision): resolve image job lifecycle by provider and model"
```

---

### Task 3: fal GPT Image 2 Edit Catalog Registration And Validation

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Fal/FalImageCapabilities.cs`
- Modify: `src/Rook/Services/Vision/Image/Fal/FalImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/Fal/FalImageOptionsCodec.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderRegistrationTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Fal/FalImageOptionsCodecTests.cs`
- Test: `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`

- [ ] **Step 1: Write failing fal registration tests**

Add to `FalImageProviderRegistrationTests.cs`:

```csharp
[Fact]
public void Models_ExposeGptImage2EditCapability()
{
    var registration = new FalImageProviderRegistration(new FakeImageProvider());

    Assert.True(registration.Models.ContainsKey(FalImageCapabilities.GptImage2Edit));
    var model = registration.Models[FalImageCapabilities.GptImage2Edit];
    Assert.Equal("GPT Image 2 Edit", model.Capability.Name);
    Assert.Equal(new[] { "auto" }, model.Capability.Resolutions);
    Assert.Equal(new[] { "match_input_image" }, model.Capability.AspectRatios);
    Assert.Equal(0, model.Capability.MaxReferenceImages);
    Assert.True(model.Capability.SupportsImageToImage);
    Assert.False(model.Capability.SupportsTextToImage);
}

[Fact]
public void GetSubmissionMode_ReturnsAsyncForGptImage2EditAndSyncForSchnell()
{
    var registration = new FalImageProviderRegistration(new FakeImageProvider());

    Assert.Equal(
        ImageSubmissionMode.Sync,
        registration.GetSubmissionMode(FalImageCapabilities.FluxSchnell));
    Assert.Equal(
        ImageSubmissionMode.AsyncImageJob,
        registration.GetSubmissionMode(FalImageCapabilities.GptImage2Edit));
}
```

- [ ] **Step 2: Write failing codec tests**

Add to `FalImageOptionsCodecTests.cs`:

```csharp
[Fact]
public void Validate_GptImage2Edit_accepts_auto_resolution_and_match_input_image()
{
    var codec = new FalImageOptionsCodec();
    var request = Request(
        model: FalImageCapabilities.GptImage2Edit,
        resolution: "auto",
        aspectRatio: "match_input_image");

    var result = codec.Validate(
        request,
        new FalImageOptions(),
        FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit]);

    Assert.True(result.Success);
}

[Fact]
public void Validate_GptImage2Edit_rejects_references()
{
    var codec = new FalImageOptionsCodec();
    var request = Request(
        model: FalImageCapabilities.GptImage2Edit,
        resolution: "auto",
        aspectRatio: "match_input_image",
        referenceImages: new[] { MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage) });

    var result = codec.Validate(
        request,
        new FalImageOptions(),
        FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit]);

    Assert.False(result.Success);
    Assert.Equal("reference_image_paths", result.Field);
    Assert.Contains("GPT Image 2 Edit", result.Message);
}

[Theory]
[InlineData("1K", "match_input_image", "resolution")]
[InlineData("auto", "1:1", "aspect_ratio")]
public void Validate_GptImage2Edit_rejects_unsupported_resolution_or_aspect(
    string resolution,
    string aspectRatio,
    string expectedField)
{
    var codec = new FalImageOptionsCodec();
    var request = Request(
        model: FalImageCapabilities.GptImage2Edit,
        resolution: resolution,
        aspectRatio: aspectRatio);

    var result = codec.Validate(
        request,
        new FalImageOptions(),
        FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit]);

    Assert.False(result.Success);
    Assert.Equal(expectedField, result.Field);
}
```

- [ ] **Step 3: Run failing fal registration/codec tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalImageProviderRegistrationTests|FalImageOptionsCodecTests|VisionProviderRegistrationsTests"
```

Expected: fail because `FalImageCapabilities.GptImage2Edit` is not defined.

- [ ] **Step 4: Add fal capability**

Modify `FalImageCapabilities.cs`:

```csharp
public const string GptImage2Edit = "openai/gpt-image-2/edit";
```

Add model entry:

```csharp
[GptImage2Edit] = new ImageCapability(
    Id: GptImage2Edit,
    Name: "GPT Image 2 Edit",
    Status: "available",
    Resolutions: new[] { "auto" },
    AspectRatios: new[] { "match_input_image" },
    MaxReferenceImages: 0,
    SupportsImageToImage: true,
    SupportsTextToImage: false),
```

- [ ] **Step 5: Register model and per-model submission mode**

Modify `FalImageProviderRegistration.cs`:

```csharp
public ImageSubmissionMode GetSubmissionMode(string modelId) =>
    string.Equals(modelId, FalImageCapabilities.GptImage2Edit, StringComparison.Ordinal)
        ? ImageSubmissionMode.AsyncImageJob
        : ImageSubmissionMode.Sync;
```

Add `_models` entry:

```csharp
[FalImageCapabilities.GptImage2Edit] = (
    FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit],
    new FalGptImage2EditPricingModel()),
```

Create `FalGptImage2EditPricingModel` in the same file or a focused new file if preferred:

```csharp
internal sealed class FalGptImage2EditPricingModel
    : IPricingModel<ImageGenerationRequest, ImageCapability>
{
    public const string Source = "fal-openai-gpt-image-2-edit-2026-05-05";
    public const string Provenance = "fal-openai-gpt-image-2-edit-pricing-placeholder-2026-05-05";

    public string PricingSource => Source;
    public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

    public PricingResult Estimate(ImageGenerationRequest request, ImageCapability capability)
    {
        if (request is null)
            return PricingResult.Fail(new GenerationError(
                Code: GenerationErrorCode.InvalidRequest,
                Message: "Image generation request is null.",
                Retryable: false,
                Field: "request"));

        return PricingResult.Ok(
            new JobPricing(
                Currency: "USD",
                UnitPrice: null,
                Unit: "image",
                Quantity: 1m,
                TotalUsd: null,
                PricingSource: Source),
            new CostEstimate(
                Min: 0m,
                Max: 0m,
                IsExact: false,
                Provenance: Provenance));
    }

    public JobPricing? ExtractActualSpend(
        IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
        JsonNode? responseBody) => null;
}
```

- [ ] **Step 6: Add model-specific codec validation**

In `FalImageOptionsCodec.Validate`, branch before the existing Schnell resolution/aspect logic:

```csharp
if (string.Equals(capability.Id, FalImageCapabilities.GptImage2Edit, StringComparison.Ordinal))
    return ValidateGptImage2Edit(request, capability);
```

Add:

```csharp
private static ValidationResult ValidateGptImage2Edit(
    ImageGenerationRequest request,
    ImageCapability capability)
{
    var resolution = string.IsNullOrWhiteSpace(request.Resolution)
        ? "auto"
        : request.Resolution.Trim();
    if (!string.Equals(resolution, "auto", StringComparison.OrdinalIgnoreCase))
        return ValidationResult.Fail(
            "resolution must be auto for GPT Image 2 Edit.",
            "resolution");

    if (!string.IsNullOrWhiteSpace(request.AspectRatio)
        && !string.Equals(request.AspectRatio, "match_input_image", StringComparison.Ordinal))
        return ValidationResult.Fail(
            "aspect_ratio must be match_input_image for GPT Image 2 Edit.",
            "aspect_ratio");

    if ((request.ReferenceImages?.Count ?? 0) > 0)
        return ValidationResult.Fail(
            "reference_image_paths are not supported for GPT Image 2 Edit.",
            "reference_image_paths");

    return ValidationResult.Ok();
}
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalImageProviderRegistrationTests|FalImageOptionsCodecTests|VisionProviderRegistrationsTests|VisionHandlerTests"
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Fal\FalImageCapabilities.cs `
        src\Rook\Services\Vision\Image\Fal\FalImageProviderRegistration.cs `
        src\Rook\Services\Vision\Image\Fal\FalImageOptionsCodec.cs `
        src\Rook.Tests\Services\Vision\Image\Fal\FalImageProviderRegistrationTests.cs `
        src\Rook.Tests\Services\Vision\Image\Fal\FalImageOptionsCodecTests.cs `
        src\Rook.Tests\Services\Vision\VisionProviderRegistrationsTests.cs
git commit -m "feat(vision): register fal GPT Image 2 edit model"
```

---

### Task 4: GPT Image 2 Edit Source Payload Builder

**Files:**
- Create: `src/Rook/Services/Vision/Image/Fal/FalGptImage2EditSourcePayload.cs`
- Modify: `src/Rook/Services/Vision/Image/ImageMimeDetector.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderTests.cs`

- [ ] **Step 1: Write failing source payload/provider validation tests**

Add tests to `FalImageProviderTests.cs`:

```csharp
[Fact]
public async Task SubmitAsync_gpt_image_2_prompt_only_fails_before_http_call()
{
    var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));

    var outcome = await provider.SubmitAsync(
        Request(model: FalImageCapabilities.GptImage2Edit, resolution: "auto", aspectRatio: "match_input_image", referenceImages: Array.Empty<MediaRef>()),
        EmptyMedia(),
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
    Assert.Equal("input_image_path", failed.Error.Field);
    Assert.Contains("GPT Image 2 Edit requires exactly one source image", failed.Error.Message);
    Assert.Empty(handler.Requests);
}

[Fact]
public async Task SubmitAsync_gpt_image_2_rejects_reference_image_roles_before_http_call()
{
    var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
    var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
    var reference = MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage);
    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [input] = PngMedia(),
        [reference] = PngMedia(),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: FalImageCapabilities.GptImage2Edit, resolution: "auto", aspectRatio: "match_input_image", referenceImages: new[] { reference }),
        media,
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal("reference_image_paths", failed.Error.Field);
    Assert.Empty(handler.Requests);
}

[Fact]
public async Task SubmitAsync_gpt_image_2_rejects_oversized_source_before_http_call()
{
    var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
    var bytes = PngBytes();
    Array.Resize(ref bytes, 1024 * 1024 + 1);
    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
            new ResolvedMedia(bytes, "image/png"),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: FalImageCapabilities.GptImage2Edit, resolution: "auto", aspectRatio: "match_input_image", referenceImages: Array.Empty<MediaRef>()),
        media,
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal("input_image_path", failed.Error.Field);
    Assert.Contains("GPT Image 2 Edit data URI upload", failed.Error.Message);
    Assert.Empty(handler.Requests);
}

[Theory]
[InlineData("image/gif", new byte[] { 0x47, 0x49, 0x46, 0x38 })]
[InlineData("application/octet-stream", new byte[] { 0x01, 0x02, 0x03 })]
public async Task SubmitAsync_gpt_image_2_rejects_unsupported_mime_before_http_call(
    string declaredMime,
    byte[] bytes)
{
    var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
            new ResolvedMedia(bytes, declaredMime),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: FalImageCapabilities.GptImage2Edit, resolution: "auto", aspectRatio: "match_input_image", referenceImages: Array.Empty<MediaRef>()),
        media,
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal("input_image_path", failed.Error.Field);
    Assert.Contains("PNG, JPEG, or WebP", failed.Error.Message);
    Assert.Empty(handler.Requests);
}

[Fact]
public async Task SubmitAsync_gpt_image_2_rejects_declared_mime_mismatch_before_http_call()
{
    var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
            new ResolvedMedia(PngBytes(), "image/jpeg"),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: FalImageCapabilities.GptImage2Edit, resolution: "auto", aspectRatio: "match_input_image", referenceImages: Array.Empty<MediaRef>()),
        media,
        CancellationToken.None);

    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal("input_image_path", failed.Error.Field);
    Assert.Contains("MIME does not match", failed.Error.Message);
    Assert.Empty(handler.Requests);
}
```

Add helper methods if absent:

```csharp
private static IReadOnlyDictionary<MediaRef, ResolvedMedia> EmptyMedia() =>
    new Dictionary<MediaRef, ResolvedMedia>();

private static ResolvedMedia PngMedia() => new(PngBytes(), "image/png");

private static byte[] PngBytes() =>
    new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 1, 2, 3, 4 };
```

- [ ] **Step 2: Run failing source tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "SubmitAsync_gpt_image_2_prompt_only_fails_before_http_call|SubmitAsync_gpt_image_2_rejects_reference_image_roles_before_http_call|SubmitAsync_gpt_image_2_rejects_oversized_source_before_http_call|SubmitAsync_gpt_image_2_rejects_unsupported_mime_before_http_call|SubmitAsync_gpt_image_2_rejects_declared_mime_mismatch_before_http_call"
```

Expected: fail because GPT Image 2 submit path is not implemented.

- [ ] **Step 3: Add shared MIME helper**

Modify `ImageMimeDetector.cs`:

```csharp
public static bool IsPngJpegOrWebp(string mimeType) =>
    string.Equals(mimeType, "image/png", StringComparison.Ordinal)
    || string.Equals(mimeType, "image/jpeg", StringComparison.Ordinal)
    || string.Equals(mimeType, "image/webp", StringComparison.Ordinal);

public static bool IsFlux2SupportedMime(string mimeType) =>
    IsPngJpegOrWebp(mimeType);
```

- [ ] **Step 4: Add GPT Image 2 edit source payload class**

Create `FalGptImage2EditSourcePayload.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    internal sealed class FalGptImage2EditSourcePayload
    {
        public const long MaxRawBytes = 1024 * 1024;

        private FalGptImage2EditSourcePayload(string mimeType, string dataUri)
        {
            MimeType = mimeType;
            DataUri = dataUri;
        }

        public string MimeType { get; }
        public string DataUri { get; }

        public static (FalGptImage2EditSourcePayload? Payload, GenerationError? Error) FromResolvedMedia(
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (media is null)
                return (null, InvalidSource(
                    "GPT Image 2 Edit requires exactly one source image.",
                    "input_image_path"));

            if (media.Keys.Any(r => string.Equals(r.Role, ImageMediaRoles.ReferenceImage, StringComparison.Ordinal)))
                return (null, InvalidSource(
                    "GPT Image 2 Edit does not support reference_image_paths in this release.",
                    "reference_image_paths"));

            var inputs = media
                .Where(kvp => string.Equals(kvp.Key.Role, ImageMediaRoles.InputImage, StringComparison.Ordinal))
                .ToArray();
            if (inputs.Length != 1)
                return (null, InvalidSource(
                    "GPT Image 2 Edit requires exactly one source image.",
                    "input_image_path"));

            var resolved = inputs[0].Value;
            if (resolved.Bytes is null || resolved.Bytes.Length == 0)
                return (null, InvalidSource(
                    "GPT Image 2 Edit source image is empty.",
                    "input_image_path"));

            if (resolved.Bytes.LongLength > MaxRawBytes)
                return (null, InvalidSource(
                    "Source image is too large for GPT Image 2 Edit data URI upload; capture a smaller viewport or lower resolution.",
                    "input_image_path"));

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ImageMimeDetector.IsPngJpegOrWebp(detectedMime))
                return (null, InvalidSource(
                    "GPT Image 2 Edit source image must be PNG, JPEG, or WebP.",
                    "input_image_path"));

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
                return (null, InvalidSource(
                    "GPT Image 2 Edit source image MIME does not match its bytes.",
                    "input_image_path"));

            var dataUri = $"data:{detectedMime};base64,{Convert.ToBase64String(resolved.Bytes)}";
            return (new FalGptImage2EditSourcePayload(detectedMime, dataUri), null);
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

- [ ] **Step 5: Call source payload builder from fal provider**

In `FalImageProvider.SubmitAsync`, after codec validation and before API-key lookup:

```csharp
FalGptImage2EditSourcePayload? gptSourcePayload = null;
if (string.Equals(request.Model, FalImageCapabilities.GptImage2Edit, StringComparison.Ordinal))
{
    var payload = FalGptImage2EditSourcePayload.FromResolvedMedia(media);
    if (payload.Error is not null)
        return new FailedSubmitOutcome(payload.Error);
    gptSourcePayload = payload.Payload;
}
```

Pass `gptSourcePayload` into the request builder in Task 5.

- [ ] **Step 6: Run focused source validation tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalImageProviderTests"
```

Expected: source validation tests pass; queue request tests still fail until Task 5 if already written.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Fal\FalGptImage2EditSourcePayload.cs `
        src\Rook\Services\Vision\Image\ImageMimeDetector.cs `
        src\Rook\Services\Vision\Image\Fal\FalImageProvider.cs `
        src\Rook.Tests\Services\Vision\Image\Fal\FalImageProviderTests.cs
git commit -m "feat(vision): validate fal GPT Image 2 edit source payload"
```

---

### Task 5: fal Async Image Queue Submit, Status, Result, And Cancel

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Fal/FalImageProvider.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderTests.cs`

- [ ] **Step 1: Write failing fake-HTTP queue submit test**

Add to `FalImageProviderTests.cs`:

```csharp
[Fact]
public async Task SubmitAsync_gpt_image_2_posts_queue_request_with_data_uri_and_request_id_only_handle()
{
    string? capturedBody = null;
    var (provider, handler) = MakeProvider(req =>
    {
        capturedBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
        return JsonResponse(HttpStatusCode.Created, """
            {
              "request_id": "fal-gpt-1",
              "status_url": "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/status",
              "response_url": "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/response",
              "cancel_url": "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/cancel",
              "queue_position": 0
            }
            """);
    });

    var media = new Dictionary<MediaRef, ResolvedMedia>
    {
        [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] = PngMedia(),
    };

    var outcome = await provider.SubmitAsync(
        Request(model: FalImageCapabilities.GptImage2Edit, resolution: "auto", aspectRatio: "match_input_image", referenceImages: Array.Empty<MediaRef>()),
        media,
        CancellationToken.None);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(HttpMethod.Post, request.Method);
    Assert.Equal("https://queue.fal.run/openai/gpt-image-2/edit", request.RequestUri!.ToString());

    var root = Assert.IsType<JsonObject>(JsonNode.Parse(capturedBody!));
    Assert.Equal("sunlit massing study", root["prompt"]!.GetValue<string>());
    Assert.Equal("auto", root["image_size"]!.GetValue<string>());
    Assert.Equal("high", root["quality"]!.GetValue<string>());
    Assert.Equal(1, root["num_images"]!.GetValue<int>());
    Assert.Equal("png", root["output_format"]!.GetValue<string>());
    Assert.False(root.ContainsKey("sync_mode"));
    Assert.False(root.ContainsKey("mask_url"));

    var urls = Assert.IsType<JsonArray>(root["image_urls"]);
    var dataUri = Assert.Single(urls)!.GetValue<string>();
    Assert.StartsWith("data:image/png;base64,", dataUri, StringComparison.Ordinal);

    var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
    Assert.Equal("fal-gpt-1", queued.Handle.ProviderJobId);
    Assert.Null(queued.Handle.StatusUrl);
    Assert.Null(queued.Handle.ResponseUrl);
    Assert.Null(queued.Handle.CancelUrl);
    Assert.Null(queued.Handle.ProviderMetadata);
    Assert.Null(queued.Handle.ProviderResultToken);
}
```

- [ ] **Step 2: Write failing status/result/cancel tests**

Add tests:

```csharp
[Theory]
[InlineData("IN_QUEUE", typeof(InFlightStatusOutcome))]
[InlineData("IN_PROGRESS", typeof(InFlightStatusOutcome))]
[InlineData("COMPLETED", typeof(ProviderCompleteStatusOutcome))]
public async Task GetStatusAsync_gpt_image_2_reconstructs_status_url_and_maps_state(
    string state,
    Type expectedType)
{
    var (provider, handler) = MakeProvider(req => JsonResponse(HttpStatusCode.OK, $$"""
        { "status": "{{state}}", "request_id": "fal-gpt-1", "queue_position": 1 }
        """));

    var outcome = await ((IModelAwareImageProvider)provider).GetStatusAsync(
        FalImageCapabilities.GptImage2Edit,
        new ProviderJobHandle("fal-gpt-1"),
        CancellationToken.None);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(
        "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/status",
        request.RequestUri!.ToString());
    Assert.IsType(expectedType, outcome);
}

[Fact]
public async Task FetchResultAsync_gpt_image_2_parses_exactly_one_image_url_without_provider_metadata()
{
    var (provider, handler) = MakeProvider(req => JsonResponse(HttpStatusCode.OK, """
        {
          "images": [
            {
              "url": "https://v3.fal.media/files/result.png",
              "content_type": "image/png",
              "width": 1024,
              "height": 1024
            }
          ],
          "prompt": "do not persist this",
          "seed": 42
        }
        """));

    var outcome = await ((IModelAwareImageProvider)provider).FetchResultAsync(
        FalImageCapabilities.GptImage2Edit,
        new ProviderJobHandle("fal-gpt-1"),
        CancellationToken.None);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(
        "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/response",
        request.RequestUri!.ToString());

    var success = Assert.IsType<SuccessResultOutcome>(outcome);
    var artifact = Assert.Single(success.Envelope.Artifacts);
    Assert.Equal(ImageMediaRoles.Image, artifact.Role);
    Assert.Equal("image/png", artifact.DeclaredMimeType);
    Assert.Empty(artifact.ProviderMetadata);
    var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
    Assert.Equal("https://v3.fal.media/files/result.png", remote.Url.ToString());
    Assert.Empty(success.Envelope.EnvelopeMetadata);
}

[Fact]
public async Task CancelAsync_gpt_image_2_reconstructs_cancel_url_and_maps_accepted()
{
    var (provider, handler) = MakeProvider(req =>
        JsonResponse(HttpStatusCode.Accepted, "{ \"status\": \"CANCELLATION_REQUESTED\" }"));

    var outcome = await ((IModelAwareImageProvider)provider).CancelAsync(
        FalImageCapabilities.GptImage2Edit,
        new ProviderJobHandle("fal-gpt-1"),
        CancellationToken.None);

    var request = Assert.Single(handler.Requests);
    Assert.Equal(HttpMethod.Put, request.Method);
    Assert.Equal(
        "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/cancel",
        request.RequestUri!.ToString());
    Assert.IsType<CanceledOutcome>(outcome);
}
```

Add result rejection theories for zero/multiple/malformed/non-http:

```csharp
[Theory]
[InlineData("{ \"images\": [] }")]
[InlineData("{ \"images\": [ { \"url\": \"https://v3.fal.media/a.png\" }, { \"url\": \"https://v3.fal.media/b.png\" } ] }")]
[InlineData("{ \"images\": [ { } ] }")]
[InlineData("{ \"images\": [ { \"url\": \"file:///C:/tmp/result.png\" } ] }")]
public async Task FetchResultAsync_gpt_image_2_rejects_invalid_result_shape(string body)
{
    var (provider, _) = MakeProvider(req => JsonResponse(HttpStatusCode.OK, body));

    var outcome = await ((IModelAwareImageProvider)provider).FetchResultAsync(
        FalImageCapabilities.GptImage2Edit,
        new ProviderJobHandle("fal-gpt-1"),
        CancellationToken.None);

    var failed = Assert.IsType<FailedResultOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
}
```

- [ ] **Step 3: Run failing queue tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "gpt_image_2"
```

Expected: fail until fal provider queue path is implemented.

- [ ] **Step 4: Implement queue endpoint constants and request builder**

In `FalImageProvider.cs`, add:

```csharp
private static readonly Uri FluxSchnellEndpoint =
    new("https://fal.run/fal-ai/flux/schnell");
private static readonly Uri GptImage2EditQueueEndpoint =
    new("https://queue.fal.run/openai/gpt-image-2/edit");
private const string GptImage2EditCancelHttpMethod = "PUT";
```

Rename the existing `Endpoint` references for Schnell to `FluxSchnellEndpoint`.

Add:

```csharp
private static string BuildGptImage2EditRequestJson(
    ImageGenerationRequest request,
    FalGptImage2EditSourcePayload? sourcePayload)
{
    if (sourcePayload is null)
        throw new InvalidOperationException("GPT Image 2 Edit source payload was not prepared.");

    return new JsonObject
    {
        ["prompt"] = request.Prompt,
        ["image_urls"] = new JsonArray { sourcePayload.DataUri },
        ["image_size"] = "auto",
        ["quality"] = "high",
        ["num_images"] = 1,
        ["output_format"] = "png",
    }.ToJsonString();
}
```

- [ ] **Step 5: Branch submit by model id**

For GPT Image 2 edit, post to `GptImage2EditQueueEndpoint` and parse only `request_id`:

```csharp
if (string.Equals(request.Model, FalImageCapabilities.GptImage2Edit, StringComparison.Ordinal))
{
    response = await _client.PostJsonAsync(
        apiKey!,
        GptImage2EditQueueEndpoint,
        BuildGptImage2EditRequestJson(request, gptSourcePayload),
        ct).ConfigureAwait(false);

    if (!response.IsSuccessStatusCode)
        return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(response));

    return ParseGptImage2EditSubmit(response.Body);
}
```

Implement:

```csharp
private static ProviderSubmitOutcome ParseGptImage2EditSubmit(string responseJson)
{
    try
    {
        var root = JsonNode.Parse(responseJson) as JsonObject
            ?? throw new JsonException();
        if (!TryGetString(root["request_id"], out var requestId)
            || string.IsNullOrWhiteSpace(requestId))
        {
            return FailedSubmit(
                GenerationErrorCode.ExecutionFailed,
                "fal submit response was missing request id.");
        }

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

- [ ] **Step 6: Implement model-aware lifecycle methods**

Make `FalImageProvider` implement `IModelAwareImageProvider`. Keep legacy sync lifecycle methods throwing as they do today for unsupported direct calls.

Add URL builder. Do not derive this by blindly appending `/requests` to every
future fal model id. For PR-17, use an explicit GPT Image 2 edit lifecycle
route-base constant. Confirm this base against fal queue submit evidence for
this model during fake/live setup; if fal returns a different base, update this
constant and its tests while still persisting only `request_id`.

```csharp
private const string GptImage2EditLifecycleRouteBase =
    "https://queue.fal.run/openai/gpt-image-2/requests";

private static Uri GptImage2EditRequestUri(string requestId, string suffix) =>
    new($"{GptImage2EditLifecycleRouteBase}/{Uri.EscapeDataString(requestId)}/{suffix}");
```

Add model-aware methods:

```csharp
public Task<ProviderStatusOutcome> GetStatusAsync(
    string modelId,
    ProviderJobHandle handle,
    CancellationToken ct)
{
    if (!string.Equals(modelId, FalImageCapabilities.GptImage2Edit, StringComparison.Ordinal))
        return Task.FromResult<ProviderStatusOutcome>(FailedStatus(
            GenerationErrorCode.InvalidRequest,
            $"fal image provider does not support async status for model '{modelId}'.",
            "model"));

    return GetGptImage2EditStatusAsync(handle, ct);
}
```

Mirror for cancel/result and implement `GetGptImage2EditStatusAsync`, `CancelGptImage2EditAsync`, and `FetchGptImage2EditResultAsync` using `_client.GetAsync` / `_client.SendAsync`. Reuse `FalLifecycleMapper.MapStatus(handle, root)` for status. For cancel, map:

```csharp
if (response.StatusCode == 202 || response.IsSuccessStatusCode)
    return new CanceledOutcome();
if (response.StatusCode == 400)
    return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
return new FailedCancelOutcome(FalErrorMapper.MapHttpFailure(response));
```

For result, parse exactly one image URL and return:

```csharp
var artifact = new ResultArtifact(
    Role: ImageMediaRoles.Image,
    Body: new RemoteArtifactBody(url),
    DeclaredMimeType: declaredMimeType,
    ProviderMetadata: new Dictionary<string, JsonNode>());

return new SuccessResultOutcome(
    new ProviderResultEnvelope(
        new[] { artifact },
        new Dictionary<string, JsonNode>()));
```

- [ ] **Step 7: Run fal provider tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalImageProviderTests|FalImageOptionsCodecTests|FalImageProviderRegistrationTests"
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Fal\FalImageProvider.cs `
        src\Rook.Tests\Services\Vision\Image\Fal\FalImageProviderTests.cs
git commit -m "feat(vision): add fal GPT Image 2 edit queue lifecycle"
```

---

### Task 6: Durable And Bridge Leakage Hardening

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactory.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs`
- Test: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Fal/FalImageProviderTests.cs`

- [ ] **Step 1: Write failing sanitizer tests**

Add to `ImageJobLedgerRecordFactoryTests.cs`:

```csharp
[Theory]
[InlineData("https://v3.fal.media/files/result.png")]
[InlineData("https://queue.fal.run/openai/gpt-image-2/requests/id/status")]
[InlineData("https://fal.run/openai/gpt-image-2/edit")]
[InlineData("{\"image_urls\":[\"data:image/png;base64,AAAA\"]}")]
[InlineData("{\"request_id\":\"fal-gpt-1\",\"status_url\":\"https://queue.fal.run/x\"}")]
public void SanitizeError_redacts_fal_transport_details(string message)
{
    var safe = ImageJobLedgerRecordFactory.SanitizeError(new GenerationError(
        GenerationErrorCode.ExecutionFailed,
        message,
        Retryable: false));

    Assert.NotNull(safe);
    Assert.Equal("Image job failed; provider details were redacted.", safe!.Message);
}
```

- [ ] **Step 2: Write bridge leakage regression**

Add to `ImageJobOpHandlerTests.cs`:

```csharp
[Fact]
public void DispatchOffUi_Status_DoesNotExposeFalTransportInError()
{
    var jobId = Guid.Parse("cccccccc-cccc-cccc-cccc-cccccccccccc");
    var manager = new StubImageJobManager
    {
        StatusImpl = _ => ImageJobStatusResult.Failed(
            ImageJobState.Error,
            new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "fal failed with {\"image_urls\":[\"data:image/png;base64,AAAA\"],\"status_url\":\"https://queue.fal.run/x\"}",
                Retryable: false)),
    };
    var handler = new ImageJobOpHandler(manager, NewVisionHandler());

    var response = handler.DispatchOffUi($$"""
        { "op": "image_job_status", "job_id": "{{jobId:D}}" }
        """);
    var json = JsonSerializer.Serialize(response.Data);

    Assert.DoesNotContain("image_urls", json);
    Assert.DoesNotContain("data:image/", json);
    Assert.DoesNotContain("queue.fal.run", json);
    Assert.Contains("redacted", json, StringComparison.OrdinalIgnoreCase);
}
```

- [ ] **Step 3: Write provider metadata non-leak test**

Extend `FetchResultAsync_gpt_image_2_parses_exactly_one_image_url_without_provider_metadata` from Task 5 to assert serialized envelope has no fal/source transport keys except the in-memory `RemoteArtifactBody` URL:

```csharp
var serializedMetadata = string.Join(
    "\n",
    artifact.ProviderMetadata.Select(kvp => $"{kvp.Key}:{kvp.Value}"))
    + "\n"
    + string.Join("\n", success.Envelope.EnvelopeMetadata.Select(kvp => $"{kvp.Key}:{kvp.Value}"));
Assert.DoesNotContain("fal.media", serializedMetadata);
Assert.DoesNotContain("image_urls", serializedMetadata);
Assert.DoesNotContain("request_id", serializedMetadata);
Assert.DoesNotContain("prompt", serializedMetadata);
```

- [ ] **Step 4: Run failing leakage tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "SanitizeError_redacts_fal_transport_details|DispatchOffUi_Status_DoesNotExposeFalTransportInError|FetchResultAsync_gpt_image_2_parses_exactly_one_image_url_without_provider_metadata"
```

Expected: sanitizer test fails until banned strings are updated.

- [ ] **Step 5: Add fal redaction strings**

Modify `ImageJobLedgerRecordFactory.BannedSubstrings`:

```csharp
"fal.media",
"queue.fal.run",
"fal.run",
"image_urls",
"\"request_id\"",
```

Do not add bare `request_id` because the ledger intentionally stores a safe scalar request id under `provider_job_id`.

- [ ] **Step 6: Run leakage tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobLedgerRecordFactoryTests|ImageJobOpHandlerTests|FalImageProviderTests"
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerRecordFactory.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobLedgerRecordFactoryTests.cs `
        src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs `
        src\Rook.Tests\Services\Vision\Image\Fal\FalImageProviderTests.cs
git commit -m "test(vision): harden fal image job leakage boundaries"
```

---

### Task 7: Bridge, Catalog, And UI Routing Gates

**Files:**
- Modify only if needed: `src/Rook/UI/Vision/Resources/app.js`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Test: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add catalog and bridge request tests**

Add to `VisionHandlerTests.cs`:

```csharp
[Fact]
public async Task ListImageModels_ExposesFalGptImage2EditAsSourceImageAsyncModel()
{
    var handler = NewHandlerWithSecrets(new InMemoryGenerationSecretStore());

    var response = handler.ListImageModels(new Dictionary<string, JsonElement>());
    var json = JsonSerializer.Serialize(response.Data);

    Assert.Contains("openai/gpt-image-2/edit", json);
    Assert.Contains("\"provider_name\":\"fal\"", json);
    Assert.Contains("\"submission_mode\":\"async_image_job\"", json);
    Assert.Contains("\"supports_image_to_image\":true", json);
    Assert.Contains("\"supports_text_to_image\":false", json);
    Assert.Contains("\"max_reference_images\":0", json);
    Assert.DoesNotContain("openai/gpt-image-2\"", json);
}
```

Use the existing handler construction pattern in the file; if method names differ, place the assertions in the existing model-list test.

Add to `ImageJobOpHandlerTests.cs`:

```csharp
[Fact]
public async Task Start_GptImage2Edit_WithSource_UsesImageJobPathAndResolvedFalModel()
{
    var inputPath = WriteTempPng();
    var manager = new CapturingImageJobManager();
    var handler = MakeHandler(manager, DefaultRegistryWithFalGptImage2Edit());

    var response = await handler.DispatchAsync($$"""
        {
          "op": "image_generate_start",
          "model": "openai/gpt-image-2/edit",
          "prompt": "make this model more photoreal",
          "resolution": "auto",
          "aspect_ratio": "match_input_image",
          "input_image_path": "{{Escape(inputPath)}}"
        }
        """);

    Assert.True(response.Success);
    Assert.Equal("openai/gpt-image-2/edit", manager.CapturedStart!.Request.Model);
    Assert.Equal("fal", manager.CapturedStart.ResolvedModel!.ProviderName);
    Assert.Equal(ImageSubmissionMode.AsyncImageJob, manager.CapturedStart.ResolvedModel.SubmissionMode);
    Assert.Contains(
        manager.CapturedStart.ResolvedMedia,
        kvp => kvp.Key.Role == ImageMediaRoles.InputImage);
}

[Fact]
public async Task Start_GptImage2Edit_WithReferenceImage_FailsBeforeManagerSubmit()
{
    var inputPath = WriteTempPng();
    var referencePath = WriteTempPng();
    var manager = new CapturingImageJobManager();
    var handler = MakeHandler(manager, DefaultRegistryWithFalGptImage2Edit());

    var response = await handler.DispatchAsync($$"""
        {
          "op": "image_generate_start",
          "model": "openai/gpt-image-2/edit",
          "prompt": "make this model more photoreal",
          "resolution": "auto",
          "aspect_ratio": "match_input_image",
          "input_image_path": "{{Escape(inputPath)}}",
          "reference_image_paths": [ "{{Escape(referencePath)}}" ]
        }
        """);

    Assert.False(response.Success);
    Assert.Null(manager.CapturedStart);
    var json = JsonSerializer.Serialize(response.Data);
    Assert.Contains("reference_image_paths", json);
}
```

- [ ] **Step 2: Add UI resource assertions**

Add or extend `VisionWebSurfaceTests.cs`:

```csharp
[Fact]
public void AppJs_SourceImageAsyncRoutingIsProviderNeutralForFalGptImage2Edit()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("function isSourceImageAsyncImageModel", js);
    Assert.Contains("model.submission_mode === \"async_image_job\"", js);
    Assert.Contains("model.supports_image_to_image !== false", js);
    Assert.Contains("await generateImageJob(prompt, model, sourcePath);", js);
    Assert.Contains("await studioGenerateImageJob(args, model);", js);
    Assert.DoesNotContain("provider_name === \"replicate\"", js);
    Assert.DoesNotContain("openai/gpt-image-2/edit", js);
}
```

The final assertion keeps the UI provider-neutral; model-specific behavior belongs in catalog metadata and provider code.

- [ ] **Step 3: Run UI/bridge focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionHandlerTests|ImageJobOpHandlerTests|VisionWebSurfaceTests"
```

Expected: pass. If a UI assertion fails because `resolution: auto` is not valid in the selector, make the smallest `app.js` change needed to select the catalog-provided first resolution, following the existing PR-16 fallback pattern.

- [ ] **Step 4: Commit**

```powershell
git add src\Rook.Tests\Handlers\VisionHandlerTests.cs `
        src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs `
        src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs `
        src\Rook\UI\Vision\Resources\app.js
git commit -m "test(vision): cover fal GPT Image 2 edit bridge routing"
```

---

### Task 8: Manager Restart, Result Materialization, And Ledger Leakage

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`
- Modify if needed: `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`

- [ ] **Step 1: Write fake provider integration test for GPT Image 2 edit materialization**

Add to `ImageJobManagerTests.cs`:

```csharp
[Fact]
public async Task FalGptImage2Edit_job_materializes_without_leaking_fal_transport_to_ledger_or_artifact_metadata()
{
    var provider = new CompletingModelAwareProvider(
        providerName: "fal",
        modelId: "openai/gpt-image-2/edit",
        remoteUrl: new Uri("https://v3.fal.media/files/result.png"));
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new SingleModelRegistration(
            provider,
            "fal",
            "openai/gpt-image-2/edit",
            ImageSubmissionMode.AsyncImageJob),
    });
    var ledger = new FakeImageJobLedger();
    var artifactStore = MakeArtifactStore();
    var materializer = new ImageArtifactMaterializer(new TestHttpMessageHandler
    {
        OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new ByteArrayContent(PngBytes()),
        },
    });
    var manager = MakeManager(
        registry,
        artifactStore,
        ledger: ledger,
        materializer: materializer,
        pollInterval: TimeSpan.FromMilliseconds(1));

    var submit = await manager.SubmitAsync(
        new ImageJobStartRequest(
            new ImageGenerationRequest(
                Model: "openai/gpt-image-2/edit",
                Prompt: "preserved local artifact prompt",
                Resolution: "auto",
                AspectRatio: "match_input_image",
                NumberOfImages: 1,
                ReferenceImages: Array.Empty<MediaRef>(),
                Options: new FalImageOptions()),
            new Dictionary<MediaRef, ResolvedMedia>
            {
                [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
                    new ResolvedMedia(PngBytes(), "image/png"),
            },
            parentArtifactIds: Array.Empty<Guid>(),
            resolvedModel: registry.ResolveForTest("openai/gpt-image-2/edit")),
        CancellationToken.None);

    Assert.Null(submit.Error);
    var complete = await WaitForCompleteAsync(manager, submit.JobId!.Value);
    Assert.NotNull(complete.ArtifactId);

    var ledgerText = string.Join("\n", ledger.Records.Select(r => JsonSerializer.Serialize(r)));
    Assert.Contains("\"ProviderJobId\":\"fal-gpt-1\"", ledgerText);
    Assert.DoesNotContain("fal.media", ledgerText);
    Assert.DoesNotContain("queue.fal.run", ledgerText);
    Assert.DoesNotContain("image_urls", ledgerText);
    Assert.DoesNotContain("data:image/", ledgerText);
    Assert.DoesNotContain("preserved local artifact prompt", ledgerText);

    var artifact = artifactStore.Get(complete.ArtifactId!.Value)!;
    var metadata = JsonSerializer.Serialize(artifact.Metadata);
    Assert.Contains("preserved local artifact prompt", metadata);
    Assert.DoesNotContain("fal.media", metadata);
    Assert.DoesNotContain("queue.fal.run", metadata);
    Assert.DoesNotContain("image_urls", metadata);
    Assert.DoesNotContain("data:image/", metadata);
    Assert.DoesNotContain("fal-gpt-1", metadata);
}
```

Use existing image-job test helpers for `MakeManager`, `MakeArtifactStore`, and waiting for completion. If `ResolveForTest` does not exist, inline:

```csharp
Assert.True(registry.TryResolve("openai/gpt-image-2/edit", out var resolved));
```

and pass `resolved`.

- [ ] **Step 2: Write restart cancel test with request-id-only handle**

Add:

```csharp
[Fact]
public async Task FalGptImage2Edit_cancel_after_restart_uses_request_id_only()
{
    var provider = new ModelAwareLifecycleProvider("fal");
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new SingleModelRegistration(provider, "fal", "openai/gpt-image-2/edit", ImageSubmissionMode.AsyncImageJob),
    });
    var ledger = new FakeImageJobLedger();
    var jobId = Guid.Parse("dddddddd-dddd-dddd-dddd-dddddddddddd");
    var now = DateTimeOffset.Parse("2026-05-05T12:00:00Z", CultureInfo.InvariantCulture);
    ledger.Append(ImageJobLedgerRecordFactory.WithState(
        ImageJobLedgerRecordFactory.FromInitial(jobId, "fal", "openai/gpt-image-2/edit", ImageJobState.Queued, now),
        ImageJobState.Interrupted,
        now.AddSeconds(1),
        providerJobId: "fal-gpt-1"));
    var manager = MakeManager(registry, ledger: ledger);

    var cancel = await manager.CancelAsync(jobId, CancellationToken.None);

    Assert.Null(cancel.Error);
    Assert.Equal(ImageJobState.Cancelled, cancel.State);
    Assert.Equal("openai/gpt-image-2/edit", Assert.Single(provider.CancelModels));
    Assert.Equal("fal-gpt-1", Assert.Single(provider.CancelJobIds));
    var text = string.Join("\n", ledger.Records.Select(r => JsonSerializer.Serialize(r)));
    Assert.DoesNotContain("status_url", text);
    Assert.DoesNotContain("response_url", text);
    Assert.DoesNotContain("cancel_url", text);
    Assert.DoesNotContain("queue.fal.run", text);
}
```

- [ ] **Step 3: Run manager tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobManagerTests"
```

Expected: pass. If artifact metadata includes fal URLs, fix the fal GPT result path to return empty provider metadata rather than filtering in the manager.

- [ ] **Step 4: Commit**

```powershell
git add src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobManagerTests.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs
git commit -m "test(vision): cover fal GPT Image 2 edit durable lifecycle"
```

---

### Task 9: Boundary Scan And Focused Test Gate

**Files:**
- No source edits expected.

- [ ] **Step 1: Run focused managed test suites**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalImageProviderTests|FalImageProviderRegistrationTests|FalImageOptionsCodecTests|DefaultImageProviderRegistryTests|ImageJobManagerTests|ImageJobLedgerRecordFactoryTests|ImageJobOpHandlerTests|VisionHandlerTests|VisionWebSurfaceTests|VisionProviderRegistrationsTests"
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full managed test suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: full suite passes.

- [ ] **Step 3: Run diff check**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: no whitespace errors.

- [ ] **Step 4: Run boundary scans**

Run:

```powershell
rg -n "openai/gpt-image-2|GptImage2|GPT Image 2|image_generate_start|image_job_status|image_jobs|image_job_result|image_job_cancel" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected: no PR-17 image job/model exposure through native, MCP, or internal registrar surfaces. If existing unrelated `image_*` references appear, inspect and document them before proceeding.

Run:

```powershell
rg -n "fal.media|queue.fal.run|image_urls|data:image/" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected: no hits.

- [ ] **Step 5: Commit any final test-only adjustments**

If no files changed, skip this commit. If test assertions needed small updates:

```powershell
git add <changed-files>
git commit -m "test(vision): verify fal GPT Image 2 edit boundaries"
```

---

### Task 10: Build, Deploy, Live Rhino Smoke, And PR Closeout

**Files:**
- No source edits expected unless live fal smoke exposes a provider schema bug.

- [ ] **Step 1: Build managed companion**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -c Release -f net7.0
```

Expected: build succeeds with no errors. Existing warnings may remain if unrelated.

- [ ] **Step 2: Deploy managed companion to Rhino plugin folder**

Use the existing deployment script or copy the net7.0 companion outputs to:

```text
C:\Users\aryan\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\
```

Verify deployed `Rook.rhp`, `Rook.deps.json`, and `Rook.runtimeconfig.json` hashes match:

```powershell
Get-FileHash src\Rook\bin\Release\net7.0\Rook.rhp
Get-FileHash C:\Users\aryan\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.rhp
```

Expected: SHA-256 hashes match.

- [ ] **Step 3: Live Rhino fal smoke**

With Rhino closed before deployment and reopened after deployment:

1. Configure or confirm fal API key in RookVision Settings.
2. Capture a viewport/source image in Generate or select an existing Studio source.
3. Select `GPT Image 2 Edit`.
4. Enter a non-sensitive smoke prompt.
5. Submit and confirm async job status progresses through queued/submitting/polling/materializing.
6. Confirm local generated image appears in Gallery.
7. Confirm `image_jobs`, `image_job_status`, and `image_job_result` work through the UI path.
8. Restart Rhino and confirm completed artifact persists in Gallery.
9. If timing allows, start another job and cancel while queued; confirm UI reports cancellation without exposing fal URLs or request ids.

Do not commit screenshots, prompts, source images, data URIs, fal URLs, provider envelopes, or credentials.

- [ ] **Step 4: If live smoke exposes fal schema drift, fix with a narrow commit**

If fal rejects the request, inspect only sanitized status/error evidence and fake-test the schema correction before changing code. Example commit:

```powershell
git add src\Rook\Services\Vision\Image\Fal\FalImageProvider.cs `
        src\Rook.Tests\Services\Vision\Image\Fal\FalImageProviderTests.cs
git commit -m "fix(vision): align fal GPT Image 2 edit request schema"
```

- [ ] **Step 5: Final verification**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FalImageProviderTests|ImageJobManagerTests|ImageJobOpHandlerTests|VisionWebSurfaceTests"
dotnet test src\Rook.Tests\Rook.Tests.csproj
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: focused tests pass, full suite passes, diff check passes, branch is clean except being ahead of `origin/main`.

- [ ] **Step 6: Request review before merge**

Use `superpowers:requesting-code-review` before opening or merging the PR. Include:

- PR-17 scope summary;
- live Rhino fal smoke result;
- focused and full test output;
- boundary scan result;
- explicit note that prompt metadata in completed local artifacts is preserved by design.

---

## Plan Self-Review

- Spec coverage: Tasks cover model-level submission mode, single provider identity, provider + model restart lookup, request-id-only handles, bounded data URI source transport, fixed fal request body, queue submit/status/result/cancel, leakage boundaries, UI routing, fake HTTP tests, boundary scans, and live Rhino smoke.
- Scope check: Plan stays inside managed Vision image stack. No native, MCP, public HTTP, dynamic discovery, mask, reference, upload, prompt-only GPT Image 2, or durable schema work is included.
- Type consistency: Model id is consistently `openai/gpt-image-2/edit`; provider id is consistently `fal`; model-level mode method is `GetSubmissionMode(string modelId)`; model-aware lifecycle interface is `IModelAwareImageProvider`; durable safe scalar remains `provider_job_id`.
- Placeholder scan: The plan contains no placeholder tasks; every implementation task names files, methods, assertions, commands, and expected outcomes.
