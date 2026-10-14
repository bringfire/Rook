using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoPreparedMediaSlot
    {
        private readonly byte[] _bytes;
        internal VideoPreparedMediaSlot(string role, MediaRef reference, ResolvedMedia media)
        {
            Role = role; Ref = reference; MimeType = media.MimeType;
            _bytes = (byte[])media.Bytes.Clone();
            using var sha = SHA256.Create();
            Sha256 = BitConverter.ToString(sha.ComputeHash(_bytes)).Replace("-", "").ToLowerInvariant();
        }
        public string Role { get; }
        public MediaRef Ref { get; }
        public string MimeType { get; }
        public string Sha256 { get; }
        public int ByteLength => _bytes.Length;
        public byte[] CopyBytes() => (byte[])_bytes.Clone();
        public Stream OpenRead() => new MemoryStream(_bytes, 0, _bytes.Length, writable: false, publiclyVisible: false);
    }

    internal sealed class VideoPreparedMediaSnapshot
    {
        private VideoPreparedMediaSnapshot(IReadOnlyList<VideoPreparedMediaSlot> slots) { Slots = slots; }
        public IReadOnlyList<VideoPreparedMediaSlot> Slots { get; }
        public static VideoPreparedMediaSnapshot Capture(VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolved)
        {
            var slots = new List<VideoPreparedMediaSlot>();
            void Add(string role, MediaRef? reference)
            {
                if (reference is null) return;
                if (!resolved.TryGetValue(reference, out var media)) throw new ArgumentException("Resolved input missing: " + role, nameof(resolved));
                slots.Add(new VideoPreparedMediaSlot(role, reference, media));
            }
            Add("start_frame", request.StartFrame);
            Add("end_frame", request.EndFrame);
            for (int i = 0; i < (request.ReferenceFrames?.Count ?? 0); i++) Add("reference_frames[" + i + "]", request.ReferenceFrames![i]);
            return new VideoPreparedMediaSnapshot(Array.AsReadOnly(slots.ToArray()));
        }
        public IReadOnlyDictionary<MediaRef, ResolvedMedia> ToResolvedMedia() => Slots.GroupBy(s => s.Ref).ToDictionary(g => g.Key, g => new ResolvedMedia(g.First().CopyBytes(), g.First().MimeType));
    }
}
