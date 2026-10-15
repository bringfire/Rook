using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoBoundedMediaTests : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "rook-video-bounds-" + Guid.NewGuid().ToString("N"));
        private readonly ArtifactStore _store;
        public VideoBoundedMediaTests() { _store = new ArtifactStore(_root); }

        [Fact]
        public async Task Read_OverCap_StopsAtArtifactBoundary()
        {
            var artifact = _store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
            using (var file = File.OpenWrite(_store.GetBlobAbsolutePath(artifact.Id, "image"))) file.SetLength(33_554_433);
            var result = await new ArtifactOnlyVideoMediaResolver(_store).ResolveAllAsync(
                new[] { MediaRef.ForArtifact(artifact.Id, "image") }, CancellationToken.None);
            Assert.False(result.Success);
            Assert.Equal("source_input_too_large", result.Error!.ProviderErrorCode);
        }

        [Fact]
        public async Task Read_ExactCapAndAggregateLimit()
        {
            using var lease = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            using var first = (await BoundedVideoSourceReader.ReadAsync(new PatternStream(33_554_432), 33_554_432, "start_frame", lease, CancellationToken.None)).Buffer!;
            Assert.Equal(33_554_432, first.Length);
            using var second = (await BoundedVideoSourceReader.ReadAsync(new PatternStream(33_554_432), 33_554_432, "end_frame", lease, CancellationToken.None)).Buffer!;
            Assert.Equal(67_108_864, lease.AdmittedOriginalBytes);
            var third = await BoundedVideoSourceReader.ReadAsync(new PatternStream(1), 1, "reference_frames[0]", lease, CancellationToken.None);
            Assert.Equal("source_input_too_large", third.Error!.ProviderErrorCode);
            Assert.True(lease.Buffers.PeakReservedBytes <= 134_217_728);
        }

        [Theory]
        [InlineData(3, 2, 3)] // early EOF
        [InlineData(3, 4, 4)] // growth within ceiling
        [InlineData(3, 4, 33554433)] // growth past ceiling
        [InlineData(3, 4, 3)] // extra EOF byte despite unchanged length
        [InlineData(3, 3, 2)] // shrink despite complete payload
        public async Task Read_GrowthShrinkAndExtraByteDiscardSnapshot(int initial, int payload, long finalLength)
        {
            using var lease = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            var result = await BoundedVideoSourceReader.ReadAsync(new PatternStream(initial, payload, finalLength),
                initial, "start_frame", lease, CancellationToken.None);
            Assert.Null(result.Buffer);
            Assert.Equal("source_changed", result.Error!.ProviderErrorCode);
            Assert.Equal(0, lease.Buffers.ReservedBytes);
        }

        [Fact]
        public async Task Read_ReservationDenialHappensBeforePayloadRead()
        {
            using var lease = await new VideoPreparationResources(transientLimit: 4).AcquireAsync(CancellationToken.None);
            var source = new PatternStream(5);
            var result = await BoundedVideoSourceReader.ReadAsync(source, 5, "start_frame", lease, CancellationToken.None);
            Assert.True(result.Error!.Retryable);
            Assert.Equal(0, source.ReadCalls);
            Assert.Equal(0, lease.Buffers.ReservedBytes);
        }

        [Fact]
        public async Task Read_QueuedCancellationReleasesPermit()
        {
            var resources = new VideoPreparationResources();
            using var first = await resources.AcquireAsync(CancellationToken.None);
            using var second = await resources.AcquireAsync(CancellationToken.None);
            using var stop = new CancellationTokenSource();
            var pending = resources.AcquireAsync(stop.Token);
            Assert.False(pending.IsCompleted);
            stop.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending);
            first.Dispose();
            using var replacement = await resources.AcquireAsync(CancellationToken.None);
            Assert.Equal(2, resources.ActiveBundles);
        }

        [Fact]
        public async Task Read_CancellationReleasesPayloadAndScratch()
        {
            using var lease = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            using var stop = new CancellationTokenSource();
            var source = new BlockingStream();
            var read = BoundedVideoSourceReader.ReadAsync(source, 3, "start_frame", lease, stop.Token);
            await source.Entered.Task;
            stop.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => read);
            Assert.Equal(0, lease.Buffers.ReservedBytes);
        }

        [Fact]
        public async Task Capture_RepeatedRolesShareReservedStorage()
        {
            var artifact = _store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 97, 98, 99 }, "png") });
            var reference = MediaRef.ForArtifact(artifact.Id, "image");
            var request = TestVideoFixtures.DefaultT2vRequest(referenceFrames: new[] { reference, reference });
            using var lease = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            var result = await new ArtifactOnlyVideoMediaResolver(_store).ResolveSnapshotAsync(request, lease, CancellationToken.None);
            using var snapshot = result.Snapshot!;
            Assert.Equal(3, lease.AdmittedOriginalBytes);
            Assert.Equal(new[] { "reference_frames[0]", "reference_frames[1]" }, snapshot.Slots.Select(s => s.Role));
            Assert.Equal(1, snapshot.UniqueStorageCount);
            Assert.All(snapshot.Slots, s => Assert.Equal("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", s.Sha256));
            using var opened = snapshot.Slots[0].OpenRead();
            snapshot.Dispose();
            Assert.Equal(97, opened.ReadByte());
            opened.Dispose();
            Assert.Equal(0, lease.Buffers.ReservedBytes);
        }

        [Fact]
        public async Task Read_PathStatIsNotAdmission()
        {
            var artifact = _store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
            var path = _store.GetBlobAbsolutePath(artifact.Id, "image");
            var earlier = new FileInfo(path);
            Assert.Equal(1, earlier.Length);
            using (var changed = File.OpenWrite(path)) changed.SetLength(33_554_433);
            using var result = await new ArtifactOnlyVideoMediaResolver(_store).ResolveAllAsync(
                new[] { MediaRef.ForArtifact(artifact.Id, "image") }, CancellationToken.None);
            Assert.Equal("source_input_too_large", result.Error!.ProviderErrorCode);
        }

        [Fact]
        public async Task Read_DeniesAlreadyOpenWriter()
        {
            var artifact = _store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
            using var writer = new FileStream(_store.GetBlobAbsolutePath(artifact.Id, "image"),
                FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite | FileShare.Delete);
            using var result = await new ArtifactOnlyVideoMediaResolver(_store).ResolveAllAsync(
                new[] { MediaRef.ForArtifact(artifact.Id, "image") }, CancellationToken.None);
            Assert.Equal("source_changed", result.Error!.ProviderErrorCode);
        }

        [Fact]
        public async Task Lease_DisposalWaitsForFrozenReaders()
        {
            var resources = new VideoPreparationResources(maxBundles: 1);
            var phase = await resources.AcquireAsync(CancellationToken.None);
            var read = await BoundedVideoSourceReader.ReadAsync(new PatternStream(3), 3, "start_frame", phase, CancellationToken.None);
            using var stream = read.Buffer!.OpenRead();
            read.Buffer.Dispose();
            phase.Dispose();
            Assert.Equal(1, resources.ActiveBundles);
            var next = resources.AcquireAsync(CancellationToken.None);
            Assert.False(next.IsCompleted);
            stream.Dispose();
            using var resumed = await next;
            Assert.Equal(1, resources.ActiveBundles);
        }


        private class PatternStream : Stream
        {
            private readonly long _initial, _payload, _final;
            private long _position;
            public int ReadCalls { get; private set; }
            public PatternStream(long initial, long? payload = null, long? final = null)
            { _initial = initial; _payload = payload ?? initial; _final = final ?? initial; }
            public override long Length => _position == 0 ? _initial : _final;
            public override long Position { get => _position; set => throw new NotSupportedException(); }
            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override int Read(byte[] buffer, int offset, int count)
            {
                ReadCalls++;
                Assert.InRange(count, 1, 65_536);
                int n = (int)Math.Min(count, _payload - _position);
                Array.Clear(buffer, offset, n); _position += n; return n;
            }
            public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct)
            { ct.ThrowIfCancellationRequested(); return Task.FromResult(Read(buffer, offset, count)); }
            public override void Flush() { }
            public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
            public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }

        private sealed class BlockingStream : PatternStream
        {
            public readonly TaskCompletionSource<bool> Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
            public BlockingStream() : base(3) { }
            public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct)
            { Entered.TrySetResult(true); await Task.Delay(Timeout.Infinite, ct); return 0; }
        }

        public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
    }
}
