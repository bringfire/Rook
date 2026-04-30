# PR-9 Provider Settings Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement provider-driven Settings credential cards and provider-aware image picker metadata for Gemini plus fal.ai, without native credential route exposure.

**Architecture:** Add a managed provider credential metadata catalog from lightweight declarative metadata, with an explicit credential-owner mapping so model provider identity remains separate from Settings credential-card identity. Keep image/video provider registration construction on the existing registry paths only. Add canonical provider-aware Vision bridge ops for set/test/clear secret and `list_image_models`, keep legacy Gemini ops as narrow shims, and update the Vision UI to render provider cards plus deterministic image descriptors. Validation state remains JS panel-session only.

**Tech Stack:** C#/.NET Framework plugin code, xUnit tests, embedded HTML/CSS/JavaScript Vision panel resources, `nlohmann/json`/native code untouched.

---

## Scope And Guardrails

- Do not modify `src/RookNative/**`.
- Do not add native public credential routes or native trampoline entries for `set_provider_secret`, `test_provider_secret`, `clear_provider_secret`, or `list_image_models`.
- Keep `set_api_key` and `test_api_key` Gemini-only.
- Keep `list_image_models` off-UI and deterministic: local registry metadata plus persisted credential presence only.
- Keep fal Settings validation non-generation and non-spend. Ambiguous proof returns `validation_state: "inconclusive"`.
- Persist only encrypted secret values and previews. Do not persist validation state.
- `InvalidCredential` is warning-only. `MissingRequiredSecret` and capability mismatch are the only deterministic blockers.
- `get_settings_overview.available_models` remains a shim. New UI prefers `list_image_models`.

## File Structure

Create:

- `src/Rook/Services/Vision/Generation/ProviderCredentialMetadata.cs` - immutable provider credential metadata record: provider name plus merged secret requirements.
- `src/Rook/Services/Vision/Generation/ProviderCredentialMetadataCatalog.cs` - merges declarative credential metadata by credential-owner provider name and de-duplicates secret requirements by key.
- `src/Rook/Services/Vision/VisionProviderRegistrations.cs` - central managed helper that constructs default image/video provider registration arrays for registries and exposes lightweight declarative credential metadata, including credential-owner mapping and secret display-name normalization.
- `src/Rook.Tests/Services/Vision/Generation/ProviderCredentialMetadataCatalogTests.cs` - unit coverage for merge/de-dup/conflict behavior.

Modify:

- `src/Rook/Services/Vision/Image/IImageProviderRegistry.cs` - expose provider credential metadata enumeration only if using registry method; preferred plan uses catalog instead, so avoid changing this unless implementation inspection finds catalog awkward.
- `src/Rook/Services/Vision/Image/DefaultImageProviderRegistry.cs` - use shared registration helper only if constructor ownership requires it; otherwise existing behavior remains.
- `src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs` - construct video registrations through `VisionProviderRegistrations.CreateVideoRegistrations`.
- `src/Rook/Handlers/VisionHandler.cs` - add provider-aware ops, image descriptor op, metadata catalog dependency, credential status projection, and legacy shim wiring.
- `src/Rook/UI/Vision/VisionWebSurface.cs` - add bridge-only op routes.
- `src/Rook/UI/Vision/Resources/index.html` - replace hard-coded API key card with credentials container while preserving existing Gemini visual treatment.
- `src/Rook/UI/Vision/Resources/app.js` - render provider cards, call new ops, load `list_image_models`, maintain session validation overlay, and keep fallback to `available_models`.
- `src/Rook/UI/Vision/Resources/styles.css` - small Settings/card/status additions only.
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs` - provider ops, catalog response, compatibility shim tests.
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs` - route allowlist and embedded resource assertions.
- `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs` - pin video factory uses shared registration helper if needed.

## Task 1: Provider Credential Metadata Catalog

**Files:**
- Create: `src/Rook/Services/Vision/Generation/ProviderCredentialMetadata.cs`
- Create: `src/Rook/Services/Vision/Generation/ProviderCredentialMetadataCatalog.cs`
- Create: `src/Rook.Tests/Services/Vision/Generation/ProviderCredentialMetadataCatalogTests.cs`

- [ ] **Step 1: Write failing catalog tests**

Add tests that prove provider metadata merges across modalities and rejects conflicting requirement metadata:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public class ProviderCredentialMetadataCatalogTests
    {
        [Fact]
        public void FromProviders_merges_requirements_by_provider_name_and_secret_key()
        {
            var catalog = ProviderCredentialMetadataCatalog.FromProviders(new[]
            {
                Provider("gemini", Requirement(GenerationSecretKeys.GeminiApiKey, "Gemini API key")),
                Provider("gemini", Requirement(GenerationSecretKeys.GeminiApiKey, "Gemini API key")),
                Provider("fal", Requirement(GenerationSecretKeys.FalApiKey, "fal.ai API key")),
            });

            var providers = catalog.EnumerateProviders().ToArray();

            Assert.Equal(new[] { "gemini", "fal" }, providers.Select(p => p.ProviderName));
            Assert.Single(providers[0].SecretRequirements);
            Assert.Equal(GenerationSecretKeys.GeminiApiKey, providers[0].SecretRequirements[0].Key);
            Assert.Single(providers[1].SecretRequirements);
            Assert.Equal(GenerationSecretKeys.FalApiKey, providers[1].SecretRequirements[0].Key);
        }

        [Fact]
        public void FromProviders_rejects_conflicting_requirement_metadata_for_same_provider_key()
        {
            var ex = Assert.Throws<InvalidOperationException>(() =>
                ProviderCredentialMetadataCatalog.FromProviders(new[]
                {
                    Provider("fal", Requirement(GenerationSecretKeys.FalApiKey, "fal API key")),
                    Provider("fal", Requirement(GenerationSecretKeys.FalApiKey, "fal.ai API key")),
                }));

            Assert.Contains("Conflicting secret requirement metadata", ex.Message);
            Assert.Contains("fal", ex.Message);
            Assert.Contains(GenerationSecretKeys.FalApiKey, ex.Message);
        }

        [Fact]
        public void TryGetProvider_returns_false_for_unknown_provider()
        {
            var catalog = ProviderCredentialMetadataCatalog.FromProviders(new[]
            {
                Provider("gemini", Requirement(GenerationSecretKeys.GeminiApiKey, "Gemini API key")),
            });

            Assert.False(catalog.TryGetProvider("fal", out _));
        }

        private static ProviderCredentialMetadata Provider(
            string providerName,
            params ProviderSecretRequirement[] requirements)
            => new(providerName, requirements);

        private static ProviderSecretRequirement Requirement(string key, string displayName)
            => new(key, displayName, isRequired: true);
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ProviderCredentialMetadataCatalogTests
```

Expected: compile failure because `ProviderCredentialMetadata` and `ProviderCredentialMetadataCatalog` do not exist.

- [ ] **Step 3: Add catalog types**

Create `ProviderCredentialMetadata.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderCredentialMetadata
    {
        public ProviderCredentialMetadata(
            string providerName,
            IReadOnlyList<ProviderSecretRequirement> secretRequirements)
        {
            if (string.IsNullOrWhiteSpace(providerName))
                throw new ArgumentException("Provider name must be non-empty.", nameof(providerName));
            if (secretRequirements is null)
                throw new ArgumentNullException(nameof(secretRequirements));

            var copy = new ProviderSecretRequirement[secretRequirements.Count];
            for (var i = 0; i < secretRequirements.Count; i++)
            {
                copy[i] = secretRequirements[i]
                    ?? throw new ArgumentException("Secret requirements cannot contain null entries.", nameof(secretRequirements));
            }

            ProviderName = providerName;
            SecretRequirements = Array.AsReadOnly(copy);
        }

        public string ProviderName { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
    }
}
```

Create `ProviderCredentialMetadataCatalog.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderCredentialMetadataCatalog
    {
        private readonly Dictionary<string, ProviderCredentialMetadata> _byProvider;
        private readonly List<ProviderCredentialMetadata> _ordered;

        private ProviderCredentialMetadataCatalog(List<ProviderCredentialMetadata> ordered)
        {
            _ordered = ordered;
            _byProvider = new Dictionary<string, ProviderCredentialMetadata>(StringComparer.Ordinal);
            foreach (var provider in ordered)
                _byProvider[provider.ProviderName] = provider;
        }

        public static ProviderCredentialMetadataCatalog FromProviders(
            IEnumerable<ProviderCredentialMetadata> providers)
        {
            if (providers is null) throw new ArgumentNullException(nameof(providers));

            var byProvider = new Dictionary<string, List<ProviderSecretRequirement>>(StringComparer.Ordinal);
            var order = new List<string>();

            foreach (var provider in providers)
            {
                if (provider is null)
                    throw new ArgumentException("Provider metadata cannot contain null entries.", nameof(providers));

                if (!byProvider.TryGetValue(provider.ProviderName, out var requirements))
                {
                    requirements = new List<ProviderSecretRequirement>();
                    byProvider[provider.ProviderName] = requirements;
                    order.Add(provider.ProviderName);
                }

                foreach (var requirement in provider.SecretRequirements)
                    AddOrValidate(provider.ProviderName, requirements, requirement);
            }

            var ordered = new List<ProviderCredentialMetadata>(order.Count);
            foreach (var providerName in order)
                ordered.Add(new ProviderCredentialMetadata(providerName, byProvider[providerName]));

            return new ProviderCredentialMetadataCatalog(ordered);
        }

        public IReadOnlyList<ProviderCredentialMetadata> EnumerateProviders() => _ordered;

        public bool TryGetProvider(string providerName, out ProviderCredentialMetadata metadata)
        {
            if (!string.IsNullOrWhiteSpace(providerName)
                && _byProvider.TryGetValue(providerName, out var found))
            {
                metadata = found;
                return true;
            }

            metadata = null!;
            return false;
        }

        private static void AddOrValidate(
            string providerName,
            List<ProviderSecretRequirement> existing,
            ProviderSecretRequirement requirement)
        {
            foreach (var current in existing)
            {
                if (!string.Equals(current.Key, requirement.Key, StringComparison.Ordinal))
                    continue;

                if (!string.Equals(current.DisplayName, requirement.DisplayName, StringComparison.Ordinal)
                    || current.IsRequired != requirement.IsRequired
                    || current.IsSensitive != requirement.IsSensitive)
                {
                    throw new InvalidOperationException(
                        $"Conflicting secret requirement metadata for provider '{providerName}' key '{requirement.Key}'.");
                }
                return;
            }

            existing.Add(requirement);
        }
    }
}
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ProviderCredentialMetadataCatalogTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Generation\ProviderCredentialMetadata.cs `
        src\Rook\Services\Vision\Generation\ProviderCredentialMetadataCatalog.cs `
        src\Rook.Tests\Services\Vision\Generation\ProviderCredentialMetadataCatalogTests.cs
