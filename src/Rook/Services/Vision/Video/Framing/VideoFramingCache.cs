using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed class VideoFramingCache : IDisposable
    {
        private readonly object _gate = new();
        private readonly Dictionary<string, Entry> _entries = new(StringComparer.Ordinal);
        private readonly Dictionary<Guid, (Entry Entry, VideoFrozenBuffer Bytes)> _previews = new();
        private readonly Dictionary<object, (int Users, int Capacity)> _storage = new();
        private readonly Func<DateTimeOffset> _now;
        private readonly long _maxBytes;
        private readonly int _maxBundles;
        private long _retained;
        private bool _closed;
        public VideoFramingCache(Func<DateTimeOffset>? now = null, long maxBytes = VideoPreparationLimits.RetainedBytes, int maxBundles = 16)
        { _now = now ?? (() => DateTimeOffset.UtcNow); _maxBytes = maxBytes; _maxBundles = maxBundles; }
        public long RetainedBytes { get { lock (_gate) return _retained; } }
        public int BundleCount { get { lock (_gate) return _entries.Count; } }
        public VideoPreparedBundleLease? TryGet(string key)
        {
            lock (_gate) { SweepCore(); return !_closed && _entries.TryGetValue(key, out var entry) ? Pin(entry) : null; }
        }
        // Takes ownership even when capacity is unavailable or another caller won convergence.
        public VideoPreparedBundleLease? Admit(string key, VideoPreparedBundle bundle)
        {
            lock (_gate)
            {
                SweepCore();
                if (_closed) { bundle.Dispose(); return null; }
                if (_entries.TryGetValue(key, out var existing)) { bundle.Dispose(); return Pin(existing); }
                var buffers = bundle.Buffers.ToArray();
                long extra = buffers.Where(b => !_storage.ContainsKey(b.StorageIdentity)).Sum(b => (long)b.Length);
                if (extra > _maxBytes) { bundle.Dispose(); return null; }
                while (_entries.Count >= _maxBundles || extra > _maxBytes - _retained)
                {
                    var victim = _entries.Values.Where(e => e.Pins == 0).OrderBy(e => e.LastUsed).FirstOrDefault();
                    if (victim == null) { bundle.Dispose(); return null; }
                    Remove(victim);
                    extra = buffers.Where(b => !_storage.ContainsKey(b.StorageIdentity)).Sum(b => (long)b.Length);
                }
                var entry = new Entry(key, bundle, _now());
                foreach (var b in buffers)
                {
                    if (_storage.TryGetValue(b.StorageIdentity, out var charge)) _storage[b.StorageIdentity] = (charge.Users + 1, charge.Capacity);
                    else { _storage.Add(b.StorageIdentity, (1, b.Length)); _retained += b.Length; }
                }
                // Retained accounting is established before transient ownership is released.
                foreach (var b in buffers) b.TransferToRetainedCache();
                foreach (var group in bundle.Prepared.Slots.GroupBy(s => s.Buffer.StorageIdentity))
                {
                    var id = Guid.NewGuid();
                    _previews.Add(id, (entry, group.First().Buffer));
                    foreach (var slot in group) entry.Ids.Add(slot.Role, id);
                }
                _entries.Add(key, entry); return Pin(entry);
            }
        }
        public Stream? TryOpenPreview(Guid id, string role)
            => TryOpenPreview(id, role, out _);
        internal Stream? TryOpenPreview(Guid id, string role, out string? mimeType)
        {
            lock (_gate)
            {
                mimeType = null;
                SweepCore();
                if (_closed || role != "image" || !_previews.TryGetValue(id, out var preview)) return null;
                var pin = Pin(preview.Entry);
                mimeType = preview.Entry.Bundle.Prepared.Slots.First(s => ReferenceEquals(s.Buffer.StorageIdentity, preview.Bytes.StorageIdentity)).MimeType;
                try { return new PinnedStream(preview.Bytes.OpenRead(), pin); }
                catch { pin.Dispose(); throw; }
            }
        }
        public void Sweep() { lock (_gate) SweepCore(); }
        private void SweepCore()
        {
            var now = _now();
            foreach (var entry in _entries.Values.Where(e => e.Pins == 0 && (_closed || now - e.LastUsed >= TimeSpan.FromMinutes(30))).ToArray()) Remove(entry);
        }
        private VideoPreparedBundleLease Pin(Entry entry)
        {
            entry.Pins++; entry.LastUsed = _now();
            return new(entry.Bundle, entry.Ids, () => { lock (_gate) { entry.Pins--; entry.LastUsed = _now(); if (_closed && entry.Pins == 0) Remove(entry); } },
                () => { lock (_gate) return Pin(entry); });
        }
        private void Remove(Entry entry)
        {
            if (entry.Pins != 0) throw new InvalidOperationException("Cannot evict pinned prepared media.");
            _entries.Remove(entry.Key);
            foreach (var id in entry.Ids.Values.Distinct()) _previews.Remove(id);
            foreach (var b in entry.Bundle.Buffers)
            {
                var charge = _storage[b.StorageIdentity];
                if (charge.Users == 1) { _storage.Remove(b.StorageIdentity); _retained -= charge.Capacity; }
                else _storage[b.StorageIdentity] = (charge.Users - 1, charge.Capacity);
            }
            entry.Bundle.Dispose();
        }
        public void Dispose() { lock (_gate) { _closed = true; SweepCore(); } }
        private sealed class Entry(string key, VideoPreparedBundle bundle, DateTimeOffset now)
        {
            public string Key { get; } = key;
            public VideoPreparedBundle Bundle { get; } = bundle;
            public Dictionary<string, Guid> Ids { get; } = new(StringComparer.Ordinal);
            public int Pins;
            public DateTimeOffset LastUsed = now;
        }
        private sealed class PinnedStream(Stream inner, VideoPreparedBundleLease pin) : Stream
        {
            private VideoPreparedBundleLease? _pin = pin;
            public override bool CanRead => inner.CanRead; public override bool CanSeek => inner.CanSeek; public override bool CanWrite => false;
            public override long Length => inner.Length; public override long Position { get => inner.Position; set => inner.Position = value; }
            public override int Read(byte[] buffer, int offset, int count) => inner.Read(buffer, offset, count);
            public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct) => inner.ReadAsync(buffer, offset, count, ct);
            public override long Seek(long offset, SeekOrigin origin) => inner.Seek(offset, origin);
            public override void Flush() { } public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
            protected override void Dispose(bool disposing) { if (disposing) { inner.Dispose(); Interlocked.Exchange(ref _pin, null)?.Dispose(); } base.Dispose(disposing); }
        }
    }
}
