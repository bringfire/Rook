using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed class VideoPreparedBundle : IDisposable
    {
        private readonly JsonObject? _evidence;
        public VideoPreparedMediaSnapshot Originals { get; }
        public VideoPreparedMediaSnapshot Prepared { get; }
        public JsonObject? SourcePreparation => (JsonObject?)_evidence?.DeepClone();
        public VideoPreparedBundle(VideoPreparedMediaSnapshot originals, VideoPreparedMediaSnapshot prepared, JsonObject? sourcePreparation)
        { Originals = originals; Prepared = prepared; _evidence = (JsonObject?)sourcePreparation?.DeepClone(); }
        internal IEnumerable<VideoFrozenBuffer> Buffers => Originals.Slots.Concat(Prepared.Slots).Select(s => s.Buffer).GroupBy(b => b.StorageIdentity).Select(g => g.First());
        public void Dispose() { Originals.Dispose(); if (!ReferenceEquals(Originals, Prepared)) Prepared.Dispose(); }
    }
    internal sealed class VideoPreparedBundleLease : IDisposable
    {
        private readonly object _gate = new();
        private Action? _release;
        private readonly Func<VideoPreparedBundleLease> _retain;
        private readonly VideoPreparedBundle _bundle;
        private readonly IReadOnlyDictionary<string, Guid> _previewIds;
        internal VideoPreparedBundleLease(VideoPreparedBundle bundle, IReadOnlyDictionary<string, Guid> ids, Action release, Func<VideoPreparedBundleLease> retain)
        { _bundle = bundle; _previewIds = ids; _release = release; _retain = retain; }
        public VideoPreparedMediaSnapshot Originals => _bundle.Originals;
        public VideoPreparedMediaSnapshot Prepared => _bundle.Prepared;
        public JsonObject? SourcePreparation => _bundle.SourcePreparation;
        public Guid PreviewId(string role) => _previewIds[role];
        public VideoPreparedBundleLease Retain()
        { lock (_gate) return _release != null ? _retain() : throw new ObjectDisposedException(nameof(VideoPreparedBundleLease)); }
        public void Dispose()
        { Action? release; lock (_gate) { release = _release; _release = null; } release?.Invoke(); }
    }
    internal sealed record VideoPreparedBundleResult(VideoPreparedBundleLease? Bundle, GenerationError? Error);
}
