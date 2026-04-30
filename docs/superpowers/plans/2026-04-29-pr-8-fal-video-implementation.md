# PR-8 fal.ai Video Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add managed-only fal.ai queue video support for `fal-ai/wan/v2.7/text-to-video` while preserving existing `/vision/video/*` route shapes.

**Architecture:** `FalVideoProvider` owns fal protocol and returns URL-backed result artifacts. `VideoJobManager` owns local video artifact materialization and `ArtifactStore` writes. `VideoOpHandler` resolves the requested model and delegates provider options parsing to the resolved model codec.

**Tech Stack:** C# multi-targeted `net7.0;net48`, xUnit tests on `net48`, `System.Text.Json.Nodes`, `HttpClient`, existing Rook generation/provider seams.

---

## Source Spec

Approved design: `docs/superpowers/plans/2026-04-29-pr-8-fal-video-design.md`

Important scope constraints:

- Register only `fal-ai/wan/v2.7/text-to-video`.
- Do not register `fal-ai/wan/v2.7/image-to-video`.
- Do not add audio input or `audio_url` support.
- Do not expose `negative_prompt` or `enable_prompt_expansion` options.
- Do not edit `src/RookNative/**`.
- Live fal calls are opt-in only and require spend approval environment flags.

## File Structure

### New production files

- `src/Rook/Services/Vision/Video/Fal/FalVideoOptions.cs`
  - Empty sealed provider options type for PR-8.
- `src/Rook/Services/Vision/Video/Fal/FalVideoOptionsCodec.cs`
  - Strict `{}` codec. Rejects any fal video option field in PR-8.
- `src/Rook/Services/Vision/Video/Fal/FalVideoCapabilities.cs`
  - Static descriptor for `fal-ai/wan/v2.7/text-to-video`.
- `src/Rook/Services/Vision/Video/Fal/FalWanT2vPricingModel.cs`
  - Per-output-second pricing at `$0.10/s`.
- `src/Rook/Services/Vision/Video/Fal/FalVideoProviderRegistration.cs`
  - Registers the one fal T2V model with codec, capability, and pricing.
- `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`
  - fal queue submit, status, fetch, and cancel protocol adapter.
- `src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs`
  - Video-specific inline/remote artifact materializer with production cap `250 MB`.

### Modified production files

- `src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs`
  - Add lazy fal key provider and fal registration beside Veo.
- `src/Rook/Handlers/VideoOpHandler.cs`
  - Replace unconditional Veo options parsing with registry-resolved codec deserialization.
- `src/Rook/Services/Vision/Video/VideoJobManager.cs`
  - Materialize both inline and remote video artifacts through `VideoArtifactMaterializer`.
- `src/Rook/Services/Vision/Video/VideoJobPricingTranslator.cs`
  - Add `FalWanT2vPricingModel` to the existing `PricingKind.PerSecond` classification.

### New test files

- `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoOptionsCodecTests.cs`
- `src/Rook.Tests/Services/Vision/Video/Fal/FalWanT2vPricingModelTests.cs`
- `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderRegistrationTests.cs`
- `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`
- `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoLiveSmokeTests.cs`
- `src/Rook.Tests/Services/Vision/Video/VideoArtifactMaterializerTests.cs`

### Modified test files

- `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`
  - Handler parser routing tests.
- `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`
  - Remote artifact and failure-state tests.
- `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`
  - Factory and list-model tests.
- `src/Rook.Tests/Services/Vision/Video/FakeVideoProvider.cs`
  - Add a helper returning `RemoteArtifactBody`.

## Task 1: Verify fal Queue Cancel Method

**Files:**
- Read: `docs/superpowers/plans/2026-04-29-pr-8-fal-video-design.md`
- Read: fal queue docs at `https://docs.fal.ai/model-apis/model-endpoints/queue/`
- No code changes in this task.

- [ ] **Step 1: Verify current official cancel method**

Open the current fal queue API reference and confirm the queue endpoint table still lists:

```text
https://queue.fal.run/{model_id}/requests/{request_id}/cancel | PUT | Cancels a request that has not started processing
```

If the official source says anything other than `PUT`, stop and update this implementation plan before writing provider tests.

- [ ] **Step 2: Record the evidence in the task notes**

Add an implementation note in the task branch description or commit message:

```text
Verified fal queue cancel method from official queue API docs on 2026-04-29: PUT /{model_id}/requests/{request_id}/cancel.
```

- [ ] **Step 3: Commit**

No commit is required if no files changed.

## Task 2: Fal Video Options, Capability, Pricing, and Registration

**Files:**
- Create: `src/Rook/Services/Vision/Video/Fal/FalVideoOptions.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalVideoOptionsCodec.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalVideoCapabilities.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalWanT2vPricingModel.cs`
- Create: `src/Rook/Services/Vision/Video/Fal/FalVideoProviderRegistration.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoOptionsCodecTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Fal/FalWanT2vPricingModelTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderRegistrationTests.cs`

- [ ] **Step 1: Write failing codec tests**

Create `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoOptionsCodecTests.cs`:

```csharp
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoOptionsCodecTests
    {
        private readonly FalVideoOptionsCodec _codec = new();

        [Fact]
        public void Deserialize_empty_object_returns_fal_options()
        {
            var result = _codec.Deserialize(new JsonObject());

            Assert.True(result.Success);
            Assert.IsType<FalVideoOptions>(result.Options);
            Assert.Null(result.Error);
        }

        [Theory]
        [InlineData("negative_prompt")]
        [InlineData("enable_prompt_expansion")]
        [InlineData("audio_url")]
        [InlineData("future_field")]
        public void Deserialize_unknown_or_deferred_fields_fail(string field)
        {
            var json = new JsonObject { [field] = "x" };

            var result = _codec.Deserialize(json);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal(field, result.Error.Field);
        }

        [Fact]
        public void Serialize_fal_options_returns_empty_object()
        {
            var json = _codec.Serialize(new FalVideoOptions());

            Assert.Empty(json);
        }

        [Fact]
        public void Validate_accepts_fal_options_for_t2v()
        {
            var request = Request(new FalVideoOptions());

            var result = _codec.Validate(
                request,
                request.Options,
                FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_mismatched_options_type()
        {
            var request = Request(new VeoOptions(PersonGenerationPolicy.AllowAll));

            var result = _codec.Validate(
                request,
                request.Options,
                FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability);

            Assert.False(result.Success);
            Assert.Equal(nameof(VideoGenerationRequest.Options), result.Field);
        }

        private static VideoGenerationRequest Request(ProviderOptions options) =>
            new(
                Model: FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "a small architectural massing animation",
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: options,
                NumberOfVideos: 1);
    }
}
```

- [ ] **Step 2: Write failing pricing and registration tests**

Create `src/Rook.Tests/Services/Vision/Video/Fal/FalWanT2vPricingModelTests.cs`:

```csharp
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalWanT2vPricingModelTests
    {
        [Fact]
        public void Estimate_prices_duration_at_ten_cents_per_second()
        {
            var model = new FalWanT2vPricingModel();
            var request = new VideoGenerationRequest(
                Model: FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "clip",
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

            var result = model.Estimate(
                request,
                FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability);

            Assert.True(result.Success);
            Assert.Equal("USD", result.Pricing!.Currency);
            Assert.Equal(0.10m, result.Pricing.UnitPrice);
            Assert.Equal("output_second", result.Pricing.Unit);
            Assert.Equal(2m, result.Pricing.Quantity);
            Assert.Equal(0.20m, result.Pricing.TotalUsd);
            Assert.True(result.Estimate!.IsExact);
            Assert.Equal(FalWanT2vPricingModel.Source, result.Pricing.PricingSource);
        }

        [Fact]
        public void Pricing_model_classifies_as_per_second()
        {
            Assert.Equal(
                PricingKind.PerSecond,
                VideoJobPricingTranslator.PricingKindFor(new FalWanT2vPricingModel()));
        }
    }
}
```

Create `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderRegistrationTests.cs`:

