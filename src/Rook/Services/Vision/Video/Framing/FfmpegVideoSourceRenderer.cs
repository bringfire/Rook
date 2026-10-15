using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.Video.Framing
{
    internal interface IVideoSourceRenderer
    {
        string? VerifyProfile();
        Task<VideoPreparedSourceResult> RenderAsync(VideoFrozenBuffer original, VideoStillImageInfo info,
            VideoFramingRecipe recipe, VideoPreparationLease lease, CancellationToken ct);
    }
    internal sealed class FfmpegVideoSourceRenderer : IVideoSourceRenderer
    {
        private readonly IFramingProcessRunner _runner;
        private readonly Func<string?> _bundledPath;
        public FfmpegVideoSourceRenderer(IFramingProcessRunner? runner = null, Func<string?>? bundledPath = null)
        { _runner = runner ?? new WindowsFramingProcessRunner(); _bundledPath = bundledPath ?? FfmpegBundledBinaryLocator.GetInstalledFfmpegPath; }
        public string? VerifyProfile()
        { var result = VerifiedFramingRenderer.Resolve(_bundledPath()); using var held = result.Renderer; return result.FailureDetail; }
        public async Task<VideoPreparedSourceResult> RenderAsync(VideoFrozenBuffer original, VideoStillImageInfo info,
            VideoFramingRecipe recipe, VideoPreparationLease lease, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            const string field = "source_framing";
            var inspected = VideoStillImageInspector.Inspect(original, field);
            if (inspected.Error != null) return new(null, inspected.Error);
            if (inspected.Info != info) return Failed("invalid_source");
            var layout = recipe.Layout;
            var resolution = layout.CanvasWidth > layout.CanvasHeight ? layout.CanvasHeight : layout.CanvasWidth;
            string? resolutionName = resolution switch { 720 => "720p", 1080 => "1080p", 2160 => "4k", _ => null };
            if (resolutionName == null) return Failed("render_limits_exceeded");
            var geometry = VideoFramingGeometry.Create(info, resolutionName, layout.CanvasWidth > layout.CanvasHeight ? "16:9" : "9:16", recipe.Mode, field);
            if (geometry.Error != null) return new(null, geometry.Error);
            if (geometry.Layout != layout || recipe.RendererSha256 != VideoFramingRendererProfile.Sha256) return Failed("renderer_profile_mismatch");
            var verified = VerifiedFramingRenderer.Resolve(_bundledPath());
            if (verified.Renderer == null) return Failed(verified.FailureDetail!);
            using var executable = verified.Renderer;
            var root = Path.Combine(Path.GetTempPath(), "rook-video-framing-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                string input = Path.Combine(root, info.MimeType == "image/png" ? "source.png" : info.MimeType == "image/webp" ? "source.webp" : "source.jpg");
                using (var source = original.OpenRead())
                using (var target = new FileStream(input, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1, true))
                using (lease.Buffers.Reserve(VideoPreparationLimits.ChunkBytes))
                    await source.CopyToAsync(target, VideoPreparationLimits.ChunkBytes, ct).ConfigureAwait(false);
                long peak = 0;
                foreach (var encoding in new (string Name, int? Q)[] { ("png", null), ("mjpeg", 2), ("mjpeg", 3), ("mjpeg", 4) })
                {
                    ct.ThrowIfCancellationRequested();
                    string output = Path.Combine(root, encoding.Name == "png" ? "output.png" : "output.jpg");
                    var finalRecipe = recipe with { Encoding = encoding.Name, Quantizer = encoding.Q };
                    var run = await _runner.RunAsync(new(executable.Path, Arguments(input, output, finalRecipe), root, output), ct).ConfigureAwait(false);
                    peak = Math.Max(peak, run.PeakJobChargeBytes);
                    if (!run.Success) return Failed(run.FailureDetail ?? "renderer_failed");
                    using (var opened = new FileStream(output, FileMode.Open, FileAccess.Read, FileShare.Read, 1, true))
                    {
                        long length = opened.Length;
                        // Inspect length on the held handle BEFORE allocating/reading the encoded payload.
                        if (length <= VideoPreparationLimits.UploadBytes)
                        {
                            var read = await BoundedVideoSourceReader.ReadOutputAsync(opened, length, field, lease, ct).ConfigureAwait(false);
                            if (read.Buffer == null) return new(null, read.Error);
                            bool accepted = false;
                            try
                            {
                                var metadata = VideoStillImageInspector.Inspect(read.Buffer, field);
                                if (metadata.Info is not { } outputInfo || outputInfo.Width != layout.CanvasWidth || outputInfo.Height != layout.CanvasHeight ||
                                    outputInfo.Orientation != 1 || outputInfo.MimeType != (encoding.Name == "png" ? "image/png" : "image/jpeg"))
                                    return Failed("invalid_output");
                                ct.ThrowIfCancellationRequested();
                                var prepared = new VideoPreparedSource(read.Buffer, finalRecipe, peak);
                                accepted = true; return new(prepared, null);
                            }
                            finally { if (!accepted) read.Buffer.Dispose(); }
                        }
                    }
                    File.Delete(output);
                }
                return Failed("encoded_output_too_large");
            }
            catch (OperationCanceledException) { throw; }
            catch (VideoPreparationBusyException) { return new(null, VideoSourcePreparationErrors.Busy(field)); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or OverflowException)
            { return Failed("renderer_failed"); }
            finally { Directory.Delete(root, true); }
            VideoPreparedSourceResult Failed(string detail) => new(null, VideoSourcePreparationErrors.Create("source_preparation_failed", field, recipe.Mode.Wire(), detail));
        }
        internal static IReadOnlyList<string> Arguments(string input, string output, VideoFramingRecipe recipe)
        {
            var layout = recipe.Layout;
            string orientation = recipe.Source.Orientation switch { 2 => "hflip,", 3 => "hflip,vflip,", 4 => "vflip,", 5 => "transpose=clock,hflip,", 6 => "transpose=clock,", 7 => "transpose=clock,vflip,", 8 => "transpose=cclock,", _ => "" };
            string graph = "[0:v]" + orientation + "format=rgba,split[foreground][background];" +
                "[background]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:replace=1[black];" +
                "[black][foreground]overlay=alpha=straight:format=rgb,format=rgba," +
                $"scale={layout.ScaledWidth}:{layout.ScaledHeight}:flags=lanczos+accurate_rnd+bitexact," +
                (recipe.Mode == SourceFramingMode.Fit ? $"pad={layout.CanvasWidth}:{layout.CanvasHeight}:{layout.OffsetX}:{layout.OffsetY}:color=black," :
                    $"crop={layout.CanvasWidth}:{layout.CanvasHeight}:{layout.OffsetX}:{layout.OffsetY},") +
                "setsar=1,setparams=range=full:color_primaries=unknown:color_trc=unknown:colorspace=unknown,sidedata=mode=delete,metadata=mode=delete,format=" + (recipe.Encoding == "png" ? "rgb24" : "yuvj444p") + "[out]";
            var args = new List<string> { "-nostdin", "-hide_banner", "-loglevel", "error", "-cpuflags", "0", "-fflags", "+bitexact", "-noautorotate", "-threads", "1",
                "-i", input, "-filter_threads", "1", "-filter_complex_threads", "1", "-filter_complex", graph, "-map", "[out]", "-an", "-sn", "-dn", "-frames:v", "1",
                "-map_metadata", "-1", "-flags:v", "+bitexact", "-threads:v", "1", "-c:v", recipe.Encoding };
            if (recipe.Quantizer is int q) args.AddRange(new[] { "-q:v", q.ToString(System.Globalization.CultureInfo.InvariantCulture) });
            args.AddRange(new[] { "-f", "image2", "-update", "1", "-y", output });
            return args;
        }
    }
}
