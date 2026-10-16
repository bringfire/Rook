using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Threading;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class FalVeoEnablementTests
    {
        [Fact]
        public void FalPickerAdvertisesOnlyQualifiedReferencesWhileGoogleRetainsReferences()
        {
            var registration = new FalVeoProviderRegistration(new FalVideoProvider(() => "test-only"), new FalVeoBindingCatalog());
            foreach (var model in registration.Models.Values)
            {
                Assert.False(model.Capability.SupportsReferenceImages);
                Assert.Equal(0, model.Capability.MaxReferenceImages);
            }
            Assert.True(VeoCapabilities.Models["veo-3.1-generate-preview"].Capability.SupportsReferenceImages);
        }

        [Fact]
        public async Task UnqualifiedReferenceFallbackExplainsTheSourcePolicyAndPreservesGoogleRoute()
        {
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var media = new VideoRouteQuoteTests.Media();
            media.Values[source] = FalVeoCompatibilityTests.Image(1280, 720);
            var intent = VideoRequestIntent.Normalize(VideoRouteQuoteTests.Intent().Request.With(referenceFrames: new[] { source }), new JsonObject());
            var catalog = new FalVeoBindingCatalog();
            var unavailable = await VideoRouteQuoteTests.Service(new VideoRouteQuoteTests.Secrets { Google = null }, media, catalog).QuoteAsync(intent, default);
            Assert.Equal("reference_frames", unavailable.Error!.Field);
            Assert.DoesNotContain("continuity", unavailable.Error.Message);
            var google = await VideoRouteQuoteTests.Service(new VideoRouteQuoteTests.Secrets(), media, catalog).QuoteAsync(intent, default);
            Assert.NotNull(google.Quote);
            Assert.Equal("veo", google.Quote!.Candidates.Single(c => c.EligibilityError == null).Model.ProviderName);
        }

        [Fact]
        public void AllVerifiedTiersPreserveModeMappingAfterTheDeprecationDate()
        {
            var catalog = new FalVeoBindingCatalog();
            var frame = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            foreach (var tier in new[] { "veo-3.1-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.1-lite-generate-preview" })
            foreach (var mode in new[] { VideoMode.T2V, VideoMode.I2V, VideoMode.Interp })
            {
                var request = VideoRouteQuoteTests.Intent().Request.With(model: tier, mode: mode,
                    startFrame: mode == VideoMode.T2V ? null : frame, endFrame: mode == VideoMode.Interp ? frame : null);
                var resolved = catalog.Resolve(request, new DateTimeOffset(2027, 1, 1, 0, 0, 0, TimeSpan.Zero));
                Assert.Null(resolved.Error);
                Assert.StartsWith(VideoSubmissionCoordinator.FalModelFor(tier)!, resolved.Binding!.SubmitEndpoint);
                Assert.Equal("fal-ai/veo3.1", resolved.Binding.LifecycleRoot);
            }
            Assert.Equal(9, catalog.All.Count(b => b.SubmissionVerified));
            Assert.All(catalog.All.Where(b => b.SubmitEndpoint.EndsWith("/reference-to-video")), b => Assert.False(b.SubmissionVerified));
        }

        [Theory]
        [InlineData("veo-3.1-generate-preview")]
        [InlineData("veo-3.1-fast-generate-preview")]
        [InlineData("veo-3.1-lite-generate-preview")]
        public async Task DefaultCatalogEnablesMissingGoogleFallbackWithoutCalendarShutdown(string model)
        {
            var catalog = new FalVeoBindingCatalog();
            var request = VideoRouteQuoteTests.Intent().Request.With(model: model);
            var binding = catalog.Resolve(request, new DateTimeOffset(2027, 1, 1, 0, 0, 0, TimeSpan.Zero));
            Assert.Null(binding.Error);
            Assert.Null(binding.Binding!.NewSubmissionCutoffUtc);
            using var rig = new VideoFalFallbackManagerTests.Rig(catalog: catalog);
            rig.Secrets.Google = null;
            Assert.True(rig.Manager.ModelAvailability(model)["can_generate"]!.GetValue<bool>());
            var result = await rig.Submit(VideoRequestIntent.Normalize(request, new JsonObject()));
            Assert.NotNull(result.JobId);
            await VideoFalFallbackManagerTests.Limit(rig.Done.Task);
            Assert.Equal(VideoJobState.Complete, rig.Record(result.JobId!.Value).State);
            Assert.Equal(0, rig.Google.Submits);
            Assert.Equal(1, rig.Fal.Submits);
        }

        [Theory]
        [InlineData(SocketError.HostNotFound)]
        [InlineData(SocketError.TryAgain)]
        [InlineData(SocketError.NoData)]
        [InlineData(SocketError.ConnectionRefused)]
        public async Task ProvenConnectionFailureFallsBackWithoutInvalidatingGoogleCredential(SocketError error)
        {
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => throw new HttpRequestException("SECRET exception sentinel", new SocketException((int)error)) };
            var google = new VeoProvider(() => "test-only", new VeoClient(new HttpClient(http)));
            using var rig = new VideoFalFallbackManagerTests.Rig(googleProvider: google);
            rig.Fal.Submit = (r, ct) => {
                var evidence = VideoExecutionSnapshot.Read(rig.Ledger.ReadAll().Records.Single()).Snapshot!.Data;
                Assert.Equal("rejected", evidence["attempts"]![0]!["dispatch_state"]!.GetValue<string>());
                Assert.Null(evidence["credential_failure"]);
                return Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(new ProviderJobHandle("fal-handle")));
            };
            var submit = await rig.Submit();
            await VideoFalFallbackManagerTests.Limit(rig.Done.Task);
            var record = rig.Record(submit.JobId!.Value);
            Assert.Equal(VideoJobState.Complete, record.State);
            Assert.Equal(1, rig.Fal.Submits);
            Assert.Equal("google_not_accepted", record.Extensions!["video_route"]!["fallback_reason"]!.GetValue<string>());
            Assert.Null(VideoExecutionSnapshot.Read(record).Snapshot!.Data["credential_failure"]);
            Assert.DoesNotContain("SECRET", record.Extensions.ToJsonString());
        }

        [Theory]
        [InlineData(SocketError.ConnectionReset)]
        [InlineData(SocketError.ConnectionAborted)]
        [InlineData(SocketError.TimedOut)]
        public async Task AmbiguousConnectionFailureNeverSubmitsFal(SocketError error)
        {
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => throw new HttpRequestException("SECRET exception sentinel", new SocketException((int)error)) };
            using var rig = new VideoFalFallbackManagerTests.Rig(googleProvider: new VeoProvider(() => "test-only", new VeoClient(new HttpClient(http))));
            var submit = await rig.Submit();
            await VideoFalFallbackManagerTests.Limit(rig.Done.Task);
            var record = rig.Record(submit.JobId!.Value);
            Assert.Equal(VideoJobState.Interrupted, record.State);
            Assert.Equal("submission_unknown", record.Error!.ProviderErrorCode);
            Assert.Equal(0, rig.Fal.Submits);
        }

        [Fact]
        public async Task ResponseReadFailureCannotMasqueradeAsInitialConnectionFailure()
        {
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new BrokenResponseContent() }) };
            var google = new VeoProvider(() => "test-only", new VeoClient(new HttpClient(http)));
            using var rig = new VideoFalFallbackManagerTests.Rig(googleProvider: google);
            var submit = await rig.Submit();
            await VideoFalFallbackManagerTests.Limit(rig.Done.Task);
            Assert.Equal("submission_unknown", rig.Record(submit.JobId!.Value).Error!.ProviderErrorCode);
            Assert.Equal(0, rig.Fal.Submits);
        }
        private sealed class BrokenResponseContent : HttpContent
        {
            protected override bool TryComputeLength(out long length) { length = 0; return false; }
            protected override Task SerializeToStreamAsync(System.IO.Stream stream, TransportContext context) => throw new HttpRequestException("SECRET response sentinel", new SocketException((int)SocketError.HostNotFound));
        }

        [Fact]
        public async Task ResponseBodyStallRetainsTheHttpTimeoutAndNeverEnablesFallback()
        {
            using var body = new BlockingResponseContent();
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = body }) };
            using var client = new HttpClient(http) { Timeout = TimeSpan.FromMilliseconds(50) };
            var google = new VeoProvider(() => "test-only", new VeoClient(client));
            var request = VideoRouteQuoteTests.Intent().Request;
            using var phase = await new Rook.Services.Vision.Video.Framing.VideoPreparationResources().AcquireAsync(default);
            using var prepared = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            var pending = ((IPreparedMediaVideoProvider)google).SubmitPreparedAsync(request, prepared, () => { }, default, phase);
            Assert.Same(pending, await Task.WhenAny(pending, Task.Delay(2000)));
            Assert.Equal("submission_unknown", Assert.IsType<FailedSubmitOutcome>(await pending).Error.ProviderErrorCode);
        }
        private sealed class BlockingResponseContent : HttpContent
        {
            private readonly TaskCompletionSource<bool> _stop = new(TaskCreationOptions.RunContinuationsAsynchronously);
            protected override bool TryComputeLength(out long length) { length = 0; return false; }
            protected override Task SerializeToStreamAsync(System.IO.Stream stream, TransportContext context) => _stop.Task;
            protected override void Dispose(bool disposing) { if (disposing) _stop.TrySetCanceled(); base.Dispose(disposing); }
        }
    }
}