```csharp
using System.Linq;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoProviderRegistrationTests
    {
        [Fact]
        public void Registration_exposes_single_wan_t2v_model()
        {
            var registration = new FalVideoProviderRegistration(new NullVideoProvider());

            var model = Assert.Single(registration.Models);
            Assert.Equal(FalVideoCapabilities.WanT2v, model.Key);
            Assert.Equal(FalVideoCapabilities.WanT2v, model.Value.Capability.Id);
            Assert.IsType<FalWanT2vPricingModel>(model.Value.PricingModel);
            Assert.IsType<FalVideoOptionsCodec>(registration.OptionsCodec);
        }

        [Fact]
        public void Capability_is_t2v_only_with_no_reference_images()
        {
            var cap = FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability;

            Assert.Equal(new[] { VideoMode.T2V }, cap.Modes);
            Assert.False(cap.SupportsReferenceImages);
            Assert.Equal(0, cap.MaxReferenceImages);
            Assert.Empty(cap.Must8sWith);
            Assert.Contains("720p", cap.Resolutions);
            Assert.Contains("1080p", cap.Resolutions);
            Assert.Contains(2, cap.Durations);
            Assert.Contains(15, cap.Durations);
        }

        [Fact]
        public void Secret_requirements_use_fal_api_key()
        {
            var registration = new FalVideoProviderRegistration(new NullVideoProvider());

            var requirement = Assert.Single(registration.SecretRequirements);
            Assert.Equal(GenerationSecretKeys.FalApiKey, requirement.Key);
            Assert.True(requirement.IsRequired);
        }
    }
}
```

Add this private class inside the registration test file:

```csharp
private sealed class NullVideoProvider : IVideoProvider
{
    public string ProviderName => FalVideoCapabilities.ProviderName;

    public System.Threading.Tasks.Task<ProviderSubmitOutcome> SubmitAsync(
        VideoGenerationRequest request,
        System.Collections.Generic.IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
        System.Threading.CancellationToken ct) =>
        throw new System.NotSupportedException();

    public System.Threading.Tasks.Task<ProviderStatusOutcome> GetStatusAsync(
        ProviderJobHandle handle,
        System.Threading.CancellationToken ct) =>
        throw new System.NotSupportedException();

    public System.Threading.Tasks.Task<ProviderCancelOutcome> CancelAsync(
        ProviderJobHandle handle,
        System.Threading.CancellationToken ct) =>
        throw new System.NotSupportedException();

    public System.Threading.Tasks.Task<ProviderResultOutcome> FetchResultAsync(
        ProviderJobHandle handle,
        System.Threading.CancellationToken ct) =>
        throw new System.NotSupportedException();
}
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~FalVideoOptionsCodecTests|FullyQualifiedName~FalWanT2vPricingModelTests|FullyQualifiedName~FalVideoProviderRegistrationTests"
```

Expected: compile failure because `FalVideoOptions`, `FalVideoOptionsCodec`, `FalVideoCapabilities`, `FalWanT2vPricingModel`, and `FalVideoProviderRegistration` do not exist.

- [ ] **Step 4: Implement fal video options**

Create `src/Rook/Services/Vision/Video/Fal/FalVideoOptions.cs`:

```csharp
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalVideoOptions : ProviderOptions
    {
    }
}
```

Create `src/Rook/Services/Vision/Video/Fal/FalVideoOptionsCodec.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalVideoOptionsCodec
        : IProviderOptionsCodec<VideoGenerationRequest, VideoCapability>
    {
        public ValidationResult Validate(
            VideoGenerationRequest request,
            ProviderOptions options,
            VideoCapability cap)
        {
            if (request is null)
                return ValidationResult.Fail("Request is null.", "Request");
            if (cap is null)
                return ValidationResult.Fail("Capability is null.", "Cap");
            if (options is not FalVideoOptions)
                return ValidationResult.Fail(
                    $"fal video codec requires {nameof(FalVideoOptions)}; got {options?.GetType().Name ?? "null"}.",
                    nameof(VideoGenerationRequest.Options));

            return ValidationResult.Ok();
        }

        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not FalVideoOptions)
                throw new InvalidOperationException(
                    $"fal video codec cannot serialize {options?.GetType().Name ?? "null"}; expected {nameof(FalVideoOptions)}.");

            return new JsonObject();
        }

        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            if (json is null)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Provider options JSON is null.",
                    Retryable: false,
                    Field: "options"));

            foreach (var kvp in json)
            {
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    $"fal video options do not support field '{kvp.Key}' in PR-8.",
                    Retryable: false,
                    Field: kvp.Key));
            }

            return ProviderOptionsDecodeResult.Ok(new FalVideoOptions());
        }
    }
}
```

- [ ] **Step 5: Implement fal video capability, pricing, and registration**

Create `src/Rook/Services/Vision/Video/Fal/FalVideoCapabilities.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video.Fal
{
    public static class FalVideoCapabilities
    {
        public const string ProviderName = "fal";
        public const string WanT2v = "fal-ai/wan/v2.7/text-to-video";

        public static readonly IReadOnlyDictionary<string, (VideoCapability Capability, Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models =
            new Dictionary<string, (VideoCapability, Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability>)>(StringComparer.Ordinal)
            {
                [WanT2v] = (
                    new VideoCapability(
                        Id: WanT2v,
                        Name: "Wan 2.7 Text to Video",
                        Status: "preview",
                        Resolutions: new[] { "720p", "1080p" },
                        Durations: new[] { 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 },
                        AspectRatios: new[] { "16:9", "9:16", "1:1", "4:3", "3:4" },
                        Modes: new[] { VideoMode.T2V },
                        SupportsReferenceImages: false,
                        MaxReferenceImages: 0,
                        Must8sWith: Array.Empty<string>()),
                    new FalWanT2vPricingModel()),
            };
    }
}
```

Create `src/Rook/Services/Vision/Video/Fal/FalWanT2vPricingModel.cs`:

```csharp
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalWanT2vPricingModel : IPricingModel<VideoGenerationRequest, VideoCapability>
    {
        public const string Source = "fal-ai/wan/v2.7/text-to-video-output-second-2026-04-29";

        public string PricingSource => Source;
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseHeader;

        public PricingResult Estimate(VideoGenerationRequest request, VideoCapability capability)
        {
            if (request is null)
                return PricingResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            var quantity = request.DurationSeconds * request.NumberOfVideos;
            var total = 0.10m * quantity;
            var pricing = new Rook.Services.Vision.Generation.JobPricing(
                Currency: "USD",
                UnitPrice: 0.10m,
                Unit: "output_second",
                Quantity: quantity,
                TotalUsd: total,
                PricingSource: Source);
            var estimate = new CostEstimate(
                Min: total,
                Max: total,
                IsExact: true,
                Provenance: Source);

            return PricingResult.Ok(pricing, estimate);
        }

        public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody)
        {
            if (!Rook.Services.Vision.Fal.FalPricingHelpers.TryGetBillableUnits(
                    responseHeaders,
                    out var units))
            {
                return null;
            }

            var total = units * 0.10m;
            return new Rook.Services.Vision.Generation.JobPricing(
                Currency: "USD",
                UnitPrice: 0.10m,
                Unit: "fal_billable_unit",
                Quantity: units,
                TotalUsd: total,
                PricingSource: Source);
        }
    }
}
```

Modify `src/Rook/Services/Vision/Video/VideoJobPricingTranslator.cs`:

```csharp
return model switch
{
    PerSecondVideoPricingModel => PricingKind.PerSecond,
    Rook.Services.Vision.Video.Fal.FalWanT2vPricingModel => PricingKind.PerSecond,
    _ => PricingKind.External,
};
```

Create `src/Rook/Services/Vision/Video/Fal/FalVideoProviderRegistration.cs`:

```csharp
using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalVideoProviderRegistration : IVideoProviderRegistration
    {
        public FalVideoProviderRegistration(IVideoProvider provider)
        {
            Provider = provider ?? throw new ArgumentNullException(nameof(provider));
            OptionsCodec = new FalVideoOptionsCodec();
            Models = FalVideoCapabilities.Models;
        }

        public string ProviderName => FalVideoCapabilities.ProviderName;
        public IVideoProvider Provider { get; }
        public IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec { get; }
        public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

        private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
            Array.AsReadOnly(new[]
            {
                new ProviderSecretRequirement(
                    GenerationSecretKeys.FalApiKey,
                    "fal API key",
                    isRequired: true),
            });
    }
}
```

