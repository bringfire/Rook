# PR-13 Hidden Replicate Image Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hidden production Replicate image provider for `black-forest-labs/flux-schnell` and prove it through fake HTTP, injected registries, image jobs, and authenticated materialization.

**Architecture:** Add production provider code under `src/Rook/Services/Vision/Image/Replicate` without adding any default app wiring. Tests explicitly inject `ReplicateImageProviderRegistration` into `DefaultImageProviderRegistry` and use `ImageJobManager` with fake Replicate API and fake output-fetch HTTP. The existing Replicate substrate remains responsible for API calls, endpoint validation, lifecycle/error mapping, and authenticated output request construction.

**Tech Stack:** C# multi-targeted `net7.0;net48`, `System.Text.Json.Nodes`, `HttpClient`, existing `Rook.Services.Vision.Generation` provider seams, existing `ImageJobManager`, xUnit.

---

## Scope Guard

Do:

- Add production code under `src/Rook/Services/Vision/Image/Replicate`.
- Add one hidden model: `black-forest-labs/flux-schnell`.
- Keep `ReplicateImageOptions` empty.
- Validate text-to-image only.
- Use the existing official-model Replicate endpoint.
- Mark Replicate output artifacts with `requires_authenticated_fetch: true`.
- Add a production request-factory selector that injects the Replicate token only for Replicate remote artifacts.
- Test through fake HTTP only.

Do not:

- Modify `VisionProviderRegistrations.CreateImageRegistrations`.
- Add Replicate credential metadata.
- Add Settings, picker, UI resource, native route, MCP, or `NativeGhBridgeRegistrar` exposure.
- Add image-to-image support.
- Add live Replicate tests.
- Add generic model-agnostic create-prediction endpoint support.

## File Structure

Create:

- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
  Hidden model id, provider name, and one `ImageCapability`.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptions.cs`
  Empty external options record.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs`
  Empty-options serialization, validation, and deserialize contract.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImagePricingModel.cs`
  Thin image pricing model that delegates actual spend extraction to `ReplicatePredictionPricing`.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
  Hidden provider registration. It is not used by default composition.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
  Async image provider implementation using `ReplicateApiClient`.
- `src/Rook/Services/Vision/Image/Replicate/ReplicateImageArtifactRequestFactorySelector.cs`
  Authenticated output request selector for `ImageJobManager`.
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`
- `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageJobManagerTests.cs`

Modify:

- `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`
  Strengthen source-level boundary assertions so default composition does not reference Replicate image provider classes.

Do not modify:

- `src/Rook/Services/Vision/VisionProviderRegistrations.cs`
- `src/Rook/RookSubsystemRoot.cs`
- `src/Rook/UI/Vision/**`
- `src/RookNative/**`
- `mcp_server/**`

---

## Task 1: Hidden Capability, Options, Registration, And Pricing

**Files:**
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptions.cs`
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs`
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImagePricingModel.cs`
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs`

- [ ] **Step 1: Add failing registration tests**

Create `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderRegistrationTests.cs`:

```csharp
using System.Linq;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
using Rook.Tests.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateImageProviderRegistrationTests
    {
        [Fact]
        public void Registration_exposes_only_flux_schnell_model()
        {
            var registration = new ReplicateImageProviderRegistration(
                new FakeImageProvider());

            Assert.Equal("replicate", registration.ProviderName);
            var model = Assert.Single(registration.Models);
            Assert.Equal("black-forest-labs/flux-schnell", model.Key);
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, model.Value.Capability.Id);
            Assert.Equal("FLUX.1 Schnell", model.Value.Capability.Name);
            Assert.Equal("available", model.Value.Capability.Status);
            Assert.Equal(new[] { "1K" }, model.Value.Capability.Resolutions);
            Assert.Equal(new[] { "1:1", "4:3", "3:4", "16:9", "9:16" }, model.Value.Capability.AspectRatios);
            Assert.Equal(0, model.Value.Capability.MaxReferenceImages);
            Assert.True(model.Value.Capability.SupportsTextToImage);
            Assert.False(model.Value.Capability.SupportsImageToImage);
            Assert.IsType<ReplicateImagePricingModel>(model.Value.PricingModel);
        }

        [Fact]
        public void Registration_declares_replicate_api_token_requirement()
        {
            var registration = new ReplicateImageProviderRegistration(
                new FakeImageProvider());

            var requirement = Assert.Single(registration.SecretRequirements);
            Assert.Equal(GenerationSecretKeys.ReplicateApiToken, requirement.Key);
            Assert.Equal("Replicate API token", requirement.DisplayName);
            Assert.True(requirement.IsRequired);
            Assert.True(requirement.IsSensitive);
        }

        [Fact]
        public void Injected_registry_resolves_only_replicate_flux_schnell()
        {
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new ReplicateImageProviderRegistration(new FakeImageProvider()),
            });

            Assert.True(registry.TryResolve(ReplicateImageCapabilities.FluxSchnell, out var resolved));
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, resolved.ModelId);
            Assert.Equal("replicate", resolved.ProviderName);
            Assert.False(registry.TryResolve("replicate/other-model", out _));

            var all = registry.EnumerateAllModels().ToArray();
            var descriptor = Assert.Single(all);
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, descriptor.ModelId);
            Assert.Equal("replicate", descriptor.ProviderName);
        }
    }
}
```

- [ ] **Step 2: Add failing options codec tests**