git commit -m "feat(vision): add provider credential metadata catalog"
```

## Task 2: Shared Provider Registration Factory

**Files:**
- Create: `src/Rook/Services/Vision/VisionProviderRegistrations.cs`
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Modify: `src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`

- [ ] **Step 1: Write failing helper tests**

Add tests that pin default provider metadata without constructing UI state or provider instances. Credential metadata is grouped by credential owner, not by model provider identity: Veo remains model provider `veo`, but its `gemini.api_key` requirement contributes to the Gemini credential card.

```csharp
[Fact]
public void VisionProviderRegistrations_metadata_merges_gemini_owner_and_fal_from_image_and_video()
{
    var metadata = VisionProviderRegistrations.CreateCredentialMetadata();

    var providers = metadata.EnumerateProviders().ToArray();

    Assert.Equal(new[] { "gemini", "fal" }, providers.Select(p => p.ProviderName));
    Assert.Contains(providers, p => p.ProviderName == "gemini"
        && p.SecretRequirements.Any(r => r.Key == GenerationSecretKeys.GeminiApiKey));
    Assert.Contains(providers, p => p.ProviderName == "fal"
        && p.SecretRequirements.Any(r => r.Key == GenerationSecretKeys.FalApiKey));
    Assert.DoesNotContain(providers, p => p.ProviderName == "veo");
}

[Fact]
public void VisionProviderRegistrations_normalizes_fal_secret_display_metadata()
{
    var metadata = VisionProviderRegistrations.CreateCredentialMetadata();

    var fal = Assert.Single(metadata.EnumerateProviders(), p => p.ProviderName == "fal");
    var requirement = Assert.Single(fal.SecretRequirements, r => r.Key == GenerationSecretKeys.FalApiKey);

    Assert.Equal("fal.ai API key", requirement.DisplayName);
}
```

Place this in a new or existing test class where `VisionProviderRegistrations` is visible. If production type is `internal`, add the test under `src/Rook.Tests/Services/Vision/`.

Also add a source-level guard test that `CreateCredentialMetadata` does not call `CreateImageRegistrations`, `CreateVideoRegistrations`, or `new VeoProvider`/`new FalVideoProvider`. This protects the lazy-video boundary from being regressed while keeping the runtime test lightweight.

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter VisionProviderRegistrations
```

Expected: compile failure because `VisionProviderRegistrations` does not exist.

- [ ] **Step 3: Add shared registration helper**

Create `src/Rook/Services/Vision/VisionProviderRegistrations.cs`:

```csharp
using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;

namespace Rook.Services.Vision
{
    internal static class VisionProviderRegistrations
    {
        public static IReadOnlyList<IImageProviderRegistration> CreateImageRegistrations(
            Func<string?> geminiKeyProvider,
            Func<string?> falKeyProvider)
            => Array.AsReadOnly(new IImageProviderRegistration[]
            {
                new GeminiImageProviderRegistration(new GeminiImageProvider(geminiKeyProvider)),
                new FalImageProviderRegistration(new FalImageProvider(falKeyProvider)),
            });

        public static IReadOnlyList<IVideoProviderRegistration> CreateVideoRegistrations(
            Func<string?> geminiKeyProvider,
            Func<string?> falKeyProvider)
            => Array.AsReadOnly(new IVideoProviderRegistration[]
            {
                new VeoProviderRegistration(new VeoProvider(geminiKeyProvider)),
                new FalVideoProviderRegistration(new FalVideoProvider(falKeyProvider)),
            });

        public static ProviderCredentialMetadataCatalog CreateCredentialMetadata()
        {
            return ProviderCredentialMetadataCatalog.FromProviders(new[]
            {
                new ProviderCredentialMetadata(
                    GeminiImageCapabilities.ProviderName,
                    Array.AsReadOnly(new[]
                    {
                        new ProviderSecretRequirement(
                            GenerationSecretKeys.GeminiApiKey,
                            "Gemini API key",
                            isRequired: true),
                    })),
                new ProviderCredentialMetadata(
                    FalImageCapabilities.ProviderName,
                    Array.AsReadOnly(new[]
                    {
                        new ProviderSecretRequirement(
                            GenerationSecretKeys.FalApiKey,
                            "fal.ai API key",
                            isRequired: true),
                    })),
            });
        }
    }
}
```

Do not change model provider names while adding this metadata. `VideoModelDescriptor.ProviderName` for Veo remains `veo`; only the Settings credential owner for `gemini.api_key` is `gemini`. Do not construct image or video provider registrations in `CreateCredentialMetadata`; Settings metadata must stay declarative and must not instantiate `VeoProvider`, `FalVideoProvider`, or the video subsystem path.

- [ ] **Step 4: Refactor default registry construction to use helper**

In `VisionHandler` constructor, replace inline default image registration construction with:

```csharp
_imageProviderRegistry = imageProviderRegistry
    ?? new DefaultImageProviderRegistry(
        VisionProviderRegistrations.CreateImageRegistrations(
            GetGeminiApiKey,
            GetFalApiKey));
```

In `VideoSubsystemFactory.Build`, replace local provider and registration construction with:

```csharp
var registry = new DefaultVideoProviderRegistry(
    VisionProviderRegistrations.CreateVideoRegistrations(
        () => generationSecrets.GetSecret(GenerationSecretKeys.GeminiApiKey),
        () => generationSecrets.GetSecret(GenerationSecretKeys.FalApiKey)));
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "DefaultImageProviderRegistryTests|DefaultVideoProviderRegistryTests|VideoSubsystemFactoryTests|VisionProviderRegistrations"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\VisionProviderRegistrations.cs `
        src\Rook\Handlers\VisionHandler.cs `
        src\Rook\Services\Vision\Video\VideoSubsystemFactory.cs `
        src\Rook.Tests