- [ ] **Step 6: Run task tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~FalVideoOptionsCodecTests|FullyQualifiedName~FalWanT2vPricingModelTests|FullyQualifiedName~FalVideoProviderRegistrationTests"
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal src\Rook\Services\Vision\Video\VideoJobPricingTranslator.cs src\Rook.Tests\Services\Vision\Video\Fal
git commit -m "feat(vision): add fal video model metadata"
```

## Task 3: FalVideoProvider Protocol Adapter

**Files:**
- Create: `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`

- [ ] **Step 1: Write failing provider tests**

Create `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`:

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
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoProviderTests
    {
        [Fact]
        public async Task Submit_posts_expected_body_and_parses_queue_handle()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.OK, @"{
                      ""request_id"": ""wan-123"",
                      ""status_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/status"",
                      ""response_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123"",
                      ""cancel_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"",
                      ""status"": ""IN_QUEUE"",
                      ""queue_position"": 3
                    }");
                },
            };
            var provider = Provider(handler);

            var outcome = await provider.SubmitAsync(
                Request(seed: 123),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("wan-123", queued.Handle.ProviderJobId);
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123/status", queued.Handle.StatusUrl!.ToString());
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123", queued.Handle.ResponseUrl!.ToString());
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel", queued.Handle.CancelUrl!.ToString());
            Assert.Equal("PUT", queued.Handle.CancelHttpMethod);
            Assert.Equal(3, queued.Handle.ProviderMetadata!["queue_position"]!.GetValue<int>());

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://queue.fal.run/fal-ai/wan/v2.7/text-to-video", request.RequestUri!.ToString());
            Assert.Equal("Key", request.Headers.Authorization!.Scheme);
            Assert.Equal("test-fal-key", request.Headers.Authorization.Parameter);

            var json = JsonNode.Parse(body!)!.AsObject();
            Assert.Equal("a clay massing animation", json["prompt"]!.GetValue<string>());
            Assert.Equal("16:9", json["aspect_ratio"]!.GetValue<string>());
            Assert.Equal("720p", json["resolution"]!.GetValue<string>());
            Assert.Equal(2, json["duration"]!.GetValue<int>());
            Assert.Equal(123, json["seed"]!.GetValue<int>());
            Assert.True(json["enable_safety_checker"]!.GetValue<bool>());
            Assert.True(json["enable_prompt_expansion"]!.GetValue<bool>());
            Assert.False(json.ContainsKey("negative_prompt"));
            Assert.False(json.ContainsKey("audio_url"));
        }

        [Fact]
        public async Task Submit_omits_seed_when_absent()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.OK, SubmitBody());
                },
            };
            var provider = Provider(handler);

            await provider.SubmitAsync(
                Request(seed: null),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var json = JsonNode.Parse(body!)!.AsObject();
            Assert.False(json.ContainsKey("seed"));
        }

        [Fact]
        public async Task Submit_missing_key_returns_dependency_unavailable()
        {
            var provider = new FalVideoProvider(() => null, new FalApiClient(new HttpClient(new TestHttpMessageHandler())));

            var outcome = await provider.SubmitAsync(
                Request(),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
        }

        [Fact]
        public async Task Submit_missing_prompt_returns_invalid_request()
        {
            var provider = Provider(new TestHttpMessageHandler());

            var outcome = await provider.SubmitAsync(
                Request(prompt: null),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal(nameof(VideoGenerationRequest.Prompt), failed.Error.Field);
        }

        [Fact]
        public async Task Status_completed_returns_provider_complete_without_fetch_success()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, @"{ ""status"": ""COMPLETED"" }"),
            };
            var provider = Provider(handler);
            var handle = Handle();

            var outcome = await provider.GetStatusAsync(handle, CancellationToken.None);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Same(handle, complete.UpdatedHandle);
        }

        [Fact]
        public async Task Fetch_requires_response_url()
        {
            var provider = Provider(new TestHttpMessageHandler());

            var outcome = await provider.FetchResultAsync(
                new ProviderJobHandle("wan-123"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.DoesNotContain("wan-123", failed.Error.Message);
        }

        [Fact]
        public async Task Fetch_parses_remote_video_artifact()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, @"{
                  ""actual_prompt"": ""expanded prompt"",
                  ""seed"": 42,
                  ""video"": {
                    ""url"": ""https://v3b.fal.media/files/out.mp4"",
                    ""content_type"": ""video/mp4"",
                    ""duration"": 2,
                    ""fps"": 24,
                    ""num_frames"": 48,
                    ""width"": 1280,
                    ""height"": 720
                  }
                }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.FetchResultAsync(Handle(), CancellationToken.None);

            var success = Assert.IsType<SuccessResultOutcome>(outcome);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(VideoMediaRoles.Video, artifact.Role);
            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.Equal("https://v3b.fal.media/files/out.mp4", remote.Url.ToString());
            Assert.Equal("video/mp4", artifact.DeclaredMimeType);
            Assert.Equal(1280, artifact.ProviderMetadata["width"]!.GetValue<int>());
            Assert.Equal("expanded prompt", success.Envelope.EnvelopeMetadata["actual_prompt"]!.GetValue<string>());
        }

        [Fact]
        public async Task Fetch_non_success_maps_provider_error()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.UnprocessableEntity, @"{ ""detail"": [{ ""msg"": ""bad"" }] }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.FetchResultAsync(Handle(), CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.NotNull(failed.Error.ProviderDetail);
        }

        [Fact]
        public async Task Cancel_uses_put_and_cancel_url()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.Accepted, @"{ ""status"": ""CANCELLATION_REQUESTED"" }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.CancelAsync(Handle(), CancellationToken.None);

            Assert.IsType<CanceledOutcome>(outcome);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Put, request.Method);
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel", request.RequestUri!.ToString());
        }

        private static FalVideoProvider Provider(TestHttpMessageHandler handler) =>
            new(() => "test-fal-key", new FalApiClient(new HttpClient(handler)));

        private static VideoGenerationRequest Request(int? seed = null, string? prompt = "a clay massing animation") =>
            new(
                Model: FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: prompt,
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: seed,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

        private static ProviderJobHandle Handle() =>
            new(
                providerJobId: "wan-123",
                statusUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123/status"),
                responseUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123"),
                cancelUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"),
                cancelHttpMethod: "PUT");

        private static HttpResponseMessage Json(HttpStatusCode status, string body) =>
            new(status)
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json"),
            };

        private static string SubmitBody() =>
            @"{
              ""request_id"": ""wan-123"",
              ""status_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/status"",
              ""response_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123"",
              ""cancel_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"",
              ""status"": ""IN_QUEUE""
            }";
    }
}
```

