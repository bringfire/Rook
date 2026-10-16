using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Framing;
using Rook.Tests.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    // This class deliberately fills the production singleton. Only this quota
    // integration test is exclusive; ordinary fake-provider fixtures own pools.
    [CollectionDefinition(Name, DisableParallelization = true)]
    public sealed class VideoProductionPreparationPoolCollection
    {
        public const string Name = "Video production preparation pool";
    }

    [Collection(VideoProductionPreparationPoolCollection.Name)]
    public sealed class VideoProviderPreparationSaturationTests
    {
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task SaturationReturnsTypedRetryableFailureBeforeAnyProviderSideEffect(bool fal)
        {
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            using var queuedStop = new CancellationTokenSource();
            var resources = VideoPreparationResources.Shared;
            using var first = await resources.AcquireAsync(deadline.Token);
            using var second = await resources.AcquireAsync(deadline.Token);
            var third = resources.AcquireAsync(queuedStop.Token);
            var fourth = resources.AcquireAsync(queuedStop.Token);
            int httpCalls = 0, admissions = 0;
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => { Interlocked.Increment(ref httpCalls); throw new InvalidOperationException("A saturated provider must not send HTTP."); } };
            var request = TestVideoFixtures.DefaultT2vRequest(model: fal ? "fal-ai/veo3.1" : "veo-3.1-generate-preview");
            if (fal) request = request.With(options: new FalVeoOptions());
            using var media = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            try
            {
                Assert.False(third.IsCompleted); Assert.False(fourth.IsCompleted);
                var response = fal
                    ? await new FalVeoQueueAdapter(() => "synthetic", new FalApiClient(new HttpClient(http)), FalVeoCompatibilityTests.ActiveCatalog(), new FalVeoQueueAdapterTests.Uploads()).SubmitPreparedAsync(request, media, () => admissions++, deadline.Token)
                    : await ((IPreparedMediaVideoProvider)new VeoProvider(() => "synthetic", new VeoClient(new HttpClient(http)))).SubmitPreparedAsync(request, media, () => admissions++, deadline.Token);
                var failure = Assert.IsType<FailedSubmitOutcome>(response);
                Assert.True(failure.Error.Retryable);
                Assert.Equal("source_preparation_failed", failure.Error.ProviderErrorCode);
                Assert.Equal("preparation_busy", failure.Error.ProviderDetail!["preparation_detail"].GetValue<string>());
                Assert.Equal(0, httpCalls); Assert.Equal(0, admissions);
            }
            finally
            {
                queuedStop.Cancel();
                foreach (var queued in new[] { third, fourth })
                    try { (await queued).Dispose(); } catch (OperationCanceledException) { }
                first.Dispose(); second.Dispose();
            }
            using var recovered = await resources.AcquireAsync(deadline.Token);
            Assert.Equal(1, resources.ActiveBundles);
        }
    }
}
