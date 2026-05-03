# PR-14 Replicate Settings And Visible Image Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Replicate `black-forest-labs/flux-schnell` visible and usable from the RookVision Generate tab through managed Settings, backend-owned image catalog routing, and bridge-only async image jobs.

**Architecture:** Add a backend-owned image `submission_mode` contract at the image registration/descriptor edge, expose Replicate through `VisionProviderRegistrations`, and route prompt-only Generate submissions for async image models through existing bridge-only `ImageJobOpHandler` ops. Keep the synchronous `generate` path source-image based, keep Studio source/edit oriented, and keep native/MCP/`NativeGhBridgeRegistrar` surfaces closed.

**Tech Stack:** C# `net7.0;net48`, xUnit, existing managed Vision provider seams, existing `ImageJobManager`, embedded Vision HTML/CSS/JavaScript resources, fake HTTP tests only.

---

## Scope Guard

Do:

- Add Replicate to managed Vision image registration and credential metadata.
- Add backend-owned `submission_mode` to image descriptors.
- Allow prompt-only `image_generate_start` only for async image-job text-to-image models.
- Keep `generate` requiring `input_image_path`.
- Wire Replicate authenticated output request selection into the production image job manager.
- Update Generate tab only for prompt-only async T2I.
- Keep Studio T2I-only models visible but disabled/incompatible.
- Add deterministic tests and boundary scans.

Do not:

- Modify `src/RookNative/**`.
- Modify `mcp_server/**`.
- Add image job or credential ops to `NativeGhBridgeRegistrar`.
- Add native/MCP/public HTTP parity.
- Add a global mode toggle.
- Add Studio prompt-only behavior.
- Add Replicate image-to-image, reference images, extra models, provider knobs, dynamic catalog, or normal live tests.

---

## File Structure

Create:

- `src/Rook/Services/Vision/Image/ImageSubmissionMode.cs`
  - Small enum used by registrations, resolved models, and descriptors.

Modify:

- `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs`
  - Add `SubmissionMode`.
- `src/Rook/Services/Vision/Image/ImageModelDescriptor.cs`
  - Add `SubmissionMode`.
- `src/Rook/Services/Vision/Image/ResolvedImageModel.cs`
  - Add `SubmissionMode`.
- `src/Rook/Services/Vision/Image/DefaultImageProviderRegistry.cs`
  - Stamp registration mode onto resolved models and descriptors.
- `src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs`
  - `SubmissionMode = ImageSubmissionMode.Sync`.
- `src/Rook/Services/Vision/Image/Fal/FalImageProviderRegistration.cs`
  - `SubmissionMode = ImageSubmissionMode.Sync`.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
  - `SubmissionMode = ImageSubmissionMode.AsyncImageJob`.
- `src/Rook/Services/Vision/VisionProviderRegistrations.cs`
  - Add Replicate image registration and credential metadata.
- `src/Rook/RookSubsystemRoot.cs`
  - Include Replicate secret provider and authenticated output request selector in image jobs.
- `src/Rook/Handlers/VisionHandler.cs`
  - Emit `submission_mode`, accept Replicate provider metadata, add prompt-only work-item mode.
- `src/Rook/Handlers/ImageJobOpHandler.cs`
  - Call work-item builder with prompt-only async image-job mode.
- `src/Rook/UI/Vision/Resources/app.js`
  - Route Generate by `submission_mode`, disable source/reference controls for T2I-only async models, poll jobs.
- `src/Rook/UI/Vision/Resources/styles.css`
  - Add disabled styling for Generate source/reference sections.

Tests:

- `src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`
- `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

---

## Task 1: Add Backend-Owned Image Submission Mode

**Files:**
- Create: `src/Rook/Services/Vision/Image/ImageSubmissionMode.cs`
- Modify: `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/ImageModelDescriptor.cs`
- Modify: `src/Rook/Services/Vision/Image/ResolvedImageModel.cs`
- Modify: `src/Rook/Services/Vision/Image/DefaultImageProviderRegistry.cs`
- Modify: `src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/Fal/FalImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`

- [ ] **Step 1: Write failing submission-mode registry tests**

In `src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs`, add:

```csharp
[Fact]
public void Resolved_and_described_gemini_models_are_sync_submission_mode()
{
    var registry = RegistryWithGemini();

    Assert.True(registry.TryResolve(GeminiImageCapabilities.NanoBanana2, out var resolved));
    Assert.Equal(ImageSubmissionMode.Sync, resolved.SubmissionMode);

    var descriptor = Assert.Single(
        registry.EnumerateAllModels(),
        m => m.ModelId == GeminiImageCapabilities.NanoBanana2);
    Assert.Equal(ImageSubmissionMode.Sync, descriptor.SubmissionMode);
}
```

In `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`, add:

```csharp
[Fact]
public void Registration_declares_async_image_job_submission_mode()
{
    var registration = new ReplicateImageProviderRegistration(
        new FakeImageProvider());

    Assert.Equal(ImageSubmissionMode.AsyncImageJob, registration.SubmissionMode);
}
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "DefaultImageProviderRegistryTests|ReplicateImageProviderRegistrationTests"
```

Expected: compile failure because `ImageSubmissionMode` and related properties do not exist.

- [ ] **Step 3: Add submission mode enum**

Create `src/Rook/Services/Vision/Image/ImageSubmissionMode.cs`:

```csharp
namespace Rook.Services.Vision.Image
{
    public enum ImageSubmissionMode
    {
        Sync = 0,
        AsyncImageJob = 1,
    }
}
```

- [ ] **Step 4: Add submission mode to registration, resolved model, and descriptor types**

Update `IImageProviderRegistration`:

```csharp
public interface IImageProviderRegistration
{
    string ProviderName { get; }
    ImageSubmissionMode SubmissionMode { get; }
    IImageProvider Provider { get; }
    IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
    IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models { get; }
    IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
}
```

Update `ImageModelDescriptor`:

```csharp
namespace Rook.Services.Vision.Image
{
    public sealed record ImageModelDescriptor(
        string ModelId,
        string ProviderName,
        ImageSubmissionMode SubmissionMode,
        ImageCapability Capability,
        string PricingSource);
}
```

Update `ResolvedImageModel`:

```csharp
public sealed record ResolvedImageModel(
    string ModelId,
    string ProviderName,
    ImageSubmissionMode SubmissionMode,
    IImageProvider Provider,
    ImageCapability Capability,
    IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel,
    IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec)
    : IResolvedModel
{
    IModelCapability IResolvedModel.Capability => Capability;
    public string PricingSource => PricingModel.PricingSource;
}
```

- [ ] **Step 5: Stamp registration mode in `DefaultImageProviderRegistry`**

In `DefaultImageProviderRegistry`, validate the enum and pass it into resolved/descriptor records:

```csharp
if (!Enum.IsDefined(typeof(ImageSubmissionMode), reg.SubmissionMode))
    throw new InvalidOperationException(
        $"Provider '{reg.ProviderName}' registration has invalid SubmissionMode '{reg.SubmissionMode}'.");
