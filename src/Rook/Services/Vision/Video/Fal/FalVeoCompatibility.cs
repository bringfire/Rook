using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video.Fal
{
    internal static class FalVeoCompatibility
    {
        // Quote eligibility is metadata-only. Actual fal upload must also call
        // ValidateForUploadAsync: omitted framing has no prior pixel decode.
        internal static async Task<GenerationError?> ValidateForUploadAsync(VideoRequestIntent intent, FalVeoBinding binding,
            VideoPreparedMediaSnapshot snapshot, VideoPreparationLease phase, FfmpegVideoSourceValidator decoder, CancellationToken ct)
        {
            var error = ValidateMetadata(intent, binding, snapshot);
            if (error != null || intent.Request.SourceFraming != null) return error;
            var checkedSources = new HashSet<string>(StringComparer.Ordinal);
            foreach (var slot in snapshot.Slots)
            {
                ct.ThrowIfCancellationRequested();
                if (!checkedSources.Add(slot.MimeType + ":" + slot.Sha256)) continue;
                error = await decoder.ValidateAsync(slot, phase, ct).ConfigureAwait(false);
                if (error != null) return error;
            }
            return null;
        }
        public static GenerationError? ValidateMetadata(VideoRequestIntent intent, FalVeoBinding binding, IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            try { using var snapshot = VideoPreparedMediaSnapshot.Capture(intent.Request, media); return ValidateMetadata(intent, binding, snapshot); }
            catch (ArgumentException) { return Error("A source frame could not be resolved.", "start_frame"); }
        }
        public static GenerationError? ValidateMetadata(VideoRequestIntent intent, FalVeoBinding binding, VideoPreparedMediaSnapshot snapshot)
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
            foreach (var slot in snapshot.Slots)
            {
                if (slot.ByteLength > 8_000_000 || slot.MimeType is not ("image/png" or "image/jpeg" or "image/webp")) return Error("fal Veo source must be PNG/JPEG/WebP and at most 8,000,000 bytes.", slot.Role);
                var inspected = VideoStillImageInspector.Inspect(slot.Buffer, slot.Role, allowLegacyPngAnimation: request.SourceFraming == null);
                if (inspected.Info is not { } info)
                    return Error("fal Veo source must be a valid still image with a shorter side of at least 720 pixels.", slot.Role);
                if (Math.Min(info.OrientedWidth, info.OrientedHeight) < 720)
                    return request.SourceFraming == null && request.Mode is VideoMode.I2V or VideoMode.Interp
                        ? VideoSourcePreparationErrors.Create("framing_choice_required", "source_framing")
                        : Error("fal Veo source must have a shorter side of at least 720 pixels.", slot.Role);
                var size = (Width: info.OrientedWidth, Height: info.OrientedHeight);
                if (request.SourceFraming != null)
                {
                    var target = request.Resolution switch { "720p" => (W: 1280, H: 720), "1080p" => (W: 1920, H: 1080), "4k" => (W: 3840, H: 2160), _ => (W: 0, H: 0) };
                    if (request.AspectRatio == "9:16") target = (target.H, target.W);
                    if (size.Width != target.W || size.Height != target.H || info.Orientation != 1)
                        return Error("Prepared source does not match the selected video canvas. Retry preparation.", slot.Role);
                }
                if (request.Mode is VideoMode.I2V or VideoMode.Interp)
                {
                    var matches = request.AspectRatio == "16:9" ? (long)size.Width * 9 == (long)size.Height * 16 : (long)size.Width * 16 == (long)size.Height * 9;
                    if (!matches) return VideoSourcePreparationErrors.Create("framing_choice_required", "source_framing");
                }
            }
            return null;
        }
        private static GenerationError Error(string message, string field) => FalVeoBindingCatalog.Error(message, field);
    }
}
