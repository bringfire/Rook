# Fal Substrate And Secret Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build PR-6: fal.ai substrate plus provider secret/status metadata, with no user-visible fal models or UI changes.

**Architecture:** Add provider credential metadata to the existing `Rook.Services.Vision.Generation` seam, then add managed-only fal substrate helpers under `Rook.Services.Vision.Fal`. PR-6 does not register fal models; it only gives later PRs the tested building blocks for fal image/video providers.

**Tech Stack:** C# multi-targeted `net7.0;net48`, xUnit, `System.Net.Http`, `System.Text.Json.Nodes`, existing `Rook.Services.Vision.Generation` seam.

---

## Source Context

PR-6 starts from `main` at `21fb43f`.

Primary design source:

- `docs/rook_docs/2026-04-29-multi-provider-phase2-fal-plan.md`

Current implementation seams:

- `src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs`
- `src/Rook/Services/Vision/Generation/DpapiGenerationSecretStore.cs`
- `src/Rook/Services/Vision/Generation/ProviderJobHandle.cs`
- `src/Rook/Services/Vision/Generation/ProviderStatusOutcome.cs`
- `src/Rook/Services/Vision/Generation/GenerationLifecycleStateNormalizer.cs`
- `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs`
- `src/Rook/Services/Vision/Video/IVideoProviderRegistration.cs`