```

Update resolved construction:

```csharp
var resolved = new ResolvedImageModel(
    ModelId: kvp.Key,
    ProviderName: reg.ProviderName,
    SubmissionMode: reg.SubmissionMode,
    Provider: reg.Provider,
    Capability: cap,
    PricingModel: pricing,
    OptionsCodec: reg.OptionsCodec);
```

Update descriptor construction:

```csharp
list.Add(new ImageModelDescriptor(
    ModelId: m.ModelId,
    ProviderName: m.ProviderName,
    SubmissionMode: m.SubmissionMode,
    Capability: m.Capability,
    PricingSource: m.PricingModel.PricingSource));
```

- [ ] **Step 6: Set modes on concrete registrations and test fakes**

In `GeminiImageProviderRegistration`:

```csharp
public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
```

In `FalImageProviderRegistration`:

```csharp
public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
```

In `ReplicateImageProviderRegistration`:

```csharp
public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.AsyncImageJob;
```

In test-only registration classes that implement `IImageProviderRegistration`, add:

```csharp
public ImageSubmissionMode SubmissionMode { get; init; } = ImageSubmissionMode.Sync;
```

If a nested test class cannot use `init` cleanly on `net48`, use a constructor parameter:

```csharp
public FakeImageProviderRegistration(..., ImageSubmissionMode submissionMode = ImageSubmissionMode.Sync)
{
    SubmissionMode = submissionMode;
    ...
}

public ImageSubmissionMode SubmissionMode { get; }
```

- [ ] **Step 7: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "DefaultImageProviderRegistryTests|ReplicateImageProviderRegistrationTests"
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\Services\Vision\Image `
        src\Rook.Tests\Services\Vision\Image `
        src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "feat(vision): add image submission mode metadata"
```

---

## Task 2: Expose Replicate In Managed Vision Registrations And Credentials

**Files:**
- Modify: `src/Rook/Services/Vision/VisionProviderRegistrations.cs`
- Modify: `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Update failing default-registration tests**

In `VisionProviderRegistrationsTests`, replace `CreateCredentialMetadata_merges_gemini_owner_and_fal_from_image_and_video` with:

```csharp
[Fact]
public void CreateCredentialMetadata_merges_gemini_fal_and_replicate()
{
    var metadata = VisionProviderRegistrations.CreateCredentialMetadata();

    var providers = metadata.EnumerateProviders().ToArray();

    Assert.Equal(new[] { "gemini", "fal", "replicate" }, providers.Select(p => p.ProviderName));
    Assert.Contains(
        Assert.Single(providers, p => p.ProviderName == "gemini").SecretRequirements,
        r => r.Key == GenerationSecretKeys.GeminiApiKey);
    Assert.Contains(
        Assert.Single(providers, p => p.ProviderName == "fal").SecretRequirements,
        r => r.Key == GenerationSecretKeys.FalApiKey);

    var replicate = Assert.Single(providers, p => p.ProviderName == "replicate");
    var requirement = Assert.Single(replicate.SecretRequirements);
    Assert.Equal(GenerationSecretKeys.ReplicateApiToken, requirement.Key);
    Assert.Equal("Replicate API token", requirement.DisplayName);
    Assert.True(requirement.IsRequired);
    Assert.True(requirement.IsSensitive);

    Assert.DoesNotContain(providers, p => p.ProviderName == "veo");
}
```

Replace `CreateImageRegistrations_default_composition_does_not_reference_replicate` with:

```csharp
[Fact]
public void CreateImageRegistrations_default_composition_includes_replicate()
{
    var registrations = VisionProviderRegistrations.CreateImageRegistrations(
        () => null,
        () => null,
        () => null);
    var registry = new DefaultImageProviderRegistry(registrations);

    Assert.True(registry.TryResolve("black-forest-labs/flux-schnell", out var resolved));
    Assert.Equal("replicate", resolved.ProviderName);
    Assert.Equal(ImageSubmissionMode.AsyncImageJob, resolved.SubmissionMode);
    Assert.True(registry.TryResolveProviderByName("replicate", out _));
}
```

Keep `CreateCredentialMetadata_does_not_construct_provider_registrations`, but remove the assertions that forbid Replicate symbols. It should still assert:

```csharp
Assert.DoesNotContain("CreateImageRegistrations", methodBody);
Assert.DoesNotContain("CreateVideoRegistrations", methodBody);
Assert.DoesNotContain("new VeoProvider", methodBody);
Assert.DoesNotContain("new FalVideoProvider", methodBody);
Assert.DoesNotContain("new ReplicateImageProvider", methodBody);
```

- [ ] **Step 2: Update failing handler credential tests**

In `VisionHandlerTests`, replace `SetProviderSecret_RejectsReplicateBecauseItIsNotCredentialOwner` with:

```csharp
[Fact]
public void SetProviderSecret_AcceptsReplicateCredentialOwner()
{
    var store = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(store);
    var args = VisionHandler.ParseObjectBody(
        "{\"provider_name\":\"replicate\",\"secret_key\":\"replicate.api_token\",\"value\":\"replicate-token\"}");

    var response = handler.SetProviderSecret(args);

    Assert.True(response.Success);
    Assert.Equal("replicate-token", store.GetSecret(GenerationSecretKeys.ReplicateApiToken));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.Equal("replicate", data["provider_name"]);
    Assert.Equal(GenerationSecretKeys.ReplicateApiToken, data["secret_key"]);
    Assert.Equal(true, data["has_secret"]);
    Assert.NotNull(data["preview"]);
}
```

Replace `ClearProviderSecret_RejectsReplicateAndPreservesStoredSecrets` with:

```csharp
[Fact]
public void ClearProviderSecret_RemovesDeclaredReplicateKey()
{
    var store = new InMemoryGenerationSecretStore();
    store.SetSecret(GenerationSecretKeys.ReplicateApiToken, "replicate-token");
    var handler = NewHandlerWithSecrets(store);
    var args = VisionHandler.ParseObjectBody(
        "{\"provider_name\":\"replicate\",\"secret_key\":\"replicate.api_token\"}");

    var response = handler.ClearProviderSecret(args);

    Assert.True(response.Success);
    Assert.Null(store.GetSecret(GenerationSecretKeys.ReplicateApiToken));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.Equal("replicate", data["provider_name"]);
    Assert.Equal(GenerationSecretKeys.ReplicateApiToken, data["secret_key"]);
    Assert.Equal(false, data["has_secret"]);
    Assert.Null(data["preview"]);
}
```

In `GetSettingsOverview_IncludesProviderCredentialsForGeminiAndFal`, rename the test to include Replicate and add:

```csharp
AssertProviderCredential(
    credentials,
    "replicate",
    "missing_required_secret",
    GenerationSecretKeys.ReplicateApiToken,
    "missing");
