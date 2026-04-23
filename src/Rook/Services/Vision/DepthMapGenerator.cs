using System;
using System.Drawing;
using System.Drawing.Imaging;
using Rhino;
using Rhino.Display;

namespace Rook.Services.Vision
{
    /// <summary>
    /// Result of a depth-map capture. Carries the bitmap (caller disposes),
    /// the resolved mode name actually used (Arctic when available, or
    /// "fallback" when the current display mode was used), and the image
    /// dimensions.
    /// </summary>
    public sealed class DepthMapResult : IDisposable
    {
        public Bitmap? Bitmap { get; }
        public string ResolvedMode { get; }
        public int Width { get; }
        public int Height { get; }

        public DepthMapResult(Bitmap? bitmap, string resolvedMode, int width, int height)
        {
            Bitmap = bitmap;
            ResolvedMode = resolvedMode;
            Width = width;
            Height = height;
        }

        public void Dispose() => Bitmap?.Dispose();
    }

    /// <summary>
    /// Depth-map capture from a Rhino viewport. Uses the "Arctic" display
    /// mode when available (gives a depth-like flat shading) and falls
    /// back to the current display mode otherwise; either way the capture
    /// is converted to grayscale.
    ///
    /// Tier 3 viewport-state discipline applies — full <c>ViewportInfo</c>
    /// snapshot before mutation, restored via both
    /// <c>SetViewProjection</c> and <c>SetCameraLocations</c> in a
    /// finally block (see
    /// <c>ViewportHandler.CaptureTier3</c> for the reasoning — a single
    /// <c>SetViewProjection</c> is insufficient to pin camera target). SA_Banana's
    /// original only restored the display mode; Rook requires full state
    /// restore.
    /// </summary>
    public static class DepthMapGenerator
    {
        /// <summary>
        /// Generate a depth map from a viewport. Callers are responsible
        /// for choosing the view (use <see cref="DocumentContext"/> to pin
        /// the target document), and for disposing the returned bitmap.
        /// </summary>
        /// <param name="view">Rhino view to capture from.</param>
        /// <param name="maxEdge">Maximum edge length; larger viewports scale down.</param>
        public static DepthMapResult GenerateDepthMap(RhinoView view, int maxEdge = 1024)
        {
            if (view == null)
            {
                return new DepthMapResult(null, "none", 0, 0);
            }

            var vp = view.ActiveViewport;

            // Snapshot full viewport projection BEFORE any mutation.
            var savedProjection = new Rhino.DocObjects.ViewportInfo(vp);
            var savedDisplayMode = vp.DisplayMode;

            var size = view.Bounds.Size;
            var scale = Math.Min(
                maxEdge / (float)size.Width,
                maxEdge / (float)size.Height);
            scale = Math.Min(scale, 1.0f); // never upscale
            var captureSize = new Size(
                (int)(size.Width * scale),
                (int)(size.Height * scale));

            string resolvedMode = "fallback";

            try
            {
                var arcticMode = DisplayModeDescription.FindByName("Arctic");

                if (arcticMode != null)
                {
                    vp.DisplayMode = arcticMode;
                    view.Redraw();
                    resolvedMode = "Arctic";

                    using var capture = view.CaptureToBitmap(captureSize);
                    if (capture != null)
                    {
                        var gray = ConvertToGrayscale(capture);
                        return new DepthMapResult(
                            gray, resolvedMode, gray.Width, gray.Height);
                    }
                }

                // Fallback: capture current view and convert to grayscale.
                using var fallbackCapture = view.CaptureToBitmap(captureSize);
                if (fallbackCapture != null)
                {
                    var gray = ConvertToGrayscale(fallbackCapture);
                    return new DepthMapResult(
                        gray, resolvedMode, gray.Width, gray.Height);
                }

                return new DepthMapResult(null, resolvedMode, 0, 0);
            }
            finally
            {
                // Full state restore, matching ViewportHandler.CaptureTier3.
                // SetViewProjection alone is insufficient — see PR #94
                // commit 8408764 for the target-restore gotcha.
                try
                {
                    vp.SetViewProjection(savedProjection, true);
                    vp.SetCameraLocations(
                        savedProjection.TargetPoint,
                        savedProjection.CameraLocation);
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine(
                        $"Rook Vision: depth-map projection restore failed: {ex.Message}");
                }

                try
                {
                    if (savedDisplayMode != null && vp.DisplayMode?.Id != savedDisplayMode.Id)
                    {
                        vp.DisplayMode = savedDisplayMode;
                    }
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine(
                        $"Rook Vision: depth-map display-mode restore failed: {ex.Message}");
                }

                try { view.Redraw(); } catch { /* swallow */ }
            }
        }

        private static Bitmap ConvertToGrayscale(Bitmap source)
        {
            var result = new Bitmap(source.Width, source.Height, PixelFormat.Format24bppRgb);

            using var g = Graphics.FromImage(result);
            var colorMatrix = new ColorMatrix(new[]
            {
                new float[] { 0.3f,  0.3f,  0.3f,  0, 0 },
                new float[] { 0.59f, 0.59f, 0.59f, 0, 0 },
                new float[] { 0.11f, 0.11f, 0.11f, 0, 0 },
                new float[] { 0,     0,     0,     1, 0 },
                new float[] { 0,     0,     0,     0, 1 }
            });
            using var attributes = new ImageAttributes();
            attributes.SetColorMatrix(colorMatrix);

            g.DrawImage(source,
                new Rectangle(0, 0, source.Width, source.Height),
                0, 0, source.Width, source.Height,
                GraphicsUnit.Pixel,
                attributes);

            return result;
        }
    }
}