- [ ] **Step 2: Run provider tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~FalVideoProviderTests"
```

Expected: compile failure because `FalVideoProvider` does not exist.

- [ ] **Step 3: Implement `FalVideoProvider`**

Create `src/Rook/Services/Vision/Video/Fal/FalVideoProvider.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalVideoProvider : IVideoProvider
    {
        private static readonly Uri Endpoint =
            new("https://queue.fal.run/fal-ai/wan/v2.7/text-to-video");
        private const string CancelHttpMethod = "PUT";

        private readonly Func<string?> _apiKeyProvider;
        private readonly FalApiClient _client;

        public FalVideoProvider(Func<string?> apiKeyProvider, FalApiClient? client = null)
        {
            _apiKeyProvider = apiKeyProvider ?? throw new ArgumentNullException(nameof(apiKeyProvider));
            _client = client ?? new FalApiClient();
        }

        public string ProviderName => FalVideoCapabilities.ProviderName;

        public async Task<ProviderSubmitOutcome> SubmitAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            if (request is null)
                return FailedSubmit(GenerationErrorCode.InvalidRequest, "Request is null.", nameof(request));
            if (request.Options is not FalVideoOptions)
                return FailedSubmit(GenerationErrorCode.InvalidRequest, "fal video provider requires FalVideoOptions.", nameof(VideoGenerationRequest.Options));
            if (string.IsNullOrWhiteSpace(request.Prompt))
                return FailedSubmit(GenerationErrorCode.InvalidRequest, "fal text-to-video requires prompt.", nameof(VideoGenerationRequest.Prompt));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return FailedSubmit(GenerationErrorCode.DependencyUnavailable, "fal API key is not configured.");

            FalHttpResponse response;
            try
            {
                response = await _client.PostJsonAsync(apiKey!, Endpoint, BuildRequestJson(request), ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (TaskCanceledException)
            {
                return FailedSubmit(GenerationErrorCode.DependencyUnavailable, "fal video submit timed out.", retryable: true);
            }
            catch (HttpRequestException)
            {
                return FailedSubmit(GenerationErrorCode.DependencyUnavailable, "fal video submit failed due to a transport error.", retryable: true);
            }

            if (!response.IsSuccessStatusCode)
                return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(response));

            try
            {
                var root = JsonNode.Parse(response.Body);
                if (root is null)
                    return FailedSubmit(GenerationErrorCode.ExecutionFailed, "fal submit response was empty.");
                return new QueuedSubmitOutcome(FalLifecycleMapper.ParseSubmitHandle(root, CancelHttpMethod));
            }
            catch (JsonException)
            {
                return FailedSubmit(GenerationErrorCode.ExecutionFailed, "fal submit response was not valid JSON.");
            }
            catch (ArgumentException ex)
            {
                return FailedSubmit(GenerationErrorCode.ExecutionFailed, ex.Message);
            }
        }

        public async Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.InvalidRequest, "ProviderJobHandle is required.", false, nameof(handle)));
            if (handle.StatusUrl is null)
                return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal status URL is missing.", false));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal API key is not configured.", false));

            try
            {
                var response = await _client.GetAsync(apiKey!, handle.StatusUrl, ct).ConfigureAwait(false);
                if (!response.IsSuccessStatusCode)
                    return new FailedStatusOutcome(FalErrorMapper.MapHttpFailure(response));

                var root = JsonNode.Parse(response.Body);
                return root is null
                    ? new FailedStatusOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal status response was empty.", false))
                    : FalLifecycleMapper.MapStatus(handle, root);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (TaskCanceledException)
            {
                return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal status request timed out.", true));
            }
            catch (JsonException)
            {
                return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal status response was not valid JSON.", false));
            }
            catch (HttpRequestException)
            {
                return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal status request failed due to a transport error.", true));
            }
        }

        public async Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.InvalidRequest, "ProviderJobHandle is required.", false, nameof(handle)));
            if (handle.CancelUrl is null || string.IsNullOrWhiteSpace(handle.CancelHttpMethod))
                return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal cancel URL or method is missing.", false));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal API key is not configured.", false));

            try
            {
                var response = await _client.SendAsync(apiKey!, new HttpMethod(handle.CancelHttpMethod!), handle.CancelUrl, null, ct)
                    .ConfigureAwait(false);
                if (response.StatusCode == 202 || response.IsSuccessStatusCode)
                    return new CanceledOutcome();
                if (response.StatusCode == 400)
                    return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
                return new FailedCancelOutcome(FalErrorMapper.MapHttpFailure(response));
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (TaskCanceledException)
            {
                return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal cancel request timed out.", true));
            }
            catch (HttpRequestException)
            {
                return new FailedCancelOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal cancel request failed due to a transport error.", true));
            }
        }

        public async Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            if (handle is null)
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.InvalidRequest, "ProviderJobHandle is required.", false, nameof(handle)));
            if (handle.ResponseUrl is null)
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal response URL is missing.", false));

            var apiKey = _apiKeyProvider();
            if (string.IsNullOrWhiteSpace(apiKey))
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal API key is not configured.", false));

            try
            {
                var response = await _client.GetAsync(apiKey!, handle.ResponseUrl, ct).ConfigureAwait(false);
                if (!response.IsSuccessStatusCode)
                    return new FailedResultOutcome(FalErrorMapper.MapHttpFailure(response));

                return ParseFetchResult(response.Body);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (TaskCanceledException)
            {
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal result fetch timed out.", true));
            }
            catch (HttpRequestException)
            {
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "fal result fetch failed due to a transport error.", true));
            }
        }

        private static string BuildRequestJson(VideoGenerationRequest request)
        {
            var body = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["aspect_ratio"] = request.AspectRatio,
                ["resolution"] = request.Resolution,
                ["duration"] = request.DurationSeconds,
                ["enable_safety_checker"] = true,
                ["enable_prompt_expansion"] = true,
            };
            if (request.Seed is int seed)
                body["seed"] = seed;
            return body.ToJsonString();
        }

        private static ProviderResultOutcome ParseFetchResult(string body)
        {
            JsonObject root;
            try
            {
                root = JsonNode.Parse(body) as JsonObject
                    ?? throw new JsonException();
            }
            catch (JsonException)
            {
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal result response was not valid JSON.", false));
            }

            if (root["video"] is not JsonObject video)
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal result response did not contain video object.", false, "video"));

            if (!TryString(video, "url", out var urlText)
                || !Uri.TryCreate(urlText, UriKind.Absolute, out var url)
                || (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps))
            {
                return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal video URL was missing or invalid.", false, "video.url"));
            }

            var artifactMetadata = CloneObject(video);
            var envelopeMetadata = new Dictionary<string, JsonNode>();
            AddMetadata(root, envelopeMetadata, "actual_prompt");
            AddMetadata(root, envelopeMetadata, "seed");

            var artifact = new ResultArtifact(
                Role: VideoMediaRoles.Video,
                Body: new RemoteArtifactBody(url),
                DeclaredMimeType: TryString(video, "content_type", out var mime) ? mime : null,
                ProviderMetadata: artifactMetadata);

            return new SuccessResultOutcome(new ProviderResultEnvelope(new[] { artifact }, envelopeMetadata));
        }

        private static ProviderSubmitOutcome FailedSubmit(
            GenerationErrorCode code,
            string message,
            string? field = null,
            bool retryable = false) =>
            new FailedSubmitOutcome(new GenerationError(code, message, retryable, field));

        private static bool TryString(JsonObject obj, string key, out string? value)
        {
            value = null;
            try
            {
                value = obj[key]?.GetValue<string>();
                return !string.IsNullOrWhiteSpace(value);
            }
            catch
            {
                return false;
            }
        }

        private static Dictionary<string, JsonNode> CloneObject(JsonObject obj)
        {
            var copy = new Dictionary<string, JsonNode>();
            foreach (var kvp in obj)
                if (kvp.Value is not null)
                    copy[kvp.Key] = kvp.Value.DeepClone();
            return copy;
        }

        private static void AddMetadata(JsonObject source, IDictionary<string, JsonNode> metadata, string key)
        {
            var node = source[key]?.DeepClone();
            if (node is not null)
                metadata[key] = node;
        }
    }
}
```

- [ ] **Step 4: Run provider tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~FalVideoProviderTests"
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Video\Fal\FalVideoProvider.cs src\Rook.Tests\Services\Vision\Video\Fal\FalVideoProviderTests.cs
git commit -m "feat(vision): add fal queue video provider"
```

## Task 4: Registry-Resolved Video Options Parsing

**Files:**
- Modify: `src/Rook/Handlers/VideoOpHandler.cs`
- Test: `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`

- [ ] **Step 1: Add failing handler tests**

In `src/Rook.Tests/Handlers/VideoOpHandlerTests.cs`, add tests for the new parser behavior. Use the file's existing handler construction helpers where available. If no helper accepts a custom registry, add a local helper that constructs `VideoOpHandler` with `FakeVideoJobManager`, a `DefaultVideoProviderRegistry`, and `VideoCostEstimator`.

Add these tests:

```csharp
[Fact]
public void Estimate_unknown_model_fails_before_options_shape_validation()
{
    var handler = CreateHandlerWithVeoAndFal();
    var body = @"{
      ""op"": ""estimate_video_job"",
      ""model"": ""no-such-model"",
      ""mode"": ""t2v"",
      ""duration_seconds"": 2,
      ""resolution"": ""720p"",
      ""aspect_ratio"": ""16:9"",
      ""prompt"": ""clip"",
      ""options"": { ""negative_prompt"": ""would be fal-only if model existed"" }
    }";

    var response = handler.DispatchOffUi(body);

    Assert.False(response.Success);
    Assert.Equal(400, response.HttpStatus);
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    Assert.Equal("invalid_request", data["code"]);
    Assert.Equal("Model", data["field"]);
}

[Fact]
public void Estimate_fal_model_accepts_empty_options()
{
    var handler = CreateHandlerWithVeoAndFal();
    var body = @"{
      ""op"": ""estimate_video_job"",
      ""model"": ""fal-ai/wan/v2.7/text-to-video"",
      ""mode"": ""t2v"",
      ""duration_seconds"": 2,
      ""resolution"": ""720p"",
      ""aspect_ratio"": ""16:9"",
      ""prompt"": ""clip"",
      ""options"": {}
    }";

    var response = handler.DispatchOffUi(body);

    Assert.True(response.Success);
}

[Fact]
public void Estimate_fal_model_rejects_veo_options()
{
    var handler = CreateHandlerWithVeoAndFal();
    var body = @"{
      ""op"": ""estimate_video_job"",
      ""model"": ""fal-ai/wan/v2.7/text-to-video"",
      ""mode"": ""t2v"",
      ""duration_seconds"": 2,
      ""resolution"": ""720p"",
      ""aspect_ratio"": ""16:9"",
      ""prompt"": ""clip"",
      ""options"": { ""person_generation"": ""allow_all"" }
    }";

    var response = handler.DispatchOffUi(body);

    Assert.False(response.Success);
    Assert.Equal(400, response.HttpStatus);
}

[Fact]
public void Estimate_veo_model_still_accepts_person_generation_options()
{
    var handler = CreateHandlerWithVeoAndFal();
    var body = @"{
      ""op"": ""estimate_video_job"",
      ""model"": ""veo-3.1-lite-generate-preview"",
      ""mode"": ""t2v"",
      ""duration_seconds"": 8,
      ""resolution"": ""720p"",
      ""aspect_ratio"": ""16:9"",
      ""prompt"": ""clip"",
      ""options"": { ""person_generation"": ""allow_all"" }
    }";

    var response = handler.DispatchOffUi(body);

    Assert.True(response.Success);
}
```