```

In `GetSettingsOverview_WithLegacyVisionSecretStore_DoesNotThrow`, add the same Replicate missing assertion. Delete calls to `AssertNoReplicateCredentialRequirements`.

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionProviderRegistrationsTests|SetProviderSecret_AcceptsReplicate|ClearProviderSecret_RemovesDeclaredReplicate|GetSettingsOverview"
```

Expected: FAIL because production registration and credential metadata still omit Replicate.

- [ ] **Step 4: Add Replicate to production registration helper**

Update `src/Rook/Services/Vision/VisionProviderRegistrations.cs` usings:

```csharp
using Rook.Services.Vision.Image.Replicate;
```

Change `CreateImageRegistrations` signature:

```csharp
public static IImageProviderRegistration[] CreateImageRegistrations(
    Func<string?> geminiKeyProvider,
    Func<string?> falKeyProvider,
    Func<string?> replicateTokenProvider)
    => new IImageProviderRegistration[]
    {
        new GeminiImageProviderRegistration(new GeminiImageProvider(geminiKeyProvider)),
        new FalImageProviderRegistration(new FalImageProvider(falKeyProvider)),
        new ReplicateImageProviderRegistration(new ReplicateImageProvider(replicateTokenProvider)),
    };
```

Add Replicate metadata in `CreateCredentialMetadata()`:

```csharp
new ProviderCredentialMetadata(
    ReplicateImageCapabilities.ProviderName,
    Array.AsReadOnly(new[]
    {
        new ProviderSecretRequirement(
            GenerationSecretKeys.ReplicateApiToken,
            "Replicate API token",
            isRequired: true),
    })),
```

- [ ] **Step 5: Update all `CreateImageRegistrations` call sites**

In `VisionHandler` constructor:

```csharp
VisionProviderRegistrations.CreateImageRegistrations(
    GetGeminiApiKey,
    GetFalApiKey,
    GetReplicateApiToken)
```

Add:

```csharp
private string? GetReplicateApiToken()
{
    if (_generationSecrets is not null)
        return _generationSecrets.GetSecret(GenerationSecretKeys.ReplicateApiToken);
    return null;
}
```

In `RookSubsystemRoot.ImageJobs` lazy construction, pass:

```csharp
() => SharedGenerationSecretStore.GetSecret(GenerationSecretKeys.ReplicateApiToken)
```

Update test call sites in `VisionProviderRegistrationsTests` to pass the third provider.

- [ ] **Step 6: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionProviderRegistrationsTests|VisionHandlerTests"
```

Expected: PASS or only failures from tests handled in later tasks that now expect `submission_mode`.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\VisionProviderRegistrations.cs `
        src\Rook\Handlers\VisionHandler.cs `
        src\Rook\RookSubsystemRoot.cs `
        src\Rook.Tests\Services\Vision\VisionProviderRegistrationsTests.cs `
        src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "feat(vision): expose Replicate image provider metadata"
```

---

## Task 3: Wire Replicate Authenticated Output Fetch Into Production Image Jobs

**Files:**
- Modify: `src/Rook/RookSubsystemRoot.cs`
- Create: `src/Rook.Tests/RookSubsystemRootTests.cs`

- [ ] **Step 1: Add failing source-level selector wiring test**

Create `src/Rook.Tests/RookSubsystemRootTests.cs`:

```csharp
using System;
using System.IO;
using System.Linq;
using Xunit;

namespace Rook.Tests
{
    public class RookSubsystemRootTests
    {
        [Fact]
        public void ImageJobs_factory_wires_replicate_authenticated_output_selector()
        {
            var source = File.ReadAllText(FindSourceFile(
                "src", "Rook", "RookSubsystemRoot.cs"));

            Assert.Contains("ReplicateImageArtifactRequestFactorySelector", source);
            Assert.Contains("GenerationSecretKeys.ReplicateApiToken", source);
            Assert.Contains(".Select", source);
            Assert.Contains("new ImageJobManager", source);
        }

        private static string FindSourceFile(params string[] parts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                var candidate = Path.Combine(new[] { dir.FullName }.Concat(parts).ToArray());
                if (File.Exists(candidate))
                    return candidate;
                dir = dir.Parent;
            }
            throw new FileNotFoundException("Could not locate " + Path.Combine(parts));
        }
    }
}
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobs_factory_wires_replicate_authenticated_output_selector
```

Expected: FAIL because the source does not yet wire the selector.

- [ ] **Step 3: Wire selector in `RookSubsystemRoot.ImageJobs`**

Update `src/Rook/RookSubsystemRoot.cs` usings:

```csharp
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
```

In `_imageJobs` lazy construction, after registry creation:

```csharp
var selector = new ReplicateImageArtifactRequestFactorySelector(
    () => SharedGenerationSecretStore.GetSecret(
        GenerationSecretKeys.ReplicateApiToken));
var manager = new ImageJobManager(
    registry,
    SharedArtifactStore,
    requestFactorySelector: selector.Select);
return new ImageJobSubsystemBundle(manager, registry);
```

Add this internal overload to `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs` below the existing public constructor:

```csharp
internal ImageJobManager(
    IImageProviderRegistry registry,
    ArtifactStore artifactStore,
    ImageArtifactRequestFactorySelector? requestFactorySelector)
    : this(
        registry,
        artifactStore,
        clock: null,
        idGenerator: null,
        pollInterval: null,
        maxConcurrentJobs: DefaultMaxConcurrentJobs,
        materializer: null,
        requestFactorySelector: requestFactorySelector)
{
}
```

Keep the overload `internal`; `ImageArtifactRequestFactorySelector` is internal and a public constructor with that parameter would be an accessibility error.

- [ ] **Step 4: Run focused root test and Replicate image job tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobs_factory_wires_replicate_authenticated_output_selector|ReplicateImageJobManagerTests"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\RookSubsystemRoot.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs `
        src\Rook.Tests\RookSubsystemRootTests.cs
git commit -m "feat(vision): wire Replicate artifact auth for image jobs"
```

---

## Task 4: Emit `submission_mode` And Replicate Credential Availability

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Add failing `list_image_models` tests**

In `VisionHandlerTests`, update `AssertImageModel` to accept an optional submission mode:

```csharp
private static void AssertImageModel(
    IReadOnlyList<Dictionary<string, object?>> models,
    string modelId,
    string providerName,
    string credentialAvailability,
    string? submissionMode = null)
{
    var model = Assert.Single(
        models,
        m => Assert.IsType<string>(m["model_id"]) == modelId);

    Assert.Equal(providerName, ProviderName(model));
    Assert.Equal(
        credentialAvailability,
        Assert.IsType<string>(model["credential_availability"]));
    if (submissionMode is not null)
        Assert.Equal(submissionMode, Assert.IsType<string>(model["submission_mode"]));
}
```

Update `ListImageModels_ReturnsGeminiAndFalDescriptorsWithCredentialPresence` to also assert Replicate:

```csharp
AssertImageModel(
    models,
    GeminiImageCapabilities.NanoBanana2,
    "gemini",
    "available_but_unverified",
    "sync");
