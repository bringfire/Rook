using System;

namespace Rook.Services.Vision.Video.Framing
{
    internal static class VideoFramingGeometry
    {
        public static VideoFramingGeometryResult Create(VideoStillImageInfo source, string resolution, string aspect,
            SourceFramingMode mode, string field)
        {
            if (mode is not (SourceFramingMode.Fit or SourceFramingMode.Fill))
                return new(null, VideoSourcePreparationErrors.Create("source_preparation_failed", "source_framing", detail: "invalid_source"));
            try
            {
                if (source.Orientation < 1 || source.Orientation > 8 || source.BitDepth < 1 || source.BitDepth > 16 ||
                    source.Planes < 1 || source.Planes > 4) throw new OverflowException();
                ValidateSurface(source.Width, source.Height, checked((source.BitDepth * source.Planes + 7) / 8));
                ValidateSurface(source.OrientedWidth, source.OrientedHeight, 4);
                (long tw, long th) = resolution.ToLowerInvariant() switch {
                    "720p" => (1280, 720), "1080p" => (1920, 1080), "4k" => (3840, 2160),
                    _ => throw new ArgumentException("Unsupported resolution.")
                };
                if (aspect == "9:16") (tw, th) = (th, tw);
                else if (aspect != "16:9") throw new ArgumentException("Unsupported aspect.");
                long w = source.OrientedWidth, h = source.OrientedHeight;
                bool byWidth = mode == SourceFramingMode.Fit ? checked(tw * h) <= checked(th * w) : checked(tw * h) >= checked(th * w);
                long sw, sh;
                if (byWidth) { sw = tw; sh = Scale(checked(h * tw), w, mode); }
                else { sh = th; sw = Scale(checked(w * th), h, mode); }
                // Source -> orientation -> RGBA background/foreground/composite
                // -> scale -> pad/crop -> final RGB/YUV. All materialized rasters.
                ValidateSurface(sw, sh, 4);
                ValidateSurface(tw, th, 4);
                long x = mode == SourceFramingMode.Fit ? (tw - sw) / 2 : (sw - tw) / 2;
                long y = mode == SourceFramingMode.Fit ? (th - sh) / 2 : (sh - th) / 2;
                return new(new((int)tw, (int)th, (int)sw, (int)sh, (int)x, (int)y, sw > w || sh > h), null);
            }
            catch (Exception ex) when (ex is OverflowException or ArgumentException)
            { return new(null, VideoSourcePreparationErrors.Create("source_preparation_failed", field, mode.Wire(), "render_limits_exceeded")); }
        }
        private static long Scale(long product, long divisor, SourceFramingMode mode)
            => mode == SourceFramingMode.Fit ? Math.Max(1, product / divisor) : checked((product + divisor - 1) / divisor);
        private static void ValidateSurface(long width, long height, int bytesPerPixel)
        {
            if (width <= 0 || height <= 0 || width > VideoPreparationLimits.RasterEdge ||
                height > VideoPreparationLimits.RasterEdge || checked(width * height) > VideoPreparationLimits.RasterPixels)
                throw new OverflowException();
            _ = checked(width * height * bytesPerPixel);
        }
    }
}