git commit -m "refactor(vision): centralize provider registrations"
```

## Task 3: Provider Secret Bridge Ops

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Write failing handler tests for provider secret ops**

Add tests to `VisionHandlerTests`:

```csharp
[Fact]
public void SetProviderSecret_saves_declared_fal_key_and_returns_preview()
{
    var secrets = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(secrets);
    var args = ParseArgs("""
        {
          "provider_name": "fal",
          "secret_key": "fal.api_key",
          "value": "fal_123456789"
        }
        """);

    var response = handler.SetProviderSecret(args);

    Assert.True(response.Success);
    Assert.Equal("fal_123456789", secrets.GetSecret(GenerationSecretKeys.FalApiKey));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.Equal("fal", data["provider_name"]);
    Assert.Equal(GenerationSecretKeys.FalApiKey, data["secret_key"]);
    Assert.Equal(true, data["has_secret"]);
    Assert.NotNull(data["preview"]);
}

[Fact]
public void SetProviderSecret_rejects_cross_provider_key()
{
    var secrets = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(secrets);
    var args = ParseArgs("""
        {
          "provider_name": "gemini",
          "secret_key": "fal.api_key",
          "value": "fal_123456789"
        }
        """);

    var response = handler.SetProviderSecret(args);

    Assert.False(response.Success);
    Assert.Null(secrets.GetSecret(GenerationSecretKeys.FalApiKey));
}

