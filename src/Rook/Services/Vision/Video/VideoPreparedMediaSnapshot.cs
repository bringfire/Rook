using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoPreparedMediaSlot
    {
        internal VideoPreparedMediaSlot(string role, MediaRef reference, string mime, VideoFrozenBuffer buffer)
        { Role = role; Ref = reference; MimeType = mime; Buffer = buffer; }
        internal VideoFrozenBuffer Buffer { get; }
        public string Role { get; }
        public MediaRef Ref { get; }
        public string MimeType { get; }
        public string Sha256 => Buffer.Sha256;
        public int ByteLength => Buffer.Length;
        // Compatibility copies only. Dispatch uses the explicit resource-lease overload.
        public byte[] CopyBytes()
        { using var copy = Buffer.CopyOwned(new VideoBufferBudget()); return copy.Bytes; }
        public Stream OpenRead() => Buffer.OpenRead();
    }

    internal sealed record VideoResolvedSource(VideoFrozenBuffer Buffer, string MimeType);
    internal sealed record VideoSourceSnapshotResult(VideoPreparedMediaSnapshot? Snapshot, GenerationError? Error);
    internal sealed class VideoPreparedMediaSnapshot : IDisposable
    {
        private int _disposed;
        private VideoPreparedMediaSnapshot(IReadOnlyList<VideoPreparedMediaSlot> slots) { Slots = slots; }
        public IReadOnlyList<VideoPreparedMediaSlot> Slots { get; }
        public int UniqueStorageCount => Slots.Select(s => s.Buffer.StorageIdentity).Distinct().Count();
        internal static IEnumerable<(string Role, MediaRef Ref)> References(VideoGenerationRequest request)
        {
            if (request.StartFrame != null) yield return ("start_frame", request.StartFrame);
            if (request.EndFrame != null) yield return ("end_frame", request.EndFrame);
            for (int i = 0; i < (request.ReferenceFrames?.Count ?? 0); i++)
                yield return ("reference_frames[" + i + "]", request.ReferenceFrames![i]);
        }
        internal static VideoPreparedMediaSnapshot FromOwned(VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, VideoResolvedSource> resolved)
            => FromOwned(References(request), resolved);
        internal static VideoPreparedMediaSnapshot FromOwned(IEnumerable<(string Role, MediaRef Ref)> roles, IReadOnlyDictionary<MediaRef, VideoResolvedSource> resolved)
        {
            var slots = roles.Select(r => resolved.TryGetValue(r.Ref, out var source)
                ? new VideoPreparedMediaSlot(r.Role, r.Ref, source.MimeType, source.Buffer)
                : throw new ArgumentException("Resolved input missing: " + r.Role, nameof(resolved))).ToArray();
            return new VideoPreparedMediaSnapshot(Array.AsReadOnly(slots));
        }
        public static VideoPreparedMediaSnapshot Capture(VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolved)
        {
            var sources = new Dictionary<MediaRef, VideoResolvedSource>();
            var budget = new VideoBufferBudget();
            long originalLength = 0;
            try
            {
                foreach (var (_, reference) in References(request))
                {
                    if (sources.ContainsKey(reference)) continue;
                    if (!resolved.TryGetValue(reference, out var media)) throw new ArgumentException("Resolved input missing.", nameof(resolved));
                    if (media.Bytes.LongLength > VideoPreparationLimits.OriginalBytes ||
                        (originalLength += media.Bytes.LongLength) > VideoPreparationLimits.BundleOriginalBytes)
                        throw new ArgumentException("Source byte limits exceeded.", nameof(resolved));
                    sources.Add(reference, new(VideoFrozenBuffer.CopyOf(media.Bytes, budget), media.MimeType));
                }
                return FromOwned(request, sources);
            }
            catch { foreach (var source in sources.Values) source.Buffer.Dispose(); throw; }
        }
        public IReadOnlyDictionary<MediaRef, ResolvedMedia> ToResolvedMedia()
            => Slots.GroupBy(s => s.Ref).ToDictionary(g => g.Key, g => new ResolvedMedia(g.First().CopyBytes(), g.First().MimeType));
        public VideoResolvedMediaLease ToResolvedMedia(VideoPreparationLease lease)
        {
            var copies = new List<VideoOwnedBytes>();
            var media = new Dictionary<MediaRef, ResolvedMedia>();
            try
            {
                foreach (var slot in Slots)
                {
                    if (media.ContainsKey(slot.Ref)) continue;
                    var copy = slot.Buffer.CopyOwned(lease.Buffers); copies.Add(copy);
                    media.Add(slot.Ref, new ResolvedMedia(copy.Bytes, slot.MimeType));
                }
                return new VideoResolvedMediaLease(media, copies, lease.Buffers);
            }
            catch { media.Clear(); foreach (var copy in copies) copy.Dispose(); throw; }
        }
        internal void TransferToRetainedCache()
        { foreach (var buffer in Slots.Select(s => s.Buffer).Distinct()) buffer.TransferToRetainedCache(); }
        public void Dispose()
        { if (Interlocked.Exchange(ref _disposed, 1) == 0) foreach (var buffer in Slots.Select(s => s.Buffer).Distinct()) buffer.Dispose(); }
    }

    internal sealed class VideoResolvedMediaLease : IDisposable
    {
        private readonly Dictionary<MediaRef, ResolvedMedia> _media;
        private List<VideoOwnedBytes>? _copies;
        private VideoPreparationLease? _phase;
        public IReadOnlyDictionary<MediaRef, ResolvedMedia> Media => _media;
        public VideoBufferBudget Buffers { get; }
        internal VideoResolvedMediaLease(Dictionary<MediaRef, ResolvedMedia> media, List<VideoOwnedBytes> copies, VideoBufferBudget budget)
        { _media = media; _copies = copies; Buffers = budget; }
        internal void OwnPhase(VideoPreparationLease phase) { _phase = phase; }
        public void Dispose()
        {
            var copies = Interlocked.Exchange(ref _copies, null);
            if (copies is null) return;
            _media.Clear();
            foreach (var copy in copies) copy.Dispose();
            Interlocked.Exchange(ref _phase, null)?.Dispose();
        }
    }
}