AssertImageModel(
    models,
    FalImageCapabilities.FluxSchnell,
    "fal",
    "missing_required_secret",
    "sync");
AssertImageModel(
    models,
    "black-forest-labs/flux-schnell",
    "replicate",
    "missing_required_secret",
    "async_image_job");
```

Add:

```csharp
[Fact]
public void ListImageModels_ReplicatePresentTokenIsAvailableButUnverified()
{
    var store = new InMemoryGenerationSecretStore();
    store.SetSecret(GenerationSecretKeys.ReplicateApiToken, "replicate-token");
    var handler = NewHandlerWithSecrets(store);

    var response = handler.ListImageModels(new Dictionary<string, JsonElement>());

    Assert.True(response.Success);
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    var models = AssertObjectList(data["models"]);
    AssertImageModel(
        models,
        "black-forest-labs/flux-schnell",
        "replicate",
        "available_but_unverified",
        "async_image_job");
}
```

- [ ] **Step 2: Add failing Replicate `test_provider_secret` test**

In `VisionHandlerTests`, add:

```csharp
[Fact]
public async Task TestProviderSecret_Replicate_ReturnsInconclusiveWithoutPersistingCandidate()
{
    var store = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(store);
    var args = VisionHandler.ParseObjectBody(
        "{\"provider_name\":\"replicate\",\"secret_key\":\"replicate.api_token\",\"candidate_value\":\"replicate-candidate\"}");

    var response = await handler.TestProviderSecretAsync(args, CancellationToken.None);

    Assert.True(response.Success);
    Assert.Null(store.GetSecret(GenerationSecretKeys.ReplicateApiToken));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.Equal("replicate", data["provider_name"]);
    Assert.Equal(GenerationSecretKeys.ReplicateApiToken, data["secret_key"]);
    Assert.Equal("inconclusive", data["validation_state"]);
    Assert.DoesNotContain("replicate-candidate", JsonSerializer.Serialize(response.Data));
    Assert.Contains("No provider-specific validation probe", data["message"]?.ToString());
}
```

This test pins no prediction HTTP because `VisionHandler.TestProviderSecretAsync` should use the existing generic fallback for Replicate. Do not instantiate `ReplicateApiClient` in this method.

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ListImageModels|TestProviderSecret_Replicate"
```

Expected: FAIL because `submission_mode` is not emitted and Replicate is not yet in the list until earlier tasks are complete.

- [ ] **Step 4: Emit `submission_mode` in descriptors**

In `VisionHandler.ImageModelDescriptorToObj`, add:

```csharp
["submission_mode"] = ImageSubmissionModeToString(descriptor.SubmissionMode),
```

Add helper:

```csharp
private static string ImageSubmissionModeToString(ImageSubmissionMode mode)
    => mode switch
    {
        ImageSubmissionMode.Sync => "sync",
        ImageSubmissionMode.AsyncImageJob => "async_image_job",
        _ => mode.ToString().ToLowerInvariant(),
    };
```

- [ ] **Step 5: Keep Replicate test key on generic inconclusive fallback**

Verify `TestProviderSecretAsync` has no Replicate-specific prediction branch. It should fall through to:

```csharp
return Ok(ProviderSecretTestEnvelope(
    metadata.ProviderName,
    requirement!.Key,
    "inconclusive",
    "No provider-specific validation probe is available."));
```

If a future branch was introduced accidentally, remove it in PR-14.