Create `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageOptionsCodecTests.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateImageOptionsCodecTests
    {
        private readonly ReplicateImageOptionsCodec _codec = new();
        private readonly ImageCapability _cap = ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell];

        [Fact]
        public void Validate_accepts_default_text_to_image_request()
        {
            var result = _codec.Validate(Request(), new ReplicateImageOptions(), _cap);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_reference_images_before_submit()
        {
            var result = _codec.Validate(
                Request(referenceImages: new[]
                {
                    MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage),
                }),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("reference_image_paths", result.Field);
            Assert.Contains("not supported", result.Message);
        }

        [Fact]
        public void Validate_rejects_number_of_images_other_than_one()
        {
            var result = _codec.Validate(
                Request(numberOfImages: 2),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("number_of_images", result.Field);
        }

        [Theory]
        [InlineData("1:1")]
        [InlineData("4:3")]
        [InlineData("3:4")]
        [InlineData("16:9")]
        [InlineData("9:16")]
        [InlineData("")]
        public void Validate_accepts_supported_aspect_ratios_and_blank_default(string aspectRatio)
        {
            var result = _codec.Validate(
                Request(aspectRatio: aspectRatio),
                new ReplicateImageOptions(),
                _cap);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_unsupported_aspect_ratio()
        {
            var result = _codec.Validate(
                Request(aspectRatio: "21:9"),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("aspect_ratio", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_resolution()
        {
            var result = _codec.Validate(
                Request(resolution: "2K"),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("resolution", result.Field);
        }

        [Fact]
        public void Serialize_returns_empty_object()
        {
            var json = _codec.Serialize(new ReplicateImageOptions());

            Assert.Empty(json);
        }

        [Fact]
        public void Deserialize_accepts_empty_object()
        {
            var result = _codec.Deserialize(new JsonObject());

            Assert.True(result.Success);
            Assert.IsType<ReplicateImageOptions>(result.Options);
        }

        [Fact]
        public void Deserialize_rejects_provider_specific_fields()
        {
            var result = _codec.Deserialize(new JsonObject
            {
                ["seed"] = JsonValue.Create(123),
            });

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal("options", result.Error.Field);
        }

        private static ImageGenerationRequest Request(
            string resolution = "1K",
            string aspectRatio = "1:1",
            int numberOfImages = 1,
            System.Collections.Generic.IReadOnlyList<MediaRef>? referenceImages = null) =>
            new(
                Model: ReplicateImageCapabilities.FluxSchnell,
                Prompt: "sunlit massing study",
                Resolution: resolution,
                AspectRatio: aspectRatio,
                NumberOfImages: numberOfImages,
                ReferenceImages: referenceImages,
                Options: new ReplicateImageOptions());
    }
}
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderRegistrationTests|ReplicateImageOptionsCodecTests"
```

Expected: compile failure because `Rook.Services.Vision.Image.Replicate` types do not exist.

