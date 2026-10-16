using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VeoPreparedContentTests
    {
        [Fact]
        public async Task CompletedPhaseCannotReserveNewBuffersAfterReleasingAdmission()
        {
            var resources = new VideoPreparationResources(1, 1); var phase = await resources.AcquireAsync(default);
            phase.Dispose(); Assert.Equal(0, resources.ActiveBundles);
            Assert.Throws<ObjectDisposedException>(() => phase.Buffers.Reserve(1));
        }
        [Fact]
        public async Task StreamsBase64AcrossChunkBoundaries_AndPreservesRepeatedRolesAndJsonTypes()
        {
            var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var bytes = Enumerable.Range(0, 2_000_007).Select(i => (byte)(i * 17)).ToArray();
            var request = TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.Interp, startFrame: reference, endFrame: reference, prompt: "line\n<é☃>\"");
            using var media = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [reference] = new(bytes, "image/png") });
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            using var content = new VeoPreparedContent(request, media, new { durationSeconds = 8, aspectRatio = "16:9", personGeneration = "allow_adult", resolution = "720p" }, phase, default);
            long length = content.Headers.ContentLength!.Value;
            string json = await content.ReadAsStringAsync(); Assert.Equal(length, Encoding.UTF8.GetByteCount(json));
            var parsed = JsonNode.Parse(json)!; Assert.Equal(8, parsed["parameters"]!["durationSeconds"]!.GetValue<int>());
            Assert.Equal(request.Prompt, parsed["instances"]![0]!["prompt"]!.GetValue<string>());
            foreach (string role in new[] { "image", "lastFrame" }) Assert.Equal(bytes, Convert.FromBase64String(parsed["instances"]![0]![role]!["bytesBase64Encoded"]!.GetValue<string>()));
            Assert.True(phase.Buffers.PeakReservedBytes < 2_000_000, "Streaming must not reserve whole-image base64 or JSON buffers.");
        }
        [Fact]
        public async Task DisposedContentAndPhaseRemainOwnedUntilActualSerializerStops()
        {
            var resources = new VideoPreparationResources(1, 1); var phase = await resources.AcquireAsync(default);
            int released = 0; phase.OwnRetainedMedia(new VideoReleaseAction(() => Interlocked.Increment(ref released)));
            var request = TestVideoFixtures.DefaultT2vRequest(); using var media = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            var content = new VeoPreparedContent(request, media, new { durationSeconds = 8 }, phase, default);
            var target = new PausedWriter(); var copying = content.CopyToAsync(target);
            await target.Entered.Task; content.Dispose(); phase.Dispose();
            Assert.Equal(1, resources.ActiveBundles); Assert.Equal(0, released);
            target.Release.SetResult(true);
            await Assert.ThrowsAnyAsync<Exception>(() => copying);
            Assert.Equal(0, resources.ActiveBundles); Assert.Equal(1, released); Assert.Equal(0, phase.Buffers.ReservedBytes);
        }
        private sealed class PausedWriter : Stream
        {
            internal readonly TaskCompletionSource<bool> Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
            internal readonly TaskCompletionSource<bool> Release = new(TaskCreationOptions.RunContinuationsAsynchronously);
            public override async Task WriteAsync(byte[] bytes, int offset, int count, CancellationToken ct) { Entered.TrySetResult(true); await Release.Task; }
            public override bool CanRead => false; public override bool CanSeek => false; public override bool CanWrite => true;
            public override long Length => 0; public override long Position { get => 0; set => throw new NotSupportedException(); }
            public override void Flush() { } public override void SetLength(long value) => throw new NotSupportedException();
            public override int Read(byte[] b, int o, int c) => throw new NotSupportedException(); public override long Seek(long o, SeekOrigin s) => throw new NotSupportedException();
            public override void Write(byte[] b, int o, int c) => throw new NotSupportedException();
        }
    }
}