- [ ] **Step 6: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ListImageModels|TestProviderSecret_Replicate|VisionHandlerTests"
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Handlers\VisionHandler.cs src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "feat(vision): surface image submission mode"
```

---

## Task 5: Allow Prompt-Only Async Image Job Starts Without Loosening `generate`

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Modify: `src/Rook/Handlers/ImageJobOpHandler.cs`
- Modify: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Add failing image-job prompt-only tests**

In `ImageJobOpHandlerTests`, add:

```csharp
[Fact]
public async Task DispatchAsync_Start_AllowsPromptOnlyForAsyncTextToImageModel()
{
    ImageJobStartRequest? captured = null;
    var manager = new StubImageJobManager
    {
        SubmitImpl = (request, _) =>
        {
            captured = request;
            return ImageJobSubmitResult.Ok(SampleJobId, ImageJobState.Queued);
        },
    };
    var provider = new FakeAsyncTextToImageProvider();
    var handler = new ImageJobOpHandler(
        manager,
        NewVisionHandlerWithImageProvider(
            provider,
            "replicate",
            "black-forest-labs/flux-schnell",
            ImageSubmissionMode.AsyncImageJob,
            supportsImageToImage: false,
            supportsTextToImage: true));

    var response = await handler.DispatchAsync("""
        {
          "op": "image_generate_start",
          "prompt": "sunlit massing study",
          "model": "black-forest-labs/flux-schnell",
          "resolution": "1K",
          "aspect_ratio": "1:1"
        }
        """);

    AssertOk(response);
    Assert.NotNull(captured);
    Assert.Equal("black-forest-labs/flux-schnell", captured!.Request.Model);
    Assert.Empty(captured.ResolvedMedia);
    Assert.Null(captured.Request.ReferenceImages);
    Assert.Equal(ImageSubmissionMode.AsyncImageJob, captured.ResolvedModel!.SubmissionMode);
}
```

Add:

```csharp
[Fact]
public async Task DispatchAsync_Start_RejectsSourceMediaForTextToImageOnlyAsyncModel()
{
    using var temp = TempDir.Create();
    var inputPath = Path.Combine(temp.Path, "input.png");
    File.WriteAllBytes(inputPath, new byte[] { 0x89, 0x50, 0x4E, 0x47 });
    var handler = new ImageJobOpHandler(
        new StubImageJobManager(),
        NewVisionHandlerWithImageProvider(
            new FakeAsyncTextToImageProvider(),
            "replicate",
            "black-forest-labs/flux-schnell",
            ImageSubmissionMode.AsyncImageJob,
            supportsImageToImage: false,
            supportsTextToImage: true));

    var response = await handler.DispatchAsync($$"""
        {
          "op": "image_generate_start",
          "prompt": "sunlit massing study",
          "input_image_path": "{{Escape(inputPath)}}",
          "model": "black-forest-labs/flux-schnell",
          "resolution": "1K",
          "aspect_ratio": "1:1"
        }
        """);

    AssertFail(response, GenerationErrorCode.InvalidRequest, expectedHttp: 400);
}
```

Add:

```csharp
[Fact]
public async Task DispatchAsync_Start_RejectsReferencesForTextToImageOnlyAsyncModel()
{
    using var temp = TempDir.Create();
    var referencePath = Path.Combine(temp.Path, "ref.png");
    File.WriteAllBytes(referencePath, new byte[] { 0x89, 0x50, 0x4E, 0x47 });
    var handler = new ImageJobOpHandler(
        new StubImageJobManager(),
        NewVisionHandlerWithImageProvider(
            new FakeAsyncTextToImageProvider(),
            "replicate",
            "black-forest-labs/flux-schnell",
            ImageSubmissionMode.AsyncImageJob,
            supportsImageToImage: false,
            supportsTextToImage: true));

    var response = await handler.DispatchAsync($$"""
        {
          "op": "image_generate_start",
          "prompt": "sunlit massing study",
          "reference_image_paths": [ "{{Escape(referencePath)}}" ],
          "model": "black-forest-labs/flux-schnell",
          "resolution": "1K",
          "aspect_ratio": "1:1"
        }
        """);

    AssertFail(response, GenerationErrorCode.InvalidRequest, expectedHttp: 400);
}
```

- [ ] **Step 2: Add failing sync `generate` guard test**

In `VisionHandlerTests`, add:

```csharp
[Fact]
public async Task GenerateAsync_StillRequiresInputImagePath()
{
    var handler = NewHandlerWithSecrets(new InMemoryGenerationSecretStore());
    var args = ParseArgs("""
        {
          "prompt": "prompt-only should not use sync generate",
          "model": "nano-banana-2",
          "resolution": "1K",
          "aspect_ratio": "1:1"
        }
        """);

    var response = await handler.GenerateAsync(args, CancellationToken.None);

    Assert.False(response.Success);
    var message = Assert.IsType<string>(response.Data);
    Assert.Contains("input_image_path", message);
}
```

- [ ] **Step 3: Add helper fakes in `ImageJobOpHandlerTests`**

Add these usings at the top of `ImageJobOpHandlerTests`:

```csharp
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Vision.Image;
```

Add helper factory and fake provider/registration in `ImageJobOpHandlerTests`:

```csharp
private static VisionHandler NewVisionHandlerWithImageProvider(
    IImageProvider provider,
    string providerName,
    string modelId,
    ImageSubmissionMode submissionMode,
    bool supportsImageToImage,
    bool supportsTextToImage)
{
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new SingleImageProviderRegistration(
            provider,
            providerName,
            modelId,
            submissionMode,
            supportsImageToImage,
            supportsTextToImage),
    });
    var artifactRoot = Path.Combine(
        Path.GetTempPath(),
        "rook-image-job-op-artifacts-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(artifactRoot);
    return new VisionHandler(
        new ArtifactStore(artifactRoot),
        new InMemoryGenerationSecretStore(),
        new PromptEnhancer(),
        new ViewportHandler(),
        registry);
}
```

Add in-memory secrets:

```csharp
private sealed class InMemoryGenerationSecretStore : IGenerationSecretStore
{
    private readonly Dictionary<string, string> _secrets = new(StringComparer.Ordinal);

    public string? GetSecret(string secretKey) =>
        _secrets.TryGetValue(secretKey, out var value) ? value : null;

    public void SetSecret(string secretKey, string value) =>
        _secrets[secretKey] = value;

    public void RemoveSecret(string secretKey) =>
        _secrets.Remove(secretKey);

    public bool HasSecret(string secretKey) =>
        _secrets.ContainsKey(secretKey);

    public string? GetPreview(string secretKey) =>
        HasSecret(secretKey) ? "test-preview" : null;
}
```

Add fake provider:

```csharp
private sealed class FakeAsyncTextToImageProvider : IImageProvider
{
    public string ProviderName => "replicate";

    public Task<ProviderSubmitOutcome> SubmitAsync(
        ImageGenerationRequest request,
        IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
        CancellationToken ct) =>
        Task.FromResult<ProviderSubmitOutcome>(
            new QueuedSubmitOutcome(new ProviderJobHandle(
                ProviderJobId: "pred-1",
                StatusUrl: null,
                ResponseUrl: null,
                CancelUrl: null,
                CancelHttpMethod: null,
                ProviderResultToken: null,
                ProviderMetadata: null)));

    public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct) =>
        throw new InvalidOperationException();
    public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) =>
        throw new InvalidOperationException();
    public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct) =>
        throw new InvalidOperationException();
}
```

Add fake options/pricing helpers:

```csharp
private sealed record FakeImageOptions : ProviderOptions;

private sealed class FakeImageOptionsCodec
    : IProviderOptionsCodec<ImageGenerationRequest, ImageCapability>
{
    public ValidationResult Validate(
        ImageGenerationRequest request,
        ProviderOptions options,
        ImageCapability capability) => ValidationResult.Ok();

    public JsonObject Serialize(ProviderOptions options) => new JsonObject();

    public ProviderOptionsDecodeResult Deserialize(JsonObject json) =>
        ProviderOptionsDecodeResult.Ok(new FakeImageOptions());
}

private sealed class FakeImagePricingModel
    : IPricingModel<ImageGenerationRequest, ImageCapability>
{
    public string PricingSource => "test";
    public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

    public PricingResult Estimate(
        ImageGenerationRequest request,
        ImageCapability capability) =>
        PricingResult.Ok(
            new JobPricing("USD", 0m, "call", 1m, 0m, "test"),
            new CostEstimate(0m, 0m, false, "test-stub"));

    public JobPricing? ExtractActualSpend(
        IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
        JsonNode? responseBody) => null;
}
```

Add registration with `ImageSubmissionMode` and capability flags:

```csharp
private sealed class SingleImageProviderRegistration : IImageProviderRegistration
{
    private readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models;

    public SingleImageProviderRegistration(
        IImageProvider provider,
        string providerName,
        string modelId,
        ImageSubmissionMode submissionMode,
        bool supportsImageToImage,
        bool supportsTextToImage)
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
                    Resolutions: new[] { "1K" },
                    AspectRatios: new[] { "1:1" },
                    MaxReferenceImages: supportsImageToImage ? 1 : 0,
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

- [ ] **Step 4: Run focused tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "DispatchAsync_Start_AllowsPromptOnly|DispatchAsync_Start_RejectsSourceMedia|DispatchAsync_Start_RejectsReferences|GenerateAsync_StillRequiresInputImagePath"
```

Expected: FAIL because `BuildImageGenerationWorkItem` requires `input_image_path` unconditionally.

- [ ] **Step 5: Add work-item mode options in `VisionHandler`**

In `VisionHandler`, add:

```csharp
internal sealed class ImageGenerationWorkItemOptions
{
    public static readonly ImageGenerationWorkItemOptions SyncGenerate = new(
        allowPromptOnlyAsyncTextToImage: false);
    public static readonly ImageGenerationWorkItemOptions AsyncImageJob = new(
        allowPromptOnlyAsyncTextToImage: true);

