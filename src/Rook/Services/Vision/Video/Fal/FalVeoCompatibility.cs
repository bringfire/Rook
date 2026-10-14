using System;
using System.Collections.Generic;
using System.Linq;
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
            foreach (var slot in snapshot.Slots)
            {
                if (slot.ByteLength > 8_000_000 || slot.MimeType is not ("image/png" or "image/jpeg" or "image/webp")) return Error("fal Veo source must be PNG/JPEG/WebP and at most 8,000,000 bytes.", slot.Role);
                if (!ImageDimensions.TryRead(slot.CopyBytes(), slot.MimeType, out var size) || Math.Min(size.Width, size.Height) < 720) return Error("fal Veo source must be a valid image with a shorter side of at least 720 pixels.", slot.Role);
                if (request.Mode is VideoMode.I2V or VideoMode.Interp)
                {
                    var matches = request.AspectRatio == "16:9" ? (long)size.Width * 9 == (long)size.Height * 16 : (long)size.Width * 16 == (long)size.Height * 9;
                    if (!matches) return Error($"fal.ai Veo 3.1 requires a source matching the selected {request.AspectRatio} ratio; this source is {size.Width}x{size.Height}. Supply a matching source or use the Google route.", slot.Role);
                }
            }
            return null;
        }
        private static GenerationError Error(string message, string field) => FalVeoBindingCatalog.Error(message, field);
    }
}