- [ ] **Step 4: Add capability and options files**

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImageCapabilities.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Replicate
{
    public static class ReplicateImageCapabilities
    {
        public const string ProviderName = "replicate";
        public const string FluxSchnell = "black-forest-labs/flux-schnell";
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

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptions.cs`:

```csharp
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed record ReplicateImageOptions : ProviderOptions;
}
```

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImageOptionsCodec.cs`:

```csharp
using System;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImageOptionsCodec
        : IProviderOptionsCodec<ImageGenerationRequest, ImageCapability>
    {
        public ValidationResult Validate(
            ImageGenerationRequest request,
            ProviderOptions options,
            ImageCapability capability)
        {
            if (request is null)
                return ValidationResult.Fail("Request is null.", "request");
            if (capability is null)
                return ValidationResult.Fail("Capability is null.", "capability");
            if (options is not ReplicateImageOptions)
                return ValidationResult.Fail(
                    $"Replicate image provider requires {nameof(ReplicateImageOptions)}; got " +
                    $"{options?.GetType().Name ?? "null"}.",
                    "options");
            if (request.NumberOfImages != 1)
                return ValidationResult.Fail(
                    "number_of_images must be 1 for Replicate image generation.",
                    "number_of_images");

            var resolution = string.IsNullOrWhiteSpace(request.Resolution)
                ? "1K"
                : request.Resolution.ToUpperInvariant();
            if (!capability.Resolutions.Contains(resolution, StringComparer.Ordinal))
            {
                return ValidationResult.Fail(
                    $"resolution must be one of: {string.Join(", ", capability.Resolutions)} " +
                    $"for model '{capability.Id}'.",
                    "resolution");
            }

            var refCount = request.ReferenceImages?.Count ?? 0;
            if (refCount > 0)
            {
                return ValidationResult.Fail(
                    "reference_image_paths are not supported for Replicate FLUX Schnell.",
                    "reference_image_paths");
            }

            if (!string.IsNullOrWhiteSpace(request.AspectRatio)
                && !capability.AspectRatios.Contains(request.AspectRatio, StringComparer.Ordinal))
            {
                return ValidationResult.Fail(
                    "aspect_ratio must be one of: " +
                    string.Join(", ", capability.AspectRatios) + ".",
                    "aspect_ratio");
            }

            return ValidationResult.Ok();
        }

        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not ReplicateImageOptions)
                throw new ArgumentException(
                    $"Expected {nameof(ReplicateImageOptions)}.", nameof(options));
            return new JsonObject();
        }

        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            if (json is null)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Replicate image options JSON is null.",
                    Retryable: false,
                    Field: "options"));

            if (json.Count != 0)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Replicate image options do not accept provider-specific fields.",
                    Retryable: false,
                    Field: "options"));

            return ProviderOptionsDecodeResult.Ok(new ReplicateImageOptions());
        }
    }
}
```

- [ ] **Step 5: Add pricing and registration files**

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImagePricingModel.cs`:

```csharp
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImagePricingModel
        : IPricingModel<ImageGenerationRequest, ImageCapability>
    {
        public const string Source = "replicate-flux-schnell-predict-time-2026-05-01";
        public const string Provenance = "replicate-prediction-metrics-2026-05-01";

        public string PricingSource => Source;
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseBody;

        public PricingResult Estimate(ImageGenerationRequest request, ImageCapability capability)
        {
            return PricingResult.Ok(
                new JobPricing(
                    Currency: "USD",
                    UnitPrice: null,
                    Unit: "compute_second",
                    Quantity: null,
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
            JsonNode? responseBody)
        {
            return responseBody is null
                ? null
                : ReplicatePredictionPricing.ExtractActualSpend(responseBody, Source);
        }
    }
}
```

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProviderRegistration.cs`:

```csharp
using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImageProviderRegistration : IImageProviderRegistration
    {
        public ReplicateImageProviderRegistration(IImageProvider provider)
        {
            Provider = provider ?? throw new ArgumentNullException(nameof(provider));
        }

        public string ProviderName => ReplicateImageCapabilities.ProviderName;
        public IImageProvider Provider { get; }
        public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
            = new ReplicateImageOptionsCodec();

        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

        private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
            Array.AsReadOnly(new[]
            {
                new ProviderSecretRequirement(
                    GenerationSecretKeys.ReplicateApiToken,
                    "Replicate API token",
                    isRequired: true),
            });

        public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models
            => _models;

        private static readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models =
            new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal)
            {
                [ReplicateImageCapabilities.FluxSchnell] = (
                    ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell],
                    new ReplicateImagePricingModel()),
            };
    }
}
```

- [ ] **Step 6: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageProviderRegistrationTests|ReplicateImageOptionsCodecTests"
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Replicate `
        src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageProviderRegistrationTests.cs `
        src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageOptionsCodecTests.cs
git commit -m "feat(vision): add hidden Replicate image registration"
```

---

## Task 2: Submit, Status, And Cancel Provider Path

**Files:**
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`

- [ ] **Step 1: Add failing provider submit/status/cancel tests**

Create `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs` with these tests and helpers:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Replicate;
using Rook.Services.Vision.Replicate;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateImageProviderTests
    {
        [Fact]
        public async Task SubmitAsync_missing_token_returns_dependency_failure_without_http_call()
        {
            var (provider, handler) = MakeProvider(_ => Json(HttpStatusCode.OK, "{}"), apiToken: " ");

            var outcome = await provider.SubmitAsync(Request(), ResolvedMedia(), CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("Replicate API token is not configured", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_wrong_options_type_returns_invalid_request_without_http_call()
        {
            var (provider, handler) = MakeProvider(_ => Json(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                Request() with { Options = new GeminiImageOptions() },
                ResolvedMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("options", failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_reference_images_fail_before_http_call()
        {
            var (provider, handler) = MakeProvider(_ => Json(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                Request(referenceImages: new[]
                {
                    MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage),
                }),
                ResolvedMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("reference_image_paths", failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_wrong_model_fails_before_http_call()
        {
            var (provider, handler) = MakeProvider(_ => Json(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                Request() with { Model = "replicate/other-model" },
                ResolvedMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("model", failed.Error.Field);
            Assert.Contains("Unknown Replicate image model", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_posts_official_model_endpoint_and_exact_body()
        {
            string? body = null;
            var (provider, handler) = MakeProvider(req =>
            {
                body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                return Json(HttpStatusCode.Created, Prediction("pred-1", "starting"));
            });

            var outcome = await provider.SubmitAsync(
                Request(aspectRatio: ""),
                ResolvedMedia(),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                request.RequestUri!.ToString());
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8-test-token", request.Headers.Authorization.Parameter);

            var json = JsonNode.Parse(body!)!.AsObject();
            Assert.Equal(new[] { "input" }, json.Select(kvp => kvp.Key).ToArray());
            var input = json["input"]!.AsObject();
            Assert.Equal(
                new[] { "prompt", "aspect_ratio", "num_outputs", "output_format" },
                input.Select(kvp => kvp.Key).ToArray());
            Assert.Equal("sunlit massing study", input["prompt"]!.GetValue<string>());
            Assert.Equal("1:1", input["aspect_ratio"]!.GetValue<string>());
            Assert.Equal(1, input["num_outputs"]!.GetValue<int>());
            Assert.Equal("png", input["output_format"]!.GetValue<string>());
            Assert.DoesNotContain("resolution", body!);
            Assert.DoesNotContain("reference", body!);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-1", queued.Handle.ProviderJobId);
            Assert.Equal("POST", queued.Handle.CancelHttpMethod);
            Assert.Null(queued.Handle.ResponseUrl);
        }

        [Theory]
        [InlineData("starting", GenerationLifecycleState.Pending)]
        [InlineData("processing", GenerationLifecycleState.Running)]
        public async Task GetStatusAsync_maps_inflight_states_through_replicate_lifecycle_mapper(
            string providerStatus,
            GenerationLifecycleState expectedState)
        {
            var (provider, _) = MakeProvider(req =>
                req.Method == HttpMethod.Get
                    ? Json(HttpStatusCode.OK, Prediction("pred-1", providerStatus))
                    : Json(HttpStatusCode.Created, Prediction("pred-1", "starting")));
            var submit = Assert.IsType<QueuedSubmitOutcome>(
                await provider.SubmitAsync(Request(), ResolvedMedia(), CancellationToken.None));

            var status = await provider.GetStatusAsync(submit.Handle, CancellationToken.None);

            var inFlight = Assert.IsType<InFlightStatusOutcome>(status);
            Assert.Equal(expectedState, inFlight.State);
        }

        [Fact]
        public async Task GetStatusAsync_maps_succeeded_through_replicate_lifecycle_mapper()
        {
            var (provider, handler) = MakeProvider(req =>
                req.Method == HttpMethod.Get
                    ? Json(HttpStatusCode.OK, Prediction(
                        "pred-1",
                        "succeeded",
                        outputJson: "\"https://replicate.delivery/pbxt/out.png\""))
                    : Json(HttpStatusCode.Created, Prediction("pred-1", "starting")));
            var submit = Assert.IsType<QueuedSubmitOutcome>(
                await provider.SubmitAsync(Request(), ResolvedMedia(), CancellationToken.None));

            var status = await provider.GetStatusAsync(submit.Handle, CancellationToken.None);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(status);
            Assert.Equal("https://replicate.delivery/pbxt/out.png", complete.UpdatedHandle.ProviderResultToken);
            Assert.Contains(handler.Requests, r =>
                r.Method == HttpMethod.Get &&
                r.RequestUri!.ToString() == "https://api.replicate.com/v1/predictions/pred-1");
        }

        [Fact]
        public async Task GetStatusAsync_maps_failed_prediction_to_failed_status()
        {
            var (provider, _) = MakeProvider(req =>
                req.Method == HttpMethod.Get
                    ? Json(HttpStatusCode.OK, Prediction(
                        "pred-1",
                        "failed",
                        outputJson: "null",
                        extraFields: @"""error"": ""model execution failed"""))
                    : Json(HttpStatusCode.Created, Prediction("pred-1", "starting")));
            var submit = Assert.IsType<QueuedSubmitOutcome>(
                await provider.SubmitAsync(Request(), ResolvedMedia(), CancellationToken.None));

            var status = await provider.GetStatusAsync(submit.Handle, CancellationToken.None);

            var failed = Assert.IsType<FailedStatusOutcome>(status);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("failed", failed.Error.ProviderErrorCode);
        }

        [Fact]
        public async Task GetStatusAsync_maps_canceled_prediction_to_cancelled_status()
        {
            var (provider, _) = MakeProvider(req =>
                req.Method == HttpMethod.Get
                    ? Json(HttpStatusCode.OK, Prediction(
                        "pred-1",
                        "canceled",
                        outputJson: "null",
                        extraFields: @"""error"": ""user canceled"""))
                    : Json(HttpStatusCode.Created, Prediction("pred-1", "starting")));
            var submit = Assert.IsType<QueuedSubmitOutcome>(
                await provider.SubmitAsync(Request(), ResolvedMedia(), CancellationToken.None));

            var status = await provider.GetStatusAsync(submit.Handle, CancellationToken.None);

            var failed = Assert.IsType<FailedStatusOutcome>(status);
            Assert.Equal(GenerationErrorCode.Cancelled, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("canceled", failed.Error.ProviderErrorCode);
        }

        [Fact]
        public async Task GetStatusAsync_non_success_maps_http_failure()
        {
            var (provider, _) = MakeProvider(req =>
                req.Method == HttpMethod.Get
                    ? Json((HttpStatusCode)429, @"{ ""detail"": ""quota"" }")
                    : Json(HttpStatusCode.Created, Prediction("pred-1", "starting")));
            var submit = Assert.IsType<QueuedSubmitOutcome>(
                await provider.SubmitAsync(Request(), ResolvedMedia(), CancellationToken.None));

            var status = await provider.GetStatusAsync(submit.Handle, CancellationToken.None);

            var failed = Assert.IsType<FailedStatusOutcome>(status);
            Assert.Equal(GenerationErrorCode.QuotaExceeded, failed.Error.Code);
            Assert.Equal("429", failed.Error.ProviderErrorCode);
        }

        [Fact]
        public async Task CancelAsync_posts_replicate_cancel_endpoint()
        {
            var (provider, handler) = MakeProvider(req =>
                req.RequestUri!.AbsolutePath.EndsWith("/cancel", StringComparison.Ordinal)
                    ? Json(HttpStatusCode.OK, Prediction("pred-1", "canceled"))
                    : Json(HttpStatusCode.Created, Prediction("pred-1", "starting")));
            var submit = Assert.IsType<QueuedSubmitOutcome>(
                await provider.SubmitAsync(Request(), ResolvedMedia(), CancellationToken.None));

            var cancel = await provider.CancelAsync(submit.Handle, CancellationToken.None);

            Assert.IsType<CanceledOutcome>(cancel);
            Assert.Contains(handler.Requests, r =>
                r.Method == HttpMethod.Post &&
                r.RequestUri!.ToString() == "https://api.replicate.com/v1/predictions/pred-1/cancel");
        }

        private static ImageGenerationRequest Request(
            string aspectRatio = "16:9",
            IReadOnlyList<MediaRef>? referenceImages = null) =>
            new(
                Model: ReplicateImageCapabilities.FluxSchnell,
                Prompt: "sunlit massing study",
                Resolution: "1K",
                AspectRatio: aspectRatio,
                NumberOfImages: 1,
                ReferenceImages: referenceImages,
                Options: new ReplicateImageOptions());

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> ResolvedMedia()
        {
            var input = MediaRef.ForPath("C:/tmp/current.png", ImageMediaRoles.InputImage);
            return new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = new ResolvedMedia(new byte[] { 1, 2, 3 }, "image/png"),
            };
        }

        private static (ReplicateImageProvider provider, TestHttpMessageHandler handler) MakeProvider(
            Func<HttpRequestMessage, HttpResponseMessage> onSend,
            string? apiToken = "r8-test-token")
        {
            var handler = new TestHttpMessageHandler { OnSend = onSend };
            var client = new ReplicateApiClient(new HttpClient(handler));
            return (new ReplicateImageProvider(() => apiToken, client), handler);
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string json) =>
            new(status)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };

        private static string Prediction(
            string id,
            string status,
            string outputJson = "null",
            string? extraFields = null) =>
            $$"""
            {
              "id": "{{id}}",
              "status": "{{status}}",
              "output": {{outputJson}},
              "model": "black-forest-labs/flux-schnell",
              "version": "hidden-version",
              "metrics": { "predict_time": 1.25, "total_time": 2.5 },
              "urls": {
                "get": "https://api.replicate.com/v1/predictions/{{id}}",
                "cancel": "https://api.replicate.com/v1/predictions/{{id}}/cancel"
              }{{(extraFields is null ? "" : ",")}}
              {{extraFields ?? ""}}
            }
            """;
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateImageProviderTests
```

Expected: compile failure because `ReplicateImageProvider` does not exist.

- [ ] **Step 3: Add submit/status/cancel implementation**

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs` with the submit, status, cancel, and request-building code below. `FetchResultAsync` deliberately returns a typed failure until Task 3 adds profile extraction.

```csharp
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImageProvider : IImageProvider
    {
        private static readonly ReplicatePredictionEndpoint FluxSchnellEndpoint =
            ReplicatePredictionEndpoint.OfficialModel(
                "black-forest-labs",
                "flux-schnell");

        private readonly Func<string?> _apiTokenProvider;
        private readonly ReplicateApiClient _client;
        private readonly ReplicateImageOptionsCodec _codec = new();

        public ReplicateImageProvider(
            Func<string?> apiTokenProvider,
            ReplicateApiClient? client = null)
        {
            _apiTokenProvider = apiTokenProvider
                ?? throw new ArgumentNullException(nameof(apiTokenProvider));
            _client = client ?? new ReplicateApiClient();
        }

        public string ProviderName => ReplicateImageCapabilities.ProviderName;

        public async Task<ProviderSubmitOutcome> SubmitAsync(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            var validation = ValidateRequest(request);
            if (validation is not null)
                return new FailedSubmitOutcome(validation);

            var apiToken = _apiTokenProvider();
            if (string.IsNullOrWhiteSpace(apiToken))
                return new FailedSubmitOutcome(ReplicateErrorMapper.MissingToken());

            ReplicateHttpResponse response;
            try
            {
                response = await _client.CreatePredictionAsync(
                        apiToken!,
                        FluxSchnellEndpoint,
                        BuildCreateBodyJson(request),
                        ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return new FailedSubmitOutcome(Interrupted());
            }
            catch (TaskCanceledException)
            {
                return new FailedSubmitOutcome(DependencyRetryable(
                    "Replicate image request timed out. Try again."));
            }
            catch (HttpRequestException)
            {
                return new FailedSubmitOutcome(DependencyRetryable(
                    "Replicate image request failed due to a transport error."));
            }
            catch (ArgumentException ex)
            {
                return new FailedSubmitOutcome(InvalidRequest(ex.Message, "request"));
            }

            if (!response.IsSuccessStatusCode)
                return new FailedSubmitOutcome(ReplicateErrorMapper.MapHttpFailure(response));

            try
            {
                var body = ParseObject(response.Body, "Replicate submit response");
                return new QueuedSubmitOutcome(
                    ReplicateLifecycleMapper.ParseSubmitHandle(body));
            }
            catch (ArgumentException ex)
            {
                return new FailedSubmitOutcome(ExecutionFailed(ex.Message));
            }
            catch (JsonException ex)
            {
                return new FailedSubmitOutcome(ExecutionFailed(
                    $"Replicate submit response was not valid JSON: {ex.Message}"));
            }
        }

        public async Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return new FailedStatusOutcome(InvalidRequest("Provider handle is null.", "handle"));

            var apiToken = _apiTokenProvider();
            if (string.IsNullOrWhiteSpace(apiToken))
                return new FailedStatusOutcome(ReplicateErrorMapper.MissingToken());

            ReplicateHttpResponse response;
            try
            {
                response = await _client.GetPredictionAsync(
                        apiToken!,
                        handle.ProviderJobId,
                        ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return new FailedStatusOutcome(Interrupted());
            }
            catch (TaskCanceledException)
            {
                return new FailedStatusOutcome(DependencyRetryable(
                    "Replicate status request timed out. Try again."));
            }
            catch (HttpRequestException)
            {
                return new FailedStatusOutcome(DependencyRetryable(
                    "Replicate status request failed due to a transport error."));
            }
            catch (ArgumentException ex)
            {
                return new FailedStatusOutcome(InvalidRequest(ex.Message, "handle"));
            }

            if (!response.IsSuccessStatusCode)
                return new FailedStatusOutcome(ReplicateErrorMapper.MapHttpFailure(response));

            try
            {
                return ReplicateLifecycleMapper.MapStatus(
                    handle,
                    ParseObject(response.Body, "Replicate status response"));
            }
            catch (ArgumentException ex)
            {
                return new FailedStatusOutcome(ExecutionFailed(ex.Message));
            }
            catch (JsonException ex)
            {
                return new FailedStatusOutcome(ExecutionFailed(
                    $"Replicate status response was not valid JSON: {ex.Message}"));
            }
        }

        public async Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return new FailedCancelOutcome(InvalidRequest("Provider handle is null.", "handle"));

            var apiToken = _apiTokenProvider();
            if (string.IsNullOrWhiteSpace(apiToken))
                return new FailedCancelOutcome(ReplicateErrorMapper.MissingToken());

            ReplicateHttpResponse response;
            try
            {
                response = await _client.CancelPredictionAsync(
                        apiToken!,
                        handle.ProviderJobId,
                        ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return new FailedCancelOutcome(Interrupted());
            }
            catch (TaskCanceledException)
            {
                return new FailedCancelOutcome(DependencyRetryable(
                    "Replicate cancel request timed out. Try again."));
            }
            catch (HttpRequestException)
            {
                return new FailedCancelOutcome(DependencyRetryable(
                    "Replicate cancel request failed due to a transport error."));
            }
            catch (ArgumentException ex)
            {
                return new FailedCancelOutcome(InvalidRequest(ex.Message, "handle"));
            }

            return response.IsSuccessStatusCode
                ? new CanceledOutcome()
                : new FailedCancelOutcome(ReplicateErrorMapper.MapHttpFailure(response));
        }

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct) =>
            Task.FromResult<ProviderResultOutcome>(
                new FailedResultOutcome(ExecutionFailed(
                    "Replicate image result extraction is not implemented.")));

        internal static string BuildCreateBodyJson(ImageGenerationRequest request)
        {
            var body = new JsonObject
            {
                ["input"] = new JsonObject
                {
                    ["prompt"] = request.Prompt,
                    ["aspect_ratio"] = NormalizeAspectRatio(request.AspectRatio),
                    ["num_outputs"] = 1,
                    ["output_format"] = "png",
                },
            };
            return body.ToJsonString();
        }

        private GenerationError? ValidateRequest(ImageGenerationRequest request)
        {
            if (request is null)
                return InvalidRequest("Request is null.", "request");
            if (!string.Equals(
                    request.Model,
                    ReplicateImageCapabilities.FluxSchnell,
                    StringComparison.Ordinal))
            {
                return InvalidRequest(
                    $"Unknown Replicate image model: '{request.Model ?? "<null>"}'.",
                    "model");
            }

            var capability = ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell];
            var result = _codec.Validate(request, request.Options, capability);
            return result.Success
                ? null
                : InvalidRequest(result.Message ?? "Replicate image request is invalid.", result.Field);
        }

        private static string NormalizeAspectRatio(string? aspectRatio) =>
            string.IsNullOrWhiteSpace(aspectRatio) ? "1:1" : aspectRatio!;

        private static JsonObject ParseObject(string body, string label)
        {
            if (JsonNode.Parse(body) is not JsonObject root)
                throw new ArgumentException($"{label} body must be a JSON object.");
            return root;
        }

        private static GenerationError InvalidRequest(string message, string? field) =>
            new(GenerationErrorCode.InvalidRequest, message, Retryable: false, Field: field);

        private static GenerationError ExecutionFailed(string message) =>
            new(GenerationErrorCode.ExecutionFailed, message, Retryable: false);

        private static GenerationError DependencyRetryable(string message) =>
            new(GenerationErrorCode.DependencyUnavailable, message, Retryable: true);

        private static GenerationError Interrupted() =>
            new(GenerationErrorCode.Interrupted, "Request cancelled.", Retryable: false);
    }
}
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateImageProviderTests
```

Expected: PASS for submit/status/cancel tests. Fetch-result tests are added in Task 3.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Replicate\ReplicateImageProvider.cs `
        src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageProviderTests.cs
git commit -m "feat(vision): add Replicate image prediction provider"
```

---

## Task 3: FLUX-Schnell Terminal Output Extraction

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageProvider.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageProviderTests.cs`

- [ ] **Step 1: Add failing fetch-result tests**

Append these tests to `ReplicateImageProviderTests`:

```csharp
[Theory]
[InlineData("\"https://replicate.delivery/pbxt/out.png\"")]
[InlineData("[\"https://replicate.delivery/pbxt/out.png\"]")]
public async Task FetchResultAsync_accepts_single_url_output_shapes(string outputJson)
{
    var (provider, _) = MakeProvider(_ => Json(HttpStatusCode.OK, "{}"));
    var handle = TerminalHandle(outputJson);

    var result = await provider.FetchResultAsync(handle, CancellationToken.None);

    var success = Assert.IsType<SuccessResultOutcome>(result);
    var artifact = Assert.Single(success.Envelope.Artifacts);
    Assert.Equal(ImageMediaRoles.Image, artifact.Role);
    Assert.Null(artifact.DeclaredMimeType);
    var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
    Assert.Equal("https://replicate.delivery/pbxt/out.png", remote.Url.ToString());
    Assert.True(artifact.ProviderMetadata["requires_authenticated_fetch"]!.GetValue<bool>());
    Assert.Equal("https://replicate.delivery/pbxt/out.png", artifact.ProviderMetadata["url"]!.GetValue<string>());
    Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("output"));
    Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("metrics"));
    Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("model"));
    Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("version"));
    Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("urls"));
}

[Theory]
[InlineData("[]")]
[InlineData("[\"https://replicate.delivery/pbxt/a.png\", \"https://replicate.delivery/pbxt/b.png\"]")]
[InlineData("{\"image\":\"https://replicate.delivery/pbxt/out.png\"}")]
[InlineData("null")]
[InlineData("42")]
[InlineData("\"not-a-url\"")]
public async Task FetchResultAsync_rejects_unsupported_output_shapes(string outputJson)
{
    var (provider, _) = MakeProvider(_ => Json(HttpStatusCode.OK, "{}"));
    var handle = TerminalHandle(outputJson);

    var result = await provider.FetchResultAsync(handle, CancellationToken.None);

    var failed = Assert.IsType<FailedResultOutcome>(result);
    Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
    Assert.False(failed.Error.Retryable);
    Assert.Contains("exactly one image URL", failed.Error.Message);
}

[Fact]
public async Task FetchResultAsync_missing_output_metadata_returns_execution_failed()
{
    var (provider, _) = MakeProvider(_ => Json(HttpStatusCode.OK, "{}"));
    var handle = new ProviderJobHandle(
        "pred-1",
        providerResultToken: null,
        providerMetadata: new Dictionary<string, JsonNode>
        {
            ["metrics"] = JsonNode.Parse(@"{ ""predict_time"": 1.25 }")!,
        });

    var result = await provider.FetchResultAsync(handle, CancellationToken.None);

    var failed = Assert.IsType<FailedResultOutcome>(result);
    Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
}

private static ProviderJobHandle TerminalHandle(string outputJson)
{
    var metadata = new Dictionary<string, JsonNode>
    {
        ["output"] = JsonNode.Parse(outputJson)!,
        ["metrics"] = JsonNode.Parse(@"{ ""predict_time"": 1.25, ""total_time"": 2.5 }")!,
        ["model"] = JsonValue.Create("black-forest-labs/flux-schnell")!,
        ["version"] = JsonValue.Create("hidden-version")!,
        ["urls"] = JsonNode.Parse(@"{ ""get"": ""https://api.replicate.com/v1/predictions/pred-1"", ""cancel"": ""https://api.replicate.com/v1/predictions/pred-1/cancel"" }")!,
    };

    var token = outputJson == "\"https://replicate.delivery/pbxt/out.png\""
        || outputJson == "[\"https://replicate.delivery/pbxt/out.png\"]"
            ? "https://replicate.delivery/pbxt/out.png"
            : null;

    return new ProviderJobHandle(
        "pred-1",
        providerResultToken: token,
        providerMetadata: metadata);
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FetchResultAsync_accepts_single_url_output_shapes|FetchResultAsync_rejects_unsupported_output_shapes|FetchResultAsync_missing_output_metadata_returns_execution_failed"
```

Expected: FAIL because `FetchResultAsync` still returns the Task 2 stub failure.

- [ ] **Step 3: Replace `FetchResultAsync` with output extraction**

Replace the stub `FetchResultAsync` in `ReplicateImageProvider.cs` with:

```csharp
public Task<ProviderResultOutcome> FetchResultAsync(
    ProviderJobHandle handle,
    CancellationToken ct)
{
    if (handle is null)
    {
        return Task.FromResult<ProviderResultOutcome>(
            new FailedResultOutcome(InvalidRequest(
                "Provider handle is null.",
                "handle")));
    }

    if (!TrySelectMaterializableOutputUrl(handle, out var outputUrl))
    {
        return Task.FromResult<ProviderResultOutcome>(
            new FailedResultOutcome(ExecutionFailed(
                "Replicate FLUX Schnell output did not contain exactly one image URL.")));
    }

    var artifactMetadata = new Dictionary<string, JsonNode>
    {
        ["url"] = JsonValue.Create(outputUrl.ToString())!,
        ["requires_authenticated_fetch"] = JsonValue.Create(true)!,
    };

    var artifact = new ResultArtifact(
        Role: ImageMediaRoles.Image,
        Body: new RemoteArtifactBody(outputUrl),
        DeclaredMimeType: null,
        ProviderMetadata: artifactMetadata);

    return Task.FromResult<ProviderResultOutcome>(
        new SuccessResultOutcome(
            new ProviderResultEnvelope(
                new[] { artifact },
                CopyMetadata(handle.ProviderMetadata))));
}
```

Add these helpers inside `ReplicateImageProvider`:

```csharp
private static bool TrySelectMaterializableOutputUrl(
    ProviderJobHandle handle,
    out Uri outputUrl)
{
    outputUrl = null!;
    if (string.IsNullOrWhiteSpace(handle.ProviderResultToken))
        return false;
    if (!Uri.TryCreate(handle.ProviderResultToken, UriKind.Absolute, out var uri))
        return false;
    if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
        return false;
    outputUrl = uri;
    return true;
}

private static IReadOnlyDictionary<string, JsonNode> CopyMetadata(
    IReadOnlyDictionary<string, JsonNode>? metadata)
{
    var copy = new Dictionary<string, JsonNode>();
    if (metadata is null)
        return copy;

    foreach (var kvp in metadata)
        copy[kvp.Key] = kvp.Value.DeepClone();
    return copy;
}
```

- [ ] **Step 4: Run fetch-result tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FetchResultAsync_accepts_single_url_output_shapes|FetchResultAsync_rejects_unsupported_output_shapes|FetchResultAsync_missing_output_metadata_returns_execution_failed"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Replicate\ReplicateImageProvider.cs `
        src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageProviderTests.cs
git commit -m "feat(vision): extract Replicate image outputs"
```

---

## Task 4: Replicate Authenticated Output Selector And Image Job Integration

**Files:**
- Create: `src/Rook/Services/Vision/Image/Replicate/ReplicateImageArtifactRequestFactorySelector.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageJobManagerTests.cs`

- [ ] **Step 1: Add failing image job integration tests**

Create `src/Rook.Tests/Services/Vision/Image/Replicate/ReplicateImageJobManagerTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Image.Replicate;
using Rook.Services.Vision.Replicate;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateImageJobManagerTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _artifactStore;
        private readonly FakeImageJobClock _clock = new();
        private readonly FakeImageJobIdGenerator _idGenerator = new();

        public ReplicateImageJobManagerTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-replicate-image-job-{Guid.NewGuid():N}");
            _artifactStore = new ArtifactStore(Path.Combine(_root, "artifacts"));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task Replicate_image_job_submits_polls_fetches_with_authenticated_output_copy()
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = req =>
                    req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.EndsWith("/predictions", StringComparison.Ordinal)
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, Prediction(
                            "pred-1",
                            "succeeded",
                            outputJson: "\"https://replicate.delivery/pbxt/out.png\"")),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: "r8-job-token",
                selectorApiToken: "r8-job-token");

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Equal("Bearer", outputHandler.Authorization!.Scheme);
            Assert.Equal("r8-job-token", outputHandler.Authorization.Parameter);
            var artifact = _artifactStore.Get(status.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Equal(VisionHandler.ArtifactKindGeneratedImage, artifact!.Kind);
            Assert.Equal("replicate", artifact.Metadata["provider"]!.GetValue<string>());
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, artifact.Metadata["model"]!.GetValue<string>());
            var metadataJson = MetadataJson(artifact);
            Assert.DoesNotContain("r8-job-token", metadataJson);
            Assert.DoesNotContain("replicate.delivery", metadataJson);
            Assert.Equal(new byte[] { 9, 8, 7 }, File.ReadAllBytes(
                _artifactStore.GetBlobAbsolutePath(artifact.Id, ImageMediaRoles.Image)));
        }

        [Fact]
        public async Task Missing_token_fails_before_output_fetch()
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = req =>
                    req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.EndsWith("/predictions", StringComparison.Ordinal)
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, Prediction(
                            "pred-1",
                            "succeeded",
                            outputJson: "\"https://replicate.delivery/pbxt/out.png\"")),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: "r8-provider-token",
                selectorApiToken: null);

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.NotNull(status.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, status.Error!.Code);
            Assert.False(status.Error.Retryable);
            Assert.Equal(0, outputHandler.SendCount);
        }

        [Theory]
        [InlineData("https://replicate.delivery.evil.test/out.png")]
        [InlineData("http://replicate.delivery/out.png")]
        public async Task Unsafe_output_url_fails_before_output_fetch(string outputUrl)
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = req =>
                    req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.EndsWith("/predictions", StringComparison.Ordinal)
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, Prediction(
                            "pred-1",
                            "succeeded",
                            outputJson: JsonValue.Create(outputUrl)!.ToJsonString())),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: "r8-job-token",
                selectorApiToken: "r8-job-token");

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.NotNull(status.Error);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, status.Error!.Code);
            Assert.False(status.Error.Retryable);
            Assert.Equal(0, outputHandler.SendCount);
        }

        [Fact]
        public async Task Data_removed_fails_on_status_path_before_fetch()
        {
            var apiHandler = new TestHttpMessageHandler
            {
                OnSend = req =>
                    req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.EndsWith("/predictions", StringComparison.Ordinal)
                        ? Json(HttpStatusCode.Created, Prediction("pred-1", "starting"))
                        : Json(HttpStatusCode.OK, """
                            {
                              "id": "pred-1",
                              "status": "succeeded",
                              "data_removed": true,
                              "urls": {
                                "get": "https://api.replicate.com/v1/predictions/pred-1",
                                "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
                              }
                            }
                            """),
            };
            var outputHandler = new CapturingOutputHandler();
            using var manager = Manager(
                apiHandler,
                outputHandler,
                providerApiToken: "r8-job-token",
                selectorApiToken: "r8-job-token");

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.NotNull(status.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, status.Error!.Code);
            Assert.Contains("expired", status.Error.Message);
            Assert.Equal(0, outputHandler.SendCount);
        }

        private ImageJobManager Manager(
            TestHttpMessageHandler apiHandler,
            HttpMessageHandler outputHandler,
            string? providerApiToken,
            string? selectorApiToken)
        {
            var provider = new ReplicateImageProvider(
                () => providerApiToken,
                new ReplicateApiClient(new HttpClient(apiHandler)));
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new ReplicateImageProviderRegistration(provider),
            });
            var selector = new ReplicateImageArtifactRequestFactorySelector(() => selectorApiToken);
            return new ImageJobManager(
                registry,
                _artifactStore,
                _clock,
                _idGenerator,
                TimeSpan.FromMilliseconds(1),
                ImageJobManager.DefaultMaxConcurrentJobs,
                new ImageArtifactMaterializer(outputHandler),
                selector.Select);
        }

        private static ImageJobStartRequest Start() =>
            new(
                new ImageGenerationRequest(
                    Model: ReplicateImageCapabilities.FluxSchnell,
                    Prompt: "sunlit massing study",
                    Resolution: "1K",
                    AspectRatio: "1:1",
                    NumberOfImages: 1,
                    ReferenceImages: null,
                    Options: new ReplicateImageOptions()),
                new Dictionary<MediaRef, ResolvedMedia>(),
                Array.Empty<Guid>());

        private static async Task<ImageJobStatusResult> WaitForTerminalAsync(
            ImageJobManager manager,
            Guid jobId)
        {
            var deadline = DateTime.UtcNow.AddSeconds(5);
            ImageJobStatusResult? last = null;
            while (DateTime.UtcNow < deadline)
            {
                last = await manager.GetStatusAsync(jobId, CancellationToken.None);
                if (last.State is ImageJobState.Complete or ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted)
                    return last;
                await Task.Delay(10);
            }
            throw new TimeoutException($"Job did not reach terminal state. Last state: {last?.State}.");
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string json) =>
            new(status)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };

        private static string MetadataJson(Artifact artifact)
        {
            var obj = new JsonObject();
            foreach (var kvp in artifact.Metadata)
                obj[kvp.Key] = kvp.Value?.DeepClone();
            return obj.ToJsonString();
        }

        private static string Prediction(string id, string status, string outputJson = "null") =>
            $$"""
            {
              "id": "{{id}}",
              "status": "{{status}}",
              "output": {{outputJson}},
              "model": "black-forest-labs/flux-schnell",
              "version": "hidden-version",
              "metrics": { "predict_time": 1.25, "total_time": 2.5 },
              "urls": {
                "get": "https://api.replicate.com/v1/predictions/{{id}}",
                "cancel": "https://api.replicate.com/v1/predictions/{{id}}/cancel"
              }
            }
            """;

        private sealed class CapturingOutputHandler : HttpMessageHandler
        {
            public int SendCount { get; private set; }
            public AuthenticationHeaderValue? Authorization { get; private set; }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                SendCount++;
                Authorization = request.Headers.Authorization;
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 9, 8, 7 }),
                };
                response.Content.Headers.ContentType = new MediaTypeHeaderValue("image/png");
                return Task.FromResult(response);
            }
        }
    }

}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateImageJobManagerTests
```

Expected: compile failure because `ReplicateImageArtifactRequestFactorySelector` does not exist.

- [ ] **Step 3: Add selector implementation**

Create `src/Rook/Services/Vision/Image/Replicate/ReplicateImageArtifactRequestFactorySelector.cs`:

```csharp
using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateImageArtifactRequestFactorySelector
    {
        private readonly Func<string?> _apiTokenProvider;

        public ReplicateImageArtifactRequestFactorySelector(Func<string?> apiTokenProvider)
        {
            _apiTokenProvider = apiTokenProvider
                ?? throw new ArgumentNullException(nameof(apiTokenProvider));
        }

        public ImageArtifactRequestFactory? Select(
            ResolvedImageModel model,
            ResultArtifact artifact)
        {
            if (model is null)
                return null;
            if (!string.Equals(
                    model.ProviderName,
                    ReplicateImageCapabilities.ProviderName,
                    StringComparison.Ordinal))
            {
                return null;
            }

            return _ =>
            {
                if (artifact.Body is not RemoteArtifactBody remote)
                {
                    return ImageArtifactFetchRequest.Failed(new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Replicate image artifact required authenticated fetch but was not remote.",
                        Retryable: false));
                }

                var apiToken = _apiTokenProvider();
                if (string.IsNullOrWhiteSpace(apiToken))
                    return ImageArtifactFetchRequest.Failed(ReplicateErrorMapper.MissingToken());

                try
                {
                    return ImageArtifactFetchRequest.Created(
                        ReplicateApiClient.BuildAuthenticatedOutputRequest(
                            apiToken!,
                            remote.Url));
                }
                catch (ArgumentException ex)
                {
                    return ImageArtifactFetchRequest.Failed(new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        ex.Message,
                        Retryable: false));
                }
            };
        }
    }
}
```

- [ ] **Step 4: Run image job tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ReplicateImageJobManagerTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Replicate\ReplicateImageArtifactRequestFactorySelector.cs `
        src\Rook.Tests\Services\Vision\Image\Replicate\ReplicateImageJobManagerTests.cs
