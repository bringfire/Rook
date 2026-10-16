using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFramingCacheTests
    {
        [Fact]
        public void Cache_ByteCountEntryCountTtlAndPinnedExhaustion()
        {
            var now = DateTimeOffset.UtcNow;
            using var cache = new VideoFramingCache(() => now, maxBytes: 100, maxBundles: 2);
            using var one = cache.Admit("one", Bundle(40))!;
            using var two = cache.Admit("two", Bundle(40))!;
            Assert.Equal(80, cache.RetainedBytes); Assert.Equal(2, cache.BundleCount);
            Assert.Null(cache.Admit("busy", Bundle(30))); Assert.Equal(80, cache.RetainedBytes);
            var id = one.PreviewId("start_frame");
            using var stream = cache.TryOpenPreview(id, "image")!;
            one.Dispose(); two.Dispose(); now += TimeSpan.FromMinutes(31);
            cache.Sweep(); Assert.Equal(1, cache.BundleCount); using (var check = cache.TryGet("one")) Assert.NotNull(check);
            stream.Dispose(); cache.Sweep(); // release updates last use: a new idle window
            now += TimeSpan.FromMinutes(31); cache.Sweep();
            Assert.Null(cache.TryOpenPreview(id, "image")); Assert.Equal(0, cache.RetainedBytes);
        }
        [Fact]
        public void Cache_CancelOneCallerDoesNotReleaseAnotherPin_AndStreamPins()
        {
            using var cache = new VideoFramingCache(maxBytes: 64, maxBundles: 1);
            var first = cache.Admit("same", Bundle(40))!;
            using var other = first.Retain();
            var id = first.PreviewId("start_frame");
            using var read = cache.TryOpenPreview(id, "image")!;
            first.Dispose(); Assert.Null(cache.Admit("other", Bundle(40)));
            Assert.Equal(40, other.Prepared.Slots[0].ByteLength); other.Dispose();
            Assert.Equal(0, read.ReadByte()); Assert.Null(cache.Admit("other", Bundle(40)));
            read.Dispose(); using var next = cache.Admit("other", Bundle(40)); Assert.NotNull(next);
            Assert.Null(cache.TryOpenPreview(id, "image"));
        }
        [Fact]
        public void Cache_ConvergingEntriesDisposeLosingBuffers_AndCloseWaitsForPins()
        {
            using var cache = new VideoFramingCache(maxBytes: 100, maxBundles: 2);
            using var first = cache.Admit("same", Bundle(40))!;
            using var second = cache.Admit("same", Bundle(40))!;
            Assert.Equal(first.PreviewId("start_frame"), second.PreviewId("start_frame"));
            Assert.Equal(40, cache.RetainedBytes); cache.Dispose();
            Assert.Null(cache.TryOpenPreview(first.PreviewId("start_frame"), "image"));
            Assert.Equal(40, first.Prepared.Slots[0].ByteLength);
            first.Dispose(); second.Dispose(); Assert.Equal(0, cache.RetainedBytes);
        }
        private static VideoPreparedBundle Bundle(int size)
        {
            var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var source = new VideoResolvedSource(VideoFrozenBuffer.CopyOf(new byte[size], new VideoBufferBudget()), "image/png");
            var snapshot = VideoPreparedMediaSnapshot.FromOwned(new[] { ("start_frame", reference) }, new Dictionary<MediaRef, VideoResolvedSource> { [reference] = source });
            return new(snapshot, snapshot, null);
        }
    }
}