[Fact]
public void Legacy_SetApiKey_cannot_set_fal_secret()
{
    var secrets = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(secrets);
    var args = ParseArgs("""
        {
          "api_key": "gemini-value",
          "provider_name": "fal",
          "secret_key": "fal.api_key"
        }
        """);

    var response = handler.SetApiKey(args);

    Assert.True(response.Success);
    Assert.Equal("gemini-value", secrets.GetSecret(GenerationSecretKeys.GeminiApiKey));
    Assert.Null(secrets.GetSecret(GenerationSecretKeys.FalApiKey));
}
```

Add helpers if absent:

```csharp
private static VisionHandler NewHandlerWithSecrets(IGenerationSecretStore secrets)
    => new(
        new ArtifactStore(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"))),
        secrets,
        new PromptEnhancer(),
        new ViewportHandler());
```

- [ ] **Step 2: Write failing bridge route tests**

Update `VisionWebSurfaceTests.OpRoutes_Contains_All_Expected_Ops` expected array with:

```csharp
"set_provider_secret", "test_provider_secret", "clear_provider_secret",
"list_image_models",
```

Update dispatcher route theory:

```csharp
[InlineData("set_provider_secret", "OffUi")]
[InlineData("clear_provider_secret", "OffUi")]
[InlineData("list_image_models", "OffUi")]
[InlineData("test_provider_secret", "Async")]
```

- [ ] **Step 3: Run tests and verify fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionHandlerTests|VisionWebSurfaceTests"
```

Expected: compile failure for missing provider methods and route failures for missing op names.

- [ ] **Step 4: Add metadata catalog dependency and op routing**

In `VisionHandler`, add a private field:

```csharp
private readonly ProviderCredentialMetadataCatalog _credentialMetadata;
```

Extend the private constructor with a defaulted `ProviderCredentialMetadataCatalog? credentialMetadata = null` parameter, and initialize:

```csharp
_credentialMetadata = credentialMetadata
    ?? VisionProviderRegistrations.CreateCredentialMetadata();
```

Add off-UI dispatch cases:

```csharp
"set_provider_secret" => SetProviderSecret(args),
"clear_provider_secret" => ClearProviderSecret(args),
"list_image_models" => ListImageModels(args),
```

Add async dispatch case:

```csharp
"test_provider_secret" => await TestProviderSecretAsync(args, cancellationToken).ConfigureAwait(false),
```

Update wrong-dispatch guard sets so provider ops report the correct dispatcher if misrouted.

In `VisionWebSurface.OpRoutes`, add:

```csharp
["set_provider_secret"] = VisionOpRoute.OffUi,
["clear_provider_secret"] = VisionOpRoute.OffUi,
["list_image_models"] = VisionOpRoute.OffUi,
["test_provider_secret"] = VisionOpRoute.Async,
```

- [ ] **Step 5: Add provider secret set/clear implementation**

Add helper methods in `VisionHandler`:

```csharp
internal ApiResponse SetProviderSecret(Dictionary<string, JsonElement> args)
{
    var (metadata, requirement, error) = ResolveProviderSecret(args);
    if (error is not null) return Fail(error);
    if (!TryGetProviderSecretStore(out var secretStore, out var storeError)) return Fail(storeError);

    var value = RequireString(args, "value", 4096);
    try
    {
        secretStore!.SetSecret(requirement!.Key, value);
    }
    catch (ArgumentException ex)
    {
        return Fail(ex.Message);
    }

    return Ok(ProviderSecretMutationEnvelope(secretStore!, metadata!.ProviderName, requirement.Key));
}

internal ApiResponse ClearProviderSecret(Dictionary<string, JsonElement> args)
{
    var (metadata, requirement, error) = ResolveProviderSecret(args);
    if (error is not null) return Fail(error);
    if (!TryGetProviderSecretStore(out var secretStore, out var storeError)) return Fail(storeError);

    secretStore!.RemoveSecret(requirement!.Key);
    return Ok(ProviderSecretMutationEnvelope(secretStore!, metadata!.ProviderName, requirement.Key));
}
```

Add explicit secret-store helpers. Provider mutation and stored-provider test paths require the new generation secret store; read-only Settings/model summaries must degrade through the legacy Gemini store path instead of throwing:

```csharp
private bool TryGetProviderSecretStore(
    out IGenerationSecretStore? secretStore,
    out string error)
{
    if (_generationSecrets is not null)
    {
        secretStore = _generationSecrets;
        error = "";
        return true;
    }

    secretStore = null;
    error = "Provider secret operations require the generation secret store.";
    return false;
}

private IGenerationSecretStore CredentialStatusSecretStore
    => _generationSecrets ?? new LegacyGeminiGenerationSecretStatusStore(_secrets);
```

Add a small private adapter for read-only summaries when a handler is constructed with the legacy `VisionSecretStore` path:

```csharp
private sealed class LegacyGeminiGenerationSecretStatusStore : IGenerationSecretStore
{
    private readonly VisionSecretStore _legacy;

    public LegacyGeminiGenerationSecretStatusStore(VisionSecretStore legacy)
    {
        _legacy = legacy ?? throw new ArgumentNullException(nameof(legacy));
    }

    public string? GetSecret(string secretKey)
        => string.Equals(secretKey, GenerationSecretKeys.GeminiApiKey, StringComparison.Ordinal)
            ? _legacy.GetGeminiApiKey()
            : null;

    public bool HasSecret(string secretKey)
        => string.Equals(secretKey, GenerationSecretKeys.GeminiApiKey, StringComparison.Ordinal)
            && _legacy.HasGeminiApiKey();

    public string? GetPreview(string secretKey)
        => string.Equals(secretKey, GenerationSecretKeys.GeminiApiKey, StringComparison.Ordinal)
            ? _legacy.GetApiKeyPreview()
            : null;

    public void SetSecret(string secretKey, string value)
        => throw new NotSupportedException("Legacy credential status adapter is read-only.");

    public void RemoveSecret(string secretKey)
        => throw new NotSupportedException("Legacy credential status adapter is read-only.");
}
```

Add a `GetSettingsOverview` test that constructs `VisionHandler` with the existing `VisionSecretStore` constructor and asserts the overview still succeeds, includes provider credential summaries, reports Gemini presence from the legacy store, and reports fal missing instead of throwing. Add a `ListImageModels` equivalent if existing tests cover that constructor path.

Add resolver:

```csharp
private (ProviderCredentialMetadata? Metadata, ProviderSecretRequirement? Requirement, string? Error)
    ResolveProviderSecret(Dictionary<string, JsonElement> args)
{
    var providerName = RequireString(args, "provider_name", 128);
    var secretKey = RequireString(args, "secret_key", 256);

    if (!_credentialMetadata.TryGetProvider(providerName, out var metadata))
        return (null, null, $"Unknown provider '{providerName}'.");

    foreach (var requirement in metadata.SecretRequirements)
    {
        if (string.Equals(requirement.Key, secretKey, StringComparison.Ordinal))
            return (metadata, requirement, null);
    }

    return (metadata, null, $"Secret key '{secretKey}' is not declared by provider '{providerName}'.");
}
```

Add mutation envelope:

```csharp
private Dictionary<string, object?> ProviderSecretMutationEnvelope(
    IGenerationSecretStore secretStore,
    string providerName,
    string secretKey)
    => new()
    {
        ["provider_name"] = providerName,
        ["secret_key"] = secretKey,
        ["has_secret"] = secretStore.HasSecret(secretKey),
        ["preview"] = secretStore.GetPreview(secretKey),
    };
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionHandlerTests|VisionWebSurfaceTests"
```

Expected: provider set/clear and route tests pass, except tests for test-provider-secret if added in Task 4.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Handlers\VisionHandler.cs `
        src\Rook\UI\Vision\VisionWebSurface.cs `
        src\Rook.Tests\Handlers\VisionHandlerTests.cs `
        src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): add provider secret bridge ops"
```

## Task 4: Provider Secret Test Results

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Write failing tests for test semantics**

Add tests:

```csharp
[Fact]
public async Task TestProviderSecret_without_candidate_reads_stored_secret_without_persisting_validation()
{
    var secrets = new InMemoryGenerationSecretStore();
    secrets.SetSecret(GenerationSecretKeys.FalApiKey, "fal-stored-key");
    var handler = NewHandlerWithSecrets(secrets);
    var args = ParseArgs("""
        {
          "provider_name": "fal",
          "secret_key": "fal.api_key"
        }
        """);

    var response = await handler.TestProviderSecretAsync(args, CancellationToken.None);

    Assert.True(response.Success);
    Assert.Equal("fal-stored-key", secrets.GetSecret(GenerationSecretKeys.FalApiKey));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.Equal("inconclusive", data["validation_state"]);
}

[Fact]
public async Task TestProviderSecret_with_candidate_does_not_save_candidate()
{
    var secrets = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(secrets);
    var args = ParseArgs("""
        {
          "provider_name": "fal",
          "secret_key": "fal.api_key",
          "candidate_value": "fal-candidate"
        }
        """);

    var response = await handler.TestProviderSecretAsync(args, CancellationToken.None);

    Assert.True(response.Success);
    Assert.Null(secrets.GetSecret(GenerationSecretKeys.FalApiKey));
    var serialized = System.Text.Json.JsonSerializer.Serialize(response.Data);
    Assert.DoesNotContain("fal-candidate", serialized);
}

[Fact]
public async Task TestProviderSecret_with_blank_candidate_fails_without_using_stored_secret()
{
    var secrets = new InMemoryGenerationSecretStore();
    secrets.SetSecret(GenerationSecretKeys.FalApiKey, "fal-stored-key");
    var handler = NewHandlerWithSecrets(secrets);
    var args = ParseArgs("""
        {
          "provider_name": "fal",
          "secret_key": "fal.api_key",
          "candidate_value": "   "
        }
        """);

    var response = await handler.TestProviderSecretAsync(args, CancellationToken.None);

    Assert.False(response.Success);
    Assert.Equal("fal-stored-key", secrets.GetSecret(GenerationSecretKeys.FalApiKey));
}

[Fact]
public async Task Legacy_TestApiKey_cannot_test_fal_secret()
{
    var secrets = new InMemoryGenerationSecretStore();
    secrets.SetSecret(GenerationSecretKeys.FalApiKey, "fal-stored-key");
    var handler = NewHandlerWithSecrets(secrets);
    var args = ParseArgs("""
        {
          "provider_name": "fal",
          "secret_key": "fal.api_key"
        }
        """);

    var response = await handler.TestApiKeyAsync(args, CancellationToken.None);

    Assert.False(response.Success);
    Assert.Contains("No API key provided or stored", response.Data?.ToString());
}
```

Add or preserve coverage that an invalid Gemini probe through legacy `test_api_key` returns `Success == false`, not a success-style provider validation envelope. If the current `PromptEnhancer` makes Gemini invalid-probe testing hard to isolate, keep existing legacy failure coverage and add a fake enhancer seam only if already present.

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "TestProviderSecret|Legacy_TestApiKey"
```

Expected: compile failure because `TestProviderSecretAsync` does not exist.

- [ ] **Step 3: Add provider test implementation**

Add in `VisionHandler`:

```csharp
internal async Task<ApiResponse> TestProviderSecretAsync(
    Dictionary<string, JsonElement> args,
    CancellationToken cancellationToken)
{
    var (metadata, requirement, error) = ResolveProviderSecret(args);
    if (error is not null) return Fail(error);

    var hasCandidate = args.ContainsKey("candidate_value");
    string? value;
    if (hasCandidate)
    {
        value = GetStringArg(args, "candidate_value");
    }
    else
    {
        if (!TryGetProviderSecretStore(out var secretStore, out var storeError)) return Fail(storeError);
        value = secretStore!.GetSecret(requirement!.Key);
    }

    if (hasCandidate && string.IsNullOrWhiteSpace(value))
        return Fail("Credential value must be non-empty.");

    if (!hasCandidate && string.IsNullOrEmpty(value))
    {
        return Fail($"No stored credential for provider '{metadata!.ProviderName}' key '{requirement.Key}'.");
    }

    if (string.IsNullOrWhiteSpace(value))
        return Fail("Credential value must be non-empty.");

    if (string.Equals(metadata!.ProviderName, "gemini", StringComparison.Ordinal)
        && string.Equals(requirement!.Key, GenerationSecretKeys.GeminiApiKey, StringComparison.Ordinal))
    {
        var result = await TestGeminiProviderSecretAsync(value!, cancellationToken).ConfigureAwait(false);
        return Ok(ProviderSecretTestEnvelope(
            "gemini",
            GenerationSecretKeys.GeminiApiKey,
            result.ValidationState,
            result.Message));
    }

    if (string.Equals(metadata.ProviderName, "fal", StringComparison.Ordinal)
        && string.Equals(requirement!.Key, GenerationSecretKeys.FalApiKey, StringComparison.Ordinal))
    {
        return await TestFalProviderSecretAsync(value!, cancellationToken).ConfigureAwait(false);
    }

    return Ok(ProviderSecretTestEnvelope(metadata.ProviderName, requirement!.Key, "inconclusive",
        "No provider-specific validation probe is available."));
}
```

Extract existing `TestApiKeyAsync` probe body into a core result helper used by both provider-aware and legacy paths:

```csharp
private async Task<ProviderSecretValidationResult> TestGeminiProviderSecretAsync(
    string apiKey,
    CancellationToken cancellationToken)
{
    var probe = await _enhancer.EnhancePromptAsync(
        apiKey, "ping", null, cancellationToken).ConfigureAwait(false);

    if (probe.Success)
        return ProviderSecretValidationResult.Valid();

    return ProviderSecretValidationResult.Invalid(GenericizeProviderError(probe.Error));
}
```

Change `TestApiKeyAsync` to remain Gemini-only and preserve legacy failure semantics for the existing UI, which treats successful bridge calls as "Test passed":

```csharp
internal async Task<ApiResponse> TestApiKeyAsync(
    Dictionary<string, JsonElement> args,
    CancellationToken cancellationToken)
{
    string? apiKey = GetStringArg(args, "api_key");
    if (string.IsNullOrEmpty(apiKey))
    {
        try { apiKey = _secrets.GetGeminiApiKey(); }
        catch (InvalidOperationException ex) { return Fail(ex.Message); }

        if (string.IsNullOrEmpty(apiKey))
            return Fail("No API key provided or stored. Pass 'api_key' to test a candidate key, or configure one via set_api_key first.");
    }

    var result = await TestGeminiProviderSecretAsync(apiKey!, cancellationToken).ConfigureAwait(false);
    if (string.Equals(result.ValidationState, "valid", StringComparison.Ordinal))
        return Ok(new Dictionary<string, object?> { ["ok"] = true });

    return Fail(result.Message ?? "API key test failed.");
}
```

Add a fal credential probe seam that is explicitly non-generation and non-spend. Production behavior for PR-9 returns `inconclusive` unless a proven non-generation platform endpoint is wired in the same task; tests can inject probe outcomes to pin valid/invalid/inconclusive mapping without live network calls:

```csharp
internal Func<string, CancellationToken, Task<ProviderSecretValidationResult>> FalCredentialProbeAsync { get; set; }
    = DefaultFalCredentialProbeAsync;

private async Task<ApiResponse> TestFalProviderSecretAsync(
    string apiKey,
    CancellationToken cancellationToken)
{
    var result = await FalCredentialProbeAsync(apiKey, cancellationToken).ConfigureAwait(false);
    return Ok(ProviderSecretTestEnvelope(
        "fal",
        GenerationSecretKeys.FalApiKey,
        result.ValidationState,
        result.Message));
}

private static Task<ProviderSecretValidationResult> DefaultFalCredentialProbeAsync(
    string apiKey,
    CancellationToken cancellationToken)
{
    _ = apiKey;
    _ = cancellationToken;
    return Task.FromResult(ProviderSecretValidationResult.Inconclusive(
        "fal credential could not be proven without running generation work."));
}
```

Use the same result shape for Gemini and fal internally:

```csharp
internal readonly struct ProviderSecretValidationResult
{
    private ProviderSecretValidationResult(string validationState, string? message)
    {
        ValidationState = validationState;
        Message = message;
    }

    public string ValidationState { get; }
    public string? Message { get; }

    public static ProviderSecretValidationResult Valid(string? message = null)
        => new("valid", message);

    public static ProviderSecretValidationResult Invalid(string? message = null)
        => new("invalid", message);

    public static ProviderSecretValidationResult Inconclusive(string? message = null)
        => new("inconclusive", message);
}
```

If a stable fal platform endpoint is selected during implementation, wire it only through `DefaultFalCredentialProbeAsync`: map 401/403 to `invalid`, clear authenticated success to `valid`, and endpoint/public/redirect/rate-limit/scope/network ambiguity to `inconclusive`. Do not call `fal.run`, `fal.subscribe`, `queue.fal.run`, or any model endpoint from Settings.

Add envelope:

```csharp
private static Dictionary<string, object?> ProviderSecretTestEnvelope(
    string providerName,
    string secretKey,
    string validationState,
    string? message)
    => new()
    {
        ["provider_name"] = providerName,
        ["secret_key"] = secretKey,
        ["validation_state"] = validationState,
        ["message"] = string.IsNullOrEmpty(message) ? null : message,
    };
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "TestProviderSecret|Legacy_TestApiKey|TestApiKey"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Handlers\VisionHandler.cs src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "feat(vision): test provider secrets without persistence"
```

## Task 5: Settings Overview Provider Credential Summaries

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Write failing overview tests**

Add tests:

```csharp
[Fact]
public void GetSettingsOverview_includes_provider_credentials_for_gemini_and_fal()
{
    var secrets = new InMemoryGenerationSecretStore();
    secrets.SetSecret(GenerationSecretKeys.GeminiApiKey, "gemini-secret");
    var handler = NewHandlerWithSecrets(secrets);

    var response = handler.GetSettingsOverview(new Dictionary<string, JsonElement>());

    Assert.True(response.Success);
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    var credentials = Assert.IsAssignableFrom<IEnumerable<object>>(data["provider_credentials"]);
    var serialized = System.Text.Json.JsonSerializer.Serialize(credentials);
    Assert.Contains("\"provider_name\":\"gemini\"", serialized);
    Assert.Contains("\"provider_name\":\"fal\"", serialized);
    Assert.Contains("\"availability\":\"available_but_unverified\"", serialized);
    Assert.Contains("\"availability\":\"missing_required_secret\"", serialized);
}

[Fact]
public void GetSettingsOverview_preserves_legacy_available_models_alias()
{
    var handler = NewHandlerWithSecrets(new InMemoryGenerationSecretStore());

    var response = handler.GetSettingsOverview(new Dictionary<string, JsonElement>());

    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.True(data.ContainsKey("available_models"));
    Assert.True(data.ContainsKey("has_api_key"));
    Assert.True(data.ContainsKey("api_key_preview"));
}

[Fact]
public void GetSettingsOverview_with_legacy_vision_secret_store_does_not_throw()
{
    var root = CreateTempRoot("rook-vision-settings-legacy-provider-summary");
    var settingsPath = Path.Combine(root, "RookSettings.json");
    var secrets = new VisionSecretStore(new RookSettingsStore(settingsPath));
    secrets.SetGeminiApiKey("gemini-legacy-secret");
    var handler = new VisionHandler(
        new ArtifactStore(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"))),
        secrets,
        new PromptEnhancer(),
        new ViewportHandler());

    var response = handler.GetSettingsOverview(new Dictionary<string, JsonElement>());

    Assert.True(response.Success);
    var serialized = System.Text.Json.JsonSerializer.Serialize(response.Data);
    Assert.Contains("\"provider_name\":\"gemini\"", serialized);
    Assert.Contains("\"provider_name\":\"fal\"", serialized);
    Assert.Contains("\"presence\":\"present\"", serialized);
    Assert.Contains("\"missing_required_secret\"", serialized);
}
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "GetSettingsOverview"
```

Expected: provider credentials assertion fails because field is absent.

- [ ] **Step 3: Implement credential summary projection**

In `GetSettingsOverview`, add:

```csharp
["provider_credentials"] = BuildProviderCredentialSummaries(),
```

Add helpers:

```csharp
private List<Dictionary<string, object?>> BuildProviderCredentialSummaries()
{
    var summaries = new List<Dictionary<string, object?>>();
    foreach (var provider in _credentialMetadata.EnumerateProviders())
    {
        var status = ProviderCredentialStatusBuilder.Build(
            provider.ProviderName,
            provider.SecretRequirements,
            CredentialStatusSecretStore);

        summaries.Add(ProviderCredentialStatusToObj(status));
    }
    return summaries;
}

private static Dictionary<string, object?> ProviderCredentialStatusToObj(
    ProviderCredentialStatus status)
{
    var secrets = new List<Dictionary<string, object?>>(status.Secrets.Count);
    foreach (var secret in status.Secrets)
        secrets.Add(ProviderSecretStatusToObj(secret));

    return new Dictionary<string, object?>
    {
        ["provider_name"] = status.ProviderName,
        ["availability"] = CredentialAvailabilityToString(status.Availability),
        ["message"] = status.Message,
        ["secrets"] = secrets,
    };
}

private static Dictionary<string, object?> ProviderSecretStatusToObj(
    ProviderSecretStatus status)
    => new()
    {
        ["key"] = status.Requirement.Key,
        ["display_name"] = status.Requirement.DisplayName,
        ["is_required"] = status.Requirement.IsRequired,
        ["is_sensitive"] = status.Requirement.IsSensitive,
        ["presence"] = status.Presence == ProviderSecretPresence.Present ? "present" : "missing",
        ["validation_state"] = SecretValidationStateToString(status.ValidationState),
        ["preview"] = status.Preview,
        ["message"] = status.Message,
    };
```

Add string mappers:

```csharp
private static string CredentialAvailabilityToString(ProviderCredentialAvailability availability)
    => availability switch
    {
        ProviderCredentialAvailability.MissingRequiredSecret => "missing_required_secret",
        ProviderCredentialAvailability.InvalidCredential => "invalid_credential",
        ProviderCredentialAvailability.Available => "available",
        ProviderCredentialAvailability.AvailableButUnverified => "available_but_unverified",
        ProviderCredentialAvailability.AvailableWithInconclusiveValidation => "available_with_inconclusive_validation",
        _ => availability.ToString().ToLowerInvariant(),
    };

private static string SecretValidationStateToString(ProviderSecretValidationState state)
    => state switch
    {
        ProviderSecretValidationState.NotAttempted => "not_attempted",
        ProviderSecretValidationState.Valid => "valid",
        ProviderSecretValidationState.Invalid => "invalid",
        ProviderSecretValidationState.Inconclusive => "inconclusive",
        _ => state.ToString().ToLowerInvariant(),
    };
```

- [ ] **Step 4: Run tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "GetSettingsOverview|ProviderCredentialStatusBuilderTests"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Handlers\VisionHandler.cs src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "feat(vision): expose provider credential summaries"
```

## Task 6: Canonical `list_image_models`

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Write failing list-image-model tests**

Add tests:

```csharp
[Fact]
public void ListImageModels_returns_gemini_and_fal_descriptors_with_credential_presence()
{
    var secrets = new InMemoryGenerationSecretStore();
    secrets.SetSecret(GenerationSecretKeys.GeminiApiKey, "gemini-secret");
    var handler = NewHandlerWithSecrets(secrets);

    var response = handler.ListImageModels(new Dictionary<string, JsonElement>());

    Assert.True(response.Success);
    var json = System.Text.Json.JsonSerializer.Serialize(response.Data);
    Assert.Contains(GeminiImageCapabilities.NanoBanana2, json);
    Assert.Contains(FalImageCapabilities.FluxSchnell, json);
    Assert.Contains("\"provider_name\":\"gemini\"", json);
    Assert.Contains("\"provider_name\":\"fal\"", json);
    Assert.Contains("\"credential_availability\":\"available_but_unverified\"", json);
    Assert.Contains("\"credential_availability\":\"missing_required_secret\"", json);
}

[Fact]
public void ListImageModels_does_not_depend_on_settings_overview_available_models()
{
    var handler = NewHandlerWithSecrets(new InMemoryGenerationSecretStore());

    var response = handler.ListImageModels(new Dictionary<string, JsonElement>());

    Assert.True(response.Success);
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.True(data.ContainsKey("models"));
    Assert.False(data.ContainsKey("available_models"));
}

[Fact]
public void ListImageModels_with_legacy_vision_secret_store_does_not_throw()
{
    var root = CreateTempRoot("rook-vision-list-image-models-legacy-provider-summary");
    var settingsPath = Path.Combine(root, "RookSettings.json");
    var secrets = new VisionSecretStore(new RookSettingsStore(settingsPath));
    secrets.SetGeminiApiKey("gemini-legacy-secret");
    var handler = new VisionHandler(
        new ArtifactStore(Path.Combine(root, "artifacts")),
        secrets,
        new PromptEnhancer(),
        new ViewportHandler());

    var response = handler.ListImageModels(new Dictionary<string, JsonElement>());

    Assert.True(response.Success);
    var json = System.Text.Json.JsonSerializer.Serialize(response.Data);
    Assert.Contains("\"provider_name\":\"gemini\"", json);
    Assert.Contains("\"provider_name\":\"fal\"", json);
    Assert.Contains("\"credential_availability\":\"available_but_unverified\"", json);
    Assert.Contains("\"credential_availability\":\"missing_required_secret\"", json);
}
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ListImageModels"
```

Expected: compile failure because `ListImageModels` does not exist.

- [ ] **Step 3: Implement descriptor projection**

Add `ListImageModels` in `VisionHandler`:

```csharp
internal ApiResponse ListImageModels(Dictionary<string, JsonElement> args)
{
    _ = args;
    var descriptors = _imageProviderRegistry.EnumerateAllModels();
    var models = new List<Dictionary<string, object?>>(descriptors.Count);
    foreach (var descriptor in descriptors)
        models.Add(ImageModelDescriptorToObj(descriptor));

    return Ok(new Dictionary<string, object?>
    {
        ["models"] = models,
    });
}
```

Add projection helpers:

```csharp
private Dictionary<string, object?> ImageModelDescriptorToObj(ImageModelDescriptor descriptor)
{
    var credentialStatus = BuildCredentialStatusForProvider(descriptor.ProviderName);
    return new Dictionary<string, object?>
    {
        ["model_id"] = descriptor.ModelId,
        ["provider_name"] = descriptor.ProviderName,
        ["pricing_source"] = descriptor.PricingSource,
        ["credential_availability"] = CredentialAvailabilityToString(credentialStatus.Availability),
        ["credential_message"] = credentialStatus.Message,
        ["capability"] = ImageCapabilityToObj(descriptor.Capability),
    };
}

private ProviderCredentialStatus BuildCredentialStatusForProvider(string providerName)
{
    if (!_credentialMetadata.TryGetProvider(providerName, out var metadata))
    {
        return new ProviderCredentialStatus(
            providerName,
            ProviderCredentialAvailability.AvailableButUnverified,
            Array.Empty<ProviderSecretStatus>(),
            null);
    }

    return ProviderCredentialStatusBuilder.Build(
        metadata.ProviderName,
        metadata.SecretRequirements,
        CredentialStatusSecretStore);
}

private static Dictionary<string, object?> ImageCapabilityToObj(ImageCapability capability)
    => new()
    {
        ["id"] = capability.Id,
        ["name"] = capability.Name,
        ["status"] = capability.Status,
        ["modality"] = capability.Modality,
        ["sub_capabilities"] = capability.SubCapabilities,
        ["resolutions"] = capability.Resolutions,
        ["aspect_ratios"] = capability.AspectRatios,
        ["max_reference_images"] = capability.MaxReferenceImages,
        ["supports_image_to_image"] = capability.SupportsImageToImage,
        ["supports_text_to_image"] = capability.SupportsTextToImage,
    };
```

Do not add `pricing_kind` unless also adding a focused image pricing classifier and tests. The spec allows it to be absent in PR-9.

- [ ] **Step 4: Run tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ListImageModels|GetSettingsOverview"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Handlers\VisionHandler.cs src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "feat(vision): list provider-aware image models"
```

## Task 7: Settings UI Provider Cards

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html`
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Modify: `src/Rook/UI/Vision/Resources/styles.css`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Write failing resource tests**

Add tests:

```csharp
[Fact]
public void IndexHtml_Settings_UsesProviderCredentialsContainer()
{
    var html = ReadVisionResource("index.html");

    Assert.Contains("id=\"provider-credentials\"", html);
    Assert.DoesNotContain("id=\"save-api-key\"", html);
}

[Fact]
public void AppJs_RendersProviderCredentialCardsAndUsesProviderOps()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("function renderProviderCredentials", js);
    Assert.Contains("bridgeCall(\"set_provider_secret\"", js);
    Assert.Contains("bridgeCall(\"test_provider_secret\"", js);
    Assert.Contains("bridgeCall(\"clear_provider_secret\"", js);
    Assert.Contains("sessionValidationBySecret", js);
}

[Fact]
public void AppJs_RemovesOrGuardsLegacyApiKeyControls()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("if (el.providerCredentials)", js);
    Assert.Contains("if (el.toggleKeyBtn && el.apiKey)", js);
    Assert.Contains("if (el.saveApiKeyBtn && el.apiKey)", js);
    Assert.Contains("if (el.testApiKeyBtn && el.apiKey)", js);
}
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "IndexHtml_Settings_UsesProviderCredentialsContainer|AppJs_RendersProviderCredentialCardsAndUsesProviderOps"
```

Expected: FAIL because resources still have hard-coded API key controls.

- [ ] **Step 3: Replace settings credential markup**

In `index.html`, replace the current API Configuration card body with a credentials container that preserves the card shell:

```html
<div class="settings-card">
    <div class="card-header">
        <div class="card-icon">...</div>
        <h3>Credentials</h3>
    </div>
    <div class="card-body">
        <div id="provider-credentials" class="provider-credentials"></div>
        <div id="api-key-status" class="status-indicator"></div>
    </div>
</div>
```

Keep `id="api-key-status"` so existing status display tests and user feedback placement stay stable. Remove static `api-key`, `toggle-key`, `test-api-key`, and `save-api-key` controls only after JS replacement is ready in the same task.

In `app.js`, remove or guard every old hard-coded API key control reference before the markup removal lands:

```javascript
el.providerCredentials = $("provider-credentials");
el.apiKeyStatus = $("api-key-status");

// Remove legacy caching/listeners when no static key field exists, or keep them only behind null guards
// for a temporary compatibility fallback.
el.apiKey = $("api-key");
el.toggleKeyBtn = $("toggle-key");
el.saveApiKeyBtn = $("save-api-key");
el.testApiKeyBtn = $("test-api-key");
```

Any remaining legacy path must be guarded like:

```javascript
if (el.toggleKeyBtn && el.apiKey) {
    el.toggleKeyBtn.addEventListener("click", () => {
        const isPassword = el.apiKey.type === "password";
        el.apiKey.type = isPassword ? "text" : "password";
    });
}
if (el.saveApiKeyBtn && el.apiKey) el.saveApiKeyBtn.addEventListener("click", saveApiKey);
if (el.testApiKeyBtn && el.apiKey) el.testApiKeyBtn.addEventListener("click", testApiKey);
```

Also guard legacy status writes in `loadSettingsOverview`, `saveApiKey`, and `testApiKey` with `if (el.apiKey && el.apiKeyStatus)`. The provider-card renderer is the primary PR-9 path; the old `saveApiKey`/`testApiKey` functions may remain only as guarded compatibility code and must not throw when the static controls are absent.

- [ ] **Step 4: Add JS session overlay and renderer**

In `app.js`, add:

```javascript
const sessionValidationBySecret = new Map();

function secretOverlayKey(providerName, secretKey) {
    return `${providerName}::${secretKey}`;
}

function clearSecretOverlay(providerName, secretKey) {
    sessionValidationBySecret.delete(secretOverlayKey(providerName, secretKey));
}

function providerDisplayName(name) {
    if (name === "gemini") return "Google AI";
    if (name === "fal") return "fal.ai";
    return name;
}

function providerHelpText(name) {
    if (name === "gemini") return "Get your key from Google AI Studio. Stored encrypted under your Windows profile.";
    if (name === "fal") return "Get your key from fal.ai. Settings tests avoid generation work by default.";
    return "Stored encrypted under your Windows profile.";
}
```

Add renderer:

```javascript
function renderProviderCredentials(providers) {
    if (!el.providerCredentials) return;
    const list = Array.isArray(providers) ? providers : [];
    el.providerCredentials.innerHTML = list.map(provider => {
        const providerName = provider.provider_name || "";
        const secrets = Array.isArray(provider.secrets) ? provider.secrets : [];
        const fields = secrets.map(secret => {
            const key = secret.key || "";
            const overlay = sessionValidationBySecret.get(secretOverlayKey(providerName, key));
            const validation = overlay || secret.validation_state || "not_attempted";
            const preview = secret.preview || "";
            const placeholder = preview || `Enter ${secret.display_name || "credential"}`;
            return `
                <div class="provider-secret" data-provider="${escapeAttr(providerName)}" data-secret-key="${escapeAttr(key)}">
                    <label>${escapeHtml(secret.display_name || key)}</label>
                    <div class="input-group">
                        <input type="password" class="provider-secret-input" placeholder="${escapeAttr(placeholder)}">
                    </div>
                    <span class="input-hint">${escapeHtml(providerHelpText(providerName))}</span>
                    <div class="settings-actions">
                        <button class="btn btn-secondary provider-secret-test" type="button">Test</button>
                        <button class="btn btn-primary provider-secret-save" type="button">Save Key</button>
                        <button class="btn btn-secondary provider-secret-clear" type="button">Clear</button>
                    </div>
                    <div class="status-indicator ${credentialStatusClass(validation)}">${escapeHtml(credentialStatusText(secret, validation))}</div>
                </div>`;
        }).join("");
        return `
            <section class="provider-credential-card">
                <h4>${escapeHtml(providerDisplayName(providerName))}</h4>
                ${fields}
            </section>`;
    }).join("");
}
```

Add status helpers:

```javascript
function credentialStatusClass(validation) {
    if (validation === "valid") return "success";
    if (validation === "invalid") return "error";
    if (validation === "inconclusive") return "warning";
    return "";
}

function credentialStatusText(secret, validation) {
    if (validation === "valid") return "Test passed.";
    if (validation === "invalid") return "Credential test failed.";
    if (validation === "inconclusive") return "Credential present, validation inconclusive.";
    if (secret.presence === "present") return secret.preview ? `Configured (${secret.preview}).` : "Configured.";
    return "Not configured.";
}
```

In `loadSettingsOverview`, after reading `data`, call:

```javascript
renderProviderCredentials(data.provider_credentials);
```

Keep existing legacy key status assignments only as compatibility fallback if `provider_credentials` is absent and `el.apiKey && el.apiKeyStatus` are present.

- [ ] **Step 5: Add delegated click handlers**

Add:

```javascript
async function handleProviderCredentialClick(event) {
    const button = event.target.closest("button");
    if (!button) return;
    const row = button.closest(".provider-secret");
    if (!row) return;

    const providerName = row.dataset.provider || "";
    const secretKey = row.dataset.secretKey || "";
    const input = row.querySelector(".provider-secret-input");
    const value = input ? input.value.trim() : "";

    if (button.classList.contains("provider-secret-save")) {
        if (!value) {
            showCredentialRowStatus(row, "Enter a key first.", "error");
            return;
        }
        await bridgeCall("set_provider_secret", { provider_name: providerName, secret_key: secretKey, value });
        if (input) input.value = "";
        clearSecretOverlay(providerName, secretKey);
        await loadSettingsOverview();
        return;
    }

    if (button.classList.contains("provider-secret-clear")) {
        await bridgeCall("clear_provider_secret", { provider_name: providerName, secret_key: secretKey });
        clearSecretOverlay(providerName, secretKey);
        await loadSettingsOverview();
        return;
    }

    if (button.classList.contains("provider-secret-test")) {
        const args = { provider_name: providerName, secret_key: secretKey };
        if (value) args.candidate_value = value;
        const result = await bridgeCall("test_provider_secret", args);
        sessionValidationBySecret.set(secretOverlayKey(providerName, secretKey), result.validation_state || "inconclusive");
        showCredentialRowStatus(row, credentialStatusText({}, result.validation_state), credentialStatusClass(result.validation_state));
    }
}

function showCredentialRowStatus(row, message, type) {
    const status = row.querySelector(".status-indicator");
    if (!status) return;
    status.textContent = message;
    status.className = `status-indicator ${type || ""}`;
}
```

Wire in cache/listeners:

```javascript
el.providerCredentials = $("provider-credentials");
if (el.providerCredentials) {
    el.providerCredentials.addEventListener("click", handleProviderCredentialClick);
    el.providerCredentials.addEventListener("input", event => {
        const row = event.target.closest(".provider-secret");
        if (!row) return;
        clearSecretOverlay(row.dataset.provider || "", row.dataset.secretKey || "");
    });
}
```

- [ ] **Step 6: Add minimal CSS**

Add:

```css
.provider-credentials {
    display: grid;
    gap: var(--space-3);
}

.provider-credential-card {
    border-bottom: 1px dashed rgba(10, 10, 12, 0.15);
    padding-bottom: var(--space-3);
}

.provider-credential-card:last-child {
    border-bottom: none;
    padding-bottom: 0;
}

.provider-credential-card h4 {
    font-family: var(--type-display);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-bottom: var(--space-2);
}

.provider-secret {
    display: grid;
    gap: var(--space-1);
}

.status-indicator.warning {
    color: #8a5a00;
}
```

- [ ] **Step 7: Run resource tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests"
```

Expected: PASS. If brittle string tests fail due to removed legacy IDs, update tests to assert new provider-card behavior and fallback code, not old hard-coded buttons.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\UI\Vision\Resources\index.html `
        src\Rook\UI\Vision\Resources\app.js `
        src\Rook\UI\Vision\Resources\styles.css `
        src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): render provider credential cards"
```

## Task 8: Image Picker Uses `list_image_models`

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Write failing resource tests**

Add:

```csharp
[Fact]
public void AppJs_ImageCatalog_PrefersListImageModelsWithAvailableModelsFallback()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("bridgeCall(\"list_image_models\"", js);
    Assert.Contains("function normalizeImageModelDescriptor", js);
    Assert.Contains("data.available_models", js);
}