git commit -m "feat(vision): authenticate Replicate image artifacts"
```

---

## Task 5: Boundary Guards And No-Exposure Scans

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`

- [ ] **Step 1: Strengthen default registration source guard**

In `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`, update `CreateCredentialMetadata_does_not_construct_provider_registrations` so it also rejects Replicate construction:

```csharp
Assert.DoesNotContain("ReplicateImageProviderRegistration", methodBody);
Assert.DoesNotContain("ReplicateImageProvider", methodBody);
```

Add this test to the same file:

```csharp
[Fact]
public void CreateImageRegistrations_default_composition_does_not_reference_replicate()
{
    var source = File.ReadAllText(FindSourceFile());
    var methodBody = ExtractMethodBody(source, "CreateImageRegistrations");

    Assert.DoesNotContain("ReplicateImageProviderRegistration", methodBody);
    Assert.DoesNotContain("ReplicateImageProvider", methodBody);
    Assert.DoesNotContain("ReplicateApiToken", methodBody);
}
```

Rename `ExtractCreateCredentialMetadataBody` to `ExtractMethodBody` and change it to accept the method name:

```csharp
private static string ExtractMethodBody(string source, string methodName)
{
    var signatureIndex = source.IndexOf(methodName, StringComparison.Ordinal);
    if (signatureIndex < 0)
        throw new InvalidOperationException($"{methodName} was not found.");

    var openBrace = source.IndexOf('{', signatureIndex);
    if (openBrace < 0)
        throw new InvalidOperationException($"{methodName} body was not found.");

    var depth = 0;
    for (var i = openBrace; i < source.Length; i++)
    {
        if (source[i] == '{') depth++;
        if (source[i] == '}') depth--;
        if (depth == 0)
            return source.Substring(openBrace, i - openBrace + 1);
    }

    throw new InvalidOperationException($"{methodName} body was not closed.");
}
```