Add this helper if the file does not already have equivalent composition:

```csharp
private static VideoOpHandler CreateHandlerWithVeoAndFal()
{
    var fakeProvider = new Rook.Tests.Services.Vision.Video.FakeVideoProvider();
    var registry = new DefaultVideoProviderRegistry(new IVideoProviderRegistration[]
    {
        new VeoProviderRegistration(fakeProvider),
        new Rook.Services.Vision.Video.Fal.FalVideoProviderRegistration(fakeProvider),
    });
    var manager = new Rook.Tests.Services.Vision.Video.Fixtures.FakeVideoJobManager();
    return new VideoOpHandler(manager, registry, new VideoCostEstimator());
}
```

Add this exact helper beside the existing `NewHandler(...)` helper:

```csharp
private static VideoOpHandler NewHandlerWithVeoAndFal(
    IVideoJobManager? manager = null,
    IVideoCostEstimator? estimator = null)
{
    var fakeProvider = new FakeVideoProvider();
    var registry = new DefaultVideoProviderRegistry(new IVideoProviderRegistration[]
    {
        new VeoProviderRegistration(fakeProvider),
        new Rook.Services.Vision.Video.Fal.FalVideoProviderRegistration(fakeProvider),
    });

    return new VideoOpHandler(
        manager: manager ?? new StubManager(),
        registry: registry,
        estimator: estimator ?? new VideoCostEstimator());
}
```

Use `NewHandlerWithVeoAndFal()` in the four new parser tests.

- [ ] **Step 2: Run handler tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoOpHandlerTests"
```

Expected: fal estimate test fails because `ParseGenerationRequest` still calls `ParseVeoOptions` unconditionally.

- [ ] **Step 3: Modify `VideoOpHandler` request parsing**

Change `ParseGenerationRequest` from `static` to an instance method and return the resolved model:

```csharp
private (VideoGenerationRequest? Request, ResolvedVideoModel? Model, VideoJobError? Error)
    ParseGenerationRequest(Dictionary<string, JsonElement> args)
```

After parsing the `model` string and before parsing options, add:

```csharp
if (!_registry.TryResolve(model!, out var resolvedModel))
{
    return (null, null, BadField(
        nameof(VideoGenerationRequest.Model),
        $"Unknown model: '{model}'."));
}
```

Replace the Veo-only options block with:

```csharp
var (optionsEl, optionsObjErr) = GetOptionalObject(args, "options");
if (optionsObjErr is not null) return (null, null, optionsObjErr);
if (optionsEl is null)
    return (null, null, BadField("options",
        "Missing required 'options' field (typed provider options)."));

var optionsJson = JsonNode.Parse(optionsEl.Value.GetRawText()) as JsonObject;
if (optionsJson is null)
    return (null, null, BadField("options", "'options' must be a JSON object."));

var decoded = resolvedModel.OptionsCodec.Deserialize(optionsJson);
if (!decoded.Success)
    return (null, null, VideoProviderOutcomeAdapters.ToVideoJobError(decoded.Error!));

var options = decoded.Options!;
```

When returning the parsed request:

```csharp
return (request, resolvedModel, null);
```

Update callers:

```csharp
var (request, _, parseErr) = ParseGenerationRequest(args);
```

for submit, and:

```csharp
var (request, model, parseErr) = ParseGenerationRequest(args);
if (parseErr is not null) return FailWithError(parseErr);

var result = _estimator.Estimate(model!, request!);
```

for estimate.

Do not remove `ParseVeoOptions` yet if other tests still reference it; if it becomes unused and private, delete it in the same edit.

- [ ] **Step 4: Run handler tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoOpHandlerTests"
```

Expected: all handler tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Handlers\VideoOpHandler.cs src\Rook.Tests\Handlers\VideoOpHandlerTests.cs
git commit -m "feat(vision): resolve video options by provider model"
```

## Task 5: Video Artifact Materializer

**Files:**
- Create: `src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/VideoArtifactMaterializerTests.cs`

- [ ] **Step 1: Write failing materializer tests**

Create `src/Rook.Tests/Services/Vision/Video/VideoArtifactMaterializerTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoArtifactMaterializerTests
    {
        [Fact]
        public async Task Inline_under_cap_materializes_without_http()
        {
            var handler = new CapturingHandler(_ => throw new InvalidOperationException("HTTP should not be called."));
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Inline(new byte[] { 1, 2, 3, 4 }, "video/mp4"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(new byte[] { 1, 2, 3, 4 }, result.Bytes);
            Assert.Equal("video/mp4", result.MimeType);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task Inline_over_cap_fails()
        {
            var materializer = new VideoArtifactMaterializer(maxGeneratedVideoBytes: 3);

            var result = await materializer.MaterializeAsync(
                Inline(new byte[] { 1, 2, 3, 4 }, "video/mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Remote_content_length_over_cap_fails_before_read()
        {
            var content = new ReadTrackingContent(length: 5);
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK) { Content = content });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.False(content.WasRead);
        }

        [Fact]
        public async Task Remote_missing_content_length_fails_when_stream_crosses_cap()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StreamContent(new RepeatingStream(length: 5)),
                });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
        }

        [Fact]
        public async Task Remote_exactly_cap_is_allowed()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1, 2, 3, 4 }),
                });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(new byte[] { 1, 2, 3, 4 }, result.Bytes);
        }

        [Fact]
        public async Task Remote_empty_body_fails()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(Array.Empty<byte>()),
                });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
        }

        [Fact]
        public async Task Remote_does_not_send_authorization_header()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.Null(Assert.Single(handler.Requests).Headers.Authorization);
        }

        [Fact]
        public async Task Declared_mime_wins_over_response_mime()
        {
            var handler = new CapturingHandler(_ =>
            {
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                };
                response.Content.Headers.ContentType = new MediaTypeHeaderValue("video/webm");
                return response;
            });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out", "video/mp4"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("video/mp4", result.MimeType);
        }

        [Fact]
        public async Task Response_mime_used_when_declared_absent()
        {
            var handler = new CapturingHandler(_ =>
            {
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                };
                response.Content.Headers.ContentType = new MediaTypeHeaderValue("video/webm");
                return response;
            });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("video/webm", result.MimeType);
        }

        [Fact]
        public async Task Fallback_mime_is_mp4()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                });
            var materializer = new VideoArtifactMaterializer(handler, maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("video/mp4", result.MimeType);
        }

        private static ResultArtifact Inline(byte[] bytes, string mime) =>
            new(
                Role: VideoMediaRoles.Video,
                Body: new InlineArtifactBody(bytes),
                DeclaredMimeType: mime,
                ProviderMetadata: EmptyMetadata());

        private static ResultArtifact Remote(string url, string? declaredMimeType = null) =>
            new(
                Role: VideoMediaRoles.Video,
                Body: new RemoteArtifactBody(new Uri(url)),
                DeclaredMimeType: declaredMimeType,
                ProviderMetadata: EmptyMetadata());

        private static IReadOnlyDictionary<string, JsonNode> EmptyMetadata() =>
            new Dictionary<string, JsonNode>();

        private sealed class CapturingHandler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, HttpResponseMessage> _onSend;
            public CapturingHandler(Func<HttpRequestMessage, HttpResponseMessage> onSend) => _onSend = onSend;
            public List<HttpRequestMessage> Requests { get; } = new();

            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                Requests.Add(request);
                return Task.FromResult(_onSend(request));
            }
        }

        private sealed class ReadTrackingContent : HttpContent
        {
            private readonly long _length;
            public ReadTrackingContent(long length)
            {
                _length = length;
                Headers.ContentLength = length;
            }

            public bool WasRead { get; private set; }
            protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context)
            {
                WasRead = true;
                return Task.CompletedTask;
            }

            protected override bool TryComputeLength(out long length)
            {
                length = _length;
                return true;
            }
        }

        private sealed class RepeatingStream : Stream
        {
            private long _remaining;
            public RepeatingStream(long length) => _remaining = length;
            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException();
            public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
            public override void Flush() { }
            public override int Read(byte[] buffer, int offset, int count)
            {
                if (_remaining <= 0) return 0;
                var toRead = (int)Math.Min(count, _remaining);
                for (var i = 0; i < toRead; i++) buffer[offset + i] = 1;
                _remaining -= toRead;
                return toRead;
            }
            public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
            public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }
    }
}
```

- [ ] **Step 2: Run materializer tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoArtifactMaterializerTests"
```