Verification target:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore
dotnet build src/Rook/Rook.csproj --no-restore -p:RhinoPluginDir=
git diff --check
```

Native `RookNative` is out of scope for PR-6.

---

## File Structure

Create:

- `src/Rook/Services/Vision/Generation/ProviderSecretRequirement.cs` — immutable per-key requirement descriptor.
- `src/Rook/Services/Vision/Generation/ProviderSecretPresence.cs` — per-key presence enum.
- `src/Rook/Services/Vision/Generation/ProviderSecretValidationState.cs` — per-key live validation enum.
- `src/Rook/Services/Vision/Generation/ProviderSecretStatus.cs` — per-key computed status.
- `src/Rook/Services/Vision/Generation/ProviderCredentialAvailability.cs` — provider-level aggregate availability enum.
- `src/Rook/Services/Vision/Generation/ProviderCredentialStatus.cs` — provider-level aggregate status.
- `src/Rook/Services/Vision/Generation/ProviderCredentialStatusBuilder.cs` — metadata-only aggregation from `IGenerationSecretStore`.
- `src/Rook/Services/Vision/Fal/FalSecretKeys.cs` — fal-specific key constants that reference `GenerationSecretKeys`.
- `src/Rook/Services/Vision/Fal/FalHttpResponse.cs` — immutable response snapshot for fal substrate tests and parsers.
- `src/Rook/Services/Vision/Fal/FalApiClient.cs` — HTTP-only fal client: auth header, JSON submit, GET, cancel method dispatch.
- `src/Rook/Services/Vision/Fal/FalLifecycleMapper.cs` — fal queue JSON to `ProviderJobHandle` / `ProviderStatusOutcome`.
- `src/Rook/Services/Vision/Fal/FalErrorMapper.cs` — fal-shaped HTTP/body/header failures to `GenerationError`.
- `src/Rook/Services/Vision/Fal/FalPricingHelpers.cs` — case-insensitive `x-fal-billable-units` extraction.
- `src/Rook.Tests/Services/Vision/Generation/ProviderCredentialStatusBuilderTests.cs`
- `src/Rook.Tests/Services/Vision/Fal/FalApiClientTests.cs`
- `src/Rook.Tests/Services/Vision/Fal/FalLifecycleMapperTests.cs`
- `src/Rook.Tests/Services/Vision/Fal/FalErrorMapperTests.cs`
- `src/Rook.Tests/Services/Vision/Fal/FalPricingHelpersTests.cs`

Modify:

- `src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs` — add fal/replicate/tencent constants to `GenerationSecretKeys`.
- `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs` — add `SecretRequirements`.
- `src/Rook/Services/Vision/Video/IVideoProviderRegistration.cs` — add `SecretRequirements`.
- `src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs` — return Gemini secret requirement.
- `src/Rook/Services/Vision/Video/VeoProviderRegistration.cs` — return Gemini secret requirement.
- Test fake registration classes that implement provider-registration interfaces.
- `src/Rook.Tests/Services/Vision/Generation/InvariantBypassTests.cs` — include new immutable metadata types.

Do not modify:

- `src/RookNative/**`
- `src/Rook/UI/**`
- `src/Rook/Handlers/VisionHandler.cs`
- provider catalog registration in composition roots

---

### Task 1: Add Provider Secret Metadata Types

**Files:**
- Create: `src/Rook/Services/Vision/Generation/ProviderSecretRequirement.cs`
- Create: `src/Rook/Services/Vision/Generation/ProviderSecretPresence.cs`
- Create: `src/Rook/Services/Vision/Generation/ProviderSecretValidationState.cs`
- Create: `src/Rook/Services/Vision/Generation/ProviderSecretStatus.cs`
- Create: `src/Rook/Services/Vision/Generation/ProviderCredentialAvailability.cs`
- Create: `src/Rook/Services/Vision/Generation/ProviderCredentialStatus.cs`
- Modify: `src/Rook.Tests/Services/Vision/Generation/InvariantBypassTests.cs`

- [ ] **Step 1: Write invariant tests for the new immutable types**

Add these entries to the `InvariantTypes()` list in `src/Rook.Tests/Services/Vision/Generation/InvariantBypassTests.cs`:

```csharp
new object[] { typeof(ProviderSecretRequirement) },
new object[] { typeof(ProviderSecretStatus) },
new object[] { typeof(ProviderCredentialStatus) },
```

- [ ] **Step 2: Run the invariant tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~InvariantBypassTests"
```

Expected: compile failure because the three metadata types do not exist.

- [ ] **Step 3: Add `ProviderSecretRequirement`**

Create `src/Rook/Services/Vision/Generation/ProviderSecretRequirement.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Provider-declared credential slot. Phase 2 uses provider-level
    /// static requirements only; operation/model overlays are deferred
    /// to a later descriptor contract.
    /// </summary>
    public sealed class ProviderSecretRequirement
    {
        public ProviderSecretRequirement(
            string key,
            string displayName,
            bool isRequired,
            bool isSensitive = true)
        {
            if (string.IsNullOrWhiteSpace(key))
                throw new ArgumentException(
                    "Secret requirement key must be non-empty.", nameof(key));
            if (string.IsNullOrWhiteSpace(displayName))
                throw new ArgumentException(
                    "Secret requirement display name must be non-empty.",
                    nameof(displayName));

            Key = key;
            DisplayName = displayName;
            IsRequired = isRequired;
            IsSensitive = isSensitive;
        }

        public string Key { get; }
        public string DisplayName { get; }
        public bool IsRequired { get; }
        public bool IsSensitive { get; }
    }
}
```

- [ ] **Step 4: Add presence and validation enums**

Create `src/Rook/Services/Vision/Generation/ProviderSecretPresence.cs`:

```csharp
namespace Rook.Services.Vision.Generation
{
    public enum ProviderSecretPresence
    {
        Missing = 0,
        Present = 1,
    }
}
```

Create `src/Rook/Services/Vision/Generation/ProviderSecretValidationState.cs`:

```csharp
namespace Rook.Services.Vision.Generation
{
    public enum ProviderSecretValidationState
    {
        NotAttempted = 0,
        Valid = 1,
        Invalid = 2,
        Inconclusive = 3,
    }
}
```

- [ ] **Step 5: Add per-key status type**

Create `src/Rook/Services/Vision/Generation/ProviderSecretStatus.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderSecretStatus
    {
        public ProviderSecretStatus(
            ProviderSecretRequirement requirement,
            ProviderSecretPresence presence,
            ProviderSecretValidationState validationState,
            string? preview,
            string? message)
        {
            Requirement = requirement
                ?? throw new ArgumentNullException(nameof(requirement));
            Presence = presence;
            ValidationState = validationState;
            Preview = string.IsNullOrEmpty(preview) ? null : preview;
            Message = string.IsNullOrEmpty(message) ? null : message;
        }

        public ProviderSecretRequirement Requirement { get; }
        public ProviderSecretPresence Presence { get; }
        public ProviderSecretValidationState ValidationState { get; }
        public string? Preview { get; }
        public string? Message { get; }
    }
}
```

- [ ] **Step 6: Add provider-level availability enum and status type**

Create `src/Rook/Services/Vision/Generation/ProviderCredentialAvailability.cs`:

```csharp
namespace Rook.Services.Vision.Generation
{
    public enum ProviderCredentialAvailability
    {
        MissingRequiredSecret = 0,
        InvalidCredential = 1,
        Available = 2,
        AvailableButUnverified = 3,
        AvailableWithInconclusiveValidation = 4,
    }
}
```

Create `src/Rook/Services/Vision/Generation/ProviderCredentialStatus.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderCredentialStatus
    {
        public ProviderCredentialStatus(
            string providerName,
            ProviderCredentialAvailability availability,
            IReadOnlyList<ProviderSecretStatus> secrets,
            string? message)
        {
            if (string.IsNullOrWhiteSpace(providerName))
                throw new ArgumentException(
                    "Provider name must be non-empty.", nameof(providerName));
            if (secrets is null)
                throw new ArgumentNullException(nameof(secrets));

            var copy = new ProviderSecretStatus[secrets.Count];
            for (var i = 0; i < secrets.Count; i++)
            {
                copy[i] = secrets[i]
                    ?? throw new ArgumentException(
                        $"Secrets[{i}] is null.", nameof(secrets));
            }

            ProviderName = providerName;
            Availability = availability;
            Secrets = copy;
            Message = string.IsNullOrEmpty(message) ? null : message;
        }

        public string ProviderName { get; }
        public ProviderCredentialAvailability Availability { get; }
        public IReadOnlyList<ProviderSecretStatus> Secrets { get; }
        public string? Message { get; }
    }
}
```

- [ ] **Step 7: Run invariant tests and verify they pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~InvariantBypassTests"
```

Expected: pass.

- [ ] **Step 8: Commit Task 1**

Run:

```powershell
git add src/Rook/Services/Vision/Generation/ProviderSecretRequirement.cs `
        src/Rook/Services/Vision/Generation/ProviderSecretPresence.cs `
        src/Rook/Services/Vision/Generation/ProviderSecretValidationState.cs `
        src/Rook/Services/Vision/Generation/ProviderSecretStatus.cs `
        src/Rook/Services/Vision/Generation/ProviderCredentialAvailability.cs `
        src/Rook/Services/Vision/Generation/ProviderCredentialStatus.cs `
        src/Rook.Tests/Services/Vision/Generation/InvariantBypassTests.cs
git commit -m "feat(vision): add provider credential status types"
```

---

### Task 2: Add Credential Status Aggregation

**Files:**
- Create: `src/Rook/Services/Vision/Generation/ProviderCredentialStatusBuilder.cs`
- Create: `src/Rook.Tests/Services/Vision/Generation/ProviderCredentialStatusBuilderTests.cs`

- [ ] **Step 1: Write builder tests**

Create `src/Rook.Tests/Services/Vision/Generation/ProviderCredentialStatusBuilderTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public class ProviderCredentialStatusBuilderTests
    {
        [Fact]
        public void Missing_required_secret_blocks_provider()
        {
            var store = new FakeSecretStore();
            store.SetSecret("optional.token", "optional-value");
            var requirements = new[]
            {
                new ProviderSecretRequirement("provider.api_key", "API key", isRequired: true),
                new ProviderSecretRequirement("optional.token", "Optional token", isRequired: false),
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                requirements,
                store);

            Assert.Equal(
                ProviderCredentialAvailability.MissingRequiredSecret,
                status.Availability);
            Assert.Equal(ProviderSecretPresence.Missing, status.Secrets[0].Presence);
            Assert.Equal(ProviderSecretPresence.Present, status.Secrets[1].Presence);
        }

        [Fact]
        public void Optional_missing_secret_does_not_block_provider()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var requirements = new[]
            {
                new ProviderSecretRequirement("provider.api_key", "API key", isRequired: true),
                new ProviderSecretRequirement("provider.sts_token", "STS token", isRequired: false),
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                requirements,
                store);

            Assert.Equal(
                ProviderCredentialAvailability.AvailableButUnverified,
                status.Availability);
            Assert.Equal(ProviderSecretPresence.Missing, status.Secrets[1].Presence);
        }

        [Fact]
        public void Required_invalid_validation_blocks_provider()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Invalid,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations);

            Assert.Equal(
                ProviderCredentialAvailability.InvalidCredential,
                status.Availability);
        }

        [Fact]
        public void Optional_invalid_validation_is_per_key_only()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            store.SetSecret("provider.sts_token", "bad");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.sts_token"] = ProviderSecretValidationState.Invalid,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[]
                {
                    new ProviderSecretRequirement("provider.api_key", "API key", true),
                    new ProviderSecretRequirement("provider.sts_token", "STS token", false),
                },
                store,
                validations);

            Assert.Equal(
                ProviderCredentialAvailability.AvailableButUnverified,
                status.Availability);
            Assert.Equal(
                ProviderSecretValidationState.Invalid,
                status.Secrets[1].ValidationState);
        }

        [Fact]
        public void Required_inconclusive_validation_sets_provider_inconclusive()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Inconclusive,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations);

            Assert.Equal(
                ProviderCredentialAvailability.AvailableWithInconclusiveValidation,
                status.Availability);
        }

        [Fact]
        public void Required_valid_validation_sets_provider_available()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Valid,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations);

            Assert.Equal(ProviderCredentialAvailability.Available, status.Availability);
        }

        private sealed class FakeSecretStore : IGenerationSecretStore
        {
            private readonly Dictionary<string, string> _values =
                new Dictionary<string, string>(StringComparer.Ordinal);

            public string? GetSecret(string secretKey) =>
                _values.TryGetValue(secretKey, out var value) ? value : null;

            public void SetSecret(string secretKey, string value)
            {
                _values[secretKey] = value;
            }

            public void RemoveSecret(string secretKey)
            {
                _values.Remove(secretKey);
            }

            public bool HasSecret(string secretKey) => _values.ContainsKey(secretKey);

            public string? GetPreview(string secretKey) =>
                _values.ContainsKey(secretKey) ? "prev…1234" : null;
        }
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~ProviderCredentialStatusBuilderTests"
```

Expected: compile failure because `ProviderCredentialStatusBuilder` does not exist.

- [ ] **Step 3: Add builder implementation**

Create `src/Rook/Services/Vision/Generation/ProviderCredentialStatusBuilder.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public static class ProviderCredentialStatusBuilder
    {
        public static ProviderCredentialStatus Build(
            string providerName,
            IReadOnlyList<ProviderSecretRequirement> requirements,
            IGenerationSecretStore secretStore,
            IReadOnlyDictionary<string, ProviderSecretValidationState>? validationStates = null,
            IReadOnlyDictionary<string, string>? validationMessages = null)
        {
            if (string.IsNullOrWhiteSpace(providerName))
                throw new ArgumentException(
                    "Provider name must be non-empty.", nameof(providerName));
            if (requirements is null)
                throw new ArgumentNullException(nameof(requirements));
            if (secretStore is null)
                throw new ArgumentNullException(nameof(secretStore));

            var statuses = new List<ProviderSecretStatus>(requirements.Count);
            foreach (var requirement in requirements)
            {
                if (requirement is null)
                    throw new ArgumentException(
                        "Secret requirements cannot contain null entries.",
                        nameof(requirements));

                var presence = secretStore.HasSecret(requirement.Key)
                    ? ProviderSecretPresence.Present
                    : ProviderSecretPresence.Missing;

                var validation = ProviderSecretValidationState.NotAttempted;
                if (validationStates is not null
                    && validationStates.TryGetValue(requirement.Key, out var found))
                {
                    validation = found;
                }

                string? message = null;
                if (validationMessages is not null)
                    validationMessages.TryGetValue(requirement.Key, out message);

                statuses.Add(new ProviderSecretStatus(
                    requirement,
                    presence,
                    validation,
                    secretStore.GetPreview(requirement.Key),
                    message));
            }

            return new ProviderCredentialStatus(
                providerName,
                ComputeAvailability(statuses),
                statuses,
                BuildMessage(statuses));
        }

        private static ProviderCredentialAvailability ComputeAvailability(
            IReadOnlyList<ProviderSecretStatus> statuses)
        {
            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.Presence == ProviderSecretPresence.Missing)
                {
                    return ProviderCredentialAvailability.MissingRequiredSecret;
                }
            }

            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.ValidationState == ProviderSecretValidationState.Invalid)
                {
                    return ProviderCredentialAvailability.InvalidCredential;
                }
            }

            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.ValidationState == ProviderSecretValidationState.Inconclusive)
                {
                    return ProviderCredentialAvailability.AvailableWithInconclusiveValidation;
                }
            }

            var sawRequired = false;
            var allRequiredValid = true;
            foreach (var status in statuses)
            {
                if (!status.Requirement.IsRequired) continue;
                sawRequired = true;
                if (status.ValidationState != ProviderSecretValidationState.Valid)
                    allRequiredValid = false;
            }

            if (sawRequired && allRequiredValid)
                return ProviderCredentialAvailability.Available;

            return ProviderCredentialAvailability.AvailableButUnverified;
        }

        private static string? BuildMessage(IReadOnlyList<ProviderSecretStatus> statuses)
        {
            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.Presence == ProviderSecretPresence.Missing)
                {
                    return $"Missing required credential: {status.Requirement.DisplayName}.";
                }
            }

            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.ValidationState == ProviderSecretValidationState.Invalid)
                {
                    return status.Message
                        ?? $"Invalid credential: {status.Requirement.DisplayName}.";
                }
            }

            return null;
        }
    }
}
```

- [ ] **Step 4: Run builder tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~ProviderCredentialStatusBuilderTests"
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add src/Rook/Services/Vision/Generation/ProviderCredentialStatusBuilder.cs `
        src/Rook.Tests/Services/Vision/Generation/ProviderCredentialStatusBuilderTests.cs
git commit -m "feat(vision): aggregate provider credential status"
```

---

### Task 3: Expose Secret Requirements From Provider Registrations

**Files:**
- Modify: `src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs`
- Modify: `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Video/IVideoProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs`
- Modify: `src/Rook/Services/Vision/Video/VeoProviderRegistration.cs`
- Modify: every test fake implementing `IImageProviderRegistration` or `IVideoProviderRegistration`

- [ ] **Step 1: Add secret-key constants**

In `src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs`, update `GenerationSecretKeys`:

```csharp
public static class GenerationSecretKeys
{
    public const string GeminiApiKey = "gemini.api_key";
    public const string FalApiKey = "fal.api_key";
    public const string ReplicateApiToken = "replicate.api_token";
    public const string TencentSecretId = "tencent.secret_id";
    public const string TencentSecretKey = "tencent.secret_key";
    public const string TencentStsToken = "tencent.sts_token";
}
```

- [ ] **Step 2: Add registration interface properties**

In `src/Rook/Services/Vision/Image/IImageProviderRegistration.cs`, add:

```csharp
IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
```

The full interface should be:

```csharp
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public interface IImageProviderRegistration
    {
        string ProviderName { get; }
        IImageProvider Provider { get; }
        IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
        IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models { get; }
        IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
    }
}
```

In `src/Rook/Services/Vision/Video/IVideoProviderRegistration.cs`, add the same property:

```csharp
IReadOnlyList<Rook.Services.Vision.Generation.ProviderSecretRequirement> SecretRequirements { get; }
```

- [ ] **Step 3: Update Gemini image registration**

In `src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs`, add:

```csharp
public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
    = new[]
    {
        new ProviderSecretRequirement(
            GenerationSecretKeys.GeminiApiKey,
            "Gemini API key",
            isRequired: true),
    };
```

- [ ] **Step 4: Update Veo video registration**

In `src/Rook/Services/Vision/Video/VeoProviderRegistration.cs`, add:

```csharp
public IReadOnlyList<Rook.Services.Vision.Generation.ProviderSecretRequirement> SecretRequirements { get; }
    = new[]
    {
        new Rook.Services.Vision.Generation.ProviderSecretRequirement(
            Rook.Services.Vision.Generation.GenerationSecretKeys.GeminiApiKey,
            "Gemini API key",
            isRequired: true),
    };
```

- [ ] **Step 5: Update test fake registrations**

Run:

```powershell
rg -n "class .*Registration|IImageProviderRegistration|IVideoProviderRegistration" src\Rook.Tests src\Rook\Services\Vision
```

For each fake implementation, add:

```csharp
public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; init; }
    = Array.Empty<ProviderSecretRequirement>();
```

If the fake is not using `init`, use:

```csharp
public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
    = Array.Empty<ProviderSecretRequirement>();
```

Add `using Rook.Services.Vision.Generation;` when needed.

- [ ] **Step 6: Add registration metadata tests**

Add tests to existing registry test files:

In `src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs`, add:

```csharp
[Fact]
public void Gemini_registration_declares_gemini_secret_requirement()
{
    var registration = new GeminiImageProviderRegistration(new FakeImageProvider());

    var requirement = Assert.Single(registration.SecretRequirements);
    Assert.Equal(GenerationSecretKeys.GeminiApiKey, requirement.Key);
    Assert.True(requirement.IsRequired);
}
```

In `src/Rook.Tests/Services/Vision/Video/DefaultVideoProviderRegistryTests.cs`, add:

```csharp
[Fact]
public void Veo_registration_declares_gemini_secret_requirement()
{
    var registration = new VeoProviderRegistration(new FakeVideoProvider());

    var requirement = Assert.Single(registration.SecretRequirements);
    Assert.Equal(GenerationSecretKeys.GeminiApiKey, requirement.Key);
    Assert.True(requirement.IsRequired);
}
```

- [ ] **Step 7: Run registry tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~DefaultVideoProviderRegistryTests"
```

Expected: pass.

- [ ] **Step 8: Commit Task 3**

Run:

```powershell
git add src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs `
        src/Rook/Services/Vision/Image/IImageProviderRegistration.cs `
        src/Rook/Services/Vision/Video/IVideoProviderRegistration.cs `
        src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs `
        src/Rook/Services/Vision/Video/VeoProviderRegistration.cs `
        src/Rook.Tests
git commit -m "feat(vision): expose provider secret requirements"
```

---

### Task 4: Add Fal HTTP Substrate

**Files:**
- Create: `src/Rook/Services/Vision/Fal/FalSecretKeys.cs`
- Create: `src/Rook/Services/Vision/Fal/FalHttpResponse.cs`
- Create: `src/Rook/Services/Vision/Fal/FalApiClient.cs`
- Create: `src/Rook.Tests/Services/Vision/Fal/FalApiClientTests.cs`

- [ ] **Step 1: Write fal client tests**

Create `src/Rook.Tests/Services/Vision/Fal/FalApiClientTests.cs`:

```csharp
using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalApiClientTests
    {
        [Fact]
        public async Task PostJsonAsync_sends_key_auth_and_json_body()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{\"ok\":true}", Encoding.UTF8, "application/json"),
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var response = await client.PostJsonAsync(
                "test-key",
                new Uri("https://fal.run/fal-ai/flux/schnell"),
                "{\"prompt\":\"red cube\"}",
                CancellationToken.None);

            Assert.Equal(200, response.StatusCode);
            Assert.Equal("{\"ok\":true}", response.Body);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("Key", request.Headers.Authorization!.Scheme);
            Assert.Equal("test-key", request.Headers.Authorization.Parameter);
            Assert.Equal("application/json", request.Content!.Headers.ContentType!.MediaType);
        }

        [Fact]
        public async Task GetAsync_preserves_headers_case_insensitively()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    var response = new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("{\"status\":\"COMPLETED\"}", Encoding.UTF8, "application/json"),
                    };
                    response.Headers.TryAddWithoutValidation("x-fal-billable-units", "2.0");
                    return response;
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var response = await client.GetAsync(
                "test-key",
                new Uri("https://queue.fal.run/status/abc"),
                CancellationToken.None);

            Assert.True(response.Headers.ContainsKey("x-fal-billable-units"));
            Assert.Equal("2.0", response.Headers["x-fal-billable-units"][0]);
        }

        [Theory]
        [InlineData("POST")]
        [InlineData("PUT")]
        [InlineData("DELETE")]
        public async Task SendAsync_supports_cancel_methods(string method)
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            await client.SendAsync(
                "test-key",
                new HttpMethod(method),
                new Uri("https://queue.fal.run/cancel/abc"),
                bodyJson: null,
                CancellationToken.None);

            Assert.Equal(method, handler.Requests.Last().Method.Method);
        }

        [Fact]
        public async Task SendAsync_rejects_non_http_urls_before_adding_auth()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.GetAsync(
                    "test-key",
                    new Uri("file:///C:/temp/secret.json"),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalApiClientTests"
```

Expected: compile failure because fal substrate types do not exist. If `TestHttpMessageHandler` is inaccessible because it is `internal` in another namespace, change that helper to `public sealed class TestHttpMessageHandler` or duplicate a local fal test helper. Prefer making it public if no tests object.

- [ ] **Step 3: Add fal secret keys**

Create `src/Rook/Services/Vision/Fal/FalSecretKeys.cs`:

```csharp
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public static class FalSecretKeys
    {
        public const string ApiKey = GenerationSecretKeys.FalApiKey;
    }
}
```

- [ ] **Step 4: Add immutable fal response snapshot**

Create `src/Rook/Services/Vision/Fal/FalHttpResponse.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Fal
{
    public sealed class FalHttpResponse
    {
        public FalHttpResponse(
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
                copy[kvp.Key] = new List<string>(kvp.Value).ToArray();
            }
            Headers = copy;
        }

        public int StatusCode { get; }
        public string Body { get; }
        public IReadOnlyDictionary<string, IReadOnlyList<string>> Headers { get; }
        public bool IsSuccessStatusCode => StatusCode >= 200 && StatusCode <= 299;
    }
}
```

- [ ] **Step 5: Add fal API client**

Create `src/Rook/Services/Vision/Fal/FalApiClient.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Fal
{
    public sealed class FalApiClient
    {
        private readonly HttpClient _httpClient;

        public FalApiClient(HttpClient? httpClient = null)
        {
            _httpClient = httpClient ?? new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(5),
            };
        }

        public Task<FalHttpResponse> PostJsonAsync(
            string apiKey,
            Uri url,
            string bodyJson,
            CancellationToken ct) =>
            SendAsync(apiKey, HttpMethod.Post, url, bodyJson, ct);

        public Task<FalHttpResponse> GetAsync(
            string apiKey,
            Uri url,
            CancellationToken ct) =>
            SendAsync(apiKey, HttpMethod.Get, url, bodyJson: null, ct);

        public async Task<FalHttpResponse> SendAsync(
            string apiKey,
            HttpMethod method,
            Uri url,
            string? bodyJson,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(apiKey))
                throw new ArgumentException("fal API key must be non-empty.", nameof(apiKey));
            if (method is null) throw new ArgumentNullException(nameof(method));
            if (url is null) throw new ArgumentNullException(nameof(url));
            if (!url.IsAbsoluteUri)
                throw new ArgumentException("fal URL must be absolute.", nameof(url));
            if (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps)
                throw new ArgumentException(
                    $"fal URL must use http or https scheme; got '{url.Scheme}'.",
                    nameof(url));

            using var request = new HttpRequestMessage(method, url);
            request.Headers.Authorization = new AuthenticationHeaderValue("Key", apiKey);
            if (bodyJson is not null)
            {
                request.Content = new StringContent(bodyJson, Encoding.UTF8, "application/json");
            }

            using var response = await _httpClient.SendAsync(request, ct)
                .ConfigureAwait(false);
            var body = response.Content is null
                ? string.Empty
                : await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            return new FalHttpResponse(
                (int)response.StatusCode,
                body,
                CopyHeaders(response));
        }

        private static IReadOnlyDictionary<string, IReadOnlyList<string>> CopyHeaders(
            HttpResponseMessage response)
        {
            var headers = new Dictionary<string, IReadOnlyList<string>>(
                StringComparer.OrdinalIgnoreCase);

            foreach (var header in response.Headers)
                headers[header.Key] = new List<string>(header.Value).ToArray();

            if (response.Content is not null)
            {
                foreach (var header in response.Content.Headers)
                    headers[header.Key] = new List<string>(header.Value).ToArray();
            }

            return headers;
        }
    }
}
```

- [ ] **Step 6: Run fal client tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalApiClientTests"
```

Expected: pass.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add src/Rook/Services/Vision/Fal/FalSecretKeys.cs `
        src/Rook/Services/Vision/Fal/FalHttpResponse.cs `
        src/Rook/Services/Vision/Fal/FalApiClient.cs `
        src/Rook.Tests/Services/Vision/Fal/FalApiClientTests.cs `
        src/Rook.Tests/Services/Vision/Video/TestHttpMessageHandler.cs
git commit -m "feat(vision): add fal HTTP substrate"
```

---

### Task 5: Add Fal Lifecycle Mapping

**Files:**
- Create: `src/Rook/Services/Vision/Fal/FalLifecycleMapper.cs`
- Create: `src/Rook.Tests/Services/Vision/Fal/FalLifecycleMapperTests.cs`

- [ ] **Step 1: Write lifecycle mapper tests**

Create `src/Rook.Tests/Services/Vision/Fal/FalLifecycleMapperTests.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalLifecycleMapperTests
    {
        [Fact]
        public void ParseSubmitHandle_reads_queue_urls_and_cancel_method()
        {
            var json = JsonNode.Parse("""
                {
                  "request_id": "abc123",
                  "status": "IN_QUEUE",
                  "status_url": "https://queue.fal.run/status/abc123",
                  "response_url": "https://queue.fal.run/response/abc123",
                  "cancel_url": "https://queue.fal.run/cancel/abc123",
                  "queue_position": 3
                }
                """)!;

            var handle = FalLifecycleMapper.ParseSubmitHandle(json, "PUT");

            Assert.Equal("abc123", handle.ProviderJobId);
            Assert.Equal("https://queue.fal.run/status/abc123", handle.StatusUrl!.ToString());
            Assert.Equal("https://queue.fal.run/response/abc123", handle.ResponseUrl!.ToString());
            Assert.Equal("https://queue.fal.run/cancel/abc123", handle.CancelUrl!.ToString());
            Assert.Equal("PUT", handle.CancelHttpMethod);
            Assert.Equal(3, handle.ProviderMetadata!["queue_position"]!.GetValue<int>());
        }

        [Theory]
        [InlineData("IN_QUEUE", typeof(InFlightStatusOutcome), GenerationLifecycleState.Pending)]
        [InlineData("IN_PROGRESS", typeof(InFlightStatusOutcome), GenerationLifecycleState.Running)]
        [InlineData("COMPLETED", typeof(ProviderCompleteStatusOutcome), GenerationLifecycleState.Completed)]
        public void MapStatus_maps_fal_states(string rawState, Type expectedType, GenerationLifecycleState expectedState)
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse($$"""
                {
                  "request_id": "abc123",
                  "status": "{{rawState}}",
                  "queue_position": 1
                }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            Assert.IsType(expectedType, outcome);
            if (outcome is InFlightStatusOutcome inFlight)
                Assert.Equal(expectedState, inFlight.State);
        }

        [Fact]
        public void MapStatus_unknown_state_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                { "request_id": "abc123", "status": "TOTALLY_NEW" }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("Unknown fal lifecycle state", failed.Error.Message);
        }
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalLifecycleMapperTests"
```

Expected: compile failure because `FalLifecycleMapper` does not exist.

- [ ] **Step 3: Add lifecycle mapper**

Create `src/Rook/Services/Vision/Fal/FalLifecycleMapper.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public static class FalLifecycleMapper
    {
        public static ProviderJobHandle ParseSubmitHandle(
            JsonNode submitBody,
            string cancelHttpMethod)
        {
            if (submitBody is not JsonObject root)
                throw new ArgumentException("fal submit body must be a JSON object.", nameof(submitBody));

            var requestId = RequiredString(root, "request_id");
            var metadata = new Dictionary<string, JsonNode>();
            if (root["queue_position"] is JsonNode queuePosition)
                metadata["queue_position"] = queuePosition.DeepClone();
            if (root["status"] is JsonNode status)
                metadata["status"] = status.DeepClone();

            return new ProviderJobHandle(
                providerJobId: requestId,
                statusUrl: OptionalUri(root, "status_url"),
                responseUrl: OptionalUri(root, "response_url"),
                cancelUrl: OptionalUri(root, "cancel_url"),
                cancelHttpMethod: cancelHttpMethod,
                providerMetadata: metadata);
        }

        public static ProviderStatusOutcome MapStatus(
            ProviderJobHandle handle,
            JsonNode statusBody)
        {
            if (handle is null) throw new ArgumentNullException(nameof(handle));
            if (statusBody is not JsonObject root)
            {
                return new FailedStatusOutcome(new GenerationError(
                    GenerationErrorCode.ExecutionFailed,
                    "fal status body was not a JSON object.",
                    Retryable: false));
            }

            var rawStatus = OptionalString(root, "status");
            if (rawStatus is null
                || !GenerationLifecycleStateNormalizer.TryNormalize(rawStatus, out var state))
            {
                return new FailedStatusOutcome(new GenerationError(
                    GenerationErrorCode.ExecutionFailed,
                    $"Unknown fal lifecycle state '{rawStatus ?? "<missing>"}'.",
                    Retryable: false,
                    ProviderErrorCode: rawStatus));
            }

            if (state == GenerationLifecycleState.Pending
                || state == GenerationLifecycleState.Running)
            {
                var queuePosition = OptionalInt(root, "queue_position");
                return new InFlightStatusOutcome(
                    state,
                    queuePosition is null
                        ? null
                        : new GenerationProgress(QueuePosition: queuePosition));
            }

            if (state == GenerationLifecycleState.Completed)
                return new ProviderCompleteStatusOutcome(handle);

            if (state == GenerationLifecycleState.Canceled)
            {
                return new FailedStatusOutcome(new GenerationError(
                    GenerationErrorCode.Cancelled,
                    "fal job was cancelled.",
                    Retryable: false,
                    ProviderErrorCode: rawStatus));
            }

            return new FailedStatusOutcome(new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                $"fal job failed with state '{rawStatus}'.",
                Retryable: false,
                ProviderErrorCode: rawStatus));
        }

        private static string RequiredString(JsonObject root, string name)
        {
            var value = OptionalString(root, name);
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException($"fal response missing required '{name}'.");
            return value!;
        }

        private static string? OptionalString(JsonObject root, string name)
        {
            var node = root[name];
            return node is null ? null : node.GetValue<string>();
        }

        private static int? OptionalInt(JsonObject root, string name)
        {
            var node = root[name];
            return node is null ? null : node.GetValue<int>();
        }

        private static Uri? OptionalUri(JsonObject root, string name)
        {
            var value = OptionalString(root, name);
            return string.IsNullOrWhiteSpace(value) ? null : new Uri(value!);
        }
    }
}
```

- [ ] **Step 4: Run lifecycle tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalLifecycleMapperTests"
```

Expected: pass.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add src/Rook/Services/Vision/Fal/FalLifecycleMapper.cs `
        src/Rook.Tests/Services/Vision/Fal/FalLifecycleMapperTests.cs
git commit -m "feat(vision): map fal queue lifecycle"
```

---

### Task 6: Add Fal Error Mapping And Pricing Helpers

**Files:**
- Create: `src/Rook/Services/Vision/Fal/FalErrorMapper.cs`
- Create: `src/Rook/Services/Vision/Fal/FalPricingHelpers.cs`
- Create: `src/Rook.Tests/Services/Vision/Fal/FalErrorMapperTests.cs`
- Create: `src/Rook.Tests/Services/Vision/Fal/FalPricingHelpersTests.cs`

- [ ] **Step 1: Write error mapper tests**

Create `src/Rook.Tests/Services/Vision/Fal/FalErrorMapperTests.cs`:

```csharp
using System.Collections.Generic;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalErrorMapperTests
    {
        [Fact]
        public void Maps_401_to_dependency_unavailable_non_retryable()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                401,
                "{\"detail\":\"bad key\"}",
                new Dictionary<string, IReadOnlyList<string>>()));

            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error.Code);
            Assert.False(error.Retryable);
            Assert.Equal("401", error.ProviderErrorCode);
        }

        [Fact]
        public void Maps_422_detail_array_to_invalid_request_with_provider_detail()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                422,
                "{\"detail\":[{\"loc\":[\"body\",\"image\"],\"msg\":\"field required\",\"type\":\"missing\"}]}",
                new Dictionary<string, IReadOnlyList<string>>()));

            Assert.Equal(GenerationErrorCode.InvalidRequest, error.Code);
            Assert.False(error.Retryable);
            Assert.NotNull(error.ProviderDetail);
            Assert.True(error.ProviderDetail!.ContainsKey("detail"));
        }

        [Fact]
        public void Retry_header_controls_retryability()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                503,
                "{\"detail\":\"busy\"}",
                new Dictionary<string, IReadOnlyList<string>>
                {
                    ["x-fal-needs-retry"] = new[] { "true" },
                }));

            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error.Code);
            Assert.True(error.Retryable);
        }
    }
}
```

- [ ] **Step 2: Write pricing helper tests**

Create `src/Rook.Tests/Services/Vision/Fal/FalPricingHelpersTests.cs`:

```csharp
using System.Collections.Generic;
using Rook.Services.Vision.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalPricingHelpersTests
    {
        [Theory]
        [InlineData("x-fal-billable-units")]
        [InlineData("X-Fal-Billable-Units")]
        [InlineData("X-FAL-BILLABLE-UNITS")]
        public void TryGetBillableUnits_is_case_insensitive(string headerName)
        {
            var headers = new Dictionary<string, IReadOnlyList<string>>
            {
                [headerName] = new[] { "2.5" },
            };

            Assert.True(FalPricingHelpers.TryGetBillableUnits(headers, out var units));
            Assert.Equal(2.5m, units);
        }

        [Fact]
        public void TryGetBillableUnits_returns_false_when_missing_or_invalid()
        {
            Assert.False(FalPricingHelpers.TryGetBillableUnits(
                new Dictionary<string, IReadOnlyList<string>>(),
                out _));

            Assert.False(FalPricingHelpers.TryGetBillableUnits(
                new Dictionary<string, IReadOnlyList<string>>
                {
                    ["x-fal-billable-units"] = new[] { "not-a-number" },
                },
                out _));
        }
    }
}
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalErrorMapperTests|FullyQualifiedName~FalPricingHelpersTests"
```

Expected: compile failure because mapper/helper types do not exist.

- [ ] **Step 4: Add fal error mapper**

Create `src/Rook/Services/Vision/Fal/FalErrorMapper.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public static class FalErrorMapper
    {
        public static GenerationError MapHttpFailure(FalHttpResponse response)
        {
            if (response is null) throw new ArgumentNullException(nameof(response));

            var code = response.StatusCode switch
            {
                400 => GenerationErrorCode.InvalidRequest,
                401 => GenerationErrorCode.DependencyUnavailable,
                403 => GenerationErrorCode.DependencyUnavailable,
                422 => GenerationErrorCode.InvalidRequest,
                429 => GenerationErrorCode.QuotaExceeded,
                >= 500 => GenerationErrorCode.DependencyUnavailable,
                _ => GenerationErrorCode.ExecutionFailed,
            };

            var retryable = NeedsRetry(response.Headers)
                || response.StatusCode == 408
                || response.StatusCode == 429
                || response.StatusCode >= 500;

            if (response.StatusCode == 401 || response.StatusCode == 403)
                retryable = false;
            if (response.StatusCode == 400 || response.StatusCode == 422)
                retryable = false;

            var detail = ParseBody(response.Body);
            return new GenerationError(
                code,
                BuildMessage(response.StatusCode, detail, response.Body),
                retryable,
                ProviderErrorCode: response.StatusCode.ToString(),
                ProviderDetail: detail);
        }

        private static bool NeedsRetry(
            IReadOnlyDictionary<string, IReadOnlyList<string>> headers)
        {
            foreach (var kvp in headers)
            {
                if (!string.Equals(kvp.Key, "x-fal-needs-retry",
                        StringComparison.OrdinalIgnoreCase))
                    continue;
                return kvp.Value.Count > 0
                    && string.Equals(kvp.Value[0], "true", StringComparison.OrdinalIgnoreCase);
            }
            return false;
        }

        private static IReadOnlyDictionary<string, JsonNode>? ParseBody(string body)
        {
            if (string.IsNullOrWhiteSpace(body))
                return null;
            try
            {
                var root = JsonNode.Parse(body);
                if (root is not JsonObject obj)
                    return null;
                var dict = new Dictionary<string, JsonNode>();
                foreach (var kvp in obj)
                {
                    if (kvp.Value is not null)
                        dict[kvp.Key] = kvp.Value.DeepClone();
                }
                return dict;
            }
            catch (JsonException)
            {
                return null;
            }
        }

        private static string BuildMessage(
            int statusCode,
            IReadOnlyDictionary<string, JsonNode>? detail,
            string body)
        {
            return $"fal request failed with HTTP {statusCode}.";
        }
    }
}
```

- [ ] **Step 5: Add pricing helper**

Create `src/Rook/Services/Vision/Fal/FalPricingHelpers.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Globalization;

namespace Rook.Services.Vision.Fal
{
    public static class FalPricingHelpers
    {
        public static bool TryGetBillableUnits(
            IReadOnlyDictionary<string, IReadOnlyList<string>> headers,
            out decimal units)
        {
            if (headers is null) throw new ArgumentNullException(nameof(headers));

            foreach (var kvp in headers)
            {
                if (!string.Equals(kvp.Key, "x-fal-billable-units",
                        StringComparison.OrdinalIgnoreCase))
                    continue;

                if (kvp.Value.Count > 0
                    && decimal.TryParse(
                        kvp.Value[0],
                        NumberStyles.Number,
                        CultureInfo.InvariantCulture,
                        out units))
                    return true;
            }

            units = 0m;
            return false;
        }
    }
}
```

- [ ] **Step 6: Run mapper/helper tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FalErrorMapperTests|FullyQualifiedName~FalPricingHelpersTests"
```

Expected: pass.

- [ ] **Step 7: Commit Task 6**

Run:

```powershell
git add src/Rook/Services/Vision/Fal/FalErrorMapper.cs `
        src/Rook/Services/Vision/Fal/FalPricingHelpers.cs `
        src/Rook.Tests/Services/Vision/Fal/FalErrorMapperTests.cs `
        src/Rook.Tests/Services/Vision/Fal/FalPricingHelpersTests.cs
git commit -m "feat(vision): add fal error and pricing helpers"
```

---

### Task 7: Guard PR-6 Scope And Run Full Verification

**Files:**
- Verify only.

- [ ] **Step 1: Confirm no user-visible registration or UI changes**

Run:

```powershell
git diff --name-only main...HEAD
```

Expected files are limited to:

```text
src/Rook/Services/Vision/Generation/**
src/Rook/Services/Vision/Fal/**
src/Rook/Services/Vision/Image/IImageProviderRegistration.cs
src/Rook/Services/Vision/Image/Gemini/GeminiImageProviderRegistration.cs
src/Rook/Services/Vision/Video/IVideoProviderRegistration.cs
src/Rook/Services/Vision/Video/VeoProviderRegistration.cs
src/Rook.Tests/**
docs/superpowers/plans/**
```

If `src/Rook/UI/**`, `src/RookNative/**`, `src/Rook/Handlers/VisionHandler.cs`, or composition-root model registration changed, stop and split that work out of PR-6.

- [ ] **Step 2: Run forbidden-symbol guard**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~SymbolScanGuardTests"
```

Expected: pass.

- [ ] **Step 3: Run focused generation/fal/video registry tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Services.Vision.Generation|FullyQualifiedName~Services.Vision.Fal|FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~DefaultVideoProviderRegistryTests"
```

Expected: pass.

- [ ] **Step 4: Run full managed test suite**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore
```

Expected: pass.

- [ ] **Step 5: Run managed build**

Run:

```powershell
dotnet build src/Rook/Rook.csproj --no-restore -p:RhinoPluginDir=
```

Expected: pass. Existing warnings are acceptable only if they were already present.

- [ ] **Step 6: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 7: Commit verification-only doc update if needed**

If implementation required small comments or doc corrections during verification, commit those separately:

```powershell
git add <exact-files>
git commit -m "docs(vision): clarify fal substrate scope"
```

If no files changed, skip this step.

---

## Self-Review Checklist

- PR-6 does not register fal image or video models.
- PR-6 does not touch `RookSubsystemRoot`, `VisionHandler`, `VisionWebSurface`, or `RookNative`.
- `SecretRequirements` is static provider-level metadata only.
- Optional secrets do not affect provider-level availability.
- `Invalid` credential validation is transient input to the builder, not persisted to `IGenerationSecretStore`.
- Fal lifecycle maps `COMPLETED` to provider-complete, not Rook job complete.
- Fal pricing helper only extracts billable units; per-model rate interpretation is left to PR-7/PR-8 pricing models.
- No Replicate/Tencent provider implementation appears in production code.
- Forbidden 3D symbol scan passes.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-29-fal-substrate-secret-metadata.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