    private ImageGenerationWorkItemOptions(bool allowPromptOnlyAsyncTextToImage)
    {
        AllowPromptOnlyAsyncTextToImage = allowPromptOnlyAsyncTextToImage;
    }

    public bool AllowPromptOnlyAsyncTextToImage { get; }
}
```

Change existing method to call the overload:

```csharp
internal ImageGenerationWorkItemResult BuildImageGenerationWorkItem(
    Dictionary<string, JsonElement> args) =>
    BuildImageGenerationWorkItem(args, ImageGenerationWorkItemOptions.SyncGenerate);
```

Add overload:

```csharp
internal ImageGenerationWorkItemResult BuildImageGenerationWorkItem(
    Dictionary<string, JsonElement> args,
    ImageGenerationWorkItemOptions options)
{
    if (options is null) throw new ArgumentNullException(nameof(options));
    ...
}
```

Move the existing body into the overload and adjust source handling as described below.

- [ ] **Step 6: Make input media optional only after resolving async T2I model**

Within the overload:

1. Read `prompt`, model, resolution, and aspect ratio first.
2. Resolve the model before requiring `input_image_path`.
3. Compute:

```csharp
var hasInputImage = args.TryGetValue("input_image_path", out var inputImageEl)
    && inputImageEl.ValueKind == JsonValueKind.String
    && !string.IsNullOrWhiteSpace(inputImageEl.GetString());
var allowPromptOnly = options.AllowPromptOnlyAsyncTextToImage
    && resolvedModel.SubmissionMode == ImageSubmissionMode.AsyncImageJob
    && resolvedModel.Capability.SupportsTextToImage;
```

4. If no input and not allowed:

```csharp
return ImageGenerationWorkItemResult.Fail(
    Fail("Missing or non-string field 'input_image_path'."));
```

5. If no input and allowed, skip input media creation and leave `resolvedMedia` empty.
6. If input is present but `resolvedModel.Capability.SupportsImageToImage == false`, return:

```csharp
return ImageGenerationWorkItemResult.Fail(
    Fail("Selected image model does not support source image input."));
```

7. If `reference_image_paths` is present and `resolvedModel.Capability.MaxReferenceImages == 0`, return:

```csharp
return ImageGenerationWorkItemResult.Fail(
    Fail("Selected image model does not support reference_image_paths."));
```

8. Keep existing file existence, size, aggregate bytes, and `ResolvedMedia` population for source/reference paths when input is present and supported.

- [ ] **Step 7: Update `ImageJobOpHandler` start path**

In `ImageJobOpHandler.StartAsync`, change:

```csharp
var workResult = _visionHandler.BuildImageGenerationWorkItem(args);
```

to:

```csharp
var workResult = _visionHandler.BuildImageGenerationWorkItem(
    args,
    VisionHandler.ImageGenerationWorkItemOptions.AsyncImageJob);
```

- [ ] **Step 8: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobOpHandlerTests|GenerateAsync_StillRequiresInputImagePath|GenerateAsync_AsyncImageProviderStillFailsWithCompatibilityMessage"
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add src\Rook\Handlers\VisionHandler.cs `
        src\Rook\Handlers\ImageJobOpHandler.cs `
        src\Rook.Tests\Handlers\VisionHandlerTests.cs `
        src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs
git commit -m "feat(vision): allow prompt-only async image jobs"
```

---

## Task 6: Update Generate UI For Async Image Jobs

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Modify: `src/Rook/UI/Vision/Resources/styles.css`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add failing resource tests for submission-mode routing**

In `VisionWebSurfaceTests`, add:

```csharp
[Fact]
public void AppJs_ConsumesSubmissionModeFromImageCatalog()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("submission_mode", js);
    Assert.Contains("function isAsyncImageJobModel", js);
    Assert.Contains("m.submission_mode || \"sync\"", js);
}
```

Add:

```csharp
[Fact]
public void AppJs_GenerateRoutesAsyncModelsThroughImageJobOps()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("async function generateImageJob", js);
    Assert.Contains("bridgeCall(\"image_generate_start\"", js);
    Assert.Contains("bridgeCall(\"image_job_status\"", js);
    Assert.Contains("bridgeCall(\"image_job_result\"", js);
    Assert.Contains("state === \"materializing\"", js);
    Assert.DoesNotContain("provider_name === \"replicate\"", js);
}
```

Add:

```csharp
[Fact]
public void AppJs_DisablesGenerateSourceControlsForTextToImageOnlyAsyncModels()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("function updateGenerateInputMode", js);
    Assert.Contains("generate-input-disabled", js);
    Assert.Contains("el.captureBtn.disabled = promptOnlyAsync", js);
    Assert.Contains("el.addReferenceBtn.disabled = promptOnlyAsync", js);
    Assert.Contains("generateReferences = [];", js);
}
```

Add:

```csharp
[Fact]
public void AppJs_StudioKeepsTextToImageOnlyModelsIncompatible()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("function validateStudioModelForSubmit", js);
    Assert.Contains("Selected model is incompatible with Studio", js);
}
```

- [ ] **Step 2: Run resource tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "SubmissionMode|GenerateRoutesAsync|GenerateSourceControls|StudioKeeps"
```

Expected: FAIL because current JS has no async image job routing.

- [ ] **Step 3: Normalize `submission_mode` in model descriptors**

In `normalizeImageModelDescriptor`, add:

```javascript
submission_mode: m.submission_mode || "sync",
```

In `normalizeLegacyAvailableModel`, add:

```javascript
submission_mode: m.submission_mode || "sync",
```

Add helpers:

```javascript
function isAsyncImageJobModel(model) {
    return !!model && model.submission_mode === "async_image_job";
}

function isPromptOnlyAsyncImageModel(model) {
    return isAsyncImageJobModel(model)
        && model.supports_text_to_image !== false
        && model.supports_image_to_image === false;
}
```

- [ ] **Step 4: Split Generate and Studio validation**

Replace current `validateImageModelForSubmit` with:

