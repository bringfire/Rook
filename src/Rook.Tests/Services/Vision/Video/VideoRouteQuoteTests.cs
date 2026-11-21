using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoRouteQuoteTests
    {
        [Fact]
        public void Configured_fractional_duration_bypasses_legacy_capabilities_and_integer_quantity()
        {
            using var files = Rook.Tests.Services.Vision.Fal.FalDeclarativePricingTests.Seconds();
            var normalized = Rook.Tests.Services.Vision.Fal.FalDeclarativePricingTests.Normalize(files, new JsonObject());
            var model = files.Compile().Catalog!.Definitions[0];
            var strategy = new Rook.Services.Vision.Fal.Models.FalDeclarativePricing();
            var registry = new DefaultVideoProviderRegistry(new[] { new ConfiguredFalVideoRegistration(model,
                new Rook.Services.Vision.Fal.FalConfiguredExecutor(new Rook.Services.Vision.Fal.FalApiClient(), () => null),
                new Rook.Services.Vision.Fal.Models.FalAdapterRegistry(), strategy.ForVideo(model, new Rook.Services.Vision.Fal.Models.FalAdapterRegistry())) });
            Assert.True(registry.TryResolve(model.ModelId, out var resolved));
            var shell = new VideoGenerationRequest(model.ModelId, VideoMode.T2V, 0, "placeholder", "placeholder", null, null, null, null, null,
                new Rook.Services.Vision.Fal.Models.FalModelOptions(normalized.SuppliedInput, "text_to_video"), 1);
            var estimate = new VideoCostEstimator().Estimate(resolved!, shell);
            Assert.True(estimate.Success, estimate.Error?.Message); Assert.Equal(.30m, estimate.Estimate!.DollarsUsd);
            Assert.Equal(PricingKind.External, estimate.Estimate.Pricing.Kind);
            Assert.Null(estimate.Estimate.Pricing.UnitPriceUsd);
            Assert.Null(estimate.Estimate.DurationSeconds);
            Assert.Equal(1.5m, estimate.Estimate.ConfiguredRequest!.EffectiveRequestFields["duration_seconds"]!.GetValue<decimal>());
            var conflicting = shell.With(options: new Rook.Services.Vision.Fal.Models.FalModelOptions(
                new Rook.Services.Vision.Fal.Models.FalModelInput(operationId: "image_to_video"), "text_to_video"));
            Assert.False(new VideoCostEstimator().Estimate(resolved!, conflicting).Success);
            Assert.False(resolved!.PricingModel.Estimate(conflicting, resolved.Capability).Success);
        }
        internal sealed class Secrets : IGenerationSecretStore
        {
            public string? Google = "google";
            public string? Fal = "fal";
            public int FalReads;
            public bool ThrowFal;
            public string? GetSecret(string key) { if (key == GenerationSecretKeys.FalApiKey) { FalReads++; if (ThrowFal) throw new Exception("secret raw"); return Fal; } return Google; }
            public bool HasSecret(string key) => key == GenerationSecretKeys.FalApiKey ? !string.IsNullOrWhiteSpace(Fal) : !string.IsNullOrWhiteSpace(Google);
            public string? GetPreview(string key) => null;
            public void SetSecret(string key, string value) => throw new NotSupportedException();
            public void RemoveSecret(string key) => throw new NotSupportedException();
        }
        internal sealed class Media : IMediaResolver
        {
            public Dictionary<MediaRef, ResolvedMedia> Values = new();
            public Task<MediaResolutionResult> ResolveAllAsync(IReadOnlyList<MediaRef> refs, CancellationToken ct) { ct.ThrowIfCancellationRequested(); return Task.FromResult(MediaResolutionResult.Ok(Values)); }
        }
        internal static VideoRouteQuoteService Service(Secrets? secrets = null, Media? media = null, FalVeoBindingCatalog? catalog = null)
        {
            catalog ??= FalVeoCompatibilityTests.ActiveCatalog();
            var registry = new DefaultVideoProviderRegistry(new IVideoProviderRegistration[] { new VeoProviderRegistration(new FakeVideoProvider()), new FalVeoProviderRegistration(new FalVideoProvider(() => "fal"), catalog) });
            return new VideoRouteQuoteService(new VideoSubmissionCoordinator(registry, catalog, secrets ?? new Secrets()), media ?? new Media(), new FakeVideoJobClock());
        }
        internal static VideoRequestIntent Intent() => VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", resolution: "1080p"), new JsonObject());

        [Fact]
        public void Configured_direct_quote_has_one_candidate_and_does_not_select_Google_fallback()
        {
            using var files = Rook.Tests.Services.Vision.Fal.FalDeclarativePricingTests.Seconds();
            var request = Rook.Tests.Services.Vision.Fal.FalDeclarativePricingTests.Normalize(files, new JsonObject());
            using var media = Rook.Tests.Services.Vision.Fal.FalQuoteServiceTests.Capture(request);
            var secrets = new Secrets { ThrowFal = true };
            var result = Service(secrets).QuoteConfigured(request, media);
            Assert.Null(result.Error); Assert.Equal(.30m, result.Quote!.MaximumEstimatedCostUsd);
            Assert.Single(result.Quote.ToJson()["candidates"]!.AsArray()); Assert.Equal(0, secrets.FalReads);
        }

        [Theory]
        [InlineData("image-to-video")]
        [InlineData("first-last-frame-to-video")]
        [InlineData("reference-to-video")]
        public async Task QuotesAndCapsUseSelectedEndpointPrices(string endpoint)
        {
            var catalog = new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b =>
                b.SubmitEndpoint == "fal-ai/veo3.1/" + endpoint ? b with {
                    RatesUsdPerSecond = new Dictionary<string, decimal> { ["1080p"] = .90m },
                    PricingSource = "endpoint-specific", PricingRevision = "endpoint-revision"
                } : b));
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var media = new Media(); media.Values[input] = FalVeoCompatibilityTests.Image(1280, 720);
            var request = Intent().Request;
            request = endpoint switch {
                "image-to-video" => request.With(mode: VideoMode.I2V, startFrame: input),
                "first-last-frame-to-video" => request.With(mode: VideoMode.Interp, startFrame: input, endFrame: input),
                _ => request.With(referenceFrames: new[] { input })
            };
            var service = Service(new Secrets { Google = null }, media, catalog);
            var quote = (await service.QuoteAsync(VideoRequestIntent.Normalize(request, new JsonObject()), default)).Quote!;
            Assert.NotNull(quote);
            Assert.Equal(7.20m, quote.PrimaryEstimate.DollarsUsd);
            Assert.Equal(8, quote.PrimaryEstimate.DurationSeconds);
            Assert.Equal(7.20m, quote.MaximumEstimatedCostUsd);
            Assert.Equal(.90m, quote.PrimaryEstimate.Pricing.UnitPriceUsd);
            Assert.Equal(PricingKind.PerSecond, quote.PrimaryEstimate.Pricing.Kind);
            Assert.Equal("endpoint-specific", quote.PrimaryEstimate.Pricing.PricingSource);
            var selected = quote.Candidates.Single(c => c.Model.ProviderName == "fal");
            Assert.Equal("cost_cap_exceeded", service.ValidateConfirmation(quote, new(null, 3.20m), selected)!.ProviderErrorCode);
            Assert.Null(service.ValidateConfirmation(quote, new(quote.EstimateFingerprint, 7.20m), selected));
            var directRequest = selected.Request;
            var direct = new VideoCostEstimator().Estimate(selected.Model, directRequest);
            Assert.Equal(7.20m, direct.Estimate!.DollarsUsd);
            var textQuote = (await service.QuoteAsync(Intent(), default)).Quote!;
            Assert.Equal(3.20m, textQuote.PrimaryEstimate.DollarsUsd);
        }

        [Fact]
        public async Task MissingSelectedEndpointPriceCannotBorrowTextEndpointPrice()
        {
            var catalog = new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b =>
                b.SubmitEndpoint.EndsWith("/image-to-video", StringComparison.Ordinal)
                    ? b with { RatesUsdPerSecond = new Dictionary<string, decimal>() } : b));
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var media = new Media(); media.Values[input] = FalVeoCompatibilityTests.Image(1280, 720);
            var intent = VideoRequestIntent.Normalize(Intent().Request.With(mode: VideoMode.I2V, startFrame: input), new JsonObject());
            var result = await Service(new Secrets { Google = null }, media, catalog).QuoteAsync(intent, default);
            Assert.Null(result.Quote);
            Assert.NotNull(result.Error);
        }

        [Fact]
        public void CanonicalizationPreservesOrderRepeatsAndProvenance()
        {
            Assert.Equal(VideoEstimateFingerprint.Compute(new JsonObject { ["a"] = 2, ["z"] = 1 }), VideoEstimateFingerprint.Compute(new JsonObject { ["z"] = 1, ["a"] = 2 }));
            Assert.NotEqual(VideoEstimateFingerprint.Compute(new JsonObject { ["a"] = new JsonArray(1, 2, 1) }), VideoEstimateFingerprint.Compute(new JsonObject { ["a"] = new JsonArray(1, 1, 2) }));
            var previous = CultureInfo.CurrentCulture;
            try { CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("fr-FR"); Assert.Equal(VideoEstimateFingerprint.Compute(new JsonObject { ["price"] = 1.20m }), VideoEstimateFingerprint.Compute(JsonNode.Parse("{\"price\":1.20}")!.AsObject())); }
            finally { CultureInfo.CurrentCulture = previous; }
        }

        [Fact]
        public async Task CapUsesCurrentSelectedRouteAndFingerprintIncludesSeedSupport()
        {
            var original = (await Service().QuoteAsync(Intent(), default)).Quote!;
            var oldFal = original.Candidates.Single(c => c.Model.ProviderName == "fal");
            var catalog = new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b => b with { RatesUsdPerSecond = new Dictionary<string, decimal> { ["720p"] = 2m, ["1080p"] = 2m, ["4k"] = 2m } }));
            var service = Service(catalog: catalog); var current = (await service.QuoteAsync(Intent(), default)).Quote!;
            Assert.Equal("cost_cap_exceeded", service.ValidateConfirmation(current, new(null, 4m), oldFal)?.ProviderErrorCode);
            var changedSeed = (await Service(catalog: new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b => b with { SupportsSeed = false }))).QuoteAsync(Intent(), default)).Quote!;
            Assert.NotEqual(original.EstimateFingerprint, changedSeed.EstimateFingerprint);
        }
        [Fact]
        public async Task FingerprintChangesBelowCapAndForLowerPrices()
        {
            var original = (await Service().QuoteAsync(Intent(), default)).Quote!;
            var revisedCatalog = new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b => b with { PricingRevision = "lower", RatesUsdPerSecond = new Dictionary<string, decimal> { ["720p"] = .10m, ["1080p"] = .10m, ["4k"] = .10m } }));
            var service = Service(catalog: revisedCatalog);
            var revised = (await service.QuoteAsync(Intent(), default)).Quote!;
            Assert.NotEqual(original.EstimateFingerprint, revised.EstimateFingerprint);
            Assert.Equal("estimate_stale", service.ValidateConfirmation(revised, new(original.EstimateFingerprint, 100m), null)!.ProviderErrorCode);
        }

        [Fact]
        public async Task ByteReplacementUnderSameArtifactIdInvalidatesQuote()
        {
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var media = new Media();
            media.Values[input] = FalVeoCompatibilityTests.Image(1280, 720);
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: input), new JsonObject());
            var service = Service(media: media);
            var before = (await service.QuoteAsync(intent, default)).Quote!;
            var data = media.Values[input].Bytes.Concat(new byte[] { 1 }).ToArray();
            media.Values[input] = new(data, "image/png");
            var after = (await service.QuoteAsync(intent, default)).Quote!;
            Assert.NotEqual(before.EstimateFingerprint, after.EstimateFingerprint);
        }

        [Fact]
        public async Task PreparedBytesCannotBeValidatedByAnABARead()
        {
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var media = new Media();
            var a = FalVeoCompatibilityTests.Image(1280, 720);
            media.Values[input] = a;
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: input), new JsonObject());
            var service = Service(media: media);
            var accepted = (await service.QuoteAsync(intent, default)).Quote!;
            media.Values[input] = new(a.Bytes.Concat(new byte[] { 1 }).ToArray(), a.MimeType);
            var preparedB = VideoPreparedMediaSnapshot.Capture(intent.Request, media.Values);
            media.Values[input] = a;
            var current = (await service.QuoteAsync(intent, default)).Quote!;
            Assert.Equal(accepted.EstimateFingerprint, current.EstimateFingerprint);
            Assert.Equal("estimate_stale", service.ValidatePreparedMedia(preparedB, current)!.ProviderErrorCode);
            Assert.Equal("estimate_stale", service.ValidatePreparedMedia(preparedB, accepted)!.ProviderErrorCode);
            Assert.NotEqual(accepted.EstimateFingerprint, (await service.QuotePreparedAsync(intent, preparedB, default)).Quote!.EstimateFingerprint);
        }

        [Fact]
        public async Task NormalQuotedFallbackDoesNotInvalidateFingerprint()
        {
            var service = Service();
            var quote = (await service.QuoteAsync(Intent(), default)).Quote!;
            var fal = quote.Candidates.Single(c => c.Model.ProviderName == "fal");
            Assert.Equal(3.20m, fal.Estimate!.DollarsUsd);
            Assert.Equal(3.20m, quote.MaximumEstimatedCostUsd);
            Assert.Null(service.ValidateConfirmation(quote, new(quote.EstimateFingerprint, 3.20m), fal));
        }

        [Fact]
        public async Task LegacyConfirmationContractsRemainDistinct()
        {
            var service = Service();
            var quote = (await service.QuoteAsync(Intent(), default)).Quote!;
            Assert.Null(service.ValidateConfirmation(quote, new(null, null), null));
            Assert.Null(service.ValidateConfirmation(quote, new(null, 4m), null));
            Assert.NotNull(service.ValidateConfirmation(quote, new(quote.EstimateFingerprint, null), null));
            Assert.NotNull(service.ValidateConfirmation(quote, new(null, 1m), quote.Candidates.Last()));
        }

        [Fact]
        public async Task UnusedFalSecretIsNotRead()
        {
            var secrets = new Secrets { ThrowFal = true };
            Assert.NotNull((await Service(secrets).QuoteAsync(Intent(), default)).Quote);
            Assert.Equal(0, secrets.FalReads);
        }

        [Fact]
        public async Task UnknownPriceCannotBecomeZero()
        {
            var catalog = new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b => b with { RatesUsdPerSecond = new Dictionary<string, decimal>() }));
            var result = await Service(new Secrets { Google = null }, catalog: catalog).QuoteAsync(Intent(), default);
            Assert.Null(result.Quote);
            Assert.NotNull(result.Error);
        }
    }
}
