using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    internal sealed record VisionPresentationStateSnapshot
    {
        public bool SurfacePresent { get; init; }
        public IReadOnlyList<WebViewHostPresentationRecord> Entries { get; init; } =
            Array.Empty<WebViewHostPresentationRecord>();
    }

    internal sealed class VisionPresentationStateStore : IWebViewHostPresentationRecorder
    {
        private const int DefaultCapacity = 256;

        private readonly object _gate = new();
        private readonly int _capacity;
        private readonly Queue<WebViewHostPresentationRecord> _entries;
        private readonly Stopwatch _clock = Stopwatch.StartNew();
        private long _nextSequence;
        private int _surfaceRegistrationCount;

        public VisionPresentationStateStore(int capacity = DefaultCapacity)
        {
            _capacity = capacity > 0 ? capacity : DefaultCapacity;
            _entries = new Queue<WebViewHostPresentationRecord>(_capacity);
        }

        public IDisposable RegisterSurface()
        {
            lock (_gate)
            {
                _surfaceRegistrationCount++;
            }

            return new SurfaceRegistration(this);
        }

        public void Append(WebViewHostPresentationRecord record)
        {
            try
            {
                var stamped = record with
                {
                    Sequence = Interlocked.Increment(ref _nextSequence),
                    Utc = DateTimeOffset.UtcNow,
                    ElapsedMilliseconds = _clock.ElapsedMilliseconds,
                    ThreadId = Thread.CurrentThread.ManagedThreadId
                };

                lock (_gate)
                {
                    while (_entries.Count >= _capacity)
                    {
                        _entries.Dequeue();
                    }

                    _entries.Enqueue(stamped);
                }
            }
            catch
            {
                // Diagnostics must never affect the presentation path.
            }
        }

        public VisionPresentationStateSnapshot Snapshot()
        {
            lock (_gate)
            {
                return new VisionPresentationStateSnapshot
                {
                    SurfacePresent = _surfaceRegistrationCount > 0,
                    Entries = _entries.ToArray()
                };
            }
        }

        private void UnregisterSurface()
        {
            lock (_gate)
            {
                if (_surfaceRegistrationCount > 0)
                    _surfaceRegistrationCount--;
            }
        }

        private sealed class SurfaceRegistration : IDisposable
        {
            private VisionPresentationStateStore? _owner;

            public SurfaceRegistration(VisionPresentationStateStore owner)
            {
                _owner = owner;
            }

            public void Dispose()
            {
                var owner = Interlocked.Exchange(ref _owner, null);
                owner?.UnregisterSurface();
            }
        }
    }
}