```javascript
function validateGenerateModelForSubmit(selectEl) {
    const model = selectedImageModel(selectEl);
    if (!model) return null;
    const availability = effectiveCredentialAvailability(model);
    if (availability === "missing_required_secret") {
        return `${providerDisplayName(model.provider_name)} key is required before using this model.`;
    }
    if (!isPromptOnlyAsyncImageModel(model) && !capturedViewport) {
        return "Capture a viewport first.";
    }
    return null;
}

function validateStudioModelForSubmit(selectEl) {
    const model = selectedImageModel(selectEl);
    if (!model) return null;
    const availability = effectiveCredentialAvailability(model);
    if (availability === "missing_required_secret") {
        return `${providerDisplayName(model.provider_name)} key is required before using this model.`;
    }
    if (model.supports_image_to_image === false) {
        return "Selected model is incompatible with Studio source-image editing.";
    }
    return null;
}
```

Update Generate call sites to use `validateGenerateModelForSubmit`. Update Studio call sites to use `validateStudioModelForSubmit`.

- [ ] **Step 5: Add Generate input-mode UI control**

Add:

```javascript
function updateGenerateInputMode() {
    const model = selectedImageModel(el.modelSelect);
    const promptOnlyAsync = isPromptOnlyAsyncImageModel(model);
    const generateView = document.getElementById("generate-view");
    if (generateView) {
        generateView.classList.toggle("generate-input-disabled", promptOnlyAsync);
    }

    if (el.captureBtn) el.captureBtn.disabled = promptOnlyAsync;
    if (el.viewportSelect) el.viewportSelect.disabled = promptOnlyAsync;
    if (el.addReferenceBtn) el.addReferenceBtn.disabled = promptOnlyAsync;
    if (el.clearReferencesBtn) el.clearReferencesBtn.disabled = promptOnlyAsync;

    if (promptOnlyAsync) {
        generateReferences = [];
        renderReferencePreview(generateReferences, el.referencePreview);
        showStatus("Selected model uses prompt-only generation.", "info");
    }
}
```

In `populateImageModelDropdowns`, after `syncResolutionOptions();`, call:

```javascript
updateGenerateInputMode();
```

In the model change listener, replace `syncResolutionOptions` with:

```javascript
el.modelSelect.addEventListener("change", () => {
    syncResolutionOptions();
    updateGenerateInputMode();
});
```

Guard `captureViewport`:

```javascript
if (isPromptOnlyAsyncImageModel(selectedImageModel(el.modelSelect))) {
    return;
}
```

In `captureViewport`, call `updateGenerateInputMode()` in the `finally` block after the existing button/spinner cleanup. This prevents an in-flight capture from re-enabling source controls if the user switches to a prompt-only async model before capture completes:

```javascript
finally {
    setGenerating(el.captureBtn, el.captureText, el.captureSpinner, false);
    updateGenerateInputMode();
}
```

- [ ] **Step 6: Route Generate by submission mode**

Change `generateImage` to:

```javascript
async function generateImage() {
    const prompt = el.prompt.value.trim();
    if (!prompt) { showStatus("Please enter a prompt.", "error"); return; }

    const model = selectedImageModel(el.modelSelect);
    const modelError = validateGenerateModelForSubmit(el.modelSelect);
    if (modelError) {
        showStatus(modelError, "error");
        return;
    }

    if (isAsyncImageJobModel(model)) {
        await generateImageJob(prompt, model);
        return;
    }

    await generateSyncImage(prompt, model);
}
```

Move current body after validation into:

```javascript
async function generateSyncImage(prompt, model) {
    const sourcePath = capturedViewport && capturedViewport.file_path;
    setGenerating(el.generateBtn, el.generateText, el.generateSpinner, true);
    showStatus("Generating image...", "info");
    try {
        const args = {
            prompt,
            input_image_path: sourcePath,
            resolution: el.resolutionSelect.value,
        };
        const aspectRatio = selectedAspectRatio(el.aspectSelect);
        if (aspectRatio) args.aspect_ratio = aspectRatio;
        if (el.modelSelect.value) args.model = el.modelSelect.value;
        if (generateReferences.length > 0) {
            args.reference_image_paths = generateReferences.map(r => r.path);
        }
        const artifact = await bridgeCall("generate", args);
        renderGeneratedArtifact(artifact, "Image generated.");
    } catch (e) {
        if (model && isCredentialFailureMessage(e.message)) {
            markProviderCredentialInvalid(model.provider_name);
        }
        showStatus(e.message, "error");
    } finally {
        setGenerating(el.generateBtn, el.generateText, el.generateSpinner, false);
    }
}
```

Add:

```javascript
function renderGeneratedArtifact(artifact, successMessage) {
    latestArtifactId = artifact && artifact.artifact_id;
    if (latestArtifactId) {
        el.resultImage.src = `/blob/${encodeURIComponent(latestArtifactId)}/image?ts=${Date.now()}`;
        el.resultPanel.classList.remove("hidden");
        showStatus(successMessage || "Image generated.", "success");
    } else {
        showStatus("Generation returned no artifact.", "error");
    }
}
```

- [ ] **Step 7: Add async image job polling**

Add:

```javascript
async function generateImageJob(prompt, model) {
    setGenerating(el.generateBtn, el.generateText, el.generateSpinner, true);
    showStatus("Starting image job...", "info");
    try {
        const args = {
            prompt,
            resolution: el.resolutionSelect.value,
        };
        const aspectRatio = selectedAspectRatio(el.aspectSelect);
        if (aspectRatio) args.aspect_ratio = aspectRatio;
        if (el.modelSelect.value) args.model = el.modelSelect.value;

        const start = await bridgeCall("image_generate_start", args);
        const jobId = start.job_id;
        let terminal = null;
        for (let attempt = 0; attempt < 180; attempt++) {
            const status = await bridgeCall("image_job_status", { job_id: jobId });
            showImageJobStatus(status);
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
        renderGeneratedArtifact({ artifact_id: result.result_artifact_id }, "Image generated.");
    } catch (e) {
        if (model && isCredentialFailureMessage(e.message)) {
            markProviderCredentialInvalid(model.provider_name);
        }
        showStatus(e.message, "error");
    } finally {
        setGenerating(el.generateBtn, el.generateText, el.generateSpinner, false);
    }
}

function showImageJobStatus(status) {
    const state = status && status.state || "unknown";
    if (state === "queued") showStatus("Image job queued...", "info");
    else if (state === "submitting") showStatus("Submitting image job...", "info");
    else if (state === "polling") showStatus("Image job running...", "info");
    else if (state === "materializing") showStatus("Saving generated image...", "info");
    else if (state === "complete") showStatus("Image job complete.", "success");
    else if (state === "cancelled") showStatus("Image job cancelled.", "error");
    else if (state === "error") showStatus("Image job failed.", "error");
    else showStatus(`Image job ${state}...`, "info");
}

function delay(ms) {
    return new Promise(resolve => window.setTimeout(resolve, ms));
}
```

- [ ] **Step 8: Keep Studio incompatible**

In `studioGenerate`, replace:

```javascript
const modelError = validateImageModelForSubmit(el.studioModelSelect);
```

with:

