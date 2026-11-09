using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Fal
{
    /// <summary>Admitted original bytes and provenance, never uploaded URLs. The caller owns this
    /// snapshot until quote derivation or SubmitAsync settles, then must dispose it before polling.
    /// Compatibility copies/prepared values require the snapshot to remain alive while in use.</summary>
    public sealed class FalMediaSnapshot : IDisposable
    {
        private readonly string _hash, _operation;
        private readonly object _gate = new();
        private readonly VideoPreparationLease? _phase;
        private readonly List<IDisposable> _ownedValues = new();
        private bool _disposed;
        public IReadOnlyList<FalMediaSnapshotSlot> Slots { get; }
        /// <summary>Expected capture validation failure. Invalid snapshots own no slots and are
        /// rejected by preparation and execution before upload or dispatch admission.</summary>
        public GenerationError? ValidationError { get; }
        internal VideoPreparationLease Phase => _phase ?? throw new FalMediaPreparationException(ValidationError!);
        private FalMediaSnapshot(FalNormalizedRequest request, IEnumerable<FalMediaSnapshotSlot> slots, GenerationError? error, VideoPreparationLease? phase)
        { _hash = request.Binding.DefinitionHash; _operation = request.Binding.OperationId; Slots = Array.AsReadOnly(slots.ToArray()); ValidationError = error; _phase = phase; foreach (var slot in Slots) slot.Owner = this; }

        public static FalMediaSnapshot Capture(FalNormalizedRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
            => Capture(request, media, VideoPreparationResources.Shared);

        internal static FalMediaSnapshot Capture(FalNormalizedRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media, VideoPreparationResources resources)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (media == null) throw new ArgumentNullException(nameof(media));
            if (!resources.TryAcquire(out var phase)) return new FalMediaSnapshot(request, Array.Empty<FalMediaSnapshotSlot>(), Busy(), null);
            var slots = new List<FalMediaSnapshotSlot>();
            GenerationError? error = null;
            long total = 0;
            var budget = phase!.Buffers;
            var accounted = new HashSet<MediaRef>();
            try
            {
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
                    VideoFrozenBuffer? buffer = VideoFrozenBuffer.CopyOf(resolved.Bytes, budget);
                    try
                    {
                        using var sniff = buffer.CopyOwned(budget);
                        var mime = ImageMimeDetector.Detect(sniff.Bytes);
                        if (!ImageMimeDetector.IsPngJpegOrWebp(mime) || !string.Equals(mime, resolved.MimeType, StringComparison.Ordinal))
                        { error = Invalid("Configured fal source media must be PNG, JPEG or WebP with matching MIME.", field); break; }
                        slots.Add(new FalMediaSnapshotSlot(instruction, buffer, mime));
                        total += buffer.Length; accounted.Add(instruction.Input.Source);
                        buffer = null; // ownership transferred to the slot
                    }
                    finally { buffer?.Dispose(); }
                }
                if (error == null && accounted.Count != media.Count) error = Invalid("Unaccounted configured fal source media.", "media");
            }
            catch (VideoPreparationBusyException) { error = Busy(); }
            catch { foreach (var slot in slots) slot.Dispose(); phase.Dispose(); throw; }
            if (error != null) { foreach (var slot in slots) slot.Dispose(); slots.Clear(); phase.Dispose(); phase = null; }
            return new FalMediaSnapshot(request, slots, error, phase);
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
        private static GenerationError Busy() => new(GenerationErrorCode.DependencyUnavailable, "Source preparation capacity is busy; release retained snapshots before trying again.", true, "media", "media_preparation_busy");
        internal void OwnValues(IDisposable values)
        {
            lock (_gate)
            {
                if (_disposed) { values.Dispose(); throw new ObjectDisposedException(nameof(FalMediaSnapshot)); }
                _ownedValues.Add(values);
            }
        }
        internal byte[] CopyBytes(FalMediaSnapshotSlot slot)
        {
            lock (_gate)
            {
                if (_disposed) throw new ObjectDisposedException(nameof(FalMediaSnapshot));
                var copy = slot.CopyOwned(Phase.Buffers);
                _ownedValues.Add(copy); return copy.Bytes;
            }
        }
        public void Dispose()
        {
            lock (_gate)
            {
                if (_disposed) return; _disposed = true;
                foreach (var values in _ownedValues) values.Dispose(); _ownedValues.Clear();
                foreach (var slot in Slots) slot.Dispose();
                _phase?.Dispose();
            }
        }
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
        internal FalMediaSnapshot Owner { private get; set; } = null!;
        internal FalMediaSnapshotSlot(FalMediaInstruction instruction, VideoFrozenBuffer buffer, string mime)
        {
            Source = instruction.Input.Source; Role = instruction.Role; Ordinal = instruction.Ordinal;
            Transport = instruction.Definition.Transport; _buffer = buffer; MimeType = mime; Sha256 = buffer.Sha256;
        }
        public byte[] CopyBytes() => Owner.CopyBytes(this);
        internal VideoOwnedBytes CopyOwned(VideoBufferBudget budget) => _buffer.CopyOwned(budget);
        // The complete prepared-batch envelope reserves the largest such copy before any upload.
        internal byte[] CopyForPreparedBatch() => _buffer.Read(bytes => bytes.ToArray());
        internal T Read<T>(VideoBufferReader<T> reader) => _buffer.Read(reader);
        internal void Dispose() => _buffer.Dispose();
    }
}