[Fact]
public void AppJs_InvalidCredentialWarningDoesNotDisableSubmit()
{
    var js = ReadVisionResource("app.js");

    Assert.Contains("function effectiveCredentialAvailability", js);
    Assert.Contains("function markProviderCredentialInvalid", js);
    Assert.Contains("sessionValidationBySecret.get", js);
    Assert.Contains("invalid_credential", js);
    Assert.DoesNotContain("availability === \"invalid_credential\" && option.disabled", js);
}
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageCatalog|InvalidCredentialWarning"
```

Expected: FAIL because image catalog still only uses `available_models`.

- [ ] **Step 3: Add image model loader**

Add:

```javascript
async function loadImageModels() {
    try {
        const data = await bridgeCall("list_image_models");
        if (Array.isArray(data.models) && data.models.length > 0) {
            modelCatalog = data.models.map(normalizeImageModelDescriptor);
            populateImageModelDropdowns(modelCatalog);
            return true;
        }
    } catch (e) {
        // Legacy fallback remains in loadSettingsOverview via available_models.
    }
    return false;
}

function normalizeImageModelDescriptor(m) {
    const cap = m.capability || {};
    return {
        model_id: m.model_id || "",
        short_name: m.short_name || m.model_id || "",
        label: cap.name || m.model_id || "",
        provider_name: m.provider_name || "",
        credential_availability: m.credential_availability || "available_but_unverified",
        credential_message: m.credential_message || "",
        supported_resolutions: cap.resolutions || m.supported_resolutions || [],
        aspect_ratios: cap.aspect_ratios || [],
        supports_image_to_image: cap.supports_image_to_image !== false,
        supports_text_to_image: cap.supports_text_to_image !== false,
        max_reference_images: Number(cap.max_reference_images || 0),
    };
}
```

Track provider-to-secret ownership from Settings summaries so the picker can join the JS session validation overlay without passing that overlay back into `list_image_models`:

```javascript
const providerSecretKeyByProvider = new Map();