Update the existing `CreateCredentialMetadata_does_not_construct_provider_registrations` call site to:

```csharp
var methodBody = ExtractMethodBody(source, "CreateCredentialMetadata");
```

- [ ] **Step 2: Run boundary tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter VisionProviderRegistrationsTests
```

Expected: PASS.

- [ ] **Step 3: Run source boundary scans**

Run:

```powershell
rg -n "ReplicateImageProvider|ReplicateImageProviderRegistration|ReplicateImageCapabilities|replicate.api_token" src\Rook\UI src\RookNative mcp_server src\Rook\InternalBridge src\Rook\Services\Vision\VisionProviderRegistrations.cs
```

Expected: no hits.

Run:

```powershell
rg -n "black-forest-labs/flux-schnell|replicate.delivery|requires_authenticated_fetch" src\RookNative mcp_server src\Rook\UI
```

Expected: no hits.

- [ ] **Step 4: Commit**

```powershell
git add src\Rook.Tests\Services\Vision\VisionProviderRegistrationsTests.cs
git commit -m "test(vision): preserve hidden Replicate boundary"
```

---

## Task 6: Focused And Full Verification

**Files:**
- No production files unless verification exposes a scoped bug.

- [ ] **Step 1: Run focused Replicate image provider suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImage"
```