Expected: compile failure because `VideoArtifactMaterializer` does not exist.

- [ ] **Step 3: Implement materializer**

Create `src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs`:

```csharp
using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoArtifactMaterializer
    {
        internal const long MaxGeneratedVideoBytes = 250L * 1024 * 1024;

        private readonly HttpClient _httpClient;
        private readonly long _maxGeneratedVideoBytes;

        public VideoArtifactMaterializer(long? maxGeneratedVideoBytes = null)
            : this(new HttpClientHandler(), maxGeneratedVideoBytes)
        {
        }

        internal VideoArtifactMaterializer(
            HttpMessageHandler handler,
            long? maxGeneratedVideoBytes = null)
        {
            if (handler is null) throw new ArgumentNullException(nameof(handler));
            _httpClient = new HttpClient(handler);
            _maxGeneratedVideoBytes = maxGeneratedVideoBytes ?? MaxGeneratedVideoBytes;
        }

        public async Task<VideoArtifactMaterializationResult> MaterializeAsync(
            ResultArtifact artifact,
            CancellationToken cancellationToken)
        {
            if (artifact is null) throw new ArgumentNullException(nameof(artifact));

            if (artifact.Body is InlineArtifactBody inline)
            {
                if (inline.Bytes.LongLength > _maxGeneratedVideoBytes)
                    return VideoArtifactMaterializationResult.Fail(ExecutionFailed("Inline video artifact exceeded the maximum allowed size."));

                return VideoArtifactMaterializationResult.Ok(
                    inline.Bytes,
                    ResolveMimeType(artifact.DeclaredMimeType, null));
            }

            if (artifact.Body is not RemoteArtifactBody remote)
                return VideoArtifactMaterializationResult.Fail(ExecutionFailed("Video artifact body type is unsupported."));

            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, remote.Url);
                using var response = await _httpClient.SendAsync(
                        request,
                        HttpCompletionOption.ResponseHeadersRead,
                        cancellationToken)
                    .ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                {
                    return VideoArtifactMaterializationResult.Fail(new GenerationError(
                        GenerationErrorCode.DependencyUnavailable,
                        $"Remote video artifact fetch failed with HTTP {(int)response.StatusCode}.",
                        IsRetryableStatus(response.StatusCode)));
                }

                if (response.Content is null)
                    return VideoArtifactMaterializationResult.Fail(ExecutionFailed("Remote video artifact response was empty."));

                var contentLength = response.Content.Headers.ContentLength;
                if (contentLength > _maxGeneratedVideoBytes)
                    return VideoArtifactMaterializationResult.Fail(ExecutionFailed("Remote video artifact exceeded the maximum allowed size."));

                var mimeType = ResolveMimeType(
                    artifact.DeclaredMimeType,
                    response.Content.Headers.ContentType?.MediaType);

                using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
                using var buffer = new MemoryStream();
                var readBuffer = new byte[81920];
                while (true)
                {
                    var read = await stream.ReadAsync(
                            readBuffer,
                            0,
                            readBuffer.Length,
                            cancellationToken)
                        .ConfigureAwait(false);
                    if (read == 0) break;

                    if (buffer.Length + read > _maxGeneratedVideoBytes)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed("Remote video artifact exceeded the maximum allowed size."));

                    buffer.Write(readBuffer, 0, read);
                }

                if (buffer.Length == 0)
                    return VideoArtifactMaterializationResult.Fail(ExecutionFailed("Remote video artifact response was empty."));

                return VideoArtifactMaterializationResult.Ok(buffer.ToArray(), mimeType);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return VideoArtifactMaterializationResult.Fail(new GenerationError(
                    GenerationErrorCode.Interrupted,
                    "Remote video artifact fetch was cancelled.",
                    Retryable: false));
            }
            catch (TaskCanceledException)
            {
                return VideoArtifactMaterializationResult.Fail(new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    "Remote video artifact fetch timed out.",
                    Retryable: true));
            }
            catch (HttpRequestException)
            {
                return VideoArtifactMaterializationResult.Fail(new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    "Remote video artifact fetch failed due to a transport error.",
                    Retryable: true));
            }
            catch (IOException)
            {
                return VideoArtifactMaterializationResult.Fail(new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    "Remote video artifact fetch failed while reading the response stream.",
                    Retryable: true));
            }
        }

        private static string ResolveMimeType(string? declaredMimeType, string? responseMimeType)
        {
            if (!string.IsNullOrWhiteSpace(declaredMimeType))
                return declaredMimeType!;
            if (!string.IsNullOrWhiteSpace(responseMimeType))
                return responseMimeType!;
            return "video/mp4";
        }

        private static bool IsRetryableStatus(HttpStatusCode statusCode)
        {
            var status = (int)statusCode;
            return status >= 500 && status <= 599;
        }

        private static GenerationError ExecutionFailed(string message) =>
            new(GenerationErrorCode.ExecutionFailed, message, Retryable: false);
    }

    internal sealed class VideoArtifactMaterializationResult
    {
        private VideoArtifactMaterializationResult(
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

        public static VideoArtifactMaterializationResult Ok(byte[] bytes, string mimeType) =>
            new(true, bytes, mimeType, null);

        public static VideoArtifactMaterializationResult Fail(GenerationError error) =>
            new(false, null, null, error);
    }
}
```

- [ ] **Step 4: Run materializer tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoArtifactMaterializerTests"
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Video\VideoArtifactMaterializer.cs src\Rook.Tests\Services\Vision\Video\VideoArtifactMaterializerTests.cs
git commit -m "feat(vision): materialize remote video artifacts"
```

## Task 6: Integrate Video Materializer Into VideoJobManager

**Files:**
- Modify: `src/Rook/Services/Vision/Video/VideoJobManager.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/FakeVideoProvider.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`

- [ ] **Step 1: Add fake provider remote result helper**

In `src/Rook.Tests/Services/Vision/Video/FakeVideoProvider.cs`, add:

```csharp
public static ProviderResultOutcome ResultRemote(
    string url,
    string? declaredMimeType = "video/mp4") =>
    new SuccessResultOutcome(
        new ProviderResultEnvelope(
            new[]
            {
                new ResultArtifact(
                    Role: VideoMediaRoles.Video,
                    Body: new RemoteArtifactBody(new Uri(url)),
                    DeclaredMimeType: declaredMimeType,
                    ProviderMetadata: EmptyMetadata),
            },
            EmptyMetadata));
```

Ensure the file has `using System;`.

- [ ] **Step 2: Add failing manager tests**

In `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`, add tests that inject `VideoArtifactMaterializer` with a fake HTTP handler:

```csharp
[Fact]
public async Task Remote_video_artifact_reaches_Complete_with_existing_artifact_shape()
{
    var jobId = Guid.NewGuid();
    _idGen.Sequence.Enqueue(jobId);
    _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-123");
    _provider.OnGetStatus = handle => FakeVideoProvider.StatusComplete(handle, "ignored-token");
    _provider.OnFetchResult = _ => FakeVideoProvider.ResultRemote("https://cdn.example.test/out.mp4");
    var materializer = new VideoArtifactMaterializer(
        new CapturingVideoHttpHandler(_ =>
            new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(FakeMp4),
            }));

    var mgr = Manager(videoArtifactMaterializer: materializer);
    await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
    var final = await WaitForTerminalAsync(mgr, jobId);

    Assert.Equal(VideoJobState.Complete, final.State);
    var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
    Assert.Equal("generated_video", artifact!.Kind);
    Assert.Equal("video", Assert.Single(artifact.Files).Role);
}