function rememberProviderSecretKeys(providers) {
    providerSecretKeyByProvider.clear();
    const list = Array.isArray(providers) ? providers : [];
    list.forEach(provider => {
        const providerName = provider.provider_name || "";
        const secrets = Array.isArray(provider.secrets) ? provider.secrets : [];
        const primary = secrets.find(s => s && s.is_required !== false) || secrets[0];
        if (providerName && primary && primary.key) {
            providerSecretKeyByProvider.set(providerName, primary.key);
        }
    });
}

function effectiveCredentialAvailability(model) {
    const base = model.credential_availability || "available_but_unverified";
    const providerName = model.provider_name || "";
    const secretKey = model.credential_secret_key || providerSecretKeyByProvider.get(providerName);
    if (!providerName || !secretKey) return base;

    const overlay = sessionValidationBySecret.get(secretOverlayKey(providerName, secretKey));
    if (overlay === "invalid") return "invalid_credential";
    if (overlay === "valid") return "available";
    if (overlay === "inconclusive" && base !== "missing_required_secret") {
        return "available_with_inconclusive_validation";
    }
    return base;
}

function markProviderCredentialInvalid(providerName) {
    const secretKey = providerSecretKeyByProvider.get(providerName || "");
    if (!providerName || !secretKey) return;
    sessionValidationBySecret.set(secretOverlayKey(providerName, secretKey), "invalid");
    populateImageModelDropdowns(modelCatalog);
}
```

Call `rememberProviderSecretKeys(data.provider_credentials)` in `loadSettingsOverview` before rendering credentials or models. After `test_provider_secret` updates `sessionValidationBySecret`, call `populateImageModelDropdowns(modelCatalog)` so warning state in open pickers refreshes immediately. In existing image-generation submit error handling, if an auth failure can be attributed to the selected model's provider, call `markProviderCredentialInvalid(selectedModel.provider_name)`; this is panel-session state only and still does not block resubmission by itself.

Add dropdown rendering:

```javascript
function populateImageModelDropdowns(models) {
    const options = models.map(m => {
        const availability = effectiveCredentialAvailability(m);
        const disabled = availability === "missing_required_secret";
        const provider = m.provider_name ? ` · ${providerDisplayName(m.provider_name)}` : "";
        const warning = availability === "invalid_credential" ? " · credential warning" : "";
        const suffix = disabled ? " · configure key" : `${provider}${warning}`;
        return `<option value="${escapeAttr(m.short_name || m.model_id)}"${disabled ? " disabled" : ""}>${escapeHtml(m.label || m.model_id)}${escapeHtml(suffix)}</option>`;
    }).join("");
    if (el.modelSelect) el.modelSelect.innerHTML = options;
    if (el.studioModelSelect) el.studioModelSelect.innerHTML = options;
    syncResolutionOptions();
}
```

In `loadSettingsOverview`, call `await loadImageModels()` before legacy `available_models` population. Only execute legacy population if `loadImageModels()` returned false.

- [ ] **Step 4: Keep capability mismatch deterministic**

Update `syncResolutionOptions` and any selected-model helpers to read normalized descriptor fields:

```javascript
function supportedResolutionsForSelectedModel(selectEl) {
    const selected = selectEl && selectEl.value;
    const entry = modelCatalog.find(m => (m.short_name || m.model_id) === selected);
    if (entry && Array.isArray(entry.supported_resolutions) && entry.supported_resolutions.length > 0) {
        return entry.supported_resolutions;
    }
    return ["1K", "2K", "4K"];
}
```

When references are present, disable or prevent submit for models where `supports_image_to_image === false`. Use existing reference-count checks where possible; do not add visible filter controls.

- [ ] **Step 5: Run resource tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\UI\Vision\Resources\app.js src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): load provider-aware image catalog"
```

