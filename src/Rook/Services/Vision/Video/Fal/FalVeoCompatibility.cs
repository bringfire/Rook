using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Video.Fal
{
    internal static class FalVeoCompatibility
    {
        public static GenerationError? Validate(VideoRequestIntent intent, FalVeoBinding binding, IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            var request = intent.Request;
            if (intent.PersonGenerationSupplied) return Error("Explicit Google person_generation cannot be translated to fal provider defaults.", "options.person_generation");
            if (string.IsNullOrWhiteSpace(request.Prompt)) return Error("fal Veo requires a nonempty prompt; supply a prompt or use Google.", "prompt");
            if (request.Seed.HasValue && !binding.SupportsSeed) return Error("This endpoint cannot preserve a seed.", "seed");
            var references = request.ReferenceFrames?.Count ?? 0;
            if (references > 0 && (request.Mode != VideoMode.T2V || request.StartFrame != null || request.EndFrame != null)) return Error("References cannot be combined with start/end frames.", "reference_frames");
            if (request.Mode == VideoMode.I2V && request.EndFrame != null || request.Mode == VideoMode.T2V && (request.StartFrame != null || request.EndFrame != null)) return Error("This mode cannot preserve these frame roles.", "end_frame");
            var effective = request.With(model: binding.ModelId, options: new FalVeoOptions());
            var shape = CapabilityValidator.Validate(binding.Capability, effective);
            if (!shape.Success) return Error(shape.Message!, shape.Field ?? "request");
            var supplied = intent.SuppliedOptions;
            if (VideoSubmissionCoordinator.IsGoogleModel(request.Model))
            {
                if (supplied.Count != 0) return Error("Google-specific options cannot be translated.", "options");
            }
            else if (new FalVeoOptionsCodec().Deserialize(supplied).Error is { } optionError) return optionError;
            VideoPreparedMediaSnapshot snapshot;
            try { snapshot = VideoPreparedMediaSnapshot.Capture(request, media); }
            catch (ArgumentException) { return Error("A source frame could not be resolved.", "start_frame"); }
            using var captured = snapshot;
            foreach (var slot in snapshot.Slots)
            {
                if (slot.ByteLength > 8_000_000 || slot.MimeType is not ("image/png" or "image/jpeg" or "image/webp")) return Error("fal Veo source must be PNG/JPEG/WebP and at most 8,000,000 bytes.", slot.Role);
                var bytes = slot.CopyBytes();
                if (!ImageDimensions.TryRead(bytes, slot.MimeType, out var size) || !HasCompleteImage(bytes, slot.MimeType) || Math.Min(size.Width, size.Height) < 720) return Error("fal Veo source must be a valid image with a shorter side of at least 720 pixels.", slot.Role);
                if (request.Mode is VideoMode.I2V or VideoMode.Interp)
                {
                    var matches = request.AspectRatio == "16:9" ? (long)size.Width * 9 == (long)size.Height * 16 : (long)size.Width * 16 == (long)size.Height * 9;
                    if (!matches) return Error($"fal.ai Veo 3.1 requires a source matching the selected {request.AspectRatio} ratio; this source is {size.Width}x{size.Height}. Supply a matching source or use the Google route.", slot.Role);
                }
            }
            return null;
        }
        private static GenerationError Error(string message, string field) => FalVeoBindingCatalog.Error(message, field);
        private static bool HasCompleteImage(byte[] bytes, string mime)
        {
            if (mime == "image/webp")
            {
                // Windows GDI+ has no built-in WebP decoder. Require a complete RIFF
                // container and an actual bounded image bitstream, not only VP8X dimensions.
                if (bytes.Length < 20 || (long)BitConverter.ToUInt32(bytes, 4) + 8 != bytes.Length) return false;
                bool image = false;
                for (long offset = 12; offset + 8 <= bytes.Length;)
                {
                    int index = (int)offset; long length = BitConverter.ToUInt32(bytes, index + 4);
                    long end = offset + 8 + length + (length & 1);
                    if (end > bytes.Length) return false;
                    var chunk = System.Text.Encoding.ASCII.GetString(bytes, index, 4);
                    if ((chunk == "VP8 " && length >= 10) || (chunk == "VP8L" && length >= 5)) image = true;
                    offset = end;
                    if (offset == bytes.Length) return image;
                }
                return false;
            }
            try
            {
                using var stream = new MemoryStream(bytes, false);
                using var image = System.Drawing.Image.FromStream(stream, false, true);
                return image.Width > 0 && image.Height > 0;
            }
            catch (Exception ex) when (ex is ArgumentException or OutOfMemoryException or System.Runtime.InteropServices.ExternalException) { return false; }
        }
    }
}