Expected: PASS.

- [ ] **Step 2: Run Replicate substrate and image job regression suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "Replicate|ImageJob|ImageArtifactMaterializerTests"
```

Expected: PASS.

- [ ] **Step 3: Run provider catalog and Vision handler boundary suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionProviderRegistrationsTests|VisionHandlerTests|DefaultImageProviderRegistryTests"
```

Expected: PASS.

- [ ] **Step 4: Run hidden boundary scans**

Run:

```powershell
rg -n "ReplicateImageProvider|ReplicateImageProviderRegistration|ReplicateImageCapabilities|replicate.api_token" src\Rook\UI src\RookNative mcp_server src\Rook\InternalBridge src\Rook\Services\Vision\VisionProviderRegistrations.cs
```

Expected: no hits.

Run:

```powershell
rg -n "image_generate_start|image_job_status|image_job_cancel|image_job_result|image_jobs" src\RookNative mcp_server
```

Expected: no hits.

- [ ] **Step 5: Run broad managed Vision suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "Vision|Image|Generation|Fal|Replicate"
```

Expected: PASS.

- [ ] **Step 6: Run full managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: PASS. If local tooling prevents the full suite from completing, record the exact failure and all focused passing evidence.

- [ ] **Step 7: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected:

- `git diff --check` clean.
- changed files limited to managed Vision image Replicate code, managed tests, and plan/spec docs.
- no files under `src/RookNative/**`.
- no files under `mcp_server/**`.
- no UI resource edits.

## Self-Review Checklist

- [ ] Production Replicate image provider code exists under `src/Rook/Services/Vision/Image/Replicate`.
- [ ] `VisionProviderRegistrations.CreateImageRegistrations` remains Gemini + fal only.
- [ ] `CreateCredentialMetadata()` remains Gemini + fal only.
- [ ] Default `list_image_models` still omits Replicate.
- [ ] The only Replicate image model is `black-forest-labs/flux-schnell`.
- [ ] `ReplicateImageOptionsCodec` accepts empty options only.
- [ ] Reference images fail with `field = "reference_image_paths"` before HTTP.
- [ ] Create body includes only `prompt`, `aspect_ratio`, `num_outputs`, and `output_format`.
- [ ] Create body does not include `resolution` or media bytes.
- [ ] `data_removed: true` fails on the status path.
- [ ] `FetchResultAsync` accepts only one output URL and rejects unsupported output shapes.
- [ ] Replicate remote artifacts require authenticated fetch.
- [ ] The selector injects Bearer auth only for Replicate remote artifacts.
- [ ] Missing token and unsafe output URLs send no output-fetch request.
- [ ] No token appears in job status/result responses or artifact metadata.
- [ ] No native, MCP, Settings, picker, UI resource, or `NativeGhBridgeRegistrar` exposure is added.
- [ ] No live provider calls run in normal tests.