## Task 9: Native Boundary And Full Verification

**Files:**
- Modify tests only if a native allowlist/source test exists.
- No production native files.

- [ ] **Step 1: Search for accidental native exposure**

Run:

```powershell
rg -n "set_provider_secret|test_provider_secret|clear_provider_secret|list_image_models" src\RookNative src\Rook\InternalBridge src\Rook\UI\Vision
```

Expected:

- No hits under `src\RookNative`.
- Hits under `src\Rook\UI\Vision\VisionWebSurface.cs`.
- `list_image_models` and credential ops must not appear in native allowlists or `NativeGhBridgeRegistrar.ExpectedVisionOps`.

- [ ] **Step 2: Add or update boundary assertion if harness exists**

If `NativeGhBridgeRegistrarTests` already pins `ExpectedVisionOps`, add assertions:

```csharp
Assert.DoesNotContain("set_provider_secret", NativeGhBridgeRegistrar.ExpectedVisionOps);
Assert.DoesNotContain("test_provider_secret", NativeGhBridgeRegistrar.ExpectedVisionOps);
Assert.DoesNotContain("clear_provider_secret", NativeGhBridgeRegistrar.ExpectedVisionOps);
Assert.DoesNotContain("list_image_models", NativeGhBridgeRegistrar.ExpectedVisionOps);
```