[Fact]
public async Task Provider_complete_then_failed_fetch_persists_Error_not_Complete()
{
    var jobId = Guid.NewGuid();
    _idGen.Sequence.Enqueue(jobId);
    _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-123");
    _provider.OnGetStatus = handle => FakeVideoProvider.StatusComplete(handle, "ignored-token");
    _provider.OnFetchResult = _ => FakeVideoProvider.ResultFailed(new VideoJobError(
        VideoErrorCode.ExecutionFailed,
        "fetch failed",
        Retryable: false));

    var mgr = Manager();
    await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
    var final = await WaitForTerminalAsync(mgr, jobId);

    Assert.Equal(VideoJobState.Error, final.State);
    Assert.Null(final.ResultArtifactId);
    Assert.Equal(VideoErrorCode.ExecutionFailed, final.Error!.Code);
}

[Fact]
public async Task Materialization_failure_preserves_provider_handle_metadata()
{
    var jobId = Guid.NewGuid();
    _idGen.Sequence.Enqueue(jobId);
    var handle = new ProviderJobHandle(
        providerJobId: "wan-123",
        statusUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123/status"),
        responseUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123"),
        cancelUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"),
        cancelHttpMethod: "PUT");
    _provider.OnSubmit = (_, _) => new QueuedSubmitOutcome(handle);
    _provider.OnGetStatus = h => new ProviderCompleteStatusOutcome(h);
    _provider.OnFetchResult = _ => FakeVideoProvider.ResultRemote("https://cdn.example.test/out.mp4");
    var materializer = new VideoArtifactMaterializer(
        new CapturingVideoHttpHandler(_ =>
            new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(Array.Empty<byte>()),
            }));

    var mgr = Manager(videoArtifactMaterializer: materializer);
    await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
    var final = await WaitForTerminalAsync(mgr, jobId);

    Assert.Equal(VideoJobState.Error, final.State);
    var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
    Assert.Equal("wan-123", latest.ProviderJobId);
    Assert.NotNull(latest.ProviderHandle);
    Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123", latest.ProviderHandle!.ResponseUrl!.ToString());
}
```

Add this helper in the test file:

```csharp
private sealed class CapturingVideoHttpHandler : HttpMessageHandler
{
    private readonly Func<HttpRequestMessage, HttpResponseMessage> _onSend;
    public CapturingVideoHttpHandler(Func<HttpRequestMessage, HttpResponseMessage> onSend) => _onSend = onSend;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
        Task.FromResult(_onSend(request));
}
```

Update the local `Manager(...)` helper signature to use the internal
constructor overload added below:

```csharp
private VideoJobManager Manager(
    TimeSpan? pollInterval = null,
    IVideoCostEstimator? estimator = null,
    VideoArtifactMaterializer? videoArtifactMaterializer = null) =>
    new(
        registry: _registry,
        mediaResolver: _resolver,
        ledger: _ledger,
        estimator: estimator ?? _estimator,
        artifactStore: _artifactStore,
        clock: _clock,
        idGenerator: _idGen,
        pollInterval: pollInterval ?? TimeSpan.FromMilliseconds(5),
        maxConcurrentJobs: VideoJobManager.DefaultMaxConcurrentJobs,
        videoArtifactMaterializer: videoArtifactMaterializer);
```

- [ ] **Step 3: Run manager tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoJobManagerTests"
```

Expected: compile failure because `VideoJobManager` does not accept `videoArtifactMaterializer`, or remote result still errors with missing inline artifact.

- [ ] **Step 4: Modify `VideoJobManager` constructor and fields**

In `VideoJobManager`, add a field:

```csharp
private readonly VideoArtifactMaterializer _videoArtifactMaterializer;
```

Do not add `VideoArtifactMaterializer` to the existing public constructor.
`VideoArtifactMaterializer` is internal, and a public constructor cannot expose
an internal parameter type.

Keep the current public constructor signature and make it chain to a new
internal constructor:

```csharp
public VideoJobManager(
    IVideoProviderRegistry registry,
    IMediaResolver mediaResolver,
    IVideoJobLedger ledger,
    IVideoCostEstimator estimator,
    ArtifactStore artifactStore,
    IVideoJobClock? clock = null,
    IVideoJobIdGenerator? idGenerator = null,
    TimeSpan? pollInterval = null,
    int maxConcurrentJobs = DefaultMaxConcurrentJobs)
    : this(
        registry,
        mediaResolver,
        ledger,
        estimator,
        artifactStore,
        clock,
        idGenerator,
        pollInterval,
        maxConcurrentJobs,
        videoArtifactMaterializer: null)
{
}
```

Add the internal constructor with the same body the public constructor had
before, plus materializer assignment:

```csharp
internal VideoJobManager(
    IVideoProviderRegistry registry,
    IMediaResolver mediaResolver,
    IVideoJobLedger ledger,
    IVideoCostEstimator estimator,
    ArtifactStore artifactStore,
    IVideoJobClock? clock,
    IVideoJobIdGenerator? idGenerator,
    TimeSpan? pollInterval,
    int maxConcurrentJobs,
    VideoArtifactMaterializer? videoArtifactMaterializer)
{
    _registry = registry ?? throw new ArgumentNullException(nameof(registry));
    _mediaResolver = mediaResolver ?? throw new ArgumentNullException(nameof(mediaResolver));
    _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
    _estimator = estimator ?? throw new ArgumentNullException(nameof(estimator));
    _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
    _clock = clock ?? new SystemVideoJobClock();
    _idGenerator = idGenerator ?? new GuidVideoJobIdGenerator();
    _pollInterval = pollInterval ?? DefaultPollInterval;
    _concurrency = new SemaphoreSlim(maxConcurrentJobs, maxConcurrentJobs);
    _videoArtifactMaterializer = videoArtifactMaterializer ?? new VideoArtifactMaterializer();
}
```

- [ ] **Step 5: Replace inline-only extraction in async and sync completion paths**

Replace calls to `TryExtractInlineVideoArtifact(...)` in `RunJobAsync` and `CompleteSyncSubmitAsync` with:

```csharp
var materialized = await MaterializeVideoArtifactAsync(
    successFetch.Envelope,
    ct).ConfigureAwait(false);
if (!materialized.Success)
{
    current = AppendTransition(
        current,
        VideoJobState.Error,
        error: materialized.Error);
    running.LatestRecord = current;
    return;
}

var videoBytes = materialized.Bytes!;
var videoMimeType = materialized.MimeType!;
```

For the sync path, use `success.Envelope`.

Add this helper:

```csharp
private async Task<VideoArtifactMaterializationResult> MaterializeVideoArtifactAsync(
    ProviderResultEnvelope envelope,
    CancellationToken ct)
{
    foreach (var artifact in envelope.Artifacts)
    {
        if (artifact.Role == VideoMediaRoles.Video)
            return await _videoArtifactMaterializer.MaterializeAsync(artifact, ct)
                .ConfigureAwait(false);
    }

    return VideoArtifactMaterializationResult.Fail(MissingVideoArtifactError());
}
```

Rename `MissingInlineVideoArtifactError` to `MissingVideoArtifactError` and update the message:

```csharp
private static GenerationError MissingVideoArtifactError() =>
    new(
        GenerationErrorCode.ExecutionFailed,
        "Provider result envelope did not contain a video artifact.",
        Retryable: false);
```

Leave `ExtensionFromMime` unchanged.

- [ ] **Step 6: Run manager tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VideoArtifactMaterializerTests"
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Video\VideoJobManager.cs src\Rook.Tests\Services\Vision\Video\FakeVideoProvider.cs src\Rook.Tests\Services\Vision\Video\VideoJobManagerTests.cs
git commit -m "feat(vision): route video provider artifacts through materializer"
```

## Task 7: Factory Wiring and Model Descriptor Regression

**Files:**
- Modify: `src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`

- [ ] **Step 1: Add failing factory/list-model tests**

In `VideoSubsystemFactoryTests.cs`, modify `Build_RegistryEnumeratesExactVeoCapabilitiesModelIdSet` so the expected set includes the new fal model:

```csharp
var expected = VeoCapabilities.Models.Keys
    .Concat(new[] { "fal-ai/wan/v2.7/text-to-video" })
    .OrderBy(k => k, StringComparer.Ordinal)
    .ToArray();
