using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class FakeVideoProviderTests
    {
        private static VideoGenerationRequest SampleRequest() =>
            TestVideoFixtures.DefaultT2vRequest();

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> NoMedia
            = new Dictionary<MediaRef, ResolvedMedia>();

        // ─── Hooks fire when set ──────────────────────────────────────

        [Fact]
        public async Task Submit_invokes_OnSubmit_when_set()
        {
            var fake = new FakeVideoProvider
            {
                OnSubmitOutcome = (req, media) => new QueuedSubmitOutcome(
                    new ProviderJobHandle("custom-id-42")),
            };

            var result = await fake.SubmitAsync(SampleRequest(), NoMedia, CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(result);
            Assert.Equal("custom-id-42", queued.Handle.ProviderJobId);
            Assert.Null(queued.Handle.ProviderResultToken);
        }

        [Fact]
        public async Task Cancel_invokes_OnCancel_when_set()
        {
            var fake = new FakeVideoProvider
            {
                OnCancel = id => ProviderCancelResult.Ok(VideoJobState.Cancelled),
            };

            var result = await fake.CancelAsync("any", CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, result.State);
        }

        // ─── Recorded calls preserve order ────────────────────────────

        [Fact]
        public async Task RecordedCalls_captures_methods_in_order()
        {
            var fake = new FakeVideoProvider();

            await fake.SubmitAsync(SampleRequest(), NoMedia, CancellationToken.None);
            await fake.GetStatusAsync("fake-job-1", CancellationToken.None);
            await fake.GetStatusAsync("fake-job-1", CancellationToken.None);
            await fake.CancelAsync("fake-job-1", CancellationToken.None);

            Assert.Collection(fake.RecordedCalls,
                c => Assert.Equal("Submit", c.Method),
                c => Assert.Equal("GetStatus", c.Method),
                c => Assert.Equal("GetStatus", c.Method),
                c => Assert.Equal("Cancel", c.Method));
        }

        // ─── Default behaviour is sensible ────────────────────────────

        [Fact]
        public async Task Default_Submit_returns_submitting_with_provider_id()
        {
            var fake = new FakeVideoProvider();

            var result = await fake.SubmitAsync(SampleRequest(), NoMedia, CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(result);
            Assert.Equal("fake-job-1", queued.Handle.ProviderJobId);
            Assert.Null(queued.Handle.ProviderResultToken);
        }

        [Fact]
        public async Task Default_FetchResult_when_premature_surfaces_error()
        {
            // Pinning the ProviderFetchResult invariant: when Error != null,
            // Bytes / MimeType are null. The fake's default behaviour models
            // the "premature fetch" failure mode honestly.
            var fake = new FakeVideoProvider();

            var result = await fake.FetchResultAsync("any", "any-token", CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Null(result.Bytes);
            Assert.Null(result.MimeType);
        }

        [Fact]
        public async Task Custom_FetchResult_carries_bytes_and_mime()
        {
            var bytes = new byte[] { 0x00, 0x00, 0x00, 0x18 }; // "ftyp" mp4 header start
            var fake = new FakeVideoProvider
            {
                OnFetchResult = (id, token) => ProviderFetchResult.Ok(bytes, "video/mp4"),
            };

            var result = await fake.FetchResultAsync("any", "https://example/v.mp4", CancellationToken.None);

            Assert.Same(bytes, result.Bytes);
            Assert.Equal("video/mp4", result.MimeType);
            Assert.Null(result.Error);
        }

        [Fact]
        public async Task FetchResult_receives_providerResultToken()
        {
            string? capturedToken = null;
            var fake = new FakeVideoProvider
            {
                OnFetchResult = (id, token) =>
                {
                    capturedToken = token;
                    return ProviderFetchResult.Ok(new byte[] { 1 }, "video/mp4");
                },
            };

            await fake.FetchResultAsync("job-1", "https://veo/result/abc", CancellationToken.None);

            Assert.Equal("https://veo/result/abc", capturedToken);
        }
    }
}
