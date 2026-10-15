using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed class VideoPreparedSource : IDisposable
    {
        public VideoFrozenBuffer Bytes { get; }
        public VideoFramingRecipe Recipe { get; }
        public string MimeType => Recipe.Encoding == "png" ? "image/png" : "image/jpeg";
        public long PeakJobChargeBytes { get; }
        public VideoPreparedSource(VideoFrozenBuffer bytes, VideoFramingRecipe recipe, long peakJobChargeBytes)
        { Bytes = bytes; Recipe = recipe; PeakJobChargeBytes = peakJobChargeBytes; }
        public void Dispose() => Bytes.Dispose();
    }
    internal sealed record VideoPreparedSourceResult(VideoPreparedSource? Source, GenerationError? Error);
}
