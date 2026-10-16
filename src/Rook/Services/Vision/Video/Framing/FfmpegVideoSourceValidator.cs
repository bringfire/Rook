using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.Video.Framing
{
    // Legacy fal sends original bytes, so framing's pixel decode never ran.
    // Decode the complete default image in the same contained process profile;
    // a tiny discarded output proves decoding without copying a decoded raster
    // into managed memory. The original encoded bytes remain untouched.
    internal sealed class FfmpegVideoSourceValidator
    {
        private readonly IFramingProcessRunner _runner;
        private readonly Func<string?> _bundledPath;
        public FfmpegVideoSourceValidator(IFramingProcessRunner? runner = null, Func<string?>? bundledPath = null)
        { _runner = runner ?? new WindowsFramingProcessRunner(); _bundledPath = bundledPath ?? FfmpegBundledBinaryLocator.GetInstalledFfmpegPath; }

        public async Task<GenerationError?> ValidateAsync(VideoPreparedMediaSlot slot, VideoPreparationLease phase, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var inspected = VideoStillImageInspector.Inspect(slot.Buffer, slot.Role, allowLegacyPngAnimation: true);
            if (inspected.Error != null) return inspected.Error;
            var info = inspected.Info!;
            if (info.MimeType != slot.MimeType || slot.ByteLength > VideoPreparationLimits.UploadBytes) return Failed("invalid_source");
            if (info.Width > VideoPreparationLimits.RasterEdge || info.Height > VideoPreparationLimits.RasterEdge ||
                (long)info.Width * info.Height > VideoPreparationLimits.RasterPixels) return Failed("render_limits_exceeded");
            var verified = VerifiedFramingRenderer.Resolve(_bundledPath());
            if (verified.Renderer == null) return Failed(verified.FailureDetail!);
            using var executable = verified.Renderer;
            var root = Path.Combine(Path.GetTempPath(), "rook-video-source-validation-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                string codec = info.MimeType == "image/png" ? "png" : info.MimeType == "image/jpeg" ? "mjpeg" : "webp";
                string input = Path.Combine(root, "source." + (codec == "mjpeg" ? "jpg" : codec)), output = Path.Combine(root, "decoded.png");
                using (var source = slot.OpenRead())
                using (var file = new FileStream(input, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1, true))
                using (phase.Buffers.Reserve(VideoPreparationLimits.ChunkBytes))
                    await source.CopyToAsync(file, VideoPreparationLimits.ChunkBytes, ct).ConfigureAwait(false);
                var run = await _runner.RunAsync(new(executable.Path, Arguments(input, output, codec), root, output), ct).ConfigureAwait(false);
                if (!run.EnforcementEstablished) return Failed("enforcement_unavailable");
                if (!run.Success) return Failed(run.FailureDetail is "render_limits_exceeded" or "enforcement_unavailable" ? run.FailureDetail : "invalid_source");
                // -loglevel error and strict decoder flags: an error-concealed frame
                // must not become proof of valid compressed pixels.
                if (!string.IsNullOrWhiteSpace(run.Diagnostics)) return Failed("invalid_source");
                using var opened = new FileStream(output, FileMode.Open, FileAccess.Read, FileShare.Read, 1, true);
                if (opened.Length <= 0 || opened.Length > 4096) return Failed("invalid_output");
                var read = await BoundedVideoSourceReader.ReadOutputAsync(opened, opened.Length, slot.Role, phase, ct).ConfigureAwait(false);
                if (read.Buffer == null) return read.Error;
                using var decoded = read.Buffer;
                var complete = VideoStillImageInspector.Inspect(decoded, slot.Role);
                if (complete.Info is not { MimeType: "image/png", Width: 1, Height: 1 }) return Failed("invalid_output");
                ct.ThrowIfCancellationRequested();
                return null;
            }
            catch (OperationCanceledException) { throw; }
            catch (VideoPreparationBusyException) { return VideoSourcePreparationErrors.Busy(slot.Role); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or OverflowException)
            { return Failed("invalid_source"); }
            finally { Directory.Delete(root, true); }
            GenerationError Failed(string detail) => VideoSourcePreparationErrors.Create("source_preparation_failed", slot.Role, detail: detail);
        }
        internal static IReadOnlyList<string> Arguments(string input, string output, string codec) => new[] {
            "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-cpuflags", "0", "-fflags", "+bitexact",
            "-err_detect", "crccheck+bitstream+buffer+explode", "-noautorotate", "-threads", "1", "-f", "image2", "-c:v", codec, "-i", input,
            "-filter_threads", "1", "-vf", "scale=1:1:flags=bilinear,format=rgb24,sidedata=mode=delete,metadata=mode=delete",
            "-an", "-sn", "-dn", "-frames:v", "1", "-map_metadata", "-1", "-threads:v", "1", "-c:v", "png", "-f", "image2", "-update", "1", "-y", output
        };
    }
}
