using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Fal
{
    /// <summary>Owned original bytes and provenance, never uploaded URLs. Dispose after preparation
    /// and quote verification finish. Byte access always returns a detached copy.</summary>
    public sealed class FalMediaSnapshot : IDisposable
    {
        private readonly string _hash, _operation;
        private bool _disposed;
        public IReadOnlyList<FalMediaSnapshotSlot> Slots { get; }
        /// <summary>Expected capture validation failure. Invalid snapshots own no slots and are
        /// rejected by preparation and execution before upload or dispatch admission.</summary>
        public GenerationError? ValidationError { get; }
        private FalMediaSnapshot(FalNormalizedRequest request, IEnumerable<FalMediaSnapshotSlot> slots, GenerationError? error)
        { _hash = request.Binding.DefinitionHash; _operation = request.Binding.OperationId; Slots = Array.AsReadOnly(slots.ToArray()); ValidationError = error; }

        public static FalMediaSnapshot Capture(FalNormalizedRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (media == null) throw new ArgumentNullException(nameof(media));
            var slots = new List<FalMediaSnapshotSlot>();
            GenerationError? error = null;
            long total = 0;
            var budget = new VideoBufferBudget();
            var accounted = new HashSet<MediaRef>();
            foreach (var instruction in request.Media.OrderBy(m => m.Role, StringComparer.Ordinal).ThenBy(m => m.Ordinal))
            {
                var field = instruction.Role;
                if (!media.TryGetValue(instruction.Input.Source, out var resolved) || resolved == null)
                { error = Invalid("Configured fal source media was not resolved.", field); break; }
                var limit = Math.Min(instruction.Definition.MaxBytes ?? 30L * 1024 * 1024, 30L * 1024 * 1024);
                if (instruction.Definition.Preparation != "validated_original" ||
                    instruction.Definition.Transport is not ("data_uri" or "fal_upload") ||
                    request.Binding.Result.MimeFamily == "video" && instruction.Definition.Transport != "fal_upload")
                { error = Invalid("Unsupported configured fal source preparation profile.", field); break; }
                // Intersect catalog limits with the existing bounded video preparation ceilings.
                if (request.Binding.Result.MimeFamily == "video") limit = Math.Min(limit, VideoPreparationLimits.UploadBytes);
                if (resolved.Bytes.LongLength > limit || resolved.Bytes.LongLength > VideoPreparationLimits.BundleOriginalBytes - total)
                { error = Invalid("Configured fal source media exceeds the runtime or operation byte limit.", field); break; }
                var buffer = VideoFrozenBuffer.CopyOf(resolved.Bytes, budget);
                using var sniff = buffer.CopyOwned(budget);
                var mime = ImageMimeDetector.Detect(sniff.Bytes);
                if (!ImageMimeDetector.IsPngJpegOrWebp(mime) || !string.Equals(mime, resolved.MimeType, StringComparison.Ordinal))
                { buffer.Dispose(); error = Invalid("Configured fal source media must be PNG, JPEG or WebP with matching MIME.", field); break; }
                slots.Add(new FalMediaSnapshotSlot(instruction, buffer, mime));
                total += buffer.Length; accounted.Add(instruction.Input.Source);
            }
            if (error == null && accounted.Count != media.Count) error = Invalid("Unaccounted configured fal source media.", "media");
            if (error != null) { foreach (var slot in slots) slot.Dispose(); slots.Clear(); }
            return new FalMediaSnapshot(request, slots, error);
        }

        internal GenerationError? Validate(FalNormalizedRequest request)
        {
            if (_disposed) return Invalid("Configured fal source snapshot has been disposed.", "media");
            if (ValidationError != null) return ValidationError;
            if (_hash != request.Binding.DefinitionHash || _operation != request.Binding.OperationId || Slots.Count != request.Media.Count ||
                request.Media.Any(m => !Slots.Any(s => s.Role == m.Role && s.Ordinal == m.Ordinal && s.Source.Equals(m.Input.Source))))
                return Invalid("Configured fal source snapshot does not match the pinned request.", "media");
            return null;
        }
        internal static GenerationError Invalid(string message, string field) => new(GenerationErrorCode.InvalidRequest, message, false, field);
        public void Dispose() { if (_disposed) return; _disposed = true; foreach (var slot in Slots) slot.Dispose(); }
    }

    public sealed class FalMediaSnapshotSlot
    {
        private readonly VideoFrozenBuffer _buffer;
        public MediaRef Source { get; }
        public string Role { get; }
        public int Ordinal { get; }
        public string MimeType { get; }
        public string Sha256 { get; }
        public long ByteLength => _buffer.Length;
        internal string Transport { get; }
        internal FalMediaSnapshotSlot(FalMediaInstruction instruction, VideoFrozenBuffer buffer, string mime)
        {
            Source = instruction.Input.Source; Role = instruction.Role; Ordinal = instruction.Ordinal;
            Transport = instruction.Definition.Transport; _buffer = buffer; MimeType = mime; Sha256 = buffer.Sha256;
        }
        public byte[] CopyBytes() { using var copy = _buffer.CopyOwned(new VideoBufferBudget()); return copy.Bytes; }
        internal VideoOwnedBytes CopyOwned(VideoBufferBudget budget) => _buffer.CopyOwned(budget);
        internal void Dispose() => _buffer.Dispose();
    }
}
