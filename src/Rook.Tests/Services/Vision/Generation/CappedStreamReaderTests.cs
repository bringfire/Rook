using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public sealed class CappedStreamReaderTests
    {
        [Fact]
        public async Task Under_cap_returns_all_bytes()
        {
            using var stream = new ScriptedStream(total: 5, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.NotNull(bytes);
            Assert.Equal(5, bytes!.Length);
        }

        [Fact]
        public async Task Exactly_at_cap_returns_bytes()
        {
            using var stream = new ScriptedStream(total: 10, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.NotNull(bytes);
            Assert.Equal(10, bytes!.Length);
        }

        [Fact]
        public async Task One_over_cap_returns_null()
        {
            using var stream = new ScriptedStream(total: 11, chunk: 16);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.Null(bytes);
        }

        [Fact]
        public async Task Multi_chunk_crossing_cap_returns_null()
        {
            using var stream = new ScriptedStream(total: 12, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.Null(bytes);
        }

        [Fact]
        public async Task Empty_stream_returns_empty_array_not_null()
        {
            using var stream = new ScriptedStream(total: 0, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.NotNull(bytes);
            Assert.Empty(bytes!);
        }

        [Fact]
        public async Task Cancellation_throws_operation_cancelled()
        {
            // Cancels before the first read; proves the token propagates through
            // ReadAsync (the helper does not catch OperationCanceledException).
            using var stream = new ScriptedStream(total: 100, chunk: 4);
            using var cts = new CancellationTokenSource();
            cts.Cancel();

            await Assert.ThrowsAsync<OperationCanceledException>(
                () => CappedStreamReader.ReadCappedAsync(stream, cap: 1000, ct: cts.Token));
        }

        // Yields `total` bytes in reads of at most `chunk` bytes; honors cancellation.
        private sealed class ScriptedStream : Stream
        {
            private long _remaining;
            private readonly int _chunk;

            public ScriptedStream(long total, int chunk)
            {
                _remaining = total;
                _chunk = chunk;
            }

            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException();

            public override long Position
            {
                get => throw new NotSupportedException();
                set => throw new NotSupportedException();
            }

            public override void Flush() { }

            public override int Read(byte[] buffer, int offset, int count)
            {
                if (_remaining <= 0)
                    return 0;

                var toRead = (int)Math.Min(Math.Min(count, _chunk), _remaining);
                for (var i = 0; i < toRead; i++)
                    buffer[offset + i] = 7;
                _remaining -= toRead;
                return toRead;
            }

            public override Task<int> ReadAsync(
                byte[] buffer,
                int offset,
                int count,
                CancellationToken cancellationToken)
            {
                cancellationToken.ThrowIfCancellationRequested();
                return Task.FromResult(Read(buffer, offset, count));
            }

            public override long Seek(long offset, SeekOrigin origin) =>
                throw new NotSupportedException();

            public override void SetLength(long value) =>
                throw new NotSupportedException();

            public override void Write(byte[] buffer, int offset, int count) =>
                throw new NotSupportedException();
        }
    }
}
