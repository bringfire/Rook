using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    internal sealed record VisionPresentationStateSnapshot
    {
        public DateTimeOffset DumpRequestedUtc { get; init; }
        public bool SurfacePresent { get; init; }
        public int EntryCount { get; init; }
        public int Capacity { get; init; }
        public IReadOnlyList<WebViewHostPresentationRecord> Entries { get; init; } =
            Array.Empty<WebViewHostPresentationRecord>();
    }

    internal static class VisionPresentationStateDump
    {
        public static JsonSerializerOptions JsonOptions { get; } = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true
        };

        public static VisionPresentationStateDumpPayload CreatePayload(
            VisionPresentationStateSnapshot snapshot,
            string rookVersion,
            string rhinoVersion,
            int processId,
            int threadId)
            => new VisionPresentationStateDumpPayload
            {
                RookVersion = rookVersion,
                RhinoVersion = rhinoVersion,
                ProcessId = processId,
                ThreadId = threadId,
                DumpRequestedUtc = snapshot.DumpRequestedUtc,
                SurfacePresent = snapshot.SurfacePresent,
                EntryCount = snapshot.EntryCount,
                Capacity = snapshot.Capacity,
                Entries = snapshot.Entries.ToArray()
            };
    }

    internal sealed record VisionPresentationStateDumpPayload
    {
        public string RookVersion { get; init; } = string.Empty;
        public string RhinoVersion { get; init; } = string.Empty;
        public int ProcessId { get; init; }
        public int ThreadId { get; init; }
        public DateTimeOffset DumpRequestedUtc { get; init; }
        public bool SurfacePresent { get; init; }
        public int EntryCount { get; init; }
        public int Capacity { get; init; }
        public WebViewHostPresentationRecord[] Entries { get; init; } =
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
                var entries = _entries.ToArray();
                return new VisionPresentationStateSnapshot
                {
                    DumpRequestedUtc = DateTimeOffset.UtcNow,
                    SurfacePresent = _surfaceRegistrationCount > 0,
                    EntryCount = entries.Length,
                    Capacity = _capacity,
                    Entries = entries
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