If the set is private and no source test exists, document in the final PR notes that the boundary was verified by `rg` and review.

- [ ] **Step 3: Run focused managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ProviderCredentialMetadataCatalogTests|VisionHandlerTests|VisionWebSurfaceTests|DefaultImageProviderRegistryTests|DefaultVideoProviderRegistryTests|VideoSubsystemFactoryTests|ProviderCredentialStatusBuilderTests|GenerationSecretStoreTests"
```

Expected: PASS.

- [ ] **Step 4: Run full managed tests if practical**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: PASS. If this cannot run because Rhino/MFC or local machine prerequisites are missing, record the exact failure in the final answer. Do not claim full build verification unless it actually passes.

- [ ] **Step 5: Final status and commit any boundary test changes**

If Step 2 changed tests:

```powershell
git add src\Rook.Tests
git commit -m "test(vision): pin provider credential bridge boundary"
```

Otherwise no commit is needed for this task.

## Self-Review Checklist

Before opening a PR or asking for review:

- [ ] `set_api_key` and `test_api_key` cannot set or test fal.
- [ ] `set_provider_secret` rejects cross-provider secret keys.
- [ ] `test_provider_secret` never persists or returns candidate values.
- [ ] `clear_provider_secret` uses `IGenerationSecretStore.RemoveSecret`.
- [ ] fal Settings test does not call `fal.run` or `queue.fal.run`.
- [ ] `list_image_models` returns descriptors without using `get_settings_overview`.
- [ ] `get_settings_overview.available_models` still exists as a legacy alias.
- [ ] Missing fal key keeps fal models visible but not submittable.
- [ ] `InvalidCredential` warning does not block submit.
- [ ] No provider validation state is saved to settings.
- [ ] No files under `src/RookNative/**` changed.
