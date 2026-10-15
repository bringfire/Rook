using System;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video.Framing
{
    internal static class VideoPreparationLimits
    {
        public const long OriginalBytes = 33_554_432, BundleOriginalBytes = 67_108_864;
        public const long TransientBytes = 134_217_728, RetainedBytes = 268_435_456;
        public const long RendererCommitBytes = 536_870_912;
        public const int ChunkBytes = 65_536, UploadBytes = 8_000_000, RasterEdge = 16_384;
        public const long RasterPixels = 32_000_000;
    }

    internal sealed class VideoPreparationResources
    {
        public static readonly VideoPreparationResources Shared = new();
        private readonly SemaphoreSlim _bundles, _renderers;
        private readonly long _transientLimit;
        private int _activeBundles;
        public VideoPreparationResources(int maxBundles = 2, int maxRenderers = 2,
            long transientLimit = VideoPreparationLimits.TransientBytes)
        { _bundles = new(maxBundles, maxBundles); _renderers = new(maxRenderers, maxRenderers); _transientLimit = transientLimit; }
        public int ActiveBundles => Volatile.Read(ref _activeBundles);
        public async Task<VideoPreparationLease> AcquireAsync(CancellationToken ct)
        {
            await _bundles.WaitAsync(ct).ConfigureAwait(false);
            Interlocked.Increment(ref _activeBundles);
            return new VideoPreparationLease(_transientLimit, () => { Interlocked.Decrement(ref _activeBundles); _bundles.Release(); });
        }
        public async Task<IDisposable> AcquireRendererAsync(CancellationToken ct)
        {
            await _renderers.WaitAsync(ct).ConfigureAwait(false);
            return new VideoReleaseAction(() => _renderers.Release());
        }
    }

    internal sealed class VideoPreparationLease : IDisposable
    {
        private readonly Action _release;
        private int _disposed, _released;
        private long _originalBytes;
        public VideoBufferBudget Buffers { get; }
        public long AdmittedOriginalBytes => Interlocked.Read(ref _originalBytes);
        internal VideoPreparationLease(long limit, Action release)
        { _release = release; Buffers = new VideoBufferBudget(limit, TryRelease); }
        internal bool AdmitOriginal(long length)
        {
            if (length > VideoPreparationLimits.OriginalBytes) return false;
            // A lease is serial by contract; keep admission atomic for cancellation/diagnostics.
            lock (this)
            {
                if (length > VideoPreparationLimits.BundleOriginalBytes - _originalBytes) return false;
                _originalBytes += length; return true;
            }
        }
        public void Dispose() { Interlocked.Exchange(ref _disposed, 1); TryRelease(); }
        private void TryRelease()
        {
            if (Volatile.Read(ref _disposed) != 0 && Buffers.ReservedBytes == 0 &&
                Interlocked.Exchange(ref _released, 1) == 0) _release();
        }
    }

    internal sealed class VideoBufferBudget
    {
        private readonly object _gate = new();
        private readonly long _limit;
        private readonly Action? _changed;
        private long _reserved, _peak;
        public VideoBufferBudget(long limit = VideoPreparationLimits.TransientBytes, Action? changed = null)
        { _limit = limit; _changed = changed; }
        public long ReservedBytes { get { lock (_gate) return _reserved; } }
        public long PeakReservedBytes { get { lock (_gate) return _peak; } }
        public VideoBufferReservation Reserve(int capacity)
        {
            lock (_gate)
            {
                if (capacity < 0 || capacity > _limit - _reserved) throw new VideoPreparationBusyException();
                _reserved += capacity; _peak = Math.Max(_peak, _reserved);
                return new VideoBufferReservation(this, capacity);
            }
        }
        internal void Release(int capacity)
        { lock (_gate) _reserved -= capacity; _changed?.Invoke(); }
    }

    internal sealed class VideoBufferReservation : IDisposable
    {
        private VideoBufferBudget? _budget;
        private readonly int _capacity;
        internal VideoBufferReservation(VideoBufferBudget budget, int capacity) { _budget = budget; _capacity = capacity; }
        public void Dispose() { Interlocked.Exchange(ref _budget, null)?.Release(_capacity); }
    }

    internal sealed class VideoPreparationBusyException : Exception { }
    internal sealed class VideoReleaseAction : IDisposable
    {
        private Action? _release;
        public VideoReleaseAction(Action release) { _release = release; }
        public void Dispose() { Interlocked.Exchange(ref _release, null)?.Invoke(); }
    }
}