```

Then add:

```csharp
[Fact]
public void Build_registers_fal_wan_t2v_model()
{
    var (secrets, artifacts) = FreshDeps();
    var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
    try
    {
        var fal = Assert.Single(
            bundle.Registry.EnumerateAllModels(),
            m => m.ModelId == "fal-ai/wan/v2.7/text-to-video");
        Assert.Equal("fal", fal.ProviderName);
        Assert.Equal(PricingKind.PerSecond, fal.PricingKind);
        Assert.Equal(new[] { VideoMode.T2V }, fal.Capability.Modes);
        Assert.False(fal.Capability.SupportsReferenceImages);
        Assert.Equal(0, fal.Capability.MaxReferenceImages);
        Assert.Empty(fal.Capability.Must8sWith);
    }
    finally { bundle.Manager.Dispose(); }
}

[Fact]
public void Build_does_not_register_fal_i2v_model()
{
    var (secrets, artifacts) = FreshDeps();
    var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
    try
    {
        Assert.DoesNotContain(
            bundle.Registry.EnumerateAllModels(),
            m => m.ModelId == "fal-ai/wan/v2.7/image-to-video");
    }
    finally { bundle.Manager.Dispose(); }
}
```

- [ ] **Step 2: Run factory tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoSubsystemFactoryTests"
```

Expected: fal model descriptor test fails because factory registers only Veo.

- [ ] **Step 3: Wire fal provider in factory**

In `VideoSubsystemFactory.Build(...)`, add:

```csharp
var falVideoProvider = new Rook.Services.Vision.Video.Fal.FalVideoProvider(
    () => generationSecrets.GetSecret(GenerationSecretKeys.FalApiKey));
```

Update registrations:

```csharp
var registry = new DefaultVideoProviderRegistry(
    new IVideoProviderRegistration[]
    {
        new VeoProviderRegistration(veoProvider),
        new Rook.Services.Vision.Video.Fal.FalVideoProviderRegistration(falVideoProvider),
    });
```

- [ ] **Step 4: Run factory and model route tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VideoSubsystemFactoryTests|FullyQualifiedName~VideoOpHandlerTests"
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Video\VideoSubsystemFactory.cs src\Rook.Tests\Services\Vision\Video\VideoSubsystemFactoryTests.cs
git commit -m "feat(vision): register fal text-to-video model"
```

## Task 8: Gated fal Video Live Smoke

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoLiveSmokeTests.cs`

- [ ] **Step 1: Write skipped-by-default live smoke**

Create `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoLiveSmokeTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoLiveSmokeTests
    {
        private const string LiveEnabledEnvVar = "ROOK_FAL_VIDEO_LIVE";
        private const string ApiKeyEnvVar = "ROOK_FAL_API_KEY";
        private const string AcceptSpendEnvVar = "ROOK_ACCEPT_FAL_SPEND";

        [Fact]
        public async Task Wan_t2v_live_smoke_returns_remote_video_artifact_when_explicitly_enabled()
        {
            if (!string.Equals(
                    Environment.GetEnvironmentVariable(LiveEnabledEnvVar),
                    "1",
                    StringComparison.Ordinal))
            {
                return;
            }

            var apiKey = Environment.GetEnvironmentVariable(ApiKeyEnvVar);
            Assert.False(
                string.IsNullOrWhiteSpace(apiKey),
                $"{ApiKeyEnvVar} must be set when {LiveEnabledEnvVar}=1.");

            Assert.True(
                string.Equals(
                    Environment.GetEnvironmentVariable(AcceptSpendEnvVar),
                    "1",
                    StringComparison.Ordinal),
                $"{AcceptSpendEnvVar}=1 must be set when {LiveEnabledEnvVar}=1.");

            var provider = new FalVideoProvider(() => apiKey);
            var request = new VideoGenerationRequest(
                Model: FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "short architectural clay massing orbit, simple daylight",
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

            var submit = await provider.SubmitAsync(
                request,
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);
            var queued = Assert.IsType<QueuedSubmitOutcome>(submit);

            ProviderJobHandle handle = queued.Handle;
            for (var i = 0; i < 90; i++)
            {
                var status = await provider.GetStatusAsync(handle, CancellationToken.None);
                if (status is ProviderCompleteStatusOutcome complete)
                {
                    handle = complete.UpdatedHandle;
                    break;
                }

                if (status is FailedStatusOutcome failed)
                    throw new Xunit.Sdk.XunitException(failed.Error.Message);

                await Task.Delay(TimeSpan.FromSeconds(5));
            }

            var fetch = await provider.FetchResultAsync(handle, CancellationToken.None);
            var success = Assert.IsType<SuccessResultOutcome>(fetch);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(VideoMediaRoles.Video, artifact.Role);
            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.True(remote.Url.IsAbsoluteUri);
            Assert.True(remote.Url.Scheme == Uri.UriSchemeHttp || remote.Url.Scheme == Uri.UriSchemeHttps);

            var materialized = await new VideoArtifactMaterializer()
                .MaterializeAsync(artifact, CancellationToken.None);
            Assert.True(
                materialized.Success,
                materialized.Error?.Message ?? "Live video materialization failed.");
            Assert.NotEmpty(materialized.Bytes!);
            Assert.Equal("video/mp4", materialized.MimeType);
        }
    }
}
```

- [ ] **Step 2: Run live smoke test without env vars**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~FalVideoLiveSmokeTests"
```

Expected: pass without making a live fal request because `ROOK_FAL_VIDEO_LIVE` is not `1`.

- [ ] **Step 3: Commit**

```powershell
git add src\Rook.Tests\Services\Vision\Video\Fal\FalVideoLiveSmokeTests.cs
git commit -m "test(vision): add gated fal video live smoke"
```

## Task 9: Final Verification

**Files:**
- No planned file edits.

- [ ] **Step 1: Run targeted fal/video tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~FalVideo|FullyQualifiedName~VideoArtifactMaterializer|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VideoOpHandlerTests|FullyQualifiedName~VideoSubsystemFactoryTests|FullyQualifiedName~VideoJobRecordFactoryByteIdentityTests|FullyQualifiedName~JsonlVideoJobLedgerTests"
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full managed test suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: all tests pass. This is a managed test suite; do not claim native `RookNative` build verification from this command.

- [ ] **Step 3: Verify no native files changed**

Run:

```powershell
git diff --name-only origin/main...HEAD | rg "^src/RookNative/" ; if ($LASTEXITCODE -eq 1) { "no native changes" }
```

Expected:

```text
no native changes
```

- [ ] **Step 4: Verify fal scope guards**

Run:

```powershell
rg -n "image-to-video|audio_url|negative_prompt|enable_prompt_expansion" src\Rook\Services\Vision\Video src\Rook.Tests\Services\Vision\Video
```

Expected:

- No production registration for `fal-ai/wan/v2.7/image-to-video`.
- No production request body field `audio_url`.
- No public fal video option accepting `negative_prompt`.
- `enable_prompt_expansion` appears only in `FalVideoProvider` request-body construction and tests that assert the fixed `true` value or strict rejection as an option.

- [ ] **Step 5: Inspect worktree after verification**

Run:

```powershell
git status --short
```

Expected: no unstaged or uncommitted files. If the status shows files changed
because a verification command exposed a compile or test issue, fix those files,
rerun the failing verification command, and commit the concrete fix with a
message that names the corrected behavior.

## Self-Review Checklist

- Spec coverage:
  - Single T2V model: Task 2, Task 7.
  - Empty fal options: Task 2, Task 4.
  - fal queue lifecycle: Task 3.
  - provider handle URL fields: Task 3, Task 6.
  - remote mp4 materialization: Task 5, Task 6.
  - Veo byte-identity fixtures: Task 9.
  - fake cancel coverage: Task 3, existing manager cancel tests.
  - live smoke gated by env vars: Task 8.
  - no native changes: Task 9.
- Type consistency:
  - `FalVideoOptions`, `FalVideoOptionsCodec`, `FalVideoProvider`, and `FalVideoCapabilities.WanT2v` names are used consistently.
  - `ProviderJobHandle.CancelHttpMethod` is verified before tests pin `PUT`.
  - `VideoArtifactMaterializer` returns `VideoArtifactMaterializationResult` consumed by `VideoJobManager`.
- Scope:
  - No Replicate, Tencent, 3D, I2V, audio, settings UI, picker UI, or dynamic catalog work appears in implementation tasks.