```javascript
const modelError = validateStudioModelForSubmit(el.studioModelSelect);
```

In `populateImageModelDropdowns`, do not use one shared `supports_image_to_image === false` disabled rule for both pickers. Generate must disable only missing-credential models; Studio must disable missing-credential models and T2I-only models. Build or patch options with this split:

```javascript
function shouldDisableGenerateModel(model) {
    return effectiveCredentialAvailability(model) === "missing_required_secret";
}

function shouldDisableStudioModel(model) {
    return shouldDisableGenerateModel(model)
        || model.supports_image_to_image === false;
}
```

When creating Generate option elements:

```javascript
option.disabled = shouldDisableGenerateModel(model);
```

When creating Studio option elements:

```javascript
option.disabled = shouldDisableStudioModel(model);
```

Keep T2I-only options visibly incompatible in Studio with this post-population pass:

```javascript
function applyStudioModelCompatibility() {
    if (!el.studioModelSelect) return;
    for (const option of el.studioModelSelect.options) {
        const model = modelCatalog.find(m => imageModelOptionValue(m) === option.value);
        if (model && model.supports_image_to_image === false) {
            option.disabled = true;
            if (!option.textContent.includes("incompatible with Studio")) {
                option.textContent += " - incompatible with Studio";
            }
        }
    }
}
```

Call `applyStudioModelCompatibility()` after populating selects.

- [ ] **Step 9: Add Generate-scoped disabled CSS**

In `styles.css`, add near reference/source styles:

```css
#generate-view.generate-input-disabled .preview-panel,
#generate-view.generate-input-disabled .reference-section {
    opacity: 0.45;
}

#generate-view.generate-input-disabled .preview-panel button,
#generate-view.generate-input-disabled .preview-panel select,
#generate-view.generate-input-disabled .reference-section button {
    pointer-events: none;
}

#generate-view .reference-upload:disabled,
#generate-view .btn-text:disabled {
    cursor: not-allowed;
    opacity: 0.45;
}
```

The class must be scoped to the Generate view or Generate layout, not `document.body`; Studio also uses `.reference-section` and must not be dimmed or disabled by the Generate prompt-only state.

- [ ] **Step 10: Run resource tests and focused UI test suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests"
```

Expected: PASS.

- [ ] **Step 11: Commit**

```powershell
git add src\Rook\UI\Vision\Resources\app.js `
        src\Rook\UI\Vision\Resources\styles.css `
        src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): route Generate async image jobs"
```

---

## Task 7: Focused Integration And Boundary Verification

**Files:**
- Modify tests only if verification exposes a scoped boundary gap.
- No production native or MCP files.

- [ ] **Step 1: Run registration and catalog tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionProviderRegistrationsTests|DefaultImageProviderRegistryTests|ReplicateImageProviderRegistrationTests|VisionHandlerTests"
```

Expected: PASS.

- [ ] **Step 2: Run image job and Replicate suites**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobOpHandlerTests|ReplicateImage|ImageJob|ImageArtifactMaterializerTests"
```

Expected: PASS.

- [ ] **Step 3: Run UI resource tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests"
```

Expected: PASS.

- [ ] **Step 4: Run boundary scans**

Run:

```powershell
rg -n "image_generate_start|image_job_status|image_job_cancel|image_job_result|image_jobs|set_provider_secret|test_provider_secret|clear_provider_secret|list_image_models" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected:

- no hits under `src\RookNative`;
- no hits under `mcp_server`;
- no hits in `src\Rook\InternalBridge\NativeGhBridgeRegistrar.cs`.

Run:

```powershell
rg -n "ReplicateImageProvider|ReplicateImageProviderRegistration|ReplicateImageCapabilities|replicate.api_token|black-forest-labs/flux-schnell|replicate.delivery" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected: no hits.

- [ ] **Step 5: Run durable leakage scans**

Run:

```powershell
rg -n "replicate.delivery|Bearer|replicate-token|api_token" src\Rook.Tests\Services\Vision\Image\Replicate src\Rook.Tests\Handlers
```

Expected: test fixtures may contain fake token strings and host names, but production artifact metadata assertions must prove those strings do not appear in serialized job responses/artifact metadata. If production code serializes `replicate.delivery`, fix before proceeding.

- [ ] **Step 6: Run broad managed Vision suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "Vision|Image|Generation|Fal|Replicate"
```

Expected: PASS.

- [ ] **Step 7: Run full managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: PASS. If the full suite cannot complete for local prerequisite reasons, record the exact command, failure, and all focused passing evidence.

- [ ] **Step 8: Diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected:

- `git diff --check` clean.
- changed files limited to managed Vision code/resources/tests and docs.
- no files under `src/RookNative/**`.
- no files under `mcp_server/**`.

- [ ] **Step 9: Optional manual live smoke gate**

Do not run this by default. Ask the user immediately before any live call:

```text
Do you approve one low-cost live Replicate smoke for black-forest-labs/flux-schnell using the configured Replicate token?
```

Only if approved:

1. Confirm focused fake-HTTP/backend/UI tests have passed.
2. Confirm a real Replicate token is configured in Settings.
3. Run one Generate prompt-only job with `black-forest-labs/flux-schnell`.
4. Verify the UI routes through `image_generate_start`, polls status, materializes a local artifact, and renders it.
5. Inspect artifact metadata and job responses for no provider URL or secret.

Record whether the live smoke was skipped or completed in final PR notes.

- [ ] **Step 10: Commit any final test-only boundary fixes**

If Task 7 changed tests:

```powershell
git add src\Rook.Tests
git commit -m "test(vision): pin Replicate visibility boundaries"
```

If no files changed, no commit is needed.

---

## Self-Review Checklist

- [ ] Replicate is visible in managed Settings credential metadata.
- [ ] Replicate credential set/clear works through provider-aware ops.
- [ ] Replicate credential test returns inconclusive without calling prediction endpoints.
- [ ] `list_image_models` emits backend-owned `submission_mode`.
- [ ] Gemini/fal image descriptors are `sync`.
- [ ] Replicate FLUX Schnell descriptor is `async_image_job`.
- [ ] Generate routes async models through image job ops.
- [ ] Generate prompt-only path is allowed only for async T2I jobs.
- [ ] Sync `generate` still requires `input_image_path`.
- [ ] Studio remains source/edit oriented and marks T2I-only models incompatible/disabled.
- [ ] `RookSubsystemRoot.ImageJobs` wires Replicate authenticated output request selector.
- [ ] Replicate outputs are copied into local artifacts before completion.
- [ ] No provider URL or secret leaks into durable metadata or responses.
- [ ] No `src/RookNative/**` changes.
- [ ] No `mcp_server/**` changes.
- [ ] No `NativeGhBridgeRegistrar` exposure.
- [ ] Optional live smoke remains explicit-approval only.
