using System;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Framing;
using Rook.Tests.Services.Vision.Video.Fal;
using Xunit;
using System.Linq;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFramingQuoteTests
    {
        [Fact]
        public async Task Dispatch_DerivedTamperAndRepricingBelowCapRequireReconfirmation()
        {
            using var rig = new Rig(); var prepared = await rig.Quotes.PrepareSubmissionAsync(rig.Intent, default); using var held = prepared.Bundle!; var accepted = prepared.Quote!;
            var evidence = held.SourcePreparation!; evidence["slots"]![0]!["recipe"]!["offset_x"] = 271;
            using var tampered = rig.Cache.Admit("tampered", new VideoPreparedBundle(held.Originals.Retain(), held.Prepared.Retain(), evidence))!;
            using (var phase = await rig.Resources.AcquireAsync(default))
            {
                var result = await rig.Quotes.RevalidateForDispatchAsync(rig.Intent, tampered, accepted, new(accepted.EstimateFingerprint, 10m), rig.Coordinator.SelectInitial(accepted), phase, default);
                Assert.Equal("estimate_stale", result.Error!.ProviderErrorCode);
            }
            var changed = new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b => b.SubmitEndpoint == "fal-ai/veo3.1/image-to-video"
                ? b with { RatesUsdPerSecond = new System.Collections.Generic.Dictionary<string, decimal> { ["1080p"] = .90m }, PricingRevision = "changed" } : b));
            var coordinator = new VideoSubmissionCoordinator(rig.Coordinator.Registry, changed, new VideoRouteQuoteTests.Secrets());
            var quotes = new VideoRouteQuoteService(coordinator, new ArtifactOnlyVideoMediaResolver(rig.Store, rig.Resources), new FakeVideoJobClock(), rig.Preparation);
            using var freshPhase = await rig.Resources.AcquireAsync(default);
            var repriced = await quotes.RevalidateForDispatchAsync(rig.Intent, held, accepted, new(accepted.EstimateFingerprint, 10m), rig.Coordinator.SelectInitial(accepted), freshPhase, default);
            Assert.Equal("estimate_stale", repriced.Error!.ProviderErrorCode);
        }
        internal sealed class Rig : IDisposable
        {
            internal readonly string Root = Path.Combine(Path.GetTempPath(), "rook-framed-quote-" + Guid.NewGuid().ToString("N"));
            internal readonly ArtifactStore Store;
            internal readonly VideoPreparationResources Resources = new();
            internal readonly VideoFramingCache Cache;
            internal readonly VideoFramingPreparationService Preparation;
            internal readonly VideoSubmissionCoordinator Coordinator;
            internal readonly VideoRouteQuoteService Quotes;
            internal readonly VideoRequestIntent Intent;
            internal readonly MediaRef Source;
            internal DateTimeOffset Now = DateTimeOffset.UtcNow;
            internal Rig(IVideoProvider? google = null, FalVideoProvider? fal = null, VideoRouteQuoteTests.Secrets? secrets = null)
            {
                Store = new ArtifactStore(Root); Cache = new VideoFramingCache(() => Now);
                var artifact = Store.Create("captured_viewport", new[] { new BlobInput("image", File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("rgb-1166x912.png")), "png") });
                Source = MediaRef.ForArtifact(artifact.Id, "image");
                var media = new ArtifactOnlyVideoMediaResolver(Store, Resources);
                Preparation = new(media, Cache, new FfmpegVideoSourceRenderer(bundledPath: () => VideoSourceRendererTests.Binary), Resources);
                var catalog = FalVeoCompatibilityTests.ActiveCatalog();
                var registry = new DefaultVideoProviderRegistry(new IVideoProviderRegistration[] { new VeoProviderRegistration(google ?? new VeoProvider(() => "test-only")), new FalVeoProviderRegistration(fal ?? new FalVideoProvider(() => "test-only"), catalog) });
                Coordinator = new(registry, catalog, secrets ?? new VideoRouteQuoteTests.Secrets());
                Quotes = new(Coordinator, media, new FakeVideoJobClock(), Preparation);
                Intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", mode: VideoMode.I2V, resolution: "1080p", startFrame: Source).With(sourceFraming: SourceFramingMode.Fit), new JsonObject());
            }
            public void Dispose() { Cache.Dispose(); if (Directory.Exists(Root)) Directory.Delete(Root, true); }
        }
        [Fact]
        public async Task Quote_FingerprintBindsRecipesButNotPreviewIds()
        {
            using var rig = new Rig();
            var previewRequest = new VideoFramingPreviewRequest(rig.Intent.Request.Model, VideoMode.I2V, new[] { new VideoFramingSourceSlot("start_frame", rig.Source) }, "1080p", "16:9");
            var preview = await rig.Preparation.PreviewAsync(previewRequest, default);
            var quote = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
            Assert.Equal(preview.Fit!.Slots[0].Sha256, quote.SourcePreparation!["slots"]![0]!["prepared_sha256"]!.GetValue<string>());
            Assert.DoesNotContain(preview.Fit.Slots[0].PreviewId.ToString("D"), quote.CanonicalSnapshot.ToJsonString());
            var fill = (await rig.Quotes.QuoteAsync(VideoRequestIntent.Normalize(rig.Intent.Request.With(sourceFraming: SourceFramingMode.Fill), new JsonObject()), default)).Quote!;
            Assert.NotEqual(quote.EstimateFingerprint, fill.EstimateFingerprint);
            var copy = quote.SourcePreparation!; copy["mode"] = "tampered"; Assert.Equal("fit", quote.SourcePreparation!["mode"]!.GetValue<string>());
            rig.Now += TimeSpan.FromMinutes(31); rig.Cache.Sweep();
            var regenerated = await rig.Preparation.PreviewAsync(previewRequest, default);
            var again = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
            Assert.NotEqual(preview.Fit.Slots[0].PreviewId, regenerated.Fit!.Slots[0].PreviewId);
            Assert.Equal(quote.EstimateFingerprint, again.EstimateFingerprint); Assert.Equal(0, rig.Resources.ActiveBundles);
        }
        [Fact]
        public async Task Dispatch_SourceAbaCannotValidateDifferentPreparedBytes()
        {
            using var rig = new Rig(); var accepted = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
            string path = rig.Store.GetBlobAbsolutePath(rig.Source.ArtifactId!.Value, "image"); var a = File.ReadAllBytes(path);
            File.WriteAllBytes(path, File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("square.png")));
            var prepared = await rig.Quotes.PrepareSubmissionAsync(rig.Intent, default); using var heldB = prepared.Bundle!;
            File.WriteAllBytes(path, a);
            using var phase = await rig.Resources.AcquireAsync(default);
            var check = await rig.Quotes.RevalidateForDispatchAsync(rig.Intent, heldB, accepted,
                new(accepted.EstimateFingerprint, accepted.MaximumEstimatedCostUsd), rig.Coordinator.SelectInitial(accepted), phase, default);
            Assert.Equal("estimate_stale", check.Error!.ProviderErrorCode);
        }
    }
}
