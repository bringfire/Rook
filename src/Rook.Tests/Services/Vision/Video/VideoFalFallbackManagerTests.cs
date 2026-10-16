using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoFalFallbackManagerTests
    {
        [Theory]
        [InlineData(false, false)]
        [InlineData(false, true)]
        [InlineData(true, false)]
        [InlineData(true, true)]
        public async Task EndpointPriceControlsDispatchCapAndDurablePricing(bool rejectedGoogle, bool sufficientCap)
        {
            var catalog = new FalVeoBindingCatalog(FalVeoCompatibilityTests.ActiveCatalog().All.Select(b =>
                b.SubmitEndpoint == "fal-ai/veo3.1/image-to-video" ? b with {
                    RatesUsdPerSecond = new Dictionary<string, decimal> { ["1080p"] = .90m }, PricingSource = "i2v-specific"
                } : b));
            using var rig = new Rig(catalog: catalog);
            if (rejectedGoogle) rig.Google.Submit = (r, ct) => Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "rejected", false, null, "rook.veo.key_rejected")));
            else rig.Secrets.Google = null;
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            rig.Media.Values[input] = FalVeoCompatibilityTests.Image(1280, 720);
            var intent = VideoRequestIntent.Normalize(VideoRouteQuoteTests.Intent().Request.With(mode: VideoMode.I2V, startFrame: input), new JsonObject());
            var submit = await rig.Submit(intent, new(null, sufficientCap ? 7.20m : 3.20m));
            if (!sufficientCap && !rejectedGoogle)
            {
                Assert.Null(submit.JobId);
                Assert.Equal("cost_cap_exceeded", submit.GenerationError!.ProviderErrorCode);
                Assert.Equal(0, rig.Fal.Submits);
                return;
            }
            Assert.NotNull(submit.JobId); await Limit(rig.Done.Task);
            var record = rig.Record(submit.JobId!.Value);
            if (!sufficientCap)
            {
                Assert.Equal(VideoJobState.Error, record.State);
                Assert.Equal("cost_cap_exceeded", record.Error!.ProviderErrorCode);
                Assert.Equal(0, rig.Fal.Submits);
                return;
            }
            Assert.Equal(VideoJobState.Complete, record.State);
            Assert.Equal("fal", record.Provider);
            Assert.Equal(.90m, record.Pricing.UnitPriceUsd);
            Assert.Equal(7.20m, record.Pricing.TotalUsd);
            Assert.Equal("i2v-specific", record.Pricing.PricingSource);
            Assert.Equal(1, rig.Fal.Submits);
        }

        internal static byte[] ValidVideoBytes()
        {
            var root = new DirectoryInfo(AppContext.BaseDirectory);
            while (root != null && !File.Exists(Path.Combine(root.FullName, "Rook.sln"))) root = root.Parent;
            return File.ReadAllBytes(Path.Combine(root!.FullName, "third_party/ffmpeg/fixtures/sidecar-smoke-h264.mp4"));
        }
        internal static TaskCompletionSource<T> Signal<T>() => new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal static async Task<T> Limit<T>(Task<T> task) { if (await Task.WhenAny(task, Task.Delay(10000)) != task) throw new TimeoutException("Test barrier was not reached."); return await task; }
        internal sealed class Provider : IVideoProvider, IPreparedMediaVideoProvider
        {
            public string ProviderName { get; set; } = "veo";
            internal int Submits, Cancels, Polls;
            internal Func<VideoPreparedMediaSnapshot, Task>? Prepare;
            internal Func<ProviderJobHandle, CancellationToken, Task<ProviderResultOutcome>>? Fetch;
            internal Func<VideoGenerationRequest, CancellationToken, Task<ProviderSubmitOutcome>> Submit = (r, ct) => Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(new ProviderJobHandle(r.Prompt ?? "handle")));
            internal Func<ProviderJobHandle, CancellationToken, Task<ProviderStatusOutcome>> Poll = (h, ct) => Task.FromResult<ProviderStatusOutcome>(new ProviderCompleteStatusOutcome(h));
            public async Task<ProviderSubmitOutcome> SubmitPreparedAsync(VideoGenerationRequest request, VideoPreparedMediaSnapshot media, Action beforeDispatch, CancellationToken ct, VideoPreparationLease? phase = null) { if (Prepare != null) await Prepare(media); beforeDispatch(); Interlocked.Increment(ref Submits); return await Submit(request, ct); }
            public Task<ProviderSubmitOutcome> SubmitAsync(VideoGenerationRequest r, IReadOnlyDictionary<MediaRef, ResolvedMedia> m, CancellationToken ct) => throw new InvalidOperationException("Mutable submit seam used.");
            public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle h, CancellationToken ct) { Interlocked.Increment(ref Polls); return Poll(h, ct); }
            public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle h, CancellationToken ct) { Interlocked.Increment(ref Cancels); return Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome()); }
            public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle h, CancellationToken ct) => Fetch?.Invoke(h, ct) ?? Task.FromResult<ProviderResultOutcome>(new SuccessResultOutcome(new ProviderResultEnvelope(new[] { new ResultArtifact("video", new InlineArtifactBody(ValidVideoBytes()), "video/mp4", new Dictionary<string, JsonNode>()) }, new Dictionary<string, JsonNode>())));
        }
        internal sealed class Ledger : IVideoJobLedger
        {
            internal readonly JsonlVideoJobLedger Inner;
            internal Action<VideoJobRecord>? BeforeAppend;
            internal Ledger(string path) { Inner = new(path); }
            public void Append(VideoJobRecord record) { BeforeAppend?.Invoke(record); Inner.Append(record); }
            public VideoJobLedgerReadResult ReadAll() => Inner.ReadAll();
        }
        internal sealed class Registration : IVideoProviderRegistration
        {
            private readonly FalVeoProviderRegistration _base;
            internal Registration(IVideoProvider provider, FalVeoBindingCatalog catalog) { Provider = provider; _base = new(new FalVideoProvider(() => "unused"), catalog); }
            public string ProviderName => "fal";
            public IVideoProvider Provider { get; }
            public IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec => _base.OptionsCodec;
            public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models => _base.Models;
            public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _base.SecretRequirements;
        }
        internal sealed class Rig : IDisposable
        {
            internal readonly string DirectoryPath = Path.Combine(Path.GetTempPath(), "rook-route-" + Guid.NewGuid());
            internal readonly VideoRouteQuoteTests.Secrets Secrets = new();
            internal readonly VideoRouteQuoteTests.Media Media = new();
            internal readonly Provider Google = new();
            internal readonly Provider Fal = new() { ProviderName = "fal" };
            internal readonly VideoExecutionBudgetTests.Timer Timer = new();
            internal readonly FakeVideoJobClock Clock = new();
            internal readonly TaskCompletionSource<Guid> Done = Signal<Guid>();
            internal readonly Ledger Ledger;
            internal readonly ArtifactStore Store;
            internal readonly VideoJobManager Manager;
            internal readonly VideoRouteQuoteService Quotes;
            internal readonly VideoSubmissionCoordinator Coordinator;
            internal Rig(Func<ArtifactStore, VideoPublicationService>? publication = null, IVideoPosterSidecarProducer? poster = null, IVideoProvider? googleProvider = null, FalVeoBindingCatalog? catalog = null)
            {
                Ledger = new(Path.Combine(DirectoryPath, "ledger.jsonl")); Store = new(Path.Combine(DirectoryPath, "artifacts"));
                catalog ??= FalVeoCompatibilityTests.ActiveCatalog();
                var registry = new DefaultVideoProviderRegistry(new IVideoProviderRegistration[] { new VeoProviderRegistration(googleProvider ?? Google), new Registration(Fal, catalog) });
                var coordinator = Coordinator = new VideoSubmissionCoordinator(registry, catalog, Secrets);
                Quotes = new(coordinator, Media, Clock, new VideoFramingPreparationService(Media, new VideoFramingCache(), resources: new VideoPreparationResources()));
                Manager = new(registry, Media, Ledger, new VideoCostEstimator(), Store, Clock, null, TimeSpan.Zero, 2, null, posterProducer: poster, coordinator: coordinator, routeQuotes: Quotes, deadlineTimer: Timer, publication: publication?.Invoke(Store));
                Manager.AfterRunForTests = id => Done.TrySetResult(id);
            }
            internal Task<JobSubmitResult> Submit(VideoRequestIntent? intent = null, VideoSubmitConfirmation? confirmation = null) => ((IVideoConfirmedJobManager)Manager).SubmitConfirmedAsync(intent ?? VideoRouteQuoteTests.Intent(), confirmation ?? new(null, null), default);
            internal VideoJobRecord Record(Guid id) => Ledger.ReadAll().Records.Single(r => r.JobId == id);
            public void Dispose() { Manager.Dispose(); if (Directory.Exists(DirectoryPath)) try { Directory.Delete(DirectoryPath, true); } catch (IOException) { } }
        }

        [Fact]
        public async Task MissingKeyMotivatingI2vUsesSameJobAndFal()
        {
            using var rig = new Rig(); rig.Secrets.Google = null;
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image"); rig.Media.Values[input] = FalVeoCompatibilityTests.Image(1280, 720);
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", mode: VideoMode.I2V, startFrame: input, resolution: "1080p"), new JsonObject());
            var submit = await rig.Submit(intent); Assert.NotNull(submit.JobId);
            await Limit(rig.Done.Task);
            var record = rig.Record(submit.JobId!.Value);
            Assert.Equal("fal", record.Provider); Assert.Equal("fal-ai/veo3.1", record.Model);
            Assert.Equal(3.20m, record.Pricing.TotalUsd);
            Assert.Equal(0, rig.Google.Submits); Assert.Equal(1, rig.Fal.Submits);
            Assert.Equal(VideoJobState.Complete, record.State);
            Assert.NotNull(record.Extensions!["video_route"]);
        }
        [Fact]
        public async Task ConfiguredGoogleDoesNotReadFalSecret()
        {
            using var rig = new Rig(); rig.Secrets.ThrowFal = true;
            var submit = await rig.Submit(); await Limit(rig.Done.Task);
            Assert.Equal(VideoJobState.Complete, rig.Record(submit.JobId!.Value).State);
            Assert.Equal(0, rig.Secrets.FalReads); Assert.Equal(0, rig.Fal.Submits);
        }
        [Fact]
        public async Task RejectedGooglePersistsBeforeFalRoute()
        {
            using var rig = new Rig();
            rig.Google.Submit = (r, ct) => Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "rejected", false, null, "rook.veo.key_rejected")));
            rig.Fal.Submit = (r, ct) => { var data = VideoExecutionSnapshot.Read(rig.Ledger.ReadAll().Records.Single()).Snapshot!.Data; Assert.Equal("rejected", data["attempts"]![0]!["dispatch_state"]!.GetValue<string>()); return Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(new ProviderJobHandle("fal-handle"))); };
            var result = await rig.Submit(); await Limit(rig.Done.Task);
            Assert.Equal("fal", rig.Record(result.JobId!.Value).Provider);
            Assert.Equal(1, rig.Google.Submits); Assert.Equal(1, rig.Fal.Submits);
        }
        [Fact]
        public async Task DirectFalNeverReadsGoogle()
        {
            using var rig = new Rig();
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1").With(options: new FalVeoOptions());
            var result = await rig.Submit(VideoRequestIntent.Normalize(request, new JsonObject())); await Limit(rig.Done.Task);
            Assert.Equal(0, rig.Google.Submits); Assert.Null(rig.Record(result.JobId!.Value).Extensions!["video_route"]);
        }
    }
}
