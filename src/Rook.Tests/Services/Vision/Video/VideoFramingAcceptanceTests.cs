using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFramingAcceptanceTests
    {
        [Fact]
        public async Task Preparation_AdmissionHasBoundedWaitersAndRecoversAfterCancellation()
        {
            var resources = new VideoPreparationResources();
            using var first = await resources.AcquireAsync(default);
            using var second = await resources.AcquireAsync(default);
            using var cancellation = new CancellationTokenSource();
            var third = resources.AcquireAsync(cancellation.Token);
            var fourth = resources.AcquireAsync(cancellation.Token);
            var overflow = resources.AcquireAsync(default);
            Assert.True(overflow.IsCompleted); // Reject immediately; no fifth retained waiter.
            await Assert.ThrowsAsync<VideoPreparationBusyException>(() => overflow);
            cancellation.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => third);
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => fourth);
            first.Dispose(); using var replacement = await resources.AcquireAsync(default);
            Assert.Equal(2, resources.ActiveBundles);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task OriginalResolution_RequiresDurableVisibilityForGeneratedSidecars(bool unknownOwner)
        {
            using var rig = new VideoFramingQuoteTests.Rig();
            var artifact = rig.Store.Create("generated_video", new[] { new BlobInput("start_frame", File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("square.png")), "png") },
                metadata: new Dictionary<string, JsonNode?> { ["video_job_id"] = JsonValue.Create(unknownOwner ? "unknown" : Guid.NewGuid().ToString("D")) },
                flags: new Dictionary<string, JsonNode?> { ["video_publication"] = JsonValue.Create("provisional") });
            var media = MediaRef.ForArtifact(artifact.Id, "start_frame");
            using var result = await new ArtifactOnlyVideoMediaResolver(rig.Store).ResolveAllAsync(new[] { media }, default);
            Assert.False(result.Success);
            // A matching durable Complete record may authorize the source even if marker finalization failed.
            using var allowed = await new ArtifactOnlyVideoMediaResolver(rig.Store, rig.Resources, a => a.Id == artifact.Id).ResolveAllAsync(new[] { media }, default);
            Assert.True(allowed.Success);
        }

        public static IEnumerable<object[]> RejectedReads()
        {
            foreach (string path in new[] { "preview", "estimate", "submit", "legacy" })
                foreach (string fault in new[] { "oversized", "growth", "growth_past_cap", "shrink", "cancelled" })
                    yield return new object[] { path, fault };
        }
        [Theory, MemberData(nameof(RejectedReads))]
        public async Task EveryEntryPath_RejectsUnstableOrOversizedOriginalsBeforePreparation(string path, string fault)
        {
            using var rig = new VideoFramingQuoteTests.Rig();
            var resources = new VideoPreparationResources();
            var reader = new FaultStream(fault);
            var resolver = new ArtifactOnlyVideoMediaResolver(rig.Store, resources, openSource: _ => reader);
            using var cache = new VideoFramingCache();
            var preparation = new VideoFramingPreparationService(resolver, cache, resources: resources);
            var quotes = new VideoRouteQuoteService(rig.Coordinator, resolver, new FakeVideoJobClock(), preparation);
            var intent = path == "legacy" ? VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", mode: VideoMode.I2V, resolution: "1080p", startFrame: rig.Source), new JsonObject()) : rig.Intent;
            using var stop = new CancellationTokenSource();
            Exception? thrown = null;
            Rook.Services.Vision.Generation.GenerationError? error = null;
            var ledger = new FakeVideoJobLedger();
            async Task Run()
            {
                if (path == "preview") error = (await preparation.PreviewAsync(new(intent.Request.Model, VideoMode.I2V,
                    new[] { new VideoFramingSourceSlot("start_frame", rig.Source) }, "1080p", "16:9"), stop.Token)).Error;
                else if (path == "submit")
                {
                    using var manager = new VideoJobManager(rig.Coordinator.Registry, resolver, ledger, new VideoCostEstimator(), rig.Store,
                        null, null, null, 2, null, coordinator: rig.Coordinator, routeQuotes: quotes);
                    var quote = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
                    var result = await ((IVideoConfirmedJobManager)manager).SubmitConfirmedAsync(intent, new(quote.EstimateFingerprint, quote.MaximumEstimatedCostUsd), stop.Token);
                    Assert.Null(result.JobId);
                    error = result.GenerationError ?? (result.Error == null ? null : (Rook.Services.Vision.Generation.GenerationError)result.Error);
                }
                else error = (await quotes.QuoteAsync(intent, stop.Token)).Error;
            }
            var running = Run();
            if (fault == "cancelled") { await reader.Entered.Task; stop.Cancel(); }
            try { await running; } catch (OperationCanceledException ex) { thrown = ex; }
            if (fault == "cancelled") Assert.NotNull(thrown);
            else Assert.Equal(fault == "oversized" ? "source_input_too_large" : "source_changed", error!.ProviderErrorCode);
            Assert.Equal(0, cache.BundleCount); Assert.Equal(0, resources.ActiveBundles); Assert.Empty(ledger.AllRecords);
            Assert.Single(rig.Store.List()); Assert.True(reader.MaxRead <= VideoPreparationLimits.ChunkBytes);
        }
        private sealed class FaultStream : Stream
        {
            private readonly string _fault; private int _position;
            internal readonly TaskCompletionSource<bool> Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
            internal int MaxRead;
            internal FaultStream(string fault) { _fault = fault; }
            public override long Length => _fault == "oversized" ? 33_554_433 : _position == 0 ? 3 : _fault == "growth_past_cap" ? 33_554_433 : _fault == "shrink" ? 2 : 4;
            public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct)
            {
                MaxRead = Math.Max(count, MaxRead); Entered.TrySetResult(true);
                if (_fault == "cancelled") await Task.Delay(Timeout.Infinite, ct);
                int amount = Math.Min(count, 3 - _position); Array.Clear(buffer, offset, amount); _position += amount; return amount;
            }
            public override bool CanRead => true; public override bool CanWrite => false; public override bool CanSeek => false;
            public override long Position { get => _position; set => throw new NotSupportedException(); }
            public override int Read(byte[] b, int o, int c) => throw new NotSupportedException();
            public override void Flush() { }
            public override long Seek(long o, SeekOrigin s) => throw new NotSupportedException();
            public override void SetLength(long l) => throw new NotSupportedException();
            public override void Write(byte[] b, int o, int c) => throw new NotSupportedException();
        }
    }
}
