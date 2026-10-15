using System;
using System.IO;
using System.Security.Cryptography;
using System.Threading;

namespace Rook.Services.Vision.Video.Framing
{
    // A handle to immutable shared storage. Streams own a reference; disposing the
    // snapshot cannot invalidate a currently opened preview or provider read.
    internal sealed class VideoFrozenBuffer : IDisposable
    {
        private Storage? _storage;
        private VideoFrozenBuffer(Storage storage) { _storage = storage; }
        private Storage Data => _storage ?? throw new ObjectDisposedException(nameof(VideoFrozenBuffer));
        public int Length => Data.Length;
        public string Sha256 => Data.Sha256;
        internal object StorageIdentity => Data;
        internal static VideoFrozenBuffer Adopt(byte[] owned, VideoBufferReservation reservation, string sha256)
            => new(new Storage(owned, reservation, sha256));
        public static VideoFrozenBuffer CopyOf(byte[] source, VideoBufferBudget budget)
        {
            using var scratch = budget.Reserve(VideoPreparationLimits.ChunkBytes);
            var reservation = budget.Reserve(source.Length);
            try
            {
                var bytes = (byte[])source.Clone();
                return Adopt(bytes, reservation, Hash(bytes));
            }
            catch { reservation.Dispose(); throw; }
        }
        internal static string Hash(byte[] bytes)
        { using var sha = SHA256.Create(); return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(); }
        public VideoFrozenBuffer Retain() { var data = Data; data.Retain(); return new(data); }
        public Stream OpenRead() { var data = Data; data.Retain(); return new FrozenReadStream(data); }
        internal void TransferToRetainedCache() => Data.ReleaseTransientCharge();
        public VideoOwnedBytes CopyOwned(VideoBufferBudget budget)
        {
            var data = Data;
            var reservation = budget.Reserve(data.Length);
            try
            {
                var copy = new byte[data.Length];
                data.Read(0, copy, 0, copy.Length);
                return new VideoOwnedBytes(copy, reservation);
            }
            catch { reservation.Dispose(); throw; }
        }
        public void Dispose() { Interlocked.Exchange(ref _storage, null)?.Release(); }

        private sealed class Storage
        {
            private readonly object _gate = new();
            private byte[]? _bytes;
            private VideoBufferReservation? _reservation;
            private int _references = 1;
            public int Length { get; }
            public string Sha256 { get; }
            public Storage(byte[] bytes, VideoBufferReservation reservation, string sha)
            { _bytes = bytes; _reservation = reservation; Length = bytes.Length; Sha256 = sha; }
            public void Retain() { lock (_gate) { if (_bytes is null) throw new ObjectDisposedException(nameof(Storage)); _references++; } }
            public void Release()
            {
                VideoBufferReservation? release = null;
                lock (_gate) { if (--_references == 0) { _bytes = null; release = _reservation; _reservation = null; } }
                release?.Dispose();
            }
            public void ReleaseTransientCharge()
            { VideoBufferReservation? release; lock (_gate) { release = _reservation; _reservation = null; } release?.Dispose(); }
            public int Read(long position, byte[] buffer, int offset, int count)
            {
                lock (_gate)
                {
                    if (_bytes is null) throw new ObjectDisposedException(nameof(Storage));
                    int n = (int)Math.Min(count, Math.Max(0, Length - position));
                    Buffer.BlockCopy(_bytes, (int)position, buffer, offset, n); return n;
                }
            }
        }
        private sealed class FrozenReadStream : Stream
        {
            private Storage? _data; private long _position;
            public FrozenReadStream(Storage data) { _data = data; }
            private Storage Data => _data ?? throw new ObjectDisposedException(nameof(FrozenReadStream));
            public override bool CanRead => _data != null;
            public override bool CanSeek => _data != null;
            public override bool CanWrite => false;
            public override long Length => Data.Length;
            public override long Position { get => _position; set { if (value < 0 || value > Length) throw new ArgumentOutOfRangeException(nameof(value)); _position = value; } }
            public override int Read(byte[] buffer, int offset, int count)
            {
                if (buffer == null) throw new ArgumentNullException(nameof(buffer));
                if (offset < 0 || count < 0 || offset > buffer.Length - count) throw new ArgumentOutOfRangeException();
                int n = Data.Read(_position, buffer, offset, count); _position += n; return n;
            }
            public override long Seek(long offset, SeekOrigin origin)
            { Position = checked(offset + (origin == SeekOrigin.Begin ? 0 : origin == SeekOrigin.Current ? Position : Length)); return Position; }
            protected override void Dispose(bool disposing) { if (disposing) Interlocked.Exchange(ref _data, null)?.Release(); base.Dispose(disposing); }
            public override void Flush() { }
            public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }
    }
    internal sealed class VideoOwnedBytes : IDisposable
    {
        private VideoBufferReservation? _reservation;
        public byte[] Bytes { get; private set; }
        public VideoOwnedBytes(byte[] bytes, VideoBufferReservation reservation) { Bytes = bytes; _reservation = reservation; }
        public void Dispose() { Bytes = Array.Empty<byte>(); Interlocked.Exchange(ref _reservation, null)?.Dispose(); }
    }
}
